"""Robust covariance and risk-only allocators for portfolio research."""

import numpy as np
import pandas as pd
from pypfopt import EfficientCVaR, EfficientFrontier, HRPOpt, risk_models
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

from portfolio_signals import cap_and_normalize_weights


TRADING_DAYS_PER_YEAR = 252


def _clean_prices(price_data):
    prices = pd.DataFrame(price_data).copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index().apply(pd.to_numeric, errors="coerce")
    prices = prices.replace([np.inf, -np.inf], np.nan).ffill()
    return prices.dropna(axis=1, how="all")


def _returns(price_data):
    return (
        _clean_prices(price_data)
        .pct_change()
        .replace([np.inf, -np.inf], np.nan)
        .dropna(how="all")
    )


def covariance_diagnostics(covariance):
    """Return conditioning and diversification diagnostics."""
    covariance = pd.DataFrame(covariance, dtype=float)
    values = (covariance.values + covariance.values.T) / 2.0
    eigenvalues = np.linalg.eigvalsh(values)
    positive = eigenvalues[eigenvalues > 1e-12]
    condition_number = (
        None
        if len(positive) == 0
        else float(positive.max() / positive.min())
    )
    total = float(np.maximum(eigenvalues, 0.0).sum())
    probabilities = (
        np.maximum(eigenvalues, 0.0) / total
        if total > 0
        else np.array([])
    )
    effective_rank = (
        None
        if len(probabilities) == 0
        else float(
            np.exp(
                -np.sum(
                    probabilities[probabilities > 0]
                    * np.log(probabilities[probabilities > 0])
                )
            )
        )
    )
    volatility = np.sqrt(np.clip(np.diag(values), 0.0, None))
    denominator = np.outer(volatility, volatility)
    correlation = np.divide(
        values,
        denominator,
        out=np.zeros_like(values),
        where=denominator > 0,
    )
    upper = correlation[np.triu_indices_from(correlation, k=1)]
    return {
        "asset_count": int(len(covariance)),
        "minimum_eigenvalue": (
            None if len(eigenvalues) == 0 else float(eigenvalues.min())
        ),
        "maximum_eigenvalue": (
            None if len(eigenvalues) == 0 else float(eigenvalues.max())
        ),
        "condition_number": condition_number,
        "effective_rank": effective_rank,
        "average_pairwise_correlation": (
            None if len(upper) == 0 else float(np.mean(upper))
        ),
    }


def robust_covariance(
    price_data,
    ledoit_weight=0.50,
    oas_weight=0.30,
    exponential_weight=0.20,
    exponential_span=180,
):
    """Blend shrinkage and responsive covariance estimators, then repair PSD."""
    prices = _clean_prices(price_data)
    tickers = list(prices.columns)
    weights = np.asarray(
        [ledoit_weight, oas_weight, exponential_weight],
        dtype=float,
    )
    weights = np.clip(weights, 0.0, None)
    if float(weights.sum()) <= 0:
        raise ValueError("At least one robust covariance weight must be positive")
    weights = weights / float(weights.sum())

    shrinkage = risk_models.CovarianceShrinkage(prices)
    led = shrinkage.ledoit_wolf().reindex(index=tickers, columns=tickers)
    oas = shrinkage.oracle_approximating().reindex(
        index=tickers,
        columns=tickers,
    )
    exp = risk_models.exp_cov(
        prices,
        span=max(20, int(exponential_span)),
        frequency=TRADING_DAYS_PER_YEAR,
    ).reindex(index=tickers, columns=tickers)
    blended = led * weights[0] + oas * weights[1] + exp * weights[2]
    blended = risk_models.fix_nonpositive_semidefinite(
        blended,
        fix_method="spectral",
    )
    return blended, {
        "method": "ledoit_oas_exponential_blend",
        "weights": {
            "ledoit_wolf": float(weights[0]),
            "oracle_approximating": float(weights[1]),
            "exponential": float(weights[2]),
        },
        "exponential_span": int(exponential_span),
        "covariance": covariance_diagnostics(blended),
    }


def robust_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
):
    """Long-only minimum variance using blended robust covariance."""
    prices = _clean_prices(price_data)
    covariance, diagnostics = robust_covariance(prices)
    cap = max(float(max_asset_weight), 1.0 / max(1, len(prices.columns)) + 1e-9)
    try:
        optimizer = EfficientFrontier(
            pd.Series(0.0, index=prices.columns),
            covariance,
            weight_bounds=(0.0, min(1.0, cap)),
        )
        optimizer.min_volatility()
        weights = pd.Series(
            optimizer.clean_weights(),
            dtype=float,
        ).reindex(prices.columns).fillna(0.0)
    except Exception:
        weights = pd.Series(
            1.0 / len(prices.columns),
            index=prices.columns,
            dtype=float,
        )
    weights = cap_and_normalize_weights(
        weights,
        max_asset_weight=max_asset_weight,
    )
    return weights, diagnostics


def maximum_diversification_weights(
    price_data,
    max_asset_weight=0.20,
):
    """Maximize weighted standalone volatility per unit portfolio volatility."""
    prices = _clean_prices(price_data).dropna(how="any")
    tickers = list(prices.columns)
    if not tickers:
        raise ValueError("Maximum diversification requires price data")

    covariance = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    matrix = covariance.reindex(
        index=tickers,
        columns=tickers,
    ).to_numpy(dtype=float)
    standalone_volatility = np.sqrt(
        np.clip(np.diag(matrix), 0.0, None)
    )
    cap = max(
        float(max_asset_weight),
        1.0 / max(1, len(tickers)) + 1e-9,
    )
    initial = cap_and_normalize_weights(
        pd.Series(
            1.0 / np.where(
                standalone_volatility > 0.0,
                standalone_volatility,
                np.nan,
            ),
            index=tickers,
        ).fillna(0.0),
        max_asset_weight=max_asset_weight,
    ).to_numpy(dtype=float)

    def diversification_ratio(weights):
        portfolio_variance = float(weights @ matrix @ weights)
        if portfolio_variance <= 1e-16:
            return 0.0
        return float(
            weights @ standalone_volatility
            / np.sqrt(portfolio_variance)
        )

    result = minimize(
        lambda weights: -diversification_ratio(weights),
        initial,
        method="SLSQP",
        bounds=[(0.0, min(1.0, cap))] * len(tickers),
        constraints=({
            "type": "eq",
            "fun": lambda weights: weights.sum() - 1.0,
        },),
        options={"maxiter": 500, "ftol": 1e-12},
    )
    raw = initial if not result.success else result.x
    weights = cap_and_normalize_weights(
        pd.Series(raw, index=tickers, dtype=float),
        max_asset_weight=max_asset_weight,
    )
    equal = np.full(len(tickers), 1.0 / len(tickers))
    return weights, {
        "method": "ledoit_wolf_maximum_diversification",
        "optimizer_success": bool(result.success),
        "optimizer_message": str(result.message),
        "diversification_ratio": diversification_ratio(
            weights.to_numpy(dtype=float)
        ),
        "inverse_volatility_start_ratio": diversification_ratio(
            initial
        ),
        "equal_weight_diversification_ratio": diversification_ratio(
            equal
        ),
        "covariance": covariance_diagnostics(covariance),
    }


