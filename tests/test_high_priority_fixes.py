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


def test_fx_alignment_does_not_backfill_future_rate(monkeypatch):
    target_dates = pd.date_range("2024-01-02", periods=4, freq="B")
    fx_data = pd.DataFrame(
        {"Close": [1300.0, 1310.0]},
        index=target_dates[2:],
    )
    monkeypatch.setattr(
        portfolio_optimization.yf,
        "download",
        lambda *args, **kwargs: fx_data,
    )

    factor = portfolio_optimization._fetch_usd_conversion_factor(
        "KRW",
        "2024-01-02",
        "2024-01-08",
        target_dates,
    )

    assert factor.iloc[:2].isna().all()
    assert factor.iloc[2] == pytest.approx(1.0 / 1300.0)


def test_lightweight_pipeline_normalizes_period_return_to_annual_simple_return(monkeypatch):
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
    portfolio_optimization.get_cache().clear()

    result = portfolio_optimization.data_and_forecast_pipeline(
        start_date="2024-01-02",
        end_date="2024-01-05",
        ticker_group=None,
        tickers=["AAPL", "MSFT"],
        forecast_method="LIGHTWEIGHT",
        forecast_horizon=63,
        min_history=0,
    )

    expected = np.expm1(np.log1p(0.21) * (252 / 63))
    assert result["mu"]["AAPL"] == pytest.approx(expected)
    assert result["mu"]["MSFT"] == pytest.approx(expected)


def test_lightweight_failure_becomes_prior_only_no_view(monkeypatch):
    dates = pd.date_range("2020-01-02", periods=260, freq="B")
    prices = pd.DataFrame(
        {
            "AAPL": np.linspace(100.0, 120.0, len(dates)),
            "MSFT": np.linspace(200.0, 230.0, len(dates)),
        },
        index=dates,
    )

    class FakeCovarianceShrinkage:
        def __init__(self, data):
            self.data = data

        def ledoit_wolf(self):
            tickers = list(self.data.columns)
            return pd.DataFrame(
                np.eye(len(tickers)),
                index=tickers,
                columns=tickers,
            )

    monkeypatch.setattr(
        portfolio_optimization,
        "get_stock_data",
        lambda *args, **kwargs: prices,
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "lightweight_ensemble_forecast",
        MagicMock(side_effect=RuntimeError("forced failure")),
    )
    monkeypatch.setattr(
        portfolio_optimization.risk_models,
        "CovarianceShrinkage",
        FakeCovarianceShrinkage,
    )
    portfolio_optimization.get_cache().clear()

    result = portfolio_optimization.data_and_forecast_pipeline(
        start_date="2020-01-02",
        end_date="2020-12-31",
        ticker_group=None,
        tickers=["AAPL", "MSFT"],
        forecast_method="LIGHTWEIGHT",
        forecast_horizon=63,
        min_history=0,
    )

    assert set(result["no_view_tickers"]) == {"AAPL", "MSFT"}
    assert result["mu"].to_dict() == pytest.approx(
        result["prior_mu"].to_dict()
    )
    assert all(
        value == pytest.approx(
            portfolio_optimization.MAX_FORECAST_UNCERTAINTY
        )
        for value in result["uncertainties"]
    )


