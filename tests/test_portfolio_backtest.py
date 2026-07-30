import json
import os
import subprocess
import sys
from concurrent.futures import Future
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import portfolio_backtest
import portfolio_optimization
from portfolio_alpha_v2 import (
    factor_neutral_cross_sectional_alpha,
    fit_regularized_alpha,
    point_in_time_snapshot,
)
from forecast_models import (
    ARIMATransformerPredictor,
    NO_VIEW_FORECAST_UNCERTAINTY,
    TransformerForecastModel,
    no_view_prediction,
)
from forecast_signal_research import (
    build_completed_forward_targets,
    empirical_oos_uncertainty,
    prediction_distribution_diagnostics,
    signal_only_gate,
)
from lightweight_forecast import (
    calibrated_lightweight_ensemble_forecast,
    lightweight_ensemble_forecast,
)
from portfolio_signals import (
    adaptive_cross_sectional_alpha,
    adaptive_factor_momentum_scores,
    calibrate_cross_sectional_alpha,
    drawdown_score,
    dual_horizon_momentum_weights,
    factor_residual_momentum_scores,
    fifty_two_week_high_score,
    high_momentum_scores,
    market_cap_weight,
    momentum_6m,
    momentum_12_1,
    profitability_momentum_scores,
    risk_parity,
    risk_momentum_blend_weights,
    short_term_reversal_score,
    signal_tilt_weights,
    signal_stack_bl_views,
    volatility_score,
)


def _synthetic_prices(rows=90):
    dates = pd.date_range("2024-01-02", periods=rows, freq="B")
    x = np.arange(rows)
    return pd.DataFrame(
        {
            "AAA": 100.0 * np.exp(0.0010 * x),
            "BBB": 80.0 * np.exp(0.0006 * x + 0.01 * np.sin(x / 5.0)),
            "CCC": 120.0 * np.exp(0.0002 * x + 0.008 * np.cos(x / 7.0)),
        },
        index=dates,
    )


def _synthetic_factor_research_data(rows=520, ticker_count=8):
    dates = pd.date_range("2018-01-02", periods=rows, freq="B")
    x = np.arange(rows)
    tickers = [f"T{index:02d}" for index in range(ticker_count)]
    prices = {}
    for index, ticker in enumerate(tickers):
        cycle = 0.004 * np.sin(x / (7.0 + index))
        drift = 0.0002 + index * 0.00008
        prices[ticker] = 100.0 * np.exp(drift * x + cycle)
    price_frame = pd.DataFrame(prices, index=dates)

    rows_out = []
    for position in range(0, rows, 42):
        for index, ticker in enumerate(tickers):
            rows_out.append({
                "available_date": dates[position],
                "ticker": ticker,
                "sector": ("tech", "financials", "healthcare")[index % 3],
                "market_cap": 1_000_000_000.0 * (index + 1) * (1 + position / rows),
                "quality": 0.2 * index + 0.01 * position,
                "profitability": 1.0 - 0.08 * index + 0.005 * position,
                "valuation": 0.1 * (ticker_count - index) + 0.002 * position,
                "liquidity": np.log1p((index + 1) * (position + 20)),
            })
    return price_frame, pd.DataFrame(rows_out)


def test_untrained_transformer_predict_returns_no_view():
    model = TransformerForecastModel()

    prediction = model.predict(horizon=21)

    assert prediction["source"] == "no_view"
    assert prediction["expected_return"] is None
    assert prediction["uncertainty"] == pytest.approx(NO_VIEW_FORECAST_UNCERTAINTY)


def test_arima_transformer_ignores_no_view_transformer_component(monkeypatch):
    predictor = ARIMATransformerPredictor()
    predictor.history = np.linspace(100.0, 120.0, 150)
    monkeypatch.setattr(predictor.arima, "forecast", lambda prices, horizon=63: (0.02, 0.10))
    monkeypatch.setattr(
        predictor.transformer,
        "predict",
        lambda horizon=63: no_view_prediction("forced no-view"),
    )

    prediction = predictor.predict(horizon=63)

    assert prediction["source"] != "no_view"
    assert prediction["expected_return"] == pytest.approx(0.02 * (252 / 63))
    assert prediction["components"] == {"ARIMA": pytest.approx(0.08)}


def test_transformer_reports_pre_and_post_clip_diagnostics():
    class FakeModel:
        @staticmethod
        def predict(values, verbose=0):
            return np.array([[0.02]])

    class IdentityScaler:
        @staticmethod
        def inverse_transform(values):
            return np.asarray(values, dtype=float)

        @staticmethod
        def transform(values):
            return np.asarray(values, dtype=float)

    model = TransformerForecastModel(lookback=10, forecast_clip=0.20)
    model.model = FakeModel()
    model.scaler = IdentityScaler()
    model.last_sequence = np.zeros((10, 1))
    model.training_daily_rmse = 0.01

    prediction = model.predict(horizon=63)

    assert prediction["expected_return"] == pytest.approx(0.69)
    assert prediction["diagnostics"]["pre_annual_clip_log_return"] > 0.69
    assert prediction["diagnostics"]["annual_clip_boundary_hit"] is True
    assert prediction["diagnostics"]["uncertainty_source"] == "in_sample_training_rmse"


def test_forecast_distribution_and_oos_uncertainty_diagnostics():
    distribution = prediction_distribution_diagnostics([
        {"expected_return": 0.69, "uncertainty": 0.20},
        {"expected_return": 0.69, "uncertainty": 0.20},
        {"expected_return": -0.69, "uncertainty": 0.30},
        {"expected_return": None, "uncertainty": 5.0},
    ])
    calibration = empirical_oos_uncertainty(
        pd.Series(np.linspace(-0.10, 0.10, 20)),
        pd.Series(np.linspace(-0.08, 0.12, 20)),
        reported_uncertainties=pd.Series(np.full(20, 0.03)),
        minimum_observations=20,
    )
    gate = signal_only_gate(
        {
            "period_count": 8,
            "mean_rank_ic": 0.05,
            "positive_rank_ic_rate": 0.625,
            "mean_top_bottom_spread": 0.01,
        },
        distribution,
    )

    assert distribution["coverage_rate"] == pytest.approx(0.75)
    assert distribution["boundary_saturation_rate"] == pytest.approx(1.0)
    assert distribution["tie_rate"] == pytest.approx(1 / 3)
    assert calibration["reported_uncertainty_coverage"] == pytest.approx(1.0)
    assert gate["status"] == "rejected"
    assert "Forecast boundary saturation is too high." in gate["reasons"]


def test_calibrated_lightweight_forecast_uses_completed_origins_only():
    rows = 520
    x = np.arange(rows)
    prices = 100.0 * np.exp(
        0.0004 * x + 0.012 * np.sin(x / 11.0)
    )
    cutoff = 479

    result = calibrated_lightweight_ensemble_forecast(
        prices[:cutoff + 1],
        horizon=63,
    )
    mutated = prices.copy()
    mutated[cutoff + 1:] *= np.linspace(1.0, 8.0, rows - cutoff - 1)
    repeated = calibrated_lightweight_ensemble_forecast(
        mutated[:cutoff + 1],
        horizon=63,
    )

    assert result["period_return"] == pytest.approx(
        lightweight_ensemble_forecast(
            prices[:cutoff + 1],
            horizon=63,
        )
    )
    assert result["annual_expected_return"] == pytest.approx(
        repeated["annual_expected_return"]
    )
    assert result["annual_uncertainty"] == pytest.approx(
        repeated["annual_uncertainty"]
    )
    diagnostics = result["diagnostics"]
    assert diagnostics["observation_count"] == 5
    assert all(
        row["forward_end_position"] <= cutoff
        for row in diagnostics["calibration_rows"]
    )


def test_calibrated_lightweight_bl_reports_oos_uncertainty():
    prices = _synthetic_factor_research_data(
        rows=520,
        ticker_count=8,
    )[0]

    views, uncertainties, failed, diagnostics = (
        portfolio_backtest._forecast_views(
            prices.iloc[:504],
            "calibrated_lightweight",
            63,
        )
    )

    assert failed == 0
    assert views.notna().all()
    assert uncertainties.between(1e-4, 5.0).all()
    calibration = diagnostics[
        "lightweight_uncertainty_calibration"
    ]
    assert set(calibration) == set(prices.columns)
    assert all(
        item["observation_count"] == 6
        for item in calibration.values()
    )
    _, bl_diagnostics = portfolio_backtest._black_litterman_weights(
        prices.iloc[:504],
        "calibrated_lightweight",
        63,
        0.25,
        0.02,
    )
    assert bl_diagnostics["signal_scores"] == (
        bl_diagnostics["raw_views"]
    )


def test_fifty_two_week_high_signal_prefers_prices_near_prior_highs():
    dates = pd.date_range("2020-01-02", periods=252, freq="B")
    prices = pd.DataFrame(
        {
            "NEAR": np.linspace(80.0, 120.0, len(dates)),
            "FAR": np.concatenate([
                np.linspace(80.0, 140.0, 126),
                np.linspace(140.0, 90.0, 126),
            ]),
            "MID": np.concatenate([
                np.linspace(90.0, 110.0, 126),
                np.linspace(110.0, 100.0, 126),
            ]),
        },
        index=dates,
    )

    scores = fifty_two_week_high_score(prices)

    assert scores["NEAR"] > scores["MID"] > scores["FAR"]


def test_high_momentum_signal_and_weights_ignore_future_rows():
    prices = _synthetic_factor_research_data(
        rows=580,
        ticker_count=8,
    )[0]
    cutoff = 503
    changed = prices.copy()
    changed.iloc[cutoff + 1:] *= np.linspace(
        1.0,
        50.0,
        len(changed) - cutoff - 1,
    )[:, None]

    scores = high_momentum_scores(prices.iloc[:cutoff + 1])
    repeated_scores = high_momentum_scores(
        changed.iloc[:cutoff + 1]
    )
    weights, diagnostics = (
        portfolio_backtest._price_signal_rank_tilt_weights(
            prices.iloc[:cutoff + 1],
            "high_momentum",
            0.25,
        )
    )
    repeated_weights, repeated_diagnostics = (
        portfolio_backtest._price_signal_rank_tilt_weights(
            changed.iloc[:cutoff + 1],
            "high_momentum",
            0.25,
        )
    )

    pd.testing.assert_series_equal(scores, repeated_scores)
    assert weights == pytest.approx(repeated_weights)
    assert diagnostics == repeated_diagnostics
    assert sum(weights.values()) == pytest.approx(1.0)
    equal_weight = 1.0 / len(weights)
    active_share = 0.5 * sum(
        abs(weight - equal_weight)
        for weight in weights.values()
    )
    assert active_share == pytest.approx(
        portfolio_backtest.PRICE_SIGNAL_TARGET_ACTIVE_SHARE
    )