def random_matrix_denoised_covariance(price_data):
    """Denoise sample correlation eigenvalues with Marchenko-Pastur."""
    prices = _clean_prices(price_data)
    tickers = list(prices.columns)
    returns = _returns(prices).dropna(how="any")
    asset_count = len(tickers)
    minimum_rows = max(60, asset_count + 2)
    if len(returns) < minimum_rows:
        raise ValueError(
            "RMT covariance requires at least "
            f"{minimum_rows} complete return rows"
        )

    standardized = (
        returns - returns.mean(axis=0)
    ) / returns.std(axis=0, ddof=0).replace(0.0, np.nan)
    standardized = standardized.dropna(axis=1, how="any")
    if list(standardized.columns) != tickers:
        raise ValueError("RMT covariance requires non-constant assets")

    sample_correlation = (
        standardized.cov(ddof=0).to_numpy(dtype=float)
    )
    sample_correlation = (
        sample_correlation + sample_correlation.T
    ) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(sample_correlation)
    concentration_ratio = float(asset_count / len(standardized))
    noise_upper_bound = float(
        (1.0 + np.sqrt(concentration_ratio)) ** 2
    )
    noise_mask = eigenvalues <= noise_upper_bound
    denoised_eigenvalues = eigenvalues.copy()
    if noise_mask.any():
        denoised_eigenvalues[noise_mask] = float(
            eigenvalues[noise_mask].mean()
        )
    denoised_correlation = (
        eigenvectors
        @ np.diag(denoised_eigenvalues)
        @ eigenvectors.T
    )
    diagonal = np.sqrt(
        np.clip(np.diag(denoised_correlation), 1e-12, None)
    )
    denoised_correlation = denoised_correlation / np.outer(
        diagonal,
        diagonal,
    )
    np.fill_diagonal(denoised_correlation, 1.0)

    ledoit_daily = LedoitWolf().fit(
        returns.to_numpy(dtype=float)
    ).covariance_
    annual_volatility = np.sqrt(
        np.clip(np.diag(ledoit_daily), 0.0, None)
        * TRADING_DAYS_PER_YEAR
    )
    covariance = pd.DataFrame(
        denoised_correlation
        * np.outer(annual_volatility, annual_volatility),
        index=tickers,
        columns=tickers,
    )
    covariance = risk_models.fix_nonpositive_semidefinite(
        covariance,
        fix_method="spectral",
    )
    return covariance, {
        "method": "marchenko_pastur_correlation_denoising",
        "observation_count": int(len(standardized)),
        "asset_count": int(asset_count),
        "concentration_ratio": concentration_ratio,
        "noise_eigenvalue_upper_bound": noise_upper_bound,
        "noise_eigenvalue_count": int(noise_mask.sum()),
        "signal_eigenvalue_count": int((~noise_mask).sum()),
        "variance_source": "ledoit_wolf_diagonal",
        "covariance": covariance_diagnostics(covariance),
    }


def random_matrix_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
):
    """Long-only minimum variance with RMT-denoised correlations."""
    prices = _clean_prices(price_data)
    covariance, diagnostics = random_matrix_denoised_covariance(
        prices
    )
    weights, optimizer_success = _minimum_variance_from_covariance(
        covariance,
        prices.columns,
        max_asset_weight,
    )
    diagnostics["optimizer_success"] = bool(optimizer_success)
    return weights, diagnostics


def _minimum_variance_from_covariance(
    covariance,
    tickers,
    max_asset_weight,
):
    tickers = list(tickers)
    cap = max(
        float(max_asset_weight),
        1.0 / max(1, len(tickers)) + 1e-9,
    )
    try:
        optimizer = EfficientFrontier(
            pd.Series(0.0, index=tickers),
            pd.DataFrame(covariance).reindex(
                index=tickers,
                columns=tickers,
            ),
            weight_bounds=(0.0, min(1.0, cap)),
        )
        optimizer.min_volatility()
        raw = pd.Series(
            optimizer.clean_weights(),
            dtype=float,
        ).reindex(tickers).fillna(0.0)
        success = True
    except Exception:
        raw = pd.Series(1.0 / len(tickers), index=tickers, dtype=float)
        success = False
    return (
        cap_and_normalize_weights(
            raw,
            max_asset_weight=max_asset_weight,
        ),
        success,
    )


def _candidate_covariances(price_data):
    prices = _clean_prices(price_data)
    tickers = list(prices.columns)
    shrinkage = risk_models.CovarianceShrinkage(prices)
    candidates = {
        "ledoit_wolf": shrinkage.ledoit_wolf(),
        "oracle_approximating": shrinkage.oracle_approximating(),
        "exponential_60": risk_models.exp_cov(
            prices,
            span=60,
            frequency=TRADING_DAYS_PER_YEAR,
        ),
        "exponential_180": risk_models.exp_cov(
            prices,
            span=180,
            frequency=TRADING_DAYS_PER_YEAR,
        ),
        "robust_static": robust_covariance(prices)[0],
    }
    return {
        name: risk_models.fix_nonpositive_semidefinite(
            covariance.reindex(index=tickers, columns=tickers),
            fix_method="spectral",
        )
        for name, covariance in candidates.items()
    }


def _covariance_correlation(covariance):
    matrix = pd.DataFrame(covariance, dtype=float)
    values = matrix.to_numpy(dtype=float)
    volatility = np.sqrt(np.clip(np.diag(values), 1e-16, None))
    denominator = np.outer(volatility, volatility)
    correlation = np.divide(
        values,
        denominator,
        out=np.zeros_like(values),
        where=denominator > 0,
    )
    np.fill_diagonal(correlation, 1.0)
    return pd.DataFrame(
        correlation,
        index=matrix.index,
        columns=matrix.columns,
    )


