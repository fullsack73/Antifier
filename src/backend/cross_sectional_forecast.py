"""Pooled cross-sectional forecast baselines for signal-only research."""

import time
import tracemalloc

import numpy as np
import pandas as pd

from forecast_signal_research import (
    cross_sectional_rank_diagnostics,
    empirical_oos_uncertainty,
    paired_rank_signal_block_bootstrap,
    prediction_distribution_diagnostics,
    rank_signal_block_bootstrap,
    signal_only_gate,
)
from portfolio_statistics import holm_bonferroni
from portfolio_alpha_v2 import (
    PIT_ALPHA_FEATURES,
    factor_residual_forward_returns,
    point_in_time_snapshot,
)
from universe_manifest import (
    normalize_universe_manifest,
    universe_snapshot,
)


POOLED_FEATURE_COLUMNS = (
    "momentum_1m",
    "momentum_3m",
    "momentum_6m",
    "momentum_12_1",
    "low_volatility_1m",
    "low_volatility_3m",
    "drawdown_6m",
    "market_beta_6m",
)
PIT_MISSING_FEATURE_COLUMNS = tuple(
    f"{column}_missing" for column in PIT_ALPHA_FEATURES
)
FACTOR_POOLED_FEATURE_COLUMNS = (
    POOLED_FEATURE_COLUMNS
    + PIT_ALPHA_FEATURES
    + PIT_MISSING_FEATURE_COLUMNS
)
QUALITY_POOLED_FEATURE_COLUMNS = (
    "quality",
    "profitability",
    "profitability_missing",
)
DEFAULT_NESTED_RIDGE_PENALTIES = (1.0, 5.0, 20.0, 100.0)
FACTOR_FULL_OBJECTIVES = {
    "factor_residual_ridge",
    "factor_residual_nested_ridge",
    "factor_residual_rank_nested_ridge",
    "factor_residual_market_nested_ridge",
}
NESTED_RIDGE_OBJECTIVES = {
    "factor_residual_nested_ridge",
    "factor_residual_rank_nested_ridge",
    "factor_residual_market_nested_ridge",
}
RANK_TARGET_OBJECTIVES = {
    "listwise_rank_ridge",
    "factor_residual_rank_nested_ridge",
}
POOLED_OBJECTIVES = (
    "absolute_ridge",
    "relative_ridge",
    "factor_residual_price_ridge",
    "factor_residual_ridge",
    "factor_residual_nested_ridge",
    "factor_residual_rank_nested_ridge",
    "factor_residual_market_nested_ridge",
    "factor_residual_quality_ridge",
    "pairwise_ridge",
    "listwise_rank_ridge",
)


def _clean_prices(price_data):
    prices = pd.DataFrame(price_data).copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index().apply(pd.to_numeric, errors="coerce")
    prices = prices.replace([np.inf, -np.inf], np.nan).ffill()
    return prices.dropna(axis=1, how="all")


def _cross_sectional_standardize(values):
    series = pd.Series(values, dtype=float).replace([np.inf, -np.inf], np.nan)
    valid = series.dropna()
    result = pd.Series(np.nan, index=series.index, dtype=float)
    if len(valid) < 2:
        return result
    winsorized = valid.clip(
        lower=float(valid.quantile(0.05)),
        upper=float(valid.quantile(0.95)),
    )
    scale = float(winsorized.std(ddof=0))
    if scale <= 1e-12:
        result.loc[valid.index] = 0.0
    else:
        result.loc[valid.index] = (
            (winsorized - float(winsorized.mean())) / scale
        ).clip(-3.0, 3.0)
    return result


def _market_beta(price_history, lookback=126):
    prices = _clean_prices(price_history).tail(max(21, int(lookback)) + 1)
    returns = prices.pct_change().replace([np.inf, -np.inf], np.nan)
    market = returns.mean(axis=1, skipna=True)
    variance = float(market.var(ddof=0))
    if not np.isfinite(variance) or variance <= 1e-12:
        return pd.Series(np.nan, index=prices.columns, dtype=float)
    return returns.apply(
        lambda values: values.cov(market, ddof=0) / variance
        if int(values.notna().sum()) >= 20
        else np.nan
    )


