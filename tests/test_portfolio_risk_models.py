import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import portfolio_backtest  # noqa: E402
from portfolio_signals import risk_managed_momentum_weights  # noqa: E402
from portfolio_risk_models import (  # noqa: E402
    covariance_diagnostics,
    covariance_forecast_loss,
    covariance_stress_diagnostics,
    cross_validated_covariance,
    cross_validated_minimum_variance_weights,
    equal_risk_contribution_weights,
    forecast_ensemble_covariance,
    forecast_ensemble_minimum_variance_weights,
    hierarchical_risk_parity_weights,
    minimum_cvar_weights,
    nested_blended_minimum_variance_weights,
    random_matrix_denoised_covariance,
    random_matrix_minimum_variance_weights,
    regime_minimum_variance_weights,
    regime_conditioned_covariance,
    resampled_minimum_variance_weights,
    risk_allocator_case_gate,
    robust_covariance,
    robust_minimum_variance_weights,
    scenario_robust_minimum_variance_weights,
    stability_regularized_minimum_variance_weights,
    volatility_targeted_minimum_variance_weights,
)


def _correlated_prices(rows=620, asset_count=6):
    rng = np.random.default_rng(42)
    dates = pd.date_range("2010-01-04", periods=rows, freq="B")
    market = rng.normal(0.0003, 0.010, rows)
    returns = {}
    for index in range(asset_count):
        beta = 0.5 + index * 0.2
        idiosyncratic = rng.normal(0.0, 0.004 + index * 0.001, rows)
        returns[f"A{index}"] = market * beta + idiosyncratic
    return pd.DataFrame({
        ticker: 100.0 * np.exp(np.cumsum(values))
        for ticker, values in returns.items()
    }, index=dates)


def _regime_shift_prices(rows=620, asset_count=6):
    rng = np.random.default_rng(7)
    dates = pd.date_range("2010-01-04", periods=rows, freq="B")
    calm_rows = rows - 126
    market = np.concatenate([
        rng.normal(0.0003, 0.004, calm_rows),
        rng.normal(-0.0002, 0.025, rows - calm_rows),
    ])
    returns = {}
    for index in range(asset_count):
        idiosyncratic = np.concatenate([
            rng.normal(0.0, 0.002, calm_rows),
            rng.normal(0.0, 0.008, rows - calm_rows),
        ])
        returns[f"A{index}"] = market * (0.6 + index * 0.1) + idiosyncratic
    return pd.DataFrame({
        ticker: 100.0 * np.exp(np.cumsum(values))
        for ticker, values in returns.items()
    }, index=dates)


def test_robust_covariance_is_psd_and_reports_conditioning():
    covariance, metadata = robust_covariance(_correlated_prices())
    diagnostics = covariance_diagnostics(covariance)

    assert np.linalg.eigvalsh(covariance.values).min() >= -1e-10
    assert metadata["method"] == "ledoit_oas_exponential_blend"
    assert diagnostics["condition_number"] > 0
    assert 1.0 <= diagnostics["effective_rank"] <= len(covariance)


@pytest.mark.parametrize(
    "allocator",
    (
        robust_minimum_variance_weights,
        equal_risk_contribution_weights,
        hierarchical_risk_parity_weights,
        regime_minimum_variance_weights,
        minimum_cvar_weights,
        cross_validated_minimum_variance_weights,
        forecast_ensemble_minimum_variance_weights,
        stability_regularized_minimum_variance_weights,
        nested_blended_minimum_variance_weights,
        resampled_minimum_variance_weights,
        scenario_robust_minimum_variance_weights,
        random_matrix_minimum_variance_weights,
    ),
)
def test_robust_risk_allocators_are_long_only_capped(allocator):
    weights, diagnostics = allocator(
        _correlated_prices(),
        max_asset_weight=0.25,
    )

    assert weights.sum() == pytest.approx(1.0)
    assert weights.min() >= 0.0
    assert weights.max() <= 0.250001
    assert diagnostics


