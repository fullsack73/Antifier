import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from shadow_forward import (
    append_observation,
    create_campaign,
    evaluate_campaign,
    record_outcome,
    verify_ledger,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "shadow_forward"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _initialized(tmp_path):
    ledger = tmp_path / "shadow.sqlite3"
    campaign = _fixture("campaign.json")
    create_campaign(
        ledger,
        campaign,
        now="2026-08-28T00:00:00+00:00",
    )
    return ledger


def test_baseline_observation_is_append_only_and_duplicate_aware(tmp_path):
    ledger = _initialized(tmp_path)
    observation = _fixture("observation.json")
    now = "2026-08-28T21:00:00+00:00"

    first = append_observation(ledger, observation, now=now)
    duplicate = append_observation(ledger, observation, now=now)

    assert first["status"] == "recorded"
    assert duplicate["status"] == "duplicate_detected"
    changed = copy.deepcopy(observation)
    changed["data_provenance"]["coverage"] = 0.9
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        append_observation(ledger, changed, now=now)
    assert verify_ledger(ledger) == {
        "status": "ok",
        "campaigns": 1,
        "observations": 1,
        "outcomes": 0,
        "outcome_attempts": 0,
    }


def test_backfill_and_candidate_injection_are_rejected(tmp_path):
    ledger = _initialized(tmp_path)
    observation = _fixture("observation.json")
    append_observation(
        ledger,
        observation,
        now="2026-08-28T21:00:00+00:00",
    )

    backfill = copy.deepcopy(observation)
    backfill["as_of_timestamp"] = "2026-08-28T19:00:00+00:00"
    with pytest.raises(ValueError, match="backfill"):
        append_observation(
            ledger,
            backfill,
            now="2026-08-28T22:00:00+00:00",
        )

    injected = copy.deepcopy(observation)
    injected["as_of_timestamp"] = "2026-08-28T22:00:00+00:00"
    injected["candidate"] = {"weights": {"AAA": 0.5, "BBB": 0.5}}
    with pytest.raises(ValueError, match="baseline-only"):
        append_observation(
            ledger,
            injected,
            now="2026-08-28T23:00:00+00:00",
        )


def test_failed_observation_is_recorded_without_model_outputs(tmp_path):
    ledger = _initialized(tmp_path)
    failed = _fixture("observation.json")
    failed.update({
        "status": "network_failure",
        "baseline": None,
        "candidate": None,
        "eligible_universe": [],
        "as_of_timestamp": "2026-08-28T20:00:00+00:00",
    })
    failed["data_provenance"] = {
        "source": "fixture",
        "error": "network timeout",
        "coverage": 0.0,
        "missing_tickers": ["AAA", "BBB"],
    }

    result = append_observation(
        ledger,
        failed,
        now="2026-08-28T21:00:00+00:00",
    )
    assert result["status"] == "recorded"
    assert evaluate_campaign(ledger, failed["campaign_id"])[
        "observation_status_counts"
    ] == {"network_failure": 1}


def test_complete_observation_requires_data_and_execution_identities(tmp_path):
    ledger = _initialized(tmp_path)
    observation = _fixture("observation.json")
    observation["data_provenance"].pop("data_sha256")
    with pytest.raises(ValueError, match="data_provenance.data_sha256"):
        append_observation(
            ledger,
            observation,
            now="2026-08-28T21:00:00+00:00",
        )

    observation = _fixture("observation.json")
    observation["baseline"]["execution"]["transaction_cost"] = 0.002
    with pytest.raises(ValueError, match="transaction cost identity"):
        append_observation(
            ledger,
            observation,
            now="2026-08-28T21:00:00+00:00",
        )


def test_alpha_candidate_requires_preexisting_signal_gate(tmp_path):
    campaign = _fixture("campaign.json")
    campaign["lane"] = "alpha"
    campaign["candidate_specification"] = {"candidate_id": "alpha-v1"}

    with pytest.raises(ValueError, match="signal-only gate"):
        create_campaign(
            tmp_path / "shadow.sqlite3",
            campaign,
            now="2026-08-28T00:00:00+00:00",
        )


def test_outcome_requires_maturity_and_complete_coverage(tmp_path):
    ledger = _initialized(tmp_path)
    observation = _fixture("observation.json")
    append_observation(
        ledger,
        observation,
        now="2026-08-28T21:00:00+00:00",
    )
    outcome = _fixture("outcome.json")
    immature = copy.deepcopy(outcome)
    immature["prices"] = immature["prices"][:3]

    attempt = record_outcome(
        ledger,
        observation["campaign_id"],
        observation["as_of_timestamp"],
        immature,
        now="2026-09-02T23:00:00+00:00",
    )
    assert attempt == {"status": "immature", "outcome_recorded": False}

    recorded = record_outcome(
        ledger,
        observation["campaign_id"],
        observation["as_of_timestamp"],
        outcome,
        now="2026-09-03T00:00:00+00:00",
    )
    assert recorded["status"] == "recorded"
    assert recorded["metrics"]["horizon_observations"] == 3
    with pytest.raises(ValueError, match="Duplicate realized outcome"):
        record_outcome(
            ledger,
            observation["campaign_id"],
            observation["as_of_timestamp"],
            outcome,
            now="2026-09-03T01:00:00+00:00",
        )
    evaluation = evaluate_campaign(ledger, observation["campaign_id"])
    assert evaluation["status"] == "insufficient_mature_observations"
    assert evaluation["mature_outcome_count"] == 1
    assert evaluation["production_auto_promotion"] is False
    assert verify_ledger(ledger)["outcome_attempts"] == 1


def test_database_triggers_reject_updates(tmp_path):
    ledger = _initialized(tmp_path)
    with sqlite3.connect(ledger) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE campaigns SET campaign_id = 'changed'"
            )


