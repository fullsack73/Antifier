import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from production_baseline_observation import (
    build_production_baseline_observation,
    collect_production_baseline_observation,
)
from shadow_forward import (
    append_observation,
    create_campaign,
    evaluate_campaign,
    outcome_price_sha256,
    record_outcome,
    verify_ledger,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "shadow_forward"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _observation():
    campaign = _fixture("campaign.json")
    run_spec = _fixture("production_run.json")
    capture = _fixture("production_capture.json")
    observation = build_production_baseline_observation(
        campaign,
        run_spec,
        capture["optimizer_result"],
        capture["rerun_result"],
        as_of_timestamp=capture["as_of_timestamp"],
    )
    return campaign, run_spec, capture, observation


def test_adapter_derives_baseline_execution_and_risk_from_optimizer_results(tmp_path):
    campaign, _, _, observation = _observation()
    baseline = observation["baseline"]
    execution = baseline["execution"]

    assert observation["contract_version"] == 2
    assert observation["candidate"] is None
    assert baseline["signal"] == {"status": "no_view", "scores": {}}
    assert baseline["optimization_method"] == "MIN_VARIANCE"
    assert baseline["forecast_method_effective"] == "RISK_ONLY"
    assert baseline["risk_forecast"]["annual_volatility"] == pytest.approx(
        0.1833030277982336
    )
    assert sum(baseline["weights"].values()) + baseline["cash_weight"] == pytest.approx(1.0)
    assert execution["transaction_cost"] == pytest.approx(
        execution["turnover"] * 0.001
    )
    assert execution["post_cost_wealth"] == pytest.approx(
        execution["reference_wealth"] - execution["transaction_cost"]
    )

    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-28T00:00:00+00:00")
    append_observation(
        ledger,
        observation,
        now="2026-08-28T21:00:00+00:00",
    )
    assert verify_ledger(ledger)["observations"] == 1


def test_v2_ledger_recomputes_values_instead_of_trusting_boolean_claims(tmp_path):
    campaign, _, _, observation = _observation()
    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-28T00:00:00+00:00")
    forged = copy.deepcopy(observation)
    forged["baseline"]["execution"]["transaction_cost"] = 0.5
    forged["baseline"]["execution"]["checks"] = {
        "transaction_cost_identity": True,
        "wealth_identity": True,
    }

    with pytest.raises(ValueError, match="execution identity failed"):
        append_observation(
            ledger,
            forged,
            now="2026-08-28T21:00:00+00:00",
        )

    forged_coverage = copy.deepcopy(observation)
    forged_coverage["data_provenance"]["coverage"] = 0.5
    with pytest.raises(ValueError, match="coverage identity"):
        append_observation(
            ledger,
            forged_coverage,
            now="2026-08-28T21:00:00+00:00",
        )


def test_same_as_of_retry_ignores_recording_time_but_detects_input_change(tmp_path):
    campaign, _, _, observation = _observation()
    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-28T00:00:00+00:00")
    append_observation(ledger, observation, now="2026-08-28T21:00:00+00:00")
    retry = append_observation(
        ledger,
        observation,
        now="2026-08-28T22:00:00+00:00",
    )
    assert retry["status"] == "duplicate_detected"

    changed = copy.deepcopy(observation)
    changed["data_provenance"]["data_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        append_observation(
            ledger,
            changed,
            now="2026-08-28T23:00:00+00:00",
        )


def test_live_collector_is_dependency_injected_and_forces_production_baseline(tmp_path):
    campaign, run_spec, capture, _ = _observation()
    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-28T00:00:00+00:00")
    calls = []

    def optimizer(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(capture["optimizer_result"])

    observation = collect_production_baseline_observation(
        ledger,
        campaign["campaign_id"],
        run_spec,
        scheduled_for=capture["as_of_timestamp"],
        optimizer=optimizer,
    )

    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0]["optimization_method"] == "MIN_VARIANCE"
    assert calls[0]["forecast_method"] == "RISK_ONLY"
    assert calls[0]["persist_result"] is False
    assert calls[0]["load_if_available"] is False
    assert observation["status"] == "complete"


def test_live_collector_converts_unexpected_failure_to_appendable_observation(tmp_path):
    campaign, run_spec, capture, _ = _observation()
    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-28T00:00:00+00:00")

    def optimizer(**kwargs):
        raise RuntimeError("fixture optimizer failure")

    observation = collect_production_baseline_observation(
        ledger,
        campaign["campaign_id"],
        run_spec,
        scheduled_for=capture["as_of_timestamp"],
        optimizer=optimizer,
    )
    assert observation["status"] == "calculation_failure"
    assert observation["baseline"] is None
    recorded = append_observation(
        ledger,
        observation,
        now="2026-08-28T01:00:00+00:00",
    )
    assert recorded["status"] == "recorded"


def test_adapter_records_partial_and_network_failure_without_candidate():
    campaign, run_spec, capture, _ = _observation()
    partial = copy.deepcopy(capture["optimizer_result"])
    partial["prices"].pop("BBB")
    partial_rerun = copy.deepcopy(partial)
    observation = build_production_baseline_observation(
        campaign,
        run_spec,
        partial,
        partial_rerun,
        as_of_timestamp=capture["as_of_timestamp"],
    )
    assert observation["status"] == "partial"
    assert observation["baseline"]["execution"]["missing_price_tickers"] == ["BBB"]

    failure = build_production_baseline_observation(
        campaign,
        run_spec,
        {
            "error": "timeout",
            "data_eligibility": {
                "requested_tickers": ["AAA", "BBB"],
                "eligible_tickers": [],
            },
            "market_data_provenance": {
                "status": "network_failure",
                "coverage": 0.0,
                "missing_tickers": ["AAA", "BBB"],
            },
        },
        {},
        as_of_timestamp=capture["as_of_timestamp"],
    )
    assert failure["status"] == "network_failure"
    assert failure["baseline"] is None
    assert failure["candidate"] is None


def test_v2_outcome_requires_source_hash_and_includes_execution_cost(tmp_path):
    campaign, _, _, observation = _observation()
    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-28T00:00:00+00:00")
    append_observation(ledger, observation, now="2026-08-28T21:00:00+00:00")
    outcome = _fixture("outcome.json")
    outcome["data_sha256"] = outcome_price_sha256(outcome["prices"])

    forged = copy.deepcopy(outcome)
    forged["data_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="does not match"):
        record_outcome(
            ledger,
            campaign["campaign_id"],
            observation["as_of_timestamp"],
            forged,
            now="2026-09-03T00:00:00+00:00",
        )

    recorded = record_outcome(
        ledger,
        campaign["campaign_id"],
        observation["as_of_timestamp"],
        outcome,
        now="2026-09-03T00:00:00+00:00",
    )
    metrics = recorded["metrics"]
    assert metrics["realized_return"] < metrics["gross_market_return"]
    assert metrics["transaction_cost_drag"] == pytest.approx(
        observation["baseline"]["execution"]["transaction_cost"]
    )


def test_partial_observation_outcome_is_recorded_but_excluded_from_evaluation(tmp_path):
    campaign, run_spec, capture, _ = _observation()
    partial = copy.deepcopy(capture["optimizer_result"])
    partial["prices"].pop("BBB")
    observation = build_production_baseline_observation(
        campaign,
        run_spec,
        partial,
        copy.deepcopy(partial),
        as_of_timestamp=capture["as_of_timestamp"],
    )
    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-28T00:00:00+00:00")
    append_observation(ledger, observation, now="2026-08-28T01:00:00+00:00")
    outcome = _fixture("outcome.json")
    outcome["data_sha256"] = outcome_price_sha256(outcome["prices"])
    record_outcome(
        ledger,
        campaign["campaign_id"],
        observation["as_of_timestamp"],
        outcome,
        now="2026-09-03T00:00:00+00:00",
    )

    evaluation = evaluate_campaign(ledger, campaign["campaign_id"])
    assert evaluation["recorded_outcome_count"] == 1
    assert evaluation["mature_outcome_count"] == 0


def test_outcome_network_failure_can_be_logged_without_fake_data_hash(tmp_path):
    campaign, _, _, observation = _observation()
    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-28T00:00:00+00:00")
    append_observation(ledger, observation, now="2026-08-28T21:00:00+00:00")

    result = record_outcome(
        ledger,
        campaign["campaign_id"],
        observation["as_of_timestamp"],
        {
            "status": "network_failure",
            "data_provenance": {"source": "fixture", "error": "timeout"},
            "error": "timeout",
        },
        now="2026-09-03T00:00:00+00:00",
    )
    assert result == {"status": "network_failure", "outcome_recorded": False}
    assert verify_ledger(ledger)["outcome_attempts"] == 1


def test_collect_baseline_cli_uses_same_adapter_with_offline_capture(tmp_path):
    campaign = _fixture("campaign.json")
    ledger = tmp_path / "shadow.sqlite3"
    create_campaign(ledger, campaign, now="2026-08-27T00:00:00+00:00")
    command = [
        sys.executable,
        str(ROOT / "tools" / "shadow_forward.py"),
        "--ledger",
        str(ledger),
        "collect-baseline",
        "--campaign-id",
        campaign["campaign_id"],
        "--run-spec",
        str(FIXTURES / "production_run.json"),
        "--fixture-capture",
        str(FIXTURES / "production_capture.json"),
    ]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout)["status"] == "recorded"
    assert verify_ledger(ledger)["observations"] == 1
