from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import stats
import yfinance as yf


MIN_COMMON_OBSERVATIONS = 20


class HedgeAnalysisError(Exception):
    """Base error for pairs/correlation analysis failures."""


class HedgeAnalysisInputError(ValueError, HedgeAnalysisError):
    """Raised when request parameters or aligned market data are invalid."""


class HedgeDataUnavailableError(HedgeAnalysisError):
    """Raised when yfinance returns no usable price data."""


class HedgeUpstreamError(HedgeAnalysisError):
    """Raised when an upstream market-data call fails."""


def validate_date_range(start_date, end_date):
    try:
        parsed_start = datetime.strptime(start_date, "%Y-%m-%d")
        parsed_end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as exc:
        raise HedgeAnalysisInputError("Invalid date format. Please use YYYY-MM-DD format") from exc

    if parsed_start >= parsed_end:
        raise HedgeAnalysisInputError("Start date must be before end date")

    if parsed_end > datetime.now():
        raise HedgeAnalysisInputError("End date cannot be in the future")

    return parsed_start, parsed_end


def analysis_period(start_date=None, end_date=None):
    if bool(start_date) != bool(end_date):
        raise HedgeAnalysisInputError("Both start_date and end_date are required when setting a custom period")

    if start_date and end_date:
        return validate_date_range(start_date, end_date)

    default_end = datetime.now() - timedelta(days=1)
    return default_end - timedelta(days=180), default_end


def fetch_history(stock, ticker, start_date, end_date):
    try:
        history = stock.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
        )
    except Exception as exc:
        raise HedgeUpstreamError(f"Could not fetch price history for {ticker}") from exc

    if history is None or history.empty or "Close" not in history.columns:
        raise HedgeDataUnavailableError(f"No price data available for {ticker}")

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if close.empty:
        raise HedgeDataUnavailableError(f"No usable close price data available for {ticker}")

    return close


def daily_returns(close):
    returns = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    returns.index = pd.to_datetime(returns.index).tz_localize(None).normalize()
    return returns[~returns.index.duplicated(keep="last")].sort_index()


def align_returns(returns1, returns2):
    aligned = pd.concat([returns1.rename("ticker1"), returns2.rename("ticker2")], axis=1, join="inner").dropna()
    if len(aligned) < MIN_COMMON_OBSERVATIONS:
        raise HedgeAnalysisInputError(
            f"At least {MIN_COMMON_OBSERVATIONS} overlapping daily returns are required; found {len(aligned)}"
        )

    if aligned["ticker1"].nunique() < 2 or aligned["ticker2"].nunique() < 2:
        raise HedgeAnalysisInputError("Both tickers need varying daily returns for correlation analysis")

    return aligned


def relationship_strength(correlation):
    magnitude = abs(correlation)
    if magnitude >= 0.7:
        return "Strong"
    if magnitude >= 0.4:
        return "Moderate"
    return "Weak"


def correlation_direction(correlation):
    if correlation <= -0.4:
        return "Negative"
    if correlation >= 0.4:
        return "Positive"
    return "Low"


def correlation_summary(correlation):
    direction = correlation_direction(correlation)
    if direction == "Negative":
        return "The pair has a negative return relationship over this period."
    if direction == "Positive":
        return "The pair has a positive return relationship over this period."
    return "The pair has a low linear return relationship over this period."


def safe_company_name(stock, ticker):
    try:
        info = stock.info or {}
    except Exception:
        return ticker
    return info.get("longName") or info.get("shortName") or ticker


def analyze_hedge_relationship(ticker1, ticker2, start_date=None, end_date=None):
    if ticker1 == ticker2:
        raise HedgeAnalysisInputError("ticker1 and ticker2 must be different")

    start_dt, end_dt = analysis_period(start_date, end_date)

    stock1 = yf.Ticker(ticker1)
    stock2 = yf.Ticker(ticker2)

    close1 = fetch_history(stock1, ticker1, start_dt, end_dt)
    close2 = fetch_history(stock2, ticker2, start_dt, end_dt)

    aligned = align_returns(daily_returns(close1), daily_returns(close2))
    returns1 = aligned["ticker1"]
    returns2 = aligned["ticker2"]

    correlation, p_value = stats.pearsonr(returns1, returns2)
    regression = stats.linregress(returns2, returns1)

    if not np.isfinite(correlation) or not np.isfinite(p_value):
        raise HedgeAnalysisInputError("Could not calculate a finite correlation for the selected period")

    r_squared = regression.rvalue ** 2
    strength = relationship_strength(float(correlation))
    direction = correlation_direction(float(correlation))

    return {
        "analysis_type": "pairs_correlation_regression",
        "company1": safe_company_name(stock1, ticker1),
        "company2": safe_company_name(stock2, ticker2),
        "ticker1": ticker1,
        "ticker2": ticker2,
        "period": {
            "start": start_dt.strftime("%Y-%m-%d"),
            "end": end_dt.strftime("%Y-%m-%d"),
        },
        "observations": int(len(aligned)),
        "correlation": float(correlation),
        "p_value": float(p_value),
        "strength": strength,
        "correlation_signal": {
            "direction": direction,
            "strength": strength,
            "summary": correlation_summary(float(correlation)),
        },
        "regression": {
            "alpha": float(regression.intercept),
            "beta": float(regression.slope),
            "r_squared": float(r_squared),
            "p_value": float(regression.pvalue),
            "standard_error": float(regression.stderr),
        },
    }
