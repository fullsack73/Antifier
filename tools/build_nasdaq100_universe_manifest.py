#!/usr/bin/env python3
"""Build dated Nasdaq-100 membership events from a pinned history page."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from universe_manifest import (  # noqa: E402
    normalize_universe_manifest,
    universe_manifest_digest,
    universe_snapshot,
)


SOURCE_URL = (
    "https://en.wikipedia.org/w/index.php?"
    "title=List_of_NASDAQ-100_companies&oldid=1365378481"
)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _clean_ticker(value):
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def parse_nasdaq100_history(source_html):
    """Parse the pinned current-component and component-change tables."""
    html = Path(source_html).read_text(encoding="utf-8")
    tables = pd.read_html(StringIO(html))
    if len(tables) < 2:
        raise ValueError("Nasdaq-100 page has an unexpected table layout")

    current = tables[0].copy()
    changes = tables[1].copy()
    if "Ticker" not in current.columns:
        raise ValueError("Nasdaq-100 current-component table lacks Ticker")
    expected_change_columns = [
        ("Date", "Date"),
        ("Added", "Ticker"),
        ("Added", "Security"),
        ("Removed", "Ticker"),
        ("Removed", "Security"),
        ("Reason", "Reason"),
    ]
    if list(changes.columns) != expected_change_columns:
        raise ValueError("Nasdaq-100 component-change columns changed")

    current_tickers = sorted({
        _clean_ticker(value) for value in current["Ticker"]
        if _clean_ticker(value)
    })
    if not 100 <= len(current_tickers) <= 110:
        raise ValueError(
            "Nasdaq-100 current snapshot has an unexpected size: "
            f"{len(current_tickers)}"
        )

    changes.columns = [
        "effective_date",
        "added_ticker",
        "added_security",
        "removed_ticker",
        "removed_security",
        "reason",
    ]
    changes["effective_date"] = pd.to_datetime(
        changes["effective_date"],
        errors="coerce",
    )
    if changes["effective_date"].isna().any():
        raise ValueError("Nasdaq-100 change table has invalid dates")
    for column in ("added_ticker", "removed_ticker"):
        changes[column] = changes[column].map(_clean_ticker)
    if (
        (changes["added_ticker"] == "")
        & (changes["removed_ticker"] == "")
    ).any():
        raise ValueError("Nasdaq-100 change row has no ticker action")
    return current_tickers, changes.sort_values(
        "effective_date",
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)


def build_membership_events(
    current_tickers,
    changes,
    start_date,
    end_date,
):
    """Reconstruct a closed historical interval from the current snapshot."""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if start >= end:
        raise ValueError("Nasdaq-100 start date must precede end date")

    expected_size = len(set(current_tickers))
    size_tolerance = max(2, round(expected_size * 0.1))
    minimum_size = expected_size - size_tolerance
    maximum_size = expected_size + size_tolerance
    state = set(current_tickers)
    relevant = changes.loc[changes["effective_date"] > start].copy()
    for effective_date, group in relevant.groupby(
        "effective_date",
        sort=False,
    ):
        if effective_date <= end:
            continue
        for row in group.itertuples(index=False):
            if row.added_ticker:
                if row.added_ticker not in state:
                    raise ValueError(
                        "Cannot reverse Nasdaq-100 addition absent from "
                        f"current state: {effective_date.date()} "
                        f"{row.added_ticker}"
                    )
                state.remove(row.added_ticker)
            if row.removed_ticker:
                state.add(row.removed_ticker)

    end_state = set(state)
    reverse_interval = relevant.loc[
        relevant["effective_date"] <= end
    ]
    for effective_date, group in reverse_interval.groupby(
        "effective_date",
        sort=False,
    ):
        for row in group.itertuples(index=False):
            if row.added_ticker:
                if row.added_ticker not in state:
                    raise ValueError(
                        "Cannot reverse Nasdaq-100 addition absent from "
                        f"interval state: {effective_date.date()} "
                        f"{row.added_ticker}"
                    )
                state.remove(row.added_ticker)
            if row.removed_ticker:
                state.add(row.removed_ticker)

    if not minimum_size <= len(state) <= maximum_size:
        raise ValueError(
            "Nasdaq-100 reconstructed start snapshot has unexpected size: "
            f"{len(state)}"
        )

    rows = [
        {
            "effective_date": start,
            "ticker": ticker,
            "in_universe": True,
        }
        for ticker in sorted(state)
    ]
    for row in changes.sort_values(
        "effective_date",
        kind="stable",
    ).itertuples(index=False):
        if not start < row.effective_date <= end:
            continue
        if (
            row.added_ticker
            and row.added_ticker == row.removed_ticker
        ):
            continue
        if row.removed_ticker:
            rows.append({
                "effective_date": row.effective_date,
                "ticker": row.removed_ticker,
                "in_universe": False,
            })
        if row.added_ticker:
            rows.append({
                "effective_date": row.effective_date,
                "ticker": row.added_ticker,
                "in_universe": True,
            })

    events = normalize_universe_manifest(rows)
    if universe_snapshot(events, end) != sorted(end_state):
        raise ValueError("Nasdaq-100 forward reconstruction failed")
    for effective_date in sorted(
        changes.loc[
            (changes["effective_date"] > start)
            & (changes["effective_date"] <= end),
            "effective_date",
        ].unique()
    ):
        count = len(universe_snapshot(events, effective_date))
        if not minimum_size <= count <= maximum_size:
            raise ValueError(
                "Nasdaq-100 snapshot has unexpected size: "
                f"{pd.Timestamp(effective_date).date()} {count}"
            )
    return events


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-html", required=True)
    parser.add_argument("--start", default="2016-12-31")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--output", required=True)
    parser.add_argument("--provenance-output")
    args = parser.parse_args(argv)

    try:
        source_path = Path(args.source_html).expanduser().resolve()
        current, changes = parse_nasdaq100_history(source_path)
        events = build_membership_events(
            current,
            changes,
            args.start,
            args.end,
        )

        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = events.copy()
        serializable["effective_date"] = serializable[
            "effective_date"
        ].dt.strftime("%Y-%m-%d")
        serializable.to_csv(output_path, index=False)
        provenance_path = (
            Path(args.provenance_output).expanduser().resolve()
            if args.provenance_output
            else output_path.with_suffix(".provenance.json")
        )
        provenance_path.write_text(
            json.dumps(
                {
                    "source": SOURCE_URL,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "universe_policy": (
                        "current Nasdaq-100 snapshot reverse-reconstructed "
                        "with dated component changes"
                    ),
                    "survivorship_policy": "historical_constituents",
                    "source_quality": (
                        "secondary public history; pinned revision, table "
                        "schema, forward reconstruction, and snapshot size "
                        "checked"
                    ),
                    "source_license": "CC BY-SA 4.0",
                    "source_attribution": (
                        "Wikipedia contributors, List of NASDAQ-100 companies"
                    ),
                    "raw_source_file": str(source_path),
                    "raw_source_sha256": _sha256(source_path),
                    "manifest_file": str(output_path),
                    "manifest_sha256": universe_manifest_digest(events),
                    "event_count": int(len(events)),
                    "ticker_count": int(events["ticker"].nunique()),
                    "start_date": args.start,
                    "end_date": args.end,
                    "start_snapshot_count": len(
                        universe_snapshot(events, args.start)
                    ),
                    "end_snapshot_count": len(
                        universe_snapshot(events, args.end)
                    ),
                    "promotion_note": (
                        "Membership is point-in-time for the declared "
                        "interval; price and issuer identity coverage must "
                        "pass separate gates."
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {provenance_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
