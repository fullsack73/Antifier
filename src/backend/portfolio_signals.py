"""Robust portfolio signals used by optimizer research paths."""

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252
MOMENTUM_SKIP_DAYS = 21
MOMENTUM_LOOKBACK_DAYS = 252
SIX_MONTH_MOMENTUM_LOOKBACK_DAYS = 126
MOMENTUM_VIEW_UNCERTAINTY = 0.20
SIGNAL_STACK_VIEW_UNCERTAINTY = 0.40
FORECAST_RANK_VIEW_UNCERTAINTY = 0.50


def _clean_price_frame(price_data):
    data = pd.DataFrame(price_data).copy()
    data.index = pd.to_datetime(data.index)
    data = data.sort_index()
    data = data.apply(pd.to_numeric, errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).ffill()
    return data.dropna(axis=1, how="all")


def cap_and_normalize_weights(weights, max_asset_weight=None):
    """Normalize long-only weights while respecting a per-asset cap when feasible."""
    series = (
        pd.Series(weights, dtype=float)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .clip(lower=0.0)
    )
    if series.empty:
        return series

    total = float(series.sum())
    if total <= 0:
        series = pd.Series(1.0 / len(series), index=series.index)
    else:
        series = series / total

    try:
        cap = float(max_asset_weight)
    except (TypeError, ValueError):
        cap = None
    if cap is None or not np.isfinite(cap) or cap <= 0 or cap >= 1:
        return series

    if len(series) * cap < 1:
        cap = min(1.0, (1.0 / len(series)) + 1e-9)

    capped = series.copy()
    for _ in range(len(capped) + 2):
        over = capped > cap
        if not bool(over.any()):
            break
        excess = float((capped[over] - cap).sum())
        capped.loc[over] = cap
        under = ~over
        under_sum = float(capped[under].sum())
        if under_sum <= 0 or excess <= 0:
            break
        capped.loc[under] += capped.loc[under] / under_sum * excess

    total = float(capped.sum())
    if total <= 0:
        return pd.Series(1.0 / len(capped), index=capped.index)
    return capped / total


def risk_parity(price_data, max_asset_weight=0.2):
    """Inverse-volatility risk-parity approximation from trailing daily returns."""
    data = _clean_price_frame(price_data)
    if data.empty:
        return pd.Series(dtype=float)

    returns = data.pct_change().replace([np.inf, -np.inf], np.nan).dropna(how="all")
    vol = returns.std(ddof=0).replace([np.inf, -np.inf], np.nan)
    inv_vol = 1.0 / vol.where(vol > 0)
    inv_vol = inv_vol.reindex(data.columns).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return cap_and_normalize_weights(inv_vol, max_asset_weight=max_asset_weight)


def rank_to_unit_scores(values, higher_is_better=True):
    """Cross-sectional rank score in [-1, 1] with NaN preserved."""
    series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan)
    valid = series.dropna()
    scores = pd.Series(np.nan, index=series.index, dtype=float)
    if valid.empty:
        return scores
    if len(valid) == 1:
        scores.loc[valid.index] = 0.0
        return scores

    ranks = valid.rank(method="average", pct=True, ascending=bool(higher_is_better))
    centered = ranks - float(ranks.mean())
    max_abs = float(centered.abs().max())
    scores.loc[valid.index] = 0.0 if max_abs <= 0 else centered / max_abs
    return scores


def momentum_rank(price_data, lookback=MOMENTUM_LOOKBACK_DAYS, skip=MOMENTUM_SKIP_DAYS):
    """Cross-sectional momentum rank score in [-1, 1]."""
    data = _clean_price_frame(price_data)
    lookback = int(lookback)
    skip = int(skip)
    if data.empty or lookback <= 1 or skip < 0 or lookback <= skip or len(data) < lookback:
        return pd.Series(np.nan, index=data.columns)

    start_prices = data.iloc[-lookback].replace(0.0, np.nan)
    end_prices = data.iloc[-(skip + 1)] if skip > 0 else data.iloc[-1]
    raw_momentum = (end_prices / start_prices - 1.0).replace([np.inf, -np.inf], np.nan)
    return rank_to_unit_scores(raw_momentum, higher_is_better=True).reindex(data.columns)


