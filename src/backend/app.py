from native_threading import configure_native_threading

configure_native_threading()

from flask import Flask, jsonify, request
from flask_cors import CORS
import numpy as np
import yfinance as yf
import warnings
import re
import os
import hashlib
from datetime import datetime, timedelta
import pandas as pd
from hedge_analysis import analyze_hedge_relationship
from portfolio_benchmark import calculate_portfolio_benchmark


from forecast_models import LSTMPriceModel, LightGBMPriceModel, ARIMAPriceModel
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from financial_statement import get_financial_dashboard, get_financial_statements
from portfolio_optimization import (
    optimize_portfolio,
    load_portfolio_result,
    list_saved_portfolios,
    manage_portfolio_logic,
    get_asset_names,
    forecast_single_ticker_with_arima_transformer,
    forecast_single_ticker_with_transformer
)
from stock_screener import search_stocks


app = Flask(__name__)


class ExternalDataError(RuntimeError):
    """Raised when an upstream market-data dependency cannot satisfy a request."""


class ModelExecutionError(RuntimeError):
    """Raised when a local model fails while serving an otherwise valid request."""

BASE_CURRENCY = "USD"
TRADING_DAYS_PER_YEAR = 252
MONTE_CARLO_SIMULATIONS = 500
MIN_DAILY_VOLATILITY = 0.0025
MAX_DAILY_VOLATILITY = 0.12
ENSEMBLE_MODEL_TYPES = {
    "DEEP_LEARNING",
    "ENSEMBLE",
    "DEEP LEARNING ENSEMBLE",
    "ARIMA_TRANSFORMER",
    "ARIMA + TRANSFORMER",
}
TRANSFORMER_MODEL_TYPES = {"TRANSFORMER"}
STOCK_MODEL_TYPES = {"LSTM", "LightGBM", "ARIMA"} | ENSEMBLE_MODEL_TYPES | TRANSFORMER_MODEL_TYPES
SAFE_TICKER_PATTERN = re.compile(r"^[A-Za-z0-9.^=\-]{1,24}$")
DIRECT_USD_QUOTE_CURRENCIES = {"AUD", "EUR", "GBP", "NZD"}
TICKER_SUFFIX_CURRENCIES = {
    ".KS": "KRW",
    ".KQ": "KRW",
    ".T": "JPY",
    ".HK": "HKD",
    ".L": "GBp",
    ".AX": "AUD",
    ".TO": "CAD",
    ".V": "CAD",
    ".PA": "EUR",
    ".DE": "EUR",
    ".F": "EUR",
    ".MI": "EUR",
    ".MC": "EUR",
    ".AS": "EUR",
    ".BR": "EUR",
    ".SW": "CHF",
    ".ST": "SEK",
    ".OL": "NOK",
    ".CO": "DKK",
    ".SS": "CNY",
    ".SZ": "CNY",
    ".TW": "TWD",
    ".SI": "SGD",
    ".BO": "INR",
    ".NS": "INR",
    ".SA": "BRL",
    ".MX": "MXN",
    ".JO": "ZAR",
}

ALLOWED_CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

