"""Walk-forward portfolio backtests for optimizer forecast methods."""

import hashlib
import json
import logging
import sqlite3
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier, risk_models, black_litterman, BlackLittermanModel
from pypfopt.exceptions import OptimizationError

from lightweight_forecast import (
    calibrated_lightweight_ensemble_forecast,
    lightweight_ensemble_forecast,
)
from portfolio_optimization import (
    DEFAULT_FORECAST_UNCERTAINTY,
    DEFAULT_MAX_TURNOVER,
    DEFAULT_REBALANCE_BAND,
    MAX_FORECAST_UNCERTAINTY,
    MIN_FORECAST_CONFIDENCE,
    _annual_log_return_to_simple_return,
    apply_min_holding_threshold,
    apply_trade_controls,
    _calculate_historical_cagr,
    _confidence_from_uncertainty,
    _dedupe_tickers,
    _historical_returns_with_hac_uncertainty,
    _james_stein_expected_returns,
    _normalize_expected_return_series,
    _normalize_uncertainty_series,
    _period_return_to_annual_simple_return,
    _shrink_expected_returns,
    forecast_single_ticker_with_arima_transformer,
    forecast_single_ticker_with_transformer,
    get_stock_data,
)
from portfolio_alpha_v2 import (
    FACTOR_NEUTRAL_TARGET_ACTIVE_SHARE,
    factor_neutral_cross_sectional_alpha,
)
from forecast_signal_research import prediction_distribution_diagnostics
from portfolio_risk_models import (
    cross_validated_minimum_variance_weights,
    equal_risk_contribution_weights,
    forecast_ensemble_minimum_variance_weights,
    hierarchical_risk_parity_weights,
    maximum_diversification_weights,
    minimum_cvar_weights,
    nested_clustered_minimum_variance_weights,
    nested_blended_minimum_variance_weights,
    online_allocator_ensemble_weights,
    resampled_minimum_variance_weights,
    regime_minimum_variance_weights,
    random_matrix_minimum_variance_weights,
    robust_minimum_variance_weights,
    scenario_robust_minimum_variance_weights,
    stability_regularized_minimum_variance_weights,
    trend_filtered_minimum_variance_weights,
    trend_filtered_risk_parity_weights,
    volatility_targeted_minimum_variance_weights,
)
from portfolio_signals import (
    ADAPTIVE_ALPHA_TARGET_ACTIVE_SHARE,
    DUAL_HORIZON_MOMENTUM_COMPONENT_WEIGHTS,
    FIFTY_TWO_WEEK_HIGH_LOOKBACK_DAYS,
    FORECAST_RANK_VIEW_UNCERTAINTY,
    HIGH_MOMENTUM_COMPONENT_WEIGHTS,
    MOMENTUM_VIEW_UNCERTAINTY,
    RISK_MOMENTUM_COMPONENT_WEIGHTS,
    SIGNAL_STACK_VIEW_UNCERTAINTY,
    SIX_MONTH_MOMENTUM_LOOKBACK_DAYS,
    adaptive_cross_sectional_alpha,
    dual_horizon_momentum_weights,
    fifty_two_week_high_score,
    high_momentum_scores,
    low_volatility_tilt,
    market_cap_weight,
    momentum_bl_views,
    momentum_12_1,
    momentum_tilt_weights,
    rank_to_unit_scores,
    risk_parity,
    risk_managed_momentum_weights,
    risk_momentum_blend_weights,
    signal_tilt_weights,
    signal_stack_bl_views,
)
from ticker_lists import get_ticker_group


logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
LIGHTWEIGHT_RANK_TARGET_ACTIVE_SHARE = 0.20
PRICE_SIGNAL_TARGET_ACTIVE_SHARE = 0.20
MINVAR_MOMENTUM_COMPONENT_WEIGHTS = {
    "min_variance": 0.50,
    "momentum_12_1_rank_tilt": 0.50,
}
DEFAULT_BACKTEST_MODELS = (
    "equal_weight",
    "min_variance",
    "risk_parity",
    "momentum_6m",
    "low_volatility",
    "market_cap_weight",
    "momentum_12_1",
    "historical_bl",
    "momentum_bl",
    "signal_stack_bl",
    "adaptive_signal_tilt",
    "historical_mpt",
    "lightweight_bl",
    "calibrated_lightweight_bl",
    "arima_transformer_rank_bl",
    "transformer_rank_bl",
    "arima_transformer_bl",
    "transformer_bl",
)
SUPPORTED_BACKTEST_MODELS = DEFAULT_BACKTEST_MODELS + (
    "factor_neutral_alpha_tilt",
    "robust_min_variance",
    "equal_risk_contribution",
    "hierarchical_risk_parity",
    "nested_clustered_minimum_variance",
    "regime_minimum_variance",
    "minimum_cvar",
    "cross_validated_min_variance",
    "forecast_ensemble_min_variance",
    "stability_regularized_min_variance",
    "nested_blended_min_variance",
    "resampled_min_variance",
    "scenario_robust_min_variance",
    "volatility_targeted_min_variance",
    "random_matrix_minimum_variance",
    "risk_managed_momentum",
    "dual_horizon_momentum",
    "trend_filtered_minimum_variance",
    "trend_filtered_risk_parity",
    "maximum_diversification",
    "online_allocator_ensemble",
    "lightweight_rank_tilt",
    "james_stein_bl",
    "hac_historical_bl",
    "momentum_12_1_rank_tilt",
    "high_momentum_rank_tilt",
    "risk_momentum_blend",
    "minvar_momentum_blend",
)

PROMOTION_BASELINE_MODELS = (
    "equal_weight",
    "historical_bl",
    "risk_parity",
    "momentum_bl",
    "momentum_6m",
    "low_volatility",
    "momentum_12_1",
)

PROMOTION_CANDIDATE_MODELS = (
    "factor_neutral_alpha_tilt",
    "adaptive_signal_tilt",
    "arima_transformer_rank_bl",
    "transformer_rank_bl",
    "arima_transformer_bl",
    "transformer_bl",
)

_FORECAST_RANK_CACHE = {}
_FORECAST_RANK_CACHE_STATS = {
    "memory_hits": 0,
    "persistent_hits": 0,
    "misses": 0,
    "writes": 0,
}
_FORECAST_RANK_PERSISTENT_CACHE = None
_FORECAST_RANK_CACHE_NAMESPACE = "default"
FORECAST_RANK_CACHE_SCHEMA_VERSION = "2026-07-23-v2-diagnostics"


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Unsupported cache value type: {type(value).__name__}")


