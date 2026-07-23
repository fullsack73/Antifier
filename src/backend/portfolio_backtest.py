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

from lightweight_forecast import lightweight_ensemble_forecast
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
    _normalize_expected_return_series,
    _normalize_uncertainty_series,
    _period_return_to_annual_simple_return,
    _shrink_expected_returns,
    forecast_single_ticker_with_arima_transformer,
    forecast_single_ticker_with_transformer,
    get_stock_data,
)
from portfolio_signals import (
    FORECAST_RANK_VIEW_UNCERTAINTY,
    MOMENTUM_VIEW_UNCERTAINTY,
    SIGNAL_STACK_VIEW_UNCERTAINTY,
    SIX_MONTH_MOMENTUM_LOOKBACK_DAYS,
    low_volatility_tilt,
    market_cap_weight,
    momentum_bl_views,
    momentum_tilt_weights,
    rank_to_unit_scores,
    risk_parity,
    signal_stack_bl_views,
)
from ticker_lists import get_ticker_group


logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
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
    "historical_mpt",
    "lightweight_bl",
    "arima_transformer_rank_bl",
    "transformer_rank_bl",
    "arima_transformer_bl",
    "transformer_bl",
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
FORECAST_RANK_CACHE_SCHEMA_VERSION = "2026-07-23-v1"


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


def _normalize_weights(weights, tickers):
    cleaned = {
        ticker: max(0.0, _to_float(weights.get(ticker, 0.0)))
        for ticker in tickers
    }
    total = sum(cleaned.values())
    if total <= 0:
        return _equal_weights(tickers)
    return {ticker: weight / total for ticker, weight in cleaned.items()}


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
    }


def _forecast_views(train_prices, method, forecast_horizon):
    tickers = list(train_prices.columns)
    views = {}
    uncertainties = {}
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

    if method in ("arima_transformer_rank", "transformer_rank"):
        return _forecast_rank_views(train_prices, method, forecast_horizon)

    for ticker in tickers:
        prices = train_prices[ticker].dropna()
        if method == "historical":
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
    return views, uncertainties, failed, {}


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

    no_view_mask = views.isna()
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
    return weights, {
        "failed_forecast_count": int(failed),
        "avg_forecast_confidence": avg_confidence,
        **forecast_diagnostics,
    }


