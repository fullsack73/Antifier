"""
Task Group 3: Test Review & Gap Analysis
Additional strategic tests for Portfolio Management feature.
Maximum 10 tests covering critical edge cases and E2E workflows.
"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock
import sys
import os

# Mock ML modules
sys.modules['tensorflow'] = MagicMock()
sys.modules['tensorflow.keras'] = MagicMock()
sys.modules['tensorflow.keras.models'] = MagicMock()
sys.modules['tensorflow.keras.layers'] = MagicMock()
sys.modules['tensorflow.keras.callbacks'] = MagicMock()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/backend')))
from portfolio_optimization import calculate_rebalance_orders, iteratively_solve_max_sharpe
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


# --- Edge Case 1: Zero initial holdings (all-new portfolio from cash only) ---
def test_rebalance_zero_initial_holdings():
    """User starts with no existing stocks and only injects cash."""
    current_holdings = {}
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0, "GOOGL": 100.0}
    target_weights = {"AAPL": 0.3, "MSFT": 0.5, "GOOGL": 0.2}
    cash_injection = 10000.0

    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)

    assert result["total_target_value"] == 10000.0
    # All targets should be in buy_list since no existing assets
    assert "AAPL" in result["buy_list"]
    assert "MSFT" in result["buy_list"]
    assert "GOOGL" in result["buy_list"]
    assert len(result["sell_list"]) == 0
    # Check exact fractional quantities
    assert result["buy_list"]["AAPL"]["quantity"] == pytest.approx(20.0)    # 3000/150
    assert result["buy_list"]["MSFT"]["quantity"] == pytest.approx(25.0)    # 5000/200
    assert result["buy_list"]["GOOGL"]["quantity"] == pytest.approx(20.0)   # 2000/100


# --- Edge Case 2: Massive cash injection dwarfing existing holdings ---
def test_rebalance_massive_cash_injection():
    """Cash injection is 100x the existing portfolio value."""
    current_holdings = {"AAPL": 1.0}  # Value: $150
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.5, "MSFT": 0.5}
    cash_injection = 15000.0  # Total: $15150

    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)

    assert result["total_target_value"] == pytest.approx(15150.0)
    # AAPL target = 15150 * 0.5 = 7575, current = 150 → buy 49.5
    assert "AAPL" in result["buy_list"]
    assert result["buy_list"]["AAPL"]["quantity"] == pytest.approx(49.5)
    # MSFT target = 15150 * 0.5 = 7575, current = 0 → buy 37.875
    assert "MSFT" in result["buy_list"]
    assert result["buy_list"]["MSFT"]["quantity"] == pytest.approx(37.875)


# --- Edge Case 3: Single-asset concentrated portfolio fully redistributed ---
def test_rebalance_single_asset_to_diversified():
    """User holds only one stock, target is evenly split across 3."""
    current_holdings = {"AAPL": 10.0}  # Value: $1500
    latest_prices = {"AAPL": 150.0, "MSFT": 100.0, "GOOGL": 50.0}
    target_weights = {"AAPL": 1/3, "MSFT": 1/3, "GOOGL": 1/3}
    cash_injection = 0.0

    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)

    assert result["total_target_value"] == pytest.approx(1500.0)
    # AAPL: target = 500, current = 1500 → sell (1500-500)/150 = 6.667
    assert "AAPL" in result["sell_list"]
    assert result["sell_list"]["AAPL"]["quantity"] == pytest.approx(6.666666666666667)
    # MSFT: target = 500, current = 0 → buy 500/100 = 5
    assert "MSFT" in result["buy_list"]
    assert result["buy_list"]["MSFT"]["quantity"] == pytest.approx(5.0)
    # GOOGL: target = 500, current = 0 → buy 500/50 = 10
    assert "GOOGL" in result["buy_list"]
    assert result["buy_list"]["GOOGL"]["quantity"] == pytest.approx(10.0)


# --- Edge Case 4: Target weight is zero for an existing holding (full sell) ---
def test_rebalance_full_sell_of_existing_asset():
    """Target weight is 0 for one asset → should completely sell it."""
    current_holdings = {"AAPL": 10.0, "MSFT": 5.0}  # Value: 2500
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.0, "MSFT": 1.0}
    cash_injection = 0.0

    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)

    assert "AAPL" in result["sell_list"]
    assert result["sell_list"]["AAPL"]["quantity"] == pytest.approx(10.0)
    assert "MSFT" in result["buy_list"]
    assert result["buy_list"]["MSFT"]["quantity"] == pytest.approx(7.5)  # (2500-1000)/200


# --- Edge Case 5: Verify fractional precision with very small quantities ---
def test_rebalance_fractional_precision():
    """Small fractional holdings should produce precise fractional outputs."""
    current_holdings = {"AAPL": 0.1}  # Value: $15
    latest_prices = {"AAPL": 150.0, "MSFT": 200.0}
    target_weights = {"AAPL": 0.5, "MSFT": 0.5}
    cash_injection = 85.0  # Total: $100

    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)

    assert result["total_target_value"] == pytest.approx(100.0)
    # AAPL target = 50, current = 15 → need to buy (50-15)/150 = 0.2333...
    assert "AAPL" in result["buy_list"]
    assert result["buy_list"]["AAPL"]["quantity"] == pytest.approx(0.23333333333333334)
    # MSFT target = 50, current = 0 → need to buy 50/200 = 0.25
    assert "MSFT" in result["buy_list"]
    assert result["buy_list"]["MSFT"]["quantity"] == pytest.approx(0.25)


# --- Edge Case 6: Iterative solver produces valid diversified weights ---
def test_iteratively_solve_max_sharpe_diversified():
    """Solver should produce valid diversified weights summing to 1."""
    mu = pd.Series({"AAPL": 0.10, "MSFT": 0.08, "GOOGL": 0.06})
    S = pd.DataFrame(
        [[0.04, 0.005, 0.002],
         [0.005, 0.02, 0.001],
         [0.002, 0.001, 0.01]],
        index=["AAPL", "MSFT", "GOOGL"],
        columns=["AAPL", "MSFT", "GOOGL"]
    )

    weights = iteratively_solve_max_sharpe(mu, S, risk_free_rate=0.02, max_asset_weight=1.0)

    assert isinstance(weights, dict)
    assert sum(weights.values()) == pytest.approx(1.0)
    # All weights should be non-negative
    for w in weights.values():
        assert w >= -1e-6


# --- E2E Test 7: 3-asset portfolio through API endpoint ---
def test_manage_portfolio_api_3_asset_e2e(client):
    """End-to-end: 3-asset portfolio with cash injection via API."""
    with patch("app.manage_portfolio_logic") as mock_logic:
        mock_logic.return_value = {
            "weights": {"AAPL": 0.4, "MSFT": 0.35, "GOOGL": 0.25},
            "prices": {"AAPL": 150.0, "MSFT": 200.0, "GOOGL": 100.0},
            "buy_list": {
                "GOOGL": {"quantity": 10.0, "price": 100.0, "value": 1000.0}
            },
            "sell_list": {
                "AAPL": {"quantity": 2.0, "price": 150.0, "value": 300.0}
            },
            "total_target_value": 5000.0,
            "expected_return": 0.15,
            "volatility": 0.20,
            "sharpe_ratio": 0.65
        }

        response = client.post('/api/manage-portfolio', json={
            "current_holdings": {"AAPL": 10.0, "MSFT": 5.0, "GOOGL": 0.0},
            "cash_injection": 1000.0,
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "risk_free_rate": 0.02,
            "forecast_method": "LIGHTWEIGHT",
            "optimization_method": "BL"
        })

        assert response.status_code == 200
        data = response.get_json()
        assert "weights" in data
        assert "buy_list" in data
        assert "sell_list" in data
        assert len(data["weights"]) == 3
        assert data["total_target_value"] == 5000.0
        assert "GOOGL" in data["buy_list"]
        assert "AAPL" in data["sell_list"]


# --- Edge Case 8: API returns 400 on missing required fields ---
def test_manage_portfolio_api_missing_fields(client):
    """API should return 400 when required fields are missing."""
    response = client.post('/api/manage-portfolio', json={
        "cash_injection": 500
        # Missing: current_holdings, start_date, end_date
    })

    assert response.status_code == 400


# --- Edge Case 9: Holdings conservation check (net value unchanged without cash injection) ---
def test_rebalance_value_conservation():
    """Total portfolio value should be preserved when no cash is injected."""
    current_holdings = {"AAPL": 5.0, "MSFT": 10.0, "GOOGL": 8.0}
    latest_prices = {"AAPL": 200.0, "MSFT": 100.0, "GOOGL": 50.0}
    target_weights = {"AAPL": 0.5, "MSFT": 0.3, "GOOGL": 0.2}
    cash_injection = 0.0

    result = calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection)

    # Total value = 5*200 + 10*100 + 8*50 = 1000 + 1000 + 400 = 2400
    assert result["total_target_value"] == pytest.approx(2400.0)

    # Verify buy total value == sell total value (conservation)
    buy_value = sum(item["value"] for item in result["buy_list"].values())
    sell_value = sum(item["value"] for item in result["sell_list"].values())
    assert buy_value == pytest.approx(sell_value, abs=0.01)
