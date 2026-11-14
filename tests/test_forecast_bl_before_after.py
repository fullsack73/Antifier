import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

from tools import compare_forecast_bl_before_after as comparison


def train():
    rng = np.random.default_rng(24)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.0004, .01, (504, 6)), axis=0)),
                        index=pd.bdate_range("2017-01-01", periods=504), columns=list("ABCDEF"))


def test_uncertainty_reconstruction_uses_purged_train_target_scale():
    prices = train()
    saved = {"predictions": {}}
    for ticker in prices:
        _, _, y, ends = comparison.supervised_returns(prices[ticker], 63)
        tr, va = comparison.purged_split(ends, 63)
        saved["predictions"][ticker] = {"raw": .04, "validation_loss": [4., 1., 2.],
                                          "train_rows": len(tr), "validation_rows": len(va)}
    views, sigma = comparison.views_for_origin(prices, saved, True)
    expected_scale = StandardScaler().fit(y[tr, None]).scale_[0]
    assert sigma.iloc[-1] == pytest.approx(max(.01, expected_scale * 4))
    assert np.allclose(views, np.expm1(.16))
    saved["predictions"]["A"]["train_rows"] += 1
    with pytest.raises(ValueError, match="partition"):
        comparison.views_for_origin(prices, saved, True)


def test_legacy_uses_actual_annual_clipped_api_component():
    prices = train()
    saved = {"predictions": {t: {"raw": 1., "original_standalone": .95,
                                  "original_hybrid_component": .1, "reported_uncertainty": .2} for t in prices}}
    views, sigma = comparison.views_for_origin(prices, saved, False)
    assert np.allclose(views, np.expm1(.4))
    assert np.allclose(sigma, .2)


def test_bl_helper_applies_shared_prior_confidence_and_omega(monkeypatch):
    prices = train()
    seen = {}
    real = comparison.backtest.BlackLittermanModel
    def construct(covariance, **kwargs):
        seen.update(kwargs)
        return real(covariance, **kwargs)
    monkeypatch.setattr(comparison.backtest, "BlackLittermanModel", construct)
    views = pd.Series(.1, index=prices.columns)
    sigma = pd.Series(.2, index=prices.columns)
    weights, diagnostics = comparison.bl_weights(prices, views, sigma)
    assert seen["tau"] == .05 and seen["risk_aversion"] == 2.5
    assert sum(weights.values()) == pytest.approx(1.)
    assert max(weights.values()) <= .20001
    assert diagnostics["annual_uncertainty"] == sigma.to_dict()
    assert not diagnostics["bl_fallback"]
    confidence = comparison.backtest._confidence_from_uncertainty(sigma)
    expected = (sigma / confidence).clip(lower=1e-4, upper=comparison.backtest.MAX_FORECAST_UNCERTAINTY)
    assert np.allclose(np.diag(seen["omega"]), expected ** 2)
