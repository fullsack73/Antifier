#!/usr/bin/env python3
"""Reproduce DFL covariance learning for unconstrained and capped GMV."""

import argparse
import hashlib
import json
import os
import random
import sys
import time
import tracemalloc
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")

import numpy as np
import pandas as pd
import tensorflow as tf
from pypfopt import risk_models
from sklearn.covariance import LedoitWolf, OAS


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from build_fama_french_industry_panel import (  # noqa: E402
    parse_value_weighted_daily_returns,
)
from portfolio_backtest import (  # noqa: E402
    _cash_value_path,
    _portfolio_metrics,
)
from portfolio_optimization import (  # noqa: E402
    _fund_transaction_cost,
    apply_trade_controls,
)
from portfolio_risk_models import (  # noqa: E402
    _minimum_variance_from_covariance,
    covariance_diagnostics,
)
from portfolio_signals import cap_and_normalize_weights  # noqa: E402
from portfolio_statistics import (  # noqa: E402
    holm_bonferroni,
    paired_block_bootstrap,
)
from research_split import validate_comparison_execution_settings  # noqa: E402


TRADING_DAYS_PER_YEAR = 252


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolve_manifest_file(declared_path):
    """Resolve a locked data path across repository checkouts."""
    declared = Path(declared_path).expanduser()
    if declared.exists():
        return declared.resolve()
    if not declared.is_absolute():
        return (ROOT / declared).resolve()
    parts = declared.parts
    for index in range(len(parts) - 1):
        if parts[index:index + 2] == ("data", "research"):
            candidate = ROOT.joinpath(*parts[index:])
            if candidate.exists():
                return candidate.resolve()
            break
    return declared.resolve()


