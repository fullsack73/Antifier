import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "research_mean_shrinkage",
    ROOT / "tools" / "research_mean_shrinkage.py",
)
research_mean_shrinkage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_mean_shrinkage)


def _summary(
    *,
    candidate_volatility=0.12,
    candidate_sharpe=0.80,
    candidate_drawdown=-0.20,
    candidate_turnover=0.10,
):
    return {
        "historical_bl": {
            "annual_volatility": 0.14,
            "sharpe": 0.70,
            "max_drawdown": -0.25,
            "avg_controlled_turnover": 0.12,
        },
        "james_stein_bl": {
            "annual_volatility": candidate_volatility,
            "sharpe": candidate_sharpe,
            "max_drawdown": candidate_drawdown,
            "avg_controlled_turnover": candidate_turnover,
        },
    }


def test_mean_shrinkage_gate_passes_only_joint_risk_improvement():
    gate = research_mean_shrinkage.deterministic_gate(_summary())

    assert gate["status"] == "passed"
    assert gate["reasons"] == []
    assert gate["baseline"] == "historical_bl"
    assert gate["turnover_limit"] == 0.50


def test_mean_shrinkage_gate_rejects_worse_closest_baseline_metrics():
    gate = research_mean_shrinkage.deterministic_gate(
        _summary(
            candidate_volatility=0.15,
            candidate_sharpe=0.60,
            candidate_drawdown=-0.30,
            candidate_turnover=0.60,
        )
    )

    assert gate["status"] == "rejected"
    assert len(gate["reasons"]) == 4
