#!/usr/bin/env python3
"""Evaluate fixed characteristic-quality plus momentum against momentum."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from forecast_signal_research import (  # noqa: E402
    cross_sectional_rank_diagnostics,
    paired_rank_signal_block_bootstrap,
    rank_signal_block_bootstrap,
    signal_only_gate,
)
from portfolio_signals import (  # noqa: E402
    momentum_rank,
    rank_to_unit_scores,
)
from portfolio_statistics import holm_bonferroni  # noqa: E402
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "accrual_quality_momentum"
BASELINE = "momentum_12_1"
DIAGNOSTIC = "accrual_quality"
NET_ISSUANCE_CANDIDATE = "net_issuance_quality_momentum"
NET_ISSUANCE_DIAGNOSTIC = "net_issuance_quality"
RESIDUAL_VARIANCE_CANDIDATE = "low_residual_variance_momentum"
RESIDUAL_VARIANCE_DIAGNOSTIC = "low_residual_variance"
MOMENTUM_WEIGHT = 0.50


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def accrual_quality_buckets(tickers):
    """Parse inverse accrual quintiles from official French labels."""
    values = {}
    for ticker in tickers:
        label = str(ticker).strip()
        if "LoAC" in label:
            accrual_bucket = 1
        elif "HiAC" in label:
            accrual_bucket = 5
        else:
            match = re.search(r"\bAC([1-5])(?:\s|$)", label)
            if match is None:
                raise ValueError(
                    f"Cannot parse accrual bucket: {label}"
                )
            accrual_bucket = int(match.group(1))
        values[label] = float(6 - accrual_bucket)
    return pd.Series(values, dtype=float)


def net_issuance_quality_buckets(tickers):
    """Parse conservative net-share-issuance buckets from French labels."""
    values = {}
    for ticker in tickers:
        label = str(ticker).strip()
        if "NegNI" in label:
            quality_bucket = 7
        elif "ZeroNI" in label:
            quality_bucket = 6
        elif "LoNI" in label:
            quality_bucket = 5
        elif "HiNI" in label:
            quality_bucket = 1
        else:
            match = re.search(r"\bNI([2-4])(?:\s|$)", label)
            if match is None:
                raise ValueError(
                    f"Cannot parse net-share-issuance bucket: {label}"
                )
            quality_bucket = 6 - int(match.group(1))
        values[label] = float(quality_bucket)
    return pd.Series(values, dtype=float)


def residual_variance_quality_buckets(tickers):
    """Parse inverse FF3 residual-variance quintiles from French labels."""
    values = {}
    for ticker in tickers:
        label = str(ticker).strip()
        if "LoVAR" in label:
            variance_bucket = 1
        elif "HiVAR" in label:
            variance_bucket = 5
        else:
            match = re.search(r"\bVAR([1-5])(?:\s|$)", label)
            if match is None:
                raise ValueError(
                    f"Cannot parse residual-variance bucket: {label}"
                )
            variance_bucket = int(match.group(1))
        values[label] = float(6 - variance_bucket)
    return pd.Series(values, dtype=float)


def _signal_kind(args):
    return str(getattr(args, "signal_kind", "accrual"))


def _candidate_name(args):
    return {
        "accrual": CANDIDATE,
        "net_issuance": NET_ISSUANCE_CANDIDATE,
        "residual_variance": RESIDUAL_VARIANCE_CANDIDATE,
    }[_signal_kind(args)]


def _diagnostic_name(args):
    return {
        "accrual": DIAGNOSTIC,
        "net_issuance": NET_ISSUANCE_DIAGNOSTIC,
        "residual_variance": RESIDUAL_VARIANCE_DIAGNOSTIC,
    }[_signal_kind(args)]


def _settings(args):
    settings = {
        "train_window": int(args.train_window),
        "horizon": int(args.horizon),
        "rebalance_step": int(args.rebalance_step),
        "momentum_lookback": int(args.momentum_lookback),
        "momentum_skip": int(args.momentum_skip),
        "momentum_weight": MOMENTUM_WEIGHT,
        "primary_candidate": _candidate_name(args),
        "diagnostic_signal": _diagnostic_name(args),
        "baseline": BASELINE,
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_block_size": int(args.bootstrap_block_size),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
    }
    if _signal_kind(args) == "net_issuance":
        settings.update({
            "net_issuance_quality_weight": 1.0 - MOMENTUM_WEIGHT,
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
        })
    elif _signal_kind(args) == "residual_variance":
        settings.update({
            "low_residual_variance_weight": 1.0 - MOMENTUM_WEIGHT,
            "residual_variance_signal": (
                "inverse_official_monthly_ff3_residual_variance_quintile"
            ),
            "residual_variance_definition": (
                "variance_of_ff3_residuals_from_60_lagged_daily_returns_"
                "minimum_20"
            ),
            "bucket_order_best_to_worst": [
                "LoVAR",
                "VAR2",
                "VAR3",
                "VAR4",
                "HiVAR",
            ],
        })
    else:
        settings.update({
            "accrual_quality_weight": 1.0 - MOMENTUM_WEIGHT,
            "accrual_signal": (
                "inverse_official_annual_working_capital_accrual_quintile"
            ),
            "accrual_definition": (
                "change_in_operating_working_capital_divided_by_"
                "book_equity"
            ),
        })
    return settings


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
    return prices, provenance, path, provenance_path


def _distribution_diagnostics(periods):
    prediction_count = 0
    valid_count = 0
    coverage_rates = []
    tie_rates = []
    for period in periods:
        scores = pd.Series(period["scores"], dtype=float)
        valid = scores.replace([np.inf, -np.inf], np.nan).dropna()
        prediction_count += int(len(scores))
        valid_count += int(len(valid))
        coverage_rates.append(
            float(len(valid) / len(scores)) if len(scores) else 0.0
        )
        tie_rates.append(
            0.0
            if valid.empty
            else float(1.0 - valid.nunique() / len(valid))
        )
    return {
        "prediction_count": prediction_count,
        "valid_count": valid_count,
        "coverage_rate": (
            0.0
            if prediction_count == 0
            else float(valid_count / prediction_count)
        ),
        "active_universe_coverage_rate": (
            0.0 if not coverage_rates else float(np.mean(coverage_rates))
        ),
        "boundary_saturation_rate": None,
        "tie_rate": (
            None if not tie_rates else float(np.mean(tie_rates))
        ),
    }


def _period_record(as_of, forward_end, scores, realized):
    return {
        "period_id": as_of.strftime("%Y-%m-%d"),
        "as_of_date": as_of.strftime("%Y-%m-%d"),
        "forward_end_date": forward_end.strftime("%Y-%m-%d"),
        "scores": {
            str(ticker): float(value)
            for ticker, value in scores.dropna().items()
        },
        "realized_returns": {
            str(ticker): float(value)
            for ticker, value in realized.dropna().items()
        },
    }


def _evaluation_positions(prices, args):
    last_position = len(prices) - int(args.horizon) - 1
    positions = list(
        range(
            int(args.train_window),
            last_position + 1,
            int(args.rebalance_step),
        )
    )
    if not positions:
        raise ValueError("No evaluation positions for requested settings")
    return positions


def _run_periods(prices, accrual_quality, args):
    candidate_periods = []
    diagnostic_periods = []
    baseline_periods = []
    for position in _evaluation_positions(prices, args):
        train_prices = prices.iloc[
            position - int(args.train_window):position
        ]
        momentum = momentum_rank(
            train_prices,
            lookback=args.momentum_lookback,
            skip=args.momentum_skip,
        )
        accrual = rank_to_unit_scores(
            accrual_quality,
            higher_is_better=True,
        ).reindex(prices.columns)
        combined = rank_to_unit_scores(
            MOMENTUM_WEIGHT * momentum
            + (1.0 - MOMENTUM_WEIGHT) * accrual,
            higher_is_better=True,
        ).reindex(prices.columns)
        realized = (
            prices.iloc[position + int(args.horizon)]
            / prices.iloc[position]
            - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        as_of = prices.index[position]
        forward_end = prices.index[position + int(args.horizon)]
        candidate_periods.append(
            _period_record(as_of, forward_end, combined, realized)
        )
        diagnostic_periods.append(
            _period_record(as_of, forward_end, accrual, realized)
        )
        baseline_periods.append(
            _period_record(as_of, forward_end, momentum, realized)
        )
    return candidate_periods, diagnostic_periods, baseline_periods


def _signal_result(name, periods, args, seed):
    rank = cross_sectional_rank_diagnostics(periods)
    distribution = _distribution_diagnostics(periods)
    bootstrap = rank_signal_block_bootstrap(
        periods,
        block_size=args.bootstrap_block_size,
        samples=args.bootstrap_samples,
        seed=seed,
    )
    gate = signal_only_gate(
        rank,
        distribution,
        rank_bootstrap=bootstrap,
        minimum_bootstrap_probability=(
            args.bootstrap_minimum_probability
        ),
    )
    return {
        "name": name,
        "rank_diagnostics": rank,
        "distribution_diagnostics": distribution,
        "bootstrap": bootstrap,
        "gate": gate,
        "periods": periods,
    }


def _paired_gate(paired, minimum_probability, candidate_name=CANDIDATE):
    probability = paired.get("probability", {})
    reasons = []
    if paired.get("status") != "ok":
        reasons.append(
            "Insufficient paired dependent-period observations."
        )
        p_value = 1.0
    else:
        if (
            probability["higher_mean_rank_ic"]
            < minimum_probability
        ):
            reasons.append(
                "Paired rank-IC improvement probability is below 95%."
            )
        if (
            probability["higher_mean_top_bottom_spread"]
            < minimum_probability
        ):
            reasons.append(
                "Paired spread improvement probability is below 95%."
            )
        p_value = max(
            1.0 - probability["higher_mean_rank_ic"],
            1.0
            - probability["higher_mean_top_bottom_spread"],
        )
    holm = holm_bonferroni({candidate_name: p_value}, alpha=0.05)[
        candidate_name
    ]
    if not holm["significant"]:
        reasons.append(
            "Paired improvement is not significant after Holm correction."
        )
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }, holm


def _fmt(value):
    return "n/a" if value is None else f"{float(value):.4f}"


def _write_report(payload, output_path):
    net_issuance = payload["feature_kind"] == "net_issuance"
    residual_variance = payload["feature_kind"] == "residual_variance"
    if net_issuance:
        title = "# Net-Issuance Quality Momentum Research"
    elif residual_variance:
        title = "# Low Residual-Variance Momentum Research"
    else:
        title = "# Accrual-Quality Momentum Research"
    lines = [
        title,
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        *(
            []
            if net_issuance or residual_variance
            else [
                (
                    "- Economic benchmark only: French working-capital "
                    "accrual is related to, but not identical with, SEC "
                    "cash-accrual quality."
                )
            ]
        ),
        "",
        "## Signal quality",
        "",
        (
            "| Signal | Periods | Mean rank IC | Positive IC | "
            "Mean top-bottom | P(IC>0) | P(spread>0) | Gate |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key in ("candidate", "diagnostic", "baseline"):
        result = payload[key]
        rank = result["rank_diagnostics"]
        probability = result["bootstrap"].get("probability", {})
        lines.append(
            "| {name} | {periods} | {ic} | {positive} | "
            "{spread} | {p_ic} | {p_spread} | {gate} |".format(
                name=result["name"],
                periods=rank["period_count"],
                ic=_fmt(rank["mean_rank_ic"]),
                positive=_fmt(rank["positive_rank_ic_rate"]),
                spread=_fmt(rank["mean_top_bottom_spread"]),
                p_ic=_fmt(probability.get("positive_mean_rank_ic")),
                p_spread=_fmt(
                    probability.get(
                        "positive_mean_top_bottom_spread"
                    )
                ),
                gate=result["gate"]["status"],
            )
        )
    paired = payload["paired_bootstrap"]
    probability = paired.get("probability", {})
    lines.extend([
        "",
        "## Candidate minus momentum",
        "",
        (
            "- Mean rank IC difference: "
            f"`{_fmt(paired['observed_difference']['mean_rank_ic'])}`"
        ),
        (
            "- Mean top-bottom difference: "
            f"`{_fmt(paired['observed_difference']['mean_top_bottom_spread'])}`"
        ),
        (
            "- P(higher mean rank IC): "
            f"`{_fmt(probability.get('higher_mean_rank_ic'))}`"
        ),
        (
            "- P(higher mean spread): "
            f"`{_fmt(probability.get('higher_mean_top_bottom_spread'))}`"
        ),
        (
            "- Paired gate: "
            f"`{payload['paired_gate']['status']}`"
        ),
        "",
        "## Guardrail",
        "",
        "- 2000+ validation and holdout remain sealed after this research.",
        "- Do not tune blend weight, horizon, or rebalance step on this result.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument(
        "--signal-kind",
        choices=("accrual", "net_issuance", "residual_variance"),
        default="accrual",
    )
    parser.add_argument("--train-window", type=int, default=72)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--rebalance-step", type=int, default=12)
    parser.add_argument("--momentum-lookback", type=int, default=12)
    parser.add_argument("--momentum-skip", type=int, default=1)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-block-size", type=int, default=3)
    parser.add_argument(
        "--bootstrap-minimum-probability",
        type=float,
        default=0.95,
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        prices, provenance, price_path, provenance_path = (
            _load_prices(args)
        )
        quality_loader = {
            "accrual": accrual_quality_buckets,
            "net_issuance": net_issuance_quality_buckets,
            "residual_variance": residual_variance_quality_buckets,
        }[args.signal_kind]
        quality = quality_loader(prices.columns)
        candidate_name = _candidate_name(args)
        diagnostic_name = _diagnostic_name(args)
        positions = _evaluation_positions(prices, args)
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.research_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[candidate_name],
            settings=_settings(args),
            evaluation_start=prices.index[positions[0]],
            evaluation_end=prices.index[positions[-1]],
            universe_manifest_sha256=(
                provenance.get("universe_manifest_sha256")
                or provenance.get("basket_manifest_sha256")
            ),
            price_file_sha256=provenance.get("price_file_sha256"),
            factor_file_sha256=None,
            auxiliary_files={},
        )
        if split["role"] != "research":
            raise ValueError("Signal research manifest role must be research")
        (
            candidate_periods,
            diagnostic_periods,
            baseline_periods,
        ) = _run_periods(prices, quality, args)
        candidate = _signal_result(
            candidate_name,
            candidate_periods,
            args,
            seed=42,
        )
        diagnostic = _signal_result(
            diagnostic_name,
            diagnostic_periods,
            args,
            seed=43,
        )
        baseline = _signal_result(
            BASELINE,
            baseline_periods,
            args,
            seed=44,
        )
        paired = paired_rank_signal_block_bootstrap(
            candidate_periods,
            baseline_periods,
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=45,
        )
        paired_gate, paired_holm = _paired_gate(
            paired,
            args.bootstrap_minimum_probability,
            candidate_name=candidate_name,
        )
        promotion_eligible = bool(
            candidate["gate"]["status"] == "passed"
            and paired_gate["status"] == "passed"
            and split.get("promotion_safe", False)
            and provenance.get("promotion_safe", False)
        )
        payload = {
            "research_split": args.research_split,
            "experiment_namespace": args.experiment_namespace,
            "feature_kind": args.signal_kind,
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
                {
                    "accrual": "portfolio_accrual_quality_buckets",
                    "net_issuance": (
                        "portfolio_net_issuance_quality_buckets"
                    ),
                    "residual_variance": (
                        "portfolio_residual_variance_quality_buckets"
                    ),
                }[args.signal_kind]: {
                    ticker: int(value)
                    for ticker, value in quality.items()
                },
            },
            "settings": _settings(args),
            "candidate": candidate,
            "diagnostic": diagnostic,
            "baseline": baseline,
            "paired_bootstrap": paired,
            "paired_holm": paired_holm,
            "paired_gate": paired_gate,
            "promotion_eligible": promotion_eligible,
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
