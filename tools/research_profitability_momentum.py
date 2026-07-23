#!/usr/bin/env python3
"""Evaluate fixed fundamental-plus-momentum signals against raw momentum."""

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
    momentum_12_1,
    profitability_momentum_scores,
)
from portfolio_statistics import holm_bonferroni  # noqa: E402
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "profitability_momentum"
QUALITY_CANDIDATE = "quality_momentum"
VALUE_QUALITY_CANDIDATE = "value_quality_momentum"
BASELINE = "momentum_12_1"
MOMENTUM_WEIGHT = 0.50


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def operating_profitability_buckets(tickers):
    """Parse fixed OP quintiles from official French portfolio labels."""
    values = {}
    for ticker in tickers:
        label = str(ticker).strip()
        if "LoOP" in label:
            bucket = 1
        elif "HiOP" in label:
            bucket = 5
        else:
            match = re.search(r"\bOP([1-5])(?:\s|$)", label)
            if match is None:
                raise ValueError(
                    f"Cannot parse operating-profitability bucket: {label}"
                )
            bucket = int(match.group(1))
        values[label] = float(bucket)
    return pd.Series(values, dtype=float)


def investment_buckets(tickers):
    """Parse fixed investment quintiles from official French labels."""
    values = {}
    for ticker in tickers:
        label = str(ticker).strip()
        if "LoINV" in label:
            bucket = 1
        elif "HiINV" in label:
            bucket = 5
        else:
            match = re.search(r"\bINV([1-5])(?:\s|$)", label)
            if match is None:
                raise ValueError(
                    f"Cannot parse investment bucket: {label}"
                )
            bucket = int(match.group(1))
        values[label] = float(bucket)
    return pd.Series(values, dtype=float)


def book_to_market_buckets(tickers):
    """Parse fixed book-to-market quintiles from official French labels."""
    values = {}
    for ticker in tickers:
        label = str(ticker).strip()
        if "LoBM" in label:
            bucket = 1
        elif "HiBM" in label:
            bucket = 5
        else:
            match = re.search(r"\bBM([1-5])(?:\s|$)", label)
            if match is None:
                raise ValueError(
                    f"Cannot parse book-to-market bucket: {label}"
                )
            bucket = int(match.group(1))
        values[label] = float(bucket)
    return pd.Series(values, dtype=float)


def _candidate_name(args):
    if args.signal_kind == "quality":
        return QUALITY_CANDIDATE
    if args.signal_kind == "value_quality":
        return VALUE_QUALITY_CANDIDATE
    return CANDIDATE


def _settings(args):
    settings = {
        "train_window": int(args.train_window),
        "horizon": int(args.horizon),
        "rebalance_step": int(args.rebalance_step),
        "momentum_lookback": 252,
        "momentum_skip": 21,
        "momentum_weight": MOMENTUM_WEIGHT,
        "profitability_weight": 1.0 - MOMENTUM_WEIGHT,
        "profitability_signal": (
            "official_annual_operating_profitability_quintile"
        ),
        "baseline": BASELINE,
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_block_size": int(args.bootstrap_block_size),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
    }
    if args.signal_kind in {"quality", "value_quality"}:
        settings.pop("profitability_weight")
        settings["profitability_weight"] = 0.25
        if args.signal_kind == "quality":
            settings["conservative_investment_weight"] = 0.25
            settings["investment_signal"] = (
                "inverse_official_annual_investment_quintile"
            )
        else:
            settings["value_weight"] = 0.25
            settings["value_signal"] = (
                "official_annual_book_to_market_quintile"
            )
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
    coverage_rates = []
    tie_rates = []
    prediction_count = 0
    valid_count = 0
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


