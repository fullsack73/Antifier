#!/usr/bin/env python3
"""Build dated DJIA membership events from a pinned historical HTML page."""

import argparse
import hashlib
import json
import re
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
    snapshots_to_membership_events,
    universe_manifest_digest,
    universe_snapshot,
)


SOURCE_URL = (
    "https://en.wikipedia.org/w/index.php?"
    "title=Historical_components_of_the_Dow_Jones_Industrial_Average"
    "&oldid=1362314398"
)
SOURCE_DATES = (
    "2026-06-29",
    "2024-11-08",
    "2024-02-26",
    "2020-08-31",
    "2020-04-06",
    "2019-04-02",
    "2018-06-26",
    "2017-09-01",
    "2015-03-19",
    "2013-09-23",
    "2012-09-24",
    "2009-06-08",
    "2008-09-22",
    "2008-02-19",
    "2005-11-21",
)
COMPANY_TICKERS = {
    "3M Company": "MMM",
    "AT&T Inc.": "T",
    "Alcoa Inc.": "AA",
    "Altria Group Incorporated": "MO",
    "Amazon.com, Inc.": "AMZN",
    "American Express Company": "AXP",
    "American International Group, Inc.": "AIG",
    "Amgen Inc.": "AMGN",
    "Apple Inc.": "AAPL",
    "Bank of America Corporation": "BAC",
    "Caterpillar Inc.": "CAT",
    "Chevron Corporation": "CVX",
    "Cisco Systems, Inc.": "CSCO",
    "Citigroup Inc.": "C",
    "Dow Inc.": "DOW",
    "DowDuPont Inc.": "DWDP",
    "E.I. du Pont de Nemours & Company": "DD",
    "Exxon Mobil Corporation": "XOM",
    "General Electric Company": "GE",
    "General Motors Corporation": "GM",
    "Hewlett-Packard Company": "HPQ",
    "Honeywell International Inc.": "HON",
    "Intel Corporation": "INTC",
    "International Business Machines Corporation": "IBM",
    "JPMorgan Chase & Co.": "JPM",
    "Johnson & Johnson": "JNJ",
    "Kraft Foods Inc.": "KFT",
    "McDonald's Corporation": "MCD",
    "Merck & Co., Inc.": "MRK",
    "Microsoft Corporation": "MSFT",
    "Nike, Inc.": "NKE",
    "Nvidia Corporation": "NVDA",
    "Pfizer Inc.": "PFE",
    "Raytheon Technologies Corporation": "RTX",
    "Salesforce, Inc.": "CRM",
    "The Boeing Company": "BA",
    "The Coca-Cola Company": "KO",
    "The Goldman Sachs Group, Inc.": "GS",
    "The Home Depot, Inc.": "HD",
    "The Procter & Gamble Company": "PG",
    "The Sherwin-Williams Company": "SHW",
    "The Travelers Companies, Inc.": "TRV",
    "The Walt Disney Company": "DIS",
    "United Technologies Corporation": "UTX",
    "UnitedHealth Group Inc.": "UNH",
    "UnitedHealth Group Incorporated": "UNH",
    "Verizon Communications Inc.": "VZ",
    "Visa Inc.": "V",
    "Wal-Mart Stores, Inc.": "WMT",
    "Walgreens Boots Alliance, Inc.": "WBA",
    "Walmart Inc.": "WMT",
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _clean_company_name(value):
    value = str(value).strip()
    if (
        not value
        or value == "nan"
        or "↓" in value
        or value.startswith("Dropped from Average")
    ):
        return None
    value = re.sub(r"\s*[↑†]\s*", " ", value)
    value = re.sub(r"\s*\(formerly.*$", "", value, flags=re.IGNORECASE)
    return value.strip()


def parse_dow_snapshots(source_html, end_date=None):
    """Parse pinned Wikipedia full-composition tables into ticker snapshots."""
    html = Path(source_html).read_text(encoding="utf-8")
    tables = pd.read_html(StringIO(html))
    if len(tables) < len(SOURCE_DATES) + 1:
        raise ValueError("Historical DJIA page has an unexpected table layout")
    end = None if end_date is None else pd.Timestamp(end_date)
    rows = []
    for table_index, effective_date in enumerate(SOURCE_DATES, start=1):
        date = pd.Timestamp(effective_date)
        if end is not None and date > end:
            continue
        members = []
        for raw in tables[table_index].astype(str).to_numpy().ravel():
            name = _clean_company_name(raw)
            if name is None:
                continue
            ticker = COMPANY_TICKERS.get(name)
            if ticker is None:
                raise ValueError(
                    f"No ticker mapping for DJIA company name: {name}"
                )
            members.append(ticker)
        members = sorted(set(members))
        if len(members) != 30:
            raise ValueError(
                f"DJIA snapshot {effective_date} has {len(members)} members"
            )
        rows.extend(
            {
                "effective_date": date,
                "ticker": ticker,
            }
            for ticker in members
        )
    return pd.DataFrame(rows).sort_values(
        ["effective_date", "ticker"]
    ).reset_index(drop=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-html", required=True)
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--output", required=True)
    parser.add_argument("--provenance-output")
    args = parser.parse_args(argv)

    try:
        source_path = Path(args.source_html).expanduser().resolve()
        snapshots = parse_dow_snapshots(source_path, end_date=args.end)
        events = snapshots_to_membership_events(snapshots)
        for date, group in snapshots.groupby("effective_date"):
            actual = universe_snapshot(events, date)
            expected = sorted(group["ticker"].tolist())
            if actual != expected:
                raise ValueError(
                    f"Membership event reconstruction failed at {date.date()}"
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
                        "full dated DJIA constituent snapshots reconstructed "
                        "to membership events"
                    ),
                    "survivorship_policy": "historical_constituents",
                    "source_quality": (
                        "secondary public history; pinned revision and "
                        "snapshot-size checked"
                    ),
                    "source_license": "CC BY-SA 4.0",
                    "source_attribution": (
                        "Wikipedia contributors, Historical components of "
                        "the Dow Jones Industrial Average"
                    ),
                    "raw_source_file": str(source_path),
                    "raw_source_sha256": _sha256(source_path),
                    "manifest_file": str(output_path),
                    "manifest_sha256": universe_manifest_digest(events),
                    "snapshot_count": int(
                        snapshots["effective_date"].nunique()
                    ),
                    "event_count": int(len(events)),
                    "ticker_count": int(events["ticker"].nunique()),
                    "start_date": snapshots[
                        "effective_date"
                    ].min().strftime("%Y-%m-%d"),
                    "end_date": snapshots[
                        "effective_date"
                    ].max().strftime("%Y-%m-%d"),
                    "promotion_note": (
                        "Membership is point-in-time; price and issuer identity "
                        "coverage must pass separate gates."
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
