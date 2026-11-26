import pytest

from tools.evaluate_stock_attention import score


def test_metrics_keep_seeds_separate_and_do_not_count_repeats_as_new_outcomes():
    rows = [{"seed": seed, "origin": "2025-01-01", "ticker": str(i), "realized": actual,
             "cross_stock": actual, "temporal_only": .4 - actual}
            for seed in (42, 43) for i, actual in enumerate((.1, .2, .3))]
    result = score(rows, "cross_stock")
    assert result["rows"] == 6 and result["unique_stock_dates"] == 3
    assert result["rmse"] == 0
    assert result["mean_rank_ic"] == pytest.approx(1)
    assert result["mean_top_bottom_log_return_spread"] == pytest.approx(.2)
    assert score(rows, "temporal_only")["mean_rank_ic"] == pytest.approx(-1)


def test_cli_runs_paired_cases_and_resumes_fits(tmp_path, monkeypatch):
    import json
    import sys
    import numpy as np
    import pandas as pd
    import tools.evaluate_stock_attention as evaluation
    prices = pd.DataFrame(np.exp(np.arange(1008)[:, None] * np.array([.001, .002, .003])),
                          columns=["A", "B", "C"], index=pd.bdate_range("2020-01-01", periods=1008))
    csv = tmp_path / "prices.csv"
    prices.to_csv(csv)
    calls = []
    def fit(x, y, train, validation, latest, cross, seed):
        assert x.shape == (381, 3, 60, 1)
        assert len(train) == 280 and len(validation) == 39
        calls.append((cross, seed))
        return {"scaled_prediction": [0., 0., 0.], "fit_seconds": .01}
    monkeypatch.setattr(evaluation, "benchmark", fit)
    monkeypatch.setattr(evaluation.importlib.metadata, "version", lambda _: "test")
    monkeypatch.setattr(sys, "argv", ["evaluate", "--csv", str(csv), "--output-dir", str(tmp_path / "result")])
    evaluation.main()
    assert len(calls) == 48
    result = json.loads((tmp_path / "result/summary.json").read_text())
    assert result["metrics"]["cross_stock"]["unique_stock_dates"] == 24
    assert result["metrics"]["cross_stock"]["rows"] == 72
    assert result["paired_mse_cross_minus_temporal"] == 0
    monkeypatch.setattr(evaluation, "benchmark", lambda *_: pytest.fail("must reuse completed fits"))
    evaluation.main()
