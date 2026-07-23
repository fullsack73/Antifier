import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from portfolio_statistics import (  # noqa: E402
    bootstrap_improvement_gate,
    holm_bonferroni,
    paired_block_bootstrap,
)


def test_paired_block_bootstrap_detects_strong_risk_improvement():
    rng = np.random.default_rng(7)
    dates = pd.date_range("2010-01-04", periods=1500, freq="B")
    common = rng.normal(0.0004, 0.008, len(dates))
    baseline = pd.Series(
        common + rng.normal(0.0, 0.006, len(dates)),
        index=dates,
    )
    candidate = pd.Series(
        common + 0.0003 + rng.normal(0.0, 0.001, len(dates)),
        index=dates,
    )

    result = paired_block_bootstrap(
        candidate,
        baseline,
        risk_free_rate=0.0,
        block_size=21,
        samples=1000,
        seed=11,
    )
    gate = bootstrap_improvement_gate(result, minimum_probability=0.90)

    assert result["status"] == "ok"
    assert result["probability"]["lower_volatility"] > 0.99
    assert result["probability"]["higher_sharpe"] > 0.90
    assert gate["status"] == "passed"


def test_paired_block_bootstrap_is_deterministic_and_aligned():
    dates = pd.date_range("2020-01-02", periods=300, freq="B")
    baseline = pd.Series(np.linspace(-0.01, 0.01, 300), index=dates)
    candidate = baseline * 0.9
    candidate = candidate.iloc[5:]

    first = paired_block_bootstrap(
        candidate,
        baseline,
        samples=200,
        seed=123,
    )
    second = paired_block_bootstrap(
        candidate,
        baseline,
        samples=200,
        seed=123,
    )

    assert first == second
    assert first["observation_count"] == 295


def test_paired_bootstrap_uses_historical_daily_risk_free_returns():
    dates = pd.date_range("2020-01-02", periods=300, freq="B")
    baseline = pd.Series(0.0005, index=dates)
    candidate = pd.Series(0.0010, index=dates)
    risk_free = pd.Series(0.0002, index=dates)

    result = paired_block_bootstrap(
        candidate,
        baseline,
        risk_free_daily_returns=risk_free,
        samples=200,
    )

    assert result["observed"]["candidate"][
        "annualized_excess_return"
    ] == pytest.approx((0.0010 - 0.0002) * 252)
    assert result["observed"]["baseline"][
        "annualized_excess_return"
    ] == pytest.approx((0.0005 - 0.0002) * 252)


def test_bootstrap_gate_rejects_insufficient_data():
    result = paired_block_bootstrap(
        [0.01, -0.01, 0.005],
        [0.01, -0.01, 0.005],
        block_size=21,
        samples=100,
    )

    assert result["status"] == "insufficient_data"
    assert bootstrap_improvement_gate(result)["status"] == "rejected"


def test_return_pair_drops_nonfinite_observations():
    result = paired_block_bootstrap(
        pd.Series([0.01, np.nan] * 100),
        pd.Series([0.0, 0.01] * 100),
        block_size=10,
        samples=100,
    )

    assert result["observation_count"] == 100
    assert result["observed"]["difference"]["annualized_return"] == pytest.approx(
        2.52
    )


def test_holm_bonferroni_controls_familywise_error():
    result = holm_bonferroni(
        {
            "strong": 0.001,
            "borderline": 0.03,
            "weak": 0.20,
        },
        alpha=0.05,
    )

    assert result["strong"]["adjusted_p_value"] == pytest.approx(0.003)
    assert result["strong"]["significant"] is True
    assert result["borderline"]["adjusted_p_value"] == pytest.approx(0.06)
    assert result["borderline"]["significant"] is False
