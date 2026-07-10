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
    aggregate_gauntlet_promotion,
    fetch_backtest_price_data,
    run_portfolio_model_backtest,
)
from portfolio_optimization import get_market_caps  # noqa: E402


GAUNTLET_MODELS = (
    "equal_weight",
    "min_variance",
    "risk_parity",
    "momentum_6m",
    "low_volatility",
    "market_cap_weight",
    "momentum_12_1",
    "historical_bl",
    "momentum_bl",
    "signal_stack_bl",
    "historical_mpt",
    "lightweight_bl",
    "arima_transformer_rank_bl",
    "transformer_rank_bl",
)

GAUNTLET_BASKETS = {
    "sp500_sample": {
        "label": "SP500 sample",
        "tickers": ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "JPM", "JNJ", "XOM", "PG"],
    },
    "dow": {
        "label": "DOW",
        "ticker_group": "DOW",
    },
    "tech": {
        "label": "tech basket",
        "tickers": ["AAPL", "MSFT", "NVDA", "AVGO", "AMD", "CRM", "ADBE", "ORCL"],
    },
    "defensive": {
        "label": "defensive basket",
        "tickers": ["PG", "KO", "PEP", "WMT", "COST", "JNJ", "MRK", "NEE"],
    },
    "mixed_etf": {
        "label": "mixed ETF-like basket",
        "tickers": ["SPY", "QQQ", "IWM", "EFA", "EEM", "AGG", "TLT", "GLD", "VNQ", "DBC"],
    },
}

GAUNTLET_REGIMES = {
    "bull": ("2016-01-01", "2019-12-31"),
    "crash": ("2018-01-01", "2020-12-31"),
    "inflation_rate_shock": ("2020-01-01", "2023-12-31"),
    "sideways": ("2014-01-01", "2016-12-31"),
}

GAUNTLET_REBALANCE_BANDS = (0.02, 0.03, 0.05)
GAUNTLET_MAX_TURNOVERS = (0.20, 0.35, 0.50)


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
        "ctrlTurn",
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
            _fmt(metrics.get("controlled_turnover")),
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


def _default_gauntlet_output_path():
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("logs") / f"portfolio_gauntlet_{stamp}.json"


def _market_caps_for_prices(prices, models, fetch_market_caps):
    selected_models = tuple(models or DEFAULT_BACKTEST_MODELS)
    if not fetch_market_caps or "market_cap_weight" not in selected_models:
        return None
    try:
        return get_market_caps(list(prices.columns))
    except Exception:
        return None


def _gauntlet_cases(preset, max_cases=None):
    if preset == "smoke":
        basket_names = ("tech",)
        regime_names = ("bull",)
        bands = (0.02,)
        turnovers = (0.35,)
    else:
        basket_names = tuple(GAUNTLET_BASKETS.keys())
        regime_names = tuple(GAUNTLET_REGIMES.keys())
        bands = GAUNTLET_REBALANCE_BANDS
        turnovers = GAUNTLET_MAX_TURNOVERS

    cases = []
    for basket_name in basket_names:
        basket = GAUNTLET_BASKETS[basket_name]
        for regime_name in regime_names:
            start, end = GAUNTLET_REGIMES[regime_name]
            for rebalance_band in bands:
                for max_turnover in turnovers:
                    case = {
                        "basket": basket["label"],
                        "basket_key": basket_name,
                        "regime": regime_name,
                        "start": start,
                        "end": end,
                        "rebalance_band": rebalance_band,
                        "max_turnover": max_turnover,
                    }
                    if basket.get("ticker_group"):
                        case["ticker_group"] = basket["ticker_group"]
                    else:
                        case["tickers"] = list(basket["tickers"])
                    cases.append(case)
                    if max_cases is not None and len(cases) >= max_cases:
                        return cases
    return cases


