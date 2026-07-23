import importlib.util
from argparse import Namespace
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


def test_value_quality_validation_freezes_four_characteristic_cases():
    args = Namespace(signal_kind="value_quality")
    cases = VALIDATION._validation_cases(args)

    assert VALIDATION._candidate_name(args) == "value_quality_momentum"
    assert [case["id"] for case in cases] == [
        "low_value",
        "high_value",
        "low_profitability",
        "high_profitability",
    ]
    assert all(len(case["tickers"]) == 10 for case in cases)


def test_net_issuance_validation_freezes_size_and_issuance_cases():
    args = Namespace(signal_kind="net_issuance")
    cases = VALIDATION._validation_cases(args)

    assert (
        VALIDATION._candidate_name(args)
        == "net_issuance_quality_momentum"
    )
    assert [case["id"] for case in cases] == [
        "small_size",
        "large_size",
        "low_net_issuance",
        "high_net_issuance",
    ]
    assert all(len(case["tickers"]) >= 14 for case in cases)


def test_net_issuance_case_gate_accepts_eleven_annual_periods():
    result = {
        "candidate": {
            **_diagnostics(0.06, 0.012),
            "period_count": 11,
        },
        "baseline": {
            **_diagnostics(0.01, 0.002),
            "period_count": 11,
        },
    }

    assert (
        VALIDATION._case_gate(result, minimum_periods=10)["status"]
        == "passed"
    )