def pooled_price_features(price_history):
    """Build PIT-safe cross-sectional price features at history end."""
    prices = _clean_prices(price_history)
    tickers = list(prices.columns)
    features = pd.DataFrame(index=tickers, columns=POOLED_FEATURE_COLUMNS, dtype=float)
    if len(prices) < 253:
        return features

    latest = prices.iloc[-1]
    features["momentum_1m"] = latest / prices.iloc[-22] - 1.0
    features["momentum_3m"] = latest / prices.iloc[-64] - 1.0
    features["momentum_6m"] = latest / prices.iloc[-127] - 1.0
    features["momentum_12_1"] = prices.iloc[-22] / prices.iloc[-253] - 1.0

    returns = prices.pct_change()
    features["low_volatility_1m"] = -returns.tail(21).std(ddof=0)
    features["low_volatility_3m"] = -returns.tail(63).std(ddof=0)
    six_month = prices.tail(126)
    features["drawdown_6m"] = (six_month / six_month.cummax() - 1.0).min()
    features["market_beta_6m"] = _market_beta(prices, lookback=126)

    for column in POOLED_FEATURE_COLUMNS:
        features[column] = _cross_sectional_standardize(features[column])
    return features


def pooled_point_in_time_features(
    point_in_time_features,
    as_of_date,
    tickers,
):
    """Build neutral-imputed fundamental predictors known by ``as_of_date``."""
    ticker_order = [str(ticker).strip().upper() for ticker in tickers]
    snapshot = point_in_time_snapshot(
        point_in_time_features,
        as_of_date,
        tickers=ticker_order,
    ).reindex(ticker_order)
    features = pd.DataFrame(
        index=ticker_order,
        columns=PIT_ALPHA_FEATURES + PIT_MISSING_FEATURE_COLUMNS,
        dtype=float,
    )
    for column in PIT_ALPHA_FEATURES:
        raw = pd.to_numeric(snapshot[column], errors="coerce")
        features[column] = _cross_sectional_standardize(raw).fillna(0.0)
        features[f"{column}_missing"] = raw.isna().astype(float)
    return features


def _forward_target(
    prices,
    position,
    horizon,
    target_kind,
    point_in_time_features=None,
    active_tickers=None,
    market_returns_history=None,
):
    returns = (
        prices.iloc[position + horizon] / prices.iloc[position] - 1.0
    ).replace([np.inf, -np.inf], np.nan)
    if active_tickers is not None:
        returns = returns.reindex(active_tickers)
    if target_kind == "absolute":
        return returns, None
    if target_kind == "relative":
        return returns - float(returns.median(skipna=True)), None
    if target_kind == "factor_residual":
        if point_in_time_features is None:
            raise ValueError(
                "factor_residual target requires point_in_time_features"
            )
        snapshot = point_in_time_snapshot(
            point_in_time_features,
            prices.index[position],
            tickers=returns.index,
        )
        return factor_residual_forward_returns(
            returns,
            prices.loc[
                prices.index[:position + 1],
                returns.index,
            ],
            snapshot,
            market_returns_history=market_returns_history,
        )
    raise ValueError(f"Unsupported target kind: {target_kind}")


def _objective_target_kind(objective):
    if objective == "absolute_ridge":
        return "absolute"
    if objective in {
        "factor_residual_price_ridge",
        "factor_residual_ridge",
        "factor_residual_nested_ridge",
        "factor_residual_rank_nested_ridge",
        "factor_residual_market_nested_ridge",
        "factor_residual_quality_ridge",
    }:
        return "factor_residual"
    return "relative"


