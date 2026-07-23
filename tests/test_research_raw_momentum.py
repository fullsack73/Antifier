import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "research_raw_momentum",
    ROOT / "tools" / "research_raw_momentum.py",
)
research_raw_momentum = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_raw_momentum)


def _summary(candidate_sharpe=0.80, candidate_drawdown=-0.20):
    return {
        "equal_weight": {
            "cagr": 0.08,
            "sharpe": 0.50,
            "max_drawdown": -0.30,
            "avg_controlled_turnover": 0.02,
        },
        "risk_parity": {
            "cagr": 0.09,
            "sharpe": 0.55,
            "max_drawdown": -0.28,
            "avg_controlled_turnover": 0.03,
        },
        "historical_bl": {
            "cagr": 0.10,
            "sharpe": 0.60,
            "max_drawdown": -0.27,
            "avg_controlled_turnover": 0.08,
        },
        "lightweight_bl": {
            "cagr": 0.11,
            "sharpe": 0.65,
            "max_drawdown": -0.25,
            "avg_controlled_turnover": 0.12,
        },
        "momentum_12_1_rank_tilt": {
            "cagr": 0.13,
            "sharpe": candidate_sharpe,
            "max_drawdown": candidate_drawdown,
            "avg_controlled_turnover": 0.10,
            "failed_forecast_count": 0,
        },
    }


def test_raw_momentum_gate_passes_all_default_and_guard_baselines():
    gate = research_raw_momentum._deterministic_gate(_summary())

    assert gate["status"] == "passed"
    assert gate["reasons"] == []


def test_raw_momentum_gate_rejects_default_or_guard_failure():
    gate = research_raw_momentum._deterministic_gate(
        _summary(candidate_sharpe=0.52, candidate_drawdown=-0.35)
    )

    assert gate["status"] == "rejected"
    assert gate["reasons"]
