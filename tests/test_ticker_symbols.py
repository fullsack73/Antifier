import pandas as pd
import pytest

import app as app_module
import ticker_lists
from portfolio_constraints import normalize_asset_constraints, normalize_current_weights
from stock_screener import _normalize_ticker_list
from ticker_symbols import normalize_yahoo_ticker


def test_normalize_yahoo_ticker_maps_us_class_shares_only():
    assert normalize_yahoo_ticker("brk.b") == "BRK-B"
    assert normalize_yahoo_ticker("BF.B") == "BF-B"
    assert normalize_yahoo_ticker("005930.KS") == "005930.KS"


def test_sp500_tickers_use_yahoo_aliases(tmp_path, monkeypatch):
    csv_path = tmp_path / "snp.csv"
    pd.DataFrame({"Symbol": ["AAPL", "BRK.B", "BF.B"]}).to_csv(csv_path, index=False)
    monkeypatch.setattr(ticker_lists, "find_file", lambda _filename: str(csv_path))

    assert ticker_lists.get_sp500_tickers() == ["AAPL", "BRK-B", "BF-B"]


def test_api_and_portfolio_constraints_share_yahoo_aliases():
    assert app_module.normalize_ticker_param("BRK.B") == "BRK-B"
    assert normalize_asset_constraints([
        {"ticker": "BF.B", "max_weight": 0.2},
    ])[0]["ticker"] == "BF-B"
    assert normalize_current_weights({"BRK.B": 0.5}) == {"BRK-B": 0.5}
    assert _normalize_ticker_list(["BRK.B", "BF.B"]) == ("BF-B", "BRK-B")


def test_alias_collisions_are_rejected():
    with pytest.raises(ValueError, match="duplicate ticker BRK-B"):
        app_module.normalize_ticker_mapping(
            {"BRK.B": 1, "BRK-B": 2},
            "current_holdings",
        )
