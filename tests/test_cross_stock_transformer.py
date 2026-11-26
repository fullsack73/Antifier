import threading
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import cross_stock_transformer as joint
import portfolio_optimization as portfolio


def panel(stocks=3):
    values = 100 * np.exp(np.cumsum(np.random.default_rng(4).normal(.0003, .01, (504, stocks)), axis=0))
    return pd.DataFrame(values, index=pd.bdate_range("2023-01-01", periods=504),
                        columns=[f"S{i}" for i in range(stocks)])


@pytest.mark.parametrize("horizon", [21, 63, 126])
def test_training_preparation_matches_frozen_research(horizon):
    from tools.benchmark_stock_attention import prepare
    prices = panel()
    padded = np.concatenate([prices, np.repeat(prices.iloc[-1:].to_numpy(), horizon, axis=0)])
    expected = prepare(padded, horizon=horizon)
    actual = joint.prepare_training(prices, horizon)
    for i in range(5):
        np.testing.assert_array_equal(actual[i], expected[i])
    np.testing.assert_array_equal(actual[5].mean_, expected[5].mean_)


def test_builder_and_loss_match_research_and_use_other_stocks():
    tf = pytest.importorskip("tensorflow")
    from tools.benchmark_stock_attention import build_model
    from tools.backtest_stock_losses import loss_value
    x = np.random.default_rng(7).normal(size=(1, 3, 60, 1)).astype("float32")
    expected = build_model(3, True, 42)(x, training=False).numpy()
    model = joint.build_model(3, 42)
    actual = model(x, training=False).numpy()
    np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=1e-6)
    changed = x.copy()
    changed[:, 1] *= -2
    assert abs(model(changed, training=False).numpy()[0, 0] - actual[0, 0]) > 1e-6
    labels = tf.constant([[-1., 0., 1.]])
    prediction = tf.Variable([[-.5, 0., .5]])
    with tf.GradientTape() as tape:
        value = joint.correlation_loss(labels, prediction)
    assert value.numpy() == pytest.approx(loss_value(labels, prediction, "mse_corr").numpy())
    assert np.isfinite(tape.gradient(value, prediction).numpy()).all()
    tf.keras.backend.clear_session()


def test_cache_key_covers_other_stocks_dates_cohort_horizon_and_version(monkeypatch):
    prices = panel()
    key = joint.panel_cache_key(prices, 63)
    changed = prices.copy()
    changed.iloc[200, 1] *= 1.01
    assert joint.panel_cache_key(changed, 63) != key
    assert joint.panel_cache_key(prices.iloc[:, :2], 63) != key
    assert joint.panel_cache_key(prices.iloc[:, ::-1], 63) != key
    shifted = prices.copy()
    shifted.index += pd.Timedelta(days=1)
    assert joint.panel_cache_key(shifted, 63) != key
    assert joint.panel_cache_key(prices, 21) != key
    monkeypatch.setattr(joint, "MODEL_VERSION", "other-version")
    assert joint.panel_cache_key(prices, 63) != key
    args = ("2023-01-01", "2025-01-01", None)
    assert portfolio._pipeline_key_func(*args, ["A", "B"], "TRANSFORMER") != portfolio._pipeline_key_func(*args, ["B", "A"], "TRANSFORMER")
    old_key = portfolio._pipeline_key_func(*args, ["A", "B"], "TRANSFORMER")
    monkeypatch.setattr(portfolio, "JOINT_FORECAST_VERSION", "changed")
    assert portfolio._pipeline_key_func(*args, ["A", "B"], "TRANSFORMER") != old_key


def test_cache_hit_keeps_invalid_stock_no_view_and_does_not_spawn(monkeypatch):
    import cache_manager
    prices = panel()
    prices.iloc[200, 2] = np.nan
    values = {t: {"expected_return": .2, "uncertainty": .1} for t in prices.columns[:2]}
    monkeypatch.setattr(cache_manager, "get_cache", lambda: SimpleNamespace(get=lambda key: values))
    monkeypatch.setattr(joint.mp, "get_context", lambda *a: pytest.fail("cache hit must not spawn"))
    progress = []
    result = joint.forecast_panel(prices, progress_callback=lambda *args: progress.append(args))
    assert result["S0"]["expected_return"] == .2
    assert result["S2"]["source"] == "no_view"
    assert progress[0][:2] == (3, 3)


def test_bad_history_and_horizon_do_not_start_training(monkeypatch):
    monkeypatch.setattr(joint.mp, "get_context", lambda *a: pytest.fail("must validate before spawn"))
    for prices, horizon in [(panel().iloc[:-1], 63), (panel(1), 63), (panel(), True), (panel(), 1.5)]:
        assert all(p["source"] == "no_view" for p in joint.forecast_panel(prices, horizon).values())
    broken = panel()
    broken.index = broken.index[::-1]
    with pytest.raises(ValueError):
        joint.forecast_panel(broken)


