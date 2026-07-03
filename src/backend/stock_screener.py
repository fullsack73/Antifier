import logging
import yfinance as yf
import pandas as pd
import numpy as np
from cache_manager import cached
from financial_statement import build_financial_decision_summary
from ticker_lists import get_ticker_group
import time

# Configure logging for this module
logger = logging.getLogger(__name__)

import concurrent.futures


METRIC_ALIASES = {
    'financial score': 'Financial Score',
    'financial_score': 'Financial Score',
    'score': 'Financial Score',
    'decision score': 'Financial Score',
    'decision_score': 'Financial Score',
    'pe': 'P/E',
    'p/e': 'P/E',
    'trailing pe': 'P/E',
    'trailing_pe': 'P/E',
    'forward pe': 'Forward P/E',
    'forward_pe': 'Forward P/E',
    'fwd pe': 'Forward P/E',
    'fwd_pe': 'Forward P/E',
    'pb': 'P/B',
    'p/b': 'P/B',
    'p_b': 'P/B',
    'price book': 'P/B',
    'price_book': 'P/B',
    'price to book': 'P/B',
    'price_to_book': 'P/B',
    'price sales': 'Price/Sales',
    'price_sales': 'Price/Sales',
    'price/sales': 'Price/Sales',
    'psr': 'Price/Sales',
    'p/s': 'Price/Sales',
    'peg': 'PEG',
    'debt equity': 'Debt/Equity',
    'debt_equity': 'Debt/Equity',
    'debt/equity': 'Debt/Equity',
    'debt to equity': 'Debt/Equity',
    'debt_to_equity': 'Debt/Equity',
    'roe': 'ROE',
    'return on equity': 'ROE',
    'return_on_equity': 'ROE',
    'roa': 'ROA',
    'return on assets': 'ROA',
    'return_on_assets': 'ROA',
    'profit margin': 'Profit Margin',
    'profit_margin': 'Profit Margin',
    'market cap': 'Market Cap',
    'market_cap': 'Market Cap',
    'market capitalization': 'Market Cap',
    'price': 'Price',
    'current price': 'Price',
    'current_price': 'Price',
}

OPERATOR_ALIASES = {
    'under': '<',
    'below': '<',
    'less': '<',
    'less_than': '<',
    'lt': '<',
    '<': '<',
    'over': '>',
    'above': '>',
    'greater': '>',
    'greater_than': '>',
    'gt': '>',
    '>': '>',
    'equals': '=',
    'equal': '=',
    'eq': '=',
    '=': '=',
    '==': '=',
    'at least': '>=',
    'at_least': '>=',
    'minimum': '>=',
    'min': '>=',
    'gte': '>=',
    'ge': '>=',
    '>=': '>=',
    'at most': '<=',
    'at_most': '<=',
    'maximum': '<=',
    'max': '<=',
    'lte': '<=',
    'le': '<=',
    '<=': '<=',
}


def _normalize_filter_token(value):
    return str(value or '').strip().replace('-', ' ').replace('_', ' ').lower()


def _normalize_metric_name(metric):
    if metric is None:
        return None

    metric_str = str(metric).strip()
    if not metric_str:
        return None

    exact_alias = METRIC_ALIASES.get(metric_str.lower())
    if exact_alias:
        return exact_alias

    normalized = _normalize_filter_token(metric_str)
    return METRIC_ALIASES.get(normalized, metric_str)


def _normalize_operator(operator):
    if operator is None:
        return None

    operator_str = str(operator).strip()
    if not operator_str:
        return None

    exact_alias = OPERATOR_ALIASES.get(operator_str.lower())
    if exact_alias:
        return exact_alias

    normalized = _normalize_filter_token(operator_str)
    return OPERATOR_ALIASES.get(normalized)

