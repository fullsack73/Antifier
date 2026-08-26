import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


if not isinstance(sys.modules.get("tensorflow"), (types.ModuleType, type(None))):
    for module_name in list(sys.modules):
        if module_name == "tensorflow" or module_name.startswith("tensorflow."):
            del sys.modules[module_name]
import tensorflow as tf


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from research_dfl_covariance import (  # noqa: E402
    build_partition_samples,
    dfl_loss,
    fit_arm,
    load_locked_experiment,
    lower_triangular_to_covariance,
    unconstrained_gmv_weights,
)


def _config(asset_count=3):
    return {
        "input_horizon": 4,
        "output_horizon": 5,
        "sample_covariance_ddof": 1,
        "partition_policy": {
            "test": {
                "start": "2020-01-06",
                "end": "2020-05-29",
                "step": 1,
                "feature_window_must_be_inside_partition": False,
                "future_window_must_be_inside_partition": True,
            }
        },
        "model": {
            "moving_average_kernel": 3,
            "hidden_dimension": 8,
            "hidden_activation": "relu",
            "covariance_jitter": 1e-5,
            "learning_rate": 1e-4,
            "maximum_epochs": 2,
            "batch_size": 4,
            "early_stopping_patience": 1,
            "restore_best_weights": True,
        },
        "determinism": {"shuffle": True},
        "asset_count": asset_count,
    }


def _training_samples(seed, rows, asset_count=3):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(rows, 4, asset_count)).astype(np.float32)
    matrices = rng.normal(size=(rows, asset_count, asset_count))
    covariance = (
        matrices @ np.swapaxes(matrices, 1, 2)
        + 0.1 * np.eye(asset_count)[None, :, :]
    ).astype(np.float32)
    return {"x": x, "covariance": covariance}


def test_lower_triangular_output_is_symmetric_positive_definite():
    vectors = tf.constant(
        [[1.0, 0.2, 0.8, -0.1, 0.3, 0.6]],
        dtype=tf.float32,
    )

    covariance = lower_triangular_to_covariance(vectors, 3).numpy()[0]
    weights = unconstrained_gmv_weights(covariance[None, :, :]).numpy()[0]

    np.testing.assert_allclose(covariance, covariance.T, atol=1e-7)
    assert np.linalg.eigvalsh(covariance).min() > 0.0
    assert np.isfinite(weights).all()
    assert weights.sum() == pytest.approx(1.0)


def test_future_rows_cannot_change_an_earlier_feature_window():
    dates = pd.date_range("2020-01-01", periods=80, freq="B")
    rng = np.random.default_rng(42)
    returns = pd.DataFrame(
        rng.normal(size=(len(dates), 3)),
        index=dates,
        columns=["A", "B", "C"],
    )
    changed = returns.copy()
    changed.iloc[4:9] *= 100.0

    original_samples = build_partition_samples(returns, _config(), "test")
    changed_samples = build_partition_samples(changed, _config(), "test")

    np.testing.assert_array_equal(
        original_samples["x"][0],
        changed_samples["x"][0],
    )
    assert not np.allclose(
        original_samples["covariance"][0],
        changed_samples["covariance"][0],
    )
    first = original_samples["records"][0]
    assert first["feature_end"] < first["label_start"]


def test_dfl_gradient_is_finite_and_nonzero():
    vectors = tf.Variable(
        [[0.7, 0.1, 0.9, -0.2, 0.3, 0.8]],
        dtype=tf.float32,
    )
    future_covariance = tf.constant(
        [[[1.0, 0.2, 0.1], [0.2, 1.5, 0.3], [0.1, 0.3, 0.8]]],
        dtype=tf.float32,
    )

    with tf.GradientTape() as tape:
        loss = dfl_loss(3, 1e-5)(future_covariance, vectors)
    gradient = tape.gradient(loss, vectors).numpy()

    assert np.isfinite(gradient).all()
    assert np.linalg.norm(gradient) > 1e-8


def test_same_seed_training_produces_deterministic_predictions():
    config = _config()
    train = _training_samples(1, 16)
    validation = _training_samples(2, 8)
    test = _training_samples(3, 4)

    first, first_metadata = fit_arm(
        "dfl", train, validation, test, config, seed=17
    )
    second, second_metadata = fit_arm(
        "dfl", train, validation, test, config, seed=17
    )

    np.testing.assert_allclose(first, second, rtol=0.0, atol=1e-6)
    assert first_metadata["prediction_sha256"] == second_metadata[
        "prediction_sha256"
    ]


def test_invalid_or_insufficient_data_fails_explicitly():
    dates = pd.date_range("2020-01-01", periods=6, freq="B")
    returns = pd.DataFrame(
        np.ones((6, 3)),
        index=dates,
        columns=["A", "B", "C"],
    )
    with pytest.raises(ValueError, match="no valid samples"):
        build_partition_samples(returns, _config(), "test")

    invalid = pd.DataFrame(
        np.ones((80, 3)),
        index=pd.date_range("2020-01-01", periods=80, freq="B"),
        columns=["A", "B", "C"],
    )
    invalid.iloc[10, 0] = np.nan
    with pytest.raises(ValueError, match="complete"):
        build_partition_samples(invalid, _config(), "test")


def test_locked_manifest_and_source_are_self_consistent():
    manifest = ROOT / "data/research/derived/fama_french_49_industry_dfl_covariance_manifest_v1.json"
    config = ROOT / "data/research/derived/fama_french_49_industry_dfl_covariance_config_v1.json"

    loaded_manifest, loaded_config, returns = load_locked_experiment(
        manifest,
        config,
    )

    assert loaded_manifest["locked"] is True
    assert loaded_manifest["promotion_safe"] is False
    assert loaded_config["production_defaults_must_remain_unchanged"] is True
    assert returns.shape[1] == 49
