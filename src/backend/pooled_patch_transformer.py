"""Research-only pooled Patch Transformer for cross-sectional alpha signals.

The production optimizer intentionally does not import this module.  It trains a
single model across dates and assets, predicts forward returns directly at
multiple horizons, and evaluates the primary horizon before any portfolio
construction is attempted.
"""

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from cross_sectional_forecast import (
    FACTOR_PIT_FEATURE_COLUMNS,
    POOLED_FEATURE_COLUMNS,
    pooled_point_in_time_features,
    pooled_price_features,
)
from forecast_signal_research import (
    cross_sectional_rank_diagnostics,
    paired_rank_signal_block_bootstrap,
    prediction_distribution_diagnostics,
    rank_signal_block_bootstrap,
    sequential_forecast_confidence_gate,
    signal_only_gate,
)
from portfolio_alpha_v2 import (
    factor_residual_forward_returns,
    point_in_time_snapshot,
)


logger = logging.getLogger(__name__)

PATCH_CHANNELS = (
    "close_return",
    "intraday_return",
    "high_low_range",
    "volume_change",
    "market_return",
    "relative_return",
)
KRONOS_CONTEXT_COLUMNS = ("kronos_score", "kronos_missing")


@dataclass(frozen=True)
class PatchTransformerConfig:
    """Frozen research specification for the compact pooled model."""

    lookback: int = 504
    patch_size: int = 5
    horizons: tuple = (21, 63)
    d_model: int = 32
    num_heads: int = 4
    ff_dim: int = 64
    num_blocks: int = 2
    dense_units: int = 32
    dropout: float = 0.15
    learning_rate: float = 5e-4
    weight_decay: float = 1e-4
    epochs: int = 12
    batch_size: int = 32
    patience: int = 3
    validation_periods: int = 2
    random_state: int = 42

    def normalized(self):
        horizons = tuple(sorted({max(1, int(value)) for value in self.horizons}))
        lookback = max(40, int(self.lookback))
        patch_size = max(2, int(self.patch_size))
        if lookback // patch_size < 4:
            raise ValueError("Patch Transformer requires at least four patches")
        return PatchTransformerConfig(
            lookback=lookback,
            patch_size=patch_size,
            horizons=horizons,
            d_model=max(8, int(self.d_model)),
            num_heads=max(1, int(self.num_heads)),
            ff_dim=max(8, int(self.ff_dim)),
            num_blocks=max(1, int(self.num_blocks)),
            dense_units=max(4, int(self.dense_units)),
            dropout=float(np.clip(self.dropout, 0.0, 0.8)),
            learning_rate=max(1e-6, float(self.learning_rate)),
            weight_decay=max(0.0, float(self.weight_decay)),
            epochs=max(1, int(self.epochs)),
            batch_size=max(1, int(self.batch_size)),
            patience=max(0, int(self.patience)),
            validation_periods=max(1, int(self.validation_periods)),
            random_state=int(self.random_state),
        )


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_kronos_checkpoint(path, expected_horizon=None):
    """Load frozen Kronos scores as exact-date, exact-ticker context features."""
    path = Path(path).expanduser().resolve()
    signatures = []
    rows = []
    case_universes = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            signature = dict(payload.get("signature") or {})
            origin = dict(payload.get("origin") or {})
            if not signature or not origin:
                raise ValueError(
                    f"Invalid Kronos checkpoint row {line_number}: missing signature/origin"
                )
            signatures.append(signature)
            horizon = int(origin.get("horizon", 0))
            if expected_horizon is not None and horizon != int(expected_horizon):
                raise ValueError(
                    f"Kronos horizon mismatch at row {line_number}: "
                    f"{horizon} != {int(expected_horizon)}"
                )
            as_of_date = pd.Timestamp(origin["train_end"]).tz_localize(None)
            case_id = str(origin.get("case_id") or "unknown")
            scores = dict(origin.get("scores") or {})
            case_universes.setdefault(case_id, set()).update(scores)
            for ticker, score in scores.items():
                value = float(score)
                if not np.isfinite(value):
                    continue
                rows.append({
                    "as_of_date": as_of_date,
                    "ticker": str(ticker).strip().upper(),
                    "kronos_score": value,
                    "case_id": case_id,
                    "period_id": str(origin.get("period_id") or ""),
                    "horizon": horizon,
                })
    if not rows:
        raise ValueError("Kronos checkpoint contains no finite scores")
    canonical_signatures = {
        json.dumps(signature, sort_keys=True, separators=(",", ":"))
        for signature in signatures
    }
    if len(canonical_signatures) != 1:
        raise ValueError("Kronos checkpoint mixes incompatible signatures")
    frame = pd.DataFrame.from_records(rows)
    duplicates = frame.duplicated(["as_of_date", "ticker"], keep=False)
    if bool(duplicates.any()):
        raise ValueError("Kronos checkpoint has duplicate date/ticker scores")
    frame = frame.sort_values(["as_of_date", "ticker"]).reset_index(drop=True)
    return frame, {
        "checkpoint": str(path),
        "checkpoint_sha256": _sha256(path),
        "signature": signatures[0],
        "origin_count": int(frame["period_id"].nunique()),
        "score_count": int(len(frame)),
        "case_universes": {
            key: sorted(value) for key, value in sorted(case_universes.items())
        },
    }


