import numpy as np
import pytest

import direct_horizon_forecast as direct
import portfolio_optimization as portfolio


def test_production_selectors_use_direct_models():
    assert portfolio.TransformerForecastModel is direct.DirectHorizonTransformerForecastModel
    assert portfolio.ARIMATransformerPredictor is direct.DirectARIMATransformerPredictor


def test_direct_contract_converts_same_period_to_annual_and_caches_by_horizon(monkeypatch):
    model = direct.DirectHorizonTransformerForecastModel()
    model.train(np.exp(np.arange(504) * .001))
    calls = []
    def predict(horizon):
        calls.append(horizon)
        return {"period_log_return": .2, "validation_period_rmse": .03}
    monkeypatch.setattr(model, "_predict_period", predict)
    result = model.predict(63)
    assert result["expected_return"] == pytest.approx(.8)
    assert result["uncertainty"] == pytest.approx(.12)
    assert result["diagnostics"]["forecast_kind"] == "direct"
    assert not result["diagnostics"]["uncertainty_is_calibrated"]
    assert model.forecast(63, annualize=False) == pytest.approx(.2)
    assert calls == [63]
    model.predict(21)
    assert calls == [63, 21]
    model.train(np.exp(np.arange(504) * .002))
    model.predict(63)
    assert calls == [63, 21, 63]


def test_bad_history_or_insufficient_completed_targets_return_no_view():
    model = direct.DirectHorizonTransformerForecastModel()
    assert model.predict(63)["expected_return"] is None
    model.train(np.r_[np.ones(200), np.nan, np.ones(303)])
    assert model.predict(63)["source"] == "no_view"
    model.train(np.ones(150))
    assert model.predict(252)["source"] == "no_view"


@pytest.mark.parametrize("horizon", [0, -1, 1.5, True, 366])
def test_invalid_horizon_never_trains(monkeypatch, horizon):
    model = direct.DirectHorizonTransformerForecastModel()
    model.train(np.ones(504))
    monkeypatch.setattr(model, "_predict_period", lambda _: pytest.fail("must validate before fitting"))
    assert model.predict(horizon)["expected_return"] is None


def test_hybrid_combines_direct_and_arima_same_annual_units(monkeypatch):
    model = direct.DirectARIMATransformerPredictor()
    model.train_all(np.exp(np.arange(504) * .001))
    monkeypatch.setattr(model.arima, "forecast", lambda prices, horizon: (.02, .1))
    monkeypatch.setattr(model.transformer, "_predict_period", lambda h: {"period_log_return": .04, "validation_period_rmse": .03})
    result = model.predict(63)
    assert result["expected_return"] == pytest.approx((.08 + .16) / 2)
    assert result["diagnostics"]["components"]["Transformer"]["model_version"] == direct.MODEL_VERSION
    model.train_all(np.r_[np.ones(503), np.nan])
    assert model.predict(63)["source"] == "no_view"


def test_wrapper_does_not_remove_missing_dates(monkeypatch):
    import pandas as pd
    seen = []
    class Model:
        def train(self, prices):
            seen.append(prices)
        def predict(self, horizon):
            return {"expected_return": None, "source": "no_view"}
        def cleanup(self):
            pass
    monkeypatch.setattr(portfolio, "TransformerForecastModel", Model)
    values = pd.Series(np.r_[np.ones(200), np.nan, np.ones(303)])
    portfolio._generate_transformer_prediction("TEST", values, 63)
    assert len(seen[0]) == 504 and np.isnan(seen[0][200])


def test_prediction_and_pipeline_caches_are_versioned(monkeypatch):
    prices = np.ones(504)
    key = portfolio._direct_forecast_cache_key("transformer", "TEST", prices, 63)
    assert key != portfolio._direct_forecast_cache_key("transformer", "TEST", prices[:, None], 63)
    assert key != portfolio._direct_forecast_cache_key("arima_transformer", "TEST", prices, 63)
    changed = prices.copy()
    changed[250] = 2
    assert key != portfolio._direct_forecast_cache_key("transformer", "TEST", changed, 63)
    args = ("2020-01-01", "2025-01-01", None, ["TEST"], "TRANSFORMER")
    pipeline = portfolio._pipeline_key_func(*args)
    monkeypatch.setattr(portfolio, "DIRECT_FORECAST_VERSION", "different-version")
    assert key != portfolio._direct_forecast_cache_key("transformer", "TEST", prices, 63)
    assert pipeline != portfolio._pipeline_key_func(*args)


@pytest.mark.parametrize("kind,wrapper", [("Transformer", "forecast_single_ticker_with_transformer"),
                                        ("ARIMA + Transformer", "forecast_single_ticker_with_arima_transformer")])
def test_stock_chart_uses_requested_horizon_and_preserves_direct_output(monkeypatch, kind, wrapper):
    import app
    import pandas as pd
    from types import SimpleNamespace
    seen = []
    def predict(ticker, prices, horizon):
        seen.append((prices, horizon))
        return {"expected_return": .8, "uncertainty": .2, "diagnostics": {"model_version": "direct-horizon-v1"}}
    monkeypatch.setattr(app, wrapper, predict)
    monkeypatch.setattr(app, "build_arima_in_sample_regression", lambda prices: {})
    monkeypatch.setattr(app, "generate_monte_carlo_future_predictions", lambda *args, **kwargs: {"daily": kwargs["daily_log_return"]})
    prices = pd.Series(np.r_[np.ones(503), np.nan], index=pd.bdate_range("2020-01-01", periods=504))
    result = app.generate_forecast_regression_response("TEST", SimpleNamespace(info={}), prices, 63, "USD", {}, kind)
    assert seen[0][1] == 63 and len(seen[0][0]) == 504
    assert result["model_metadata"]["expected_annual_log_return"] == .8
    assert result["future_predictions"]["daily"] == pytest.approx(.8 / 252)
