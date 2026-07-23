"""Robust portfolio signals used by optimizer research paths."""

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252
MOMENTUM_SKIP_DAYS = 21
MOMENTUM_LOOKBACK_DAYS = 252
SIX_MONTH_MOMENTUM_LOOKBACK_DAYS = 126
DUAL_HORIZON_MOMENTUM_COMPONENT_WEIGHTS = {
    "momentum_6m": 0.50,
    "momentum_12_1": 0.50,
}
SHORT_TERM_REVERSAL_DAYS = 21
MOMENTUM_VIEW_UNCERTAINTY = 0.20
SIGNAL_STACK_VIEW_UNCERTAINTY = 0.40
FORECAST_RANK_VIEW_UNCERTAINTY = 0.50
ADAPTIVE_ALPHA_TARGET_ACTIVE_SHARE = 0.20
ADAPTIVE_ALPHA_FALLBACK_WEIGHTS = {
    "momentum_12_1": 0.30,
    "momentum_6m": 0.20,
    "reversal_1m": 0.15,
    "low_volatility": 0.20,
    "drawdown": 0.15,
}


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

    capped = pd.Series(0.0, index=series.index, dtype=float)
    free = list(series.index)
    remaining = 1.0
    while free:
        free_values = series.loc[free].clip(lower=0.0)
        free_total = float(free_values.sum())
        allocation = (
            pd.Series(remaining / len(free), index=free, dtype=float)
            if free_total <= 0
            else free_values / free_total * remaining
        )
        over = allocation > cap
        if not bool(over.any()):
            capped.loc[free] = allocation
            remaining = 0.0
            break
        capped.loc[allocation.index[over]] = cap
        remaining -= cap * int(over.sum())
        free = list(allocation.index[~over])

    residual = 1.0 - float(capped.sum())
    if abs(residual) > 1e-12:
        room = (cap - capped).clip(lower=0.0)
        if residual > 0 and float(room.sum()) > 0:
            capped += room / float(room.sum()) * residual
        elif residual < 0:
            positive = capped > 0
            capped.loc[positive] += (
                capped.loc[positive] / float(capped.loc[positive].sum())
                * residual
            )
    return capped.clip(lower=0.0, upper=cap)


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


def profitability_momentum_scores(
    price_data,
    profitability_values,
    momentum_weight=0.50,
):
    """Blend trailing momentum with a point-in-time profitability rank."""
    data = _clean_price_frame(price_data)
    try:
        momentum_weight = float(momentum_weight)
    except (TypeError, ValueError) as exc:
        raise ValueError("momentum_weight must be between 0 and 1") from exc
    if (
        not np.isfinite(momentum_weight)
        or momentum_weight < 0.0
        or momentum_weight > 1.0
    ):
        raise ValueError("momentum_weight must be between 0 and 1")

    momentum = momentum_12_1(data)
    profitability = pd.Series(
        profitability_values,
        dtype=float,
    ).reindex(data.columns)
    profitability_rank = rank_to_unit_scores(
        profitability,
        higher_is_better=True,
    )
    combined = (
        momentum_weight * momentum
        + (1.0 - momentum_weight) * profitability_rank
    )
    return rank_to_unit_scores(
        combined.where(momentum.notna() & profitability_rank.notna()),
        higher_is_better=True,
    ).reindex(data.columns)


def _point_in_time_component_scores(component, as_of_date, tickers):
    """Return a ranked component snapshot available by ``as_of_date``."""
    if isinstance(component, pd.DataFrame):
        history = component.copy()
        history.index = pd.to_datetime(history.index)
        history = history.sort_index()
        history = history.loc[
            history.index <= pd.Timestamp(as_of_date)
        ]
        raw = (
            pd.Series(np.nan, index=tickers, dtype=float)
            if history.empty
            else pd.to_numeric(
                history.iloc[-1],
                errors="coerce",
            ).reindex(tickers)
        )
    else:
        raw = pd.Series(component, dtype=float).reindex(tickers)
    return rank_to_unit_scores(raw, higher_is_better=True).reindex(tickers)