def covariance_forecast_loss(predicted_covariance, realized_returns):
    """Score a covariance forecast against a completed OOS return window."""
    predicted = pd.DataFrame(predicted_covariance, dtype=float)
    returns = (
        pd.DataFrame(realized_returns)
        .reindex(columns=predicted.columns)
        .replace([np.inf, -np.inf], np.nan)
        .dropna(how="any")
    )
    minimum_rows = max(20, len(predicted.columns) + 2)
    if len(returns) < minimum_rows:
        raise ValueError(
            "Insufficient realized returns for covariance scoring: "
            f"{len(returns)} < {minimum_rows}"
        )
    realized = returns.cov(ddof=0) * TRADING_DAYS_PER_YEAR
    realized = risk_models.fix_nonpositive_semidefinite(
        realized,
        fix_method="spectral",
    )
    predicted = risk_models.fix_nonpositive_semidefinite(
        predicted.reindex(index=realized.index, columns=realized.columns),
        fix_method="spectral",
    )
    realized_values = realized.to_numpy(dtype=float)
    predicted_values = predicted.to_numpy(dtype=float)
    realized_norm = float(np.linalg.norm(realized_values, ord="fro"))
    covariance_error = float(
        np.linalg.norm(
            predicted_values - realized_values,
            ord="fro",
        )
        / max(realized_norm, 1e-12)
    )
    predicted_correlation = _covariance_correlation(predicted)
    realized_correlation = _covariance_correlation(realized)
    upper = np.triu_indices(len(predicted), k=1)
    correlation_error = (
        0.0
        if len(upper[0]) == 0
        else float(
            np.sqrt(
                np.mean(
                    np.square(
                        predicted_correlation.values[upper]
                        - realized_correlation.values[upper]
                    )
                )
            )
        )
    )

    diagonal = np.sqrt(
        np.clip(np.diag(predicted_values), 1e-12, None)
    )
    probes = [
        np.full(len(predicted), 1.0 / len(predicted)),
        (1.0 / diagonal) / float((1.0 / diagonal).sum()),
    ]
    log_variance_errors = []
    for weights in probes:
        predicted_variance = float(
            weights @ predicted_values @ weights
        )
        realized_variance = float(
            weights @ realized_values @ weights
        )
        log_variance_errors.append(
            abs(
                np.log(
                    max(predicted_variance, 1e-12)
                    / max(realized_variance, 1e-12)
                )
            )
        )
    variance_calibration_error = float(np.mean(log_variance_errors))
    composite_loss = float(
        np.mean(
            (
                covariance_error,
                correlation_error,
                variance_calibration_error,
            )
        )
    )
    return {
        "observation_count": int(len(returns)),
        "relative_frobenius_error": covariance_error,
        "correlation_rmse": correlation_error,
        "portfolio_log_variance_error": variance_calibration_error,
        "composite_loss": composite_loss,
    }


def _stressed_covariance(
    covariance,
    correlation_shock=0.25,
    volatility_shock=1.25,
):
    """Return a PSD covariance under a bounded correlation/volatility shock."""
    matrix = pd.DataFrame(covariance, dtype=float)
    correlation = _covariance_correlation(matrix).to_numpy(dtype=float)
    shock = float(np.clip(correlation_shock, 0.0, 1.0))
    stressed_correlation = (
        correlation * (1.0 - shock)
        + np.ones_like(correlation) * shock
    )
    volatility = (
        np.sqrt(
            np.clip(
                np.diag(matrix.to_numpy(dtype=float)),
                1e-16,
                None,
            )
        )
        * max(1.0, float(volatility_shock))
    )
    stressed = pd.DataFrame(
        stressed_correlation * np.outer(volatility, volatility),
        index=matrix.index,
        columns=matrix.columns,
    )
    return risk_models.fix_nonpositive_semidefinite(
        stressed,
        fix_method="spectral",
    )


def covariance_stress_diagnostics(
    covariance,
    weights,
    correlation_shock=0.25,
    volatility_shock=1.25,
):
    """Measure portfolio risk under a PSD correlation/volatility shock."""
    matrix = pd.DataFrame(covariance, dtype=float)
    aligned_weights = pd.Series(weights, dtype=float).reindex(
        matrix.columns
    ).fillna(0.0)
    values = matrix.to_numpy(dtype=float)
    stressed_matrix = _stressed_covariance(
        matrix,
        correlation_shock=correlation_shock,
        volatility_shock=volatility_shock,
    )
    shock = float(np.clip(correlation_shock, 0.0, 1.0))
    stressed = stressed_matrix.to_numpy(dtype=float)
    weight_values = aligned_weights.to_numpy(dtype=float)
    baseline_volatility = float(
        np.sqrt(max(weight_values @ values @ weight_values, 0.0))
    )
    stressed_volatility = float(
        np.sqrt(max(weight_values @ stressed @ weight_values, 0.0))
    )
    return {
        "correlation_shock": shock,
        "volatility_shock": max(1.0, float(volatility_shock)),
        "baseline_annual_volatility": baseline_volatility,
        "stressed_annual_volatility": stressed_volatility,
        "stress_amplification": (
            None
            if baseline_volatility <= 1e-12
            else float(stressed_volatility / baseline_volatility)
        ),
        "effective_asset_count": float(
            1.0 / max(np.square(weight_values).sum(), 1e-12)
        ),
        "maximum_weight": float(aligned_weights.max()),
    }


