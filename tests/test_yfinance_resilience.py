import logging
import os
import sys

import numpy as np
import pandas as pd
import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

import portfolio_optimization
import cache_manager


@pytest.fixture(autouse=True)
def isolated_yahoo_session(monkeypatch):
    monkeypatch.setattr(portfolio_optimization, "_YFINANCE_SESSION", None)
    yield
    portfolio_optimization._close_yfinance_session()


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


def test_get_stock_data_retries_all_nan_ticker_and_keeps_shared_session(monkeypatch):
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
    assert session.closed is False


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
    assert session.closed is False


def test_get_stock_data_keeps_shared_session_when_download_raises(monkeypatch):
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
    assert session.closed is False


def test_bl_fetches_share_live_session_after_price_download(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    sessions = []
    cache = MagicMock()
    cache.get.return_value = None

    def new_session():
        session = FakeSession()
        sessions.append(session)
        return session

    def download(tickers, **kwargs):
        assert kwargs['session'] is sessions[-1]
        assert not kwargs['session'].closed
        if tickers == '^GSPC':
            assert kwargs['timeout'] == portfolio_optimization.YFINANCE_REQUEST_TIMEOUT_SECONDS
            return pd.DataFrame({'Close': [100.0, 101.0, 99.0, 103.0]})
        return _multi_ticker_close_frame({'MSFT': [100.0, 101.0]})

    def tickers(symbols, session=None):
        assert not sessions[0].closed
        assert session is sessions[-1] and not session.closed
        return SimpleNamespace(tickers={
            symbol: SimpleNamespace(info={'marketCap': 1e12, 'currency': 'USD'})
            for symbol in symbols.split()
        })

    monkeypatch.setattr(portfolio_optimization, 'get_cache', lambda: cache)
    monkeypatch.setattr(cache_manager, 'get_cache', lambda: cache)
    monkeypatch.setattr(portfolio_optimization, '_configure_yfinance_runtime', lambda: None)
    monkeypatch.setattr(portfolio_optimization, '_create_yfinance_session', new_session)
    monkeypatch.setattr(portfolio_optimization.yf, 'download', download)
    monkeypatch.setattr(portfolio_optimization.yf, 'Tickers', tickers)
    monkeypatch.setattr(
        portfolio_optimization.black_litterman, 'market_implied_risk_aversion',
        lambda prices, **kwargs: 3.0,
    )

    portfolio_optimization.get_stock_data.__wrapped__(['MSFT'], '2024-01-01', '2024-02-01')
    assert portfolio_optimization.get_market_caps(['MSFT']) == {'MSFT': 1e12}
    assert portfolio_optimization.get_market_implied_risk_aversion_cached(
        '2024-01-01', '2024-02-01', 0.03,
    ) == 3.0
    assert len(sessions) == 1 and not sessions[0].closed
    assert cache.get.call_args_list[0].args[0].startswith('get_market_caps_session_v2_')
    assert cache.get.call_args_list[1].args[0].startswith('bl_delta_session_v2_')


def test_market_caps_retry_empty_results_and_cache_success(monkeypatch, caplog):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    stored = {}
    cache = MagicMock()
    cache.get.side_effect = stored.get
    cache.set.side_effect = lambda key, value, **kwargs: stored.update({key: value})
    calls = []
    sessions = []

    def new_session():
        session = FakeSession()
        sessions.append(session)
        return session

    def tickers(symbols, session=None):
        calls.append(symbols)
        if len(calls) == 1:
            raise RuntimeError('temporary Yahoo failure')
        return SimpleNamespace(tickers={
            'MSFT': SimpleNamespace(info={'marketCap': 1e12, 'currency': 'USD'}),
        })

    monkeypatch.setattr(portfolio_optimization, 'get_cache', lambda: cache)
    monkeypatch.setattr(cache_manager, 'get_cache', lambda: cache)
    monkeypatch.setattr(portfolio_optimization, '_configure_yfinance_runtime', lambda: None)
    monkeypatch.setattr(portfolio_optimization, '_create_yfinance_session', new_session)
    monkeypatch.setattr(portfolio_optimization.yf, 'Tickers', tickers)

    with caplog.at_level(logging.WARNING):
        assert portfolio_optimization.get_market_caps(['MSFT']) == {}
    assert not stored
    assert 'temporary Yahoo failure' in caplog.text
    assert portfolio_optimization.get_market_caps(['MSFT']) == {'MSFT': 1e12}
    assert portfolio_optimization.get_market_caps(['MSFT']) == {'MSFT': 1e12}
    assert len(calls) == 2
    cache.set.assert_called_once()
    assert cache.set.call_args.kwargs == {'l1_ttl': 86400, 'l2_ttl': 604800}
    assert len(sessions) == 1 and not sessions[0].closed


def test_market_caps_log_per_ticker_failures_and_keep_available_caps(monkeypatch, caplog):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    class BrokenQuote:
        @property
        def info(self):
            raise RuntimeError('Session is closed, cannot send request.')

    session = FakeSession()
    cache = MagicMock()
    cache.get.return_value = None
    monkeypatch.setattr(portfolio_optimization, 'get_cache', lambda: cache)
    monkeypatch.setattr(cache_manager, 'get_cache', lambda: cache)
    monkeypatch.setattr(portfolio_optimization, '_configure_yfinance_runtime', lambda: None)
    monkeypatch.setattr(portfolio_optimization, '_create_yfinance_session', lambda: session)
    monkeypatch.setattr(portfolio_optimization.yf, 'Tickers', lambda *args, **kwargs: SimpleNamespace(
        tickers={'BAD': BrokenQuote(), 'MSFT': SimpleNamespace(
            info={'marketCap': 1e12, 'currency': 'USD'},
        )},
    ))
    with caplog.at_level(logging.WARNING):
        assert portfolio_optimization.get_market_caps(['BAD', 'MSFT']) == {'MSFT': 1e12}
    assert 'Market cap fetch failed for BAD: Session is closed' in caplog.text
    assert not session.closed


def test_yahoo_session_survives_cancel_and_closes_at_shutdown(monkeypatch):
    session = FakeSession()
    created = []

    def create():
        created.append(session)
        return session

    monkeypatch.setattr(portfolio_optimization, '_configure_yfinance_runtime', lambda: None)
    monkeypatch.setattr(portfolio_optimization, '_create_yfinance_session', create)
    with pytest.raises(portfolio_optimization.OptimizationCancelled):
        with portfolio_optimization._managed_yfinance_session():
            raise portfolio_optimization.OptimizationCancelled('cancelled')
    assert not session.closed
    with portfolio_optimization._managed_yfinance_session() as borrowed:
        assert borrowed is session
    assert created == [session]
    portfolio_optimization._close_yfinance_session()
    assert session.closed


def test_concurrent_yahoo_borrowers_share_one_live_session(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from unittest.mock import MagicMock

    factory = MagicMock(side_effect=FakeSession)
    barrier = Barrier(4)
    monkeypatch.setattr(portfolio_optimization, '_configure_yfinance_runtime', lambda: None)
    monkeypatch.setattr(portfolio_optimization, '_create_yfinance_session', factory)

    def borrow(_):
        with portfolio_optimization._managed_yfinance_session() as session:
            barrier.wait(timeout=5)
            assert not session.closed
            return session

    with ThreadPoolExecutor(max_workers=4) as pool:
        sessions = list(pool.map(borrow, range(4)))
    factory.assert_called_once()
    assert all(session is sessions[0] and not session.closed for session in sessions)


@pytest.mark.parametrize('regression', [False, True])
def test_app_chart_and_regression_after_optimizer_price_fetch(monkeypatch, regression):
    import app as app_module
    from yfinance.data import YfData

    data = YfData()
    # Restore yfinance's original session after this test closes its own session.
    monkeypatch.setattr(data, '_session', data._session)
    history = pd.DataFrame(
        {'Close': np.linspace(100.0, 120.0, 80)},
        index=pd.date_range('2024-01-02', periods=80, freq='B'),
    )
    observed = []

    def check_session():
        assert data._session is portfolio_optimization._YFINANCE_SESSION
        data._session._check_session_closed()
        observed.append(data._session)

    def download(*args, session=None, **kwargs):
        portfolio_optimization.yf.Ticker('AAPL', session=session)
        check_session()
        return history.copy()

    def ticker_history(self, *args, **kwargs):
        check_session()
        return history.copy()

    def ticker_info(self):
        check_session()
        return {'longName': 'Apple', 'currency': 'USD'}

    monkeypatch.setattr(portfolio_optimization, '_configure_yfinance_runtime', lambda: None)
    monkeypatch.setattr(portfolio_optimization.yf, 'download', download)
    monkeypatch.setattr(portfolio_optimization.yf.Ticker, 'history', ticker_history)
    monkeypatch.setattr(portfolio_optimization.yf.Ticker, 'info', property(ticker_info))
    monkeypatch.setattr(app_module, 'forecast_single_ticker_with_transformer',
                        lambda *args, **kwargs: {'expected_return': 0.08, 'uncertainty': 0.2})

    prices = portfolio_optimization.get_stock_data.__wrapped__(['AAPL'], '2024-01-01', '2024-06-01')
    assert not prices.empty
    response = app_module.app.test_client().get('/api/get-data', query_string={
        'ticker': 'AAPL', 'start_date': '2024-01-01', 'end_date': '2024-06-01',
        'regression': str(regression).lower(), 'model': 'TRANSFORMER', 'future_days': 3,
    })
    assert response.status_code == 200, response.get_json()
    assert len(response.get_json()['prices']) == 80
    if regression:
        assert len(response.get_json()['future_predictions']) == 3
    assert len(observed) >= 3
    assert all(session is observed[0] and not session._closed for session in observed)


def test_raw_history_preserves_gaps_and_uses_separate_cache_key(monkeypatch):
    session = FakeSession()
    raw = _multi_ticker_close_frame({'AAPL': [100., np.nan], 'MSFT': [200., 201.]})
    monkeypatch.setattr(portfolio_optimization, '_configure_yfinance_runtime', lambda: None)
    monkeypatch.setattr(portfolio_optimization, '_create_yfinance_session', lambda: session)
    monkeypatch.setattr(portfolio_optimization.yf, 'download', lambda *args, **kwargs: raw.copy())
    standard = portfolio_optimization.get_stock_data.__wrapped__(['AAPL', 'MSFT'], '2024-01-01', '2024-02-01')
    untouched = portfolio_optimization.get_stock_data.__wrapped__(['AAPL', 'MSFT'], '2024-01-01', '2024-02-01', preserve_missing=True)
    assert standard['AAPL'].iloc[-1] == 100.
    assert np.isnan(untouched['AAPL'].iloc[-1])
    assert portfolio_optimization._stock_data_key_func(['AAPL'], '2024-01-01', '2024-02-01') != portfolio_optimization._stock_data_key_func(['AAPL'], '2024-01-01', '2024-02-01', preserve_missing=True)
