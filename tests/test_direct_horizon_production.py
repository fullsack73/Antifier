import numpy as np
import pytest

import direct_horizon_forecast as direct
import portfolio_optimization as portfolio


def test_production_selectors_use_direct_models():
    assert portfolio.TransformerForecastModel is direct.DirectHorizonTransformerForecastModel
    assert portfolio.ARIMATransformerPredictor is direct.DirectARIMATransformerPredictor


def test_direct_model_uses_position_and_can_distinguish_reversed_returns(monkeypatch):
    pytest.importorskip("tensorflow")
    builder = direct.build_transformer
    built = []

    def capture(position, seed):
        model = builder(position, seed)
        built.append((position, model))
        return model

    monkeypatch.setattr(direct, "build_transformer", capture)
    model = direct.DirectHorizonTransformerForecastModel()
    model.train(np.exp(np.cumsum(np.random.default_rng(5).normal(0, .01, 504))))
    assert model.predict(63)["source"] == "transformer"
    assert built[0][0] is True
    sequence = np.random.default_rng(10).normal(size=(1, 60, 1)).astype("float32")
    forward = float(built[0][1](sequence, training=False).numpy()[0, 0])
    reverse = float(built[0][1](sequence[:, ::-1, :], training=False).numpy()[0, 0])
    assert abs(forward - reverse) > 1e-6


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
    model.train_all(np.exp(np.arange(150) * .001))
    monkeypatch.setattr(model.arima, "forecast", lambda prices, horizon: (.02, .1))
    monkeypatch.setattr(model.transformer, "_predict_period", lambda h: {"period_log_return": .04, "validation_period_rmse": .03})
    result = model.predict(63)
    assert result["expected_return"] == pytest.approx((.08 + .16) / 2)
    assert result["diagnostics"]["components"]["Transformer"]["model_version"] == direct.MODEL_VERSION
    model.train_all(np.r_[np.ones(503), np.nan])
    assert model.predict(63)["source"] == "no_view"


def test_hybrid_weights_use_only_three_completed_prior_periods(monkeypatch):
    seen = []
    def prediction(model, horizon):
        seen.append(model.history.copy())
        assert model.transformer.epochs == 7 and model.transformer.random_state == 43
        return {"expected_return": .378, "components": {"ARIMA": .252, "Transformer": .504},
                "source": "arima_transformer", "diagnostics": {}}
    monkeypatch.setattr(direct.ARIMATransformerPredictor, "predict", prediction)
    model = direct.DirectARIMATransformerPredictor(transformer_kwargs={"epochs": 7, "random_state": 43})
    prices = np.exp(np.arange(693) * .001)
    model.train_all(prices[-504:], calibration_prices=prices)
    result = model.predict(63)
    assert [len(history) for history in seen] == [504, 504, 504, 504]
    for history, start in zip(seen, (189, 0, 63, 126)):
        np.testing.assert_array_equal(history, prices[start:start + 504])
    assert result["diagnostics"]["completed_weight_periods"] == 3
    assert result["diagnostics"]["arima_weight"] == pytest.approx(.75)
    assert result["expected_return"] == pytest.approx(.315)


def test_hybrid_weight_defaults_to_equal_when_past_forecast_fails(monkeypatch):
    calls = []
    def prediction(model, horizon):
        calls.append(len(model.history))
        if len(calls) > 1:
            raise RuntimeError("past model failed")
        return {"expected_return": .378, "components": {"ARIMA": .252, "Transformer": .504},
                "source": "arima_transformer", "diagnostics": {}}
    monkeypatch.setattr(direct.ARIMATransformerPredictor, "predict", prediction)
    model = direct.DirectARIMATransformerPredictor()
    prices = np.exp(np.arange(693) * .001)
    model.train_all(prices[-504:], calibration_prices=prices)
    result = model.predict(63)
    assert result["diagnostics"]["arima_weight"] == .5
    assert result["diagnostics"]["completed_weight_periods"] == 0


@pytest.mark.parametrize("context", ["absent", "short", "mismatch", "nan"])
def test_hybrid_never_shortens_window_when_context_is_insufficient(monkeypatch, context):
    calls = []
    def prediction(model, horizon):
        calls.append(len(model.history))
        return {"expected_return": .378, "components": {"ARIMA": .252, "Transformer": .504},
                "source": "arima_transformer", "diagnostics": {}}
    monkeypatch.setattr(direct.ARIMATransformerPredictor, "predict", prediction)
    prices = np.exp(np.arange(693) * .001)
    calibration = None if context == "absent" else prices.copy()
    if context == "short":
        calibration = calibration[1:]
    if context == "mismatch":
        calibration[-1] *= 2
    if context == "nan":
        calibration[0] = np.nan
    model = direct.DirectARIMATransformerPredictor()
    model.train_all(prices[-504:], calibration_prices=calibration)
    result = model.predict(63)
    assert calls == [504]
    assert result["diagnostics"]["arima_weight"] == .5
    assert not result["diagnostics"]["weight_history_sufficient"]
    assert result["diagnostics"]["completed_weight_periods"] == 0


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


def test_rank_cache_schema_changes_forecast_key(monkeypatch):
    import portfolio_backtest
    import pandas as pd
    prices = pd.Series(np.ones(100), index=pd.bdate_range("2020-01-01", periods=100))
    key = portfolio_backtest._forecast_rank_cache_key("TEST", prices, "TRANSFORMER", 63)
    monkeypatch.setattr(portfolio_backtest, "FORECAST_RANK_CACHE_SCHEMA_VERSION", "old-schema")
    assert key != portfolio_backtest._forecast_rank_cache_key("TEST", prices, "TRANSFORMER", 63)


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
