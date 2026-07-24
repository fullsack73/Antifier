#!/usr/bin/env python3
"""Import promotion-safe CRSP monthly stocks with dated CIK links."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from universe_manifest import (  # noqa: E402
    snapshots_to_membership_events,
    universe_manifest_digest,
)


CRSP_MISSING_RETURN_CODES = {-44.0, -55.0, -66.0, -77.0, -88.0, -99.0}
COMMON_SHARE_CODES = {10, 11}
PRIMARY_EXCHANGE_CODES = {1, 2, 3}
STOCK_REQUIRED_COLUMNS = {
    "permno",
    "date",
    "ret",
    "dlret",
    "prc",
    "shrout",
    "shrcd",
    "exchcd",
    "ticker",
}
LINK_REQUIRED_COLUMNS = {
    "permno",
    "cik",
    "effective_start",
    "effective_end",
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_ticker(permno):
    return f"PERMNO_{int(permno)}"


def _crsp_numeric(series):
    values = pd.to_numeric(series, errors="coerce")
    for code in CRSP_MISSING_RETURN_CODES:
        values = values.mask(np.isclose(values, code, rtol=0.0, atol=1e-12))
    return values


def combine_crsp_returns(ret, dlret):
    """Combine regular and delisting returns without losing either leg."""
    regular = _crsp_numeric(pd.Series(ret, dtype=object))
    delisting = _crsp_numeric(pd.Series(dlret, dtype=object))
    combined = pd.Series(np.nan, index=regular.index, dtype=float)
    both = regular.notna() & delisting.notna()
    combined.loc[both] = (
        (1.0 + regular.loc[both]) * (1.0 + delisting.loc[both]) - 1.0
    )
    regular_only = regular.notna() & delisting.isna()
    combined.loc[regular_only] = regular.loc[regular_only]
    delisting_only = regular.isna() & delisting.notna()
    combined.loc[delisting_only] = delisting.loc[delisting_only]
    if (combined.dropna() < -1.0 - 1e-12).any():
        raise ValueError("CRSP combined return cannot be below -100%")
    return combined.clip(lower=-1.0)


def normalize_crsp_monthly_stock(frame):
    """Validate and filter a WRDS CRSP monthly stock export."""
    data = pd.DataFrame(frame).copy()
    missing = sorted(STOCK_REQUIRED_COLUMNS - set(data.columns))
    if missing:
        raise ValueError(
            "CRSP monthly stock data is missing columns: "
            + ", ".join(missing)
        )
    data = data.loc[:, sorted(STOCK_REQUIRED_COLUMNS)].copy()
    data["permno"] = pd.to_numeric(data["permno"], errors="coerce")
    data["date"] = (
        pd.to_datetime(data["date"], errors="coerce")
        + pd.offsets.MonthEnd(0)
    )
    for column in ("prc", "shrout", "shrcd", "exchcd"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data["permno"].isna().any() or data["date"].isna().any():
        raise ValueError("CRSP monthly stock data has invalid PERMNO/date")
    data["permno"] = data["permno"].astype(int)
    if (data["permno"] <= 0).any():
        raise ValueError("CRSP PERMNO must be positive")
    if data.duplicated(["permno", "date"]).any():
        raise ValueError("CRSP monthly stock data has duplicate PERMNO/date")
    data = data.loc[
        data["shrcd"].isin(COMMON_SHARE_CODES)
        & data["exchcd"].isin(PRIMARY_EXCHANGE_CODES)
    ].copy()
    if data.empty:
        raise ValueError("CRSP filters removed every security observation")
    data["return"] = combine_crsp_returns(data["ret"], data["dlret"])
    data["market_cap"] = (
        data["prc"].abs() * data["shrout"] * 1000.0
    ).where(data["prc"].notna() & data["shrout"].notna())
    data["canonical_ticker"] = data["permno"].map(_canonical_ticker)
    data["display_ticker"] = (
        data["ticker"].fillna("").astype(str).str.strip().str.upper()
    )
    return data.sort_values(["date", "permno"]).reset_index(drop=True)


def normalize_crsp_cik_links(frame):
    """Validate non-overlapping dated PERMNO-to-CIK links."""
    links = pd.DataFrame(frame).copy()
    missing = sorted(LINK_REQUIRED_COLUMNS - set(links.columns))
    if missing:
        raise ValueError(
            "CRSP/CCM identity links are missing columns: "
            + ", ".join(missing)
        )
    keep = [
        "permno",
        "cik",
        "effective_start",
        "effective_end",
    ]
    for optional in ("link_type", "link_primary", "sector"):
        if optional in links.columns:
            keep.append(optional)
    links = links.loc[:, keep].copy()
    links["permno"] = pd.to_numeric(links["permno"], errors="coerce")
    links["cik"] = pd.to_numeric(links["cik"], errors="coerce")
    links["effective_start"] = pd.to_datetime(
        links["effective_start"],
        errors="coerce",
    )
    links["effective_end"] = pd.to_datetime(
        links["effective_end"],
        errors="coerce",
    )
    if (
        links["permno"].isna().any()
        or links["cik"].isna().any()
        or (links["permno"] <= 0).any()
        or (links["cik"] <= 0).any()
    ):
        raise ValueError("CRSP/CCM identity links have invalid PERMNO/CIK")
    links["permno"] = links["permno"].astype(int)
    links["cik"] = links["cik"].astype(int)
    inverted = (
        links["effective_start"].notna()
        & links["effective_end"].notna()
        & (links["effective_start"] > links["effective_end"])
    )
    if inverted.any():
        raise ValueError("CRSP/CCM identity link interval is inverted")
    for permno, group in links.groupby("permno"):
        ordered = group.sort_values(
            ["effective_start", "effective_end"],
            na_position="first",
        )
        previous_end = None
        seen = False
        for row in ordered.itertuples(index=False):
            start = (
                pd.Timestamp.min
                if pd.isna(row.effective_start)
                else pd.Timestamp(row.effective_start)
            )
            end = (
                pd.Timestamp.max
                if pd.isna(row.effective_end)
                else pd.Timestamp(row.effective_end)
            )
            if seen and previous_end == pd.Timestamp.max:
                raise ValueError(
                    f"Open CRSP/CCM identity interval precedes another "
                    f"link for PERMNO {permno}"
                )
            if seen and start <= previous_end:
                raise ValueError(
                    f"Overlapping CRSP/CCM identity links for PERMNO "
                    f"{permno}"
                )
            previous_end = end
            seen = True
    return links.sort_values(
        ["permno", "effective_start", "effective_end"],
        na_position="first",
    ).reset_index(drop=True)


def assign_point_in_time_cik(stock, links):
    """Attach exactly one identity link to every security-month."""
    data = pd.DataFrame(stock).copy()
    identity = pd.Series(pd.NA, index=data.index, dtype="Int64")
    for permno, rows in data.groupby("permno").groups.items():
        candidates = links.loc[links["permno"] == int(permno)]
        for link in candidates.itertuples(index=False):
            start = (
                pd.Timestamp.min
                if pd.isna(link.effective_start)
                else pd.Timestamp(link.effective_start)
            )
            end = (
                pd.Timestamp.max
                if pd.isna(link.effective_end)
                else pd.Timestamp(link.effective_end)
            )
            mask = data.index.isin(rows) & data["date"].between(start, end)
            if identity.loc[mask].notna().any():
                raise ValueError(
                    f"Multiple active CIK links for PERMNO {permno}"
                )
            identity.loc[mask] = int(link.cik)
    if identity.isna().any():
        sample = data.loc[
            identity.isna(),
            ["permno", "date"],
        ].head(10)
        raise ValueError(
            "CRSP observations lack point-in-time CIK links: "
            + sample.to_json(orient="records", date_format="iso")
        )
    data["cik"] = identity.astype(int)
    return data


def build_crsp_research_artifacts(stock_frame, link_frame):
    """Build canonical panels, universe events, and SEC-compatible identity."""
    stock = normalize_crsp_monthly_stock(stock_frame)
    links = normalize_crsp_cik_links(link_frame)
    stock = assign_point_in_time_cik(stock, links)
    returns = stock.pivot(
        index="date",
        columns="canonical_ticker",
        values="return",
    ).sort_index()
    prices = (1.0 + returns).cumprod() * 100.0
    market_caps = stock.pivot(
        index="date",
        columns="canonical_ticker",
        values="market_cap",
    ).sort_index()
    ordered = sorted(
        returns.columns,
        key=lambda value: int(value.split("_", 1)[1]),
    )
    returns = returns.reindex(columns=ordered)
    prices = prices.reindex(columns=ordered)
    market_caps = market_caps.reindex(columns=ordered)
    snapshots = stock.loc[:, ["date", "canonical_ticker"]].rename(
        columns={
            "date": "effective_date",
            "canonical_ticker": "ticker",
        }
    )
    universe = snapshots_to_membership_events(snapshots)
    latest_symbols = (
        stock.loc[stock["display_ticker"] != ""]
        .sort_values(["permno", "date"])
        .drop_duplicates("permno", keep="last")
        .set_index("permno")["display_ticker"]
        .to_dict()
    )
    security_master = links.copy()
    security_master["ticker"] = security_master["permno"].map(
        _canonical_ticker
    )
    security_master["display_ticker"] = security_master["permno"].map(
        latest_symbols
    )
    if "sector" not in security_master.columns:
        security_master["sector"] = None
    security_master = security_master.loc[
        :,
        [
            "ticker",
            "permno",
            "cik",
            "effective_start",
            "effective_end",
            "display_ticker",
            "sector",
            *[
                column
                for column in ("link_type", "link_primary")
                if column in security_master.columns
            ],
        ],
    ]
    return {
        "returns": returns,
        "prices": prices,
        "market_caps": market_caps,
        "universe": universe,
        "security_master": security_master,
        "diagnostics": {
            "row_count": int(len(stock)),
            "security_count": int(stock["permno"].nunique()),
            "issuer_count": int(stock["cik"].nunique()),
            "first_date": stock["date"].min().strftime("%Y-%m-%d"),
            "last_date": stock["date"].max().strftime("%Y-%m-%d"),
            "delisting_return_count": int(
                _crsp_numeric(stock["dlret"]).notna().sum()
            ),
            "identity_coverage_rate": 1.0,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-data", required=True)
    parser.add_argument("--identity-links", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", default="crsp_monthly_research")
    args = parser.parse_args(argv)

    try:
        stock_path = Path(args.stock_data).expanduser().resolve()
        links_path = Path(args.identity_links).expanduser().resolve()
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        artifacts = build_crsp_research_artifacts(
            pd.read_csv(stock_path),
            pd.read_csv(links_path),
        )
        outputs = {}
        for key in (
            "returns",
            "prices",
            "market_caps",
            "universe",
            "security_master",
        ):
            path = output_dir / f"{args.name}_{key}.csv"
            artifacts[key].to_csv(path, index=(key in {
                "returns",
                "prices",
                "market_caps",
            }))
            outputs[key] = {
                "file": str(path),
                "sha256": _sha256(path),
            }
        provenance_path = output_dir / f"{args.name}.provenance.json"
        provenance = {
            "source": "CRSP U.S. Stock with dated CCM/Compustat CIK links",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "stock_input": {
                "file": str(stock_path),
                "sha256": _sha256(stock_path),
            },
            "identity_input": {
                "file": str(links_path),
                "sha256": _sha256(links_path),
            },
            "security_policy": (
                "CRSP common shares 10/11 on NYSE/AMEX/NASDAQ 1/2/3"
            ),
            "return_policy": (
                "(1+RET)*(1+DLRET)-1; single available leg retained"
            ),
            "identity_policy": (
                "PERMNO permanent key with complete non-overlapping "
                "point-in-time CIK links"
            ),
            "price_policy": (
                "return wealth index without leading or cross-security fill"
            ),
            "universe_policy": "point_in_time_membership",
            "survivorship_policy": "survivorship_safe_with_delisting_returns",
            "outputs": outputs,
            "universe_manifest_sha256": universe_manifest_digest(
                artifacts["universe"]
            ),
            "diagnostics": artifacts["diagnostics"],
            "promotion_safe": True,
        }
        provenance_path.write_text(
            json.dumps(provenance, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    for payload in outputs.values():
        print(f"Wrote {payload['file']}")
    print(f"Wrote {provenance_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
