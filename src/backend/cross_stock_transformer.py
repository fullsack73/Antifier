"""Portfolio-wide Transformer approved for production by the user on 2026-11-24."""
from native_threading import configure_native_threading
configure_native_threading()

import hashlib
import json
import logging
import multiprocessing as mp
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from direct_horizon_forecast import supervised_returns, purged_split
from forecast_models import no_view_prediction

MODEL_VERSION = "cross-stock-mse-corr-v1"
SEEDS = (42, 43, 44)
logger = logging.getLogger(__name__)


def prepare_training(prices, horizon=63):
    if isinstance(horizon, (bool, np.bool_)) or not isinstance(horizon, (int, np.integer)) or not 1 <= horizon <= 365:
        raise ValueError("Invalid forecast horizon")
    values = np.asarray(prices, dtype=float)
    if values.ndim != 2 or values.shape[0] != 504 or values.shape[1] < 2:
        raise ValueError("Require 504 common price dates and at least two stocks")
    histories = [supervised_returns(values[:, i], horizon) for i in range(values.shape[1])]
    x = np.stack([h[1] for h in histories], axis=1)
    y = np.stack([h[2] for h in histories], axis=1)
    train, validation = purged_split(histories[0][3], horizon)
    xs = StandardScaler().fit(x[train].reshape(-1, 1))
    ys = StandardScaler().fit(y[train].reshape(-1, 1))
    x = xs.transform(x.reshape(-1, 1)).reshape(x.shape).astype("float32")
    y = ys.transform(y.reshape(-1, 1)).reshape(y.shape).astype("float32")
    latest = np.stack([h[0][-60:] for h in histories])[None, ..., None]
    latest = xs.transform(latest.reshape(-1, 1)).reshape(latest.shape).astype("float32")
    return x, y, train, validation, latest, ys


def build_model(stocks, seed):
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
    attention = layers.MultiHeadAttention(num_heads=2, key_dim=16, dropout=.1,
                                         attention_axes=(1,), name="stock_attention")(x, x)
    x = layers.LayerNormalization(epsilon=1e-6)(x + layers.Dropout(.1)(attention))
    x = layers.Dense(32, activation="relu")(x)
    x = layers.Dropout(.1)(x)
    output = layers.Reshape((stocks,))(layers.Dense(1)(x))
    model = tf.keras.Model(inputs, output)
    # Match the frozen research builder's compile before replacing its loss.
    model.compile(optimizer=tf.keras.optimizers.Adam(.001), loss="mse")
    return model


def correlation_loss(actual, predicted):
    import tensorflow as tf
    mse = tf.reduce_mean(tf.square(predicted - actual))
    a = actual - tf.reduce_mean(actual, axis=-1, keepdims=True)
    p = predicted - tf.reduce_mean(predicted, axis=-1, keepdims=True)
    variance_a = tf.reduce_mean(a * a, axis=-1)
    correlation = tf.reduce_mean(a * p, axis=-1) / tf.sqrt(variance_a * tf.reduce_mean(p * p, axis=-1) + 1e-6)
    extra = tf.reduce_mean(tf.where(variance_a > 1e-8, 1 - correlation, tf.zeros_like(correlation)))
    return .5 * mse + .5 * extra