def _run_gauntlet(args):
    models = tuple(args.models or GAUNTLET_MODELS)
    cases = _gauntlet_cases(args.gauntlet_preset, max_cases=args.max_cases)
    runs = []
    csv_prices = pd.read_csv(args.csv, index_col=0, parse_dates=True) if args.csv else None

    for idx, case in enumerate(cases, start=1):
        print(
            f"[{idx}/{len(cases)}] {case['basket']} / {case['regime']} "
            f"band={case['rebalance_band']:.2%} max_turnover={case['max_turnover']:.0%}"
        )
        try:
            if csv_prices is not None:
                prices = csv_prices.copy()
            else:
                prices = fetch_backtest_price_data(
                    tickers=case.get("tickers"),
                    ticker_group=case.get("ticker_group"),
                    start_date=case["start"],
                    end_date=case["end"],
                )
            market_caps = _market_caps_for_prices(prices, models, args.fetch_market_caps)
            result = run_portfolio_model_backtest(
                prices,
                models=models,
                start_date=None if csv_prices is not None else case["start"],
                end_date=None if csv_prices is not None else case["end"],
                train_window=args.train_window,
                rebalance_frequency=args.rebalance_frequency,
                forecast_horizon=args.forecast_horizon,
                transaction_cost_bps=args.transaction_cost_bps,
                max_asset_weight=args.max_asset_weight,
                rebalance_band=case["rebalance_band"],
                max_turnover=case["max_turnover"],
                min_holding_weight=args.min_holding_weight,
                market_caps=market_caps,
                risk_free_rate=args.risk_free_rate,
                initial_value=args.initial_value,
            )
            runs.append({"case": case, "result": result})
        except Exception as exc:
            runs.append({"case": case, "error": str(exc)})

    completed_runs = [run for run in runs if "result" in run]
    payload = {
        "preset": args.gauntlet_preset,
        "models": list(models),
        "case_count": len(cases),
        "completed_count": len(completed_runs),
        "settings": {
            "train_window": args.train_window,
            "rebalance_frequency": args.rebalance_frequency,
            "forecast_horizon": args.forecast_horizon,
            "transaction_cost_bps": args.transaction_cost_bps,
            "max_asset_weight": args.max_asset_weight,
            "min_holding_weight": args.min_holding_weight,
            "risk_free_rate": args.risk_free_rate,
            "initial_value": args.initial_value,
            "fetch_market_caps": bool(args.fetch_market_caps),
        },
        "promotion_gauntlet": aggregate_gauntlet_promotion(completed_runs),
        "runs": runs,
    }
    return payload


def _print_gauntlet_summary(payload):
    decision = payload["promotion_gauntlet"]
    print(
        f"\nGauntlet: {payload['completed_count']}/{payload['case_count']} completed; "
        f"promotion={decision['status']} ({decision['candidate_model']})"
    )
    print(
        f"Survival: {decision['survival_count']}/{decision['usable_count']} "
        f"({decision['survival_rate']:.1%})"
    )
    for reason in decision.get("reasons", []):
        print(f"- {reason}")


def _write_gauntlet_report(payload, output_path):
    report_path = output_path.with_suffix(".md")
    decision = payload["promotion_gauntlet"]
    lines = [
        "# Portfolio Performance Gauntlet",
        "",
        f"- Preset: `{payload['preset']}`",
        f"- Completed: {payload['completed_count']} / {payload['case_count']}",
        f"- Candidate: `{decision['candidate_model']}`",
        f"- Status: `{decision['status']}`",
        f"- Survival: {decision['survival_count']} / {decision['usable_count']} ({decision['survival_rate']:.1%})",
        "",
        "## Reasons",
        "",
    ]
    lines.extend([f"- {reason}" for reason in decision.get("reasons", [])] or ["- None"])
    lines.extend([
        "",
        "## Cases",
        "",
        "| Basket | Regime | Band | Max Turnover | Survived | First Reason |",
        "|---|---:|---:|---:|---:|---|",
    ])
    for case in decision.get("cases", []):
        first_reason = (case.get("reasons") or [""])[0]
        lines.append(
            "| {basket} | {regime} | {band} | {turnover} | {survived} | {reason} |".format(
                basket=case.get("basket") or "",
                regime=case.get("regime") or "",
                band=_fmt(case.get("rebalance_band")),
                turnover=_fmt(case.get("max_turnover")),
                survived="yes" if case.get("survived") else "no",
                reason=str(first_reason).replace("|", "\\|"),
            )
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


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
    parser.add_argument("--rebalance-band", type=float, default=0.02)
    parser.add_argument("--max-turnover", type=float, default=0.35)
    parser.add_argument("--min-holding-weight", type=float, default=0.0)
    parser.add_argument("--risk-free-rate", type=float, default=0.02, help="Annual decimal rate, e.g. 0.02")
    parser.add_argument("--initial-value", type=float, default=10000.0)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=DEFAULT_BACKTEST_MODELS,
        default=None,
    )
    parser.add_argument("--output", default=None, help="JSON output path")
    parser.add_argument(
        "--gauntlet-preset",
        choices=("standard", "smoke"),
        help="Run a repeatable multi-basket/regime gauntlet instead of one backtest",
    )
    parser.add_argument("--max-cases", type=int, default=None, help="Limit gauntlet cases for smoke/debug runs")
    parser.add_argument(
        "--fetch-market-caps",
        action="store_true",
        help="Fetch market caps for the market_cap_weight baseline when that model is selected",
    )
    args = parser.parse_args(argv)

    try:
        if args.gauntlet_preset:
            payload = _run_gauntlet(args)
            output_path = Path(args.output) if args.output else _default_gauntlet_output_path()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            report_path = _write_gauntlet_report(payload, output_path)
            _print_gauntlet_summary(payload)
            print(f"\nWrote {output_path}")
            print(f"Wrote {report_path}")
            return 0

        if args.csv and args.ticker_group:
            raise ValueError("--csv and --ticker-group cannot be combined")
        prices = _load_prices(args)
        market_caps = _market_caps_for_prices(prices, args.models, args.fetch_market_caps)
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
            rebalance_band=args.rebalance_band,
            max_turnover=args.max_turnover,
            min_holding_weight=args.min_holding_weight,
            market_caps=market_caps,
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
