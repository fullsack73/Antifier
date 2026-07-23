import pytest
import numpy as np
import pandas as pd
from copy import deepcopy
from unittest.mock import patch, MagicMock
import sys
import os

# Mock ML modules that might not be installed
sys.modules['tensorflow'] = MagicMock()
sys.modules['tensorflow.keras'] = MagicMock()
sys.modules['tensorflow.keras.models'] = MagicMock()
sys.modules['tensorflow.keras.layers'] = MagicMock()
sys.modules['tensorflow.keras.callbacks'] = MagicMock()

# Now import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/backend')))
from portfolio_optimization import calculate_rebalance_orders, iteratively_solve_max_sharpe
from portfolio_optimization import _convert_price_data_to_usd, _get_ticker_currency
from portfolio_optimization import optimize_portfolio, manage_portfolio_logic
from app import app, normalize_history_close_to_usd, build_historical_log_trend_regression
from app import build_arima_in_sample_regression

def test_calculate_rebalance_orders_no_injection():
    current_holdings = {"AAPL": 10.0, "MSFT": 5.0}
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.6, "MSFT": 0.4}
    cash_injection = 0.0
    
    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)
    
    assert result["total_target_value"] == 2500
    assert result["required_price_tickers"] == ["AAPL", "MSFT"]
    assert result["execution_price_coverage"] == 1.0
    assert len(result["buy_list"]) == 0
    assert len(result["sell_list"]) == 0


@pytest.mark.parametrize("invalid_price", [None, 0.0, -1.0, np.nan, np.inf])
def test_calculate_rebalance_orders_rejects_invalid_required_price(invalid_price):
    with pytest.raises(
        ValueError,
        match="Missing or invalid latest price for required tickers: AAPL",
    ):
        calculate_rebalance_orders(
            {"AAPL": 10.0},
            {"AAPL": 1.0},
            {"AAPL": invalid_price},
            0.0,
        )


def test_calculate_rebalance_orders_requires_prices_for_new_targets():
    with pytest.raises(
        ValueError,
        match="Missing or invalid latest price for required tickers: MSFT",
    ):
        calculate_rebalance_orders(
            {},
            {"MSFT": 1.0},
            {},
            1000.0,
        )


def test_calculate_rebalance_orders_ignores_zero_exposure_without_price():
    result = calculate_rebalance_orders(
        {"DUST": 0.0},
        {"AAPL": 1.0, "DUST": 0.0},
        {"AAPL": 100.0},
        1000.0,
    )

    assert result["required_price_tickers"] == ["AAPL"]
    assert result["execution_price_coverage"] == 1.0
    assert result["buy_list"]["AAPL"]["quantity"] == pytest.approx(10.0)


def test_rebalance_funds_transaction_cost_from_fractional_buys():
    result = calculate_rebalance_orders(
        {},
        {"AAPL": 1.0},
        {"AAPL": 100.0},
        1000.0,
        transaction_cost_bps=100.0,
    )

    target_value = result["target_quantities"]["AAPL"] * 100.0
    assert result["buy_list"]["AAPL"]["quantity"] == pytest.approx(
        1000.0 / 101.0
    )
    assert result["transaction_cost"] == pytest.approx(
        result["gross_trade_value"] * 0.01
    )
    assert target_value + result["transaction_cost"] + result["remaining_cash"] == (
        pytest.approx(1000.0)
    )
    assert result["remaining_cash"] == pytest.approx(0.0, abs=1e-9)


def test_rebalance_transaction_cost_reduces_buys_without_hidden_sells():
    result = calculate_rebalance_orders(
        {"AAPL": 10.0},
        {"AAPL": 0.0, "MSFT": 1.0},
        {"AAPL": 100.0, "MSFT": 100.0},
        0.0,
        transaction_cost_bps=100.0,
    )

    assert result["sell_list"]["AAPL"]["quantity"] == pytest.approx(10.0)
    assert result["buy_list"]["MSFT"]["quantity"] == pytest.approx(
        (1000.0 - 2000.0 / 101.0) / 100.0
    )
    assert result["transaction_cost_diagnostics"][
        "transaction_cost_funding_buy_reduction"
    ] == pytest.approx(2000.0 / 101.0)
    executed_value = (
        result["target_quantities"]["MSFT"] * 100.0
        + result["transaction_cost"]
        + result["remaining_cash"]
    )
    assert executed_value == pytest.approx(1000.0)


