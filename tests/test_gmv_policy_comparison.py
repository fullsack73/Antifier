import copy
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from gmv_policy_comparison import (  # noqa: E402
    RebalanceNotDue,
    build_comparison_observation,
    build_failed_comparison_observation,
    collect_live_comparison_inputs,
    create_comparison_spec,
    validate_comparison_spec,
)
from research_split import canonical_json_digest  # noqa: E402
from shadow_forward import (  # noqa: E402
    append_observation,
    create_campaign,
    evaluate_campaign,
    latest_complete_observation,
    outcome_price_sha256,
    record_outcome,
    verify_ledger,
)


TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


def _spec():
    return create_comparison_spec(
        TICKERS,
        universe_source_sha256="a" * 64,
        code_revision="fixture-revision",
    )


def _campaign(spec):
    return {
        "campaign_id": "fixture-policy-comparison-v1",
        "timezone": "UTC",
        "lane": "risk",
        "evidence_scope": "calendar_forward_shadow",
        "horizon_observations": 63,
        "minimum_coverage": 0.8,
        "universe_policy": {"requested_universe_sha256": spec["requested_universe_sha256"]},
        "baseline_specification": spec["production_baseline"],
        "candidate_specification": None,
        "comparison_specification": spec,
        "execution_conditions": {
            "transaction_cost_bps": 10.0,
            "rebalance_band": 0.02,
            "max_turnover": 0.35,
        },
    }


def _optimizer_result(weights=None, prices=None, data_hash="b" * 64):
    weights = weights or {ticker: 1.0 / len(TICKERS) for ticker in TICKERS}
    prices = prices or {ticker: 100.0 for ticker in TICKERS}
    covariance = {
        ticker: {
            other: 0.04 if ticker == other else 0.005
            for other in TICKERS
        }
        for ticker in TICKERS
    }
    return {
        "weights": weights,
        "cash_weight": 1.0 - sum(weights.values()),
        "prices": prices,
        "optimization_method": "MIN_VARIANCE",
        "forecast_method_effective": "RISK_ONLY",
        "forecast_bypassed": True,
        "data_eligibility": {
            "requested_tickers": TICKERS,
            "eligible_tickers": TICKERS,
        },
        "market_data_provenance": {
            "source": "fixture_adjusted_close",
            "status": "complete",
            "coverage": 1.0,
            "row_count": 504,
            "data_sha256": data_hash,
            "missing_tickers": [],
        },
        "classification_metadata": {"securities": {}},
        "optimizer_controls": {
            "solver_objective": "ledoit_wolf_minimum_variance",
            "asset_constraints": [],
            "group_constraints": [],
        },
        "_observation_context": {"covariance": covariance},
    }


def _observation(spec, campaign, first, prior=None, as_of="2026-08-29T00:00:00+00:00"):
    return build_comparison_observation(
        campaign,
        spec,
        first,
        copy.deepcopy(first),
        as_of_timestamp=as_of,
        prior_observation=prior,
    )


def test_spec_hash_and_locked_settings_detect_drift():
    spec = _spec()
    assert validate_comparison_spec(spec) == spec
    changed = copy.deepcopy(spec)
    changed["settings"]["rebalance_frequency"] = 21
    changed["comparison_spec_sha256"] = canonical_json_digest({
        key: value for key, value in changed.items() if key != "comparison_spec_sha256"
    })
    with pytest.raises(ValueError, match="setting changed"):
        validate_comparison_spec(changed)


def test_tracked_registration_artifact_hash():
    path = ROOT / "data" / "research" / "derived" / "production_gmv_policy_forward_registration_v1.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))
    expected = artifact.pop("artifact_sha256")
    assert canonical_json_digest(artifact) == expected


def test_initial_allocation_is_identical_and_costed_once():
    spec = _spec()
    campaign = _campaign(spec)
    observation = _observation(spec, campaign, _optimizer_result())
    policies = observation["policies"]
    base = policies["buy_and_hold"]
    for policy in policies.values():
        assert policy["executed_quantities"] == base["executed_quantities"]
        assert policy["executed_cash"] == base["executed_cash"]
        assert policy["transaction_cost"] == pytest.approx(base["transaction_cost"])
        assert policy["turnover"] == pytest.approx(base["turnover"])
        assert sum(policy["weights"].values()) + policy["cash_weight"] == pytest.approx(1.0)
        assert policy["post_cost_wealth"] == pytest.approx(
            policy["pre_trade_wealth"] - policy["transaction_cost"]
        )


