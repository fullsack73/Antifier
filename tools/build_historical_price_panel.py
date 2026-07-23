#!/usr/bin/env python3
"""Build a provenance-tracked historical price panel for a dated universe."""

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
from universe_manifest import (  # noqa: E402
    manifest_tickers_during,
    normalize_universe_manifest,
    universe_manifest_digest,
    validate_universe_provenance,
)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_aliases(path):
    if not path:
        return {}, None
    alias_path = Path(path).expanduser().resolve()
    frame = pd.read_csv(alias_path)
    required = {"ticker", "price_ticker"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(
            "Price aliases are missing required columns: "
            + ", ".join(missing)
        )
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["price_ticker"] = (
        frame["price_ticker"].astype(str).str.strip().str.upper()
    )
    if frame.duplicated("ticker").any():
        raise ValueError("Price aliases contain duplicate tickers")
    if (frame["ticker"] == "").any() or (frame["price_ticker"] == "").any():
        raise ValueError("Price aliases require non-empty symbols")
    return dict(zip(frame["ticker"], frame["price_ticker"])), {
        "file": str(alias_path),
        "sha256": _sha256(alias_path),
        "records": frame.to_dict(orient="records"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-manifest", required=True)
    parser.add_argument("--universe-provenance", required=True)
    parser.add_argument("--price-aliases")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        manifest_path = Path(args.universe_manifest).expanduser().resolve()
        provenance_path = Path(
            args.universe_provenance
        ).expanduser().resolve()
        manifest = normalize_universe_manifest(pd.read_csv(manifest_path))
        universe_provenance = validate_universe_provenance(
            json.loads(provenance_path.read_text(encoding="utf-8")),
            require_promotion_safe=True,
        )
        manifest_digest = universe_manifest_digest(manifest)
        declared_digest = universe_provenance.get("manifest_sha256")
        if declared_digest and declared_digest != manifest_digest:
            raise ValueError(
                "Universe manifest SHA-256 does not match provenance"
            )
        aliases, alias_provenance = _load_aliases(args.price_aliases)
        tickers = manifest_tickers_during(
            manifest,
            args.start,
            args.end,
        )
        price_symbols = sorted({
            aliases.get(ticker, ticker) for ticker in tickers
        })
        downloaded = fetch_backtest_price_data(
            tickers=price_symbols,
            start_date=args.start,
            end_date=args.end,
        )
        downloaded = pd.DataFrame(downloaded).replace(
            [np.inf, -np.inf],
            np.nan,
        )
        panel = pd.DataFrame(index=downloaded.index)
        missing = []
        for ticker in tickers:
            price_ticker = aliases.get(ticker, ticker)
            if price_ticker not in downloaded.columns:
                panel[ticker] = np.nan
                missing.append(ticker)
            else:
                panel[ticker] = pd.to_numeric(
                    downloaded[price_ticker],
                    errors="coerce",
                )

        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        panel.to_csv(output_path)
        usable = {
            ticker: int(panel[ticker].notna().sum())
            for ticker in panel.columns
        }
        output_provenance_path = output_path.with_suffix(
            ".provenance.json"
        )
        output_provenance_path.write_text(
            json.dumps(
                {
                    "source": "Yahoo Finance adjusted price history",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "start_date": args.start,
                    "end_date": args.end,
                    "row_count": int(len(panel)),
                    "ticker_count": int(len(panel.columns)),
                    "price_file": str(output_path),
                    "price_file_sha256": _sha256(output_path),
                    "universe_manifest": str(manifest_path),
                    "universe_manifest_sha256": manifest_digest,
                    "universe_provenance": str(provenance_path),
                    "price_aliases": alias_provenance,
                    "missing_tickers": sorted(missing),
                    "usable_observations": usable,
                },
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {output_provenance_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
