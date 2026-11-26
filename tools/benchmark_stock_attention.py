#!/usr/bin/env python3
"""Time a small joint temporal model with/without cross-stock attention."""
import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/backend"))
from direct_horizon_forecast import supervised_returns, purged_split
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


def prepare(prices, horizon=63):
    if isinstance(horizon, (bool, np.bool_)) or not isinstance(horizon, (int, np.integer)) or horizon <= 0:
        raise ValueError("Require a positive integer forecast horizon")
    values = np.asarray(prices, dtype=float)
    if values.ndim != 2 or len(values) != 504 + horizon or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError(f"Require {504 + horizon} finite positive prices for each stock")
    histories = [supervised_returns(values[:504, i], horizon) for i in range(values.shape[1])]
    x = np.stack([h[1] for h in histories], axis=1)
    y = np.stack([h[2] for h in histories], axis=1)
    train, validation = purged_split(histories[0][3], horizon)
    xs = StandardScaler().fit(x[train].reshape(-1, 1))
    ys = StandardScaler().fit(y[train].reshape(-1, 1))
    scaled_x = xs.transform(x.reshape(-1, 1)).reshape(x.shape).astype("float32")
    scaled_y = ys.transform(y.reshape(-1, 1)).reshape(y.shape).astype("float32")
    latest = np.stack([h[0][-60:] for h in histories])[None, ..., None]
    latest = xs.transform(latest.reshape(-1, 1)).reshape(latest.shape).astype("float32")
    realized = np.log(values[-1] / values[503])
    return scaled_x, scaled_y, train, validation, latest, ys, realized


