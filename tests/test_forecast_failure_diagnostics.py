import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import forecast_failure_diagnostics as diagnostic

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("failure_cli", ROOT / "tools/diagnose_forecast_failures.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_targets_preserve_dates_and_log_units():
    prices = np.exp(np.arange(800) * .002)
    assert diagnostic.target_at(prices, 504, 63) == pytest.approx(.126)
    prices[520] = np.nan
    with pytest.raises(ValueError, match="consecutive"):
        diagnostic.target_at(prices, 504, 63)
    with pytest.raises(ValueError, match="consecutive"):
        diagnostic.supervised_returns(prices)


def test_direct_labels_completed_and_validation_purged():
    prices = np.exp(np.arange(504) * .001)
    returns, x, y, ends = diagnostic.supervised_returns(prices, 63)
    train, validation = diagnostic.purged_split(ends, 63)
    assert y == pytest.approx(np.full(len(y), .063))
    assert ends[train[-1]] + 63 <= ends[validation[0]]
    assert x.shape == (len(ends), 60, 1)
    assert ends[-1] + 63 == len(returns)


def test_output_conventions_retain_raw_and_expose_clipping_difference():
    r = diagnostic.period_outputs(2., 1., 63)
    assert r["raw"] == 2.
    assert r["daily_limited"] == 1.
    assert r["canonical"] == 2.
    assert r["original_standalone"] == 1.
    assert r["original_hybrid_component"] == pytest.approx(.69 / 4)


class FakeARIMA:
    order = (1, 0, 0)
    with_intercept = True
    arima_res_ = SimpleNamespace(mle_retvals={"converged": True})

    def resid(self):
        return np.tile([-.1, .1], 100)

    def predict(self, n_periods, return_conf_int=True):
        return np.full(n_periods, .001), np.tile([-.2, .2], (n_periods, 1))


def test_arima_actual_path_and_false_uncertainty():
    result = diagnostic.arima_forecast(np.exp(np.arange(504) * .001), 63,
                                      loader=lambda: lambda *a, **k: FakeARIMA())
    assert result["path"] == "arima"
    assert result["raw"] == pytest.approx(.063)
    assert result["reported_uncertainty"] == .01
    assert result["residual_std"] == pytest.approx(.1)
    assert result["order"] == [1, 0, 0]


def test_arima_failures_are_not_labelled_as_successful_arima():
    def fail(*a, **k):
        raise ValueError("forced")
    trend = diagnostic.arima_forecast(np.exp(np.arange(504) * .001), 63, loader=lambda: fail)
    assert trend["path"] == "trend_fallback"
    assert trend["arima_error"] == "forced"
    short = diagnostic.arima_forecast([1., 2.], 63)
    assert short["path"] == "short_input_constant"
    assert short["raw"] == .05


def test_nested_arima_trend_failure_traces_constant_fallback(monkeypatch):
    import forecast_models
    def fail(*a, **k):
        raise ValueError("forced nested failure")
    monkeypatch.setattr(forecast_models, "linregress", fail)
    result = diagnostic.arima_forecast(np.exp(np.arange(504) * .001), loader=lambda: fail)
    assert result["path"] == "constant_fallback"
    assert result["raw"] == .05
    assert result["trend_error"] == "forced nested failure"


def test_hybrid_error_decomposition_including_covariance_and_bias():
    actual = np.array([.1, -.1, .2, .05])
    r = diagnostic.mixture_decomposition(actual, np.array([.2, -.05, .15, .1]),
                                         np.array([0., -.2, .3, .03]))
    assert r["reconstructed_mse"] == pytest.approx(r["observed_mse"], abs=1e-15)


def test_original_hybrid_decomposition_uses_actual_clipped_component():
    rows = [cli.record(name, "2020-01-01", "A", 0., value) for name, value in [
        ("original_arima", .1), ("original_transformer", 1.),
        ("original_transformer_component", .2), ("original_hybrid", .15)]]
    result = diagnostic.summarize(rows, [])
    assert result["mixtures"]["original"]["observed_mse"] == pytest.approx(.15 ** 2)
    without_component = diagnostic.summarize([r for r in rows if r["model"] != "original_transformer_component"], [])
    assert "original" not in without_component["mixtures"]


def test_imputation_only_depends_on_training_data():
    train = np.array([[1., np.nan], [2., 4.], [3., 6.], [4., 8.]])
    y = np.array([1., 2., 3., 4.])
    a = diagnostic.ridge_predict(train, y, [[2., np.nan]])
    b = diagnostic.ridge_predict(train, y, [[2., np.nan], [10000., -10000.]])
    assert a[0] == pytest.approx(b[0])


def test_clustered_bootstrap_does_not_count_duplicate_tickers_as_dates():
    rows = []
    for i in range(10):
        for ticker in ["A", "B"]:
            for name, mse in [("candidate", .01), ("baseline", .04)]:
                rows.append({"origin": f"2020-{i + 1:02d}-01", "ticker": ticker,
                             "seed": 42, "model": name, "error_squared": mse})
    result = diagnostic.paired_mse_bootstrap(pd.DataFrame(rows), "candidate", "baseline", 200)
    assert result["origins"] == 10
    assert result["paired_rows"] == 20
    assert result["mse_difference"] == pytest.approx(-.03)
    assert result["upper_95"] < 0


def test_unavailable_hypotheses_stay_in_multiple_test_family():
    rows = []
    for i in range(10):
        for name, value in [("candidate", .1), ("baseline", .2)]:
            rows.append(cli.record(name, f"2020-{i+1:02d}-01", "A", .0, value))
    r = diagnostic.summarize(rows, [("candidate", "baseline"), ("absent", "baseline")])
    assert r["comparisons"]["absent_vs_baseline"]["holm"]["raw_p_value"] == 1.
    assert r["metrics"]["candidate"]["date_equal_mse"] == pytest.approx(.01)


def test_future_prices_and_filings_do_not_change_asof_inputs():
    dates = pd.bdate_range("2017-01-01", periods=1100)
    prices = pd.DataFrame({"AAPL": np.exp(np.arange(1100) * .001)}, index=dates)
    members = pd.DataFrame([{"effective_date": dates[0], "ticker": "AAPL", "in_universe": True}])
    original = cli.usable_history(prices, members, 600, "AAPL", 504)
    prices.loc[dates[664]:, "AAPL"] *= 100
    changed = cli.usable_history(prices, members, 600, "AAPL", 504)
    np.testing.assert_array_equal(original, changed)
    pit = pd.DataFrame([{"ticker": "AAPL", "available_date": dates[500], "sector": "Tech",
                         "market_cap": 1e9, "quality": .1, "profitability": .2, "valuation": .3, "liquidity": .4},
                        {"ticker": "AAPL", "available_date": dates[700], "sector": "Tech",
                         "market_cap": 1e9, "quality": 100, "profitability": .2, "valuation": .3, "liquidity": .4}])
    a = cli.point_in_time_snapshot(pit, dates[600])
    pit.loc[1, "quality"] = -100
    pd.testing.assert_frame_equal(a, cli.point_in_time_snapshot(pit, dates[600]))


def test_checkpoint_resume_requires_same_contract(tmp_path):
    (tmp_path / "checkpoints").mkdir()
    task = {"id": "123", "stage": "A", "kind": "integrity"}
    manifest = {"sha256": "abc", "tasks": [task]}
    cli.write_json(cli.checkpoint_path(tmp_path, task),
                   {"task": task, "manifest_sha256": "abc", "status": "ok", "result": {}})
    assert len(cli.read_checkpoints(tmp_path, manifest)) == 1
    manifest["sha256"] = "different"
    with pytest.raises(ValueError, match="Checkpoint"):
        cli.read_checkpoints(tmp_path, manifest)


def test_gate_requires_all_positive_controls_and_seeds():
    checkpoints = [{"task": {"stage": "A"}, "status": "ok", "result": {"checks_passed": True}}]
    for process in ["ar1", "order", "noise", "external"]:
        for seed in [101, 102, 103]:
            checkpoints.append({"task": {"stage": "B"}, "status": "ok", "result": {
                "process": process, "data_seed": seed,
                "transformer": {str(s): {"mse_ratio": .5} for s in cli.SEEDS}, "arima_mse_ratio": .5,
                "external_visible_mse_ratio": .01}})
    assert cli.gate_results(checkpoints)["transformer"]["passed"]
    import json
    gates = cli.gate_results(checkpoints)
    assert json.loads(json.dumps(gates)) == gates
    assert type(gates["transformer"]["processes"]["ar1"]["passed"]) is bool
    checkpoints.pop()
    assert not cli.gate_results(checkpoints)["transformer"]["passed"]


def test_manifest_rejects_source_or_data_drift(monkeypatch, tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("a,b\n1,2\n")
    manifest = {"sources": {"source": "hash"}, "inputs": {"data": {"path": str(path), "sha256": diagnostic.file_digest(path)}}}
    manifest["sha256"] = diagnostic.digest(manifest)
    monkeypatch.setattr(cli, "source_hashes", lambda: {"source": "hash"})
    cli.verify_manifest(manifest)
    path.write_text("changed")
    with pytest.raises(ValueError, match="Input data drift"):
        cli.verify_manifest(manifest)


def test_budget_skips_work_and_resume_does_not_rerun(monkeypatch, tmp_path):
    task = {"id": "123", "stage": "A", "kind": "integrity"}
    manifest = {"sha256": "abc", "tasks": [task]}
    cli.write_json(tmp_path / "run_state.json", {"manifest_sha256": "abc", "started_at": 0,
                                                "stage_spent": {s: 0 for s in cli.STAGES}, "durations": {}})
    monkeypatch.setattr(cli, "verify_manifest", lambda _: None)
    monkeypatch.setattr(cli, "render_report", lambda *_: None)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: pytest.fail("Budget-exhausted job must not launch"))
    cli.run_campaign(tmp_path, manifest)
    result = json_read(cli.checkpoint_path(tmp_path, task))
    assert result["status"] == "budget_not_run"
    cli.run_campaign(tmp_path, manifest)
    assert json_read(cli.checkpoint_path(tmp_path, task)) == result


def test_hybrid_uses_same_components_and_preserves_target_dates(monkeypatch):
    dates = pd.bdate_range("2017-01-01", periods=800)
    prices = pd.DataFrame({"AAPL": np.exp(np.arange(800) * .001)}, index=dates)
    calls = []
    def tf(*args, **kwargs):
        calls.append(kwargs["trained_model"])
        return diagnostic.period_outputs(.4, .3, args[1])
    monkeypatch.setattr(cli, "original_transformer", tf)
    monkeypatch.setattr(cli, "arima_forecast", lambda *a, **k: {"raw": .1, "path": "arima"})
    trained = object()
    result = cli.baseline_predictions(prices, 504, "AAPL", prices.AAPL[:505].to_numpy(),
                                      {"arima": {"passed": True}, "transformer": {"passed": True}}, trained, None)
    by_model = {r["model"]: r for r in result["records"]}
    assert by_model["canonical_hybrid"]["prediction"] == pytest.approx(.25)
    assert by_model["original_hybrid"]["prediction"] == pytest.approx((.1 + .69 / 4) / 2)
    assert by_model["canonical_hybrid"]["target_date"] == str(dates[567].date())
    assert all(v is trained for v in calls)


def test_report_with_pending_tasks_and_factorial_results(tmp_path):
    (tmp_path / "checkpoints").mkdir()
    tasks = [{"id": "integrity", "stage": "A", "kind": "integrity"}]
    manifest = {"sha256": "abc", "origins": ["2020-01-01"], "tasks": tasks,
                "comparisons": cli.COMPARISONS, "limitations": ["diagnostic_only"]}
    cli.write_json(cli.checkpoint_path(tmp_path, tasks[0]), {"manifest_sha256": "abc", "task": tasks[0],
                   "status": "ok", "result": {"checks_passed": True, "findings": ["test finding"]}})
    result = cli.render_report(tmp_path, manifest)
    assert not result["promotion_eligible"]
    assert not result["gates"]["transformer"]["passed"]
    assert result["findings"][0]["classification"] == "구현으로 확인"
    assert (tmp_path / "report.md").exists()


def json_read(path):
    import json
    return json.loads(path.read_text())