def test_high_momentum_models_are_opt_in_with_same_construction():
    prices = _synthetic_factor_research_data(
        rows=520,
        ticker_count=8,
    )[0]
    models = (
        "momentum_12_1_rank_tilt",
        "high_momentum_rank_tilt",
    )

    result = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=models,
        train_window=504,
        rebalance_frequency=8,
        forecast_horizon=8,
        max_asset_weight=0.25,
    )

    assert set(models).issubset(
        portfolio_backtest.SUPPORTED_BACKTEST_MODELS
    )
    assert set(models).isdisjoint(
        portfolio_backtest.DEFAULT_BACKTEST_MODELS
    )
    records = result["rebalance_records"]
    assert records
    assert all(record["signal_scores"] for record in records)
    assert all(
        record["active_share"]
        == pytest.approx(
            portfolio_backtest.PRICE_SIGNAL_TARGET_ACTIVE_SHARE
        )
        for record in records
    )


def test_risk_momentum_blend_is_exact_fixed_component_average():
    prices = _synthetic_factor_research_data(
        rows=520,
        ticker_count=8,
    )[0]
    risk_weights = risk_parity(
        prices.iloc[:504],
        max_asset_weight=0.25,
    )
    momentum_weights, _ = (
        portfolio_backtest._price_signal_rank_tilt_weights(
            prices.iloc[:504],
            "momentum_12_1",
            0.25,
        )
    )

    blended = risk_momentum_blend_weights(
        prices.iloc[:504],
        max_asset_weight=0.25,
        target_active_share=(
            portfolio_backtest.PRICE_SIGNAL_TARGET_ACTIVE_SHARE
        ),
    )
    expected = (
        0.50 * risk_weights
        + 0.50 * pd.Series(momentum_weights)
    )

    pd.testing.assert_series_equal(
        blended,
        expected,
        check_names=False,
    )


def test_risk_momentum_blend_is_opt_in_and_ignores_future_rows():
    prices = _synthetic_factor_research_data(
        rows=580,
        ticker_count=8,
    )[0]
    cutoff = 503
    changed = prices.copy()
    changed.iloc[cutoff + 1:] *= np.linspace(
        1.0,
        50.0,
        len(changed) - cutoff - 1,
    )[:, None]

    weights, diagnostics = portfolio_backtest._model_weights(
        "risk_momentum_blend",
        prices.iloc[:cutoff + 1],
        63,
        0.25,
        0.02,
    )
    repeated, repeated_diagnostics = (
        portfolio_backtest._model_weights(
            "risk_momentum_blend",
            changed.iloc[:cutoff + 1],
            63,
            0.25,
            0.02,
        )
    )

    assert "risk_momentum_blend" in (
        portfolio_backtest.SUPPORTED_BACKTEST_MODELS
    )
    assert "risk_momentum_blend" not in (
        portfolio_backtest.DEFAULT_BACKTEST_MODELS
    )
    assert weights == pytest.approx(repeated)
    assert diagnostics == repeated_diagnostics
    assert sum(weights.values()) == pytest.approx(1.0)
    assert diagnostics["alpha_component_weights"] == {
        "risk_parity": 0.50,
        "momentum_12_1_rank_tilt": 0.50,
    }


def test_minvar_momentum_blend_is_exact_fixed_component_average():
    prices = _synthetic_factor_research_data(
        rows=520,
        ticker_count=8,
    )[0].iloc[:504]
    minimum_variance, _ = portfolio_backtest._model_weights(
        "min_variance",
        prices,
        63,
        0.25,
        0.02,
    )
    momentum, _ = (
        portfolio_backtest._price_signal_rank_tilt_weights(
            prices,
            "momentum_12_1",
            0.25,
        )
    )

    blended, diagnostics = portfolio_backtest._model_weights(
        "minvar_momentum_blend",
        prices,
        63,
        0.25,
        0.02,
    )
    expected = (
        0.50 * pd.Series(minimum_variance)
        + 0.50 * pd.Series(momentum)
    )

    assert blended == pytest.approx(expected.to_dict())
    assert diagnostics["alpha_component_weights"] == {
        "min_variance": 0.50,
        "momentum_12_1_rank_tilt": 0.50,
    }


def test_minvar_momentum_blend_is_opt_in_and_ignores_future_rows():
    prices = _synthetic_factor_research_data(
        rows=580,
        ticker_count=8,
    )[0]
    cutoff = 503
    changed = prices.copy()
    changed.iloc[cutoff + 1:] *= np.linspace(
        1.0,
        50.0,
        len(changed) - cutoff - 1,
    )[:, None]

    weights, diagnostics = portfolio_backtest._model_weights(
        "minvar_momentum_blend",
        prices.iloc[:cutoff + 1],
        63,
        0.25,
        0.02,
    )
    repeated, repeated_diagnostics = (
        portfolio_backtest._model_weights(
            "minvar_momentum_blend",
            changed.iloc[:cutoff + 1],
            63,
            0.25,
            0.02,
        )
    )

    assert "minvar_momentum_blend" in (
        portfolio_backtest.SUPPORTED_BACKTEST_MODELS
    )
    assert "minvar_momentum_blend" not in (
        portfolio_backtest.DEFAULT_BACKTEST_MODELS
    )
    assert weights == pytest.approx(repeated)
    assert diagnostics == repeated_diagnostics
    assert sum(weights.values()) == pytest.approx(1.0)


def test_conditional_volatility_minvar_reuses_arima_transformer_path(
    monkeypatch,
):
    prices = _synthetic_factor_research_data(
        rows=520,
        ticker_count=8,
    )[0].iloc[:504]
    calls = []

    def fake_forecast(ticker, history, horizon):
        calls.append((ticker, len(history), horizon))
        return {
            "expected_return": 0.0,
            "uncertainty": 0.1,
            "source": "arima_transformer",
        }

    monkeypatch.setattr(
        portfolio_backtest,
        "forecast_single_ticker_with_arima_transformer",
        fake_forecast,
    )
    portfolio_backtest.configure_forecast_rank_cache(
        namespace="conditional-volatility-test",
    )
    weights, diagnostics = portfolio_backtest._model_weights(
        "conditional_volatility_minimum_variance",
        prices,
        63,
        0.25,
        0.02,
    )

    assert len(calls) == len(prices.columns)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert max(weights.values()) <= 0.25 + 1e-9
    assert diagnostics["failed_forecast_count"] == 0
    assert diagnostics["risk_model"]["forecast_coverage_rate"] == 1.0
    assert "conditional_volatility_minimum_variance" in (
        portfolio_backtest.SUPPORTED_BACKTEST_MODELS
    )
    assert "conditional_volatility_minimum_variance" not in (
        portfolio_backtest.DEFAULT_BACKTEST_MODELS
    )


def test_james_stein_expected_returns_reduce_cross_sectional_dispersion():
    dates = pd.date_range("2020-01-02", periods=400, freq="B")
    rng = np.random.default_rng(42)
    daily_returns = rng.normal(
        loc=np.array([0.0015, 0.0005, -0.0004]),
        scale=np.array([0.012, 0.010, 0.011]),
        size=(len(dates), 3),
    )
    prices = pd.DataFrame(
        100.0 * np.cumprod(1.0 + daily_returns, axis=0),
        index=dates,
        columns=["AAA", "BBB", "CCC"],
    )

    estimates, diagnostics = (
        portfolio_optimization._james_stein_expected_returns(prices)
    )

    raw_annual_means = prices.pct_change(
        fill_method=None
    ).dropna().mean() * 252
    assert estimates.notna().all()
    assert diagnostics["estimator"] == "jorion_bayes_stein"
    assert 0.0 <= diagnostics["shrinkage_intensity"] <= 1.0
    assert estimates.std(ddof=0) < raw_annual_means.std(ddof=0)
    assert diagnostics["shrunk_mean_dispersion"] < (
        diagnostics["sample_mean_dispersion"]
    )


def test_james_stein_estimator_uses_only_supplied_training_rows():
    prices = _synthetic_factor_research_data(
        rows=580,
        ticker_count=8,
    )[0]
    cutoff = 503
    changed = prices.copy()
    changed.iloc[cutoff + 1:] *= np.linspace(
        1.0,
        50.0,
        len(changed) - cutoff - 1,
    )[:, None]

    estimates, diagnostics = (
        portfolio_optimization._james_stein_expected_returns(
            prices.iloc[:cutoff + 1]
        )
    )
    repeated, repeated_diagnostics = (
        portfolio_optimization._james_stein_expected_returns(
            changed.iloc[:cutoff + 1]
        )
    )

    pd.testing.assert_series_equal(estimates, repeated)
    assert diagnostics == repeated_diagnostics


def test_james_stein_bl_is_opt_in_and_reports_estimator_diagnostics():
    prices = _synthetic_factor_research_data(
        rows=520,
        ticker_count=8,
    )[0]

    result = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("historical_bl", "james_stein_bl"),
        train_window=504,
        rebalance_frequency=8,
        forecast_horizon=8,
        max_asset_weight=0.25,
    )

    assert "james_stein_bl" in (
        portfolio_backtest.SUPPORTED_BACKTEST_MODELS
    )
    assert "james_stein_bl" not in (
        portfolio_backtest.DEFAULT_BACKTEST_MODELS
    )
    records = [
        record
        for record in result["rebalance_records"]
        if record["model"] == "james_stein_bl"
    ]
    assert records
    assert all(
        record["mean_estimator"]["estimator"]
        == "jorion_bayes_stein"
        for record in records
    )
    assert all(
        0.0 <= record["mean_estimator"]["shrinkage_intensity"] <= 1.0
        for record in records
    )


def test_hac_historical_uncertainty_uses_only_training_rows():
    prices = _synthetic_factor_research_data(
        rows=580,
        ticker_count=8,
    )[0]
    cutoff = 503
    changed = prices.copy()
    changed.iloc[cutoff + 1:] *= np.linspace(
        1.0,
        50.0,
        len(changed) - cutoff - 1,
    )[:, None]

    views, uncertainties, diagnostics = (
        portfolio_optimization
        ._historical_returns_with_hac_uncertainty(
            prices.iloc[:cutoff + 1]
        )
    )
    repeated_views, repeated_uncertainties, repeated_diagnostics = (
        portfolio_optimization
        ._historical_returns_with_hac_uncertainty(
            changed.iloc[:cutoff + 1]
        )
    )

    pd.testing.assert_series_equal(views, repeated_views)
    pd.testing.assert_series_equal(
        uncertainties,
        repeated_uncertainties,
    )
    assert diagnostics == repeated_diagnostics
    assert uncertainties.between(1e-4, 5.0).all()


def test_hac_uncertainty_reflects_positive_return_autocorrelation():
    rng = np.random.default_rng(123)
    innovations = rng.normal(0.0, 0.008, 600)
    returns = np.zeros_like(innovations)
    for index in range(1, len(returns)):
        returns[index] = 0.75 * returns[index - 1] + innovations[index]
    dates = pd.date_range("2018-01-02", periods=len(returns), freq="B")
    prices = pd.DataFrame(
        {"AAA": 100.0 * np.cumprod(1.0 + returns)},
        index=dates,
    )

    _, uncertainties, diagnostics = (
        portfolio_optimization
        ._historical_returns_with_hac_uncertainty(prices)
    )

    ticker = diagnostics["ticker_diagnostics"]["AAA"]
    assert ticker["lag_count"] > 0
    assert ticker["annual_standard_error"] > (
        ticker["annual_naive_standard_error"]
    )
    assert uncertainties["AAA"] == pytest.approx(
        ticker["annual_standard_error"]
    )


def test_hac_historical_bl_is_research_only_and_auditable():
    prices = _synthetic_factor_research_data(
        rows=520,
        ticker_count=8,
    )[0]

    result = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("historical_bl", "hac_historical_bl"),
        train_window=504,
        rebalance_frequency=8,
        forecast_horizon=8,
        max_asset_weight=0.25,
    )

    assert "hac_historical_bl" in (
        portfolio_backtest.SUPPORTED_BACKTEST_MODELS
    )
    assert "hac_historical_bl" not in (
        portfolio_backtest.DEFAULT_BACKTEST_MODELS
    )
    records = [
        record
        for record in result["rebalance_records"]
        if record["model"] == "hac_historical_bl"
    ]
    assert records
    assert all(
        record["uncertainty_estimator"]["estimator"]
        == "newey_west_hac_mean_standard_error"
        for record in records
    )


def test_lightweight_rank_tilt_ignores_future_rows_and_hits_active_share():
    prices = _synthetic_factor_research_data(
        rows=580,
        ticker_count=8,
    )[0]
    cutoff = 519
    weights, diagnostics = (
        portfolio_backtest._lightweight_rank_tilt_weights(
            prices.iloc[:cutoff + 1],
            63,
            0.25,
        )
    )
    mutated = prices.copy()
    mutated.iloc[cutoff + 1:] *= np.linspace(
        1.0,
        20.0,
        len(mutated) - cutoff - 1,
    )[:, None]
    repeated, repeated_diagnostics = (
        portfolio_backtest._lightweight_rank_tilt_weights(
            mutated.iloc[:cutoff + 1],
            63,
            0.25,
        )
    )

    assert weights == pytest.approx(repeated)
    assert diagnostics["signal_scores"] == pytest.approx(
        repeated_diagnostics["signal_scores"]
    )
    assert sum(weights.values()) == pytest.approx(1.0)
    assert max(weights.values()) <= 0.250001
    equal_weight = 1.0 / len(weights)
    active_share = 0.5 * sum(
        abs(weight - equal_weight)
        for weight in weights.values()
    )
    assert active_share == pytest.approx(
        portfolio_backtest.LIGHTWEIGHT_RANK_TARGET_ACTIVE_SHARE
    )


def test_completed_forecast_targets_respect_training_cutoff():
    prices, factors = _synthetic_factor_research_data(rows=360)
    cutoff = prices.index[299]
    future_changed = prices.copy()
    future_changed.loc[future_changed.index > cutoff] *= 100.0

    relative = build_completed_forward_targets(
        prices,
        horizon=21,
        target_kind="relative",
        training_end=cutoff,
    )
    changed = build_completed_forward_targets(
        future_changed,
        horizon=21,
        target_kind="relative",
        training_end=cutoff,
    )
    residual = build_completed_forward_targets(
        prices,
        horizon=21,
        target_kind="factor_residual",
        training_end=cutoff,
        point_in_time_features=factors,
    )

    pd.testing.assert_frame_equal(relative, changed)
    assert not relative.empty
    assert not residual.empty
    assert relative["forward_end_date"].max() <= cutoff
    assert residual["forward_end_date"].max() <= cutoff
    assert relative.groupby("as_of_date")["target"].median().abs().max() < 1e-12


def test_optimizer_maps_no_view_to_prior_only_expected_return(monkeypatch):
    captured = {}
    pipeline_result = {
        "mu": pd.Series({"AAA": 0.0, "BBB": 0.20}),
        "prior_mu": pd.Series({"AAA": 0.11, "BBB": 0.04}),
        "S": pd.DataFrame(
            [[0.04, 0.005], [0.005, 0.03]],
            index=["AAA", "BBB"],
            columns=["AAA", "BBB"],
        ),
        "uncertainties": pd.Series({"AAA": portfolio_optimization.MAX_FORECAST_UNCERTAINTY, "BBB": 0.20}),
        "no_view_tickers": ["AAA"],
        "tickers": ["AAA", "BBB"],
        "latest_prices": {"AAA": 100.0, "BBB": 80.0},
    }

    class FakeEfficientFrontier:
        def __init__(self, mu, S, weight_bounds=None):
            captured["mu"] = mu.copy()

        def add_objective(self, *args, **kwargs):
            pass

        def max_sharpe(self, risk_free_rate=0.0):
            pass

        def efficient_return(self, target_return):
            pass

        def clean_weights(self):
            return {"AAA": 0.5, "BBB": 0.5}

        def portfolio_performance(self, risk_free_rate=0.0):
            return (0.08, 0.16, 0.4)

    monkeypatch.setattr(portfolio_optimization, "data_and_forecast_pipeline", lambda *args, **kwargs: pipeline_result)
    monkeypatch.setattr(portfolio_optimization, "EfficientFrontier", FakeEfficientFrontier)
    monkeypatch.setattr(portfolio_optimization, "get_asset_names", lambda tickers: {ticker: ticker for ticker in tickers})

    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=["AAA", "BBB"],
        optimization_method="MPT",
        forecast_method="ARIMA_TRANSFORMER",
    )

    assert captured["mu"]["AAA"] == pytest.approx(0.11)
    assert result["no_view_tickers"] == ["AAA"]
    assert result["failed_forecast_count"] == 1
    assert result["return_confidence"]["AAA"] == pytest.approx(portfolio_optimization.MIN_FORECAST_CONFIDENCE)


def test_optimizer_min_variance_bypasses_forecast_and_uses_ledoit_gmv(
    monkeypatch,
):
    captured = {"forecast_method": None, "min_volatility_calls": 0}
    tickers = ["AAA", "BBB"]
    pipeline_result = {
        "mu": pd.Series({"AAA": 0.10, "BBB": 0.08}),
        "prior_mu": pd.Series({"AAA": 0.09, "BBB": 0.07}),
        "S": pd.DataFrame(
            [[0.04, 0.005], [0.005, 0.03]],
            index=tickers,
            columns=tickers,
        ),
        "uncertainties": pd.Series({"AAA": 0.20, "BBB": 0.20}),
        "no_view_tickers": [],
        "tickers": tickers,
        "latest_prices": {"AAA": 100.0, "BBB": 80.0},
    }

    def fake_pipeline(*args, **kwargs):
        captured["forecast_method"] = args[4]
        return pipeline_result

    class FakeEfficientFrontier:
        def __init__(self, mu, covariance, weight_bounds=None):
            captured["mu"] = mu.copy()
            captured["covariance"] = covariance.copy()

        def add_objective(self, *args, **kwargs):
            pass

        def min_volatility(self):
            captured["min_volatility_calls"] += 1

        def max_sharpe(self, risk_free_rate=0.0):
            raise AssertionError("Risk-only default must not maximize Sharpe")

        def clean_weights(self):
            return {"AAA": 0.40, "BBB": 0.60}

    monkeypatch.setattr(
        portfolio_optimization,
        "data_and_forecast_pipeline",
        fake_pipeline,
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "EfficientFrontier",
        FakeEfficientFrontier,
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "get_asset_names",
        lambda selected: {ticker: ticker for ticker in selected},
    )

    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=tickers,
        forecast_method="TRANSFORMER",
        max_asset_weight=1.0,
    )

    assert captured["forecast_method"] == "RISK_ONLY"
    assert captured["min_volatility_calls"] == 1
    assert result["weights"] == pytest.approx(
        {"AAA": 0.40, "BBB": 0.60}
    )
    assert result["optimization_method"] == "MIN_VARIANCE"
    assert result["forecast_method_requested"] == "TRANSFORMER"
    assert result["forecast_method_effective"] == "RISK_ONLY"
    assert result["forecast_bypassed"] is True
    assert result["expected_return_role"] == (
        "historical_diagnostic_not_optimization_input"
    )
    assert result["optimizer_controls"]["solver_objective"] == (
        "ledoit_wolf_minimum_variance"
    )


def test_optimizer_min_variance_rejects_return_or_risk_target():
    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=["AAA", "BBB"],
        optimization_method="MIN_VARIANCE",
        target_return=0.08,
    )

    assert "global minimum variance" in result["error"]


def test_optimizer_min_holding_output_preserves_asset_cap(monkeypatch):
    tickers = ["AAA", "BBB", "CCC"]
    pipeline_result = {
        "mu": pd.Series(
            {"AAA": 0.10, "BBB": 0.08, "CCC": 0.06}
        ),
        "prior_mu": pd.Series(
            {"AAA": 0.09, "BBB": 0.07, "CCC": 0.05}
        ),
        "S": pd.DataFrame(
            np.diag([0.04, 0.03, 0.02]),
            index=tickers,
            columns=tickers,
        ),
        "uncertainties": pd.Series(
            {"AAA": 0.20, "BBB": 0.20, "CCC": 0.20}
        ),
        "no_view_tickers": [],
        "tickers": tickers,
        "latest_prices": {"AAA": 100.0, "BBB": 80.0, "CCC": 60.0},
    }

    class FakeEfficientFrontier:
        def __init__(self, mu, S, weight_bounds=None):
            pass

        def add_objective(self, *args, **kwargs):
            pass

        def max_sharpe(self, risk_free_rate=0.0):
            pass

        def clean_weights(self):
            return {"AAA": 0.60, "BBB": 0.36, "CCC": 0.04}

    monkeypatch.setattr(
        portfolio_optimization,
        "data_and_forecast_pipeline",
        lambda *args, **kwargs: pipeline_result,
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "EfficientFrontier",
        FakeEfficientFrontier,
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "get_asset_names",
        lambda selected: {ticker: ticker for ticker in selected},
    )

    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=tickers,
        optimization_method="MPT",
        forecast_method="LIGHTWEIGHT",
        max_asset_weight=0.60,
        min_holding_weight=0.05,
    )

    assert result["weights"] == pytest.approx(
        {"AAA": 0.60, "BBB": 0.40}
    )
    assert sum(result["weights"].values()) == pytest.approx(1.0)
    assert max(result["weights"].values()) <= 0.600000001
    assert result["optimizer_controls"][
        "effective_max_asset_weight"
    ] == pytest.approx(0.60)

    controlled = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=tickers,
        optimization_method="MPT",
        forecast_method="LIGHTWEIGHT",
        max_asset_weight=0.60,
        min_holding_weight=0.05,
        current_weights={"AAA": 0.20, "BBB": 0.20},
        rebalance_band=0.0,
        max_turnover=0.20,
    )

    controlled_weights = pd.Series(controlled["weights"], dtype=float)
    optimizer_mu = pd.Series(
        controlled["optimizer_expected_returns"],
        dtype=float,
    )
    expected_return = float(
        controlled_weights.reindex(tickers).fillna(0.0) @ optimizer_mu
        + controlled["cash_weight"] * 0.02
    )
    expected_risk = float(
        np.sqrt(
            controlled_weights["AAA"] ** 2 * 0.04
            + controlled_weights["BBB"] ** 2 * 0.03
        )
    )
    assert controlled_weights.sum() == pytest.approx(0.60)
    assert controlled["risky_exposure"] == pytest.approx(0.60)
    assert controlled["cash_weight"] == pytest.approx(0.40)
    assert controlled["controlled_cash_weight"] == pytest.approx(0.40)
    assert controlled["performance_coverage"] == pytest.approx(1.0)
    assert controlled["performance_status"] == "complete"
    assert controlled["unmodeled_weights"] == {}
    assert controlled["return"] == pytest.approx(expected_return)
    assert controlled["risk"] == pytest.approx(expected_risk)

    unmodeled = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=tickers,
        optimization_method="MPT",
        forecast_method="LIGHTWEIGHT",
        max_asset_weight=0.60,
        min_holding_weight=0.05,
        current_weights={
            "AAA": 0.10,
            "BBB": 0.10,
            "OLD": 0.80,
        },
        rebalance_band=0.0,
        max_turnover=0.20,
    )

    assert unmodeled["weights"] == pytest.approx(
        {"AAA": 0.1625, "BBB": 0.1375, "OLD": 0.70}
    )
    assert unmodeled["risky_exposure"] == pytest.approx(1.0)
    assert unmodeled["cash_weight"] == pytest.approx(0.0)
    assert unmodeled["modeled_risky_exposure"] == pytest.approx(0.30)
    assert unmodeled["unmodeled_risky_exposure"] == pytest.approx(0.70)
    assert unmodeled["unmodeled_weights"] == pytest.approx(
        {"OLD": 0.70}
    )
    assert unmodeled["performance_coverage"] == pytest.approx(0.30)
    assert unmodeled["performance_status"] == (
        "unavailable_unmodeled_exposure"
    )
    assert unmodeled["return"] is None
    assert unmodeled["risk"] is None
    assert unmodeled["sharpe_ratio"] is None
    assert unmodeled["performance_warning"]


