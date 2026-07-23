#!/usr/bin/env python3
"""Validate frozen quality momentum on a locked four-case split."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
TOOLS = ROOT / "tools"
for directory in (BACKEND, TOOLS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from forecast_signal_research import (  # noqa: E402
    cross_sectional_rank_diagnostics,
    paired_rank_signal_block_bootstrap,
    rank_signal_block_bootstrap,
    signal_only_gate,
)
from research_profitability_momentum import (  # noqa: E402
    BASELINE,
    MOMENTUM_WEIGHT,
    QUALITY_CANDIDATE,
    VALUE_QUALITY_CANDIDATE,
    _distribution_diagnostics,
    _paired_gate,
    _run_periods,
    book_to_market_buckets,
    investment_buckets,
    operating_profitability_buckets,
)
from research_accrual_quality import (  # noqa: E402
    NET_ISSUANCE_CANDIDATE,
    _paired_gate as _issuance_paired_gate,
    _run_periods as _run_issuance_periods,
    net_issuance_quality_buckets,
)
from research_split import validate_research_split_run  # noqa: E402


QUALITY_VALIDATION_CASES = (
    {
        "id": "low_profitability",
        "tickers": (
            "LoOP LoINV", "OP1 INV2", "OP1 INV3", "OP1 INV4",
            "LoOP HiINV", "OP2 INV1", "OP2 INV2", "OP2 INV3",
            "OP2 INV4", "OP2 INV5",
        ),
    },
    {
        "id": "high_profitability",
        "tickers": (
            "OP4 INV1", "OP4 INV2", "OP4 INV3", "OP4 INV4",
            "OP4 INV5", "HiOP LoINV", "OP5 INV2", "OP5 INV3",
            "OP5 INV4", "HiOP HiINV",
        ),
    },
    {
        "id": "low_investment",
        "tickers": (
            "LoOP LoINV", "OP1 INV2", "OP2 INV1", "OP2 INV2",
            "OP3 INV1", "OP3 INV2", "OP4 INV1", "OP4 INV2",
            "HiOP LoINV", "OP5 INV2",
        ),
    },
    {
        "id": "high_investment",
        "tickers": (
            "OP1 INV4", "LoOP HiINV", "OP2 INV4", "OP2 INV5",
            "OP3 INV4", "OP3 INV5", "OP4 INV4", "OP4 INV5",
            "OP5 INV4", "HiOP HiINV",
        ),
    },
)
VALUE_QUALITY_VALIDATION_CASES = (
    {
        "id": "low_value",
        "tickers": (
            "LoBM LoOP", "BM1 OP2", "BM1 OP3", "BM1 OP4",
            "LoBM HiOP", "BM2 OP1", "BM2 OP2", "BM2 OP3",
            "BM2 OP4", "BM2 OP5",
        ),
    },
    {
        "id": "high_value",
        "tickers": (
            "BM4 OP1", "BM4 OP2", "BM4 OP3", "BM4 OP4",
            "BM4 OP5", "HiBM LoOP", "BM5 OP2", "BM5 OP3",
            "BM5 OP4", "HiBM HiOP",
        ),
    },
    {
        "id": "low_profitability",
        "tickers": (
            "LoBM LoOP", "BM1 OP2", "BM2 OP1", "BM2 OP2",
            "BM3 OP1", "BM3 OP2", "BM4 OP1", "BM4 OP2",
            "HiBM LoOP", "BM5 OP2",
        ),
    },
    {
        "id": "high_profitability",
        "tickers": (
            "BM1 OP4", "LoBM HiOP", "BM2 OP4", "BM2 OP5",
            "BM3 OP4", "BM3 OP5", "BM4 OP4", "BM4 OP5",
            "BM5 OP4", "HiBM HiOP",
        ),
    },
)
NET_ISSUANCE_VALIDATION_CASES = (
    {
        "id": "small_size",
        "tickers": (
            "SMALL NegNI", "SMALL ZeroNI", "SMALL LoNI",
            "ME1 NI2", "ME1 NI3", "ME1 NI4", "SMALL HiNI",
            "ME2 NegNI", "ME2 ZeroNI", "ME2 LoNI",
            "ME2 NI2", "ME2 NI3", "ME2 NI4", "ME2 HiNI",
        ),
    },
    {
        "id": "large_size",
        "tickers": (
            "ME4 NegNI", "ME4 ZeroNI", "ME4 LoNI",
            "ME4 NI2", "ME4 NI3", "ME4 NI4", "ME4 HiNI",
            "BIG NegNI", "BIG ZeroNI", "BIG LoNI",
            "ME5 NI2", "ME5 NI3", "ME5 NI4", "BIG HiNI",
        ),
    },
    {
        "id": "low_net_issuance",
        "tickers": (
            "SMALL NegNI", "SMALL ZeroNI", "SMALL LoNI",
            "ME2 NegNI", "ME2 ZeroNI", "ME2 LoNI",
            "ME3 NegNI", "ME3 ZeroNI", "ME3 LoNI",
            "ME4 NegNI", "ME4 ZeroNI", "ME4 LoNI",
            "BIG NegNI", "BIG ZeroNI", "BIG LoNI",
        ),
    },
    {
        "id": "high_net_issuance",
        "tickers": (
            "ME1 NI3", "ME1 NI4", "SMALL HiNI",
            "ME2 NI3", "ME2 NI4", "ME2 HiNI",
            "ME3 NI3", "ME3 NI4", "ME3 HiNI",
            "ME4 NI3", "ME4 NI4", "ME4 HiNI",
            "ME5 NI3", "ME5 NI4", "BIG HiNI",
        ),
    },
)


def _candidate_name(args):
    if args.signal_kind == "net_issuance":
        return NET_ISSUANCE_CANDIDATE
    return (
        VALUE_QUALITY_CANDIDATE
        if args.signal_kind == "value_quality"
        else QUALITY_CANDIDATE
    )


def _validation_cases(args):
    if args.signal_kind == "net_issuance":
        return NET_ISSUANCE_VALIDATION_CASES
    return (
        VALUE_QUALITY_VALIDATION_CASES
        if args.signal_kind == "value_quality"
        else QUALITY_VALIDATION_CASES
    )


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _settings(args):
    candidate = _candidate_name(args)
    cases = _validation_cases(args)
    if args.signal_kind == "net_issuance":
        return {
            "train_window": int(args.train_window),
            "horizon": int(args.horizon),
            "rebalance_step": int(args.rebalance_step),
            "momentum_lookback": 12,
            "momentum_skip": 1,
            "momentum_weight": 0.50,
            "net_issuance_quality_weight": 0.50,
            "net_issuance_signal": (
                "inverse_official_annual_net_share_issues_bucket"
            ),
            "net_issuance_definition": (
                "change_in_log_split_adjusted_shares_outstanding_"
                "from_fiscal_t_minus_2_to_t_minus_1"
            ),
            "bucket_order_best_to_worst": [
                "NegNI",
                "ZeroNI",
                "LoNI",
                "NI2",
                "NI3",
                "NI4",
                "HiNI",
            ],
            "baseline": BASELINE,
            "bootstrap_samples": int(args.bootstrap_samples),
            "bootstrap_block_size": int(args.bootstrap_block_size),
            "bootstrap_minimum_probability": float(
                args.bootstrap_minimum_probability
            ),
            "minimum_case_periods": 10,
            "frozen_candidate_policy": {
                "source_split_id": str(args.frozen_from),
                "candidate": candidate,
                "candidate_specification": "unchanged",
            },
            "validation_cases": [
                {
                    "id": case["id"],
                    "tickers": list(case["tickers"]),
                }
                for case in cases
            ],
        }
    if args.signal_kind == "value_quality":
        return {
            "train_window": int(args.train_window),
            "horizon": int(args.horizon),
            "rebalance_step": int(args.rebalance_step),
            "momentum_lookback": 252,
            "momentum_skip": 21,
            "momentum_weight": 0.50,
            "value_weight": 0.25,
            "profitability_weight": 0.25,
            "value_signal": "official_annual_book_to_market_quintile",
            "profitability_signal": (
                "official_annual_operating_profitability_quintile"
            ),
            "baseline": BASELINE,
            "bootstrap_samples": int(args.bootstrap_samples),
            "bootstrap_block_size": int(args.bootstrap_block_size),
            "bootstrap_minimum_probability": float(
                args.bootstrap_minimum_probability
            ),
            "frozen_candidate_policy": {
                "source_split_id": str(args.frozen_from),
                "candidate": candidate,
                "candidate_specification": "unchanged",
            },
            "validation_cases": [
                {
                    "id": case["id"],
                    "tickers": list(case["tickers"]),
                }
                for case in cases
            ],
        }
    return {
        "train_window": int(args.train_window),
        "horizon": int(args.horizon),
        "rebalance_step": int(args.rebalance_step),
        "momentum_lookback": 252,
        "momentum_skip": 21,
        "momentum_weight": 0.50,
        "profitability_weight": 0.25,
        "conservative_investment_weight": 0.25,
        "profitability_signal": (
            "official_annual_operating_profitability_quintile"
        ),
        "investment_signal": (
            "inverse_official_annual_investment_quintile"
        ),
        "baseline": BASELINE,
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_block_size": int(args.bootstrap_block_size),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
        "frozen_candidate_policy": {
            "source_split_id": str(args.frozen_from),
            "candidate": candidate,
            "candidate_specification": "unchanged",
        },
        "validation_cases": [
            {
                "id": case["id"],
                "tickers": list(case["tickers"]),
            }
            for case in cases
        ],
    }


def _load_frozen_result(args):
    path = Path(args.frozen_result).expanduser().resolve()
    payload = _load_json(path)
    if payload.get("research_split") != args.frozen_from:
        raise ValueError(
            "Frozen result split does not match --frozen-from"
        )
    candidate = _candidate_name(args)
    if payload.get("candidate", {}).get("name") != candidate:
        raise ValueError("Frozen result candidate does not match")
    if not payload.get("promotion_eligible"):
        raise ValueError("Frozen result is not promotion eligible")
    frozen_settings = payload.get("settings", {})
    if args.signal_kind == "net_issuance":
        expected = {
            "momentum_weight": 0.50,
            "net_issuance_quality_weight": 0.50,
            "momentum_lookback": 12,
            "momentum_skip": 1,
        }
    elif args.signal_kind == "value_quality":
        expected = {
            "momentum_weight": 0.50,
            "profitability_weight": 0.25,
            "value_weight": 0.25,
            "momentum_lookback": 252,
            "momentum_skip": 21,
        }
    else:
        expected = {
            "momentum_weight": 0.50,
            "profitability_weight": 0.25,
            "conservative_investment_weight": 0.25,
            "momentum_lookback": 252,
            "momentum_skip": 21,
        }
    if any(frozen_settings.get(key) != value for key, value in expected.items()):
        raise ValueError("Frozen result candidate specification drifted")
    return payload, path, _sha256(path)


def _load_prices(args):
    path = Path(args.csv).expanduser().resolve()
    provenance_path = Path(
        args.price_provenance
    ).expanduser().resolve()
    provenance = _load_json(provenance_path)
    if provenance.get("price_file_sha256") != _sha256(path):
        raise ValueError("Price CSV SHA-256 does not match provenance")
    prices = pd.read_csv(path, index_col=0, parse_dates=True)
    if list(provenance.get("tickers") or []) != list(prices.columns):
        raise ValueError("Price provenance ticker order mismatch")
    cases = _validation_cases(args)
    required = {
        ticker
        for case in cases
        for ticker in case["tickers"]
    }
    missing = sorted(required - set(prices.columns))
    if missing:
        raise ValueError(
            "Validation price panel is missing: " + ", ".join(missing)
        )
    return prices, provenance, path, provenance_path


def _fundamental_signal(tickers, args):
    if args.signal_kind == "net_issuance":
        return net_issuance_quality_buckets(tickers)
    profitability = operating_profitability_buckets(tickers)
    return (
        0.50 * profitability
        + 0.50 * book_to_market_buckets(tickers)
        if args.signal_kind == "value_quality"
        else (
            0.50 * profitability
            + 0.50 * (6.0 - investment_buckets(tickers))
        )
    )


def _rank_results(prices, args):
    if args.signal_kind == "net_issuance":
        run_args = argparse.Namespace(**vars(args))
        run_args.momentum_lookback = 12
        run_args.momentum_skip = 1
        candidate_periods, _, baseline_periods = _run_issuance_periods(
            prices,
            _fundamental_signal(prices.columns, args),
            run_args,
        )
    else:
        candidate_periods, baseline_periods = _run_periods(
            prices,
            _fundamental_signal(prices.columns, args),
            args,
        )
    return {
        "candidate_periods": candidate_periods,
        "baseline_periods": baseline_periods,
        "candidate": cross_sectional_rank_diagnostics(
            candidate_periods
        ),
        "baseline": cross_sectional_rank_diagnostics(
            baseline_periods
        ),
    }


def _case_gate(result, minimum_periods=16):
    candidate = result["candidate"]
    baseline = result["baseline"]
    reasons = []
    if candidate["period_count"] < minimum_periods:
        reasons.append(
            f"Fewer than {minimum_periods} completed validation periods."
        )
    if candidate["mean_coverage_rate"] < 0.80:
        reasons.append("Candidate coverage is below 80%.")
    if candidate["mean_rank_ic"] <= 0.0:
        reasons.append("Candidate mean rank IC is not positive.")
    if candidate["mean_top_bottom_spread"] <= 0.0:
        reasons.append("Candidate top-bottom spread is not positive.")
    if candidate["mean_rank_ic"] <= baseline["mean_rank_ic"]:
        reasons.append("Candidate mean rank IC does not beat baseline.")
    if (
        candidate["mean_top_bottom_spread"]
        <= baseline["mean_top_bottom_spread"]
    ):
        reasons.append(
            "Candidate top-bottom spread does not beat baseline."
        )
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }


def _aggregate_gate(result, args):
    candidate_distribution = _distribution_diagnostics(
        result["candidate_periods"]
    )
    candidate_bootstrap = rank_signal_block_bootstrap(
        result["candidate_periods"],
        block_size=args.bootstrap_block_size,
        samples=args.bootstrap_samples,
        seed=42,
    )
    candidate_gate = signal_only_gate(
        result["candidate"],
        candidate_distribution,
        rank_bootstrap=candidate_bootstrap,
        minimum_bootstrap_probability=(
            args.bootstrap_minimum_probability
        ),
    )
    paired = paired_rank_signal_block_bootstrap(
        result["candidate_periods"],
        result["baseline_periods"],
        block_size=args.bootstrap_block_size,
        samples=args.bootstrap_samples,
        seed=44,
    )
    paired_gate_fn = (
        _issuance_paired_gate
        if args.signal_kind == "net_issuance"
        else _paired_gate
    )
    paired_gate, paired_holm = paired_gate_fn(
        paired,
        args.bootstrap_minimum_probability,
        _candidate_name(args),
    )
    reasons = (
        list(candidate_gate["reasons"])
        + list(paired_gate["reasons"])
    )
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "candidate_gate": candidate_gate,
        "candidate_bootstrap": candidate_bootstrap,
        "paired_gate": paired_gate,
        "paired_bootstrap": paired,
        "paired_holm": paired_holm,
    }


def _write_report(payload, output_path):
    if payload["candidate"] == NET_ISSUANCE_CANDIDATE:
        title = "# Frozen Net-Issuance Quality-Momentum Validation"
    elif payload["candidate"] == VALUE_QUALITY_CANDIDATE:
        title = "# Frozen Value-Quality-Momentum Validation"
    else:
        title = "# Frozen Quality-Momentum Validation"
    lines = [
        title,
        "",
        f"- Split: `{payload['validation_split']}`",
        f"- Frozen from: `{payload['frozen_from']}`",
        f"- Passed cases: {payload['passed_case_count']} / 4",
        f"- Aggregate gate: `{payload['aggregate_gate']['status']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Cases",
        "",
        (
            "| Case | Candidate IC | Baseline IC | Candidate spread | "
            "Baseline spread | Gate |"
        ),
        "|---|---:|---:|---:|---:|---|",
    ]
    for run in payload["case_runs"]:
        lines.append(
            "| {case} | {candidate_ic:.4f} | {baseline_ic:.4f} | "
            "{candidate_spread:.4f} | {baseline_spread:.4f} | "
            "{gate} |".format(
                case=run["case"]["id"],
                candidate_ic=run["candidate"]["mean_rank_ic"],
                baseline_ic=run["baseline"]["mean_rank_ic"],
                candidate_spread=run["candidate"][
                    "mean_top_bottom_spread"
                ],
                baseline_spread=run["baseline"][
                    "mean_top_bottom_spread"
                ],
                gate=run["gate"]["status"],
            )
        )
    paired = payload["aggregate_gate"]["paired_bootstrap"]
    probability = paired.get("probability", {})
    lines.extend([
        "",
        "## Aggregate",
        "",
        (
            "- P(higher mean rank IC): "
            f"`{probability.get('higher_mean_rank_ic', 0.0):.4f}`"
        ),
        (
            "- P(higher mean spread): "
            f"`{probability.get('higher_mean_top_bottom_spread', 0.0):.4f}`"
        ),
        (
            "- Holm-adjusted p-value: "
            f"`{payload['aggregate_gate']['paired_holm']['adjusted_p_value']:.4f}`"
        ),
        "",
        "## Decision",
        "",
        "- All four deterministic cases and aggregate statistical gate must pass.",
        "- 2012+ locked holdout remains sealed unless validation passes.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--signal-kind",
        choices=("quality", "value_quality", "net_issuance"),
        default="quality",
    )
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--validation-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--frozen-from", required=True)
    parser.add_argument("--frozen-result", required=True)
    parser.add_argument("--train-window", type=int, default=505)
    parser.add_argument("--horizon", type=int, default=63)
    parser.add_argument("--rebalance-step", type=int, default=63)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-block-size", type=int, default=4)
    parser.add_argument(
        "--bootstrap-minimum-probability",
        type=float,
        default=0.95,
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        frozen, frozen_path, frozen_sha = _load_frozen_result(args)
        candidate = _candidate_name(args)
        cases = _validation_cases(args)
        prices, provenance, price_path, provenance_path = (
            _load_prices(args)
        )
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.validation_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[candidate],
            settings=_settings(args),
            evaluation_start=prices.index[args.train_window],
            evaluation_end=prices.index[
                len(prices) - int(args.horizon) - 1
            ],
            universe_manifest_sha256=(
                provenance.get("universe_manifest_sha256")
                or provenance.get("basket_manifest_sha256")
            ),
            price_file_sha256=provenance.get("price_file_sha256"),
            factor_file_sha256=None,
            auxiliary_files={"frozen_result": frozen_sha},
        )
        if split["role"] != "validation":
            raise ValueError("Validation manifest role must be validation")

        aggregate_result = _rank_results(prices, args)
        aggregate_gate = _aggregate_gate(aggregate_result, args)
        case_runs = []
        minimum_case_periods = (
            10 if args.signal_kind == "net_issuance" else 16
        )
        for case in cases:
            case_result = _rank_results(
                prices.loc[:, list(case["tickers"])],
                args,
            )
            case_runs.append({
                "case": {
                    "id": case["id"],
                    "tickers": list(case["tickers"]),
                },
                "candidate": case_result["candidate"],
                "baseline": case_result["baseline"],
                "gate": _case_gate(
                    case_result,
                    minimum_periods=minimum_case_periods,
                ),
            })
        passed_case_count = sum(
            run["gate"]["status"] == "passed"
            for run in case_runs
        )
        validation_passed = bool(
            passed_case_count == len(cases)
            and aggregate_gate["status"] == "passed"
        )
        payload = {
            "validation_split": args.validation_split,
            "experiment_namespace": args.experiment_namespace,
            "frozen_from": args.frozen_from,
            "frozen_result": {
                "file": str(frozen_path),
                "sha256": frozen_sha,
                "promotion_eligible": frozen["promotion_eligible"],
            },
            "split": {
                **split,
                "file": str(split_path),
                "file_sha256": _sha256(split_path),
            },
            "data": {
                "price_file": str(price_path),
                "price_provenance_file": str(provenance_path),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
            },
            "settings": _settings(args),
            "candidate": candidate,
            "baseline": BASELINE,
            "passed_case_count": int(passed_case_count),
            "case_count": int(len(cases)),
            "aggregate_gate": aggregate_gate,
            "case_runs": case_runs,
            "aggregate_rank_diagnostics": {
                "candidate": aggregate_result["candidate"],
                "baseline": aggregate_result["baseline"],
            },
            "validation_passed": validation_passed,
            "promotion_eligible": bool(
                validation_passed
                and split.get("promotion_safe", False)
                and provenance.get("promotion_safe", False)
            ),
        }
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        report_path = _write_report(payload, output_path)
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
