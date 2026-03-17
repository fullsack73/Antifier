import pytest
import numpy as np
import pandas as pd
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
from app import app

def test_calculate_rebalance_orders_no_injection():
    current_holdings = {"AAPL": 10.0, "MSFT": 5.0}
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.6, "MSFT": 0.4}
    cash_injection = 0.0
    
    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)
    
    assert result["total_target_value"] == 2500
    assert len(result["buy_list"]) == 0
    assert len(result["sell_list"]) == 0

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
