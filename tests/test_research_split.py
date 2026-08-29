import pytest

from research_split import (
    candidate_specification_digest,
    dataset_lineage_digest,
    load_research_policy,
    normalize_research_split_manifest,
    research_split_digest,
    validate_comparison_execution_settings,
    validate_research_split_run,
)


def _manifest():
    payload = {
        "schema_version": 1,
        "split_id": "historical-dow-research-v1",
        "role": "research",
        "evaluation_start": "2011-01-01",
        "evaluation_end": "2025-09-30",
        "experiment_namespace": "pit-factor-v1",
        "objectives": [
            "factor_residual_price_ridge",
            "factor_residual_ridge",
        ],
        "settings": {
            "horizon": 63,
            "maximum_training_periods": 12,
            "ridge_penalty": 5.0,
        },
        "universe_manifest_sha256": "a" * 64,
        "price_file_sha256": "b" * 64,
        "factor_file_sha256": "c" * 64,
        "locked": True,
    }
    payload["manifest_sha256"] = research_split_digest(payload)
    return payload


def test_split_manifest_detects_content_drift():
    payload = _manifest()
    payload["evaluation_end"] = "2024-12-31"

    with pytest.raises(ValueError, match="does not match its content"):
        normalize_research_split_manifest(payload)


def test_split_run_rejects_objective_or_data_drift():
    payload = _manifest()

    with pytest.raises(ValueError, match="mismatch for objectives"):
        validate_research_split_run(
            payload,
            split_id=payload["split_id"],
            experiment_namespace=payload["experiment_namespace"],
            objectives=["factor_residual_ridge"],
            settings=payload["settings"],
            evaluation_start=payload["evaluation_start"],
            evaluation_end=payload["evaluation_end"],
            universe_manifest_sha256="a" * 64,
            price_file_sha256="b" * 64,
            factor_file_sha256="c" * 64,
            auxiliary_files={},
        )

    with pytest.raises(ValueError, match="mismatch for price_file_sha256"):
        validate_research_split_run(
            payload,
            split_id=payload["split_id"],
            experiment_namespace=payload["experiment_namespace"],
            objectives=payload["objectives"],
            settings=payload["settings"],
            evaluation_start=payload["evaluation_start"],
            evaluation_end=payload["evaluation_end"],
            universe_manifest_sha256="a" * 64,
            price_file_sha256="d" * 64,
            factor_file_sha256="c" * 64,
            auxiliary_files={},
        )


def test_legacy_locked_research_split_is_integrity_only():
    payload = _manifest()

    result = validate_research_split_run(
        payload,
        split_id=payload["split_id"],
        experiment_namespace=payload["experiment_namespace"],
        objectives=payload["objectives"],
        settings=payload["settings"],
        evaluation_start=payload["evaluation_start"],
        evaluation_end=payload["evaluation_end"],
        universe_manifest_sha256="a" * 64,
        price_file_sha256="b" * 64,
        factor_file_sha256="c" * 64,
        auxiliary_files={},
    )

    assert result["integrity_locked"] is True
    assert result["promotion_safe"] is False
    assert result["evidence_scope"] == "legacy_unclassified"


def test_legacy_locked_holdout_is_not_new_promotion_evidence():
    payload = _manifest()
    payload["role"] = "locked_holdout"
    payload["manifest_sha256"] = research_split_digest(payload)

    result = validate_research_split_run(
        payload,
        split_id=payload["split_id"],
        experiment_namespace=payload["experiment_namespace"],
        objectives=payload["objectives"],
        settings=payload["settings"],
        evaluation_start=payload["evaluation_start"],
        evaluation_end=payload["evaluation_end"],
        universe_manifest_sha256="a" * 64,
        price_file_sha256="b" * 64,
        factor_file_sha256="c" * 64,
        auxiliary_files={},
    )

    assert result["integrity_locked"] is True
    assert result["promotion_safe"] is False


