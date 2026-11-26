#!/usr/bin/env python3
"""Select 12 frozen Transformer configurations using past validation only."""
import argparse
import hashlib
import importlib.metadata
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/backend"))
from direct_horizon_forecast import build_transformer, supervised_returns, purged_split
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

CONFIGS = [dict(epochs=epochs, learning_rate=rate, patience=patience)
           for epochs in (5, 20, 50) for rate in (.001, .0003) for patience in (2, 5)]


def fit_candidate(prices, config):
    returns, x, y, ends = supervised_returns(prices, 63)
    train, validation = purged_split(ends, 63)
    xs = StandardScaler().fit(x[train].reshape(-1, 1))
    ys = StandardScaler().fit(y[train, None])
    scaled_x = xs.transform(x.reshape(-1, 1)).reshape(x.shape).astype("float32")
    scaled_y = ys.transform(y[:, None]).astype("float32")
    import tensorflow as tf
    model = build_transformer(True, 42)
    try:
        model.optimizer.learning_rate.assign(config["learning_rate"])
        fitted = model.fit(scaled_x[train], scaled_y[train],
                           validation_data=(scaled_x[validation], scaled_y[validation]),
                           epochs=config["epochs"], batch_size=32, shuffle=False, verbose=0,
                           callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss",
                                      patience=config["patience"], restore_best_weights=True)])
        values = ys.inverse_transform(np.asarray(model(scaled_x[validation], training=False))).ravel()
        rmse = float(np.sqrt(np.mean((values - y[validation]) ** 2)))
        tensor = xs.transform(returns[-60:, None])[None].astype("float32")
        prediction = float(ys.inverse_transform(np.asarray(model(tensor, training=False)).reshape(1, 1))[0, 0])
        if not np.isfinite([rmse, prediction]).all():
            raise ValueError("Nonfinite forecast or validation error")
        return {"validation_rmse": rmse, "prediction": prediction,
                "epochs_run": len(fitted.history["loss"]),
                "best_epoch": int(np.argmin(fitted.history["val_loss"])) + 1,
                "train_rows": len(train), "validation_rows": len(validation)}
    finally:
        tf.keras.backend.clear_session()


def choose_candidate(results):
    """Tie order is fixed in CONFIGS; no realized outcome is accepted here."""
    if len(results) != len(CONFIGS) or any(not np.isfinite(r["validation_rmse"]) for r in results):
        raise ValueError("Need all 12 finite validation results")
    return min(range(len(results)), key=lambda i: results[i]["validation_rmse"])


def metrics(rows, field):
    frame = pd.DataFrame(rows)
    error = frame[field] - frame["realized"]
    rank_ics = [g[field].corr(g.realized, method="spearman") for _, g in frame.groupby("origin")
                if len(g) >= 3 and g[field].nunique() > 1 and g.realized.nunique() > 1]
    return {"count": len(frame), "rmse": float(np.sqrt(np.mean(error ** 2))),
            "mae": float(np.mean(abs(error))), "mean_rank_ic": float(np.mean(rank_ics)) if rank_ics else None}


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source = Path(args.csv)
    raw = source.read_bytes()
    import io
    prices = pd.read_csv(io.BytesIO(raw), index_col=0, parse_dates=True).astype(float)
    if (len(prices) != 1008 or not isinstance(prices.index, pd.DatetimeIndex)
            or prices.index.hasnans or not prices.index.is_unique or not prices.index.is_monotonic_increasing
            or prices.columns.empty or not prices.columns.is_unique
            or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()):
        raise ValueError("Require 1008 ordered, finite, positive price observations per ticker")
    manifest = {"purpose": "consumed_historical_diagnostic_only", "promotion_eligible": False,
                "input_sha256": hashlib.sha256(raw).hexdigest(), "configs": CONFIGS,
                "seed": 42, "horizon": 63, "train_window": 504, "batch_size": 32,
                "selection": "minimum purged validation period RMSE per ticker and origin, fixed tie order",
                "evaluation": "next 63 returns excluded from fit and selection",
                "sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                            ("src/backend/direct_horizon_forecast.py", "tools/tune_direct_forecast.py")},
                "packages": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "tensorflow", "scikit-learn")}}
    folder = Path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("Input, code, settings or environment changed; cannot resume")
    else:
        write_json(manifest_path, manifest)
    rows = []
    total = 8 * len(prices.columns) * len(CONFIGS)
    done = 0
    for origin in range(503, len(prices) - 63, 63):
        for ticker_id, ticker in enumerate(prices.columns):
            history = prices[ticker].iloc[origin - 503:origin + 1].to_numpy()
            candidates = []
            for config_id, config in enumerate(CONFIGS):
                checkpoint = folder / f"fit-{origin}-{ticker_id}-{config_id}.json"
                if checkpoint.exists():
                    result = json.loads(checkpoint.read_text())
                else:
                    result = fit_candidate(history, config)
                    write_json(checkpoint, result)
                candidates.append(result)
                done += 1
                print(f"fit {done}/{total} {ticker} {prices.index[origin].date()} config={config_id}", flush=True)
            selected = choose_candidate(candidates)
            # Only now read the future outcome, after the configuration is locked.
            realized = float(np.log(prices[ticker].iloc[origin + 63] / prices[ticker].iloc[origin]))
            row = {"origin": str(prices.index[origin].date()), "ticker": ticker,
                   "outcome_date": str(prices.index[origin + 63].date()), "realized": realized,
                   "default": candidates[0]["prediction"], "tuned": candidates[selected]["prediction"],
                   "zero": 0., "selected_config": selected,
                   "selected_validation_rmse": candidates[selected]["validation_rmse"],
                   "selected_epochs_run": candidates[selected]["epochs_run"],
                   "selected_best_epoch": candidates[selected]["best_epoch"]}
            rows.append(row)
            write_json(folder / "rows.json", rows)
    frame = pd.DataFrame(rows)
    delta = ((frame.tuned - frame.realized) ** 2 - (frame.default - frame.realized) ** 2)
    summary = {**manifest, "metrics": {m: metrics(rows, m) for m in ("default", "tuned", "zero")},
               "selection_counts": dict(Counter(str(r["selected_config"]) for r in rows)),
               "paired_mse_tuned_minus_default": float(delta.mean()),
               "better_dates": int((delta.groupby(frame.origin).mean() < 0).sum()),
               "better_individual_predictions": int((delta < 0).sum()), "units": "63_day_log_return"}
    write_json(folder / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
