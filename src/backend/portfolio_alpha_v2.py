"""Point-in-time, factor-neutral cross-sectional alpha research helpers."""

import numpy as np
import pandas as pd

from portfolio_signals import rank_to_unit_scores


PIT_REQUIRED_COLUMNS = (
    "available_date",
    "ticker",
    "sector",
    "market_cap",
    "quality",
    "profitability",
    "valuation",
    "liquidity",
)
PIT_ALPHA_FEATURES = (
    "quality",
    "profitability",
    "valuation",
    "liquidity",
)
PIT_CASH_ACCRUAL_FEATURES = ("cash_accrual_quality",)
PIT_SEASONAL_EARNINGS_FEATURES = ("seasonal_earnings_change",)
FACTOR_NEUTRAL_TARGET_ACTIVE_SHARE = 0.20


def normalize_point_in_time_features(
    feature_data,
    extra_feature_columns=(),
):
    """
    Validate long-form point-in-time features.

    Feature values must already be directionally oriented: higher quality,
    profitability, value attractiveness, and liquidity are better. ``available_date``
    is the first date on which the row could have been known.
    """
    frame = pd.DataFrame(feature_data).copy()
    extra_feature_columns = tuple(
        dict.fromkeys(str(column) for column in extra_feature_columns)
    )
    overlap = set(extra_feature_columns).intersection(
        PIT_REQUIRED_COLUMNS
    )
    if overlap:
        raise ValueError(
            "Extra point-in-time feature columns overlap core columns: "
            + ", ".join(sorted(overlap))
        )
    missing = [column for column in PIT_REQUIRED_COLUMNS if column not in frame.columns]
    missing.extend(
        column
        for column in extra_feature_columns
        if column not in frame.columns
    )
    if missing:
        raise ValueError(
            "Point-in-time factor data is missing required columns: "
            + ", ".join(missing)
        )

    frame = frame.loc[
        :,
        PIT_REQUIRED_COLUMNS + extra_feature_columns,
    ].copy()
    frame["available_date"] = pd.to_datetime(frame["available_date"], errors="coerce")
    if frame["available_date"].isna().any():
        raise ValueError("Point-in-time factor data contains invalid available_date values")

    missing_labels = frame["ticker"].isna() | frame["sector"].isna()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["sector"] = frame["sector"].astype(str).str.strip()
    if missing_labels.any() or (frame["ticker"] == "").any() or (frame["sector"] == "").any():
        raise ValueError("Point-in-time factor data requires non-empty ticker and sector")

    numeric_columns = (
        ("market_cap",)
        + PIT_ALPHA_FEATURES
        + extra_feature_columns
    )
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    if frame["market_cap"].isna().any() or (frame["market_cap"] <= 0).any():
        raise ValueError("Point-in-time factor data requires positive market_cap values")

    duplicate = frame.duplicated(["ticker", "available_date"], keep=False)
    if duplicate.any():
        raise ValueError(
            "Point-in-time factor data has duplicate ticker/available_date rows"
        )
    return frame.sort_values(["available_date", "ticker"]).reset_index(drop=True)


def point_in_time_snapshot(
    feature_data,
    as_of_date,
    tickers=None,
    extra_feature_columns=(),
):
    """Return latest row known by ``as_of_date`` for each requested ticker."""
    frame = normalize_point_in_time_features(
        feature_data,
        extra_feature_columns=extra_feature_columns,
    )
    as_of = pd.Timestamp(as_of_date)
    eligible = frame.loc[frame["available_date"] <= as_of].copy()
    if tickers is not None:
        ticker_order = [str(ticker).strip().upper() for ticker in tickers]
        eligible = eligible.loc[eligible["ticker"].isin(ticker_order)]
    else:
        ticker_order = None

    if eligible.empty:
        return eligible.set_index("ticker")
    latest = eligible.drop_duplicates("ticker", keep="last").set_index("ticker")
    if ticker_order is not None:
        latest = latest.reindex(ticker_order).dropna(subset=["available_date"])
    return latest


def _cross_sectional_zscore(values, clip=3.0):
    series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan)
    valid = series.dropna()
    result = pd.Series(np.nan, index=series.index, dtype=float)
    if len(valid) < 2:
        return result
    lower = float(valid.quantile(0.05))
    upper = float(valid.quantile(0.95))
    winsorized = valid.clip(lower=lower, upper=upper)
    scale = float(winsorized.std(ddof=0))
    if scale <= 1e-12:
        result.loc[valid.index] = 0.0
    else:
        result.loc[valid.index] = (
            (winsorized - float(winsorized.mean())) / scale
        ).clip(lower=-abs(float(clip)), upper=abs(float(clip)))
    return result