def test_ml_pipeline_converts_annual_log_return_to_annual_simple_return(monkeypatch):
    dates = pd.to_datetime(["2024-02-02", "2024-02-03", "2024-02-04", "2024-02-05"])
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
    monkeypatch.setattr(
        portfolio_optimization,
        "ml_forecast_returns",
        lambda data, progress_callback=None, horizon=63: (
            pd.Series({"AAPL": np.log1p(0.12), "MSFT": np.log1p(-0.05)}),
            pd.Series({"AAPL": 0.05, "MSFT": 0.05}),
        ),
    )
    monkeypatch.setattr(portfolio_optimization.risk_models, "CovarianceShrinkage", FakeCovarianceShrinkage)
    portfolio_optimization.get_cache().clear()

    result = portfolio_optimization.data_and_forecast_pipeline(
        start_date="2024-02-02",
        end_date="2024-02-05",
        ticker_group=None,
        tickers=["AAPL", "MSFT"],
        forecast_method="ARIMA_TRANSFORMER",
        forecast_horizon=63,
        min_history=0,
    )

    assert result["mu"]["AAPL"] == pytest.approx(0.12)
    assert result["mu"]["MSFT"] == pytest.approx(-0.05)
    assert result["uncertainties"]["AAPL"] == pytest.approx(1.12 * 0.05)
    assert result["uncertainties"]["MSFT"] == pytest.approx(0.95 * 0.05)


def test_mpt_uses_confidence_adjusted_expected_returns(monkeypatch):
    captured = {}
    pipeline_result = {
        "mu": pd.Series({"AAPL": 0.40, "MSFT": 0.08}),
        "prior_mu": pd.Series({"AAPL": 0.08, "MSFT": 0.08}),
        "S": pd.DataFrame(
            [[0.04, 0.005], [0.005, 0.02]],
            index=["AAPL", "MSFT"],
            columns=["AAPL", "MSFT"],
        ),
        "uncertainties": pd.Series({"AAPL": 0.20, "MSFT": 0.20}),
        "tickers": ["AAPL", "MSFT"],
        "latest_prices": {"AAPL": 150.0, "MSFT": 200.0},
        "data_eligibility": {
            "eligible_tickers": ["AAPL", "MSFT"],
            "dropped_tickers": [],
        },
    }

    class FakeEfficientFrontier:
        def __init__(self, mu, S, weight_bounds=None):
            captured["mu"] = mu.copy()

        def add_objective(self, *args, **kwargs):
            pass

        def max_sharpe(self, risk_free_rate=0.0):
            pass

        def clean_weights(self):
            return {"AAPL": 0.6, "MSFT": 0.4}

        def portfolio_performance(self, risk_free_rate=0.0):
            return (0.20, 0.15, 1.0)

    monkeypatch.setattr(portfolio_optimization, "data_and_forecast_pipeline", lambda *args, **kwargs: pipeline_result)
    monkeypatch.setattr(portfolio_optimization, "EfficientFrontier", FakeEfficientFrontier)
    monkeypatch.setattr(portfolio_optimization, "get_asset_names", lambda tickers: {ticker: ticker for ticker in tickers})

    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=["AAPL", "MSFT"],
        optimization_method="MPT",
        forecast_method="ARIMA_TRANSFORMER",
    )

    assert captured["mu"]["AAPL"] == pytest.approx(0.24)
    assert captured["mu"]["MSFT"] == pytest.approx(0.08)
    assert result["return_confidence"]["AAPL"] == pytest.approx(0.5)
    assert result["adjusted_expected_returns"]["AAPL"] == pytest.approx(0.24)
    assert result["data_eligibility"] == pipeline_result["data_eligibility"]


