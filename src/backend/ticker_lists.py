import pandas as pd
import os
import logging

from ticker_symbols import normalize_yahoo_ticker

logger = logging.getLogger(__name__)

# Helper to find file in CWD or up one level (root)
def find_file(filename):
    if os.path.exists(filename):
        return filename
    # Check parent dir if we are in src
    parent = os.path.join(os.path.dirname(os.getcwd()), filename)
    if os.path.exists(parent):
        return parent
    # Check if we are in src and file is in root relative to file location
    file_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(file_dir)
    possible_path = os.path.join(root_dir, filename)
    if os.path.exists(possible_path):
        return possible_path
    return None

def get_sp500_tickers():
    """Gets the list of S&P 500 tickers from snp.csv."""
    try:
        csv_path = find_file('snp.csv')
        if csv_path:
            df = pd.read_csv(csv_path)
            return [normalize_yahoo_ticker(symbol) for symbol in df['Symbol'].tolist()]
        else:
            logger.error("snp.csv not found")
            return []
    except Exception as e:
        logger.error(f"Error fetching S&P 500 tickers: {e}")
        return []

def get_dow_tickers():
    """Gets the list of Dow Jones tickers from dow.csv."""
    try:
        csv_path = find_file('dow.csv')
        if csv_path:
            df = pd.read_csv(csv_path)
            return df['Symbol'].tolist()
        else:
            logger.error("dow.csv not found")
            return []
    except Exception as e:
        logger.error(f"Error fetching Dow Jones tickers: {e}")
        return []

TICKER_GROUPS = {
    "S&P 500": get_sp500_tickers,
    "Dow Jones": get_dow_tickers,
    "Any": get_sp500_tickers # Default to S&P 500 for 'Any' to avoid blowing up
}

def get_ticker_group(group_name):
    """Returns a list of tickers for a given group name."""
    # Map frontend names to keys if necessary
    mapping = {
        "S&P 500": "S&P 500",
        "DJIA": "Dow Jones",
        "Dow Jones": "Dow Jones",
        "DOW": "Dow Jones",
        "Dow": "Dow Jones",
        "Any": "Any"
    }
    
    key = mapping.get(group_name, "Any")
    
    if key in TICKER_GROUPS:
        return TICKER_GROUPS[key]()
    else:
        logger.warning(f"Unknown ticker group: {group_name}, defaulting to S&P 500")
        return TICKER_GROUPS["S&P 500"]()