def momentum_12_1(price_data, lookback=MOMENTUM_LOOKBACK_DAYS, skip=MOMENTUM_SKIP_DAYS):
    """Cross-sectional 12-1 momentum rank score in [-1, 1], excluding the latest month."""
    return momentum_rank(price_data, lookback=lookback, skip=skip)


def momentum_6m(price_data, lookback=SIX_MONTH_MOMENTUM_LOOKBACK_DAYS):
    """Six-month cross-sectional momentum rank score in [-1, 1]."""
    return momentum_rank(price_data, lookback=lookback, skip=0)


def volatility_score(price_data, lookback=MOMENTUM_LOOKBACK_DAYS):
    """Low-volatility rank score in [-1, 1], where lower trailing vol is better."""
    data = _clean_price_frame(price_data)
    if data.empty:
        return pd.Series(dtype=float)
    window = data.tail(max(2, int(lookback)))
    returns = window.pct_change().replace([np.inf, -np.inf], np.nan).dropna(how="all")
    vol = returns.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)
    return rank_to_unit_scores(vol.reindex(data.columns), higher_is_better=False)


def drawdown_score(price_data, lookback=MOMENTUM_LOOKBACK_DAYS):
    """Drawdown rank score in [-1, 1], where shallower trailing drawdown is better."""
    data = _clean_price_frame(price_data)
    if data.empty:
        return pd.Series(dtype=float)
    window = data.tail(max(2, int(lookback)))
    drawdowns = window / window.cummax() - 1.0
    max_drawdowns = drawdowns.min().replace([np.inf, -np.inf], np.nan)
    return rank_to_unit_scores(max_drawdowns.reindex(data.columns), higher_is_better=True)


def momentum_tilt_weights(price_data, lookback=MOMENTUM_LOOKBACK_DAYS, skip=MOMENTUM_SKIP_DAYS,
                          max_asset_weight=0.2):
    """Long-only momentum tilt weights from cross-sectional rank scores."""
    data = _clean_price_frame(price_data)
    scores = momentum_rank(data, lookback=lookback, skip=skip)
    raw = (scores + 1.0).clip(lower=0.0).fillna(0.0)
    return cap_and_normalize_weights(raw.reindex(data.columns), max_asset_weight=max_asset_weight)


def low_volatility_tilt(price_data, max_asset_weight=0.2):
    """Long-only low-volatility tilt weights from trailing risk ranks."""
    data = _clean_price_frame(price_data)
    scores = volatility_score(data)
    raw = (scores + 1.0).clip(lower=0.0).fillna(0.0)
    return cap_and_normalize_weights(raw.reindex(data.columns), max_asset_weight=max_asset_weight)


def market_cap_weight(market_caps, tickers=None, max_asset_weight=0.2):
    """Market-cap weights when market caps are supplied, falling back to an empty series."""
    caps = pd.Series(market_caps or {}, dtype=float).replace([np.inf, -np.inf], np.nan)
    if tickers is not None:
        caps = caps.reindex(list(tickers))
    caps = caps.clip(lower=0.0).fillna(0.0)
    if caps.empty or float(caps.sum()) <= 0:
        return pd.Series(0.0, index=[] if tickers is None else list(tickers), dtype=float)
    return cap_and_normalize_weights(caps, max_asset_weight=max_asset_weight)