def _canonical_digest(payload, excluded=()):
    content = {
        key: value
        for key, value in dict(payload).items()
        if key not in set(excluded)
    }
    return hashlib.sha256(
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_value(value):
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        return value if np.isfinite(value) else None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d")
    return value


def load_locked_experiment(manifest_path, config_path):
    manifest_path = Path(manifest_path).expanduser().resolve()
    config_path = Path(config_path).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    declared = manifest.get("manifest_sha256")
    actual = _canonical_digest(manifest, excluded=("manifest_sha256",))
    if declared != actual:
        raise ValueError("Locked manifest SHA-256 does not match its content")
    if not manifest.get("locked"):
        raise ValueError("Experiment manifest must be locked")
    if manifest["configuration"]["file_sha256"] != _sha256(config_path):
        raise ValueError("Configuration SHA-256 does not match the manifest")
    if manifest["experiment_id"] != config["experiment_id"]:
        raise ValueError("Manifest and configuration experiment IDs differ")
    source_path = _resolve_manifest_file(
        manifest["data"]["source_file"]
    )
    if manifest["data"]["source_file_sha256"] != _sha256(source_path):
        raise ValueError("Source archive SHA-256 does not match the manifest")
    returns = parse_value_weighted_daily_returns(source_path) * 100.0
    ordered = list(manifest["universe"]["ordered_tickers"])
    if list(returns.columns) != ordered:
        raise ValueError("Source ordered universe does not match the manifest")
    ordered_digest = hashlib.sha256(
        json.dumps(ordered, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if ordered_digest != manifest["universe"]["ordered_tickers_sha256"]:
        raise ValueError("Ordered universe SHA-256 does not match")
    return manifest, config, returns


def build_partition_samples(returns, config, partition_name):
    returns = pd.DataFrame(returns, dtype=float).copy()
    returns.index = pd.to_datetime(returns.index)
    returns = returns.sort_index()
    if returns.empty or returns.isna().any().any():
        raise ValueError("Returns must be non-empty, finite, and complete")
    if not np.isfinite(returns.to_numpy()).all():
        raise ValueError("Returns contain non-finite values")
    input_horizon = int(config["input_horizon"])
    output_horizon = int(config["output_horizon"])
    policy = config["partition_policy"][partition_name]
    start = pd.Timestamp(policy["start"])
    end = pd.Timestamp(policy["end"])
    step = int(policy["step"])
    eligible = []
    for position, signal_date in enumerate(returns.index):
        if signal_date < start or signal_date > end:
            continue
        first_feature = position - input_horizon + 1
        last_label = position + output_horizon
        if first_feature < 0 or last_label >= len(returns):
            continue
        if (
            policy["feature_window_must_be_inside_partition"]
            and returns.index[first_feature] < start
        ):
            continue
        if (
            policy["future_window_must_be_inside_partition"]
            and returns.index[last_label] > end
        ):
            continue
        eligible.append(position)
    selected = eligible[::step]
    if not selected:
        raise ValueError(f"Partition {partition_name} has no valid samples")

    features = []
    future_covariances = []
    future_returns = []
    records = []
    for position in selected:
        feature = returns.iloc[
            position - input_horizon + 1 : position + 1
        ].to_numpy(dtype=np.float32)
        future = returns.iloc[
            position + 1 : position + output_horizon + 1
        ]
        covariance = np.cov(
            future.to_numpy(dtype=np.float64),
            rowvar=False,
            ddof=int(config["sample_covariance_ddof"]),
        )
        if feature.shape != (input_horizon, returns.shape[1]):
            raise ValueError("Feature window has an invalid shape")
        if future.shape != (output_horizon, returns.shape[1]):
            raise ValueError("Future window has an invalid shape")
        if not np.isfinite(covariance).all():
            raise ValueError("Future covariance is not finite")
        features.append(feature)
        future_covariances.append(covariance.astype(np.float32))
        future_returns.append(
            (future.to_numpy(dtype=np.float64) / 100.0)
        )
        records.append({
            "signal_date": returns.index[position],
            "feature_start": returns.index[position - input_horizon + 1],
            "feature_end": returns.index[position],
            "label_start": future.index[0],
            "label_end": future.index[-1],
            "future_dates": future.index,
        })
    return {
        "x": np.asarray(features, dtype=np.float32),
        "covariance": np.asarray(future_covariances, dtype=np.float32),
        "future_returns": np.asarray(future_returns, dtype=np.float64),
        "records": records,
        "tickers": list(returns.columns),
    }


def validate_sample_contract(samples, manifest, partition_name):
    expected = manifest["sample_contract"][partition_name]
    if len(samples["x"]) != int(expected["sample_count"]):
        raise ValueError(
            f"{partition_name} sample count drifted from the manifest"
        )
    records = samples["records"]
    if records[0]["signal_date"].strftime("%Y-%m-%d") != expected[
        "first_signal_date"
    ]:
        raise ValueError(f"{partition_name} first signal date drifted")
    if records[-1]["signal_date"].strftime("%Y-%m-%d") != expected[
        "last_signal_date"
    ]:
        raise ValueError(f"{partition_name} last signal date drifted")
    if records[-1]["label_end"].strftime("%Y-%m-%d") != expected[
        "last_label_date"
    ]:
        raise ValueError(f"{partition_name} last label date drifted")
    violations = [
        record
        for record in records
        if not (
            record["feature_end"] < record["label_start"]
            and record["label_start"] <= record["label_end"]
        )
    ]
    if violations:
        raise ValueError(f"{partition_name} contains lookahead")
    return 0


def set_deterministic_seed(seed):
    random.seed(int(seed))
    np.random.seed(int(seed))
    tf.keras.utils.set_random_seed(int(seed))
    try:
        tf.config.experimental.enable_op_determinism()
    except (AttributeError, RuntimeError):
        pass
    try:
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.threading.set_intra_op_parallelism_threads(1)
    except RuntimeError:
        pass


def lower_triangular_to_covariance(values, asset_count, jitter=1e-5):
    values = tf.convert_to_tensor(values)
    asset_count = int(asset_count)
    expected = asset_count * (asset_count + 1) // 2
    if values.shape.rank != 2 or values.shape[-1] != expected:
        raise ValueError(
            f"Expected lower-triangular vectors with width {expected}"
        )
    rows, columns = np.tril_indices(asset_count)
    flat_indices = rows * asset_count + columns
    embedding = tf.one_hot(
        flat_indices,
        depth=asset_count * asset_count,
        dtype=values.dtype,
    )
    lower = tf.reshape(
        tf.matmul(values, embedding),
        (-1, asset_count, asset_count),
    )
    covariance = tf.matmul(lower, lower, transpose_b=True)
    identity = tf.eye(asset_count, batch_shape=[tf.shape(values)[0]])
    return covariance + tf.cast(jitter, values.dtype) * identity


def unconstrained_gmv_weights(covariances):
    covariances = tf.convert_to_tensor(covariances)
    if covariances.shape.rank != 3:
        raise ValueError("Covariance input must be batched square matrices")
    asset_count = tf.shape(covariances)[-1]
    ones = tf.ones(
        (tf.shape(covariances)[0], asset_count, 1),
        dtype=covariances.dtype,
    )
    solved = tf.linalg.solve(covariances, ones)
    denominator = tf.reduce_sum(solved, axis=1, keepdims=True)
    return tf.squeeze(solved / denominator, axis=-1)


def pfl_loss(asset_count, jitter):
    def loss(y_true, y_pred):
        predicted = lower_triangular_to_covariance(
            y_pred,
            asset_count,
            jitter,
        )
        return tf.reduce_mean(tf.square(predicted - y_true))

    return loss


def dfl_loss(asset_count, jitter):
    def loss(y_true, y_pred):
        predicted = lower_triangular_to_covariance(
            y_pred,
            asset_count,
            jitter,
        )
        weights = unconstrained_gmv_weights(predicted)
        variance = tf.einsum("bi,bij,bj->b", weights, y_true, weights)
        return tf.reduce_mean(variance)

    return loss


def build_model(asset_count, config, seed):
    set_deterministic_seed(seed)
    model_config = config["model"]
    inputs = tf.keras.Input(
        shape=(int(config["input_horizon"]), int(asset_count)),
        name="returns",
    )
    trend = tf.keras.layers.AveragePooling1D(
        pool_size=int(model_config["moving_average_kernel"]),
        strides=1,
        padding="same",
        name="moving_average_trend",
    )(inputs)
    seasonal = tf.keras.layers.Subtract(name="seasonal")([inputs, trend])
    combined = tf.keras.layers.Concatenate(axis=-1)([trend, seasonal])
    flattened = tf.keras.layers.Flatten()(combined)
    hidden = tf.keras.layers.Dense(
        int(model_config["hidden_dimension"]),
        activation=model_config["hidden_activation"],
        name="hidden",
    )(flattened)
    output_width = asset_count * (asset_count + 1) // 2
    outputs = tf.keras.layers.Dense(
        output_width,
        name="lower_triangular_L",
    )(hidden)
    return tf.keras.Model(inputs=inputs, outputs=outputs)


def fit_arm(arm, train, validation, test, config, seed, verbose=0):
    if arm not in {"pfl", "dfl"}:
        raise ValueError(f"Unsupported training arm: {arm}")
    asset_count = train["x"].shape[-1]
    tf.keras.backend.clear_session()
    model = build_model(asset_count, config, seed)
    jitter = float(config["model"]["covariance_jitter"])
    loss = (
        pfl_loss(asset_count, jitter)
        if arm == "pfl"
        else dfl_loss(asset_count, jitter)
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(
            learning_rate=float(config["model"]["learning_rate"])
        ),
        loss=loss,
    )
    early_stopping = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss",
        patience=int(config["model"]["early_stopping_patience"]),
        restore_best_weights=bool(config["model"]["restore_best_weights"]),
    )
    tracemalloc.start()
    started = time.perf_counter()
    history = model.fit(
        train["x"],
        train["covariance"],
        validation_data=(validation["x"], validation["covariance"]),
        epochs=int(config["model"]["maximum_epochs"]),
        batch_size=int(config["model"]["batch_size"]),
        shuffle=bool(config["determinism"]["shuffle"]),
        callbacks=[early_stopping],
        verbose=int(verbose),
    )
    vectors = model.predict(
        test["x"],
        batch_size=int(config["model"]["batch_size"]),
        verbose=0,
    )
    covariances = lower_triangular_to_covariance(
        vectors,
        asset_count,
        jitter,
    ).numpy()
    runtime = time.perf_counter() - started
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if not np.isfinite(covariances).all():
        raise ValueError(f"{arm} generated non-finite covariance")
    minimum_eigenvalue = float(
        min(np.linalg.eigvalsh(matrix).min() for matrix in covariances)
    )
    if minimum_eigenvalue <= 0.0:
        raise ValueError(f"{arm} generated a non-positive-definite covariance")
    result = {
        "arm": arm,
        "seed": int(seed),
        "epochs_completed": int(len(history.history["loss"])),
        "best_validation_loss": float(min(history.history["val_loss"])),
        "final_training_loss": float(history.history["loss"][-1]),
        "runtime_seconds": float(runtime),
        "peak_python_memory_bytes": int(peak_memory),
        "minimum_prediction_eigenvalue": minimum_eigenvalue,
        "prediction_sha256": hashlib.sha256(
            np.asarray(covariances, dtype="<f4").tobytes()
        ).hexdigest(),
    }
    tf.keras.backend.clear_session()
    return covariances.astype(np.float64), result


def _numpy_gmv_weights(covariance, jitter=1e-5):
    covariance = np.asarray(covariance, dtype=np.float64)
    if covariance.ndim != 2 or covariance.shape[0] != covariance.shape[1]:
        raise ValueError("Covariance must be a square matrix")
    if not np.isfinite(covariance).all():
        raise ValueError("Covariance must be finite")
    covariance = (covariance + covariance.T) / 2.0
    covariance = covariance + float(jitter) * np.eye(len(covariance))
    ones = np.ones(len(covariance), dtype=np.float64)
    solved = np.linalg.solve(covariance, ones)
    denominator = float(ones @ solved)
    if not np.isfinite(denominator) or abs(denominator) <= 1e-14:
        raise ValueError("GMV normalization denominator is invalid")
    weights = solved / denominator
    if not np.isfinite(weights).all():
        raise ValueError("GMV weights are not finite")
    return weights


def _baseline_covariances(feature_window):
    feature_window = np.asarray(feature_window, dtype=np.float64)
    frame = pd.DataFrame(feature_window)
    return {
        "historical_sample_covariance_gmv": np.cov(
            feature_window,
            rowvar=False,
            ddof=1,
        ),
        "ledoit_wolf_constant_variance_gmv": LedoitWolf().fit(
            feature_window
        ).covariance_,
        "ledoit_wolf_constant_correlation_gmv": (
            risk_models.CovarianceShrinkage(
                frame,
                returns_data=True,
                frequency=1,
            ).ledoit_wolf(
                shrinkage_target="constant_correlation"
            ).to_numpy(dtype=float)
        ),
        "oas_gmv": OAS().fit(feature_window).covariance_,
    }


def evaluate_unconstrained_covariances(
    name,
    covariances,
    test,
    jitter=1e-5,
):
    covariances = np.asarray(covariances, dtype=np.float64)
    if len(covariances) != len(test["x"]):
        raise ValueError(f"{name} covariance count does not match test samples")
    period_volatilities = []
    period_variances = []
    frobenius_errors = []
    concentrations = []
    weights_by_period = []
    oracle_regrets = []
    for covariance, future_covariance, future_returns in zip(
        covariances,
        test["covariance"],
        test["future_returns"],
    ):
        weights = _numpy_gmv_weights(covariance, jitter=jitter)
        daily = future_returns @ weights
        period_variance = float(weights @ future_covariance @ weights)
        period_volatilities.append(
            float(np.std(daily, ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
        )
        period_variances.append(period_variance)
        frobenius_errors.append(
            float(np.linalg.norm(covariance - future_covariance, ord="fro"))
        )
        concentrations.append(float(weights @ weights))
        weights_by_period.append(weights)
        oracle = _numpy_gmv_weights(future_covariance, jitter=jitter)
        oracle_regrets.append(
            float(period_variance - oracle @ future_covariance @ oracle)
        )
    turnovers = [
        float(np.abs(current - previous).sum())
        for previous, current in zip(weights_by_period, weights_by_period[1:])
    ]
    return {
        "model": name,
        "mean_realized_annualized_volatility": float(
            np.mean(period_volatilities)
        ),
        "mean_period_variance_percent_squared": float(
            np.mean(period_variances)
        ),
        "mean_covariance_frobenius_error": float(
            np.mean(frobenius_errors)
        ),
        "mean_concentration": float(np.mean(concentrations)),
        "maximum_absolute_weight": float(
            max(np.abs(weights).max() for weights in weights_by_period)
        ),
        "gross_turnover": float(sum(turnovers)),
        "mean_gross_turnover": (
            0.0 if not turnovers else float(np.mean(turnovers))
        ),
        "mean_oracle_gmv_regret_percent_squared": float(
            np.mean(oracle_regrets)
        ),
        "period_volatilities": period_volatilities,
        "numerical_fallback_count": 0,
    }


def evaluate_unconstrained_baselines(test, jitter=1e-5):
    asset_count = test["x"].shape[-1]
    covariance_by_model = {
        "equal_weight": [None] * len(test["x"]),
        "historical_sample_covariance_gmv": [],
        "ledoit_wolf_constant_variance_gmv": [],
        "ledoit_wolf_constant_correlation_gmv": [],
        "oas_gmv": [],
    }
    for feature in test["x"]:
        for name, covariance in _baseline_covariances(feature).items():
            covariance_by_model[name].append(covariance)
    results = {}
    equal_covariance = np.repeat(
        np.eye(asset_count, dtype=float)[None, :, :],
        len(test["x"]),
        axis=0,
    )
    equal = evaluate_unconstrained_covariances(
        "equal_weight",
        equal_covariance,
        test,
        jitter=jitter,
    )
    equal["mean_covariance_frobenius_error"] = None
    equal["mean_oracle_gmv_regret_percent_squared"] = float(np.mean([
        np.full(asset_count, 1.0 / asset_count)
        @ future_covariance
        @ np.full(asset_count, 1.0 / asset_count)
        - _numpy_gmv_weights(future_covariance, jitter=jitter)
        @ future_covariance
        @ _numpy_gmv_weights(future_covariance, jitter=jitter)
        for future_covariance in test["covariance"]
    ]))
    results["equal_weight"] = equal
    for name in covariance_by_model:
        if name == "equal_weight":
            continue
        results[name] = evaluate_unconstrained_covariances(
            name,
            covariance_by_model[name],
            test,
            jitter=jitter,
        )
    return results


def checkpoint_1_gate(seed_results, baseline_results, seeds):
    completed = sorted(result["seed"] for result in seed_results)
    expected = sorted(int(seed) for seed in seeds)
    dfl_volatility = float(np.mean([
        result["dfl"]["mean_realized_annualized_volatility"]
        for result in seed_results
    ]))
    pfl_volatility = float(np.mean([
        result["pfl"]["mean_realized_annualized_volatility"]
        for result in seed_results
    ]))
    shrinkage_names = (
        "ledoit_wolf_constant_variance_gmv",
        "ledoit_wolf_constant_correlation_gmv",
        "oas_gmv",
    )
    strongest = min(
        shrinkage_names,
        key=lambda name: baseline_results[name][
            "mean_realized_annualized_volatility"
        ],
    )
    strongest_volatility = baseline_results[strongest][
        "mean_realized_annualized_volatility"
    ]
    fallback_count = int(sum(
        result[arm]["numerical_fallback_count"]
        for result in seed_results
        for arm in ("pfl", "dfl")
    ))
    reasons = []
    if completed != expected:
        reasons.append("Not all five predefined seeds completed.")
    if not dfl_volatility < pfl_volatility:
        reasons.append("DFL mean volatility did not improve identical-backbone PFL.")
    if not dfl_volatility < strongest_volatility:
        reasons.append(
            f"DFL mean volatility did not improve strongest shrinkage baseline {strongest}."
        )
    if fallback_count != 0:
        reasons.append("A model numerical fallback occurred.")
    return {
        "status": "PASS" if not reasons else "REJECT",
        "reasons": reasons,
        "dfl_mean_realized_annualized_volatility": dfl_volatility,
        "pfl_mean_realized_annualized_volatility": pfl_volatility,
        "strongest_shrinkage_baseline": strongest,
        "strongest_shrinkage_realized_annualized_volatility": float(
            strongest_volatility
        ),
        "completed_seeds": completed,
        "lookahead_violation_count": 0,
        "model_numerical_fallback_count": fallback_count,
    }


def _daily_returns_from_values(values, initial_value):
    series = pd.Series(values, dtype=float).sort_index()
    returns = series.pct_change()
    if not series.empty:
        returns.iloc[0] = float(series.iloc[0] / initial_value - 1.0)
    return returns.replace([np.inf, -np.inf], np.nan).dropna()


def _practical_target_weights(covariance, tickers, max_asset_weight):
    weights, success = _minimum_variance_from_covariance(
        pd.DataFrame(covariance, index=tickers, columns=tickers),
        tickers,
        max_asset_weight,
    )
    if not success:
        raise ValueError("Long-only capped minimum-variance solver failed")
    return weights


def run_practical_transfer(
    test,
    dfl_covariances,
    pfl_covariances,
    config,
    risk_free_daily_returns,
):
    settings = config["checkpoint_2"]
    tickers = list(test["tickers"])
    max_weight = float(settings["max_asset_weight"])
    model_names = (
        "ledoit_wolf_long_only_capped_gmv",
        "dfl_long_only_capped_gmv",
        "pfl_long_only_capped_gmv",
        "equal_weight",
        "inverse_volatility_risk_parity",
    )
    states = {
        name: {
            "current_values": pd.Series(0.0, index=tickers),
            "cash": float(settings["initial_capital"]),
            "values": {},
            "turnovers": [],
            "costs": [],
            "predicted_volatilities": [],
            "realized_volatilities": [],
            "concentrations": [],
            "maximum_weights": [],
        }
        for name in model_names
    }
    covariance_coverage = {name: 0 for name in model_names}
    records = []
    for period, (feature, future, record) in enumerate(zip(
        test["x"],
        test["future_returns"],
        test["records"],
    )):
        ledoit = LedoitWolf().fit(feature).covariance_
        inverse_volatility = pd.Series(
            1.0 / np.std(feature, axis=0, ddof=0),
            index=tickers,
        ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        targets = {
            "ledoit_wolf_long_only_capped_gmv": _practical_target_weights(
                ledoit,
                tickers,
                max_weight,
            ),
            "dfl_long_only_capped_gmv": _practical_target_weights(
                dfl_covariances[period],
                tickers,
                max_weight,
            ),
            "pfl_long_only_capped_gmv": _practical_target_weights(
                pfl_covariances[period],
                tickers,
                max_weight,
            ),
            "equal_weight": pd.Series(1.0 / len(tickers), index=tickers),
            "inverse_volatility_risk_parity": cap_and_normalize_weights(
                inverse_volatility,
                max_asset_weight=max_weight,
            ),
        }
        predicted = {
            "ledoit_wolf_long_only_capped_gmv": ledoit,
            "dfl_long_only_capped_gmv": dfl_covariances[period],
            "pfl_long_only_capped_gmv": pfl_covariances[period],
            "equal_weight": np.cov(feature, rowvar=False, ddof=1),
            "inverse_volatility_risk_parity": np.cov(
                feature,
                rowvar=False,
                ddof=1,
            ),
        }
        for name in model_names:
            covariance = np.asarray(predicted[name], dtype=float)
            if not np.isfinite(covariance).all():
                raise ValueError(f"{name} practical covariance is invalid")
            covariance_coverage[name] += 1
            state = states[name]
            portfolio_value = float(state["current_values"].sum() + state["cash"])
            target_values = targets[name] * portfolio_value
            initial = period == 0
            controlled, controls = apply_trade_controls(
                state["current_values"],
                target_values,
                portfolio_value=portfolio_value,
                rebalance_band=(0.0 if initial else float(settings["rebalance_band"])),
                max_turnover=(None if initial else float(settings["maximum_turnover"])),
            )
            controlled, cost, _, cash, cost_diagnostics = _fund_transaction_cost(
                state["current_values"],
                controlled,
                portfolio_value,
                float(settings["transaction_cost_bps"]),
            )
            controlled = controlled.reindex(tickers).fillna(0.0)
            cumulative = pd.DataFrame(
                np.cumprod(1.0 + future, axis=0),
                index=record["future_dates"],
                columns=tickers,
            )
            asset_path = cumulative.mul(controlled, axis=1)
            cash_dates = pd.DatetimeIndex(
                [record["signal_date"], *list(record["future_dates"])]
            )
            cash_path = _cash_value_path(
                cash,
                cash_dates,
                risk_free_rate=0.0,
                risk_free_daily_returns=risk_free_daily_returns,
            ).iloc[1:]
            daily_values = asset_path.sum(axis=1) + cash_path.to_numpy()
            for date, value in daily_values.items():
                state["values"][date.strftime("%Y-%m-%d")] = float(value)
            state["current_values"] = asset_path.iloc[-1]
            state["cash"] = float(cash_path.iloc[-1])
            controlled_weights = controlled / portfolio_value
            predicted_volatility = float(
                np.sqrt(
                    max(
                        0.0,
                        controlled_weights.to_numpy()
                        @ (covariance / 10000.0)
                        @ controlled_weights.to_numpy(),
                    )
                    * TRADING_DAYS_PER_YEAR
                )
            )
            realized_volatility = float(
                np.std(future @ controlled_weights.to_numpy(), ddof=0)
                * np.sqrt(TRADING_DAYS_PER_YEAR)
            )
            state["turnovers"].append(float(controls["controlled_turnover"]))
            state["costs"].append(float(cost))
            state["predicted_volatilities"].append(predicted_volatility)
            state["realized_volatilities"].append(realized_volatility)
            state["concentrations"].append(
                float(np.square(controlled_weights).sum())
            )
            state["maximum_weights"].append(float(controlled_weights.max()))
            records.append({
                "model": name,
                "signal_date": record["signal_date"],
                "period_end": record["label_end"],
                "controlled_turnover": float(controls["controlled_turnover"]),
                "turnover_cap_hit": bool(controls["turnover_cap_hit"]),
                "transaction_cost": float(cost),
                "predicted_annualized_volatility": predicted_volatility,
                "realized_annualized_volatility": realized_volatility,
                "maximum_weight": float(controlled_weights.max()),
                "cost_diagnostics": cost_diagnostics,
            })
    summary = {}
    daily_returns = {}
    for name, state in states.items():
        metrics = _portfolio_metrics(
            state["values"],
            risk_free_rate=0.0,
            risk_free_daily_returns=risk_free_daily_returns,
            initial_value=float(settings["initial_capital"]),
        )
        returns = _daily_returns_from_values(
            state["values"],
            float(settings["initial_capital"]),
        )
        daily_returns[name] = returns
        predicted_values = np.asarray(state["predicted_volatilities"])
        realized_values = np.asarray(state["realized_volatilities"])
        metrics.update({
            "net_cumulative_return": float(
                metrics["final_value"] / float(settings["initial_capital"]) - 1.0
            ),
            "average_controlled_turnover": float(np.mean(state["turnovers"])),
            "maximum_controlled_turnover": float(np.max(state["turnovers"])),
            "transaction_costs": float(sum(state["costs"])),
            "transaction_cost_drag_fraction_of_initial_capital": float(
                sum(state["costs"]) / float(settings["initial_capital"])
            ),
            "risk_forecast_bias": float(np.mean(realized_values - predicted_values)),
            "risk_forecast_mae": float(np.mean(np.abs(realized_values - predicted_values))),
            "average_realized_to_predicted_volatility_ratio": float(
                np.mean(realized_values / predicted_values)
            ),
            "average_concentration": float(np.mean(state["concentrations"])),
            "maximum_weight": float(np.max(state["maximum_weights"])),
            "valid_covariance_coverage": float(
                covariance_coverage[name] / len(test["x"])
            ),
        })
        summary[name] = metrics

    common_settings = {
        "eligible_universe_sha256": hashlib.sha256(
            json.dumps(tickers, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "rebalance_dates": [
            record["signal_date"].strftime("%Y-%m-%d")
            for record in test["records"]
        ],
        "horizon": int(config["output_horizon"]),
        "rebalance_step": int(settings["rebalance_frequency"]),
        "max_asset_weight": max_weight,
        "rebalance_band": float(settings["rebalance_band"]),
        "max_turnover": float(settings["maximum_turnover"]),
        "transaction_cost_bps": float(settings["transaction_cost_bps"]),
        "risk_free_sha256": config.get("risk_free_sha256", "manifest"),
    }
    validate_comparison_execution_settings(common_settings, common_settings)
    bootstrap_settings = settings["bootstrap"]
    bootstrap = paired_block_bootstrap(
        daily_returns["dfl_long_only_capped_gmv"],
        daily_returns["ledoit_wolf_long_only_capped_gmv"],
        risk_free_rate=0.0,
        block_size=int(bootstrap_settings["method"].split("_")[1]),
        samples=int(bootstrap_settings["samples"]),
        seed=int(bootstrap_settings["seed"]),
        risk_free_daily_returns=risk_free_daily_returns,
    )
    probabilities = bootstrap.get("probability", {})
    familywise = holm_bonferroni({
        "dfl_long_only_capped_gmv": max(
            1.0 - float(probabilities.get("lower_volatility", 0.0)),
            1.0 - float(probabilities.get("higher_sharpe", 0.0)),
        )
    })
    candidate = summary["dfl_long_only_capped_gmv"]
    baseline = summary["ledoit_wolf_long_only_capped_gmv"]
    turnover_limit = max(
        0.50,
        2.0 * baseline["average_controlled_turnover"],
    )
    reasons = []
    if candidate["annual_volatility"] >= baseline["annual_volatility"]:
        reasons.append("Net annualized volatility did not improve Ledoit-Wolf.")
    if probabilities.get("lower_volatility", 0.0) < 0.95:
        reasons.append("P(lower volatility) is below 95%.")
    if candidate["sharpe"] is None or baseline["sharpe"] is None or candidate["sharpe"] <= baseline["sharpe"]:
        reasons.append("Sharpe did not improve Ledoit-Wolf.")
    if probabilities.get("higher_sharpe", 0.0) < 0.95:
        reasons.append("P(higher Sharpe) is below 95%.")
    if candidate["max_drawdown"] < baseline["max_drawdown"]:
        reasons.append("Maximum drawdown is worse than Ledoit-Wolf.")
    if candidate["average_controlled_turnover"] > turnover_limit:
        reasons.append("Average controlled turnover exceeds its gate.")
    if candidate["valid_covariance_coverage"] < 1.0:
        reasons.append("Candidate covariance coverage is incomplete.")
    if not familywise["dfl_long_only_capped_gmv"]["significant"]:
        reasons.append("The practical gate is not valid after Holm correction.")
    return {
        "status": "PASS" if not reasons else "REJECT",
        "reasons": reasons,
        "settings": common_settings,
        "summary_by_model": summary,
        "paired_bootstrap": bootstrap,
        "holm_bonferroni": familywise,
        "turnover_limit": turnover_limit,
        "rebalance_records": records,
    }


def _summary_markdown(payload):
    gate = payload["checkpoint_1_gate"]
    lines = [
        "# DFL Covariance Research Result",
        "",
        f"- Experiment: `{payload['experiment_id']}`",
        f"- Decision: **{payload['decision']}**",
        f"- Checkpoint 1: `{gate['status']}`",
        f"- Promotion safe: `{payload['promotion_safe']}`",
        f"- Test samples: `{payload['data_audit']['sample_counts']['test']}`",
        "",
        "## Checkpoint 1",
        "",
        "| Model | Mean annualized realized volatility |",
        "|---|---:|",
    ]
    for name, result in payload["unconstrained_baselines"].items():
        lines.append(
            f"| {name} | {result['mean_realized_annualized_volatility']:.6f} |"
        )
    lines.extend([
        f"| PFL five-seed mean | {gate['pfl_mean_realized_annualized_volatility']:.6f} |",
        f"| DFL five-seed mean | {gate['dfl_mean_realized_annualized_volatility']:.6f} |",
        "",
        "## Gate reasons",
        "",
    ])
    if gate["reasons"]:
        lines.extend(f"- {reason}" for reason in gate["reasons"])
    else:
        lines.append("- All Checkpoint 1 requirements passed.")
    practical = payload.get("checkpoint_2")
    if practical is not None:
        lines.extend([
            "",
            "## Checkpoint 2",
            "",
            f"- Status: `{practical['status']}`",
        ])
        lines.extend(f"- {reason}" for reason in practical["reasons"])
    else:
        lines.extend([
            "",
            "## Checkpoint 2",
            "",
            "Skipped by the preregistered Checkpoint 1 stop rule.",
        ])
    lines.extend([
        "",
        "## Guardrail",
        "",
        "This is reproduction-only diagnostic evidence. Production Ledoit-Wolf GMV remains unchanged.",
    ])
    return "\n".join(lines) + "\n"


def run_experiment(manifest_path, config_path, output_path, verbose=0):
    manifest, config, returns = load_locked_experiment(
        manifest_path,
        config_path,
    )
    partition_starts = [
        pd.Timestamp(policy["start"])
        for policy in config["partition_policy"].values()
    ]
    partition_ends = [
        pd.Timestamp(policy["end"])
        for policy in config["partition_policy"].values()
    ]
    returns = returns.loc[min(partition_starts) : max(partition_ends)]
    samples = {
        name: build_partition_samples(returns, config, name)
        for name in ("train", "validation", "test")
    }
    lookahead_violations = sum(
        validate_sample_contract(samples[name], manifest, name)
        for name in samples
    )
    if lookahead_violations:
        raise ValueError("Lookahead violations detected")
    jitter = float(config["model"]["covariance_jitter"])
    baseline_results = evaluate_unconstrained_baselines(
        samples["test"],
        jitter=jitter,
    )
    seed_results = []
    dfl_predictions = []
    pfl_predictions = []
    training_runs = []
    for seed in config["seeds"]:
        per_seed = {"seed": int(seed)}
        for arm, prediction_store in (
            ("pfl", pfl_predictions),
            ("dfl", dfl_predictions),
        ):
            covariances, training = fit_arm(
                arm,
                samples["train"],
                samples["validation"],
                samples["test"],
                config,
                seed,
                verbose=verbose,
            )
            prediction_store.append(covariances)
            training_runs.append(training)
            per_seed[arm] = evaluate_unconstrained_covariances(
                arm,
                covariances,
                samples["test"],
                jitter=jitter,
            )
            per_seed[f"{arm}_training"] = training
        seed_results.append(per_seed)
    gate = checkpoint_1_gate(
        seed_results,
        baseline_results,
        config["seeds"],
    )
    dfl_predictions = np.asarray(dfl_predictions, dtype=np.float32)
    pfl_predictions = np.asarray(pfl_predictions, dtype=np.float32)
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prediction_path = output_path.with_name(
        output_path.stem.replace("result", "predictions") + ".npz"
    )
    np.savez_compressed(
        prediction_path,
        dfl_covariances=dfl_predictions,
        pfl_covariances=pfl_predictions,
        signal_dates=np.asarray([
            record["signal_date"].strftime("%Y-%m-%d")
            for record in samples["test"]["records"]
        ]),
    )
    checkpoint_2 = None
    if gate["status"] == "PASS":
        risk_free_path = Path(manifest["data"]["risk_free_file"])
        if _sha256(risk_free_path) != manifest["data"]["risk_free_file_sha256"]:
            raise ValueError("Risk-free SHA-256 does not match the manifest")
        risk_free_frame = pd.read_csv(
            risk_free_path,
            index_col=0,
            parse_dates=True,
        )
        checkpoint_2 = run_practical_transfer(
            samples["test"],
            dfl_predictions.mean(axis=0),
            pfl_predictions.mean(axis=0),
            config,
            risk_free_frame[manifest["data"]["risk_free_column_for_checkpoint_2"]],
        )
    decision = (
        "PASS"
        if gate["status"] == "PASS"
        and checkpoint_2 is not None
        and checkpoint_2["status"] == "PASS"
        else "REJECT"
    )
    payload = {
        "schema_version": 1,
        "experiment_id": manifest["experiment_id"],
        "decision": decision,
        "promotion_safe": False,
        "production_default_changed": False,
        "manifest": {
            "file": str(Path(manifest_path).resolve()),
            "file_sha256": _sha256(manifest_path),
            "self_digest": manifest["manifest_sha256"],
        },
        "configuration": {
            "file": str(Path(config_path).resolve()),
            "file_sha256": _sha256(config_path),
        },
        "data": {
            "file": manifest["data"]["source_file"],
            "file_sha256": manifest["data"]["source_file_sha256"],
            "ordered_universe_sha256": manifest["universe"]["ordered_tickers_sha256"],
        },
        "data_audit": {
            "promotion_safe": False,
            "deviations": manifest["paper_deviations_locked_before_training"],
            "prior_consumed_splits": manifest["prior_consumed_splits"],
            "sample_counts": {
                name: int(len(samples[name]["x"])) for name in samples
            },
            "lookahead_violation_count": int(lookahead_violations),
        },
        "unconstrained_baselines": baseline_results,
        "seed_results": seed_results,
        "training_runs": training_runs,
        "seed_summary": {
            arm: {
                "mean_realized_annualized_volatility": float(np.mean([
                    item[arm]["mean_realized_annualized_volatility"]
                    for item in seed_results
                ])),
                "std_realized_annualized_volatility": float(np.std([
                    item[arm]["mean_realized_annualized_volatility"]
                    for item in seed_results
                ], ddof=0)),
            }
            for arm in ("pfl", "dfl")
        },
        "checkpoint_1_gate": gate,
        "checkpoint_2": checkpoint_2,
        "prediction_artifact": {
            "file": str(prediction_path),
            "file_sha256": _sha256(prediction_path),
            "content_sha256": hashlib.sha256(
                dfl_predictions.astype("<f4").tobytes()
                + pfl_predictions.astype("<f4").tobytes()
            ).hexdigest(),
        },
        "runtime_variance_policy": (
            "runtime_seconds and peak_python_memory_bytes are measured diagnostics; "
            "deterministic reruns compare all other fields and prediction content hashes"
        ),
    }
    payload = _json_value(payload)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path = output_path.with_suffix(".md")
    markdown_path.write_text(_summary_markdown(payload), encoding="utf-8")
    return payload, output_path, markdown_path, prediction_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload, output, markdown, predictions = run_experiment(
            args.manifest,
            args.config,
            args.output,
            verbose=1 if args.verbose else 0,
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Decision: {payload['decision']}")
    print(f"Wrote {output}")
    print(f"Wrote {markdown}")
    print(f"Wrote {predictions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
