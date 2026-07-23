import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "research_online_reversal_ensemble.py"
SPEC = importlib.util.spec_from_file_location(
    "research_online_reversal_ensemble",
    TOOL_PATH,
)
RESEARCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESEARCH)


def test_hedge_starts_equal_and_favors_lower_completed_loss():
    initial = RESEARCH.hedge_weights(
        {"momentum_12_1": 0.0, "short_term_reversal": 0.0},
        completed_count=0,
    )
    updated = RESEARCH.hedge_weights(
        {"momentum_12_1": 3.0, "short_term_reversal": 1.0},
        completed_count=4,
    )

    assert initial.tolist() == [0.5, 0.5]
    assert updated["short_term_reversal"] > updated["momentum_12_1"]
    assert abs(float(updated.sum()) - 1.0) < 1e-12


def test_online_weights_use_only_completed_periods():
    dates = pd.date_range("2000-01-31", periods=16, freq="ME")
    prices = pd.DataFrame(
        {
            "SMALL LoPRIOR": range(100, 116),
            "ME2 PRIOR2": range(100, 84, -1),
            "ME3 PRIOR3": range(90, 106),
            "ME4 PRIOR4": range(110, 94, -1),
            "BIG HiPRIOR": range(80, 96),
        },
        index=dates,
        dtype=float,
    )
    args = type(
        "Args",
        (),
        {
            "train_window": 12,
            "horizon": 1,
            "rebalance_step": 1,
        },
    )()

    result = RESEARCH._run_periods(prices, args)

    assert result["weight_history"][0]["completed_period_count"] == 0
    assert result["weight_history"][0]["momentum_weight"] == 0.5
    assert result["weight_history"][1]["completed_period_count"] == 1