def scenario_robust_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
    recent_span=60,
    correlation_shock=0.25,
    volatility_shock=1.25,
):
    """Minimize worst predicted variance across baseline, recent, and stress."""
    prices = _clean_prices(price_data).dropna(how="any")
    tickers = list(prices.columns)
    if not tickers:
        raise ValueError("Scenario-robust allocation requires price data")

    baseline = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    recent = risk_models.exp_cov(
        prices,
        span=max(20, int(recent_span)),
        frequency=TRADING_DAYS_PER_YEAR,
    )
    scenarios = {
        "ledoit_wolf": baseline,
        "recent_exponential": recent,
        "correlation_volatility_stress": _stressed_covariance(
            baseline,
            correlation_shock=correlation_shock,
            volatility_shock=volatility_shock,
        ),
    }
    scenarios = {
        name: risk_models.fix_nonpositive_semidefinite(
            covariance.reindex(index=tickers, columns=tickers),
            fix_method="spectral",
        )
        for name, covariance in scenarios.items()
    }
    scenario_values = {
        name: covariance.to_numpy(dtype=float)
        for name, covariance in scenarios.items()
    }
    baseline_weights, baseline_success = _minimum_variance_from_covariance(
        baseline,
        tickers,
        max_asset_weight,
    )
    initial_weights = baseline_weights.to_numpy(dtype=float)
    initial_worst_variance = max(
        float(initial_weights @ matrix @ initial_weights)
        for matrix in scenario_values.values()
    )
    asset_count = len(tickers)
    cap = max(
        float(max_asset_weight),
        1.0 / max(1, asset_count) + 1e-9,
    )

    constraints = [{
        "type": "eq",
        "fun": lambda values: float(values[:-1].sum() - 1.0),
    }]
    for matrix in scenario_values.values():
        constraints.append({
            "type": "ineq",
            "fun": (
                lambda values, scenario=matrix: float(
                    values[-1]
                    - values[:-1] @ scenario @ values[:-1]
                )
            ),
        })
    result = minimize(
        lambda values: float(values[-1]),
        np.append(initial_weights, initial_worst_variance),
        method="SLSQP",
        bounds=(
            [(0.0, min(1.0, cap))] * asset_count
            + [(0.0, None)]
        ),
        constraints=tuple(constraints),
        options={"maxiter": 1000, "ftol": 1e-12},
    )
    raw_weights = (
        result.x[:-1]
        if result.success and np.isfinite(result.x).all()
        else initial_weights
    )
    weights = cap_and_normalize_weights(
        pd.Series(raw_weights, index=tickers, dtype=float),
        max_asset_weight=max_asset_weight,
    )
    scenario_variances = {
        name: float(weights.values @ matrix @ weights.values)
        for name, matrix in scenario_values.items()
    }
    baseline_scenario_variances = {
        name: float(
            baseline_weights.values
            @ matrix
            @ baseline_weights.values
        )
        for name, matrix in scenario_values.items()
    }
    worst_name = max(
        scenario_variances,
        key=scenario_variances.get,
    )
    worst_variance = scenario_variances[worst_name]
    baseline_worst_variance = max(
        baseline_scenario_variances.values()
    )
    return weights, {
        "method": "scenario_worst_case_minimum_variance",
        "optimizer_success": bool(result.success),
        "optimizer_message": str(result.message),
        "baseline_optimizer_success": bool(baseline_success),
        "scenario_count": int(len(scenarios)),
        "recent_span": int(recent_span),
        "correlation_shock": float(
            np.clip(correlation_shock, 0.0, 1.0)
        ),
        "volatility_shock": float(
            max(1.0, float(volatility_shock))
        ),
        "active_worst_case_scenario": worst_name,
        "scenario_annual_volatilities": {
            name: float(np.sqrt(max(variance, 0.0)))
            for name, variance in scenario_variances.items()
        },
        "worst_case_annual_volatility": float(
            np.sqrt(max(worst_variance, 0.0))
        ),
        "baseline_worst_case_annual_volatility": float(
            np.sqrt(max(baseline_worst_variance, 0.0))
        ),
        "worst_case_variance_reduction": float(
            baseline_worst_variance - worst_variance
        ),
        "baseline_l1_distance": float(
            (weights - baseline_weights).abs().sum()
        ),
        "covariance": covariance_diagnostics(baseline),
    }


def volatility_targeted_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
    state_lookback=252,
    state_step=63,
    minimum_risky_exposure=0.25,
):
    """Scale minimum-variance exposure against its historical risk state."""
    prices = _clean_prices(price_data).dropna(how="any")
    tickers = list(prices.columns)
    if not tickers:
        raise ValueError("Volatility targeting requires price data")

    covariance = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    base_weights, success = _minimum_variance_from_covariance(
        covariance,
        tickers,
        max_asset_weight,
    )
    lookback = max(126, int(state_lookback))
    step = max(21, int(state_step))
    current_state_prices = prices.tail(lookback)
    current_state_covariance = risk_models.CovarianceShrinkage(
        current_state_prices
    ).ledoit_wolf()
    current_variance = float(
        base_weights.values
        @ current_state_covariance.to_numpy(dtype=float)
        @ base_weights.values
    )
    current_volatility = float(np.sqrt(max(current_variance, 0.0)))

    historical_volatilities = []
    for cutoff in range(lookback, len(prices), step):
        historical_prices = prices.iloc[
            max(0, cutoff - lookback):cutoff
        ]
        if len(historical_prices) < lookback:
            continue
        historical_covariance = risk_models.CovarianceShrinkage(
            historical_prices
        ).ledoit_wolf()
        historical_weights, _ = _minimum_variance_from_covariance(
            historical_covariance,
            tickers,
            max_asset_weight,
        )
        historical_variance = float(
            historical_weights.values
            @ historical_covariance.to_numpy(dtype=float)
            @ historical_weights.values
        )
        if np.isfinite(historical_variance) and historical_variance > 0:
            historical_volatilities.append(
                float(np.sqrt(historical_variance))
            )

    reference_volatility = (
        current_volatility
        if not historical_volatilities
        else float(np.median(historical_volatilities))
    )
    minimum_exposure = float(
        np.clip(minimum_risky_exposure, 0.0, 1.0)
    )
    risky_exposure = (
        1.0
        if current_volatility <= 1e-12
        else float(
            np.clip(
                reference_volatility / current_volatility,
                minimum_exposure,
                1.0,
            )
        )
    )
    weights = base_weights * risky_exposure
    return weights, {
        "method": "historical_state_volatility_targeted_minimum_variance",
        "optimizer_success": bool(success),
        "allow_cash_reserve": True,
        "target_risky_exposure": risky_exposure,
        "target_cash_weight": float(1.0 - risky_exposure),
        "current_predicted_annual_volatility": current_volatility,
        "reference_predicted_annual_volatility": reference_volatility,
        "scaled_predicted_annual_volatility": float(
            current_volatility * risky_exposure
        ),
        "historical_state_count": int(len(historical_volatilities)),
        "state_lookback": int(lookback),
        "state_step": int(step),
        "minimum_risky_exposure": minimum_exposure,
        "covariance": covariance_diagnostics(covariance),
    }


def trend_filtered_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
    trend_lookback=252,
):
    """Keep minimum-variance sleeves only when trailing absolute trend is positive."""
    prices = _clean_prices(price_data).dropna(how="any")
    tickers = list(prices.columns)
    lookback = max(2, int(trend_lookback))
    if not tickers or len(prices) < lookback:
        raise ValueError(
            "Trend-filtered minimum variance requires at least "
            f"{lookback} complete price rows"
        )

    covariance = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    base_weights, success = _minimum_variance_from_covariance(
        covariance,
        tickers,
        max_asset_weight,
    )
    start_prices = prices.iloc[-lookback].replace(0.0, np.nan)
    trailing_returns = (
        prices.iloc[-1] / start_prices - 1.0
    ).replace([np.inf, -np.inf], np.nan)
    active = trailing_returns.gt(0.0).fillna(False)
    weights = base_weights.where(active, 0.0)
    risky_exposure = float(np.clip(weights.sum(), 0.0, 1.0))

    return weights, {
        "method": "positive_12m_trend_filtered_ledoit_wolf_minimum_variance",
        "optimizer_success": bool(success),
        "allow_cash_reserve": True,
        "target_risky_exposure": risky_exposure,
        "target_cash_weight": float(1.0 - risky_exposure),
        "trend_lookback": int(lookback),
        "active_trend_count": int(active.sum()),
        "inactive_trend_count": int((~active).sum()),
        "trailing_returns": {
            str(ticker): float(value)
            for ticker, value in trailing_returns.dropna().items()
        },
        "covariance": covariance_diagnostics(covariance),
    }