def test_later_observation_separates_policies_without_lookahead():
    spec = _spec()
    campaign = _campaign(spec)
    initial = _observation(spec, campaign, _optimizer_result())
    prices = {"AAA": 130.0, "BBB": 115.0, "CCC": 100.0, "DDD": 90.0, "EEE": 85.0, "FFF": 80.0}
    rolling_weights = {"AAA": 0.2, "BBB": 0.2, "CCC": 0.2, "DDD": 0.2, "EEE": 0.1, "FFF": 0.1}
    second_result = _optimizer_result(rolling_weights, prices, data_hash="c" * 64)
    second = _observation(
        spec,
        campaign,
        second_result,
        prior=initial,
        as_of="2026-11-27T00:00:00+00:00",
    )
    buy_hold = second["policies"]["buy_and_hold"]
    fixed = second["policies"]["fixed_target"]
    rolling = second["policies"]["rolling_reoptimization"]
    assert buy_hold["action"] == "observe_only"
    assert buy_hold["turnover"] == 0.0
    assert buy_hold["transaction_cost"] == 0.0
    assert fixed["immutable_target"] == initial["policies"]["fixed_target"]["immutable_target"]
    assert fixed["target_weights"] == pytest.approx({ticker: 1 / 6 for ticker in TICKERS})
    assert rolling["target_weights"] == pytest.approx(rolling_weights)
    assert fixed["target_weights"] != rolling["target_weights"]
    assert second["common_prices"] == prices
    for policy in second["policies"].values():
        assert policy["turnover"] <= 0.35 + 1e-10
        assert all(policy["checks"].values())


def test_missing_price_and_nondeterministic_result_create_no_partial_state():
    spec = _spec()
    campaign = _campaign(spec)
    missing = _optimizer_result()
    missing["prices"].pop("FFF")
    with pytest.raises(ValueError, match="Missing frozen-universe"):
        _observation(spec, campaign, missing)

    first = _optimizer_result()
    rerun = copy.deepcopy(first)
    rerun["weights"]["AAA"] += 0.001
    rerun["weights"]["BBB"] -= 0.001
    with pytest.raises(ValueError, match="deterministic rerun"):
        build_comparison_observation(
            campaign,
            spec,
            first,
            rerun,
            as_of_timestamp="2026-08-29T00:00:00+00:00",
        )


def test_failed_observation_is_no_trade_and_preserves_last_complete_state(tmp_path):
    spec = _spec()
    campaign = _campaign(spec)
    ledger = tmp_path / "failure.sqlite3"
    created = create_campaign(ledger, campaign, now="2026-08-29T00:00:00+00:00")
    initial = _observation(
        spec, campaign, _optimizer_result(), as_of=created["campaign"]["created_at"]
    )
    append_observation(ledger, initial, now="2026-08-29T00:01:00+00:00")
    failed = build_failed_comparison_observation(
        campaign,
        spec,
        as_of_timestamp="2026-08-30T00:00:00+00:00",
        error="missing frozen-universe execution prices",
        status="data_missing",
        prior_observation=initial,
    )
    assert failed["policies"] is None
    assert failed["data_provenance"]["no_trade"] is True
    append_observation(ledger, failed, now="2026-08-30T00:01:00+00:00")
    assert latest_complete_observation(ledger, campaign["campaign_id"])[
        "as_of_timestamp"
    ] == initial["as_of_timestamp"]
    assert verify_ledger(ledger)["observations"] == 2


def test_rebalance_waits_for_63_new_trading_observations():
    spec = _spec()
    campaign = _campaign(spec)
    first = _optimizer_result()
    first["market_data_provenance"]["available_through"] = "2026-08-28"
    initial = _observation(spec, campaign, first)
    later = _optimizer_result(data_hash="c" * 64)
    later["_observation_context"]["observation_dates"] = (
        pd.bdate_range("2024-09-16", "2026-09-11").strftime("%Y-%m-%d").tolist()
    )
    with pytest.raises(RebalanceNotDue, match="Rebalance not due"):
        _observation(
            spec,
            campaign,
            later,
            prior=initial,
            as_of="2026-09-12T00:00:00+00:00",
        )


