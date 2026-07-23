import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "research_risk_momentum_blend",
    ROOT / "tools" / "research_risk_momentum_blend.py",
)
research_risk_momentum_blend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_risk_momentum_blend)


def _summary(candidate_volatility=0.10, candidate_sharpe=0.80):
    return {
        "equal_weight": {
            "annual_volatility": 0.15,
            "sharpe": 0.55,
            "max_drawdown": -0.30,
            "avg_controlled_turnover": 0.02,
        },
        "risk_parity": {
            "annual_volatility": 0.12,
            "sharpe": 0.65,
            "max_drawdown": -0.25,
            "avg_controlled_turnover": 0.04,
        },
        "momentum_12_1_rank_tilt": {
            "annual_volatility": 0.14,
            "sharpe": 0.70,
            "max_drawdown": -0.28,
            "avg_controlled_turnover": 0.15,
        },
        "risk_momentum_blend": {
            "annual_volatility": candidate_volatility,
            "sharpe": candidate_sharpe,
            "max_drawdown": -0.20,
            "avg_controlled_turnover": 0.09,
        },
    }


def test_risk_momentum_gate_requires_both_component_improvements():
    gate = research_risk_momentum_blend._deterministic_gate(
        _summary()
    )

    assert gate["status"] == "passed"
    assert gate["reasons"] == []


def test_risk_momentum_gate_rejects_any_component_failure():
    gate = research_risk_momentum_blend._deterministic_gate(
        _summary(candidate_volatility=0.13, candidate_sharpe=0.68)
    )

    assert gate["status"] == "rejected"
    assert gate["reasons"]