def test_rebalance_integer_orders_remain_cash_feasible_after_cost():
    result = calculate_rebalance_orders(
        {},
        {"AAPL": 1.0},
        {"AAPL": 333.0},
        1000.0,
        allow_fractional=False,
        transaction_cost_bps=10.0,
    )

    assert result["target_quantities"]["AAPL"] == 3.0
    assert result["transaction_cost"] == pytest.approx(0.999)
    assert result["remaining_cash"] == pytest.approx(0.001)
    assert (
        result["target_quantities"]["AAPL"] * 333.0
        + result["transaction_cost"]
        + result["remaining_cash"]
    ) == pytest.approx(1000.0)


def test_manage_portfolio_rejects_partial_orders_when_holding_price_is_missing():
    opt_payload = {
        "weights": {"AAPL": 1.0},
        "prices": {"AAPL": 100.0},
        "return": 0.08,
        "risk": 0.12,
        "sharpe_ratio": 0.5,
    }

    with patch(
        "portfolio_optimization.optimize_portfolio",
        return_value=deepcopy(opt_payload),
    ):
        result = manage_portfolio_logic(
            current_holdings={"OLD": 2.0},
            cash_injection=0.0,
            start_date="2023-01-01",
            end_date="2023-12-31",
            risk_free_rate=0.02,
            optimization_method="MPT",
        )

    assert result["required_price_tickers"] == ["AAPL", "OLD"]
    assert result["missing_price_tickers"] == ["OLD"]
    assert result["execution_price_coverage"] == pytest.approx(0.5)
    assert "OLD" in result["error"]
    assert "buy_list" not in result
    assert "sell_list" not in result


def test_manage_portfolio_returns_validation_error_for_nonfinite_holding():
    opt_payload = {
        "weights": {"AAPL": 1.0},
        "prices": {"AAPL": 100.0},
    }

    with patch(
        "portfolio_optimization.optimize_portfolio",
        return_value=deepcopy(opt_payload),
    ):
        result = manage_portfolio_logic(
            current_holdings={"AAPL": np.nan},
            cash_injection=0.0,
            start_date="2023-01-01",
            end_date="2023-12-31",
            risk_free_rate=0.02,
            optimization_method="MPT",
        )

    assert result == {
        "error": "current_holdings[AAPL] must be a finite non-negative number"
    }


def test_calculate_rebalance_orders_with_injection():
    current_holdings = {"AAPL": 10.0, "MSFT": 5.0} # Value 2500
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.5, "MSFT": 0.5}
    cash_injection = 500.0
    
    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)
    
    assert result["total_target_value"] == 3000.0
    assert len(result["buy_list"]) == 1
    assert "MSFT" in result["buy_list"]
    assert result["buy_list"]["MSFT"]["quantity"] == 2.5
    assert len(result["sell_list"]) == 0

def test_calculate_rebalance_orders_rebalance():
    current_holdings = {"AAPL": 10.0, "MSFT": 5.0} # Value 2500
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.2, "MSFT": 0.8} # AAPL=500, MSFT=2000
    cash_injection = 0.0
    
    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)
    assert "AAPL" in result["sell_list"]
    assert pytest.approx(result["sell_list"]["AAPL"]["quantity"]) == 6.666666666666667
    
    assert "MSFT" in result["buy_list"]
    assert result["buy_list"]["MSFT"]["quantity"] == 5.0

def test_calculate_rebalance_orders_new_asset():
    current_holdings = {"AAPL": 10.0} # Value 1500
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.5, "MSFT": 0.5}
    cash_injection = 500.0 # Total 2000
    
    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)
    assert "AAPL" in result["sell_list"]
    assert "MSFT" in result["buy_list"]
    assert result["buy_list"]["MSFT"]["quantity"] == 5.0
    assert pytest.approx(result["sell_list"]["AAPL"]["quantity"]) == 3.333333333333333