def test_campaign_specification_change_is_rejected(tmp_path):
    ledger = tmp_path / "shadow.sqlite3"
    campaign = _fixture("campaign.json")
    create_campaign(
        ledger,
        campaign,
        now="2026-08-28T00:00:00+00:00",
    )
    changed = copy.deepcopy(campaign)
    changed["horizon_observations"] += 1

    with pytest.raises(ValueError, match="different specification"):
        create_campaign(
            ledger,
            changed,
            now="2026-08-28T00:01:00+00:00",
        )


def test_campaign_creation_time_cannot_be_backdated(tmp_path):
    ledger = tmp_path / "shadow.sqlite3"
    campaign = _fixture("campaign.json")
    campaign["created_at"] = "2000-01-01T00:00:00+00:00"

    created = create_campaign(
        ledger,
        campaign,
        now="2026-08-28T00:00:00+00:00",
    )
    assert created["campaign"]["created_at"] == "2026-08-28T00:00:00+00:00"
    observation = _fixture("observation.json")
    observation["as_of_timestamp"] = "2026-08-27T23:59:59+00:00"
    with pytest.raises(ValueError, match="backfill"):
        append_observation(
            ledger,
            observation,
            now="2026-08-28T00:01:00+00:00",
        )


def test_cli_init_observe_and_verify(tmp_path):
    ledger = tmp_path / "cli.sqlite3"
    campaign = _fixture("campaign.json")
    campaign["campaign_id"] = "cli-baseline-v1"
    observation = _fixture("observation.json")
    observation["campaign_id"] = campaign["campaign_id"]
    campaign_path = tmp_path / "campaign.json"
    observation_path = tmp_path / "observation.json"
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
    tool = ROOT / "tools" / "shadow_forward.py"

    init = subprocess.run(
        [
            sys.executable,
            str(tool),
            "--ledger",
            str(ledger),
            "init",
            "--campaign-spec",
            str(campaign_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert init.returncode == 0, init.stderr
    observation["as_of_timestamp"] = json.loads(init.stdout)["campaign"][
        "created_at"
    ]
    observation_path.write_text(json.dumps(observation), encoding="utf-8")

    for command in (
        ["observe", "--input", str(observation_path)],
        ["verify"],
    ):
        result = subprocess.run(
            [sys.executable, str(tool), "--ledger", str(ledger), *command],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
