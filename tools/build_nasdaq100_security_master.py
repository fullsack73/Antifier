#!/usr/bin/env python3
"""Build a Nasdaq-100 ticker-to-CIK security master from pinned sources."""

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

from sec_point_in_time import sic_sector  # noqa: E402


HISTORICAL_CIK_OVERRIDES = {
    "ALXN": 899866,
    "ANSS": 1013462,
    "ATVI": 718877,
    "CA": 356028,
    "CELG": 816284,
    "CERN": 804753,
    "CTXS": 877890,
    "DISCA": 1437107,
    "DISCK": 1437107,
    "DISH": 1001082,
    "ESRX": 1532063,
    "FI": 798354,
    "HOLX": 859737,
    "MXIM": 743316,
    "MYL": 1623613,
    "NLOK": 849399,
    "QRTEA": 1355096,
    "SGEN": 1060736,
    "SHPG": 936402,
    "SPLK": 1353283,
    "VIAB": 1339947,
    "WBA": 1618921,
    "XLNX": 743988,
    "YHOO": 1011006,
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _companyfacts_entity(companyfacts_dir, cik):
    path = Path(companyfacts_dir) / f"CIK{int(cik):010d}.json"
    if not path.is_file():
        raise ValueError(f"Missing local companyfacts file for CIK {cik}")
    with path.open(encoding="utf-8") as handle:
        prefix = handle.read(4096)
    marker = '"entityName":"'
    if marker not in prefix:
        raise ValueError(f"Cannot read entityName from {path.name}")
    return prefix.split(marker, 1)[1].split('"', 1)[0]


def _component_names_and_sectors(component_html):
    tables = pd.read_html(
        StringIO(Path(component_html).read_text(encoding="utf-8"))
    )
    current = tables[0]
    changes = tables[1].copy()
    changes.columns = [
        "date",
        "added_ticker",
        "added_security",
        "removed_ticker",
        "removed_security",
        "reason",
    ]
    names = {}
    sectors = {}
    for row in current.itertuples(index=False):
        ticker = str(row[0]).strip().upper()
        names.setdefault(ticker, set()).add(str(row[1]).strip())
        sectors[ticker] = str(row[2]).strip()
    for row in changes.itertuples(index=False):
        if pd.notna(row.added_ticker):
            ticker = str(row.added_ticker).strip().upper()
            names.setdefault(ticker, set()).add(
                str(row.added_security).strip()
            )
        if pd.notna(row.removed_ticker):
            ticker = str(row.removed_ticker).strip().upper()
            names.setdefault(ticker, set()).add(
                str(row.removed_security).strip()
            )
    return {
        ticker: " | ".join(sorted(values))
        for ticker, values in names.items()
    }, sectors


def _load_sic_sectors(submissions_dir, ciks):
    if not submissions_dir:
        return {}
    directory = Path(submissions_dir).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(
            f"SEC submissions directory does not exist: {directory}"
        )
    sectors = {}
    for cik in sorted(set(ciks)):
        path = directory / f"CIK{int(cik):010d}.json"
        if not path.is_file():
            raise ValueError(f"Missing SEC submissions file for CIK {cik}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("cik", -1)) != int(cik):
            raise ValueError(f"SEC submissions CIK mismatch for {cik}")
        sector = sic_sector(payload.get("sic"))
        if sector != "Unknown":
            sectors[int(cik)] = sector
    return sectors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-manifest", required=True)
    parser.add_argument("--sec-ticker-json", required=True)
    parser.add_argument("--component-html", required=True)
    parser.add_argument("--companyfacts-dir", required=True)
    parser.add_argument("--submissions-dir")
    parser.add_argument("--submissions-provenance")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        if bool(args.submissions_dir) != bool(
            args.submissions_provenance
        ):
            raise ValueError(
                "--submissions-dir and --submissions-provenance "
                "must be used together"
            )
        universe_path = Path(args.universe_manifest).expanduser().resolve()
        sec_path = Path(args.sec_ticker_json).expanduser().resolve()
        component_path = Path(args.component_html).expanduser().resolve()
        companyfacts_dir = Path(
            args.companyfacts_dir
        ).expanduser().resolve()
        tickers = sorted(
            pd.read_csv(universe_path)["ticker"]
            .astype(str)
            .str.strip()
            .str.upper()
            .unique()
        )
        sec_payload = json.loads(sec_path.read_text(encoding="utf-8"))
        sec_index = {
            str(record["ticker"]).strip().upper(): record
            for record in sec_payload.values()
        }
        names, sectors = _component_names_and_sectors(component_path)

        rows = []
        for ticker in tickers:
            if ticker in sec_index:
                cik = int(sec_index[ticker]["cik_str"])
                mapping_source = "SEC company_tickers.json"
            else:
                cik = HISTORICAL_CIK_OVERRIDES.get(ticker)
                mapping_source = "historical CIK override"
            if cik is None:
                raise ValueError(f"No CIK mapping for {ticker}")
            entity_name = _companyfacts_entity(companyfacts_dir, cik)
            rows.append({
                "ticker": ticker,
                "cik": cik,
                "effective_start": "",
                "effective_end": "",
                "sector": sectors.get(ticker, "Unknown"),
                "component_security_name": names.get(ticker, ""),
                "sec_entity_name": entity_name,
                "mapping_source": mapping_source,
            })

        sic_sectors = _load_sic_sectors(
            args.submissions_dir,
            [row["cik"] for row in rows],
        )
        if sic_sectors:
            for row in rows:
                row["sector"] = sic_sectors.get(row["cik"], "Unknown")
                row["sector_source"] = (
                    "SEC submissions SIC"
                    if row["cik"] in sic_sectors
                    else "missing SEC SIC"
                )
        else:
            for row in rows:
                row["sector_source"] = (
                    "current Wikipedia ICB"
                    if row["sector"] != "Unknown"
                    else "unavailable"
                )

        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(rows)
        frame.to_csv(output_path, index=False)
        provenance_path = output_path.with_suffix(".provenance.json")
        provenance_path.write_text(
            json.dumps(
                {
                    "source": (
                        "SEC company_tickers.json plus locally verified "
                        "historical issuer overrides"
                    ),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "security_master_file": str(output_path),
                    "security_master_sha256": _sha256(output_path),
                    "ticker_count": int(len(frame)),
                    "issuer_count": int(frame["cik"].nunique()),
                    "official_mapping_count": int(
                        (frame["mapping_source"]
                         == "SEC company_tickers.json").sum()
                    ),
                    "historical_override_count": int(
                        (frame["mapping_source"]
                         == "historical CIK override").sum()
                    ),
                    "unknown_sector_count": int(
                        (frame["sector"] == "Unknown").sum()
                    ),
                    "universe_manifest": str(universe_path),
                    "universe_manifest_sha256": _sha256(universe_path),
                    "sec_ticker_file": str(sec_path),
                    "sec_ticker_file_sha256": _sha256(sec_path),
                    "component_history_file": str(component_path),
                    "component_history_file_sha256": _sha256(
                        component_path
                    ),
                    "submissions_directory": (
                        str(
                            Path(args.submissions_dir)
                            .expanduser()
                            .resolve()
                        )
                        if args.submissions_dir
                        else None
                    ),
                    "submissions_provenance": (
                        str(
                            Path(args.submissions_provenance)
                            .expanduser()
                            .resolve()
                        )
                        if args.submissions_provenance
                        else None
                    ),
                    "submissions_provenance_sha256": (
                        _sha256(args.submissions_provenance)
                        if args.submissions_provenance
                        else None
                    ),
                    "companyfacts_directory": str(companyfacts_dir),
                    "promotion_safe": bool(
                        args.submissions_dir
                        and (frame["sector"] != "Unknown").mean() >= 0.99
                    ),
                    "promotion_note": (
                        "Issuer identities and sectors are source-locked; "
                        "Yahoo price coverage remains a separate gate."
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
