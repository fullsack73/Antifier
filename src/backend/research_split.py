"""Immutable research/validation/holdout split contracts."""

import hashlib
import json
from pathlib import Path

import pandas as pd


SPLIT_ROLES = {"research", "validation", "locked_holdout"}
RESEARCH_LANES = {"alpha", "risk", "execution_correctness"}
EVIDENCE_SCOPES = {
    "production_baseline",
    "experimental_public_data",
    "aggregate_portfolio_research",
    "accepted_unavailable_evidence",
    "calendar_forward_shadow",
}
BLOCKED_CONSUMED_USES = {
    "candidate_selection",
    "tuning",
    "validation",
    "promotion",
}
ACKNOWLEDGED_CONSUMED_USES = {"diagnostic", "reproduction"}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_POLICY = (
    REPOSITORY_ROOT / "data" / "research" / "research_policy_v1.json"
)
DEFAULT_CONSUMPTION_REGISTRY = (
    REPOSITORY_ROOT / "data" / "research" / "evidence_consumption_v1.jsonl"
)
COMPARISON_EXECUTION_FIELDS = (
    "eligible_universe_sha256",
    "rebalance_dates",
    "horizon",
    "rebalance_step",
    "max_asset_weight",
    "rebalance_band",
    "max_turnover",
    "transaction_cost_bps",
    "risk_free_sha256",
)
REQUIRED_FIELDS = {
    "schema_version",
    "split_id",
    "role",
    "evaluation_start",
    "evaluation_end",
    "experiment_namespace",
    "objectives",
    "settings",
    "universe_manifest_sha256",
    "price_file_sha256",
    "factor_file_sha256",
    "locked",
    "manifest_sha256",
}


