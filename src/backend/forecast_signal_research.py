"""Signal-only diagnostics for portfolio forecast research."""

import numpy as np
import pandas as pd

from portfolio_alpha_v2 import (
    factor_residual_forward_returns,
    point_in_time_snapshot,
)


ANNUAL_LOG_RETURN_CLIP = 0.69


def build_completed_forward_targets(
    price_data,
    horizon=63,
    target_kind="relative",
    training_end=None,
    step=None,
    minimum_history=126,
    point_in_time_features=None,
):
    """Build only targets whose forward window completes by training cutoff."""
    prices = pd.DataFrame(price_data).copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index().apply(pd.to_numeric, errors="coerce")
    if training_end is not None:
        prices = prices.loc[prices.index <= pd.Timestamp(training_end)]
    horizon = max(1, int(horizon))
    step = horizon if step is None else max(1, int(step))
    target_kind = str(target_kind).strip().lower()
    if target_kind not in {"absolute", "relative", "factor_residual"}:
        raise ValueError(
            "target_kind must be absolute, relative, or factor_residual"
        )
    if target_kind == "factor_residual" and point_in_time_features is None:
        raise ValueError(
            "factor_residual targets require point_in_time_features"
        )

    last_position = len(prices) - horizon - 1
    positions = (
        []
        if last_position < int(minimum_history) - 1
        else range(int(minimum_history) - 1, last_position + 1, step)
    )
    records = []
    for position in positions:
        as_of = prices.index[position]
        forward_end = prices.index[position + horizon]
        returns = (
            prices.iloc[position + horizon] / prices.iloc[position] - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        factor_diagnostics = None
        if target_kind == "relative":
            target = returns - float(returns.median(skipna=True))
        elif target_kind == "factor_residual":
            snapshot = point_in_time_snapshot(
                point_in_time_features,
                as_of,
                tickers=prices.columns,
            )
            target, factor_diagnostics = factor_residual_forward_returns(
                returns,
                prices.iloc[:position + 1],
                snapshot,
            )
        else:
            target = returns

        for ticker, value in target.dropna().items():
            records.append({
                "as_of_date": as_of,
                "forward_end_date": forward_end,
                "ticker": ticker,
                "target": float(value),
                "target_kind": target_kind,
                "factor_r_squared": (
                    None
                    if factor_diagnostics is None
                    else factor_diagnostics.get("r_squared")
                ),
            })
    return pd.DataFrame.from_records(
        records,
        columns=(
            "as_of_date",
            "forward_end_date",
            "ticker",
            "target",
            "target_kind",
            "factor_r_squared",
        ),
    )


def prediction_distribution_diagnostics(
    predictions,
    annual_clip=ANNUAL_LOG_RETURN_CLIP,
):
    """Measure coverage, clipping, ties, dispersion, and uncertainty."""
    rows = list(predictions or [])
    values = pd.Series(
        [row.get("expected_return") for row in rows],
        dtype=float,
    ).replace([np.inf, -np.inf], np.nan)
    uncertainties = pd.Series(
        [row.get("uncertainty") for row in rows],
        dtype=float,
    ).replace([np.inf, -np.inf], np.nan)
    valid = values.dropna()
    clip = abs(float(annual_clip))
    boundary = valid.abs().sub(clip).abs() <= 1e-8
    rounded_unique = int(valid.round(10).nunique()) if len(valid) else 0

    quantiles = {}
    if len(valid):
        quantiles = {
            str(quantile): float(valid.quantile(quantile))
            for quantile in (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)
        }
    finite_uncertainty = uncertainties.dropna()
    return {
        "prediction_count": int(len(rows)),
        "valid_count": int(len(valid)),
        "no_view_count": int(values.isna().sum()),
        "coverage_rate": float(len(valid) / len(rows)) if rows else 0.0,
        "mean": None if valid.empty else float(valid.mean()),
        "standard_deviation": (
            None if valid.empty else float(valid.std(ddof=0))
        ),
        "quantiles": quantiles,
        "annual_clip": clip,
        "positive_boundary_count": int((valid >= clip - 1e-8).sum()),
        "negative_boundary_count": int((valid <= -clip + 1e-8).sum()),
        "boundary_saturation_count": int(boundary.sum()),
        "boundary_saturation_rate": (
            float(boundary.mean()) if len(valid) else None
        ),
        "unique_value_count": rounded_unique,
        "unique_value_ratio": (
            float(rounded_unique / len(valid)) if len(valid) else None
        ),
        "tie_rate": (
            float(1.0 - rounded_unique / len(valid)) if len(valid) else None
        ),
        "uncertainty_count": int(len(finite_uncertainty)),
        "mean_reported_uncertainty": (
            None
            if finite_uncertainty.empty
            else float(finite_uncertainty.mean())
        ),
    }


def empirical_oos_uncertainty(
    predictions,
    realized_returns,
    reported_uncertainties=None,
    nominal_coverage=0.80,
    minimum_observations=20,
):
    """Calibrate uncertainty from completed OOS residuals in matching units."""
    predicted = pd.Series(predictions, dtype=float)
    realized = pd.Series(realized_returns, dtype=float).reindex(predicted.index)
    valid = (
        predicted.replace([np.inf, -np.inf], np.nan).notna()
        & realized.replace([np.inf, -np.inf], np.nan).notna()
    )
    residuals = (realized.loc[valid] - predicted.loc[valid]).astype(float)
    count = int(len(residuals))
    if count < int(minimum_observations):
        raise ValueError(
            "Insufficient OOS residuals for uncertainty calibration: "
            f"{count} < {int(minimum_observations)}"
        )

    nominal = float(np.clip(nominal_coverage, 0.50, 0.99))
    absolute_errors = residuals.abs()
    calibrated_radius = float(absolute_errors.quantile(nominal))
    result = {
        "observation_count": count,
        "nominal_coverage": nominal,
        "calibrated_absolute_error_radius": calibrated_radius,
        "mae": float(absolute_errors.mean()),
        "rmse": float(np.sqrt(np.mean(np.square(residuals)))),
        "bias": float(residuals.mean()),
    }
    if reported_uncertainties is not None:
        reported = pd.Series(
            reported_uncertainties,
            dtype=float,
        ).reindex(predicted.index).loc[valid]
        usable = reported.notna() & (reported >= 0)
        result["reported_uncertainty_count"] = int(usable.sum())
        result["reported_uncertainty_coverage"] = (
            None
            if not bool(usable.any())
            else float(
                (
                    absolute_errors.loc[usable.index[usable]]
                    <= reported.loc[usable]
                ).mean()
            )
        )
    return result


def cross_sectional_rank_diagnostics(periods):
    """Aggregate period-level rank IC, top-bottom spread, and coverage."""
    rows = []
    for period in periods or []:
        scores = pd.Series(period.get("scores", {}), dtype=float)
        realized = pd.Series(
            period.get("realized_returns", {}),
            dtype=float,
        ).reindex(scores.index)
        valid = scores.notna() & realized.notna()
        if int(valid.sum()) < 2:
            continue
        rank_ic = scores.loc[valid].corr(realized.loc[valid], method="spearman")
        order = scores.loc[valid].sort_values()
        bucket_size = max(1, int(np.ceil(len(order) * 0.20)))
        bottom = order.index[:bucket_size]
        top = order.index[-bucket_size:]
        rows.append({
            "rank_ic": None if pd.isna(rank_ic) else float(rank_ic),
            "top_bottom_spread": float(
                realized.loc[top].mean() - realized.loc[bottom].mean()
            ),
            "coverage_rate": float(valid.sum() / len(scores)) if len(scores) else 0.0,
        })

    rank_ics = [row["rank_ic"] for row in rows if row["rank_ic"] is not None]
    spreads = [row["top_bottom_spread"] for row in rows]
    return {
        "period_count": int(len(rows)),
        "mean_rank_ic": None if not rank_ics else float(np.mean(rank_ics)),
        "positive_rank_ic_rate": (
            None
            if not rank_ics
            else float(np.mean(np.asarray(rank_ics) > 0.0))
        ),
        "mean_top_bottom_spread": (
            None if not spreads else float(np.mean(spreads))
        ),
        "mean_coverage_rate": (
            None
            if not rows
            else float(np.mean([row["coverage_rate"] for row in rows]))
        ),
    }


def signal_only_gate(
    rank_diagnostics,
    distribution_diagnostics,
    minimum_periods=8,
    minimum_coverage=0.80,
    maximum_saturation_rate=0.10,
    maximum_tie_rate=0.25,
):
    """Reject weak forecast signals before portfolio construction."""
    reasons = []
    if int(rank_diagnostics.get("period_count", 0)) < int(minimum_periods):
        reasons.append("Insufficient completed OOS signal periods.")
    if (
        rank_diagnostics.get("mean_rank_ic") is None
        or rank_diagnostics["mean_rank_ic"] <= 0.0
    ):
        reasons.append("Mean OOS cross-sectional rank IC is not positive.")
    if (
        rank_diagnostics.get("positive_rank_ic_rate") is None
        or rank_diagnostics["positive_rank_ic_rate"] < 0.50
    ):
        reasons.append("Positive OOS rank IC rate is below 50%.")
    if (
        rank_diagnostics.get("mean_top_bottom_spread") is None
        or rank_diagnostics["mean_top_bottom_spread"] <= 0.0
    ):
        reasons.append("Mean OOS top-minus-bottom spread is not positive.")
    if (
        distribution_diagnostics.get("coverage_rate", 0.0)
        < float(minimum_coverage)
    ):
        reasons.append("Forecast coverage is below the configured minimum.")
    saturation_rate = distribution_diagnostics.get("boundary_saturation_rate")
    if (
        saturation_rate is not None
        and saturation_rate > float(maximum_saturation_rate)
    ):
        reasons.append("Forecast boundary saturation is too high.")
    tie_rate = distribution_diagnostics.get("tie_rate")
    if tie_rate is not None and tie_rate > float(maximum_tie_rate):
        reasons.append("Forecast tie rate is too high.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }
