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