def test_scenario_robust_allocator_reduces_training_worst_case_risk():
    weights, diagnostics = scenario_robust_minimum_variance_weights(
        _correlated_prices(),
        max_asset_weight=0.25,
    )

    assert diagnostics["optimizer_success"] is True
    assert diagnostics["scenario_count"] == 3
    assert diagnostics["worst_case_variance_reduction"] >= -1e-10
    assert (
        diagnostics["worst_case_annual_volatility"]
        <= diagnostics["baseline_worst_case_annual_volatility"] + 1e-8
    )
    assert weights.sum() == pytest.approx(1.0)


def test_random_matrix_covariance_is_psd_and_denoises_noise():
    prices = _correlated_prices(rows=620, asset_count=20)

    covariance, diagnostics = random_matrix_denoised_covariance(
        prices
    )

    assert covariance.shape == (20, 20)
    assert np.linalg.eigvalsh(covariance.values).min() >= -1e-10
    assert diagnostics["method"] == (
        "marchenko_pastur_correlation_denoising"
    )
    assert diagnostics["noise_eigenvalue_count"] > 0
    assert diagnostics["signal_eigenvalue_count"] > 0
    assert (
        diagnostics["noise_eigenvalue_count"]
        + diagnostics["signal_eigenvalue_count"]
        == 20
    )
    assert diagnostics["variance_source"] == "ledoit_wolf_diagonal"


def test_volatility_targeted_allocator_holds_cash_in_elevated_risk():
    weights, diagnostics = volatility_targeted_minimum_variance_weights(
        _regime_shift_prices(),
        max_asset_weight=0.25,
    )

    assert 0.25 <= weights.sum() < 1.0
    assert diagnostics["allow_cash_reserve"] is True
    assert diagnostics["target_cash_weight"] > 0.0
    assert (
        diagnostics["current_predicted_annual_volatility"]
        > diagnostics["reference_predicted_annual_volatility"]
    )
    assert weights.max() <= 0.250001


def test_backtest_cash_path_accrues_point_in_time_risk_free_returns():
    dates = pd.date_range("2020-01-01", periods=4, freq="B")
    risk_free = pd.Series(
        [0.01, 0.02, 0.03],
        index=dates[:3],
    )

    path = portfolio_backtest._cash_value_path(
        100.0,
        dates,
        risk_free_rate=0.0,
        risk_free_daily_returns=risk_free,
    )

    assert path.iloc[0] == pytest.approx(100.0)
    assert path.iloc[1] == pytest.approx(102.0)
    assert path.iloc[2] == pytest.approx(105.06)
    assert path.iloc[3] == pytest.approx(108.2118)


def test_equal_risk_contribution_balances_covariance_risk():
    _, diagnostics = equal_risk_contribution_weights(
        _correlated_prices(),
        max_asset_weight=0.40,
    )

    assert diagnostics["optimizer_success"] is True
    assert diagnostics["risk_contribution_dispersion"] < 0.02


def test_backtest_runs_robust_risk_allocator_family():
    result = portfolio_backtest.run_portfolio_model_backtest(
        _correlated_prices(),
        models=(
            "robust_min_variance",
            "equal_risk_contribution",
            "hierarchical_risk_parity",
            "regime_minimum_variance",
            "minimum_cvar",
            "forecast_ensemble_min_variance",
            "stability_regularized_min_variance",
            "nested_blended_min_variance",
            "resampled_min_variance",
            "scenario_robust_min_variance",
            "volatility_targeted_min_variance",
            "random_matrix_minimum_variance",
        ),
        train_window=252,
        rebalance_frequency=63,
        forecast_horizon=63,
        max_asset_weight=0.25,
    )

    assert set(result["summary_by_model"]) == {
        "robust_min_variance",
        "equal_risk_contribution",
        "hierarchical_risk_parity",
        "regime_minimum_variance",
        "minimum_cvar",
        "forecast_ensemble_min_variance",
        "stability_regularized_min_variance",
        "nested_blended_min_variance",
        "resampled_min_variance",
        "scenario_robust_min_variance",
        "volatility_targeted_min_variance",
        "random_matrix_minimum_variance",
    }
    assert all(
        record["risk_model"]
        for record in result["rebalance_records"]
    )


