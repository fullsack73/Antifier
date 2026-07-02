import os
import sys

import numpy as np
import pandas as pd
import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

import app as app_module
import hedge_analysis


def _prices_from_returns(returns, start="2024-01-02"):
    values = 100 * np.cumprod([1.0] + [1 + value for value in returns])
    return pd.DataFrame(
        {"Close": values},
        index=pd.date_range(start, periods=len(values), freq="B"),
    )


class FakeTicker:
    histories = {}
    names = {}
    fail_info = set()

    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, start=None, end=None):
        data = self.histories.get(self.ticker)
        if data is None:
            return pd.DataFrame()
        return data

    @property
    def info(self):
        if self.ticker in self.fail_info:
            raise RuntimeError("info unavailable")
        return {"longName": self.names.get(self.ticker, self.ticker)}


def test_pairs_analysis_returns_correlation_and_regression(monkeypatch):
    base_returns = np.linspace(-0.02, 0.02, 35)
    inverse_returns = -0.6 * base_returns + 0.001
    FakeTicker.histories = {
        "AAPL": _prices_from_returns(inverse_returns),
        "MSFT": _prices_from_returns(base_returns),
    }
    FakeTicker.names = {"AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation"}
    FakeTicker.fail_info = set()
    monkeypatch.setattr(hedge_analysis.yf, "Ticker", FakeTicker)

    result = hedge_analysis.analyze_hedge_relationship("AAPL", "MSFT", "2024-01-02", "2024-03-15")

    assert result["analysis_type"] == "pairs_correlation_regression"
    assert "is_hedge" not in result
    assert result["ticker1"] == "AAPL"
    assert result["ticker2"] == "MSFT"
    assert result["company1"] == "Apple Inc."
    assert result["company2"] == "Microsoft Corporation"
    assert result["observations"] >= hedge_analysis.MIN_COMMON_OBSERVATIONS
    assert result["correlation"] < -0.99
    assert result["correlation_signal"]["direction"] == "Negative"
    assert result["regression"]["beta"] == pytest.approx(-0.6)
    assert result["regression"]["r_squared"] == pytest.approx(1.0)


def test_pairs_analysis_rejects_same_ticker():
    with pytest.raises(hedge_analysis.HedgeAnalysisInputError, match="must be different"):
        hedge_analysis.analyze_hedge_relationship("AAPL", "AAPL", "2024-01-02", "2024-03-15")


def test_pairs_analysis_rejects_insufficient_overlap(monkeypatch):
    FakeTicker.histories = {
        "AAPL": _prices_from_returns([0.01, 0.02, -0.01]),
        "MSFT": _prices_from_returns([0.02, -0.01, 0.01]),
    }
    FakeTicker.names = {}
    FakeTicker.fail_info = set()
    monkeypatch.setattr(hedge_analysis.yf, "Ticker", FakeTicker)

    with pytest.raises(hedge_analysis.HedgeAnalysisInputError, match="overlapping daily returns"):
        hedge_analysis.analyze_hedge_relationship("AAPL", "MSFT", "2024-01-02", "2024-01-10")


def test_pairs_analysis_handles_missing_company_info(monkeypatch):
    base_returns = np.linspace(-0.01, 0.012, 25)
    FakeTicker.histories = {
        "AAPL": _prices_from_returns(base_returns),
        "MSFT": _prices_from_returns(base_returns * 0.8),
    }
    FakeTicker.names = {"MSFT": "Microsoft Corporation"}
    FakeTicker.fail_info = {"AAPL"}
    monkeypatch.setattr(hedge_analysis.yf, "Ticker", FakeTicker)

    result = hedge_analysis.analyze_hedge_relationship("AAPL", "MSFT", "2024-01-02", "2024-03-01")

    assert result["company1"] == "AAPL"
    assert result["company2"] == "Microsoft Corporation"


def test_analyze_hedge_endpoint_maps_domain_errors(monkeypatch):
    app_module.app.config["TESTING"] = True

    def raise_input(*_args, **_kwargs):
        raise hedge_analysis.HedgeAnalysisInputError("bad pair")

    monkeypatch.setattr(app_module, "analyze_hedge_relationship", raise_input)
    response = app_module.app.test_client().get("/api/analyze-hedge?ticker1=AAPL&ticker2=MSFT")
    assert response.status_code == 400
    assert response.get_json()["error"] == "bad pair"

    def raise_empty(*_args, **_kwargs):
        raise hedge_analysis.HedgeDataUnavailableError("No price data available for MSFT")

    monkeypatch.setattr(app_module, "analyze_hedge_relationship", raise_empty)
    response = app_module.app.test_client().get("/api/analyze-hedge?ticker1=AAPL&ticker2=MSFT")
    assert response.status_code == 404
    assert response.get_json()["error"] == "No price data available for MSFT"

    def raise_upstream(*_args, **_kwargs):
        raise hedge_analysis.HedgeUpstreamError("provider timeout")

    monkeypatch.setattr(app_module, "analyze_hedge_relationship", raise_upstream)
    response = app_module.app.test_client().get("/api/analyze-hedge?ticker1=AAPL&ticker2=MSFT")
    assert response.status_code == 502
    assert response.get_json()["error"] == "Market data provider failed while analyzing the pair"
