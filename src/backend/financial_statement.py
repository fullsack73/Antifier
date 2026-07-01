import math
from numbers import Real

import pandas as pd
import yfinance as yf

STATEMENT_TYPES = ("income", "balance", "cash")
STATEMENT_FREQUENCIES = ("annual", "quarterly")

TOTAL_SCORE_WEIGHT = 100
DECISION_THRESHOLDS = (
    (80, "STRONG BUY"),
    (65, "BUY"),
    (50, "HOLD"),
    (35, "REDUCE"),
    (0, "SELL"),
)


def _json_safe_value(value):
    if isinstance(value, Real) and math.isinf(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _safe_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _format_number(value, decimals=2):
    number = _safe_number(value)
    if number is None:
        return "N/A"
    return f"{number:.{decimals}f}"


def _format_percent(value, decimals=1):
    number = _safe_number(value)
    if number is None:
        return "N/A"
    return f"{number * 100:.{decimals}f}%"


def _format_market_cap(value):
    number = _safe_number(value)
    if number is None:
        return "N/A"
    abs_number = abs(number)
    if abs_number >= 1_000_000_000_000:
        return f"{number / 1_000_000_000_000:.2f}T"
    if abs_number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if abs_number >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    return f"{number:,.0f}"


def _get_statement_frame(ticker, statement_type="income", frequency="annual"):
    if statement_type == "income":
        return ticker.quarterly_financials if frequency == "quarterly" else ticker.financials
    if statement_type == "balance":
        return ticker.quarterly_balance_sheet if frequency == "quarterly" else ticker.balance_sheet
    if statement_type == "cash":
        return ticker.quarterly_cashflow if frequency == "quarterly" else ticker.cashflow
    return None


def _statement_payload_from_frame(data):
    if data is None or data.empty:
        return None

    statement = data.copy()
    statement.columns = [
        col.strftime('%Y-%m-%d') if hasattr(col, 'strftime') else str(col)
        for col in statement.columns
    ]

    result = {
        "dates": list(statement.columns),
        "breakdown": []
    }

    for index, row in statement.iterrows():
        result["breakdown"].append({
            "row_label": index,
            "values": [_json_safe_value(value) for value in row.tolist()]
        })

    return result


def _calculate_debt_ratio(balance_sheet):
    if balance_sheet is None or balance_sheet.empty:
        return None

    latest_column = balance_sheet.columns[0]
    liabilities_labels = (
        "Total Liabilities Net Minority Interest",
        "Total Liabilities",
        "Total Liability",
    )
    assets_labels = ("Total Assets",)

    liabilities = None
    assets = None
    for label in liabilities_labels:
        if label in balance_sheet.index:
            liabilities = _safe_number(balance_sheet.loc[label, latest_column])
            break
    for label in assets_labels:
        if label in balance_sheet.index:
            assets = _safe_number(balance_sheet.loc[label, latest_column])
            break

    if liabilities is None or assets in (None, 0):
        return None
    return liabilities / assets


def _normalize_debt_to_equity(value):
    number = _safe_number(value)
    if number is None:
        return None
    # yfinance often returns this as percentage points, e.g. 98.5 for 0.985x.
    if abs(number) > 10:
        return number / 100
    return number


def _score_lower_better(value, good, fair, weak):
    number = _safe_number(value)
    if number is None:
        return None
    if number <= 0:
        return 0, "negative"
    if number <= good:
        return 100, "positive"
    if number <= fair:
        return 65, "neutral"
    if number <= weak:
        return 35, "caution"
    return 10, "negative"


def _score_higher_better(value, good, fair, weak):
    number = _safe_number(value)
    if number is None:
        return None
    if number >= good:
        return 100, "positive"
    if number >= fair:
        return 65, "neutral"
    if number >= weak:
        return 35, "caution"
    return 10, "negative"


def _score_current_ratio(value):
    number = _safe_number(value)
    if number is None:
        return None
    if 1.5 <= number <= 3:
        return 100, "positive"
    if 1 <= number < 1.5 or 3 < number <= 4:
        return 65, "neutral"
    if 0.75 <= number < 1 or 4 < number <= 6:
        return 35, "caution"
    return 10, "negative"


def _score_debt_ratio(value):
    number = _safe_number(value)
    if number is None:
        return None
    if number <= 0:
        return 0, "negative"
    if number <= 0.5:
        return 100, "positive"
    if number <= 0.75:
        return 65, "neutral"
    if number <= 1:
        return 35, "caution"
    return 10, "negative"


def _score_beta(value):
    number = _safe_number(value)
    if number is None:
        return None
    if 0.7 <= number <= 1.2:
        return 100, "positive"
    if 0 <= number < 0.7 or 1.2 < number <= 1.5:
        return 65, "neutral"
    if 1.5 < number <= 2:
        return 35, "caution"
    return 10, "negative"


def _benchmark_comparison(key, value, benchmarks, industry):
    benchmark = benchmarks.get(key) if benchmarks else None
    number = _safe_number(value)
    benchmark_value = _safe_number(benchmark.get("value")) if isinstance(benchmark, dict) else None

    if number is None or benchmark_value in (None, 0):
        return {
            "basis": "absolute_rule",
            "industry": industry,
            "industry_average": None,
            "status": "industry_average_unavailable",
        }

    difference = (number - benchmark_value) / abs(benchmark_value)
    if difference <= -0.05:
        position = "below"
    elif difference >= 0.05:
        position = "above"
    else:
        position = "near"

    return {
        "basis": benchmark.get("basis", "sector_average"),
        "industry": industry,
        "benchmark_name": benchmark.get("name"),
        "industry_average": benchmark_value,
        "industry_average_display": _format_number(benchmark_value),
        "relative_difference": difference,
        "relative_difference_display": _format_percent(difference),
        "position": position,
        "status": "available",
    }


def _metric(
    key,
    label,
    category,
    value,
    display_value,
    unit,
    weight,
    score_result,
    threshold_label,
    industry,
    benchmarks,
):
    if score_result is None:
        score = None
        signal = "missing"
    else:
        score, signal = score_result

    return {
        "key": key,
        "label": label,
        "category": category,
        "value": _safe_number(value),
        "display_value": display_value,
        "unit": unit,
        "weight": weight,
        "score": score,
        "signal": signal,
        "threshold": threshold_label,
        "comparison": _benchmark_comparison(key, value, benchmarks, industry),
    }


def _average(values):
    cleaned = [_safe_number(value) for value in values]
    cleaned = [value for value in cleaned if value is not None and value > 0]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _fetch_sector_benchmarks(info, ticker_symbol, sample_size=25):
    sector = info.get("sector")
    if not sector:
        return {}
    country = str(info.get("country") or "").strip().lower()
    if country and country not in {"united states", "usa", "us"}:
        return {}

    try:
        query = yf.EquityQuery("and", [
            yf.EquityQuery("eq", ["region", "us"]),
            yf.EquityQuery("eq", ["sector", sector]),
        ])
        response = yf.screen(
            query,
            size=sample_size,
            sortField="intradaymarketcap",
            sortAsc=False,
        )
    except Exception:
        return {}

    quotes = response.get("quotes", []) if isinstance(response, dict) else []
    if not quotes:
        return {}

    current_symbol = str(ticker_symbol or "").upper()
    peer_quotes = [
        quote for quote in quotes
        if str(quote.get("symbol", "")).upper() != current_symbol
    ] or quotes

    field_map = {
        "per": "trailingPE",
        "forward_pe": "forwardPE",
        "pbr": "priceToBook",
        "psr": "priceToSalesTrailing12Months",
    }
    benchmarks = {}

    for metric_key, quote_field in field_map.items():
        average = _average(quote.get(quote_field) for quote in peer_quotes)
        if average is not None:
            benchmarks[metric_key] = {
                "basis": "sector_average",
                "name": sector,
                "value": average,
                "sample_size": len(peer_quotes),
            }

    return benchmarks


def _build_investment_metrics(info, debt_ratio, benchmarks=None):
    industry = info.get("industry") or info.get("sector") or "N/A"
    pe_ratio = _safe_number(info.get("trailingPE"))
    forward_pe = _safe_number(info.get("forwardPE"))
    pb_ratio = _safe_number(info.get("priceToBook"))
    ps_ratio = _safe_number(info.get("priceToSalesTrailing12Months"))
    peg_ratio = _safe_number(info.get("pegRatio") or info.get("trailingPegRatio"))
    current_ratio = _safe_number(info.get("currentRatio"))
    quick_ratio = _safe_number(info.get("quickRatio"))
    debt_to_equity = _normalize_debt_to_equity(info.get("debtToEquity"))
    roe = _safe_number(info.get("returnOnEquity"))
    roa = _safe_number(info.get("returnOnAssets"))
    profit_margin = _safe_number(info.get("profitMargins") or info.get("profitMargin"))
    operating_margin = _safe_number(info.get("operatingMargins"))
    revenue_growth = _safe_number(info.get("revenueGrowth"))
    earnings_growth = _safe_number(info.get("earningsGrowth"))
    beta = _safe_number(info.get("beta"))

    return [
        _metric("per", "P/E", "valuation", pe_ratio, _format_number(pe_ratio), "ratio", 8,
                _score_lower_better(pe_ratio, 15, 25, 40), "<=15 attractive, 15-25 fair, >40 expensive", industry, benchmarks),
        _metric("forward_pe", "Forward P/E", "valuation", forward_pe, _format_number(forward_pe), "ratio", 6,
                _score_lower_better(forward_pe, 15, 25, 40), "<=15 attractive, 15-25 fair, >40 expensive", industry, benchmarks),
        _metric("pbr", "P/B", "valuation", pb_ratio, _format_number(pb_ratio), "ratio", 7,
                _score_lower_better(pb_ratio, 1.5, 3, 6), "<=1.5 attractive, 1.5-3 fair, >6 expensive", industry, benchmarks),
        _metric("psr", "P/S", "valuation", ps_ratio, _format_number(ps_ratio), "ratio", 5,
                _score_lower_better(ps_ratio, 2, 5, 10), "<=2 attractive, 2-5 fair, >10 expensive", industry, benchmarks),
        _metric("peg", "PEG", "valuation", peg_ratio, _format_number(peg_ratio), "ratio", 7,
                _score_lower_better(peg_ratio, 1, 2, 3), "<=1 attractive, 1-2 fair, >3 expensive", industry, benchmarks),
        _metric("roe", "ROE", "profitability", roe, _format_percent(roe), "percent", 9,
                _score_higher_better(roe, 0.15, 0.08, 0), ">=15% strong, 8-15% fair, <0% weak", industry, benchmarks),
        _metric("roa", "ROA", "profitability", roa, _format_percent(roa), "percent", 5,
                _score_higher_better(roa, 0.07, 0.03, 0), ">=7% strong, 3-7% fair, <0% weak", industry, benchmarks),
        _metric("profit_margin", "Profit Margin", "profitability", profit_margin, _format_percent(profit_margin), "percent", 8,
                _score_higher_better(profit_margin, 0.15, 0.05, 0), ">=15% strong, 5-15% fair, <0% weak", industry, benchmarks),
        _metric("operating_margin", "Operating Margin", "profitability", operating_margin, _format_percent(operating_margin), "percent", 5,
                _score_higher_better(operating_margin, 0.15, 0.05, 0), ">=15% strong, 5-15% fair, <0% weak", industry, benchmarks),
        _metric("revenue_growth", "Revenue Growth", "growth", revenue_growth, _format_percent(revenue_growth), "percent", 7,
                _score_higher_better(revenue_growth, 0.10, 0, -0.05), ">=10% strong, 0-10% fair, <-5% weak", industry, benchmarks),
        _metric("earnings_growth", "Earnings Growth", "growth", earnings_growth, _format_percent(earnings_growth), "percent", 7,
                _score_higher_better(earnings_growth, 0.10, 0, -0.05), ">=10% strong, 0-10% fair, <-5% weak", industry, benchmarks),
        _metric("debt_to_equity", "Debt/Equity", "stability", debt_to_equity, _format_number(debt_to_equity), "ratio", 7,
                _score_lower_better(debt_to_equity, 0.8, 1.5, 3), "<=0.8 conservative, 0.8-1.5 fair, >3 stretched", industry, benchmarks),
        _metric("debt_ratio", "Debt Ratio", "stability", debt_ratio, _format_number(debt_ratio), "ratio", 6,
                _score_debt_ratio(debt_ratio), "<=0.5 conservative, 0.5-0.75 fair, >1 stretched", industry, benchmarks),
        _metric("current_ratio", "Current Ratio", "stability", current_ratio, _format_number(current_ratio), "ratio", 5,
                _score_current_ratio(current_ratio), "1.5-3 healthy, <1 liquidity risk, >4 potential idle capital", industry, benchmarks),
        _metric("quick_ratio", "Quick Ratio", "stability", quick_ratio, _format_number(quick_ratio), "ratio", 4,
                _score_current_ratio(quick_ratio), "1.5-3 healthy, <1 liquidity risk, >4 potential idle capital", industry, benchmarks),
        _metric("beta", "Beta", "risk", beta, _format_number(beta), "ratio", 4,
                _score_beta(beta), "0.7-1.2 balanced, >1.5 volatile, <0 defensive", industry, benchmarks),
    ]


def _decision_from_score(score, confidence):
    if score is None or confidence < 20:
        return "INSUFFICIENT DATA"
    for minimum, label in DECISION_THRESHOLDS:
        if score >= minimum:
            return label
    return "SELL"


def _score_dashboard_metrics(metrics):
    available = [metric for metric in metrics if metric["score"] is not None]
    possible_weight = sum(metric["weight"] for metric in metrics)
    available_weight = sum(metric["weight"] for metric in available)

    if not available or not available_weight:
        return {
            "score": None,
            "max_score": TOTAL_SCORE_WEIGHT,
            "available_metrics": 0,
            "total_metrics": len(metrics),
            "confidence": 0,
            "label": "INSUFFICIENT DATA",
        }

    weighted_score = sum(metric["score"] * metric["weight"] for metric in available)
    score = round(weighted_score / available_weight)
    confidence = round((available_weight / possible_weight) * 100) if possible_weight else 0

    return {
        "score": score,
        "max_score": TOTAL_SCORE_WEIGHT,
        "available_metrics": len(available),
        "total_metrics": len(metrics),
        "confidence": confidence,
        "label": _decision_from_score(score, confidence),
    }


def _collect_all_statements(ticker):
    statements = {}
    errors = {}

    for frequency in STATEMENT_FREQUENCIES:
        statements[frequency] = {}
        errors[frequency] = {}

        for statement_type in STATEMENT_TYPES:
            try:
                frame = _get_statement_frame(ticker, statement_type, frequency)
                payload = _statement_payload_from_frame(frame)
                if payload is None:
                    statements[frequency][statement_type] = None
                    errors[frequency][statement_type] = f"No {frequency} {statement_type} statement data found."
                else:
                    statements[frequency][statement_type] = payload
            except Exception as exc:
                statements[frequency][statement_type] = None
                errors[frequency][statement_type] = str(exc)

    return statements, errors


def _legacy_ratios_from_metrics(ticker_symbol, info, metrics):
    by_key = {metric["key"]: metric for metric in metrics}
    return {
        "ticker": ticker_symbol,
        "longName": info.get('longName'),
        "per": by_key.get("per", {}).get("display_value", "N/A"),
        "pbr": by_key.get("pbr", {}).get("display_value", "N/A"),
        "psr": by_key.get("psr", {}).get("display_value", "N/A"),
        "debt_ratio": by_key.get("debt_ratio", {}).get("display_value", "N/A"),
        "liquidity_ratio": by_key.get("current_ratio", {}).get("display_value", "N/A"),
    }

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
        info = ticker.info or {}
        debt_ratio = _calculate_debt_ratio(ticker.balance_sheet)
        metrics = _build_investment_metrics(info, debt_ratio)
        return _legacy_ratios_from_metrics(ticker_symbol, info, metrics)

    except (KeyError, IndexError, TypeError) as e:
        return {"error": f"Could not retrieve all financial data for {ticker_symbol}. Some data might be unavailable."}


def get_financial_dashboard(ticker_symbol):
    """
    Fetches investment-oriented financial metrics plus full statement tables.
    The decision label is a rule-based analytical signal, not investment advice.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}
        if not isinstance(info, dict):
            info = {}

        balance_sheet = _get_statement_frame(ticker, "balance", "annual")
        debt_ratio = _calculate_debt_ratio(balance_sheet)
        benchmarks = _fetch_sector_benchmarks(info, ticker_symbol)
        metrics = _build_investment_metrics(info, debt_ratio, benchmarks)
        decision = _score_dashboard_metrics(metrics)
        statements, statement_errors = _collect_all_statements(ticker)
        ratios = _legacy_ratios_from_metrics(ticker_symbol, info, metrics)

        return {
            **ratios,
            "company": {
                "ticker": ticker_symbol,
                "name": info.get("longName") or info.get("shortName") or ticker_symbol,
                "sector": info.get("sector") or "N/A",
                "industry": info.get("industry") or "N/A",
                "currency": info.get("currency") or info.get("financialCurrency") or "N/A",
                "market_cap": _safe_number(info.get("marketCap")),
                "market_cap_display": _format_market_cap(info.get("marketCap")),
            },
            "metrics": metrics,
            "decision": decision,
            "statements": statements,
            "statement_errors": statement_errors,
            "analysis_note": "Rule-based financial signal generated from available yfinance data. It is not investment advice.",
        }

    except Exception as e:
        return {"error": f"Error fetching financial dashboard: {str(e)}"}


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
        data = _get_statement_frame(ticker, statement_type, frequency)

        if data is None:
            return {"error": "Invalid statement type. Choose 'income', 'balance', or 'cash'."}

        if data is None or data.empty:
             return {"error": f"No {frequency} {statement_type} statement data found for {ticker_symbol}."}

        return _statement_payload_from_frame(data)

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
