import numpy as np
import pandas as pd

from forecast_signal_research import sequential_forecast_confidence_gate
from portfolio_risk_models import (
    conditional_volatility_covariance,
    conditional_volatility_minimum_variance_weights,
    forecast_conditional_volatilities,
)
from portfolio_signals import confidence_gated_gmv_overlay


def _completed_periods(count=12):
    return [
        {
            "period_id": index,
            "forward_end_date": pd.Timestamp("2020-01-01")
            + pd.Timedelta(days=30 * index),
            "scores": {"A": 0.0, "B": 1.0, "C": 2.0, "D": 3.0},
            "realized_returns": {
                "A": 0.00,
                "B": 0.01,
                "C": 0.02,
                "D": 0.03,
            },
        }
        for index in range(count)
    ]


def _predictions():
    return [
        {
            "ticker": ticker,
            "expected_return": value,
            "uncertainty": 0.10,
        }
        for ticker, value in zip("ABCD", (-0.2, -0.05, 0.1, 0.25))
    ]


def _prices(rows=400):
    index = pd.date_range("2018-01-01", periods=rows, freq="B")
    x = np.arange(rows, dtype=float)
    return pd.DataFrame(
        {
            ticker: 100.0
            * np.exp(0.0002 * x + scale * np.sin(x / (10.0 + scale)))
            for ticker, scale in zip("ABCD", (0.01, 0.02, 0.03, 0.04))
        },
        index=index,
    )


def test_sequential_gate_uses_only_completed_outcomes_and_is_deterministic():
    periods = _completed_periods()
    periods.append(
        {
            **periods[-1],
            "period_id": 99,
            "forward_end_date": "2030-01-01",
            "scores": {"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.0},
        }
    )
    first = sequential_forecast_confidence_gate(
        periods,
        _predictions(),
        "2022-01-01",
        bootstrap_samples=200,
    )
    second = sequential_forecast_confidence_gate(
        periods,
        _predictions(),
        "2022-01-01",
        bootstrap_samples=200,
    )

    assert first == second
    assert first["active"]
    assert first["strength"] == 1.0
    assert first["completed_period_count"] == 12


def test_rejected_gate_zeroes_overlay_and_passed_gate_respects_constraints():
    gmv = pd.Series({"A": 0.40, "B": 0.30, "C": 0.20, "D": 0.10})
    scores = pd.Series({"A": -1.0, "B": -0.5, "C": 0.5, "D": 1.0})
    rejected, rejected_diagnostics = confidence_gated_gmv_overlay(
        gmv,
        scores,
        {"active": False, "strength": 0.0},
        max_asset_weight=0.50,
    )
    active, active_diagnostics = confidence_gated_gmv_overlay(
        gmv,
        scores,
        {"active": True, "strength": 1.0},
        max_asset_weight=0.50,
    )

    pd.testing.assert_series_equal(rejected, gmv)
    assert rejected_diagnostics["realized_active_share"] == 0.0
    assert np.isclose(active.sum(), 1.0)
    assert active.max() <= 0.50 + 1e-12
    assert active_diagnostics["realized_active_share"] > 0.0


def test_conditional_covariance_is_psd_and_invalid_forecast_falls_back():
    prices = _prices()
    forecast = pd.Series({"A": 0.10, "B": np.nan, "C": 0.20, "D": -1.0})
    covariance, diagnostics = conditional_volatility_covariance(
        prices,
        forecast,
    )
    weights, weight_diagnostics = (
        conditional_volatility_minimum_variance_weights(
            prices,
            forecast,
            max_asset_weight=0.40,
        )
    )

    assert np.linalg.eigvalsh(covariance).min() >= -1e-10
    assert diagnostics["fallback_tickers"] == ["B", "D"]
    assert np.isclose(weights.sum(), 1.0)
    assert weights.max() <= 0.40 + 1e-9
    assert weight_diagnostics["optimizer_success"]


def test_volatility_adapter_reuses_return_forecast_contract():
    calls = []

    def forecast(ticker, history, horizon):
        calls.append((ticker, len(history), horizon))
        return {
            "expected_return": 0.0 if ticker != "D" else None,
            "source": "arima_transformer",
        }

    values, details = forecast_conditional_volatilities(
        _prices(),
        forecast,
        horizon=63,
    )

    assert len(calls) == 4
    assert values.loc[["A", "B", "C"]].notna().all()
    assert pd.isna(values["D"])
    assert details["A"]["source"] == "arima_transformer"
