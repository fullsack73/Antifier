import json

import numpy as np
import pandas as pd
import pytest

from tools import compare_forecast_mpt_before_after as comparison


def fixture():
    dates = pd.bdate_range("2017-01-01", periods=631)
    rng = np.random.default_rng(73)
    panel = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.0003, .01, (631, 6)), axis=0)),
                         index=dates, columns=list("ABCDEF"))
    tasks = [{"id": str(i), "origin": str(dates[i].date()), "index": i} for i in [504, 567]]
    improved = []
    for task in tasks:
        i = task["index"]
        scores = {ticker: .01 * (n + 1) for n, ticker in enumerate(panel)}
        weights, diag = comparison.shared.weights_for_origin(panel.iloc[i - 504:i], scores)
        improved.append({"task": task, "weights": weights, "diagnostics": diag,
                         "period_end": str(dates[i + 63].date()), "predictions": {k: {"raw": v} for k, v in scores.items()}})
    parent_manifest = {"tasks": tasks, "sha256": "parent", "limitations": ["diagnostic_only"]}
    reference = comparison.shared.replay(panel, parent_manifest, improved)
    manifest = {"tasks": tasks, "sha256": "child", "parent_manifest_sha256": "parent",
                "improved_reference": reference["summary"]["model_mpt"], "improved_fallback_count": 0,
                "limitations": ["diagnostic_only"]}
    legacy = [{"task": c["task"], "weights": c["weights"]["model_mpt"],
               "diagnostics": c["diagnostics"], "legacy_period_scores": {k: v["raw"] for k, v in c["predictions"].items()}}
              for c in improved]
    return panel, manifest, legacy, improved


def test_same_weights_have_zero_difference_and_reproduce_parent(tmp_path):
    panel, manifest, legacy, improved = fixture()
    result = comparison.replay(panel, manifest, legacy, improved)
    assert result["improved_reference_reproduced"]
    assert all(v == pytest.approx(0) for v in result["improved_minus_legacy"].values())
    for name, daily in result["daily_returns"].items():
        assert np.prod(1 + np.array(list(daily.values()))) - 1 == pytest.approx(result["summary"][name]["net_cumulative_return"])
    comparison.report(tmp_path, result)
    assert json.loads((tmp_path / "result.json").read_text())["promotion_eligible"] is False


def test_missing_origin_and_changed_improved_result_are_rejected():
    panel, manifest, legacy, improved = fixture()
    with pytest.raises(ValueError, match="Missing or reordered"):
        comparison.replay(panel, manifest, legacy[:1], improved)
    manifest["improved_reference"]["cagr"] += .01
    with pytest.raises(ValueError, match="did not reproduce"):
        comparison.replay(panel, manifest, legacy, improved)


def test_worker_uses_api_clipped_output_and_identical_parent_training(monkeypatch, tmp_path):
    panel, _, _, _ = fixture()
    task = {"id": "origin", "index": 504, "origin": str(panel.index[504].date())}
    parent = tmp_path / "parent"
    (parent / "checkpoints").mkdir(parents=True)
    train = panel.iloc[:504]
    saved = {"train_prices_sha256": comparison.digest(train.to_numpy().tolist()),
             "train_start": str(train.index[0].date()), "train_end": str(train.index[-1].date()),
             "period_end": str(panel.index[567].date())}
    (parent / "checkpoints/origin.json").write_text(json.dumps(saved))
    output = tmp_path / "child"
    (output / "checkpoints").mkdir(parents=True)
    monkeypatch.setattr(comparison, "verify", lambda m: None)
    monkeypatch.setattr(comparison.shared, "panel", lambda p: panel)
    calls = []
    def old_forecast(values, horizon, seed):
        calls.append(values)
        assert horizon == 63 and seed == 42
        return {"raw": 1., "original_standalone": .95, "original_hybrid_component": .69 / 4}
    monkeypatch.setattr(comparison, "original_transformer", old_forecast)
    seen = {}
    def weights(values, scores):
        seen.update(scores=scores)
        return {"model_mpt": {k: 1 / 6 for k in panel}}, {"mpt_fallback_to_gmv": False}
    monkeypatch.setattr(comparison.shared, "weights_for_origin", weights)
    manifest = {"tasks": [task], "parent": str(parent), "inputs": {}, "tickers": list(panel), "sha256": "test"}
    comparison.worker(output, manifest, 0)
    assert all(v == .69 / 4 for v in seen["scores"].values())
    for n, values in enumerate(calls):
        np.testing.assert_array_equal(values, train.iloc[:, n].to_numpy())
    saved["train_prices_sha256"] = "different"
    (parent / "checkpoints/origin.json").write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="training input mismatch"):
        comparison.worker(output, manifest, 0)


def test_verify_rejects_parent_artifact_drift(monkeypatch, tmp_path):
    parent = tmp_path / "parent.json"
    parent.write_text("original")
    monkeypatch.setattr(comparison, "sources", lambda: {"source": "same"})
    manifest = {"sources": {"source": "same"}, "parent_files": {str(parent): comparison.file_digest(parent)},
                "inputs": {}, "environment": {"packages": {}}}
    manifest["sha256"] = comparison.digest(manifest)
    comparison.verify(manifest)
    parent.write_text("changed")
    with pytest.raises(ValueError, match="Parent artifact drift"):
        comparison.verify(manifest)