def test_portfolio_manager_applies_default_trade_controls_and_can_disable():
    opt_payload = {
        "weights": {"AAA": 0.51, "BBB": 0.49},
        "prices": {"AAA": 100.0, "BBB": 100.0},
        "return": 0.08,
        "risk": 0.12,
        "sharpe_ratio": 0.5,
    }

    with patch("portfolio_optimization.optimize_portfolio", side_effect=lambda **kwargs: deepcopy(opt_payload)), \
         patch("portfolio_optimization.get_asset_names", side_effect=lambda tickers: {ticker: ticker for ticker in tickers}):
        controlled = manage_portfolio_logic(
            current_holdings={"AAA": 5.0, "BBB": 5.0},
            cash_injection=0.0,
            start_date="2023-01-01",
            end_date="2023-12-31",
            risk_free_rate=0.02,
            optimization_method="MPT",
        )
        uncontrolled = manage_portfolio_logic(
            current_holdings={"AAA": 5.0, "BBB": 5.0},
            cash_injection=0.0,
            start_date="2023-01-01",
            end_date="2023-12-31",
            risk_free_rate=0.02,
            optimization_method="MPT",
            rebalance_band=0.0,
            max_turnover=None,
        )

    assert controlled["buy_list"] == {}
    assert controlled["sell_list"] == {}
    assert controlled["rebalance_controls"]["skipped_trade_count"] == 2
    assert controlled["controlled_weights"]["AAA"] == pytest.approx(0.5)
    assert controlled["controlled_weights"]["BBB"] == pytest.approx(0.5)

    assert "AAA" in uncontrolled["buy_list"]
    assert "BBB" in uncontrolled["sell_list"]
    assert "rebalance_controls" not in uncontrolled

def test_calculate_rebalance_orders_integer_redistribution():
    current_holdings = {"AAPL": 0.0, "MSFT": 0.0} 
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.6, "MSFT": 0.4}
    
    # target values: AAPL = 630 (4.2 shares), MSFT = 420 (2.1 shares)
    # Floor quantities: AAPL = 4 (600), MSFT = 2 (400)
    # Remaining cash: 30 + 20 = 50
    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection=1050.0, allow_fractional=False)
    
    import pytest
    assert result["total_target_value"] == 1050.0
    assert result["buy_list"]["AAPL"]["quantity"] == 4.0
    assert result["buy_list"]["MSFT"]["quantity"] == 2.0
    assert result["remaining_cash"] == pytest.approx(50.0)

def test_calculate_rebalance_orders_fractional_overrides():
    current_holdings = {"AAPL": 0.0, "MSFT": 0.0}
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.6, "MSFT": 0.4}
    
    # AAPL gets 630 (4.2 shares)
    # MSFT gets 420 (2.1 shares)
    # Overrides: AAPL fractional, MSFT integer
    # AAPL gets 4.2 shares. MSFT gets 2 shares (400)
    # Remaining 20 redistributes to AAPL -> 20 / 150 = 0.13333333333333333
    # AAPL total shares: 4.2 + 0.13333333333333333 = 4.333333333333333
    
    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection=1050.0, allow_fractional=False, fractional_overrides={"AAPL": True})
    
    assert result["total_target_value"] == 1050.0
    assert pytest.approx(result["buy_list"]["AAPL"]["quantity"]) == 4.333333333333333
    assert result["buy_list"]["MSFT"]["quantity"] == 2.0
    assert result["remaining_cash"] == 0.0