def _canonical_payload(manifest):
    payload = {
        key: value
        for key, value in dict(manifest).items()
        if key != "manifest_sha256"
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def research_split_digest(manifest):
    """Hash all split fields except the self-declared digest."""
    return hashlib.sha256(_canonical_payload(manifest)).hexdigest()


def canonical_json_digest(value):
    """Return a stable SHA-256 for a JSON-compatible contract value."""
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def candidate_specification_digest(manifest):
    """Hash only the hypothesis and settings, independent of data lineage."""
    payload = dict(manifest or {})
    return canonical_json_digest({
        "experiment_namespace": payload.get("experiment_namespace"),
        "objectives": payload.get("objectives"),
        "settings": payload.get("settings"),
    })


def dataset_lineage_digest(manifest):
    """Hash the immutable universe, price, factor, and auxiliary inputs."""
    payload = dict(manifest or {})
    return canonical_json_digest({
        "universe_manifest_sha256": payload.get(
            "universe_manifest_sha256"
        ),
        "price_file_sha256": payload.get("price_file_sha256"),
        "factor_file_sha256": payload.get("factor_file_sha256"),
        "auxiliary_files": payload.get("auxiliary_files", {}),
    })


def load_research_policy(path=DEFAULT_RESEARCH_POLICY):
    """Load and minimally validate the versioned research policy artifact."""
    policy_path = Path(path)
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("Unsupported research policy schema_version")
    if not str(payload.get("policy_id", "")).strip():
        raise ValueError("Research policy requires policy_id")
    if set(payload.get("lanes", {})) != RESEARCH_LANES:
        raise ValueError("Research policy must define all research lanes")
    scopes = set(payload.get("evidence_scopes", {}))
    if scopes != EVIDENCE_SCOPES:
        raise ValueError("Research policy must define all evidence scopes")
    return {
        **payload,
        "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
    }


def _registry_record_digest(record):
    payload = {
        key: value
        for key, value in dict(record).items()
        if key != "record_sha256"
    }
    return canonical_json_digest(payload)


def load_consumption_registry(path=DEFAULT_CONSUMPTION_REGISTRY):
    """Validate and return the append-only, hash-chained consumption ledger."""
    registry_path = Path(path)
    if not registry_path.exists():
        return []
    records = []
    previous = None
    for line_number, raw_line in enumerate(
        registry_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        if int(record.get("schema_version", 0)) != 1:
            raise ValueError(
                f"Unsupported consumption record at line {line_number}"
            )
        if record.get("previous_record_sha256") != previous:
            raise ValueError(
                f"Consumption registry chain mismatch at line {line_number}"
            )
        actual = _registry_record_digest(record)
        if record.get("record_sha256") != actual:
            raise ValueError(
                f"Consumption registry digest mismatch at line {line_number}"
            )
        for field in (
            "split_id",
            "manifest_sha256",
            "result_sha256",
            "dataset_lineage_sha256",
            "evaluation_start",
            "evaluation_end",
            "consumed_at",
        ):
            if not str(record.get(field, "")).strip():
                raise ValueError(
                    f"Consumption record is missing {field} at line "
                    f"{line_number}"
                )
        for field in (
            "manifest_sha256",
            "result_sha256",
            "dataset_lineage_sha256",
            "record_sha256",
        ):
            value = str(record[field])
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(
                    f"Consumption record has invalid {field} at line "
                    f"{line_number}"
                )
        records.append(record)
        previous = actual
    return records


def append_consumption_record(path, record):
    """Append one verified consumption event; never rewrite existing rows."""
    registry_path = Path(path)
    existing = load_consumption_registry(registry_path)
    payload = dict(record or {})
    split_id = str(payload.get("split_id", "")).strip()
    manifest_sha = str(payload.get("manifest_sha256", "")).strip()
    if any(
        item["split_id"] == split_id
        or item["manifest_sha256"] == manifest_sha
        for item in existing
    ):
        raise ValueError("Research split is already recorded as consumed")
    payload.update({
        "schema_version": 1,
        "previous_record_sha256": (
            existing[-1]["record_sha256"] if existing else None
        ),
    })
    payload["record_sha256"] = _registry_record_digest(payload)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        handle.write("\n")
    return payload


def validate_evidence_use(
    manifest,
    *,
    requested_use="candidate_selection",
    consumption_registry=DEFAULT_CONSUMPTION_REGISTRY,
    acknowledge_consumed=False,
):
    """Reject selection or tuning with an already observed split or lineage."""
    payload = dict(manifest or {})
    requested_use = str(requested_use or "").strip().lower()
    supported = BLOCKED_CONSUMED_USES | ACKNOWLEDGED_CONSUMED_USES
    if requested_use not in supported:
        raise ValueError(f"Unsupported research evidence use: {requested_use!r}")
    start = pd.Timestamp(payload["evaluation_start"])
    end = pd.Timestamp(payload["evaluation_end"])
    lineage = dataset_lineage_digest(payload)
    matches = []
    for record in load_consumption_registry(consumption_registry):
        same_identity = (
            record["split_id"] == payload["split_id"]
            or record["manifest_sha256"] == payload["manifest_sha256"]
        )
        record_start = pd.Timestamp(record["evaluation_start"])
        record_end = pd.Timestamp(record["evaluation_end"])
        overlaps_lineage = (
            record["dataset_lineage_sha256"] == lineage
            and start <= record_end
            and end >= record_start
        )
        if same_identity or overlaps_lineage:
            matches.append(record)
    if not matches:
        return {
            "consumption_state": "reserved",
            "candidate_selection_allowed": True,
            "matched_consumption_records": [],
        }
    if requested_use in BLOCKED_CONSUMED_USES:
        raise ValueError(
            "Consumed research evidence cannot be reused for "
            f"{requested_use}"
        )
    if not acknowledge_consumed:
        raise ValueError(
            "Consumed diagnostic/reproduction use requires explicit "
            "acknowledgement"
        )
    return {
        "consumption_state": "consumed",
        "candidate_selection_allowed": False,
        "matched_consumption_records": [
            item["record_sha256"] for item in matches
        ],
    }


def normalize_research_split_manifest(manifest):
    """Validate a split contract and its self-declared immutable digest."""
    payload = dict(manifest or {})
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        raise ValueError(
            "Research split manifest is missing required fields: "
            + ", ".join(missing)
        )
    schema_version = int(payload["schema_version"])
    if schema_version not in {1, 2}:
        raise ValueError("Unsupported research split schema_version")

    split_id = str(payload["split_id"] or "").strip()
    namespace = str(payload["experiment_namespace"] or "").strip()
    role = str(payload["role"] or "").strip().lower()
    if not split_id or not namespace:
        raise ValueError(
            "Research split requires split_id and experiment_namespace"
        )
    if role not in SPLIT_ROLES:
        raise ValueError(f"Unsupported research split role: {role!r}")

    start = pd.Timestamp(payload["evaluation_start"])
    end = pd.Timestamp(payload["evaluation_end"])
    if pd.isna(start) or pd.isna(end) or start > end:
        raise ValueError(
            "Research split requires a valid evaluation date interval"
        )
    objectives = [
        str(value).strip()
        for value in list(payload["objectives"] or [])
        if str(value).strip()
    ]
    if not objectives or len(objectives) != len(set(objectives)):
        raise ValueError(
            "Research split objectives must be non-empty and unique"
        )
    settings = payload["settings"]
    if not isinstance(settings, dict) or not settings:
        raise ValueError("Research split settings must be a non-empty object")
    if not isinstance(payload["locked"], bool):
        raise ValueError("Research split locked must be boolean")
    for field in (
        "universe_manifest_sha256",
        "price_file_sha256",
    ):
        if len(str(payload[field] or "").strip()) != 64:
            raise ValueError(f"Research split requires a SHA-256 in {field}")
    factor_digest = payload["factor_file_sha256"]
    if factor_digest is not None and len(str(factor_digest).strip()) != 64:
        raise ValueError(
            "Research split factor_file_sha256 must be null or SHA-256"
        )
    auxiliary_files = payload.get("auxiliary_files", {})
    if not isinstance(auxiliary_files, dict):
        raise ValueError(
            "Research split auxiliary_files must be an object"
        )
    for name, digest in auxiliary_files.items():
        if (
            not str(name).strip()
            or len(str(digest or "").strip()) != 64
        ):
            raise ValueError(
                "Research split auxiliary_files requires named SHA-256 "
                "values"
            )

    declared_digest = str(payload["manifest_sha256"] or "").strip()
    actual_digest = research_split_digest(payload)
    if declared_digest != actual_digest:
        raise ValueError(
            "Research split manifest SHA-256 does not match its content"
        )
    normalized = {
        **payload,
        "schema_version": schema_version,
        "split_id": split_id,
        "role": role,
        "evaluation_start": start.strftime("%Y-%m-%d"),
        "evaluation_end": end.strftime("%Y-%m-%d"),
        "experiment_namespace": namespace,
        "objectives": objectives,
        "settings": settings,
        "universe_manifest_sha256": str(
            payload["universe_manifest_sha256"]
        ).strip(),
        "price_file_sha256": str(payload["price_file_sha256"]).strip(),
        "factor_file_sha256": (
            None
            if factor_digest is None
            else str(factor_digest).strip()
        ),
        "auxiliary_files": {
            str(name): str(digest).strip()
            for name, digest in auxiliary_files.items()
        },
        "locked": bool(payload["locked"]),
        "manifest_sha256": actual_digest,
    }
    if schema_version == 2:
        policy = load_research_policy()
        lane = str(payload.get("lane", "")).strip().lower()
        scope = str(payload.get("evidence_scope", "")).strip().lower()
        if lane not in RESEARCH_LANES:
            raise ValueError("Research split schema v2 requires a valid lane")
        if scope not in EVIDENCE_SCOPES:
            raise ValueError(
                "Research split schema v2 requires a valid evidence_scope"
            )
        expected = {
            "policy_sha256": policy["policy_sha256"],
            "candidate_specification_sha256": (
                candidate_specification_digest(payload)
            ),
            "dataset_lineage_sha256": dataset_lineage_digest(payload),
        }
        for field, value in expected.items():
            if payload.get(field) != value:
                raise ValueError(
                    f"Research split schema v2 mismatch for {field}"
                )
        normalized.update({"lane": lane, "evidence_scope": scope})
    return normalized


def validate_research_split_run(
    manifest,
    *,
    split_id,
    experiment_namespace,
    objectives,
    settings,
    evaluation_start,
    evaluation_end,
    universe_manifest_sha256,
    price_file_sha256,
    factor_file_sha256,
    auxiliary_files=None,
    evidence_use="candidate_selection",
    consumption_registry=DEFAULT_CONSUMPTION_REGISTRY,
    acknowledge_consumed=False,
):
    """Reject any run whose identity, dates, data, or hypotheses drift."""
    normalized = normalize_research_split_manifest(manifest)
    expected = {
        "split_id": str(split_id).strip(),
        "experiment_namespace": str(experiment_namespace).strip(),
        "objectives": list(objectives),
        "settings": dict(settings),
        "evaluation_start": pd.Timestamp(evaluation_start).strftime(
            "%Y-%m-%d"
        ),
        "evaluation_end": pd.Timestamp(evaluation_end).strftime("%Y-%m-%d"),
        "universe_manifest_sha256": str(
            universe_manifest_sha256 or ""
        ).strip(),
        "price_file_sha256": str(price_file_sha256 or "").strip(),
        "factor_file_sha256": (
            None
            if factor_file_sha256 is None
            else str(factor_file_sha256).strip()
        ),
        "auxiliary_files": dict(auxiliary_files or {}),
    }
    for field, value in expected.items():
        if normalized[field] != value:
            raise ValueError(
                f"Research split manifest mismatch for {field}: "
                f"expected {normalized[field]!r}, got {value!r}"
            )
    evidence = validate_evidence_use(
        normalized,
        requested_use=evidence_use,
        consumption_registry=consumption_registry,
        acknowledge_consumed=acknowledge_consumed,
    )
    evidence_scope = normalized.get("evidence_scope", "legacy_unclassified")
    production_evidence_allowed = bool(
        evidence_scope == "production_baseline"
        and evidence["consumption_state"] != "consumed"
    )
    return {
        **normalized,
        **evidence,
        "integrity_locked": bool(normalized["locked"]),
        "evidence_scope": evidence_scope,
        "production_evidence_allowed": production_evidence_allowed,
        "promotion_safe": production_evidence_allowed,
    }


def validate_comparison_execution_settings(
    baseline_settings,
    candidate_settings,
    required_fields=COMPARISON_EXECUTION_FIELDS,
):
    """Require baseline and candidate to share every execution condition."""
    baseline = dict(baseline_settings or {})
    candidate = dict(candidate_settings or {})
    missing = [
        field
        for field in required_fields
        if field not in baseline or field not in candidate
    ]
    if missing:
        raise ValueError(
            "Comparison settings are missing required fields: "
            + ", ".join(missing)
        )
    mismatches = [
        field
        for field in required_fields
        if baseline[field] != candidate[field]
    ]
    if mismatches:
        raise ValueError(
            "Baseline and candidate execution settings differ: "
            + ", ".join(mismatches)
        )
    return {
        field: baseline[field]
        for field in required_fields
    }