def test_black_litterman_uses_confidence_adjusted_views_and_omega(monkeypatch):
    captured = {}
    pipeline_result = {
        "mu": pd.Series({"AAPL": 0.40, "MSFT": 0.08}),
        "prior_mu": pd.Series({"AAPL": 0.02, "MSFT": 0.02}),
        "S": pd.DataFrame(
            [[0.04, 0.005], [0.005, 0.02]],
            index=["AAPL", "MSFT"],
            columns=["AAPL", "MSFT"],
        ),
        "uncertainties": pd.Series({"AAPL": 0.20, "MSFT": 0.20}),
        "tickers": ["AAPL", "MSFT"],
        "latest_prices": {"AAPL": 150.0, "MSFT": 200.0},
    }

    class FakeBlackLittermanModel:
        def __init__(self, S, pi=None, absolute_views=None, omega=None, risk_aversion=None, tau=None):
            captured["pi"] = pi.copy()
            captured["absolute_views"] = absolute_views.copy()
            captured["omega"] = omega.copy()

        def bl_returns(self):
            return captured["absolute_views"]

        def bl_cov(self):
            return pipeline_result["S"]

    class FakeEfficientFrontier:
        def __init__(self, mu, S, weight_bounds=None):
            captured["optimizer_mu"] = mu.copy()

        def add_objective(self, *args, **kwargs):
            pass

        def max_sharpe(self, risk_free_rate=0.0):
            pass

        def clean_weights(self):
            return {"AAPL": 0.6, "MSFT": 0.4}

        def portfolio_performance(self, risk_free_rate=0.0):
            return (0.20, 0.15, 1.0)

    market_prior = pd.Series({"AAPL": 0.08, "MSFT": 0.08})

    monkeypatch.setattr(portfolio_optimization, "data_and_forecast_pipeline", lambda *args, **kwargs: pipeline_result)
    monkeypatch.setattr(portfolio_optimization, "get_market_caps", lambda tickers: {"AAPL": 1e12, "MSFT": 1e12})
    monkeypatch.setattr(
        portfolio_optimization,
        "_latest_market_caps_are_point_in_time_compatible",
        lambda end_date: True,
    )
    monkeypatch.setattr(portfolio_optimization, "get_market_implied_risk_aversion_cached", lambda *args, **kwargs: 2.5)
    monkeypatch.setattr(portfolio_optimization.black_litterman, "market_implied_prior_returns", lambda *args, **kwargs: market_prior)
    monkeypatch.setattr(portfolio_optimization, "BlackLittermanModel", FakeBlackLittermanModel)
    monkeypatch.setattr(portfolio_optimization, "EfficientFrontier", FakeEfficientFrontier)
    monkeypatch.setattr(portfolio_optimization, "get_asset_names", lambda tickers: {ticker: ticker for ticker in tickers})

    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=["AAPL", "MSFT"],
        optimization_method="BL",
        forecast_method="ARIMA_TRANSFORMER",
    )

    assert captured["absolute_views"]["AAPL"] == pytest.approx(0.24)
    assert captured["absolute_views"]["MSFT"] == pytest.approx(0.08)
    assert captured["omega"][0, 0] == pytest.approx(0.16)
    assert captured["omega"][1, 1] == pytest.approx(0.16)
    assert captured["optimizer_mu"]["AAPL"] == pytest.approx(0.24)
    assert result["prior_expected_returns"]["AAPL"] == pytest.approx(0.08)
    assert result["return_confidence"]["AAPL"] == pytest.approx(0.5)


def test_price_alignment_does_not_backfill_pre_listing_history():
    dates = pd.date_range("2020-01-01", periods=6, freq="B")
    prices = pd.DataFrame(
        {
            "OLD": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
            "NEW": [np.nan, np.nan, np.nan, 20.0, 21.0, 22.0],
        },
        index=dates,
    )

    aligned = portfolio_optimization._align_price_history_without_lookahead(
        prices
    )

    assert aligned.index[0] == dates[3]
    assert list(aligned["NEW"]) == [20.0, 21.0, 22.0]
    assert len(aligned) == 3


