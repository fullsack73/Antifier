import json
import logging
import hashlib
import re
import warnings
from pathlib import Path
import time
from datetime import datetime, timedelta

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
from forecast_models import EnsemblePredictor
from lightweight_forecast import lightweight_ensemble_forecast

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("logs/portfolio_results")


def worker_initializer():
    """Initialize worker process environment to restrict threading."""
    import os
    # Force single-threaded execution for libraries in worker processes
    # to prevent CPU oversubscription when running many workers.
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['MKL_NUM_THREADS'] = '1'
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['TF_NUM_INTRAOP_THREADS'] = '1'
    os.environ['TF_NUM_INTEROP_THREADS'] = '1'
    # Also for numexpr if used by pandas/numpy
    os.environ['NUMEXPR_NUM_THREADS'] = '1'


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
def _generate_ensemble_prediction(ticker, ticker_data):
    """
    Train ensemble models and generate prediction for a single ticker.
    Returns dictionary with expected_return and uncertainty.
    """
    try:
        prices = ticker_data.values
        
        # Validate data
        if len(prices) < 100:
            logger.warning(f"Insufficient data for ML training on {ticker}: {len(prices)} points")
            return None
        
        valid_prices = prices[~np.isnan(prices)]
        if len(valid_prices) < 100:
            logger.warning(f"Too many NaN values for {ticker}")
            return None
        
        # Use EnsemblePredictor
        start_time = time.time()
        predictor = EnsemblePredictor()
        predictor.train_all(valid_prices)
        prediction = predictor.predict()
        elapsed = time.time() - start_time
        
        logger.info(f"Ensemble Prediction for {ticker}: "
                   f"Return={prediction['expected_return']:.4f}, "
                   f"Uncertainty={prediction['uncertainty']:.4f} "
                   f"in {elapsed:.2f}s")
        
        return prediction
        
    except Exception as e:
        logger.error(f"Ensemble forecasting failed for {ticker}: {e}")
        return None
    finally:
        gc.collect()

@cached(l1_ttl=900, l2_ttl=14400)  # 15 min L1, 4 hour L2 cache for predictions
def _ml_forecast_single_ticker(ticker, ticker_data):
    """Forecast returns for single ticker using Ensemble models with caching.
    
    Falls back to lightweight forecasting when insufficient data.
    Returns dictionary with expected_return and uncertainty.
    """
    try:
        prices = ticker_data.values
        valid_prices = prices[~np.isnan(prices)]
        
        # Validate data - use lightweight mode if insufficient data for ML
        if len(valid_prices) < 100:
            logger.info(f"Using lightweight forecast for {ticker}: {len(valid_prices)} points (< 100 required for ML)")
            forecast_value = lightweight_ensemble_forecast(valid_prices)
            return ticker, {'expected_return': forecast_value, 'uncertainty': 0.05}
        
        # Generate ensemble prediction
        prediction = _generate_ensemble_prediction(ticker, ticker_data)
        
        if prediction is None:
            # Fallback to lightweight forecast
            logger.warning(f"ML training failed for {ticker}, using lightweight forecast")
            forecast_value = lightweight_ensemble_forecast(valid_prices)
            return ticker, {'expected_return': forecast_value, 'uncertainty': 0.05}
        
        return ticker, prediction
        
    finally:
        gc.collect()



def ml_forecast_returns(data, batch_size=50, progress_callback=None):
    """
    Forecast expected returns using ML models with memory-efficient batch processing.
    
    Args:
        data: DataFrame with stock prices (dates as index, tickers as columns)
        batch_size: Number of tickers to process in each batch (Increased for throughput)
        progress_callback: Optional callback(current, total, message)
    
    Returns:
        tuple: (forecasts_series, uncertainties_series)
    """
    start_time = time.time()
    logger.info(f"Starting BATCH ML forecasting for {len(data.columns)} tickers")
    
    # ProcessPool Tuning (Task 2)
    # Since we restricted inner-model threading (Task 1), we can safely use more workers
    import os
    cpu_count = os.cpu_count() or 4
    # Reserve 1 core for OS/Main process to keep system responsive
    usable_cores = max(1, cpu_count - 1)
    # Cap at 16 to prevent diminishing returns from excessive process management
    max_workers = min(usable_cores, len(data.columns), 16)
    
    logger.info(f"Using {max_workers} parallel workers for ML forecasting (Optimized process pool)")
    
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
                    future = executor.submit(_ml_forecast_single_ticker, ticker, data[ticker])
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
                progress_callback(completed, len(tickers), f"ML Training: Batch {batch_idx + 1}/{total_batches} complete")

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
        logger.info(f"BATCH ML forecasting completed in {elapsed_time:.2f}s for {len(forecasts)} tickers")
        
        # Log cache performance
        cache = get_cache()
        cache_stats = cache.stats()
        logger.info(f"CACHE HIT RATES: L1={cache_stats['hit_ratios']['l1']:.1%}, "
                   f"L2={cache_stats['hit_ratios']['l2']:.1%}, "
                   f"Overall={cache_stats['hit_ratios']['overall']:.1%}")
        
        return pd.Series(forecasts), pd.Series(uncertainties)
        
    except Exception as e:
        logger.error(f"ML forecasting failed critically: {e}. Using lightweight ensemble fallback.")
        # Fallback: 경량 앙상블 방식으로 직접 예측
        forecasts = {}
        uncertainties = {}
        for ticker in data.columns:
            try:
                prices = data[ticker].values
                valid_prices = prices[~np.isnan(prices)]
                if len(valid_prices) >= 10:
                    val = lightweight_ensemble_forecast(valid_prices)
                    forecasts[ticker] = val
                    uncertainties[ticker] = 0.05
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