def test_contract_v3_is_append_only_and_mature_pair_only(tmp_path):
    spec = _spec()
    campaign = _campaign(spec)
    ledger = tmp_path / "comparison.sqlite3"
    created = create_campaign(
        ledger,
        campaign,
        now="2026-08-29T00:00:00+00:00",
    )
    observation = _observation(
        spec,
        campaign,
        _optimizer_result(),
        as_of=created["campaign"]["created_at"],
    )
    append_observation(
        ledger,
        observation,
        now="2026-08-29T00:01:00+00:00",
    )
    rows = []
    dates = pd.bdate_range("2026-08-28", periods=64)
    for index, date in enumerate(dates):
        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "prices": {ticker: 100.0 + index * (position + 1) / 100.0 for position, ticker in enumerate(TICKERS)},
        })
    immature = {"status": "complete", "prices": rows[:-1], "data_provenance": {"source": "fixture"}}
    immature["data_sha256"] = outcome_price_sha256(immature["prices"])
    assert record_outcome(
        ledger,
        campaign["campaign_id"],
        observation["as_of_timestamp"],
        immature,
        now="2026-11-30T00:00:00+00:00",
    )["status"] == "immature"
    outcome = {"status": "complete", "prices": rows, "data_provenance": {"source": "fixture"}}
    outcome["data_sha256"] = outcome_price_sha256(outcome["prices"])
    recorded = record_outcome(
        ledger,
        campaign["campaign_id"],
        observation["as_of_timestamp"],
        outcome,
        now="2026-12-01T00:00:00+00:00",
    )
    assert set(recorded["policy_metrics"]) == set(spec["policies"])
    assert all(
        metrics["daily_returns"][min(metrics["daily_returns"])]
        < (1.0001 - 1.0)
        for metrics in recorded["policy_metrics"].values()
    )
    evaluation = evaluate_campaign(ledger, campaign["campaign_id"])
    assert evaluation["status"] == "forward_pending"
    assert evaluation["mature_paired_observation_count"] == 1
    assert evaluation["no_automatic_promotion"] is True
    assert verify_ledger(ledger)["outcome_attempts"] == 1


def test_cli_help_explains_forward_restriction():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "gmv_policy_comparison.py"), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    help_text = " ".join(result.stdout.lower().split())
    assert "historical evidence and backfill are forbidden" in help_text
    assert "no command promotes production automatically" in help_text


def test_live_collection_discovers_then_locks_exact_504_rows():
    spec = _spec()
    dates = pd.bdate_range("2024-01-02", periods=510).strftime("%Y-%m-%d").tolist()
    calls = []

    def fake_optimizer(**kwargs):
        calls.append(kwargs)
        result = _optimizer_result(data_hash="d" * 64)
        if len(calls) == 1:
            result["market_data_provenance"]["row_count"] = 510
            result["_observation_context"]["observation_dates"] = dates
        else:
            result["_observation_context"]["observation_dates"] = dates[-504:]
        return result

    first, second = collect_live_comparison_inputs(
        spec,
        as_of_timestamp="2026-08-29T00:00:00+00:00",
        optimizer=fake_optimizer,
    )
    assert len(calls) == 3
    assert calls[1]["start_date"] == dates[-504]
    assert calls[2]["start_date"] == dates[-504]
    assert first == second


def test_fixture_cli_is_offline_and_deterministic(tmp_path):
    spec_path = tmp_path / "spec.json"
    input_path = tmp_path / "fixture.json"
    output_path = tmp_path / "result.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")
    first = _optimizer_result()
    second = _optimizer_result(
        {"AAA": 0.2, "BBB": 0.2, "CCC": 0.2, "DDD": 0.2, "EEE": 0.1, "FFF": 0.1},
        {"AAA": 110.0, "BBB": 105.0, "CCC": 102.0, "DDD": 98.0, "EEE": 95.0, "FFF": 90.0},
        data_hash="e" * 64,
    )
    input_path.write_text(json.dumps({
        "campaign_id": "offline-fixture",
        "observations": [
            {
                "as_of_timestamp": "2026-08-29T00:00:00+00:00",
                "optimizer_result": first,
                "rerun_result": first,
            },
            {
                "as_of_timestamp": "2026-11-27T00:00:00+00:00",
                "optimizer_result": second,
                "rerun_result": second,
            },
        ],
    }), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "gmv_policy_comparison.py"),
            "fixture-run",
            "--spec", str(spec_path),
            "--input", str(input_path),
            "--output", str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "diagnostic_fixture_only"
    assert payload["deterministic_rerun"] is True
    assert payload["no_automatic_promotion"] is True
