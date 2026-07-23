"""Dated research-universe manifests and survivorship-policy guardrails."""

import hashlib
import json

import pandas as pd


UNIVERSE_REQUIRED_COLUMNS = (
    "effective_date",
    "ticker",
    "in_universe",
)
PROMOTION_SAFE_POLICIES = {
    "historical_constituents",
    "point_in_time_membership",
    "survivorship_safe",
}


def normalize_universe_manifest(manifest):
    frame = pd.DataFrame(manifest).copy()
    missing = [
        column
        for column in UNIVERSE_REQUIRED_COLUMNS
        if column not in frame.columns
    ]
    if missing:
        raise ValueError(
            "Universe manifest is missing required columns: "
            + ", ".join(missing)
        )
    frame = frame.loc[:, UNIVERSE_REQUIRED_COLUMNS].copy()
    frame["effective_date"] = pd.to_datetime(
        frame["effective_date"],
        errors="coerce",
    )
    if frame["effective_date"].isna().any():
        raise ValueError("Universe manifest has invalid effective_date values")
    frame["ticker"] = (
        frame["ticker"].astype(str).str.strip().str.upper()
    )
    if (frame["ticker"] == "").any():
        raise ValueError("Universe manifest requires non-empty tickers")
    if not frame["in_universe"].map(
        lambda value: isinstance(value, bool)
        or value in (0, 1, "0", "1", "true", "false", "True", "False")
    ).all():
        raise ValueError("Universe manifest in_universe must be boolean")
    frame["in_universe"] = frame["in_universe"].map(
        lambda value: (
            value
            if isinstance(value, bool)
            else str(value).lower() in {"1", "true"}
        )
    )
    if frame.duplicated(["effective_date", "ticker"]).any():
        raise ValueError(
            "Universe manifest has duplicate effective_date/ticker rows"
        )
    return frame.sort_values(
        ["effective_date", "ticker"]
    ).reset_index(drop=True)


def universe_snapshot(manifest, as_of_date):
    """Resolve membership using events known by the requested date."""
    frame = normalize_universe_manifest(manifest)
    eligible = frame.loc[
        frame["effective_date"] <= pd.Timestamp(as_of_date)
    ]
    if eligible.empty:
        return []
    latest = eligible.drop_duplicates("ticker", keep="last")
    return sorted(
        latest.loc[latest["in_universe"], "ticker"].tolist()
    )


def manifest_tickers_during(manifest, start_date, end_date):
    """Return every ticker active at any point in the requested interval."""
    frame = normalize_universe_manifest(manifest)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    candidate_dates = [start]
    candidate_dates.extend(
        frame.loc[
            (frame["effective_date"] >= start)
            & (frame["effective_date"] <= end),
            "effective_date",
        ].tolist()
    )
    tickers = set()
    for date in sorted(set(candidate_dates)):
        tickers.update(universe_snapshot(frame, date))
    return sorted(tickers)


def universe_manifest_digest(manifest):
    frame = normalize_universe_manifest(manifest)
    payload = frame.assign(
        effective_date=frame["effective_date"].dt.strftime("%Y-%m-%d")
    ).to_dict(orient="records")
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def snapshots_to_membership_events(snapshots):
    """Convert dated full constituent snapshots into membership events."""
    frame = pd.DataFrame(snapshots).copy()
    required = {"effective_date", "ticker"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(
            "Constituent snapshots are missing required fields: "
            + ", ".join(missing)
        )
    frame = frame.loc[:, ["effective_date", "ticker"]].copy()
    frame["effective_date"] = pd.to_datetime(
        frame["effective_date"],
        errors="coerce",
    )
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    if frame["effective_date"].isna().any() or (frame["ticker"] == "").any():
        raise ValueError(
            "Constituent snapshots require valid dates and tickers"
        )
    if frame.duplicated(["effective_date", "ticker"]).any():
        raise ValueError(
            "Constituent snapshots contain duplicate date/ticker rows"
        )

    events = []
    previous = set()
    for effective_date, group in frame.groupby(
        "effective_date",
        sort=True,
    ):
        current = set(group["ticker"])
        for ticker in sorted(current - previous):
            events.append({
                "effective_date": effective_date,
                "ticker": ticker,
                "in_universe": True,
            })
        for ticker in sorted(previous - current):
            events.append({
                "effective_date": effective_date,
                "ticker": ticker,
                "in_universe": False,
            })
        previous = current
    return normalize_universe_manifest(events)


def validate_universe_provenance(provenance, require_promotion_safe=False):
    required = {
        "source",
        "retrieved_at",
        "universe_policy",
        "survivorship_policy",
    }
    provenance = dict(provenance or {})
    missing = sorted(required - set(provenance))
    if missing:
        raise ValueError(
            "Universe provenance is missing required fields: "
            + ", ".join(missing)
        )
    policy = str(provenance["survivorship_policy"]).strip().lower()
    promotion_safe = policy in PROMOTION_SAFE_POLICIES
    if require_promotion_safe and not promotion_safe:
        raise ValueError(
            "Universe is not promotion-safe under survivorship policy "
            f"{provenance['survivorship_policy']!r}"
        )
    return {
        **provenance,
        "promotion_safe": promotion_safe,
    }
