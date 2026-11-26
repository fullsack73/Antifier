import numpy as np
import pandas as pd
import pytest

from tools.evaluate_direct_forecast_oos import evaluate


def test_each_forecast_uses_only_available_history_and_scores_full_horizon():
    dates = pd.bdate_range("2020-01-01", periods=110)
    prices = pd.Series(np.exp(np.arange(110) * .01), index=dates)
    seen = []

    class Model:
        def train(self, values):
            seen.append(values.copy())

        def predict(self, horizon):
            return {"expected_return": .01 * 252, "source": "transformer",
                    "diagnostics": {"validation_period_rmse": .03}}

        def cleanup(self):
            pass

    result = evaluate(prices, horizon=5, train_window=100, model_factory=Model)
    assert result["origin_count"] == result["success_count"] == 2
    assert result["rmse"] == pytest.approx(0, abs=1e-12)
    assert result["rows"][0]["origin"] == dates[99].strftime("%Y-%m-%d")
    assert result["rows"][0]["outcome_date"] == dates[104].strftime("%Y-%m-%d")
    np.testing.assert_array_equal(seen[0], prices.iloc[:100])
    np.testing.assert_array_equal(seen[1], prices.iloc[5:105])


def test_no_view_and_incomplete_period_are_not_scored():
    prices = pd.Series(np.ones(108), index=pd.bdate_range("2020-01-01", periods=108))

    class Model:
        def train(self, values):
            pass

        def predict(self, horizon):
            return {"expected_return": None, "source": "no_view", "reason": "failed"}

        def cleanup(self):
            pass

    result = evaluate(prices, horizon=5, train_window=100, model_factory=Model)
    assert result["origin_count"] == result["failure_count"] == 1
    assert result["rmse"] is None
    assert result["rows"][0]["failure"] == "failed"


def test_missing_values_and_duplicate_dates_are_rejected():
    prices = pd.Series(np.ones(105), index=pd.bdate_range("2020-01-01", periods=105))
    prices.iloc[20] = np.nan
    with pytest.raises(ValueError, match="finite and positive"):
        evaluate(prices, 5, 100)
    prices.iloc[20] = 1
    prices.index = pd.DatetimeIndex([prices.index[0]] + list(prices.index[:-1]))
    with pytest.raises(ValueError, match="unique, increasing"):
        evaluate(prices, 5, 100)
