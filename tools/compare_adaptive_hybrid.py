#!/usr/bin/env python3
"""Compare hybrid components and weights using completed historical outcomes."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))
from direct_horizon_forecast import DirectARIMATransformerPredictor, MODEL_VERSION

METHODS = ("arima", "transformer", "equal", "adaptive")


def cross_error_weight(errors):
    """Use uncentered error cross-moments, then the same 50% shrinkage and bounds."""
    errors = np.asarray(errors, dtype=float)
    if errors.ndim != 2 or errors.shape[1] != 2 or len(errors) < 3 or not np.isfinite(errors).all():
        return .5
    arima, transformer = errors.T
    denominator = float(np.mean((arima - transformer) ** 2))
    if denominator <= 1e-12:
        return .5
    weight = np.mean(transformer ** 2 - arima * transformer) / denominator
    return float(.25 + .5 * np.clip(weight, 0, 1))


def summarize(rows, methods=METHODS):
    frame = pd.DataFrame(rows)
    complete = frame.dropna(subset=["realized", *methods])
    metrics = {}
    for method in methods:
        error = complete[method] - complete["realized"]
        correlations = []
        for _, group in complete.groupby("origin"):
            if len(group) >= 3 and group[method].nunique() > 1 and group["realized"].nunique() > 1:
                correlations.append(group[method].corr(group["realized"], method="spearman"))
        metrics[method] = {"count": len(complete),
                           "rmse": float(np.sqrt(np.mean(error ** 2))) if len(complete) else None,
                           "mae": float(np.mean(np.abs(error))) if len(complete) else None,
                           "mean_rank_ic": float(np.mean(correlations)) if correlations else None,
                           "rank_ic_periods": len(correlations)}
    return {"attempted": len(frame), "complete": len(complete), "metrics": metrics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--evaluation-start", type=pd.Timestamp)
    parser.add_argument("--cross-error", action="store_true", help="Also compare a research-only cross-error weight")
    args = parser.parse_args()
    source = Path(args.csv)
    raw = source.read_bytes()
    prices = pd.read_csv(source, index_col=0, parse_dates=True)
    if (not prices.index.is_unique or not prices.index.is_monotonic_increasing or
            prices.index.hasnans or any(t not in prices for t in args.tickers)):
        raise ValueError("Prices require unique, increasing dates and requested tickers")
    prices = prices[args.tickers].astype(float)
    if len(prices) < 567 or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Need at least 567 finite positive prices per ticker")
    origins = [i for i in range(503, len(prices) - 63, 63)
               if args.evaluation_start is None or prices.index[i] >= args.evaluation_start]
    if not origins:
        raise ValueError("No completed evaluation periods")
    folder = Path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"purpose": "diagnostic_only", "promotion_eligible": False,
                "input": str(source.resolve()), "input_sha256": hashlib.sha256(raw).hexdigest(),
                "model_version": MODEL_VERSION, "tickers": args.tickers,
                "horizon": 63, "train_window": 504,
                "origins": [str(prices.index[i].date()) for i in origins],
                "cross_error_comparison": args.cross_error,
                "model_source_sha256": hashlib.sha256((ROOT / "src/backend/direct_horizon_forecast.py").read_bytes()).hexdigest(),
                "weight_policy": "three_completed_equal_length_windows_or_equal_weights",
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    with (folder / "rows.jsonl").open("x") as output:
        for origin in origins:
            for ticker in args.tickers:
                series = prices[ticker]
                model = DirectARIMATransformerPredictor()
                try:
                    model.train_all(series.iloc[origin - 503:origin + 1].to_numpy(),
                                    calibration_prices=series.iloc[max(0, origin - 503 - 189):origin + 1].to_numpy())
                    prediction = model.predict(63)
                finally:
                    model.cleanup()
                components = prediction.get("components", {})
                arima, transformer = components.get("ARIMA"), components.get("Transformer")
                row = {"origin": str(prices.index[origin].date()),
                       "outcome_date": str(prices.index[origin + 63].date()), "ticker": ticker,
                       "realized": float(np.log(series.iloc[origin + 63] / series.iloc[origin])),
                       "arima": None if arima is None else arima / 4,
                       "transformer": None if transformer is None else transformer / 4,
                       "equal": None if arima is None or transformer is None else (arima + transformer) / 8,
                       "adaptive": None if arima is None or transformer is None else prediction["expected_return"] / 4,
                       "arima_weight": prediction.get("diagnostics", {}).get("arima_weight"),
                       "completed_weight_periods": prediction.get("diagnostics", {}).get("completed_weight_periods"),
                       "weight_history_sufficient": prediction.get("diagnostics", {}).get("weight_history_sufficient"),
                       "reason": prediction.get("reason")}
                if args.cross_error:
                    errors = prediction.get("diagnostics", {}).get("completed_weight_errors", [])
                    weight = cross_error_weight(errors)
                    row.update({"cross_error": None if arima is None or transformer is None else
                                (weight * arima + (1 - weight) * transformer) / 4,
                                "cross_error_arima_weight": weight, "completed_weight_errors": errors})
                rows.append(row)
                output.write(json.dumps(row, allow_nan=False) + "\n")
                output.flush()
                print(f"completed {row['origin']} {ticker}", flush=True)
    methods = (*METHODS, "cross_error") if args.cross_error else METHODS
    result = {**manifest, **summarize(rows, methods), "units": "63_day_log_return"}
    (folder / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