def test_nested_blended_allocator_uses_completed_inner_variance_folds():
    weights, diagnostics = nested_blended_minimum_variance_weights(
        _correlated_prices(rows=700),
        max_asset_weight=0.25,
        blend_grid=(0.0, 0.5, 1.0),
    )

    assert weights.sum() == pytest.approx(1.0)
    assert diagnostics["inner_fold_count"] >= 1
    assert diagnostics["fallback"] is False
    assert diagnostics["selected_inverse_volatility_weight"] in {
        0.0,
        0.5,
        1.0,
    }
    assert set(diagnostics["candidate_scores"]) == {
        "0.0",
        "0.5",
        "1.0",
    }


def test_risk_allocator_gate_requires_improvement_over_min_variance():
    baseline = {
        "annual_volatility": 0.20,
        "sharpe": 0.30,
        "max_drawdown": -0.30,
        "avg_controlled_turnover": 0.10,
    }
    passed = risk_allocator_case_gate({
        "min_variance": baseline,
        "robust_min_variance": {
            "annual_volatility": 0.19,
            "sharpe": 0.31,
            "max_drawdown": -0.29,
            "avg_controlled_turnover": 0.11,
        },
    })
    rejected = risk_allocator_case_gate({
        "min_variance": baseline,
        "robust_min_variance": {
            "annual_volatility": 0.21,
            "sharpe": 0.29,
            "max_drawdown": -0.31,
            "avg_controlled_turnover": 0.11,
        },
    })

    assert passed["status"] == "passed"
    assert rejected["status"] == "rejected"
    assert len(rejected["reasons"]) == 3


def test_portfolio_metrics_include_downside_and_tail_risk():
    values = pd.Series(
        [100.0, 102.0, 99.0, 103.0, 97.0, 104.0],
        index=pd.date_range("2024-01-02", periods=6, freq="B"),
    )

    metrics = portfolio_backtest._portfolio_metrics(values, risk_free_rate=0.02)

    assert metrics["annual_downside_deviation"] > 0
    assert metrics["sortino"] is not None
    assert metrics["calmar"] is not None
    assert metrics["omega"] is not None
    assert metrics["daily_var_95"] > 0
    assert metrics["daily_cvar_95"] >= metrics["daily_var_95"]


def test_portfolio_metrics_use_historical_daily_risk_free_returns():
    dates = pd.date_range("2024-01-02", periods=253, freq="B")
    values = pd.Series(
        100.0 * np.cumprod(np.full(len(dates), 1.001)),
        index=dates,
    )
    risk_free = pd.Series(0.0002, index=dates)

    metrics = portfolio_backtest._portfolio_metrics(
        values,
        risk_free_rate=0.02,
        risk_free_daily_returns=risk_free,
    )

    assert metrics["risk_free_observation_coverage"] == 1.0
    assert metrics["annualized_excess_return"] == pytest.approx(
        (0.001 - 0.0002) * 252,
        rel=1e-6,
    )
    assert metrics["annualized_risk_free_return"] == pytest.approx(
        (1.0002 ** 252) - 1.0,
        rel=1e-6,
    )


def test_cross_validated_covariance_reports_inner_selection():
    covariance, diagnostics = cross_validated_covariance(
        _correlated_prices(),
        max_asset_weight=0.25,
    )

    assert covariance.shape == (6, 6)
    assert diagnostics["method"] == "cross_validated_covariance"
    assert diagnostics["selected_estimator"] in {
        "ledoit_wolf",
        "oracle_approximating",
        "exponential_60",
        "exponential_180",
        "robust_static",
    }
    assert diagnostics["inner_fold_count"] > 0


def test_covariance_forecast_loss_prefers_realized_covariance():
    prices = _correlated_prices(rows=700)
    returns = prices.pct_change().dropna()
    realized_window = returns.iloc[-63:]
    realized = realized_window.cov(ddof=0) * 252
    distorted = realized.copy()
    distorted.values[:] = np.diag(np.diag(realized.values) * 3.0)

    exact = covariance_forecast_loss(realized, realized_window)
    wrong = covariance_forecast_loss(distorted, realized_window)

    assert exact["composite_loss"] == pytest.approx(0.0, abs=1e-8)
    assert wrong["composite_loss"] > exact["composite_loss"]


def test_forecast_ensemble_covariance_is_psd_and_weighted():
    covariance, diagnostics = forecast_ensemble_covariance(
        _correlated_prices()
    )

    assert np.linalg.eigvalsh(covariance.values).min() >= -1e-10
    assert diagnostics["method"] == (
        "oos_forecast_loss_covariance_ensemble"
    )
    assert diagnostics["inner_fold_count"] > 0
    assert sum(diagnostics["ensemble_weights"].values()) == pytest.approx(1.0)
    assert all(
        weight > 0
        for weight in diagnostics["ensemble_weights"].values()
    )


def test_covariance_stress_diagnostics_raise_predicted_risk():
    prices = _correlated_prices()
    covariance, _ = robust_covariance(prices)
    weights = pd.Series(
        1.0 / len(prices.columns),
        index=prices.columns,
    )

    diagnostics = covariance_stress_diagnostics(
        covariance,
        weights,
    )

    assert diagnostics["stressed_annual_volatility"] > (
        diagnostics["baseline_annual_volatility"]
    )
    assert diagnostics["stress_amplification"] > 1.0
    assert diagnostics["effective_asset_count"] == pytest.approx(
        len(prices.columns)
    )


def test_stability_regularization_uses_previous_target():
    prices = _correlated_prices()
    previous = pd.Series(
        [0.25, 0.25, 0.25, 0.25, 0.0, 0.0],
        index=prices.columns,
    )
    weights, diagnostics = stability_regularized_minimum_variance_weights(
        prices,
        previous_weights=previous,
        max_asset_weight=0.25,
    )

    assert weights.sum() == pytest.approx(1.0)
    assert weights.min() >= 0.0
    assert weights.max() <= 0.250001
    assert diagnostics["optimizer_success"] is True
    assert diagnostics["reference_source"] == "previous_target"


def test_backtest_reports_out_of_sample_risk_forecast_calibration():
    result = portfolio_backtest.run_portfolio_model_backtest(
        _correlated_prices(),
        models=("min_variance",),
        train_window=252,
        rebalance_frequency=63,
        forecast_horizon=63,
        max_asset_weight=0.25,
    )
    metrics = result["summary_by_model"]["min_variance"]

    assert metrics["risk_forecast_mae"] is not None
    assert metrics["risk_forecast_mae"] >= 0.0
    assert metrics["avg_risk_forecast_ratio"] > 0.0
    assert all(
        record["realized_period_annual_volatility"] is not None
        for record in result["rebalance_records"]
    )


def test_resampled_minimum_variance_is_reproducible():
    prices = _correlated_prices()
    first, first_diagnostics = resampled_minimum_variance_weights(
        prices,
        max_asset_weight=0.25,
        bootstrap_samples=8,
        seed=17,
    )
    second, second_diagnostics = resampled_minimum_variance_weights(
        prices,
        max_asset_weight=0.25,
        bootstrap_samples=8,
        seed=17,
    )

    pd.testing.assert_series_equal(first, second)
    assert first_diagnostics == second_diagnostics
    assert first_diagnostics["optimizer_success_rate"] == pytest.approx(1.0)


def test_regime_covariance_uses_bounded_continuous_stress():
    covariance, diagnostics = regime_conditioned_covariance(
        _correlated_prices()
    )

    assert covariance.shape == (6, 6)
    assert diagnostics["method"] == (
        "continuous_regime_conditioned_covariance_v2"
    )
    assert 0.0 <= diagnostics["stress_intensity"] <= 1.0
    assert diagnostics["regime"] in {"normal", "stress"}


def test_risk_managed_momentum_is_long_only_capped():
    weights = risk_managed_momentum_weights(
        _correlated_prices(),
        max_asset_weight=0.25,
    )

    assert weights.sum() == pytest.approx(1.0)
    assert weights.min() >= 0.0
    assert weights.max() <= 0.250001
