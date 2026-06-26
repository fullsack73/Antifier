import math
from numbers import Real

import pandas as pd
import yfinance as yf


def _json_safe_value(value):
    if isinstance(value, Real) and math.isinf(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value

def get_financial_ratios(ticker_symbol):
    """
    Fetches key financial ratios for a given stock ticker.

    Args:
        ticker_symbol (str): The stock ticker symbol (e.g., "MSFT").

    Returns:
        dict: A dictionary containing the financial ratios.
              Returns an error message in the 'error' key if data is unavailable.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info

        # --- Get ratios from .info dictionary ---
        pe_ratio = info.get('trailingPE')
        pb_ratio = info.get('priceToBook')
        ps_ratio = info.get('priceToSalesTrailing12Months')
        liquidity_ratio = info.get('currentRatio')

        # --- Calculate Debt Ratio from Balance Sheet ---
        balance_sheet = ticker.balance_sheet
        debt_ratio = None
        if not balance_sheet.empty:
            # yfinance balance sheet columns are timestamps, get the most recent one
            latest_column = balance_sheet.columns[0]
            if 'Total Liabilities Net Minority Interest' in balance_sheet.index and 'Total Assets' in balance_sheet.index:
                total_debt = balance_sheet.loc['Total Liabilities Net Minority Interest', latest_column]
                total_assets = balance_sheet.loc['Total Assets', latest_column]
                debt_ratio = total_debt / total_assets if total_assets else None

        ratios = {
            "ticker": ticker_symbol,
            "longName": info.get('longName'),
            "per": f"{pe_ratio:.2f}" if pe_ratio is not None else "N/A",
            "pbr": f"{pb_ratio:.2f}" if pb_ratio is not None else "N/A",
            "psr": f"{ps_ratio:.2f}" if ps_ratio is not None else "N/A",
            "debt_ratio": f"{debt_ratio:.2f}" if debt_ratio is not None else "N/A",
            "liquidity_ratio": f"{liquidity_ratio:.2f}" if liquidity_ratio is not None else "N/A",
        }
        return ratios

    except (KeyError, IndexError, TypeError) as e:
        return {"error": f"Could not retrieve all financial data for {ticker_symbol}. Some data might be unavailable."}

def get_financial_statements(ticker_symbol, statement_type="income", frequency="annual"):
    """
    Fetches financial statements for a given stock ticker.

    Args:
        ticker_symbol (str): The stock ticker symbol.
        statement_type (str): "income", "balance", or "cash".
        frequency (str): "annual" or "quarterly".

    Returns:
        dict: A dictionary containing the financial statement data.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # Determine which attribute to access based on type and frequency
        if statement_type == "income":
            if frequency == "quarterly":
                data = ticker.quarterly_financials
            else:
                data = ticker.financials
        elif statement_type == "balance":
            if frequency == "quarterly":
                data = ticker.quarterly_balance_sheet
            else:
                data = ticker.balance_sheet
        elif statement_type == "cash":
            if frequency == "quarterly":
                data = ticker.quarterly_cashflow
            else:
                data = ticker.cashflow
        else:
             return {"error": "Invalid statement type. Choose 'income', 'balance', or 'cash'."}

        if data is None or data.empty:
             return {"error": f"No {frequency} {statement_type} statement data found for {ticker_symbol}."}

        # Convert DataFrame to a format suitable for JSON response (frontend table)
        # We want columns to be dates (as strings) and index to be line items
        
        # Format columns (dates) to string 'YYYY-MM-DD'
        data.columns = [col.strftime('%Y-%m-%d') if hasattr(col, 'strftime') else str(col) for col in data.columns]
        
        # Prepare structure: columns list and rows dictionary
        result = {
            "dates": list(data.columns),
            "breakdown": []
        }
        
        for index, row in data.iterrows():
            result["breakdown"].append({
                "row_label": index,
                "values": [_json_safe_value(value) for value in row.tolist()]
            })
            
        return result

    except Exception as e:
        return {"error": f"Error fetching financial statements: {str(e)}"}

# Example usage:
if __name__ == '__main__':
    print("--- Running financial_statement.py script ---")
    # You can change this ticker symbol to test with others
    test_ticker = "AAPL"
    financial_data = get_financial_ratios(test_ticker)
    print(financial_data)

    test_ticker_2 = "GOOGL"
    financial_data_2 = get_financial_ratios(test_ticker_2)
    print(financial_data_2)
