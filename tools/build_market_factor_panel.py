#!/usr/bin/env python3
"""Build a dated U.S. market-factor and risk-free panel from official data."""

import argparse
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


FRED_DGS3MO_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
)
FRENCH_DAILY_FACTORS_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_daily_CSV.zip"
)


def _sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _download(url):
    response = requests.get(
        url,
        timeout=60,
        headers={
            "User-Agent": (
                "Antifier research data builder "
                "https://github.com/anthropics/antifier"
            )
        },
    )
    response.raise_for_status()
    return response.content


def _parse_french(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(
                "Unexpected Fama-French archive member count"
            )
        text = archive.read(names[0]).decode("utf-8")
    rows = []
    for line in text.splitlines():
        fields = [value.strip() for value in line.split(",")]
        if not fields or len(fields[0]) != 8 or not fields[0].isdigit():
            continue
        if len(fields) < 5:
            continue
        rows.append({
            "date": pd.Timestamp(fields[0]),
            "mkt_rf": float(fields[1]) / 100.0,
            "smb": float(fields[2]) / 100.0,
            "hml": float(fields[3]) / 100.0,
            "rf_daily": float(fields[4]) / 100.0,
        })
    if not rows:
        raise ValueError("Fama-French archive contains no daily factor rows")
    return pd.DataFrame(rows).set_index("date").sort_index()


def _parse_fred(payload):
    frame = pd.read_csv(io.BytesIO(payload))
    date_column = (
        "observation_date"
        if "observation_date" in frame.columns
        else "DATE"
    )
    if date_column not in frame or "DGS3MO" not in frame:
        raise ValueError("Unexpected FRED DGS3MO CSV columns")
    frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce")
    frame["DGS3MO"] = pd.to_numeric(frame["DGS3MO"], errors="coerce")
    return (
        frame.dropna(subset=[date_column, "DGS3MO"])
        .set_index(date_column)[["DGS3MO"]]
        .rename(columns={"DGS3MO": "dgs3mo_annual_yield"})
        .sort_index()
        / 100.0
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--reuse-raw",
        action="store_true",
        help="Read existing raw files without downloading replacements",
    )
    args = parser.parse_args(argv)

    try:
        start = pd.Timestamp(args.start)
        end = pd.Timestamp(args.end)
        if start > end:
            raise ValueError("--start must be on or before --end")
        raw_dir = Path(args.raw_dir).expanduser().resolve()
        raw_dir.mkdir(parents=True, exist_ok=True)
        fred_path = raw_dir / "fred_dgs3mo.csv"
        french_path = raw_dir / "fama_french_daily_factors.zip"
        if args.reuse_raw:
            if not fred_path.exists() or not french_path.exists():
                raise ValueError(
                    "--reuse-raw requires fred_dgs3mo.csv and "
                    "fama_french_daily_factors.zip"
                )
            fred_payload = fred_path.read_bytes()
            french_payload = french_path.read_bytes()
        else:
            fred_payload = _download(FRED_DGS3MO_URL)
            french_payload = _download(FRENCH_DAILY_FACTORS_URL)
            fred_path.write_bytes(fred_payload)
            french_path.write_bytes(french_payload)

        factors = _parse_french(french_payload).loc[start:end]
        yields = _parse_fred(fred_payload)
        panel = pd.merge_asof(
            factors.sort_index(),
            yields.sort_index(),
            left_index=True,
            right_index=True,
            direction="backward",
        )
        panel["rf_daily_dgs3mo"] = (
            (1.0 + panel["dgs3mo_annual_yield"])
            ** (1.0 / 252.0)
            - 1.0
        )
        if panel.empty or panel["dgs3mo_annual_yield"].isna().any():
            raise ValueError(
                "Official factor panel has missing backward-looking yield"
            )
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        panel.to_csv(output_path)
        provenance_path = output_path.with_suffix(".provenance.json")
        provenance_path.write_text(
            json.dumps(
                {
                    "source": (
                        "Kenneth French Data Library daily U.S. factors "
                        "and FRED DGS3MO"
                    ),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "official_sources": {
                        "fama_french_daily_factors": (
                            FRENCH_DAILY_FACTORS_URL
                        ),
                        "fred_dgs3mo": FRED_DGS3MO_URL,
                    },
                    "availability_policy": (
                        "daily observations joined to the latest DGS3MO "
                        "observation on or before each factor date"
                    ),
                    "units": {
                        "mkt_rf": "daily decimal return",
                        "smb": "daily decimal return",
                        "hml": "daily decimal return",
                        "rf_daily": "daily decimal return",
                        "rf_daily_dgs3mo": (
                            "daily decimal return derived from latest "
                            "DGS3MO annual yield"
                        ),
                        "dgs3mo_annual_yield": "annual decimal yield",
                    },
                    "start_date": panel.index.min().strftime("%Y-%m-%d"),
                    "end_date": panel.index.max().strftime("%Y-%m-%d"),
                    "row_count": int(len(panel)),
                    "factor_file": str(output_path),
                    "factor_file_sha256": _sha256(output_path),
                    "raw_files": {
                        "fama_french_daily_factors": {
                            "file": str(french_path),
                            "sha256": _sha256_bytes(french_payload),
                        },
                        "fred_dgs3mo": {
                            "file": str(fred_path),
                            "sha256": _sha256_bytes(fred_payload),
                        },
                    },
                    "promotion_safe": True,
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