def trend_filtered_risk_parity_weights(
    price_data,
    max_asset_weight=0.20,
    trend_lookback=252,
):
    """Keep inverse-volatility sleeves only when trailing absolute trend is positive."""
    prices = _clean_prices(price_data).dropna(how="any")
    tickers = list(prices.columns)
    lookback = max(2, int(trend_lookback))
    if not tickers or len(prices) < lookback:
        raise ValueError(
            "Trend-filtered risk parity requires at least "
            f"{lookback} complete price rows"
        )

    volatility = (
        _returns(prices)
        .std(ddof=0)
        .replace([np.inf, -np.inf], np.nan)
    )
    inverse_volatility = 1.0 / volatility.where(volatility > 0.0)
    base_weights = cap_and_normalize_weights(
        inverse_volatility.reindex(tickers).fillna(0.0),
        max_asset_weight=max_asset_weight,
    )
    start_prices = prices.iloc[-lookback].replace(0.0, np.nan)
    trailing_returns = (
        prices.iloc[-1] / start_prices - 1.0
    ).replace([np.inf, -np.inf], np.nan)
    active = trailing_returns.gt(0.0).fillna(False)
    weights = base_weights.where(active, 0.0)
    risky_exposure = float(np.clip(weights.sum(), 0.0, 1.0))

    return weights, {
        "method": "positive_12m_trend_filtered_inverse_volatility",
        "allow_cash_reserve": True,
        "target_risky_exposure": risky_exposure,
        "target_cash_weight": float(1.0 - risky_exposure),
        "trend_lookback": int(lookback),
        "active_trend_count": int(active.sum()),
        "inactive_trend_count": int((~active).sum()),
        "trailing_returns": {
            str(ticker): float(value)
            for ticker, value in trailing_returns.dropna().items()
        },
    }


def forecast_ensemble_covariance(
    price_data,
    inner_train_window=252,
    inner_validation_window=63,
    max_folds=4,
):
    """Soft-ensemble covariance estimators by completed OOS forecast loss."""
    prices = _clean_prices(price_data).dropna(how="any")
    tickers = list(prices.columns)
    validation_window = max(21, int(inner_validation_window))
    minimum_train = max(126, int(inner_train_window))
    cutoffs = list(
        range(
            minimum_train,
            len(prices) - validation_window + 1,
            validation_window,
        )
    )[-max(1, int(max_folds)):]
    losses = {}
    fold_diagnostics = {}
    for cutoff in cutoffs:
        inner_train = prices.iloc[:cutoff]
        validation_returns = _returns(
            prices.iloc[cutoff - 1:cutoff + validation_window]
        ).dropna(how="any")
        for name, covariance in _candidate_covariances(
            inner_train
        ).items():
            try:
                diagnostics = covariance_forecast_loss(
                    covariance,
                    validation_returns,
                )
            except ValueError:
                continue
            losses.setdefault(name, []).append(
                diagnostics["composite_loss"]
            )
            fold_diagnostics.setdefault(name, []).append(diagnostics)

    full_candidates = _candidate_covariances(prices)
    median_losses = {
        name: float(np.median(values))
        for name, values in losses.items()
        if values and name in full_candidates
    }
    if not median_losses:
        covariance = full_candidates["ledoit_wolf"]
        return covariance, {
            "method": "oos_forecast_loss_covariance_ensemble",
            "fallback": True,
            "inner_fold_count": 0,
            "candidate_losses": {},
            "ensemble_weights": {"ledoit_wolf": 1.0},
            "fold_diagnostics": {},
            "covariance": covariance_diagnostics(covariance),
        }

    inverse_loss = {
        name: 1.0 / max(loss, 1e-8)
        for name, loss in median_losses.items()
    }
    inverse_total = float(sum(inverse_loss.values()))
    equal_weight = 1.0 / len(inverse_loss)
    ensemble_weights = {
        name: float(
            0.50 * equal_weight
            + 0.50 * inverse_loss[name] / inverse_total
        )
        for name in inverse_loss
    }
    covariance = sum(
        full_candidates[name] * weight
        for name, weight in ensemble_weights.items()
    )
    covariance = risk_models.fix_nonpositive_semidefinite(
        covariance,
        fix_method="spectral",
    )
    return covariance, {
        "method": "oos_forecast_loss_covariance_ensemble",
        "fallback": False,
        "inner_fold_count": int(
            max((len(values) for values in losses.values()), default=0)
        ),
        "candidate_losses": median_losses,
        "ensemble_weights": ensemble_weights,
        "fold_diagnostics": fold_diagnostics,
        "covariance": covariance_diagnostics(covariance),
    }


def forecast_ensemble_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
):
    """Minimum variance using a stable OOS-scored covariance ensemble."""
    prices = _clean_prices(price_data)
    covariance, diagnostics = forecast_ensemble_covariance(prices)
    weights, success = _minimum_variance_from_covariance(
        covariance,
        prices.columns,
        max_asset_weight,
    )
    return weights, {
        **diagnostics,
        "optimizer_success": bool(success),
        "stress": covariance_stress_diagnostics(
            covariance,
            weights,
        ),
    }


def cross_validated_covariance(
    price_data,
    max_asset_weight=0.20,
    inner_train_window=252,
    inner_validation_window=63,
    max_folds=4,
):
    """Select a covariance estimator using training-window-only walk-forward risk."""
    prices = _clean_prices(price_data).dropna(how="any")
    tickers = list(prices.columns)
    validation_window = max(21, int(inner_validation_window))
    minimum_train = max(126, int(inner_train_window))
    available_cutoffs = list(
        range(
            minimum_train,
            len(prices) - validation_window + 1,
            validation_window,
        )
    )
    cutoffs = available_cutoffs[-max(1, int(max_folds)):]
    if not cutoffs:
        covariance = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
        return covariance, {
            "method": "cross_validated_covariance",
            "selected_estimator": "ledoit_wolf",
            "inner_fold_count": 0,
            "fallback": True,
            "candidate_scores": {},
            "covariance": covariance_diagnostics(covariance),
        }

    candidate_losses = {}
    candidate_successes = {}
    for cutoff in cutoffs:
        inner_train = prices.iloc[:cutoff]
        inner_validation = _returns(
            prices.iloc[cutoff - 1:cutoff + validation_window]
        ).dropna(how="any")
        if inner_validation.empty:
            continue
        for name, covariance in _candidate_covariances(inner_train).items():
            weights, success = _minimum_variance_from_covariance(
                covariance,
                tickers,
                max_asset_weight,
            )
            validation_portfolio = inner_validation.reindex(
                columns=tickers,
            ).mul(weights, axis=1).sum(axis=1)
            realized_variance = float(
                validation_portfolio.var(ddof=0) * TRADING_DAYS_PER_YEAR
            )
            if np.isfinite(realized_variance):
                candidate_losses.setdefault(name, []).append(realized_variance)
                candidate_successes.setdefault(name, []).append(bool(success))

    scores = {
        name: float(np.median(losses))
        for name, losses in candidate_losses.items()
        if losses
    }
    selected = min(scores, key=scores.get) if scores else "ledoit_wolf"
    full_candidates = _candidate_covariances(prices)
    covariance = full_candidates.get(
        selected,
        full_candidates["ledoit_wolf"],
    )
    return covariance, {
        "method": "cross_validated_covariance",
        "selected_estimator": selected,
        "inner_fold_count": int(
            max(
                (len(values) for values in candidate_losses.values()),
                default=0,
            )
        ),
        "fallback": not bool(scores),
        "candidate_scores": scores,
        "candidate_success_rates": {
            name: float(np.mean(values))
            for name, values in candidate_successes.items()
            if values
        },
        "covariance": covariance_diagnostics(covariance),
    }


