#!/usr/bin/env python3
"""Audit magnitude-free lightweight forecast ranks as a portfolio tilt."""

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
    rank_signal_block_bootstrap,
    signal_only_gate,
)
from portfolio_backtest import (  # noqa: E402
    LIGHTWEIGHT_RANK_TARGET_ACTIVE_SHARE,
    run_portfolio_model_backtest,
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


CANDIDATE = "lightweight_rank_tilt"
BASELINE = "lightweight_bl"
PORTFOLIO_BASELINES = (BASELINE, "equal_weight")
MODELS = (
    "equal_weight",
    "risk_parity",
    "historical_bl",
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
        "primary_baseline": BASELINE,
        "portfolio_baselines": list(PORTFOLIO_BASELINES),
        "models": list(MODELS),
        "construction": {
            "point_forecast": "unchanged_lightweight_ensemble",
            "magnitude_policy": "cross_sectional_rank_only",
            "allocator": "equal_weight_active_share_tilt",
            "target_active_share": float(
                LIGHTWEIGHT_RANK_TARGET_ACTIVE_SHARE
            ),
        },
    }


def _candidate_periods(result):
    periods = []
    coverage = []
    ties = []
    for record in result.get("rebalance_records", []):
        if record.get("model") != CANDIDATE:
            continue
        scores = record.get("signal_scores", {})
        realized = record.get("realized_forward_returns", {})
        periods.append({
            "period_id": record.get("rebalance_date"),
            "scores": scores,
            "realized_returns": realized,
        })
        score_values = np.asarray(
            [
                value
                for value in scores.values()
                if value is not None and np.isfinite(value)
            ],
            dtype=float,
        )
        universe_count = max(1, len(realized))
        coverage.append(float(len(score_values) / universe_count))
        ties.append(
            0.0
            if len(score_values) == 0
            else float(
                1.0
                - len(np.unique(np.round(score_values, 10)))
                / len(score_values)
            )
        )
    return periods, {
        "coverage_rate": (
            0.0 if not coverage else float(np.mean(coverage))
        ),
        "boundary_saturation_rate": 0.0,
        "tie_rate": None if not ties else float(np.mean(ties)),
    }


def _deterministic_gate(summary, signal_gate):
    candidate = summary[CANDIDATE]
    baseline = summary[BASELINE]
    reasons = []
    for baseline_name in (
        BASELINE,
        "equal_weight",
        "risk_parity",
        "historical_bl",
    ):
        comparison = summary[baseline_name]
        if candidate["sharpe"] <= comparison["sharpe"]:
            reasons.append(f"Sharpe does not beat {baseline_name}.")
        if candidate["max_drawdown"] < comparison["max_drawdown"]:
            reasons.append(
                f"Max drawdown is worse than {baseline_name}."
            )
    if candidate["cagr"] <= baseline["cagr"]:
        reasons.append("CAGR does not improve current lightweight BL.")
    if candidate["cagr"] <= summary["equal_weight"]["cagr"]:
        reasons.append("CAGR does not beat equal weight.")
    if candidate["avg_controlled_turnover"] > max(
        0.50,
        baseline["avg_controlled_turnover"] * 1.25,
    ):
        reasons.append("Turnover exceeds the predeclared baseline guard.")
    if candidate.get("failed_forecast_count", 0) > 0:
        reasons.append("Candidate produced no-view forecasts.")
    if signal_gate["status"] != "passed":
        reasons.extend(
            f"Signal gate: {reason}"
            for reason in signal_gate["reasons"]
        )
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }


def _portfolio_statistical_gate(
    result,
    risk_free,
    args,
):
    daily_returns = result["daily_returns_by_model"]
    paired = {}
    p_values = {}
    reasons = []
    for index, baseline in enumerate(PORTFOLIO_BASELINES):
        comparison = paired_block_bootstrap(
            daily_returns[CANDIDATE],
            daily_returns[baseline],
            risk_free_rate=result["settings"]["risk_free_rate"],
            block_size=args.portfolio_bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=42 + index,
            risk_free_daily_returns=risk_free,
        )
        paired[baseline] = comparison
        probability = comparison.get("probability", {})
        for objective in ("higher_return", "higher_sharpe"):
            value = probability.get(objective)
            key = f"{baseline}:{objective}"
            p_values[key] = None if value is None else 1.0 - value
            if (
                value is None
                or value < args.bootstrap_minimum_probability
            ):
                reasons.append(
                    f"{key} probability is below "
                    f"{args.bootstrap_minimum_probability:.0%}."
                )
    holm = holm_bonferroni(
        p_values,
        alpha=1.0 - args.bootstrap_minimum_probability,
    )
    for objective in p_values:
        if objective not in holm or not holm[objective]["significant"]:
            reasons.append(f"{objective} fails Holm correction.")
    return paired, holm, {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }


def _write_report(payload, output_path):
    summary = payload["result"]["summary_by_model"]
    signal = payload["signal_diagnostics"]
    lines = [
        "# Lightweight Rank-Tilt Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Rows/tickers: `{payload['data']['row_count']}` / "
        f"`{payload['data']['ticker_count']}`",
        f"- Signal gate: `{payload['signal_gate']['status']}`",
        f"- Portfolio gate: `{payload['portfolio_gate']['status']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Performance",
        "",
        "| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        metrics = summary[model]
        lines.append(
            "| {model} | {cagr} | {volatility} | {sharpe} | "
            "{drawdown} | {turnover} |".format(
                model=model,
                cagr=_fmt(metrics.get("cagr")),
                volatility=_fmt(metrics.get("annual_volatility")),
                sharpe=_fmt(metrics.get("sharpe")),
                drawdown=_fmt(metrics.get("max_drawdown")),
                turnover=_fmt(metrics.get("avg_controlled_turnover")),
            )
        )
    lines.extend([
        "",
        "## Signal",
        "",
        f"- Mean rank IC: `{_fmt(signal.get('mean_rank_ic'))}`",
        f"- Positive rank-IC rate: "
        f"`{_fmt(signal.get('positive_rank_ic_rate'))}`",
        f"- Mean top-bottom spread: "
        f"`{_fmt(signal.get('mean_top_bottom_spread'))}`",
    ])
    for baseline in PORTFOLIO_BASELINES:
        probability = payload["paired_bootstrap"][baseline].get(
            "probability",
            {},
        )
        lines.extend([
            "",
            f"## Paired vs {baseline}",
            "",
            f"- P(higher return): "
            f"`{_fmt(probability.get('higher_return'))}`",
            f"- P(higher Sharpe): "
            f"`{_fmt(probability.get('higher_sharpe'))}`",
        ])
    lines.extend([
        "",
        "## Guardrail",
        "",
        "- Existing lightweight point forecasts are unchanged.",
        "- Cross-sectional order is the only forecast input to weights.",
        "- Validation and holdout remain sealed unless every gate passes.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--max-asset-weight", type=float, default=0.20)
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
        periods, distribution = _candidate_periods(result)
        signal_diagnostics = cross_sectional_rank_diagnostics(periods)
        signal_bootstrap = rank_signal_block_bootstrap(
            periods,
            block_size=args.signal_bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=41,
        )
        signal_gate = signal_only_gate(
            signal_diagnostics,
            distribution,
            rank_bootstrap=signal_bootstrap,
            minimum_bootstrap_probability=(
                args.bootstrap_minimum_probability
            ),
        )
        deterministic = _deterministic_gate(
            result["summary_by_model"],
            signal_gate,
        )
        paired, holm, statistical = _portfolio_statistical_gate(
            result,
            risk_free,
            args,
        )
        portfolio_gate = {
            "status": (
                "passed"
                if deterministic["status"] == "passed"
                and statistical["status"] == "passed"
                else "rejected"
            ),
            "deterministic": deterministic,
            "statistical": statistical,
        }
        promotion_eligible = bool(
            split["promotion_safe"]
            and signal_gate["status"] == "passed"
            and portfolio_gate["status"] == "passed"
        )
        result_for_output = {
            key: value
            for key, value in result.items()
            if key != "rebalance_records"
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
                "excluded_source_tickers": (
                    price_provenance.get("excluded_tickers", [])
                ),
            },
            "settings": settings,
            "signal_diagnostics": signal_diagnostics,
            "signal_distribution": distribution,
            "signal_bootstrap": signal_bootstrap,
            "signal_gate": signal_gate,
            "paired_bootstrap": paired,
            "holm_gate": holm,
            "portfolio_gate": portfolio_gate,
            "rebalance_record_count": int(
                len(result.get("rebalance_records", []))
            ),
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
