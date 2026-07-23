import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from cross_sectional_forecast import (  # noqa: E402
    FACTOR_POOLED_FEATURE_COLUMNS,
    POOLED_FEATURE_COLUMNS,
    PIT_MISSING_FEATURE_COLUMNS,
    compare_pooled_objectives,
    pooled_point_in_time_features,
    pooled_price_features,
    walk_forward_pooled_ridge,
)
from portfolio_alpha_v2 import PIT_ALPHA_FEATURES  # noqa: E402
from forecast_signal_research import (  # noqa: E402
    rank_signal_block_bootstrap,
)


def _research_prices(rows=600, ticker_count=10):
    dates = pd.date_range("2008-01-02", periods=rows, freq="B")
    x = np.arange(rows)
    return pd.DataFrame({
        f"R{index:02d}": 100.0 * np.exp(
            (0.00015 + index * 0.00005) * x
            + 0.006 * np.sin(x / (8.0 + index))
        )
        for index in range(ticker_count)
    }, index=dates)


def _point_in_time_features(prices):
    rows = []
    for date_index, available_date in enumerate(
        prices.index[252::21]
    ):
        for ticker_index, ticker in enumerate(prices.columns):
            rows.append({
                "available_date": available_date,
                "ticker": ticker,
                "sector": f"S{ticker_index % 3}",
                "market_cap": 1_000_000_000.0 * (ticker_index + 1),
                "quality": ticker_index + date_index * 0.1,
                "profitability": ticker_index * 0.5 - date_index * 0.1,
                "valuation": -ticker_index + date_index * 0.05,
                "liquidity": ticker_index * 0.2,
            })
    return pd.DataFrame(rows)


def test_pooled_price_features_use_history_through_as_of_only():
    prices = _research_prices(rows=360)
    as_of_prices = prices.iloc[:320]
    future_changed = prices.copy()
    future_changed.iloc[320:] *= 100.0

    baseline = pooled_price_features(as_of_prices)
    changed = pooled_price_features(future_changed.iloc[:320])

    pd.testing.assert_frame_equal(baseline, changed)
    assert list(baseline.columns) == list(POOLED_FEATURE_COLUMNS)
    assert baseline.notna().all().all()


def test_rank_signal_block_bootstrap_detects_persistent_signal():
    periods = [
        {
            "scores": {"A": 0.0, "B": 1.0, "C": 2.0},
            "realized_returns": {
                "A": float(index),
                "B": float(index + 1),
                "C": float(index + 2),
            },
        }
        for index in range(12)
    ]

    result = rank_signal_block_bootstrap(
        periods,
        block_size=3,
        samples=200,
        seed=7,
    )

    assert result["status"] == "ok"
    assert result["probability"]["positive_mean_rank_ic"] == 1.0
    assert (
        result["probability"]["positive_mean_top_bottom_spread"]
        == 1.0
    )


def test_walk_forward_pooled_ridge_uses_completed_training_targets():
    result = walk_forward_pooled_ridge(
        _research_prices(),
        objective="relative_ridge",
        horizon=21,
        rebalance_step=21,
        minimum_training_periods=4,
        maximum_training_periods=8,
        minimum_observations=20,
    )

    assert result["records"]
    assert result["rank_diagnostics"]["period_count"] >= 8
    assert result["cost"]["fit_count"] == len(result["records"])
    assert result["cost"]["prediction_count"] > 0
    assert result["uncertainty_diagnostics"]["observation_count"] >= 20
    assert set(result["feature_diagnostics"]) == set(
        POOLED_FEATURE_COLUMNS
    )
    assert all(
        "multiple_testing" in diagnostic
        for diagnostic in result["feature_diagnostics"].values()
    )
    assert any(
        record["reported_uncertainty"] is not None
        for record in result["records"]
    )
    assert all(
        pd.Timestamp(record["train_end_date"])
        <= pd.Timestamp(record["as_of_date"])
        < pd.Timestamp(record["forward_end_date"])
        for record in result["records"]
    )


def test_pit_predictors_ignore_future_filing_rows():
    prices = _research_prices(rows=360)
    feature_data = _point_in_time_features(prices)
    as_of = prices.index[300]
    future = feature_data["available_date"] > as_of
    changed = feature_data.copy()
    changed.loc[future, list(PIT_ALPHA_FEATURES)] = 1e12

    baseline = pooled_point_in_time_features(
        feature_data,
        as_of,
        prices.columns,
    )
    future_changed = pooled_point_in_time_features(
        changed,
        as_of,
        prices.columns,
    )

    pd.testing.assert_frame_equal(baseline, future_changed)
    assert list(baseline.columns) == list(
        PIT_ALPHA_FEATURES + PIT_MISSING_FEATURE_COLUMNS
    )
    assert baseline.notna().all().all()


def test_factor_residual_model_uses_pit_fundamentals_as_predictors():
    prices = _research_prices()
    result = walk_forward_pooled_ridge(
        prices,
        objective="factor_residual_ridge",
        horizon=21,
        rebalance_step=21,
        minimum_training_periods=4,
        maximum_training_periods=8,
        minimum_observations=20,
        point_in_time_features=_point_in_time_features(prices),
    )

    assert result["records"]
    assert result["settings"]["point_in_time_fundamentals"]
    assert result["settings"]["feature_columns"] == list(
        FACTOR_POOLED_FEATURE_COLUMNS
    )
    assert set(PIT_ALPHA_FEATURES).issubset(result["mean_coefficients"])
    assert set(PIT_MISSING_FEATURE_COLUMNS).issubset(
        result["mean_coefficients"]
    )