CORS(app, 
     resources={
         "/*": {
             "origins": ALLOWED_CORS_ORIGINS,
             "methods": ["GET", "POST", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization", "Accept"],
             "supports_credentials": True,
             "expose_headers": ["Content-Type", "Authorization"],
             "max_age": 3600
         }
     })


def normalize_ticker_param(value, default=None, field_name="ticker"):
    ticker = str(value or default or "").strip().upper()
    if not ticker:
        raise ValueError(f"{field_name} is required")
    if not SAFE_TICKER_PATTERN.fullmatch(ticker):
        raise ValueError(f"{field_name} contains invalid characters")
    return ticker


def parse_float_param(value, field_name, required=True, default=None):
    if value is None or value == "":
        if required:
            raise ValueError(f"{field_name} is required")
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid number") from exc


def parse_int_param(value, field_name, required=True, default=None):
    if value is None or value == "":
        if required:
            raise ValueError(f"{field_name} is required")
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid integer") from exc

def validate_date_range(start_date, end_date):
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Check if dates are valid
        if start_date >= end_date:
            raise ValueError("Start date must be before end date")
            
        # Check if dates are not in the future
        if end_date > datetime.now():
            raise ValueError("End date cannot be in the future")
            
        return start_date, end_date
    except ValueError as e:
        raise ValueError(f"Invalid date range: {str(e)}")
    except Exception as e:
        raise ValueError(f"Invalid date format. Please use YYYY-MM-DD format")


def normalize_currency(currency):
    if not currency:
        return None
    currency = str(currency).strip()
    if currency in {"GBp", "GBX"}:
        return "GBp"
    return currency.upper()


def infer_currency_from_ticker(ticker):
    ticker_upper = str(ticker or "").upper()
    for suffix, currency in TICKER_SUFFIX_CURRENCIES.items():
        if ticker_upper.endswith(suffix):
            return currency
    return None


def extract_fast_info_currency(fast_info):
    if not fast_info:
        return None
    if isinstance(fast_info, dict):
        return fast_info.get("currency")
    return getattr(fast_info, "currency", None)


def get_ticker_currency(ticker):
    """Return quote currency for the stock/regression API."""
    inferred_currency = infer_currency_from_ticker(ticker)
    if inferred_currency:
        return normalize_currency(inferred_currency)

    ticker_text = str(ticker or "").strip()
    if "." not in ticker_text and not ticker_text.upper().endswith("=X"):
        return BASE_CURRENCY

    try:
        stock = yf.Ticker(ticker)
        currency = extract_fast_info_currency(getattr(stock, "fast_info", None))
        if not currency:
            currency = (stock.info or {}).get("currency")
        return normalize_currency(currency) or BASE_CURRENCY
    except Exception as e:
        print(f"Could not determine quote currency for {ticker}; assuming {BASE_CURRENCY}: {e}")
        return BASE_CURRENCY


def fx_spec_for_currency(currency):
    currency = normalize_currency(currency)
    if not currency or currency == BASE_CURRENCY:
        return None
    if currency == "GBp":
        return "GBPUSD=X", "multiply", 0.01
    if currency in DIRECT_USD_QUOTE_CURRENCIES:
        return f"{currency}USD=X", "multiply", 1.0
    return f"{currency}=X", "divide", 1.0


def extract_close_series(raw_data):
    if raw_data is None or raw_data.empty:
        return pd.Series(dtype=float)
    if isinstance(raw_data.columns, pd.MultiIndex):
        if "Close" in raw_data.columns.get_level_values(0):
            close_data = raw_data["Close"]
        else:
            close_data = raw_data
        if isinstance(close_data, pd.DataFrame):
            return close_data.iloc[:, 0]
        return close_data
    if "Close" in raw_data.columns:
        close_data = raw_data["Close"]
        if isinstance(close_data, pd.DataFrame):
            return close_data.iloc[:, 0]
        return close_data
    return raw_data.iloc[:, 0]


def date_indexed_series(series):
    date_index = pd.to_datetime(series.index).tz_localize(None).normalize()
    return pd.Series(series.to_numpy(dtype=float), index=date_index).sort_index()


def fetch_usd_conversion_factor(currency, start_date, end_date, target_index):
    """Fetch a daily factor that converts one unit of currency into USD."""
    spec = fx_spec_for_currency(currency)
    if spec is None:
        return pd.Series(1.0, index=target_index)

    fx_ticker, operation, unit_multiplier = spec
    raw_fx_data = yf.download(fx_ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
    fx_close = extract_close_series(raw_fx_data).dropna()
    if fx_close.empty:
        return None

    target_dates = pd.to_datetime(target_index).tz_localize(None).normalize()
    fx_close_by_date = date_indexed_series(fx_close)
    fx_close_by_date = fx_close_by_date[~fx_close_by_date.index.duplicated(keep="last")]
    aligned_index = fx_close_by_date.index.union(target_dates)
    aligned_fx_close = (
        fx_close_by_date
        .reindex(aligned_index)
        .sort_index()
        .ffill()
        .bfill()
        .reindex(target_dates)
    )

    if aligned_fx_close.isna().all():
        return None

    if operation == "multiply":
        factor_values = aligned_fx_close * unit_multiplier
    else:
        factor_values = unit_multiplier / aligned_fx_close

    factor = pd.Series(factor_values.to_numpy(dtype=float), index=target_index)
    return factor.replace([np.inf, -np.inf], np.nan).ffill().bfill()


def normalize_history_close_to_usd(ticker, df, start_date, end_date):
    """Normalize a yfinance history dataframe's Close column into USD for charting."""
    if df.empty or 'Close' not in df.columns:
        return df, BASE_CURRENCY, {}

    source_currency = get_ticker_currency(ticker)
    if source_currency == BASE_CURRENCY:
        return df, BASE_CURRENCY, {
            "source_currency": source_currency,
            "display_currency": BASE_CURRENCY,
        }

    conversion_factor = fetch_usd_conversion_factor(source_currency, start_date, end_date, df.index)
    if conversion_factor is None or conversion_factor.dropna().empty:
        raise ValueError(f"Could not convert {ticker} prices to {BASE_CURRENCY}.")

    normalized_df = df.copy()
    normalized_df['Close'] = normalized_df['Close'].multiply(conversion_factor, axis=0)

    return normalized_df, BASE_CURRENCY, {
        "source_currency": source_currency,
        "display_currency": BASE_CURRENCY,
    }


def is_ensemble_model_type(model_type):
    return str(model_type or "").strip().upper() in ENSEMBLE_MODEL_TYPES


def is_transformer_model_type(model_type):
    return str(model_type or "").strip().upper() in TRANSFORMER_MODEL_TYPES


def build_historical_log_trend_regression(close_series):
    close_series = close_series.dropna()
    dates = close_series.index.strftime('%Y-%m-%d').tolist()
    values = close_series.values.astype(float)

    if len(values) < 2:
        return {date: float(price) for date, price in zip(dates, values)}

    valid_mask = np.isfinite(values) & (values > 0)
    if valid_mask.sum() < 2:
        return {date: float(price) for date, price in zip(dates, values)}

    x = np.arange(len(values), dtype=float)
    slope, intercept = np.polyfit(x[valid_mask], np.log(values[valid_mask]), 1)
    fitted_prices = np.exp(intercept + slope * x)
    fitted_prices = np.where(np.isfinite(fitted_prices), fitted_prices, values)

    return {date: float(price) for date, price in zip(dates, fitted_prices)}


def build_arima_in_sample_regression(close_series):
    close_series = close_series.dropna()
    if len(close_series) < 30:
        return build_historical_log_trend_regression(close_series)

    dates = close_series.index.strftime('%Y-%m-%d').tolist()
    observed_prices = close_series.values.astype(float)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pmdarima import auto_arima
            arima_model = auto_arima(
                observed_prices,
                seasonal=False,
                stepwise=True,
                suppress_warnings=True,
                error_action='ignore',
                max_p=3,
                max_q=3,
                max_d=2
            )

        fitted_prices = np.asarray(arima_model.predict_in_sample(), dtype=float).reshape(-1)
        if len(fitted_prices) != len(observed_prices):
            return build_historical_log_trend_regression(close_series)

        d_order = 0
        try:
            d_order = int(arima_model.order[1])
        except Exception:
            d_order = 0

        if d_order > 0:
            fitted_prices[:d_order] = observed_prices[:d_order]

        fitted_prices = np.where(np.isfinite(fitted_prices), fitted_prices, observed_prices)
        return {date: float(price) for date, price in zip(dates, fitted_prices)}
    except Exception as exc:
        app.logger.warning(f"ARIMA in-sample regression failed; using log trend fallback: {exc}")
        return build_historical_log_trend_regression(close_series)


def generate_monte_carlo_future_predictions(
    ticker,
    close_series,
    future_days,
    expected_prices=None,
    daily_log_return=None,
    simulations=MONTE_CARLO_SIMULATIONS
):
    close_series = close_series.dropna()
    close_series = close_series[close_series > 0]
    if future_days <= 0 or close_series.empty:
        return {}

    last_price = float(close_series.iloc[-1])
    last_date = close_series.index[-1]
    future_dates = [
        (last_date + timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range(1, future_days + 1)
    ]

    log_returns = np.log(close_series / close_series.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    fallback_drift = float(log_returns.mean()) if not log_returns.empty and np.isfinite(log_returns.mean()) else 0.0
    volatility = float(log_returns.std(ddof=1)) if len(log_returns) > 1 else np.nan
    if not np.isfinite(volatility) or volatility <= 0:
        volatility = max(abs(fallback_drift), 0.01)
    volatility = float(np.clip(volatility, MIN_DAILY_VOLATILITY, MAX_DAILY_VOLATILITY))

    if expected_prices is not None:
        expected_prices = np.asarray(expected_prices, dtype=float).reshape(-1)[:future_days]
        if len(expected_prices) == 0:
            expected_prices = np.full(future_days, last_price)
        elif len(expected_prices) < future_days:
            expected_prices = np.pad(
                expected_prices,
                (0, future_days - len(expected_prices)),
                mode='edge'
            )
        expected_prices = np.where(np.isfinite(expected_prices) & (expected_prices > 0), expected_prices, last_price)
        expected_path = np.concatenate(([last_price], expected_prices))
        daily_drifts = np.diff(np.log(expected_path))
        daily_drifts = np.where(np.isfinite(daily_drifts), daily_drifts, fallback_drift)
    elif daily_log_return is not None and np.isfinite(daily_log_return):
        daily_drifts = np.full(future_days, float(daily_log_return))
    else:
        daily_drifts = np.full(future_days, fallback_drift)

    seed_input = f"{ticker}:{last_date.strftime('%Y-%m-%d')}:{last_price:.6f}:{future_days}:{simulations}"
    seed = int(hashlib.sha256(seed_input.encode("utf-8")).hexdigest()[:16], 16) % (2 ** 32)
    rng = np.random.default_rng(seed)
    shocks = rng.normal(loc=0.0, scale=volatility, size=(simulations, future_days))
    simulated_log_returns = daily_drifts.reshape(1, -1) + shocks
    simulated_paths = last_price * np.exp(np.cumsum(simulated_log_returns, axis=1))

    mean_prices = simulated_paths.mean(axis=0)
    min_prices = simulated_paths.min(axis=0)
    max_prices = simulated_paths.max(axis=0)

    return {
        date: {
            "mean": float(mean_price),
            "min": float(min_price),
            "max": float(max_price)
        }
        for date, mean_price, min_price, max_price in zip(future_dates, mean_prices, min_prices, max_prices)
    }


def generate_forecast_regression_response(ticker, stock, close_series, future_days, price_currency, currency_metadata, model_type):
    close_series = close_series.dropna()
    if close_series.empty:
        return {}

    use_transformer_only = is_transformer_model_type(model_type)
    if use_transformer_only:
        prediction = forecast_single_ticker_with_transformer(ticker, close_series, horizon=TRADING_DAYS_PER_YEAR)
        model_label = "TRANSFORMER"
        default_source = "transformer"
    else:
        prediction = forecast_single_ticker_with_arima_transformer(ticker, close_series, horizon=TRADING_DAYS_PER_YEAR)
        model_label = "ARIMA_TRANSFORMER"
        default_source = "arima_transformer"

    annual_log_return = float(prediction.get('expected_return', 0.08))
    annual_log_return = float(np.clip(annual_log_return, -0.69, 0.69))
    daily_log_return = annual_log_return / TRADING_DAYS_PER_YEAR

    dates = close_series.index.strftime('%Y-%m-%d').tolist()
    original_data = {date: float(price) for date, price in zip(dates, close_series.values)}

    if use_transformer_only:
        regression_data = build_historical_log_trend_regression(close_series)
    else:
        regression_data = build_arima_in_sample_regression(close_series)

    future_predictions = generate_monte_carlo_future_predictions(
        ticker,
        close_series,
        future_days,
        daily_log_return=daily_log_return
    )

    info = stock.info
    company_name = info.get('longName', ticker)

    return {
        'prices': original_data,
        'regression': regression_data,
        'future_predictions': future_predictions,
        'companyName': company_name,
        'price_currency': price_currency,
        'source_currency': currency_metadata.get('source_currency', price_currency),
        'slope': 'N/A',
        'intercept': 'N/A',
        'model_metadata': {
            'model': model_label,
            'expected_annual_log_return': annual_log_return,
            'uncertainty': prediction.get('uncertainty'),
            'components': prediction.get('components', {}),
            'source': prediction.get('source', default_source)
        }
    }

def generate_regression_data(ticker="", start_date=None, end_date=None, future_days=0, model_type='LSTM'):
    try:
        if start_date and end_date:
            start_date, end_date = validate_date_range(start_date, end_date)
        else:
            end_date = datetime.now() - timedelta(days=1)
            start_date = end_date - timedelta(days=90)
        
        print(f"Fetching {ticker} data from {start_date} to {end_date} using {model_type}")
        
        # fetch stock data
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                          end=end_date.strftime('%Y-%m-%d'))
        
        if df.empty:
            print(f"No data received from yfinance for {ticker}")
            raise ExternalDataError(f"No data available for ticker {ticker}")

        df, price_currency, currency_metadata = normalize_history_close_to_usd(ticker, df, start_date, end_date)

        if is_ensemble_model_type(model_type) or is_transformer_model_type(model_type):
            return generate_forecast_regression_response(
                ticker,
                stock,
                df['Close'],
                future_days,
                price_currency,
                currency_metadata,
                model_type
            )

        # ARIMA should model the original time series directly.
        # Do not force ARIMA into the feature-based regression pipeline used by LSTM/LightGBM.
        if model_type == 'ARIMA':
            close_series = df['Close'].dropna()
            if len(close_series) < 30:
                print(f"Not enough data for ARIMA on {ticker}")
                raise ValueError(f"Not enough data for ARIMA on {ticker}")

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from pmdarima import auto_arima
                arima_model = auto_arima(
                    close_series.values,
                    seasonal=False,
                    stepwise=True,
                    suppress_warnings=True,
                    error_action='ignore',
                    max_p=3,
                    max_q=3,
                    max_d=2
                )

            fitted_prices = np.asarray(arima_model.predict_in_sample(), dtype=float)

            # ARIMA with differencing (d > 0) can produce unstable leading fitted values
            # because the first states are not fully initialized.
            # Replace the first d points with observed prices for a visually consistent chart.
            d_order = 0
            try:
                d_order = int(arima_model.order[1])
            except Exception:
                d_order = 0

            if d_order > 0:
                fitted_prices[:d_order] = close_series.values[:d_order]

            # Defensive fallback for rare edge cases where the first point is still non-finite.
            if len(fitted_prices) > 0 and not np.isfinite(fitted_prices[0]):
                fitted_prices[0] = float(close_series.values[0])

            dates = close_series.index.strftime('%Y-%m-%d').tolist()
            original_data = {date: float(price) for date, price in zip(dates, close_series.values)}
            regression_data = {date: float(price) for date, price in zip(dates, fitted_prices)}

            future_predictions = {}
            if future_days > 0:
                future_prices = arima_model.predict(n_periods=future_days)
                future_predictions = generate_monte_carlo_future_predictions(
                    ticker,
                    close_series,
                    future_days,
                    expected_prices=future_prices
                )

            info = stock.info
            company_name = info.get('longName', ticker)

            return {
                'prices': original_data,
                'regression': regression_data,
                'future_predictions': future_predictions,
                'companyName': company_name,
                'price_currency': price_currency,
                'source_currency': currency_metadata.get('source_currency', price_currency),
                'slope': 'N/A',
                'intercept': 'N/A'
            }
            
        # Feature Engineering: Create features that might predict the *change* in price
        df['Time'] = np.arange(len(df))
        df['MA7'] = df['Close'].rolling(window=7).mean()
        df['MA21'] = df['Close'].rolling(window=21).mean()
        df['Lag1'] = df['Close'].shift(1)
        
        # Target variable: Daily change in price
        df['Price_Change'] = df['Close'].diff()

        # Drop rows with NaN values
        df.dropna(inplace=True)
        
        if df.empty:
            print(f"Not enough data for {ticker} after feature engineering. Consider a longer date range.")
            raise ValueError(f"Not enough data for {ticker} after feature engineering")
            
        # Prepare data for regression        
        feature_columns = ['Time', 'MA7', 'MA21', 'Lag1', 'Volume']
        X = df[feature_columns].values
        
        # Target variable: Price Change
        y = df['Price_Change'].values.reshape(-1, 1) # Predict the change, not the absolute price
        
        # Scale data
        # Use Standard Scaler for Price Change to center around 0
        scaler_X = MinMaxScaler(feature_range=(0, 1))
        scaler_y = StandardScaler()
        
        X_scaled = scaler_X.fit_transform(X)
        y_scaled = scaler_y.fit_transform(y)
        
        # Reshape for LSTM: (samples, time_steps, features)
        X_reshaped = X_scaled.reshape((X_scaled.shape[0], 1, X_scaled.shape[1]))
        
        # Select and train model
        input_shape = (1, X_scaled.shape[1])
        if model_type == 'LightGBM':
            model = LightGBMPriceModel()
        elif model_type == 'ARIMA':
            model = ARIMAPriceModel()
        else:
            model = LSTMPriceModel(input_shape)

        # Fit model
        model.fit(X_reshaped, y_scaled)

        predicted_changes_scaled = model.predict(X_reshaped)
        predicted_changes = scaler_y.inverse_transform(predicted_changes_scaled).flatten()
        
        # The regression line is the cumulative sum of predicted changes, starting from the price before the first prediction
        # Since we dropped the first row, df['Lag1'].iloc[0] is the Close price of the dropped row (t-1)
        initial_price = df['Lag1'].iloc[0]
        regression_line = initial_price + np.cumsum(predicted_changes)
        
        # Convert to date:value format
        dates = df.index.strftime('%Y-%m-%d').tolist()
        original_data = {date: float(price) for date, price in zip(dates, df['Close'])}
        regression_data = {date: float(price) for date, price in zip(dates, regression_line)}
        
        # Get stock info
        info = stock.info
        company_name = info.get('longName', ticker)

        future_prices = []
        if future_days > 0 and not X_reshaped.size == 0:
            last_known_price = df['Close'].iloc[-1]

            # Use the last row of features as the starting point for future predictions.
            # Keep MA/Volume constant as a lightweight approximation.
            last_features = df[feature_columns].iloc[-1:].copy()

            for i in range(future_days):
                # Scale input for prediction
                last_features_scaled = scaler_X.transform(last_features.values)
                last_features_reshaped = last_features_scaled.reshape((1, 1, last_features_scaled.shape[1]))

                # Predict the change for the next day
                predicted_change_scaled = model.predict(last_features_reshaped, verbose=0)
                predicted_change = scaler_y.inverse_transform(predicted_change_scaled)[0][0]

                # Calculate the new price
                next_price = last_known_price + predicted_change

                last_features['Time'] += 1
                last_features['Lag1'] = last_known_price

                future_prices.append(float(next_price))

                # Update last known price for the next prediction
                last_known_price = next_price

        future_predictions = generate_monte_carlo_future_predictions(
            ticker,
            df['Close'],
            future_days,
            expected_prices=future_prices
        )
        
        return {
            'prices': original_data,
            'regression': regression_data,
            'future_predictions': future_predictions,
            'companyName': company_name,
            'price_currency': price_currency,
            'source_currency': currency_metadata.get('source_currency', price_currency),
            'slope': 'N/A',
            'intercept': 'N/A'
        }
        
    except (ValueError, ExternalDataError):
        raise
    except Exception as e:
        print(f"Error generating regression data: {str(e)}")
        raise ModelExecutionError(f"Error generating regression data: {str(e)}") from e

def generate_data(ticker="", start_date=None, end_date=None):
    try:
        # use provided dates or default to 3 months from 'yesterday'
        if start_date and end_date:
            start_date, end_date = validate_date_range(start_date, end_date)
        else:
            end_date = datetime.now() - timedelta(days=1)
            start_date = end_date - timedelta(days=90)
        
        print(f"Fetching {ticker} data from {start_date} to {end_date}")
        
        # fetch stock data
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date.strftime('%Y-%m-%d'), 
                          end=end_date.strftime('%Y-%m-%d'))
        
        if df.empty:
            print(f"No data received from yfinance for {ticker}")
            return {}

        df, price_currency, currency_metadata = normalize_history_close_to_usd(ticker, df, start_date, end_date)
            
        print(f"DataFrame shape: {df.shape}")
        print(f"DataFrame columns: {df.columns}")
        print(f"First few rows:\n{df.head()}")
        
        # get stock info
        info = stock.info
        company_name = info.get('longName', ticker)
        
        # convert to date:value format
        data = {date.strftime('%Y-%m-%d'): float(price) for date, price in zip(df.index, df['Close'])}
        print(f"Generated data dictionary with {len(data)} entries")
        
        return {
            'prices': data,
            'companyName': company_name,
            'price_currency': price_currency,
            'source_currency': currency_metadata.get('source_currency', price_currency),
            'regression': {},
            'future_predictions': {}
        }
        
    except Exception as e:
        print(f"Error fetching data: {str(e)}")
        return {
            'prices': {},
            'companyName': ticker,
            'price_currency': BASE_CURRENCY,
            'source_currency': BASE_CURRENCY,
            'regression': {},
            'future_predictions': {}
        }
    

    
# API endpoint to send data to the frontend
@app.route('/get-data', methods=['GET', 'OPTIONS'])
@app.route('/api/get-data', methods=['GET', 'OPTIONS'])
def get_data():
    try:
        ticker = normalize_ticker_param(request.args.get('ticker'), default='AAPL')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        include_regression = request.args.get('regression', 'false').lower() == 'true'
        future_days = parse_int_param(
            request.args.get('future_days', '0'),
            "future_days",
            required=False,
            default=0
        )
        if future_days < 0 or future_days > 365:
            raise ValueError("future_days must be between 0 and 365")

        model_type = request.args.get('model', 'LSTM')
        if model_type not in STOCK_MODEL_TYPES:
            raise ValueError(f"Unsupported model type: {model_type}")
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    try:
        if include_regression:
            data = generate_regression_data(ticker, start_date, end_date, future_days=future_days, model_type=model_type)
        else:
            # Default data gen doesn't use model
            data = generate_data(ticker, start_date, end_date)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except ExternalDataError as e:
        return jsonify({'error': str(e)}), 502
    except ModelExecutionError as e:
        app.logger.error(str(e))
        return jsonify({'error': 'Model execution failed while generating regression data'}), 500

    return jsonify(data)

# add new endpoint for hedge analysis
@app.route('/analyze-hedge', methods=['GET', 'OPTIONS'])
@app.route('/api/analyze-hedge', methods=['GET', 'OPTIONS'])
def analyze_hedge():
    try:
        ticker1 = normalize_ticker_param(request.args.get('ticker1'), field_name='ticker1')
        ticker2 = normalize_ticker_param(request.args.get('ticker2'), field_name='ticker2')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    result = analyze_hedge_relationship(ticker1, ticker2, start_date, end_date)
    return jsonify(result)



@app.route('/financial-statement', methods=['GET'])
@app.route('/api/financial-statement', methods=['GET'])
def financial_statement():
    try:
        ticker = normalize_ticker_param(request.args.get('ticker'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    statement_type = request.args.get('type')
    frequency = request.args.get('frequency', 'annual')

    if statement_type and statement_type not in {"income", "balance", "cash"}:
        return jsonify({"error": "type must be one of income, balance, or cash"}), 400
    if frequency not in {"annual", "quarterly"}:
        return jsonify({"error": "frequency must be annual or quarterly"}), 400

    if statement_type:
        data = get_financial_statements(ticker, statement_type, frequency)
    else:
        data = get_financial_dashboard(ticker)

    if 'error' in data:
        # If it's just a "unavailable data" error, we might still want to return 200 with the error message
        # But 404 is fine if it really failed.
        return jsonify(data), 404

    return jsonify(data)

import queue
import threading
import json
from flask import Response, stream_with_context

# Global store for request queues: {request_id: queue.Queue}
REQUEST_QUEUES = {}
REQUEST_QUEUES_LOCK = threading.RLock()
MAX_ACTIVE_REQUEST_QUEUES = 64
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def get_or_create_request_queue(request_id):
    """Return a bounded, validated SSE queue for an optimization job."""
    if not isinstance(request_id, str) or not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ValueError("request_id must be a safe identifier up to 128 characters")

    with REQUEST_QUEUES_LOCK:
        if request_id not in REQUEST_QUEUES and len(REQUEST_QUEUES) >= MAX_ACTIVE_REQUEST_QUEUES:
            raise RuntimeError("Too many active optimization requests")
        return REQUEST_QUEUES.setdefault(request_id, queue.Queue())


def put_progress_event(request_id, event, close=False):
    with REQUEST_QUEUES_LOCK:
        q = REQUEST_QUEUES.get(request_id)
    if q is None:
        return False
    q.put(event)
    if close:
        q.put(None)
    return True


def push_progress(request_id, progress, total, message, status='running', result=None):
    """Helper to push progress events to the SSE queue."""
    if status == 'completed':
        event = {'type': 'complete', 'progress': 100, 'message': message or 'Optimization complete'}
        if result is not None:
            event['result'] = result
        put_progress_event(request_id, event, close=True)
    elif status == 'error':
        put_progress_event(request_id, {'type': 'error', 'message': message}, close=True)
    else:
        percentage = int((progress / total) * 100) if total > 0 else 0
        put_progress_event(request_id, {'type': 'progress', 'progress': percentage, 'message': message})

@app.route('/api/progress-stream/<request_id>', methods=['GET'])
def stream_progress(request_id):
    def event_stream():
        try:
            # Lazy initialization: Allow connecting before POST
            q = get_or_create_request_queue(request_id)
        except ValueError as e:
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return
        except RuntimeError as e:
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return
        
        while True:
            try:
                # Wait for next event
                event = q.get(timeout=600) # 10 min timeout
                if event is None:
                    break
                
                # Format as SSE
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            except queue.Empty:
                yield f"event: ping\ndata: keep-alive\n\n"
            except Exception as e:
                app.logger.error(f"SSE stream error: {str(e)}")
                break
        
        # Cleanup
        with REQUEST_QUEUES_LOCK:
            if REQUEST_QUEUES.get(request_id) is q:
                del REQUEST_QUEUES[request_id]

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

@app.route('/api/optimize-portfolio', methods=['POST'])
def optimize_portfolio_endpoint():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request must be JSON"}), 400
    
    ticker_group = data.get('ticker_group')
    tickers = data.get('tickers')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    risk_free_rate = data.get('risk_free_rate')
    target_return = data.get('target_return')
    risk_tolerance = data.get('risk_tolerance')
    portfolio_id = data.get('portfolio_id')
    persist_result = bool(data.get('persist_result'))
    load_if_available = bool(data.get('load_if_available'))
    request_id = data.get('request_id')
    forecast_method = data.get('forecast_method', 'LIGHTWEIGHT')
    optimization_method = data.get('optimization_method', 'BL')
    
    try:
        validate_date_range(start_date, end_date)
        risk_free_rate = parse_float_param(risk_free_rate, "risk_free_rate")
        if target_return is not None:
            target_return = parse_float_param(target_return, "target_return", required=False)
        if risk_tolerance is not None:
            risk_tolerance = parse_float_param(risk_tolerance, "risk_tolerance", required=False)

        # Advanced settings
        forecast_horizon = parse_int_param(
            data.get('forecast_horizon', 63),
            'forecast_horizon',
            required=False,
            default=63
        )
        min_history = parse_int_param(
            data.get('min_history', 504),
            'min_history',
            required=False,
            default=504
        )
        bl_tau = parse_float_param(
            data.get('bl_tau', 0.05),
            'bl_tau',
            required=False,
            default=0.05
        )
        if forecast_horizon < 1 or forecast_horizon > 365:
            raise ValueError('forecast_horizon must be between 1 and 365')
        if min_history < 30:
            raise ValueError('min_history must be at least 30')
        if bl_tau <= 0:
            raise ValueError('bl_tau must be positive')
        if tickers is not None:
            if not isinstance(tickers, list):
                raise ValueError('tickers must be a list')
            tickers = [normalize_ticker_param(ticker) for ticker in tickers]
    except (TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400

    if not request_id:
        return jsonify({"error": "request_id is required"}), 400

    # Initialize Queue for SSE (Idempotent)
    try:
        get_or_create_request_queue(request_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 429

    def background_optimization(req_id, params):
        try:
            # Define callback adapter for weighted progress
            def progress_adapter(current, total, message):
                push_progress(req_id, current, total, message, status='running')

            result = optimize_portfolio(
                start_date=params['start_date'],
                end_date=params['end_date'],
                risk_free_rate=params['risk_free_rate'],
                ticker_group=params['ticker_group'],
                tickers=params['tickers'],
                target_return=params['target_return'],
                risk_tolerance=params['risk_tolerance'],
                portfolio_id=params['portfolio_id'],
                persist_result=params['persist_result'],
                load_if_available=params['load_if_available'],
                progress_callback=progress_adapter,
                forecast_method=params.get('forecast_method', 'LIGHTWEIGHT'),
                optimization_method=params.get('optimization_method', 'BL'),
                forecast_horizon=params.get('forecast_horizon', 63),
                min_history=params.get('min_history', 504),
                bl_tau=params.get('bl_tau', 0.05)
            )

            if "error" in result:
                push_progress(req_id, 0, 0, result["error"], status='error')
            else:
                 push_progress(
                     req_id,
                     100,
                     100,
                     'Optimization complete',
                     status='completed',
                     result=result
                 )

        except Exception as e:
            app.logger.error(f"Background optimization failed: {e}")
            push_progress(req_id, 0, 0, str(e), status='error')

    # Start background thread
    params = {
        'ticker_group': ticker_group, 'tickers': tickers, 'start_date': start_date, 
        'end_date': end_date, 'risk_free_rate': risk_free_rate, 'target_return': target_return,
        'risk_tolerance': risk_tolerance, 'portfolio_id': portfolio_id, 
        'persist_result': persist_result, 'load_if_available': load_if_available,
        'forecast_method': forecast_method, 'optimization_method': optimization_method,
        'forecast_horizon': forecast_horizon, 'bl_tau': bl_tau,
        'min_history': min_history
    }
    thread = threading.Thread(target=background_optimization, args=(request_id, params))
    thread.daemon = True
    thread.start()

    return jsonify({"message": "Optimization started", "request_id": request_id})


@app.route('/api/portfolio-results', methods=['GET'])
def list_portfolio_results_endpoint():
    try:
        return jsonify({'portfolio_ids': list_saved_portfolios()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio-results/<portfolio_id>', methods=['GET'])
def get_portfolio_result_endpoint(portfolio_id):
    result = load_portfolio_result(portfolio_id)
    if not result:
        return jsonify({'error': f'Portfolio {portfolio_id} not found'}), 404
    return jsonify(result)

@app.route('/api/stock-screener', methods=['POST'])
def stock_screener_endpoint():
    data = request.get_json(silent=True)
    if not data or 'filters' not in data:
        return jsonify({"error": "Request must be JSON and contain a 'filters' key"}), 400

    filters = data.get('filters')
    if not isinstance(filters, dict):
        return jsonify({"error": "'filters' must be a dictionary"}), 400

    try:
        results = search_stocks(filters)
        return jsonify(results)
    except Exception as e:
        # Log the exception for debugging
        app.logger.error(f"Stock screener failed with exception: {e}")
        return jsonify({"error": "An internal error occurred while screening stocks."}), 500


@app.route('/api/asset-names', methods=['POST'])
def asset_names_endpoint():
    data = request.get_json(silent=True) or {}
    tickers = data.get('tickers', [])
    if not isinstance(tickers, list):
        return jsonify({'error': 'tickers must be a list'}), 400

    try:
        normalized_tickers = [
            normalize_ticker_param(ticker)
            for ticker in tickers[:100]
        ]
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'asset_names': get_asset_names(normalized_tickers)})

@app.route('/api/benchmark-portfolio', methods=['POST'])
def benchmark_portfolio_endpoint():
    """
    Benchmark a portfolio against S&P 500 and risk-free assets.
    
    Request JSON:
        portfolio_data: dict with weights and prices
        budget: float (investment amount)
        start_date: string (YYYY-MM-DD format)
        end_date: string (YYYY-MM-DD format)
        risk_free_rate: float (annual rate as decimal, e.g., 0.04)
    
    Returns:
        JSON with portfolio_timeline, sp500_timeline, riskfree_timeline, and summary
    """
    try:
        data = request.get_json(silent=True)
        
        # Validate request data
        if not data:
            return jsonify({'error': 'Request must be JSON'}), 400
        
        required_fields = ['portfolio_data', 'budget', 'start_date', 'end_date', 'risk_free_rate']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return jsonify({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        # Extract and validate parameters
        portfolio_data = data.get('portfolio_data')
        budget = data.get('budget')
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        risk_free_rate = data.get('risk_free_rate')
        
        # Validate budget
        try:
            budget = float(budget)
            if budget <= 0:
                return jsonify({'error': 'Budget must be a positive number'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Budget must be a valid number'}), 400
        
        # Validate risk-free rate
        try:
            risk_free_rate = float(risk_free_rate)
        except (ValueError, TypeError):
            return jsonify({'error': 'Risk-free rate must be a valid number'}), 400
        
        # Validate date range
        try:
            start_date, end_date = validate_date_range(start_date_str, end_date_str)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # Validate portfolio data structure
        if not isinstance(portfolio_data, dict):
            return jsonify({'error': 'Portfolio data must be an object'}), 400
        
        if 'weights' not in portfolio_data or 'prices' not in portfolio_data:
            return jsonify({
                'error': 'Portfolio data must contain "weights" and "prices" fields'
            }), 400
        
        # Calculate benchmark
        result = calculate_portfolio_benchmark(
            portfolio_data, 
            budget, 
            start_date, 
            end_date, 
            risk_free_rate
        )
        
        return jsonify(result), 200
        
    except ValueError as e:
        # Handle validation errors from calculation module
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        # Handle unexpected errors
        app.logger.error(f"Portfolio benchmarking failed: {str(e)}")
        return jsonify({
            'error': 'An internal error occurred while benchmarking the portfolio'
        }), 500

@app.route('/api/manage-portfolio', methods=['POST'])
def manage_portfolio_endpoint():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        current_holdings = data.get('current_holdings', {})
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        
        forecast_method = data.get('forecast_method', 'LIGHTWEIGHT')
        optimization_method = data.get('optimization_method', 'BL')
        ticker_group = data.get('ticker_group')
        
        target_return = data.get('target_return')
        risk_tolerance = data.get('risk_tolerance')
        allow_fractional = bool(data.get('allow_fractional', True))
        fractional_overrides = data.get('fractional_overrides', {})
        tickers = data.get('tickers', None)

        if not isinstance(current_holdings, dict):
            return jsonify({'error': 'current_holdings must be an object'}), 400
        if not isinstance(fractional_overrides, dict):
            return jsonify({'error': 'fractional_overrides must be an object'}), 400
        if tickers is not None and not isinstance(tickers, list):
            return jsonify({'error': 'tickers must be a list'}), 400

        try:
            start_date, end_date = validate_date_range(start_date_str, end_date_str)
            cash_injection = parse_float_param(
                data.get('cash_injection', 0.0),
                'cash_injection',
                required=False,
                default=0.0
            )
            risk_free_rate = parse_float_param(
                data.get('risk_free_rate', 0.0),
                'risk_free_rate',
                required=False,
                default=0.0
            )
            forecast_horizon = parse_int_param(
                data.get('forecast_horizon', 63),
                'forecast_horizon',
                required=False,
                default=63
            )
            min_history = parse_int_param(
                data.get('min_history', 504),
                'min_history',
                required=False,
                default=504
            )
            bl_tau = parse_float_param(
                data.get('bl_tau', 0.05),
                'bl_tau',
                required=False,
                default=0.05
            )
            if target_return is not None:
                target_return = parse_float_param(target_return, 'target_return', required=False)
            if risk_tolerance is not None:
                risk_tolerance = parse_float_param(risk_tolerance, 'risk_tolerance', required=False)
            if cash_injection < 0:
                raise ValueError('cash_injection must be non-negative')
            if forecast_horizon < 1 or forecast_horizon > 365:
                raise ValueError('forecast_horizon must be between 1 and 365')
            if min_history < 30:
                raise ValueError('min_history must be at least 30')
            if bl_tau <= 0:
                raise ValueError('bl_tau must be positive')
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        result = manage_portfolio_logic(
            current_holdings=current_holdings,
            cash_injection=cash_injection,
            start_date=start_date,
            end_date=end_date,
            risk_free_rate=risk_free_rate,
            forecast_method=forecast_method,
            optimization_method=optimization_method,
            ticker_group=ticker_group,
            target_return=target_return,
            risk_tolerance=risk_tolerance,
            forecast_horizon=forecast_horizon,
            min_history=min_history,
            bl_tau=bl_tau,
            allow_fractional=allow_fractional,
            fractional_overrides=fractional_overrides,
            tickers=tickers
        )
        
        if "error" in result:
            return jsonify(result), 400
            
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"manage_portfolio failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    import multiprocessing as mp

    mp.freeze_support()
    app.run(debug=False, threaded=True, use_reloader=False)
