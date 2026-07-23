#!/usr/bin/env python3
"""Validate one frozen risk allocator across four representative cases."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from portfolio_backtest import (  # noqa: E402
    fetch_backtest_price_data,
    run_portfolio_model_backtest,
)
from portfolio_risk_models import risk_allocator_case_gate  # noqa: E402


FROZEN_CANDIDATE = "robust_min_variance"
VALIDATION_MODELS = (
    "equal_weight",
    "min_variance",
    "risk_parity",
    FROZEN_CANDIDATE,
)
VALIDATION_CASES = (
    {
        "basket": "SP500 sample",
        "regime": "bull",
        "tickers": [
            "AAPL", "MSFT", "AMZN", "GOOGL", "META",
            "NVDA", "JPM", "JNJ", "XOM", "PG",
        ],
        "start": "2016-01-01",
        "end": "2019-12-31",
    },
    {
        "basket": "tech basket",
        "regime": "crash",
        "tickers": [
            "AAPL", "MSFT", "NVDA", "AVGO",
            "AMD", "CRM", "ADBE", "ORCL",
        ],
        "start": "2018-01-01",
        "end": "2020-12-31",
    },
    {
        "basket": "defensive basket",
        "regime": "inflation_rate_shock",
        "tickers": [
            "PG", "KO", "PEP", "WMT",
            "COST", "JNJ", "MRK", "NEE",
        ],
        "start": "2020-01-01",
        "end": "2023-12-31",
    },
    {
        "basket": "mixed ETF-like basket",
        "regime": "sideways",
        "tickers": [
            "SPY", "QQQ", "IWM", "EFA", "EEM",
            "AGG", "TLT", "GLD", "VNQ", "DBC",
        ],
        "start": "2014-01-01",
        "end": "2016-12-31",
    },
)


def _fmt(value):
    return "NA" if value is None else f"{float(value):.4f}"


def _write_report(payload, output_path):
    lines = [
        "# Frozen Risk Allocator Validation",
        "",
        f"- Candidate: `{payload['candidate']}`",
        f"- Passed: {payload['passed_count']} / {payload['case_count']}",
        f"- Status: `{payload['status']}`",
        "",
        "## Cases",
        "",
        "| Basket | Regime | Candidate Sharpe | Baseline Sharpe | Candidate vol | Baseline vol | Candidate DD | Baseline DD | Gate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for run in payload["runs"]:
        candidate = run["result"]["summary_by_model"][FROZEN_CANDIDATE]
        baseline = run["result"]["summary_by_model"]["min_variance"]
        lines.append(
            "| {basket} | {regime} | {candidate_sharpe} | "
            "{baseline_sharpe} | {candidate_vol} | {baseline_vol} | "
            "{candidate_dd} | {baseline_dd} | {gate} |".format(
                basket=run["case"]["basket"],
                regime=run["case"]["regime"],
                candidate_sharpe=_fmt(candidate["sharpe"]),
                baseline_sharpe=_fmt(baseline["sharpe"]),
                candidate_vol=_fmt(candidate["annual_volatility"]),
                baseline_vol=_fmt(baseline["annual_volatility"]),
                candidate_dd=_fmt(candidate["max_drawdown"]),
                baseline_dd=_fmt(baseline["max_drawdown"]),
                gate=run["gate"]["status"],
            )
        )
    lines.extend([
        "",
        "## Decision",
        "",
        "- Promotion requires all four cases to pass against Ledoit-Wolf minimum variance.",
        "- Locked holdout remains untouched.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--max-asset-weight", type=float, default=0.20)
    parser.add_argument("--rebalance-band", type=float, default=0.02)
    parser.add_argument("--max-turnover", type=float, default=0.35)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    runs = []
    try:
        for case in VALIDATION_CASES:
            prices = fetch_backtest_price_data(
                tickers=case["tickers"],
                start_date=case["start"],
                end_date=case["end"],
            )
            result = run_portfolio_model_backtest(
                prices,
                models=VALIDATION_MODELS,
                train_window=args.train_window,
                rebalance_frequency=args.rebalance_frequency,
                forecast_horizon=args.rebalance_frequency,
                transaction_cost_bps=args.transaction_cost_bps,
                max_asset_weight=args.max_asset_weight,
                rebalance_band=args.rebalance_band,
                max_turnover=args.max_turnover,
            )
            gate = risk_allocator_case_gate(result["summary_by_model"])
            runs.append({
                "case": case,
                "gate": gate,
                "result": result,
            })
        passed_count = sum(
            run["gate"]["status"] == "passed"
            for run in runs
        )
        payload = {
            "evaluation_split": "validation",
            "candidate": FROZEN_CANDIDATE,
            "candidate_specification": {
                "covariance": {
                    "ledoit_wolf": 0.50,
                    "oracle_approximating": 0.30,
                    "exponential_180d": 0.20,
                },
                "allocator": "long_only_minimum_variance",
            },
            "settings": vars(args),
            "case_count": len(VALIDATION_CASES),
            "passed_count": int(passed_count),
            "status": (
                "validation_passed"
                if passed_count == len(VALIDATION_CASES)
                else "validation_rejected"
            ),
            "runs": runs,
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
