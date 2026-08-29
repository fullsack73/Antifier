"""Append-only calendar-forward shadow observation and outcome ledger."""

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_constraints import constraint_diagnostics, prepare_constraint_model
from portfolio_statistics import holm_bonferroni, paired_block_bootstrap
from research_split import canonical_json_digest, load_research_policy


SCHEMA_VERSION = 1
OBSERVATION_CONTRACT_VERSION = 2
POLICY_COMPARISON_CONTRACT_VERSION = 3
OBSERVATION_STATUSES = {
    "complete",
    "partial",
    "network_failure",
    "data_missing",
    "calculation_failure",
}
FAILED_OBSERVATION_STATUSES = {
    "network_failure",
    "data_missing",
    "calculation_failure",
}
OUTCOME_ATTEMPT_STATUSES = {
    "immature",
    "network_failure",
    "data_missing",
    "partial_coverage",
}


def _utc_now():
    return datetime.now(timezone.utc)


def _timestamp(value, field):
    parsed = pd.Timestamp(value)
    if pd.isna(parsed) or parsed.tz is None:
        raise ValueError(f"{field} must be a timezone-aware timestamp")
    return parsed.tz_convert("UTC")


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(value):
    return json.loads(value) if isinstance(value, str) else dict(value)


def _require_sha(value, field):
    value = str(value or "").strip().lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a SHA-256")
    return value


