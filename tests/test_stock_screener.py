import os
import sys
import logging
import uuid


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

import stock_screener


class FakeTicker:
    pass


def _fake_score_summary(ticker_symbol, ticker=None):
    scores = {
        "AAPL": 67,
        "MSFT": 82,
        "LOW": 49,
        "NODATA": None,
    }
    score = scores[ticker_symbol]
    label = "INSUFFICIENT DATA" if score is None else "BUY"

    return {
        "info": {
            "currentPrice": 100,
            "currency": "USD",
        },
        "company": {
            "name": f"{ticker_symbol} Inc.",
            "sector": "Technology",
            "industry": "Software",
            "currency": "USD",
            "market_cap": 1_000_000_000,
        },
        "decision": {
            "score": score,
            "max_score": 100,
            "available_metrics": 12 if score is not None else 0,
            "total_metrics": 16,
            "confidence": 75 if score is not None else 0,
            "label": label,
        },
        "metrics": [
            {"key": "per", "value": 30},
            {"key": "forward_pe", "value": 25},
            {"key": "pbr", "value": 5},
            {"key": "psr", "value": 7},
            {"key": "peg", "value": 2},
            {"key": "debt_to_equity", "value": 0.4},
            {"key": "roe", "value": 0.2},
            {"key": "roa", "value": 0.1},
            {"key": "profit_margin", "value": 0.15},
        ],
    }


def test_search_stocks_filters_by_financial_score(monkeypatch):
    monkeypatch.setattr(stock_screener.yf, "Ticker", lambda _ticker: FakeTicker())
    monkeypatch.setattr(stock_screener, "build_financial_decision_summary", _fake_score_summary)

    results = stock_screener.search_stocks({
        "Index": "Custom",
        "tickers": ["AAPL", "MSFT", "LOW", "NODATA"],
        "criteria": [
            {"metric": "Financial Score", "operator": "Over", "value": "65"}
        ],
    })

    assert {row["Ticker"] for row in results} == {"AAPL", "MSFT"}
    assert {row["Financial Score"] for row in results} == {67, 82}
    assert all(row["P/E"] == 30 for row in results)
    assert all(row["Score Confidence"] == 75 for row in results)


def test_search_stocks_can_filter_below_financial_score(monkeypatch):
    monkeypatch.setattr(stock_screener.yf, "Ticker", lambda _ticker: FakeTicker())
    monkeypatch.setattr(stock_screener, "build_financial_decision_summary", _fake_score_summary)

    results = stock_screener.search_stocks({
        "Index": "Custom",
        "tickers": ["AAPL", "MSFT", "LOW", "NODATA"],
        "criteria": [
            {"metric": "Financial Score", "operator": "Under", "value": "50"}
        ],
    })

    assert [row["Ticker"] for row in results] == ["LOW"]
    assert results[0]["Financial Score"] == 49


def test_search_stocks_accepts_financial_score_aliases(monkeypatch):
    monkeypatch.setattr(stock_screener.yf, "Ticker", lambda _ticker: FakeTicker())
    monkeypatch.setattr(stock_screener, "build_financial_decision_summary", _fake_score_summary)

    results = stock_screener.search_stocks({
        "Index": "Custom",
        "tickers": ["AAPL", "MSFT", "LOW", "NODATA"],
        "criteria": [
            {"metric": "financial_score", "operator": "gte", "value": "67"}
        ],
    })

    assert [row["Ticker"] for row in results] == ["MSFT", "AAPL"]
    assert {row["Financial Score"] for row in results} == {67, 82}


def test_apply_filters_accepts_api_style_score_alias():
    df = stock_screener.pd.DataFrame([
        {"Ticker": "AAPL", "Financial Score": 67},
        {"Ticker": "MSFT", "Financial Score": 82},
        {"Ticker": "LOW", "Financial Score": 49},
    ])

    results = stock_screener.apply_filters(df, [
        {"metric": "score", "operator": "lt", "value": "50"}
    ])

    assert results.to_dict("records") == [
        {"Ticker": "LOW", "Financial Score": 49}
    ]