def test_optimizer_adds_turnover_penalty_objective_when_current_weights_exist(monkeypatch):
    captured = {"objectives": []}
    pipeline_result = {
        "mu": pd.Series({"AAA": 0.10, "BBB": 0.08}),
        "prior_mu": pd.Series({"AAA": 0.09, "BBB": 0.07}),
        "S": pd.DataFrame(
            [[0.04, 0.005], [0.005, 0.03]],
            index=["AAA", "BBB"],
            columns=["AAA", "BBB"],
        ),
        "uncertainties": pd.Series({"AAA": 0.20, "BBB": 0.20}),
        "no_view_tickers": [],
        "tickers": ["AAA", "BBB"],
        "latest_prices": {"AAA": 100.0, "BBB": 80.0},
    }

    class FakeEfficientFrontier:
        def __init__(self, mu, S, weight_bounds=None):
            pass

        def add_objective(self, func, **kwargs):
            captured["objectives"].append((func, kwargs))

        def max_sharpe(self, risk_free_rate=0.0):
            pass

        def efficient_return(self, target_return):
            pass

        def clean_weights(self):
            return {"AAA": 0.5, "BBB": 0.5}

        def portfolio_performance(self, risk_free_rate=0.0):
            return (0.08, 0.16, 0.4)

    monkeypatch.setattr(portfolio_optimization, "data_and_forecast_pipeline", lambda *args, **kwargs: pipeline_result)
    monkeypatch.setattr(portfolio_optimization, "EfficientFrontier", FakeEfficientFrontier)
    monkeypatch.setattr(portfolio_optimization, "get_asset_names", lambda tickers: {ticker: ticker for ticker in tickers})

    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=["AAA", "BBB"],
        optimization_method="MPT",
        forecast_method="LIGHTWEIGHT",
        current_weights={"AAA": 0.80, "BBB": 0.20},
        turnover_penalty=0.15,
    )

    penalty_objectives = [
        kwargs for _, kwargs in captured["objectives"]
        if kwargs.get("gamma") == pytest.approx(0.15)
    ]
    assert penalty_objectives
    assert penalty_objectives[0]["current_weights"].tolist() == pytest.approx([0.8, 0.2])
    assert result["optimizer_controls"]["turnover_penalty"] == pytest.approx(0.15)
    assert result["optimizer_controls"]["solver_objective"] == (
        "regularized_max_sharpe_grid"
    )


def test_turnover_and_transaction_cost_math():
    turnover, cost = portfolio_backtest.calculate_turnover_and_cost(
        {"AAA": 500.0, "BBB": 500.0},
        {"AAA": 0.60, "BBB": 0.40},
        portfolio_value=1000.0,
        transaction_cost_bps=10.0,
    )

    assert turnover == pytest.approx(0.20)
    assert cost == pytest.approx(0.20)


def test_transaction_cost_funding_reduces_only_buy_orders():
    target, cost, investable, cash, diagnostics = (
        portfolio_backtest._fund_transaction_cost(
            {"AAA": 500.0, "BBB": 500.0},
            {"AAA": 600.0, "BBB": 400.0},
            portfolio_value=1000.0,
            transaction_cost_bps=100.0,
        )
    )

    assert target["AAA"] == pytest.approx(598.01980198)
    assert target["BBB"] == pytest.approx(400.0)
    assert cost == pytest.approx(1.98019802)
    assert investable == pytest.approx(target.sum())
    assert cash == pytest.approx(0.0)
    assert diagnostics["pre_cost_controlled_trade_value"] == pytest.approx(
        200.0
    )
    assert diagnostics["controlled_trade_value"] == pytest.approx(
        198.01980198
    )
    assert diagnostics["transaction_cost_funding_buy_reduction"] == (
        pytest.approx(1.98019802)
    )
    assert cost == pytest.approx(
        diagnostics["controlled_trade_value"] * 0.01
    )


def test_transaction_cost_funding_uses_existing_cash_first():
    target, cost, investable, cash, diagnostics = (
        portfolio_backtest._fund_transaction_cost(
            {"AAA": 500.0, "BBB": 500.0},
            {"AAA": 550.0, "BBB": 400.0},
            portfolio_value=1000.0,
            transaction_cost_bps=100.0,
        )
    )

    assert target.to_dict() == pytest.approx(
        {"AAA": 550.0, "BBB": 400.0}
    )
    assert cost == pytest.approx(1.5)
    assert investable == pytest.approx(998.5)
    assert cash == pytest.approx(48.5)
    assert diagnostics["transaction_cost_funding_buy_reduction"] == 0.0
    assert diagnostics["cash_before_transaction_cost"] == pytest.approx(50.0)
    assert diagnostics["cash_after_transaction_cost"] == pytest.approx(48.5)


def test_gross_period_return_values_the_costless_target_path():
    dates = pd.date_range("2024-01-02", periods=6, freq="B")
    prices = pd.DataFrame(
        {
            "AAA": [100.0, 100.0, 100.0, 100.0, 150.0, 200.0],
            "BBB": [100.0, 100.0, 100.0, 100.0, 150.0, 200.0],
        },
        index=dates,
    )

    result = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("equal_weight",),
        train_window=3,
        rebalance_frequency=2,
        forecast_horizon=1,
        transaction_cost_bps=1000.0,
        risk_free_rate=0.0,
        rebalance_band=0.0,
        max_turnover=1.0,
    )

    record = result["rebalance_records"][0]
    metrics = result["summary_by_model"]["equal_weight"]
    assert record["gross_period_end_value"] == pytest.approx(20000.0)
    assert record["net_period_end_value"] == pytest.approx(
        18181.8181818
    )
    assert record["gross_period_return"] == pytest.approx(1.0)
    assert record["net_period_return"] == pytest.approx(0.81818181818)
    assert record["transaction_cost_return_drag"] == pytest.approx(
        0.18181818182
    )
    assert metrics["gross_cumulative_return"] == pytest.approx(1.0)
    assert metrics["net_cumulative_return"] == pytest.approx(0.81818181818)


def test_primary_metrics_include_initial_allocation_cost():
    dates = pd.date_range("2024-01-02", periods=6, freq="B")
    prices = pd.DataFrame(
        {
            "AAA": np.full(6, 100.0),
            "BBB": np.full(6, 100.0),
        },
        index=dates,
    )

    result = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("equal_weight",),
        train_window=3,
        rebalance_frequency=2,
        forecast_horizon=1,
        transaction_cost_bps=1000.0,
        risk_free_rate=0.0,
        rebalance_band=0.0,
        max_turnover=1.0,
        initial_value=10000.0,
    )

    metrics = result["summary_by_model"]["equal_weight"]
    expected_net_return = 9090.9090909 / 10000.0 - 1.0
    expected_cagr = (
        (1.0 + expected_net_return)
        ** (portfolio_backtest.TRADING_DAYS_PER_YEAR / 2.0)
        - 1.0
    )
    assert metrics["final_value"] == pytest.approx(9090.9090909)
    assert metrics["net_cumulative_return"] == pytest.approx(
        expected_net_return
    )
    assert metrics["cagr"] == pytest.approx(expected_cagr)
    assert metrics["max_drawdown"] == pytest.approx(expected_net_return)
    assert metrics["annual_volatility"] > 0.0


def test_inverse_vol_risk_parity_weights_sum_cap_and_prefer_lower_vol():
    dates = pd.date_range("2024-01-02", periods=80, freq="B")
    x = np.arange(len(dates))
    prices = pd.DataFrame(
        {
            "LOW": 100.0 * np.exp(0.0004 * x + 0.002 * np.sin(x / 4.0)),
            "MID": 100.0 * np.exp(0.0004 * x + 0.010 * np.sin(x / 3.0)),
            "HIGH": 100.0 * np.exp(0.0004 * x + 0.030 * np.sin(x / 2.0)),
        },
        index=dates,
    )

    weights = risk_parity(prices, max_asset_weight=0.60)

    assert weights.sum() == pytest.approx(1.0)
    assert weights.max() <= 0.600001
    assert weights["LOW"] > weights["HIGH"]


def test_momentum_12_1_excludes_most_recent_month():
    dates = pd.date_range("2024-01-02", periods=260, freq="B")
    aaa = np.linspace(100.0, 220.0, 260)
    bbb = np.full(260, 100.0)
    aaa[-21:] = np.linspace(220.0, 40.0, 21)
    prices = pd.DataFrame({"AAA": aaa, "BBB": bbb}, index=dates)

    scores = momentum_12_1(prices)
    short_scores = momentum_12_1(prices.iloc[-120:])

    assert scores["AAA"] > scores["BBB"]
    assert short_scores.isna().all()