def adaptive_factor_momentum_scores(
    price_data,
    factor_components,
    horizon=63,
    max_observations=12,
    prior_weights=None,
    prior_shrinkage=0.75,
    max_component_weight=0.60,
):
    """Shrink completed-period IC weights toward a fixed factor prior."""
    data = _clean_price_frame(price_data)
    tickers = list(data.columns)
    components = {
        str(name): value
        for name, value in dict(factor_components or {}).items()
    }
    component_names = ["momentum_12_1", *components]
    if len(component_names) < 2:
        raise ValueError(
            "Adaptive factor momentum requires a fundamental component"
        )
    prior_shrinkage = float(prior_shrinkage)
    if (
        not np.isfinite(prior_shrinkage)
        or prior_shrinkage < 0.0
        or prior_shrinkage > 1.0
    ):
        raise ValueError("prior_shrinkage must be between 0 and 1")

    default_factor_weight = 0.50 / max(1, len(components))
    prior = pd.Series(
        (
            {
                "momentum_12_1": 0.50,
                **{
                    name: default_factor_weight
                    for name in components
                },
            }
            if prior_weights is None
            else prior_weights
        ),
        index=component_names,
        dtype=float,
    )
    prior = cap_and_normalize_weights(
        prior,
        max_asset_weight=max_component_weight,
    )
    horizon = max(1, int(horizon))
    latest_signal_position = len(data) - horizon - 1
    positions = (
        []
        if latest_signal_position < MOMENTUM_LOOKBACK_DAYS - 1
        else list(
            range(
                MOMENTUM_LOOKBACK_DAYS - 1,
                latest_signal_position + 1,
                horizon,
            )
        )[-max(1, int(max_observations)):]
    )

    component_ics = {name: [] for name in component_names}
    calibration_rows = []
    for position in positions:
        as_of = data.index[position]
        history = data.iloc[:position + 1]
        scores = {
            "momentum_12_1": momentum_12_1(history),
            **{
                name: _point_in_time_component_scores(
                    component,
                    as_of,
                    tickers,
                )
                for name, component in components.items()
            },
        }
        forward_returns = (
            data.iloc[position + horizon] / data.iloc[position] - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        relative_returns = (
            forward_returns - float(forward_returns.median(skipna=True))
        )
        row_ics = {}
        for name, values in scores.items():
            rank_ic = _finite_spearman(values, relative_returns)
            row_ics[name] = rank_ic
            if rank_ic is not None:
                component_ics[name].append(rank_ic)
        calibration_rows.append({
            "as_of_date": as_of.strftime("%Y-%m-%d"),
            "forward_end_date": data.index[
                position + horizon
            ].strftime("%Y-%m-%d"),
            "component_rank_ic": row_ics,
        })

    raw_evidence = pd.Series(
        {
            name: (
                0.0
                if not values
                else max(0.0, float(np.mean(values)))
            )
            for name, values in component_ics.items()
        },
        dtype=float,
    )
    empirical = (
        prior
        if float(raw_evidence.sum()) <= 0.0
        else cap_and_normalize_weights(
            raw_evidence,
            max_asset_weight=max_component_weight,
        )
    )
    weights = cap_and_normalize_weights(
        prior_shrinkage * prior
        + (1.0 - prior_shrinkage) * empirical,
        max_asset_weight=max_component_weight,
    )

    as_of = data.index[-1] if not data.empty else pd.NaT
    current_scores = {
        "momentum_12_1": momentum_12_1(data),
        **{
            name: _point_in_time_component_scores(
                component,
                as_of,
                tickers,
            )
            for name, component in components.items()
        },
    }
    weighted = pd.Series(0.0, index=tickers, dtype=float)
    available = pd.Series(0.0, index=tickers, dtype=float)
    for name, scores in current_scores.items():
        aligned = pd.Series(scores, dtype=float).reindex(tickers)
        valid = aligned.notna()
        weighted.loc[valid] += aligned.loc[valid] * float(weights[name])
        available.loc[valid] += float(weights[name])
    combined = weighted / available.replace(0.0, np.nan)
    scores = rank_to_unit_scores(
        combined,
        higher_is_better=True,
    ).reindex(tickers)
    return scores, {
        "component_weights": {
            name: float(value) for name, value in weights.items()
        },
        "prior_weights": {
            name: float(value) for name, value in prior.items()
        },
        "empirical_weights": {
            name: float(value) for name, value in empirical.items()
        },
        "prior_shrinkage": prior_shrinkage,
        "max_component_weight": float(max_component_weight),
        "components": {
            name: {
                "mean_rank_ic": (
                    None if not values else float(np.mean(values))
                ),
                "observation_count": int(len(values)),
            }
            for name, values in component_ics.items()
        },
        "calibration_rows": calibration_rows,
        "coverage_count": int(scores.notna().sum()),
    }


def momentum_6m(price_data, lookback=SIX_MONTH_MOMENTUM_LOOKBACK_DAYS):
    """Six-month cross-sectional momentum rank score in [-1, 1]."""
    return momentum_rank(price_data, lookback=lookback, skip=0)


def factor_residual_momentum_scores(
    price_data,
    factor_data,
    beta_lookback=504,
    signal_lookback=MOMENTUM_LOOKBACK_DAYS,
    skip=MOMENTUM_SKIP_DAYS,
):
    """Rank trailing momentum after removing dated MKT/SMB/HML exposure."""
    prices = _clean_price_frame(price_data).dropna(how="any")
    factors = pd.DataFrame(factor_data).copy()
    factors.index = pd.to_datetime(factors.index)
    factors = (
        factors.sort_index()
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    required_factors = ["mkt_rf", "smb", "hml", "rf_daily"]
    missing = [
        column for column in required_factors
        if column not in factors
    ]
    if missing:
        raise ValueError(
            "Factor residual momentum requires: "
            + ", ".join(required_factors)
        )

    beta_window = max(int(signal_lookback), int(beta_lookback))
    signal_window = max(2, int(signal_lookback))
    skip = max(0, int(skip))
    required_price_rows = max(
        beta_window + 1,
        signal_window + skip + 1,
    )
    if prices.empty or len(prices) < required_price_rows:
        return pd.Series(np.nan, index=prices.columns), {
            "coverage_count": 0,
            "required_price_rows": int(required_price_rows),
        }

    returns = prices.pct_change().dropna(how="any")
    aligned_factors = factors.reindex(returns.index)
    beta_returns = returns.tail(beta_window)
    beta_factors = aligned_factors.reindex(beta_returns.index)
    if skip > 0:
        signal_returns = returns.iloc[
            -(signal_window + skip):-skip
        ]
    else:
        signal_returns = returns.tail(signal_window)
    signal_factors = aligned_factors.reindex(signal_returns.index)

    raw_scores = pd.Series(np.nan, index=prices.columns, dtype=float)
    exposures = {}
    design_columns = ["intercept", "mkt_rf", "smb", "hml"]
    for ticker in prices.columns:
        beta_frame = pd.concat(
            [
                beta_returns[ticker].rename("asset_return"),
                beta_factors[required_factors],
            ],
            axis=1,
        ).dropna()
        if len(beta_frame) < signal_window:
            continue
        design = np.column_stack([
            np.ones(len(beta_frame)),
            beta_frame[["mkt_rf", "smb", "hml"]].to_numpy(
                dtype=float
            ),
        ])
        excess = (
            beta_frame["asset_return"] - beta_frame["rf_daily"]
        ).to_numpy(dtype=float)
        coefficients, _, _, _ = np.linalg.lstsq(
            design,
            excess,
            rcond=None,
        )

        signal_frame = pd.concat(
            [
                signal_returns[ticker].rename("asset_return"),
                signal_factors[required_factors],
            ],
            axis=1,
        ).dropna()
        if len(signal_frame) < signal_window:
            continue
        signal_design = np.column_stack([
            np.ones(len(signal_frame)),
            signal_frame[["mkt_rf", "smb", "hml"]].to_numpy(
                dtype=float
            ),
        ])
        signal_excess = (
            signal_frame["asset_return"] - signal_frame["rf_daily"]
        ).to_numpy(dtype=float)
        residuals = signal_excess - signal_design @ coefficients
        residual_volatility = float(np.std(residuals, ddof=0))
        if residual_volatility <= 1e-12:
            continue
        raw_scores[ticker] = float(
            np.mean(residuals)
            / residual_volatility
            * np.sqrt(TRADING_DAYS_PER_YEAR)
        )
        exposures[str(ticker)] = {
            name: float(value)
            for name, value in zip(design_columns, coefficients)
        }

    scores = rank_to_unit_scores(
        raw_scores,
        higher_is_better=True,
    ).reindex(prices.columns)
    coverage_count = int(scores.notna().sum())
    return scores, {
        "method": "ff3_residual_sharpe_momentum",
        "beta_lookback": int(beta_window),
        "signal_lookback": int(signal_window),
        "skip": int(skip),
        "coverage_count": coverage_count,
        "coverage_rate": float(
            coverage_count / len(prices.columns)
        ),
        "raw_scores": {
            str(ticker): float(value)
            for ticker, value in raw_scores.dropna().items()
        },
        "factor_exposures": exposures,
    }


def dual_horizon_momentum_weights(price_data, max_asset_weight=0.2):
    """Blend fixed 6-month and 12-1 cross-sectional momentum ranks."""
    data = _clean_price_frame(price_data)
    if data.empty:
        return pd.Series(dtype=float)

    component_scores = {
        "momentum_6m": momentum_6m(data),
        "momentum_12_1": momentum_12_1(data),
    }
    composite = pd.Series(0.0, index=data.columns, dtype=float)
    available_weight = pd.Series(0.0, index=data.columns, dtype=float)
    for name, weight in DUAL_HORIZON_MOMENTUM_COMPONENT_WEIGHTS.items():
        aligned = component_scores[name].reindex(data.columns)
        valid = aligned.notna()
        composite.loc[valid] += aligned.loc[valid] * float(weight)
        available_weight.loc[valid] += float(weight)

    composite = composite / available_weight.replace(0.0, np.nan)
    raw = (composite + 1.0).clip(lower=0.0).fillna(0.0)
    return cap_and_normalize_weights(
        raw.reindex(data.columns),
        max_asset_weight=max_asset_weight,
    )


def short_term_reversal_score(price_data, lookback=SHORT_TERM_REVERSAL_DAYS):
    """One-month reversal rank, where recent relative losers rank higher."""
    data = _clean_price_frame(price_data)
    lookback = max(2, int(lookback))
    if data.empty or len(data) < lookback:
        return pd.Series(np.nan, index=data.columns)

    start_prices = data.iloc[-lookback].replace(0.0, np.nan)
    recent_return = (data.iloc[-1] / start_prices - 1.0).replace([np.inf, -np.inf], np.nan)
    return rank_to_unit_scores(recent_return, higher_is_better=False).reindex(data.columns)


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


def cross_sectional_alpha_components(price_data):
    """Price-only weak alpha components, each oriented so higher is better."""
    data = _clean_price_frame(price_data)
    return {
        "momentum_12_1": momentum_12_1(data),
        "momentum_6m": momentum_6m(data),
        "reversal_1m": short_term_reversal_score(data),
        "low_volatility": volatility_score(data),
        "drawdown": drawdown_score(data),
    }


def _finite_spearman(left, right):
    left = pd.Series(left, dtype=float).replace([np.inf, -np.inf], np.nan)
    right = pd.Series(right, dtype=float).reindex(left.index).replace([np.inf, -np.inf], np.nan)
    valid = left.notna() & right.notna()
    if int(valid.sum()) < 2 or left[valid].nunique() < 2 or right[valid].nunique() < 2:
        return None
    value = left[valid].corr(right[valid], method="spearman")
    return None if pd.isna(value) or not np.isfinite(value) else float(value)


def calibrate_cross_sectional_alpha(
    price_data,
    horizon=63,
    max_observations=8,
    minimum_history=63,
):
    """
    Estimate component reliability from completed forward windows inside training data.

    Feature snapshots use prices through their as-of date. Their forward relative
    returns end before the final training date, so live target generation never sees
    the backtest evaluation period.
    """
    data = _clean_price_frame(price_data)
    horizon = max(1, int(horizon))
    minimum_history = max(42, int(minimum_history))
    latest_signal_position = len(data) - horizon - 1
    if latest_signal_position < minimum_history - 1:
        positions = []
    else:
        positions = list(range(minimum_history - 1, latest_signal_position + 1, horizon))
        positions = positions[-max(1, int(max_observations)):]

    component_ics = {name: [] for name in ADAPTIVE_ALPHA_FALLBACK_WEIGHTS}
    calibration_rows = []
    for position in positions:
        history = data.iloc[:position + 1]
        forward_returns = (
            data.iloc[position + horizon].reindex(data.columns)
            / data.iloc[position].reindex(data.columns)
            - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        relative_returns = forward_returns - float(forward_returns.median(skipna=True))
        row_ics = {}
        for name, scores in cross_sectional_alpha_components(history).items():
            rank_ic = _finite_spearman(scores, relative_returns)
            row_ics[name] = rank_ic
            if rank_ic is not None:
                component_ics[name].append(rank_ic)
        calibration_rows.append({
            "as_of_date": data.index[position].strftime("%Y-%m-%d"),
            "forward_end_date": data.index[position + horizon].strftime("%Y-%m-%d"),
            "component_rank_ic": row_ics,
        })

    component_summary = {}
    raw_weights = {}
    for name, values in component_ics.items():
        count = len(values)
        mean_ic = None if not values else float(np.mean(values))
        median_ic = None if not values else float(np.median(values))
        positive_rate = None if not values else float(np.mean(np.asarray(values) > 0.0))
        reliability = float(count / (count + 3.0))
        raw_weight = 0.0 if mean_ic is None else max(0.0, mean_ic) * reliability
        raw_weights[name] = raw_weight
        component_summary[name] = {
            "mean_rank_ic": mean_ic,
            "median_rank_ic": median_ic,
            "positive_rank_ic_rate": positive_rate,
            "observation_count": int(count),
            "reliability": reliability,
        }

    positive_total = float(sum(raw_weights.values()))
    if positive_total > 0:
        weights = {name: float(value / positive_total) for name, value in raw_weights.items()}
        source = "rolling_positive_ic"
    else:
        weights = dict(ADAPTIVE_ALPHA_FALLBACK_WEIGHTS)
        source = "conservative_fallback"

    return {
        "horizon": horizon,
        "source": source,
        "weights": weights,
        "components": component_summary,
        "rows": calibration_rows,
    }


def adaptive_cross_sectional_alpha(price_data, horizon=63):
    """Combine weak signals with trailing IC calibration and return diagnostics."""
    data = _clean_price_frame(price_data)
    components = cross_sectional_alpha_components(data)
    calibration = calibrate_cross_sectional_alpha(data, horizon=horizon)
    weights = calibration["weights"]
    tickers = list(data.columns)

    weighted_sum = pd.Series(0.0, index=tickers, dtype=float)
    available_weight = pd.Series(0.0, index=tickers, dtype=float)
    for name, scores in components.items():
        weight = max(0.0, float(weights.get(name, 0.0)))
        aligned = pd.Series(scores, dtype=float).reindex(tickers)
        valid = aligned.notna()
        weighted_sum.loc[valid] += aligned.loc[valid] * weight
        available_weight.loc[valid] += weight

    raw_score = weighted_sum / available_weight.replace(0.0, np.nan)
    scores = rank_to_unit_scores(raw_score, higher_is_better=True).reindex(tickers)
    coverage = int(scores.notna().sum())
    return scores, {
        "component_scores": {
            name: {
                ticker: float(value)
                for ticker, value in pd.Series(component).dropna().items()
            }
            for name, component in components.items()
        },
        "component_weights": {name: float(weight) for name, weight in weights.items()},
        "calibration": calibration,
        "coverage_count": coverage,
        "coverage_rate": float(coverage / len(tickers)) if tickers else 0.0,
    }


def signal_tilt_weights(
    signal_scores,
    max_asset_weight=0.2,
    target_active_share=ADAPTIVE_ALPHA_TARGET_ACTIVE_SHARE,
):
    """Map cross-sectional scores to a transparent long-only equal-weight tilt."""
    scores = pd.Series(signal_scores, dtype=float).replace([np.inf, -np.inf], np.nan)
    if scores.empty:
        return scores

    base = pd.Series(1.0 / len(scores), index=scores.index, dtype=float)
    score_mean = scores.mean(skipna=True)
    score_mean = 0.0 if pd.isna(score_mean) else float(score_mean)
    centered = scores.fillna(score_mean)
    centered = centered - float(centered.mean())
    absolute_total = float(centered.abs().sum())
    if absolute_total <= 0:
        return cap_and_normalize_weights(base, max_asset_weight=max_asset_weight)

    desired_l1 = 2.0 * min(0.49, max(0.0, float(target_active_share)))
    tilted = (base + centered / absolute_total * desired_l1).clip(lower=0.0)
    return cap_and_normalize_weights(tilted, max_asset_weight=max_asset_weight)


def momentum_tilt_weights(price_data, lookback=MOMENTUM_LOOKBACK_DAYS, skip=MOMENTUM_SKIP_DAYS,
                          max_asset_weight=0.2):
    """Long-only momentum tilt weights from cross-sectional rank scores."""
    data = _clean_price_frame(price_data)
    scores = momentum_rank(data, lookback=lookback, skip=skip)
    raw = (scores + 1.0).clip(lower=0.0).fillna(0.0)
    return cap_and_normalize_weights(raw.reindex(data.columns), max_asset_weight=max_asset_weight)


def risk_managed_momentum_weights(
    price_data,
    momentum_lookback=SIX_MONTH_MOMENTUM_LOOKBACK_DAYS,
    volatility_lookback=63,
    max_asset_weight=0.2,
):
    """Scale positive cross-sectional momentum ranks by inverse recent volatility."""
    data = _clean_price_frame(price_data)
    scores = momentum_rank(
        data,
        lookback=momentum_lookback,
        skip=0,
    ).reindex(data.columns)
    returns = (
        data.tail(max(2, int(volatility_lookback)) + 1)
        .pct_change()
        .replace([np.inf, -np.inf], np.nan)
        .dropna(how="all")
    )
    volatility = returns.std(ddof=0).reindex(data.columns)
    inverse_volatility = 1.0 / volatility.where(volatility > 0)
    momentum_strength = ((scores + 1.0) / 2.0).clip(
        lower=0.0,
        upper=1.0,
    )
    raw = (
        momentum_strength
        * inverse_volatility.replace([np.inf, -np.inf], np.nan)
    ).fillna(0.0)
    return cap_and_normalize_weights(
        raw,
        max_asset_weight=max_asset_weight,
    )


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
