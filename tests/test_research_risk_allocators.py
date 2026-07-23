import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "research_risk_allocators",
    ROOT / "tools" / "research_risk_allocators.py",
)
research_risk_allocators = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_risk_allocators)


def test_hac_historical_candidate_uses_historical_bl_baseline():
    summary = {
        "equal_weight": {
            "annual_volatility": 0.15,
            "sharpe": 0.60,
            "max_drawdown": -0.30,
            "avg_controlled_turnover": 0.02,
        },
        "risk_parity": {
            "annual_volatility": 0.13,
            "sharpe": 0.65,
            "max_drawdown": -0.25,
            "avg_controlled_turnover": 0.03,
        },
        "historical_bl": {
            "annual_volatility": 0.14,
            "sharpe": 0.70,
            "max_drawdown": -0.28,
            "avg_controlled_turnover": 0.10,
        },
        "hac_historical_bl": {
            "annual_volatility": 0.12,
            "sharpe": 0.75,
            "max_drawdown": -0.24,
            "avg_controlled_turnover": 0.08,
        },
    }

    gate = research_risk_allocators._risk_gate(
        summary,
        "hac_historical_bl",
    )

    assert gate["status"] == "passed"
    assert gate["baseline"] == "historical_bl"