def _clean_price_frame(price_data):
    prices = pd.DataFrame(price_data).copy()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    prices = prices.sort_index().apply(pd.to_numeric, errors="coerce")
    return prices.replace([np.inf, -np.inf], np.nan).ffill().dropna(
        axis=1,
        how="all",
    )


def ohlcv_panels(ohlcv_data):
    """Convert long OHLCV rows to aligned wide panels without leading fill."""
    frame = pd.DataFrame(ohlcv_data).copy()
    required = {"timestamp", "ticker", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("OHLCV data is missing: " + ", ".join(missing))
    frame["timestamp"] = pd.to_datetime(frame["timestamp"]).dt.tz_localize(None)
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    panels = {}
    close = None
    for field in ("open", "high", "low", "close", "volume"):
        if field not in frame:
            continue
        values = pd.to_numeric(frame[field], errors="coerce")
        panel = frame.assign(_value=values).pivot(
            index="timestamp",
            columns="ticker",
            values="_value",
        ).sort_index()
        panels[field] = panel
        if field == "close":
            close = panel
    if close is None:
        raise ValueError("OHLCV data did not produce a close panel")
    for field in ("open", "high", "low"):
        panels.setdefault(field, close.copy())
    panels.setdefault(
        "volume",
        pd.DataFrame(np.nan, index=close.index, columns=close.columns),
    )
    return panels


def _standardize_time_channel(values):
    series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan)
    valid = series.dropna()
    if valid.empty:
        return np.zeros(len(series), dtype=np.float32)
    median = float(valid.median())
    scale = float((valid - median).abs().median()) * 1.4826
    if not np.isfinite(scale) or scale <= 1e-8:
        scale = float(valid.std(ddof=0))
    if not np.isfinite(scale) or scale <= 1e-8:
        scale = 1.0
    return (
        ((series.fillna(median) - median) / scale)
        .clip(-8.0, 8.0)
        .to_numpy(dtype=np.float32)
    )