def _market_betas(price_history, market_returns_history=None):
    prices = pd.DataFrame(price_history).apply(pd.to_numeric, errors="coerce")
    returns = prices.pct_change(fill_method=None).replace(
        [np.inf, -np.inf],
        np.nan,
    )
    if market_returns_history is None:
        market = returns.mean(axis=1, skipna=True)
        market_source = "cross_sectional_equal_weight"
    else:
        market = pd.Series(
            market_returns_history,
            dtype=float,
        ).copy()
        market.index = pd.to_datetime(market.index)
        market = (
            market.sort_index()
            .reindex(returns.index)
            .replace([np.inf, -np.inf], np.nan)
        )
        market_source = "external_market_factor"
    market_variance = float(market.var(ddof=0))
    if not np.isfinite(market_variance) or market_variance <= 1e-12:
        return (
            pd.Series(np.nan, index=prices.columns, dtype=float),
            market_source,
        )
    return returns.apply(
        lambda values: values.cov(market, ddof=0) / market_variance
        if int(values.notna().sum()) >= 20
        else np.nan
    ), market_source


def factor_residual_forward_returns(
    forward_returns,
    price_history,
    snapshot,
    market_returns_history=None,
):
    """Remove beta, sector, and log-size common-factor exposure cross-sectionally."""
    returns = pd.Series(forward_returns, dtype=float).replace([np.inf, -np.inf], np.nan)
    factors = pd.DataFrame(index=returns.index)
    market_betas, market_beta_source = _market_betas(
        price_history,
        market_returns_history=market_returns_history,
    )
    factors["market_beta"] = market_betas.reindex(returns.index)
    factors["log_market_cap"] = np.log(
        pd.to_numeric(snapshot["market_cap"], errors="coerce").reindex(returns.index)
    )
    sectors = snapshot["sector"].reindex(returns.index)
    sector_count = int(sectors.dropna().nunique())
    sector_dummies = pd.get_dummies(sectors, prefix="sector", dtype=float)
    if len(sector_dummies.columns) > 1:
        sector_dummies = sector_dummies.iloc[:, 1:]
    else:
        sector_dummies = pd.DataFrame(index=returns.index)

    factors["market_beta"] = _cross_sectional_zscore(factors["market_beta"])
    factors["log_market_cap"] = _cross_sectional_zscore(factors["log_market_cap"])
    design = pd.concat([factors, sector_dummies], axis=1)
    valid = returns.notna() & design.notna().all(axis=1)
    minimum_rows = max(5, int(design.shape[1]) + 2)
    residuals = pd.Series(np.nan, index=returns.index, dtype=float)
    if int(valid.sum()) < minimum_rows:
        return residuals, {
            "observation_count": int(valid.sum()),
            "factor_count": int(design.shape[1]),
            "sector_count": sector_count,
            "sector_dummy_count": int(len(sector_dummies.columns)),
            "r_squared": None,
            "market_beta_source": market_beta_source,
        }

    x = design.loc[valid].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(x)), x])
    y = returns.loc[valid].to_numpy(dtype=float)
    penalty = np.eye(x.shape[1], dtype=float) * 1e-6
    penalty[0, 0] = 0.0
    coefficients = np.linalg.pinv(x.T @ x + penalty) @ x.T @ y
    fitted = x @ coefficients
    residual_values = y - fitted
    residuals.loc[valid] = residual_values
    total_sum_squares = float(np.sum((y - float(np.mean(y))) ** 2))
    residual_sum_squares = float(np.sum(residual_values ** 2))
    r_squared = (
        None
        if total_sum_squares <= 1e-12
        else float(1.0 - residual_sum_squares / total_sum_squares)
    )
    return residuals, {
        "observation_count": int(valid.sum()),
        "factor_count": int(design.shape[1]),
        "sector_count": sector_count,
        "sector_dummy_count": int(len(sector_dummies.columns)),
        "r_squared": r_squared,
        "market_beta_source": market_beta_source,
    }


def _capped_signed_coefficients(coefficients, max_feature_weight):
    coefficients = pd.Series(coefficients, dtype=float).replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0.0)
    absolute = coefficients.abs()
    if float(absolute.sum()) <= 1e-12:
        return coefficients

    count = len(coefficients)
    cap = max(1.0 / max(1, count), min(1.0, float(max_feature_weight)))
    weights = absolute / float(absolute.sum())
    for _ in range(count + 2):
        over = weights > cap
        if not bool(over.any()):
            break
        excess = float((weights.loc[over] - cap).sum())
        weights.loc[over] = cap
        under = ~over
        under_total = float(weights.loc[under].sum())
        if excess <= 0 or under_total <= 0:
            break
        weights.loc[under] += weights.loc[under] / under_total * excess
    return np.sign(coefficients) * weights


