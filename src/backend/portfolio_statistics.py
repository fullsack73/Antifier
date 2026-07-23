"""Statistical comparison helpers for portfolio research backtests."""

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def _clean_return_pair(
    candidate_returns,
    baseline_returns,
    risk_free_daily_returns=None,
):
    series = [
        pd.Series(candidate_returns, dtype=float).rename("candidate"),
        pd.Series(baseline_returns, dtype=float).rename("baseline"),
    ]
    if risk_free_daily_returns is not None:
        risk_free = pd.Series(
            risk_free_daily_returns,
            dtype=float,
        ).rename("risk_free")
        risk_free.index = pd.to_datetime(risk_free.index)
        candidate_index = pd.to_datetime(series[0].index)
        risk_free = risk_free.sort_index().reindex(candidate_index).ffill()
        risk_free.index = series[0].index
        series.append(risk_free)
    frame = pd.concat(
        series,
        axis=1,
        join="inner",
    )
    return frame.replace([np.inf, -np.inf], np.nan).dropna()


def _return_statistics(
    values,
    risk_free_rate,
    risk_free_daily_returns=None,
):
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return {
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe": None,
        }
    annualized_return = float(np.mean(values) * TRADING_DAYS_PER_YEAR)
    annualized_volatility = float(
        np.std(values, ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)
    )
    annualized_excess_return = (
        annualized_return - float(risk_free_rate)
        if risk_free_daily_returns is None
        else float(
            np.mean(
                values - np.asarray(
                    risk_free_daily_returns,
                    dtype=float,
                )
            )
            * TRADING_DAYS_PER_YEAR
        )
    )
    sharpe = (
        None
        if annualized_volatility <= 1e-12
        else float(annualized_excess_return / annualized_volatility)
    )
    return {
        "annualized_return": annualized_return,
        "annualized_excess_return": annualized_excess_return,
        "annualized_volatility": annualized_volatility,
        "sharpe": sharpe,
    }


def paired_block_bootstrap(
    candidate_returns,
    baseline_returns,
    risk_free_rate=0.02,
    block_size=21,
    samples=2000,
    seed=42,
    risk_free_daily_returns=None,
):
    """Paired circular block bootstrap for dependent daily portfolio returns."""
    frame = _clean_return_pair(
        candidate_returns,
        baseline_returns,
        risk_free_daily_returns=risk_free_daily_returns,
    )
    observation_count = len(frame)
    block_size = max(2, min(int(block_size), max(2, observation_count)))
    samples = max(100, int(samples))
    if observation_count < block_size * 2:
        return {
            "status": "insufficient_data",
            "observation_count": int(observation_count),
            "block_size": int(block_size),
            "samples": int(samples),
        }

    columns = ["candidate", "baseline"]
    if "risk_free" in frame:
        columns.append("risk_free")
    values = frame[columns].values
    observed_risk_free = (
        None if values.shape[1] == 2 else values[:, 2]
    )
    observed_candidate = _return_statistics(
        values[:, 0],
        risk_free_rate,
        observed_risk_free,
    )
    observed_baseline = _return_statistics(
        values[:, 1],
        risk_free_rate,
        observed_risk_free,
    )
    observed_difference = {
        key: (
            None
            if observed_candidate[key] is None
            or observed_baseline[key] is None
            else float(observed_candidate[key] - observed_baseline[key])
        )
        for key in observed_candidate
    }

    rng = np.random.default_rng(int(seed))
    block_count = int(np.ceil(observation_count / block_size))
    volatility_differences = []
    sharpe_differences = []
    return_differences = []
    offsets = np.arange(block_size)
    for _ in range(samples):
        starts = rng.integers(0, observation_count, size=block_count)
        indices = (
            starts[:, None] + offsets[None, :]
        ).reshape(-1)[:observation_count] % observation_count
        sampled = values[indices]
        sampled_risk_free = (
            None if sampled.shape[1] == 2 else sampled[:, 2]
        )
        candidate_stats = _return_statistics(
            sampled[:, 0],
            risk_free_rate,
            sampled_risk_free,
        )
        baseline_stats = _return_statistics(
            sampled[:, 1],
            risk_free_rate,
            sampled_risk_free,
        )
        volatility_differences.append(
            candidate_stats["annualized_volatility"]
            - baseline_stats["annualized_volatility"]
        )
        return_differences.append(
            candidate_stats["annualized_return"]
            - baseline_stats["annualized_return"]
        )
        if (
            candidate_stats["sharpe"] is not None
            and baseline_stats["sharpe"] is not None
        ):
            sharpe_differences.append(
                candidate_stats["sharpe"] - baseline_stats["sharpe"]
            )

    def interval(values):
        values = np.asarray(values, dtype=float)
        return {
            "lower_95": float(np.quantile(values, 0.025)),
            "median": float(np.quantile(values, 0.50)),
            "upper_95": float(np.quantile(values, 0.975)),
        }

    volatility_values = np.asarray(volatility_differences, dtype=float)
    return_values = np.asarray(return_differences, dtype=float)
    sharpe_values = np.asarray(sharpe_differences, dtype=float)
    return {
        "status": "ok",
        "observation_count": int(observation_count),
        "block_size": int(block_size),
        "samples": int(samples),
        "seed": int(seed),
        "observed": {
            "candidate": observed_candidate,
            "baseline": observed_baseline,
            "difference": observed_difference,
        },
        "probability": {
            "lower_volatility": float(np.mean(volatility_values < 0.0)),
            "higher_return": float(np.mean(return_values > 0.0)),
            "higher_sharpe": (
                None
                if len(sharpe_values) == 0
                else float(np.mean(sharpe_values > 0.0))
            ),
        },
        "difference_interval": {
            "annualized_volatility": interval(volatility_values),
            "annualized_return": interval(return_values),
            "sharpe": (
                None if len(sharpe_values) == 0 else interval(sharpe_values)
            ),
        },
    }


def bootstrap_improvement_gate(
    bootstrap_result,
    minimum_probability=0.95,
):
    """Reject improvements unsupported by paired dependent-return evidence."""
    if bootstrap_result.get("status") != "ok":
        return {
            "status": "rejected",
            "reasons": ["Insufficient data for paired block bootstrap."],
        }
    probability = bootstrap_result["probability"]
    reasons = []
    if probability["lower_volatility"] < float(minimum_probability):
        reasons.append(
            "Lower-volatility probability is below "
            f"{float(minimum_probability):.0%}."
        )
    if (
        probability["higher_sharpe"] is None
        or probability["higher_sharpe"] < float(minimum_probability)
    ):
        reasons.append(
            "Higher-Sharpe probability is below "
            f"{float(minimum_probability):.0%}."
        )
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "minimum_probability": float(minimum_probability),
    }


def holm_bonferroni(p_values, alpha=0.05):
    """Control family-wise error across simultaneously researched candidates."""
    finite = {
        str(name): float(value)
        for name, value in dict(p_values).items()
        if value is not None and np.isfinite(float(value))
    }
    count = len(finite)
    ordered = sorted(finite.items(), key=lambda item: item[1])
    adjusted = {}
    running_max = 0.0
    for rank, (name, value) in enumerate(ordered):
        corrected = min(1.0, (count - rank) * value)
        running_max = max(running_max, corrected)
        adjusted[name] = float(running_max)
    return {
        name: {
            "raw_p_value": finite[name],
            "adjusted_p_value": adjusted[name],
            "significant": bool(adjusted[name] <= float(alpha)),
        }
        for name in finite
    }
