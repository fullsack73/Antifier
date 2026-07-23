#!/usr/bin/env python3
"""Evaluate a locked 52-week-high and momentum rank blend."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
TOOLS = ROOT / "tools"
for path in (BACKEND, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from forecast_signal_research import (  # noqa: E402
    cross_sectional_rank_diagnostics,
    paired_rank_signal_block_bootstrap,
    rank_signal_block_bootstrap,
    signal_only_gate,
)
from portfolio_backtest import (  # noqa: E402
    PRICE_SIGNAL_TARGET_ACTIVE_SHARE,
    run_portfolio_model_backtest,
)
from portfolio_signals import (  # noqa: E402
    FIFTY_TWO_WEEK_HIGH_LOOKBACK_DAYS,
    HIGH_MOMENTUM_COMPONENT_WEIGHTS,
    MOMENTUM_LOOKBACK_DAYS,
    MOMENTUM_SKIP_DAYS,
)
from portfolio_statistics import (  # noqa: E402
    holm_bonferroni,
    paired_block_bootstrap,
)
from research_lightweight_uncertainty import (  # noqa: E402
    _fmt,
    _load_json,
    _load_prices,
    _load_risk_free,
    _sha256,
)
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "high_momentum_rank_tilt"
BASELINE = "momentum_12_1_rank_tilt"
MODELS = (
    "equal_weight",
    "risk_parity",
    BASELINE,
    CANDIDATE,
)


def _settings(args):
    return {
        "train_window": int(args.train_window),
        "rebalance_frequency": int(args.rebalance_frequency),
        "forecast_horizon": int(args.forecast_horizon),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "max_asset_weight": float(args.max_asset_weight),
        "rebalance_band": float(args.rebalance_band),
        "max_turnover": float(args.max_turnover),
        "bootstrap_samples": int(args.bootstrap_samples),
        "portfolio_bootstrap_block_size": int(
            args.portfolio_bootstrap_block_size
        ),
        "signal_bootstrap_block_size": int(
            args.signal_bootstrap_block_size
        ),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
        "candidate": CANDIDATE,
        "baseline": BASELINE,
        "models": list(MODELS),
        "signal_policy": {
            "momentum_lookback": MOMENTUM_LOOKBACK_DAYS,
            "momentum_skip": MOMENTUM_SKIP_DAYS,
            "fifty_two_week_high_lookback": (
                FIFTY_TWO_WEEK_HIGH_LOOKBACK_DAYS
            ),
            "component_weights": dict(
                HIGH_MOMENTUM_COMPONENT_WEIGHTS
            ),
            "component_transform": (
                "cross_sectional_rank_minus_one_to_one"
            ),
            "blend_transform": (
                "rerank_fixed_weight_component_average"
            ),
            "allocator": "equal_weight_active_share_rank_tilt",
            "target_active_share": float(
                PRICE_SIGNAL_TARGET_ACTIVE_SHARE
            ),
        },
    }


def _model_periods(result, model):
    periods = []
    coverage = []
    ties = []
    for record in result.get("rebalance_records", []):
        if record.get("model") != model:
            continue
        scores = record.get("signal_scores", {})
        realized = record.get("realized_forward_returns", {})
        periods.append({
            "period_id": record.get("rebalance_date"),
            "scores": scores,
            "realized_returns": realized,
        })
        finite = np.asarray(
            [
                value
                for value in scores.values()
                if value is not None and np.isfinite(value)
            ],
            dtype=float,
        )
        coverage.append(
            float(len(finite) / max(1, len(realized)))
        )
        ties.append(
            0.0
            if len(finite) == 0
            else float(
                1.0
                - len(np.unique(np.round(finite, 10)))
                / len(finite)
            )
        )
    return periods, {
        "coverage_rate": (
            0.0 if not coverage else float(np.mean(coverage))
        ),
        "boundary_saturation_rate": 0.0,
        "tie_rate": None if not ties else float(np.mean(ties)),
    }


def _signal_result(periods, distribution, args, seed):
    diagnostics = cross_sectional_rank_diagnostics(periods)
    bootstrap = rank_signal_block_bootstrap(
        periods,
        block_size=args.signal_bootstrap_block_size,
        samples=args.bootstrap_samples,
        seed=seed,
    )
    gate = signal_only_gate(
        diagnostics,
        distribution,
        rank_bootstrap=bootstrap,
        minimum_bootstrap_probability=(
            args.bootstrap_minimum_probability
        ),
    )
    return {
        "rank_diagnostics": diagnostics,
        "distribution_diagnostics": distribution,
        "bootstrap": bootstrap,
        "gate": gate,
        "periods": periods,
    }


def _deterministic_portfolio_gate(summary):
    candidate = summary[CANDIDATE]
    baseline = summary[BASELINE]
    equal = summary["equal_weight"]
    reasons = []
    if candidate["cagr"] <= baseline["cagr"]:
        reasons.append("CAGR does not improve raw momentum.")
    if (
        candidate["sharpe"] is None
        or baseline["sharpe"] is None
        or candidate["sharpe"] <= baseline["sharpe"]
    ):
        reasons.append("Sharpe does not improve raw momentum.")
    if candidate["max_drawdown"] < baseline["max_drawdown"]:
        reasons.append("Max drawdown is worse than raw momentum.")
    if (
        equal["sharpe"] is not None
        and candidate["sharpe"] <= equal["sharpe"]
    ):
        reasons.append("Sharpe does not beat equal weight.")
    if candidate["avg_controlled_turnover"] > max(
        0.50,
        1.25 * baseline["avg_controlled_turnover"],
    ):
        reasons.append("Turnover exceeds the frozen baseline guard.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }


def _combined_gate(
    candidate_signal,
    paired_signal,
    paired_portfolio,
    deterministic,
    minimum_probability,
):
    reasons = list(deterministic["reasons"])
    if candidate_signal["gate"]["status"] != "passed":
        reasons.extend(
            f"Absolute signal: {reason}"
            for reason in candidate_signal["gate"]["reasons"]
        )
    signal_probability = paired_signal.get("probability", {})
    portfolio_probability = paired_portfolio.get(
        "probability",
        {},
    )
    hypotheses = {
        "signal:higher_mean_rank_ic": signal_probability.get(
            "higher_mean_rank_ic"
        ),
        "signal:higher_mean_top_bottom_spread": (
            signal_probability.get(
                "higher_mean_top_bottom_spread"
            )
        ),
        "portfolio:higher_return": portfolio_probability.get(
            "higher_return"
        ),
        "portfolio:higher_sharpe": portfolio_probability.get(
            "higher_sharpe"
        ),
    }
    p_values = {
        name: (
            None if probability is None else 1.0 - probability
        )
        for name, probability in hypotheses.items()
    }
    for name, probability in hypotheses.items():
        if (
            probability is None
            or probability < minimum_probability
        ):
            reasons.append(
                f"{name} probability is below "
                f"{minimum_probability:.0%}."
            )
    holm = holm_bonferroni(
        p_values,
        alpha=1.0 - minimum_probability,
    )
    for name in hypotheses:
        if name not in holm or not holm[name]["significant"]:
            reasons.append(f"{name} fails Holm correction.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "hypothesis_probabilities": hypotheses,
    }, holm


def _write_report(payload, output_path):
    summary = payload["result"]["summary_by_model"]
    candidate = payload["candidate_signal"]["rank_diagnostics"]
    baseline = payload["baseline_signal"]["rank_diagnostics"]
    paired_signal = payload["paired_signal"].get(
        "probability",
        {},
    )
    paired_portfolio = payload["paired_portfolio"].get(
        "probability",
        {},
    )
    lines = [
        "# 52-Week-High Momentum Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Gate: `{payload['combined_gate']['status']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Signal",
        "",
        "| Signal | Periods | Mean rank IC | Positive IC | "
        "Mean top-bottom |",
        "|---|---:|---:|---:|---:|",
        "| Raw 12-1 momentum | {periods} | {ic} | {positive} | "
        "{spread} |".format(
            periods=baseline["period_count"],
            ic=_fmt(baseline["mean_rank_ic"]),
            positive=_fmt(baseline["positive_rank_ic_rate"]),
            spread=_fmt(baseline["mean_top_bottom_spread"]),
        ),
        "| 52-week-high blend | {periods} | {ic} | {positive} | "
        "{spread} |".format(
            periods=candidate["period_count"],
            ic=_fmt(candidate["mean_rank_ic"]),
            positive=_fmt(candidate["positive_rank_ic_rate"]),
            spread=_fmt(candidate["mean_top_bottom_spread"]),
        ),
        "",
        f"- P(higher IC): "
        f"`{_fmt(paired_signal.get('higher_mean_rank_ic'))}`",
        f"- P(higher spread): "
        f"`{_fmt(paired_signal.get('higher_mean_top_bottom_spread'))}`",
        "",
        "## Portfolio",
        "",
        "| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        metrics = summary[model]
        lines.append(
            "| {model} | {cagr} | {volatility} | {sharpe} | "
            "{drawdown} | {turnover} |".format(
                model=model,
                cagr=_fmt(metrics["cagr"]),
                volatility=_fmt(metrics["annual_volatility"]),
                sharpe=_fmt(metrics["sharpe"]),
                drawdown=_fmt(metrics["max_drawdown"]),
                turnover=_fmt(metrics["avg_controlled_turnover"]),
            )
        )
    lines.extend([
        "",
        f"- P(higher return): "
        f"`{_fmt(paired_portfolio.get('higher_return'))}`",
        f"- P(higher Sharpe): "
        f"`{_fmt(paired_portfolio.get('higher_sharpe'))}`",
        "",
        "## Guardrail",
        "",
        "- Component weights and horizons were locked before the run.",
        "- Candidate and raw momentum use identical rank-tilt construction.",
        "- Validation remains sealed unless absolute, paired, portfolio, "
        "and Holm gates all pass.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--risk-free-data", required=True)
    parser.add_argument("--risk-free-provenance", required=True)
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
    parser.add_argument("--forecast-horizon", type=int, default=63)
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=10.0,
    )
    parser.add_argument("--max-asset-weight", type=float, default=0.10)
    parser.add_argument("--rebalance-band", type=float, default=0.02)
    parser.add_argument("--max-turnover", type=float, default=0.35)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument(
        "--portfolio-bootstrap-block-size",
        type=int,
        default=21,
    )
    parser.add_argument(
        "--signal-bootstrap-block-size",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--bootstrap-minimum-probability",
        type=float,
        default=0.95,
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        prices, price_path, price_provenance_path, price_provenance = (
            _load_prices(args)
        )
        (
            risk_free,
            risk_free_path,
            risk_free_provenance_path,
            risk_free_provenance,
        ) = _load_risk_free(args, prices)
        settings = _settings(args)
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.research_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[CANDIDATE],
            settings=settings,
            evaluation_start=prices.index[args.train_window],
            evaluation_end=prices.index[-1],
            universe_manifest_sha256=price_provenance[
                "basket_manifest_sha256"
            ],
            price_file_sha256=price_provenance["price_file_sha256"],
            factor_file_sha256=risk_free_provenance[
                "factor_file_sha256"
            ],
            auxiliary_files={
                "price_provenance": _sha256(
                    price_provenance_path
                ),
                "risk_free_provenance": _sha256(
                    risk_free_provenance_path
                ),
            },
        )
        if split["role"] != "research":
            raise ValueError("Manifest role must be research")

        result = run_portfolio_model_backtest(
            prices,
            models=MODELS,
            train_window=args.train_window,
            rebalance_frequency=args.rebalance_frequency,
            forecast_horizon=args.forecast_horizon,
            transaction_cost_bps=args.transaction_cost_bps,
            max_asset_weight=args.max_asset_weight,
            rebalance_band=args.rebalance_band,
            max_turnover=args.max_turnover,
            include_daily_returns=True,
            risk_free_daily_returns=risk_free,
        )
        candidate_periods, candidate_distribution = _model_periods(
            result,
            CANDIDATE,
        )
        baseline_periods, baseline_distribution = _model_periods(
            result,
            BASELINE,
        )
        candidate_signal = _signal_result(
            candidate_periods,
            candidate_distribution,
            args,
            41,
        )
        baseline_signal = _signal_result(
            baseline_periods,
            baseline_distribution,
            args,
            42,
        )
        paired_signal = paired_rank_signal_block_bootstrap(
            candidate_periods,
            baseline_periods,
            block_size=args.signal_bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=43,
        )
        paired_portfolio = paired_block_bootstrap(
            result["daily_returns_by_model"][CANDIDATE],
            result["daily_returns_by_model"][BASELINE],
            risk_free_rate=result["settings"]["risk_free_rate"],
            block_size=args.portfolio_bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=44,
            risk_free_daily_returns=risk_free,
        )
        deterministic = _deterministic_portfolio_gate(
            result["summary_by_model"]
        )
        combined, holm = _combined_gate(
            candidate_signal,
            paired_signal,
            paired_portfolio,
            deterministic,
            args.bootstrap_minimum_probability,
        )
        promotion_eligible = bool(
            split["promotion_safe"]
            and combined["status"] == "passed"
        )
        result_for_output = {
            key: value
            for key, value in result.items()
            if key not in {
                "rebalance_records",
                "daily_returns_by_model",
            }
        }
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
                "risk_free_file": str(risk_free_path),
                "risk_free_provenance_file": str(
                    risk_free_provenance_path
                ),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
                "tickers": list(prices.columns),
            },
            "settings": settings,
            "candidate_signal": candidate_signal,
            "baseline_signal": baseline_signal,
            "paired_signal": paired_signal,
            "paired_portfolio": paired_portfolio,
            "deterministic_portfolio_gate": deterministic,
            "holm_gate": holm,
            "combined_gate": combined,
            "promotion_eligible": promotion_eligible,
            "result": result_for_output,
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
