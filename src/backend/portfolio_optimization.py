import json
import logging
import hashlib
import re
import warnings
from pathlib import Path
import time
from datetime import datetime, timedelta
from native_threading import configure_native_threading, get_ml_worker_limit, is_windows

configure_native_threading()

# Silence Protobuf warnings from TensorFlow/Google libraries
warnings.filterwarnings("ignore", message=".*Protobuf gencode version.*")

import yfinance as yf
import pandas as pd
import numpy as np
from pypfopt import EfficientFrontier, risk_models, objective_functions, BlackLittermanModel, black_litterman
from pypfopt.exceptions import OptimizationError
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc
from cache_manager import (
    get_cache, cached
)
from ticker_lists import get_ticker_group
from forecast_models import ARIMATransformerPredictor, TransformerForecastModel
from lightweight_forecast import lightweight_ensemble_forecast

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("logs/portfolio_results")
BASE_CURRENCY = "USD"

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


def worker_initializer():
    """Initialize worker process environment to restrict threading."""
    # Force single-threaded execution for libraries in worker processes to
    # prevent CPU oversubscription when running many ML workers.
    configure_native_threading(force=True)


def _ensure_results_dir():
    """Create persistence directory if it does not exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _to_serializable(value):
    """Convert numpy/pandas objects to JSON-serializable primitives."""
    if isinstance(value, (np.generic, np.float32, np.float64)):
        return float(value)
    if isinstance(value, (np.integer, np.int32, np.int64)):
        return int(value)
    if isinstance(value, (pd.Series, pd.Index)):
        return [_to_serializable(v) for v in value.tolist()]
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_serializable(v) for v in value]
    return value


def _dedupe_tickers(tickers):
    """Return uppercase ticker symbols without duplicates, preserving first-seen order."""
    deduped = []
    seen = set()
    for ticker in tickers or []:
        if ticker is None:
            continue
        cleaned = str(ticker).strip().rstrip('\\').upper()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


@cached(l1_ttl=86400, l2_ttl=604800)
def get_asset_names(tickers):
    """Fetch display names for tickers, falling back to the ticker symbol."""
    names = {}
    cleaned_tickers = _dedupe_tickers(tickers)
    if not cleaned_tickers:
        return names

    try:
        batch_size = 50
        for i in range(0, len(cleaned_tickers), batch_size):
            batch = cleaned_tickers[i:i + batch_size]
            try:
                yf_tickers = yf.Tickers(" ".join(batch))
                for ticker in batch:
                    try:
                        info = yf_tickers.tickers[ticker].info
                        name = (
                            info.get("longName")
                            or info.get("shortName")
                            or info.get("displayName")
                            or ticker
                        )
                        names[ticker] = str(name)
                    except Exception:
                        names[ticker] = ticker
            except Exception as e:
                logger.warning(f"Batch name fetch failed: {e}")
                for ticker in batch:
                    names[ticker] = ticker
    except Exception as e:
        logger.warning(f"Asset name fetch failed: {e}")

    for ticker in cleaned_tickers:
        names.setdefault(ticker, ticker)
    return names


def _normalize_currency(currency):
    if not currency:
        return None
    currency = str(currency).strip()
    if currency in {"GBp", "GBX"}:
        return "GBp"
    return currency.upper()


def _infer_currency_from_ticker(ticker):
    ticker_upper = str(ticker or "").upper()
    for suffix, currency in TICKER_SUFFIX_CURRENCIES.items():
        if ticker_upper.endswith(suffix):
            return currency
    return None


def _extract_fast_info_currency(fast_info):
    if not fast_info:
        return None
    if isinstance(fast_info, dict):
        return fast_info.get("currency")
    return getattr(fast_info, "currency", None)


def _get_ticker_currency(ticker):
    """Return the quote currency for a ticker, using suffix inference before slower metadata."""
    inferred_currency = _infer_currency_from_ticker(ticker)
    if inferred_currency:
        return _normalize_currency(inferred_currency)

    ticker_text = str(ticker or "").strip()
    if "." not in ticker_text and not ticker_text.upper().endswith("=X"):
        return BASE_CURRENCY

    try:
        stock = yf.Ticker(ticker)
        currency = _extract_fast_info_currency(getattr(stock, "fast_info", None))
        if not currency:
            currency = (stock.info or {}).get("currency")
        return _normalize_currency(currency) or BASE_CURRENCY
    except Exception as e:
        logger.warning(f"Could not determine quote currency for {ticker}; assuming {BASE_CURRENCY}: {e}")
        return BASE_CURRENCY


def _fx_spec_for_currency(currency):
    currency = _normalize_currency(currency)
    if not currency or currency == BASE_CURRENCY:
        return None
    if currency == "GBp":
        return "GBPUSD=X", "multiply", 0.01
    if currency in DIRECT_USD_QUOTE_CURRENCIES:
        return f"{currency}USD=X", "multiply", 1.0
    return f"{currency}=X", "divide", 1.0


def _extract_close_series(raw_data):
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


def _date_indexed_series(series):
    """Return a copy indexed by calendar date, avoiding Yahoo timezone mismatches."""
    date_index = pd.to_datetime(series.index).tz_localize(None).normalize()
    return pd.Series(series.to_numpy(dtype=float), index=date_index).sort_index()


def _fetch_usd_conversion_factor(currency, start_date, end_date, target_index):
    """Fetch a daily factor that converts one unit of currency into USD."""
    spec = _fx_spec_for_currency(currency)
    if spec is None:
        return pd.Series(1.0, index=target_index)

    fx_ticker, operation, unit_multiplier = spec
    try:
        raw_fx_data = yf.download(fx_ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
        fx_close = _extract_close_series(raw_fx_data).dropna()
        if fx_close.empty:
            logger.warning(f"No FX data returned for {currency} via {fx_ticker}")
            return None

        target_dates = pd.to_datetime(target_index).tz_localize(None).normalize()
        fx_close_by_date = _date_indexed_series(fx_close)
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
            logger.warning(f"FX data for {currency} could not be aligned to stock dates")
            return None

        if operation == "multiply":
            factor_values = aligned_fx_close * unit_multiplier
        else:
            factor_values = unit_multiplier / aligned_fx_close

        factor = pd.Series(factor_values.to_numpy(dtype=float), index=target_index)
        return factor.replace([np.inf, -np.inf], np.nan).ffill().bfill()
    except Exception as e:
        logger.warning(f"Failed to fetch FX data for {currency} via {fx_ticker}: {e}")
        return None


@cached(l1_ttl=3600, l2_ttl=86400)
def _fetch_latest_usd_conversion_scalar(currency):
    """Fetch the latest scalar that converts one unit of currency into USD."""
    spec = _fx_spec_for_currency(currency)
    if spec is None:
        return 1.0

    fx_ticker, operation, unit_multiplier = spec
    try:
        raw_fx_data = yf.download(fx_ticker, period="5d", progress=False, auto_adjust=True)
        fx_close = _extract_close_series(raw_fx_data).dropna()
        if fx_close.empty:
            return None

        latest_fx = float(fx_close.iloc[-1])
        if latest_fx <= 0:
            return None

        if operation == "multiply":
            return latest_fx * unit_multiplier
        return unit_multiplier / latest_fx
    except Exception as e:
        logger.warning(f"Failed to fetch latest FX data for {currency} via {fx_ticker}: {e}")
        return None


def _convert_price_data_to_usd(data, start_date, end_date, ticker_currencies=None):
    """
    Convert local-currency Yahoo close prices into USD.

    Yahoo returns local exchange closes, so a Korean stock like 035420.KS arrives
    around 200,000 KRW. Portfolio value math assumes a single base currency, so
    non-USD series must be converted before latest prices and weights are used.
    """
    if data.empty:
        return data, {}, []

    converted = data.copy()
    ticker_currencies = ticker_currencies or {}
    currency_metadata = {}
    conversion_failures = []
    factor_cache = {}

    for ticker in list(converted.columns):
        currency = _normalize_currency(ticker_currencies.get(ticker)) or _get_ticker_currency(ticker)
        currency = _normalize_currency(currency) or BASE_CURRENCY
        currency_metadata[ticker] = {
            "source_currency": currency,
            "display_currency": BASE_CURRENCY,
        }

        if currency == BASE_CURRENCY:
            continue

        if currency not in factor_cache:
            factor_cache[currency] = _fetch_usd_conversion_factor(currency, start_date, end_date, converted.index)

        conversion_factor = factor_cache[currency]
        if conversion_factor is None or conversion_factor.dropna().empty:
            logger.warning(f"Dropping {ticker}: unable to convert {currency} prices to {BASE_CURRENCY}")
            converted = converted.drop(columns=[ticker])
            conversion_failures.append(ticker)
            continue

        converted[ticker] = converted[ticker].multiply(conversion_factor, axis=0)
        logger.info(f"Converted {ticker} prices from {currency} to {BASE_CURRENCY}")

    return converted, currency_metadata, conversion_failures


def save_portfolio_result(portfolio_id, result, metadata=None):
    """Persist portfolio optimization output and metadata to disk."""
    if not portfolio_id:
        raise ValueError("portfolio_id is required to save results")
    if not isinstance(result, dict):
        raise ValueError("result must be a dictionary")

    payload = {
        "portfolio_id": portfolio_id,
        "result": _to_serializable(result),
        "metadata": _to_serializable(metadata or {}),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    _ensure_results_dir()
    output_path = RESULTS_DIR / f"{portfolio_id}.json"
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    logger.info(f"Saved portfolio result to {output_path}")


def load_portfolio_result(portfolio_id):
    """Load a previously saved portfolio optimization result."""
    if not portfolio_id:
        raise ValueError("portfolio_id is required to load results")

    output_path = RESULTS_DIR / f"{portfolio_id}.json"
    if not output_path.exists():
        logger.info(f"No saved portfolio result found for {portfolio_id}")
        return None

    with open(output_path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    result = payload.get("result", {})
    result["metadata"] = payload.get("metadata", {})
    result["saved_at"] = payload.get("saved_at")
    result["portfolio_id"] = payload.get("portfolio_id", portfolio_id)
    logger.info(f"Loaded portfolio result from {output_path}")
    return result


def list_saved_portfolios():
    """Return available saved portfolio identifiers."""
    if not RESULTS_DIR.exists():
        return []
    return sorted(p.stem for p in RESULTS_DIR.glob("*.json"))

@cached(l1_ttl=900, l2_ttl=14400)  # 15 min L1, 4 hour L2 cache
def get_stock_data(tickers, start_date, end_date, progress_callback=None):
    """Fetch stock data for given tickers and date range using chunked batch processing."""
    logger.info(f"GET_STOCK_DATA: Starting fetch for {len(tickers)} tickers")
    
    all_series = []
    
    # Process in chunks to prevent one bad ticker from blocking the whole batch
    BATCH_SIZE = 50
    
    # Helper to chunk list
    def chunked_iterable(iterable, size):
        for i in range(0, len(iterable), size):
            yield iterable[i:i + size]

    for chunk_idx, chunk in enumerate(chunked_iterable(tickers, BATCH_SIZE)):
        if progress_callback:
            progress_callback(chunk_idx * BATCH_SIZE, len(tickers), f"Fetching data for tickers {chunk_idx * BATCH_SIZE + 1}-{min((chunk_idx + 1) * BATCH_SIZE, len(tickers))}")
        
        logger.info(f"GET_STOCK_DATA: Processing chunk {chunk_idx+1} ({len(chunk)} tickers)")
        chunk_data = pd.DataFrame()
        
        # Try batch download for this chunk
        try:
            def _download_chunk():
                return yf.download(chunk, start=start_date, end=end_date, progress=False, auto_adjust=True, threads=True)

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_download_chunk)
                try:
                    # 20 seconds timeout for a chunk of 50
                    raw_data = future.result(timeout=20)
                    
                    # Extract Close data logic
                    if len(chunk) == 1:
                        if isinstance(raw_data.columns, pd.MultiIndex):
                            c_data = raw_data['Close'] if 'Close' in raw_data.columns.get_level_values(0) else raw_data
                        else:
                            c_data = raw_data['Close'] if 'Close' in raw_data.columns else raw_data
                        c_data.name = chunk[0]
                        chunk_data = pd.DataFrame(c_data)
                    else:
                        if isinstance(raw_data.columns, pd.MultiIndex):
                            if 'Close' in raw_data.columns.get_level_values(0):
                                chunk_data = raw_data['Close']
                            else:
                                chunk_data = raw_data
                        else:
                            chunk_data = raw_data

                    chunk_data = chunk_data.ffill().dropna(how='all')
                    
                except TimeoutError:
                    logger.warning(f"GET_STOCK_DATA: Chunk {chunk_idx+1} timed out")
                except Exception as e:
                    logger.warning(f"GET_STOCK_DATA: Chunk {chunk_idx+1} failed: {e}")

        except Exception as e:
            logger.error(f"GET_STOCK_DATA: Chunk wrapper failed: {e}")

        # Fallback for this chunk if batch failed or resulted in empty data
        if chunk_data.empty:
            logger.info(f"GET_STOCK_DATA: Fallback to individual fetch for chunk {chunk_idx+1}")
            individual_data = {}
            max_workers = min(32, len(chunk))
            
            def _fetch_single_safe(ticker):
                try:
                    data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
                    if not data.empty and 'Close' in data.columns:
                        val = data['Close']
                        if isinstance(val, (int, float, np.number)):
                             val = pd.Series([val], index=data.index)
                        return ticker, val
                except Exception:
                    pass
                return ticker, None

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ticker = {executor.submit(_fetch_single_safe, t): t for t in chunk}
                for future in as_completed(future_to_ticker):
                    t = future_to_ticker[future]
                    try:
                        r_tick, r_val = future.result(timeout=5)
                        if r_val is not None:
                            if isinstance(r_val, (int, float, str, bool, np.number)):
                                continue
                            individual_data[r_tick] = r_val
                    except Exception:
                        pass
            
            if individual_data:
                chunk_data = pd.DataFrame(individual_data).ffill().dropna(how='all')

        if not chunk_data.empty:
             all_series.append(chunk_data)

    # Combine all chunks
    if not all_series:
        logger.error("GET_STOCK_DATA: All chunks failed")
        return pd.DataFrame()
        
    logger.info(f"GET_STOCK_DATA: Combining {len(all_series)} chunks")
    try:
        final_data = pd.concat(all_series, axis=1)
        final_data = final_data.ffill().dropna(how='all')
        logger.info(f"GET_STOCK_DATA: Final shape: {final_data.shape}")
        return final_data
    except Exception as e:
        logger.error(f"GET_STOCK_DATA: Error combining chunks: {e}")
        return pd.DataFrame()

# NOTE: 모델 객체를 캐시하지 않음 - 메모리 누수 방지를 위해 forecast 결과만 캐시
def _generate_arima_transformer_prediction(ticker, ticker_data, horizon=252):
    """
    Train ARIMA + Transformer models and generate prediction for a single ticker.
    Returns dictionary with expected_return and uncertainty.
    """
    predictor = None
    try:
        prices = ticker_data.values
        
        # Validate data
        if len(prices) < 100:
            logger.warning(f"Insufficient data for ARIMA + Transformer training on {ticker}: {len(prices)} points")
            return None
        
        valid_prices = prices[~np.isnan(prices)]
        if len(valid_prices) < 100:
            logger.warning(f"Too many NaN values for {ticker}")
            return None
        
        start_time = time.time()
        predictor = ARIMATransformerPredictor()
        predictor.train_all(valid_prices)
        prediction = predictor.predict(horizon=horizon)
        elapsed = time.time() - start_time
        
        logger.info(f"ARIMA + Transformer Prediction for {ticker}: "
                   f"Return={prediction['expected_return']:.4f}, "
                   f"Uncertainty={prediction['uncertainty']:.4f} "
                   f"in {elapsed:.2f}s")
        
        return prediction
        
    except Exception as e:
        logger.error(f"ARIMA + Transformer forecasting failed for {ticker}: {e}")
        return None
    finally:
        if predictor is not None:
            predictor.cleanup()
        gc.collect()


def _generate_transformer_prediction(ticker, ticker_data, horizon=252):
    """
    Train a Transformer model and generate an annualized log-return prediction
    for a single ticker.
    """
    model = None
    try:
        prices = ticker_data.values
        valid_prices = prices[~np.isnan(prices)]

        if len(valid_prices) < 100:
            logger.warning(f"Insufficient data for Transformer training on {ticker}: {len(valid_prices)} points")
            return None

        start_time = time.time()
        model = TransformerForecastModel()
        model.train(valid_prices)
        prediction = model.predict(horizon=horizon)
        elapsed = time.time() - start_time

        logger.info(f"Transformer Prediction for {ticker}: "
                    f"Return={prediction['expected_return']:.4f}, "
                    f"Uncertainty={prediction['uncertainty']:.4f} "
                    f"in {elapsed:.2f}s")

        return prediction

    except Exception as e:
        logger.error(f"Transformer forecasting failed for {ticker}: {e}")
        return None
    finally:
        if model is not None:
            model.cleanup()
        gc.collect()


def forecast_single_ticker_with_arima_transformer(ticker, ticker_data, horizon=252):
    """
    Forecast a single ticker with the same ARIMA + Transformer path used by portfolio optimization.

    Returns expected_return as an annualized log return so callers can convert it
    into a daily compounded price path.
    """
    prices = ticker_data.values if hasattr(ticker_data, "values") else np.asarray(ticker_data)
    valid_prices = prices[~np.isnan(prices)]

    if len(valid_prices) < 100:
        logger.info(f"Using lightweight forecast for {ticker}: {len(valid_prices)} points (< 100 required for ARIMA + Transformer)")
        period_return = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
        annual_log_return = np.log1p(np.clip(period_return, -0.95, None)) * (252 / horizon)
        return {
            'expected_return': float(annual_log_return),
            'uncertainty': 0.05,
            'components': {},
            'source': 'lightweight_fallback'
        }

    prediction = _generate_arima_transformer_prediction(ticker, ticker_data, horizon=horizon)
    if prediction is None:
        logger.warning(f"ARIMA + Transformer training failed for {ticker}, using lightweight forecast")
        period_return = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
        annual_log_return = np.log1p(np.clip(period_return, -0.95, None)) * (252 / horizon)
        return {
            'expected_return': float(annual_log_return),
            'uncertainty': 0.05,
            'components': {},
            'source': 'lightweight_fallback'
        }

    prediction['expected_return'] = float(prediction.get('expected_return', 0.08))
    prediction['source'] = 'arima_transformer'
    return prediction


def forecast_single_ticker_with_ensemble(ticker, ticker_data, horizon=252):
    """Backward-compatible alias: the old ensemble path now uses ARIMA + Transformer."""
    return forecast_single_ticker_with_arima_transformer(ticker, ticker_data, horizon=horizon)


def forecast_single_ticker_with_transformer(ticker, ticker_data, horizon=252):
    """
    Forecast a single ticker using the Transformer path.

    Returns expected_return as an annualized log return.
    """
    prices = ticker_data.values if hasattr(ticker_data, "values") else np.asarray(ticker_data)
    valid_prices = prices[~np.isnan(prices)]

    if len(valid_prices) < 100:
        logger.info(f"Using lightweight forecast for {ticker}: {len(valid_prices)} points (< 100 required for Transformer)")
        period_return = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
        annual_log_return = np.log1p(np.clip(period_return, -0.95, None)) * (252 / horizon)
        return {
            'expected_return': float(annual_log_return),
            'uncertainty': 0.05,
            'components': {},
            'source': 'lightweight_fallback'
        }

    prediction = _generate_transformer_prediction(ticker, ticker_data, horizon=horizon)
    if prediction is None:
        logger.warning(f"Transformer training failed for {ticker}, using lightweight forecast")
        period_return = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
        annual_log_return = np.log1p(np.clip(period_return, -0.95, None)) * (252 / horizon)
        return {
            'expected_return': float(annual_log_return),
            'uncertainty': 0.05,
            'components': {},
            'source': 'lightweight_fallback'
        }

    prediction['expected_return'] = float(prediction.get('expected_return', 0.08))
    prediction['source'] = 'transformer'
    return prediction


@cached(l1_ttl=900, l2_ttl=14400)  # 15 min L1, 4 hour L2 cache for predictions
def _ml_forecast_single_ticker(ticker, ticker_data, horizon=252):
    """Forecast returns for single ticker using ARIMA + Transformer with caching.
    
    Falls back to lightweight forecasting when insufficient data.
    Returns dictionary with expected_return and uncertainty.
    """
    try:
        prices = ticker_data.values
        valid_prices = prices[~np.isnan(prices)]
        
        # Validate data - use lightweight mode if insufficient data for ML
        if len(valid_prices) < 100:
            logger.info(f"Using lightweight forecast for {ticker}: {len(valid_prices)} points (< 100 required for ARIMA + Transformer)")
            period_return = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
            annual_log_return = np.log1p(np.clip(period_return, -0.95, None)) * (252 / horizon)
            return ticker, {'expected_return': annual_log_return, 'uncertainty': 0.05}
        
        prediction = _generate_arima_transformer_prediction(ticker, ticker_data, horizon=horizon)
        
        if prediction is None:
            # Fallback to lightweight forecast
            logger.warning(f"ARIMA + Transformer training failed for {ticker}, using lightweight forecast")
            period_return = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
            annual_log_return = np.log1p(np.clip(period_return, -0.95, None)) * (252 / horizon)
            return ticker, {'expected_return': annual_log_return, 'uncertainty': 0.05}
        
        return ticker, prediction
        
    finally:
        gc.collect()


@cached(l1_ttl=900, l2_ttl=14400)
def _transformer_forecast_single_ticker(ticker, ticker_data, horizon=252):
    """Forecast returns for one ticker using the Transformer model with caching."""
    try:
        prices = ticker_data.values
        valid_prices = prices[~np.isnan(prices)]

        if len(valid_prices) < 100:
            logger.info(f"Using lightweight forecast for {ticker}: {len(valid_prices)} points (< 100 required for Transformer)")
            forecast_value = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
            annual_log_return = np.log1p(np.clip(forecast_value, -0.95, None)) * (252 / horizon)
            return ticker, {'expected_return': annual_log_return, 'uncertainty': 0.05}

        prediction = _generate_transformer_prediction(ticker, ticker_data, horizon=horizon)

        if prediction is None:
            logger.warning(f"Transformer training failed for {ticker}, using lightweight forecast")
            forecast_value = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
            annual_log_return = np.log1p(np.clip(forecast_value, -0.95, None)) * (252 / horizon)
            return ticker, {'expected_return': annual_log_return, 'uncertainty': 0.05}

        return ticker, prediction

    finally:
        gc.collect()



def ml_forecast_returns(data, batch_size=50, progress_callback=None, horizon=252):
    """
    Forecast expected returns using ARIMA + Transformer with memory-efficient batch processing.
    
    Args:
        data: DataFrame with stock prices (dates as index, tickers as columns)
        batch_size: Number of tickers to process in each batch (Increased for throughput)
        progress_callback: Optional callback(current, total, message)
    
    Returns:
        tuple: (forecasts_series, uncertainties_series)
    """
    start_time = time.time()
    logger.info(f"Starting BATCH ARIMA + Transformer forecasting for {len(data.columns)} tickers")
    
    if is_windows() and batch_size > 20:
        logger.info(f"Reducing ML forecast batch_size from {batch_size} to 20 on Windows for memory stability")
        batch_size = 20

    max_workers = get_ml_worker_limit(len(data.columns))
    
    logger.info(f"Using {max_workers} parallel workers for ML forecasting")
    
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed

    # Use spawn context for safety with ML libraries (TensorFlow/PyTorch)
    ctx = mp.get_context('spawn')

    forecasts = {}
    uncertainties = {}
    tickers = list(data.columns)
    total_batches = (len(tickers) + batch_size - 1) // batch_size
    
    try:
        # 배치 단위로 처리하여 메모리 관리
        for batch_idx in range(total_batches):
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(tickers))
            batch_tickers = tickers[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch_tickers)} tickers)")
            
            # ProcessPoolExecutor for true parallelism
            with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx, initializer=worker_initializer) as executor:
                future_to_ticker = {}
                for ticker in batch_tickers:
                    future = executor.submit(_ml_forecast_single_ticker, ticker, data[ticker], horizon)
                    future_to_ticker[future] = ticker
                
                for future in as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    try:
                        result_ticker, prediction_result = future.result()
                        # Handle old return type (float) vs new (dict) for safety during transition
                        if isinstance(prediction_result, dict):
                            forecasts[result_ticker] = prediction_result.get('expected_return', 0.05)
                            uncertainties[result_ticker] = prediction_result.get('uncertainty', 0.05)
                        else:
                            forecasts[result_ticker] = float(prediction_result)
                            uncertainties[result_ticker] = 0.05
                    except Exception as exc:
                        logger.error(f"ML forecasting exception for {ticker}: {exc}")
                        forecasts[ticker] = 0.08
                        uncertainties[ticker] = 0.05
            
            # 배치 완료 후 메모리 정리
            gc.collect()
            
            # 진행 상황 로깅
            completed = len(forecasts)
            logger.info(f"Batch {batch_idx + 1} complete. Total progress: {completed}/{len(tickers)} ({100*completed/len(tickers):.1f}%)")
            
            if progress_callback:
                progress_callback(completed, len(tickers), f"ARIMA + Transformer Training: Batch {batch_idx + 1}/{total_batches} complete")

            # 메모리 상태 체크
            import psutil
            mem = psutil.virtual_memory()
            logger.info(f"Memory usage: {mem.percent:.1f}% ({mem.used / 1024**3:.1f}GB / {mem.total / 1024**3:.1f}GB)")
            
            # 메모리 사용량이 85% 이상이면 경고 및 추가 정리
            if mem.percent > 85:
                logger.warning(f"High memory usage detected ({mem.percent:.1f}%). Forcing garbage collection.")
                gc.collect()
                # Keras/TensorFlow 세션 정리 시도
                try:
                    import tensorflow as tf
                    tf.keras.backend.clear_session()
                except Exception:
                    pass
        
        elapsed_time = time.time() - start_time
        logger.info(f"BATCH ARIMA + Transformer forecasting completed in {elapsed_time:.2f}s for {len(forecasts)} tickers")
        
        # Log cache performance
        cache = get_cache()
        cache_stats = cache.stats()
        logger.info(f"CACHE HIT RATES: L1={cache_stats['hit_ratios']['l1']:.1%}, "
                   f"L2={cache_stats['hit_ratios']['l2']:.1%}, "
                   f"Overall={cache_stats['hit_ratios']['overall']:.1%}")
        
        return pd.Series(forecasts), pd.Series(uncertainties)
        
    except Exception as e:
        logger.error(f"ARIMA + Transformer forecasting failed critically: {e}. Using lightweight ensemble fallback.")
        # Fallback: 경량 앙상블 방식으로 직접 예측
        forecasts = {}
        uncertainties = {}
        for ticker in data.columns:
            try:
                prices = data[ticker].values
                valid_prices = prices[~np.isnan(prices)]
                if len(valid_prices) >= 10:
                    period_return = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
                    forecasts[ticker] = np.log1p(np.clip(period_return, -0.95, None)) * (252 / horizon)
                    uncertainties[ticker] = 0.05
                else:
                    forecasts[ticker] = 0.05
                    uncertainties[ticker] = 0.05
            except Exception:
                forecasts[ticker] = 0.05
                uncertainties[ticker] = 0.05
        return pd.Series(forecasts), pd.Series(uncertainties)


def transformer_forecast_returns(data, batch_size=20, progress_callback=None, horizon=252):
    """
    Forecast expected returns using a standalone Transformer model.

    Returns:
        tuple: (forecasts_series, uncertainties_series)
    """
    start_time = time.time()
    logger.info(f"Starting Transformer forecasting for {len(data.columns)} tickers")

    if is_windows() and batch_size > 10:
        logger.info(f"Reducing Transformer batch_size from {batch_size} to 10 on Windows for memory stability")
        batch_size = 10

    max_workers = get_ml_worker_limit(len(data.columns))
    max_workers = max(1, min(max_workers, 2))

    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed

    ctx = mp.get_context('spawn')
    forecasts = {}
    uncertainties = {}
    tickers = list(data.columns)
    total_batches = (len(tickers) + batch_size - 1) // batch_size

    try:
        for batch_idx in range(total_batches):
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(tickers))
            batch_tickers = tickers[batch_start:batch_end]

            logger.info(f"Processing Transformer batch {batch_idx + 1}/{total_batches} ({len(batch_tickers)} tickers)")

            with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx, initializer=worker_initializer) as executor:
                future_to_ticker = {}
                for ticker in batch_tickers:
                    future = executor.submit(_transformer_forecast_single_ticker, ticker, data[ticker], horizon)
                    future_to_ticker[future] = ticker

                for future in as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    try:
                        result_ticker, prediction_result = future.result()
                        forecasts[result_ticker] = prediction_result.get('expected_return', 0.05)
                        uncertainties[result_ticker] = prediction_result.get('uncertainty', 0.05)
                    except Exception as exc:
                        logger.error(f"Transformer forecasting exception for {ticker}: {exc}")
                        forecasts[ticker] = 0.08
                        uncertainties[ticker] = 0.05

            gc.collect()

            completed = len(forecasts)
            logger.info(f"Transformer batch {batch_idx + 1} complete. Total progress: {completed}/{len(tickers)}")
            if progress_callback:
                progress_callback(completed, len(tickers), f"Transformer Training: Batch {batch_idx + 1}/{total_batches} complete")

        elapsed_time = time.time() - start_time
        logger.info(f"Transformer forecasting completed in {elapsed_time:.2f}s for {len(forecasts)} tickers")
        return pd.Series(forecasts), pd.Series(uncertainties)

    except Exception as e:
        logger.error(f"Transformer forecasting failed critically: {e}. Using lightweight ensemble fallback.")
        forecasts = {}
        uncertainties = {}
        for ticker in data.columns:
            try:
                prices = data[ticker].values
                valid_prices = prices[~np.isnan(prices)]
                if len(valid_prices) >= 10:
                    period_return = lightweight_ensemble_forecast(valid_prices, horizon=horizon)
                    forecasts[ticker] = np.log1p(np.clip(period_return, -0.95, None)) * (252 / horizon)
                else:
                    forecasts[ticker] = 0.05
                uncertainties[ticker] = 0.05
            except Exception:
                forecasts[ticker] = 0.05
                uncertainties[ticker] = 0.05
        return pd.Series(forecasts), pd.Series(uncertainties)


@cached(l1_ttl=86400, l2_ttl=604800)  # 24 hours L1, 7 days L2 (Market caps change slowly)
def get_market_caps(tickers):
    """Fetch market capitalizations for tickers using yfinance."""
    mcaps = {}
    try:
        logger.info(f"Fetching market caps for {len(tickers)} tickers")
        batch_size = 50
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i+batch_size]
            try:
                tickers_str = " ".join(batch)
                yf_tickers = yf.Tickers(tickers_str)
                for ticker in batch:
                    try:
                        # info access can be slow.
                        info = yf_tickers.tickers[ticker].info
                        mc = info.get("marketCap") or info.get("totalAssets")
                        if mc:
                            currency = _normalize_currency(info.get("currency") or info.get("financialCurrency"))
                            currency = currency or _get_ticker_currency(ticker)
                            if currency != BASE_CURRENCY:
                                conversion_factor = _fetch_latest_usd_conversion_scalar(currency)
                                if conversion_factor:
                                    mc = float(mc) * conversion_factor
                                else:
                                    logger.warning(f"Skipping market cap for {ticker}: cannot convert {currency} to {BASE_CURRENCY}")
                                    continue
                            mcaps[ticker] = float(mc)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Batch info fetch failed: {e}")
    except Exception as e:
        logger.error(f"Market cap fetch failed: {e}")
    return mcaps


@cached(l1_ttl=3600, l2_ttl=86400)
def get_market_implied_risk_aversion_cached(start_date, end_date, risk_free_rate):
    """Calculate market implied risk aversion (delta) for S&P 500."""
    market_ticker = "^GSPC"
    try:
        # Use simple caching for standard S&P500 fetch
        market_data = yf.download(market_ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
        
        if isinstance(market_data.columns, pd.MultiIndex): 
            if 'Close' in market_data.columns.get_level_values(0):
                    market_prices = market_data['Close']
            else:
                    market_prices = market_data.iloc[:, 0]
        elif 'Close' in market_data.columns:
            market_prices = market_data['Close']
        else:
            market_prices = market_data.iloc[:, 0]

        market_prices = market_prices.dropna()
        
        if market_prices.empty:
                return 2.5
        
        delta = black_litterman.market_implied_risk_aversion(market_prices, risk_free_rate=risk_free_rate)
        logger.info(f"Market implied risk aversion (delta): {delta:.4f}")
        return float(delta)
    except Exception as e:
        logger.warning(f"Delta calculation failed: {e}. Using delta=2.5")
        return 2.5


@cached(l1_ttl=600, l2_ttl=3600)  # 10 min L1, 1 hour L2 cache for portfolio optimization

def _pipeline_key_func(start_date, end_date, ticker_group, tickers, forecast_method, forecast_horizon=252, min_history=100, progress_callback=None):
    """Generate cache key for pipeline, excluding progress callback."""
    if tickers:
        tickers_str = ",".join(sorted(tickers))
    else:
        tickers_str = "None"
    key_str = f"{start_date}|{end_date}|{ticker_group}|{tickers_str}|{forecast_method}|{forecast_horizon}|{min_history}|usd_fx_v1"
    return f"pipeline_{hashlib.md5(key_str.encode()).hexdigest()}"

@cached(l1_ttl=3600, l2_ttl=86400, key_func=_pipeline_key_func)
def data_and_forecast_pipeline(start_date, end_date, ticker_group, tickers, forecast_method, forecast_horizon=252, min_history=100, progress_callback=None):
    """
    Pipeline for Data Fetching, Cleaning, and Forecasting.
    Decoupled from optimization constraints to enable 'Warm Start'.
    """
    logger.info("Executing data_and_forecast_pipeline (Refreshed/Cold Start)")
    
    if tickers:
        pass
    elif ticker_group:
        tickers = get_ticker_group(ticker_group)
    else:
        raise ValueError("Either ticker_group or tickers must be provided.")

    def _weighted_progress(stage_start, stage_end, current, total, message):
        if progress_callback and total > 0:
            stage_range = stage_end - stage_start
            normalized = (current / total) * stage_range
            global_progress = stage_start + normalized
            progress_callback(global_progress, 100, message)

    logger.info(f"PIPELINE STAGE 1: Attempting to fetch data for {len(tickers)} tickers")
    def fetch_callback(current, total, message):
        _weighted_progress(0, 30, current, total, message)
        
    data = get_stock_data(tickers, start_date, end_date, progress_callback=fetch_callback)
    
    if data.empty:
        logger.warning("Could not fetch any valid data.")
        return {
            "error": "Could not fetch any valid data for the given tickers and date range."
        }

    currency_metadata = {}
    currency_conversion_failures = []
    
    # --- START: MINIMUM HISTORY CHECK ---
    # Drop assets with insufficient data points (User Configurable)
    if min_history > 0:
        valid_counts = data.count()
        insufficient_tickers = valid_counts[valid_counts < min_history].index.tolist()
        
        if insufficient_tickers:
            logger.info(f"Dropped {len(insufficient_tickers)} tickers due to insufficient history (<{min_history} points): {insufficient_tickers}")
            data = data.drop(columns=insufficient_tickers)
            # Update tickers list to reflect drops (though data columns are the source of truth)
            if tickers:
                tickers = [t for t in tickers if t not in insufficient_tickers]
            
        if data.empty:
            logger.warning(f"All tickers dropped due to insufficient history (<{min_history} points).")
            return {
                "error": f"All selected tickers have less than {min_history} days of data in the selected period."
            }
    # --- END: MINIMUM HISTORY CHECK ---

    # DEBUG: Check for large values in data that might cause overflow
    # Use max() to check magnitude without triggering overflow if possible, or just strict check
    try:
        data_max = data.max().max()
        data_min = data.min().min()
        logger.info(f"DEBUG: Data range: Min={data_min}, Max={data_max}")
        if data_max > 1e15 or data_min < -1e15:
             logger.warning(f"DEBUG: Extremely large values detected in price data!")
             cols_large = []
             for col in data.columns:
                 if data[col].max() > 1e15 or data[col].min() < -1e15:
                     cols_large.append(col)
             logger.warning(f"DEBUG: Tickers with large values: {cols_large}")
    except Exception as e:
        logger.error(f"DEBUG: Data check failed: {e}")

    # --- START: STRICT TIMEFRAME / LIVENESS CHECK ---
    # Drop assets that stopped trading early (Delisted/Stale).
    # This prevents 0.0 or flat-filled prices which cause Infinity in returns.
    try:
        ts_end = pd.Timestamp(end_date)
        # Allow 14 days of buffer (for holidays or slight delays in data source)
        staleness_cutoff = ts_end - pd.Timedelta(days=14)
        
        stale_tickers = []
        for ticker in data.columns:
            last_valid = data[ticker].last_valid_index()
            # If no data at all, or last data point is before cutoff => DEAD
            if last_valid is None or last_valid < staleness_cutoff:
                cutoff_str = staleness_cutoff.date()
                last_str = last_valid.date() if last_valid else "None"
                logger.warning(f"Dropping {ticker}: Last data {last_str} < Cutoff {cutoff_str} (Likely DELISTED)")
                stale_tickers.append(ticker)
        
        if stale_tickers:
            data = data.drop(columns=stale_tickers)
            logger.info(f"Liveness Check: Dropped {len(stale_tickers)} stale tickers.")

        if data.empty:
            logger.error("No valid tickers remaining after Liveness Check.")
            return {
                "error": f"All tickers were dropped because they stopped trading before {end_date}."
            }
    except Exception as e:
         logger.error(f"Error during Liveness Check: {e}")
    # --- END: STRICT TIMEFRAME CHECK ---

    data, currency_metadata, currency_conversion_failures = _convert_price_data_to_usd(data, start_date, end_date)
    if currency_conversion_failures:
        logger.warning(f"Dropped tickers with unavailable FX conversion: {currency_conversion_failures}")
        if tickers:
            tickers = [t for t in tickers if t not in currency_conversion_failures]

    if data.empty:
        logger.error("No valid tickers remaining after currency conversion.")
        return {
            "error": "Could not convert selected non-USD prices into USD."
        }

    # Sanitization: Replace infinity with NaN to prevent overflow in covariance calculation
    data = data.replace([np.inf, -np.inf], np.nan)
    data = data.dropna(axis=1, how='all')
    final_tickers = data.columns.tolist()
    
    def ml_callback(current, total, message):
        _weighted_progress(30, 90, current, total, message)

    mu_forecast = None
    uncertainties = None
    
    if forecast_method in ["HISTORICAL", "MPT", "CLASSIC_MPT"]:
        logger.info("Using Historical CAGR for Forecasting")
        cagr_series = {}
        for ticker in final_tickers:
            try:
                prices = data[ticker].dropna()
                if len(prices) >= 2:
                    start_price = prices.iloc[0]
                    end_price = prices.iloc[-1]
                    years = len(prices) / 252.0
                    cagr = (end_price / start_price) ** (1 / years) - 1 if (start_price>0 and end_price>0 and years>0) else -0.99
                    cagr_series[ticker] = cagr
                else:
                    cagr_series[ticker] = 0.0
            except Exception:
                cagr_series[ticker] = 0.0
        mu_forecast = pd.Series(cagr_series).fillna(0)
        # Fix for NoneType error: Ensure uncertainties is initialized for HISTORICAL mode
        uncertainties = pd.Series({t: 0.0 for t in final_tickers})
    
    elif forecast_method in ["LIGHTWEIGHT", "Lightweight"]:
        logger.info(f"Using Lightweight Ensemble Forecast (Horizon={forecast_horizon})")
        forecasts = {}
        uncertainties_dict = {}
        for i, ticker in enumerate(final_tickers):
            if i % 10 == 0:
                ml_callback(i, len(final_tickers), f"Lightweight forecasting {i}/{len(final_tickers)}")
            try:
                prices = data[ticker].dropna().values
                valid_prices = prices[~np.isnan(prices)]
                if len(valid_prices) > 0:
                    val = lightweight_ensemble_forecast(valid_prices, horizon=forecast_horizon)
                else:
                    val = 0.05
                forecasts[ticker] = val
                uncertainties_dict[ticker] = 0.05
            except Exception:
                forecasts[ticker] = 0.05
                uncertainties_dict[ticker] = 0.05
        
        mu_forecast = pd.Series(forecasts).fillna(0.0)
        uncertainties = pd.Series(uncertainties_dict).fillna(0.05)
        
    elif forecast_method in ["DEEP_LEARNING", "Ensemble", "ARIMA_TRANSFORMER", "ARIMA + Transformer"]:
        logger.info(f"Using ARIMA + Transformer Forecast (Horizon={forecast_horizon})")
        mu_forecast, uncertainties = ml_forecast_returns(
            data,
            progress_callback=ml_callback,
            horizon=forecast_horizon
        )

    elif forecast_method in ["TRANSFORMER", "Transformer"]:
        logger.info(f"Using Transformer Forecast (Horizon={forecast_horizon})")
        mu_forecast, uncertainties = transformer_forecast_returns(
            data,
            progress_callback=ml_callback,
            horizon=forecast_horizon
        )
    
    else:
        logger.warning(f"Unknown forecast method '{forecast_method}', defaulting to Lightweight")
        forecasts = {}
        uncertainties_dict = {}
        for ticker in final_tickers:
            prices = data[ticker].dropna().values
            valid_prices = prices[~np.isnan(prices)]
            val = lightweight_ensemble_forecast(valid_prices, horizon=forecast_horizon) if len(valid_prices)>0 else 0.05
            forecasts[ticker] = val
            uncertainties_dict[ticker] = 0.05
        mu_forecast = pd.Series(forecasts).fillna(0.0)
        uncertainties = pd.Series(uncertainties_dict).fillna(0.05)

    # DEBUG: Check Forecasts
    if mu_forecast is not None:
         logger.info(f"DEBUG: Forecast stats: Min={mu_forecast.min()}, Max={mu_forecast.max()}")
         if np.isinf(mu_forecast).any() or (mu_forecast.abs() > 1e6).any():
             logger.error("DEBUG: mu_forecast contains INF or huge values!")
             logger.error(f"DEBUG: Bad forecasts: {mu_forecast[np.isinf(mu_forecast) | (mu_forecast.abs() > 1e6)]}")
         # Sanitize Forecasts
         mu_forecast = mu_forecast.replace([np.inf, -np.inf], 0.0)
         mu_forecast = mu_forecast.clip(lower=-1.0, upper=10.0) # Clip unreasonable returns

    aligned_data = data[mu_forecast.index]

    # DEBUG: Check aligned data before covariance
    logger.info(f"DEBUG: aligned_data shape: {aligned_data.shape}")
    
    # 1. Replace 0.0 with NaN (Price of 0 causes Division by Zero in returns)
    aligned_data = aligned_data.replace(0.0, np.nan)
    
    # 2. Fill gaps (Forward fill then Backward fill)
    aligned_data = aligned_data.ffill().bfill()
    
    # 3. Check for specific bad values
    if np.isinf(aligned_data.values).any():
         logger.error("DEBUG: aligned_data contains INF values even after cleanup!")
         aligned_data = aligned_data.replace([np.inf, -np.inf], np.nan).dropna(axis=1)

    # 4. Check for remaining NaNs and drop columns (tickers) that are broken
    if aligned_data.isna().any().any():
        logger.warning("DEBUG: aligned_data contains NaNs. Dropping bad columns.")
        aligned_data = aligned_data.dropna(axis=1)

    # Ensure no large values in aligned_data (Price data)
    cols_to_drop = []
    for col in aligned_data.columns:
        if aligned_data[col].max() > 1e8: 
            logger.warning(f"DEBUG: Dropping {col} due to suspicious price > 1e8: {aligned_data[col].max()}")
            cols_to_drop.append(col)
    
    # Re-align everything based on the survived columns
    valid_columns = [c for c in aligned_data.columns if c not in cols_to_drop]
    aligned_data = aligned_data[valid_columns]
    
    # Ensure mu_forecast and uncertainties match the valid columns
    common_tickers = [t for t in mu_forecast.index if t in valid_columns]
    
    aligned_data = aligned_data[common_tickers]
    mu_forecast = mu_forecast[common_tickers]
    uncertainties = uncertainties[common_tickers]
    final_tickers = common_tickers

    if aligned_data.empty:
        logger.error("All tickers were dropped due to data quality issues.")
        raise ValueError("No valid data remaining after sanitization.")

    S_hist = risk_models.CovarianceShrinkage(aligned_data).ledoit_wolf()
    
    latest_prices = {}
    for ticker in final_tickers:
        try:
            series = data[ticker].dropna()
            if not series.empty:
                latest_prices[ticker] = float(series.iloc[-1])
        except Exception:
            pass
            
    return {
        "mu": mu_forecast,
        "S": S_hist,
        "tickers": final_tickers,
        "uncertainties": uncertainties,
        "latest_prices": latest_prices,
        "price_currency": BASE_CURRENCY,
        "source_currencies": {
            ticker: currency_metadata.get(ticker, {}).get("source_currency", BASE_CURRENCY)
            for ticker in final_tickers
        }
    }

def optimize_portfolio(start_date, end_date, risk_free_rate, ticker_group=None, tickers=None,
                       target_return=None, risk_tolerance=None, portfolio_id=None,
                       persist_result=False, load_if_available=False, progress_callback=None,
                       l2_gamma=0.05, max_asset_weight=0.2,
                       forecast_method="LIGHTWEIGHT", optimization_method="BL",
                       forecast_horizon=252, min_history=100, bl_tau=0.05):
    """Optimize portfolio and optionally persist or reuse saved results."""

    # Resolve ticker source as early as possible so we can sanitize/de-duplicate once.
    if not tickers and ticker_group:
        tickers = get_ticker_group(ticker_group)
    
    # Sanitization: Cleanse tickers if provided (fixes RTF/formatting issues)
    if tickers:
        cleaned_tickers = []
        for t in tickers:
            # Remove whitespace and trailing backslashes (common in RTF)
            t_clean = t.strip().rstrip('\\')
            # Validate: Allow alphanumeric, dots, dashes, carets
            if t_clean and re.match(r'^[A-Z0-9\.\-\^]+$', t_clean, re.IGNORECASE):
                cleaned_tickers.append(t_clean)
            else:
                logger.warning(f"Ignoring invalid ticker format: '{t}'")

        # Remove duplicates while preserving input order (case-insensitive key).
        deduped_tickers = []
        seen = set()
        duplicate_count = 0
        for t in cleaned_tickers:
            dedupe_key = t.upper()
            if dedupe_key in seen:
                duplicate_count += 1
                continue
            seen.add(dedupe_key)
            deduped_tickers.append(t)

        if duplicate_count > 0:
            logger.info(f"Removed {duplicate_count} duplicate tickers before optimization")

        tickers = deduped_tickers
        if not tickers and not ticker_group:
             return {"error": "No valid tickers found after sanitization."}

    # Log cache performance at start of optimization
    cache = get_cache()
    try:
        cache_stats = cache.stats()
        if 'l1_cache' in cache_stats:
            logger.info(f"CACHE MEMORY: {cache_stats['l1_cache'].get('memory_usage_mb', 0):.1f}MB")
    except Exception:
        pass
    
    # Short-circuit if saved result should be reused (Persistence Layer)
    if portfolio_id and load_if_available:
        saved_result = load_portfolio_result(portfolio_id)
        if saved_result:
            logger.info(f"Returning previously saved result for {portfolio_id}")
            return saved_result

    # 1. Determine Forecast Method (User Choice Respected)
    logger.info(f"Executing: Forecast={forecast_method}, Optimization={optimization_method}")

    # 2. Run Cached Pipeline (Data & Forecasting)
    try:
        pipeline_result = data_and_forecast_pipeline(
            start_date, end_date, ticker_group, tickers, forecast_method, 
            forecast_horizon=forecast_horizon,
            min_history=min_history,
            progress_callback=progress_callback
        )
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return {"error": f"Pipeline execution failed: {str(e)}"}

    if "error" in pipeline_result:
        return pipeline_result

    mu = pipeline_result["mu"]
    S = pipeline_result["S"]
    uncertainties = pipeline_result["uncertainties"]
    final_tickers = pipeline_result["tickers"]
    latest_prices = pipeline_result.get("latest_prices", {})
    price_currency = pipeline_result.get("price_currency", BASE_CURRENCY)
    source_currencies = pipeline_result.get("source_currencies", {})

    # 3. Apply Optimization Logic (BL or MPT)
    if optimization_method in ["BL", "Black-Litterman"]:
        logger.info("Applying Black-Litterman Optimization")
        try:
            # If uncertainties missing, set default
            if uncertainties is None:
                uncertainties = pd.Series({t: 0.05 for t in mu.index})
            
            # Ensure uncertainties are positive to prevent divide-by-zero
            uncertainties = uncertainties.clip(lower=1e-4)
            
            # Market Caps
            mcaps = get_market_caps(list(mu.index))
            
            # Delta from Market
            delta = get_market_implied_risk_aversion_cached(start_date, end_date, risk_free_rate)
            
            if mcaps:
                logger.info("Applying Black-Litterman with Market Prior")
                market_prior = black_litterman.market_implied_prior_returns(mcaps, delta, S, risk_free_rate=risk_free_rate)
                
                curr_uncertainties = uncertainties.reindex(mu.index).fillna(0.05)
                omega = np.diag(curr_uncertainties ** 2)
                
                bl = BlackLittermanModel(S, pi=market_prior, absolute_views=mu, omega=omega, risk_aversion=delta, tau=bl_tau)
                mu = bl.bl_returns()
                S = bl.bl_cov()
                logger.info("Black-Litterman optimization successful.")
            else:
                logger.warning("No market caps available for BL. Fallback to Mean-Variance with Forecast.")
        except Exception as e:
             logger.error(f"Black-Litterman failed: {e}. Fallback to Mean-Variance with Forecast.")
             
    elif optimization_method in ["MPT", "Mean-Variance", "Classic MPT"]:
        logger.info("Applying Mean-Variance Optimization")
        pass

    # 4. Efficient Frontier Optimization
    try:
        asset_count = len(mu.index)
        if asset_count == 0:
            return {"error": "No valid assets remained after data preparation."}

        effective_max_asset_weight = max_asset_weight
        if (
            effective_max_asset_weight is not None
            and effective_max_asset_weight > 0
            and asset_count * effective_max_asset_weight < 1
        ):
            effective_max_asset_weight = min(1.0, (1.0 / asset_count) + 1e-6)
            logger.info(
                "Relaxed max_asset_weight to %.6f for %d assets so weights can sum to 1.",
                effective_max_asset_weight,
                asset_count,
            )

        ef = EfficientFrontier(mu, S, weight_bounds=(0, effective_max_asset_weight))

        # Add L2 regularization
        if l2_gamma > 0:
            ef.add_objective(objective_functions.L2_reg, gamma=l2_gamma)

        # Set optimization objective
        if target_return:
            ef.efficient_return(target_return)
        elif risk_tolerance:
            ef.efficient_risk(risk_tolerance)
        else:
            ef.max_sharpe(risk_free_rate=risk_free_rate)

        # Get optimized weights
        weights = ef.clean_weights()
        
        # Filter out assets with near-zero weight
        final_weights = {ticker: weight for ticker, weight in weights.items() if weight > 1e-4}

        # Get performance metrics
        performance = ef.portfolio_performance(risk_free_rate=risk_free_rate)
        # performance: (return, volatility, sharpe)
        
        # Filter prices
        final_prices = {t: latest_prices.get(t, 0.0) for t in final_tickers}

        result_payload = {
            "weights": final_weights,
            "return": performance[0],
            "risk": performance[1],
            "sharpe_ratio": performance[2],
            "prices": final_prices,
            "asset_names": get_asset_names(final_weights.keys()),
            "price_currency": price_currency,
            "source_currencies": {t: source_currencies.get(t, BASE_CURRENCY) for t in final_tickers}
        }

        if portfolio_id and persist_result:
            metadata = {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "risk_free_rate": risk_free_rate,
                "ticker_group": ticker_group,
                "tickers": tickers,
                "target_return": target_return,
                "risk_tolerance": risk_tolerance,
                "l2_gamma": l2_gamma,
                "max_asset_weight": max_asset_weight
            }
            save_portfolio_result(portfolio_id, result_payload, metadata)
            result_payload["portfolio_id"] = portfolio_id
        
        return result_payload

    except OptimizationError as e:
        logger.warning(f"pypfopt OptimizationError: {e}")
        if target_return:
            error_message = "Infeasible constraints. The portfolio cannot achieve the requested Target Return with the current constraints."
        elif risk_tolerance:
            error_message = "Infeasible constraints. The portfolio cannot achieve the requested risk target with the current constraints."
        else:
            error_message = "Infeasible constraints. The optimizer could not solve a max-Sharpe allocation with the current asset universe and constraints."
        return {
            "error": error_message,
            "details": str(e)
        }
    except Exception as e:
        logger.error(f"General Optimization Exception: {e}")
        return {
            "error": f"Optimization failed: {str(e)}"
        }

def iteratively_solve_max_sharpe(mu, S, risk_free_rate, max_asset_weight=0.2):
    """Iteratively adjust target return/risk space to calculate the max Sharpe ratio allocation."""
    best_sharpe = -np.inf
    best_weights = None
    
    min_ret = mu.min()
    max_ret = mu.max()
    
    if max_ret <= 0 or min_ret >= max_ret:
        ef = EfficientFrontier(mu, S, weight_bounds=(0, max_asset_weight))
        return ef.max_sharpe(risk_free_rate=risk_free_rate)
        
    num_steps = 50
    step_size = (max_ret - min_ret) / num_steps
    target_returns = np.arange(min_ret + step_size, max_ret, step_size)
    
    for tr in target_returns:
        try:
            ef = EfficientFrontier(mu, S, weight_bounds=(0, max_asset_weight))
            ef.efficient_return(tr)
            weights = ef.clean_weights()
            ret, risk, sharpe = ef.portfolio_performance(risk_free_rate=risk_free_rate)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_weights = weights
        except OptimizationError:
            continue
            
    if best_weights is None:
        ef = EfficientFrontier(mu, S, weight_bounds=(0, max_asset_weight))
        best_weights = ef.max_sharpe(risk_free_rate=risk_free_rate)
    
    return best_weights

def calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection, allow_fractional=True, fractional_overrides=None):
    """
    Generate exact Buy List and Sell List comparing current holdings to target optimized weights,
    respecting fractional trading constraints and redistributing unused cash.
    """
    import math
    if fractional_overrides is None:
        fractional_overrides = {}
        
    def is_fractional(ticker):
        return fractional_overrides.get(ticker, allow_fractional)

    total_current_value = 0.0
    current_values = {}
    for ticker, qty in current_holdings.items():
        price = latest_prices.get(ticker, 0.0)
        value = price * float(qty)
        current_values[ticker] = value
        total_current_value += value
        
    total_target_value = total_current_value + float(cash_injection)
    
    # Calculate ideal target quantities first
    ideal_quantities = {}
    all_tickers = set(current_holdings.keys()).union(target_weights.keys())
    for ticker in all_tickers:
        price = latest_prices.get(ticker, 0.0)
        target_weight = target_weights.get(ticker, 0.0)
        if price > 0:
            ideal_quantities[ticker] = (total_target_value * target_weight) / price
            
    # Apply fractional constraints
    target_quantities = {}
    remaining_cash = 0.0
    fractional_tickers = []
    
    for ticker, ideal_qty in ideal_quantities.items():
        price = latest_prices.get(ticker, 0.0)
        if is_fractional(ticker):
            target_quantities[ticker] = ideal_qty
            if target_weights.get(ticker, 0.0) > 0:
                fractional_tickers.append(ticker)
        else:
            floor_qty = math.floor(ideal_qty)
            target_quantities[ticker] = float(floor_qty)
            remaining_cash += (ideal_qty - floor_qty) * price
            
    # Redistribute remaining cash
    if remaining_cash > 0.01:
        if fractional_tickers:
            frac_weight_sum = sum(target_weights.get(t, 0.0) for t in fractional_tickers)
            if frac_weight_sum > 0:
                for ticker in fractional_tickers:
                    extra_cash = (target_weights[ticker] / frac_weight_sum) * remaining_cash
                    target_quantities[ticker] += extra_cash / latest_prices[ticker]
                remaining_cash = 0.0
            
        if remaining_cash > 0.01:
            sorted_tickers = sorted(
                [t for t in target_quantities.keys() if not is_fractional(t)],
                key=lambda t: target_weights.get(t, 0.0), 
                reverse=True
            )
            changed = True
            while changed and remaining_cash > 0.01:
                changed = False
                for ticker in sorted_tickers:
                    price = latest_prices.get(ticker, 0.0)
                    if price > 0 and price <= remaining_cash:
                        target_quantities[ticker] += 1.0
                        remaining_cash -= price
                        changed = True
                        break

    buy_list = {}
    sell_list = {}
    
    for ticker in all_tickers:
        price = latest_prices.get(ticker, 0.0)
        if price <= 0:
            continue
            
        target_qty = target_quantities.get(ticker, 0.0)
        current_qty = float(current_holdings.get(ticker, 0.0))
        delta_qty = target_qty - current_qty
        
        if delta_qty > 1e-6:
            buy_list[ticker] = {"quantity": float(delta_qty), "price": float(price), "value": float(delta_qty * price)}
        elif delta_qty < -1e-6:
            sell_list[ticker] = {"quantity": float(abs(delta_qty)), "price": float(price), "value": float(abs(delta_qty) * price)}

    return {
        "buy_list": buy_list,
        "sell_list": sell_list,
        "target_quantities": target_quantities,
        "target_weights": target_weights,
        "total_target_value": total_target_value,
        "remaining_cash": float(remaining_cash)
    }

def manage_portfolio_logic(current_holdings, cash_injection, start_date, end_date, risk_free_rate, 
                           forecast_method="LIGHTWEIGHT", optimization_method="BL",
                           ticker_group=None,
                           tickers=None, allow_fractional=True, fractional_overrides=None, **kwargs):

    universe_tickers = list(current_holdings.keys())
    if tickers:
        universe_tickers.extend(tickers)
    elif ticker_group and ticker_group != "CURRENT_HOLDINGS":
        universe_tickers.extend(get_ticker_group(ticker_group))

    tickers = _dedupe_tickers(universe_tickers)
        
    opt_result = optimize_portfolio(
        start_date=start_date,
        end_date=end_date,
        risk_free_rate=risk_free_rate,
        ticker_group=ticker_group,
        tickers=tickers,
        forecast_method=forecast_method,
        optimization_method=optimization_method,
        **kwargs
    )
    
    if "error" in opt_result:
        return opt_result

    target_weights = opt_result["weights"]
    latest_prices = opt_result["prices"]
    
    # Wait: actually we might want to iteratively solve if the prompt insists.
    # We will use the optimized weights from optimize_portfolio or iteratively calculate them if asked.
    # For now, optimize_portfolio already returned the best weights (either by max_sharpe or otherwise).
    
    rebalance_data = calculate_rebalance_orders(
        current_holdings, target_weights, latest_prices, cash_injection,
        allow_fractional=allow_fractional, fractional_overrides=fractional_overrides
    )
    opt_result.update(rebalance_data)
    opt_result["current_holdings"] = current_holdings
    opt_result["cash_injection"] = cash_injection
    display_tickers = set(current_holdings.keys())
    display_tickers.update(opt_result.get("weights", {}).keys())
    display_tickers.update(opt_result.get("prices", {}).keys())
    display_tickers.update(rebalance_data.get("buy_list", {}).keys())
    display_tickers.update(rebalance_data.get("sell_list", {}).keys())
    opt_result["asset_names"] = get_asset_names(sorted(display_tickers))
    
    return opt_result