def cross_validated_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
):
    """Long-only minimum variance with nested estimator selection."""
    prices = _clean_prices(price_data)
    covariance, diagnostics = cross_validated_covariance(
        prices,
        max_asset_weight=max_asset_weight,
    )
    weights, success = _minimum_variance_from_covariance(
        covariance,
        prices.columns,
        max_asset_weight,
    )
    return weights, {
        **diagnostics,
        "optimizer_success": bool(success),
    }


def stability_regularized_minimum_variance_weights(
    price_data,
    previous_weights=None,
    max_asset_weight=0.20,
    regularization_strength=0.25,
):
    """Minimum variance with a scale-aware penalty toward prior target weights."""
    prices = _clean_prices(price_data)
    tickers = list(prices.columns)
    covariance = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    matrix = covariance.reindex(index=tickers, columns=tickers).values
    asset_count = len(tickers)
    cap = max(
        float(max_asset_weight),
        1.0 / max(1, asset_count) + 1e-9,
    )
    reference = pd.Series(
        {} if previous_weights is None else previous_weights,
        dtype=float,
    ).reindex(tickers)
    valid_previous = bool(
        previous_weights is not None
        and reference.notna().sum() == asset_count
        and float(reference.fillna(0.0).clip(lower=0.0).sum()) > 0
    )
    if not valid_previous:
        diagonal = np.sqrt(np.clip(np.diag(matrix), 1e-12, None))
        reference = pd.Series(1.0 / diagonal, index=tickers, dtype=float)
    reference = cap_and_normalize_weights(
        reference,
        max_asset_weight=max_asset_weight,
    )
    scale = float(np.mean(np.clip(np.diag(matrix), 1e-12, None)))
    penalty = max(0.0, float(regularization_strength)) * scale

    def objective(weights):
        variance = float(weights @ matrix @ weights)
        stability = float(np.sum(np.square(weights - reference.values)))
        return variance + penalty * stability

    result = minimize(
        objective,
        reference.values,
        method="SLSQP",
        bounds=[(0.0, min(1.0, cap))] * asset_count,
        constraints=(
            {
                "type": "eq",
                "fun": lambda weights: float(weights.sum() - 1.0),
            },
        ),
        options={"maxiter": 500, "ftol": 1e-12},
    )
    raw = reference.values if not result.success else result.x
    weights = cap_and_normalize_weights(
        pd.Series(raw, index=tickers, dtype=float),
        max_asset_weight=max_asset_weight,
    )
    return weights, {
        "method": "stability_regularized_ledoit_wolf_minimum_variance",
        "optimizer_success": bool(result.success),
        "optimizer_message": str(result.message),
        "regularization_strength": float(regularization_strength),
        "regularization_penalty": penalty,
        "reference_source": (
            "previous_target" if valid_previous else "inverse_volatility"
        ),
        "reference_l1_distance": float((weights - reference).abs().sum()),
        "covariance": covariance_diagnostics(covariance),
    }


def _inverse_volatility_weights(price_data, max_asset_weight):
    returns = _returns(price_data)
    volatility = returns.std(ddof=0).replace(0.0, np.nan)
    inverse = (1.0 / volatility).replace(
        [np.inf, -np.inf],
        np.nan,
    ).fillna(0.0)
    if float(inverse.sum()) <= 0.0:
        inverse = pd.Series(
            1.0,
            index=pd.DataFrame(price_data).columns,
            dtype=float,
        )
    return cap_and_normalize_weights(
        inverse,
        max_asset_weight=max_asset_weight,
    )


def nested_blended_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
    blend_grid=(0.0, 0.25, 0.50, 0.75, 1.0),
    inner_train=252,
    inner_validation=63,
):
    """Select min-variance/inverse-vol shrinkage on completed inner folds."""
    prices = _clean_prices(price_data)
    tickers = list(prices.columns)
    inner_train = max(63, int(inner_train))
    inner_validation = max(21, int(inner_validation))
    blend_grid = tuple(sorted({
        float(np.clip(value, 0.0, 1.0))
        for value in blend_grid
        if np.isfinite(float(value))
    }))
    if not blend_grid:
        raise ValueError("nested blend grid requires a finite value")

    losses = {blend: [] for blend in blend_grid}
    fold_count = 0
    last_train_end = len(prices) - inner_validation - 1
    for train_end in range(
        inner_train,
        last_train_end + 1,
        inner_validation,
    ):
        inner_prices = prices.iloc[
            train_end - inner_train:train_end + 1
        ]
        validation_returns = (
            prices.iloc[
                train_end:train_end + inner_validation + 1
            ]
            .pct_change()
            .replace([np.inf, -np.inf], np.nan)
            .dropna(how="any")
        )
        if len(validation_returns) < max(20, len(tickers) + 2):
            continue
        covariance = risk_models.CovarianceShrinkage(
            inner_prices
        ).ledoit_wolf()
        min_variance, _ = _minimum_variance_from_covariance(
            covariance,
            tickers,
            max_asset_weight,
        )
        inverse_volatility = _inverse_volatility_weights(
            inner_prices,
            max_asset_weight,
        )
        for blend in blend_grid:
            weights = cap_and_normalize_weights(
                (1.0 - blend) * min_variance
                + blend * inverse_volatility,
                max_asset_weight=max_asset_weight,
            )
            portfolio_returns = validation_returns.reindex(
                columns=tickers
            ).mul(weights, axis=1).sum(axis=1)
            losses[blend].append(
                float(portfolio_returns.var(ddof=0) * TRADING_DAYS_PER_YEAR)
            )
        fold_count += 1

    scores = {
        blend: float(np.median(values))
        for blend, values in losses.items()
        if values
    }
    selected_blend = (
        0.50
        if not scores
        else min(scores, key=lambda blend: (scores[blend], -blend))
    )
    covariance = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    min_variance, success = _minimum_variance_from_covariance(
        covariance,
        tickers,
        max_asset_weight,
    )
    inverse_volatility = _inverse_volatility_weights(
        prices,
        max_asset_weight,
    )
    weights = cap_and_normalize_weights(
        (1.0 - selected_blend) * min_variance
        + selected_blend * inverse_volatility,
        max_asset_weight=max_asset_weight,
    )
    return weights, {
        "method": "nested_min_variance_inverse_volatility_blend",
        "selection_metric": "median completed inner-fold realized variance",
        "selected_inverse_volatility_weight": float(selected_blend),
        "blend_grid": [float(value) for value in blend_grid],
        "inner_train": int(inner_train),
        "inner_validation": int(inner_validation),
        "inner_fold_count": int(fold_count),
        "fallback": not bool(scores),
        "candidate_scores": {
            str(float(blend)): float(score)
            for blend, score in scores.items()
        },
        "optimizer_success": bool(success),
        "minimum_variance_l1_distance": float(
            (weights - min_variance).abs().sum()
        ),
        "inverse_volatility_l1_distance": float(
            (weights - inverse_volatility).abs().sum()
        ),
        "covariance": covariance_diagnostics(covariance),
    }


