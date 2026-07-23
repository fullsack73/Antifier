"""
Lightweight forecasting methods for portfolios with insufficient data.
These methods don't require extensive historical data and provide fast predictions.
"""

import numpy as np
import logging
from scipy.stats import linregress
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
DEFAULT_CALIBRATION_MIN_HISTORY = 126
DEFAULT_CALIBRATION_MAX_ORIGINS = 6
DEFAULT_UNCERTAINTY_PRIOR = 0.20
DEFAULT_UNCERTAINTY_PRIOR_WEIGHT = 0.50
MAX_CALIBRATED_UNCERTAINTY = 5.0


def _annualize_period_return(period_return, horizon):
    """Convert a simple horizon return to a bounded annual simple return."""
    value = float(period_return)
    if not np.isfinite(value):
        raise ValueError("period_return must be finite")
    horizon = max(1, int(horizon))
    annual_log_return = (
        np.log1p(max(-0.99, value))
        * TRADING_DAYS_PER_YEAR
        / horizon
    )
    lower = np.log1p(-0.99)
    upper = np.log1p(10.0)
    return float(np.expm1(np.clip(annual_log_return, lower, upper)))


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


def calibrated_lightweight_ensemble_forecast(
    prices,
    horizon=63,
    min_origin_history=DEFAULT_CALIBRATION_MIN_HISTORY,
    max_origins=DEFAULT_CALIBRATION_MAX_ORIGINS,
    uncertainty_prior=DEFAULT_UNCERTAINTY_PRIOR,
    uncertainty_prior_weight=DEFAULT_UNCERTAINTY_PRIOR_WEIGHT,
):
    """Estimate forecast uncertainty from completed historical residuals.

    The point forecast is deliberately identical to
    ``lightweight_ensemble_forecast``. Calibration origins are spaced by one
    forecast horizon and only use targets completed by the final input row.
    """
    values = np.asarray(prices, dtype=float).reshape(-1)
    values = values[np.isfinite(values) & (values > 0.0)]
    if len(values) < 10:
        raise ValueError(
            "Calibrated lightweight forecast requires at least 10 prices"
        )

    horizon = max(1, int(horizon))
    min_origin_history = max(10, int(min_origin_history))
    max_origins = max(1, int(max_origins))
    prior = max(1e-4, abs(float(uncertainty_prior)))
    prior_weight = float(
        np.clip(uncertainty_prior_weight, 0.0, 1.0)
    )

    period_forecast = float(
        lightweight_ensemble_forecast(values, horizon=horizon)
    )
    annual_forecast = _annualize_period_return(
        period_forecast,
        horizon,
    )
    last_completed_origin = len(values) - horizon - 1
    origins = (
        []
        if last_completed_origin < min_origin_history - 1
        else list(
            range(
                min_origin_history - 1,
                last_completed_origin + 1,
                horizon,
            )
        )[-max_origins:]
    )

    residuals = []
    calibration_rows = []
    for origin in origins:
        historical_period_forecast = float(
            lightweight_ensemble_forecast(
                values[:origin + 1],
                horizon=horizon,
            )
        )
        predicted = _annualize_period_return(
            historical_period_forecast,
            horizon,
        )
        realized_period_return = float(
            values[origin + horizon] / values[origin] - 1.0
        )
        realized = _annualize_period_return(
            realized_period_return,
            horizon,
        )
        residual = float(realized - predicted)
        residuals.append(residual)
        calibration_rows.append({
            "origin_position": int(origin),
            "forward_end_position": int(origin + horizon),
            "predicted_annual_return": predicted,
            "realized_annual_return": realized,
            "residual": residual,
        })

    if residuals:
        residual_array = np.asarray(residuals, dtype=float)
        raw_rmse = float(
            np.sqrt(np.mean(np.square(residual_array)))
        )
        bias = float(np.mean(residual_array))
    else:
        raw_rmse = prior
        bias = None
    calibrated_variance = (
        prior_weight * prior ** 2
        + (1.0 - prior_weight) * raw_rmse ** 2
    )
    uncertainty = float(
        np.clip(
            np.sqrt(max(0.0, calibrated_variance)),
            1e-4,
            MAX_CALIBRATED_UNCERTAINTY,
        )
    )
    return {
        "period_return": period_forecast,
        "annual_expected_return": annual_forecast,
        "annual_uncertainty": uncertainty,
        "diagnostics": {
            "method": "completed_oos_residual_rmse",
            "horizon": horizon,
            "min_origin_history": min_origin_history,
            "max_origins": max_origins,
            "uncertainty_prior": prior,
            "uncertainty_prior_weight": prior_weight,
            "observation_count": int(len(residuals)),
            "raw_oos_rmse": raw_rmse,
            "oos_bias": bias,
            "calibration_rows": calibration_rows,
        },
    }
