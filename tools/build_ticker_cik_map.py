#!/usr/bin/env python3
"""Build a small ticker-to-CIK map from Yahoo SEC filing metadata."""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sec_point_in_time import extract_cik_from_filing_metadata  # noqa: E402


def _load_tickers(args):
    tickers = list(args.tickers or [])
    if args.ticker_csv:
        frame = pd.read_csv(args.ticker_csv)
        column = "ticker" if "ticker" in frame.columns else "Symbol"
        if column not in frame.columns:
            raise ValueError("Ticker CSV requires ticker or Symbol column")
        tickers.extend(frame[column].dropna().astype(str).tolist())
    normalized = []
    seen = set()
    for value in tickers:
        ticker = str(value).strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            normalized.append(ticker)
    if not normalized:
        raise ValueError("Provide --tickers or --ticker-csv")
    return normalized


def _resolve_ticker(ticker):
    try:
        filings = yf.Ticker(ticker).get_sec_filings()
        cik = extract_cik_from_filing_metadata(filings)
        return {
            "ticker": ticker,
            "cik": cik,
            "status": "ok" if cik is not None else "missing",
            "error": None,
        }
    except Exception as exc:
        return {
            "ticker": ticker,
            "cik": None,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _json_records(frame):
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict(orient="records")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--ticker-csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--minimum-coverage", type=float, default=0.90)
    args = parser.parse_args(argv)

    try:
        tickers = _load_tickers(args)
        rows = []
        with ThreadPoolExecutor(
            max_workers=max(1, min(8, int(args.workers)))
        ) as executor:
            futures = {
                executor.submit(_resolve_ticker, ticker): ticker
                for ticker in tickers
            }
            for future in as_completed(futures):
                rows.append(future.result())
        frame = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
        successful = frame.loc[
            frame["status"] == "ok",
            ["ticker", "cik"],
        ].copy()
        successful["cik"] = successful["cik"].astype(int)
        coverage = float(len(successful) / len(frame))
        if coverage < float(args.minimum_coverage):
            failures = _json_records(frame.loc[
                frame["status"] != "ok",
                ["ticker", "status", "error"],
            ])
            raise ValueError(
                f"Ticker-CIK coverage {coverage:.2%} is below "
                f"{float(args.minimum_coverage):.2%}: "
                + json.dumps(failures)
            )

        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        successful.to_csv(output_path, index=False)
        provenance_path = output_path.with_suffix(".provenance.json")
        provenance_path.write_text(
            json.dumps(
                {
                    "source": "Yahoo Finance SEC filing metadata",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "ticker_count": int(len(frame)),
                    "mapped_count": int(len(successful)),
                    "coverage": coverage,
                    "failures": _json_records(frame.loc[
                        frame["status"] != "ok"
                    ]),
                },
                indent=2,
                allow_nan=False,
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