def resampled_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
    bootstrap_samples=32,
    block_size=21,
    seed=42,
):
    """Average minimum-variance weights across paired circular block resamples."""
    prices = _clean_prices(price_data)
    returns = _returns(prices).dropna(how="any")
    tickers = list(prices.columns)
    observation_count = len(returns)
    block_size = max(2, min(int(block_size), max(2, observation_count)))
    bootstrap_samples = max(8, int(bootstrap_samples))
    if observation_count < block_size * 2:
        weights, success = _minimum_variance_from_covariance(
            risk_models.CovarianceShrinkage(prices).ledoit_wolf(),
            tickers,
            max_asset_weight,
        )
        return weights, {
            "method": "resampled_ledoit_wolf_minimum_variance",
            "fallback": True,
            "optimizer_success_rate": float(success),
            "bootstrap_samples": 0,
            "block_size": int(block_size),
        }

    rng = np.random.default_rng(int(seed))
    values = returns.reindex(columns=tickers).values
    block_count = int(np.ceil(observation_count / block_size))
    offsets = np.arange(block_size)
    sampled_weights = []
    successes = []
    for _ in range(bootstrap_samples):
        starts = rng.integers(0, observation_count, size=block_count)
        indices = (
            starts[:, None] + offsets[None, :]
        ).reshape(-1)[:observation_count] % observation_count
        sampled_returns = values[indices]
        estimator = LedoitWolf().fit(sampled_returns)
        covariance = pd.DataFrame(
            estimator.covariance_ * TRADING_DAYS_PER_YEAR,
            index=tickers,
            columns=tickers,
        )
        weights, success = _minimum_variance_from_covariance(
            covariance,
            tickers,
            max_asset_weight,
        )
        sampled_weights.append(weights.values)
        successes.append(bool(success))

    weight_matrix = np.asarray(sampled_weights, dtype=float)
    weights = cap_and_normalize_weights(
        pd.Series(weight_matrix.mean(axis=0), index=tickers),
        max_asset_weight=max_asset_weight,
    )
    original_covariance = risk_models.CovarianceShrinkage(
        prices
    ).ledoit_wolf()
    return weights, {
        "method": "resampled_ledoit_wolf_minimum_variance",
        "fallback": False,
        "bootstrap_samples": int(bootstrap_samples),
        "block_size": int(block_size),
        "seed": int(seed),
        "optimizer_success_rate": float(np.mean(successes)),
        "mean_weight_dispersion": float(
            np.mean(np.std(weight_matrix, axis=0, ddof=0))
        ),
        "covariance": covariance_diagnostics(original_covariance),
    }


def regime_conditioned_covariance(price_data):
    """Choose a fixed normal/stress covariance recipe from training-only state."""
    prices = _clean_prices(price_data)
    returns = _returns(prices)
    market_returns = returns.mean(axis=1, skipna=True)
    rolling_volatility = (
        market_returns.rolling(63).std(ddof=0)
        * np.sqrt(TRADING_DAYS_PER_YEAR)
    ).dropna()
    current_volatility = (
        None
        if rolling_volatility.empty
        else float(rolling_volatility.iloc[-1])
    )
    volatility_percentile = (
        None
        if rolling_volatility.empty
        else float(
            (rolling_volatility <= rolling_volatility.iloc[-1]).mean()
        )
    )
    recent_correlation = returns.tail(63).corr()
    long_correlation = returns.tail(252).corr()

    def average_upper(frame):
        values = frame.values
        upper = values[np.triu_indices_from(values, k=1)]
        finite = upper[np.isfinite(upper)]
        return None if len(finite) == 0 else float(np.mean(finite))

    recent_average_correlation = average_upper(recent_correlation)
    long_average_correlation = average_upper(long_correlation)
    volatility_stress = (
        0.0
        if volatility_percentile is None
        else float(
            np.clip(
                (volatility_percentile - 0.50) / 0.40,
                0.0,
                1.0,
            )
        )
    )
    correlation_change = (
        0.0
        if recent_average_correlation is None
        or long_average_correlation is None
        else recent_average_correlation - long_average_correlation
    )
    correlation_stress = float(
        np.clip(correlation_change / 0.20, 0.0, 1.0)
    )
    stress_intensity = max(volatility_stress, correlation_stress)
    baseline = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    stress_covariance, stress_diagnostics = robust_covariance(
        prices,
        ledoit_weight=0.40,
        oas_weight=0.20,
        exponential_weight=0.40,
        exponential_span=60,
    )
    covariance = (
        baseline * (1.0 - stress_intensity)
        + stress_covariance * stress_intensity
    )
    covariance = risk_models.fix_nonpositive_semidefinite(
        covariance,
        fix_method="spectral",
    )
    regime = "stress" if stress_intensity >= 0.50 else "normal"
    diagnostics = {
        **stress_diagnostics,
        "method": "continuous_regime_conditioned_covariance_v2",
        "regime": regime,
        "stress_intensity": float(stress_intensity),
        "state": {
            "market_volatility_63d": current_volatility,
            "market_volatility_percentile": volatility_percentile,
            "recent_average_correlation": recent_average_correlation,
            "long_average_correlation": long_average_correlation,
            "correlation_change": float(correlation_change),
            "volatility_stress": float(volatility_stress),
            "correlation_stress": float(correlation_stress),
        },
        "covariance": covariance_diagnostics(covariance),
    }
    return covariance, diagnostics