def test_convert_krw_prices_to_usd_before_portfolio_math():
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    prices = pd.DataFrame(
        {
            "035420.KS": [200000.0, 210000.0],
            "AAPL": [100.0, 110.0],
        },
        index=dates,
    )
    fx_data = pd.DataFrame({"Close": [1300.0, 1400.0]}, index=dates)

    with patch("portfolio_optimization.yf.download", return_value=fx_data) as mock_download:
        converted, metadata, failures = _convert_price_data_to_usd(
            prices,
            start_date="2024-01-01",
            end_date="2024-01-04",
            ticker_currencies={"035420.KS": "KRW", "AAPL": "USD"},
        )

    assert failures == []
    assert mock_download.call_args.args[0] == "KRW=X"
    assert converted["035420.KS"].iloc[0] == pytest.approx(200000.0 / 1300.0)
    assert converted["035420.KS"].iloc[1] == pytest.approx(210000.0 / 1400.0)
    assert converted["AAPL"].iloc[0] == pytest.approx(100.0)
    assert metadata["035420.KS"]["source_currency"] == "KRW"
    assert metadata["035420.KS"]["display_currency"] == "USD"


def test_fx_conversion_aligns_by_calendar_date_not_exact_timestamp():
    stock_dates = pd.to_datetime(["2024-01-02 15:30", "2024-01-03 15:30"])
    fx_dates = pd.to_datetime(["2024-01-02 00:00", "2024-01-03 00:00"])
    prices = pd.DataFrame({"035420.KS": [200000.0, 210000.0]}, index=stock_dates)
    fx_data = pd.DataFrame({"Close": [1300.0, 1400.0]}, index=fx_dates)

    with patch("portfolio_optimization.yf.download", return_value=fx_data):
        converted, _, failures = _convert_price_data_to_usd(
            prices,
            start_date="2024-01-01",
            end_date="2024-01-04",
            ticker_currencies={"035420.KS": "KRW"},
        )

    assert failures == []
    assert converted.index.equals(stock_dates)
    assert converted["035420.KS"].iloc[0] == pytest.approx(200000.0 / 1300.0)
    assert converted["035420.KS"].iloc[1] == pytest.approx(210000.0 / 1400.0)


def test_fx_conversion_uses_nearest_available_rate_for_missing_stock_date():
    stock_dates = pd.to_datetime(["2024-01-03 15:30"])
    fx_dates = pd.to_datetime(["2024-01-02 00:00"])
    prices = pd.DataFrame({"035420.KS": [200000.0]}, index=stock_dates)
    fx_data = pd.DataFrame({"Close": [1300.0]}, index=fx_dates)

    with patch("portfolio_optimization.yf.download", return_value=fx_data):
        converted, _, failures = _convert_price_data_to_usd(
            prices,
            start_date="2024-01-01",
            end_date="2024-01-04",
            ticker_currencies={"035420.KS": "KRW"},
        )

    assert failures == []
    assert converted["035420.KS"].iloc[0] == pytest.approx(200000.0 / 1300.0)


def test_plain_us_tickers_assume_usd_without_metadata_lookup():
    with patch("portfolio_optimization.yf.Ticker") as mock_ticker:
        currency = _get_ticker_currency("AAPL")

    assert currency == "USD"
    mock_ticker.assert_not_called()


def test_stock_chart_history_close_is_normalized_to_usd():
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    history = pd.DataFrame(
        {
            "Close": [200000.0, 210000.0],
            "Volume": [1000, 1200],
        },
        index=dates,
    )
    fx_data = pd.DataFrame({"Close": [1300.0, 1400.0]}, index=dates)

    with patch("app.yf.download", return_value=fx_data) as mock_download:
        normalized, price_currency, metadata = normalize_history_close_to_usd(
            "035420.KS",
            history,
            start_date="2024-01-01",
            end_date="2024-01-04",
        )

    assert mock_download.call_args.args[0] == "KRW=X"
    assert normalized["Close"].iloc[0] == pytest.approx(200000.0 / 1300.0)
    assert normalized["Close"].iloc[1] == pytest.approx(210000.0 / 1400.0)
    assert normalized["Volume"].iloc[0] == 1000
    assert price_currency == "USD"
    assert metadata["source_currency"] == "KRW"