def test_six_month_momentum_low_vol_and_drawdown_scores_rank_cross_sectionally():
    dates = pd.date_range("2024-01-02", periods=150, freq="B")
    x = np.arange(len(dates))
    prices = pd.DataFrame(
        {
            "MOM": 100.0 * np.exp(0.0020 * x),
            "CALM": 100.0 * np.exp(0.0005 * x + 0.002 * np.sin(x / 8.0)),
            "VOL": 100.0 * np.exp(0.0005 * x + 0.050 * np.sin(x / 2.0)),
        },
        index=dates,
    )
    prices.loc[dates[-20:], "VOL"] *= np.linspace(1.0, 0.65, 20)

    momentum_scores = momentum_6m(prices)
    vol_scores = volatility_score(prices)
    dd_scores = drawdown_score(prices)

    assert momentum_scores["MOM"] > momentum_scores["CALM"]
    assert vol_scores["CALM"] > vol_scores["VOL"]
    assert dd_scores["CALM"] > dd_scores["VOL"]


def test_dual_horizon_momentum_blends_fixed_ranks_and_respects_cap():
    dates = pd.date_range("2023-01-02", periods=280, freq="B")
    x = np.arange(len(dates))
    prices = pd.DataFrame(
        {
            "STEADY": 100.0 * np.exp(0.0010 * x),
            "REVERSAL": np.r_[
                100.0 * np.exp(0.0020 * x[:-21]),
                np.linspace(165.0, 90.0, 21),
            ],
            "FLAT": np.full(len(dates), 100.0),
        },
        index=dates,
    )

    weights = dual_horizon_momentum_weights(
        prices,
        max_asset_weight=0.50,
    )

    assert weights.sum() == pytest.approx(1.0)
    assert (weights >= 0.0).all()
    assert weights.max() <= 0.50 + 1e-12
    assert weights["STEADY"] > weights["REVERSAL"]


def test_dual_horizon_momentum_uses_only_supplied_history():
    prices = _synthetic_prices(300)

    first = dual_horizon_momentum_weights(prices.iloc[:280])
    mutated = prices.copy()
    mutated.iloc[280:] *= pd.Series(
        {"AAA": 0.25, "BBB": 3.0, "CCC": 2.0}
    )
    second = dual_horizon_momentum_weights(mutated.iloc[:280])

    pd.testing.assert_series_equal(first, second)


def test_profitability_momentum_blends_pit_rank_without_lookahead():
    dates = pd.date_range("2020-01-02", periods=300, freq="B")
    x = np.arange(len(dates))
    prices = pd.DataFrame(
        {
            "LOW": 100.0 * np.exp(0.0006 * x),
            "MID": 100.0 * np.exp(0.0006 * x),
            "HIGH": 100.0 * np.exp(0.0006 * x),
        },
        index=dates,
    )
    profitability = {"LOW": 1.0, "MID": 3.0, "HIGH": 5.0}

    scores = profitability_momentum_scores(
        prices.iloc[:280],
        profitability,
    )
    mutated = prices.copy()
    mutated.iloc[280:] *= pd.Series(
        {"LOW": 4.0, "MID": 0.5, "HIGH": 0.25}
    )
    repeated = profitability_momentum_scores(
        mutated.iloc[:280],
        profitability,
    )

    assert scores["HIGH"] > scores["MID"] > scores["LOW"]
    pd.testing.assert_series_equal(scores, repeated)


def test_adaptive_factor_momentum_uses_only_completed_pit_rows():
    dates = pd.date_range("2018-01-02", periods=520, freq="B")
    x = np.arange(len(dates))
    tickers = ["A", "B", "C", "D", "E"]
    prices = pd.DataFrame(
        {
            ticker: 100.0 * np.exp(
                (0.0002 + index * 0.00015) * x
                + 0.01 * np.sin(x / (8.0 + index))
            )
            for index, ticker in enumerate(tickers)
        },
        index=dates,
    )
    value = pd.DataFrame(
        np.tile(np.arange(1.0, 6.0), (len(dates), 1)),
        index=dates,
        columns=tickers,
    )
    investment = pd.DataFrame(
        np.tile(np.arange(5.0, 0.0, -1.0), (len(dates), 1)),
        index=dates,
        columns=tickers,
    )

    scores, diagnostics = adaptive_factor_momentum_scores(
        prices.iloc[:480],
        {
            "value": value,
            "conservative_investment": investment,
        },
    )
    mutated_prices = prices.copy()
    mutated_prices.iloc[480:] *= pd.Series(
        {"A": 4.0, "B": 3.0, "C": 2.0, "D": 0.5, "E": 0.25}
    )
    mutated_value = value.copy()
    mutated_value.iloc[480:] = mutated_value.iloc[480:].iloc[:, ::-1].to_numpy()
    repeated, repeated_diagnostics = adaptive_factor_momentum_scores(
        mutated_prices.iloc[:480],
        {
            "value": mutated_value,
            "conservative_investment": investment,
        },
    )

    pd.testing.assert_series_equal(scores, repeated)
    assert sum(diagnostics["component_weights"].values()) == pytest.approx(1.0)
    assert max(diagnostics["component_weights"].values()) <= 0.600001
    assert diagnostics["component_weights"] == pytest.approx(
        repeated_diagnostics["component_weights"]
    )
    assert all(
        pd.Timestamp(row["forward_end_date"]) <= prices.index[479]
        for row in diagnostics["calibration_rows"]
    )


def test_factor_residual_momentum_removes_common_factor_and_has_no_lookahead():
    rng = np.random.default_rng(123)
    dates = pd.date_range("2010-01-04", periods=620, freq="B")
    factors = pd.DataFrame(
        {
            "mkt_rf": rng.normal(0.0003, 0.010, len(dates)),
            "smb": rng.normal(0.0001, 0.005, len(dates)),
            "hml": rng.normal(0.0001, 0.005, len(dates)),
            "rf_daily": np.full(len(dates), 0.00005),
        },
        index=dates,
    )
    residual_trends = {
        "POS": 0.0008,
        "FLAT": 0.0,
        "NEG": -0.0008,
    }
    prices = {}
    for ticker, residual_trend in residual_trends.items():
        changing_residual = np.zeros(len(dates))
        changing_residual[300:] = residual_trend
        returns = (
            factors["rf_daily"]
            + factors["mkt_rf"]
            + 0.4 * factors["smb"]
            - 0.2 * factors["hml"]
            + changing_residual
            + rng.normal(0.0, 0.002, len(dates))
        )
        prices[ticker] = 100.0 * np.exp(
            np.cumsum(np.log1p(returns))
        )
    prices = pd.DataFrame(prices, index=dates)

    scores, diagnostics = factor_residual_momentum_scores(
        prices.iloc[:580],
        factors.iloc[:580],
    )
    mutated = prices.copy()
    mutated.iloc[580:] *= pd.Series(
        {"POS": 0.25, "FLAT": 2.0, "NEG": 4.0}
    )
    repeated, _ = factor_residual_momentum_scores(
        mutated.iloc[:580],
        factors.iloc[:580],
    )

    assert scores["POS"] > scores["FLAT"] > scores["NEG"]
    assert diagnostics["coverage_count"] == 3
    assert diagnostics["beta_lookback"] == 504
    pd.testing.assert_series_equal(scores, repeated)


def test_short_term_reversal_prefers_recent_relative_loser():
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    prices = pd.DataFrame(
        {
            "LOSER": np.linspace(100.0, 80.0, len(dates)),
            "FLAT": np.full(len(dates), 100.0),
            "WINNER": np.linspace(100.0, 120.0, len(dates)),
        },
        index=dates,
    )

    scores = short_term_reversal_score(prices)

    assert scores["LOSER"] > scores["FLAT"] > scores["WINNER"]


def test_adaptive_alpha_calibration_uses_completed_training_windows_only():
    prices = _synthetic_prices(360)

    calibration = calibrate_cross_sectional_alpha(
        prices,
        horizon=21,
        max_observations=4,
    )
    scores, diagnostics = adaptive_cross_sectional_alpha(prices, horizon=21)

    assert calibration["rows"]
    assert len(calibration["rows"]) <= 4
    assert all(
        pd.Timestamp(row["as_of_date"]) < pd.Timestamp(row["forward_end_date"])
        <= prices.index[-1]
        for row in calibration["rows"]
    )
    assert sum(calibration["weights"].values()) == pytest.approx(1.0)
    assert diagnostics["coverage_rate"] == pytest.approx(1.0)
    assert scores.notna().all()


def test_point_in_time_snapshot_never_uses_future_rows():
    prices, factors = _synthetic_factor_research_data(rows=180)
    as_of = prices.index[80]
    future = factors.iloc[:8].copy()
    future["available_date"] = prices.index[-1] + pd.Timedelta(days=30)
    future["quality"] = 9999.0

    baseline = point_in_time_snapshot(factors, as_of, tickers=prices.columns)
    with_future = point_in_time_snapshot(
        pd.concat([factors, future], ignore_index=True),
        as_of,
        tickers=prices.columns,
    )

    pd.testing.assert_frame_equal(baseline, with_future)
    assert (baseline["available_date"] <= as_of).all()


def test_regularized_alpha_caps_single_feature_concentration():
    index = pd.RangeIndex(80)
    features = pd.DataFrame({
        "quality": np.linspace(-1.0, 1.0, len(index)),
        "profitability": np.sin(np.arange(len(index))),
        "valuation": np.cos(np.arange(len(index))),
        "liquidity": np.sin(np.arange(len(index)) / 3.0),
    }, index=index)
    targets = features["quality"] * 10.0 + features["profitability"] * 0.01

    coefficients, diagnostics = fit_regularized_alpha(
        features,
        targets,
        ridge_penalty=1.0,
        max_feature_weight=0.45,
        minimum_observations=40,
    )

    assert coefficients.abs().sum() == pytest.approx(1.0)
    assert coefficients.abs().max() <= 0.450001
    assert diagnostics["observation_count"] == 80


def test_factor_neutral_alpha_ignores_unavailable_future_fundamentals():
    prices, factors = _synthetic_factor_research_data()
    baseline_scores, baseline_diagnostics = factor_neutral_cross_sectional_alpha(
        prices,
        factors,
        horizon=42,
        minimum_observations=32,
    )
    future = factors.iloc[:8].copy()
    future["available_date"] = prices.index[-1] + pd.Timedelta(days=30)
    future["quality"] = -9999.0
    future["valuation"] = 9999.0
    future_scores, future_diagnostics = factor_neutral_cross_sectional_alpha(
        prices,
        pd.concat([factors, future], ignore_index=True),
        horizon=42,
        minimum_observations=32,
    )

    pd.testing.assert_series_equal(baseline_scores, future_scores)
    assert baseline_diagnostics["component_weights"] == pytest.approx(
        future_diagnostics["component_weights"]
    )
    assert all(
        pd.Timestamp(row["latest_available_date"])
        <= pd.Timestamp(row["as_of_date"])
        for row in baseline_diagnostics["calibration"]["rows"]
    )
    assert abs(sum(
        abs(value)
        for value in baseline_diagnostics["component_weights"].values()
    ) - 1.0) < 1e-9


