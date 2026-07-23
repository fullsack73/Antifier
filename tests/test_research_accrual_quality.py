import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "research_accrual_quality.py"
SPEC = importlib.util.spec_from_file_location(
    "research_accrual_quality",
    TOOL_PATH,
)
RESEARCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESEARCH)


def test_accrual_quality_buckets_invert_official_quintiles():
    labels = [
        "SMALL LoAC",
        "ME1 AC2",
        "ME3 AC3",
        "ME5 AC4",
        "BIG HiAC",
    ]

    result = RESEARCH.accrual_quality_buckets(labels)

    assert result.tolist() == [5.0, 4.0, 3.0, 2.0, 1.0]


def test_net_issuance_quality_orders_special_and_quintile_buckets():
    labels = [
        "SMALL NegNI",
        "ME1 ZeroNI",
        "ME2 LoNI",
        "ME3 NI2",
        "ME3 NI3",
        "ME4 NI4",
        "BIG HiNI",
    ]

    result = RESEARCH.net_issuance_quality_buckets(labels)

    assert result.tolist() == [7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]


def test_residual_variance_quality_inverts_official_quintiles():
    labels = [
        "SMALL LoVAR",
        "ME2 VAR1",
        "ME3 VAR2",
        "ME3 VAR3",
        "ME4 VAR4",
        "ME5 VAR5",
        "BIG HiVAR",
    ]

    result = RESEARCH.residual_variance_quality_buckets(labels)

    assert result.tolist() == [5.0, 5.0, 4.0, 3.0, 2.0, 1.0, 1.0]


def test_short_term_reversal_inverts_prior_month_quintiles():
    labels = [
        "SMALL LoPRIOR",
        "ME2 PRIOR1",
        "ME3 PRIOR2",
        "ME3 PRIOR3",
        "ME4 PRIOR4",
        "ME5 PRIOR5",
        "BIG HiPRIOR",
    ]

    result = RESEARCH.short_term_reversal_buckets(labels)

    assert result.tolist() == [5.0, 5.0, 4.0, 3.0, 2.0, 1.0, 1.0]


def test_accrual_research_uses_only_pre_signal_momentum_prices():
    dates = pd.date_range("2000-01-31", periods=18, freq="ME")
    prices = pd.DataFrame(
        {
            "SMALL LoAC": range(100, 118),
            "BIG HiAC": range(100, 82, -1),
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
            "momentum_lookback": 12,
            "momentum_skip": 1,
        },
    )()
    accrual = RESEARCH.accrual_quality_buckets(prices.columns)

    baseline = RESEARCH._run_periods(prices, accrual, args)[0]
    changed = prices.copy()
    changed.loc[dates[12]:, :] = [
        [1e9, 1.0] if index % 2 == 0 else [1.0, 1e9]
        for index in range(len(changed.loc[dates[12]:]))
    ]
    changed_result = RESEARCH._run_periods(changed, accrual, args)[0]

    assert baseline[0]["scores"] == changed_result[0]["scores"]
    assert baseline[0]["as_of_date"] == dates[12].strftime("%Y-%m-%d")
