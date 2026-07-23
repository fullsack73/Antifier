"""Immutable research/validation/holdout split contracts."""

import hashlib
import json

import pandas as pd


SPLIT_ROLES = {"research", "validation", "locked_holdout"}
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


def normalize_research_split_manifest(manifest):
    """Validate a split contract and its self-declared immutable digest."""
    payload = dict(manifest or {})
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        raise ValueError(
            "Research split manifest is missing required fields: "
            + ", ".join(missing)
        )
    if int(payload["schema_version"]) != 1:
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
    return {
        **payload,
        "schema_version": 1,
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
    return {
        **normalized,
        "promotion_safe": bool(
            normalized["role"] in {"research", "locked_holdout"}
            and normalized["locked"]
        ),
    }
