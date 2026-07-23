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
try:
    import cvxpy as cp
except Exception:  # pragma: no cover - PyPortfolioOpt normally provides cvxpy.
    cp = None
from pypfopt import EfficientFrontier, risk_models, objective_functions, BlackLittermanModel, black_litterman
from pypfopt.exceptions import OptimizationError
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
import gc
from cache_manager import (
    get_cache, cached
)
from ticker_lists import get_ticker_group
from forecast_models import (
    ARIMATransformerPredictor,
    TransformerForecastModel,
    NO_VIEW_FORECAST_UNCERTAINTY,
    no_view_prediction,
)
from lightweight_forecast import lightweight_ensemble_forecast

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("logs/portfolio_results")
BASE_CURRENCY = "USD"
PORTFOLIO_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EXPECTED_RETURN_LOWER_BOUND = -0.99
EXPECTED_RETURN_UPPER_BOUND = 10.0
DEFAULT_FORECAST_UNCERTAINTY = 0.20
CONFIDENCE_REFERENCE_UNCERTAINTY = 0.20
MIN_FORECAST_CONFIDENCE = 0.05
MAX_FORECAST_CONFIDENCE = 0.95
MAX_FORECAST_UNCERTAINTY = 5.0
DEFAULT_REBALANCE_BAND = 0.02
DEFAULT_MAX_TURNOVER = 0.35
TRADING_DAYS_PER_YEAR = 252

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


class OptimizationCancelled(RuntimeError):
    """Raised when a long-running optimization job is cancelled cooperatively."""


def _raise_if_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise OptimizationCancelled("Optimization cancelled")


def _call_forecast_function(forecast_func, data, progress_callback, horizon, cancel_event):
    try:
        return forecast_func(
            data,
            progress_callback=progress_callback,
            horizon=horizon,
            cancel_event=cancel_event,
        )
    except TypeError as exc:
        if "cancel_event" not in str(exc):
            raise
        _raise_if_cancelled(cancel_event)
        return forecast_func(
            data,
            progress_callback=progress_callback,
            horizon=horizon,
        )


def _ensure_results_dir():
    """Create persistence directory if it does not exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _portfolio_result_path(portfolio_id):
    """Return a safe on-disk path for a persisted portfolio result."""
    if not isinstance(portfolio_id, str) or not PORTFOLIO_ID_PATTERN.fullmatch(portfolio_id):
        raise ValueError("portfolio_id must be a safe slug up to 128 characters")

    _ensure_results_dir()
    results_root = RESULTS_DIR.resolve()
    output_path = (results_root / f"{portfolio_id}.json").resolve()
    if results_root not in output_path.parents:
        raise ValueError("portfolio_id resolves outside the portfolio results directory")
    return output_path


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


def _annual_log_return_to_simple_return(annual_log_return):
    """Convert an annualized log return into an annualized simple return."""
    try:
        annual_log_return = float(annual_log_return)
    except (TypeError, ValueError):
        return 0.0

    if not np.isfinite(annual_log_return):
        return 0.0

    log_lower = np.log1p(EXPECTED_RETURN_LOWER_BOUND)
    log_upper = np.log1p(EXPECTED_RETURN_UPPER_BOUND)
    return float(np.expm1(np.clip(annual_log_return, log_lower, log_upper)))


def _period_return_to_annual_simple_return(period_return, horizon):
    """Annualize a forecast horizon return into a simple annual return."""
    try:
        period_return = float(period_return)
    except (TypeError, ValueError):
        return 0.0

    if not np.isfinite(period_return):
        return 0.0

    period_return = np.clip(period_return, EXPECTED_RETURN_LOWER_BOUND, None)
    annual_log_return = np.log1p(period_return) * (252 / max(1, int(horizon)))
    return _annual_log_return_to_simple_return(annual_log_return)


def _annual_log_uncertainty_to_simple_uncertainty(annual_log_return, annual_log_uncertainty):
    """Approximate annual log-return uncertainty on the annual simple-return scale."""
    try:
        annual_log_uncertainty = abs(float(annual_log_uncertainty))
    except (TypeError, ValueError):
        return DEFAULT_FORECAST_UNCERTAINTY

    if not np.isfinite(annual_log_uncertainty):
        return DEFAULT_FORECAST_UNCERTAINTY

    try:
        annual_log_return = float(annual_log_return)
    except (TypeError, ValueError):
        annual_log_return = 0.0

    if not np.isfinite(annual_log_return):
        annual_log_return = 0.0

    log_lower = np.log1p(EXPECTED_RETURN_LOWER_BOUND)
    log_upper = np.log1p(EXPECTED_RETURN_UPPER_BOUND)
    scale = np.exp(np.clip(annual_log_return, log_lower, log_upper))
    return float(np.clip(scale * annual_log_uncertainty, 1e-4, MAX_FORECAST_UNCERTAINTY))


def _annual_log_uncertainty_series_to_simple(mu_log, uncertainties):
    """Convert forecast uncertainty from annual log-return scale to simple-return scale."""
    mu_log = pd.Series(mu_log)
    uncertainties = pd.Series(uncertainties).reindex(mu_log.index).fillna(DEFAULT_FORECAST_UNCERTAINTY)
    return pd.Series(
        {
            ticker: _annual_log_uncertainty_to_simple_uncertainty(mu_log.loc[ticker], uncertainties.loc[ticker])
            for ticker in mu_log.index
        }
    )


def _normalize_expected_return_series(mu):
    """Sanitize optimizer expected returns as annualized simple returns."""
    return (
        pd.Series(mu)
        .replace([np.inf, -np.inf], 0.0)
        .fillna(0.0)
        .clip(lower=EXPECTED_RETURN_LOWER_BOUND, upper=EXPECTED_RETURN_UPPER_BOUND)
    )


def _normalize_uncertainty_series(uncertainties, index):
    """Sanitize annualized simple-return uncertainty inputs."""
    if uncertainties is None:
        uncertainties = pd.Series({ticker: DEFAULT_FORECAST_UNCERTAINTY for ticker in index})
    return (
        pd.Series(uncertainties)
        .reindex(index)
        .replace([np.inf, -np.inf], DEFAULT_FORECAST_UNCERTAINTY)
        .fillna(DEFAULT_FORECAST_UNCERTAINTY)
        .abs()
        .clip(lower=1e-4, upper=MAX_FORECAST_UNCERTAINTY)
    )


def _confidence_from_uncertainty(uncertainties):
    """Map return uncertainty to a bounded forecast confidence score."""
    uncertainties = _normalize_uncertainty_series(uncertainties, pd.Series(uncertainties).index)
    confidence = 1.0 / (1.0 + (uncertainties / CONFIDENCE_REFERENCE_UNCERTAINTY) ** 2)
    return confidence.clip(lower=MIN_FORECAST_CONFIDENCE, upper=MAX_FORECAST_CONFIDENCE)


def _is_no_view_prediction(prediction):
    """Return True when a forecast intentionally carries no alpha view."""
    if not isinstance(prediction, dict):
        return False
    expected_return = prediction.get("expected_return")
    return prediction.get("source") == "no_view" or expected_return is None


def _no_view_for_ticker(reason):
    prediction = no_view_prediction(reason)
    prediction["uncertainty"] = max(NO_VIEW_FORECAST_UNCERTAINTY, MAX_FORECAST_UNCERTAINTY)
    return prediction


def _shrink_expected_returns(forecast_mu, prior_mu, confidence):
    """Blend forecasts toward a prior according to forecast confidence."""
    forecast_mu = _normalize_expected_return_series(forecast_mu)
    prior_mu = _normalize_expected_return_series(prior_mu).reindex(forecast_mu.index).fillna(0.0)
    confidence = pd.Series(confidence).reindex(forecast_mu.index).fillna(MIN_FORECAST_CONFIDENCE)
    adjusted_mu = prior_mu + confidence * (forecast_mu - prior_mu)
    return _normalize_expected_return_series(adjusted_mu)


def _calculate_historical_cagr(data):
    """Calculate annualized simple returns from the available price history."""
    cagr_series = {}
    for ticker in data.columns:
        try:
            prices = data[ticker].dropna()
            if len(prices) >= 2:
                start_price = float(prices.iloc[0])
                end_price = float(prices.iloc[-1])
                years = len(prices) / 252.0
                if start_price > 0 and end_price > 0 and years > 0:
                    cagr_series[ticker] = (end_price / start_price) ** (1 / years) - 1
                else:
                    cagr_series[ticker] = EXPECTED_RETURN_LOWER_BOUND
            else:
                cagr_series[ticker] = 0.0
        except Exception:
            cagr_series[ticker] = 0.0
    return _normalize_expected_return_series(pd.Series(cagr_series))


def _james_stein_expected_returns(data):
    """Shrink sample means toward the global-minimum-variance mean.

    This is the parameter-free Jorion/Bayes-Stein cross-sectional estimator.
    It reduces expected-return estimation error without inspecting any rows
    outside the price frame supplied by the caller.
    """
    prices = (
        pd.DataFrame(data)
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    tickers = list(prices.columns)
    returns = (
        prices.pct_change(fill_method=None)
        .replace([np.inf, -np.inf], np.nan)
        .dropna(axis=0, how="any")
    )
    fallback = _calculate_historical_cagr(prices).reindex(tickers).fillna(0.0)
    diagnostics = {
        "estimator": "jorion_bayes_stein",
        "observation_count": int(len(returns)),
        "asset_count": int(len(tickers)),
        "shrinkage_intensity": 0.0,
        "target_daily_return": None,
        "target_annual_return": None,
    }
    if returns.empty or not tickers:
        diagnostics["fallback_reason"] = "insufficient_complete_returns"
        return fallback, diagnostics

    sample_mean = returns.mean().reindex(tickers).astype(float)
    if len(tickers) == 1 or len(returns) < 2:
        annualized = _normalize_expected_return_series(
            sample_mean * TRADING_DAYS_PER_YEAR
        )
        target_daily = float(sample_mean.iloc[0])
        diagnostics.update({
            "target_daily_return": target_daily,
            "target_annual_return": float(
                annualized.iloc[0]
            ),
            "fallback_reason": "insufficient_cross_section",
        })
        return annualized, diagnostics

    covariance = returns.cov().reindex(
        index=tickers,
        columns=tickers,
    )
    covariance_values = covariance.to_numpy(dtype=float)
    mean_values = sample_mean.to_numpy(dtype=float)
    try:
        precision = np.linalg.pinv(covariance_values)
        ones = np.ones(len(tickers), dtype=float)
        denominator = float(ones @ precision @ ones)
        if not np.isfinite(denominator) or denominator <= 0.0:
            raise ValueError("non-positive GMV precision denominator")
        target_daily = float(
            (ones @ precision @ mean_values) / denominator
        )
        deviation = mean_values - target_daily
        distance = float(
            len(returns) * (deviation @ precision @ deviation)
        )
        if not np.isfinite(distance):
            raise ValueError("non-finite mean dispersion")
        distance = max(0.0, distance)
        numerator = float(len(tickers) + 2)
        shrinkage = float(
            np.clip(
                numerator / (numerator + distance),
                0.0,
                1.0,
            )
        )
        shrunk_daily = (
            target_daily + (1.0 - shrinkage) * deviation
        )
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
        diagnostics["fallback_reason"] = (
            f"estimator_failure:{type(exc).__name__}"
        )
        return fallback, diagnostics

    annualized = _normalize_expected_return_series(
        pd.Series(
            shrunk_daily * TRADING_DAYS_PER_YEAR,
            index=tickers,
            dtype=float,
        )
    )
    diagnostics.update({
        "shrinkage_intensity": shrinkage,
        "target_daily_return": target_daily,
        "target_annual_return": float(
            np.clip(
                target_daily * TRADING_DAYS_PER_YEAR,
                EXPECTED_RETURN_LOWER_BOUND,
                EXPECTED_RETURN_UPPER_BOUND,
            )
        ),
        "sample_mean_dispersion": float(
            sample_mean.std(ddof=0)
        ),
        "shrunk_mean_dispersion": float(
            pd.Series(shrunk_daily).std(ddof=0)
        ),
    })
    return annualized, diagnostics


def _historical_returns_with_hac_uncertainty(data):
    """Estimate historical views with Newey-West mean uncertainty.

    The point estimate remains the historical CAGR. Only its annualized
    standard error changes, using a data-length Newey-West lag rule and rows
    supplied by the caller.
    """
    prices = (
        pd.DataFrame(data)
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    tickers = list(prices.columns)
    views = _calculate_historical_cagr(prices).reindex(tickers)
    uncertainties = {}
    ticker_diagnostics = {}
    for ticker in tickers:
        returns = (
            prices[ticker]
            .pct_change(fill_method=None)
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .to_numpy(dtype=float)
        )
        observation_count = int(len(returns))
        if observation_count < 2:
            uncertainties[ticker] = MAX_FORECAST_UNCERTAINTY
            ticker_diagnostics[ticker] = {
                "observation_count": observation_count,
                "lag_count": 0,
                "annual_standard_error": (
                    MAX_FORECAST_UNCERTAINTY
                ),
                "fallback_reason": "insufficient_returns",
            }
            continue

        centered = returns - float(np.mean(returns))
        lag_count = min(
            observation_count - 1,
            max(
                0,
                int(
                    np.floor(
                        4.0
                        * (observation_count / 100.0) ** (2.0 / 9.0)
                    )
                ),
            ),
        )
        long_run_variance = float(
            np.dot(centered, centered) / observation_count
        )
        for lag in range(1, lag_count + 1):
            autocovariance = float(
                np.dot(centered[lag:], centered[:-lag])
                / observation_count
            )
            bartlett_weight = 1.0 - lag / (lag_count + 1.0)
            long_run_variance += (
                2.0 * bartlett_weight * autocovariance
            )
        long_run_variance = max(0.0, long_run_variance)
        annual_standard_error = float(
            np.sqrt(long_run_variance / observation_count)
            * TRADING_DAYS_PER_YEAR
        )
        annual_standard_error = float(
            np.clip(
                annual_standard_error,
                1e-4,
                MAX_FORECAST_UNCERTAINTY,
            )
        )
        uncertainties[ticker] = annual_standard_error
        ticker_diagnostics[ticker] = {
            "observation_count": observation_count,
            "lag_count": int(lag_count),
            "annual_standard_error": annual_standard_error,
            "annual_naive_standard_error": float(
                np.std(returns, ddof=1)
                / np.sqrt(observation_count)
                * TRADING_DAYS_PER_YEAR
            ),
        }

    uncertainty_series = pd.Series(
        uncertainties,
        index=tickers,
        dtype=float,
    )
    finite = uncertainty_series.replace(
        [np.inf, -np.inf],
        np.nan,
    ).dropna()
    diagnostics = {
        "estimator": "newey_west_hac_mean_standard_error",
        "lag_rule": "floor(4*(T/100)^(2/9))",
        "ticker_diagnostics": ticker_diagnostics,
        "median_annual_standard_error": (
            None if finite.empty else float(finite.median())
        ),
        "minimum_annual_standard_error": (
            None if finite.empty else float(finite.min())
        ),
        "maximum_annual_standard_error": (
            None if finite.empty else float(finite.max())
        ),
    }
    return (
        views,
        _normalize_uncertainty_series(uncertainty_series, tickers),
        diagnostics,
    )


def _align_price_history_without_lookahead(data):
    """Align assets on their common observable history without backward fill."""
    aligned = (
        pd.DataFrame(data)
        .sort_index()
        .replace([0.0, np.inf, -np.inf], np.nan)
    )
    aligned = aligned.dropna(axis=1, how="all")
    if aligned.empty:
        return aligned
    first_valid_dates = [
        aligned[ticker].first_valid_index()
        for ticker in aligned.columns
        if aligned[ticker].first_valid_index() is not None
    ]
    if not first_valid_dates:
        return aligned.iloc[0:0]
    common_start = max(first_valid_dates)
    aligned = aligned.loc[aligned.index >= common_start].ffill()
    return aligned.dropna(axis=1, how="any")


def _initialize_data_eligibility(
    price_data,
    requested_tickers,
    min_history,
    end_date,
    staleness_days=14,
):
    """Create a JSON-safe audit trail before any universe filtering."""
    data = pd.DataFrame(price_data)
    requested = list(dict.fromkeys(
        str(ticker).strip()
        for ticker in requested_tickers
        if str(ticker).strip()
    ))
    window_rows = int(len(data.index))
    ticker_diagnostics = {}
    for ticker in requested:
        series = (
            pd.to_numeric(data[ticker], errors="coerce")
            if ticker in data
            else pd.Series(dtype=float)
        )
        valid = series.replace([np.inf, -np.inf], np.nan).dropna()
        first = valid.first_valid_index()
        last = valid.last_valid_index()
        ticker_diagnostics[ticker] = {
            "status": "pending",
            "observation_count": int(len(valid)),
            "window_observation_count": window_rows,
            "coverage_rate": (
                float(len(valid) / window_rows)
                if window_rows
                else 0.0
            ),
            "first_observation_date": (
                None
                if first is None
                else pd.Timestamp(first).strftime("%Y-%m-%d")
            ),
            "last_observation_date": (
                None
                if last is None
                else pd.Timestamp(last).strftime("%Y-%m-%d")
            ),
            "drop_reasons": [],
        }
    diagnostics = {
        "policy": {
            "minimum_observations": int(max(0, min_history)),
            "staleness_days": int(max(0, staleness_days)),
            "alignment": (
                "latest_common_first_observation_then_forward_fill"
            ),
            "leading_fill": "forbidden",
            "base_currency": BASE_CURRENCY,
        },
        "requested_tickers": requested,
        "requested_count": int(len(requested)),
        "ticker_diagnostics": ticker_diagnostics,
    }
    missing = [
        ticker for ticker in requested
        if ticker not in data or data[ticker].notna().sum() == 0
    ]
    _mark_data_eligibility_drop(
        diagnostics,
        missing,
        reason="no_price_data",
        stage="fetch",
    )
    diagnostics["requested_end_date"] = pd.Timestamp(end_date).strftime(
        "%Y-%m-%d"
    )
    return diagnostics


def _mark_data_eligibility_drop(
    diagnostics,
    tickers,
    reason,
    stage,
):
    for ticker in tickers:
        item = diagnostics["ticker_diagnostics"].setdefault(
            str(ticker),
            {
                "status": "pending",
                "observation_count": 0,
                "window_observation_count": 0,
                "coverage_rate": 0.0,
                "first_observation_date": None,
                "last_observation_date": None,
                "drop_reasons": [],
            },
        )
        event = {"reason": str(reason), "stage": str(stage)}
        if event not in item["drop_reasons"]:
            item["drop_reasons"].append(event)
        item["status"] = "dropped"


def _finalize_data_eligibility(diagnostics, aligned_data):
    aligned = pd.DataFrame(aligned_data)
    eligible = [
        ticker
        for ticker in diagnostics["requested_tickers"]
        if (
            ticker in aligned
            and diagnostics["ticker_diagnostics"][ticker]["status"]
            != "dropped"
            and not aligned[ticker]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .empty
        )
    ]
    eligible_set = set(eligible)
    for ticker, item in diagnostics["ticker_diagnostics"].items():
        if ticker in eligible_set:
            item["status"] = "eligible"
        elif item["status"] == "pending":
            _mark_data_eligibility_drop(
                diagnostics,
                [ticker],
                reason="alignment_missing",
                stage="alignment",
            )
    dropped = [
        ticker
        for ticker in diagnostics["requested_tickers"]
        if diagnostics["ticker_diagnostics"].get(
            ticker,
            {},
        ).get("status") == "dropped"
    ]
    diagnostics.update({
        "eligible_tickers": eligible,
        "eligible_count": int(len(eligible)),
        "dropped_tickers": dropped,
        "dropped_count": int(len(dropped)),
        "aligned_observation_count": int(len(aligned)),
        "aligned_start_date": (
            None
            if aligned.empty
            else pd.Timestamp(aligned.index.min()).strftime("%Y-%m-%d")
        ),
        "aligned_end_date": (
            None
            if aligned.empty
            else pd.Timestamp(aligned.index.max()).strftime("%Y-%m-%d")
        ),
    })
    return diagnostics


def _latest_market_caps_are_point_in_time_compatible(
    end_date,
    reference_date=None,
    tolerance_days=14,
):
    """Latest market caps are valid only for a near-live optimization date."""
    try:
        end = pd.Timestamp(end_date).tz_localize(None).normalize()
        reference = (
            pd.Timestamp.utcnow().tz_localize(None).normalize()
            if reference_date is None
            else pd.Timestamp(reference_date).tz_localize(None).normalize()
        )
    except Exception:
        return False
    distance = (reference - end).days
    return bool(-1 <= distance <= max(0, int(tolerance_days)))


def _series_to_float_dict(series):
    """Return a JSON-friendly float dictionary from a pandas Series-like object."""
    return {str(k): float(v) for k, v in pd.Series(series).items() if np.isfinite(v)}


def _sanitize_value_series(values, index=None):
    series = pd.Series(values, dtype=float)
    if index is not None:
        series = series.reindex(index)
    return (
        series
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .clip(lower=0.0)
    )


def _safe_float(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if np.isfinite(value) else default


def _weights_from_values(values, denominator):
    denominator = _safe_float(denominator, 0.0)
    if denominator <= 0:
        return {}
    return {
        str(ticker): float(value / denominator)
        for ticker, value in pd.Series(values, dtype=float).items()
        if np.isfinite(value) and value > 1e-10
    }


def _performance_for_weights(weights, expected_returns, covariance, risk_free_rate):
    """Calculate metrics for the weights actually returned to the caller."""
    mu = pd.Series(expected_returns, dtype=float)
    weight_series = (
        pd.Series(weights, dtype=float)
        .reindex(mu.index)
        .fillna(0.0)
    )
    total = float(weight_series.sum())
    if total > 0:
        weight_series = weight_series / total
    matrix = pd.DataFrame(covariance).reindex(
        index=mu.index,
        columns=mu.index,
    )
    expected_return = float(weight_series @ mu)
    variance = float(
        weight_series.values @ matrix.values @ weight_series.values
    )
    volatility = float(np.sqrt(max(0.0, variance)))
    sharpe = (
        None
        if volatility <= 1e-12
        else float(
            (expected_return - float(risk_free_rate)) / volatility
        )
    )
    return expected_return, volatility, sharpe


def apply_min_holding_threshold(weights, min_holding_weight=0.0):
    """Drop tiny long-only positions and renormalize when the threshold is feasible."""
    threshold = max(0.0, _safe_float(min_holding_weight, 0.0))
    series = (
        pd.Series(weights, dtype=float)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .clip(lower=0.0)
    )
    if series.empty:
        return {}

    total = float(series.sum())
    if total <= 0:
        return {str(ticker): 0.0 for ticker in series.index}
    normalized = series / total
    if threshold <= 0:
        return {str(ticker): float(weight) for ticker, weight in normalized.items()}

    filtered = normalized.where(normalized >= threshold, 0.0)
    filtered_total = float(filtered.sum())
    if filtered_total <= 0:
        return {str(ticker): float(weight) for ticker, weight in normalized.items()}
    filtered = filtered / filtered_total
    return {str(ticker): float(weight) for ticker, weight in filtered.items()}


def _turnover_penalty_objective(weights, current_weights, gamma=0.0):
    if cp is None or gamma <= 0:
        return 0
    return float(gamma) * cp.norm(weights - np.asarray(current_weights, dtype=float), 1)


def apply_trade_controls(current_values, target_values, portfolio_value=None,
                         rebalance_band=0.0, max_turnover=None):
    """
    Apply rebalance band and gross-turnover cap to target dollar values.

    The helper works in value space, so it can be reused by the backtester and
    Portfolio Manager before costs, share rounding, or order generation.
    """
    current_raw = pd.Series(current_values, dtype=float)
    target_raw = pd.Series(target_values, dtype=float)
    index = current_raw.index.union(target_raw.index)
    current = _sanitize_value_series(current_raw, index=index)
    target = _sanitize_value_series(target_raw, index=index)

    inferred_value = max(float(current.sum()), float(target.sum()), 0.0)
    portfolio_value = _safe_float(portfolio_value, inferred_value)
    if portfolio_value <= 0:
        portfolio_value = inferred_value

    deltas = target - current
    gross_trade_value = float(deltas.abs().sum())

    band = max(0.0, _safe_float(rebalance_band, 0.0))
    threshold = band * portfolio_value if portfolio_value > 0 else 0.0
    controlled_deltas = deltas.copy()
    skipped_mask = (controlled_deltas.abs() > 1e-10) & (controlled_deltas.abs() < threshold)
    controlled_deltas.loc[skipped_mask] = 0.0

    # A per-asset band can otherwise keep only one side of a self-financing
    # rebalance. Reintroduce the minimum skipped opposite-side trades needed
    # to preserve the target's intended risky/cash exposure.
    desired_net_trade = float(target.sum() - current.sum())
    band_net_trade = float(controlled_deltas.sum())
    net_trade_gap = desired_net_trade - band_net_trade
    reintroduced_mask = pd.Series(False, index=index, dtype=bool)
    if net_trade_gap > 1e-10:
        remaining_buys = (deltas - controlled_deltas).clip(lower=0.0)
        available = float(remaining_buys.sum())
        if available > 0:
            addition = remaining_buys * min(1.0, net_trade_gap / available)
            controlled_deltas += addition
            reintroduced_mask |= addition > 1e-10
    elif net_trade_gap < -1e-10:
        remaining_sells = (controlled_deltas - deltas).clip(lower=0.0)
        available = float(remaining_sells.sum())
        if available > 0:
            addition = remaining_sells * min(
                1.0,
                -net_trade_gap / available,
            )
            controlled_deltas -= addition
            reintroduced_mask |= addition > 1e-10

    cap_hit = False
    turnover_cap = None
    if max_turnover is not None:
        turnover_cap = max(0.0, _safe_float(max_turnover, 0.0))
        max_trade_value = turnover_cap * portfolio_value
        post_band_trade = float(controlled_deltas.abs().sum())
        if portfolio_value > 0 and post_band_trade > max_trade_value + 1e-10:
            scale = max_trade_value / post_band_trade if post_band_trade > 0 else 0.0
            controlled_deltas *= scale
            cap_hit = True

    # Defensive guard for malformed targets or a constrained net purchase.
    available_cash = max(0.0, portfolio_value - float(current.sum()))
    net_buy_value = float(controlled_deltas.sum())
    cash_balance_adjusted = False
    if net_buy_value > available_cash + 1e-10:
        buy_mask = controlled_deltas > 0
        buy_value = float(controlled_deltas.loc[buy_mask].sum())
        if buy_value > 0:
            scale = max(0.0, (buy_value - (net_buy_value - available_cash)) / buy_value)
            controlled_deltas.loc[buy_mask] *= scale
            cash_balance_adjusted = True

    controlled_target = (current + controlled_deltas).clip(lower=0.0)
    controlled_trade_value = float(controlled_deltas.abs().sum())
    turnover = gross_trade_value / portfolio_value if portfolio_value > 0 else 0.0
    controlled_turnover = controlled_trade_value / portfolio_value if portfolio_value > 0 else 0.0

    diagnostics = {
        "enabled": bool(band > 0 or max_turnover is not None),
        "rebalance_band": float(band),
        "max_turnover": None if turnover_cap is None else float(turnover_cap),
        "gross_trade_value": gross_trade_value,
        "controlled_trade_value": controlled_trade_value,
        "turnover": float(turnover),
        "controlled_turnover": float(controlled_turnover),
        "skipped_trade_count": int(
            (
                (deltas.abs() > 1e-10)
                & (controlled_deltas.abs() <= 1e-10)
            ).sum()
        ),
        "band_reintroduced_trade_count": int(reintroduced_mask.sum()),
        "desired_net_trade_value": float(desired_net_trade),
        "post_control_net_trade_value": float(controlled_deltas.sum()),
        "turnover_cap_hit": bool(cap_hit),
        "cash_balance_adjusted": bool(cash_balance_adjusted),
    }
    return controlled_target, diagnostics


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
        return factor.replace([np.inf, -np.inf], np.nan).ffill()
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

    output_path = _portfolio_result_path(portfolio_id)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    logger.info(f"Saved portfolio result to {output_path}")


def load_portfolio_result(portfolio_id):
    """Load a previously saved portfolio optimization result."""
    if not portfolio_id:
        raise ValueError("portfolio_id is required to load results")

    output_path = _portfolio_result_path(portfolio_id)
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


def _stock_data_key_func(tickers, start_date, end_date, progress_callback=None, cancel_event=None):
    tickers_str = ",".join(tickers or [])
    key_str = f"{tickers_str}|{start_date}|{end_date}|stock_data_v2"
    return f"stock_data_{hashlib.md5(key_str.encode()).hexdigest()}"


@cached(l1_ttl=900, l2_ttl=14400, key_func=_stock_data_key_func)  # 15 min L1, 4 hour L2 cache
def get_stock_data(tickers, start_date, end_date, progress_callback=None, cancel_event=None):
    """Fetch stock data for given tickers and date range using chunked batch processing."""
    _raise_if_cancelled(cancel_event)
    logger.info(f"GET_STOCK_DATA: Starting fetch for {len(tickers)} tickers")
    
    all_series = []
    
    # Process in chunks to prevent one bad ticker from blocking the whole batch
    BATCH_SIZE = 50
    
    # Helper to chunk list
    def chunked_iterable(iterable, size):
        for i in range(0, len(iterable), size):
            yield iterable[i:i + size]

    for chunk_idx, chunk in enumerate(chunked_iterable(tickers, BATCH_SIZE)):
        _raise_if_cancelled(cancel_event)
        if progress_callback:
            progress_callback(chunk_idx * BATCH_SIZE, len(tickers), f"Fetching data for tickers {chunk_idx * BATCH_SIZE + 1}-{min((chunk_idx + 1) * BATCH_SIZE, len(tickers))}")
        
        logger.info(f"GET_STOCK_DATA: Processing chunk {chunk_idx+1} ({len(chunk)} tickers)")
        chunk_data = pd.DataFrame()
        
        # Try batch download for this chunk
        try:
            def _download_chunk():
                return yf.download(chunk, start=start_date, end=end_date, progress=False, auto_adjust=True, threads=True)

            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(_download_chunk)
            wait_for_shutdown = True
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

            except FuturesTimeoutError:
                wait_for_shutdown = False
                future.cancel()
                logger.warning(f"GET_STOCK_DATA: Chunk {chunk_idx+1} timed out")
            except Exception as e:
                logger.warning(f"GET_STOCK_DATA: Chunk {chunk_idx+1} failed: {e}")
            finally:
                executor.shutdown(wait=wait_for_shutdown, cancel_futures=not wait_for_shutdown)

        except Exception as e:
            logger.error(f"GET_STOCK_DATA: Chunk wrapper failed: {e}")

        # Fallback for this chunk if batch failed or resulted in empty data
        if chunk_data.empty:
            logger.info(f"GET_STOCK_DATA: Fallback to individual fetch for chunk {chunk_idx+1}")
            individual_data = {}
            max_workers = min(32, len(chunk))
            
            def _fetch_single_safe(ticker):
                _raise_if_cancelled(cancel_event)
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
                    _raise_if_cancelled(cancel_event)
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
        
        if _is_no_view_prediction(prediction):
            logger.info(f"ARIMA + Transformer produced no view for {ticker} in {elapsed:.2f}s")
        else:
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

        if _is_no_view_prediction(prediction):
            logger.info(f"Transformer produced no view for {ticker} in {elapsed:.2f}s")
        else:
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

    Returns expected_return as an annualized log return, or an explicit no-view
    payload when this ML path cannot produce a valid forecast.
    """
    prices = ticker_data.values if hasattr(ticker_data, "values") else np.asarray(ticker_data)
    valid_prices = prices[~np.isnan(prices)]

    if len(valid_prices) < 100:
        logger.info(f"ARIMA + Transformer no-view for {ticker}: {len(valid_prices)} points (< 100 required)")
        return _no_view_for_ticker("insufficient data for ARIMA + Transformer")

    prediction = _generate_arima_transformer_prediction(ticker, ticker_data, horizon=horizon)
    if prediction is None:
        logger.warning(f"ARIMA + Transformer training failed for {ticker}, returning no-view")
        return _no_view_for_ticker("ARIMA + Transformer training failed")

    if _is_no_view_prediction(prediction):
        return prediction

    prediction['expected_return'] = float(prediction.get('expected_return'))
    prediction['source'] = 'arima_transformer'
    return prediction


def forecast_single_ticker_with_ensemble(ticker, ticker_data, horizon=252):
    """Backward-compatible alias: the old ensemble path now uses ARIMA + Transformer."""
    return forecast_single_ticker_with_arima_transformer(ticker, ticker_data, horizon=horizon)


def forecast_single_ticker_with_transformer(ticker, ticker_data, horizon=252):
    """
    Forecast a single ticker using the Transformer path.

    Returns expected_return as an annualized log return, or an explicit no-view
    payload when this ML path cannot produce a valid forecast.
    """
    prices = ticker_data.values if hasattr(ticker_data, "values") else np.asarray(ticker_data)
    valid_prices = prices[~np.isnan(prices)]

    if len(valid_prices) < 100:
        logger.info(f"Transformer no-view for {ticker}: {len(valid_prices)} points (< 100 required)")
        return _no_view_for_ticker("insufficient data for Transformer")

    prediction = _generate_transformer_prediction(ticker, ticker_data, horizon=horizon)
    if prediction is None:
        logger.warning(f"Transformer training failed for {ticker}, returning no-view")
        return _no_view_for_ticker("Transformer training failed")

    if _is_no_view_prediction(prediction):
        return prediction

    prediction['expected_return'] = float(prediction.get('expected_return'))
    prediction['source'] = 'transformer'
    return prediction


@cached(l1_ttl=900, l2_ttl=14400)  # 15 min L1, 4 hour L2 cache for predictions
def _ml_forecast_single_ticker(ticker, ticker_data, horizon=252):
    """Forecast returns for single ticker using ARIMA + Transformer with caching.
    
    Returns no-view when insufficient data or model failure prevents a valid ML forecast.
    Returns dictionary with expected_return and uncertainty.
    """
    try:
        prices = ticker_data.values
        valid_prices = prices[~np.isnan(prices)]
        
        if len(valid_prices) < 100:
            logger.info(f"ARIMA + Transformer no-view for {ticker}: {len(valid_prices)} points (< 100 required)")
            return ticker, _no_view_for_ticker("insufficient data for ARIMA + Transformer")
        
        prediction = _generate_arima_transformer_prediction(ticker, ticker_data, horizon=horizon)
        
        if prediction is None:
            logger.warning(f"ARIMA + Transformer training failed for {ticker}, returning no-view")
            return ticker, _no_view_for_ticker("ARIMA + Transformer training failed")
        
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
            logger.info(f"Transformer no-view for {ticker}: {len(valid_prices)} points (< 100 required)")
            return ticker, _no_view_for_ticker("insufficient data for Transformer")

        prediction = _generate_transformer_prediction(ticker, ticker_data, horizon=horizon)

        if prediction is None:
            logger.warning(f"Transformer training failed for {ticker}, returning no-view")
            return ticker, _no_view_for_ticker("Transformer training failed")

        return ticker, prediction

    finally:
        gc.collect()



def ml_forecast_returns(data, batch_size=50, progress_callback=None, horizon=252, cancel_event=None):
    """
    Forecast expected returns using ARIMA + Transformer with memory-efficient batch processing.
    
    Args:
        data: DataFrame with stock prices (dates as index, tickers as columns)
        batch_size: Number of tickers to process in each batch (Increased for throughput)
        progress_callback: Optional callback(current, total, message)
    
    Returns:
        tuple: (forecasts_series, uncertainties_series)
    """
    _raise_if_cancelled(cancel_event)
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
            _raise_if_cancelled(cancel_event)
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(tickers))
            batch_tickers = tickers[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch_tickers)} tickers)")
            
            # ProcessPoolExecutor for true parallelism
            with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx, initializer=worker_initializer) as executor:
                future_to_ticker = {}
                for ticker in batch_tickers:
                    _raise_if_cancelled(cancel_event)
                    future = executor.submit(_ml_forecast_single_ticker, ticker, data[ticker], horizon)
                    future_to_ticker[future] = ticker
                
                for future in as_completed(future_to_ticker):
                    _raise_if_cancelled(cancel_event)
                    ticker = future_to_ticker[future]
                    try:
                        result_ticker, prediction_result = future.result()
                        # Handle old return type (float) vs new (dict) for safety during transition
                        if isinstance(prediction_result, dict):
                            forecasts[result_ticker] = prediction_result.get('expected_return')
                            uncertainties[result_ticker] = prediction_result.get('uncertainty', DEFAULT_FORECAST_UNCERTAINTY)
                        else:
                            forecasts[result_ticker] = float(prediction_result)
                            uncertainties[result_ticker] = DEFAULT_FORECAST_UNCERTAINTY
                    except Exception as exc:
                        logger.error(f"ML forecasting exception for {ticker}: {exc}")
                        forecasts[ticker] = None
                        uncertainties[ticker] = MAX_FORECAST_UNCERTAINTY
            
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
        
    except OptimizationCancelled:
        raise
    except Exception as e:
        logger.error(f"ARIMA + Transformer forecasting failed critically: {e}. Returning no-view forecasts.")
        forecasts = {}
        uncertainties = {}
        for ticker in data.columns:
            _raise_if_cancelled(cancel_event)
            forecasts[ticker] = None
            uncertainties[ticker] = MAX_FORECAST_UNCERTAINTY
        return pd.Series(forecasts), pd.Series(uncertainties)


def transformer_forecast_returns(data, batch_size=20, progress_callback=None, horizon=252, cancel_event=None):
    """
    Forecast expected returns using a standalone Transformer model.

    Returns:
        tuple: (forecasts_series, uncertainties_series)
    """
    _raise_if_cancelled(cancel_event)
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
            _raise_if_cancelled(cancel_event)
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(tickers))
            batch_tickers = tickers[batch_start:batch_end]

            logger.info(f"Processing Transformer batch {batch_idx + 1}/{total_batches} ({len(batch_tickers)} tickers)")

            with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx, initializer=worker_initializer) as executor:
                future_to_ticker = {}
                for ticker in batch_tickers:
                    _raise_if_cancelled(cancel_event)
                    future = executor.submit(_transformer_forecast_single_ticker, ticker, data[ticker], horizon)
                    future_to_ticker[future] = ticker

                for future in as_completed(future_to_ticker):
                    _raise_if_cancelled(cancel_event)
                    ticker = future_to_ticker[future]
                    try:
                        result_ticker, prediction_result = future.result()
                        forecasts[result_ticker] = prediction_result.get('expected_return')
                        uncertainties[result_ticker] = prediction_result.get('uncertainty', DEFAULT_FORECAST_UNCERTAINTY)
                    except Exception as exc:
                        logger.error(f"Transformer forecasting exception for {ticker}: {exc}")
                        forecasts[ticker] = None
                        uncertainties[ticker] = MAX_FORECAST_UNCERTAINTY

            gc.collect()

            completed = len(forecasts)
            logger.info(f"Transformer batch {batch_idx + 1} complete. Total progress: {completed}/{len(tickers)}")
            if progress_callback:
                progress_callback(completed, len(tickers), f"Transformer Training: Batch {batch_idx + 1}/{total_batches} complete")

        elapsed_time = time.time() - start_time
        logger.info(f"Transformer forecasting completed in {elapsed_time:.2f}s for {len(forecasts)} tickers")
        return pd.Series(forecasts), pd.Series(uncertainties)

    except OptimizationCancelled:
        raise
    except Exception as e:
        logger.error(f"Transformer forecasting failed critically: {e}. Returning no-view forecasts.")
        forecasts = {}
        uncertainties = {}
        for ticker in data.columns:
            _raise_if_cancelled(cancel_event)
            forecasts[ticker] = None
            uncertainties[ticker] = MAX_FORECAST_UNCERTAINTY
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

def _pipeline_key_func(
    start_date,
    end_date,
    ticker_group,
    tickers,
    forecast_method,
    forecast_horizon=63,
    min_history=504,
    progress_callback=None,
    cancel_event=None,
):
    """Generate cache key for pipeline, excluding progress callback."""
    if tickers:
        tickers_str = ",".join(sorted(tickers))
    else:
        tickers_str = "None"
    key_str = f"{start_date}|{end_date}|{ticker_group}|{tickers_str}|{forecast_method}|{forecast_horizon}|{min_history}|usd_fx_mu_conf_v3_eligibility"
    return f"pipeline_{hashlib.md5(key_str.encode()).hexdigest()}"

@cached(l1_ttl=3600, l2_ttl=86400, key_func=_pipeline_key_func)
def data_and_forecast_pipeline(
    start_date,
    end_date,
    ticker_group,
    tickers,
    forecast_method,
    forecast_horizon=63,
    min_history=504,
    progress_callback=None,
    cancel_event=None,
):
    """
    Pipeline for Data Fetching, Cleaning, and Forecasting.
    Decoupled from optimization constraints to enable 'Warm Start'.
    """
    _raise_if_cancelled(cancel_event)
    logger.info("Executing data_and_forecast_pipeline (Refreshed/Cold Start)")
    
    if tickers:
        pass
    elif ticker_group:
        tickers = get_ticker_group(ticker_group)
    else:
        raise ValueError("Either ticker_group or tickers must be provided.")
    requested_tickers = list(tickers)

    def _weighted_progress(stage_start, stage_end, current, total, message):
        if progress_callback and total > 0:
            stage_range = stage_end - stage_start
            normalized = (current / total) * stage_range
            global_progress = stage_start + normalized
            progress_callback(global_progress, 100, message)

    logger.info(f"PIPELINE STAGE 1: Attempting to fetch data for {len(tickers)} tickers")
    def fetch_callback(current, total, message):
        _weighted_progress(0, 30, current, total, message)
        
    data = get_stock_data(tickers, start_date, end_date, progress_callback=fetch_callback, cancel_event=cancel_event)
    _raise_if_cancelled(cancel_event)
    data_eligibility = _initialize_data_eligibility(
        data,
        requested_tickers,
        min_history,
        end_date,
    )
    
    if data.empty:
        logger.warning("Could not fetch any valid data.")
        return {
            "error": "Could not fetch any valid data for the given tickers and date range.",
            "data_eligibility": _finalize_data_eligibility(
                data_eligibility,
                data,
            ),
        }

    currency_metadata = {}
    currency_conversion_failures = []
    
    # --- START: MINIMUM HISTORY CHECK ---
    # Drop assets with insufficient data points (User Configurable)
    if min_history > 0:
        valid_counts = data.count()
        insufficient_tickers = valid_counts[valid_counts < min_history].index.tolist()
        
        if insufficient_tickers:
            _mark_data_eligibility_drop(
                data_eligibility,
                insufficient_tickers,
                reason="insufficient_history",
                stage="minimum_history",
            )
            logger.info(f"Dropped {len(insufficient_tickers)} tickers due to insufficient history (<{min_history} points): {insufficient_tickers}")
            data = data.drop(columns=insufficient_tickers)
            # Update tickers list to reflect drops (though data columns are the source of truth)
            if tickers:
                tickers = [t for t in tickers if t not in insufficient_tickers]
            
        if data.empty:
            logger.warning(f"All tickers dropped due to insufficient history (<{min_history} points).")
            return {
                "error": f"All selected tickers have less than {min_history} days of data in the selected period.",
                "data_eligibility": _finalize_data_eligibility(
                    data_eligibility,
                    data,
                ),
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
            _mark_data_eligibility_drop(
                data_eligibility,
                stale_tickers,
                reason="stale_price",
                stage="liveness",
            )
            data = data.drop(columns=stale_tickers)
            logger.info(f"Liveness Check: Dropped {len(stale_tickers)} stale tickers.")

        if data.empty:
            logger.error("No valid tickers remaining after Liveness Check.")
            return {
                "error": f"All tickers were dropped because they stopped trading before {end_date}.",
                "data_eligibility": _finalize_data_eligibility(
                    data_eligibility,
                    data,
                ),
            }
    except Exception as e:
         logger.error(f"Error during Liveness Check: {e}")
    # --- END: STRICT TIMEFRAME CHECK ---

    data, currency_metadata, currency_conversion_failures = _convert_price_data_to_usd(data, start_date, end_date)
    if currency_conversion_failures:
        _mark_data_eligibility_drop(
            data_eligibility,
            currency_conversion_failures,
            reason="fx_unavailable",
            stage="currency_conversion",
        )
        logger.warning(f"Dropped tickers with unavailable FX conversion: {currency_conversion_failures}")
        if tickers:
            tickers = [t for t in tickers if t not in currency_conversion_failures]

    if data.empty:
        logger.error("No valid tickers remaining after currency conversion.")
        return {
            "error": "Could not convert selected non-USD prices into USD.",
            "data_eligibility": _finalize_data_eligibility(
                data_eligibility,
                data,
            ),
        }

    # Sanitization: Replace infinity with NaN to prevent overflow in covariance calculation
    data = data.replace([np.inf, -np.inf], np.nan)
    pre_sanitization_columns = list(data.columns)
    data = data.dropna(axis=1, how='all')
    _mark_data_eligibility_drop(
        data_eligibility,
        [
            ticker
            for ticker in pre_sanitization_columns
            if ticker not in data.columns
        ],
        reason="invalid_price",
        stage="sanitization",
    )
    final_tickers = data.columns.tolist()
    
    def ml_callback(current, total, message):
        _weighted_progress(30, 90, current, total, message)

    mu_forecast = None
    uncertainties = None
    no_view_tickers = []
    
    if forecast_method in ["HISTORICAL", "MPT", "CLASSIC_MPT"]:
        logger.info("Using Historical CAGR for Forecasting")
        mu_forecast = _calculate_historical_cagr(data[final_tickers])
        uncertainties = pd.Series({t: DEFAULT_FORECAST_UNCERTAINTY for t in final_tickers})
    
    elif forecast_method in ["LIGHTWEIGHT", "Lightweight"]:
        logger.info(f"Using Lightweight Ensemble Forecast (Horizon={forecast_horizon})")
        forecasts = {}
        uncertainties_dict = {}
        for i, ticker in enumerate(final_tickers):
            _raise_if_cancelled(cancel_event)
            if i % 10 == 0:
                ml_callback(i, len(final_tickers), f"Lightweight forecasting {i}/{len(final_tickers)}")
            try:
                prices = data[ticker].dropna().values
                valid_prices = prices[~np.isnan(prices)]
                if len(valid_prices) > 0:
                    period_return = lightweight_ensemble_forecast(valid_prices, horizon=forecast_horizon)
                    val = _period_return_to_annual_simple_return(period_return, forecast_horizon)
                else:
                    val = None
                    no_view_tickers.append(ticker)
                forecasts[ticker] = val
                uncertainties_dict[ticker] = DEFAULT_FORECAST_UNCERTAINTY
            except Exception:
                forecasts[ticker] = None
                uncertainties_dict[ticker] = MAX_FORECAST_UNCERTAINTY
                no_view_tickers.append(ticker)
        
        mu_forecast = pd.Series(forecasts)
        uncertainties = pd.Series(uncertainties_dict).fillna(DEFAULT_FORECAST_UNCERTAINTY)
        
    elif forecast_method in ["DEEP_LEARNING", "Ensemble", "ARIMA_TRANSFORMER", "ARIMA + Transformer"]:
        logger.info(f"Using ARIMA + Transformer Forecast (Horizon={forecast_horizon})")
        mu_log_forecast, uncertainties = _call_forecast_function(
            ml_forecast_returns,
            data,
            ml_callback,
            forecast_horizon,
            cancel_event,
        )
        mu_log_forecast = pd.Series(mu_log_forecast)
        no_view_tickers = mu_log_forecast[mu_log_forecast.isna()].index.tolist()
        mu_forecast = mu_log_forecast.apply(_annual_log_return_to_simple_return)
        uncertainties = _annual_log_uncertainty_series_to_simple(mu_log_forecast, uncertainties)
        if no_view_tickers:
            uncertainties.loc[no_view_tickers] = MAX_FORECAST_UNCERTAINTY

    elif forecast_method in ["TRANSFORMER", "Transformer"]:
        logger.info(f"Using Transformer Forecast (Horizon={forecast_horizon})")
        mu_log_forecast, uncertainties = _call_forecast_function(
            transformer_forecast_returns,
            data,
            ml_callback,
            forecast_horizon,
            cancel_event,
        )
        mu_log_forecast = pd.Series(mu_log_forecast)
        no_view_tickers = mu_log_forecast[mu_log_forecast.isna()].index.tolist()
        mu_forecast = mu_log_forecast.apply(_annual_log_return_to_simple_return)
        uncertainties = _annual_log_uncertainty_series_to_simple(mu_log_forecast, uncertainties)
        if no_view_tickers:
            uncertainties.loc[no_view_tickers] = MAX_FORECAST_UNCERTAINTY
    
    else:
        logger.warning(f"Unknown forecast method '{forecast_method}', defaulting to Lightweight")
        forecasts = {}
        uncertainties_dict = {}
        for ticker in final_tickers:
            _raise_if_cancelled(cancel_event)
            prices = data[ticker].dropna().values
            valid_prices = prices[~np.isnan(prices)]
            if len(valid_prices) > 0:
                period_return = lightweight_ensemble_forecast(valid_prices, horizon=forecast_horizon)
                val = _period_return_to_annual_simple_return(period_return, forecast_horizon)
            else:
                val = None
                no_view_tickers.append(ticker)
            forecasts[ticker] = val
            uncertainties_dict[ticker] = DEFAULT_FORECAST_UNCERTAINTY
        mu_forecast = pd.Series(forecasts)
        uncertainties = pd.Series(uncertainties_dict).fillna(DEFAULT_FORECAST_UNCERTAINTY)

    # DEBUG: Check Forecasts
    if mu_forecast is not None:
         mu_forecast = pd.to_numeric(
             pd.Series(mu_forecast),
             errors="coerce",
         )
         logger.info(f"DEBUG: Forecast stats: Min={mu_forecast.min()}, Max={mu_forecast.max()}")
         if np.isinf(mu_forecast).any() or (mu_forecast.abs() > 1e6).any():
             logger.error("DEBUG: mu_forecast contains INF or huge values!")
             logger.error(f"DEBUG: Bad forecasts: {mu_forecast[np.isinf(mu_forecast) | (mu_forecast.abs() > 1e6)]}")
         # Sanitize annualized simple returns before optimization.
         mu_forecast = _normalize_expected_return_series(mu_forecast)

    forecast_tickers = [
        ticker for ticker in data.columns
        if ticker in mu_forecast.index
    ]
    _mark_data_eligibility_drop(
        data_eligibility,
        [
            ticker for ticker in data.columns
            if ticker not in forecast_tickers
        ],
        reason="forecast_output_missing",
        stage="forecast",
    )
    aligned_data = data[forecast_tickers]

    # DEBUG: Check aligned data before covariance
    logger.info(f"DEBUG: aligned_data shape: {aligned_data.shape}")
    
    # Align on the latest first-observable date and forward-fill only. Backward
    # fill would copy a future listing price into the pre-listing period.
    pre_alignment_columns = list(aligned_data.columns)
    aligned_data = _align_price_history_without_lookahead(aligned_data)
    _mark_data_eligibility_drop(
        data_eligibility,
        [
            ticker
            for ticker in pre_alignment_columns
            if ticker not in aligned_data.columns
        ],
        reason="alignment_missing",
        stage="alignment",
    )
    
    # 3. Check for specific bad values
    if np.isinf(aligned_data.values).any():
         logger.error("DEBUG: aligned_data contains INF values even after cleanup!")
         pre_inf_columns = list(aligned_data.columns)
         aligned_data = aligned_data.replace([np.inf, -np.inf], np.nan).dropna(axis=1)
         _mark_data_eligibility_drop(
             data_eligibility,
             [
                 ticker
                 for ticker in pre_inf_columns
                 if ticker not in aligned_data.columns
             ],
             reason="invalid_price",
             stage="sanitization",
         )

    # 4. Check for remaining NaNs and drop columns (tickers) that are broken
    if aligned_data.isna().any().any():
        logger.warning("DEBUG: aligned_data contains NaNs. Dropping bad columns.")
        pre_nan_columns = list(aligned_data.columns)
        aligned_data = aligned_data.dropna(axis=1)
        _mark_data_eligibility_drop(
            data_eligibility,
            [
                ticker
                for ticker in pre_nan_columns
                if ticker not in aligned_data.columns
            ],
            reason="alignment_missing",
            stage="alignment",
        )

    # Ensure no large values in aligned_data (Price data)
    cols_to_drop = []
    for col in aligned_data.columns:
        if aligned_data[col].max() > 1e8: 
            logger.warning(f"DEBUG: Dropping {col} due to suspicious price > 1e8: {aligned_data[col].max()}")
            cols_to_drop.append(col)
    
    # Re-align everything based on the survived columns
    _mark_data_eligibility_drop(
        data_eligibility,
        cols_to_drop,
        reason="invalid_price",
        stage="sanitization",
    )
    valid_columns = [c for c in aligned_data.columns if c not in cols_to_drop]
    aligned_data = aligned_data[valid_columns]
    
    # Ensure mu_forecast and uncertainties match the valid columns
    common_tickers = [t for t in mu_forecast.index if t in valid_columns]
    
    aligned_data = aligned_data[common_tickers]
    mu_forecast = mu_forecast[common_tickers]
    uncertainties = _normalize_uncertainty_series(uncertainties, common_tickers)
    no_view_tickers = [ticker for ticker in no_view_tickers if ticker in common_tickers]
    if no_view_tickers:
        uncertainties.loc[no_view_tickers] = MAX_FORECAST_UNCERTAINTY
    final_tickers = common_tickers

    if aligned_data.empty:
        logger.error("All tickers were dropped due to data quality issues.")
        return {
            "error": "No valid data remaining after sanitization.",
            "data_eligibility": _finalize_data_eligibility(
                data_eligibility,
                aligned_data,
            ),
        }

    prior_mu = _calculate_historical_cagr(aligned_data)
    if no_view_tickers:
        mu_forecast.loc[no_view_tickers] = prior_mu.reindex(no_view_tickers).fillna(0.0)
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
        "prior_mu": prior_mu,
        "S": S_hist,
        "tickers": final_tickers,
        "uncertainties": uncertainties,
        "no_view_tickers": no_view_tickers,
        "latest_prices": latest_prices,
        "price_currency": BASE_CURRENCY,
        "source_currencies": {
            ticker: currency_metadata.get(ticker, {}).get("source_currency", BASE_CURRENCY)
            for ticker in final_tickers
        },
        "data_eligibility": _finalize_data_eligibility(
            data_eligibility,
            aligned_data,
        ),
    }

def optimize_portfolio(start_date, end_date, risk_free_rate, ticker_group=None, tickers=None,
                       target_return=None, risk_tolerance=None, portfolio_id=None,
                       persist_result=False, load_if_available=False, progress_callback=None,
                       l2_gamma=0.0, max_asset_weight=0.2,
                       forecast_method="LIGHTWEIGHT", optimization_method="BL",
                       forecast_horizon=63, min_history=504, bl_tau=0.05,
                       current_weights=None, rebalance_band=None, max_turnover=None,
                       turnover_penalty=0.0, min_holding_weight=0.0,
                       cancel_event=None):
    """Optimize portfolio and optionally persist or reuse saved results."""
    _raise_if_cancelled(cancel_event)

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
        _raise_if_cancelled(cancel_event)
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
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
    except OptimizationCancelled:
        raise
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return {"error": f"Pipeline execution failed: {str(e)}"}

    if "error" in pipeline_result:
        return pipeline_result

    raw_mu = _normalize_expected_return_series(pipeline_result["mu"])
    prior_mu = _normalize_expected_return_series(
        pipeline_result.get("prior_mu", pd.Series({t: risk_free_rate for t in raw_mu.index}))
    ).reindex(raw_mu.index).fillna(risk_free_rate)
    no_view_tickers = [
        ticker for ticker in pipeline_result.get("no_view_tickers", [])
        if ticker in raw_mu.index
    ]
    if no_view_tickers:
        raw_mu.loc[no_view_tickers] = prior_mu.reindex(no_view_tickers).fillna(risk_free_rate)
    S = pipeline_result["S"]
    uncertainties = _normalize_uncertainty_series(pipeline_result.get("uncertainties"), raw_mu.index)
    if no_view_tickers:
        uncertainties.loc[no_view_tickers] = MAX_FORECAST_UNCERTAINTY
    confidence = _confidence_from_uncertainty(uncertainties)
    adjusted_mu = _shrink_expected_returns(raw_mu, prior_mu, confidence)
    mu = adjusted_mu.copy()
    final_tickers = pipeline_result["tickers"]
    latest_prices = pipeline_result.get("latest_prices", {})
    price_currency = pipeline_result.get("price_currency", BASE_CURRENCY)
    source_currencies = pipeline_result.get("source_currencies", {})
    data_eligibility = pipeline_result.get("data_eligibility")

    # 3. Apply Optimization Logic (BL or MPT)
    market_prior_source = "not_applicable"
    _raise_if_cancelled(cancel_event)
    if optimization_method in ["BL", "Black-Litterman"]:
        logger.info("Applying Black-Litterman Optimization")
        market_prior_source = "historical_return_fallback"
        try:
            # Latest market caps are not point-in-time data for historical runs.
            market_caps_compatible = (
                _latest_market_caps_are_point_in_time_compatible(end_date)
            )
            mcaps = (
                get_market_caps(list(raw_mu.index))
                if market_caps_compatible
                else {}
            )
            if not market_caps_compatible:
                logger.warning(
                    "Skipping latest market caps for historical end date %s.",
                    end_date,
                )
            
            # Delta from Market
            delta = get_market_implied_risk_aversion_cached(start_date, end_date, risk_free_rate)
            
            if mcaps:
                logger.info("Applying Black-Litterman with Market Prior")
                market_prior_source = "latest_market_caps"
                market_prior = black_litterman.market_implied_prior_returns(mcaps, delta, S, risk_free_rate=risk_free_rate)
                prior_mu = (
                    _normalize_expected_return_series(market_prior)
                    .reindex(raw_mu.index)
                    .fillna(prior_mu)
                )
                if no_view_tickers:
                    raw_mu.loc[no_view_tickers] = prior_mu.reindex(no_view_tickers).fillna(risk_free_rate)
                adjusted_mu = _shrink_expected_returns(raw_mu, prior_mu, confidence)
                
                effective_uncertainties = (
                    uncertainties.reindex(raw_mu.index).fillna(DEFAULT_FORECAST_UNCERTAINTY)
                    / confidence.reindex(raw_mu.index).fillna(MIN_FORECAST_CONFIDENCE)
                ).clip(lower=1e-4, upper=MAX_FORECAST_UNCERTAINTY)
                omega = np.diag(effective_uncertainties ** 2)
                mu = adjusted_mu.copy()
                
                bl = BlackLittermanModel(
                    S,
                    pi=prior_mu,
                    absolute_views=adjusted_mu,
                    omega=omega,
                    risk_aversion=delta,
                    tau=bl_tau,
                )
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
        _raise_if_cancelled(cancel_event)
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

        l2_gamma = max(0.0, _safe_float(l2_gamma, 0.0))
        turnover_penalty = max(0.0, _safe_float(turnover_penalty, 0.0))
        current_weight_vector = None
        if turnover_penalty > 0 and current_weights:
            current_weight_vector = _sanitize_value_series(
                current_weights,
                index=mu.index,
            )
            current_total = float(current_weight_vector.sum())
            if current_total > 0:
                current_weight_vector = current_weight_vector / current_total
            else:
                current_weight_vector = None
            if cp is None:
                logger.warning("Skipping turnover penalty because cvxpy is unavailable.")
                current_weight_vector = None

        def build_frontier():
            frontier = EfficientFrontier(
                mu,
                S,
                weight_bounds=(0, effective_max_asset_weight),
            )
            if l2_gamma > 0:
                frontier.add_objective(
                    objective_functions.L2_reg,
                    gamma=l2_gamma,
                )
            if current_weight_vector is not None:
                frontier.add_objective(
                    _turnover_penalty_objective,
                    current_weights=current_weight_vector.reindex(mu.index).fillna(0.0).values,
                    gamma=turnover_penalty,
                )
            return frontier

        # Set optimization objective
        _raise_if_cancelled(cancel_event)
        solver_objective = None
        ef = build_frontier()
        if target_return is not None:
            ef.efficient_return(target_return)
            weights = ef.clean_weights()
            solver_objective = "efficient_return"
        elif risk_tolerance is not None:
            ef.efficient_risk(risk_tolerance)
            weights = ef.clean_weights()
            solver_objective = "efficient_risk"
        elif l2_gamma > 0 or current_weight_vector is not None:
            minimum_target = max(
                float(risk_free_rate) + 1e-6,
                float(pd.Series(mu).min()),
            )
            maximum_target = float(pd.Series(mu).max())
            best = None
            if maximum_target > minimum_target:
                for candidate_target in np.linspace(
                    minimum_target,
                    maximum_target,
                    24,
                ):
                    _raise_if_cancelled(cancel_event)
                    candidate_frontier = build_frontier()
                    try:
                        candidate_frontier.efficient_return(
                            float(candidate_target)
                        )
                        candidate_weights = (
                            candidate_frontier.clean_weights()
                        )
                        candidate_performance = _performance_for_weights(
                            candidate_weights,
                            mu,
                            S,
                            risk_free_rate,
                        )
                    except (OptimizationError, ValueError):
                        continue
                    candidate_sharpe = candidate_performance[2]
                    if candidate_sharpe is not None and (
                        best is None or candidate_sharpe > best[0]
                    ):
                        best = (
                            candidate_sharpe,
                            candidate_weights,
                            candidate_frontier,
                        )
            if best is None:
                ef = build_frontier()
                ef.min_volatility()
                weights = ef.clean_weights()
                solver_objective = "regularized_min_volatility_fallback"
            else:
                _, weights, ef = best
                solver_objective = "regularized_max_sharpe_grid"
        else:
            ef.max_sharpe(risk_free_rate=risk_free_rate)
            weights = ef.clean_weights()
            solver_objective = "max_sharpe"

        thresholded_weights = apply_min_holding_threshold(weights, min_holding_weight)
        
        # Filter out assets with near-zero weight
        final_weights = {ticker: weight for ticker, weight in thresholded_weights.items() if weight > 1e-4}
        control_payload = {}
        controls_requested = rebalance_band is not None or max_turnover is not None
        if controls_requested and current_weights:
            pre_control_weights = dict(final_weights)
            target_values = pd.Series(final_weights, dtype=float)
            current_weight_series = _sanitize_value_series(
                current_weights,
                index=pd.Index(sorted(set(current_weights.keys()) | set(target_values.index)))
            )
            controlled_values, rebalance_controls = apply_trade_controls(
                current_weight_series,
                target_values,
                portfolio_value=1.0,
                rebalance_band=0.0 if rebalance_band is None else rebalance_band,
                max_turnover=max_turnover,
            )
            controlled_weights = {
                ticker: float(weight)
                for ticker, weight in controlled_values.items()
                if np.isfinite(weight) and weight > 1e-4
            }
            final_weights = controlled_weights
            control_payload = {
                "rebalance_controls": rebalance_controls,
                "pre_control_weights": pre_control_weights,
                "controlled_weights": controlled_weights,
            }

        performance = _performance_for_weights(
            final_weights,
            mu,
            S,
            risk_free_rate,
        )
        
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
            "source_currencies": {t: source_currencies.get(t, BASE_CURRENCY) for t in final_tickers},
            "raw_expected_returns": _series_to_float_dict(raw_mu),
            "prior_expected_returns": _series_to_float_dict(prior_mu),
            "adjusted_expected_returns": _series_to_float_dict(adjusted_mu),
            "optimizer_expected_returns": _series_to_float_dict(mu),
            "return_uncertainty": _series_to_float_dict(uncertainties),
            "return_confidence": _series_to_float_dict(confidence),
            "no_view_tickers": no_view_tickers,
            "failed_forecast_count": len(no_view_tickers),
            "market_prior_source": market_prior_source,
            "data_eligibility": data_eligibility,
            "optimizer_controls": {
                "solver_objective": solver_objective,
                "l2_gamma": float(l2_gamma),
                "turnover_penalty": float(turnover_penalty),
                "min_holding_weight": float(max(0.0, _safe_float(min_holding_weight, 0.0))),
            },
        }
        result_payload.update(control_payload)

        if portfolio_id and persist_result:
            _raise_if_cancelled(cancel_event)
            metadata = {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "risk_free_rate": risk_free_rate,
                "ticker_group": ticker_group,
                "tickers": tickers,
                "target_return": target_return,
                "risk_tolerance": risk_tolerance,
                "l2_gamma": l2_gamma,
                "max_asset_weight": max_asset_weight,
                "turnover_penalty": turnover_penalty,
                "min_holding_weight": min_holding_weight,
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
    except OptimizationCancelled:
        raise
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

def calculate_rebalance_orders(current_holdings, target_weights, latest_prices, cash_injection,
                               allow_fractional=True, fractional_overrides=None,
                               rebalance_band=0.0, max_turnover=None):
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
    
    all_tickers = set(current_holdings.keys()).union(target_weights.keys())
    pre_control_target_values = {
        ticker: total_target_value * float(target_weights.get(ticker, 0.0))
        for ticker in all_tickers
    }
    controls_enabled = (
        max(0.0, _safe_float(rebalance_band, 0.0)) > 0
        or max_turnover is not None
    )
    if controls_enabled:
        controlled_target_values, rebalance_controls = apply_trade_controls(
            current_values,
            pre_control_target_values,
            portfolio_value=total_target_value,
            rebalance_band=rebalance_band,
            max_turnover=max_turnover,
        )
    else:
        controlled_target_values = _sanitize_value_series(pre_control_target_values)
        rebalance_controls = None

    controlled_sum = float(controlled_target_values.sum())
    if controlled_sum > total_target_value + 1e-10 and controlled_sum > 0:
        controlled_target_values *= total_target_value / controlled_sum
        controlled_sum = float(controlled_target_values.sum())
    control_cash_reserve = max(0.0, total_target_value - controlled_sum)

    # Calculate ideal target quantities first
    ideal_quantities = {}
    all_tickers = set(all_tickers).union(controlled_target_values.index)
    for ticker in all_tickers:
        price = latest_prices.get(ticker, 0.0)
        target_value = float(controlled_target_values.get(ticker, 0.0))
        if price > 0:
            ideal_quantities[ticker] = target_value / price
            
    # Apply fractional constraints
    target_quantities = {}
    rounding_cash = 0.0
    fractional_tickers = []
    
    for ticker, ideal_qty in ideal_quantities.items():
        price = latest_prices.get(ticker, 0.0)
        if is_fractional(ticker):
            target_quantities[ticker] = ideal_qty
            if controlled_target_values.get(ticker, 0.0) > 0:
                fractional_tickers.append(ticker)
        else:
            floor_qty = math.floor(ideal_qty)
            target_quantities[ticker] = float(floor_qty)
            rounding_cash += (ideal_qty - floor_qty) * price
            
    # Redistribute only rounding cash. Cash reserved by trade controls stays in cash.
    if rounding_cash > 0.01:
        if fractional_tickers:
            frac_value_sum = sum(controlled_target_values.get(t, 0.0) for t in fractional_tickers)
            if frac_value_sum > 0:
                for ticker in fractional_tickers:
                    extra_cash = (controlled_target_values[ticker] / frac_value_sum) * rounding_cash
                    target_quantities[ticker] += extra_cash / latest_prices[ticker]
                rounding_cash = 0.0
            
        if rounding_cash > 0.01:
            sorted_tickers = sorted(
                [t for t in target_quantities.keys() if not is_fractional(t)],
                key=lambda t: controlled_target_values.get(t, 0.0),
                reverse=True
            )
            changed = True
            while changed and rounding_cash > 0.01:
                changed = False
                for ticker in sorted_tickers:
                    price = latest_prices.get(ticker, 0.0)
                    if price > 0 and price <= rounding_cash:
                        target_quantities[ticker] += 1.0
                        rounding_cash -= price
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

    result = {
        "buy_list": buy_list,
        "sell_list": sell_list,
        "target_quantities": target_quantities,
        "target_weights": target_weights,
        "total_target_value": total_target_value,
        "remaining_cash": float(control_cash_reserve + rounding_cash)
    }
    if controls_enabled:
        rebalance_controls = dict(rebalance_controls)
        rebalance_controls["control_cash_reserve"] = float(control_cash_reserve)
        result.update({
            "rebalance_controls": rebalance_controls,
            "pre_control_weights": _weights_from_values(pre_control_target_values, total_target_value),
            "controlled_weights": _weights_from_values(controlled_target_values, total_target_value),
        })
    return result

def manage_portfolio_logic(current_holdings, cash_injection, start_date, end_date, risk_free_rate, 
                           forecast_method="LIGHTWEIGHT", optimization_method="BL",
                           ticker_group=None,
                           tickers=None, allow_fractional=True, fractional_overrides=None,
                           rebalance_band=DEFAULT_REBALANCE_BAND,
                           max_turnover=DEFAULT_MAX_TURNOVER,
                           **kwargs):

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
        allow_fractional=allow_fractional,
        fractional_overrides=fractional_overrides,
        rebalance_band=rebalance_band,
        max_turnover=max_turnover,
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
