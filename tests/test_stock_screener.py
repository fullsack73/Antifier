import os
import sys


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
