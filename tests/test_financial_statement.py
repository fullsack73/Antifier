import json
import os
import sys

import numpy as np
import pandas as pd


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

import financial_statement


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
            "industry": "Software",
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
        financial_statement.yf,
        "screen",
        lambda *_args, **_kwargs: {
            "quotes": [
                {"symbol": "PEER1", "trailingPE": 18, "forwardPE": 17, "priceToBook": 2.0},
                {"symbol": "PEER2", "trailingPE": 16, "forwardPE": 16, "priceToBook": 2.4},
            ]
        },
    )

    result = financial_statement.get_financial_dashboard("FAKE")

    assert result["company"]["industry"] == "Software"
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
    assert metrics_by_key["debt_to_equity"]["value"] == 0.4
    json.dumps(result, allow_nan=False)


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
