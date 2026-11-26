import numpy as np
import pandas as pd
import pytest

from tools import backtest_attention_mpt as experiment


def test_mpt_uses_annual_return_units_and_three_percent_risk_free():
    observed = {}
    class Frontier:
        def __init__(self, mu, covariance, weight_bounds):
            observed.update(mu=mu, bounds=weight_bounds)
            self.weights = np.full(6, 1 / 6)

        def max_sharpe(self, risk_free_rate):
            observed["risk_free"] = risk_free_rate

    gmv = {str(i): 1 / 6 for i in range(6)}
    prediction = np.linspace(.01, .06, 6)
    weights, diagnostics = experiment.mpt_weights(prediction, np.eye(6), gmv, solver=Frontier)
    np.testing.assert_allclose(observed["mu"], np.expm1(4 * prediction))
    assert observed["risk_free"] == .03
    assert observed["bounds"] == (0, .2)
    assert weights == gmv and not diagnostics["mpt_fallback_to_gmv"]
    with pytest.raises(ValueError):
        experiment.mpt_weights([np.nan] * 6, np.eye(6), gmv)


def test_optimizer_failure_is_explicit_exact_gmv_fallback():
    gmv = {str(i): 1 / 6 for i in range(6)}
    weights, diagnostics = experiment.mpt_weights(np.zeros(6), pd.DataFrame(np.eye(6), index=gmv, columns=gmv), gmv)
    assert weights == gmv
    assert diagnostics["mpt_fallback_to_gmv"]
    assert diagnostics["fallback_reason"]


@pytest.mark.parametrize("horizon", [21, 63, 126])
def test_actual_portfolio_replay_has_common_dates_costs_and_seed_average(monkeypatch, horizon):
    def bootstrap(candidate, baseline, **kwargs):
        assert kwargs["risk_free_rate"] == .03
        np.testing.assert_allclose(kwargs["risk_free_daily_returns"], 1.03 ** (1 / 252) - 1)
        return {"test": True}
    monkeypatch.setattr(experiment, "paired_block_bootstrap", bootstrap)
    prices = pd.DataFrame(100 * np.exp(np.cumsum(np.random.default_rng(10).normal(.0003, .01, (1008, 22)), axis=0)),
                          index=pd.bdate_range("2021-01-01", periods=1008),
                          columns=[f"S{i:02}" for i in range(22)])
    forecasts = {(i, seed): {"period_log_forecast": np.linspace(.01, .08, 22).tolist()}
                 for i in experiment.ORIGINS for seed in experiment.SEEDS}
    result = experiment.replay(prices, forecasts, horizon=horizon)
    assert len(result["runs"]) == 5
    np.testing.assert_allclose(list(result["daily_returns"]["mpt_ensemble"].values()),
                               list(result["daily_returns"]["mpt_seed42"].values()), atol=1e-12)
    assert result["mpt_fallback_counts"]["mpt_ensemble"] == 0
    assert set(result["daily_returns"]["gmv"]) == set(result["daily_returns"]["mpt_ensemble"])
    for name, run in result["runs"].items():
        summary = run["summary"]
        assert summary["annualized_risk_free_return"] == pytest.approx(.03)
        assert summary["transaction_costs"] > 0 and summary["rebalance_count"] == 8
        returns = np.array(list(result["daily_returns"][name].values()))
        assert np.prod(1 + returns) - 1 == pytest.approx(summary["net_cumulative_return"])
        for record in run["records"][1:]:
            assert record["controlled_turnover"] <= .35 + 1e-8
        for target in run["target_records"]:
            assert max(target["models"]["min_variance"]["weights"].values()) <= .2 + 1e-8
            if name != "gmv":
                assert target["experiment_diagnostics"]["model_forecast_horizon"] == horizon


def test_fit_rejects_incomplete_training_window():
    pytest.importorskip("tensorflow")
    with pytest.raises(ValueError, match="504"):
        experiment.fit_period_forecast(np.ones((503, 22)), 42)
