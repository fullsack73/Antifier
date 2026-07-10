"""Robust portfolio signals used by optimizer research paths."""

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252
MOMENTUM_SKIP_DAYS = 21
MOMENTUM_LOOKBACK_DAYS = 252
MOMENTUM_VIEW_UNCERTAINTY = 0.20


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


def momentum_12_1(price_data, lookback=MOMENTUM_LOOKBACK_DAYS, skip=MOMENTUM_SKIP_DAYS):
    """Cross-sectional 12-1 momentum rank score in [-1, 1], excluding the latest month."""
    data = _clean_price_frame(price_data)
    if data.empty or len(data) < int(lookback) or int(skip) <= 0 or int(lookback) <= int(skip):
        return pd.Series(np.nan, index=data.columns)

    start_prices = data.iloc[-int(lookback)].replace(0.0, np.nan)
    end_prices = data.iloc[-int(skip)]
    raw_momentum = (end_prices / start_prices - 1.0).replace([np.inf, -np.inf], np.nan)
    valid = raw_momentum.dropna()
    scores = pd.Series(np.nan, index=data.columns, dtype=float)
    if valid.empty:
        return scores
    if len(valid) == 1:
        scores.loc[valid.index] = 0.0
        return scores

    ranks = valid.rank(method="average", pct=True)
    centered = ranks - float(ranks.mean())
    max_abs = float(centered.abs().max())
    scores.loc[valid.index] = 0.0 if max_abs <= 0 else centered / max_abs
    return scores


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