def _fit_pooled_ridge(
    training_rows,
    objective,
    ridge_penalty,
    minimum_observations,
    feature_columns,
):
    frame = pd.DataFrame(training_rows)
    valid = (
        frame["target"].notna()
        & frame[list(feature_columns)].notna().all(axis=1)
    )
    frame = frame.loc[valid].copy()
    if len(frame) < int(minimum_observations):
        raise ValueError(
            "Insufficient pooled training observations: "
            f"{len(frame)} < {int(minimum_observations)}"
        )

    x = frame.loc[:, feature_columns].to_numpy(dtype=float)
    y = frame["target"].to_numpy(dtype=float)
    fit_row_count = len(frame)
    if objective in RANK_TARGET_OBJECTIVES:
        ranked = frame.groupby("as_of_date")["target"].rank(
            method="average",
            pct=True,
        )
        y = (ranked - frame.groupby("as_of_date")["target"].transform(
            lambda values: values.rank(method="average", pct=True).mean()
        )).to_numpy(dtype=float)
    elif objective == "pairwise_ridge":
        pair_x = []
        pair_y = []
        for _, group in frame.groupby("as_of_date", sort=True):
            group_x = group.loc[:, feature_columns].to_numpy(dtype=float)
            group_y = group["target"].to_numpy(dtype=float)
            for left in range(len(group)):
                for right in range(left + 1, len(group)):
                    difference = float(group_y[left] - group_y[right])
                    if abs(difference) <= 1e-12:
                        continue
                    pair_x.append(group_x[left] - group_x[right])
                    pair_y.append(difference)
        if len(pair_x) < int(minimum_observations):
            raise ValueError(
                "Insufficient pooled pairwise observations: "
                f"{len(pair_x)} < {int(minimum_observations)}"
            )
        x = np.asarray(pair_x, dtype=float)
        y = np.asarray(pair_y, dtype=float)
        fit_row_count = len(pair_x)

    use_intercept = objective != "pairwise_ridge"
    design = (
        np.column_stack([np.ones(len(x)), x])
        if use_intercept
        else x
    )
    penalty = np.eye(design.shape[1], dtype=float) * max(
        0.0,
        float(ridge_penalty),
    )
    if use_intercept:
        penalty[0, 0] = 0.0
    fitted = np.linalg.pinv(design.T @ design + penalty) @ design.T @ y
    intercept = float(fitted[0]) if use_intercept else 0.0
    coefficients = fitted[1:] if use_intercept else fitted
    return intercept, pd.Series(
        coefficients,
        index=feature_columns,
        dtype=float,
    ), {
        "source_row_count": int(len(frame)),
        "fit_row_count": int(fit_row_count),
        "ridge_penalty": float(ridge_penalty),
    }


def _select_nested_ridge_penalty(
    training_rows,
    penalties,
    minimum_observations,
    feature_columns,
    validation_periods=3,
    fit_objective="factor_residual_ridge",
):
    """Select regularization using only completed inner time folds."""
    frame = pd.DataFrame(training_rows).copy()
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
    frame["forward_end_date"] = pd.to_datetime(
        frame["forward_end_date"]
    )
    dates = sorted(frame["as_of_date"].dropna().unique())
    validation_count = min(
        max(1, int(validation_periods)),
        max(0, len(dates) - 2),
    )
    validation_dates = dates[-validation_count:] if validation_count else []
    diagnostics = {}
    for penalty in penalties:
        rank_ics = []
        fold_rows = []
        for validation_date in validation_dates:
            inner_training = frame.loc[
                frame["forward_end_date"] <= validation_date
            ].to_dict(orient="records")
            validation = frame.loc[
                frame["as_of_date"] == validation_date
            ].copy()
            try:
                intercept, coefficients, fit = _fit_pooled_ridge(
                    inner_training,
                    fit_objective,
                    penalty,
                    minimum_observations,
                    feature_columns,
                )
            except ValueError as exc:
                if str(exc).startswith("Insufficient pooled"):
                    continue
                raise
            scores = (
                validation.loc[:, feature_columns]
                .mul(coefficients, axis=1)
                .sum(axis=1, min_count=len(feature_columns))
                + intercept
            )
            target = pd.to_numeric(
                validation["target"],
                errors="coerce",
            )
            valid = scores.notna() & target.notna()
            rank_ic = (
                None
                if int(valid.sum()) < 3
                else scores.loc[valid].corr(
                    target.loc[valid],
                    method="spearman",
                )
            )
            if rank_ic is not None and np.isfinite(rank_ic):
                rank_ics.append(float(rank_ic))
                fold_rows.append({
                    "validation_date": pd.Timestamp(
                        validation_date
                    ).strftime("%Y-%m-%d"),
                    "rank_ic": float(rank_ic),
                    "training_row_count": fit["source_row_count"],
                    "training_latest_forward_end": pd.Timestamp(
                        max(
                            row["forward_end_date"]
                            for row in inner_training
                        )
                    ).strftime("%Y-%m-%d"),
                    "validation_row_count": int(valid.sum()),
                })
        diagnostics[str(float(penalty))] = {
            "mean_rank_ic": (
                None if not rank_ics else float(np.mean(rank_ics))
            ),
            "fold_count": int(len(rank_ics)),
            "folds": fold_rows,
        }
    eligible = [
        (result["mean_rank_ic"], float(penalty))
        for penalty, result in (
            (float(key), value)
            for key, value in diagnostics.items()
        )
        if result["mean_rank_ic"] is not None
    ]
    selected = (
        float(max(penalties))
        if not eligible
        else max(eligible, key=lambda item: (item[0], item[1]))[1]
    )
    return selected, {
        "selection_metric": "mean inner-fold cross-sectional rank IC",
        "validation_periods": int(validation_count),
        "validation_dates": [
            pd.Timestamp(value).strftime("%Y-%m-%d")
            for value in validation_dates
        ],
        "candidates": diagnostics,
        "selected_penalty": float(selected),
    }