def test_fetch_single_stock_data_treats_yfinance_failure_as_missing(monkeypatch):
    monkeypatch.setattr(stock_screener.yf, "Ticker", lambda _ticker: FakeTicker())

    def raise_yfinance_error(_ticker_symbol, ticker=None):
        raise Exception("HTTP Error 401: Invalid Crumb")

    monkeypatch.setattr(stock_screener, "build_financial_decision_summary", raise_yfinance_error)

    assert stock_screener.fetch_single_stock_data("BAD") is None


def test_fetch_universe_data_quiets_and_restores_yfinance_logger(monkeypatch):
    yfinance_logger = logging.getLogger("yfinance")
    original_level = yfinance_logger.level
    observed_levels = []

    def fake_fetch_single_stock_data(ticker):
        observed_levels.append(yfinance_logger.level)
        return {"Ticker": ticker, "Financial Score": 70}

    monkeypatch.setattr(stock_screener, "fetch_single_stock_data", fake_fetch_single_stock_data)
    yfinance_logger.setLevel(logging.ERROR)

    try:
        result = stock_screener.fetch_universe_data(["AAPL", "MSFT"])
        restored_level = yfinance_logger.level
    finally:
        yfinance_logger.setLevel(original_level)

    assert set(result["Ticker"]) == {"AAPL", "MSFT"}
    assert observed_levels
    assert all(level == logging.CRITICAL for level in observed_levels)
    assert restored_level == logging.ERROR


def test_custom_ticker_universe_reuses_cached_raw_data(monkeypatch):
    suffix = uuid.uuid4().hex
    first = f"CACHEA{suffix}"
    second = f"CACHEB{suffix}"
    fetch_calls = []

    def fake_fetch_universe_data(tickers):
        fetch_calls.append(tuple(tickers))
        return stock_screener.pd.DataFrame([
            {"Ticker": first, "Financial Score": 80},
            {"Ticker": second, "Financial Score": 60},
        ])

    monkeypatch.setattr(stock_screener, "fetch_universe_data", fake_fetch_universe_data)

    filters = {
        "Index": "Custom",
        "tickers": [first, second],
        "criteria": [
            {"metric": "Financial Score", "operator": "Over", "value": "70"}
        ],
    }
    reordered_filters = {
        **filters,
        "tickers": [second.lower(), first.lower()],
    }

    first_results = stock_screener.search_stocks(filters)
    second_results = stock_screener.search_stocks(reordered_filters)

    assert [row["Ticker"] for row in first_results] == [first]
    assert [row["Ticker"] for row in second_results] == [first]
    assert fetch_calls == [(first.upper(), second.upper())]


def test_custom_ticker_universe_does_not_cache_empty_fetch(monkeypatch):
    suffix = uuid.uuid4().hex
    ticker = f"EMPTY{suffix}"
    fetch_calls = []

    def fake_fetch_universe_data(tickers):
        fetch_calls.append(tuple(tickers))
        if len(fetch_calls) == 1:
            return stock_screener.pd.DataFrame()
        return stock_screener.pd.DataFrame([
            {"Ticker": ticker, "Financial Score": 80},
        ])

    monkeypatch.setattr(stock_screener, "fetch_universe_data", fake_fetch_universe_data)

    filters = {
        "Index": "Custom",
        "tickers": [ticker],
        "criteria": [
            {"metric": "Financial Score", "operator": "Over", "value": "70"}
        ],
    }

    assert stock_screener.search_stocks(filters) == []
    assert [row["Ticker"] for row in stock_screener.search_stocks(filters)] == [ticker]
    assert fetch_calls == [(ticker.upper(),), (ticker.upper(),)]


def test_fetch_universe_data_warns_when_all_tickers_fail(monkeypatch, caplog):
    monkeypatch.setattr(stock_screener, "fetch_single_stock_data", lambda _ticker: None)
    caplog.set_level(logging.WARNING, logger="stock_screener")

    result = stock_screener.fetch_universe_data(["AAPL", "MSFT"])

    assert result.empty
    assert "No stock screener data could be fetched for 2 tickers" in caplog.text