def _period_record(period_id, forward_end, scores, realized):
    return {
        "period_id": period_id,
        "as_of_date": period_id,
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


def _run_periods(prices, fundamental_signal, args):
    candidate_periods = []
    baseline_periods = []
    last_position = len(prices) - int(args.horizon) - 1
    for position in range(
        int(args.train_window),
        last_position + 1,
        int(args.rebalance_step),
    ):
        train_prices = prices.iloc[
            position - int(args.train_window):position
        ]
        as_of = prices.index[position]
        forward_end = prices.index[position + int(args.horizon)]
        candidate_scores = profitability_momentum_scores(
            train_prices,
            fundamental_signal,
            momentum_weight=MOMENTUM_WEIGHT,
        )
        baseline_scores = momentum_12_1(train_prices)
        realized = (
            prices.iloc[position + int(args.horizon)]
            / prices.iloc[position]
            - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        period_id = as_of.strftime("%Y-%m-%d")
        candidate_periods.append(
            _period_record(
                period_id,
                forward_end,
                candidate_scores,
                realized,
            )
        )
        baseline_periods.append(
            _period_record(
                period_id,
                forward_end,
                baseline_scores,
                realized,
            )
        )
    return candidate_periods, baseline_periods


def _paired_gate(paired, minimum_probability, candidate_name):
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
    holm = holm_bonferroni(
        {candidate_name: p_value},
        alpha=0.05,
    )[candidate_name]
    if not holm["significant"]:
        reasons.append(
            "Paired improvement is not significant after Holm correction."
        )
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }, holm


def _write_report(payload, output_path):
    candidate = payload["candidate"]
    baseline = payload["baseline"]
    paired = payload["paired_bootstrap"]
    candidate_name = candidate["name"]
    lines = [
        (
            "# Profitability-Momentum Research"
            if candidate_name == CANDIDATE
            else (
                "# Quality-Momentum Research"
                if candidate_name == QUALITY_CANDIDATE
                else "# Value-Quality-Momentum Research"
            )
        ),
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        f"- Candidate gate: `{candidate['gate']['status']}`",
        f"- Paired improvement gate: `{payload['paired_gate']['status']}`",
        "",
        "## Signal quality",
        "",
        (
            "| Signal | Periods | Mean rank IC | Positive IC | "
            "Mean top-bottom | P(IC>0) | P(spread>0) |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in ((candidate_name, candidate), (BASELINE, baseline)):
        rank = result["rank_diagnostics"]
        probability = result["bootstrap"].get("probability", {})
        lines.append(
            "| {name} | {periods} | {ic:.4f} | {positive:.4f} | "
            "{spread:.4f} | {p_ic:.4f} | {p_spread:.4f} |".format(
                name=name,
                periods=rank["period_count"],
                ic=rank["mean_rank_ic"],
                positive=rank["positive_rank_ic_rate"],
                spread=rank["mean_top_bottom_spread"],
                p_ic=probability.get("positive_mean_rank_ic", 0.0),
                p_spread=probability.get(
                    "positive_mean_top_bottom_spread",
                    0.0,
                ),
            )
        )
    paired_probability = paired.get("probability", {})
    lines.extend([
        "",
        "## Paired candidate minus baseline",
        "",
        (
            "- Mean rank IC difference: "
            f"`{paired['observed_difference']['mean_rank_ic']:.4f}`"
        ),
        (
            "- Mean top-bottom difference: "
            f"`{paired['observed_difference']['mean_top_bottom_spread']:.4f}`"
        ),
        (
            "- P(higher mean rank IC): "
            f"`{paired_probability['higher_mean_rank_ic']:.4f}`"
        ),
        (
            "- P(higher mean spread): "
            f"`{paired_probability['higher_mean_top_bottom_spread']:.4f}`"
        ),
        (
            "- Holm-adjusted p-value: "
            f"`{payload['paired_holm']['adjusted_p_value']:.4f}`"
        ),
        "",
        "## Guardrail",
        "",
        "- Portfolio validation is allowed only if candidate and paired gates pass.",
        "- Do not tune blend weight, lookback, skip, or horizon on this result.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--signal-kind",
        choices=("profitability", "quality", "value_quality"),
        default="profitability",
    )
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
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
        prices, provenance, price_path, provenance_path = (
            _load_prices(args)
        )
        candidate_name = _candidate_name(args)
        profitability = operating_profitability_buckets(prices.columns)
        investment = (
            investment_buckets(prices.columns)
            if args.signal_kind == "quality"
            else None
        )
        book_to_market = (
            book_to_market_buckets(prices.columns)
            if args.signal_kind == "value_quality"
            else None
        )
        fundamental_signal = (
            profitability
            if investment is None and book_to_market is None
            else (
                0.50 * profitability + 0.50 * (6.0 - investment)
                if investment is not None
                else 0.50 * profitability + 0.50 * book_to_market
            )
        )
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.research_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[candidate_name],
            settings=_settings(args),
            evaluation_start=prices.index[args.train_window],
            evaluation_end=prices.index[
                len(prices) - int(args.horizon) - 1
            ],
            universe_manifest_sha256=provenance.get(
                "basket_manifest_sha256"
            ),
            price_file_sha256=provenance.get("price_file_sha256"),
            factor_file_sha256=None,
            auxiliary_files={},
        )
        if split["role"] != "research":
            raise ValueError("Signal research manifest role must be research")

        candidate_periods, baseline_periods = _run_periods(
            prices,
            fundamental_signal,
            args,
        )
        candidate_rank = cross_sectional_rank_diagnostics(
            candidate_periods
        )
        baseline_rank = cross_sectional_rank_diagnostics(
            baseline_periods
        )
        candidate_distribution = _distribution_diagnostics(
            candidate_periods
        )
        baseline_distribution = _distribution_diagnostics(
            baseline_periods
        )
        candidate_bootstrap = rank_signal_block_bootstrap(
            candidate_periods,
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=42,
        )
        baseline_bootstrap = rank_signal_block_bootstrap(
            baseline_periods,
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=43,
        )
        minimum_probability = float(
            args.bootstrap_minimum_probability
        )
        candidate_gate = signal_only_gate(
            candidate_rank,
            candidate_distribution,
            rank_bootstrap=candidate_bootstrap,
            minimum_bootstrap_probability=minimum_probability,
        )
        baseline_gate = signal_only_gate(
            baseline_rank,
            baseline_distribution,
            rank_bootstrap=baseline_bootstrap,
            minimum_bootstrap_probability=minimum_probability,
        )
        paired = paired_rank_signal_block_bootstrap(
            candidate_periods,
            baseline_periods,
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=44,
        )
        paired_gate, paired_holm = _paired_gate(
            paired,
            minimum_probability,
            candidate_name,
        )
        promotion_eligible = bool(
            candidate_gate["status"] == "passed"
            and paired_gate["status"] == "passed"
            and split.get("promotion_safe", False)
            and provenance.get("promotion_safe", False)
        )
        payload = {
            "research_split": args.research_split,
            "experiment_namespace": args.experiment_namespace,
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
                "portfolio_profitability_buckets": {
                    ticker: int(value)
                    for ticker, value in profitability.items()
                },
                **(
                    {}
                    if investment is None
                    else {
                        "portfolio_investment_buckets": {
                        ticker: int(value)
                        for ticker, value in investment.items()
                        }
                    }
                ),
                **(
                    {}
                    if book_to_market is None
                    else {
                        "portfolio_book_to_market_buckets": {
                            ticker: int(value)
                            for ticker, value in book_to_market.items()
                        }
                    }
                ),
            },
            "settings": _settings(args),
            "candidate": {
                "name": candidate_name,
                "rank_diagnostics": candidate_rank,
                "distribution_diagnostics": candidate_distribution,
                "bootstrap": candidate_bootstrap,
                "gate": candidate_gate,
                "periods": candidate_periods,
            },
            "baseline": {
                "name": BASELINE,
                "rank_diagnostics": baseline_rank,
                "distribution_diagnostics": baseline_distribution,
                "bootstrap": baseline_bootstrap,
                "gate": baseline_gate,
                "periods": baseline_periods,
            },
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