def test_pipeline_reports_per_ticker_data_eligibility(monkeypatch):
    dates = pd.date_range(end="2024-12-31", periods=60, freq="B")
    prices = pd.DataFrame(
        {
            "AAPL": np.linspace(100.0, 120.0, len(dates)),
            "MSFT": np.linspace(200.0, 230.0, len(dates)),
            "NEW": [np.nan] * 40 + list(np.linspace(20.0, 25.0, 20)),
            "STALE": list(np.linspace(30.0, 35.0, 40)) + [np.nan] * 20,
        },
        index=dates,
    )

    class FakeCovarianceShrinkage:
        def __init__(self, data):
            self.data = data

        def ledoit_wolf(self):
            tickers = list(self.data.columns)
            return pd.DataFrame(
                np.eye(len(tickers)),
                index=tickers,
                columns=tickers,
            )

    monkeypatch.setattr(
        portfolio_optimization,
        "get_stock_data",
        lambda *args, **kwargs: prices,
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "_convert_price_data_to_usd",
        lambda data, *args: (data, {}, []),
    )
    monkeypatch.setattr(
        portfolio_optimization.risk_models,
        "CovarianceShrinkage",
        FakeCovarianceShrinkage,
    )
    portfolio_optimization.get_cache().clear()

    result = portfolio_optimization.data_and_forecast_pipeline(
        start_date="2024-10-01",
        end_date="2024-12-31",
        ticker_group=None,
        tickers=["AAPL", "MSFT", "NEW", "STALE"],
        forecast_method="HISTORICAL",
        min_history=30,
    )

    eligibility = result["data_eligibility"]
    assert result["tickers"] == ["AAPL", "MSFT"]
    assert eligibility["eligible_tickers"] == ["AAPL", "MSFT"]
    assert eligibility["dropped_tickers"] == ["NEW", "STALE"]
    assert eligibility["eligible_count"] == 2
    assert eligibility["dropped_count"] == 2
    assert eligibility["aligned_observation_count"] == 60
    assert eligibility["ticker_diagnostics"]["AAPL"]["coverage_rate"] == 1.0
    assert eligibility["ticker_diagnostics"]["NEW"]["drop_reasons"] == [
        {
            "reason": "insufficient_history",
            "stage": "minimum_history",
        }
    ]
    assert eligibility["ticker_diagnostics"]["STALE"]["drop_reasons"] == [
        {"reason": "stale_price", "stage": "liveness"}
    ]


def test_pipeline_error_reports_missing_and_insufficient_tickers(monkeypatch):
    dates = pd.date_range(end="2024-12-31", periods=20, freq="B")
    prices = pd.DataFrame(
        {"SHORT": np.linspace(10.0, 11.0, len(dates))},
        index=dates,
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "get_stock_data",
        lambda *args, **kwargs: prices,
    )
    portfolio_optimization.get_cache().clear()

    result = portfolio_optimization.data_and_forecast_pipeline(
        start_date="2024-12-01",
        end_date="2024-12-31",
        ticker_group=None,
        tickers=["SHORT", "MISSING"],
        forecast_method="HISTORICAL",
        min_history=30,
    )

    assert "error" in result
    eligibility = result["data_eligibility"]
    assert eligibility["eligible_count"] == 0
    assert eligibility["dropped_tickers"] == ["SHORT", "MISSING"]
    assert eligibility["ticker_diagnostics"]["SHORT"]["drop_reasons"] == [
        {
            "reason": "insufficient_history",
            "stage": "minimum_history",
        }
    ]
    assert eligibility["ticker_diagnostics"]["MISSING"]["drop_reasons"] == [
        {"reason": "no_price_data", "stage": "fetch"}
    ]


def test_historical_run_does_not_fetch_latest_market_caps(monkeypatch):
    pipeline_result = {
        "mu": pd.Series({"AAPL": 0.10, "MSFT": 0.08}),
        "prior_mu": pd.Series({"AAPL": 0.08, "MSFT": 0.07}),
        "S": pd.DataFrame(
            [[0.04, 0.005], [0.005, 0.02]],
            index=["AAPL", "MSFT"],
            columns=["AAPL", "MSFT"],
        ),
        "uncertainties": pd.Series({"AAPL": 0.10, "MSFT": 0.10}),
        "tickers": ["AAPL", "MSFT"],
        "latest_prices": {"AAPL": 150.0, "MSFT": 200.0},
    }
    market_caps = MagicMock(return_value={"AAPL": 1e12, "MSFT": 1e12})
    monkeypatch.setattr(
        portfolio_optimization,
        "data_and_forecast_pipeline",
        lambda *args, **kwargs: pipeline_result,
    )
    monkeypatch.setattr(portfolio_optimization, "get_market_caps", market_caps)
    monkeypatch.setattr(
        portfolio_optimization,
        "get_asset_names",
        lambda tickers: {ticker: ticker for ticker in tickers},
    )

    result = portfolio_optimization.optimize_portfolio(
        start_date="2018-01-01",
        end_date="2020-12-31",
        risk_free_rate=0.02,
        tickers=["AAPL", "MSFT"],
        optimization_method="BL",
        forecast_method="HISTORICAL",
        max_asset_weight=1.0,
    )

    assert "error" not in result
    assert market_caps.call_count == 0
    assert result["market_prior_source"] == "historical_return_fallback"


