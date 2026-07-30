import logging
import os
import sys

import numpy as np
import pandas as pd


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

import portfolio_optimization


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _multi_ticker_close_frame(values_by_ticker):
    index = pd.to_datetime(["2024-01-02", "2024-01-03"])
    columns = pd.MultiIndex.from_tuples(
        [("Close", ticker) for ticker in values_by_ticker],
        names=["Price", "Ticker"],
    )
    values = np.column_stack(list(values_by_ticker.values()))
    return pd.DataFrame(values, index=index, columns=columns)


def test_get_stock_data_retries_all_nan_ticker_and_closes_session(monkeypatch):
    session = FakeSession()
    calls = []

    def fake_download(tickers, **kwargs):
        calls.append((tickers, kwargs))
        if list(tickers) == ["AAPL", "MSFT"]:
            return _multi_ticker_close_frame(
                {
                    "AAPL": [100.0, 101.0],
                    "MSFT": [np.nan, np.nan],
                }
            )
        assert list(tickers) == ["MSFT"]
        return _multi_ticker_close_frame({"MSFT": [200.0, 202.0]})

    monkeypatch.setattr(portfolio_optimization, "_configure_yfinance_runtime", lambda: None)
    monkeypatch.setattr(portfolio_optimization, "_create_yfinance_session", lambda: session)
    monkeypatch.setattr(portfolio_optimization.yf, "download", fake_download)

    result = portfolio_optimization.get_stock_data.__wrapped__(
        ["AAPL", "MSFT"],
        "2024-01-01",
        "2024-02-01",
    )

    assert list(result.columns) == ["AAPL", "MSFT"]
    assert result["MSFT"].tolist() == [200.0, 202.0]
    assert len(calls) == 2
    assert all(call_kwargs["threads"] is False for _, call_kwargs in calls)
    assert all(call_kwargs["session"] is session for _, call_kwargs in calls)
    assert session.closed is True


def test_yfinance_session_uses_certifi_ca_bundle(monkeypatch):
    expected_session = FakeSession()
    observed_kwargs = {}

    def fake_session_factory(**kwargs):
        observed_kwargs.update(kwargs)
        return expected_session

    monkeypatch.setattr(portfolio_optimization.certifi, "where", lambda: "/safe/ca.pem")
    monkeypatch.setattr(portfolio_optimization.curl_requests, "Session", fake_session_factory)

    session = portfolio_optimization._create_yfinance_session()

    assert session is expected_session
    assert observed_kwargs == {
        "impersonate": "chrome",
        "verify": "/safe/ca.pem",
    }


def test_yfinance_cache_uses_explicit_writable_location(tmp_path, monkeypatch):
    configured_locations = []
    cache_dir = tmp_path / "yfinance-cache"

    monkeypatch.setenv("ANTIFIER_YFINANCE_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(portfolio_optimization, "_YFINANCE_RUNTIME_CONFIGURED", False)
    monkeypatch.setattr(
        portfolio_optimization.yf,
        "set_tz_cache_location",
        configured_locations.append,
    )

    portfolio_optimization._configure_yfinance_runtime()

    assert cache_dir.is_dir()
    assert configured_locations == [str(cache_dir)]


def test_get_stock_data_reports_and_omits_ticker_missing_after_retries(
    monkeypatch,
    caplog,
):
    session = FakeSession()

    def fake_download(tickers, **_kwargs):
        if list(tickers) == ["AAPL", "MSFT"]:
            return _multi_ticker_close_frame(
                {
                    "AAPL": [100.0, 101.0],
                    "MSFT": [np.nan, np.nan],
                }
            )
        return pd.DataFrame()

    monkeypatch.setattr(portfolio_optimization, "_configure_yfinance_runtime", lambda: None)
    monkeypatch.setattr(portfolio_optimization, "_create_yfinance_session", lambda: session)
    monkeypatch.setattr(portfolio_optimization.yf, "download", fake_download)
    monkeypatch.setattr(portfolio_optimization.time, "sleep", lambda _seconds: None)

    with caplog.at_level(logging.WARNING):
        result = portfolio_optimization.get_stock_data.__wrapped__(
            ["AAPL", "MSFT"],
            "2024-01-01",
            "2024-02-01",
        )

    assert list(result.columns) == ["AAPL"]
    assert "Missing 1 tickers after retries: MSFT" in caplog.text
    assert "Final missing tickers: MSFT" in caplog.text
    assert session.closed is True


def test_get_stock_data_closes_session_when_download_raises(monkeypatch):
    session = FakeSession()

    def raise_network_error(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(portfolio_optimization, "_configure_yfinance_runtime", lambda: None)
    monkeypatch.setattr(portfolio_optimization, "_create_yfinance_session", lambda: session)
    monkeypatch.setattr(portfolio_optimization.yf, "download", raise_network_error)
    monkeypatch.setattr(portfolio_optimization.time, "sleep", lambda _seconds: None)

    result = portfolio_optimization.get_stock_data.__wrapped__(
        ["AAPL"],
        "2024-01-01",
        "2024-02-01",
    )

    assert result.empty
    assert session.closed is True
