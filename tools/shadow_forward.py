#!/usr/bin/env python3
"""Manage append-only Antifier calendar-forward shadow observations."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) in sys.path:
    sys.path.remove(str(BACKEND))
sys.path.insert(0, str(BACKEND))

from shadow_forward import (  # noqa: E402
    append_observation,
    create_campaign,
    evaluate_campaign,
    get_campaign,
    record_outcome,
    verify_ledger,
)
from production_baseline_observation import (  # noqa: E402
    build_production_baseline_observation,
    collect_production_baseline_observation,
)


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--campaign-spec", required=True)

    observe = commands.add_parser("observe")
    observe.add_argument("--input", required=True)

    collect = commands.add_parser(
        "collect-baseline",
        help="collect one production GMV baseline observation without placing orders",
    )
    collect.add_argument("--campaign-id", required=True)
    collect.add_argument("--run-spec", required=True)
    collect.add_argument("--scheduled-for")
    collect.add_argument(
        "--fixture-capture",
        help="offline optimizer-result capture for deterministic regression tests",
    )

    outcome = commands.add_parser("record-outcome")
    outcome.add_argument("--campaign-id", required=True)
    outcome.add_argument("--as-of", required=True)
    outcome.add_argument("--input", required=True)

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--campaign-id", required=True)
    evaluate.add_argument("--output")

    commands.add_parser("verify")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = create_campaign(args.ledger, _json(args.campaign_spec))
        elif args.command == "observe":
            result = append_observation(args.ledger, _json(args.input))
        elif args.command == "collect-baseline":
            run_spec = _json(args.run_spec)
            if args.fixture_capture:
                capture = _json(args.fixture_capture)
                observation = build_production_baseline_observation(
                    get_campaign(args.ledger, args.campaign_id),
                    run_spec,
                    capture["optimizer_result"],
                    capture["rerun_result"],
                    as_of_timestamp=(
                        args.scheduled_for or capture["as_of_timestamp"]
                    ),
                )
            else:
                observation = collect_production_baseline_observation(
                    args.ledger,
                    args.campaign_id,
                    run_spec,
                    scheduled_for=args.scheduled_for,
                )
            result = append_observation(args.ledger, observation)
        elif args.command == "record-outcome":
            result = record_outcome(
                args.ledger,
                args.campaign_id,
                args.as_of,
                _json(args.input),
            )
        elif args.command == "evaluate":
            result = evaluate_campaign(args.ledger, args.campaign_id)
            if args.output:
                Path(args.output).write_text(
                    json.dumps(result, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        else:
            result = verify_ledger(args.ledger)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