def build_model(stocks, cross_stock, seed):
    import tensorflow as tf
    from tensorflow.keras import layers
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)
    inputs = tf.keras.Input((stocks, 60, 1))
    x = layers.Dense(32)(inputs)
    angles = np.arange(60)[:, None] / np.power(10000., 2 * (np.arange(32) // 2) / 32)
    encoding = np.where(np.arange(32) % 2 == 0, np.sin(angles), np.cos(angles)).astype("float32")
    x = x + tf.constant(encoding[None, None])
    attention = layers.MultiHeadAttention(num_heads=2, key_dim=16, dropout=.1,
                                         attention_axes=(2,), name="temporal_attention")(x, x)
    x = layers.LayerNormalization(epsilon=1e-6)(x + layers.Dropout(.1)(attention))
    ff = layers.Dense(64, activation="relu")(x)
    ff = layers.Dense(32)(ff)
    x = layers.LayerNormalization(epsilon=1e-6)(x + layers.Dropout(.1)(ff))
    x = layers.Lambda(lambda value: tf.reduce_mean(value, axis=2), name="temporal_pool")(x)
    if cross_stock:
        attention = layers.MultiHeadAttention(num_heads=2, key_dim=16, dropout=.1,
                                             attention_axes=(1,), name="stock_attention")(x, x)
        x = layers.LayerNormalization(epsilon=1e-6)(x + layers.Dropout(.1)(attention))
    x = layers.Dense(32, activation="relu")(x)
    x = layers.Dropout(.1)(x)
    output = layers.Reshape((stocks,))(layers.Dense(1)(x))
    model = tf.keras.Model(inputs, output)
    model.compile(optimizer=tf.keras.optimizers.Adam(.001), loss="mse")
    return model


def benchmark(x, y, train, validation, latest, cross_stock, seed):
    import tensorflow as tf
    epoch_seconds = []
    class Timer(tf.keras.callbacks.Callback):
        def on_epoch_begin(self, epoch, logs=None):
            self.started = time.perf_counter()

        def on_epoch_end(self, epoch, logs=None):
            epoch_seconds.append(time.perf_counter() - self.started)

    started = time.perf_counter()
    model = build_model(x.shape[1], cross_stock, seed)
    build_seconds = time.perf_counter() - started
    try:
        started = time.perf_counter()
        model.fit(x[train], y[train], validation_data=(x[validation], y[validation]),
                  epochs=5, batch_size=8, shuffle=False, verbose=0, callbacks=[Timer()])
        fit_seconds = time.perf_counter() - started
        @tf.function(input_signature=[tf.TensorSpec(latest.shape, tf.float32)])
        def predict(tensor):
            return model(tensor, training=False)
        tensor = tf.constant(latest)
        started = time.perf_counter()
        prediction = predict(tensor).numpy()
        first_inference_seconds = time.perf_counter() - started
        for _ in range(5):
            predict(tensor).numpy()
        inference = []
        for _ in range(30):
            started = time.perf_counter()
            predict(tensor).numpy()
            inference.append(time.perf_counter() - started)
        if not np.isfinite(prediction).all():
            raise ValueError("Nonfinite model output")
        return {"cross_stock": cross_stock, "seed": seed, "parameters": model.count_params(),
                "build_seconds": build_seconds, "fit_seconds": fit_seconds,
                "epoch_seconds": epoch_seconds, "warm_epoch_median_seconds": float(np.median(epoch_seconds[1:])),
                "first_inference_seconds": first_inference_seconds,
                "warm_inference_median_seconds": float(np.median(inference)),
                "scaled_prediction": prediction.ravel().tolist()}
    finally:
        tf.keras.backend.clear_session()


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source = Path(args.csv)
    prices = pd.read_csv(source, index_col=0, parse_dates=True)
    if (prices.shape != (567, 10) or not isinstance(prices.index, pd.DatetimeIndex)
            or prices.index.hasnans or not prices.index.is_unique or not prices.index.is_monotonic_increasing
            or not prices.columns.is_unique):
        raise ValueError("Require ordered 567-date, 10-stock price matrix")
    x, y, train, validation, latest, ys, realized = prepare(prices)
    folder = Path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=False)
    before_tf = time.perf_counter()
    import tensorflow as tf
    tf_import_seconds = time.perf_counter() - before_tf
    manifest = {"purpose": "timing_diagnostic_only", "promotion_eligible": False,
                "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "tickers": list(prices.columns), "origin": str(prices.index[503].date()),
                "outcome_date": str(prices.index[-1].date()), "epochs": 5, "batch_dates": 8,
                "train_dates": len(train), "validation_dates": len(validation),
                "tensorflow": tf.__version__, "devices": [d.name for d in tf.config.list_logical_devices()],
                "platform": platform.platform(), "cpu_count": os.cpu_count(),
                "tf_intra_threads_env": os.environ.get("TF_NUM_INTRAOP_THREADS"),
                "tf_inter_threads_env": os.environ.get("TF_NUM_INTEROP_THREADS"),
                "tf_import_seconds": tf_import_seconds}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    for seed in (42, 43, 44):
        for cross_stock in ((False, True) if seed != 43 else (True, False)):
            result = benchmark(x, y, train, validation, latest, cross_stock, seed)
            prediction = ys.inverse_transform(np.array(result.pop("scaled_prediction"))[:, None]).ravel()
            result.update({"prediction": prediction.tolist(), "realized": realized.tolist(),
                           "period_rmse": float(np.sqrt(np.mean((prediction - realized) ** 2)))})
            rows.append(result)
            (folder / "runs.json").write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
            print(f"seed={seed} cross_stock={cross_stock} fit={result['fit_seconds']:.3f}s", flush=True)
    summary = {}
    for flag, name in ((False, "temporal_only"), (True, "temporal_plus_stock")):
        group = [r for r in rows if r["cross_stock"] == flag]
        summary[name] = {key: float(np.median([r[key] for r in group])) for key in
                         ("fit_seconds", "warm_epoch_median_seconds", "warm_inference_median_seconds", "parameters")}
    summary["fit_time_ratio"] = summary["temporal_plus_stock"]["fit_seconds"] / summary["temporal_only"]["fit_seconds"]
    summary["main_total_seconds"] = time.perf_counter() - started
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
