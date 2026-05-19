import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

import app as app_module
import portfolio_benchmark
import portfolio_optimization


def _history_frame(values):
    return pd.DataFrame(
        {"Close": values},
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"][: len(values)]),
    )


def test_portfolio_result_ids_cannot_escape_results_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio_optimization, "RESULTS_DIR", tmp_path / "portfolio_results")

    portfolio_optimization.save_portfolio_result("safe-id_1", {"weights": {"AAPL": 1.0}})
    assert (tmp_path / "portfolio_results" / "safe-id_1.json").exists()

    with pytest.raises(ValueError):
        portfolio_optimization.save_portfolio_result("../escape", {"weights": {"AAPL": 1.0}})

    assert not (tmp_path / "escape.json").exists()


def test_benchmark_rejects_missing_ticker_data(monkeypatch):
    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, start=None, end=None):
            if self.ticker == "MSFT":
                return pd.DataFrame()
            return _history_frame([100.0, 110.0, 120.0])

    monkeypatch.setattr(portfolio_benchmark.yf, "Ticker", FakeTicker)

    with pytest.raises(ValueError, match="MSFT"):
        portfolio_benchmark.calculate_portfolio_benchmark(
            {"weights": {"AAPL": 0.5, "MSFT": 0.5}, "prices": {"AAPL": 120, "MSFT": 200}},
            budget=1000,
            start_date=datetime(2024, 1, 2),
            end_date=datetime(2024, 1, 5),
            risk_free_rate=0.04,
        )


def test_benchmark_aligns_missing_dates_without_dropping_asset_value(monkeypatch):
    histories = {
        "AAPL": pd.DataFrame(
            {"Close": [100.0, 110.0]},
            index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
        ),
        "MSFT": pd.DataFrame(
            {"Close": [200.0, 240.0]},
            index=pd.to_datetime(["2024-01-02", "2024-01-04"]),
        ),
        "^GSPC": _history_frame([4000.0, 4040.0, 4080.0]),
    }

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, start=None, end=None):
            return histories[self.ticker]

    monkeypatch.setattr(portfolio_benchmark.yf, "Ticker", FakeTicker)

    result = portfolio_benchmark.calculate_portfolio_benchmark(
        {"weights": {"AAPL": 0.5, "MSFT": 0.5}, "prices": {"AAPL": 110, "MSFT": 240}},
        budget=1000,
        start_date=datetime(2024, 1, 2),
        end_date=datetime(2024, 1, 5),
        risk_free_rate=0.04,
    )

    assert result["portfolio_timeline"]["2024-01-02"] == pytest.approx(1000.0)
    assert result["portfolio_timeline"]["2024-01-03"] == pytest.approx(1050.0)
    assert result["portfolio_timeline"]["2024-01-04"] == pytest.approx(1150.0)


def test_benchmark_converts_non_usd_prices_to_usd(monkeypatch):
    histories = {
        "035420.KS": _history_frame([130000.0, 140000.0, 150000.0]),
        "AAPL": _history_frame([100.0, 110.0, 120.0]),
        "^GSPC": _history_frame([4000.0, 4040.0, 4080.0]),
    }
    fx_data = _history_frame([1300.0, 1400.0, 1500.0])

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, start=None, end=None):
            return histories[self.ticker]

    monkeypatch.setattr(portfolio_benchmark.yf, "Ticker", FakeTicker)
    with patch("portfolio_optimization.yf.download", return_value=fx_data) as mock_download:
        result = portfolio_benchmark.calculate_portfolio_benchmark(
            {"weights": {"035420.KS": 0.5, "AAPL": 0.5}, "prices": {"035420.KS": 150000, "AAPL": 120}},
            budget=1000,
            start_date=datetime(2024, 1, 2),
            end_date=datetime(2024, 1, 5),
            risk_free_rate=0.04,
        )

    assert mock_download.call_args.args[0] == "KRW=X"
    assert result["portfolio_timeline"]["2024-01-02"] == pytest.approx(1000.0)
    assert result["summary"]["portfolio"]["initial_value"] == pytest.approx(1000.0)


def test_lightweight_pipeline_normalizes_period_return_to_annual_log_return(monkeypatch):
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    prices = pd.DataFrame(
        {
            "AAPL": [100.0, 101.0, 102.0, 103.0],
            "MSFT": [200.0, 201.0, 202.0, 203.0],
        },
        index=dates,
    )

    class FakeCovarianceShrinkage:
        def __init__(self, data):
            self.data = data

        def ledoit_wolf(self):
            tickers = list(self.data.columns)
            return pd.DataFrame(np.eye(len(tickers)), index=tickers, columns=tickers)

    monkeypatch.setattr(portfolio_optimization, "get_stock_data", lambda *args, **kwargs: prices)
    monkeypatch.setattr(portfolio_optimization, "lightweight_ensemble_forecast", lambda prices, horizon=63: 0.21)
    monkeypatch.setattr(portfolio_optimization.risk_models, "CovarianceShrinkage", FakeCovarianceShrinkage)

    result = portfolio_optimization.data_and_forecast_pipeline(
        start_date="2024-01-02",
        end_date="2024-01-05",
        ticker_group=None,
        tickers=["AAPL", "MSFT"],
        forecast_method="LIGHTWEIGHT",
        forecast_horizon=63,
        min_history=0,
    )

    expected = np.log1p(0.21) * (252 / 63)
    assert result["mu"]["AAPL"] == pytest.approx(expected)
    assert result["mu"]["MSFT"] == pytest.approx(expected)


def test_regression_endpoint_returns_error_status_for_empty_market_data():
    stock = MagicMock()
    stock.history.return_value = pd.DataFrame()

    app_module.app.config["TESTING"] = True
    with patch("app.yf.Ticker", return_value=stock):
        response = app_module.app.test_client().get("/get-data?regression=true&ticker=BAD")

    assert response.status_code == 502
    assert "error" in response.get_json()


def test_progress_events_do_not_crash_after_queue_cleanup():
    with app_module.REQUEST_QUEUES_LOCK:
        app_module.REQUEST_QUEUES.pop("already-closed", None)

    app_module.push_progress(
        "already-closed",
        100,
        100,
        "Optimization complete",
        status="completed",
        result={"weights": {"AAPL": 1.0}},
    )