def test_latest_market_cap_compatibility_is_date_bounded():
    assert portfolio_optimization._latest_market_caps_are_point_in_time_compatible(
        "2026-07-20",
        reference_date="2026-07-23",
    )
    assert not portfolio_optimization._latest_market_caps_are_point_in_time_compatible(
        "2024-12-31",
        reference_date="2026-07-23",
    )


def test_reported_performance_uses_returned_weights():
    mu = pd.Series({"A": 0.10, "B": 0.04})
    covariance = pd.DataFrame(
        [[0.04, 0.0], [0.0, 0.01]],
        index=mu.index,
        columns=mu.index,
    )

    expected_return, volatility, sharpe = (
        portfolio_optimization._performance_for_weights(
            {"A": 0.25, "B": 0.75},
            mu,
            covariance,
            risk_free_rate=0.02,
        )
    )

    assert expected_return == pytest.approx(0.055)
    assert volatility == pytest.approx(
        np.sqrt(0.25 ** 2 * 0.04 + 0.75 ** 2 * 0.01)
    )
    assert sharpe == pytest.approx((expected_return - 0.02) / volatility)


def test_regression_endpoint_returns_error_status_for_empty_market_data():
    stock = MagicMock()
    stock.history.return_value = pd.DataFrame()

    app_module.app.config["TESTING"] = True
    with patch("app.yf.Ticker", return_value=stock):
        response = app_module.app.test_client().get("/get-data?regression=true&ticker=BAD")

    assert response.status_code == 502
    assert "error" in response.get_json()


def test_api_prefixed_regression_endpoint_matches_public_contract():
    stock = MagicMock()
    stock.history.return_value = pd.DataFrame()

    app_module.app.config["TESTING"] = True
    with patch("app.yf.Ticker", return_value=stock):
        response = app_module.app.test_client().get("/api/get-data?regression=true&ticker=BAD")

    assert response.status_code == 502
    assert "error" in response.get_json()


def test_stock_data_endpoint_rejects_unsafe_ticker_input():
    app_module.app.config["TESTING"] = True
    response = app_module.app.test_client().get("/api/get-data?ticker=../AAPL")

    assert response.status_code == 400
    assert "invalid characters" in response.get_json()["error"]


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


def _reset_optimization_jobs():
    with app_module.OPTIMIZATION_JOBS_LOCK:
        for job in app_module.OPTIMIZATION_JOBS.values():
            job.cancel_event.set()
        app_module.OPTIMIZATION_JOBS.clear()


def _optimization_payload(request_id="job-test"):
    return {
        "request_id": request_id,
        "portfolio_id": request_id,
        "persist_result": True,
        "load_if_available": True,
        "ticker_group": "SP500",
        "start_date": "2024-01-01",
        "end_date": "2024-03-01",
        "risk_free_rate": 0.02,
        "forecast_method": "LIGHTWEIGHT",
        "optimization_method": "BL",
        "forecast_horizon": 63,
        "min_history": 30,
        "bl_tau": 0.05,
    }


