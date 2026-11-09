import numpy as np
import pandas as pd
import pytest

from tools import compare_improved_forecast_portfolios as comparison


def prices():
    index = pd.bdate_range("2017-01-01", periods=631)
    rng = np.random.default_rng(12)
    values = 100 * np.exp(np.cumsum(rng.normal(.0004, .012, (631, 6)), axis=0))
    return pd.DataFrame(values, index=index, columns=list("ABCDEF"))


def test_forecast_annualization_and_identical_risk_inputs():
    train = prices().iloc[:504]
    seen = {}
    class Solver:
        def __init__(self, mu, covariance, weight_bounds):
            seen.update(mu=mu, covariance=covariance, bounds=weight_bounds)
        def max_sharpe(self, risk_free_rate):
            seen["rf"] = risk_free_rate
        def clean_weights(self):
            return {k: 1 / 6 for k in train}
    weights, d = comparison.weights_for_origin(train, {k: .02 for k in train}, Solver)
    assert np.allclose(seen["mu"], np.expm1(.08))
    assert seen["rf"] == .02 and seen["bounds"] == (0., .2)
    assert not d["mpt_fallback_to_gmv"]
    assert weights["gmv_model"] == pytest.approx(weights["gmv"])


def test_mpt_failure_is_explicit_and_exact_gmv_fallback():
    train = prices().iloc[:504]
    class Fails:
        def __init__(self, *args, **kwargs):
            raise ValueError("no positive excess return")
    weights, diag = comparison.weights_for_origin(train, {k: -.01 for k in train}, Fails)
    assert weights["model_mpt"] == weights["gmv"]
    assert diag["mpt_fallback_to_gmv"]
    assert diag["fallback_reason"] == "no positive excess return"


def test_missing_forecast_cannot_silently_shrink_universe():
    with pytest.raises(ValueError, match="Every asset"):
        comparison.weights_for_origin(prices().iloc[:504], {"A": .1})


def test_three_portfolios_replay_identical_prices_costs_and_calendar(tmp_path):
    panel = prices()
    tasks = [{"id": str(i), "origin": str(panel.index[i].date()), "index": i} for i in [504, 567]]
    manifest = {"tasks": tasks, "sha256": "test", "limitations": ["diagnostic_only"]}
    checkpoints = []
    for task in tasks:
        i = task["index"]
        scores = {k: float(j + 1) * .01 for j, k in enumerate(panel)}
        weights, diag = comparison.weights_for_origin(panel.iloc[i - 504:i], scores)
        checkpoints.append({"task": task, "weights": weights, "diagnostics": diag,
                            "period_end": str(panel.index[i + 63].date()),
                            "predictions": {k: {"raw": v} for k, v in scores.items()}})
    result = comparison.replay(panel, manifest, checkpoints)
    assert not result["promotion_eligible"]
    assert result["origins"] == 2
    assert set(result["summary"]) == set(comparison.NAMES)
    dates = [list(d) for d in result["daily_returns"].values()]
    assert all(d == dates[0] for d in dates)
    assert result["daily_returns_include_initial_cost"]
    for name, returns in result["daily_returns"].items():
        assert np.prod(1 + np.array(list(returns.values()))) - 1 == pytest.approx(result["summary"][name]["net_cumulative_return"], abs=1e-10)
    for records in result["rebalance_records"].values():
        assert len(records) == 2
        assert all(sum(r["weights"].values()) == pytest.approx(1.) for r in records)
    comparison.report(tmp_path, result)
    assert (tmp_path / "result.json").exists() and (tmp_path / "report.md").exists()
    with pytest.raises(ValueError, match="missing forecast"):
        comparison.replay(panel, manifest, checkpoints[:1])


def test_net_daily_returns_preserves_already_anchored_series_and_rejects_unexplained_drift():
    run = {"daily_returns_by_model": {"min_variance": {"2020-01-02": .1}},
           "summary_by_model": {"min_variance": {"net_cumulative_return": .1}},
           "rebalance_records": [{"portfolio_value_before_cost": 100, "portfolio_value_after_cost": 99}]}
    assert comparison.net_daily_returns(run).iloc[0] == .1
    run["summary_by_model"]["min_variance"]["net_cumulative_return"] = .089
    assert comparison.net_daily_returns(run).iloc[0] == pytest.approx(.089)
    run["summary_by_model"]["min_variance"]["net_cumulative_return"] = .5
    with pytest.raises(ValueError, match="net wealth"):
        comparison.net_daily_returns(run)


def test_worker_training_stops_before_execution_date(monkeypatch, tmp_path):
    panel = prices()
    monkeypatch.setattr(comparison, "TICKERS", list(panel))
    monkeypatch.setattr(comparison, "verify", lambda m: None)
    monkeypatch.setattr(comparison, "panel", lambda p: panel)
    seen = []
    def forecast(values, **kwargs):
        seen.append(values)
        assert kwargs == {"horizon": 63, "position": False, "direct": True, "seed": 42, "epochs": 5}
        return {"raw": .02}
    monkeypatch.setattr(comparison, "transformer_forecast", forecast)
    (tmp_path / "checkpoints").mkdir()
    task = {"id": "date", "index": 504, "origin": str(panel.index[504].date())}
    manifest = {"tasks": [task], "sha256": "test", "inputs": {}}
    comparison.worker(tmp_path, manifest, 0)
    for j, values in enumerate(seen):
        np.testing.assert_array_equal(values, panel.iloc[:504, j].to_numpy())
    import json
    saved = json.loads((tmp_path / "checkpoints/date.json").read_text())
    assert saved["train_end"] < task["origin"]


def test_manifest_rejects_data_or_source_drift(monkeypatch, tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("initial")
    monkeypatch.setattr(comparison, "sources", lambda: {"source": "abc"})
    manifest = {"sources": {"source": "abc"}, "inputs": {"data": {"path": str(path), "sha256": comparison.file_digest(path)}},
                "environment": {"packages": {}}}
    manifest["sha256"] = comparison.digest(manifest)
    comparison.verify(manifest)
    path.write_text("changed")
    with pytest.raises(ValueError, match="Input drift"):
        comparison.verify(manifest)