def regime_minimum_variance_weights(
    price_data,
    max_asset_weight=0.20,
):
    """Minimum variance with a pre-declared normal/stress covariance recipe."""
    prices = _clean_prices(price_data)
    covariance, diagnostics = regime_conditioned_covariance(prices)
    cap = max(
        float(max_asset_weight),
        1.0 / max(1, len(prices.columns)) + 1e-9,
    )
    try:
        optimizer = EfficientFrontier(
            pd.Series(0.0, index=prices.columns),
            covariance,
            weight_bounds=(0.0, min(1.0, cap)),
        )
        optimizer.min_volatility()
        raw = pd.Series(
            optimizer.clean_weights(),
            dtype=float,
        ).reindex(prices.columns).fillna(0.0)
    except Exception:
        raw = pd.Series(
            1.0 / len(prices.columns),
            index=prices.columns,
            dtype=float,
        )
    weights = cap_and_normalize_weights(
        raw,
        max_asset_weight=max_asset_weight,
    )
    return weights, diagnostics


def equal_risk_contribution_weights(
    price_data,
    max_asset_weight=0.20,
):
    """Solve long-only equal-risk-contribution weights with robust covariance."""
    prices = _clean_prices(price_data)
    covariance, diagnostics = robust_covariance(prices)
    tickers = list(prices.columns)
    asset_count = len(tickers)
    cap = max(
        float(max_asset_weight),
        1.0 / max(1, asset_count) + 1e-9,
    )
    matrix = covariance.reindex(index=tickers, columns=tickers).values

    def objective(weights):
        portfolio_variance = float(weights @ matrix @ weights)
        if portfolio_variance <= 1e-16:
            return 1e6
        marginal = matrix @ weights
        contributions = weights * marginal / portfolio_variance
        target = np.full(asset_count, 1.0 / asset_count)
        return float(np.sum(np.square(contributions - target)))

    initial = np.full(asset_count, 1.0 / asset_count)
    result = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=[(0.0, min(1.0, cap))] * asset_count,
        constraints=({"type": "eq", "fun": lambda weights: weights.sum() - 1.0},),
        options={"maxiter": 500, "ftol": 1e-12},
    )
    raw = initial if not result.success else result.x
    weights = cap_and_normalize_weights(
        pd.Series(raw, index=tickers, dtype=float),
        max_asset_weight=max_asset_weight,
    )
    variance = float(weights.values @ matrix @ weights.values)
    contributions = (
        weights.values * (matrix @ weights.values) / variance
        if variance > 1e-16
        else np.zeros(asset_count)
    )
    diagnostics = {
        **diagnostics,
        "optimizer_success": bool(result.success),
        "optimizer_message": str(result.message),
        "risk_contribution_dispersion": float(
            np.std(contributions, ddof=0)
        ),
        "risk_contributions": {
            ticker: float(value)
            for ticker, value in zip(tickers, contributions)
        },
    }
    return weights, diagnostics


def hierarchical_risk_parity_weights(
    price_data,
    max_asset_weight=0.20,
):
    """Allocate by hierarchical clustering, then enforce long-only cap."""
    prices = _clean_prices(price_data)
    returns = _returns(prices)
    tickers = list(prices.columns)
    try:
        optimizer = HRPOpt(returns=returns)
        raw = pd.Series(
            optimizer.optimize(),
            dtype=float,
        ).reindex(tickers).fillna(0.0)
        linkage = optimizer.clusters.tolist() if optimizer.clusters is not None else None
        success = True
    except Exception:
        raw = pd.Series(1.0 / len(tickers), index=tickers, dtype=float)
        linkage = None
        success = False
    weights = cap_and_normalize_weights(
        raw,
        max_asset_weight=max_asset_weight,
    )
    return weights, {
        "method": "hierarchical_risk_parity",
        "optimizer_success": success,
        "cluster_linkage": linkage,
    }


def minimum_cvar_weights(
    price_data,
    max_asset_weight=0.20,
    beta=0.95,
):
    """Long-only historical expected-shortfall minimization."""
    prices = _clean_prices(price_data)
    returns = _returns(prices).dropna(how="any")
    tickers = list(prices.columns)
    beta = float(np.clip(beta, 0.80, 0.995))
    cap = max(
        float(max_asset_weight),
        1.0 / max(1, len(tickers)) + 1e-9,
    )
    try:
        optimizer = EfficientCVaR(
            pd.Series(0.0, index=tickers, dtype=float),
            returns.reindex(columns=tickers),
            beta=beta,
            weight_bounds=(0.0, min(1.0, cap)),
        )
        optimizer.min_cvar()
        raw = pd.Series(
            optimizer.clean_weights(),
            dtype=float,
        ).reindex(tickers).fillna(0.0)
        success = True
    except Exception:
        raw = pd.Series(1.0 / len(tickers), index=tickers, dtype=float)
        success = False
    weights = cap_and_normalize_weights(
        raw,
        max_asset_weight=max_asset_weight,
    )
    portfolio_returns = returns.reindex(columns=tickers).mul(
        weights,
        axis=1,
    ).sum(axis=1)
    threshold = float(portfolio_returns.quantile(1.0 - beta))
    tail = portfolio_returns.loc[portfolio_returns <= threshold]
    return weights, {
        "method": "minimum_historical_cvar",
        "beta": float(beta),
        "optimizer_success": success,
        "in_sample_daily_var": float(-threshold),
        "in_sample_daily_cvar": (
            None if tail.empty else float(-tail.mean())
        ),
    }


def risk_allocator_case_gate(
    summary_by_model,
    candidate_name="robust_min_variance",
    baseline_name="min_variance",
):
    """Require a frozen risk candidate to improve its closest baseline."""
    candidate = summary_by_model.get(candidate_name)
    baseline = summary_by_model.get(baseline_name)
    if not candidate or not baseline:
        return {
            "status": "rejected",
            "reasons": ["Candidate or baseline metrics are missing."],
        }

    reasons = []
    if (
        candidate.get("annual_volatility") is None
        or baseline.get("annual_volatility") is None
        or candidate["annual_volatility"] >= baseline["annual_volatility"]
    ):
        reasons.append(
            f"Realized volatility does not improve {baseline_name}."
        )
    if (
        candidate.get("sharpe") is None
        or baseline.get("sharpe") is None
        or candidate["sharpe"] <= baseline["sharpe"]
    ):
        reasons.append(f"Sharpe does not improve {baseline_name}.")
    if (
        candidate.get("max_drawdown") is None
        or baseline.get("max_drawdown") is None
        or candidate["max_drawdown"] < baseline["max_drawdown"]
    ):
        reasons.append(f"Max drawdown is worse than {baseline_name}.")
    baseline_turnover = float(
        baseline.get("avg_controlled_turnover", 0.0)
    )
    if float(candidate.get("avg_controlled_turnover", 0.0)) > max(
        0.50,
        baseline_turnover * 2.0,
    ):
        reasons.append(f"Turnover is too high versus {baseline_name}.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }
