"""
Portfolio Benchmarking Module

This module provides functionality to benchmark a portfolio against S&P 500 and risk-free assets
over a specified time period. It calculates historical performance metrics and aggregated returns.
"""

import yfinance as yf
from datetime import datetime


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
    
    # Extract tickers from weights
    tickers = list(weights.keys())
    
    # Fetch historical data for portfolio tickers
    portfolio_history = {}
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                             end=end_date.strftime('%Y-%m-%d'))
            if not df.empty:
                portfolio_history[ticker] = df['Close'].to_dict()
            else:
                # Skip ticker if no data available
                print(f"Warning: No data available for ticker {ticker}")
        except Exception as e:
            print(f"Error fetching data for {ticker}: {str(e)}")
            continue
    
    if not portfolio_history:
        raise ValueError("No valid historical data could be fetched for any portfolio tickers")
    
    # Fetch S&P 500 data
    sp500 = yf.Ticker("^GSPC")
    sp500_df = sp500.history(start=start_date.strftime('%Y-%m-%d'), 
                            end=end_date.strftime('%Y-%m-%d'))
    
    if sp500_df.empty:
        raise ValueError("Failed to fetch S&P 500 benchmark data")
    
    sp500_history = sp500_df['Close'].to_dict()
    
    # Calculate shares for each ticker based on weights and initial prices
    shares = {}
    for ticker, weight in weights.items():
        if ticker in portfolio_history: # ticker needs to be in history to get start price
            ticker_budget = budget * weight
            
            # CRITICAL FIX: Use the price at start_date, NOT the 'prices' argument (which is latest price)
            # Find the first available date in the history
            ticker_dates = sorted(portfolio_history[ticker].keys())
            if not ticker_dates:
                print(f"Warning: No history data for {ticker}, skipping")
                continue
                
            first_date = ticker_dates[0]
            initial_price = portfolio_history[ticker][first_date]
            
            # Handle zero or invalid prices
            if initial_price > 0:
                shares[ticker] = ticker_budget / initial_price
            else:
                print(f"Warning: Invalid start price for {ticker}, skipping")
                shares[ticker] = 0
                
    # Calculate S&P 500 shares
    sp500_dates = list(sp500_history.keys())
    # Sort just in case dictionary isn't ordered
    sp500_dates.sort()
    if sp500_dates:
        sp500_initial_price = sp500_history[sp500_dates[0]]
        sp500_shares = budget / sp500_initial_price if sp500_initial_price > 0 else 0
    else:
        sp500_shares = 0
    
    # Build timelines
    portfolio_timeline = {}
    sp500_timeline = {}
    riskfree_timeline = {}
    
    # Get all unique dates from available data
    all_dates = set()
    for ticker_data in portfolio_history.values():
        all_dates.update(ticker_data.keys())
    all_dates.update(sp500_history.keys())
    
    # Sort dates
    sorted_dates = sorted(all_dates)
    
    # Calculate portfolio value for each date
    for date in sorted_dates:
        portfolio_value = 0
        for ticker, ticker_shares in shares.items():
            if ticker in portfolio_history and date in portfolio_history[ticker]:
                portfolio_value += ticker_shares * portfolio_history[ticker][date]
        
        if portfolio_value > 0:  # Only add if we have valid data
            date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date).split(' ')[0]
            portfolio_timeline[date_str] = float(portfolio_value)
    
    # Calculate S&P 500 value for each date
    for date, price in sp500_history.items():
        sp500_value = sp500_shares * price
        date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date).split(' ')[0]
        sp500_timeline[date_str] = float(sp500_value)
    
    # Calculate risk-free asset value for each date
    for date in sorted_dates:
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
        date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date).split(' ')[0]
        riskfree_timeline[date_str] = float(riskfree_value)
    
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
