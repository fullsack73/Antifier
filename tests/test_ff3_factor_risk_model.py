import numpy as np
import pandas as pd
import pytest

import portfolio_risk_models
from portfolio_backtest import build_rebalance_targets
from portfolio_risk_models import (
    factor_model_minimum_variance_weights,
    ff3_factor_model_covariance,
)


def _synthetic_ff3(periods=380, seed=17):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-02", periods=periods, freq="B")
    factors = pd.DataFrame(
        {
            "mkt_rf": rng.normal(0.0003, 0.009, periods),
            "smb": rng.normal(0.0001, 0.005, periods),
            "hml": rng.normal(0.0001, 0.004, periods),
            "rf_daily": np.full(periods, 0.00004),
        },
        index=dates,
    )
    betas = np.asarray(
        [
            [0.7, -0.2, 0.1],
            [0.9, 0.4, -0.1],
            [1.1, -0.1, 0.3],
            [1.3, 0.2, -0.4],
            [0.5, -0.5, 0.2],
        ]
    )
    factor_values = factors[["mkt_rf", "smb", "hml"]].to_numpy()
    asset_returns = (
        factors["rf_daily"].to_numpy()[:, None]
        + factor_values @ betas.T
        + rng.normal(0.0, 0.004, (periods, len(betas)))
    )
    prices = pd.DataFrame(
        100.0 * np.exp(np.cumsum(np.log1p(asset_returns), axis=0)),
        index=dates,
        columns=["A", "B", "C", "D", "E"],
    )
    return prices, factors


def test_ff3_covariance_is_psd_and_specific_variance_is_positive():
    prices, factors = _synthetic_ff3()

    covariance, diagnostics = ff3_factor_model_covariance(prices, factors)

    np.testing.assert_allclose(covariance, covariance.T, atol=1e-12)
    assert np.linalg.eigvalsh(covariance).min() >= -1e-12
    specific = np.asarray(list(diagnostics["specific_variances"].values()))
    assert np.isfinite(specific).all()
    assert (specific >= 0.0).all()
    assert diagnostics["factor_last_date"] <= prices.index[-1].strftime(
        "%Y-%m-%d"
    )


def test_ff3_exposures_ignore_future_factors_and_future_returns():
    prices, factors = _synthetic_ff3()
    cutoff = prices.index[329]
    training_prices = prices.loc[:cutoff]
    future_mutated_prices = prices.copy()
    future_mutated_prices.loc[future_mutated_prices.index > cutoff] *= 8.0
    future_mutated_factors = factors.copy()
    future_mutated_factors.loc[
        future_mutated_factors.index > cutoff,
        ["mkt_rf", "smb", "hml"],
    ] *= -50.0

    _, expected = ff3_factor_model_covariance(
        training_prices,
        factors.loc[:cutoff],
    )
    _, repeated = ff3_factor_model_covariance(
        future_mutated_prices.loc[:cutoff],
        future_mutated_factors,
    )

    assert repeated["factor_exposures"] == expected["factor_exposures"]
    assert repeated["factor_covariance"] == expected["factor_covariance"]


def test_ff3_mapping_is_stable_under_ticker_and_date_reordering():
    prices, factors = _synthetic_ff3()
    covariance, _ = ff3_factor_model_covariance(prices, factors)

    shuffled_covariance, _ = ff3_factor_model_covariance(
        prices.loc[:, list(reversed(prices.columns))],
        factors.sample(frac=1.0, random_state=3),
    )

    pd.testing.assert_frame_equal(
        covariance.sort_index().sort_index(axis=1),
        shuffled_covariance.sort_index().sort_index(axis=1),
    )


def test_ff3_weights_are_reproducible_long_only_capped_and_fully_invested():
    prices, factors = _synthetic_ff3()
    fallback = pd.Series(0.2, index=prices.columns)

    weights, diagnostics = factor_model_minimum_variance_weights(
        prices,
        factors,
        fallback_weights=fallback,
        max_asset_weight=0.30,
    )
    repeated, _ = factor_model_minimum_variance_weights(
        prices,
        factors,
        fallback_weights=fallback,
        max_asset_weight=0.30,
    )

    pd.testing.assert_series_equal(weights, repeated)
    assert diagnostics["status"] == "candidate"
    assert weights.sum() == pytest.approx(1.0)
    assert weights.min() >= -1e-12
    assert weights.max() <= 0.300001


def test_ff3_input_and_solver_failures_use_exact_fallback(monkeypatch):
    prices, factors = _synthetic_ff3()
    fallback = pd.Series(
        [0.30, 0.25, 0.20, 0.15, 0.10],
        index=prices.columns,
    )

    missing_weights, missing_diagnostics = (
        factor_model_minimum_variance_weights(
            prices,
            factors.drop(columns="hml"),
            fallback_weights=fallback,
            max_asset_weight=0.30,
        )
    )
    pd.testing.assert_series_equal(missing_weights, fallback)
    assert missing_diagnostics["fallback_used"] is True
    assert "missing_factor_columns" in missing_diagnostics["fallback_reason"]

    monkeypatch.setattr(
        portfolio_risk_models,
        "_minimum_variance_from_covariance",
        lambda *_args, **_kwargs: (pd.Series(dtype=float), False),
    )
    failed_weights, failed_diagnostics = (
        factor_model_minimum_variance_weights(
            prices,
            factors,
            fallback_weights=fallback,
            max_asset_weight=0.30,
        )
    )
    pd.testing.assert_series_equal(failed_weights, fallback)
    assert failed_diagnostics["fallback_reason"] == "solver_failure"


def test_backtest_first_origin_does_not_use_later_prices_or_factors():
    prices, factors = _synthetic_ff3(periods=340)
    models = ["factor_model_minimum_variance"]
    original = build_rebalance_targets(
        prices,
        models=models,
        train_window=300,
        rebalance_frequency=21,
        max_asset_weight=0.30,
        factor_data=factors,
    )
    mutated_prices = prices.copy()
    mutated_factors = factors.copy()
    mutated_prices.iloc[300:] *= 4.0
    mutated_factors.iloc[300:, :3] *= -30.0
    repeated = build_rebalance_targets(
        mutated_prices,
        models=models,
        train_window=300,
        rebalance_frequency=21,
        max_asset_weight=0.30,
        factor_data=mutated_factors,
    )

    first = original["records"][0]["models"][models[0]]
    repeated_first = repeated["records"][0]["models"][models[0]]
    assert repeated_first["weights"] == pytest.approx(first["weights"])
    assert repeated_first["diagnostics"]["risk_model"][
        "factor_exposures"
    ] == first["diagnostics"]["risk_model"]["factor_exposures"]


def test_backtest_missing_factor_data_matches_ledoit_wolf_gmv_exactly():
    prices, _ = _synthetic_ff3(periods=340)
    targets = build_rebalance_targets(
        prices,
        models=["min_variance", "factor_model_minimum_variance"],
        train_window=300,
        rebalance_frequency=21,
        max_asset_weight=0.30,
        factor_data=None,
    )

    for record in targets["records"]:
        baseline = record["models"]["min_variance"]
        candidate = record["models"]["factor_model_minimum_variance"]
        assert candidate["weights"] == baseline["weights"]
        assert candidate["diagnostics"]["risk_model"][
            "status"
        ] == "ledoit_wolf_fallback"
