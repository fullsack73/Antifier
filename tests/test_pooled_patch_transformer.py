import json
import sqlite3
import types

import numpy as np
import pandas as pd
import pytest

from pooled_patch_transformer import (
    PatchTransformerConfig,
    PooledPatchTransformerRegressor,
    compare_patch_transformer_runs,
    load_kronos_checkpoint,
    make_patch_tokens,
    walk_forward_pooled_patch_transformer,
)
from tools.research_pooled_patch_transformer import (
    _cached_forecast_signal_candidates,
    _fixed_gamma_gmv_experiment,
)
from tools.validate_pooled_patch_transformer import _origin_inputs


def _prices(rows=420):
    index = pd.date_range("2020-01-01", periods=rows, freq="B")
    time = np.arange(rows, dtype=float)
    return pd.DataFrame(
        {
            ticker: 100.0
            * np.exp(
                0.0002 * time
                + scale * np.sin(time / (8.0 + offset))
            )
            for ticker, scale, offset in zip(
                "ABCDE",
                (0.01, 0.012, 0.014, 0.016, 0.018),
                range(5),
            )
        },
        index=index,
    )


def _panels(prices):
    return {
        "open": prices * 0.999,
        "high": prices * 1.002,
        "low": prices * 0.998,
        "close": prices,
        "volume": pd.DataFrame(
            1_000_000.0,
            index=prices.index,
            columns=prices.columns,
        ),
    }


def test_patch_tokens_preserve_order_and_ignore_future_values():
    prices = _prices()
    position = 300
    original = make_patch_tokens(
        _panels(prices),
        "A",
        end_position=position,
        lookback=60,
        patch_size=5,
    )
    future_mutated = prices.copy()
    future_mutated.iloc[position + 1:, 0] *= 10.0
    unchanged = make_patch_tokens(
        _panels(future_mutated),
        "A",
        end_position=position,
        lookback=60,
        patch_size=5,
    )
    history_reversed = prices.copy()
    values = history_reversed.iloc[position - 60:position + 1, 0].to_numpy()
    history_reversed.iloc[position - 60:position + 1, 0] = values[::-1]
    reversed_tokens = make_patch_tokens(
        _panels(history_reversed),
        "A",
        end_position=position,
        lookback=60,
        patch_size=5,
    )

    np.testing.assert_allclose(original, unchanged)
    assert original.shape == (12, 30)
    assert not np.allclose(original, reversed_tokens)


def test_kronos_checkpoint_loader_rejects_mixed_signatures(tmp_path):
    path = tmp_path / "kronos.jsonl"
    rows = []
    for index, ticker in enumerate(("A", "B")):
        rows.append({
            "signature": {"version": 1 + index},
            "origin": {
                "period_id": "p1",
                "case_id": "case",
                "train_end": "2022-01-03",
                "horizon": 63,
                "scores": {ticker: float(index)},
            },
        })
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="incompatible signatures"):
        load_kronos_checkpoint(path, expected_horizon=63)


class _FakeRegressor:
    def __init__(self, config, seed):
        self.output_count = len(config.horizons)

    def fit(self, patches, context, targets, dates):
        assert len(set(pd.to_datetime(dates))) >= 2
        return self

    def predict(self, patches, context):
        base = np.asarray(context)[:, [0]]
        return np.repeat(base, self.output_count, axis=1) * 0.01

    def diagnostics(self):
        return {
            "has_position_embedding": True,
            "forecast_strategy": "direct_multi_horizon",
        }

    def cleanup(self):
        return None


def _fake_factory(config, seed):
    return _FakeRegressor(config, seed)


def test_walk_forward_patch_transformer_uses_only_completed_training_targets():
    prices = _prices()
    origins = list(prices.index[260:381:10])
    result = walk_forward_pooled_patch_transformer(
        prices,
        config=PatchTransformerConfig(
            lookback=60,
            patch_size=5,
            horizons=(3, 5),
            epochs=1,
        ),
        include_kronos=False,
        origin_dates=origins,
        minimum_training_periods=3,
        maximum_training_periods=5,
        minimum_observations=10,
        regressor_factory=_fake_factory,
    )

    assert result["research_only"]
    assert result["fit_count"] > 0
    assert result["primary_horizon"] == 5
    for record in result["records"]:
        assert pd.Timestamp(record["train_end_date"]) <= pd.Timestamp(
            record["as_of_date"]
        )
        assert all(
            set(values) == {"3", "5"}
            for values in record["multi_horizon_predictions"].values()
        )


def test_walk_forward_patch_transformer_limits_evaluation_and_reports_missing_universe():
    prices = _prices()
    origins = list(prices.index[260:381:10])
    evaluation_start = origins[-3]
    requested = {
        date: list(prices.columns) + ["MISSING"] for date in origins
    }

    result = walk_forward_pooled_patch_transformer(
        prices,
        config=PatchTransformerConfig(
            lookback=60,
            patch_size=5,
            horizons=(3, 5),
            epochs=1,
        ),
        include_kronos=False,
        origin_dates=origins,
        origin_universes=requested,
        evaluation_start=evaluation_start,
        evaluation_end=origins[-1],
        minimum_training_periods=3,
        maximum_training_periods=5,
        minimum_observations=10,
        regressor_factory=_fake_factory,
    )

    assert result["fit_count"] == 3
    assert result["evaluation_start"] == evaluation_start.strftime("%Y-%m-%d")
    assert all(record["requested_universe_size"] == 6 for record in result["records"])
    assert all(record["coverage_rate"] == pytest.approx(5 / 6) for record in result["records"])
    assert all(record["missing_active_tickers"] == ["MISSING"] for record in result["records"])