def test_factor_neutral_backtest_requires_point_in_time_data():
    prices, _ = _synthetic_factor_research_data(rows=180)

    with pytest.raises(ValueError, match="requires point_in_time_features"):
        portfolio_backtest.run_portfolio_model_backtest(
            prices,
            models=("factor_neutral_alpha_tilt",),
            train_window=126,
            rebalance_frequency=21,
            forecast_horizon=21,
        )


def test_factor_neutral_backtest_runs_with_point_in_time_data():
    prices, factors = _synthetic_factor_research_data()

    result = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("factor_neutral_alpha_tilt",),
        train_window=420,
        rebalance_frequency=42,
        forecast_horizon=42,
        point_in_time_features=factors,
    )

    metrics = result["summary_by_model"]["factor_neutral_alpha_tilt"]
    records = [
        record
        for record in result["rebalance_records"]
        if record["model"] == "factor_neutral_alpha_tilt"
    ]
    assert records
    assert metrics["signal_rank_ic_count"] > 0
    assert all(
        pd.Timestamp(record["alpha_calibration"]["rows"][-1]["forward_end_date"])
        <= pd.Timestamp(record["train_end_date"])
        for record in records
    )


def test_signal_tilt_weights_target_explicit_active_share():
    weights = signal_tilt_weights(
        {"LOW": -1.0, "MID": 0.0, "HIGH": 1.0},
        max_asset_weight=0.80,
        target_active_share=0.20,
    )
    equal = pd.Series(1 / 3, index=weights.index)

    assert weights.sum() == pytest.approx(1.0)
    assert weights["HIGH"] > weights["MID"] > weights["LOW"]
    assert 0.15 <= 0.5 * float((weights - equal).abs().sum()) <= 0.200001


def test_market_cap_weight_uses_caps_when_available_and_empty_when_not():
    weights = market_cap_weight({"AAA": 100.0, "BBB": 300.0}, tickers=["AAA", "BBB"], max_asset_weight=0.80)
    missing = market_cap_weight({}, tickers=["AAA", "BBB"], max_asset_weight=0.80)

    assert weights.sum() == pytest.approx(1.0)
    assert weights["BBB"] > weights["AAA"]
    assert missing.sum() == pytest.approx(0.0)


def test_signal_stack_views_are_weak_prior_adjustments():
    prices = _synthetic_prices(280)
    prior = pd.Series({"AAA": 0.05, "BBB": 0.05, "CCC": 0.05})

    views = signal_stack_bl_views(prices, prior_returns=prior)

    assert set(views.index) == {"AAA", "BBB", "CCC"}
    assert float(views.sub(prior).abs().max()) <= 0.070001


def test_turnover_band_skips_small_trades():
    controlled, diagnostics = portfolio_optimization.apply_trade_controls(
        {"AAA": 500.0, "BBB": 500.0},
        {"AAA": 510.0, "BBB": 490.0},
        portfolio_value=1000.0,
        rebalance_band=0.02,
        max_turnover=None,
    )

    assert diagnostics["skipped_trade_count"] == 2
    assert diagnostics["controlled_turnover"] == 0.0
    assert controlled["AAA"] == pytest.approx(500.0)
    assert controlled["BBB"] == pytest.approx(500.0)


def test_turnover_band_preserves_target_cash_exposure():
    controlled, diagnostics = portfolio_optimization.apply_trade_controls(
        {"AAA": 400.0, "BBB": 300.0, "CCC": 300.0},
        {"AAA": 430.0, "BBB": 285.0, "CCC": 285.0},
        portfolio_value=1000.0,
        rebalance_band=0.02,
        max_turnover=None,
    )

    assert controlled.sum() == pytest.approx(1000.0)
    assert diagnostics["desired_net_trade_value"] == pytest.approx(0.0)
    assert diagnostics["post_control_net_trade_value"] == pytest.approx(0.0)
    assert diagnostics["band_reintroduced_trade_count"] == 2
    assert diagnostics["skipped_trade_count"] == 0


def test_max_turnover_scales_trades_to_cap():
    controlled, diagnostics = portfolio_optimization.apply_trade_controls(
        {"AAA": 500.0, "BBB": 500.0},
        {"AAA": 1000.0, "BBB": 0.0},
        portfolio_value=1000.0,
        rebalance_band=0.0,
        max_turnover=0.20,
    )

    assert diagnostics["turnover"] == pytest.approx(1.0)
    assert diagnostics["controlled_turnover"] == pytest.approx(0.20)
    assert diagnostics["turnover_cap_hit"] is True
    assert controlled["AAA"] == pytest.approx(600.0)
    assert controlled["BBB"] == pytest.approx(400.0)


def test_min_holding_threshold_drops_small_weights_when_feasible():
    filtered = portfolio_optimization.apply_min_holding_threshold(
        {"AAA": 0.90, "BBB": 0.06, "CCC": 0.04},
        min_holding_weight=0.05,
    )

    assert filtered["CCC"] == pytest.approx(0.0)
    assert filtered["AAA"] + filtered["BBB"] == pytest.approx(1.0)


def test_min_holding_threshold_preserves_max_asset_weight():
    filtered = portfolio_optimization.apply_min_holding_threshold(
        {"AAA": 0.60, "BBB": 0.36, "CCC": 0.04},
        min_holding_weight=0.05,
        max_asset_weight=0.60,
    )

    assert filtered == pytest.approx(
        {"AAA": 0.60, "BBB": 0.40, "CCC": 0.0}
    )
    assert sum(filtered.values()) == pytest.approx(1.0)
    assert max(filtered.values()) <= 0.600000001


def test_min_holding_threshold_retains_enough_assets_for_cap():
    filtered = portfolio_optimization.apply_min_holding_threshold(
        {"AAA": 0.80, "BBB": 0.10, "CCC": 0.10},
        min_holding_weight=0.15,
        max_asset_weight=0.60,
    )

    assert filtered == pytest.approx(
        {"AAA": 0.60, "BBB": 0.40, "CCC": 0.0}
    )
    assert sum(filtered.values()) == pytest.approx(1.0)
    assert max(filtered.values()) <= 0.600000001


def test_backtest_min_holding_target_preserves_asset_cap(monkeypatch):
    monkeypatch.setattr(
        portfolio_backtest,
        "_model_weights",
        lambda *args, **kwargs: (
            {"AAA": 0.60, "BBB": 0.36, "CCC": 0.04},
            {"failed_forecast_count": 0},
        ),
    )

    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(40),
        models=("equal_weight",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
        transaction_cost_bps=0.0,
        max_asset_weight=0.60,
        min_holding_weight=0.05,
        rebalance_band=0.0,
        max_turnover=1.0,
    )

    assert result["rebalance_records"]
    for record in result["rebalance_records"]:
        assert record["weights"] == pytest.approx(
            {"AAA": 0.60, "BBB": 0.40, "CCC": 0.0}
        )
        assert max(record["weights"].values()) <= 0.600000001


def test_backtest_max_turnover_sensitivity_caps_controlled_turnover():
    prices = _synthetic_prices(280)
    tight = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("momentum_6m",),
        train_window=126,
        rebalance_frequency=10,
        forecast_horizon=5,
        max_turnover=0.20,
    )
    loose = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("momentum_6m",),
        train_window=126,
        rebalance_frequency=10,
        forecast_horizon=5,
        max_turnover=0.50,
    )

    tight_records = tight["rebalance_records"]
    loose_records = loose["rebalance_records"]
    assert tight_records[0]["initial_allocation"] is True
    assert tight_records[0]["controlled_turnover"] > 0.20
    assert loose_records[0]["initial_allocation"] is True
    assert all(
        record["controlled_turnover"] <= 0.20 + 1e-9
        for record in tight_records[1:]
    )
    assert all(
        record["controlled_turnover"] <= 0.50 + 1e-9
        for record in loose_records[1:]
    )


def test_backtest_records_use_prior_prices_only(monkeypatch):
    seen_windows = []

    def fake_model_weights(model_name, train_prices, forecast_horizon, max_asset_weight, risk_free_rate, **kwargs):
        seen_windows.append((train_prices.index[0], train_prices.index[-1]))
        return {"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3}, {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
        }

    monkeypatch.setattr(portfolio_backtest, "_model_weights", fake_model_weights)

    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(45),
        models=("equal_weight",),
        train_window=15,
        rebalance_frequency=10,
        forecast_horizon=5,
    )

    assert seen_windows
    for record in result["rebalance_records"]:
        assert pd.Timestamp(record["train_end_date"]) < pd.Timestamp(record["rebalance_date"])


def test_synthetic_backtest_runs_all_model_families(monkeypatch):
    monkeypatch.setattr(
        portfolio_backtest,
        "forecast_single_ticker_with_arima_transformer",
        lambda ticker, prices, horizon=63: {"expected_return": 0.04, "uncertainty": 0.20},
    )
    monkeypatch.setattr(
        portfolio_backtest,
        "forecast_single_ticker_with_transformer",
        lambda ticker, prices, horizon=63: {"expected_return": None, "uncertainty": 5.0, "source": "no_view"},
    )

    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(80),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
        transaction_cost_bps=10,
    )

    assert set(result.keys()) == {
        "settings",
        "models",
        "summary_by_model",
        "alpha_diagnostics",
        "rebalance_records",
        "promotion_decision",
        "warnings",
    }
    assert set(result["models"]) == set(portfolio_backtest.DEFAULT_BACKTEST_MODELS)
    assert result["summary_by_model"]["equal_weight"]["rebalance_count"] > 0
    assert result["summary_by_model"]["transformer_bl"]["failed_forecast_count"] > 0
    assert "controlled_turnover" in result["summary_by_model"]["equal_weight"]
    assert "skipped_trade_count" in result["summary_by_model"]["equal_weight"]
    assert "turnover_cap_hit_count" in result["summary_by_model"]["equal_weight"]
    for record in result["rebalance_records"]:
        controls = record["rebalance_controls"]
        assert record["transaction_cost"] == pytest.approx(
            controls["controlled_trade_value"] * 0.001
        )
        assert record["portfolio_value_after_cost"] == pytest.approx(
            record["portfolio_value_before_cost"]
            - record["transaction_cost"]
        )
        assert (
            record["controlled_risky_exposure"]
            * record["portfolio_value_before_cost"]
            + controls["cash_after_transaction_cost"]
        ) == pytest.approx(record["portfolio_value_after_cost"])


def test_adaptive_signal_backtest_records_signal_construction_and_execution_layers():
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(360),
        models=("adaptive_signal_tilt",),
        train_window=280,
        rebalance_frequency=21,
        forecast_horizon=21,
        transaction_cost_bps=10,
        max_asset_weight=0.80,
        rebalance_band=0.0,
        max_turnover=1.0,
    )
    metrics = result["summary_by_model"]["adaptive_signal_tilt"]
    records = result["rebalance_records"]

    assert records
    assert metrics["signal_rank_ic_count"] > 0
    assert metrics["avg_active_share"] > 0.0
    assert metrics["avg_signal_weight_rank_correlation"] > 0.0
    assert metrics["gross_cumulative_return"] >= metrics["net_cumulative_return"]
    assert set(result["alpha_diagnostics"]["adaptive_signal_tilt"]) == {
        "signal",
        "construction",
        "execution",
    }
    assert all(record["signal_scores"] for record in records)
    assert all(record["realized_forward_returns"] for record in records)
    assert all(record["alpha_component_weights"] for record in records)
    assert all(record["train_end_date"] < record["rebalance_date"] for record in records)


def test_adaptive_signal_model_never_receives_rebalance_or_future_prices(monkeypatch):
    seen_train_end_dates = []
    original = portfolio_backtest.adaptive_cross_sectional_alpha

    def capture_training_window(train_prices, horizon=63):
        seen_train_end_dates.append(train_prices.index[-1])
        return original(train_prices, horizon=horizon)

    monkeypatch.setattr(
        portfolio_backtest,
        "adaptive_cross_sectional_alpha",
        capture_training_window,
    )
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(340),
        models=("adaptive_signal_tilt",),
        train_window=280,
        rebalance_frequency=21,
        forecast_horizon=21,
        max_asset_weight=0.80,
    )

    rebalance_dates = [
        pd.Timestamp(record["rebalance_date"])
        for record in result["rebalance_records"]
    ]
    assert len(seen_train_end_dates) == len(rebalance_dates)
    assert all(train_end < rebalance for train_end, rebalance in zip(seen_train_end_dates, rebalance_dates))


def test_synthetic_backtest_runs_risk_parity_and_momentum_bl():
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(280),
        models=("risk_parity", "momentum_bl"),
        train_window=252,
        rebalance_frequency=10,
        forecast_horizon=5,
        transaction_cost_bps=10,
    )

    assert result["models"] == ["risk_parity", "momentum_bl"]
    assert result["summary_by_model"]["risk_parity"]["rebalance_count"] > 0
    assert result["summary_by_model"]["momentum_bl"]["rebalance_count"] > 0
    assert "controlled_turnover" in result["rebalance_records"][0]


def test_synthetic_backtest_runs_new_baselines_and_gauntlet_aggregate():
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(280),
        models=(
            "equal_weight",
            "historical_bl",
            "risk_parity",
            "momentum_bl",
            "momentum_6m",
            "dual_horizon_momentum",
            "low_volatility",
            "market_cap_weight",
            "momentum_12_1",
            "signal_stack_bl",
        ),
        train_window=126,
        rebalance_frequency=10,
        forecast_horizon=5,
        transaction_cost_bps=10,
        market_caps={"AAA": 3_000_000, "BBB": 2_000_000, "CCC": 1_000_000},
        market_caps_as_of_date="2024-01-02",
    )
    aggregate = portfolio_backtest.aggregate_gauntlet_promotion([
        {"case": {"basket": "synthetic", "regime": "bull"}, "result": result}
    ])

    assert result["summary_by_model"]["momentum_6m"]["rebalance_count"] > 0
    assert result["summary_by_model"]["dual_horizon_momentum"]["rebalance_count"] > 0
    assert result["summary_by_model"]["low_volatility"]["rebalance_count"] > 0
    assert result["summary_by_model"]["market_cap_weight"]["market_cap_available_count"] > 0
    assert aggregate["usable_count"] == 1


def test_static_market_caps_without_as_of_are_not_used_in_backtest():
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(180),
        models=("market_cap_weight",),
        train_window=126,
        rebalance_frequency=21,
        market_caps={
            "AAA": 10_000_000,
            "BBB": 1_000_000,
            "CCC": 100_000,
        },
        max_asset_weight=0.80,
    )

    assert (
        result["summary_by_model"]["market_cap_weight"][
            "market_cap_available_count"
        ]
        == 0
    )
    assert all(
        record["market_caps_as_of_date"] is None
        for record in result["rebalance_records"]
    )


def test_point_in_time_market_caps_never_use_future_snapshot():
    prices = _synthetic_prices(220)
    cap_dates = [prices.index[100], prices.index[170]]
    point_in_time_caps = pd.DataFrame(
        [
            {"AAA": 9_000_000, "BBB": 2_000_000, "CCC": 1_000_000},
            {"AAA": 1_000_000, "BBB": 9_000_000, "CCC": 2_000_000},
        ],
        index=cap_dates,
    )
    result = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("market_cap_weight",),
        train_window=126,
        rebalance_frequency=21,
        point_in_time_market_caps=point_in_time_caps,
        max_asset_weight=0.80,
    )

    for record in result["rebalance_records"]:
        rebalance_date = pd.Timestamp(record["rebalance_date"])
        used_as_of = pd.Timestamp(record["market_caps_as_of_date"])
        assert used_as_of <= rebalance_date
        if rebalance_date < cap_dates[1]:
            assert used_as_of == cap_dates[0]


def test_forecast_rank_views_reuse_same_train_window_predictions(monkeypatch):
    calls = {"count": 0}
    prices = _synthetic_prices(140)

    def fake_transformer(ticker, ticker_prices, horizon=63):
        calls["count"] += 1
        return {"expected_return": 0.02 if ticker == "AAA" else 0.01, "uncertainty": 0.20}

    portfolio_backtest._FORECAST_RANK_CACHE.clear()
    monkeypatch.setattr(portfolio_backtest, "forecast_single_ticker_with_transformer", fake_transformer)

    portfolio_backtest._forecast_rank_views(prices, "transformer_rank", forecast_horizon=5)
    portfolio_backtest._forecast_rank_views(prices, "transformer_rank", forecast_horizon=5)

    assert calls["count"] == len(prices.columns)


class _ImmediateForecastExecutor:
    def __init__(self):
        self.submissions = []

    def submit(self, function, *args):
        self.submissions.append(args)
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


def _deterministic_rank_prediction(ticker, _prices, _method, _horizon):
    expected_returns = {
        "AAA": 0.03,
        "BBB": 0.02,
        "CCC": 0.01,
    }
    return {
        "expected_return": expected_returns[ticker],
        "uncertainty": 0.20,
        "source": "test",
    }


def test_forecast_rank_parallel_submits_only_cache_misses(monkeypatch):
    prices = _synthetic_prices(140)
    executor = _ImmediateForecastExecutor()
    portfolio_backtest.configure_forecast_rank_cache(None)
    monkeypatch.setattr(
        portfolio_backtest,
        "_forecast_rank_prediction_worker",
        _deterministic_rank_prediction,
    )
    cached_key = portfolio_backtest._forecast_rank_cache_key(
        "AAA",
        prices["AAA"],
        "transformer_rank",
        5,
    )
    portfolio_backtest._FORECAST_RANK_CACHE[cached_key] = (
        _deterministic_rank_prediction(
            "AAA",
            prices["AAA"],
            "transformer_rank",
            5,
        )
    )

    portfolio_backtest._forecast_rank_views(
        prices,
        "transformer_rank",
        forecast_horizon=5,
        forecast_executor=executor,
    )

    submitted_tickers = [args[0] for args in executor.submissions]
    assert submitted_tickers == ["BBB", "CCC"]
    assert portfolio_backtest._FORECAST_RANK_CACHE_STATS["memory_hits"] == 1
    assert portfolio_backtest._FORECAST_RANK_CACHE_STATS["misses"] == 2


def test_conditional_volatility_predictions_share_parallel_cache(
    monkeypatch,
):
    prices = _synthetic_prices(140)
    executor = _ImmediateForecastExecutor()
    portfolio_backtest.configure_forecast_rank_cache(None)
    monkeypatch.setattr(
        portfolio_backtest,
        "_forecast_rank_prediction_worker",
        _deterministic_rank_prediction,
    )

    predictions = portfolio_backtest._cached_forecast_predictions(
        {
            ticker: prices[ticker]
            for ticker in prices.columns
        },
        "arima_transformer_volatility",
        63,
        forecast_executor=executor,
    )

    assert set(predictions) == set(prices.columns)
    assert len(executor.submissions) == len(prices.columns)
    assert portfolio_backtest.forecast_rank_cache_stats()["memory_entries"] == (
        len(prices.columns)
    )


def test_forecast_rank_parallel_writes_sqlite_from_parent_only(
    monkeypatch,
    tmp_path,
):
    prices = _synthetic_prices(140)
    executor = _ImmediateForecastExecutor()
    cache_path = tmp_path / "parent-cache.sqlite3"
    portfolio_backtest.configure_forecast_rank_cache(cache_path)
    monkeypatch.setattr(
        portfolio_backtest,
        "_forecast_rank_prediction_worker",
        _deterministic_rank_prediction,
    )
    cache = portfolio_backtest._FORECAST_RANK_PERSISTENT_CACHE
    original_set = cache.set
    write_pids = []

    def recording_set(key, prediction):
        write_pids.append(os.getpid())
        original_set(key, prediction)

    monkeypatch.setattr(cache, "set", recording_set)
    try:
        portfolio_backtest._forecast_rank_views(
            prices,
            "transformer_rank",
            forecast_horizon=5,
            forecast_executor=executor,
        )

        assert write_pids == [os.getpid()] * len(prices.columns)
        assert cache.count() == len(prices.columns)
    finally:
        portfolio_backtest.configure_forecast_rank_cache(None)


def test_forecast_rank_parallel_worker_failure_becomes_no_view(
    monkeypatch,
    tmp_path,
):
    prices = _synthetic_prices(140)
    executor = _ImmediateForecastExecutor()
    cache_path = tmp_path / "worker-failure.sqlite3"
    portfolio_backtest.configure_forecast_rank_cache(cache_path)

    def failing_worker(ticker, ticker_prices, method, horizon):
        if ticker == "BBB":
            raise RuntimeError("synthetic worker crash")
        return _deterministic_rank_prediction(
            ticker,
            ticker_prices,
            method,
            horizon,
        )

    monkeypatch.setattr(
        portfolio_backtest,
        "_forecast_rank_prediction_worker",
        failing_worker,
    )
    try:
        _, _, failed, diagnostics = portfolio_backtest._forecast_rank_views(
            prices,
            "transformer_rank",
            forecast_horizon=5,
            forecast_executor=executor,
        )

        failed_key = portfolio_backtest._forecast_rank_cache_key(
            "BBB",
            prices["BBB"],
            "transformer_rank",
            5,
        )
        cached_failure = portfolio_backtest._FORECAST_RANK_PERSISTENT_CACHE.get(
            failed_key
        )
        assert failed == 1
        assert "BBB" not in diagnostics["raw_forecasts"]
        assert cached_failure["source"] == "no_view"
        assert "synthetic worker crash" in cached_failure["reason"]
    finally:
        portfolio_backtest.configure_forecast_rank_cache(None)


def test_forecast_rank_worker_default_cap_is_two(monkeypatch):
    monkeypatch.delenv("ANTIFIER_ML_MAX_WORKERS", raising=False)
    assert portfolio_backtest._forecast_rank_worker_count(10) == 2
    assert portfolio_backtest._forecast_rank_worker_count(1) == 1

    monkeypatch.setenv("ANTIFIER_ML_MAX_WORKERS", "4")
    assert portfolio_backtest._forecast_rank_worker_count(10) == 4


