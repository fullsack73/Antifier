import json
import os
import subprocess
import sys
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
from forecast_models import (
    ARIMATransformerPredictor,
    NO_VIEW_FORECAST_UNCERTAINTY,
    TransformerForecastModel,
    no_view_prediction,
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


def test_turnover_and_transaction_cost_math():
    turnover, cost = portfolio_backtest.calculate_turnover_and_cost(
        {"AAA": 500.0, "BBB": 500.0},
        {"AAA": 0.60, "BBB": 0.40},
        portfolio_value=1000.0,
        transaction_cost_bps=10.0,
    )

    assert turnover == pytest.approx(0.20)
    assert cost == pytest.approx(0.20)


def test_backtest_records_use_prior_prices_only(monkeypatch):
    seen_windows = []

    def fake_model_weights(model_name, train_prices, forecast_horizon, max_asset_weight, risk_free_rate):
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
        "rebalance_records",
        "promotion_decision",
        "warnings",
    }
    assert set(result["models"]) == set(portfolio_backtest.DEFAULT_BACKTEST_MODELS)
    assert result["summary_by_model"]["equal_weight"]["rebalance_count"] > 0
    assert result["summary_by_model"]["transformer_bl"]["failed_forecast_count"] > 0


def test_backtest_cli_writes_json_and_invalid_args_fail(tmp_path):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "backtest.json"
    _synthetic_prices(50).to_csv(csv_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    ok = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "backtest_portfolio_models.py"),
            "--csv",
            str(csv_path),
            "--models",
            "equal_weight",
            "--train-window",
            "15",
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
    assert payload["models"] == ["equal_weight"]
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
