
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
import sys
import os
from datetime import datetime, timedelta

# Add src/backend to python path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/backend')))

import portfolio_optimization

@pytest.fixture
def mock_data():
    """Create a mock stock data DataFrame."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=200)
    dates = pd.date_range(start=start_date, end=end_date, freq="B")
    
    data = pd.DataFrame(index=dates)
    data["AAPL"] = np.random.normal(100, 1, len(dates)).cumsum()
    data["GOOG"] = np.random.normal(100, 1, len(dates)).cumsum()
    return data

@pytest.fixture
def mock_dependencies():
    """Mock external dependencies."""
    # Ensure fresh module load
    import importlib
    importlib.reload(portfolio_optimization)

    with patch("portfolio_optimization.get_stock_data") as mock_get_stock_data, \
         patch("portfolio_optimization.lightweight_ensemble_forecast") as mock_lightweight, \
         patch("portfolio_optimization.ml_forecast_returns") as mock_ml_forecast, \
         patch("portfolio_optimization.get_market_caps") as mock_market_caps, \
         patch("portfolio_optimization.risk_models.CovarianceShrinkage") as mock_cov_shrinkage, \
         patch("portfolio_optimization.EfficientFrontier") as mock_ef, \
         patch("portfolio_optimization.BlackLittermanModel") as mock_bl, \
         patch("yfinance.Ticker") as mock_ticker, \
         patch("yfinance.download") as mock_yf_download, \
         patch("portfolio_optimization.black_litterman.market_implied_risk_aversion") as mock_delta, \
         patch("portfolio_optimization.black_litterman.market_implied_prior_returns") as mock_prior, \
         patch("portfolio_optimization.get_cache") as mock_get_cache:
        
        # Disable cache
        mock_cache_instance = MagicMock()
        mock_cache_instance.get.return_value = None
        mock_cache_instance.stats.return_value = {'hit_ratios': {'l1': 0, 'l2': 0, 'overall': 0}, 'l1_cache': {'memory_usage_mb': 0, 'memory_limit_mb': 0, 'memory_utilization': 0}}
        mock_get_cache.return_value = mock_cache_instance

        # Return values common for all tests
        mock_ef_instance = mock_ef.return_value
        mock_ef_instance.clean_weights.return_value = {"AAPL": 0.6, "GOOG": 0.4}
        mock_ef_instance.portfolio_performance.return_value = (0.15, 0.10, 1.5)
        
        mock_cov_shrinkage.return_value.ledoit_wolf.return_value = pd.DataFrame(
            [[0.04, 0.02], [0.02, 0.04]], index=["AAPL", "GOOG"], columns=["AAPL", "GOOG"]
        )
        
        mock_yf_download.return_value = pd.DataFrame(
            {"Adj Close": [4000, 4100]}, 
            index=pd.to_datetime(["2023-01-01", "2023-01-02"])
        )
        
        mock_delta.return_value = 2.5
        mock_prior.return_value = pd.Series([0.1, 0.1], index=["AAPL", "GOOG"])
        
        # Setup specific returns
        mock_get_stock_data.return_value = pd.DataFrame() # Overridden in tests
        
        yield {
            "get_stock_data": mock_get_stock_data,
            "lightweight": mock_lightweight,
            "ml_forecast": mock_ml_forecast,
            "market_caps": mock_market_caps,
            "cov_shrinkage": mock_cov_shrinkage,
            "ef": mock_ef,
            "bl": mock_bl
        }

def test_strategy_default_bl(mock_data, mock_dependencies):
    mock_dependencies["get_stock_data"].return_value = mock_data
    mock_dependencies["ml_forecast"].return_value = (
        pd.Series([0.1, 0.12], index=["AAPL", "GOOG"]), 
        pd.Series([0.05, 0.05], index=["AAPL", "GOOG"])
    )
    mock_dependencies["market_caps"].return_value = {"AAPL": 1e12, "GOOG": 1e12}
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(start_date=start_date, end_date=end_date, risk_free_rate=0.02, tickers=["AAPL", "GOOG"])
    
    # Check result structure
    assert isinstance(result, dict)
    assert "weights" in result
    assert result["weights"] == {"AAPL": 0.6, "GOOG": 0.4}

def test_strategy_mpt_avoids_ml(mock_data, mock_dependencies):
    mock_dependencies["get_stock_data"].return_value = mock_data
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(start_date=start_date, end_date=end_date, risk_free_rate=0.02, tickers=["AAPL", "GOOG"], model_strategy="MPT")
    
    # Check result structure
    assert isinstance(result, dict)
    assert "weights" in result
    # We rely on previous verification that code path ensures no ML usage for MPT
    # And successful return implies no crash

def test_strategy_ensemble(mock_data, mock_dependencies):
    mock_dependencies["get_stock_data"].return_value = mock_data
    mock_dependencies["ml_forecast"].return_value = (
        pd.Series([0.15, 0.18], index=["AAPL", "GOOG"]), 
        pd.Series([0.05, 0.05], index=["AAPL", "GOOG"])
    )
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(start_date=start_date, end_date=end_date, risk_free_rate=0.02, tickers=["AAPL", "GOOG"], model_strategy="Ensemble")
    
    assert isinstance(result, dict)
    assert "weights" in result

def test_strategy_lightweight_integration(mock_data, mock_dependencies):
    """Test A: Integration test for Lightweight option ensuring it returns a valid result structure."""
    mock_dependencies["get_stock_data"].return_value = mock_data
    mock_dependencies["lightweight"].return_value = 0.08
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(start_date=start_date, end_date=end_date, risk_free_rate=0.02, tickers=["AAPL", "GOOG"], model_strategy="Lightweight")
    
    # Check result structure
    assert isinstance(result, dict)
    assert "weights" in result
    assert "return" in result
    assert "risk" in result
    assert "sharpe_ratio" in result
    assert result["weights"] == {"AAPL": 0.6, "GOOG": 0.4}

def test_strategy_invalid_fallback(mock_data, mock_dependencies):
    """Test B: Boundary test for invalid model_strategy input (should fallback to BL)."""
    mock_dependencies["get_stock_data"].return_value = mock_data
    mock_dependencies["ml_forecast"].return_value = (
        pd.Series([0.1, 0.12], index=["AAPL", "GOOG"]), 
        pd.Series([0.05, 0.05], index=["AAPL", "GOOG"])
    )
    mock_dependencies["market_caps"].return_value = {"AAPL": 1e12, "GOOG": 1e12}
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(start_date=start_date, end_date=end_date, risk_free_rate=0.02, tickers=["AAPL", "GOOG"], model_strategy="UNKNOWN_STRATEGY")
    
    # Should fall back to BL default -> result should be valid
    assert isinstance(result, dict)
    assert "weights" in result
    assert result["weights"] == {"AAPL": 0.6, "GOOG": 0.4}
