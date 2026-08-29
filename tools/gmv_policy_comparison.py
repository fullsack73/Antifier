#!/usr/bin/env python3
"""Run the forward-only GMV operating-policy study; historical backfill is forbidden."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) in sys.path:
    sys.path.remove(str(BACKEND))
sys.path.insert(0, str(BACKEND))

from gmv_policy_comparison import (  # noqa: E402
    build_comparison_observation,
    collect_live_comparison_inputs,
    create_comparison_spec,
    load_spec,
    validate_comparison_spec,
)
from research_split import load_consumption_registry, load_research_policy  # noqa: E402
from shadow_forward import (  # noqa: E402
    append_observation,
    create_campaign,
    evaluate_campaign,
    latest_complete_observation,
    outcome_price_sha256,
    record_outcome,
    verify_ledger,
)
from ticker_lists import get_sp500_tickers  # noqa: E402


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_new(path, payload):
    target = Path(path)
    if target.exists():
        raise ValueError(f"Refusing to overwrite append-only artifact: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _revision():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _campaign(spec, campaign_id):
    return {
        "campaign_id": campaign_id,
        "timezone": "Asia/Seoul",
        "lane": "risk",
        "evidence_scope": "calendar_forward_shadow",
        "horizon_observations": spec["settings"]["outcome_horizon"],
        "minimum_coverage": 0.8,
        "universe_policy": {
            "source": spec["universe_source"],
            "requested_universe_sha256": spec["requested_universe_sha256"],
            "formation_eligible_universe_frozen": True,
        },
        "baseline_specification": spec["production_baseline"],
        "candidate_specification": None,
        "comparison_specification": spec,
        "execution_conditions": {
            "transaction_cost_bps": spec["settings"]["transaction_cost_bps"],
            "rebalance_band": spec["settings"]["rebalance_band"],
            "max_turnover": spec["settings"]["max_turnover"],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Preregister and operate the three-policy production GMV calendar-forward "
            "comparison. Consumed historical evidence and backfill are forbidden; "
            "no command promotes production automatically."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("evidence-audit", help="verify policy and consumed-evidence hash chain")

    create = commands.add_parser("spec-create", help="create the immutable S&P 500 forward specification")
    create.add_argument("--output", required=True)
    validate = commands.add_parser("spec-validate", help="validate specification and self-hash")
    validate.add_argument("--spec", required=True)

    init = commands.add_parser("forward-init", help="register a forward campaign; never backfills")
    init.add_argument("--spec", required=True)
    init.add_argument("--ledger", required=True)
    init.add_argument("--campaign-id", default="production-gmv-policy-forward-v1")

    observe = commands.add_parser("forward-observe", help="append one as-of policy transition without orders")
    observe.add_argument("--spec", required=True)
    observe.add_argument("--ledger", required=True)
    observe.add_argument("--campaign-id", default="production-gmv-policy-forward-v1")
    observe.add_argument("--as-of", required=True)
    observe.add_argument("--capture", help="offline production optimizer pair; omit for live collection")

    fixture = commands.add_parser("fixture-run", help="run an offline sequential fixture twice")
    fixture.add_argument("--spec", required=True)
    fixture.add_argument("--input", required=True)
    fixture.add_argument("--output")

    rerun = commands.add_parser("deterministic-rerun", help="verify canonical fixture rerun identity")
    rerun.add_argument("--spec", required=True)
    rerun.add_argument("--input", required=True)

    outcome = commands.add_parser("record-outcome", help="record only a mature forward outcome")
    outcome.add_argument("--ledger", required=True)
    outcome.add_argument("--campaign-id", default="production-gmv-policy-forward-v1")
    outcome.add_argument("--as-of", required=True)
    outcome.add_argument("--input", required=True)

    evaluate = commands.add_parser("evaluate", help="aggregate mature paired outcomes or return forward_pending")
    evaluate.add_argument("--ledger", required=True)
    evaluate.add_argument("--campaign-id", default="production-gmv-policy-forward-v1")
    evaluate.add_argument("--output")

    verify = commands.add_parser("verify", help="audit result and ledger hash-chain integrity")
    verify.add_argument("--ledger", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "evidence-audit":
            records = load_consumption_registry()
            policy = load_research_policy()
            result = {
                "status": "ok",
                "consumed_split_count": len(records),
                "last_record_sha256": records[-1]["record_sha256"] if records else None,
                "policy_sha256": policy["policy_sha256"],
                "untouched_historical_comparison_available": False,
                "comparison_route": "calendar_forward_only",
            }
        elif args.command == "spec-create":
            source = ROOT / "snp.csv"
            spec = create_comparison_spec(
                get_sp500_tickers(),
                universe_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                code_revision=_revision(),
            )
            _write_new(args.output, spec)
            result = {"status": "created", "comparison_spec_sha256": spec["comparison_spec_sha256"]}
        elif args.command == "spec-validate":
            spec = load_spec(args.spec)
            result = {"status": "ok", "comparison_spec_sha256": spec["comparison_spec_sha256"]}
        elif args.command == "forward-init":
            spec = load_spec(args.spec)
            result = create_campaign(args.ledger, _campaign(spec, args.campaign_id))
        elif args.command == "forward-observe":
            spec = load_spec(args.spec)
            if args.capture:
                capture = _json(args.capture)
                first, second = capture["optimizer_result"], capture["rerun_result"]
            else:
                first, second = collect_live_comparison_inputs(spec, as_of_timestamp=args.as_of)
            campaign = _campaign(spec, args.campaign_id)
            prior = latest_complete_observation(args.ledger, args.campaign_id)
            observation = build_comparison_observation(
                campaign,
                spec,
                first,
                second,
                as_of_timestamp=args.as_of,
                prior_observation=prior,
            )
            result = append_observation(args.ledger, observation)
        elif args.command in {"fixture-run", "deterministic-rerun"}:
            spec = load_spec(args.spec)
            fixture_payload = _json(args.input)
            campaign = _campaign(spec, fixture_payload.get("campaign_id", "fixture-gmv-policy-v1"))

            def execute():
                prior = None
                rows = []
                for item in fixture_payload["observations"]:
                    prior = build_comparison_observation(
                        campaign,
                        spec,
                        item["optimizer_result"],
                        item["rerun_result"],
                        as_of_timestamp=item["as_of_timestamp"],
                        prior_observation=prior,
                    )
                    rows.append(prior)
                return rows

            first = execute()
            second = execute()
            first_hash = hashlib.sha256(
                json.dumps(first, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            second_hash = hashlib.sha256(
                json.dumps(second, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if first_hash != second_hash:
                raise ValueError("Fixture deterministic rerun failed")
            result = {
                "status": "diagnostic_fixture_only",
                "forward_pending": True,
                "observation_count": len(first),
                "result_sha256": first_hash,
                "deterministic_rerun": True,
                "observations": first,
                "no_automatic_promotion": True,
            }
            if getattr(args, "output", None):
                _write_new(args.output, result)
        elif args.command == "record-outcome":
            payload = _json(args.input)
            payload.setdefault("data_sha256", outcome_price_sha256(payload.get("prices")))
            result = record_outcome(args.ledger, args.campaign_id, args.as_of, payload)
        elif args.command == "evaluate":
            result = evaluate_campaign(args.ledger, args.campaign_id)
            if args.output:
                _write_new(args.output, result)
        else:
            result = verify_ledger(args.ledger)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
