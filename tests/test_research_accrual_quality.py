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


def test_long_term_reversal_inverts_prior_13_60_quintiles():
    labels = [
        "SMALL LoPRIOR",
        "ME2 PRIOR1",
        "ME3 PRIOR2",
        "ME3 PRIOR3",
        "ME4 PRIOR4",
        "ME5 PRIOR5",
        "BIG HiPRIOR",
    ]

    result = RESEARCH.long_term_reversal_buckets(labels)

    assert result.tolist() == [5.0, 5.0, 4.0, 3.0, 2.0, 1.0, 1.0]


def test_cashflow_yield_orders_official_deciles():
    labels = [
        "Lo 10",
        "2-Dec",
        "3-Dec",
        "4-Dec",
        "5-Dec",
        "6-Dec",
        "7-Dec",
        "8-Dec",
        "9-Dec",
        "Hi 10",
    ]

    result = RESEARCH.cashflow_yield_buckets(labels)

    assert result.tolist() == list(map(float, range(1, 11)))


def test_cashflow_yield_orders_size_by_cfp_terciles():
    labels = [
        "SMALL LoCFP",
        "ME1 CFP2",
        "SMALL HiCFP",
        "BIG LoCFP",
        "ME2 CFP2",
        "BIG HiCFP",
    ]

    result = RESEARCH.cashflow_yield_buckets(labels)

    assert result.tolist() == [1.0, 2.0, 3.0, 1.0, 2.0, 3.0]


def test_cashflow_yield_only_freezes_zero_momentum_weight():
    args = type(
        "Args",
        (),
        {
            "signal_kind": "cashflow_yield_only",
            "train_window": 72,
            "horizon": 12,
            "rebalance_step": 12,
            "momentum_lookback": 12,
            "momentum_skip": 1,
            "bootstrap_samples": 2000,
            "bootstrap_block_size": 3,
            "bootstrap_minimum_probability": 0.95,
        },
    )()

    settings = RESEARCH._settings(args)

    assert settings["momentum_weight"] == 0.0
    assert settings["cashflow_yield_weight"] == 1.0
    assert settings["tuned_parameters"] == "none"


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