def _pipeline_key_func(start_date, end_date, ticker_group, tickers, forecast_method, progress_callback=None):
    """Generate cache key for pipeline, excluding progress callback."""
    if tickers:
        tickers_str = ",".join(sorted(tickers))
    else:
        tickers_str = "None"
    key_str = f"{start_date}|{end_date}|{ticker_group}|{tickers_str}|{forecast_method}"
    return f"pipeline_{hashlib.md5(key_str.encode()).hexdigest()}"

@cached(l1_ttl=3600, l2_ttl=86400, key_func=_pipeline_key_func)
def data_and_forecast_pipeline(start_date, end_date, ticker_group, tickers, forecast_method, progress_callback=None):
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
    
    elif forecast_method in ["LIGHTWEIGHT", "Lightweight"]:
        logger.info("Using Lightweight Ensemble Forecast")
        forecasts = {}
        uncertainties_dict = {}
        for i, ticker in enumerate(final_tickers):
            if i % 10 == 0:
                ml_callback(i, len(final_tickers), f"Lightweight forecasting {i}/{len(final_tickers)}")
            try:
                prices = data[ticker].dropna().values
                valid_prices = prices[~np.isnan(prices)]
                if len(valid_prices) > 0:
                    val = lightweight_ensemble_forecast(valid_prices)
                else:
                    val = 0.05
                forecasts[ticker] = val
                uncertainties_dict[ticker] = 0.05
            except Exception:
                forecasts[ticker] = 0.05
                uncertainties_dict[ticker] = 0.05
        
        mu_forecast = pd.Series(forecasts).fillna(0.0)
        uncertainties = pd.Series(uncertainties_dict).fillna(0.05)
        
    elif forecast_method in ["DEEP_LEARNING", "Ensemble"]:
        logger.info("Using Deep Learning Ensemble Forecast")
        mu_forecast, uncertainties = ml_forecast_returns(data, progress_callback=ml_callback)
    
    else:
        logger.warning(f"Unknown forecast method '{forecast_method}', defaulting to Lightweight")
        forecasts = {}
        uncertainties_dict = {}
        for ticker in final_tickers:
            prices = data[ticker].dropna().values
            valid_prices = prices[~np.isnan(prices)]
            val = lightweight_ensemble_forecast(valid_prices) if len(valid_prices)>0 else 0.05
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
        "latest_prices": latest_prices
    }

def optimize_portfolio(start_date, end_date, risk_free_rate, ticker_group=None, tickers=None,
                       target_return=None, risk_tolerance=None, portfolio_id=None,
                       persist_result=False, load_if_available=False, progress_callback=None,
                       l2_gamma=0.05, max_asset_weight=0.2, 
                       forecast_method="LIGHTWEIGHT", optimization_method="BL"):
    """Optimize portfolio and optionally persist or reuse saved results."""
    
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
        tickers = cleaned_tickers
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

    # 1. Determine Forecast Method (Handle Ex-Post overrides)
    is_ex_post = False
    try:
        if isinstance(end_date, str):
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        else:
            end_dt = end_date
        if isinstance(end_dt, datetime) and end_dt < datetime.now() - timedelta(days=90):
            is_ex_post = True
    except Exception as e:
        logger.warning(f"Could not parse date for Ex-Post check: {e}")

    if is_ex_post and optimization_method == "BL":
        logger.info("Switching 'BL' to 'MPT' (Historical) due to ex-post date range.")
        forecast_method = "HISTORICAL"
        optimization_method = "MPT"
        
    logger.info(f"Executing: Forecast={forecast_method}, Optimization={optimization_method}")

    # 2. Run Cached Pipeline (Data & Forecasting)
    try:
        pipeline_result = data_and_forecast_pipeline(
            start_date, end_date, ticker_group, tickers, forecast_method, 
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
                
                bl = BlackLittermanModel(S, pi=market_prior, absolute_views=mu, omega=omega, risk_aversion=delta)
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
        ef = EfficientFrontier(mu, S, weight_bounds=(0, max_asset_weight))

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
        final_prices = {t: latest_prices.get(t, 0.0) for t in final_weights.keys()}

        result_payload = {
            "weights": final_weights,
            "return": performance[0],
            "risk": performance[1],
            "sharpe_ratio": performance[2],
            "prices": final_prices
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
        return {
            "error": "Infeasible constraints. The portfolio cannot achieve the 'Target Return' with the current constraints.",
            "details": str(e)
        }
    except Exception as e:
        logger.error(f"General Optimization Exception: {e}")
        return {
            "error": f"Optimization failed: {str(e)}"
        }
