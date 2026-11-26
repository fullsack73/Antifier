import numpy as np
import pytest

from tools.benchmark_stock_attention import build_model, prepare


def test_preparation_excludes_future_returns_from_training_and_scaling():
    prices = np.exp(np.arange(567)[:, None] * np.linspace(.0001, .001, 10))
    original = prepare(prices)
    prices[504:] *= 2
    changed = prepare(prices)
    for index in (0, 1, 2, 3, 4):
        np.testing.assert_array_equal(original[index], changed[index])
    assert original[0].shape == (381, 10, 60, 1)
    assert len(original[2]) == 280 and len(original[3]) == 39
    np.testing.assert_allclose(changed[-1] - original[-1], np.log(2))


def test_only_stock_attention_propagates_other_stock_inputs():
    pytest.importorskip("tensorflow")
    data = np.random.default_rng(10).normal(size=(1, 10, 60, 1)).astype("float32")
    changed = data.copy()
    changed[:, 1] *= -2
    for cross in (False, True):
        model = build_model(10, cross, 42)
        original = model(data, training=False).numpy()
        updated = model(changed, training=False).numpy()
        assert original.shape == (1, 10)
        if cross:
            assert abs(original[0, 0] - updated[0, 0]) > 1e-6
            order = np.arange(10)[::-1]
            np.testing.assert_allclose(model(data[:, order], training=False).numpy(),
                                       original[:, order], atol=1e-5, rtol=1e-5)
        else:
            assert original[0, 0] == pytest.approx(updated[0, 0], abs=1e-6)