def test_cancelling_worker_terminates_process_and_does_not_cache(monkeypatch):
    import cache_manager
    event = threading.Event()
    calls = []
    class Connection:
        def poll(self, timeout=None):
            event.set()
            return False
        def close(self): pass
    process = SimpleNamespace(pid=10, start=lambda: None, is_alive=lambda: True,
                              terminate=lambda: calls.append("terminate"), join=lambda: calls.append("join"))
    context = SimpleNamespace(Pipe=lambda **kw: (Connection(), Connection()), Process=lambda **kw: process)
    monkeypatch.setattr(joint.mp, "get_context", lambda *args: context)
    monkeypatch.setattr(cache_manager, "get_cache", lambda: SimpleNamespace(get=lambda key: None,
                         set=lambda *a, **kw: pytest.fail("cancelled output must not be cached")))
    with pytest.raises(portfolio.OptimizationCancelled):
        joint.forecast_panel(panel(), cancel_event=event)
    assert calls == ["terminate", "join"]


def test_joint_mpt_uses_raw_predictions_and_exposes_model_metadata(monkeypatch):
    prices = panel(6)
    tickers = list(prices)
    raw = pd.Series(np.linspace(.05, .2, 6), index=tickers)
    pipeline = {"mu": raw, "prior_mu": raw * 0, "S": pd.DataFrame(np.eye(6) * .04, index=tickers, columns=tickers),
                "uncertainties": pd.Series(2., index=tickers), "no_view_tickers": [], "tickers": tickers,
                "latest_prices": prices.iloc[-1].to_dict(), "forecast_model": {"joint": True, "model_version": joint.MODEL_VERSION}}
    monkeypatch.setattr(portfolio, "data_and_forecast_pipeline", lambda *a, **kw: pipeline)
    result = portfolio.optimize_portfolio("2023-01-01", "2024-12-04", .03, tickers=tickers,
        optimization_method="MPT", forecast_method="TRANSFORMER", max_asset_weight=.2,
        asset_constraints=[{"ticker": "S0", "min_weight": .1, "max_weight": .15}],
        candidate_search={"enabled": False})
    assert "error" not in result, result
    assert result["forecast_model"]["model_version"] == joint.MODEL_VERSION
    assert result["optimizer_expected_returns"] == pytest.approx(raw.to_dict())
    assert sum(result["weights"].values()) == pytest.approx(1)
    assert max(result["weights"].values()) <= .2 + 1e-6
    assert .1 - 1e-6 <= result["weights"]["S0"] <= .15 + 1e-6


def test_joint_mpt_no_view_falls_back_to_constrained_gmv(monkeypatch):
    prices = panel(6)
    tickers = list(prices)
    pipeline = {"mu": pd.Series(0., index=tickers), "prior_mu": pd.Series(0., index=tickers),
                "S": pd.DataFrame(np.eye(6) * .04, index=tickers, columns=tickers),
                "uncertainties": pd.Series(5., index=tickers), "no_view_tickers": tickers,
                "tickers": tickers, "latest_prices": prices.iloc[-1].to_dict(),
                "forecast_model": {"joint": True, "model_version": joint.MODEL_VERSION}}
    monkeypatch.setattr(portfolio, "data_and_forecast_pipeline", lambda *a, **kw: pipeline)
    result = portfolio.optimize_portfolio("2023-01-01", "2024-12-04", .03, tickers=tickers,
        optimization_method="MPT", forecast_method="TRANSFORMER", max_asset_weight=.2,
        candidate_search={"enabled": False})
    assert "error" not in result, result
    assert result["optimizer_controls"]["solver_objective"] == "joint_transformer_min_variance_fallback"
    assert result["failed_forecast_count"] == 6
    assert sum(result["weights"].values()) == pytest.approx(1)


def test_old_strategy_checkpoint_is_rejected(tmp_path, monkeypatch):
    import json
    import strategy_job_checkpoint as checkpoint
    from candidate_search import POLICY_VERSION
    monkeypatch.setenv("ANTIFIER_BACKTEST_CHECKPOINT_DIR", str(tmp_path))
    request = "backtest_" + "a" * 32
    (tmp_path / f"{request}.json").write_text(json.dumps({"version": POLICY_VERSION, "settings": {}}))
    with pytest.raises(ValueError, match="version changed"):
        checkpoint.load(request)


def test_pipeline_reforecasts_selected_cohort_instead_of_candidate_scores(monkeypatch):
    prices = panel(6)
    monkeypatch.setattr(portfolio, "get_stock_data", lambda *a, **kw: prices.copy())
    monkeypatch.setattr(portfolio, "_convert_price_data_to_usd", lambda frame, *a, **kw: (frame, {}, []))
    calls = []
    def predict(data, **kwargs):
        calls.append(data)
        result = pd.Series(.1, index=data.columns)
        result.attrs["forecast_model"] = {"joint": True, "model_version": joint.MODEL_VERSION}
        return result, pd.Series(.05, index=data.columns)
    monkeypatch.setattr(portfolio, "joint_transformer_forecast_returns", predict)
    monkeypatch.setattr(portfolio, "_get_ticker_currency", lambda *a: "USD")
    candidate = {t: {"expected_return": 9., "uncertainty": .1} for t in prices}
    pipeline = portfolio.data_and_forecast_pipeline.__wrapped__("2023-01-01", "2024-12-04", None,
        list(prices), "TRANSFORMER", candidate_hook=lambda frame: (frame, candidate))
    assert "error" not in pipeline, pipeline
    assert len(calls) == 1
    assert pipeline["mu"].to_numpy() == pytest.approx(np.repeat(np.expm1(.1), 6))
    assert pipeline["forecast_model"]["joint"]
