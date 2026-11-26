import numpy as np
import pandas as pd
import pytest

from tools import compare_attention_horizons as experiment
from tools.backtest_attention_mpt import mpt_weights
from tools.benchmark_stock_attention import prepare
from direct_horizon_forecast import supervised_returns


@pytest.mark.parametrize("horizon", experiment.HORIZONS)
def test_preparation_uses_actual_horizon_and_excludes_future(horizon):
    prices = np.exp(np.cumsum(np.random.default_rng(8).normal(0, .01, (504 + horizon, 3)), axis=0))
    result = prepare(prices, horizon=horizon)
    changed = prices.copy()
    changed[504:] *= 2
    alternate = prepare(changed, horizon=horizon)
    for i in range(5):
        np.testing.assert_array_equal(result[i], alternate[i])
    assert result[0].shape == (444 - horizon, 3, 60, 1)
    _, _, targets, ends = supervised_returns(prices[:504, 0], horizon)
    restored = result[5].inverse_transform(result[1].reshape(-1, 1)).reshape(result[1].shape)
    np.testing.assert_allclose(restored[:, 0], targets, atol=1e-7)
    assert max(ends[result[2]] + horizon) <= min(ends[result[3]])
    np.testing.assert_allclose(alternate[-1] - result[-1], np.log(2))
    if horizon == 63:
        default = prepare(prices)
        for i in range(5):
            np.testing.assert_array_equal(default[i], result[i])


@pytest.mark.parametrize("horizon", experiment.HORIZONS)
def test_mpt_annualization_uses_model_horizon(horizon):
    observed = {}
    class Frontier:
        def __init__(self, mu, covariance, weight_bounds):
            observed["mu"] = mu
            self.weights = np.full(6, 1 / 6)

        def max_sharpe(self, risk_free_rate):
            assert risk_free_rate == .03

    predictions = np.linspace(.005, .04, 6)
    gmv = {str(i): 1 / 6 for i in range(6)}
    _, info = mpt_weights(predictions, np.eye(6), gmv, solver=Frontier, horizon=horizon)
    assert not info["mpt_fallback_to_gmv"]
    np.testing.assert_allclose(observed["mu"], np.expm1(predictions * 252 / horizon))


def test_forecast_metrics_use_same_completed_dates_for_all_horizons():
    prices = pd.DataFrame(np.exp(np.cumsum(np.random.default_rng(6).normal(.001, .01, (1008, 22)), axis=0)),
                          index=pd.bdate_range("2020-01-01", periods=1008))
    dates = []
    for horizon in experiment.HORIZONS:
        forecasts = {(i, s): {"period_log_forecast": np.log(prices.iloc[min(i + horizon, 1007)] / prices.iloc[i]).tolist()}
                     for i in experiment.ORIGINS for s in experiment.SEEDS}
        metrics = experiment.forecast_metrics(prices, forecasts, horizon)
        assert metrics["stock_date_count"] == 154
        assert metrics["period_log_rmse"] == pytest.approx(0, abs=1e-15)
        assert metrics["mse_skill_vs_zero"] == pytest.approx(1)
        assert metrics["mean_rank_ic"] == pytest.approx(1)
        dates.append(metrics["common_signal_dates"])
    assert all(d == dates[0] for d in dates)


@pytest.mark.parametrize("horizon", [0, -1, True, 1.5])
def test_rejects_invalid_horizon(horizon):
    with pytest.raises(ValueError):
        prepare(np.ones((567, 2)), horizon=horizon)


def test_summary_selects_ensemble_sharpe_and_rejects_changed_gmv(monkeypatch):
    monkeypatch.setattr(experiment, "paired_block_bootstrap", lambda *a, **kw: {"test": True})
    results = {}
    for h in experiment.HORIZONS:
        # A high single-seed Sharpe must not determine the selected horizon.
        runs = {"gmv": {"summary": {"sharpe": .7}}, "mpt_ensemble": {"summary": {"sharpe": 2 if h == 42 else 1}}}
        runs.update({f"mpt_seed{s}": {"summary": {"sharpe": 100 if h == 21 else 1}} for s in experiment.SEEDS})
        results[h] = {"runs": runs, "daily_returns": {"gmv": {"2024-01-01": .01}, "mpt_ensemble": {"2024-01-01": .02}},
                      "forecast_metrics": {}, "mpt_fallback_counts": {}}
    assert experiment.summarize(results)["descriptive_best_horizon"] == 42
    results[21]["daily_returns"]["gmv"]["2024-01-01"] = .03
    with pytest.raises(ValueError, match="GMV changed"):
        experiment.summarize(results)