def _feature_signal_diagnostics(
    snapshots,
    evaluation_positions,
    feature_columns,
):
    diagnostics = {}
    p_values = {}
    for column in feature_columns:
        periods = []
        for position in evaluation_positions:
            features = snapshots[position]["features"]
            target = snapshots[position]["target"].reindex(features.index)
            scores = pd.to_numeric(
                features[column],
                errors="coerce",
            )
            valid = scores.notna() & target.notna()
            periods.append({
                "scores": {
                    ticker: float(scores.loc[ticker])
                    for ticker in scores.index[valid]
                },
                "realized_returns": {
                    ticker: float(target.loc[ticker])
                    for ticker in target.index[valid]
                },
            })
        rank = cross_sectional_rank_diagnostics(periods)
        bootstrap = rank_signal_block_bootstrap(periods)
        diagnostics[column] = {
            "rank_diagnostics": rank,
            "rank_bootstrap": bootstrap,
        }
        p_values[column] = (
            None
            if bootstrap.get("status") != "ok"
            else 1.0 - min(
                bootstrap["probability"]["positive_mean_rank_ic"],
                bootstrap["probability"][
                    "positive_mean_top_bottom_spread"
                ],
            )
        )
    multiple_testing = holm_bonferroni(p_values)
    for column, result in diagnostics.items():
        result["multiple_testing"] = multiple_testing.get(column)
    return diagnostics


def walk_forward_pooled_ridge(
    price_data,
    objective="relative_ridge",
    horizon=63,
    rebalance_step=None,
    minimum_feature_history=253,
    minimum_training_periods=8,
    maximum_training_periods=12,
    minimum_observations=40,
    ridge_penalty=5.0,
    nested_ridge_penalties=DEFAULT_NESTED_RIDGE_PENALTIES,
    nested_validation_periods=3,
    nominal_uncertainty_coverage=0.80,
    point_in_time_features=None,
    market_factor_returns=None,
    universe_manifest=None,
    evaluation_start=None,
    evaluation_end=None,
):
    """Evaluate one pooled objective with strictly prior completed targets."""
    if objective not in POOLED_OBJECTIVES:
        raise ValueError(f"Unsupported pooled objective: {objective}")
    nested_ridge_penalties = tuple(
        sorted({
            float(value)
            for value in nested_ridge_penalties
            if np.isfinite(float(value)) and float(value) >= 0.0
        })
    )
    if objective in NESTED_RIDGE_OBJECTIVES and not (
        nested_ridge_penalties
    ):
        raise ValueError(
            "Nested ridge requires at least one non-negative penalty"
        )
    prices = _clean_prices(price_data)
    normalized_market_factor = None
    if market_factor_returns is not None:
        normalized_market_factor = pd.Series(
            market_factor_returns,
            dtype=float,
        ).copy()
        normalized_market_factor.index = pd.to_datetime(
            normalized_market_factor.index
        )
        normalized_market_factor = (
            normalized_market_factor.sort_index()
            .replace([np.inf, -np.inf], np.nan)
        )
    if (
        objective == "factor_residual_market_nested_ridge"
        and normalized_market_factor is None
    ):
        raise ValueError(
            "External-market nested ridge requires market_factor_returns"
        )
    horizon = max(1, int(horizon))
    step = horizon if rebalance_step is None else max(1, int(rebalance_step))
    positions = list(
        range(
            max(253, int(minimum_feature_history)) - 1,
            len(prices) - horizon,
            step,
        )
    )
    target_kind = _objective_target_kind(objective)
    if objective in FACTOR_FULL_OBJECTIVES:
        feature_columns = FACTOR_POOLED_FEATURE_COLUMNS
    elif objective == "factor_residual_quality_ridge":
        feature_columns = QUALITY_POOLED_FEATURE_COLUMNS
    else:
        feature_columns = POOLED_FEATURE_COLUMNS
    normalized_universe = (
        None
        if universe_manifest is None
        else normalize_universe_manifest(universe_manifest)
    )
    evaluation_start = (
        None if evaluation_start is None else pd.Timestamp(evaluation_start)
    )
    evaluation_end = (
        None if evaluation_end is None else pd.Timestamp(evaluation_end)
    )
    if (
        evaluation_start is not None
        and evaluation_end is not None
        and evaluation_start > evaluation_end
    ):
        raise ValueError("evaluation_start must be on or before evaluation_end")
    evaluation_records = []
    pending_residuals = []
    fit_seconds = 0.0
    fit_count = 0
    coefficient_history = []
    evaluated_positions = []

    tracemalloc.start()
    started_at = time.perf_counter()
    snapshots = {}
    for position in positions:
        requested_active_tickers = (
            list(prices.columns)
            if normalized_universe is None
            else universe_snapshot(
                normalized_universe,
                prices.index[position],
            )
        )
        active_tickers = [
            ticker
            for ticker in requested_active_tickers
            if ticker in prices.columns
        ]
        features = pooled_price_features(
            prices.iloc[:position + 1].loc[:, active_tickers]
        )
        if objective in FACTOR_FULL_OBJECTIVES | {
            "factor_residual_quality_ridge",
        }:
            pit_features = pooled_point_in_time_features(
                point_in_time_features,
                prices.index[position],
                active_tickers,
            )
            features = (
                pit_features.loc[:, QUALITY_POOLED_FEATURE_COLUMNS]
                if objective == "factor_residual_quality_ridge"
                else features.join(pit_features)
            )
        target, target_diagnostics = _forward_target(
            prices,
            position,
            horizon,
            target_kind,
            point_in_time_features=point_in_time_features,
            active_tickers=active_tickers,
            market_returns_history=(
                None
                if objective != "factor_residual_market_nested_ridge"
                else normalized_market_factor.reindex(
                    prices.index[:position + 1]
                )
            ),
        )
        valid = (
            features.notna().all(axis=1)
            & target.reindex(features.index).notna()
        )
        snapshots[position] = {
            "features": features,
            "target": target,
            "target_diagnostics": target_diagnostics,
            "active_tickers": active_tickers,
            "requested_active_tickers": requested_active_tickers,
            "training_rows": [
                {
                    "as_of_date": prices.index[position],
                    "forward_end_date": prices.index[position + horizon],
                    "ticker": ticker,
                    "target": float(target.loc[ticker]),
                    **{
                        column: float(features.loc[ticker, column])
                        for column in feature_columns
                    },
                }
                for ticker in features.index[valid]
            ],
        }

    evaluation_positions = [
        position
        for position in positions
        if (
            evaluation_start is None
            or prices.index[position] >= evaluation_start
        )
        and (
            evaluation_end is None
            or prices.index[position] <= evaluation_end
        )
    ]
    for evaluation_position in evaluation_positions:
        eligible_training_positions = [
            position
            for position in positions
            if position + horizon <= evaluation_position
        ]
        if len(eligible_training_positions) < int(minimum_training_periods):
            continue
        training_positions = eligible_training_positions[
            -max(1, int(maximum_training_periods)):
        ]
        training_rows = [
            row
            for position in training_positions
            for row in snapshots[position]["training_rows"]
        ]
        if len(training_rows) < int(minimum_observations):
            continue
        fit_started_at = time.perf_counter()
        try:
            effective_penalty = float(ridge_penalty)
            nested_diagnostics = None
            if objective in NESTED_RIDGE_OBJECTIVES:
                effective_penalty, nested_diagnostics = (
                    _select_nested_ridge_penalty(
                        training_rows,
                        nested_ridge_penalties,
                        minimum_observations,
                        feature_columns,
                        validation_periods=nested_validation_periods,
                        fit_objective=objective,
                    )
                )
            intercept, coefficients, fit_diagnostics = _fit_pooled_ridge(
                training_rows,
                objective,
                effective_penalty,
                minimum_observations,
                feature_columns,
            )
            fit_diagnostics["nested_selection"] = nested_diagnostics
        except ValueError as exc:
            if str(exc).startswith("Insufficient pooled"):
                continue
            raise
        fit_seconds += time.perf_counter() - fit_started_at
        fit_count += 1
        coefficient_history.append(coefficients)
        evaluated_positions.append(evaluation_position)

        as_of_date = prices.index[evaluation_position]
        features = snapshots[evaluation_position]["features"]
        raw_predictions = features.mul(coefficients, axis=1).sum(
            axis=1,
            min_count=len(feature_columns),
        ) + intercept
        realized_target = snapshots[evaluation_position]["target"].reindex(
            raw_predictions.index
        )
        eligible_residuals = [
            item["residual"]
            for item in pending_residuals
            if item["available_date"] <= as_of_date
        ]
        uncertainty = (
            None
            if len(eligible_residuals) < int(minimum_observations)
            else float(
                pd.Series(eligible_residuals).abs().quantile(
                    float(nominal_uncertainty_coverage)
                )
            )
        )
        valid = raw_predictions.notna() & realized_target.notna()
        active_universe_size = int(
            len(snapshots[evaluation_position]["requested_active_tickers"])
        )
        available_universe_size = int(
            len(snapshots[evaluation_position]["active_tickers"])
        )
        prediction_count = int(valid.sum())
        evaluation_records.append({
            "as_of_date": as_of_date.strftime("%Y-%m-%d"),
            "forward_end_date": prices.index[
                evaluation_position + horizon
            ].strftime("%Y-%m-%d"),
            "train_start_date": prices.index[
                training_positions[0]
            ].strftime("%Y-%m-%d"),
            "train_end_date": prices.index[
                training_positions[-1] + horizon
            ].strftime("%Y-%m-%d"),
            "scores": {
                ticker: float(raw_predictions.loc[ticker])
                for ticker in raw_predictions.index[valid]
            },
            "realized_returns": {
                ticker: float(realized_target.loc[ticker])
                for ticker in realized_target.index[valid]
            },
            "reported_uncertainty": uncertainty,
            "active_universe_size": active_universe_size,
            "available_universe_size": available_universe_size,
            "missing_active_tickers": sorted(
                set(
                    snapshots[evaluation_position][
                        "requested_active_tickers"
                    ]
                )
                - set(snapshots[evaluation_position]["active_tickers"])
            ),
            "active_prediction_count": prediction_count,
            "active_universe_coverage_rate": (
                float(prediction_count / active_universe_size)
                if active_universe_size
                else 0.0
            ),
            "fit": fit_diagnostics,
            "target_diagnostics": snapshots[evaluation_position][
                "target_diagnostics"
            ],
            "coefficients": {
                name: float(value)
                for name, value in coefficients.items()
            },
        })
        forward_end = prices.index[evaluation_position + horizon]
        for ticker in raw_predictions.index[valid]:
            pending_residuals.append({
                "available_date": forward_end,
                "residual": float(
                    realized_target.loc[ticker] - raw_predictions.loc[ticker]
                ),
            })

    elapsed_seconds = time.perf_counter() - started_at
    _, peak_memory_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    periods = [
        {
            "period_id": record["as_of_date"],
            "scores": record["scores"],
            "realized_returns": record["realized_returns"],
        }
        for record in evaluation_records
    ]
    rank_diagnostics = cross_sectional_rank_diagnostics(periods)
    prediction_rows = [
        {
            "expected_return": value,
            "uncertainty": record["reported_uncertainty"],
        }
        for record in evaluation_records
        for value in record["scores"].values()
    ]
    distribution = prediction_distribution_diagnostics(prediction_rows)
    active_total = sum(
        record["active_universe_size"] for record in evaluation_records
    )
    active_prediction_total = sum(
        record["active_prediction_count"] for record in evaluation_records
    )
    period_universe_coverages = [
        record["active_universe_coverage_rate"]
        for record in evaluation_records
    ]
    distribution["active_universe_coverage_rate"] = (
        float(active_prediction_total / active_total)
        if active_total
        else 0.0
    )
    distribution["mean_period_universe_coverage_rate"] = (
        None
        if not period_universe_coverages
        else float(np.mean(period_universe_coverages))
    )
    distribution["minimum_period_universe_coverage_rate"] = (
        None
        if not period_universe_coverages
        else float(np.min(period_universe_coverages))
    )
    prediction_series = {}
    realized_series = {}
    uncertainty_series = {}
    for record in evaluation_records:
        for ticker, value in record["scores"].items():
            key = (record["as_of_date"], ticker)
            prediction_series[key] = value
            realized_series[key] = record["realized_returns"].get(ticker)
            uncertainty_series[key] = record["reported_uncertainty"]
    uncertainty_diagnostics = None
    if len(prediction_series) >= int(minimum_observations):
        uncertainty_diagnostics = empirical_oos_uncertainty(
            prediction_series,
            realized_series,
            reported_uncertainties=uncertainty_series,
            nominal_coverage=nominal_uncertainty_coverage,
            minimum_observations=minimum_observations,
        )
    rank_bootstrap = rank_signal_block_bootstrap(periods)
    gate = signal_only_gate(
        rank_diagnostics,
        distribution,
        rank_bootstrap=rank_bootstrap,
    )
    prediction_count = len(prediction_rows)
    mean_coefficients = (
        pd.concat(coefficient_history, axis=1).mean(axis=1)
        if coefficient_history
        else pd.Series(dtype=float)
    )
    feature_diagnostics = _feature_signal_diagnostics(
        snapshots,
        evaluated_positions,
        feature_columns,
    )
    return {
        "objective": objective,
        "target_kind": target_kind,
        "settings": {
            "horizon": horizon,
            "rebalance_step": step,
            "minimum_feature_history": int(minimum_feature_history),
            "minimum_training_periods": int(minimum_training_periods),
            "maximum_training_periods": int(maximum_training_periods),
            "minimum_observations": int(minimum_observations),
            "ridge_penalty": float(ridge_penalty),
            "nested_ridge_penalties": [
                float(value) for value in nested_ridge_penalties
            ],
            "nested_validation_periods": int(
                nested_validation_periods
            ),
            "nominal_uncertainty_coverage": float(
                nominal_uncertainty_coverage
            ),
            "dated_universe_manifest": normalized_universe is not None,
            "evaluation_start": (
                None
                if evaluation_start is None
                else evaluation_start.strftime("%Y-%m-%d")
            ),
            "evaluation_end": (
                None
                if evaluation_end is None
                else evaluation_end.strftime("%Y-%m-%d")
            ),
            "feature_columns": list(feature_columns),
            "training_target_transform": (
                "cross_sectional_percentile_rank_centered"
                if objective in RANK_TARGET_OBJECTIVES
                else "raw_forward_target"
            ),
            "point_in_time_fundamentals": (
                objective in FACTOR_FULL_OBJECTIVES
                | {"factor_residual_quality_ridge"}
            ),
        },
        "rank_diagnostics": rank_diagnostics,
        "rank_bootstrap": rank_bootstrap,
        "distribution_diagnostics": distribution,
        "uncertainty_diagnostics": uncertainty_diagnostics,
        "signal_only_gate": gate,
        "cost": {
            "elapsed_seconds": float(elapsed_seconds),
            "fit_seconds": float(fit_seconds),
            "fit_count": int(fit_count),
            "prediction_count": int(prediction_count),
            "predictions_per_second": (
                float(prediction_count / elapsed_seconds)
                if elapsed_seconds > 0
                else None
            ),
            "peak_memory_bytes": int(peak_memory_bytes),
        },
        "mean_coefficients": {
            name: float(value)
            for name, value in mean_coefficients.items()
        },
        "feature_diagnostics": feature_diagnostics,
        "records": evaluation_records,
    }


