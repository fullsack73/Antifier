#!/usr/bin/env python3
"""Audit and append Antifier research-evidence consumption records."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) in sys.path:
    sys.path.remove(str(BACKEND))
sys.path.insert(0, str(BACKEND))

from research_split import (  # noqa: E402
    DEFAULT_CONSUMPTION_REGISTRY,
    append_consumption_record,
    dataset_lineage_digest,
    load_consumption_registry,
    load_research_policy,
    normalize_research_split_manifest,
    validate_evidence_use,
)


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _audit(args):
    records = load_consumption_registry(args.registry)
    policy = load_research_policy(args.policy)
    print(json.dumps({
        "status": "ok",
        "policy_id": policy["policy_id"],
        "policy_sha256": policy["policy_sha256"],
        "consumed_split_count": len(records),
        "last_record_sha256": (
            records[-1]["record_sha256"] if records else None
        ),
    }, indent=2, sort_keys=True))


def _consume(args):
    manifest = normalize_research_split_manifest(_load_json(args.split))
    result_path = Path(args.result)
    record = append_consumption_record(args.registry, {
        "split_id": manifest["split_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "dataset_lineage_sha256": dataset_lineage_digest(manifest),
        "evaluation_start": manifest["evaluation_start"],
        "evaluation_end": manifest["evaluation_end"],
        "role": manifest["role"],
        "consumed_at": datetime.now(timezone.utc).isoformat(),
        "allowed_uses": ["diagnostic", "reproduction"],
    })
    print(json.dumps(record, indent=2, sort_keys=True))


def _check_use(args):
    manifest = normalize_research_split_manifest(_load_json(args.split))
    result = validate_evidence_use(
        manifest,
        requested_use=args.use,
        consumption_registry=args.registry,
        acknowledge_consumed=args.acknowledge_consumed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_CONSUMPTION_REGISTRY),
    )
    parser.add_argument(
        "--policy",
        default=str(ROOT / "data" / "research" / "research_policy_v1.json"),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("audit")

    consume = commands.add_parser("consume")
    consume.add_argument("--split", required=True)
    consume.add_argument("--result", required=True)

    check = commands.add_parser("check-use")
    check.add_argument("--split", required=True)
    check.add_argument(
        "--use",
        required=True,
        choices=(
            "candidate_selection",
            "tuning",
            "validation",
            "promotion",
            "diagnostic",
            "reproduction",
        ),
    )
    check.add_argument("--acknowledge-consumed", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            _audit(args)
        elif args.command == "consume":
            _consume(args)
        else:
            _check_use(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