def test_legacy_locked_validation_is_not_new_promotion_evidence():
    payload = _manifest()
    payload["role"] = "validation"
    payload["manifest_sha256"] = research_split_digest(payload)

    result = validate_research_split_run(
        payload,
        split_id=payload["split_id"],
        experiment_namespace=payload["experiment_namespace"],
        objectives=payload["objectives"],
        settings=payload["settings"],
        evaluation_start=payload["evaluation_start"],
        evaluation_end=payload["evaluation_end"],
        universe_manifest_sha256="a" * 64,
        price_file_sha256="b" * 64,
        factor_file_sha256="c" * 64,
        auxiliary_files={},
    )

    assert result["integrity_locked"] is True
    assert result["promotion_safe"] is False


def test_comparison_contract_rejects_execution_drift():
    common = {
        "eligible_universe_sha256": "a" * 64,
        "rebalance_dates": ["2024-03-31", "2024-06-30"],
        "horizon": 63,
        "rebalance_step": 63,
        "max_asset_weight": 0.20,
        "rebalance_band": 0.02,
        "max_turnover": 0.35,
        "transaction_cost_bps": 10,
        "risk_free_sha256": "b" * 64,
    }
    candidate = {**common, "transaction_cost_bps": 20}

    with pytest.raises(ValueError, match="transaction_cost_bps"):
        validate_comparison_execution_settings(common, candidate)

    assert validate_comparison_execution_settings(common, common) == common


def test_schema_v2_locks_policy_candidate_and_dataset_hashes():
    payload = _manifest()
    payload.update({
        "schema_version": 2,
        "lane": "alpha",
        "evidence_scope": "experimental_public_data",
        "policy_sha256": load_research_policy()["policy_sha256"],
    })
    payload["candidate_specification_sha256"] = (
        candidate_specification_digest(payload)
    )
    payload["dataset_lineage_sha256"] = dataset_lineage_digest(payload)
    payload["manifest_sha256"] = research_split_digest(payload)

    normalized = normalize_research_split_manifest(payload)
    assert normalized["lane"] == "alpha"
    assert normalized["evidence_scope"] == "experimental_public_data"

    payload["settings"]["ridge_penalty"] = 20.0
    payload["manifest_sha256"] = research_split_digest(payload)
    with pytest.raises(ValueError, match="candidate_specification_sha256"):
        normalize_research_split_manifest(payload)


def test_policy_keeps_production_baseline_and_separates_lane_contracts():
    policy = load_research_policy()

    assert policy["production_baseline"] == {
        "optimization_method": "MIN_VARIANCE",
        "forecast_method_effective": "RISK_ONLY",
        "covariance_estimator": "ledoit_wolf",
        "objective": "long_only_capped_global_minimum_variance",
    }
    assert policy["lanes"]["alpha"]["stop_rule"] == (
        "do_not_run_overlay_or_allocator_when_signal_gate_fails"
    )
    assert policy["lanes"]["risk"]["allowed_primary_endpoints"] == [
        "realized_volatility",
        "risk_forecast_mae",
        "max_drawdown",
    ]
    assert policy["lanes"]["execution_correctness"][
        "statistical_performance_claim"
    ] is False


def test_consumed_split_rejects_selection_but_allows_acknowledged_diagnostic():
    from pathlib import Path
    import json

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "data/research/derived/"
         "fama_french_12_industry_ff3_factor_risk_smoke_split_v1.json")
        .read_text(encoding="utf-8")
    )
    kwargs = {
        "split_id": manifest["split_id"],
        "experiment_namespace": manifest["experiment_namespace"],
        "objectives": manifest["objectives"],
        "settings": manifest["settings"],
        "evaluation_start": manifest["evaluation_start"],
        "evaluation_end": manifest["evaluation_end"],
        "universe_manifest_sha256": manifest["universe_manifest_sha256"],
        "price_file_sha256": manifest["price_file_sha256"],
        "factor_file_sha256": manifest["factor_file_sha256"],
        "auxiliary_files": manifest.get("auxiliary_files", {}),
    }
    with pytest.raises(ValueError, match="Consumed research evidence"):
        validate_research_split_run(manifest, **kwargs)

    result = validate_research_split_run(
        manifest,
        evidence_use="diagnostic",
        acknowledge_consumed=True,
        **kwargs,
    )
    assert result["consumption_state"] == "consumed"
    assert result["candidate_selection_allowed"] is False
    assert result["promotion_safe"] is False
