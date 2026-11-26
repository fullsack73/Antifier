#!/usr/bin/env python3
"""Evaluate direct forecasts on completed, non-overlapping future periods."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from direct_horizon_forecast import DirectHorizonTransformerForecastModel, MODEL_VERSION


def evaluate(prices, horizon=63, train_window=504, model_factory=DirectHorizonTransformerForecastModel):
    """Fit at each origin using only its preceding window, then score completed returns."""
    if not isinstance(horizon, int) or isinstance(horizon, bool) or not 1 <= horizon <= 365:
        raise ValueError("horizon must be an integer between 1 and 365")
    if not isinstance(train_window, int) or isinstance(train_window, bool) or train_window < 100:
        raise ValueError("train_window must be an integer of at least 100")
    prices = pd.Series(prices, dtype=float)
    if not isinstance(prices.index, pd.DatetimeIndex) or prices.index.hasnans or not prices.index.is_unique or not prices.index.is_monotonic_increasing:
        raise ValueError("Prices require unique, increasing dates")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any():
        raise ValueError("Prices must be finite and positive; missing dates must not be dropped")

    rows = []
    for origin in range(train_window - 1, len(prices) - horizon, horizon):
        model = model_factory()
        try:
            model.train(prices.iloc[origin - train_window + 1:origin + 1].to_numpy())
            prediction = model.predict(horizon)
        finally:
            model.cleanup()
        predicted = prediction.get("expected_return")
        actual = float(np.log(prices.iloc[origin + horizon] / prices.iloc[origin]))
        row = {"origin": prices.index[origin].strftime("%Y-%m-%d"),
               "outcome_date": prices.index[origin + horizon].strftime("%Y-%m-%d"),
               "realized_period_log_return": actual, "source": prediction.get("source")}
        if predicted is None or not np.isfinite(predicted):
            row.update({"predicted_period_log_return": None, "error": None,
                        "validation_period_rmse": None, "failure": prediction.get("reason", "invalid forecast")})
        else:
            period = float(predicted) * horizon / 252
            row.update({"predicted_period_log_return": period, "error": actual - period,
                        "validation_period_rmse": prediction.get("diagnostics", {}).get("validation_period_rmse")})
        rows.append(row)

    errors = np.array([row["error"] for row in rows if row["error"] is not None])
    return {"purpose": "diagnostic_only", "promotion_eligible": False,
            "model_version": MODEL_VERSION, "horizon": horizon, "train_window": train_window,
            "units": "period_log_return", "origin_count": len(rows),
            "success_count": len(errors), "failure_count": len(rows) - len(errors),
            "rmse": float(np.sqrt(np.mean(errors ** 2))) if len(errors) else None,
            "mae": float(np.mean(np.abs(errors))) if len(errors) else None,
            "bias_actual_minus_prediction": float(np.mean(errors)) if len(errors) else None,
            "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Wide CSV: first column date, remaining columns ticker prices")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--output", required=True, help="New JSON output path")
    parser.add_argument("--horizon", type=int, default=63)
    parser.add_argument("--train-window", type=int, default=504)
    args = parser.parse_args()
    path = Path(args.csv)
    output = Path(args.output)
    if output.exists():
        parser.error("output already exists")
    raw = path.read_bytes()
    import io
    frame = pd.read_csv(io.BytesIO(raw), index_col=0, parse_dates=True)
    if args.ticker not in frame.columns:
        parser.error("ticker not found in CSV")
    result = evaluate(frame[args.ticker], args.horizon, args.train_window)
    result.update({"ticker": args.ticker, "input_path": str(path.resolve()),
                   "input_sha256": hashlib.sha256(raw).hexdigest()})
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Saved {result['success_count']}/{result['origin_count']} forecasts to {output}")


if __name__ == "__main__":
    main()