def test_tensorflow_model_declares_position_embedding_and_direct_head():
    tensorflow = pytest.importorskip("tensorflow")
    if not isinstance(tensorflow, types.ModuleType):
        pytest.skip("Another test installed a process-wide TensorFlow mock")
    config = PatchTransformerConfig(
        lookback=40,
        patch_size=5,
        horizons=(3, 5),
        d_model=8,
        num_heads=2,
        ff_dim=16,
        num_blocks=1,
        dense_units=8,
        epochs=1,
    )
    regressor = PooledPatchTransformerRegressor(config)
    model = regressor._build_model((8, 30), 4, 2)

    names = {layer.name for layer in model.layers}
    assert "position_embedding" in names
    assert "recent_patch_pooling" in names
    assert model.output_shape == (None, 2)
    regressor.model = model
    regressor.cleanup()


def test_fixed_gamma_experiment_replays_gmv_and_tilt_with_execution_costs():
    index = pd.date_range("2020-01-01", periods=568, freq="B")
    time = np.arange(len(index), dtype=float)
    prices = pd.DataFrame(
        {
            ticker: 100.0
            * np.exp(
                (0.0001 + 0.00002 * position) * time
                + (0.01 + 0.002 * position)
                * np.sin(time / (8.0 + position))
            )
            for position, ticker in enumerate("ABCDEF")
        },
        index=index,
    )
    record = {
        "as_of_date": index[504].strftime("%Y-%m-%d"),
        "forward_end_date": index[-1].strftime("%Y-%m-%d"),
        "scores": {
            ticker: float(position)
            for position, ticker in enumerate(prices.columns)
        },
    }

    result = _fixed_gamma_gmv_experiment(
        prices,
        {"records": [record]},
        gamma=0.025,
        max_asset_weight=0.2,
        transaction_cost_bps=10.0,
        rebalance_band=0.02,
        max_turnover=0.35,
    )

    assert result["gamma"] == pytest.approx(0.025)
    assert result["mean_raw_active_share"] == pytest.approx(0.025)
    assert result["mean_executed_active_share"] > 0.0
    assert result["paired_daily_bootstrap_vs_gmv"]["observation_count"] == 63
    assert set(result["cases"][0]["models"]) == {"gmv", "gmv_dl_tilt"}


def test_cached_forecast_candidates_recover_arima_and_transformer_components(
    tmp_path,
):
    cache_path = tmp_path / "forecast.sqlite3"
    connection = sqlite3.connect(cache_path)
    connection.execute(
        "CREATE TABLE forecast_predictions "
        "(key_payload TEXT, prediction_payload TEXT)"
    )
    for position, ticker in enumerate("ABC"):
        arima = 0.1 + position * 0.01
        transformer = 0.3 - position * 0.02
        for method, prediction in (
            (
                "arima_transformer_rank",
                {
                    "expected_return": (arima + transformer) / 2.0,
                    "components": {
                        "ARIMA": arima,
                        "Transformer": transformer,
                    },
                },
            ),
            (
                "transformer_rank",
                {"expected_return": transformer},
            ),
        ):
            key = [
                "schema",
                "frozen-namespace",
                method,
                ticker,
                63,
                504,
                "2020-01-01",
                "2021-12-07",
                "digest",
            ]
            connection.execute(
                "INSERT INTO forecast_predictions VALUES (?, ?)",
                (json.dumps(key), json.dumps(prediction)),
            )
    connection.commit()
    connection.close()
    reference = {
        "records": [{
            "period_id": "p1",
            "as_of_date": "2021-12-07",
            "forward_end_date": "2022-03-04",
            "scores": {ticker: 0.0 for ticker in "ABC"},
            "realized_returns": {
                "A": 0.03,
                "B": 0.02,
                "C": 0.01,
            },
        }],
    }

    candidates, metadata = _cached_forecast_signal_candidates(
        cache_path,
        reference,
        namespace="frozen-namespace",
    )

    assert set(candidates) == {"arima", "transformer", "arima_transformer"}
    assert candidates["arima"]["records"][0]["scores"]["A"] == pytest.approx(
        0.1
    )
    assert candidates["transformer"]["records"][0]["scores"][
        "A"
    ] == pytest.approx(0.3)
    assert candidates["arima_transformer"]["records"][0]["scores"][
        "A"
    ] == pytest.approx(0.2)
    assert metadata["row_count"] == 6


def test_fresh_origin_inputs_keep_only_frozen_training_window():
    prices = _prices(rows=1800)
    universe = pd.DataFrame({
        "effective_date": [prices.index[0]] * len(prices.columns),
        "ticker": list(prices.columns),
        "in_universe": [True] * len(prices.columns),
    })
    split = {
        "evaluation_start": "2024-01-01",
        "evaluation_end": "2025-12-31",
    }

    positions, dates, universes = _origin_inputs(prices, universe, split)
    evaluation_count = sum(date >= pd.Timestamp("2024-01-01") for date in dates)

    assert len(positions) - evaluation_count <= 12
    assert len(positions) - evaluation_count >= 8
    assert all(universes[date] == list(prices.columns) for date in dates)


def test_patch_comparison_accepts_ridge_records_with_as_of_date():
    record = {
        "as_of_date": "2024-01-08",
        "scores": {"A": 0.1, "B": -0.1},
        "realized_returns": {"A": 0.2, "B": -0.2},
    }
    candidate = {"records": [{"period_id": "2024-01-08", **record}]}
    baseline = {"records": [record]}

    result = compare_patch_transformer_runs(candidate, baseline)

    assert result["gate"]["status"] == "rejected"