def test_forecast_rank_sequential_and_parallel_result_structure_match(
    monkeypatch,
):
    prices = _synthetic_prices(140)
    monkeypatch.setattr(
        portfolio_backtest,
        "_forecast_rank_prediction_worker",
        _deterministic_rank_prediction,
    )
    portfolio_backtest.configure_forecast_rank_cache(None)
    sequential = portfolio_backtest._forecast_rank_views(
        prices,
        "transformer_rank",
        forecast_horizon=5,
    )

    portfolio_backtest.configure_forecast_rank_cache(None)
    parallel = portfolio_backtest._forecast_rank_views(
        prices,
        "transformer_rank",
        forecast_horizon=5,
        forecast_executor=_ImmediateForecastExecutor(),
    )

    pd.testing.assert_series_equal(sequential[0], parallel[0])
    pd.testing.assert_series_equal(sequential[1], parallel[1])
    assert sequential[2:] == parallel[2:]


def test_build_rebalance_targets_reuses_one_forecast_executor(
    monkeypatch,
):
    prices = _synthetic_prices(80)
    executor_token = object()
    executor_context_entries = []
    observed_executors = []

    @contextmanager
    def fake_executor_context(models, ticker_count):
        executor_context_entries.append((tuple(models), ticker_count))
        yield executor_token

    def fake_model_weights(
        model_name,
        train_prices,
        forecast_horizon,
        max_asset_weight,
        risk_free_rate,
        **kwargs,
    ):
        observed_executors.append(kwargs.get("forecast_executor"))
        return {"AAA": 0.5, "BBB": 0.3, "CCC": 0.2}, {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
        }

    monkeypatch.setattr(
        portfolio_backtest,
        "_forecast_rank_executor",
        fake_executor_context,
    )
    monkeypatch.setattr(
        portfolio_backtest,
        "_model_weights",
        fake_model_weights,
    )

    targets = portfolio_backtest.build_rebalance_targets(
        prices,
        models=("transformer_rank_bl",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
    )

    assert len(targets["records"]) > 1
    assert len(executor_context_entries) == 1
    assert observed_executors
    assert all(executor is executor_token for executor in observed_executors)


def test_forecast_rank_real_process_pool_smoke_uses_parent_cache(
    monkeypatch,
    tmp_path,
):
    prices = _synthetic_prices(20)
    cache_path = tmp_path / "process-pool.sqlite3"
    monkeypatch.setenv("ANTIFIER_ML_MAX_WORKERS", "2")
    portfolio_backtest.configure_forecast_rank_cache(cache_path)
    try:
        with portfolio_backtest._forecast_rank_executor(
            ("transformer_rank_bl",),
            len(prices.columns),
        ) as executor:
            _, _, failed, _ = portfolio_backtest._forecast_rank_views(
                prices,
                "transformer_rank",
                forecast_horizon=5,
                forecast_executor=executor,
            )

        assert failed == len(prices.columns)
        assert portfolio_backtest.forecast_rank_cache_stats()["writes"] == len(
            prices.columns
        )
        assert portfolio_backtest._FORECAST_RANK_PERSISTENT_CACHE.count() == len(
            prices.columns
        )
    finally:
        portfolio_backtest.configure_forecast_rank_cache(None)


def test_forecast_rank_views_reuse_persistent_predictions_after_memory_clear(monkeypatch, tmp_path):
    calls = {"count": 0}
    prices = _synthetic_prices(140)

    def fake_transformer(ticker, ticker_prices, horizon=63):
        calls["count"] += 1
        return {"expected_return": 0.02, "uncertainty": 0.20, "source": "test"}

    monkeypatch.setattr(portfolio_backtest, "forecast_single_ticker_with_transformer", fake_transformer)
    cache_path = tmp_path / "forecast-cache.sqlite3"
    portfolio_backtest.configure_forecast_rank_cache(cache_path)
    try:
        portfolio_backtest._forecast_rank_views(prices, "transformer_rank", forecast_horizon=5)
        portfolio_backtest._FORECAST_RANK_CACHE.clear()
        portfolio_backtest._forecast_rank_views(prices, "transformer_rank", forecast_horizon=5)

        stats = portfolio_backtest.forecast_rank_cache_stats()
        assert calls["count"] == len(prices.columns)
        assert stats["persistent_hits"] == len(prices.columns)
        assert stats["persistent_entries"] == len(prices.columns)
    finally:
        portfolio_backtest.configure_forecast_rank_cache(None)


def test_precomputed_rebalance_targets_are_reused_across_execution_sensitivities(monkeypatch):
    calls = {"count": 0}
    prices = _synthetic_prices(80)

    def fake_model_weights(model_name, train_prices, forecast_horizon, max_asset_weight, risk_free_rate, **kwargs):
        calls["count"] += 1
        return {"AAA": 0.60, "BBB": 0.30, "CCC": 0.10}, {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
        }

    monkeypatch.setattr(portfolio_backtest, "_model_weights", fake_model_weights)
    targets = portfolio_backtest.build_rebalance_targets(
        prices,
        models=("equal_weight",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
    )
    target_generation_calls = calls["count"]

    tight = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("equal_weight",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
        rebalance_band=0.02,
        max_turnover=0.20,
        rebalance_targets=targets,
    )
    loose = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("equal_weight",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
        rebalance_band=0.05,
        max_turnover=0.50,
        rebalance_targets=targets,
    )

    assert calls["count"] == target_generation_calls
    assert tight["settings"]["reused_rebalance_targets"] is True
    assert loose["settings"]["reused_rebalance_targets"] is True


def test_rank_candidate_records_cross_sectional_information_coefficient(monkeypatch):
    expected_returns = {"AAA": 0.05, "BBB": 0.03, "CCC": 0.01}

    def fake_arima_transformer(ticker, ticker_prices, horizon=63):
        return {
            "expected_return": expected_returns[ticker],
            "uncertainty": 0.20,
            "source": "test",
        }

    portfolio_backtest.configure_forecast_rank_cache(None)
    monkeypatch.setattr(
        portfolio_backtest,
        "forecast_single_ticker_with_arima_transformer",
        fake_arima_transformer,
    )
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(80),
        models=("arima_transformer_rank_bl",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
    )
    metrics = result["summary_by_model"]["arima_transformer_rank_bl"]

    assert metrics["forecast_rank_ic_count"] > 0
    assert metrics["avg_forecast_rank_ic"] > 0
    assert metrics["positive_forecast_rank_ic_rate"] > 0.5
    assert all(
        record["forecast_rank_ic"] is not None
        for record in result["rebalance_records"]
    )


def test_backtest_cli_writes_json_and_invalid_args_fail(tmp_path):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "backtest.json"
    _synthetic_prices(280).to_csv(csv_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    ok = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "backtest_portfolio_models.py"),
            "--csv",
            str(csv_path),
            "--models",
            "risk_parity",
            "momentum_bl",
            "--train-window",
            "252",
            "--rebalance-frequency",
            "10",
            "--forecast-horizon",
            "5",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert ok.returncode == 0, ok.stderr
    payload = json.loads(output_path.read_text())
    assert payload["models"] == ["risk_parity", "momentum_bl"]
    assert "summary_by_model" in payload

    bad = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "backtest_portfolio_models.py")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert bad.returncode != 0


def test_backtest_cli_gauntlet_smoke_writes_json_and_report(tmp_path):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "gauntlet.json"
    _synthetic_prices(280).to_csv(csv_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    ok = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "backtest_portfolio_models.py"),
            "--gauntlet-preset",
            "smoke",
            "--csv",
            str(csv_path),
            "--models",
            "equal_weight",
            "risk_parity",
            "momentum_6m",
            "low_volatility",
            "momentum_12_1",
            "historical_bl",
            "momentum_bl",
            "signal_stack_bl",
            "adaptive_signal_tilt",
            "--train-window",
            "126",
            "--rebalance-frequency",
            "10",
            "--forecast-horizon",
            "5",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert ok.returncode == 0, ok.stderr
    payload = json.loads(output_path.read_text())
    assert payload["preset"] == "smoke"
    assert payload["completed_count"] == 1
    assert payload["promotion_gauntlet"]["usable_count"] == 1
    assert payload["settings"]["execution_sensitivity_reuses_targets"] is True
    assert payload["evaluation_split"] == "research"
    assert payload["runs"][0]["result"]["settings"]["reused_rebalance_targets"] is True
    assert Path(payload["checkpoint_path"]).exists()
    assert (tmp_path / "portfolio_gauntlet_forecasts.sqlite3").exists()
    assert output_path.with_suffix(".md").exists()
    assert "## Alpha diagnostics" in output_path.with_suffix(".md").read_text()


def test_backtest_cli_candidate_preset_checkpoints_and_resumes(tmp_path):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "candidate.json"
    _synthetic_prices(80).to_csv(csv_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    command = [
        sys.executable,
        str(ROOT / "tools" / "backtest_portfolio_models.py"),
        "--gauntlet-preset",
        "candidate",
        "--csv",
        str(csv_path),
        "--models",
        "equal_weight",
        "--train-window",
        "20",
        "--rebalance-frequency",
        "10",
        "--forecast-horizon",
        "5",
        "--output",
        str(output_path),
    ]

    first = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    payload = json.loads(output_path.read_text())
    assert payload["preset"] == "candidate"
    assert payload["evaluation_split"] == "validation"
    assert payload["completed_count"] == 4
    assert {
        (run["case"]["basket_key"], run["case"]["regime"])
        for run in payload["runs"]
    } == {
        ("sp500_sample", "bull"),
        ("tech", "crash"),
        ("defensive", "inflation_rate_shock"),
        ("mixed_etf", "sideways"),
    }

    checkpoint_path = Path(payload["checkpoint_path"])
    first_checkpoint_lines = checkpoint_path.read_text().splitlines()
    resumed = subprocess.run(
        [*command, "--resume"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert len(checkpoint_path.read_text().splitlines()) == len(first_checkpoint_lines)


def test_holdout_preset_is_isolated_from_validation_cases():
    import importlib.util

    module_path = ROOT / "tools" / "backtest_portfolio_models.py"
    spec = importlib.util.spec_from_file_location("backtest_portfolio_models_tool", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    validation_cases = module._gauntlet_cases("candidate")
    holdout_cases = module._gauntlet_cases("holdout")
    standard_cases = module._gauntlet_cases("standard")

    assert len(validation_cases) == 4
    assert len(holdout_cases) == 4
    assert all(case["regime"] == "locked_holdout_2024_2025" for case in holdout_cases)
    assert all(case["start"] == "2022-01-01" for case in holdout_cases)
    assert all(case["regime"] != "locked_holdout_2024_2025" for case in standard_cases)
    assert module._evaluation_split("candidate") == "validation"
    assert module._evaluation_split("holdout") == "locked_holdout"
