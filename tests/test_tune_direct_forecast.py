import numpy as np
import pytest

from tools.tune_direct_forecast import CONFIGS, choose_candidate, fit_candidate


def test_selection_uses_validation_only_with_fixed_tie_order():
    results = [{"validation_rmse": .2, "prediction": 1e9} for _ in CONFIGS]
    results[4]["validation_rmse"] = .1
    assert choose_candidate(results) == 4
    results[0]["validation_rmse"] = .1
    assert choose_candidate(results) == 0
    with pytest.raises(ValueError):
        choose_candidate(results[:3])


def test_default_candidate_matches_production_forecast():
    pytest.importorskip("tensorflow")
    from direct_horizon_forecast import DirectHorizonTransformerForecastModel
    prices = np.exp(np.cumsum(np.random.default_rng(5).normal(0, .01, 504)))
    result = fit_candidate(prices, CONFIGS[0])
    model = DirectHorizonTransformerForecastModel()
    model.train(prices)
    actual = model.predict(63)
    assert actual["source"] == "transformer"
    assert result["prediction"] == pytest.approx(actual["expected_return"] / 4, abs=1e-7)
    assert result["validation_rmse"] == pytest.approx(actual["diagnostics"]["validation_period_rmse"], abs=1e-7)
    assert result["train_rows"] == 280 and result["validation_rows"] == 39
    assert result["epochs_run"] <= 5


def test_cli_keeps_current_window_and_resumes_completed_fits(tmp_path, monkeypatch):
    import json
    import sys
    import pandas as pd
    import tools.tune_direct_forecast as tuning
    prices = pd.DataFrame({"TEST": np.exp(np.arange(1008) * .001)},
                          index=pd.bdate_range("2020-01-01", periods=1008))
    csv = tmp_path / "prices.csv"
    prices.to_csv(csv)
    histories = []
    def fit(history, config):
        histories.append(history.copy())
        return {"validation_rmse": .1 if config == CONFIGS[2] else .2,
                "prediction": float(history[-1]), "epochs_run": 3, "best_epoch": 1}
    monkeypatch.setattr(tuning, "fit_candidate", fit)
    monkeypatch.setattr(tuning.importlib.metadata, "version", lambda _: "test")
    monkeypatch.setattr(sys, "argv", ["tune", "--csv", str(csv), "--output-dir", str(tmp_path / "result")])
    tuning.main()
    assert len(histories) == 96 and all(len(h) == 504 for h in histories)
    np.testing.assert_allclose(histories[0], prices.iloc[:504, 0])
    np.testing.assert_allclose(histories[-1], prices.iloc[441:945, 0])
    rows = json.loads((tmp_path / "result/rows.json").read_text())
    assert len(rows) == 8 and all(r["selected_config"] == 2 for r in rows)
    monkeypatch.setattr(tuning, "fit_candidate", lambda *_: pytest.fail("must reuse checkpoints"))
    tuning.main()
