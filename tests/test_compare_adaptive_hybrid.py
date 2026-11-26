import pytest

from tools.compare_adaptive_hybrid import cross_error_weight, summarize


@pytest.mark.parametrize("errors,expected", [
    ([[2., 1.]] * 3, .25),
    ([[1., 2.]] * 3, .75),
    ([[1., 1.]] * 3, .5),
    ([[1., -1.]] * 3, .5),
    ([], .5),
    ([[float("nan"), 1.]] * 3, .5),
])
def test_cross_error_weight_handles_bias_correlation_and_degenerate_errors(errors, expected):
    assert cross_error_weight(errors) == pytest.approx(expected)


def test_comparison_uses_common_completed_cases_and_ranking():
    rows = [
        {"origin": "2024-01-01", "realized": .1, "arima": .2, "transformer": .1, "equal": .15, "adaptive": .1},
        {"origin": "2024-01-01", "realized": .2, "arima": .1, "transformer": .2, "equal": .15, "adaptive": .2},
        {"origin": "2024-01-01", "realized": .3, "arima": .3, "transformer": .3, "equal": .3, "adaptive": .3},
        {"origin": "2024-04-01", "realized": .1, "arima": None, "transformer": .1, "equal": None, "adaptive": None},
    ]
    result = summarize(rows)
    assert result["attempted"] == 4 and result["complete"] == 3
    assert result["metrics"]["transformer"]["rmse"] == 0
    assert result["metrics"]["transformer"]["mean_rank_ic"] == pytest.approx(1)
    assert result["metrics"]["equal"]["count"] == 3


@pytest.mark.parametrize("cross_error", [False, True])
def test_comparison_passes_only_available_context_and_fixed_current_window(tmp_path, monkeypatch, cross_error):
    import sys
    import numpy as np
    import pandas as pd
    import tools.compare_adaptive_hybrid as comparison
    seen = []
    class Model:
        def train_all(self, prices, calibration_prices):
            seen.append((prices.copy(), calibration_prices.copy()))

        def predict(self, horizon):
            return {"expected_return": .1, "components": {"ARIMA": .1, "Transformer": .1},
                    "diagnostics": {"completed_weight_errors": [[2., 1.]] * 3}}

        def cleanup(self):
            pass
    prices = pd.DataFrame({"TEST": np.exp(np.arange(756) * .001)}, index=pd.bdate_range("2020-01-01", periods=756))
    csv = tmp_path / "prices.csv"
    prices.to_csv(csv)
    monkeypatch.setattr(comparison, "DirectARIMATransformerPredictor", Model)
    argv = ["compare", "--csv", str(csv), "--tickers", "TEST", "--output-dir", str(tmp_path / "result")]
    if cross_error:
        argv += ["--cross-error", "--evaluation-start", str(prices.index[692].date())]
    monkeypatch.setattr(sys, "argv", argv)
    comparison.main()
    assert [len(context) for _, context in seen] == ([693] if cross_error else [504, 567, 630, 693])
    for (current, context), origin in zip(seen, ((692,) if cross_error else (503, 566, 629, 692))):
        assert len(current) == 504
        np.testing.assert_array_equal(current, context[-504:])
        assert context[-1] == pytest.approx(prices.iloc[origin, 0])
    if cross_error:
        import json
        result = json.loads((tmp_path / "result" / "summary.json").read_text())
        assert result["metrics"]["cross_error"]["count"] == 1
