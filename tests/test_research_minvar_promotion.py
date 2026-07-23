import importlib.util
from pathlib import Path

import pytest


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


def test_generic_gate_supports_nested_clustered_candidate():
    summary = _summary()
    summary["nested_clustered_minimum_variance"] = {
        "annual_volatility": 0.08,
        "sharpe": 0.90,
        "max_drawdown": -0.18,
        "avg_controlled_turnover": 0.14,
    }

    gate = research_minvar_promotion._deterministic_gate(
        summary,
        candidate_name="nested_clustered_minimum_variance",
        statistical_baselines=(
            "min_variance",
            "risk_parity",
            "lightweight_bl",
        ),
        guard_baselines=("equal_weight", "historical_bl"),
    )

    assert gate["status"] == "passed"
    assert gate["reasons"] == []


def test_candidate_risk_diagnostics_summarizes_clusters():
    result = {
        "rebalance_records": [
            {
                "model": "nested_clustered_minimum_variance",
                "risk_model": {
                    "cluster_count": 3,
                    "requested_cluster_count": 3,
                    "silhouette_scores": {"3": 0.61},
                    "optimizer_success": True,
                    "fallback": False,
                    "pre_cap_maximum_weight": 0.24,
                    "cap_projection_l1_distance": 0.08,
                    "shrinkage_intensity": 0.20,
                    "method": "nested_clustered_minimum_variance",
                    "clusters": {"1": ["A", "B"]},
                },
            },
            {
                "model": "nested_clustered_minimum_variance",
                "risk_model": {
                    "cluster_count": 4,
                    "requested_cluster_count": 4,
                    "silhouette_scores": {"4": 0.57},
                    "optimizer_success": True,
                    "fallback": False,
                    "pre_cap_maximum_weight": 0.22,
                    "cap_projection_l1_distance": 0.04,
                    "shrinkage_intensity": 0.40,
                    "method": "nested_clustered_minimum_variance",
                    "clusters": {"1": ["A"], "2": ["B"]},
                },
            },
        ]
    }

    diagnostics = (
        research_minvar_promotion._candidate_risk_diagnostics(
            result,
            "nested_clustered_minimum_variance",
        )
    )

    assert diagnostics["cluster_count_distribution"] == {
        "3": 1,
        "4": 1,
    }
    assert diagnostics["mean_cluster_count"] == 3.5
    assert diagnostics["mean_selected_silhouette"] == 0.59
    assert diagnostics["optimizer_success_rate"] == 1.0
    assert diagnostics["fallback_rate"] == 0.0
    assert diagnostics["mean_shrinkage_intensity"] == pytest.approx(
        0.30
    )
    assert diagnostics["method_distribution"] == {
        "nested_clustered_minimum_variance": 2
    }


def test_constant_correlation_policy_is_return_forecast_free():
    policy = research_minvar_promotion.CANDIDATE_POLICIES[
        "constant_correlation_minimum_variance"
    ]

    assert policy["covariance"] == (
        "ledoit_wolf_constant_correlation"
    )
    assert policy["expected_returns"] == "unused"
    assert policy["forecast_model"] == "unused"
