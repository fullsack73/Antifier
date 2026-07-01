import os
import sys
from types import SimpleNamespace

import numpy as np


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

from forecast_models import TransformerForecastModel


def test_transformer_hpo_candidates_deduplicate_current_config_and_apply_limit():
    model = TransformerForecastModel(
        hpo_enabled=True,
        hpo_trials=2,
        hpo_space=[
            {"name": "duplicate", "lookback": 60},
            {"name": "tiny", "lookback": 20},
        ],
    )

    candidates = model._candidate_hpo_configs()

    assert [candidate["name"] for candidate in candidates] == ["current", "tiny"]
    assert candidates[1]["lookback"] == 20


def test_transformer_hpo_selects_lowest_validation_loss(monkeypatch):
    class FakeEarlyStopping:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeModel:
        def __init__(self, loss):
            self.loss = loss

        def fit(self, *args, **kwargs):
            assert kwargs["validation_data"] is not None
            assert kwargs["shuffle"] is False
            return SimpleNamespace(history={
                "loss": [self.loss + 0.1],
                "val_loss": [self.loss],
            })

    fake_tf = SimpleNamespace(
        keras=SimpleNamespace(
            backend=SimpleNamespace(clear_session=lambda: None),
            callbacks=SimpleNamespace(EarlyStopping=FakeEarlyStopping),
        ),
        random=SimpleNamespace(set_seed=lambda seed: None),
    )
    losses = {"current": 0.30, "bad": 0.25, "good": 0.05}
    build_calls = []

    model = TransformerForecastModel(
        hpo_enabled=True,
        hpo_space=[
            {"name": "bad", "lookback": 30, "d_model": 16},
            {"name": "good", "lookback": 20, "d_model": 64},
        ],
        hpo_validation_split=0.25,
        hpo_min_train_sequences=10,
    )

    def fake_build_model(sequence_length, config=None):
        build_calls.append((config["name"], sequence_length))
        return FakeModel(losses[config["name"]])

    monkeypatch.setattr(model, "_build_model", fake_build_model)

    selected = model._run_hpo(np.linspace(-1.0, 1.0, 90).reshape(-1, 1), fake_tf)

    assert selected["name"] == "good"
    assert selected["d_model"] == 64
    assert model.lookback == 20
    assert model.best_hpo_params["val_loss"] == 0.05
    assert [result["config"]["name"] for result in model.hpo_results] == ["current", "bad", "good"]
    assert build_calls == [("current", 30), ("bad", 30), ("good", 20)]
