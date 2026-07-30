import pytest

from research_split import (
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


def test_locked_research_split_is_promotion_safe():
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

    assert result["promotion_safe"] is True


def test_locked_holdout_split_is_promotion_safe():
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

    assert result["promotion_safe"] is True


def test_locked_validation_split_is_promotion_safe():
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

    assert result["promotion_safe"] is True


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
