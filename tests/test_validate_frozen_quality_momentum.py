import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "validate_frozen_quality_momentum.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_frozen_quality_momentum",
    TOOL_PATH,
)
VALIDATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATION)


def _diagnostics(rank_ic, spread):
    return {
        "period_count": 47,
        "mean_rank_ic": rank_ic,
        "positive_rank_ic_rate": 0.60,
        "mean_top_bottom_spread": spread,
        "mean_coverage_rate": 1.0,
    }


def test_quality_validation_case_requires_positive_baseline_uplift():
    passed = VALIDATION._case_gate({
        "candidate": _diagnostics(0.06, 0.012),
        "baseline": _diagnostics(0.01, 0.002),
    })
    rejected = VALIDATION._case_gate({
        "candidate": _diagnostics(0.01, 0.002),
        "baseline": _diagnostics(0.02, 0.003),
    })

    assert passed["status"] == "passed"
    assert rejected["status"] == "rejected"
    assert len(rejected["reasons"]) == 2
