#!/usr/bin/env python3
"""Paired walk-forward diagnostic of joint models with/without stock attention."""
import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.benchmark_stock_attention import benchmark, prepare
import numpy as np
import pandas as pd

METHODS = ("temporal_only", "cross_stock", "zero")


def score(rows, method):
    frame = pd.DataFrame(rows)
    error = frame[method] - frame.realized
    correlations, spreads = [], []
    for _, group in frame.groupby(["seed", "origin"]):
        if len(group) >= 3 and group[method].nunique() > 1 and group.realized.nunique() > 1:
            correlations.append(group[method].corr(group.realized, method="spearman"))
        if group[method].nunique() > 1:
            ordered = group.sort_values(method)
            size = max(1, int(np.ceil(len(group) * .2)))
            spreads.append(float(ordered.tail(size).realized.mean() - ordered.head(size).realized.mean()))
    return {"rows": len(frame), "unique_stock_dates": len(frame.drop_duplicates(["ticker", "origin"])),
            "rmse": float(np.sqrt(np.mean(error ** 2))), "mae": float(np.mean(abs(error))),
            "mean_rank_ic": float(np.mean(correlations)) if correlations else None,
            "mean_top_bottom_log_return_spread": float(np.mean(spreads)) if spreads else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source = Path(args.csv)
    raw = source.read_bytes()
    import io
    prices = pd.read_csv(io.BytesIO(raw), index_col=0, parse_dates=True).astype(float)
    if (len(prices) != 1008 or len(prices.columns) < 3 or not isinstance(prices.index, pd.DatetimeIndex)
            or prices.index.hasnans or not prices.index.is_unique or not prices.index.is_monotonic_increasing
            or not prices.columns.is_unique or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()):
        raise ValueError("Require 1008 ordered positive price observations per stock, at least 3 stocks")
    folder = Path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"purpose": "consumed_historical_diagnostic_only", "promotion_eligible": False,
                "input_sha256": hashlib.sha256(raw).hexdigest(), "tickers": list(prices.columns),
                "seeds": [42, 43, 44], "epochs": 5, "batch_dates": 8, "horizon": 63, "train_window": 504,
                "sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                            ("tools/evaluate_stock_attention.py", "tools/benchmark_stock_attention.py",
                             "src/backend/direct_horizon_forecast.py")},
                "packages": {name: importlib.metadata.version(name) for name in
                             ("tensorflow", "numpy", "pandas", "scikit-learn")}}
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("Code, data or environment changed; cannot resume")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    for origin in range(503, len(prices) - 63, 63):
        x, y, train, validation, latest, ys, realized = prepare(prices.iloc[origin - 503:origin + 64])
        for seed in manifest["seeds"]:
            predictions = {}
            for cross in ((False, True) if seed != 43 else (True, False)):
                method = "cross_stock" if cross else "temporal_only"
                path = folder / f"fit-{origin}-{seed}-{method}.json"
                if path.exists():
                    result = json.loads(path.read_text())
                else:
                    result = benchmark(x, y, train, validation, latest, cross, seed)
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
                    temporary.replace(path)
                predictions[method] = ys.inverse_transform(np.array(result["scaled_prediction"])[:, None]).ravel()
                print(f"completed {prices.index[origin].date()} seed={seed} {method} fit={result['fit_seconds']:.2f}s", flush=True)
            for i, ticker in enumerate(prices.columns):
                rows.append({"origin": str(prices.index[origin].date()),
                             "outcome_date": str(prices.index[origin + 63].date()), "seed": seed, "ticker": ticker,
                             "realized": float(realized[i]), "zero": 0.,
                             **{m: float(predictions[m][i]) for m in ("temporal_only", "cross_stock")}})
            (folder / "rows.json").write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
    summary = {**manifest, "metrics": {m: score(rows, m) for m in METHODS},
               "by_seed": {str(seed): {m: score([r for r in rows if r["seed"] == seed], m) for m in METHODS}
                           for seed in manifest["seeds"]}}
    frame = pd.DataFrame(rows)
    loss = (frame.cross_stock - frame.realized) ** 2 - (frame.temporal_only - frame.realized) ** 2
    dates = loss.groupby(frame.origin).mean()
    bootstrap = dates.to_numpy()[np.random.default_rng(42).integers(0, 8, size=(20000, 8))].mean(axis=1)
    summary.update({"paired_mse_cross_minus_temporal": float(loss.mean()),
                    "better_dates": int((dates < 0).sum()), "date_count": len(dates),
                    "descriptive_date_bootstrap_95_interval": np.quantile(bootstrap, [.025, .975]).tolist()})
    (folder / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