def fit_regularized_alpha(
    feature_rows,
    targets,
    ridge_penalty=2.0,
    max_feature_weight=0.45,
    minimum_observations=40,
):
    """Fit transparent ridge coefficients with feature concentration control."""
    features = pd.DataFrame(feature_rows).reindex(columns=PIT_ALPHA_FEATURES)
    target = pd.Series(targets, dtype=float).reindex(features.index)
    valid = target.notna() & features.notna().all(axis=1)
    observation_count = int(valid.sum())
    if observation_count < int(minimum_observations):
        raise ValueError(
            "Insufficient point-in-time calibration observations: "
            f"{observation_count} < {int(minimum_observations)}"
        )

    x = features.loc[valid].to_numpy(dtype=float)
    y = target.loc[valid].to_numpy(dtype=float)
    x = x - x.mean(axis=0, keepdims=True)
    y = y - float(y.mean())
    penalty = max(0.0, float(ridge_penalty))
    raw = np.linalg.pinv(x.T @ x + penalty * np.eye(x.shape[1])) @ x.T @ y
    raw_coefficients = pd.Series(raw, index=PIT_ALPHA_FEATURES, dtype=float)
    coefficients = _capped_signed_coefficients(
        raw_coefficients,
        max_feature_weight=max_feature_weight,
    )
    if float(coefficients.abs().sum()) <= 1e-12:
        raise ValueError("Point-in-time calibration produced no usable alpha coefficients")
    if not np.isclose(float(coefficients.abs().sum()), 1.0, atol=1e-9):
        raise ValueError(
            "Point-in-time calibration coefficients are too concentrated "
            "for the configured feature weight cap"
        )
    return coefficients, {
        "observation_count": observation_count,
        "ridge_penalty": penalty,
        "max_feature_weight": float(max_feature_weight),
        "raw_coefficients": raw_coefficients.to_dict(),
        "coefficients": coefficients.to_dict(),
    }


def _snapshot_feature_scores(snapshot, tickers):
    scores = pd.DataFrame(index=list(tickers), columns=PIT_ALPHA_FEATURES, dtype=float)
    for column in PIT_ALPHA_FEATURES:
        scores[column] = _cross_sectional_zscore(
            pd.to_numeric(snapshot[column], errors="coerce").reindex(tickers)
        )
    return scores


def factor_neutral_cross_sectional_alpha(
    price_data,
    point_in_time_features,
    horizon=63,
    max_observations=8,
    minimum_history=126,
    minimum_observations=40,
    ridge_penalty=2.0,
    max_feature_weight=0.45,
):
    """Build v2 scores from PIT features and completed factor-residual targets."""
    prices = pd.DataFrame(price_data).copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index().apply(pd.to_numeric, errors="coerce")
    features = normalize_point_in_time_features(point_in_time_features)
    horizon = max(1, int(horizon))
    latest_position = len(prices) - horizon - 1
    if latest_position < int(minimum_history) - 1:
        positions = []
    else:
        positions = list(
            range(int(minimum_history) - 1, latest_position + 1, horizon)
        )[-max(1, int(max_observations)):]

    training_features = []
    training_targets = []
    rows = []
    for position in positions:
        as_of = prices.index[position]
        history = prices.iloc[:position + 1]
        snapshot = point_in_time_snapshot(features, as_of, tickers=prices.columns)
        feature_scores = _snapshot_feature_scores(snapshot, prices.columns)
        forward_returns = (
            prices.iloc[position + horizon] / prices.iloc[position] - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        residual_returns, factor_diagnostics = factor_residual_forward_returns(
            forward_returns,
            history,
            snapshot,
        )
        row_valid = feature_scores.notna().all(axis=1) & residual_returns.notna()
        for ticker in prices.columns[row_valid]:
            training_features.append(feature_scores.loc[ticker].to_dict())
            training_targets.append(float(residual_returns.loc[ticker]))
        rows.append({
            "as_of_date": as_of.strftime("%Y-%m-%d"),
            "forward_end_date": prices.index[position + horizon].strftime("%Y-%m-%d"),
            "latest_available_date": (
                None
                if snapshot.empty
                else snapshot["available_date"].max().strftime("%Y-%m-%d")
            ),
            "observation_count": int(row_valid.sum()),
            "factor_model": factor_diagnostics,
        })

    coefficients, fit_diagnostics = fit_regularized_alpha(
        training_features,
        training_targets,
        ridge_penalty=ridge_penalty,
        max_feature_weight=max_feature_weight,
        minimum_observations=minimum_observations,
    )
    current_as_of = prices.index[-1]
    current_snapshot = point_in_time_snapshot(
        features,
        current_as_of,
        tickers=prices.columns,
    )
    current_features = _snapshot_feature_scores(current_snapshot, prices.columns)
    raw_scores = current_features.mul(coefficients, axis=1).sum(
        axis=1,
        min_count=len(PIT_ALPHA_FEATURES),
    )
    scores = rank_to_unit_scores(raw_scores, higher_is_better=True).reindex(
        prices.columns
    )
    coverage_count = int(scores.notna().sum())
    return scores, {
        "model": "ridge",
        "feature_columns": list(PIT_ALPHA_FEATURES),
        "component_scores": {
            column: {
                ticker: float(value)
                for ticker, value in current_features[column].dropna().items()
            }
            for column in PIT_ALPHA_FEATURES
        },
        "component_weights": {
            name: float(value) for name, value in coefficients.items()
        },
        "calibration": {
            **fit_diagnostics,
            "horizon": horizon,
            "rows": rows,
        },
        "coverage_count": coverage_count,
        "coverage_rate": (
            float(coverage_count / len(prices.columns))
            if len(prices.columns)
            else 0.0
        ),
        "signal_as_of_date": current_as_of.strftime("%Y-%m-%d"),
        "latest_available_date": (
            None
            if current_snapshot.empty
            else current_snapshot["available_date"].max().strftime("%Y-%m-%d")
        ),
    }
