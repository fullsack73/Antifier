import json
import logging
from pathlib import Path
import time
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
import numpy as np
from pypfopt import EfficientFrontier, risk_models, objective_functions, BlackLittermanModel, black_litterman
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



def ml_forecast_returns(data, batch_size=20, progress_callback=None):
    """
    Forecast expected returns using ML models with memory-efficient batch processing.
    
    Args:
        data: DataFrame with stock prices (dates as index, tickers as columns)
        batch_size: Number of tickers to process in each batch (메모리 관리용)
        progress_callback: Optional callback(current, total, message)
    
    Returns:
        tuple: (forecasts_series, uncertainties_series)
    """
    start_time = time.time()
    logger.info(f"Starting BATCH ML forecasting for {len(data.columns)} tickers")
    
    # 메모리 효율을 위해 worker 수 제한 (LSTM/TensorFlow가 프로세스당 많은 메모리 사용)
    import os
    max_workers = min(os.cpu_count() or 4, len(data.columns), 4)  # 최대 4로 제한
    logger.info(f"Using {max_workers} parallel workers for ML forecasting (memory-safe mode)")
    
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
            with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as executor:
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


@cached(l1_ttl=600, l2_ttl=3600)  # 10 min L1, 1 hour L2 cache for portfolio optimization
def optimize_portfolio(start_date, end_date, risk_free_rate, ticker_group=None, tickers=None,
                       target_return=None, risk_tolerance=None, portfolio_id=None,
                       persist_result=False, load_if_available=False, progress_callback=None,
                       l2_gamma=0.05, max_asset_weight=0.2):
    """Optimize portfolio and optionally persist or reuse saved results."""
    # Log cache performance at start of optimization
    cache = get_cache()
    cache_stats = cache.stats()
    logger.info(f"CACHE PERFORMANCE: L1 Hit: {cache_stats['hit_ratios']['l1']:.1%}, L2 Hit: {cache_stats['hit_ratios']['l2']:.1%}, Overall: {cache_stats['hit_ratios']['overall']:.1%}")
    logger.info(f"CACHE MEMORY: {cache_stats['l1_cache']['memory_usage_mb']:.1f}MB / {cache_stats['l1_cache']['memory_limit_mb']:.1f}MB ({cache_stats['l1_cache']['memory_utilization']:.1%})")
    
    # Short-circuit if saved result should be reused
    if portfolio_id and load_if_available:
        saved_result = load_portfolio_result(portfolio_id)
        if saved_result:
            logger.info(f"Returning previously saved result for {portfolio_id}")
            return saved_result

    # Get tickers from the selected group or use the provided list
    if tickers:
        pass
    elif ticker_group:
        tickers = get_ticker_group(ticker_group)
    else:
        raise ValueError("Either ticker_group or tickers must be provided.")

    # Define weighted progress callback wrapper
    def _weighted_progress(stage_start, stage_end, current, total, message):
        if progress_callback and total > 0:
            stage_range = stage_end - stage_start
            normalized = (current / total) * stage_range
            global_progress = stage_start + normalized
            progress_callback(global_progress, 100, message)

    # Fetch data with comprehensive logging
    logger.info(f"PIPELINE STAGE 1: Attempting to fetch data for {len(tickers)} tickers")
    logger.info(f"Initial ticker list: {tickers[:10]}{'...' if len(tickers) > 10 else ''}")
    
    # Adapter for fetching (0-30%)
    def fetch_callback(current, total, message):
        _weighted_progress(0, 30, current, total, message)

    data = get_stock_data(tickers, start_date, end_date, progress_callback=fetch_callback)
    logger.info(f"PIPELINE STAGE 1 RESULT: Fetched data shape: {data.shape}")
    logger.info(f"Fetched data columns: {list(data.columns)[:10]}{'...' if len(data.columns) > 10 else ''}")

    # Check if data is empty after fetching
    if data.empty:
        logger.warning("Could not fetch any valid data for the given tickers and date range. Aborting optimization.")
        return {
            "error": "Could not fetch any valid data for the given tickers and date range."
        }
    
    # Data cleaning stage
    logger.info(f"PIPELINE STAGE 2: Data cleaning - before dropna: {len(data.columns)} columns")
    data = data.dropna(axis=1, how='all')
    logger.info(f"PIPELINE STAGE 2 RESULT: After dropna: {len(data.columns)} columns")
    
    dropped_tickers = set(tickers) - set(data.columns)
    if dropped_tickers:
        logger.warning(f"DROPPED DURING DATA CLEANING: {len(dropped_tickers)} tickers: {list(dropped_tickers)[:10]}{'...' if len(dropped_tickers) > 10 else ''}")
    
    tickers = data.columns.tolist()
    logger.info(f"PIPELINE STAGE 2 FINAL: Proceeding with {len(tickers)} tickers for forecasting")

    # Adapter for ML Forecasting (30-90%)
    def ml_callback(current, total, message):
        _weighted_progress(30, 90, current, total, message)

    # Determine if we are doing Ex-Post (Historical) or Ex-Ante (Future) analysis
    # If end_date is significantly in the past (> 90 days), assume Ex-Post analysis
    is_ex_post = False
    try:
        # Handle string or datetime input
        if isinstance(end_date, str):
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        else:
            end_dt = end_date
            
        if end_dt < datetime.now() - timedelta(days=90):
            is_ex_post = True
            logger.info(f"Optimization end date {end_dt.date()} is >90 days in the past. Switching to Ex-Post (Historical) Optimization.")
    except Exception as e:
        logger.warning(f"Could not parse date for Ex-Post check: {e}")

    if is_ex_post:
        logger.info("Using Historical CAGR for Ex-Post Optimization")
        
        # Calculate CAGR (Geometric Mean) instead of Arithmetic Mean
        # Formula: (End_Price / Start_Price) ^ (252 / Days) - 1
        # This penalizes volatility drag compared to arithmetic mean
        cagr_series = {}
        for ticker in data.columns:
            try:
                # Get valid price series
                prices = data[ticker].dropna()
                if len(prices) >= 2:
                    start_price = prices.iloc[0]
                    end_price = prices.iloc[-1]
                    
                    if start_price > 0:
                        # Calculate total return
                        total_return = end_price / start_price
                        
                        # Calculate years elapsed (using business days approx)
                        years = len(prices) / 252.0
                        
                        # Calculate CAGR
                        if total_return > 0 and years > 0:
                            cagr = (total_return ** (1 / years)) - 1
                        else:
                            cagr = -0.99 # Effectively -100%
                            
                        cagr_series[ticker] = cagr
                    else:
                        cagr_series[ticker] = 0.0
                else:
                    cagr_series[ticker] = 0.0
            except Exception as e:
                logger.warning(f"Failed to calculate CAGR for {ticker}: {e}")
                cagr_series[ticker] = 0.0
                
        mu = pd.Series(cagr_series)
        # Handle potential NaNs
        mu = mu.fillna(0)
        
        # Filter the historical data to align with the tickers that have a forecast
        aligned_data = data[mu.index]
        # Calculate covariance matrix on the aligned data (standard historical)
        S = risk_models.CovarianceShrinkage(aligned_data).ledoit_wolf()
        
    else:
        # Calculate expected returns using ML-based forecasting
        logger.info(f"Starting ML forecasting (Ex-Ante) with Black-Litterman for {len(data.columns)} tickers")
        mu_views, uncertainties = ml_forecast_returns(data, progress_callback=ml_callback)
        logger.info(f"ML forecasting completed. Got views for {len(mu_views)} tickers.")
        
        # Link views to data
        aligned_data = data[mu_views.index]
        logger.info(f"Aligned data contains {len(aligned_data.columns)} tickers for optimization")

        # Base covariance matrix (Historical)
        S_hist = risk_models.CovarianceShrinkage(aligned_data).ledoit_wolf()
        
        # Black-Litterman Optimization
        try:
            # 1. Market Caps (for Market Prior)
            mcaps = get_market_caps(list(mu_views.index))
            
            # 2. Market Implied Risk Aversion (Delta)
            market_ticker = "^GSPC"
            try:
                market_data = yf.download(market_ticker, start=start_date, end=end_date, progress=False)
                # Handle MultiIndex in yfinance 0.2+
                if isinstance(market_data.columns, pd.MultiIndex):
                    # Try to find Adj Close for ticker
                    if "Adj Close" in market_data.columns and market_ticker in market_data["Adj Close"].columns:
                         market_prices = market_data["Adj Close"][market_ticker]
                    else:
                         market_prices = market_data.iloc[:, 0] # Fallback
                elif "Adj Close" in market_data.columns:
                    market_prices = market_data["Adj Close"]
                else:
                    market_prices = market_data.iloc[:, 0]
                
                market_prices = market_prices.dropna()
                
                if market_prices.empty:
                     logger.warning("Market prices empty. Using default delta=2.5")
                     delta = 2.5
                else:
                     delta = black_litterman.market_implied_risk_aversion(market_prices, risk_free_rate=risk_free_rate)
                     logger.info(f"Market implied risk aversion (delta): {delta:.4f}")
            except Exception as e:
                logger.warning(f"Failed to fetch market prices for delta: {e}. Using delta=2.5")
                delta = 2.5
            
            if mcaps:
                logger.info("Applying Black-Litterman with Market Prior")
                market_prior = black_litterman.market_implied_prior_returns(mcaps, delta, S_hist, risk_free_rate=risk_free_rate)
                
                # Omega (Uncertainty matrix) - using forecast uncertainty
                uncertainties = uncertainties.reindex(mu_views.index).fillna(0.05)
                omega = np.diag(uncertainties ** 2)
                
                # Create BL Model
                bl = BlackLittermanModel(S_hist, pi=market_prior, absolute_views=mu_views, omega=omega, risk_aversion=delta)
                
                mu = bl.bl_returns()
                S = bl.bl_cov() # Posterior covariance
                logger.info("Black-Litterman optimization successful.")
            else:
                 logger.warning("No market caps available. Fallback to Mean-Variance with ML views.")
                 mu = mu_views
                 S = S_hist
        except Exception as e:
            logger.error(f"Black-Litterman failed: {e}. Fallback to Mean-Variance with ML views.")
            mu = mu_views
            S = S_hist

    # mu and S are now set for EfficientFrontier


    # Initialize Efficient Frontier
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
        ef.max_sharpe()

    # Get optimized weights
    weights = ef.clean_weights()
    
    # Filter out assets with near-zero weight
    final_weights = {ticker: weight for ticker, weight in weights.items() if weight > 1e-4}

    # Get performance metrics
    performance = ef.portfolio_performance(risk_free_rate=risk_free_rate)
    optimized_return = performance[0]
    optimized_std_dev = performance[1]
    optimized_sharpe_ratio = performance[2]

    # Get the latest prices for the tickers in the final portfolio
    latest_prices = {}
    if final_weights:
        final_tickers = list(final_weights.keys())
        logger.info(f"Fetching latest prices for {len(final_tickers)} final tickers.")

        for ticker in final_tickers:
            try:
                ticker_obj = yf.Ticker(ticker)
                # Fetching history for the last 2 days to get the most recent closing price
                hist = ticker_obj.history(period="2d", auto_adjust=True)
                if not hist.empty and 'Close' in hist.columns:
                    latest_prices[ticker] = hist['Close'].iloc[-1]
                    logger.info(f"Successfully fetched latest price for {ticker}: {latest_prices[ticker]:.2f}")
                else:
                    logger.warning(f"Could not retrieve latest price for {ticker}. It might be delisted or data is unavailable.")
            except Exception as e:
                logger.error(f"An error occurred while fetching the latest price for {ticker}: {e}")


    result_payload = {
        "weights": final_weights,
        "return": optimized_return,
        "risk": optimized_std_dev,
        "sharpe_ratio": optimized_sharpe_ratio,
        "prices": latest_prices
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
    elif persist_result and not portfolio_id:
        logger.warning("persist_result is True but portfolio_id is missing; skipping save")

    return result_payload
