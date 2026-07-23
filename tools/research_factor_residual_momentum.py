#!/usr/bin/env python3
"""Evaluate fixed FF3 residual momentum against raw 12-1 momentum."""

import argparse
import hashlib
import json
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
    factor_residual_momentum_scores,
    momentum_12_1,
)
from portfolio_statistics import holm_bonferroni  # noqa: E402
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "factor_residual_momentum"
BASELINE = "momentum_12_1"
REQUIRED_FACTOR_COLUMNS = ("mkt_rf", "smb", "hml", "rf_daily")


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _settings(args):
    return {
        "train_window": int(args.train_window),
        "horizon": int(args.horizon),
        "rebalance_step": int(args.rebalance_step),
        "beta_lookback": 504,
        "signal_lookback": 252,
        "signal_skip": 21,
        "factor_model": ["mkt_rf", "smb", "hml"],
        "risk_free_policy": "fama_french_daily_one_month_tbill",
        "baseline": BASELINE,
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_block_size": int(args.bootstrap_block_size),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
    }


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


def _load_factors(args):
    path = Path(args.factor_data).expanduser().resolve()
    provenance_path = Path(
        args.factor_provenance
    ).expanduser().resolve()
    provenance = _load_json(provenance_path)
    if provenance.get("factor_file_sha256") != _sha256(path):
        raise ValueError("Factor CSV SHA-256 does not match provenance")
    factors = pd.read_csv(path, index_col=0, parse_dates=True)
    missing = [
        column for column in REQUIRED_FACTOR_COLUMNS
        if column not in factors
    ]
    if missing:
        raise ValueError(
            "Factor CSV is missing: " + ", ".join(missing)
        )
    return factors, provenance, path, provenance_path


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


def _run_periods(prices, factors, args):
    candidate_periods = []
    baseline_periods = []
    signal_diagnostics = []
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
        train_factors = factors.loc[
            factors.index <= train_prices.index[-1]
        ]
        candidate_scores, diagnostics = (
            factor_residual_momentum_scores(
                train_prices,
                train_factors,
                beta_lookback=504,
                signal_lookback=252,
                skip=21,
            )
        )
        baseline_scores = momentum_12_1(train_prices)
        realized = (
            prices.iloc[position + int(args.horizon)]
            / prices.iloc[position]
            - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        period_id = as_of.strftime("%Y-%m-%d")
        candidate_periods.append({
            "period_id": period_id,
            "as_of_date": period_id,
            "forward_end_date": forward_end.strftime("%Y-%m-%d"),
            "scores": {
                str(ticker): float(value)
                for ticker, value in candidate_scores.dropna().items()
            },
            "realized_returns": {
                str(ticker): float(value)
                for ticker, value in realized.dropna().items()
            },
        })
        baseline_periods.append({
            "period_id": period_id,
            "as_of_date": period_id,
            "forward_end_date": forward_end.strftime("%Y-%m-%d"),
            "scores": {
                str(ticker): float(value)
                for ticker, value in baseline_scores.dropna().items()
            },
            "realized_returns": {
                str(ticker): float(value)
                for ticker, value in realized.dropna().items()
            },
        })
        signal_diagnostics.append({
            "period_id": period_id,
            "coverage_count": diagnostics.get("coverage_count", 0),
            "coverage_rate": diagnostics.get("coverage_rate", 0.0),
        })
    return candidate_periods, baseline_periods, signal_diagnostics


def _write_report(payload, output_path):
    candidate = payload["candidate"]
    baseline = payload["baseline"]
    paired = payload["paired_bootstrap"]
    lines = [
        "# Factor-Residual Momentum Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        f"- Candidate gate: `{candidate['gate']['status']}`",
        f"- Paired improvement gate: `{payload['paired_gate']['status']}`",
        "",
        "## Signal quality",
        "",
        "| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in ((CANDIDATE, candidate), (BASELINE, baseline)):
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
        "- Do not tune lookbacks or factor set on this result.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--factor-data", required=True)
    parser.add_argument("--factor-provenance", required=True)
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
        prices, price_provenance, price_path, price_provenance_path = (
            _load_prices(args)
        )
        factors, factor_provenance, factor_path, factor_provenance_path = (
            _load_factors(args)
        )
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.research_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[CANDIDATE],
            settings=_settings(args),
            evaluation_start=prices.index[args.train_window],
            evaluation_end=prices.index[
                len(prices) - int(args.horizon) - 1
            ],
            universe_manifest_sha256=price_provenance.get(
                "basket_manifest_sha256"
            ),
            price_file_sha256=price_provenance.get(
                "price_file_sha256"
            ),
            factor_file_sha256=factor_provenance.get(
                "factor_file_sha256"
            ),
            auxiliary_files={},
        )
        if split["role"] != "research":
            raise ValueError("Signal research manifest role must be research")

        candidate_periods, baseline_periods, signal_diagnostics = (
            _run_periods(prices, factors, args)
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
        candidate_gate = signal_only_gate(
            candidate_rank,
            candidate_distribution,
            rank_bootstrap=candidate_bootstrap,
            minimum_bootstrap_probability=(
                args.bootstrap_minimum_probability
            ),
        )
        baseline_gate = signal_only_gate(
            baseline_rank,
            baseline_distribution,
            rank_bootstrap=baseline_bootstrap,
            minimum_bootstrap_probability=(
                args.bootstrap_minimum_probability
            ),
        )
        paired = paired_rank_signal_block_bootstrap(
            candidate_periods,
            baseline_periods,
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=44,
        )
        paired_probability = paired.get("probability", {})
        paired_reasons = []
        if paired.get("status") != "ok":
            paired_reasons.append(
                "Insufficient paired dependent-period observations."
            )
            paired_p_value = 1.0
        else:
            if (
                paired_probability["higher_mean_rank_ic"]
                < args.bootstrap_minimum_probability
            ):
                paired_reasons.append(
                    "Paired rank-IC improvement probability is below 95%."
                )
            if (
                paired_probability["higher_mean_top_bottom_spread"]
                < args.bootstrap_minimum_probability
            ):
                paired_reasons.append(
                    "Paired spread improvement probability is below 95%."
                )
            paired_p_value = max(
                1.0 - paired_probability["higher_mean_rank_ic"],
                1.0
                - paired_probability[
                    "higher_mean_top_bottom_spread"
                ],
            )
        paired_holm = holm_bonferroni(
            {CANDIDATE: paired_p_value},
            alpha=0.05,
        )[CANDIDATE]
        if not paired_holm["significant"]:
            paired_reasons.append(
                "Paired improvement is not significant after Holm correction."
            )
        paired_gate = {
            "status": (
                "passed" if not paired_reasons else "rejected"
            ),
            "reasons": paired_reasons,
        }
        promotion_eligible = bool(
            candidate_gate["status"] == "passed"
            and paired_gate["status"] == "passed"
            and split.get("promotion_safe", False)
            and price_provenance.get("promotion_safe", False)
            and factor_provenance.get("promotion_safe", False)
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
                "price_provenance_file": str(
                    price_provenance_path
                ),
                "factor_file": str(factor_path),
                "factor_provenance_file": str(
                    factor_provenance_path
                ),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
            },
            "settings": _settings(args),
            "candidate": {
                "name": CANDIDATE,
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
            "signal_diagnostics": signal_diagnostics,
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