def compare_pooled_objectives(
    price_data,
    objectives=None,
    **kwargs,
):
    """Run comparable signal-only pooled objectives on one research split."""
    selected = tuple(objectives or (
        "absolute_ridge",
        "relative_ridge",
        "pairwise_ridge",
        "listwise_rank_ridge",
    ))
    runs = {
        objective: walk_forward_pooled_ridge(
            price_data,
            objective=objective,
            **kwargs,
        )
        for objective in selected
    }
    passed = [
        objective
        for objective, result in runs.items()
        if result["signal_only_gate"]["status"] == "passed"
    ]
    p_values = {
        objective: (
            None
            if result["rank_bootstrap"].get("status") != "ok"
            else 1.0 - min(
                result["rank_bootstrap"]["probability"][
                    "positive_mean_rank_ic"
                ],
                result["rank_bootstrap"]["probability"][
                    "positive_mean_top_bottom_spread"
                ],
            )
        )
        for objective, result in runs.items()
    }
    multiple_testing = holm_bonferroni(p_values)
    passed = [
        objective
        for objective in passed
        if multiple_testing.get(objective, {}).get("significant", False)
    ]
    paired_improvement = {}
    paired_comparisons = (
        (
            "factor_residual_nested_ridge",
            "factor_residual_ridge",
        ),
        (
            "factor_residual_market_nested_ridge",
            "factor_residual_nested_ridge",
        ),
        (
            "factor_residual_rank_nested_ridge",
            "factor_residual_nested_ridge",
        ),
    )
    for nested_name, baseline_name in paired_comparisons:
        if nested_name not in runs or baseline_name not in runs:
            continue
        candidate_periods = [
            {
                "period_id": record["as_of_date"],
                "scores": record["scores"],
                "realized_returns": record["realized_returns"],
            }
            for record in runs[nested_name]["records"]
        ]
        baseline_periods = [
            {
                "period_id": record["as_of_date"],
                "scores": record["scores"],
                "realized_returns": record["realized_returns"],
            }
            for record in runs[baseline_name]["records"]
        ]
        result = paired_rank_signal_block_bootstrap(
            candidate_periods,
            baseline_periods,
        )
        probability = result.get("probability") or {}
        result["gate"] = {
            "status": (
                "passed"
                if (
                    result.get("status") == "ok"
                    and probability.get("higher_mean_rank_ic", 0.0)
                    >= 0.95
                    and probability.get(
                        "higher_mean_top_bottom_spread",
                        0.0,
                    )
                    >= 0.95
                )
                else "rejected"
            ),
            "minimum_probability": 0.95,
        }
        paired_improvement[f"{nested_name}_vs_{baseline_name}"] = result
    return {
        "objectives": list(selected),
        "passed_objectives": passed,
        "multiple_testing": multiple_testing,
        "paired_improvement": paired_improvement,
        "selection_status": (
            "no_signal_candidate"
            if not passed
            else "manual_review_required"
        ),
        "runs": runs,
    }