def _model_weights(model_name, train_prices, forecast_horizon, max_asset_weight, risk_free_rate,
                   market_caps=None):
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

    if model_name == "momentum_6m":
        weights = momentum_tilt_weights(
            train_prices,
            lookback=SIX_MONTH_MOMENTUM_LOOKBACK_DAYS,
            skip=0,
            max_asset_weight=max_asset_weight,
        ).to_dict()
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

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

    if model_name == "historical_mpt":
        mu = _calculate_historical_cagr(train_prices)
        weights = _efficient_frontier_weights(mu, covariance, max_asset_weight, "max_sharpe", risk_free_rate)
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    bl_methods = {
        "historical_bl": "historical",
        "momentum_bl": "momentum",
        "signal_stack_bl": "signal_stack",
        "lightweight_bl": "lightweight",
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


def _portfolio_metrics(value_timeline, risk_free_rate):
    series = pd.Series(value_timeline, dtype=float).sort_index()
    if len(series) < 2:
        return {
            "cagr": 0.0,
            "annual_volatility": 0.0,
            "sharpe": None,
            "max_drawdown": 0.0,
            "final_value": float(series.iloc[-1]) if len(series) else 0.0,
        }

    returns = series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    years = max((len(series) - 1) / TRADING_DAYS_PER_YEAR, 1 / TRADING_DAYS_PER_YEAR)
    cagr = (series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1 if series.iloc[0] > 0 else 0.0
    annual_vol = float(returns.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(returns) else 0.0
    sharpe = None if annual_vol <= 0 else float((cagr - risk_free_rate) / annual_vol)
    drawdown = series / series.cummax() - 1
    return {
        "cagr": float(cagr),
        "annual_volatility": annual_vol,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
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
    unsupported = sorted(set(selected) - set(DEFAULT_BACKTEST_MODELS))
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
):
    market_caps = {} if market_caps is None else dict(market_caps)
    price_hashes = pd.util.hash_pandas_object(data, index=True).values
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
        "risk_free_rate": float(risk_free_rate),
    }


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
):
    records = []
    warnings = []
    for rebalance_index in range(train_window, len(data) - 1, rebalance_frequency):
        current_date = data.index[rebalance_index]
        next_index = min(rebalance_index + rebalance_frequency, len(data) - 1)
        train_prices = data.iloc[rebalance_index - train_window:rebalance_index].dropna(axis=1)
        current_prices = data.iloc[rebalance_index].reindex(train_prices.columns)
        if train_prices.empty or current_prices.dropna().empty:
            warnings.append(f"Skipped {current_date.date()}: no valid training/current prices")
            continue

        model_targets = {}
        for model in models:
            weights, diagnostics = _model_weights(
                model,
                train_prices,
                forecast_horizon,
                max_asset_weight,
                risk_free_rate,
                market_caps=market_caps,
            )
            weights = apply_min_holding_threshold(weights, min_holding_weight)
            weights = _normalize_weights(weights, train_prices.columns)
            model_targets[model] = {
                "weights": {ticker: float(weight) for ticker, weight in weights.items()},
                "diagnostics": dict(diagnostics),
            }

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
    initial_value=10000.0,
    rebalance_targets=None,
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
            "market_cap_available_count": 0,
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
        target_record = target_records.get(current_date_key)
        if target_record is None:
            raise ValueError(f"rebalance_targets are missing {current_date_key}")

        for model in models:
            model_target = target_record.get("models", {}).get(model)
            if model_target is None:
                raise ValueError(f"rebalance_targets are missing {model} at {current_date_key}")
            weights = _normalize_weights(model_target.get("weights", {}), train_prices.columns)
            diagnostics = dict(model_target.get("diagnostics", {}))
            state = states[model]
            shares = state["shares"].reindex(train_prices.columns).fillna(0.0)
            current_values = (shares * current_prices).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            portfolio_value = float(current_values.sum() + state["cash"])
            if portfolio_value <= 0:
                warnings.append(f"Skipped {model} at {current_date.date()}: non-positive portfolio value")
                continue

            target_values_pre_control = pd.Series(weights, index=train_prices.columns).fillna(0.0) * portfolio_value
            controlled_target_values, controls = apply_trade_controls(
                current_values,
                target_values_pre_control,
                portfolio_value=portfolio_value,
                rebalance_band=rebalance_band,
                max_turnover=max_turnover,
            )
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
            forecast_rank_scores = pd.Series(
                diagnostics.get("forecast_rank_scores", {}),
                dtype=float,
            ).reindex(train_prices.columns)
            realized_period_returns = (
                period_prices.iloc[-1].reindex(train_prices.columns) / current_prices - 1.0
            )
            valid_rank_mask = (
                forecast_rank_scores.notna()
                & realized_period_returns.replace([np.inf, -np.inf], np.nan).notna()
            )
            forecast_rank_ic = None
            if (
                int(valid_rank_mask.sum()) >= 2
                and forecast_rank_scores[valid_rank_mask].nunique() >= 2
                and realized_period_returns[valid_rank_mask].nunique() >= 2
            ):
                rank_ic_value = forecast_rank_scores[valid_rank_mask].corr(
                    realized_period_returns[valid_rank_mask],
                    method="spearman",
                )
                if pd.notna(rank_ic_value) and np.isfinite(rank_ic_value):
                    forecast_rank_ic = float(rank_ic_value)
                    state["forecast_rank_ics"].append(forecast_rank_ic)

            daily_values = period_prices.mul(state["shares"], axis=1).sum(axis=1) + state["cash"]
            for date, value in daily_values.items():
                state["values"][date.strftime("%Y-%m-%d")] = float(value)

            rebalance_records.append({
                "model": model,
                "rebalance_date": current_date.strftime("%Y-%m-%d"),
                "train_start_date": train_prices.index[0].strftime("%Y-%m-%d"),
                "train_end_date": train_prices.index[-1].strftime("%Y-%m-%d"),
                "period_end_date": data.index[next_index].strftime("%Y-%m-%d"),
                "weights": {ticker: float(weight) for ticker, weight in weights.items()},
                "pre_control_weights": {ticker: float(weight) for ticker, weight in weights.items()},
                "controlled_weights": {
                    ticker: float(value / portfolio_value)
                    for ticker, value in controlled_target_values.items()
                    if portfolio_value > 0 and value > 1e-10
                },
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
                "forecast_rank_ic": forecast_rank_ic,
                "market_caps_available": diagnostics.get("market_caps_available"),
            })

    summary_by_model = {}
    for model, state in states.items():
        metrics = _portfolio_metrics(state["values"], risk_free_rate)
        total_turnover = float(sum(state["turnovers"]))
        total_controlled_turnover = float(sum(state["controlled_turnovers"]))
        rebalance_count = len(state["turnovers"])
        avg_confidence = (
            None
            if not state["forecast_confidences"]
            else float(np.mean(state["forecast_confidences"]))
        )
        metrics.update({
            "turnover": total_turnover,
            "avg_turnover": float(total_turnover / rebalance_count) if rebalance_count else 0.0,
            "controlled_turnover": total_controlled_turnover,
            "avg_controlled_turnover": float(total_controlled_turnover / rebalance_count) if rebalance_count else 0.0,
            "skipped_trade_count": int(state["skipped_trade_count"]),
            "turnover_cap_hit_count": int(state["turnover_cap_hit_count"]),
            "transaction_costs": float(sum(state["transaction_costs"])),
            "rebalance_count": int(rebalance_count),
            "failed_forecast_count": int(state["failed_forecast_count"]),
            "avg_forecast_confidence": avg_confidence,
            "avg_forecast_rank_ic": (
                None
                if not state["forecast_rank_ics"]
                else float(np.mean(state["forecast_rank_ics"]))
            ),
            "median_forecast_rank_ic": (
                None
                if not state["forecast_rank_ics"]
                else float(np.median(state["forecast_rank_ics"]))
            ),
            "positive_forecast_rank_ic_rate": (
                None
                if not state["forecast_rank_ics"]
                else float(np.mean(np.asarray(state["forecast_rank_ics"]) > 0.0))
            ),
            "forecast_rank_ic_count": int(len(state["forecast_rank_ics"])),
            "market_cap_available_count": int(state["market_cap_available_count"]),
        })
        summary_by_model[model] = metrics

    return {
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
            "initial_value": float(initial_value),
            "reused_rebalance_targets": bool(reused_rebalance_targets),
            "price_digest": expected_target_signature["price_digest"],
        },
        "models": list(models),
        "summary_by_model": summary_by_model,
        "rebalance_records": rebalance_records,
        "promotion_decision": _promotion_decision(summary_by_model),
        "warnings": warnings,
    }
