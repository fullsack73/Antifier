"""
Lightweight forecasting methods for portfolios with insufficient data.
These methods don't require extensive historical data and provide fast predictions.
"""

import numpy as np
import logging
from scipy.stats import linregress
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)


def exponential_smoothing_forecast(prices, alpha=0.3, horizon=252):
    """Fast exponential smoothing forecast.
    
    Args:
        prices: Array of historical prices
        alpha: Smoothing parameter (0 < alpha <= 1)
        horizon: Forecast horizon in days (default: 252)
    
    Returns:
        Expected return over the horizon (float)
    """
    if len(prices) < 2:
        return 0.05
    
    # Simple exponential smoothing
    smoothed = [prices[0]]
    for i in range(1, len(prices)):
        smoothed.append(alpha * prices[i] + (1 - alpha) * smoothed[i-1])
    
    # Calculate trend from last 30 days
    recent_data = smoothed[-30:] if len(smoothed) >= 30 else smoothed
    if len(recent_data) < 2:
        return 0.05
    
    # Linear trend extrapolation
    x = np.arange(len(recent_data))
    slope, intercept, _, _, _ = linregress(x, recent_data)
    
    # Project 'horizon' days ahead
    future_price = slope * (len(recent_data) + horizon) + intercept
    current_price = recent_data[-1]
    
    if current_price <= 0:
        return 0.05
    
    return (future_price / current_price) - 1


def linear_trend_forecast(prices, horizon=252):
    """Fast linear trend forecast.
    
    Args:
        prices: Array of historical prices
        horizon: Forecast horizon in days
    
    Returns:
        Expected return over the horizon (float)
    """
    if len(prices) < 10:
        return 0.05
    
    # Use last 90 days for trend analysis
    recent_prices = prices[-90:] if len(prices) >= 90 else prices
    x = np.arange(len(recent_prices)).reshape(-1, 1)
    y = recent_prices
    
    try:
        model = LinearRegression()
        model.fit(x, y)
        
        # Predict 'horizon' days ahead
        future_x = np.array([[len(recent_prices) + horizon]])
        future_price = model.predict(future_x)[0]
        current_price = recent_prices[-1]
        
        if current_price <= 0:
            return 0.05
        
        return (future_price / current_price) - 1
    except:
        return 0.05


def historical_volatility_adjusted_forecast(prices, horizon=252):
    """Historical mean with volatility adjustment.
    
    Args:
        prices: Array of historical prices
        horizon: Forecast horizon in days
    
    Returns:
        Expected return over the horizon (float)
    """
    if len(prices) < 30:
        return 0.05
    
    returns = np.diff(prices) / prices[:-1]
    returns = returns[~np.isnan(returns)]  # Remove NaN values
    
    if len(returns) < 10:
        return 0.05
    
    mean_return = np.mean(returns)
    volatility = np.std(returns)
    
    # Return over the horizon with volatility adjustment
    period_return = mean_return * horizon
    
    # Apply volatility penalty for very volatile stocks
    if volatility > 0.05:  # 5% daily volatility threshold
        period_return *= 0.8  # Reduce expected return for high volatility
    
    return period_return


def lightweight_ensemble_forecast(prices, horizon=252):
    """Ensemble of lightweight forecasting methods.
    
    Combines exponential smoothing, linear trend, and volatility-adjusted
    historical returns for a robust forecast.
    
    Args:
        prices: Array of historical prices
        horizon: Forecast horizon in days
    
    Returns:
        Expected return over the horizon (float)
    """
    if len(prices) < 10:
        logger.warning(f"Insufficient data for lightweight forecast: {len(prices)} points")
        return 0.05
    
    # Use ensemble of lightweight methods
    exp_forecast = exponential_smoothing_forecast(prices, horizon=horizon)
    trend_forecast = linear_trend_forecast(prices, horizon=horizon)
    vol_forecast = historical_volatility_adjusted_forecast(prices, horizon=horizon)
    
    # Weighted average with more weight on exponential smoothing
    forecast_value = (0.4 * exp_forecast + 0.3 * trend_forecast + 0.3 * vol_forecast)
    
    # Clip to reasonable bounds
    forecast_value = np.clip(forecast_value, -0.5, 1.0)
    
    return forecast_value
