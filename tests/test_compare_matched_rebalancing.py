import copy
import numpy as np
import pandas as pd
import pytest

from tools import compare_matched_rebalancing as experiment


@pytest.mark.parametrize("horizon,count", [(21, 24), (42, 12), (63, 8), (126, 4)])
def test_actual_execution_uses_matched_interval_and_common_full_period(horizon, count):
    prices = pd.DataFrame(100 * np.exp(np.cumsum(np.random.default_rng(6).normal(.0003, .01, (1008, 6)), axis=0)),
                          index=pd.bdate_range("2021-01-01", periods=1008), columns=list("ABCDEF"))
    signals = experiment.origins(len(prices), horizon)
    assert len(signals) == count
    forecasts = {(i, s): {"period_log_forecast": np.linspace(.01, .06, 6).tolist()}
                 for i in signals for s in experiment.SEEDS}
    result = experiment.replay(prices, forecasts, horizon)
    assert result["settings"]["rebalance_frequency"] == horizon
    assert result["settings"]["forecast_horizon"] == horizon
    for name, run in result["runs"].items():
        records = run["records"]
        assert len(records) == count
        assert [r["train_end_date"] for r in records] == [str(prices.index[i].date()) for i in signals]
        assert [r["rebalance_date"] for r in records] == [str(prices.index[i+1].date()) for i in signals]
        daily = np.array(list(result["daily_returns"][name].values()))
        assert len(daily) == 503
        assert np.prod(1+daily)-1 == pytest.approx(run["summary"]["net_cumulative_return"])
        assert run["summary"]["transaction_costs"] > 0
        assert run["summary"]["annualized_risk_free_return"] == pytest.approx(.03)
        assert all(r["controlled_turnover"] <= .35+1e-8 for r in records[1:])
    for target in result["runs"]["mpt_ensemble"]["target_records"]:
        weights = list(target["models"]["min_variance"]["weights"].values())
        assert np.isclose(sum(weights),1) and min(weights)>=-1e-8 and max(weights)<=.2+1e-8


def test_summary_has_schedule_specific_gmv_and_compares_to_fixed63(monkeypatch):
    monkeypatch.setattr(experiment, "bootstrap", lambda *a: {"test": True})
    results = {}
    for h in experiment.HORIZONS:
        runs = {"gmv": {"summary": {"sharpe": h/1000}}, "mpt_ensemble": {"summary": {"sharpe": 2 if h==21 else 1}}}
        runs.update({f"mpt_seed{s}": {"summary": {"sharpe": 1}} for s in experiment.SEEDS})
        results[h] = {"runs": runs, "daily_returns": {"gmv": {"2024-01-01": h/10000},
                     "mpt_ensemble": {"2024-01-01": .01}}, "mpt_fallback_counts": {}}
    fixed = copy.deepcopy(results)
    fixed[21]["runs"]["mpt_ensemble"]["summary"]["sharpe"] = .5
    summary = experiment.summarize(results, fixed)
    assert summary["descriptive_best_horizon"] == 21
    assert summary["by_horizon"]["21"]["fixed63_rebalancing_sharpe"] == .5
    assert summary["by_horizon"]["21"]["gmv_same_schedule"]["sharpe"] == .021
    assert summary["by_horizon"]["126"]["gmv_same_schedule"]["sharpe"] == .126
    results[21]["daily_returns"]["mpt_ensemble"] = {"2024-01-02": .01}
    with pytest.raises(ValueError, match="same daily"):
        experiment.summarize(results, fixed)


def test_reused_forecasts_require_complete_finite_cohort():
    experiment.valid_forecast({"period_log_forecast": [.1]*22},22)
    with pytest.raises(ValueError):
        experiment.valid_forecast({"period_log_forecast": [.1]*21},22)
    with pytest.raises(ValueError):
        experiment.valid_forecast({"period_log_forecast": [.1]*21+[np.nan]},22)