class _PersistentForecastRankCache:
    """SQLite store that makes expensive walk-forward forecasts resumable."""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_predictions (
                cache_key TEXT PRIMARY KEY,
                key_payload TEXT NOT NULL,
                prediction_payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.commit()

    @staticmethod
    def _serialized_key(key):
        key_payload = json.dumps(
            list(key),
            ensure_ascii=True,
            separators=(",", ":"),
            default=_json_default,
        )
        return hashlib.sha256(key_payload.encode("utf-8")).hexdigest(), key_payload

    def get(self, key):
        cache_key, _ = self._serialized_key(key)
        row = self.connection.execute(
            "SELECT prediction_payload FROM forecast_predictions WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        return None if row is None else json.loads(row[0])

    def set(self, key, prediction):
        cache_key, key_payload = self._serialized_key(key)
        prediction_payload = json.dumps(
            prediction,
            ensure_ascii=True,
            separators=(",", ":"),
            default=_json_default,
        )
        self.connection.execute(
            """
            INSERT INTO forecast_predictions (cache_key, key_payload, prediction_payload)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                key_payload = excluded.key_payload,
                prediction_payload = excluded.prediction_payload
            """,
            (cache_key, key_payload, prediction_payload),
        )
        self.connection.commit()

    def count(self):
        row = self.connection.execute("SELECT COUNT(*) FROM forecast_predictions").fetchone()
        return int(row[0]) if row else 0

    def close(self):
        self.connection.close()


def configure_forecast_rank_cache(path=None, clear_memory=True, namespace="default"):
    """Enable or disable the persistent forecast cache used by research backtests."""
    global _FORECAST_RANK_CACHE_NAMESPACE, _FORECAST_RANK_PERSISTENT_CACHE
    if _FORECAST_RANK_PERSISTENT_CACHE is not None:
        _FORECAST_RANK_PERSISTENT_CACHE.close()
        _FORECAST_RANK_PERSISTENT_CACHE = None
    if clear_memory:
        _FORECAST_RANK_CACHE.clear()
    for key in _FORECAST_RANK_CACHE_STATS:
        _FORECAST_RANK_CACHE_STATS[key] = 0
    _FORECAST_RANK_CACHE_NAMESPACE = str(namespace or "default")
    if path:
        _FORECAST_RANK_PERSISTENT_CACHE = _PersistentForecastRankCache(path)
    return forecast_rank_cache_stats()


def forecast_rank_cache_stats():
    persistent_entries = (
        _FORECAST_RANK_PERSISTENT_CACHE.count()
        if _FORECAST_RANK_PERSISTENT_CACHE is not None
        else 0
    )
    return {
        **_FORECAST_RANK_CACHE_STATS,
        "memory_entries": len(_FORECAST_RANK_CACHE),
        "persistent_entries": persistent_entries,
        "persistent_path": (
            str(_FORECAST_RANK_PERSISTENT_CACHE.path)
            if _FORECAST_RANK_PERSISTENT_CACHE is not None
            else None
        ),
        "namespace": _FORECAST_RANK_CACHE_NAMESPACE,
        "schema_version": FORECAST_RANK_CACHE_SCHEMA_VERSION,
    }


def _to_float(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if np.isfinite(value) else default


def _clean_price_frame(price_data):
    if not isinstance(price_data, pd.DataFrame):
        raise TypeError("price_data must be a pandas DataFrame")
    data = price_data.copy()
    data.index = pd.to_datetime(data.index)
    data = data.sort_index()
    data = data.apply(pd.to_numeric, errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).ffill().dropna(how="all")
    data = data.dropna(axis=1, how="all")
    data = data.loc[:, data.gt(0).any(axis=0)]
    if data.empty:
        raise ValueError("No valid positive price data available for backtest")
    return data


def fetch_backtest_price_data(tickers=None, ticker_group=None, start_date=None, end_date=None):
    if tickers:
        resolved_tickers = _dedupe_tickers(tickers)
    elif ticker_group:
        resolved_tickers = get_ticker_group(ticker_group)
    else:
        raise ValueError("Either tickers or ticker_group is required")
    if not resolved_tickers:
        raise ValueError("No valid tickers supplied")
    data = get_stock_data(resolved_tickers, start_date, end_date)
    return _clean_price_frame(data)


def _relaxed_max_weight(asset_count, max_asset_weight):
    if max_asset_weight is None or max_asset_weight <= 0:
        return 1.0
    if asset_count * max_asset_weight < 1:
        return min(1.0, (1.0 / asset_count) + 1e-6)
    return max_asset_weight


def _equal_weights(tickers):
    tickers = list(tickers)
    if not tickers:
        return {}
    weight = 1.0 / len(tickers)
    return {ticker: weight for ticker in tickers}


def _normalize_weights(weights, tickers, gross_exposure=1.0):
    cleaned = {
        ticker: max(0.0, _to_float(weights.get(ticker, 0.0)))
        for ticker in tickers
    }
    total = sum(cleaned.values())
    if total <= 0:
        normalized = _equal_weights(tickers)
    else:
        normalized = {
            ticker: weight / total
            for ticker, weight in cleaned.items()
        }
    exposure = float(np.clip(gross_exposure, 0.0, 1.0))
    return {
        ticker: weight * exposure
        for ticker, weight in normalized.items()
    }


def _finite_series_dict(values):
    series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    return {str(key): float(value) for key, value in series.items()}


def _safe_rank_correlation(left, right):
    left = pd.Series(left, dtype=float).replace([np.inf, -np.inf], np.nan)
    right = pd.Series(right, dtype=float).reindex(left.index).replace([np.inf, -np.inf], np.nan)
    valid = left.notna() & right.notna()
    if int(valid.sum()) < 2 or left[valid].nunique() < 2 or right[valid].nunique() < 2:
        return None
    value = left[valid].corr(right[valid], method="spearman")
    return None if pd.isna(value) or not np.isfinite(value) else float(value)


def _top_bottom_spread(signal_scores, realized_returns):
    scores = pd.Series(signal_scores, dtype=float).replace([np.inf, -np.inf], np.nan)
    realized = pd.Series(realized_returns, dtype=float).reindex(scores.index)
    valid = scores.notna() & realized.replace([np.inf, -np.inf], np.nan).notna()
    count = int(valid.sum())
    if count < 2 or scores[valid].nunique() < 2:
        return None
    tail_count = max(1, count // 3)
    ordered = scores[valid].sort_values()
    bottom = ordered.index[:tail_count]
    top = ordered.index[-tail_count:]
    return float(realized.loc[top].mean() - realized.loc[bottom].mean())


def _weight_diagnostics(weights, signal_scores, covariance):
    weights = pd.Series(weights, dtype=float)
    if weights.empty:
        return {}
    equal = pd.Series(1.0 / len(weights), index=weights.index, dtype=float)
    l1_distance = float((weights - equal).abs().sum())
    diagnostics = {
        "equal_weight_l1_distance": l1_distance,
        "active_share": float(0.5 * l1_distance),
        "concentration_hhi": float((weights ** 2).sum()),
        "signal_weight_rank_correlation": _safe_rank_correlation(signal_scores, weights),
    }
    try:
        aligned_covariance = pd.DataFrame(covariance).reindex(index=weights.index, columns=weights.index)
        variance = float(weights.values @ aligned_covariance.values @ weights.values)
        diagnostics["predicted_annual_volatility"] = float(np.sqrt(max(0.0, variance)))
    except Exception:
        diagnostics["predicted_annual_volatility"] = None
    return diagnostics


def _safe_covariance(train_prices):
    try:
        return risk_models.CovarianceShrinkage(train_prices).ledoit_wolf()
    except Exception as exc:
        logger.warning("Ledoit-Wolf covariance failed, using sample covariance: %s", exc)
        returns = train_prices.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        if returns.empty:
            tickers = list(train_prices.columns)
            return pd.DataFrame(np.eye(len(tickers)) * 0.05, index=tickers, columns=tickers)
        return returns.cov() * TRADING_DAYS_PER_YEAR


def _efficient_frontier_weights(mu, covariance, max_asset_weight, objective, risk_free_rate):
    tickers = list(mu.index)
    cap = _relaxed_max_weight(len(tickers), max_asset_weight)
    try:
        ef = EfficientFrontier(mu, covariance, weight_bounds=(0, cap))
        if objective == "min_volatility":
            ef.min_volatility()
        else:
            ef.max_sharpe(risk_free_rate=risk_free_rate)
        return _normalize_weights(ef.clean_weights(), tickers)
    except (OptimizationError, ValueError, Exception) as exc:
        logger.warning("Efficient frontier failed for %s: %s", objective, exc)
        if objective != "min_volatility":
            return _efficient_frontier_weights(
                pd.Series(0.0, index=tickers),
                covariance,
                max_asset_weight,
                "min_volatility",
                risk_free_rate,
            )
        return _equal_weights(tickers)


def _views_from_rank_scores(train_prices, scores, uncertainty, view_strength=0.03, max_view_shift=0.06):
    tickers = list(train_prices.columns)
    prior = _calculate_historical_cagr(train_prices).reindex(tickers).fillna(0.0)
    scores = pd.Series(scores, dtype=float).reindex(tickers).replace([np.inf, -np.inf], np.nan)
    delta = (scores * abs(float(view_strength))).clip(
        lower=-abs(float(max_view_shift)),
        upper=abs(float(max_view_shift)),
    )
    views = (prior + delta.fillna(0.0)).clip(lower=-0.99, upper=10.0)
    views.loc[scores.isna()] = np.nan
    uncertainties = pd.Series(
        {
            ticker: MAX_FORECAST_UNCERTAINTY if pd.isna(scores.get(ticker)) else uncertainty
            for ticker in tickers
        },
        dtype=float,
    )
    return views, _normalize_uncertainty_series(uncertainties, tickers), int(scores.isna().sum())


def _forecast_rank_cache_key(ticker, prices, method, horizon):
    series = pd.Series(prices, dtype=float).dropna()
    if series.empty:
        digest = "empty"
        first_date = last_date = "NA"
    else:
        first_date = str(series.index[0])
        last_date = str(series.index[-1])
        hashed = pd.util.hash_pandas_object(series, index=True).values
        digest = hashlib.blake2b(hashed.tobytes(), digest_size=16).hexdigest()
    return (
        FORECAST_RANK_CACHE_SCHEMA_VERSION,
        _FORECAST_RANK_CACHE_NAMESPACE,
        str(method),
        str(ticker),
        int(horizon),
        int(len(series)),
        first_date,
        last_date,
        digest,
    )


def _cached_forecast_rank_prediction(ticker, prices, method, horizon, predictor):
    key = _forecast_rank_cache_key(ticker, prices, method, horizon)
    if key in _FORECAST_RANK_CACHE:
        _FORECAST_RANK_CACHE_STATS["memory_hits"] += 1
    else:
        persistent_prediction = None
        if _FORECAST_RANK_PERSISTENT_CACHE is not None:
            persistent_prediction = _FORECAST_RANK_PERSISTENT_CACHE.get(key)
        if persistent_prediction is not None:
            _FORECAST_RANK_CACHE_STATS["persistent_hits"] += 1
            _FORECAST_RANK_CACHE[key] = persistent_prediction
        else:
            _FORECAST_RANK_CACHE_STATS["misses"] += 1
            prediction = predictor(ticker, prices, horizon=horizon)
            _FORECAST_RANK_CACHE[key] = prediction
            if _FORECAST_RANK_PERSISTENT_CACHE is not None:
                _FORECAST_RANK_PERSISTENT_CACHE.set(key, prediction)
                _FORECAST_RANK_CACHE_STATS["writes"] += 1
    prediction = _FORECAST_RANK_CACHE[key]
    return dict(prediction) if isinstance(prediction, dict) else prediction


def _forecast_rank_views(train_prices, method, forecast_horizon):
    tickers = list(train_prices.columns)
    forecasts = {}
    uncertainties = {}
    prediction_diagnostics = []
    failed = 0
    predictor = (
        forecast_single_ticker_with_arima_transformer
        if method == "arima_transformer_rank"
        else forecast_single_ticker_with_transformer
    )

    for ticker in tickers:
        prices = train_prices[ticker].dropna()
        prediction = _cached_forecast_rank_prediction(
            ticker,
            prices,
            method,
            forecast_horizon,
            predictor,
        )
        prediction_diagnostics.append(
            prediction if isinstance(prediction, dict) else {}
        )
        annual_log_return = prediction.get("expected_return") if isinstance(prediction, dict) else None
        if annual_log_return is None:
            forecasts[ticker] = np.nan
            uncertainties[ticker] = MAX_FORECAST_UNCERTAINTY
            failed += 1
            continue
        forecasts[ticker] = _annual_log_return_to_simple_return(annual_log_return)
        uncertainties[ticker] = max(
            FORECAST_RANK_VIEW_UNCERTAINTY,
            _to_float(prediction.get("uncertainty"), FORECAST_RANK_VIEW_UNCERTAINTY),
        )

    scores = rank_to_unit_scores(pd.Series(forecasts).reindex(tickers), higher_is_better=True)
    views, rank_uncertainties, rank_failed = _views_from_rank_scores(
        train_prices,
        scores,
        uncertainty=FORECAST_RANK_VIEW_UNCERTAINTY,
        view_strength=0.025,
        max_view_shift=0.05,
    )
    uncertainty_series = _normalize_uncertainty_series(pd.Series(uncertainties), tickers)
    uncertainty_series = pd.concat([uncertainty_series, rank_uncertainties], axis=1).max(axis=1)
    uncertainty_series.loc[views.isna()] = MAX_FORECAST_UNCERTAINTY
    return views, uncertainty_series, max(failed, rank_failed), {
        "forecast_rank_scores": {
            ticker: float(score)
            for ticker, score in scores.dropna().items()
        },
        "signal_scores": _finite_series_dict(scores),
        "raw_forecasts": _finite_series_dict(forecasts),
        "forecast_uncertainties": _finite_series_dict(uncertainty_series),
        "forecast_distribution_diagnostics": (
            prediction_distribution_diagnostics(prediction_diagnostics)
        ),
    }


def _forecast_views(train_prices, method, forecast_horizon):
    tickers = list(train_prices.columns)
    views = {}
    uncertainties = {}
    calibration_diagnostics = {}
    failed = 0

    if method == "momentum":
        prior = _calculate_historical_cagr(train_prices)
        momentum_views = momentum_bl_views(train_prices, prior_returns=prior)
        failed = int(momentum_views.isna().sum())
        uncertainties = {
            ticker: (
                MAX_FORECAST_UNCERTAINTY
                if pd.isna(momentum_views.get(ticker))
                else MOMENTUM_VIEW_UNCERTAINTY
            )
            for ticker in tickers
        }
        views = momentum_views.reindex(tickers)
        uncertainties = _normalize_uncertainty_series(pd.Series(uncertainties), tickers)
        return views, uncertainties, failed, {}

    if method == "signal_stack":
        prior = _calculate_historical_cagr(train_prices)
        views = signal_stack_bl_views(train_prices, prior_returns=prior)
        failed = int(views.isna().sum())
        uncertainties = {
            ticker: (
                MAX_FORECAST_UNCERTAINTY
                if pd.isna(views.get(ticker))
                else SIGNAL_STACK_VIEW_UNCERTAINTY
            )
            for ticker in tickers
        }
        uncertainties = _normalize_uncertainty_series(pd.Series(uncertainties), tickers)
        return views.reindex(tickers), uncertainties, failed, {}

    if method == "james_stein":
        views, estimator_diagnostics = (
            _james_stein_expected_returns(train_prices)
        )
        uncertainties = _normalize_uncertainty_series(
            pd.Series(
                DEFAULT_FORECAST_UNCERTAINTY,
                index=tickers,
                dtype=float,
            ),
            tickers,
        )
        return (
            views.reindex(tickers),
            uncertainties,
            0,
            {"mean_estimator": estimator_diagnostics},
        )

    if method == "hac_historical":
        views, uncertainties, estimator_diagnostics = (
            _historical_returns_with_hac_uncertainty(train_prices)
        )
        return (
            views.reindex(tickers),
            uncertainties.reindex(tickers),
            0,
            {"uncertainty_estimator": estimator_diagnostics},
        )

    if method in ("arima_transformer_rank", "transformer_rank"):
        return _forecast_rank_views(train_prices, method, forecast_horizon)

    for ticker in tickers:
        prices = train_prices[ticker].dropna()
        if method == "historical":
            continue
        if method == "calibrated_lightweight":
            try:
                prediction = calibrated_lightweight_ensemble_forecast(
                    prices.values,
                    horizon=forecast_horizon,
                )
                views[ticker] = prediction["annual_expected_return"]
                uncertainties[ticker] = prediction["annual_uncertainty"]
                calibration_diagnostics[ticker] = {
                    key: value
                    for key, value in prediction["diagnostics"].items()
                    if key != "calibration_rows"
                }
            except (TypeError, ValueError, FloatingPointError):
                views[ticker] = np.nan
                uncertainties[ticker] = MAX_FORECAST_UNCERTAINTY
                failed += 1
            continue
        if method == "lightweight":
            period_return = lightweight_ensemble_forecast(prices.values, horizon=forecast_horizon)
            views[ticker] = _period_return_to_annual_simple_return(period_return, forecast_horizon)
            uncertainties[ticker] = DEFAULT_FORECAST_UNCERTAINTY
            continue

        predictor = (
            forecast_single_ticker_with_arima_transformer
            if method == "arima_transformer"
            else forecast_single_ticker_with_transformer
        )
        prediction = predictor(ticker, prices, horizon=forecast_horizon)
        annual_log_return = prediction.get("expected_return") if isinstance(prediction, dict) else None
        if annual_log_return is None:
            views[ticker] = np.nan
            uncertainties[ticker] = MAX_FORECAST_UNCERTAINTY
            failed += 1
            continue
        views[ticker] = _annual_log_return_to_simple_return(annual_log_return)
        uncertainties[ticker] = _to_float(prediction.get("uncertainty"), DEFAULT_FORECAST_UNCERTAINTY)

    if method == "historical":
        views = _calculate_historical_cagr(train_prices).to_dict()
        uncertainties = {ticker: DEFAULT_FORECAST_UNCERTAINTY for ticker in tickers}

    views = pd.Series(views).reindex(tickers)
    uncertainties = _normalize_uncertainty_series(pd.Series(uncertainties), tickers)
    return views, uncertainties, failed, (
        {
            "lightweight_uncertainty_calibration": (
                calibration_diagnostics
            ),
        }
        if method == "calibrated_lightweight"
        else {}
    )


def _black_litterman_weights(train_prices, view_method, forecast_horizon, max_asset_weight, risk_free_rate):
    tickers = list(train_prices.columns)
    covariance = _safe_covariance(train_prices)
    views, uncertainties, failed, forecast_diagnostics = _forecast_views(
        train_prices,
        view_method,
        forecast_horizon,
    )
    prior = _calculate_historical_cagr(train_prices)

    try:
        equal_caps = {ticker: 1.0 for ticker in tickers}
        prior = black_litterman.market_implied_prior_returns(
            equal_caps,
            2.5,
            covariance,
            risk_free_rate=risk_free_rate,
        )
        prior = _normalize_expected_return_series(prior).reindex(tickers).fillna(0.0)
    except Exception as exc:
        logger.warning("Backtest BL prior failed, using historical CAGR prior: %s", exc)

    raw_views = pd.Series(views, dtype=float).reindex(tickers)
    no_view_mask = raw_views.isna()
    views = _normalize_expected_return_series(views)
    views.loc[no_view_mask] = prior.reindex(views.index).loc[no_view_mask].fillna(0.0)
    uncertainties.loc[no_view_mask] = MAX_FORECAST_UNCERTAINTY
    confidence = _confidence_from_uncertainty(uncertainties)
    adjusted_views = _shrink_expected_returns(views, prior, confidence)

    try:
        effective_uncertainties = (uncertainties / confidence.clip(lower=MIN_FORECAST_CONFIDENCE)).clip(
            lower=1e-4,
            upper=MAX_FORECAST_UNCERTAINTY,
        )
        bl = BlackLittermanModel(
            covariance,
            pi=prior,
            absolute_views=adjusted_views,
            omega=np.diag(effective_uncertainties ** 2),
            risk_aversion=2.5,
            tau=0.05,
        )
        mu = bl.bl_returns()
        covariance = bl.bl_cov()
    except Exception as exc:
        logger.warning("Backtest BL failed, using confidence-adjusted views: %s", exc)
        mu = adjusted_views

    weights = _efficient_frontier_weights(mu, covariance, max_asset_weight, "max_sharpe", risk_free_rate)
    finite_confidence = confidence.replace([np.inf, -np.inf], np.nan).dropna()
    avg_confidence = None if finite_confidence.empty else float(finite_confidence.mean())
    raw_shift = (raw_views - prior).abs().replace([np.inf, -np.inf], np.nan).dropna()
    adjusted_shift = (adjusted_views - prior).abs().replace([np.inf, -np.inf], np.nan).dropna()
    raw_shift_mean = None if raw_shift.empty else float(raw_shift.mean())
    adjusted_shift_mean = None if adjusted_shift.empty else float(adjusted_shift.mean())
    view_retention = (
        None
        if raw_shift_mean is None or raw_shift_mean <= 0 or adjusted_shift_mean is None
        else float(adjusted_shift_mean / raw_shift_mean)
    )
    return weights, {
        "failed_forecast_count": int(failed),
        "avg_forecast_confidence": avg_confidence,
        "prior_returns": _finite_series_dict(prior),
        "raw_views": _finite_series_dict(raw_views),
        "signal_scores": _finite_series_dict(raw_views),
        "adjusted_views": _finite_series_dict(adjusted_views),
        "posterior_returns": _finite_series_dict(mu),
        "view_signal_retention": view_retention,
        **forecast_diagnostics,
    }


def _lightweight_rank_tilt_weights(
    train_prices,
    forecast_horizon,
    max_asset_weight,
):
    """Map lightweight forecast ranks to a fixed active-share tilt."""
    tickers = list(train_prices.columns)
    forecasts = {}
    failed = 0
    for ticker in tickers:
        prices = train_prices[ticker].dropna()
        try:
            period_return = lightweight_ensemble_forecast(
                prices.values,
                horizon=forecast_horizon,
            )
            forecasts[ticker] = _period_return_to_annual_simple_return(
                period_return,
                forecast_horizon,
            )
        except (TypeError, ValueError, FloatingPointError):
            forecasts[ticker] = np.nan
            failed += 1
    scores = rank_to_unit_scores(
        pd.Series(forecasts).reindex(tickers),
        higher_is_better=True,
    )
    weights = signal_tilt_weights(
        scores,
        max_asset_weight=max_asset_weight,
        target_active_share=LIGHTWEIGHT_RANK_TARGET_ACTIVE_SHARE,
    )
    return weights.to_dict(), {
        "failed_forecast_count": int(failed),
        "avg_forecast_confidence": None,
        "signal_scores": _finite_series_dict(scores),
        "forecast_rank_scores": _finite_series_dict(scores),
        "raw_forecasts": _finite_series_dict(forecasts),
        "construction_method": "equal_weight_active_share_tilt",
        "target_active_share": (
            LIGHTWEIGHT_RANK_TARGET_ACTIVE_SHARE
        ),
    }


def _price_signal_rank_tilt_weights(
    train_prices,
    mode,
    max_asset_weight,
):
    """Construct identical rank tilts for raw and 52-week-high momentum."""
    tickers = list(train_prices.columns)
    momentum_scores = momentum_12_1(
        train_prices
    ).reindex(tickers)
    high_scores = fifty_two_week_high_score(
        train_prices,
        lookback=FIFTY_TWO_WEEK_HIGH_LOOKBACK_DAYS,
    ).reindex(tickers)
    if mode == "momentum_12_1":
        scores = momentum_scores
        component_weights = {"momentum_12_1": 1.0}
    elif mode == "high_momentum":
        scores = high_momentum_scores(
            train_prices
        ).reindex(tickers)
        component_weights = dict(
            HIGH_MOMENTUM_COMPONENT_WEIGHTS
        )
    else:
        raise ValueError(f"Unsupported price signal mode: {mode}")

    weights = signal_tilt_weights(
        scores,
        max_asset_weight=max_asset_weight,
        target_active_share=PRICE_SIGNAL_TARGET_ACTIVE_SHARE,
    )
    return weights.to_dict(), {
        "failed_forecast_count": int(scores.isna().sum()),
        "avg_forecast_confidence": None,
        "signal_scores": _finite_series_dict(scores),
        "alpha_component_scores": {
            "momentum_12_1": _finite_series_dict(
                momentum_scores
            ),
            "fifty_two_week_high": _finite_series_dict(
                high_scores
            ),
        },
        "alpha_component_weights": component_weights,
        "construction_method": (
            "equal_weight_active_share_rank_tilt"
        ),
        "target_active_share": PRICE_SIGNAL_TARGET_ACTIVE_SHARE,
    }


def _model_weights(model_name, train_prices, forecast_horizon, max_asset_weight, risk_free_rate,
                   market_caps=None, point_in_time_features=None,
                   previous_target_weights=None):
    tickers = list(train_prices.columns)
    if model_name == "equal_weight":
        return _equal_weights(tickers), {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    covariance = _safe_covariance(train_prices)
    if model_name == "min_variance":
        weights = _efficient_frontier_weights(
            pd.Series(0.0, index=tickers),
            covariance,
            max_asset_weight,
            "min_volatility",
            risk_free_rate,
        )
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    if model_name == "risk_parity":
        weights = risk_parity(train_prices, max_asset_weight=max_asset_weight).to_dict()
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    if model_name == "robust_min_variance":
        weights, risk_diagnostics = robust_minimum_variance_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "maximum_diversification":
        weights, risk_diagnostics = maximum_diversification_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "cross_validated_min_variance":
        weights, risk_diagnostics = cross_validated_minimum_variance_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "forecast_ensemble_min_variance":
        weights, risk_diagnostics = (
            forecast_ensemble_minimum_variance_weights(
                train_prices,
                max_asset_weight=max_asset_weight,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "stability_regularized_min_variance":
        weights, risk_diagnostics = (
            stability_regularized_minimum_variance_weights(
                train_prices,
                previous_weights=previous_target_weights,
                max_asset_weight=max_asset_weight,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "nested_blended_min_variance":
        weights, risk_diagnostics = (
            nested_blended_minimum_variance_weights(
                train_prices,
                max_asset_weight=max_asset_weight,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "online_allocator_ensemble":
        weights, risk_diagnostics = (
            online_allocator_ensemble_weights(
                train_prices,
                max_asset_weight=max_asset_weight,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "resampled_min_variance":
        weights, risk_diagnostics = resampled_minimum_variance_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "scenario_robust_min_variance":
        weights, risk_diagnostics = (
            scenario_robust_minimum_variance_weights(
                train_prices,
                max_asset_weight=max_asset_weight,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "volatility_targeted_min_variance":
        weights, risk_diagnostics = (
            volatility_targeted_minimum_variance_weights(
                train_prices,
                max_asset_weight=max_asset_weight,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
            "allow_cash_reserve": True,
            "target_risky_exposure": risk_diagnostics[
                "target_risky_exposure"
            ],
            "target_cash_weight": risk_diagnostics[
                "target_cash_weight"
            ],
        }

    if model_name == "trend_filtered_minimum_variance":
        weights, risk_diagnostics = (
            trend_filtered_minimum_variance_weights(
                train_prices,
                max_asset_weight=max_asset_weight,
                trend_lookback=252,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
            "allow_cash_reserve": True,
            "target_risky_exposure": risk_diagnostics[
                "target_risky_exposure"
            ],
            "target_cash_weight": risk_diagnostics[
                "target_cash_weight"
            ],
        }

    if model_name == "trend_filtered_risk_parity":
        weights, risk_diagnostics = trend_filtered_risk_parity_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
            trend_lookback=252,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
            "allow_cash_reserve": True,
            "target_risky_exposure": risk_diagnostics[
                "target_risky_exposure"
            ],
            "target_cash_weight": risk_diagnostics[
                "target_cash_weight"
            ],
        }

    if model_name == "random_matrix_minimum_variance":
        weights, risk_diagnostics = (
            random_matrix_minimum_variance_weights(
                train_prices,
                max_asset_weight=max_asset_weight,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "equal_risk_contribution":
        weights, risk_diagnostics = equal_risk_contribution_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "hierarchical_risk_parity":
        weights, risk_diagnostics = hierarchical_risk_parity_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "nested_clustered_minimum_variance":
        weights, risk_diagnostics = (
            nested_clustered_minimum_variance_weights(
                train_prices,
                max_asset_weight=max_asset_weight,
            )
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "regime_minimum_variance":
        weights, risk_diagnostics = regime_minimum_variance_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "minimum_cvar":
        weights, risk_diagnostics = minimum_cvar_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "risk_model": risk_diagnostics,
        }

    if model_name == "momentum_6m":
        weights = momentum_tilt_weights(
            train_prices,
            lookback=SIX_MONTH_MOMENTUM_LOOKBACK_DAYS,
            skip=0,
            max_asset_weight=max_asset_weight,
        ).to_dict()
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    if model_name == "dual_horizon_momentum":
        weights = dual_horizon_momentum_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "construction_method": "fixed_dual_horizon_momentum_rank_blend",
            "component_weights": dict(
                DUAL_HORIZON_MOMENTUM_COMPONENT_WEIGHTS
            ),
        }

    if model_name == "risk_managed_momentum":
        scores = rank_to_unit_scores(
            (
                train_prices.iloc[-1]
                / train_prices.iloc[
                    -min(SIX_MONTH_MOMENTUM_LOOKBACK_DAYS, len(train_prices))
                ]
                - 1.0
            ),
            higher_is_better=True,
        )
        weights = risk_managed_momentum_weights(
            train_prices,
            momentum_lookback=SIX_MONTH_MOMENTUM_LOOKBACK_DAYS,
            max_asset_weight=max_asset_weight,
        )
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "signal_scores": _finite_series_dict(scores),
            "construction_method": "inverse_volatility_scaled_6m_momentum",
        }

    if model_name == "low_volatility":
        weights = low_volatility_tilt(train_prices, max_asset_weight=max_asset_weight).to_dict()
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    if model_name == "market_cap_weight":
        weights = market_cap_weight(
            market_caps,
            tickers=tickers,
            max_asset_weight=max_asset_weight,
        )
        if weights.empty or float(weights.fillna(0.0).sum()) <= 0:
            return _equal_weights(tickers), {
                "failed_forecast_count": 0,
                "avg_forecast_confidence": None,
                "market_caps_available": False,
            }
        return weights.to_dict(), {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
            "market_caps_available": True,
        }

    if model_name == "momentum_12_1":
        weights = momentum_tilt_weights(
            train_prices,
            lookback=252,
            skip=21,
            max_asset_weight=max_asset_weight,
        ).to_dict()
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    if model_name == "momentum_12_1_rank_tilt":
        return _price_signal_rank_tilt_weights(
            train_prices,
            "momentum_12_1",
            max_asset_weight,
        )

    if model_name == "high_momentum_rank_tilt":
        return _price_signal_rank_tilt_weights(
            train_prices,
            "high_momentum",
            max_asset_weight,
        )

    if model_name == "risk_momentum_blend":
        scores = momentum_12_1(train_prices).reindex(tickers)
        weights = risk_momentum_blend_weights(
            train_prices,
            max_asset_weight=max_asset_weight,
            target_active_share=PRICE_SIGNAL_TARGET_ACTIVE_SHARE,
        )
        return weights.to_dict(), {
            "failed_forecast_count": int(scores.isna().sum()),
            "avg_forecast_confidence": None,
            "signal_scores": _finite_series_dict(scores),
            "alpha_component_weights": dict(
                RISK_MOMENTUM_COMPONENT_WEIGHTS
            ),
            "construction_method": (
                "fixed_risk_parity_momentum_rank_tilt_blend"
            ),
            "target_active_share": (
                PRICE_SIGNAL_TARGET_ACTIVE_SHARE
            ),
        }

    if model_name == "minvar_momentum_blend":
        scores = momentum_12_1(train_prices).reindex(tickers)
        minimum_variance = pd.Series(
            _efficient_frontier_weights(
                pd.Series(0.0, index=tickers),
                covariance,
                max_asset_weight,
                "min_volatility",
                risk_free_rate,
            ),
            dtype=float,
        ).reindex(tickers).fillna(0.0)
        momentum_weights, _ = _price_signal_rank_tilt_weights(
            train_prices,
            "momentum_12_1",
            max_asset_weight,
        )
        momentum_weights = pd.Series(
            momentum_weights,
            dtype=float,
        ).reindex(tickers).fillna(0.0)
        weights = (
            MINVAR_MOMENTUM_COMPONENT_WEIGHTS["min_variance"]
            * minimum_variance
            + MINVAR_MOMENTUM_COMPONENT_WEIGHTS[
                "momentum_12_1_rank_tilt"
            ]
            * momentum_weights
        )
        weights = _normalize_weights(weights, tickers)
        return weights, {
            "failed_forecast_count": int(scores.isna().sum()),
            "avg_forecast_confidence": None,
            "signal_scores": _finite_series_dict(scores),
            "alpha_component_weights": dict(
                MINVAR_MOMENTUM_COMPONENT_WEIGHTS
            ),
            "construction_method": (
                "fixed_minimum_variance_momentum_rank_tilt_blend"
            ),
            "target_active_share": (
                PRICE_SIGNAL_TARGET_ACTIVE_SHARE
            ),
        }

    if model_name == "adaptive_signal_tilt":
        scores, alpha_diagnostics = adaptive_cross_sectional_alpha(
            train_prices,
            horizon=forecast_horizon,
        )
        weights = signal_tilt_weights(
            scores,
            max_asset_weight=max_asset_weight,
            target_active_share=ADAPTIVE_ALPHA_TARGET_ACTIVE_SHARE,
        )
        coverage_count = int(alpha_diagnostics.get("coverage_count", 0))
        calibration = alpha_diagnostics.get("calibration", {})
        calibrated_ics = [
            component.get("mean_rank_ic")
            for component in calibration.get("components", {}).values()
            if component.get("mean_rank_ic") is not None
        ]
        calibrated_confidence = (
            None
            if not calibrated_ics
            else float(np.clip(max(0.0, np.mean(calibrated_ics)), 0.0, 1.0))
        )
        return weights.to_dict(), {
            "failed_forecast_count": max(0, len(tickers) - coverage_count),
            "avg_forecast_confidence": calibrated_confidence,
            "signal_scores": _finite_series_dict(scores),
            "alpha_component_scores": alpha_diagnostics.get("component_scores", {}),
            "alpha_component_weights": alpha_diagnostics.get("component_weights", {}),
            "alpha_calibration": calibration,
            "signal_coverage_count": coverage_count,
            "signal_coverage_rate": alpha_diagnostics.get("coverage_rate", 0.0),
            "construction_method": "equal_weight_active_share_tilt",
            "target_active_share": ADAPTIVE_ALPHA_TARGET_ACTIVE_SHARE,
        }

    if model_name == "factor_neutral_alpha_tilt":
        if point_in_time_features is None:
            raise ValueError(
                "factor_neutral_alpha_tilt requires point_in_time_features"
            )
        scores, alpha_diagnostics = factor_neutral_cross_sectional_alpha(
            train_prices,
            point_in_time_features,
            horizon=forecast_horizon,
        )
        weights = signal_tilt_weights(
            scores,
            max_asset_weight=max_asset_weight,
            target_active_share=FACTOR_NEUTRAL_TARGET_ACTIVE_SHARE,
        )
        coverage_count = int(alpha_diagnostics.get("coverage_count", 0))
        calibration = alpha_diagnostics.get("calibration", {})
        coefficients = calibration.get("coefficients", {})
        coefficient_strength = (
            None
            if not coefficients
            else float(np.mean(np.abs(list(coefficients.values()))))
        )
        return weights.to_dict(), {
            "failed_forecast_count": max(0, len(tickers) - coverage_count),
            "avg_forecast_confidence": coefficient_strength,
            "signal_scores": _finite_series_dict(scores),
            "alpha_component_scores": alpha_diagnostics.get("component_scores", {}),
            "alpha_component_weights": alpha_diagnostics.get("component_weights", {}),
            "alpha_calibration": calibration,
            "signal_coverage_count": coverage_count,
            "signal_coverage_rate": alpha_diagnostics.get("coverage_rate", 0.0),
            "construction_method": "equal_weight_active_share_tilt",
            "target_active_share": FACTOR_NEUTRAL_TARGET_ACTIVE_SHARE,
            "factor_neutral_target": True,
            "point_in_time_signal_as_of_date": alpha_diagnostics.get(
                "signal_as_of_date"
            ),
            "point_in_time_latest_available_date": alpha_diagnostics.get(
                "latest_available_date"
            ),
        }

    if model_name == "historical_mpt":
        mu = _calculate_historical_cagr(train_prices)
        weights = _efficient_frontier_weights(mu, covariance, max_asset_weight, "max_sharpe", risk_free_rate)
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    if model_name == "lightweight_rank_tilt":
        return _lightweight_rank_tilt_weights(
            train_prices,
            forecast_horizon,
            max_asset_weight,
        )

    bl_methods = {
        "historical_bl": "historical",
        "james_stein_bl": "james_stein",
        "hac_historical_bl": "hac_historical",
        "momentum_bl": "momentum",
        "signal_stack_bl": "signal_stack",
        "lightweight_bl": "lightweight",
        "calibrated_lightweight_bl": "calibrated_lightweight",
        "arima_transformer_rank_bl": "arima_transformer_rank",
        "transformer_rank_bl": "transformer_rank",
        "arima_transformer_bl": "arima_transformer",
        "transformer_bl": "transformer",
    }
    if model_name in bl_methods:
        return _black_litterman_weights(
            train_prices,
            bl_methods[model_name],
            forecast_horizon,
            max_asset_weight,
            risk_free_rate,
        )

    raise ValueError(f"Unsupported backtest model: {model_name}")


def calculate_turnover_and_cost(current_values, target_weights, portfolio_value, transaction_cost_bps):
    if portfolio_value <= 0:
        return 0.0, 0.0
    tickers = sorted(set(current_values.keys()) | set(target_weights.keys()))
    traded_notional = 0.0
    for ticker in tickers:
        current_value = _to_float(current_values.get(ticker), 0.0)
        target_value = portfolio_value * _to_float(target_weights.get(ticker), 0.0)
        traded_notional += abs(target_value - current_value)
    turnover = traded_notional / portfolio_value
    cost = traded_notional * (_to_float(transaction_cost_bps, 0.0) / 10000.0)
    return float(turnover), float(cost)


def _cash_value_path(
    initial_cash,
    dates,
    risk_free_rate,
    risk_free_daily_returns=None,
):
    """Accrue residual cash using only rates available on each date."""
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    if len(index) == 0:
        return pd.Series(dtype=float, index=index)
    annual_rate = _to_float(risk_free_rate, 0.0)
    daily_fallback = (
        float((1.0 + annual_rate) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0)
        if annual_rate > -1.0
        else -0.999999
    )
    rates = pd.Series(daily_fallback, index=index, dtype=float)
    if risk_free_daily_returns is not None:
        source = pd.Series(
            risk_free_daily_returns,
            dtype=float,
        ).copy()
        source.index = pd.to_datetime(source.index)
        if source.index.tz is not None:
            source.index = source.index.tz_localize(None)
        target_index = (
            index.tz_localize(None)
            if index.tz is not None
            else index
        )
        source = (
            source.sort_index()
            .replace([np.inf, -np.inf], np.nan)
        )
        aligned = source.reindex(target_index).ffill()
        rates = aligned.fillna(daily_fallback)
        rates.index = index
    rates = rates.clip(lower=-0.999999)
    rates.iloc[0] = 0.0
    return float(max(0.0, initial_cash)) * (1.0 + rates).cumprod()


def _portfolio_metrics(
    value_timeline,
    risk_free_rate,
    risk_free_daily_returns=None,
):
    empty_metrics = {
        "cagr": 0.0,
        "annual_volatility": 0.0,
        "annualized_excess_return": 0.0,
        "annualized_risk_free_return": float(risk_free_rate),
        "risk_free_observation_coverage": 0.0,
        "annual_downside_deviation": 0.0,
        "sharpe": None,
        "sortino": None,
        "calmar": None,
        "omega": None,
        "daily_var_95": None,
        "daily_cvar_95": None,
        "max_drawdown": 0.0,
        "final_value": 0.0,
    }
    series = pd.Series(value_timeline, dtype=float).sort_index()
    if len(series) < 2:
        return {
            **empty_metrics,
            "final_value": float(series.iloc[-1]) if len(series) else 0.0,
        }

    returns = series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    years = max((len(series) - 1) / TRADING_DAYS_PER_YEAR, 1 / TRADING_DAYS_PER_YEAR)
    cagr = (series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1 if series.iloc[0] > 0 else 0.0
    annual_vol = float(returns.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(returns) else 0.0
    drawdown = series / series.cummax() - 1
    max_drawdown = float(drawdown.min())
    if risk_free_daily_returns is None:
        daily_risk_free = (
            (
                (1.0 + float(risk_free_rate))
                ** (1.0 / TRADING_DAYS_PER_YEAR)
                - 1.0
            )
            if float(risk_free_rate) > -1.0
            else 0.0
        )
        aligned_risk_free = pd.Series(
            daily_risk_free,
            index=returns.index,
            dtype=float,
        )
        risk_free_coverage = 1.0
    else:
        supplied = pd.Series(
            risk_free_daily_returns,
            dtype=float,
        ).copy()
        supplied.index = pd.to_datetime(supplied.index)
        supplied = supplied.sort_index().replace(
            [np.inf, -np.inf],
            np.nan,
        )
        exact = supplied.reindex(returns.index)
        risk_free_coverage = float(exact.notna().mean())
        aligned_risk_free = exact.ffill()
        if aligned_risk_free.isna().any():
            raise ValueError(
                "Historical risk-free series does not cover the "
                "portfolio return start date"
            )
    excess_returns = returns - aligned_risk_free
    annualized_excess_return = float(
        excess_returns.mean() * TRADING_DAYS_PER_YEAR
    )
    annualized_risk_free_return = float(
        (1.0 + aligned_risk_free).prod()
        ** (TRADING_DAYS_PER_YEAR / len(aligned_risk_free))
        - 1.0
    )
    sharpe = (
        None
        if annual_vol <= 0
        else float(annualized_excess_return / annual_vol)
    )
    downside = excess_returns.clip(upper=0.0)
    downside_deviation = float(
        np.sqrt(np.mean(np.square(downside)))
        * np.sqrt(TRADING_DAYS_PER_YEAR)
    ) if len(downside) else 0.0
    sortino = (
        None
        if downside_deviation <= 0
        else float(annualized_excess_return / downside_deviation)
    )
    calmar = (
        None
        if abs(max_drawdown) <= 1e-12
        else float(cagr / abs(max_drawdown))
    )
    positive_excess = float(excess_returns.clip(lower=0.0).sum())
    negative_excess = abs(float(excess_returns.clip(upper=0.0).sum()))
    omega = (
        None
        if negative_excess <= 1e-12
        else float(positive_excess / negative_excess)
    )
    var_threshold = float(returns.quantile(0.05)) if len(returns) else np.nan
    tail_returns = returns.loc[returns <= var_threshold]
    return {
        "cagr": float(cagr),
        "annual_volatility": annual_vol,
        "annualized_excess_return": annualized_excess_return,
        "annualized_risk_free_return": annualized_risk_free_return,
        "risk_free_observation_coverage": risk_free_coverage,
        "annual_downside_deviation": downside_deviation,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "omega": omega,
        "daily_var_95": (
            None
            if not np.isfinite(var_threshold)
            else float(max(0.0, -var_threshold))
        ),
        "daily_cvar_95": (
            None
            if tail_returns.empty
            else float(max(0.0, -tail_returns.mean()))
        ),
        "max_drawdown": max_drawdown,
        "final_value": float(series.iloc[-1]),
    }


def _candidate_model_name(summary_by_model):
    for name in PROMOTION_CANDIDATE_MODELS:
        if summary_by_model.get(name):
            return name
    return PROMOTION_CANDIDATE_MODELS[0]


def _promotion_decision(summary_by_model):
    candidate_name = _candidate_model_name(summary_by_model)
    candidate = summary_by_model.get(candidate_name)
    required_baselines = list(PROMOTION_BASELINE_MODELS)
    market_cap_metrics = summary_by_model.get("market_cap_weight")
    if market_cap_metrics and market_cap_metrics.get("market_cap_available_count", 0) > 0:
        required_baselines.append("market_cap_weight")
    baselines = {
        name: summary_by_model.get(name)
        for name in required_baselines
    }
    reasons = []
    missing = [name for name, metrics in baselines.items() if not metrics]
    if not candidate or missing:
        missing_reasons = []
        if not candidate:
            missing_reasons.append(f"Candidate model {candidate_name} is missing.")
        if missing:
            missing_reasons.append(f"Required comparison models are missing: {', '.join(missing)}.")
        return {
            "candidate_model": candidate_name,
            "status": "not_promoted",
            "reasons": missing_reasons,
        }

    for name, baseline in baselines.items():
        if candidate.get("sharpe") is None or baseline.get("sharpe") is None:
            reasons.append(f"Sharpe unavailable against {name}.")
        elif candidate["sharpe"] <= baseline["sharpe"]:
            reasons.append(f"Sharpe does not beat {name}.")
        if candidate.get("cagr", 0.0) <= baseline.get("cagr", 0.0):
            reasons.append(f"CAGR does not beat {name}.")
        if candidate.get("max_drawdown", -1.0) < baseline.get("max_drawdown", -1.0):
            reasons.append(f"Max drawdown is worse than {name}.")

    historical_turnover = max(baselines["historical_bl"].get("avg_controlled_turnover", 0.0), 1e-9)
    if candidate.get("avg_controlled_turnover", 0.0) > max(0.50, historical_turnover * 2.0):
        reasons.append("Turnover is too high versus historical BL.")
    if candidate.get("failed_forecast_count", 0) > 0:
        reasons.append(f"{candidate_name} produced no-view forecasts.")
    if candidate.get("signal_rank_ic_count", 0) <= 0:
        reasons.append("Cross-sectional signal rank IC is unavailable.")
    elif candidate.get("avg_signal_rank_ic") is None or candidate["avg_signal_rank_ic"] <= 0.0:
        reasons.append("Average cross-sectional signal rank IC is not positive.")
    if (
        candidate.get("positive_signal_rank_ic_rate") is None
        or candidate["positive_signal_rank_ic_rate"] < 0.50
    ):
        reasons.append("Positive signal rank IC rate is below 50%.")
    if (
        candidate.get("avg_top_bottom_spread") is None
        or candidate["avg_top_bottom_spread"] <= 0.0
    ):
        reasons.append("Average top-minus-bottom spread is not positive.")

    if reasons:
        return {
            "candidate_model": candidate_name,
            "status": "not_promoted",
            "reasons": reasons,
        }
    return {
        "candidate_model": candidate_name,
        "status": "candidate_requires_gauntlet_confirmation",
        "reasons": [
            "Single backtest passed local baseline checks, but default promotion requires multi-basket and multi-regime gauntlet confirmation."
        ],
    }


def _candidate_survives_case(summary_by_model, candidate_name=None):
    candidate_name = candidate_name or _candidate_model_name(summary_by_model)
    candidate = summary_by_model.get(candidate_name)
    if not candidate:
        return False, [f"Candidate model {candidate_name} is missing."]

    baseline_names = list(PROMOTION_BASELINE_MODELS)
    market_cap_metrics = summary_by_model.get("market_cap_weight")
    if market_cap_metrics and market_cap_metrics.get("market_cap_available_count", 0) > 0:
        baseline_names.append("market_cap_weight")

    reasons = []
    for name in baseline_names:
        baseline = summary_by_model.get(name)
        if not baseline:
            reasons.append(f"Missing baseline {name}.")
            continue
        if candidate.get("sharpe") is None or baseline.get("sharpe") is None:
            reasons.append(f"Sharpe unavailable against {name}.")
        elif candidate["sharpe"] <= baseline["sharpe"]:
            reasons.append(f"Sharpe does not beat {name}.")
        if candidate.get("max_drawdown", -1.0) < baseline.get("max_drawdown", -1.0):
            reasons.append(f"Max drawdown is worse than {name}.")
        baseline_turnover = baseline.get("avg_controlled_turnover", 0.0)
        if candidate.get("avg_controlled_turnover", 0.0) > max(0.50, baseline_turnover * 2.0):
            reasons.append(f"Turnover is too high versus {name}.")
    if candidate.get("failed_forecast_count", 0) > 0:
        reasons.append(f"{candidate_name} produced no-view forecasts.")
    if candidate.get("signal_rank_ic_count", 0) <= 0:
        reasons.append("Cross-sectional signal rank IC is unavailable.")
    elif candidate.get("avg_signal_rank_ic") is None or candidate["avg_signal_rank_ic"] <= 0.0:
        reasons.append("Average cross-sectional signal rank IC is not positive.")
    if (
        candidate.get("positive_signal_rank_ic_rate") is None
        or candidate["positive_signal_rank_ic_rate"] < 0.50
    ):
        reasons.append("Positive signal rank IC rate is below 50%.")
    if (
        candidate.get("avg_top_bottom_spread") is None
        or candidate["avg_top_bottom_spread"] <= 0.0
    ):
        reasons.append("Average top-minus-bottom spread is not positive.")
    return not reasons, reasons


def aggregate_gauntlet_promotion(runs, candidate_model=None):
    """Aggregate promotion evidence across baskets, regimes, and sensitivity runs."""
    case_reports = []
    survival_count = 0
    usable_count = 0
    candidate_name = candidate_model

    for index, run in enumerate(runs or []):
        result = run.get("result", run) if isinstance(run, dict) else {}
        summary = result.get("summary_by_model", {}) if isinstance(result, dict) else {}
        if not summary:
            continue
        candidate_name = candidate_name or _candidate_model_name(summary)
        survived, reasons = _candidate_survives_case(summary, candidate_name=candidate_name)
        usable_count += 1
        survival_count += int(survived)
        metadata = run.get("case", {}) if isinstance(run, dict) else {}
        settings = result.get("settings", {})
        case_reports.append({
            "index": index,
            "basket": metadata.get("basket"),
            "regime": metadata.get("regime"),
            "rebalance_band": settings.get("rebalance_band"),
            "max_turnover": settings.get("max_turnover"),
            "survived": bool(survived),
            "reasons": reasons,
        })

    survival_rate = float(survival_count / usable_count) if usable_count else 0.0
    failed_cases = [case for case in case_reports if not case["survived"]]
    reasons = []
    if usable_count == 0:
        reasons.append("No usable gauntlet runs were supplied.")
    if failed_cases:
        reasons.append(f"Candidate failed {len(failed_cases)} of {usable_count} usable gauntlet runs.")
    if usable_count < 4:
        reasons.append("At least four basket/regime cases are required to reduce single-period lucky-win risk.")

    status = "not_promoted"
    if usable_count >= 4 and not failed_cases:
        status = "candidate_requires_manual_review"
        reasons.append("Candidate survived the configured gauntlet; keep manual review before changing defaults.")

    return {
        "candidate_model": candidate_name or PROMOTION_CANDIDATE_MODELS[0],
        "status": status,
        "survival_count": int(survival_count),
        "usable_count": int(usable_count),
        "survival_rate": survival_rate,
        "reasons": reasons,
        "cases": case_reports,
    }


def _validate_backtest_models(models):
    selected = tuple(models or DEFAULT_BACKTEST_MODELS)
    unsupported = sorted(set(selected) - set(SUPPORTED_BACKTEST_MODELS))
    if unsupported:
        raise ValueError(f"Unsupported backtest models: {unsupported}")
    return selected


def _prepare_backtest_data(price_data, start_date=None, end_date=None, train_window=504):
    data = _clean_price_frame(price_data)
    if start_date:
        data = data[data.index >= pd.Timestamp(start_date)]
    if end_date:
        data = data[data.index <= pd.Timestamp(end_date)]
    if len(data) < int(train_window) + 2:
        raise ValueError("Not enough rows for train_window plus one out-of-sample period")
    return data


def _rebalance_target_signature(
    data,
    models,
    train_window,
    rebalance_frequency,
    forecast_horizon,
    max_asset_weight,
    min_holding_weight,
    market_caps,
    risk_free_rate,
    point_in_time_features,
    market_caps_as_of_date,
    point_in_time_market_caps,
):
    market_caps = {} if market_caps is None else dict(market_caps)
    price_hashes = pd.util.hash_pandas_object(data, index=True).values
    factor_digest = None
    if point_in_time_features is not None:
        factor_frame = pd.DataFrame(point_in_time_features)
        factor_hashes = pd.util.hash_pandas_object(
            factor_frame,
            index=True,
        ).values
        factor_digest = hashlib.blake2b(
            factor_hashes.tobytes()
            + json.dumps(
                [str(column) for column in factor_frame.columns],
                separators=(",", ":"),
            ).encode("utf-8"),
            digest_size=16,
        ).hexdigest()
    market_cap_digest = None
    if point_in_time_market_caps is not None:
        market_cap_frame = pd.DataFrame(point_in_time_market_caps).copy()
        market_cap_frame.index = pd.to_datetime(market_cap_frame.index)
        market_cap_hashes = pd.util.hash_pandas_object(
            market_cap_frame.sort_index(),
            index=True,
        ).values
        market_cap_digest = hashlib.blake2b(
            market_cap_hashes.tobytes()
            + json.dumps(
                [str(column) for column in market_cap_frame.columns],
                separators=(",", ":"),
            ).encode("utf-8"),
            digest_size=16,
        ).hexdigest()
    return {
        "start_date": data.index[0].strftime("%Y-%m-%d"),
        "end_date": data.index[-1].strftime("%Y-%m-%d"),
        "row_count": int(len(data)),
        "tickers": list(data.columns),
        "price_digest": hashlib.blake2b(price_hashes.tobytes(), digest_size=16).hexdigest(),
        "models": list(models),
        "train_window": int(train_window),
        "rebalance_frequency": int(rebalance_frequency),
        "forecast_horizon": int(forecast_horizon),
        "max_asset_weight": float(max_asset_weight),
        "min_holding_weight": float(max(0.0, _to_float(min_holding_weight, 0.0))),
        "market_caps": {
            ticker: _to_float(market_caps.get(ticker), 0.0)
            for ticker in data.columns
        },
        "market_caps_as_of_date": (
            None
            if market_caps_as_of_date is None
            else pd.Timestamp(market_caps_as_of_date).strftime("%Y-%m-%d")
        ),
        "point_in_time_market_cap_digest": market_cap_digest,
        "risk_free_rate": float(risk_free_rate),
        "point_in_time_factor_digest": factor_digest,
    }


def _market_caps_available_at(
    tickers,
    current_date,
    market_caps=None,
    market_caps_as_of_date=None,
    point_in_time_market_caps=None,
):
    """Resolve only market-cap observations known by the rebalance date."""
    tickers = list(tickers)
    current_date = pd.Timestamp(current_date).tz_localize(None)
    if point_in_time_market_caps is not None:
        frame = pd.DataFrame(point_in_time_market_caps).copy()
        frame.index = pd.to_datetime(frame.index).tz_localize(None)
        frame = frame.sort_index()
        available = frame.loc[frame.index <= current_date]
        if not available.empty:
            row = (
                available.reindex(columns=tickers)
                .ffill()
                .iloc[-1]
                .replace([np.inf, -np.inf], np.nan)
                .dropna()
            )
            return row.to_dict(), available.index[-1].strftime("%Y-%m-%d")

    if market_caps and market_caps_as_of_date is not None:
        as_of = pd.Timestamp(market_caps_as_of_date).tz_localize(None)
        if as_of <= current_date:
            values = (
                pd.Series(market_caps, dtype=float)
                .reindex(tickers)
                .replace([np.inf, -np.inf], np.nan)
                .dropna()
            )
            return values.to_dict(), as_of.strftime("%Y-%m-%d")
    return {}, None


def _build_rebalance_targets_for_data(
    data,
    models,
    train_window,
    rebalance_frequency,
    forecast_horizon,
    max_asset_weight,
    min_holding_weight,
    market_caps,
    risk_free_rate,
    point_in_time_features,
    market_caps_as_of_date,
    point_in_time_market_caps,
):
    records = []
    warnings = []
    previous_target_weights = {}
    for rebalance_index in range(train_window, len(data) - 1, rebalance_frequency):
        current_date = data.index[rebalance_index]
        next_index = min(rebalance_index + rebalance_frequency, len(data) - 1)
        train_prices = data.iloc[rebalance_index - train_window:rebalance_index].dropna(axis=1)
        current_prices = data.iloc[rebalance_index].reindex(train_prices.columns)
        if train_prices.empty or current_prices.dropna().empty:
            warnings.append(f"Skipped {current_date.date()}: no valid training/current prices")
            continue

        model_targets = {}
        diagnostic_covariance = _safe_covariance(train_prices)
        available_market_caps, market_caps_used_as_of = (
            _market_caps_available_at(
                train_prices.columns,
                current_date,
                market_caps=market_caps,
                market_caps_as_of_date=market_caps_as_of_date,
                point_in_time_market_caps=point_in_time_market_caps,
            )
        )
        for model in models:
            weights, diagnostics = _model_weights(
                model,
                train_prices,
                forecast_horizon,
                max_asset_weight,
                risk_free_rate,
                market_caps=available_market_caps,
                point_in_time_features=point_in_time_features,
                previous_target_weights=previous_target_weights.get(model),
            )
            allow_cash_reserve = bool(
                diagnostics.get("allow_cash_reserve", False)
            )
            target_risky_exposure = (
                float(
                    np.clip(
                        diagnostics.get(
                            "target_risky_exposure",
                            sum(weights.values()),
                        ),
                        0.0,
                        1.0,
                    )
                )
                if allow_cash_reserve
                else 1.0
            )
            weights = apply_min_holding_threshold(weights, min_holding_weight)
            weights = _normalize_weights(
                weights,
                train_prices.columns,
                gross_exposure=target_risky_exposure,
            )
            diagnostics["target_risky_exposure"] = float(
                sum(weights.values())
            )
            diagnostics["target_cash_weight"] = float(
                1.0 - sum(weights.values())
            )
            signal_scores = diagnostics.get(
                "signal_scores",
                diagnostics.get("forecast_rank_scores", {}),
            )
            diagnostics.update(
                _weight_diagnostics(weights, signal_scores, diagnostic_covariance)
            )
            if model == "market_cap_weight":
                diagnostics["market_caps_as_of_date"] = (
                    market_caps_used_as_of
                )
            diagnostics["target_weights"] = {
                ticker: float(weight)
                for ticker, weight in weights.items()
            }
            model_targets[model] = {
                "weights": {ticker: float(weight) for ticker, weight in weights.items()},
                "diagnostics": dict(diagnostics),
            }
            previous_target_weights[model] = dict(weights)

        records.append({
            "rebalance_date": current_date.strftime("%Y-%m-%d"),
            "train_start_date": train_prices.index[0].strftime("%Y-%m-%d"),
            "train_end_date": train_prices.index[-1].strftime("%Y-%m-%d"),
            "period_end_date": data.index[next_index].strftime("%Y-%m-%d"),
            "models": model_targets,
        })

    return {
        "signature": _rebalance_target_signature(
            data,
            models,
            train_window,
            rebalance_frequency,
            forecast_horizon,
            max_asset_weight,
            min_holding_weight,
            market_caps,
            risk_free_rate,
            point_in_time_features,
            market_caps_as_of_date,
            point_in_time_market_caps,
        ),
        "records": records,
        "warnings": warnings,
        "forecast_cache": forecast_rank_cache_stats(),
    }


def build_rebalance_targets(
    price_data,
    models=None,
    start_date=None,
    end_date=None,
    train_window=504,
    rebalance_frequency=21,
    forecast_horizon=63,
    max_asset_weight=0.2,
    min_holding_weight=0.0,
    market_caps=None,
    risk_free_rate=0.02,
    point_in_time_features=None,
    market_caps_as_of_date=None,
    point_in_time_market_caps=None,
):
    """Precompute model targets once so execution sensitivities can replay them cheaply."""
    train_window = int(train_window)
    rebalance_frequency = max(1, int(rebalance_frequency))
    models = _validate_backtest_models(models)
    data = _prepare_backtest_data(
        price_data,
        start_date=start_date,
        end_date=end_date,
        train_window=train_window,
    )
    return _build_rebalance_targets_for_data(
        data,
        models,
        train_window,
        rebalance_frequency,
        int(forecast_horizon),
        max_asset_weight,
        min_holding_weight,
        market_caps,
        risk_free_rate,
        point_in_time_features,
        market_caps_as_of_date,
        point_in_time_market_caps,
    )


def run_portfolio_model_backtest(
    price_data,
    models=None,
    start_date=None,
    end_date=None,
    train_window=504,
    rebalance_frequency=21,
    forecast_horizon=63,
    transaction_cost_bps=10.0,
    max_asset_weight=0.2,
    rebalance_band=DEFAULT_REBALANCE_BAND,
    max_turnover=DEFAULT_MAX_TURNOVER,
    min_holding_weight=0.0,
    market_caps=None,
    risk_free_rate=0.02,
    risk_free_daily_returns=None,
    initial_value=10000.0,
    rebalance_targets=None,
    point_in_time_features=None,
    include_daily_returns=False,
    market_caps_as_of_date=None,
    point_in_time_market_caps=None,
):
    train_window = int(train_window)
    rebalance_frequency = max(1, int(rebalance_frequency))
    models = _validate_backtest_models(models)
    data = _prepare_backtest_data(
        price_data,
        start_date=start_date,
        end_date=end_date,
        train_window=train_window,
    )
    expected_target_signature = _rebalance_target_signature(
        data,
        models,
        train_window,
        rebalance_frequency,
        forecast_horizon,
        max_asset_weight,
        min_holding_weight,
        market_caps,
        risk_free_rate,
        point_in_time_features,
        market_caps_as_of_date,
        point_in_time_market_caps,
    )
    reused_rebalance_targets = rebalance_targets is not None
    if rebalance_targets is None:
        rebalance_targets = _build_rebalance_targets_for_data(
            data,
            models,
            train_window,
            rebalance_frequency,
            int(forecast_horizon),
            max_asset_weight,
            min_holding_weight,
            market_caps,
            risk_free_rate,
            point_in_time_features,
            market_caps_as_of_date,
            point_in_time_market_caps,
        )
    elif rebalance_targets.get("signature") != expected_target_signature:
        raise ValueError("rebalance_targets do not match the requested backtest data or model settings")
    target_records = {
        record["rebalance_date"]: record
        for record in rebalance_targets.get("records", [])
    }
    states = {
        model: {
            "shares": pd.Series(0.0, index=data.columns),
            "cash": float(initial_value),
            "values": OrderedDict(),
            "turnovers": [],
            "controlled_turnovers": [],
            "transaction_costs": [],
            "skipped_trade_count": 0,
            "turnover_cap_hit_count": 0,
            "failed_forecast_count": 0,
            "forecast_confidences": [],
            "forecast_rank_ics": [],
            "top_bottom_spreads": [],
            "signal_weight_rank_correlations": [],
            "signal_persistence": [],
            "active_shares": [],
            "controlled_active_shares": [],
            "execution_signal_retention": [],
            "execution_weight_l1": [],
            "concentrations": [],
            "predicted_volatilities": [],
            "execution_predicted_volatilities": [],
            "realized_period_volatilities": [],
            "risk_forecast_errors": [],
            "risk_forecast_ratios": [],
            "risky_exposures": [],
            "signal_coverage_rates": [],
            "view_signal_retentions": [],
            "gross_period_returns": [],
            "net_period_returns": [],
            "horizon_rank_ics": {},
            "previous_signal_scores": None,
            "market_cap_available_count": 0,
            "initialized": False,
        }
        for model in models
    }
    rebalance_records = []
    warnings = list(rebalance_targets.get("warnings", []))

    for rebalance_index in range(train_window, len(data) - 1, rebalance_frequency):
        current_date = data.index[rebalance_index]
        current_date_key = current_date.strftime("%Y-%m-%d")
        next_index = min(rebalance_index + rebalance_frequency, len(data) - 1)
        train_prices = data.iloc[rebalance_index - train_window:rebalance_index].dropna(axis=1)
        current_prices = data.iloc[rebalance_index].reindex(train_prices.columns)
        period_prices = data.iloc[rebalance_index:next_index + 1].reindex(columns=train_prices.columns).ffill()
        if train_prices.empty or current_prices.dropna().empty:
            continue
        diagnostic_covariance = _safe_covariance(train_prices)
        target_record = target_records.get(current_date_key)
        if target_record is None:
            raise ValueError(f"rebalance_targets are missing {current_date_key}")

        for model in models:
            model_target = target_record.get("models", {}).get(model)
            if model_target is None:
                raise ValueError(f"rebalance_targets are missing {model} at {current_date_key}")
            diagnostics = dict(model_target.get("diagnostics", {}))
            target_risky_exposure = (
                float(
                    np.clip(
                        diagnostics.get("target_risky_exposure", 1.0),
                        0.0,
                        1.0,
                    )
                )
                if diagnostics.get("allow_cash_reserve", False)
                else 1.0
            )
            weights = _normalize_weights(
                model_target.get("weights", {}),
                train_prices.columns,
                gross_exposure=target_risky_exposure,
            )
            state = states[model]
            shares = state["shares"].reindex(train_prices.columns).fillna(0.0)
            current_values = (shares * current_prices).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            portfolio_value = float(current_values.sum() + state["cash"])
            if portfolio_value <= 0:
                warnings.append(f"Skipped {model} at {current_date.date()}: non-positive portfolio value")
                continue

            target_values_pre_control = pd.Series(weights, index=train_prices.columns).fillna(0.0) * portfolio_value
            initial_allocation = not bool(state["initialized"])
            controlled_target_values, controls = apply_trade_controls(
                current_values,
                target_values_pre_control,
                portfolio_value=portfolio_value,
                rebalance_band=(
                    0.0 if initial_allocation else rebalance_band
                ),
                max_turnover=(
                    None if initial_allocation else max_turnover
                ),
            )
            controls["initial_allocation"] = initial_allocation
            cost = controls["controlled_trade_value"] * (_to_float(transaction_cost_bps, 0.0) / 10000.0)
            investable_value = max(0.0, portfolio_value - cost)
            controlled_target_values = controlled_target_values.reindex(train_prices.columns).fillna(0.0)
            controlled_sum = float(controlled_target_values.sum())
            if controlled_sum > investable_value and controlled_sum > 0:
                controlled_target_values *= investable_value / controlled_sum
                controlled_sum = float(controlled_target_values.sum())

            state["shares"] = (controlled_target_values / current_prices).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            state["cash"] = max(0.0, investable_value - controlled_sum)
            turnover = controls["turnover"]
            controlled_turnover = controls["controlled_turnover"]
            state["turnovers"].append(turnover)
            state["controlled_turnovers"].append(controlled_turnover)
            state["transaction_costs"].append(cost)
            state["skipped_trade_count"] += int(controls["skipped_trade_count"])
            state["turnover_cap_hit_count"] += int(bool(controls["turnover_cap_hit"]))
            state["failed_forecast_count"] += int(diagnostics.get("failed_forecast_count", 0))
            state["market_cap_available_count"] += int(bool(diagnostics.get("market_caps_available")))
            if diagnostics.get("avg_forecast_confidence") is not None:
                state["forecast_confidences"].append(float(diagnostics["avg_forecast_confidence"]))
            signal_scores = pd.Series(
                diagnostics.get(
                    "signal_scores",
                    diagnostics.get("forecast_rank_scores", {}),
                ),
                dtype=float,
            ).reindex(train_prices.columns)
            realized_period_returns = (
                period_prices.iloc[-1].reindex(train_prices.columns) / current_prices - 1.0
            ).replace([np.inf, -np.inf], np.nan)
            signal_rank_ic = _safe_rank_correlation(signal_scores, realized_period_returns)
            if signal_rank_ic is not None:
                state["forecast_rank_ics"].append(signal_rank_ic)
            top_bottom_spread = _top_bottom_spread(signal_scores, realized_period_returns)
            if top_bottom_spread is not None:
                state["top_bottom_spreads"].append(top_bottom_spread)

            signal_weight_rank_correlation = _safe_rank_correlation(signal_scores, weights)
            if signal_weight_rank_correlation is not None:
                state["signal_weight_rank_correlations"].append(signal_weight_rank_correlation)
            signal_persistence = _safe_rank_correlation(
                state["previous_signal_scores"],
                signal_scores,
            ) if state["previous_signal_scores"] is not None else None
            if signal_persistence is not None:
                state["signal_persistence"].append(signal_persistence)
            if signal_scores.notna().any():
                state["previous_signal_scores"] = signal_scores.copy()

            horizon_rank_ic = {}
            for diagnostic_horizon in sorted({21, int(forecast_horizon)}):
                horizon_end = rebalance_index + max(1, diagnostic_horizon)
                if horizon_end >= len(data):
                    continue
                horizon_returns = (
                    data.iloc[horizon_end].reindex(train_prices.columns) / current_prices - 1.0
                ).replace([np.inf, -np.inf], np.nan)
                rank_ic = _safe_rank_correlation(signal_scores, horizon_returns)
                if rank_ic is not None:
                    horizon_key = str(int(diagnostic_horizon))
                    horizon_rank_ic[horizon_key] = rank_ic
                    state["horizon_rank_ics"].setdefault(horizon_key, []).append(rank_ic)

            equal_weights = pd.Series(
                1.0 / len(train_prices.columns),
                index=train_prices.columns,
                dtype=float,
            )
            pre_control_weights = pd.Series(weights, dtype=float).reindex(train_prices.columns).fillna(0.0)
            controlled_weights = (
                controlled_target_values / portfolio_value
            ).reindex(train_prices.columns).fillna(0.0)
            controlled_weight_total = float(controlled_weights.sum())
            controlled_signal_weights = (
                controlled_weights / controlled_weight_total
                if controlled_weight_total > 0
                else controlled_weights
            )
            active_share = float(0.5 * (pre_control_weights - equal_weights).abs().sum())
            controlled_active_share = float(
                0.5 * (controlled_signal_weights - equal_weights).abs().sum()
            )
            execution_signal_retention = (
                None
                if active_share <= 1e-12
                else float(controlled_active_share / active_share)
            )
            execution_weight_l1 = float(
                (pre_control_weights - controlled_signal_weights).abs().sum()
            )
            state["active_shares"].append(active_share)
            state["controlled_active_shares"].append(controlled_active_share)
            state["execution_weight_l1"].append(execution_weight_l1)
            if execution_signal_retention is not None:
                state["execution_signal_retention"].append(execution_signal_retention)
            for key, state_key in (
                ("concentration_hhi", "concentrations"),
                ("predicted_annual_volatility", "predicted_volatilities"),
                ("signal_coverage_rate", "signal_coverage_rates"),
                ("view_signal_retention", "view_signal_retentions"),
            ):
                value = diagnostics.get(key)
                if value is not None and np.isfinite(_to_float(value, np.nan)):
                    state[state_key].append(float(value))

            cash_values = _cash_value_path(
                state["cash"],
                period_prices.index,
                risk_free_rate,
                risk_free_daily_returns=risk_free_daily_returns,
            )
            daily_values = (
                period_prices.mul(state["shares"], axis=1).sum(axis=1)
                + cash_values
            )
            execution_variance = float(
                controlled_weights.values
                @ diagnostic_covariance.reindex(
                    index=train_prices.columns,
                    columns=train_prices.columns,
                ).values
                @ controlled_weights.values
            )
            execution_predicted_volatility = float(
                np.sqrt(max(0.0, execution_variance))
            )
            realized_daily_returns = (
                daily_values.pct_change()
                .replace([np.inf, -np.inf], np.nan)
                .dropna()
            )
            realized_period_volatility = (
                None
                if realized_daily_returns.empty
                else float(
                    realized_daily_returns.std(ddof=0)
                    * np.sqrt(TRADING_DAYS_PER_YEAR)
                )
            )
            risk_forecast_error = (
                None
                if realized_period_volatility is None
                else float(
                    realized_period_volatility
                    - execution_predicted_volatility
                )
            )
            risk_forecast_ratio = (
                None
                if realized_period_volatility is None
                or execution_predicted_volatility <= 1e-12
                else float(
                    realized_period_volatility
                    / execution_predicted_volatility
                )
            )
            state["execution_predicted_volatilities"].append(
                execution_predicted_volatility
            )
            state["risky_exposures"].append(
                float(controlled_weights.sum())
            )
            if realized_period_volatility is not None:
                state["realized_period_volatilities"].append(
                    realized_period_volatility
                )
                state["risk_forecast_errors"].append(risk_forecast_error)
            if risk_forecast_ratio is not None:
                state["risk_forecast_ratios"].append(risk_forecast_ratio)
            for date, value in daily_values.items():
                state["values"][date.strftime("%Y-%m-%d")] = float(value)
            if not cash_values.empty:
                state["cash"] = float(cash_values.iloc[-1])
            state["initialized"] = True
            end_value = float(daily_values.iloc[-1]) if not daily_values.empty else investable_value
            net_period_return = float(end_value / portfolio_value - 1.0)
            gross_period_return = float((end_value + cost) / portfolio_value - 1.0)
            state["net_period_returns"].append(net_period_return)
            state["gross_period_returns"].append(gross_period_return)

            rebalance_records.append({
                "model": model,
                "rebalance_date": current_date.strftime("%Y-%m-%d"),
                "train_start_date": train_prices.index[0].strftime("%Y-%m-%d"),
                "train_end_date": train_prices.index[-1].strftime("%Y-%m-%d"),
                "period_end_date": data.index[next_index].strftime("%Y-%m-%d"),
                "weights": {ticker: float(weight) for ticker, weight in weights.items()},
                "pre_control_weights": {ticker: float(weight) for ticker, weight in weights.items()},
                "controlled_weights": _finite_series_dict(controlled_weights),
                "target_risky_exposure": float(sum(weights.values())),
                "target_cash_weight": float(
                    max(0.0, 1.0 - sum(weights.values()))
                ),
                "controlled_risky_exposure": float(
                    controlled_weights.sum()
                ),
                "controlled_cash_weight": float(
                    max(
                        0.0,
                        1.0 - float(controlled_weights.sum()),
                    )
                ),
                "initial_allocation": bool(initial_allocation),
                "rebalance_controls": controls,
                "turnover": float(turnover),
                "controlled_turnover": float(controlled_turnover),
                "skipped_trade_count": int(controls["skipped_trade_count"]),
                "turnover_cap_hit": bool(controls["turnover_cap_hit"]),
                "transaction_cost": float(cost),
                "portfolio_value_before_cost": float(portfolio_value),
                "portfolio_value_after_cost": float(investable_value),
                "failed_forecast_count": int(diagnostics.get("failed_forecast_count", 0)),
                "avg_forecast_confidence": diagnostics.get("avg_forecast_confidence"),
                "signal_scores": _finite_series_dict(signal_scores),
                "raw_forecasts": diagnostics.get("raw_forecasts", {}),
                "forecast_uncertainties": diagnostics.get("forecast_uncertainties", {}),
                "forecast_distribution_diagnostics": diagnostics.get(
                    "forecast_distribution_diagnostics"
                ),
                "alpha_component_scores": diagnostics.get("alpha_component_scores", {}),
                "alpha_component_weights": diagnostics.get("alpha_component_weights", {}),
                "alpha_calibration": diagnostics.get("alpha_calibration"),
                "realized_forward_returns": _finite_series_dict(realized_period_returns),
                "signal_rank_ic": signal_rank_ic,
                "forecast_rank_ic": signal_rank_ic,
                "top_bottom_spread": top_bottom_spread,
                "top_bottom_direction_hit": (
                    None if top_bottom_spread is None else bool(top_bottom_spread > 0.0)
                ),
                "horizon_rank_ic": horizon_rank_ic,
                "signal_persistence": signal_persistence,
                "signal_weight_rank_correlation": signal_weight_rank_correlation,
                "equal_weight_l1_distance": float(2.0 * active_share),
                "active_share": active_share,
                "controlled_active_share": controlled_active_share,
                "execution_signal_retention": execution_signal_retention,
                "execution_weight_l1": execution_weight_l1,
                "concentration_hhi": diagnostics.get("concentration_hhi"),
                "predicted_annual_volatility": diagnostics.get("predicted_annual_volatility"),
                "execution_predicted_annual_volatility": (
                    execution_predicted_volatility
                ),
                "realized_period_annual_volatility": (
                    realized_period_volatility
                ),
                "risk_forecast_error": risk_forecast_error,
                "risk_forecast_ratio": risk_forecast_ratio,
                "prior_returns": diagnostics.get("prior_returns", {}),
                "raw_views": diagnostics.get("raw_views", {}),
                "adjusted_views": diagnostics.get("adjusted_views", {}),
                "posterior_returns": diagnostics.get("posterior_returns", {}),
                "view_signal_retention": diagnostics.get("view_signal_retention"),
                "lightweight_uncertainty_calibration": diagnostics.get(
                    "lightweight_uncertainty_calibration"
                ),
                "mean_estimator": diagnostics.get("mean_estimator"),
                "uncertainty_estimator": diagnostics.get(
                    "uncertainty_estimator"
                ),
                "gross_period_return": gross_period_return,
                "net_period_return": net_period_return,
                "transaction_cost_return_drag": float(gross_period_return - net_period_return),
                "market_caps_available": diagnostics.get("market_caps_available"),
                "market_caps_as_of_date": diagnostics.get(
                    "market_caps_as_of_date"
                ),
                "risk_model": diagnostics.get("risk_model"),
            })

    summary_by_model = {}
    for model, state in states.items():
        metrics = _portfolio_metrics(
            state["values"],
            risk_free_rate,
            risk_free_daily_returns=risk_free_daily_returns,
        )
        total_turnover = float(sum(state["turnovers"]))
        total_controlled_turnover = float(sum(state["controlled_turnovers"]))
        rebalance_count = len(state["turnovers"])
        avg_confidence = (
            None
            if not state["forecast_confidences"]
            else float(np.mean(state["forecast_confidences"]))
        )
        mean_rank_ic = (
            None
            if not state["forecast_rank_ics"]
            else float(np.mean(state["forecast_rank_ics"]))
        )
        median_rank_ic = (
            None
            if not state["forecast_rank_ics"]
            else float(np.median(state["forecast_rank_ics"]))
        )
        positive_rank_ic_rate = (
            None
            if not state["forecast_rank_ics"]
            else float(np.mean(np.asarray(state["forecast_rank_ics"]) > 0.0))
        )
        gross_cumulative_return = (
            0.0
            if not state["gross_period_returns"]
            else float(np.prod(1.0 + np.asarray(state["gross_period_returns"])) - 1.0)
        )
        net_cumulative_return = (
            0.0
            if not state["net_period_returns"]
            else float(np.prod(1.0 + np.asarray(state["net_period_returns"])) - 1.0)
        )
        horizon_rank_ic = {
            horizon: {
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "positive_rate": float(np.mean(np.asarray(values) > 0.0)),
                "count": int(len(values)),
            }
            for horizon, values in state["horizon_rank_ics"].items()
            if values
        }
        metrics.update({
            "turnover": total_turnover,
            "avg_turnover": float(total_turnover / rebalance_count) if rebalance_count else 0.0,
            "controlled_turnover": total_controlled_turnover,
            "avg_controlled_turnover": float(total_controlled_turnover / rebalance_count) if rebalance_count else 0.0,
            "skipped_trade_count": int(state["skipped_trade_count"]),
            "turnover_cap_hit_count": int(state["turnover_cap_hit_count"]),
            "avg_risky_exposure": (
                1.0
                if not state["risky_exposures"]
                else float(np.mean(state["risky_exposures"]))
            ),
            "avg_cash_weight": (
                0.0
                if not state["risky_exposures"]
                else float(
                    1.0 - np.mean(state["risky_exposures"])
                )
            ),
            "transaction_costs": float(sum(state["transaction_costs"])),
            "rebalance_count": int(rebalance_count),
            "failed_forecast_count": int(state["failed_forecast_count"]),
            "avg_forecast_confidence": avg_confidence,
            "avg_signal_rank_ic": mean_rank_ic,
            "median_signal_rank_ic": median_rank_ic,
            "positive_signal_rank_ic_rate": positive_rank_ic_rate,
            "signal_rank_ic_count": int(len(state["forecast_rank_ics"])),
            "avg_forecast_rank_ic": mean_rank_ic,
            "median_forecast_rank_ic": median_rank_ic,
            "positive_forecast_rank_ic_rate": positive_rank_ic_rate,
            "forecast_rank_ic_count": int(len(state["forecast_rank_ics"])),
            "avg_top_bottom_spread": (
                None if not state["top_bottom_spreads"] else float(np.mean(state["top_bottom_spreads"]))
            ),
            "top_bottom_direction_hit_rate": (
                None
                if not state["top_bottom_spreads"]
                else float(np.mean(np.asarray(state["top_bottom_spreads"]) > 0.0))
            ),
            "avg_signal_weight_rank_correlation": (
                None
                if not state["signal_weight_rank_correlations"]
                else float(np.mean(state["signal_weight_rank_correlations"]))
            ),
            "avg_signal_persistence": (
                None if not state["signal_persistence"] else float(np.mean(state["signal_persistence"]))
            ),
            "horizon_rank_ic": horizon_rank_ic,
            "avg_active_share": (
                None if not state["active_shares"] else float(np.mean(state["active_shares"]))
            ),
            "avg_controlled_active_share": (
                None
                if not state["controlled_active_shares"]
                else float(np.mean(state["controlled_active_shares"]))
            ),
            "avg_execution_signal_retention": (
                None
                if not state["execution_signal_retention"]
                else float(np.mean(state["execution_signal_retention"]))
            ),
            "avg_execution_weight_l1": (
                None
                if not state["execution_weight_l1"]
                else float(np.mean(state["execution_weight_l1"]))
            ),
            "avg_concentration_hhi": (
                None if not state["concentrations"] else float(np.mean(state["concentrations"]))
            ),
            "avg_predicted_annual_volatility": (
                None
                if not state["predicted_volatilities"]
                else float(np.mean(state["predicted_volatilities"]))
            ),
            "avg_execution_predicted_annual_volatility": (
                None
                if not state["execution_predicted_volatilities"]
                else float(
                    np.mean(state["execution_predicted_volatilities"])
                )
            ),
            "avg_realized_period_annual_volatility": (
                None
                if not state["realized_period_volatilities"]
                else float(np.mean(state["realized_period_volatilities"]))
            ),
            "risk_forecast_bias": (
                None
                if not state["risk_forecast_errors"]
                else float(np.mean(state["risk_forecast_errors"]))
            ),
            "risk_forecast_mae": (
                None
                if not state["risk_forecast_errors"]
                else float(np.mean(np.abs(state["risk_forecast_errors"])))
            ),
            "avg_risk_forecast_ratio": (
                None
                if not state["risk_forecast_ratios"]
                else float(np.mean(state["risk_forecast_ratios"]))
            ),
            "avg_signal_coverage_rate": (
                None
                if not state["signal_coverage_rates"]
                else float(np.mean(state["signal_coverage_rates"]))
            ),
            "avg_view_signal_retention": (
                None
                if not state["view_signal_retentions"]
                else float(np.mean(state["view_signal_retentions"]))
            ),
            "gross_cumulative_return": gross_cumulative_return,
            "net_cumulative_return": net_cumulative_return,
            "transaction_cost_return_drag": float(
                gross_cumulative_return - net_cumulative_return
            ),
            "market_cap_available_count": int(state["market_cap_available_count"]),
        })
        summary_by_model[model] = metrics

    alpha_diagnostics = {
        model: {
            "signal": {
                "mean_rank_ic": metrics.get("avg_signal_rank_ic"),
                "median_rank_ic": metrics.get("median_signal_rank_ic"),
                "positive_rank_ic_rate": metrics.get("positive_signal_rank_ic_rate"),
                "top_bottom_spread": metrics.get("avg_top_bottom_spread"),
                "top_bottom_direction_hit_rate": metrics.get("top_bottom_direction_hit_rate"),
                "horizon_rank_ic": metrics.get("horizon_rank_ic"),
                "persistence": metrics.get("avg_signal_persistence"),
                "coverage_rate": metrics.get("avg_signal_coverage_rate"),
            },
            "construction": {
                "signal_weight_rank_correlation": metrics.get(
                    "avg_signal_weight_rank_correlation"
                ),
                "active_share": metrics.get("avg_active_share"),
                "view_signal_retention": metrics.get("avg_view_signal_retention"),
                "concentration_hhi": metrics.get("avg_concentration_hhi"),
                "predicted_annual_volatility": metrics.get(
                    "avg_predicted_annual_volatility"
                ),
            },
            "execution": {
                "raw_turnover": metrics.get("turnover"),
                "controlled_turnover": metrics.get("controlled_turnover"),
                "controlled_active_share": metrics.get("avg_controlled_active_share"),
                "signal_retention": metrics.get("avg_execution_signal_retention"),
                "weight_l1_loss": metrics.get("avg_execution_weight_l1"),
                "gross_cumulative_return": metrics.get("gross_cumulative_return"),
                "net_cumulative_return": metrics.get("net_cumulative_return"),
                "transaction_cost_return_drag": metrics.get(
                    "transaction_cost_return_drag"
                ),
            },
        }
        for model, metrics in summary_by_model.items()
    }

    result = {
        "settings": {
            "start_date": data.index[0].strftime("%Y-%m-%d"),
            "end_date": data.index[-1].strftime("%Y-%m-%d"),
            "train_window": train_window,
            "rebalance_frequency": rebalance_frequency,
            "forecast_horizon": int(forecast_horizon),
            "transaction_cost_bps": float(transaction_cost_bps),
            "max_asset_weight": float(max_asset_weight),
            "rebalance_band": float(_to_float(rebalance_band, 0.0)),
            "max_turnover": None if max_turnover is None else float(max_turnover),
            "min_holding_weight": float(max(0.0, _to_float(min_holding_weight, 0.0))),
            "risk_free_rate": float(risk_free_rate),
            "risk_free_rate_source": (
                "historical_daily_series"
                if risk_free_daily_returns is not None
                else "constant_annual_rate"
            ),
            "initial_value": float(initial_value),
            "reused_rebalance_targets": bool(reused_rebalance_targets),
            "price_digest": expected_target_signature["price_digest"],
        },
        "models": list(models),
        "summary_by_model": summary_by_model,
        "alpha_diagnostics": alpha_diagnostics,
        "rebalance_records": rebalance_records,
        "promotion_decision": _promotion_decision(summary_by_model),
        "warnings": warnings,
    }
    if include_daily_returns:
        result["daily_returns_by_model"] = {
            model: {
                str(date): float(value)
                for date, value in (
                    pd.Series(state["values"], dtype=float)
                    .sort_index()
                    .pct_change()
                    .replace([np.inf, -np.inf], np.nan)
                    .dropna()
                    .items()
                )
            }
            for model, state in states.items()
        }
    return result