def predict_panel(prices, horizon=63, progress=None):
    import tensorflow as tf
    x, y, train, validation, latest, scaler = prepare_training(prices, horizon)
    forecasts, validations = [], []
    batch = min(8, max(1, 176 // len(prices.columns)))
    try:
        for done, seed in enumerate(SEEDS, 1):
            model = build_model(len(prices.columns), seed)
            model.compile(optimizer=tf.keras.optimizers.Adam(.001), loss=correlation_loss)
            model.fit(x[train], y[train], validation_data=(x[validation], y[validation]),
                      epochs=5, batch_size=batch, shuffle=False, verbose=0)
            prediction = model(latest, training=False).numpy().ravel()
            forecasts.append(scaler.inverse_transform(prediction[:, None]).ravel())
            valid_prediction = np.concatenate([model(x[validation[i:i + batch]], training=False).numpy()
                                               for i in range(0, len(validation), batch)])
            validations.append(scaler.inverse_transform(valid_prediction.reshape(-1, 1)).reshape(valid_prediction.shape))
            if progress:
                progress(done)
            tf.keras.backend.clear_session()
        period = np.mean(np.asarray(forecasts, dtype=float), axis=0)
        actual = scaler.inverse_transform(y[validation].reshape(-1, 1)).reshape(y[validation].shape)
        rmse = np.sqrt(np.mean((np.mean(validations, axis=0) - actual) ** 2, axis=0))
        if not np.isfinite(period).all() or not np.isfinite(rmse).all():
            raise ValueError("Nonfinite joint prediction")
        return {ticker: {"expected_return": float(period[i] * 252 / horizon),
                         "uncertainty": float(np.clip(rmse[i] * 252 / horizon, 1e-4, 5.)),
                         "source": "cross_stock_transformer", "diagnostics": {
                             "model_version": MODEL_VERSION, "horizon": int(horizon),
                             "period_log_return": float(period[i]), "seeds": list(SEEDS),
                             "cohort_size": len(prices.columns), "batch_dates": batch,
                             "validation_period_rmse": float(rmse[i]), "uncertainty_is_calibrated": False}}
                for i, ticker in enumerate(prices.columns)}
    finally:
        tf.keras.backend.clear_session()


def panel_cache_key(prices, horizon):
    identity = json.dumps([MODEL_VERSION, list(prices.columns), int(horizon)], separators=(",", ":"))
    payload = identity.encode() + prices.index.asi8.tobytes() + np.asarray(prices, dtype="<f8").tobytes()
    return f"{MODEL_VERSION}_" + hashlib.sha256(payload).hexdigest()


def _worker(prices, horizon, connection):
    try:
        result = predict_panel(prices, horizon, progress=lambda done: connection.send(("progress", done)))
        connection.send(("result", result))
    except Exception as exc:
        connection.send(("error", str(exc)))
    finally:
        connection.close()


def forecast_panel(data, horizon=63, progress_callback=None, cancel_event=None):
    from cache_manager import get_cache
    from portfolio_optimization import _raise_if_cancelled, OptimizationCancelled
    _raise_if_cancelled(cancel_event)
    if (not isinstance(data, pd.DataFrame) or not isinstance(data.index, pd.DatetimeIndex)
            or data.columns.has_duplicates or data.index.has_duplicates or data.index.hasnans
            or not data.index.is_monotonic_increasing):
        raise ValueError("Joint forecasts require unique ordered price dates and tickers")
    frame = data.tail(504)
    valid = [t for t in frame if np.isfinite(frame[t]).all() and (frame[t] > 0).all()]
    missing = {t: no_view_prediction("invalid common price history") for t in frame if t not in valid}
    frame = frame[valid]
    if len(frame) != 504 or len(valid) < 2:
        return {t: no_view_prediction("need 504 common prices and at least two stocks") for t in data}
    # Validate horizon before cache lookup, so bool/float values cannot alias an integer key.
    if isinstance(horizon, (bool, np.bool_)) or not isinstance(horizon, (int, np.integer)) or not 1 <= horizon <= 365:
        return {t: no_view_prediction("invalid forecast horizon") for t in data}
    key = panel_cache_key(frame, horizon)
    cache = get_cache()
    cached = cache.get(key)
    if cached is not None:
        if progress_callback:
            progress_callback(3, 3, "Joint Transformer cache hit")
        return {**missing, **cached}
    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(frame, horizon, child))
    result = None
    try:
        process.start()
        child.close()
        while process.is_alive() or parent.poll():
            _raise_if_cancelled(cancel_event)
            if not parent.poll(.25):
                continue
            try:
                kind, value = parent.recv()
            except EOFError:
                break
            if kind == "error":
                raise RuntimeError(value)
            if kind == "result":
                result = value
                break
            if progress_callback:
                progress_callback(value, 3, f"Joint Transformer training {value}/3")
        _raise_if_cancelled(cancel_event)
        if result is None:
            raise RuntimeError("Joint forecast worker exited without a result")
        if set(result) != set(valid) or any(v.get("expected_return") is None for v in result.values()):
            raise ValueError("Incomplete joint forecast result")
        cache.set(key, result, l1_ttl=900, l2_ttl=14400)
        return {**missing, **result}
    except OptimizationCancelled:
        raise
    except Exception:
        logger.exception("Joint Transformer forecast failed")
        return {t: no_view_prediction("joint Transformer training failed") for t in data}
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join()
        parent.close()
        child.close()
