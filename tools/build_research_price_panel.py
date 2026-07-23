#!/usr/bin/env python3
"""Download a small explicit research basket with file provenance."""

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

from portfolio_backtest import fetch_backtest_price_data  # noqa: E402


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _basket_digest(tickers):
    return hashlib.sha256(
        json.dumps(
            list(tickers),
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        tickers = list(dict.fromkeys(
            str(value).strip().upper()
            for value in args.tickers
            if str(value).strip()
        ))
        if not tickers:
            raise ValueError("At least one ticker is required")
        prices = fetch_backtest_price_data(
            tickers=tickers,
            start_date=args.start,
            end_date=args.end,
        )
        prices = (
            pd.DataFrame(prices)
            .reindex(columns=tickers)
            .replace([np.inf, -np.inf], np.nan)
        )
        missing = [
            ticker
            for ticker in tickers
            if ticker not in prices or prices[ticker].notna().sum() == 0
        ]
        if missing:
            raise ValueError(
                "Downloaded panel is missing requested tickers: "
                + ", ".join(missing)
            )
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prices.to_csv(output_path)
        provenance_path = output_path.with_suffix(".provenance.json")
        provenance_path.write_text(
            json.dumps(
                {
                    "source": "Yahoo Finance adjusted price history",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "basket_policy": "explicit predeclared research basket",
                    "survivorship_policy": "not_asserted",
                    "promotion_safe": False,
                    "start_date": args.start,
                    "end_date": args.end,
                    "row_count": int(len(prices)),
                    "ticker_count": int(len(tickers)),
                    "tickers": tickers,
                    "basket_manifest_sha256": _basket_digest(tickers),
                    "price_file": str(output_path),
                    "price_file_sha256": _sha256(output_path),
                    "usable_observations": {
                        ticker: int(prices[ticker].notna().sum())
                        for ticker in tickers
                    },
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