def test_forecast_model_regression_line_uses_historical_log_trend():
    dates = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"])
    prices = pd.Series([100.0, 90.0, 130.0, 140.0], index=dates)

    regression = build_historical_log_trend_regression(prices)

    assert list(regression.keys()) == [date.strftime("%Y-%m-%d") for date in dates]
    assert all(np.isfinite(value) and value > 0 for value in regression.values())
    assert regression["2025-01-04"] > regression["2025-01-01"]
    assert regression["2025-01-01"] != pytest.approx(100.0)


def test_arima_transformer_regression_line_uses_arima_in_sample_fit():
    class FakeArimaModel:
        order = (1, 1, 1)

        def predict_in_sample(self):
            return np.array([9999.0, 91.0, 129.0, 141.0] + [150.0] * 30)

    dates = pd.date_range("2025-01-01", periods=34)
    prices = pd.Series(np.linspace(100.0, 150.0, 34), index=dates)

    with patch("pmdarima.auto_arima", return_value=FakeArimaModel()):
        regression = build_arima_in_sample_regression(prices)

    assert regression["2025-01-01"] == pytest.approx(100.0)
    assert regression["2025-01-02"] == pytest.approx(91.0)
    assert regression["2025-01-03"] == pytest.approx(129.0)
    assert regression["2025-01-04"] == pytest.approx(141.0)


