import json
import os
import sys

import numpy as np
import pandas as pd


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

import financial_statement


def setup_function():
    financial_statement._BENCHMARK_TABLE_CACHE.clear()
    financial_statement._PEER_BENCHMARK_CACHE.clear()


def test_financial_statements_replace_non_json_numbers(monkeypatch):
    class FakeTicker:
        financials = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): [1.0, np.nan, np.inf],
                pd.Timestamp("2023-12-31"): [pd.NA, 2.0, -np.inf],
            },
            index=["Revenue", "Missing", "Infinite"],
        )

    monkeypatch.setattr(financial_statement.yf, "Ticker", lambda _ticker: FakeTicker())

    result = financial_statement.get_financial_statements("AAPL", "income", "annual")

    assert result["dates"] == ["2024-12-31", "2023-12-31"]
    assert result["breakdown"] == [
        {"row_label": "Revenue", "values": [1.0, None]},
        {"row_label": "Missing", "values": [None, 2.0]},
        {"row_label": "Infinite", "values": [None, None]},
    ]
    json.dumps(result, allow_nan=False)


def test_financial_dashboard_scores_metrics_and_bundles_statements(monkeypatch):
    class FakeTicker:
        info = {
            "longName": "Example Corp",
            "sector": "Technology",
            "industry": "Software - Infrastructure",
            "country": "United States",
            "currency": "USD",
            "marketCap": 1_500_000_000,
            "trailingPE": 12,
            "forwardPE": 13,
            "priceToBook": 1.2,
            "priceToSalesTrailing12Months": 1.8,
            "pegRatio": 0.9,
            "currentRatio": 2.0,
            "quickRatio": 1.8,
            "debtToEquity": 40,
            "returnOnEquity": 0.20,
            "returnOnAssets": 0.08,
            "profitMargins": 0.18,
            "operatingMargins": 0.20,
            "revenueGrowth": 0.12,
            "earningsGrowth": 0.15,
            "beta": 1.0,
        }
        financials = pd.DataFrame(
            {pd.Timestamp("2024-12-31"): [1000]},
            index=["Total Revenue"],
        )
        quarterly_financials = financials
        balance_sheet = pd.DataFrame(
            {pd.Timestamp("2024-12-31"): [400, 1000]},
            index=["Total Liabilities Net Minority Interest", "Total Assets"],
        )
        quarterly_balance_sheet = balance_sheet
        cashflow = pd.DataFrame(
            {pd.Timestamp("2024-12-31"): [250]},
            index=["Operating Cash Flow"],
        )
        quarterly_cashflow = cashflow

    monkeypatch.setattr(financial_statement.yf, "Ticker", lambda _ticker: FakeTicker())
    monkeypatch.setattr(
        financial_statement,
        "_load_finviz_group_table",
        lambda group: pd.DataFrame(
            [
                {"Name": "Software - Infrastructure", "P/E": 18, "Fwd P/E": 17, "P/B": 2.2, "P/S": 3.0, "PEG": 1.4}
            ]
        ) if group == "Industry" else pd.DataFrame(),
    )

    result = financial_statement.get_financial_dashboard("FAKE")

    assert result["company"]["industry"] == "Software - Infrastructure"
    assert result["decision"]["label"] == "STRONG BUY"
    assert result["decision"]["score"] == 100
    assert result["decision"]["confidence"] == 100
    assert result["per"] == "12.00"
    assert result["debt_ratio"] == "0.40"
    assert result["statements"]["annual"]["income"]["breakdown"] == [
        {"row_label": "Total Revenue", "values": [1000]}
    ]

    metrics_by_key = {metric["key"]: metric for metric in result["metrics"]}
    assert metrics_by_key["pbr"]["signal"] == "positive"
    assert metrics_by_key["pbr"]["comparison"]["status"] == "available"
    assert metrics_by_key["pbr"]["comparison"]["position"] == "below"
    assert metrics_by_key["pbr"]["comparison"]["industry_average"] == 2.2
    assert metrics_by_key["pbr"]["comparison"]["basis"] == "industry_average"
    assert metrics_by_key["pbr"]["comparison"]["source"] == "finvizfinance_group_valuation"
    assert metrics_by_key["debt_to_equity"]["value"] == 0.4
    json.dumps(result, allow_nan=False)


def test_financial_benchmarks_fallback_to_representative_peers(monkeypatch):
    company_info = {
        "sector": "Technology",
        "industry": "Unknown Industry",
        "country": "United States",
    }
    peer_payloads = {
        "NVDA": {"trailingPE": 30, "forwardPE": 20, "priceToBook": 10, "priceToSalesTrailing12Months": 8, "pegRatio": 1.2},
        "MSFT": {"trailingPE": 25, "forwardPE": 18, "priceToBook": 8, "priceToSalesTrailing12Months": 7, "pegRatio": 1.8},
        "AAPL": {"trailingPE": 35, "forwardPE": 22, "priceToBook": 12, "priceToSalesTrailing12Months": 9, "pegRatio": 2.0},
    }

    class FakeTicker:
        def __init__(self, ticker):
            self.info = peer_payloads.get(ticker, {})

    monkeypatch.setattr(
        financial_statement,
        "_load_finviz_group_table",
        lambda _group: pd.DataFrame([{"Name": "Other", "P/E": 99}]),
    )
    monkeypatch.setattr(
        financial_statement,
        "SECTOR_REPRESENTATIVE_TICKERS",
        {"Technology": ["NVDA", "MSFT", "AAPL"]},
    )
    monkeypatch.setattr(financial_statement.yf, "Ticker", lambda ticker: FakeTicker(ticker))

    benchmarks = financial_statement._fetch_financial_benchmarks(company_info, "FAKE")

    assert benchmarks["per"]["basis"] == "sector_representative_average"
    assert benchmarks["per"]["source"] == "yfinance_representative_peers"
    assert benchmarks["per"]["sample_size"] == 3
    assert benchmarks["per"]["value"] == 30
    assert benchmarks["pbr"]["value"] == 10


def test_financial_dashboard_low_data_confidence_is_insufficient(monkeypatch):
    class FakeTicker:
        info = {}
        financials = pd.DataFrame()
        quarterly_financials = pd.DataFrame()
        balance_sheet = pd.DataFrame()
        quarterly_balance_sheet = pd.DataFrame()
        cashflow = pd.DataFrame()
        quarterly_cashflow = pd.DataFrame()

    monkeypatch.setattr(financial_statement.yf, "Ticker", lambda _ticker: FakeTicker())

    result = financial_statement.get_financial_dashboard("EMPTY")

    assert result["decision"]["label"] == "INSUFFICIENT DATA"
    assert result["decision"]["score"] is None
    assert result["statement_errors"]["annual"]["income"]
    json.dumps(result, allow_nan=False)