def fetch_single_stock_data(ticker_symbol):
    """
    Fetches score-oriented data for a single ticker. Used for parallel execution.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        score_summary = build_financial_decision_summary(ticker_symbol, ticker=ticker)
        info = score_summary.get("info") or {}
        company = score_summary.get("company") or {}
        decision = score_summary.get("decision") or {}
        metrics_by_key = {
            metric.get("key"): metric
            for metric in score_summary.get("metrics", [])
            if isinstance(metric, dict)
        }

        def metric_value(key):
            metric = metrics_by_key.get(key) or {}
            return metric.get("value")

        return {
            'Ticker': ticker_symbol,
            'Company': company.get('name') or ticker_symbol,
            'Sector': company.get('sector') or 'N/A',
            'Industry': company.get('industry') or 'N/A',
            'Currency': company.get('currency') or info.get('currency') or 'N/A',
            'Price': info.get('currentPrice') or info.get('regularMarketPrice'),
            'Market Cap': company.get('market_cap'),
            'Financial Score': decision.get('score'),
            'Financial Signal': decision.get('label'),
            'Score Confidence': decision.get('confidence'),
            'Available Metrics': decision.get('available_metrics'),
            'Total Metrics': decision.get('total_metrics'),
            'P/E': metric_value('per'),
            'Forward P/E': metric_value('forward_pe'),
            'P/B': metric_value('pbr'),
            'Price/Sales': metric_value('psr'),
            'PEG': metric_value('peg'),
            'Debt/Equity': metric_value('debt_to_equity'),
            'ROE': metric_value('roe'),
            'ROA': metric_value('roa'),
            'Profit Margin': metric_value('profit_margin')
        }
    except Exception as e:
        logger.debug(f"Failed to fetch data for {ticker_symbol}: {e}")
        return None

def fetch_universe_data(tickers):
    """
    Fetches key statistics for a list of tickers using yfinance.
    Optimized to use yfinance's multi-threading and caching.
    """
    data = []
    
    start_time = time.time()
    logger.info(f"Fetching data for {len(tickers)} tickers in parallel...")
    
    # Use ThreadPoolExecutor for I/O bound tasks
    # Limit max_workers to avoid hitting API rate limits or overwhelming the system
    # 20 workers is a reasonable starting point for network requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_ticker = {executor.submit(fetch_single_stock_data, t): t for t in tickers}
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker_symbol = future_to_ticker[future]
            try:
                result = future.result()
                if result:
                    data.append(result)
            except Exception as e:
                logger.error(f"Exc generated for {ticker_symbol}: {e}")

    logger.info(f"Fetched data for {len(data)} stocks in {time.time() - start_time:.2f}s")
    return pd.DataFrame(data)

@cached(l1_ttl=3600, l2_ttl=86400) # Only cache the UNIVERSE data, not the filtered result
def get_universe_dataframe(group_name):
    """
    Gets the dataframe for a whole ticker group (e.g. SP500).
    Values are cached.
    """
    tickers = get_ticker_group(group_name)
    if not tickers:
        logger.warning(f"No tickers found for group {group_name}")
        return pd.DataFrame() # Empty
        
    return fetch_universe_data(tickers)

def apply_filters(df, filters):
    """
    Applies filters to the DataFrame.
    filters: list of dicts { 'metric': 'Financial Score', 'operator': 'Over', 'value': 65 }
    """
    if df.empty:
        return df
        
    filtered_df = df.copy()
    
    for f in filters:
        metric = _normalize_metric_name(f.get('metric'))
        operator = _normalize_operator(f.get('operator'))
        value_str = str(f.get('value', ''))
        
        if not metric or not operator or not value_str:
            continue
            
        if metric not in filtered_df.columns:
            logger.warning(f"Metric {metric} not found in data")
            continue
            
        # Parse value (remove % or other chars if needed)
        try:
            clean_val_str = value_str.replace('%', '').replace(',', '').strip()
            value = float(clean_val_str)
            
            # Handle percentage metrics (ROE is often e.g. 0.15 for 15%)
            # If user types 15 for ROE, and data is 0.15, we might need adjustment.
            # yfinance returns ROE as 0.15 for 15%. 
            # If user inputs "15", we assume they mean 15% -> 0.15? Or user inputs 0.15?
            # Standard convention: 
            # P/E, P/B are raw numbers.
            # ROE, Margins are ratios (0.15).
            # Debt/Eq is ratio (e.g. 150 -> 1.5? or 150?) yfinance debtToEquity is typically percentage (e.g., 150 for 150%). 
            # Wait, yfinance debtToEquity is usually e.g. 98.544.
            
            # Heuristic: If metric is typically a percentage and value > 1, assume user used percentage points (15) and convert to decimal?
            # Actually, let's treat user input as direct comparison to yfinance output for now, but maybe divide by 100 for specific known percentage fields if the user input > 1.
            # For simplicity, I will implement exact comparison first.
            # BUT: ROE in yfinance is 0.xx. Users will type 15 (for %).
            
            is_percentage_field = metric in ['ROE', 'ROA', 'Profit Margin']
            if is_percentage_field and abs(value) > 1:
                value = value / 100.0
                
            column = pd.to_numeric(filtered_df[metric], errors='coerce')
            
            if operator == '<':
                filtered_df = filtered_df[column < value]
            elif operator == '>':
                filtered_df = filtered_df[column > value]
            elif operator == '=':
                filtered_df = filtered_df[column == value]
            elif operator == '<=':
                filtered_df = filtered_df[column <= value]
            elif operator == '>=':
                filtered_df = filtered_df[column >= value]
            
        except ValueError:
            logger.warning(f"Could not parse value {value_str} for filter {metric}")
            continue
            
    return filtered_df

def search_stocks(filters):
    """
    Main entry point for screening.
    """
    logger.info(f"Screening stocks with filters: {filters}")
    
    # 'Index' in filters determines the universe
    # Default global filters structure from frontend might be:
    # { 'Index': 'S&P 500', 'P/E': 'Under 15' ... } <- Old format
    # New format plan: { 'filters': [ { metric, operator, value } ], 'ticker_group': '...' }
    # BUT, to maintain backward compatibility if the frontend sends the old map, we should handle it,
    # OR we rely on the frontend sending the new structure I will implement.
    
    # I will support the structure passed by the NEW frontend.
    # The arguments to this function come from `app.py`.
    # `app.py` extracts `filters` from JSON body.
    
    # Let's assume the argument `filters` is the dictionary passed from `stock_screener_endpoint`.
    # If it's the OLD format (dict of keys), we need to adapt.
    # If it's the NEW format (list of dicts + group), it's cleaner.
    
    # Adaptation:
    ticker_group = filters.get('Index', 'S&P 500')
    custom_tickers = filters.get('tickers', None)
    
    # If custom tickers are provided, fetch their data directly (no cache)
    if custom_tickers and isinstance(custom_tickers, list) and len(custom_tickers) > 0:
        logger.info(f"Using {len(custom_tickers)} custom tickers for screening")
        df_universe = fetch_universe_data(custom_tickers)
    else:
        # Get universe data (Cached)
        df_universe = get_universe_dataframe(ticker_group)
    
    if df_universe.empty:
        return []
        
    # Convert 'filters' dict to list of operations if it's the old style, 
    # OR if my frontend passes a list, use that.
    # The frontend currently sends: { 'Index': ..., 'P/E': 'Under 15' }
    # I will change the frontend to send a cleaner structure, BUT I must handle the parsing here.
    
    filter_list = []
    
    # If 'filters' has a 'criteria' key (new design), use it.
    # Otherwise parse the flat dict.
    if 'criteria' in filters and isinstance(filters['criteria'], list):
         filter_list = filters['criteria']
    else:
        # Parse messy string format "Under 15"
        for key, val in filters.items():
            if key in ('Index', 'tickers'):
                continue
            if not isinstance(val, str):
                continue
            
            parts = val.split(' ')
            if len(parts) >= 2:
                op = parts[0] # Under, Over
                v = parts[1]
                filter_list.append({
                    'metric': key,
                    'operator': op,
                    'value': v
                })
    
    results_df = apply_filters(df_universe, filter_list)
    if 'Financial Score' in results_df.columns:
        results_df = results_df.sort_values(by='Financial Score', ascending=False, na_position='last')
    
    # Clean up for JSON
    results_df = results_df.replace({np.nan: None})
    
    return results_df.to_dict('records')
