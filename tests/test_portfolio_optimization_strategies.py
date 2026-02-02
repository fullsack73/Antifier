
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
        
        # Configure Black Litterman Mock returns
        mock_bl_instance = mock_bl.return_value
        mock_bl_instance.bl_returns.return_value = pd.Series([0.1, 0.12], index=["AAPL", "GOOG"])
        mock_bl_instance.bl_cov.return_value = pd.DataFrame(
            [[0.04, 0.02], [0.02, 0.04]], index=["AAPL", "GOOG"], columns=["AAPL", "GOOG"]
        )

        yield {
            "get_stock_data": mock_get_stock_data,
            "lightweight": mock_lightweight,
            "ml_forecast": mock_ml_forecast,
            "market_caps": mock_market_caps,
            "cov_shrinkage": mock_cov_shrinkage,
            "ef": mock_ef,
            "bl": mock_bl
        }

def test_optimize_bl_lightweight(mock_data, mock_dependencies):
    """Test BL + Lightweight combination."""
    mock_dependencies["get_stock_data"].return_value = mock_data
    mock_dependencies["lightweight"].return_value = 0.08
    mock_dependencies["market_caps"].return_value = {"AAPL": 1e12, "GOOG": 1e12}
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(
        start_date=start_date, 
        end_date=end_date, 
        risk_free_rate=0.02, 
        tickers=["AAPL", "GOOG"],
        forecast_method="LIGHTWEIGHT",
        optimization_method="BL"
    )
    
    # Assertions
    assert isinstance(result, dict)
    assert result["weights"] == {"AAPL": 0.6, "GOOG": 0.4}
    
    # Verify Forecast Method Calls
    assert mock_dependencies["lightweight"].call_count >= 2 # Once per ticker
    mock_dependencies["ml_forecast"].assert_not_called()
    
    # Verify Optimization Method Calls
    mock_dependencies["bl"].assert_called()


def test_optimize_bl_deep_learning(mock_data, mock_dependencies):
    """Test BL + Deep Learning combination."""
    mock_dependencies["get_stock_data"].return_value = mock_data
    # Mock ML forecast return (mu, uncertainties)
    mock_dependencies["ml_forecast"].return_value = (
        pd.Series([0.1, 0.12], index=["AAPL", "GOOG"]), 
        pd.Series([0.05, 0.05], index=["AAPL", "GOOG"])
    )
    mock_dependencies["market_caps"].return_value = {"AAPL": 1e12, "GOOG": 1e12}
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(
        start_date=start_date, 
        end_date=end_date, 
        risk_free_rate=0.02, 
        tickers=["AAPL", "GOOG"],
        forecast_method="DEEP_LEARNING",
        optimization_method="BL"
    )
    
    # Assertions
    assert isinstance(result, dict)
    
    # Verify Forecast Method Calls
    mock_dependencies["ml_forecast"].assert_called_once()
    mock_dependencies["lightweight"].assert_not_called()
    
    # Verify Optimization Method Calls
    mock_dependencies["bl"].assert_called()


def test_optimize_mpt_lightweight(mock_data, mock_dependencies):
    """Test MPT + Lightweight combination."""
    mock_dependencies["get_stock_data"].return_value = mock_data
    mock_dependencies["lightweight"].return_value = 0.08
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(
        start_date=start_date, 
        end_date=end_date, 
        risk_free_rate=0.02, 
        tickers=["AAPL", "GOOG"],
        forecast_method="LIGHTWEIGHT",
        optimization_method="MPT"
    )
    
    # Assertions
    assert isinstance(result, dict)
    
    # Verify Forecast Method Calls
    assert mock_dependencies["lightweight"].call_count >= 2
    mock_dependencies["ml_forecast"].assert_not_called()
    
    # Verify Optimization Method Calls
    # BL should NOT be called for MPT
    mock_dependencies["bl"].assert_not_called()
    
    # Verify Efficient Frontier received forecast returns directly
    # Get arguments passed to EfficientFrontier constructor
    call_args = mock_dependencies["ef"].call_args
    assert call_args is not None
    # Check that the first argument (mu) has values matching lightweight forecast (0.08)
    mu_arg = call_args[0][0]
    assert np.allclose(mu_arg.values, [0.08, 0.08])


def test_optimize_mpt_deep_learning(mock_data, mock_dependencies):
    """Test MPT + Deep Learning combination."""
    mock_dependencies["get_stock_data"].return_value = mock_data
    # Mock ML forecast return
    mock_dependencies["ml_forecast"].return_value = (
        pd.Series([0.15, 0.18], index=["AAPL", "GOOG"]), 
        pd.Series([0.05, 0.05], index=["AAPL", "GOOG"])
    )
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    result = portfolio_optimization.optimize_portfolio(
        start_date=start_date, 
        end_date=end_date, 
        risk_free_rate=0.02, 
        tickers=["AAPL", "GOOG"],
        forecast_method="DEEP_LEARNING",
        optimization_method="MPT"
    )
    
    # Assertions
    assert isinstance(result, dict)
    
    # Verify Forecast Method Calls
    mock_dependencies["ml_forecast"].assert_called_once()
    mock_dependencies["lightweight"].assert_not_called()
    
    # Verify Optimization Method Calls
    mock_dependencies["bl"].assert_not_called()
    
    # Verify Efficient Frontier received ML forecast
    call_args = mock_dependencies["ef"].call_args
    mu_arg = call_args[0][0]
    # ML forecast returns 0.15 and 0.18
    assert mu_arg["AAPL"] == 0.15
    assert mu_arg["GOOG"] == 0.18