def test_iteratively_solve_max_sharpe():
    mu = pd.Series({"AAPL": 0.1, "MSFT": 0.05})
    S = pd.DataFrame([[0.04, 0.005], [0.005, 0.02]], index=["AAPL", "MSFT"], columns=["AAPL", "MSFT"])
    
    weights = iteratively_solve_max_sharpe(mu, S, risk_free_rate=0.02, max_asset_weight=1.0)
    
    assert isinstance(weights, dict)
    assert "AAPL" in weights
    assert "MSFT" in weights
    assert sum(weights.values()) == pytest.approx(1.0)

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_manage_portfolio_api(client):
    with patch("app.manage_portfolio_logic") as mock_logic:
        mock_logic.return_value = {
            "weights": {"AAPL": 0.5, "MSFT": 0.5},
            "prices": {"AAPL": 150.0, "MSFT": 200.0},
            "buy_list": {"MSFT": {"quantity": 2.5, "price": 200.0, "value": 500.0}},
            "sell_list": {},
            "total_target_value": 3000.0
        }
        
        response = client.post('/api/manage-portfolio', json={
            "current_holdings": {"AAPL": 10.0, "MSFT": 5.0},
            "cash_injection": 500,
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "risk_free_rate": 0.02
        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert "weights" in data
        assert "buy_list" in data
        assert data["total_target_value"] == 3000.0
        assert mock_logic.call_args.kwargs["transaction_cost_bps"] == 10.0


def test_manage_portfolio_api_returns_400_for_incomplete_execution_prices(client):
    with patch("app.manage_portfolio_logic") as mock_logic:
        mock_logic.return_value = {
            "error": "Missing or invalid latest price for required tickers: OLD",
            "execution_price_coverage": 0.0,
        }

        response = client.post('/api/manage-portfolio', json={
            "current_holdings": {"OLD": 2.0},
            "cash_injection": 0.0,
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "risk_free_rate": 0.02,
        })

    assert response.status_code == 400
    assert response.get_json()["execution_price_coverage"] == 0.0


def test_manage_portfolio_api_rejects_invalid_transaction_cost(client):
    response = client.post('/api/manage-portfolio', json={
        "current_holdings": {"AAPL": 1.0},
        "cash_injection": 0.0,
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "risk_free_rate": 0.02,
        "transaction_cost_bps": 10000,
    })

    assert response.status_code == 400
    assert "transaction_cost_bps" in response.get_json()["error"]


def test_manage_portfolio_api_forwards_ticker_group(client):
    with patch("app.manage_portfolio_logic") as mock_logic:
        mock_logic.return_value = {
            "weights": {"AAPL": 0.5, "MSFT": 0.5},
            "prices": {"AAPL": 150.0, "MSFT": 200.0},
            "buy_list": {},
            "sell_list": {},
            "total_target_value": 2500.0
        }

        response = client.post('/api/manage-portfolio', json={
            "current_holdings": {"AAPL": 10.0, "GOOGL": 5.0},
            "cash_injection": 96,
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "risk_free_rate": 0.03,
            "ticker_group": "DOW"
        })

        assert response.status_code == 200
        assert mock_logic.call_args.kwargs["ticker_group"] == "DOW"


def test_manage_portfolio_combines_ticker_group_with_current_holdings():
    with patch("portfolio_optimization.get_ticker_group", return_value=["AAPL", "MSFT"]):
        with patch("portfolio_optimization.optimize_portfolio") as mock_optimize:
            mock_optimize.return_value = {
                "weights": {"AAPL": 0.5, "MSFT": 0.5},
                "prices": {"AAPL": 150.0, "GOOGL": 100.0, "MSFT": 200.0},
                "return": 0.1,
                "risk": 0.2,
                "sharpe_ratio": 0.4
            }

            result = manage_portfolio_logic(
                current_holdings={"AAPL": 10.0, "GOOGL": 5.0},
                cash_injection=96,
                start_date="2023-01-01",
                end_date="2023-12-31",
                risk_free_rate=0.03,
                ticker_group="DOW",
                optimization_method="MPT"
            )

    assert mock_optimize.call_args.kwargs["tickers"] == ["AAPL", "GOOGL", "MSFT"]
    assert result["current_holdings"] == {"AAPL": 10.0, "GOOGL": 5.0}


def test_optimize_portfolio_relaxes_weight_cap_for_small_universe():
    mu = pd.Series({"AAPL": 0.10, "GOOGL": 0.08})
    S = pd.DataFrame(
        [[0.04, 0.005], [0.005, 0.03]],
        index=["AAPL", "GOOGL"],
        columns=["AAPL", "GOOGL"]
    )
    pipeline_result = {
        "mu": mu,
        "S": S,
        "uncertainties": pd.Series({"AAPL": 0.05, "GOOGL": 0.05}),
        "tickers": ["AAPL", "GOOGL"],
        "latest_prices": {"AAPL": 150.0, "GOOGL": 100.0}
    }

    with patch("portfolio_optimization.data_and_forecast_pipeline", return_value=pipeline_result):
        result = optimize_portfolio(
            start_date="2023-01-01",
            end_date="2023-12-31",
            risk_free_rate=0.02,
            tickers=["AAPL", "GOOGL"],
            optimization_method="MPT",
            forecast_method="LIGHTWEIGHT"
        )

    assert "error" not in result
    assert sum(result["weights"].values()) == pytest.approx(1.0)


def test_optimize_portfolio_dedupes_tickers_before_pipeline():
    mu = pd.Series({"AAPL": 0.1, "MSFT": 0.08})
    S = pd.DataFrame(
        [[0.04, 0.005], [0.005, 0.02]],
        index=["AAPL", "MSFT"],
        columns=["AAPL", "MSFT"]
    )
    uncertainties = pd.Series({"AAPL": 0.05, "MSFT": 0.05})

    pipeline_result = {
        "mu": mu,
        "S": S,
        "uncertainties": uncertainties,
        "tickers": ["AAPL", "MSFT"],
        "latest_prices": {"AAPL": 150.0, "MSFT": 200.0}
    }

    with patch("portfolio_optimization.data_and_forecast_pipeline", return_value=pipeline_result) as mock_pipeline:
        with patch("portfolio_optimization.EfficientFrontier") as mock_ef_cls:
            mock_ef = MagicMock()
            mock_ef.clean_weights.return_value = {"AAPL": 0.6, "MSFT": 0.4}
            mock_ef.portfolio_performance.return_value = (0.12, 0.2, 0.5)
            mock_ef_cls.return_value = mock_ef

            result = optimize_portfolio(
                start_date="2023-01-01",
                end_date="2023-12-31",
                risk_free_rate=0.02,
                tickers=["AAPL", "AAPL", "MSFT", "aapl"],
                optimization_method="MPT",
                forecast_method="LIGHTWEIGHT"
            )

    assert "error" not in result
    assert mock_pipeline.call_count == 1
    assert mock_pipeline.call_args.args[3] == ["AAPL", "MSFT"]
