#!/usr/bin/env python3
"""Diagnostic comparison of 3 vs 12 completed periods for hybrid weights."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/backend"))
from direct_horizon_forecast import DirectARIMATransformerPredictor, MODEL_VERSION
from forecast_models import ARIMATransformerPredictor
from tools.compare_adaptive_hybrid import cross_error_weight, summarize

METHODS = ("arima", "transformer", "equal", "ignored_3", "cross_3", "ignored_12", "cross_12")


def mix_at_origin(records, origin, ticker):
    current = records[(origin, ticker)]
    a, t = current["arima"], current["transformer"]
    row = {**current, "equal": (a + t) / 2, "weights": {}}
    for count in (3, 12):
        past = [records[(origin - lag * 63, ticker)] for lag in range(count, 0, -1)]
        errors = np.array([[p["arima"] - p["realized"], p["transformer"] - p["realized"]] for p in past]) * 4
        losses = np.mean(errors ** 2, axis=0)
        weight = .5 if losses.sum() <= 1e-12 else float(.25 + .5 * losses[1] / losses.sum())
        for method, value in ((f"ignored_{count}", weight), (f"cross_{count}", cross_error_weight(errors))):
            row[method] = value * a + (1 - value) * t
            row["weights"][method] = value
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source = Path(args.csv)
    prices = pd.read_csv(source, index_col=0, parse_dates=True).loc[:, args.tickers].astype(float)
    if (len(prices) != 1764 or not isinstance(prices.index, pd.DatetimeIndex)
            or prices.index.hasnans or not prices.index.is_unique or not prices.index.is_monotonic_increasing
            or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()):
        raise ValueError("Require 1764 ordered, finite, positive price observations per ticker")
    folder = Path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"purpose": "diagnostic_only", "promotion_eligible": False, "model_version": MODEL_VERSION,
                "price_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "tickers": args.tickers,
                "train_window": 504, "horizon": 63, "weight_periods": [3, 12],
                "origins": [str(prices.index[i].date()) for i in range(1259, len(prices) - 63, 63)],
                "sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                            ("src/backend/direct_horizon_forecast.py", "src/backend/forecast_models.py",
                             "tools/compare_adaptive_hybrid.py", "tools/compare_hybrid_history.py")}}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    records = {}
    with (folder / "components.jsonl").open("x") as output:
        for origin in range(503, len(prices) - 63, 63):
            for ticker in args.tickers:
                model = DirectARIMATransformerPredictor()
                try:
                    model.train_all(prices[ticker].iloc[origin - 503:origin + 1].to_numpy())
                    prediction = ARIMATransformerPredictor.predict(model, 63)
                finally:
                    model.cleanup()
                components = prediction.get("components", {})
                if set(components) != {"ARIMA", "Transformer"} or not np.isfinite(list(components.values())).all():
                    raise ValueError(f"Missing component at {origin} {ticker}: {prediction}")
                row = {"origin": str(prices.index[origin].date()), "index": origin, "ticker": ticker,
                       "outcome_date": str(prices.index[origin + 63].date()),
                       "arima": components["ARIMA"] / 4, "transformer": components["Transformer"] / 4,
                       "realized": float(np.log(prices[ticker].iloc[origin + 63] / prices[ticker].iloc[origin]))}
                records[(origin, ticker)] = row
                output.write(json.dumps(row, allow_nan=False) + "\n")
                output.flush()
                print(f"components {len(records)}/{20 * len(args.tickers)} {row['origin']} {ticker}", flush=True)
    rows = [mix_at_origin(records, i, t) for i in range(1259, len(prices) - 63, 63) for t in args.tickers]
    (folder / "rows.jsonl").write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows))
    result = {**manifest, **summarize(rows, METHODS), "units": "63_day_log_return"}
    (folder / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
