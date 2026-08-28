"""
Portfolio Benchmarking Module

This module provides functionality to benchmark a portfolio against S&P 500 and risk-free assets
over a specified time period. It calculates historical performance metrics and aggregated returns.
"""

from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

from portfolio_optimization import _convert_price_data_to_usd, _extract_close_series
from ticker_symbols import normalize_yahoo_ticker


def _normalize_date_index(series):
    date_index = pd.to_datetime(series.index).tz_localize(None).normalize()
    normalized = pd.Series(series.to_numpy(dtype=float), index=date_index).sort_index()
    return normalized[~normalized.index.duplicated(keep="last")]


def _date_to_key(date):
    return date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date).split(' ')[0]


def calculate_portfolio_benchmark(portfolio_data, budget, start_date, end_date, risk_free_rate):
    """
    Calculate portfolio performance against benchmarks over a time period.
    
    Args:
        portfolio_data (dict): Portfolio JSON containing weights, prices, and tickers
        budget (float): Total investment amount in dollars
        start_date (datetime): Start date for benchmarking
        end_date (datetime): End date for benchmarking
        risk_free_rate (float): Annual risk-free rate as decimal (e.g., 0.04 for 4%)
        
    Returns:
        dict: Contains portfolio_timeline, sp500_timeline, riskfree_timeline, and summary metrics
        
    Raises:
        ValueError: If portfolio data is invalid or missing required fields
        Exception: If data fetching or calculation fails
    """
    # Validate portfolio structure
    if not portfolio_data or 'weights' not in portfolio_data or 'prices' not in portfolio_data:
        raise ValueError("Portfolio data must contain 'weights' and 'prices' fields")
    
    weights = portfolio_data['weights']
    prices = portfolio_data['prices']
    
    if not weights or not prices:
        raise ValueError("Portfolio weights and prices cannot be empty")

    cleaned_weights = {}
    for ticker, weight in weights.items():
        try:
            numeric_weight = float(weight)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid portfolio weight for {ticker}")
        if numeric_weight > 0:
            cleaned_weights[normalize_yahoo_ticker(ticker)] = numeric_weight

    if not cleaned_weights:
        raise ValueError("Portfolio weights must include at least one positive asset weight")
    
    # Extract tickers from weights
    tickers = list(cleaned_weights.keys())
    
    # Fetch historical data for portfolio tickers
    portfolio_history = {}
    failed_tickers = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                             end=end_date.strftime('%Y-%m-%d'))
            close = _extract_close_series(df).dropna()
            if not close.empty:
                portfolio_history[ticker] = _normalize_date_index(close)
            else:
                failed_tickers.append(ticker)
        except Exception as e:
            print(f"Error fetching data for {ticker}: {str(e)}")
            failed_tickers.append(ticker)
    
    if failed_tickers:
        raise ValueError(f"Could not fetch benchmark data for tickers: {', '.join(sorted(set(failed_tickers)))}")
    
    if not portfolio_history:
        raise ValueError("No valid historical data could be fetched for any portfolio tickers")

    portfolio_prices = pd.DataFrame(portfolio_history).sort_index()
    portfolio_prices = portfolio_prices.replace([np.inf, -np.inf], np.nan).ffill().dropna(how='any')
    if portfolio_prices.empty:
        raise ValueError("Insufficient overlapping portfolio price history to calculate benchmark")

    portfolio_prices, _, conversion_failures = _convert_price_data_to_usd(
        portfolio_prices,
        start_date,
        end_date,
    )
    if conversion_failures:
        raise ValueError(
            f"Could not convert benchmark prices to USD for tickers: {', '.join(sorted(conversion_failures))}"
        )

    missing_after_conversion = sorted(set(tickers) - set(portfolio_prices.columns))
    if missing_after_conversion:
        raise ValueError(
            f"Could not include benchmark tickers after currency conversion: {', '.join(missing_after_conversion)}"
        )

    portfolio_prices = portfolio_prices[tickers].replace([np.inf, -np.inf], np.nan).ffill().dropna(how='any')
    if portfolio_prices.empty:
        raise ValueError("Insufficient portfolio data after currency conversion")
    
    # Fetch S&P 500 data
    sp500 = yf.Ticker("^GSPC")
    sp500_df = sp500.history(start=start_date.strftime('%Y-%m-%d'), 
                            end=end_date.strftime('%Y-%m-%d'))
    
    if sp500_df.empty:
        raise ValueError("Failed to fetch S&P 500 benchmark data")
    
    sp500_close = _normalize_date_index(_extract_close_series(sp500_df).dropna())
    if sp500_close.empty:
        raise ValueError("Failed to fetch S&P 500 benchmark data")
    
    # Calculate shares for each ticker based on weights and initial prices
    shares = {}
    weight_sum = sum(cleaned_weights.values())
    for ticker, weight in cleaned_weights.items():
        initial_price = float(portfolio_prices[ticker].iloc[0])
        if initial_price <= 0 or not np.isfinite(initial_price):
            raise ValueError(f"Invalid start price for ticker {ticker}")
        ticker_budget = budget * (weight / weight_sum)
        shares[ticker] = ticker_budget / initial_price
                
    # Calculate S&P 500 shares
    portfolio_dates = portfolio_prices.index
    aligned_sp500 = (
        sp500_close
        .reindex(sp500_close.index.union(portfolio_dates))
        .sort_index()
        .ffill()
        .reindex(portfolio_dates)
        .dropna()
    )
    common_dates = portfolio_dates.intersection(aligned_sp500.index)
    if common_dates.empty:
        raise ValueError("Insufficient overlapping S&P 500 data to calculate benchmarks")

    portfolio_prices = portfolio_prices.loc[common_dates]
    aligned_sp500 = aligned_sp500.loc[common_dates]
    sp500_initial_price = float(aligned_sp500.iloc[0])
    if sp500_initial_price <= 0 or not np.isfinite(sp500_initial_price):
        raise ValueError("Invalid S&P 500 start price")
    sp500_shares = budget / sp500_initial_price
    
    # Build timelines
    portfolio_timeline = {}
    sp500_timeline = {}
    riskfree_timeline = {}
    
    # Calculate portfolio value for each date
    share_series = pd.Series(shares)
    portfolio_values = portfolio_prices.multiply(share_series, axis=1).sum(axis=1)
    for date, portfolio_value in portfolio_values.items():
        if portfolio_value > 0:
            portfolio_timeline[_date_to_key(date)] = float(portfolio_value)
    
    # Calculate S&P 500 value for each date
    for date, price in aligned_sp500.items():
        sp500_value = sp500_shares * price
        sp500_timeline[_date_to_key(date)] = float(sp500_value)
    
    # Calculate risk-free asset value for each date
    for date in common_dates:
        # Convert to timezone-naive datetime to avoid timezone mismatch
        if isinstance(date, datetime):
            date_naive = date.replace(tzinfo=None) if date.tzinfo else date
            days_elapsed = (date_naive - start_date).days
        else:
            # For pandas Timestamp, convert to naive datetime
            date_naive = date.to_pydatetime().replace(tzinfo=None)
            days_elapsed = (date_naive - start_date).days
        
        # Compound interest formula: P * (1 + r)^(t/365)
        riskfree_value = budget * ((1 + risk_free_rate) ** (days_elapsed / 365))
        riskfree_timeline[_date_to_key(date)] = float(riskfree_value)
    
    # Calculate summary metrics
    portfolio_dates = sorted(portfolio_timeline.keys())
    sp500_dates_sorted = sorted(sp500_timeline.keys())
    riskfree_dates = sorted(riskfree_timeline.keys())
    
    if not portfolio_dates or not sp500_dates_sorted or not riskfree_dates:
        raise ValueError("Insufficient data to calculate benchmarks")
    
    summary = {
        'portfolio': {
            'initial_value': float(budget),
            'final_value': float(portfolio_timeline[portfolio_dates[-1]]),
            'profit_loss': float(portfolio_timeline[portfolio_dates[-1]] - budget),
            'return_pct': float((portfolio_timeline[portfolio_dates[-1]] - budget) / budget * 100)
        },
        'sp500_benchmark': {
            'initial_value': float(budget),
            'final_value': float(sp500_timeline[sp500_dates_sorted[-1]]),
            'profit_loss': float(sp500_timeline[sp500_dates_sorted[-1]] - budget),
            'return_pct': float((sp500_timeline[sp500_dates_sorted[-1]] - budget) / budget * 100)
        },
        'risk_free_asset': {
            'initial_value': float(budget),
            'final_value': float(riskfree_timeline[riskfree_dates[-1]]),
            'profit_loss': float(riskfree_timeline[riskfree_dates[-1]] - budget),
            'return_pct': float((riskfree_timeline[riskfree_dates[-1]] - budget) / budget * 100)
        }
    }
    
    return {
        'portfolio_timeline': portfolio_timeline,
        'sp500_timeline': sp500_timeline,
        'riskfree_timeline': riskfree_timeline,
        'summary': summary
    }