def test_optimize_portfolio_request_id_is_idempotent(monkeypatch):
    _reset_optimization_jobs()
    app_module.app.config["TESTING"] = True
    monkeypatch.setattr(app_module, "start_optimization_reaper_once", lambda: None)
    calls = []

    def fake_optimize_portfolio(**kwargs):
        calls.append(kwargs)
        return {
            "weights": {"AAPL": 1.0},
            "return": 0.1,
            "risk": 0.2,
            "sharpe_ratio": 0.5,
            "prices": {"AAPL": 100.0},
        }

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(app_module, "optimize_portfolio", fake_optimize_portfolio)
    monkeypatch.setattr(app_module.threading, "Thread", ImmediateThread)

    client = app_module.app.test_client()
    first = client.post("/api/optimize-portfolio", json=_optimization_payload("idempotent-job"))
    second = client.post("/api/optimize-portfolio", json=_optimization_payload("idempotent-job"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(calls) == 1
    assert second.get_json()["status"] == "completed"


def test_optimization_job_status_reflects_latest_progress(monkeypatch):
    _reset_optimization_jobs()
    monkeypatch.setattr(app_module, "start_optimization_reaper_once", lambda: None)
    job, _ = app_module.ensure_optimization_job("progress-job")

    app_module.push_progress("progress-job", 3, 10, "Fetching data", status="running")

    response = app_module.app.test_client().get("/api/optimization-jobs/progress-job")
    data = response.get_json()

    assert response.status_code == 200
    assert data["status"] == "running"
    assert data["progress"] == 30
    assert data["message"] == "Fetching data"
    assert job.last_client_seen_at >= job.created_at


def test_progress_stream_reconnect_receives_completed_snapshot(monkeypatch):
    _reset_optimization_jobs()
    monkeypatch.setattr(app_module, "start_optimization_reaper_once", lambda: None)
    app_module.ensure_optimization_job("completed-stream-job")
    app_module.push_progress(
        "completed-stream-job",
        100,
        100,
        "Optimization complete",
        status="completed",
        result={"weights": {"AAPL": 1.0}},
    )

    response = app_module.app.test_client().get("/api/progress-stream/completed-stream-job")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "event: complete" in body
    assert '"status": "completed"' in body
    assert '"weights": {"AAPL": 1.0}' in body


def test_cancel_endpoint_sets_cancel_event_and_checkpoint_marks_cancelled(monkeypatch):
    _reset_optimization_jobs()
    monkeypatch.setattr(app_module, "start_optimization_reaper_once", lambda: None)
    job, _ = app_module.ensure_optimization_job("cancel-job")

    response = app_module.app.test_client().post("/api/optimization-jobs/cancel-job/cancel")
    assert response.status_code == 200
    assert job.cancel_event.is_set()

    app_module.push_progress("cancel-job", 0, 0, "Optimization cancelled", status="cancelled")
    status_response = app_module.app.test_client().get("/api/optimization-jobs/cancel-job")

    assert status_response.status_code == 200
    assert status_response.get_json()["status"] == "cancelled"


def test_completed_job_status_can_fall_back_to_saved_result(tmp_path, monkeypatch):
    _reset_optimization_jobs()
    monkeypatch.setattr(portfolio_optimization, "RESULTS_DIR", tmp_path / "portfolio_results")

    portfolio_optimization.save_portfolio_result("saved-job", {"weights": {"AAPL": 1.0}})

    response = app_module.app.test_client().get("/api/optimization-jobs/saved-job")
    data = response.get_json()

    assert response.status_code == 200
    assert data["status"] == "completed"
    assert data["result"]["weights"] == {"AAPL": 1.0}


def test_optimization_cancel_event_stops_before_fetch(monkeypatch):
    cancel_event = app_module.threading.Event()
    cancel_event.set()

    with pytest.raises(portfolio_optimization.OptimizationCancelled):
        portfolio_optimization.get_stock_data(
            ["AAPL"],
            "2024-01-01",
            "2024-02-01",
            cancel_event=cancel_event,
        )
