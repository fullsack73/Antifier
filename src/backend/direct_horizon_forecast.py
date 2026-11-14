"""Direct-horizon Transformer used by opt-in production forecasts."""

from native_threading import configure_native_threading
configure_native_threading()

import logging
import numpy as np
from sklearn.preprocessing import StandardScaler
from forecast_models import ARIMATransformerPredictor, no_view_prediction

logger = logging.getLogger(__name__)
MODEL_VERSION = "direct-horizon-v1"


def supervised_returns(prices, horizon=1, lookback=60):
    """Keep original time positions; reject gaps rather than compressing time."""
    prices = np.asarray(prices, dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Training prices must be consecutive, finite and positive")
    returns = np.diff(np.log(prices))
    ends = np.arange(lookback, len(returns) - horizon + 1)
    if len(ends) < 40:
        raise ValueError("Insufficient completed training targets")
    x = np.array([returns[i - lookback:i] for i in ends])[..., None]
    y = np.array([returns[i:i + horizon].sum() for i in ends])
    return returns, x, y, ends


def purged_split(ends, horizon, fraction=0.1):
    split = int(len(ends) * (1 - fraction))
    validation_start = ends[split]
    train = np.flatnonzero(ends + horizon <= validation_start)
    validation = np.arange(split, len(ends))
    if len(train) < 20 or len(validation) < 2:
        raise ValueError("Insufficient purged train/validation rows")
    return train, validation


def build_transformer(position=False, seed=42):
    """Same house architecture; the only architectural factor is position."""
    import tensorflow as tf
    from tensorflow.keras import layers

    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)
    inputs = tf.keras.Input((60, 1))
    x = layers.Dense(32)(inputs)
    if position:
        angles = np.arange(60)[:, None] / np.power(10000.0, 2 * (np.arange(32) // 2) / 32)
        encoding = np.where(np.arange(32) % 2 == 0, np.sin(angles), np.cos(angles)).astype("float32")
        x = x + tf.constant(encoding[None])
    attention = layers.MultiHeadAttention(num_heads=2, key_dim=16, dropout=0.1)(x, x)
    x = layers.LayerNormalization(epsilon=1e-6)(x + layers.Dropout(0.1)(attention))
    ff = layers.Dense(64, activation="relu")(x)
    ff = layers.Dense(32)(ff)
    x = layers.LayerNormalization(epsilon=1e-6)(x + layers.Dropout(0.1)(ff))
    x = layers.GlobalAveragePooling1D()(x)
    x = layers.Dense(32, activation="relu")(x)
    out = layers.Dense(1)(layers.Dropout(0.1)(x))
    model = tf.keras.Model(inputs, out)
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.001), loss="mse")
    return model


class DirectHorizonTransformerForecastModel:
    """Train one direct cumulative-log-return head for each requested horizon."""

    def __init__(self, epochs=5, random_state=42):
        self.epochs = int(epochs)
        self.random_state = int(random_state)
        self.history = None
        self.predictions = {}

    def train(self, prices):
        self.cleanup()
        values = np.asarray(prices, dtype=float)
        if values.ndim != 1 or len(values) < 100 or not np.isfinite(values).all() or (values <= 0).any():
            return
        self.history = values.copy()

    def cleanup(self):
        self.history = None
        self.predictions = {}

    def _predict_period(self, horizon):
        returns, x, y, ends = supervised_returns(self.history, horizon)
        tr, va = purged_split(ends, horizon)
        import tensorflow as tf
        xs = StandardScaler().fit(x[tr].reshape(-1, 1))
        ys = StandardScaler().fit(y[tr, None])
        scaled_x = xs.transform(x.reshape(-1, 1)).reshape(x.shape).astype("float32")
        scaled_y = ys.transform(y[:, None]).astype("float32")
        model = build_transformer(False, self.random_state)
        try:
            fitted = model.fit(scaled_x[tr], scaled_y[tr], validation_data=(scaled_x[va], scaled_y[va]),
                               epochs=self.epochs, batch_size=32, shuffle=False, verbose=0,
                               callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=2, restore_best_weights=True)])
            tensor = xs.transform(returns[-60:, None])[None].astype("float32")
            period = float(ys.inverse_transform(np.asarray(model(tensor, training=False)).reshape(1, 1))[0, 0])
            validation = ys.inverse_transform(np.asarray(model(scaled_x[va], training=False))).ravel()
            rmse = float(np.sqrt(np.mean((validation - y[va]) ** 2)))
            if not np.isfinite([period, rmse]).all():
                raise ValueError("Nonfinite direct-horizon forecast")
            return {"period_log_return": period, "validation_period_rmse": rmse,
                    "train_rows": len(tr), "validation_rows": len(va),
                    "epochs_run": len(fitted.history["loss"])}
        finally:
            tf.keras.backend.clear_session()

    def predict(self, horizon=252):
        if self.history is None:
            return no_view_prediction("Direct-horizon Transformer has no valid training history")
        try:
            if isinstance(horizon, bool) or int(horizon) != horizon or not 1 <= int(horizon) <= 365:
                raise ValueError("Forecast horizon must be an integer between 1 and 365")
            horizon = int(horizon)
            if horizon not in self.predictions:
                self.predictions[horizon] = self._predict_period(horizon)
            result = self.predictions[horizon]
            annual = result["period_log_return"] * 252 / horizon
            uncertainty = max(.01, result["validation_period_rmse"] * 252 / horizon)
            if not np.isfinite([annual, uncertainty]).all():
                raise ValueError("Nonfinite annual forecast")
            return {"expected_return": float(annual), "uncertainty": float(uncertainty),
                    "source": "transformer", "components": {"Transformer": float(annual)},
                    "diagnostics": {**result, "model_version": MODEL_VERSION, "forecast_kind": "direct",
                                    "horizon": horizon, "uncertainty_source": "purged_validation_period_rmse",
                                    "uncertainty_is_calibrated": False, "annual_clip_boundary_hit": False}}
        except Exception as exc:
            logger.warning("Direct-horizon Transformer no-view: %s", exc)
            return no_view_prediction(str(exc))

    def forecast(self, horizon=252, annualize=True):
        result = self.predict(horizon)
        value = result["expected_return"]
        return value if value is None or annualize else value * int(horizon) / 252


class DirectARIMATransformerPredictor(ARIMATransformerPredictor):
    """Keep the hybrid API and ARIMA component, replace its Transformer head."""

    def __init__(self, transformer_kwargs=None):
        super().__init__()
        self.transformer = DirectHorizonTransformerForecastModel(**(transformer_kwargs or {}))

    def train_all(self, prices):
        self.history = None
        self.transformer.train(prices)
        if self.transformer.history is not None:
            self.history = self.transformer.history.copy()