def _fundamental_score_series(fundamentals, tickers):
    if not fundamentals:
        return pd.Series(np.nan, index=tickers, dtype=float)
    values = {}
    candidate_keys = (
        "valuation_quality_score",
        "quality_score",
        "financial_score",
        "score",
    )
    for ticker in tickers:
        item = fundamentals.get(ticker) if isinstance(fundamentals, dict) else None
        if isinstance(item, dict):
            raw = next((item.get(key) for key in candidate_keys if item.get(key) is not None), np.nan)
        else:
            raw = item
        values[ticker] = raw
    return rank_to_unit_scores(pd.Series(values, dtype=float), higher_is_better=True)


def combined_signal_score(price_data, fundamentals=None, forecast_rank=None, component_weights=None):
    """
    Combine cross-sectional momentum, volatility, drawdown, optional fundamentals,
    and optional forecast rank into one weak rank score.
    """
    data = _clean_price_frame(price_data)
    tickers = list(data.columns)
    if not tickers:
        return pd.Series(dtype=float)

    components = {
        "momentum": momentum_12_1(data),
        "volatility": volatility_score(data),
        "drawdown": drawdown_score(data),
    }
    fundamental_scores = _fundamental_score_series(fundamentals, tickers)
    if not fundamental_scores.dropna().empty:
        components["fundamentals"] = fundamental_scores
    if forecast_rank is not None:
        forecast_scores = rank_to_unit_scores(pd.Series(forecast_rank).reindex(tickers), higher_is_better=True)
        if not forecast_scores.dropna().empty:
            components["forecast_rank"] = forecast_scores

    weights = {
        "momentum": 0.40,
        "volatility": 0.25,
        "drawdown": 0.20,
        "fundamentals": 0.15,
        "forecast_rank": 0.15,
    }
    if component_weights:
        weights.update(component_weights)

    weighted_sum = pd.Series(0.0, index=tickers)
    total_weight = pd.Series(0.0, index=tickers)
    for name, scores in components.items():
        weight = max(0.0, float(weights.get(name, 0.0)))
        aligned = pd.Series(scores).reindex(tickers)
        valid = aligned.notna()
        weighted_sum.loc[valid] += aligned.loc[valid] * weight
        total_weight.loc[valid] += weight

    combined = weighted_sum / total_weight.replace(0.0, np.nan)
    return combined.clip(lower=-1.0, upper=1.0)


def signal_stack_bl_views(
    price_data,
    prior_returns=None,
    fundamentals=None,
    forecast_rank=None,
    view_strength=0.035,
    max_view_shift=0.07,
):
    """Weak BL absolute-return views derived from a cross-sectional signal stack."""
    data = _clean_price_frame(price_data)
    scores = combined_signal_score(data, fundamentals=fundamentals, forecast_rank=forecast_rank)
    prior = pd.Series(prior_returns, dtype=float).reindex(data.columns) if prior_returns is not None else pd.Series(0.0, index=data.columns)
    prior = prior.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    delta = (scores * abs(float(view_strength))).clip(
        lower=-abs(float(max_view_shift)),
        upper=abs(float(max_view_shift)),
    )
    views = prior + delta.fillna(0.0)
    views.loc[scores.isna()] = np.nan
    return views.clip(lower=-0.99, upper=10.0)


def momentum_bl_views(
    price_data,
    prior_returns=None,
    view_strength=0.04,
    max_view_shift=0.10,
):
    """Weak BL absolute-return views derived from momentum ranks, not price forecasts."""
    data = _clean_price_frame(price_data)
    scores = momentum_12_1(data)
    prior = pd.Series(prior_returns, dtype=float).reindex(data.columns) if prior_returns is not None else pd.Series(0.0, index=data.columns)
    prior = prior.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    try:
        strength = abs(float(view_strength))
    except (TypeError, ValueError):
        strength = 0.04
    try:
        max_shift = abs(float(max_view_shift))
    except (TypeError, ValueError):
        max_shift = 0.10

    delta = (scores * strength).clip(lower=-max_shift, upper=max_shift)
    views = prior + delta.fillna(0.0)
    views.loc[scores.isna()] = np.nan
    return views.clip(lower=-0.99, upper=10.0)
