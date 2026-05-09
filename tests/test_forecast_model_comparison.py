import os
import sys

import numpy as np
import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

import forecast_models


def test_summarize_forecast_records_calculates_error_metrics():
    records = [
        {"predicted_log_return": 0.10, "actual_log_return": 0.08, "elapsed_seconds": 1.0},
        {"predicted_log_return": -0.02, "actual_log_return": -0.01, "elapsed_seconds": 3.0},
        {"predicted_log_return": None, "actual_log_return": 0.05, "elapsed_seconds": 2.0},
    ]

    summary = forecast_models._summarize_forecast_records(records)

    assert summary["n"] == 2
    assert summary["failures"] == 1
    assert summary["mae"] == pytest.approx(0.015)
    assert summary["rmse"] == pytest.approx(np.sqrt((0.02**2 + (-0.01)**2) / 2))
    assert summary["bias"] == pytest.approx(0.005)
    assert summary["directional_accuracy"] == pytest.approx(1.0)
    assert summary["avg_seconds"] == pytest.approx(2.0)


def test_compare_forecasters_on_series_uses_same_windows(monkeypatch):
    prices = np.linspace(100.0, 160.0, 180)

    monkeypatch.setattr(
        forecast_models,
        "_forecast_ensemble_period_log_return",
        lambda train_prices, horizon: 0.01,
    )
    monkeypatch.setattr(
        forecast_models,
        "_forecast_transformer_period_log_return",
        lambda train_prices, horizon, transformer_kwargs=None: 0.02,
    )
    monkeypatch.setattr(
        forecast_models,
        "_forecast_arima_transformer_period_log_return",
        lambda train_prices, horizon, transformer_kwargs=None: 0.015,
    )

    result = forecast_models.compare_forecasters_on_series(
        prices,
        horizon=5,
        min_train_size=100,
        step=10,
        max_windows=3,
    )

    assert set(result.keys()) == {"ensemble", "transformer", "arima_transformer"}
    assert result["ensemble"]["metrics"]["n"] == 3
    assert result["transformer"]["metrics"]["n"] == 3
    assert result["arima_transformer"]["metrics"]["n"] == 3
    assert [
        record["cutoff_index"] for record in result["ensemble"]["records"]
    ] == [
        record["cutoff_index"] for record in result["transformer"]["records"]
    ] == [
        record["cutoff_index"] for record in result["arima_transformer"]["records"]
    ]


def test_legacy_ensemble_comparison_path_uses_arima_transformer(monkeypatch):
    calls = []

    def fake_arima_transformer(train_prices, horizon, transformer_kwargs=None):
        calls.append((len(train_prices), horizon, transformer_kwargs))
        return 0.0123

    monkeypatch.setattr(
        forecast_models,
        "_forecast_arima_transformer_period_log_return",
        fake_arima_transformer,
    )

    result = forecast_models.compare_forecasters_on_series(
        np.linspace(100.0, 140.0, 130),
        horizon=5,
        min_train_size=100,
        step=20,
        max_windows=1,
        models=("ensemble",),
        transformer_kwargs={"epochs": 1},
    )

    assert result["ensemble"]["metrics"]["n"] == 1
    assert calls == [(120, 5, None)]


def test_legacy_portfolio_ensemble_alias_uses_arima_transformer(monkeypatch):
    import pandas as pd
    import portfolio_optimization

    calls = []

    def fake_prediction(ticker, ticker_data, horizon=252):
        calls.append((ticker, len(ticker_data), horizon))
        return {
            "expected_return": 0.12,
            "uncertainty": 0.03,
            "components": {"ARIMA": 0.10, "Transformer": 0.14},
        }

    monkeypatch.setattr(
        portfolio_optimization,
        "_generate_arima_transformer_prediction",
        fake_prediction,
    )

    prices = pd.Series(np.linspace(100.0, 130.0, 130))
    result = portfolio_optimization.forecast_single_ticker_with_ensemble("AAPL", prices, horizon=21)

    assert result["expected_return"] == pytest.approx(0.12)
    assert result["source"] == "arima_transformer"
    assert calls == [("AAPL", 130, 21)]
