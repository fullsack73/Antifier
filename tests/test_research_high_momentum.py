import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "research_high_momentum",
    ROOT / "tools" / "research_high_momentum.py",
)
research_high_momentum = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_high_momentum)


def _candidate_signal(status="passed"):
    return {
        "gate": {
            "status": status,
            "reasons": (
                [] if status == "passed" else ["negative signal"]
            ),
        },
    }


def _paired_signal(ic=0.99, spread=0.99):
    return {
        "probability": {
            "higher_mean_rank_ic": ic,
            "higher_mean_top_bottom_spread": spread,
        },
    }


def _paired_portfolio(ret=0.99, sharpe=0.99):
    return {
        "probability": {
            "higher_return": ret,
            "higher_sharpe": sharpe,
        },
    }


def test_high_momentum_combined_gate_requires_all_hypotheses():
    gate, holm = research_high_momentum._combined_gate(
        _candidate_signal(),
        _paired_signal(),
        _paired_portfolio(),
        {"status": "passed", "reasons": []},
        0.95,
    )

    assert gate["status"] == "passed"
    assert all(item["significant"] for item in holm.values())


def test_high_momentum_combined_gate_rejects_signal_or_portfolio_gap():
    gate, holm = research_high_momentum._combined_gate(
        _candidate_signal("rejected"),
        _paired_signal(ic=0.80),
        _paired_portfolio(sharpe=0.70),
        {"status": "rejected", "reasons": ["worse drawdown"]},
        0.95,
    )

    assert gate["status"] == "rejected"
    assert gate["reasons"]
    assert not all(item["significant"] for item in holm.values())
