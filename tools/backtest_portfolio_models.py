#!/usr/bin/env python3
"""Run walk-forward portfolio model backtests."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from portfolio_backtest import (  # noqa: E402
    DEFAULT_BACKTEST_MODELS,
    fetch_backtest_price_data,
    run_portfolio_model_backtest,
)


def _load_prices(args):
    if args.csv:
        frame = pd.read_csv(args.csv, index_col=0, parse_dates=True)
        if args.tickers:
            missing = [ticker for ticker in args.tickers if ticker not in frame.columns]
            if missing:
                raise ValueError(f"CSV is missing requested tickers: {missing}")
            frame = frame[args.tickers]
        return frame

    if not args.tickers and not args.ticker_group:
        raise ValueError("Provide --csv, --tickers, or --ticker-group")

    return fetch_backtest_price_data(
        tickers=args.tickers,
        ticker_group=args.ticker_group,
        start_date=args.start,
        end_date=args.end,
    )


def _fmt(value):
    if value is None:
        return "NA"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _print_summary(result):
    headers = [
        "model",
        "CAGR",
        "vol",
        "Sharpe",
        "maxDD",
        "turnover",
        "costs",
        "final",
        "fails",
        "conf",
    ]
    rows = []
    for model in result["models"]:
        metrics = result["summary_by_model"].get(model, {})
        rows.append([
            model,
            _fmt(metrics.get("cagr")),
            _fmt(metrics.get("annual_volatility")),
            _fmt(metrics.get("sharpe")),
            _fmt(metrics.get("max_drawdown")),
            _fmt(metrics.get("turnover")),
            _fmt(metrics.get("transaction_costs")),
            _fmt(metrics.get("final_value")),
            metrics.get("failed_forecast_count", 0),
            _fmt(metrics.get("avg_forecast_confidence")),
        ])

    widths = [
        max(len(str(row[i])) for row in [headers] + rows)
        for i in range(len(headers))
    ]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(row[i]).ljust(widths[i]) for i in range(len(row))))

    decision = result["promotion_decision"]
    print(f"\nPromotion: {decision['status']} ({decision['candidate_model']})")
    for reason in decision.get("reasons", []):
        print(f"- {reason}")


def _default_output_path():
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("logs") / f"portfolio_backtest_{stamp}.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="CSV with date index and ticker price columns")
    parser.add_argument("--tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--ticker-group", help="Predefined ticker group, e.g. SP500 or DOW")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD")
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=21)
    parser.add_argument("--forecast-horizon", type=int, default=63)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--max-asset-weight", type=float, default=0.2)
    parser.add_argument("--risk-free-rate", type=float, default=0.02, help="Annual decimal rate, e.g. 0.02")
    parser.add_argument("--initial-value", type=float, default=10000.0)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=DEFAULT_BACKTEST_MODELS,
        default=list(DEFAULT_BACKTEST_MODELS),
    )
    parser.add_argument("--output", default=None, help="JSON output path")
    args = parser.parse_args(argv)

    try:
        if args.csv and args.ticker_group:
            raise ValueError("--csv and --ticker-group cannot be combined")
        prices = _load_prices(args)
        result = run_portfolio_model_backtest(
            prices,
            models=args.models,
            start_date=args.start,
            end_date=args.end,
            train_window=args.train_window,
            rebalance_frequency=args.rebalance_frequency,
            forecast_horizon=args.forecast_horizon,
            transaction_cost_bps=args.transaction_cost_bps,
            max_asset_weight=args.max_asset_weight,
            risk_free_rate=args.risk_free_rate,
            initial_value=args.initial_value,
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    output_path = Path(args.output) if args.output else _default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _print_summary(result)
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