def make_patch_tokens(
    panels,
    ticker,
    *,
    end_position,
    lookback=504,
    patch_size=5,
):
    """Build ordered OHLCV/market patch tokens using history only."""
    close = _clean_price_frame(panels["close"])
    ticker = str(ticker).strip().upper()
    if ticker not in close:
        return None
    lookback = max(40, int(lookback))
    patch_size = max(2, int(patch_size))
    end_position = int(end_position)
    start_position = end_position - lookback
    if start_position < 0 or end_position >= len(close):
        return None
    window_index = close.index[start_position:end_position + 1]
    ticker_close = close.loc[window_index, ticker]
    if ticker_close.isna().any() or (ticker_close <= 0).any():
        return None

    market_close = close.loc[window_index].pct_change(fill_method=None).mean(
        axis=1,
        skipna=True,
    )
    close_return = np.log(ticker_close).diff()
    open_values = panels["open"].reindex(window_index)[ticker]
    high_values = panels["high"].reindex(window_index)[ticker]
    low_values = panels["low"].reindex(window_index)[ticker]
    volume_values = panels["volume"].reindex(window_index)[ticker]
    intraday_return = np.log(
        ticker_close / open_values.where(open_values > 0)
    )
    high_low_range = np.log(
        high_values.where(high_values > 0)
        / low_values.where(low_values > 0)
    )
    volume_change = np.log1p(volume_values.clip(lower=0)).diff()
    relative_return = close_return - market_close

    channels = pd.DataFrame({
        "close_return": close_return,
        "intraday_return": intraday_return,
        "high_low_range": high_low_range,
        "volume_change": volume_change,
        "market_return": market_close,
        "relative_return": relative_return,
    }).iloc[1:]
    if len(channels) != lookback:
        return None
    normalized = np.column_stack([
        _standardize_time_channel(channels[column])
        for column in PATCH_CHANNELS
    ])
    usable = (len(normalized) // patch_size) * patch_size
    if usable < patch_size * 4:
        return None
    normalized = normalized[-usable:]
    return normalized.reshape(
        usable // patch_size,
        patch_size * len(PATCH_CHANNELS),
    ).astype(np.float32)


def _cross_sectional_kronos_context(kronos_features, as_of_date, tickers):
    index = pd.Index([str(value).strip().upper() for value in tickers])
    result = pd.DataFrame(0.0, index=index, columns=KRONOS_CONTEXT_COLUMNS)
    result["kronos_missing"] = 1.0
    if kronos_features is None:
        return result
    frame = pd.DataFrame(kronos_features).copy()
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"]).dt.tz_localize(None)
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    snapshot = frame.loc[frame["as_of_date"] == pd.Timestamp(as_of_date)]
    raw = snapshot.set_index("ticker")["kronos_score"].reindex(index)
    valid = raw.dropna()
    if valid.empty:
        return result
    scale = float(valid.std(ddof=0))
    normalized = (
        valid - float(valid.mean())
        if not np.isfinite(scale) or scale <= 1e-12
        else (valid - float(valid.mean())) / scale
    )
    result.loc[normalized.index, "kronos_score"] = normalized.clip(-3.0, 3.0)
    result.loc[normalized.index, "kronos_missing"] = 0.0
    return result


def build_context_features(
    price_history,
    *,
    as_of_date,
    tickers,
    point_in_time_features=None,
    kronos_features=None,
    include_kronos=True,
):
    """Combine price, optional PIT, and frozen Kronos context features."""
    tickers = [str(value).strip().upper() for value in tickers]
    features = pooled_price_features(price_history.loc[:, tickers]).reindex(tickers)
    if point_in_time_features is not None:
        pit = pooled_point_in_time_features(
            point_in_time_features,
            as_of_date,
            tickers,
        ).reindex(tickers)
        features = features.join(pit.loc[:, FACTOR_PIT_FEATURE_COLUMNS])
    if include_kronos:
        features = features.join(
            _cross_sectional_kronos_context(
                kronos_features,
                as_of_date,
                tickers,
            )
        )
    return features.astype(float)


def _forward_targets(
    prices,
    position,
    horizons,
    tickers,
    target_kind,
    point_in_time_features=None,
):
    targets = pd.DataFrame(index=tickers, dtype=float)
    diagnostics = {}
    for horizon in horizons:
        forward = (
            prices.iloc[position + horizon].reindex(tickers)
            / prices.iloc[position].reindex(tickers)
            - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        if target_kind == "relative":
            target = forward - float(forward.median(skipna=True))
        elif target_kind == "factor_residual":
            if point_in_time_features is None:
                raise ValueError(
                    "factor_residual target requires point_in_time_features"
                )
            snapshot = point_in_time_snapshot(
                point_in_time_features,
                prices.index[position],
                tickers=tickers,
            )
            target, detail = factor_residual_forward_returns(
                forward,
                prices.iloc[:position + 1].loc[:, tickers],
                snapshot,
            )
            diagnostics[str(horizon)] = detail
        else:
            raise ValueError("target_kind must be relative or factor_residual")
        targets[f"target_{horizon}"] = target.reindex(tickers)
    return targets, diagnostics


class PooledPatchTransformerRegressor:
    """Small TensorFlow regressor with explicit position embeddings."""

    def __init__(self, config, seed=None):
        self.config = config.normalized()
        self.seed = self.config.random_state if seed is None else int(seed)
        self.model = None
        self.context_scaler = StandardScaler()
        self.target_scaler = StandardScaler()
        self.history = {}

    def _build_model(self, patch_shape, context_dim, output_dim):
        try:
            import tensorflow as tf
            from tensorflow import keras
            from tensorflow.keras import layers
        except Exception as exc:
            raise RuntimeError(
                "TensorFlow is required for pooled Patch Transformer research"
            ) from exc

        config = self.config
        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(self.seed)
        patch_input = keras.Input(shape=patch_shape, name="patches")
        context_input = keras.Input(shape=(context_dim,), name="context")
        x = layers.Dense(config.d_model, name="patch_projection")(patch_input)
        class PositionEmbedding(layers.Layer):
            def __init__(self, sequence_length, width, **kwargs):
                super().__init__(**kwargs)
                self.embedding = layers.Embedding(sequence_length, width)

            def call(self, inputs):
                positions = tf.range(tf.shape(inputs)[1])
                encoded = self.embedding(positions)
                return inputs + tf.expand_dims(encoded, axis=0)

        x = PositionEmbedding(
            patch_shape[0],
            config.d_model,
            name="position_embedding",
        )(x)
        for block in range(config.num_blocks):
            attention_input = layers.LayerNormalization(
                epsilon=1e-6,
                name=f"attention_norm_{block}",
            )(x)
            attention = layers.MultiHeadAttention(
                num_heads=config.num_heads,
                key_dim=max(1, config.d_model // config.num_heads),
                dropout=config.dropout,
                name=f"attention_{block}",
            )(attention_input, attention_input)
            x = layers.Add(name=f"attention_residual_{block}")([x, attention])
            feed_input = layers.LayerNormalization(
                epsilon=1e-6,
                name=f"feed_norm_{block}",
            )(x)
            feed = layers.Dense(
                config.ff_dim,
                activation="gelu",
                name=f"feed_expand_{block}",
            )(feed_input)
            feed = layers.Dropout(config.dropout)(feed)
            feed = layers.Dense(
                config.d_model,
                name=f"feed_contract_{block}",
            )(feed)
            x = layers.Add(name=f"feed_residual_{block}")([x, feed])
        recent = layers.Lambda(
            lambda tensor: tensor[:, -1, :],
            name="recent_patch_pooling",
        )(x)
        context = layers.LayerNormalization(name="context_norm")(context_input)
        context = layers.Dense(
            config.dense_units,
            activation="gelu",
            name="context_projection",
        )(context)
        combined = layers.Concatenate(name="patch_context")([recent, context])
        combined = layers.Dropout(config.dropout)(combined)
        outputs = layers.Dense(output_dim, name="direct_horizon_targets")(combined)
        model = keras.Model(
            inputs={"patches": patch_input, "context": context_input},
            outputs=outputs,
            name="pooled_patch_transformer",
        )
        try:
            optimizer = keras.optimizers.AdamW(
                learning_rate=config.learning_rate,
                weight_decay=config.weight_decay,
            )
        except AttributeError:
            optimizer = keras.optimizers.Adam(
                learning_rate=config.learning_rate,
            )
        model.compile(
            optimizer=optimizer,
            loss=keras.losses.Huber(),
        )
        return model

    def fit(self, patches, context, targets, dates):
        import tensorflow as tf

        patches = np.asarray(patches, dtype=np.float32)
        context = np.asarray(context, dtype=float)
        targets = np.asarray(targets, dtype=float)
        dates = pd.to_datetime(pd.Series(dates)).to_numpy()
        unique_dates = np.sort(np.unique(dates))
        validation_count = min(
            self.config.validation_periods,
            max(1, len(unique_dates) - 1),
        )
        validation_dates = set(unique_dates[-validation_count:])
        validation_mask = np.asarray(
            [value in validation_dates for value in dates],
            dtype=bool,
        )
        if not bool((~validation_mask).any()) or not bool(validation_mask.any()):
            raise ValueError("Transformer fit requires chronological train/validation periods")

        self.context_scaler.fit(context[~validation_mask])
        self.target_scaler.fit(targets[~validation_mask])
        scaled_context = self.context_scaler.transform(context).astype(np.float32)
        scaled_targets = self.target_scaler.transform(targets).astype(np.float32)
        train_dates = pd.Series(dates[~validation_mask])
        validation_date_values = pd.Series(dates[validation_mask])
        train_counts = train_dates.map(train_dates.value_counts()).to_numpy(dtype=float)
        validation_counts = validation_date_values.map(
            validation_date_values.value_counts()
        ).to_numpy(dtype=float)
        train_weights = 1.0 / train_counts
        train_weights *= len(train_weights) / float(train_weights.sum())
        validation_weights = 1.0 / validation_counts
        validation_weights *= (
            len(validation_weights) / float(validation_weights.sum())
        )
        self.model = self._build_model(
            patches.shape[1:],
            context.shape[1],
            targets.shape[1],
        )
        callbacks = [
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=self.config.patience,
                restore_best_weights=True,
            )
        ]
        history = self.model.fit(
            {
                "patches": patches[~validation_mask],
                "context": scaled_context[~validation_mask],
            },
            scaled_targets[~validation_mask],
            validation_data=(
                {
                    "patches": patches[validation_mask],
                    "context": scaled_context[validation_mask],
                },
                scaled_targets[validation_mask],
                validation_weights,
            ),
            epochs=self.config.epochs,
            batch_size=self.config.batch_size,
            shuffle=False,
            verbose=0,
            callbacks=callbacks,
            sample_weight=train_weights,
        )
        self.history = {
            key: [float(item) for item in values]
            for key, values in history.history.items()
        }
        return self

    def predict(self, patches, context):
        if self.model is None:
            raise RuntimeError("Patch Transformer is not fitted")
        patches = np.asarray(patches, dtype=np.float32)
        scaled_context = self.context_scaler.transform(
            np.asarray(context, dtype=float)
        ).astype(np.float32)
        scaled = self.model.predict(
            {"patches": patches, "context": scaled_context},
            verbose=0,
        )
        return self.target_scaler.inverse_transform(scaled)

    def diagnostics(self):
        return {
            "config": asdict(self.config),
            "seed": int(self.seed),
            "epochs_run": int(len(self.history.get("loss", []))),
            "best_validation_loss": (
                None
                if not self.history.get("val_loss")
                else float(min(self.history["val_loss"]))
            ),
            "has_position_embedding": bool(
                self.model is not None
                and any(layer.name == "position_embedding" for layer in self.model.layers)
            ),
            "pooling": "most_recent_ordered_patch",
            "forecast_strategy": "direct_multi_horizon",
            "sample_weight_policy": "equal_total_weight_per_signal_date",
        }

    def cleanup(self):
        if self.model is None:
            return
        try:
            import tensorflow as tf

            del self.model
            tf.keras.backend.clear_session()
        finally:
            self.model = None


def _default_regressor_factory(config, seed):
    return PooledPatchTransformerRegressor(config, seed=seed)


def _resolve_positions(prices, config, origin_dates=None, rebalance_step=None):
    maximum_horizon = max(config.horizons)
    minimum_position = max(config.lookback, 252)
    if origin_dates is None:
        step = maximum_horizon if rebalance_step is None else max(1, int(rebalance_step))
        return list(range(minimum_position, len(prices) - maximum_horizon, step))
    positions = []
    for value in sorted(set(pd.to_datetime(origin_dates))):
        position = int(prices.index.searchsorted(pd.Timestamp(value), side="right") - 1)
        if (
            position >= minimum_position
            and position + maximum_horizon < len(prices)
            and prices.index[position] == pd.Timestamp(value)
        ):
            positions.append(position)
    return positions


def walk_forward_pooled_patch_transformer(
    price_data,
    *,
    ohlcv_data=None,
    config=None,
    target_kind="relative",
    point_in_time_features=None,
    kronos_features=None,
    include_kronos=True,
    origin_dates=None,
    origin_universes=None,
    rebalance_step=None,
    evaluation_start=None,
    evaluation_end=None,
    minimum_training_periods=8,
    maximum_training_periods=12,
    minimum_observations=60,
    nominal_uncertainty_coverage=0.80,
    regressor_factory=None,
):
    """Walk forward using only targets completed before each signal date."""
    config = (config or PatchTransformerConfig()).normalized()
    prices = _clean_price_frame(price_data)
    panels = (
        ohlcv_panels(ohlcv_data)
        if ohlcv_data is not None
        else {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": pd.DataFrame(
                np.nan,
                index=prices.index,
                columns=prices.columns,
            ),
        }
    )
    panels = {
        key: value.reindex(index=prices.index, columns=prices.columns)
        for key, value in panels.items()
    }
    positions = _resolve_positions(
        prices,
        config,
        origin_dates=origin_dates,
        rebalance_step=rebalance_step,
    )
    if len(positions) < int(minimum_training_periods) + 1:
        raise ValueError("Insufficient research origins for pooled Patch Transformer")
    normalized_origin_universes = {
        pd.Timestamp(key): [str(value).strip().upper() for value in values]
        for key, values in dict(origin_universes or {}).items()
    }
    evaluation_start = (
        None if evaluation_start is None else pd.Timestamp(evaluation_start)
    )
    evaluation_end = (
        None if evaluation_end is None else pd.Timestamp(evaluation_end)
    )
    if (
        evaluation_start is not None
        and evaluation_end is not None
        and evaluation_start > evaluation_end
    ):
        raise ValueError("evaluation_start must be on or before evaluation_end")
    snapshots = {}
    for position in positions:
        as_of_date = prices.index[position]
        requested_tickers = normalized_origin_universes.get(
            as_of_date,
            list(prices.columns),
        )
        tickers = [
            ticker for ticker in requested_tickers if ticker in prices.columns
        ]
        context = build_context_features(
            prices.iloc[:position + 1],
            as_of_date=as_of_date,
            tickers=tickers,
            point_in_time_features=point_in_time_features,
            kronos_features=kronos_features,
            include_kronos=include_kronos,
        )
        targets, target_diagnostics = _forward_targets(
            prices,
            position,
            config.horizons,
            tickers,
            target_kind,
            point_in_time_features=point_in_time_features,
        )
        rows = []
        for ticker in tickers:
            patches = make_patch_tokens(
                panels,
                ticker,
                end_position=position,
                lookback=config.lookback,
                patch_size=config.patch_size,
            )
            if patches is None:
                continue
            context_values = context.loc[ticker].to_numpy(dtype=float)
            target_values = targets.loc[ticker].to_numpy(dtype=float)
            if not (
                np.isfinite(context_values).all()
                and np.isfinite(target_values).all()
            ):
                continue
            rows.append({
                "as_of_date": as_of_date,
                "forward_end_date": prices.index[position + max(config.horizons)],
                "ticker": ticker,
                "patches": patches,
                "context": context_values,
                "targets": target_values,
            })
        snapshots[position] = {
            "as_of_date": as_of_date,
            "requested_tickers": requested_tickers,
            "tickers": tickers,
            "context_columns": list(context.columns),
            "rows": rows,
            "target_diagnostics": target_diagnostics,
        }

    factory = regressor_factory or _default_regressor_factory
    records = []
    fit_seconds = 0.0
    primary_horizon = max(config.horizons)
    primary_index = list(config.horizons).index(primary_horizon)
    for evaluation_position in positions:
        evaluation_date = prices.index[evaluation_position]
        if (
            evaluation_start is not None
            and evaluation_date < evaluation_start
        ) or (
            evaluation_end is not None
            and evaluation_date > evaluation_end
        ):
            continue
        eligible_positions = [
            position
            for position in positions
            if position + max(config.horizons) <= evaluation_position
        ]
        if len(eligible_positions) < int(minimum_training_periods):
            continue
        training_positions = eligible_positions[-max(1, int(maximum_training_periods)):]
        training_rows = [
            row
            for position in training_positions
            for row in snapshots[position]["rows"]
        ]
        evaluation_rows = snapshots[evaluation_position]["rows"]
        if (
            len(training_rows) < int(minimum_observations)
            or len(evaluation_rows) < 2
        ):
            continue
        model = factory(config=config, seed=config.random_state)
        fit_started = time.perf_counter()
        model.fit(
            np.stack([row["patches"] for row in training_rows]),
            np.stack([row["context"] for row in training_rows]),
            np.stack([row["targets"] for row in training_rows]),
            [row["as_of_date"] for row in training_rows],
        )
        fit_seconds += time.perf_counter() - fit_started
        predicted = model.predict(
            np.stack([row["patches"] for row in evaluation_rows]),
            np.stack([row["context"] for row in evaluation_rows]),
        )
        model_diagnostics = (
            model.diagnostics() if hasattr(model, "diagnostics") else {}
        )
        if hasattr(model, "cleanup"):
            model.cleanup()
        tickers = [row["ticker"] for row in evaluation_rows]
        realized = np.stack([row["targets"] for row in evaluation_rows])
        completed_residuals = [
            residual
            for record in records
            if pd.Timestamp(record["forward_end_date"]) <= evaluation_date
            for residual in record["residuals"]
        ]
        uncertainty = (
            None
            if len(completed_residuals) < int(minimum_observations)
            else float(
                pd.Series(completed_residuals).abs().quantile(
                    float(nominal_uncertainty_coverage)
                )
            )
        )
        scores = {
            ticker: float(predicted[index, primary_index])
            for index, ticker in enumerate(tickers)
        }
        realized_returns = {
            ticker: float(realized[index, primary_index])
            for index, ticker in enumerate(tickers)
        }
        residuals = [
            realized_returns[ticker] - scores[ticker] for ticker in tickers
        ]
        records.append({
            "period_id": evaluation_date.strftime("%Y-%m-%d"),
            "as_of_date": evaluation_date.strftime("%Y-%m-%d"),
            "forward_end_date": prices.index[
                evaluation_position + primary_horizon
            ].strftime("%Y-%m-%d"),
            "train_start_date": prices.index[training_positions[0]].strftime(
                "%Y-%m-%d"
            ),
            "train_end_date": prices.index[
                training_positions[-1] + primary_horizon
            ].strftime("%Y-%m-%d"),
            "scores": scores,
            "realized_returns": realized_returns,
            "multi_horizon_predictions": {
                ticker: {
                    str(horizon): float(predicted[index, horizon_index])
                    for horizon_index, horizon in enumerate(config.horizons)
                }
                for index, ticker in enumerate(tickers)
            },
            "reported_uncertainty": uncertainty,
            "residuals": [float(value) for value in residuals],
            "requested_universe_size": int(
                len(snapshots[evaluation_position]["requested_tickers"])
            ),
            "missing_active_tickers": sorted(
                set(snapshots[evaluation_position]["requested_tickers"])
                - set(tickers)
            ),
            "prediction_count": int(len(tickers)),
            "coverage_rate": float(
                0.0
                if not snapshots[evaluation_position]["requested_tickers"]
                else len(tickers)
                / len(snapshots[evaluation_position]["requested_tickers"])
            ),
            "model": model_diagnostics,
            "target_diagnostics": snapshots[evaluation_position][
                "target_diagnostics"
            ],
        })

    periods = [
        {
            "period_id": record["period_id"],
            "scores": record["scores"],
            "realized_returns": record["realized_returns"],
        }
        for record in records
    ]
    predictions = [
        {
            "ticker": ticker,
            "expected_return": score,
            "uncertainty": record["reported_uncertainty"],
        }
        for record in records
        for ticker, score in record["scores"].items()
    ]
    rank = cross_sectional_rank_diagnostics(periods)
    bootstrap = rank_signal_block_bootstrap(periods)
    distribution = prediction_distribution_diagnostics(predictions)
    distribution["active_universe_coverage_rate"] = (
        0.0 if not records else float(np.mean([row["coverage_rate"] for row in records]))
    )
    gate = signal_only_gate(rank, distribution, bootstrap)
    latest_gate = None
    if records:
        latest = records[-1]
        latest_predictions = [
            {
                "ticker": ticker,
                "expected_return": score,
                "uncertainty": latest["reported_uncertainty"],
            }
            for ticker, score in latest["scores"].items()
        ]
        latest_gate = sequential_forecast_confidence_gate(
            records[:-1],
            latest_predictions,
            latest["as_of_date"],
        )
    return {
        "model": "pooled_patch_transformer",
        "research_only": True,
        "target_kind": target_kind,
        "primary_horizon": int(primary_horizon),
        "config": asdict(config),
        "include_kronos": bool(include_kronos),
        "evaluation_start": (
            None
            if evaluation_start is None
            else evaluation_start.strftime("%Y-%m-%d")
        ),
        "evaluation_end": (
            None
            if evaluation_end is None
            else evaluation_end.strftime("%Y-%m-%d")
        ),
        "context_columns": (
            [] if not snapshots else next(iter(snapshots.values()))["context_columns"]
        ),
        "origin_count": int(len(positions)),
        "fit_count": int(len(records)),
        "fit_seconds": float(fit_seconds),
        "records": records,
        "rank_diagnostics": rank,
        "distribution_diagnostics": distribution,
        "rank_bootstrap": bootstrap,
        "signal_gate": gate,
        "latest_sequential_gate": latest_gate,
    }


def compare_patch_transformer_runs(candidate, baseline):
    """Paired signal comparison for identical walk-forward origins."""
    def periods(result):
        return [
            {
                "period_id": row.get("period_id") or row["as_of_date"],
                "scores": row["scores"],
                "realized_returns": row["realized_returns"],
            }
            for row in result.get("records", [])
        ]

    paired = paired_rank_signal_block_bootstrap(
        periods(candidate),
        periods(baseline),
    )
    probability = paired.get("probability") or {}
    paired["gate"] = {
        "status": (
            "passed"
            if (
                paired.get("status") == "ok"
                and probability.get("higher_mean_rank_ic", 0.0) >= 0.95
                and probability.get("higher_mean_top_bottom_spread", 0.0) >= 0.95
            )
            else "rejected"
        ),
        "minimum_probability": 0.95,
    }
    return paired
