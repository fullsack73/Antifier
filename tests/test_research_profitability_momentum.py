import importlib.util
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "research_profitability_momentum.py"
SPEC = importlib.util.spec_from_file_location(
    "research_profitability_momentum",
    TOOL_PATH,
)
RESEARCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESEARCH)


def _args(signal_kind):
    return Namespace(
        signal_kind=signal_kind,
        train_window=505,
        horizon=63,
        rebalance_step=63,
        bootstrap_samples=2000,
        bootstrap_block_size=4,
        bootstrap_minimum_probability=0.95,
    )


def test_quality_mode_parses_french_op_and_investment_quintiles():
    labels = [
        "LoOP LoINV",
        "OP1 INV2",
        "OP3 INV4",
        "HiOP LoINV",
        "HiOP HiINV",
    ]

    profitability = RESEARCH.operating_profitability_buckets(labels)
    investment = RESEARCH.investment_buckets(labels)

    assert profitability.tolist() == [1.0, 1.0, 3.0, 5.0, 5.0]
    assert investment.tolist() == [1.0, 2.0, 4.0, 1.0, 5.0]


def test_quality_mode_freezes_half_momentum_quarter_op_and_investment():
    profitability = RESEARCH._settings(_args("profitability"))
    quality = RESEARCH._settings(_args("quality"))

    assert profitability["momentum_weight"] == 0.50
    assert profitability["profitability_weight"] == 0.50
    assert "conservative_investment_weight" not in profitability
    assert quality["momentum_weight"] == 0.50
    assert quality["profitability_weight"] == 0.25
    assert quality["conservative_investment_weight"] == 0.25
