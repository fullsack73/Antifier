#!/usr/bin/env python3
"""Compare robust risk allocators on a research-only split."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from portfolio_backtest import (  # noqa: E402
    fetch_backtest_price_data,
    run_portfolio_model_backtest,
)
from portfolio_statistics import (  # noqa: E402
    bootstrap_improvement_gate,
    holm_bonferroni,
    paired_block_bootstrap,
)


RISK_RESEARCH_MODELS = (
    "equal_weight",
    "min_variance",
    "risk_parity",
    "momentum_6m",
    "robust_min_variance",
    "equal_risk_contribution",
    "hierarchical_risk_parity",
    "regime_minimum_variance",
    "minimum_cvar",
    "cross_validated_min_variance",
    "forecast_ensemble_min_variance",
    "stability_regularized_min_variance",
    "resampled_min_variance",
    "risk_managed_momentum",
)
RISK_CANDIDATES = (
    "robust_min_variance",
    "equal_risk_contribution",
    "hierarchical_risk_parity",
    "regime_minimum_variance",
    "minimum_cvar",
    "cross_validated_min_variance",
    "forecast_ensemble_min_variance",
    "stability_regularized_min_variance",
    "resampled_min_variance",
    "risk_managed_momentum",
)
RESERVED_SPLITS = {
    "validation",
    "candidate",
    "standard",
    "holdout",
    "locked_holdout",
}


def _load_prices(args):
    if args.csv:
        prices = pd.read_csv(args.csv, index_col=0, parse_dates=True)
        if args.tickers:
            prices = prices.loc[:, args.tickers]
        return prices
    if not args.tickers:
        raise ValueError("Provide --csv or --tickers")
    return fetch_backtest_price_data(
        tickers=args.tickers,
        start_date=args.start,
        end_date=args.end,
    )


def _risk_gate(summary, candidate_name):
    candidate = summary[candidate_name]
    equal = summary["equal_weight"]
    inverse_vol = summary["risk_parity"]
    baseline_name = (
        "momentum_6m"
        if candidate_name == "risk_managed_momentum"
        else (
            "min_variance"
            if candidate_name in {
                "robust_min_variance",
                "regime_minimum_variance",
                "minimum_cvar",
                "cross_validated_min_variance",
                "forecast_ensemble_min_variance",
                "stability_regularized_min_variance",
                "resampled_min_variance",
            }
            else "risk_parity"
        )
    )
    baseline = summary[baseline_name]
    reasons = []
    if candidate["annual_volatility"] >= baseline["annual_volatility"]:
        reasons.append(
            f"Realized volatility does not improve {baseline_name}."
        )
    if candidate["max_drawdown"] < baseline["max_drawdown"]:
        reasons.append(f"Max drawdown is worse than {baseline_name}.")
    if (
        candidate["sharpe"] is None
        or baseline["sharpe"] is None
        or candidate["sharpe"] <= baseline["sharpe"]
    ):
        reasons.append(f"Sharpe does not improve {baseline_name}.")
    if (
        candidate["annual_volatility"] > inverse_vol["annual_volatility"]
        and (
            candidate["sharpe"] is None
            or inverse_vol["sharpe"] is None
            or candidate["sharpe"] <= inverse_vol["sharpe"]
        )
    ):
        reasons.append("Risk/return does not improve inverse-vol baseline.")
    if candidate["avg_controlled_turnover"] > 0.50:
        reasons.append("Average controlled turnover exceeds 50%.")
    if (
        candidate_name == "minimum_cvar"
        and (
            candidate.get("daily_cvar_95") is None
            or baseline.get("daily_cvar_95") is None
            or candidate["daily_cvar_95"] >= baseline["daily_cvar_95"]
        )
    ):
        reasons.append(f"Daily CVaR does not improve {baseline_name}.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "baseline": baseline_name,
    }


def _fmt(value):
    return "NA" if value is None else f"{float(value):.4f}"


def _write_report(payload, output_path):
    lines = [
        "# Risk Allocator Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Rows: {payload['data']['row_count']}",
        f"- Tickers: {payload['data']['ticker_count']}",
        "",
        "## Performance",
        "",
        "| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    summary = payload["result"]["summary_by_model"]
    for model in payload["models"]:
        metrics = summary[model]
        gate = payload["risk_gates"].get(model, {})
        bootstrap = payload["paired_bootstrap"].get(model, {})
        probability = bootstrap.get("probability", {})
        lines.append(
            "| {model} | {cagr} | {volatility} | {sharpe} | {sortino} | "
            "{drawdown} | {cvar} | {turnover} | {risk_mae} | "
            "{lower_volatility} | {higher_sharpe} | {gate} |".format(
                model=model,
                cagr=_fmt(metrics["cagr"]),
                volatility=_fmt(metrics["annual_volatility"]),
                sharpe=_fmt(metrics["sharpe"]),
                sortino=_fmt(metrics["sortino"]),
                drawdown=_fmt(metrics["max_drawdown"]),
                cvar=_fmt(metrics["daily_cvar_95"]),
                turnover=_fmt(metrics["avg_controlled_turnover"]),
                risk_mae=_fmt(metrics["risk_forecast_mae"]),
                lower_volatility=_fmt(
                    probability.get("lower_volatility")
                ),
                higher_sharpe=_fmt(
                    probability.get("higher_sharpe")
                ),
                gate=gate.get("status", "baseline"),
            )
        )
    lines.extend([
        "",
        "## Guardrail",
        "",
        "- Research split only; no default or promotion change.",
        "- A risk candidate must improve its closest baseline and survive the inverse-vol guard.",
        "- Freeze a candidate before any validation run.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv")
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--max-asset-weight", type=float, default=0.20)
    parser.add_argument("--rebalance-band", type=float, default=0.02)
    parser.add_argument("--max-turnover", type=float, default=0.35)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-block-size", type=int, default=21)
    parser.add_argument(
        "--bootstrap-minimum-probability",
        type=float,
        default=0.95,
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--candidates",
        nargs="+",
        choices=RISK_CANDIDATES,
        default=list(RISK_CANDIDATES),
        help="Candidate subset; required closest baselines are added",
    )
    args = parser.parse_args(argv)

    try:
        if args.research_split.strip().lower() in RESERVED_SPLITS:
            raise ValueError(
                "Reserved validation/holdout split cannot be used for research"
            )
        prices = _load_prices(args)
        candidates = list(dict.fromkeys(args.candidates))
        if (
            "forecast_ensemble_min_variance" in candidates
            and args.train_window < 315
        ):
            raise ValueError(
                "forecast_ensemble_min_variance requires --train-window "
                "at least 315 for a 252/63 completed inner OOS fold"
            )
        models = list(dict.fromkeys(
            (
                "equal_weight",
                "min_variance",
                "risk_parity",
                "momentum_6m",
                *candidates,
            )
        ))
        result = run_portfolio_model_backtest(
            prices,
            models=models,
            train_window=args.train_window,
            rebalance_frequency=args.rebalance_frequency,
            forecast_horizon=args.rebalance_frequency,
            transaction_cost_bps=args.transaction_cost_bps,
            max_asset_weight=args.max_asset_weight,
            rebalance_band=args.rebalance_band,
            max_turnover=args.max_turnover,
            include_daily_returns=True,
        )
        deterministic_gates = {
            candidate: _risk_gate(result["summary_by_model"], candidate)
            for candidate in candidates
        }
        daily_returns = result["daily_returns_by_model"]
        paired_bootstrap = {}
        statistical_gates = {}
        gates = {}
        for index, candidate in enumerate(candidates):
            baseline = deterministic_gates[candidate]["baseline"]
            bootstrap = paired_block_bootstrap(
                daily_returns[candidate],
                daily_returns[baseline],
                risk_free_rate=result["settings"]["risk_free_rate"],
                block_size=args.bootstrap_block_size,
                samples=args.bootstrap_samples,
                seed=42 + index,
            )
            statistical_gate = bootstrap_improvement_gate(
                bootstrap,
                minimum_probability=args.bootstrap_minimum_probability,
            )
            paired_bootstrap[candidate] = bootstrap
            statistical_gates[candidate] = statistical_gate
            reasons = (
                list(deterministic_gates[candidate]["reasons"])
                + list(statistical_gate["reasons"])
            )
            gates[candidate] = {
                **deterministic_gates[candidate],
                "status": "passed" if not reasons else "rejected",
                "reasons": reasons,
            }
        familywise = holm_bonferroni(
            {
                candidate: max(
                    1.0
                    - paired_bootstrap[candidate]["probability"][
                        "lower_volatility"
                    ],
                    1.0
                    - paired_bootstrap[candidate]["probability"][
                        "higher_sharpe"
                    ],
                )
                for candidate in candidates
                if paired_bootstrap[candidate].get("status") == "ok"
                and paired_bootstrap[candidate]["probability"].get(
                    "higher_sharpe"
                ) is not None
            },
            alpha=0.05,
        )
        for candidate in candidates:
            familywise_result = familywise.get(candidate)
            if (
                familywise_result is None
                or not familywise_result["significant"]
            ):
                gates[candidate]["status"] = "rejected"
                gates[candidate]["reasons"].append(
                    "Improvement is not significant after Holm correction."
                )
        payload = {
            "research_split": args.research_split,
            "data": {
                "source": (
                    str(Path(args.csv).expanduser().resolve())
                    if args.csv
                    else "yfinance"
                ),
                "start_date": prices.index.min().strftime("%Y-%m-%d"),
                "end_date": prices.index.max().strftime("%Y-%m-%d"),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
                "tickers": list(prices.columns),
            },
            "settings": {
                "train_window": args.train_window,
                "rebalance_frequency": args.rebalance_frequency,
                "transaction_cost_bps": args.transaction_cost_bps,
                "max_asset_weight": args.max_asset_weight,
                "rebalance_band": args.rebalance_band,
                "max_turnover": args.max_turnover,
                "bootstrap_samples": args.bootstrap_samples,
                "bootstrap_block_size": args.bootstrap_block_size,
                "bootstrap_minimum_probability": (
                    args.bootstrap_minimum_probability
                ),
            },
            "models": models,
            "candidates": candidates,
            "risk_gates": gates,
            "deterministic_risk_gates": deterministic_gates,
            "statistical_risk_gates": statistical_gates,
            "paired_bootstrap": paired_bootstrap,
            "familywise_statistical_gate": familywise,
            "result": result,
        }
        output_path = Path(args.output)
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