def test_factor_residual_price_baseline_uses_same_target_without_fundamentals():
    prices = _research_prices()
    result = walk_forward_pooled_ridge(
        prices,
        objective="factor_residual_price_ridge",
        horizon=21,
        rebalance_step=21,
        minimum_training_periods=4,
        maximum_training_periods=8,
        minimum_observations=20,
        point_in_time_features=_point_in_time_features(prices),
    )

    assert result["records"]
    assert result["target_kind"] == "factor_residual"
    assert not result["settings"]["point_in_time_fundamentals"]
    assert result["settings"]["feature_columns"] == list(
        POOLED_FEATURE_COLUMNS
    )


def test_compact_factor_residual_model_uses_quality_predictors_only():
    prices = _research_prices()
    result = walk_forward_pooled_ridge(
        prices,
        objective="factor_residual_quality_ridge",
        horizon=21,
        rebalance_step=21,
        minimum_training_periods=4,
        maximum_training_periods=8,
        minimum_observations=20,
        point_in_time_features=_point_in_time_features(prices),
    )

    assert result["records"]
    assert result["settings"]["point_in_time_fundamentals"]
    assert result["settings"]["feature_columns"] == [
        "quality",
        "profitability",
        "profitability_missing",
    ]
    assert set(result["mean_coefficients"]) == {
        "quality",
        "profitability",
        "profitability_missing",
    }


def test_pooled_objective_comparison_keeps_models_signal_only():
    comparison = compare_pooled_objectives(
        _research_prices(),
        objectives=(
            "absolute_ridge",
            "relative_ridge",
            "pairwise_ridge",
            "listwise_rank_ridge",
        ),
        horizon=21,
        rebalance_step=21,
        minimum_training_periods=4,
        maximum_training_periods=8,
        minimum_observations=20,
    )

    assert set(comparison["runs"]) == {
        "absolute_ridge",
        "relative_ridge",
        "pairwise_ridge",
        "listwise_rank_ridge",
    }
    assert comparison["selection_status"] in {
        "no_signal_candidate",
        "manual_review_required",
    }
    assert all(
        "portfolio" not in run
        for run in comparison["runs"].values()
    )


def test_walk_forward_uses_only_members_active_as_of_each_signal_date():
    prices = _research_prices(rows=480, ticker_count=6)
    entry_date = prices.index[400]
    manifest = pd.DataFrame(
        [
            {
                "effective_date": prices.index[0],
                "ticker": ticker,
                "in_universe": True,
            }
            for ticker in prices.columns[:5]
        ]
        + [
            {
                "effective_date": entry_date,
                "ticker": prices.columns[5],
                "in_universe": True,
            }
        ]
    )

    result = walk_forward_pooled_ridge(
        prices,
        objective="relative_ridge",
        horizon=21,
        rebalance_step=21,
        minimum_training_periods=4,
        maximum_training_periods=8,
        minimum_observations=20,
        universe_manifest=manifest,
    )

    assert result["records"]
    assert result["settings"]["dated_universe_manifest"]
    for record in result["records"]:
        scores = set(record["scores"])
        if pd.Timestamp(record["as_of_date"]) < entry_date:
            assert prices.columns[5] not in scores
            assert record["active_universe_size"] == 5
        else:
            assert record["active_universe_size"] == 6


def test_walk_forward_handles_ticker_with_late_price_inception():
    prices = _research_prices(rows=600, ticker_count=10)
    prices.loc[prices.index[:420], prices.columns[-1]] = np.nan

    result = walk_forward_pooled_ridge(
        prices,
        objective="relative_ridge",
        horizon=21,
        rebalance_step=21,
        minimum_training_periods=4,
        maximum_training_periods=8,
        minimum_observations=20,
    )

    assert result["records"]
    early_record = next(
        record for record in result["records"]
        if pd.Timestamp(record["as_of_date"]) < prices.index[420]
    )
    assert prices.columns[-1] not in early_record["scores"]


def test_research_cli_rejects_reserved_validation_split(tmp_path):
    prices_path = tmp_path / "prices.csv"
    _research_prices(rows=300).to_csv(prices_path)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "research_cross_sectional_forecasts.py"),
            "--csv",
            str(prices_path),
            "--research-split",
            "validation",
            "--experiment-namespace",
            "invalid",
            "--output",
            str(tmp_path / "result.json"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Reserved validation/holdout split" in result.stderr


def test_research_cli_requires_matching_factor_provenance(tmp_path):
    prices_path = tmp_path / "prices.csv"
    factor_path = tmp_path / "factors.csv"
    output_path = tmp_path / "result.json"
    _research_prices(rows=300).to_csv(prices_path)
    _point_in_time_features(_research_prices(rows=300)).to_csv(
        factor_path,
        index=False,
    )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "research_cross_sectional_forecasts.py"),
            "--csv",
            str(prices_path),
            "--research-split",
            "research_a",
            "--experiment-namespace",
            "factor_a",
            "--objectives",
            "factor_residual_ridge",
            "--factor-data",
            str(factor_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--factor-data requires --factor-provenance" in result.stderr
