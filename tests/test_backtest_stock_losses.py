import numpy as np
import pandas as pd
import pytest

from tools import backtest_stock_losses as experiment


def test_losses_prefer_correct_order_and_have_finite_gradients():
    tf = pytest.importorskip("tensorflow")
    actual = tf.constant([[-1., 0., 1.]])
    for kind in experiment.KINDS:
        prediction = tf.Variable([[-.5, 0., .5]])
        with tf.GradientTape() as tape:
            value = experiment.loss_value(actual, prediction, kind)
        assert np.isfinite(tape.gradient(value, prediction).numpy()).all()
        assert value.numpy() < experiment.loss_value(actual, -prediction, kind).numpy()
        assert np.isfinite(experiment.loss_value(tf.zeros_like(actual), tf.zeros_like(actual), kind).numpy())
    assert experiment.loss_value(actual, actual, "mse").numpy() == 0
    with pytest.raises(ValueError):
        experiment.loss_value(actual, actual, "unknown")


def test_selection_is_capped_and_ties_use_ticker_order():
    weights = experiment.selection_weights([1.] * 6, list("FEDCBA"))
    assert weights["F"] == 0
    assert sum(weights.values()) == pytest.approx(1)
    assert max(weights.values()) == .2
    with pytest.raises(ValueError):
        experiment.selection_weights([np.nan] * 6, list("ABCDEF"))


def test_replay_uses_same_cost_aware_portfolio_engine_for_every_loss(monkeypatch):
    monkeypatch.setattr(experiment, "paired_block_bootstrap", lambda *a, **kw: {"test": True})
    generator = np.random.default_rng(7)
    prices = pd.DataFrame(100 * np.exp(np.cumsum(generator.normal(.0003, .01, (1008, 22)), axis=0)),
                          index=pd.bdate_range("2021-01-01", periods=1008),
                          columns=[f"S{i:02}" for i in range(22)])
    forecasts = {(origin, seed, kind): {"scores": list(range(22))}
                 for origin in range(503, 945, 63) for seed in (42, 43, 44) for kind in experiment.KINDS}
    result = experiment.replay(prices, forecasts)
    assert len(result["runs"]) == 11
    assert len(set(result["mean_sharpe_by_loss"].values())) == 1
    for name, run in result["runs"].items():
        summary = run["summary"]
        assert np.isfinite(summary["sharpe"])
        assert len(run["records"]) == 8
        compounded = np.prod(1 + np.array(list(result["daily_returns"][name].values()))) - 1
        assert compounded == pytest.approx(summary["net_cumulative_return"])
    assert result["daily_returns"]["mse_seed42"] == result["daily_returns"]["mse_rank_seed44"]
