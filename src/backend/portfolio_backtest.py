"""Walk-forward portfolio backtests for optimizer forecast methods."""

import logging
from collections import OrderedDict

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
from portfolio_signals import MOMENTUM_VIEW_UNCERTAINTY, momentum_bl_views, risk_parity
from ticker_lists import get_ticker_group


logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
DEFAULT_BACKTEST_MODELS = (
    "equal_weight",
    "min_variance",
    "risk_parity",
    "historical_bl",
    "momentum_bl",
    "historical_mpt",
    "lightweight_bl",
    "arima_transformer_bl",
    "transformer_bl",
)


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
        return views, uncertainties, failed

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
    return views, uncertainties, failed


def _black_litterman_weights(train_prices, view_method, forecast_horizon, max_asset_weight, risk_free_rate):
    tickers = list(train_prices.columns)
    covariance = _safe_covariance(train_prices)
    views, uncertainties, failed = _forecast_views(train_prices, view_method, forecast_horizon)
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
    }


def _model_weights(model_name, train_prices, forecast_horizon, max_asset_weight, risk_free_rate):
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

    if model_name == "historical_mpt":
        mu = _calculate_historical_cagr(train_prices)
        weights = _efficient_frontier_weights(mu, covariance, max_asset_weight, "max_sharpe", risk_free_rate)
        return weights, {"failed_forecast_count": 0, "avg_forecast_confidence": None}

    bl_methods = {
        "historical_bl": "historical",
        "momentum_bl": "momentum",
        "lightweight_bl": "lightweight",
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


def _promotion_decision(summary_by_model):
    candidate = summary_by_model.get("arima_transformer_bl")
    required_baselines = ("equal_weight", "historical_bl", "risk_parity", "momentum_bl")
    baselines = {
        name: summary_by_model.get(name)
        for name in required_baselines
    }
    reasons = []
    missing = [name for name, metrics in baselines.items() if not metrics]
    if not candidate or missing:
        missing_reasons = []
        if not candidate:
            missing_reasons.append("Candidate model arima_transformer_bl is missing.")
        if missing:
            missing_reasons.append(f"Required comparison models are missing: {', '.join(missing)}.")
        return {
            "candidate_model": "arima_transformer_bl",
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
        reasons.append("ARIMA + Transformer produced no-view forecasts.")

    if reasons:
        return {
            "candidate_model": "arima_transformer_bl",
            "status": "not_promoted",
            "reasons": reasons,
        }
    return {
        "candidate_model": "arima_transformer_bl",
        "status": "candidate_requires_multi_universe_confirmation",
        "reasons": [
            "Single backtest passed local baseline checks, but default promotion requires SP500, DOW, and custom basket confirmation."
        ],
    }


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
    risk_free_rate=0.02,
    initial_value=10000.0,
):
    data = _clean_price_frame(price_data)
    if start_date:
        data = data[data.index >= pd.Timestamp(start_date)]
    if end_date:
        data = data[data.index <= pd.Timestamp(end_date)]
    if len(data) < int(train_window) + 2:
        raise ValueError("Not enough rows for train_window plus one out-of-sample period")

    models = tuple(models or DEFAULT_BACKTEST_MODELS)
    unsupported = sorted(set(models) - set(DEFAULT_BACKTEST_MODELS))
    if unsupported:
        raise ValueError(f"Unsupported backtest models: {unsupported}")

    train_window = int(train_window)
    rebalance_frequency = max(1, int(rebalance_frequency))
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
        }
        for model in models
    }
    rebalance_records = []
    warnings = []

    for rebalance_index in range(train_window, len(data) - 1, rebalance_frequency):
        current_date = data.index[rebalance_index]
        next_index = min(rebalance_index + rebalance_frequency, len(data) - 1)
        train_prices = data.iloc[rebalance_index - train_window:rebalance_index].dropna(axis=1)
        current_prices = data.iloc[rebalance_index].reindex(train_prices.columns)
        period_prices = data.iloc[rebalance_index:next_index + 1].reindex(columns=train_prices.columns).ffill()
        if train_prices.empty or current_prices.dropna().empty:
            warnings.append(f"Skipped {current_date.date()}: no valid training/current prices")
            continue

        for model in models:
            weights, diagnostics = _model_weights(
                model,
                train_prices,
                forecast_horizon,
                max_asset_weight,
                risk_free_rate,
            )
            weights = _normalize_weights(weights, train_prices.columns)
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
            if diagnostics.get("avg_forecast_confidence") is not None:
                state["forecast_confidences"].append(float(diagnostics["avg_forecast_confidence"]))

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
            "risk_free_rate": float(risk_free_rate),
            "initial_value": float(initial_value),
        },
        "models": list(models),
        "summary_by_model": summary_by_model,
        "rebalance_records": rebalance_records,
        "promotion_decision": _promotion_decision(summary_by_model),
        "warnings": warnings,
    }