def _connect(path):
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(ledger_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_ledger(path):
    """Create the v1 schema and database-level append-only guards."""
    with _connect(path) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS ledger_meta (
                schema_version INTEGER NOT NULL
            );
            INSERT INTO ledger_meta(schema_version)
            SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM ledger_meta);

            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                spec_sha256 TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS observations (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                as_of_timestamp TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_record_sha256 TEXT,
                record_sha256 TEXT NOT NULL UNIQUE,
                UNIQUE(campaign_id, as_of_timestamp),
                FOREIGN KEY(campaign_id) REFERENCES campaigns(campaign_id)
            );
            CREATE TABLE IF NOT EXISTS outcome_attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                as_of_timestamp TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(campaign_id)
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                as_of_timestamp TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_record_sha256 TEXT,
                record_sha256 TEXT NOT NULL UNIQUE,
                UNIQUE(campaign_id, as_of_timestamp),
                FOREIGN KEY(campaign_id, as_of_timestamp)
                    REFERENCES observations(campaign_id, as_of_timestamp)
            );
        """)
        for table in ("campaigns", "observations", "outcome_attempts", "outcomes"):
            connection.executescript(f"""
                CREATE TRIGGER IF NOT EXISTS {table}_no_update
                BEFORE UPDATE ON {table}
                BEGIN SELECT RAISE(ABORT, 'append-only table'); END;
                CREATE TRIGGER IF NOT EXISTS {table}_no_delete
                BEFORE DELETE ON {table}
                BEGIN SELECT RAISE(ABORT, 'append-only table'); END;
            """)
        version = connection.execute(
            "SELECT schema_version FROM ledger_meta"
        ).fetchone()[0]
        if version != SCHEMA_VERSION:
            raise ValueError("Unsupported shadow ledger schema_version")


def normalize_campaign_spec(spec, *, now=None, policy_path=None):
    policy = load_research_policy(policy_path) if policy_path else load_research_policy()
    payload = dict(spec or {})
    campaign_id = str(payload.get("campaign_id", "")).strip()
    if not campaign_id:
        raise ValueError("Shadow campaign requires campaign_id")
    created = _timestamp(now or _utc_now(), "created_at")
    lane = str(payload.get("lane", "")).strip().lower()
    if lane not in policy["lanes"]:
        raise ValueError("Shadow campaign requires a valid research lane")
    if payload.get("evidence_scope", "calendar_forward_shadow") != "calendar_forward_shadow":
        raise ValueError("Shadow campaign evidence_scope must be calendar_forward_shadow")
    horizon = int(payload.get("horizon_observations", 0))
    if horizon <= 0:
        raise ValueError("horizon_observations must be positive")
    coverage = float(payload.get("minimum_coverage", 0.80))
    if not 0.0 < coverage <= 1.0:
        raise ValueError("minimum_coverage must be in (0, 1]")
    baseline = dict(payload.get("baseline_specification") or {})
    required_baseline = policy["production_baseline"]
    for field, value in required_baseline.items():
        if baseline.get(field) != value:
            raise ValueError(
                f"Shadow baseline specification mismatch for {field}"
            )
    candidate = payload.get("candidate_specification")
    if candidate is not None and not isinstance(candidate, dict):
        raise ValueError("candidate_specification must be null or an object")
    if candidate is not None:
        if not str(candidate.get("candidate_id", "")).strip():
            raise ValueError("candidate_specification requires candidate_id")
        if lane == "alpha":
            if candidate.get("signal_gate_status") != "passed":
                raise ValueError(
                    "Alpha candidate requires a passed signal-only gate"
                )
            _require_sha(
                candidate.get("signal_gate_artifact_sha256"),
                "candidate.signal_gate_artifact_sha256",
            )
        if lane == "risk":
            allowed = set(policy["lanes"]["risk"]["allowed_primary_endpoints"])
            if candidate.get("primary_endpoint") not in allowed:
                raise ValueError(
                    "Risk candidate must preregister a supported primary_endpoint"
                )
    comparison = payload.get("comparison_specification")
    if comparison is not None:
        if candidate is not None:
            raise ValueError("Policy comparison cannot register a separate candidate")
        if lane != "risk":
            raise ValueError("GMV policy comparison must use the risk lane")
        if comparison.get("policies") != [
            "buy_and_hold",
            "fixed_target",
            "rolling_reoptimization",
        ]:
            raise ValueError("GMV policy comparison requires all three policies")
        _require_sha(
            comparison.get("comparison_spec_sha256"),
            "comparison_specification.comparison_spec_sha256",
        )
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "created_at": created.isoformat(),
        "timezone": str(payload.get("timezone", "UTC")).strip() or "UTC",
        "lane": lane,
        "evidence_scope": "calendar_forward_shadow",
        "horizon_observations": horizon,
        "minimum_coverage": coverage,
        "universe_policy": dict(payload.get("universe_policy") or {}),
        "baseline_specification": baseline,
        "baseline_specification_sha256": canonical_json_digest(baseline),
        "candidate_specification": candidate,
        "candidate_specification_sha256": (
            None if candidate is None else canonical_json_digest(candidate)
        ),
        "execution_conditions": dict(payload.get("execution_conditions") or {}),
        "policy_id": policy["policy_id"],
        "policy_sha256": policy["policy_sha256"],
        "production_auto_promotion": False,
        "manual_review_only": True,
    }
    if comparison is not None:
        normalized.update({
            "comparison_specification": comparison,
            "comparison_specification_sha256": canonical_json_digest(comparison),
        })
    normalized["universe_policy_sha256"] = canonical_json_digest(
        normalized["universe_policy"]
    )
    return normalized


def create_campaign(path, spec, *, now=None, policy_path=None):
    initialize_ledger(path)
    with _connect(path) as connection:
        existing = connection.execute(
            "SELECT created_at, spec_sha256 FROM campaigns WHERE campaign_id = ?",
            (str(dict(spec or {}).get("campaign_id", "")).strip(),),
        ).fetchone()
        normalized = normalize_campaign_spec(
            spec,
            now=existing["created_at"] if existing else now,
            policy_path=policy_path,
        )
        spec_json = _canonical_json(normalized)
        spec_hash = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
        if existing:
            if existing["spec_sha256"] == spec_hash:
                return {"status": "duplicate_detected", "campaign_sha256": spec_hash}
            raise ValueError("Campaign ID already exists with a different specification")
        connection.execute(
            "INSERT INTO campaigns VALUES (?, ?, ?, ?)",
            (
                normalized["campaign_id"],
                normalized["created_at"],
                spec_json,
                spec_hash,
            ),
        )
    return {"status": "created", "campaign_sha256": spec_hash, "campaign": normalized}


def _campaign(connection, campaign_id):
    row = connection.execute(
        "SELECT * FROM campaigns WHERE campaign_id = ?",
        (campaign_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown shadow campaign: {campaign_id}")
    return json.loads(row["spec_json"])


def get_campaign(path, campaign_id):
    """Return one immutable campaign specification."""
    initialize_ledger(path)
    with _connect(path) as connection:
        return _campaign(connection, campaign_id)


def _validate_baseline(payload, campaign, *, contract_version=1, eligible=None):
    baseline = dict(payload or {})
    expected = campaign["baseline_specification"]
    for field in ("optimization_method", "forecast_method_effective", "covariance_estimator"):
        if baseline.get(field) != expected[field]:
            raise ValueError(f"Observation baseline mismatch for {field}")
    if baseline.get("forecast_bypassed") is not True:
        raise ValueError("Production shadow baseline must bypass forecasts")
    signal = dict(baseline.get("signal") or {})
    if signal.get("status") != "no_view":
        raise ValueError("RISK_ONLY baseline signal must be explicit no_view")
    weights = {str(key): float(value) for key, value in dict(baseline.get("weights") or {}).items()}
    cash = float(baseline.get("cash_weight", 0.0))
    if any(not math.isfinite(value) or value < -1e-12 for value in weights.values()):
        raise ValueError("Baseline weights must be finite and nonnegative")
    if not math.isfinite(cash) or cash < -1e-12:
        raise ValueError("Baseline cash_weight must be finite and nonnegative")
    if abs(sum(weights.values()) + cash - 1.0) > 1e-6:
        raise ValueError("Baseline weights and cash must sum to one")
    _validate_risk_forecast(baseline.get("risk_forecast"), "Baseline")
    if contract_version >= OBSERVATION_CONTRACT_VERSION:
        baseline["execution"] = _validate_execution_v2(
            baseline.get("execution"),
            campaign,
            "Baseline",
            weights,
            cash,
            eligible or [],
        )
    else:
        _validate_execution(baseline.get("execution"), campaign, "Baseline")
    return baseline


def _validate_risk_forecast(payload, owner):
    forecast = dict(payload or {})
    volatility = float(forecast.get("annual_volatility", float("nan")))
    if not math.isfinite(volatility) or volatility < 0.0:
        raise ValueError(f"{owner} risk forecast must be finite and nonnegative")


def _validate_execution(payload, campaign, owner):
    execution = dict(payload or {})
    for field in (
        "invariants_passed",
        "turnover_identity_passed",
        "transaction_cost_identity_passed",
        "constraints_satisfied",
    ):
        if execution.get(field) is not True:
            raise ValueError(f"{owner} execution requires {field}=true")
    turnover = float(execution.get("turnover", float("nan")))
    cost = float(execution.get("transaction_cost", float("nan")))
    coverage = float(execution.get("price_coverage", float("nan")))
    if not math.isfinite(turnover) or turnover < 0.0:
        raise ValueError(f"{owner} turnover must be finite and nonnegative")
    if not math.isfinite(cost) or cost < 0.0:
        raise ValueError(
            f"{owner} transaction_cost must be finite and nonnegative"
        )
    if not math.isfinite(coverage) or not 0.0 <= coverage <= 1.0:
        raise ValueError(f"{owner} price_coverage must be in [0, 1]")
    cost_bps = float(campaign["execution_conditions"].get(
        "transaction_cost_bps",
        0.0,
    ))
    expected_cost = turnover * cost_bps / 10_000.0
    if abs(cost - expected_cost) > 1e-10:
        raise ValueError(f"{owner} transaction cost identity failed")


def _nonnegative_mapping(value, field):
    mapping = {str(key): float(item) for key, item in dict(value or {}).items()}
    if any(not math.isfinite(item) or item < -1e-12 for item in mapping.values()):
        raise ValueError(f"{field} must contain finite nonnegative values")
    return mapping


def _validate_execution_v2(payload, campaign, owner, weights, cash, eligible):
    """Recompute execution, coverage, constraint, and rerun checks from raw values."""
    execution = dict(payload or {})
    reference = float(execution.get("reference_wealth", float("nan")))
    post_cost = float(execution.get("post_cost_wealth", float("nan")))
    cost = float(execution.get("transaction_cost", float("nan")))
    rate = float(execution.get("transaction_cost_rate", float("nan")))
    current = _nonnegative_mapping(execution.get("current_notionals"), f"{owner} current_notionals")
    executed = _nonnegative_mapping(execution.get("executed_notionals"), f"{owner} executed_notionals")
    executed_cash = float(execution.get("executed_cash", float("nan")))
    if not math.isfinite(reference) or reference <= 0.0:
        raise ValueError(f"{owner} reference_wealth must be finite and positive")
    if not math.isfinite(post_cost) or post_cost <= 0.0:
        raise ValueError(f"{owner} post_cost_wealth must be finite and positive")
    if not math.isfinite(executed_cash) or executed_cash < -1e-12:
        raise ValueError(f"{owner} executed_cash must be finite and nonnegative")
    tickers = set(current) | set(executed)
    traded = float(sum(abs(executed.get(t, 0.0) - current.get(t, 0.0)) for t in tickers))
    turnover = traded / reference
    expected_rate = float(
        campaign["execution_conditions"].get("transaction_cost_bps", 0.0)
    ) / 10_000.0
    checks = {
        "traded_notional_identity": abs(float(execution.get("traded_notional", float("nan"))) - traded) <= 1e-10,
        "turnover_identity": abs(float(execution.get("turnover", float("nan"))) - turnover) <= 1e-10,
        "cost_rate_identity": abs(rate - expected_rate) <= 1e-12,
        "transaction_cost_identity": abs(cost - traded * expected_rate) <= 1e-10,
        "wealth_identity": abs(post_cost - (reference - cost)) <= 1e-10,
        "post_cost_holdings_identity": abs(sum(executed.values()) + executed_cash - post_cost) <= 1e-10,
        "weight_cash_identity": abs(sum(weights.values()) + cash - 1.0) <= 1e-10,
        "executed_weight_identity": all(
            abs(executed.get(ticker, 0.0) / post_cost - weights.get(ticker, 0.0)) <= 1e-10
            for ticker in set(executed) | set(weights)
        ) and abs(executed_cash / post_cost - cash) <= 1e-10,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"{owner} execution identity failed: {', '.join(failed)}")

    prices = {str(key): float(value) for key, value in dict(execution.get("prices") or {}).items()}
    computed_missing = sorted(
        ticker for ticker in eligible
        if ticker not in prices or not math.isfinite(prices[ticker]) or prices[ticker] <= 0.0
    )
    supplied_missing = sorted(set(map(str, execution.get("missing_price_tickers") or [])))
    if supplied_missing != computed_missing:
        raise ValueError(f"{owner} missing-price ticker identity failed")
    computed_coverage = 1.0 if not eligible else (len(eligible) - len(computed_missing)) / len(eligible)
    if abs(float(execution.get("price_coverage", float("nan"))) - computed_coverage) > 1e-12:
        raise ValueError(f"{owner} price coverage identity failed")

    constraint_spec = dict(execution.get("constraint_specification") or {})
    model = prepare_constraint_model(
        eligible,
        max_asset_weight=constraint_spec.get("max_asset_weight"),
        asset_constraints=constraint_spec.get("asset_constraints"),
        group_constraints=constraint_spec.get("group_constraints"),
        classifications=constraint_spec.get("classifications"),
        min_holding_weight=constraint_spec.get("min_holding_weight", 0.0),
    )
    constraints = constraint_diagnostics(weights, model, cash_weight=cash)
    if not constraints["all_satisfied"]:
        raise ValueError(f"{owner} constraint compliance failed")
    rerun = dict(execution.get("deterministic_rerun") or {})
    first_result_hash = _require_sha(
        rerun.get("first_result_sha256"),
        f"{owner} first_result_sha256",
    )
    rerun_result_hash = _require_sha(
        rerun.get("rerun_result_sha256"),
        f"{owner} rerun_result_sha256",
    )
    max_weight_difference = float(
        rerun.get("max_weight_difference", float("nan"))
    )
    if (
        first_result_hash != rerun_result_hash
        or not math.isfinite(max_weight_difference)
        or max_weight_difference > 1e-12
    ):
        raise ValueError(f"{owner} deterministic rerun failed")
    rerun.update({
        "passed": True,
        "same_data_sha256": True,
        "max_weight_difference": max_weight_difference,
    })
    execution.update({
        "traded_notional": traded,
        "turnover": turnover,
        "transaction_cost_rate": expected_rate,
        "transaction_cost": traded * expected_rate,
        "price_coverage": computed_coverage,
        "missing_price_tickers": computed_missing,
        "constraint_diagnostics": constraints,
        "deterministic_rerun": rerun,
        "checks": checks,
    })
    return execution


def _validate_candidate(
    payload,
    campaign,
    *,
    contract_version=1,
    eligible=None,
):
    candidate = dict(payload or {})
    if candidate.get("specification_sha256") != campaign[
        "candidate_specification_sha256"
    ]:
        raise ValueError("Candidate specification hash changed after campaign creation")
    for field in ("signal", "weights", "risk_forecast", "execution"):
        if not isinstance(candidate.get(field), dict):
            raise ValueError(f"Candidate observation requires {field}")
    weights = {str(key): float(value) for key, value in candidate["weights"].items()}
    cash = float(candidate.get("cash_weight", 0.0))
    if any(not math.isfinite(value) or value < -1e-12 for value in weights.values()):
        raise ValueError("Candidate weights must be finite and nonnegative")
    if not math.isfinite(cash) or cash < -1e-12:
        raise ValueError("Candidate cash_weight must be finite and nonnegative")
    if abs(sum(weights.values()) + cash - 1.0) > 1e-6:
        raise ValueError("Candidate weights and cash must sum to one")
    _validate_risk_forecast(candidate["risk_forecast"], "Candidate")
    if contract_version >= OBSERVATION_CONTRACT_VERSION:
        candidate["execution"] = _validate_execution_v2(
            candidate["execution"],
            campaign,
            "Candidate",
            weights,
            cash,
            eligible or [],
        )
    else:
        _validate_execution(candidate["execution"], campaign, "Candidate")
    return candidate


def _validate_comparison_policies(payload, campaign, eligible):
    policies = dict(payload or {})
    required = {"buy_and_hold", "fixed_target", "rolling_reoptimization"}
    if set(policies) != required:
        raise ValueError("Comparison observation requires exactly three policies")
    common_prices = None
    for policy_id in sorted(required):
        policy = dict(policies[policy_id] or {})
        if policy.get("policy_id") != policy_id:
            raise ValueError(f"Comparison policy identity mismatch: {policy_id}")
        prices = _nonnegative_mapping(policy.get("prices"), f"{policy_id} prices")
        if set(prices) != set(eligible) or any(value <= 0.0 for value in prices.values()):
            raise ValueError(f"{policy_id} requires full eligible-universe prices")
        if common_prices is None:
            common_prices = prices
        elif prices != common_prices:
            raise ValueError("Comparison policies must use identical prices")
        quantities = _nonnegative_mapping(
            policy.get("executed_quantities"),
            f"{policy_id} executed_quantities",
        )
        executed = _nonnegative_mapping(
            policy.get("executed_notionals"),
            f"{policy_id} executed_notionals",
        )
        current = _nonnegative_mapping(
            policy.get("pre_trade_notionals"),
            f"{policy_id} pre_trade_notionals",
        )
        cash = float(policy.get("executed_cash", float("nan")))
        pre_cash = float(policy.get("pre_trade_cash", float("nan")))
        pre_wealth = float(policy.get("pre_trade_wealth", float("nan")))
        post_wealth = float(policy.get("post_cost_wealth", float("nan")))
        cost = float(policy.get("transaction_cost", float("nan")))
        traded = sum(
            abs(executed.get(ticker, 0.0) - current.get(ticker, 0.0))
            for ticker in set(executed) | set(current)
        )
        rate = float(campaign["execution_conditions"].get("transaction_cost_bps", 0.0)) / 10000.0
        checks = {
            "pre_wealth": abs(sum(current.values()) + pre_cash - pre_wealth) <= 1e-8,
            "quantity_value": all(
                abs(quantities.get(ticker, 0.0) * prices[ticker] - executed.get(ticker, 0.0)) <= 1e-8
                for ticker in eligible
            ),
            "traded_notional": abs(float(policy.get("gross_traded_notional", float("nan"))) - traded) <= 1e-8,
            "turnover": abs(float(policy.get("turnover", float("nan"))) - traded / pre_wealth) <= 1e-10,
            "cost": abs(cost - traded * rate) <= 1e-8,
            "post_wealth": abs(post_wealth - (pre_wealth - cost)) <= 1e-8,
            "post_holdings": abs(sum(executed.values()) + cash - post_wealth) <= 1e-8,
        }
        weights = _nonnegative_mapping(policy.get("weights"), f"{policy_id} weights")
        cash_weight = float(policy.get("cash_weight", float("nan")))
        checks["weight_cash"] = abs(sum(weights.values()) + cash_weight - 1.0) <= 1e-10
        checks["executed_weights"] = all(
            abs(executed.get(ticker, 0.0) / post_wealth - weights.get(ticker, 0.0)) <= 1e-10
            for ticker in eligible
        )
        if policy_id == "buy_and_hold" and policy.get("action") != "initial_shared_allocation":
            checks["buy_and_hold_no_trade"] = traded <= 1e-12 and cost <= 1e-12
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise ValueError(f"{policy_id} comparison identity failed: {', '.join(failed)}")
        forecast = dict(policy.get("risk_forecast") or {})
        _validate_risk_forecast(forecast, policy_id)
        policy["checks"] = {**dict(policy.get("checks") or {}), **checks}
        policies[policy_id] = policy
    return policies


def latest_complete_observation(path, campaign_id):
    """Return the latest complete append-only state for a campaign."""
    initialize_ledger(path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM observations WHERE campaign_id = ? "
            "AND status = 'complete' ORDER BY as_of_timestamp DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
    return None if row is None else json.loads(row["payload_json"])


def append_observation(path, observation, *, now=None):
    initialize_ledger(path)
    payload = dict(observation or {})
    campaign_id = str(payload.get("campaign_id", "")).strip()
    recorded = _timestamp(now or _utc_now(), "recorded_at")
    as_of = _timestamp(payload.get("as_of_timestamp"), "as_of_timestamp")
    status = str(payload.get("status", "")).strip().lower()
    contract_version = int(payload.get("contract_version", 1))
    if contract_version not in {
        1,
        OBSERVATION_CONTRACT_VERSION,
        POLICY_COMPARISON_CONTRACT_VERSION,
    }:
        raise ValueError("Unsupported shadow observation contract_version")
    if status not in OBSERVATION_STATUSES:
        raise ValueError("Unsupported shadow observation status")
    with _connect(path) as connection:
        campaign = _campaign(connection, campaign_id)
        comparison_campaign = campaign.get("comparison_specification") is not None
        if contract_version == POLICY_COMPARISON_CONTRACT_VERSION and not comparison_campaign:
            raise ValueError("Contract v3 requires a registered policy comparison")
        if comparison_campaign and contract_version != POLICY_COMPARISON_CONTRACT_VERSION:
            raise ValueError("Registered policy comparison requires contract v3")
        if as_of < _timestamp(campaign["created_at"], "campaign.created_at"):
            raise ValueError("Historical backfill before campaign creation is forbidden")
        if as_of > recorded:
            raise ValueError("Observation as-of timestamp cannot be in the future")
        latest = connection.execute(
            "SELECT as_of_timestamp FROM observations WHERE campaign_id = ? "
            "ORDER BY as_of_timestamp DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
        requested = sorted(set(map(str, payload.get("requested_universe") or [])))
        eligible = sorted(set(map(str, payload.get("eligible_universe") or [])))
        if not requested:
            raise ValueError("Observation requires requested_universe")
        if not set(eligible).issubset(requested):
            raise ValueError("eligible_universe must be a requested-universe subset")
        provenance = dict(payload.get("data_provenance") or {})
        if not provenance:
            raise ValueError("Observation requires data_provenance")
        coverage = float(provenance.get("coverage", float("nan")))
        if not math.isfinite(coverage) or not 0.0 <= coverage <= 1.0:
            raise ValueError("data_provenance.coverage must be in [0, 1]")
        if status not in FAILED_OBSERVATION_STATUSES:
            _require_sha(
                provenance.get("data_sha256"),
                "data_provenance.data_sha256",
            )
        if contract_version >= OBSERVATION_CONTRACT_VERSION:
            computed_missing = sorted(set(requested) - set(eligible))
            computed_coverage = len(eligible) / len(requested)
            if abs(coverage - computed_coverage) > 1e-12:
                raise ValueError("data_provenance coverage identity failed")
            if sorted(set(map(str, provenance.get("missing_tickers") or []))) != computed_missing:
                raise ValueError("data_provenance missing-ticker identity failed")
        if status == "complete" and coverage < campaign["minimum_coverage"]:
            raise ValueError(
                "Complete observation is below campaign minimum coverage"
            )
        candidate = payload.get("candidate")
        if comparison_campaign:
            if payload.get("comparison_spec_sha256") != campaign[
                "comparison_specification"
            ]["comparison_spec_sha256"]:
                raise ValueError("Comparison specification hash changed")
            if status not in FAILED_OBSERVATION_STATUSES:
                payload["policies"] = _validate_comparison_policies(
                    payload.get("policies"),
                    campaign,
                    eligible,
                )
                if payload.get("baseline") is not None or candidate is not None:
                    raise ValueError("Comparison observation cannot contain baseline/candidate payloads")
            elif payload.get("policies") is not None:
                raise ValueError("Failed comparison observations cannot contain policy outputs")
        elif payload.get("policies") is not None:
            raise ValueError("Policy outputs require a comparison campaign")
        if campaign["candidate_specification"] is None and candidate is not None:
            raise ValueError("Candidate payload is forbidden for a baseline-only campaign")
        if status not in FAILED_OBSERVATION_STATUSES and not comparison_campaign:
            payload["baseline"] = _validate_baseline(
                payload.get("baseline"),
                campaign,
                contract_version=contract_version,
                eligible=eligible,
            )
            if (
                contract_version >= OBSERVATION_CONTRACT_VERSION
                and status == "complete"
                and payload["baseline"]["execution"]["price_coverage"] < 1.0
            ):
                raise ValueError("Complete observation requires full execution price coverage")
            if campaign["candidate_specification"] is not None and candidate is None:
                raise ValueError("Registered candidate observation payload is missing")
            if candidate is not None:
                payload["candidate"] = _validate_candidate(
                    candidate,
                    campaign,
                    contract_version=contract_version,
                    eligible=eligible,
                )
            for owner in ("baseline", "candidate"):
                output = payload.get(owner)
                if output is None:
                    continue
                weighted = {
                    str(ticker)
                    for ticker, weight in output["weights"].items()
                    if abs(float(weight)) > 1e-12
                }
                if not weighted.issubset(eligible):
                    raise ValueError(
                        f"{owner} weights must stay inside eligible_universe"
                    )
        elif not comparison_campaign and (
            payload.get("baseline") is not None or candidate is not None
        ):
            raise ValueError("Failed observations cannot contain model outputs")
        normalized = {
            **payload,
            "schema_version": SCHEMA_VERSION,
            "contract_version": contract_version,
            "campaign_id": campaign_id,
            "as_of_timestamp": as_of.isoformat(),
            "recorded_at": recorded.isoformat(),
            "status": status,
            "requested_universe": requested,
            "eligible_universe": eligible,
            "requested_universe_sha256": canonical_json_digest(requested),
            "eligible_universe_sha256": canonical_json_digest(eligible),
            "production_auto_promotion": False,
        }
        payload_json = _canonical_json(normalized)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        existing = connection.execute(
            "SELECT payload_json, payload_sha256 FROM observations "
            "WHERE campaign_id = ? AND as_of_timestamp = ?",
            (campaign_id, as_of.isoformat()),
        ).fetchone()
        if existing:
            previous_payload = json.loads(existing["payload_json"])
            previous_payload.pop("recorded_at", None)
            previous_payload.setdefault("contract_version", 1)
            current_payload = dict(normalized)
            current_payload.pop("recorded_at", None)
            if previous_payload == current_payload:
                return {
                    "status": "duplicate_detected",
                    "payload_sha256": existing["payload_sha256"],
                }
            raise ValueError("Conflicting duplicate observation detected")
        if latest and as_of <= _timestamp(latest["as_of_timestamp"], "latest as-of"):
            raise ValueError("Past-date observation backfill is forbidden")
        previous = connection.execute(
            "SELECT record_sha256 FROM observations "
            "ORDER BY observation_id DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["record_sha256"] if previous else None
        record_hash = canonical_json_digest({
            "payload_sha256": payload_hash,
            "previous_record_sha256": previous_hash,
        })
        connection.execute(
            "INSERT INTO observations(campaign_id, as_of_timestamp, recorded_at, "
            "status, payload_json, payload_sha256, previous_record_sha256, "
            "record_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                campaign_id,
                as_of.isoformat(),
                recorded.isoformat(),
                status,
                payload_json,
                payload_hash,
                previous_hash,
                record_hash,
            ),
        )
    return {"status": "recorded", "payload_sha256": payload_hash, "record_sha256": record_hash}


def _append_outcome_attempt(connection, campaign_id, as_of, status, details, now):
    connection.execute(
        "INSERT INTO outcome_attempts(campaign_id, as_of_timestamp, attempted_at, "
        "status, details_json) VALUES (?, ?, ?, ?, ?)",
        (campaign_id, as_of.isoformat(), now.isoformat(), status, _canonical_json(details)),
    )


def _price_frame(rows):
    records = []
    for row in rows or []:
        date = pd.Timestamp(row.get("date"))
        for ticker, value in dict(row.get("prices") or {}).items():
            records.append({"date": date, "ticker": str(ticker), "price": value})
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records).pivot(index="date", columns="ticker", values="price")
    return frame.sort_index().apply(pd.to_numeric, errors="coerce")


def canonical_outcome_price_sha256(frame):
    """Hash the ordered outcome price panel used for maturity accounting."""
    panel = pd.DataFrame(frame).copy()
    panel.columns = list(map(str, panel.columns))
    panel.index = pd.to_datetime(panel.index)
    if panel.index.tz is not None:
        panel.index = panel.index.tz_convert("UTC").tz_localize(None)
    panel = panel.sort_index().reindex(sorted(panel.columns), axis=1)
    payload = []
    for timestamp, row in panel.iterrows():
        payload.append({
            "date": pd.Timestamp(timestamp).isoformat(),
            "prices": {
                ticker: (float(value).hex() if math.isfinite(float(value)) else "nan")
                for ticker, value in row.items()
            },
        })
    return canonical_json_digest(payload)


def outcome_price_sha256(rows):
    """Return the canonical hash expected by a v2 realized-outcome payload."""
    return canonical_outcome_price_sha256(_price_frame(rows))


def _portfolio_outcome(frame, as_of, horizon, baseline):
    before = frame.loc[frame.index <= as_of]
    after = frame.loc[frame.index > as_of]
    if before.empty or len(after.index.unique()) < horizon:
        return None, "immature"
    selected = pd.concat([before.tail(1), after.iloc[:horizon]])
    weights = pd.Series(baseline["weights"], dtype=float)
    required = list(weights[weights.abs() > 1e-12].index)
    prices = selected.reindex(columns=required)
    valid_tickers = (prices.notna() & prices.gt(0.0)).all(axis=0)
    coverage = float(valid_tickers.mean()) if required else 1.0
    missing_tickers = sorted(ticker for ticker in required if not valid_tickers[ticker])
    if missing_tickers:
        return {
            "coverage": coverage,
            "missing_tickers": missing_tickers,
            "available_horizon_observations": int(len(after.index.unique())),
        }, "partial_coverage"
    shares = weights.reindex(required) / prices.iloc[0]
    cash = float(baseline.get("cash_weight", 0.0))
    values = prices.mul(shares, axis=1).sum(axis=1) + cash
    returns = values.pct_change().dropna()
    annual_volatility = float(returns.std(ddof=0) * np.sqrt(252))
    predicted = baseline.get("risk_forecast", {}).get("annual_volatility")
    risk_error = (
        None if predicted is None else float(annual_volatility - float(predicted))
    )
    ratio = (
        None
        if predicted is None or float(predicted) <= 1e-12
        else float(annual_volatility / float(predicted))
    )
    execution = dict(baseline.get("execution") or {})
    reference_wealth = float(execution.get("reference_wealth", 1.0))
    post_cost_wealth = float(execution.get("post_cost_wealth", reference_wealth))
    post_cost_factor = post_cost_wealth / reference_wealth
    gross_market_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    net_return = float(post_cost_factor * (1.0 + gross_market_return) - 1.0)
    net_values = values / values.iloc[0] * post_cost_factor
    running_peak = np.maximum.accumulate(
        np.concatenate(([1.0], net_values.to_numpy(dtype=float)))
    )
    net_drawdown = (
        np.concatenate(([1.0], net_values.to_numpy(dtype=float)))
        / running_peak
        - 1.0
    )
    return {
        "coverage": coverage,
        "missing_tickers": [],
        "horizon_start": selected.index[1].strftime("%Y-%m-%d"),
        "horizon_end": selected.index[-1].strftime("%Y-%m-%d"),
        "horizon_observations": int(horizon),
        "gross_market_return": gross_market_return,
        "realized_return": net_return,
        "transaction_cost_drag": float(1.0 - post_cost_factor),
        "realized_volatility": annual_volatility,
        "max_drawdown": float(net_drawdown.min()),
        "risk_forecast_error": risk_error,
        "risk_forecast_mae": None if risk_error is None else abs(risk_error),
        "risk_forecast_ratio": ratio,
    }, "complete"


def _comparison_policy_outcome(frame, as_of, horizon, policy, risk_free_rate):
    before = frame.loc[frame.index <= as_of]
    after = frame.loc[frame.index > as_of]
    if before.empty or len(after.index.unique()) < horizon:
        return None, "immature"
    selected = pd.concat([before.tail(1), after.iloc[:horizon]])
    quantities = pd.Series(policy["executed_quantities"], dtype=float)
    required = sorted(quantities[quantities.abs() > 1e-12].index)
    prices = selected.reindex(columns=required)
    valid = (prices.notna() & prices.gt(0.0)).all(axis=0)
    missing = sorted(ticker for ticker in required if not valid[ticker])
    if missing:
        return {
            "coverage": float(valid.mean()) if required else 1.0,
            "missing_tickers": missing,
        }, "partial_coverage"
    cash = float(policy.get("executed_cash", 0.0))
    daily_rate = (1.0 + float(risk_free_rate)) ** (1.0 / 252.0) - 1.0
    cash_path = cash * (1.0 + daily_rate) ** np.arange(len(selected))
    values = prices.mul(quantities.reindex(required), axis=1).sum(axis=1) + cash_path
    returns = values.pct_change().dropna()
    volatility = float(returns.std(ddof=0) * np.sqrt(252))
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    years = max(len(returns) / 252.0, 1.0 / 252.0)
    cagr = float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0)
    excess = float(returns.mean() * 252 - risk_free_rate)
    sharpe = None if volatility <= 1e-12 else float(excess / volatility)
    drawdown = values / values.cummax() - 1.0
    predicted = float(policy["risk_forecast"]["annual_volatility"])
    return {
        "coverage": 1.0,
        "missing_tickers": [],
        "horizon_start": selected.index[1].strftime("%Y-%m-%d"),
        "horizon_end": selected.index[-1].strftime("%Y-%m-%d"),
        "horizon_observations": int(horizon),
        "net_total_return": total_return,
        "net_cagr": cagr,
        "realized_volatility": volatility,
        "max_drawdown": float(drawdown.min()),
        "sharpe": sharpe,
        "risk_forecast_error": float(volatility - predicted),
        "risk_forecast_mae": float(abs(volatility - predicted)),
        "risk_forecast_ratio": None if predicted <= 1e-12 else float(volatility / predicted),
        "turnover": float(policy["turnover"]),
        "transaction_cost": float(policy["transaction_cost"]),
        "target_l1_deviation": float(policy["target_l1_deviation"]),
        "concentration_hhi": float(policy["concentration_hhi"]),
        "holding_drift_violation": bool(policy["holding_drift_violation"]),
        "daily_returns": {
            str(index): float(value) for index, value in returns.items()
        },
    }, "complete"


def record_outcome(path, campaign_id, as_of_timestamp, outcome, *, now=None):
    initialize_ledger(path)
    now = _timestamp(now or _utc_now(), "recorded_at")
    as_of = _timestamp(as_of_timestamp, "as_of_timestamp")
    source = dict(outcome or {})
    declared_status = str(source.get("status", "complete")).strip().lower()
    frame = _price_frame(source.get("prices"))
    with _connect(path) as connection:
        campaign = _campaign(connection, campaign_id)
        observation_row = connection.execute(
            "SELECT payload_json, status FROM observations "
            "WHERE campaign_id = ? AND as_of_timestamp = ?",
            (campaign_id, as_of.isoformat()),
        ).fetchone()
        if observation_row is None:
            raise ValueError("Outcome requires an existing observation")
        if observation_row["status"] in FAILED_OBSERVATION_STATUSES:
            raise ValueError("Failed observations cannot receive realized outcomes")
        if connection.execute(
            "SELECT 1 FROM outcomes WHERE campaign_id = ? AND as_of_timestamp = ?",
            (campaign_id, as_of.isoformat()),
        ).fetchone():
            raise ValueError("Duplicate realized outcome is forbidden")
        if not frame.empty and frame.index.max().tz is not None:
            frame.index = frame.index.tz_convert("UTC").tz_localize(None)
        naive_as_of = as_of.tz_localize(None)
        if not frame.empty and frame.index.max() > now.tz_localize(None):
            raise ValueError("Outcome data cannot contain future dates")
        observation = json.loads(observation_row["payload_json"])
        if declared_status in {"network_failure", "data_missing"}:
            _append_outcome_attempt(
                connection,
                campaign_id,
                as_of,
                declared_status,
                {
                    "data_sha256": source.get("data_sha256"),
                    "data_provenance": dict(source.get("data_provenance") or {}),
                    "error": source.get("error"),
                },
                now,
            )
            return {"status": declared_status, "outcome_recorded": False}
        supplied_hash = _require_sha(
            source.get("data_sha256"),
            "outcome.data_sha256",
        )
        contract_version = int(observation.get("contract_version", 1))
        if contract_version >= OBSERVATION_CONTRACT_VERSION:
            if not source.get("data_provenance"):
                raise ValueError("Outcome requires data_provenance")
            if supplied_hash != canonical_outcome_price_sha256(frame):
                raise ValueError("Outcome data_sha256 does not match supplied prices")
        if contract_version == POLICY_COMPARISON_CONTRACT_VERSION:
            policy_metrics = {}
            for policy_id, policy_payload in observation["policies"].items():
                metrics, policy_status = _comparison_policy_outcome(
                    frame,
                    naive_as_of,
                    int(campaign["horizon_observations"]),
                    policy_payload,
                    float(campaign["comparison_specification"]["settings"]["risk_free_rate"]),
                )
                if policy_status != "complete":
                    _append_outcome_attempt(
                        connection,
                        campaign_id,
                        as_of,
                        policy_status,
                        {
                            "data_sha256": source["data_sha256"],
                            "policy_id": policy_id,
                            "coverage": None if metrics is None else metrics.get("coverage"),
                            "missing_tickers": None if metrics is None else metrics.get("missing_tickers"),
                        },
                        now,
                    )
                    return {"status": policy_status, "outcome_recorded": False}
                policy_metrics[policy_id] = metrics
            normalized = {
                "schema_version": SCHEMA_VERSION,
                "contract_version": POLICY_COMPARISON_CONTRACT_VERSION,
                "campaign_id": campaign_id,
                "as_of_timestamp": as_of.isoformat(),
                "recorded_at": now.isoformat(),
                "data_sha256": source["data_sha256"],
                "data_provenance": dict(source.get("data_provenance") or {}),
                "policy_metrics": policy_metrics,
                "evaluation_eligible": observation.get("status") == "complete",
                "no_automatic_promotion": True,
                "production_auto_promotion": False,
            }
            payload_json = _canonical_json(normalized)
            payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            previous = connection.execute(
                "SELECT record_sha256 FROM outcomes ORDER BY outcome_id DESC LIMIT 1"
            ).fetchone()
            previous_hash = previous["record_sha256"] if previous else None
            record_hash = canonical_json_digest({
                "payload_sha256": payload_hash,
                "previous_record_sha256": previous_hash,
            })
            connection.execute(
                "INSERT INTO outcomes(campaign_id, as_of_timestamp, recorded_at, "
                "payload_json, payload_sha256, previous_record_sha256, record_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    campaign_id,
                    as_of.isoformat(),
                    now.isoformat(),
                    payload_json,
                    payload_hash,
                    previous_hash,
                    record_hash,
                ),
            )
            return {
                "status": "recorded",
                "policy_metrics": policy_metrics,
                "record_sha256": record_hash,
            }
        metrics, status = _portfolio_outcome(
            frame,
            naive_as_of,
            int(campaign["horizon_observations"]),
            observation["baseline"],
        )
        if status != "complete":
            _append_outcome_attempt(
                connection,
                campaign_id,
                as_of,
                status,
                {
                    "data_sha256": source["data_sha256"],
                    "error": source.get("error"),
                    "coverage": None if metrics is None else metrics.get("coverage"),
                    "missing_tickers": None if metrics is None else metrics.get("missing_tickers"),
                },
                now,
            )
            return {"status": status, "outcome_recorded": False}
        candidate_metrics = None
        if observation.get("candidate") is not None:
            candidate_metrics, candidate_status = _portfolio_outcome(
                frame,
                naive_as_of,
                int(campaign["horizon_observations"]),
                observation["candidate"],
            )
            if candidate_status != "complete":
                _append_outcome_attempt(
                    connection,
                    campaign_id,
                    as_of,
                    candidate_status,
                    {
                        "data_sha256": source["data_sha256"],
                        "side": "candidate",
                        "coverage": (
                            None
                            if candidate_metrics is None
                            else candidate_metrics.get("coverage")
                        ),
                    },
                    now,
                )
                return {
                    "status": candidate_status,
                    "outcome_recorded": False,
                }
        normalized = {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": campaign_id,
            "as_of_timestamp": as_of.isoformat(),
            "recorded_at": now.isoformat(),
            "data_sha256": source["data_sha256"],
            "data_provenance": dict(source.get("data_provenance") or {}),
            "baseline_metrics": metrics,
            "candidate_metrics": candidate_metrics,
            "evaluation_eligible": observation.get("status") == "complete",
            "production_auto_promotion": False,
        }
        payload_json = _canonical_json(normalized)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        previous = connection.execute(
            "SELECT record_sha256 FROM outcomes ORDER BY outcome_id DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["record_sha256"] if previous else None
        record_hash = canonical_json_digest({
            "payload_sha256": payload_hash,
            "previous_record_sha256": previous_hash,
        })
        connection.execute(
            "INSERT INTO outcomes(campaign_id, as_of_timestamp, recorded_at, "
            "payload_json, payload_sha256, previous_record_sha256, record_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                campaign_id,
                as_of.isoformat(),
                now.isoformat(),
                payload_json,
                payload_hash,
                previous_hash,
                record_hash,
            ),
        )
    return {"status": "recorded", "metrics": metrics, "record_sha256": record_hash}


def evaluate_campaign(path, campaign_id):
    initialize_ledger(path)
    policy = load_research_policy()
    with _connect(path) as connection:
        campaign = _campaign(connection, campaign_id)
        rows = connection.execute(
            "SELECT outcomes.payload_json, observations.status AS observation_status "
            "FROM outcomes JOIN observations USING(campaign_id, as_of_timestamp) "
            "WHERE outcomes.campaign_id = ? ORDER BY outcomes.as_of_timestamp",
            (campaign_id,),
        ).fetchall()
        observations = connection.execute(
            "SELECT status, COUNT(*) AS count FROM observations "
            "WHERE campaign_id = ? GROUP BY status",
            (campaign_id,),
        ).fetchall()
    if campaign.get("comparison_specification") is not None:
        payloads = [json.loads(row["payload_json"]) for row in rows]
        eligible = [
            payload for row, payload in zip(rows, payloads)
            if row["observation_status"] == "complete"
            and payload.get("evaluation_eligible", True)
            and payload.get("contract_version") == POLICY_COMPARISON_CONTRACT_VERSION
        ]
        minimum = int(
            campaign["comparison_specification"]["settings"][
                "minimum_mature_observations"
            ]
        )
        result = {
            "campaign_id": campaign_id,
            "calendar_forward_shadow": True,
            "comparison_spec_sha256": campaign["comparison_specification"][
                "comparison_spec_sha256"
            ],
            "mature_paired_observation_count": len(eligible),
            "recorded_outcome_count": len(payloads),
            "minimum_mature_observations": minimum,
            "observation_status_counts": {
                row["status"]: row["count"] for row in observations
            },
            "status": "forward_pending" if len(eligible) < minimum else "inconclusive",
            "no_automatic_promotion": True,
            "production_auto_promotion": False,
            "manual_review_only": True,
        }
        if not eligible:
            return result
        policy_ids = ["buy_and_hold", "fixed_target", "rolling_reoptimization"]
        daily = {policy_id: {} for policy_id in policy_ids}
        summaries = {}
        for policy_id in policy_ids:
            metrics = [payload["policy_metrics"][policy_id] for payload in eligible]
            for metric in metrics:
                daily[policy_id].update(metric.get("daily_returns") or {})
            summaries[policy_id] = {
                "mean_realized_volatility": float(np.mean([m["realized_volatility"] for m in metrics])),
                "mean_max_drawdown": float(np.mean([m["max_drawdown"] for m in metrics])),
                "mean_net_cagr": float(np.mean([m["net_cagr"] for m in metrics])),
                "mean_sharpe": float(np.mean([m["sharpe"] for m in metrics if m["sharpe"] is not None])),
                "cumulative_turnover": float(sum(m["turnover"] for m in metrics)),
                "transaction_cost": float(sum(m["transaction_cost"] for m in metrics)),
                "mean_target_l1_deviation": float(np.mean([m["target_l1_deviation"] for m in metrics])),
                "mean_concentration_hhi": float(np.mean([m["concentration_hhi"] for m in metrics])),
                "risk_forecast_mae": float(np.mean([m["risk_forecast_mae"] for m in metrics])),
                "risk_forecast_calibration_ratio": float(np.mean([m["risk_forecast_ratio"] for m in metrics if m["risk_forecast_ratio"] is not None])),
                "holding_drift_violation_count": int(sum(bool(m["holding_drift_violation"]) for m in metrics)),
            }
        result["summary_by_policy"] = summaries
        settings = campaign["comparison_specification"]["settings"]
        pair_results = {}
        p_values = {}
        lower_policy = {}
        for left, right in campaign["comparison_specification"]["statistics"]["paired_comparisons"]:
            comparison = paired_block_bootstrap(
                pd.Series(daily[left], dtype=float),
                pd.Series(daily[right], dtype=float),
                risk_free_rate=settings["risk_free_rate"],
                block_size=settings["bootstrap_block_size"],
                samples=settings["bootstrap_samples"],
                seed=settings["bootstrap_seed"],
            )
            key = f"{left}_vs_{right}"
            pair_results[key] = comparison
            if comparison.get("status") == "ok":
                observed = comparison["observed"]["difference"]["annualized_volatility"]
                if observed < 0.0:
                    lower_policy[key] = left
                    p_values[key] = 1.0 - comparison["probability"]["lower_volatility"]
                else:
                    lower_policy[key] = right
                    p_values[key] = comparison["probability"]["lower_volatility"]
        result["paired_statistics"] = pair_results
        result["holm_volatility"] = holm_bonferroni(p_values, alpha=0.05)
        if len(eligible) >= minimum and len(lower_policy) == 3:
            wins = {policy_id: 0 for policy_id in policy_ids}
            for key, winner in lower_policy.items():
                comparison = pair_results[key]
                interval = comparison["difference_interval"]["annualized_volatility"]
                left_wins = winner == key.split("_vs_")[0]
                excludes_zero = interval["upper_95"] < 0.0 if left_wins else interval["lower_95"] > 0.0
                if result["holm_volatility"][key]["significant"] and excludes_zero:
                    wins[winner] += 1
            candidates = [policy_id for policy_id, count in wins.items() if count == 2]
            if len(candidates) == 1:
                winner = candidates[0]
                guards = []
                for other in policy_ids:
                    if other == winner:
                        continue
                    winner_summary = summaries[winner]
                    other_summary = summaries[other]
                    guards.extend([
                        winner_summary["mean_max_drawdown"] >= other_summary["mean_max_drawdown"],
                        winner_summary["mean_sharpe"] >= other_summary["mean_sharpe"],
                        abs(winner_summary["risk_forecast_calibration_ratio"] - 1.0)
                        <= abs(other_summary["risk_forecast_calibration_ratio"] - 1.0),
                        winner_summary["cumulative_turnover"]
                        <= max(0.50, 2.0 * other_summary["cumulative_turnover"]),
                        winner_summary["mean_concentration_hhi"]
                        <= other_summary["mean_concentration_hhi"],
                    ])
                if all(guards):
                    result["status"] = "superiority"
                    result["superior_policy"] = winner
        return result
    outcome_payloads = [json.loads(row["payload_json"]) for row in rows]
    metrics = [
        payload["baseline_metrics"]
        for row, payload in zip(rows, outcome_payloads)
        if row["observation_status"] == "complete"
        and payload.get("evaluation_eligible", True)
    ]
    minimum = int(policy["shadow"]["minimum_mature_observations"])
    result = {
        "campaign_id": campaign_id,
        "calendar_forward_shadow": True,
        "production_auto_promotion": False,
        "manual_review_only": True,
        "mature_outcome_count": len(metrics),
        "recorded_outcome_count": len(outcome_payloads),
        "observation_status_counts": {row["status"]: row["count"] for row in observations},
        "status": "descriptive_only" if len(metrics) >= minimum else "insufficient_mature_observations",
        "minimum_mature_observations": minimum,
        "candidate_registered": campaign["candidate_specification"] is not None,
    }
    if metrics:
        for field in (
            "realized_return",
            "realized_volatility",
            "max_drawdown",
            "risk_forecast_mae",
            "risk_forecast_ratio",
            "coverage",
        ):
            values = [item[field] for item in metrics if item.get(field) is not None]
            result[f"mean_{field}"] = None if not values else float(np.mean(values))
    return result


def verify_ledger(path):
    initialize_ledger(path)
    with _connect(path) as connection:
        campaigns = connection.execute("SELECT * FROM campaigns ORDER BY campaign_id").fetchall()
        for row in campaigns:
            actual = hashlib.sha256(row["spec_json"].encode("utf-8")).hexdigest()
            if actual != row["spec_sha256"]:
                raise ValueError("Campaign specification hash mismatch")
        counts = {"campaigns": len(campaigns)}
        for table, id_field in (("observations", "observation_id"), ("outcomes", "outcome_id")):
            previous = None
            rows = connection.execute(f"SELECT * FROM {table} ORDER BY {id_field}").fetchall()
            for row in rows:
                payload_hash = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
                if payload_hash != row["payload_sha256"]:
                    raise ValueError(f"{table} payload hash mismatch")
                if row["previous_record_sha256"] != previous:
                    raise ValueError(f"{table} record chain mismatch")
                expected = canonical_json_digest({
                    "payload_sha256": payload_hash,
                    "previous_record_sha256": previous,
                })
                if expected != row["record_sha256"]:
                    raise ValueError(f"{table} record hash mismatch")
                previous = expected
            counts[table] = len(rows)
        counts["outcome_attempts"] = connection.execute(
            "SELECT COUNT(*) FROM outcome_attempts"
        ).fetchone()[0]
    return {"status": "ok", **counts}
