import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "research_minvar_promotion",
    ROOT / "tools" / "research_minvar_promotion.py",
)
research_minvar_promotion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_minvar_promotion)


def _summary(candidate_volatility=0.09, candidate_sharpe=0.80):
    return {
        "equal_weight": {
            "annual_volatility": 0.15,
            "sharpe": 0.55,
            "max_drawdown": -0.30,
            "avg_controlled_turnover": 0.02,
        },
        "historical_bl": {
            "annual_volatility": 0.14,
            "sharpe": 0.60,
            "max_drawdown": -0.28,
            "avg_controlled_turnover": 0.05,
        },
        "lightweight_bl": {
            "annual_volatility": 0.16,
            "sharpe": 0.50,
            "max_drawdown": -0.32,
            "avg_controlled_turnover": 0.12,
        },
        "risk_parity": {
            "annual_volatility": 0.12,
            "sharpe": 0.65,
            "max_drawdown": -0.25,
            "avg_controlled_turnover": 0.04,
        },
        "min_variance": {
            "annual_volatility": candidate_volatility,
            "sharpe": candidate_sharpe,
            "max_drawdown": -0.20,
            "avg_controlled_turnover": 0.10,
        },
    }


def test_minvar_promotion_gate_passes_all_baselines():
    gate = research_minvar_promotion._deterministic_gate(_summary())

    assert gate["status"] == "passed"
    assert gate["reasons"] == []


def test_minvar_promotion_gate_rejects_risk_parity_failure():
    gate = research_minvar_promotion._deterministic_gate(
        _summary(candidate_volatility=0.13, candidate_sharpe=0.62)
    )

    assert gate["status"] == "rejected"
    assert gate["reasons"]
