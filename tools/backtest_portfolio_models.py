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
    PROMOTION_CANDIDATE_MODELS,
    DEFAULT_BACKTEST_MODELS,
    aggregate_gauntlet_promotion,
    build_rebalance_targets,
    configure_forecast_rank_cache,
    fetch_backtest_price_data,
    forecast_rank_cache_stats,
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
    "adaptive_signal_tilt",
    "historical_mpt",
    "lightweight_bl",
    "arima_transformer_rank_bl",
    "transformer_rank_bl",
)
CANDIDATE_GAUNTLET_MODELS = tuple(
    model for model in GAUNTLET_MODELS
    if model not in ("arima_transformer_rank_bl", "transformer_rank_bl")
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
    "locked_holdout_2024_2025": ("2022-01-01", "2025-12-31"),
}
STANDARD_GAUNTLET_REGIMES = (
    "bull",
    "crash",
    "inflation_rate_shock",
    "sideways",
)

GAUNTLET_REBALANCE_BANDS = (0.02, 0.03, 0.05)
GAUNTLET_MAX_TURNOVERS = (0.20, 0.35, 0.50)
CANDIDATE_GAUNTLET_SCENARIOS = (
    ("sp500_sample", "bull"),
    ("tech", "crash"),
    ("defensive", "inflation_rate_shock"),
    ("mixed_etf", "sideways"),
)
HOLDOUT_GAUNTLET_SCENARIOS = tuple(
    (basket_name, "locked_holdout_2024_2025")
    for basket_name, _ in CANDIDATE_GAUNTLET_SCENARIOS
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
        scenario_names = (("tech", "bull"),)
        bands = (0.02,)
        turnovers = (0.35,)
    elif preset == "candidate":
        scenario_names = CANDIDATE_GAUNTLET_SCENARIOS
        bands = (0.02,)
        turnovers = (0.35,)
    elif preset == "holdout":
        scenario_names = HOLDOUT_GAUNTLET_SCENARIOS
        bands = (0.02,)
        turnovers = (0.35,)
    else:
        scenario_names = tuple(
            (basket_name, regime_name)
            for basket_name in GAUNTLET_BASKETS
            for regime_name in STANDARD_GAUNTLET_REGIMES
        )
        bands = GAUNTLET_REBALANCE_BANDS
        turnovers = GAUNTLET_MAX_TURNOVERS

    cases = []
    for basket_name, regime_name in scenario_names:
        basket = GAUNTLET_BASKETS[basket_name]
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


def _evaluation_split(preset):
    if preset == "smoke":
        return "research"
    if preset == "holdout":
        return "locked_holdout"
    return "validation"


def _case_key(case):
    return json.dumps(
        [
            case.get("basket_key"),
            case.get("regime"),
            case.get("rebalance_band"),
            case.get("max_turnover"),
        ],
        separators=(",", ":"),
    )


def _checkpoint_signature(args, models):
    return {
        "preset": args.gauntlet_preset,
        "evaluation_split": _evaluation_split(args.gauntlet_preset),
        "models": list(models),
        "train_window": int(args.train_window),
        "rebalance_frequency": int(args.rebalance_frequency),
        "forecast_horizon": int(args.forecast_horizon),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "max_asset_weight": float(args.max_asset_weight),
        "min_holding_weight": float(args.min_holding_weight),
        "risk_free_rate": float(args.risk_free_rate),
        "initial_value": float(args.initial_value),
        "fetch_market_caps": bool(args.fetch_market_caps),
        "forecast_cache_namespace": str(args.forecast_cache_namespace),
        "csv": str(Path(args.csv).expanduser().resolve()) if args.csv else None,
    }


def _load_checkpoint(checkpoint_path, args, models):
    if not checkpoint_path.exists():
        return {}
    expected_signature = _checkpoint_signature(args, models)
    runs_by_case = {}
    for line_number, line in enumerate(checkpoint_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            print(f"Ignoring incomplete checkpoint line {line_number}", file=sys.stderr)
            continue
        if entry.get("signature") != expected_signature:
            raise ValueError("Checkpoint settings do not match this gauntlet run")
        run = entry.get("run")
        if (
            isinstance(run, dict)
            and isinstance(run.get("case"), dict)
            and "result" in run
        ):
            runs_by_case[_case_key(run["case"])] = run
    return runs_by_case


def _append_checkpoint(checkpoint_path, args, models, run):
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "version": 1,
        "signature": _checkpoint_signature(args, models),
        "run": run,
    }
    with checkpoint_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
        handle.flush()


def _build_gauntlet_payload(args, models, cases, runs):
    completed_runs = [run for run in runs if "result" in run]
    candidate_reports = {
        candidate: aggregate_gauntlet_promotion(completed_runs, candidate_model=candidate)
        for candidate in PROMOTION_CANDIDATE_MODELS
        if candidate in models
    }
    primary_decision = next(
        iter(candidate_reports.values()),
        aggregate_gauntlet_promotion(completed_runs),
    )
    payload = {
        "preset": args.gauntlet_preset,
        "evaluation_split": _evaluation_split(args.gauntlet_preset),
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
            "target_generation": "once_per_basket_regime",
            "execution_sensitivity_reuses_targets": True,
            "forecast_cache_namespace": args.forecast_cache_namespace,
            "evaluation_split": _evaluation_split(args.gauntlet_preset),
        },
        "forecast_cache": forecast_rank_cache_stats(),
        "promotion_gauntlet": primary_decision,
        "promotion_by_candidate": candidate_reports,
        "runs": runs,
    }
    return payload


def _run_gauntlet(args, checkpoint_path):
    default_models = (
        CANDIDATE_GAUNTLET_MODELS
        if args.gauntlet_preset in ("candidate", "holdout")
        else GAUNTLET_MODELS
    )
    models = tuple(args.models or default_models)
    cases = _gauntlet_cases(args.gauntlet_preset, max_cases=args.max_cases)
    csv_prices = pd.read_csv(args.csv, index_col=0, parse_dates=True) if args.csv else None
    runs_by_case = (
        _load_checkpoint(checkpoint_path, args, models)
        if args.resume
        else {}
    )

    scenario_groups = {}
    for idx, case in enumerate(cases, start=1):
        scenario_key = (case["basket_key"], case["regime"])
        scenario_groups.setdefault(scenario_key, []).append((idx, case))

    for scenario_cases in scenario_groups.values():
        pending_cases = [
            (idx, case)
            for idx, case in scenario_cases
            if _case_key(case) not in runs_by_case
        ]
        if not pending_cases:
            continue
        _, scenario = pending_cases[0]
        print(
            f"Preparing targets once: {scenario['basket']} / {scenario['regime']}",
            flush=True,
        )
        try:
            if csv_prices is not None:
                prices = csv_prices.copy()
            else:
                prices = fetch_backtest_price_data(
                    tickers=scenario.get("tickers"),
                    ticker_group=scenario.get("ticker_group"),
                    start_date=scenario["start"],
                    end_date=scenario["end"],
                )
            market_caps = _market_caps_for_prices(prices, models, args.fetch_market_caps)
            target_start = None if csv_prices is not None else scenario["start"]
            target_end = None if csv_prices is not None else scenario["end"]
            rebalance_targets = build_rebalance_targets(
                prices,
                models=models,
                start_date=target_start,
                end_date=target_end,
                train_window=args.train_window,
                rebalance_frequency=args.rebalance_frequency,
                forecast_horizon=args.forecast_horizon,
                max_asset_weight=args.max_asset_weight,
                min_holding_weight=args.min_holding_weight,
                market_caps=market_caps,
                risk_free_rate=args.risk_free_rate,
            )
        except Exception as exc:
            for _, case in pending_cases:
                run = {"case": case, "error": str(exc)}
                runs_by_case[_case_key(case)] = run
                _append_checkpoint(checkpoint_path, args, models, run)
            continue

        for idx, case in pending_cases:
            print(
                f"[{idx}/{len(cases)}] {case['basket']} / {case['regime']} "
                f"band={case['rebalance_band']:.2%} max_turnover={case['max_turnover']:.0%}",
                flush=True,
            )
            try:
                result = run_portfolio_model_backtest(
                    prices,
                    models=models,
                    start_date=target_start,
                    end_date=target_end,
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
                    rebalance_targets=rebalance_targets,
                )
                run = {"case": case, "result": result}
            except Exception as exc:
                run = {"case": case, "error": str(exc)}
            runs_by_case[_case_key(case)] = run
            _append_checkpoint(checkpoint_path, args, models, run)

    ordered_runs = [
        runs_by_case[_case_key(case)]
        for case in cases
        if _case_key(case) in runs_by_case
    ]
    return _build_gauntlet_payload(args, models, cases, ordered_runs)


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
        f"- Evaluation split: `{payload['evaluation_split']}`",
        f"- Completed: {payload['completed_count']} / {payload['case_count']}",
        f"- Candidate: `{decision['candidate_model']}`",
        f"- Status: `{decision['status']}`",
        f"- Survival: {decision['survival_count']} / {decision['usable_count']} ({decision['survival_rate']:.1%})",
        f"- Target generation: `{payload['settings'].get('target_generation')}`",
        f"- Persistent forecast cache entries: {payload.get('forecast_cache', {}).get('persistent_entries', 0)}",
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
    lines.extend([
        "",
        "## Alpha diagnostics",
        "",
        "| Basket | Regime | Rank IC | Positive IC | Top-bottom | Active share | Signal retention | Cost drag |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    candidate_name = decision.get("candidate_model")
    for run in payload.get("runs", []):
        result = run.get("result", {})
        metrics = result.get("summary_by_model", {}).get(candidate_name, {})
        case = run.get("case", {})
        lines.append(
            "| {basket} | {regime} | {rank_ic} | {positive_ic} | {spread} | {active} | {retention} | {cost_drag} |".format(
                basket=case.get("basket") or "",
                regime=case.get("regime") or "",
                rank_ic=_fmt(metrics.get("avg_signal_rank_ic")),
                positive_ic=_fmt(metrics.get("positive_signal_rank_ic_rate")),
                spread=_fmt(metrics.get("avg_top_bottom_spread")),
                active=_fmt(metrics.get("avg_active_share")),
                retention=_fmt(metrics.get("avg_execution_signal_retention")),
                cost_drag=_fmt(metrics.get("transaction_cost_return_drag")),
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
    parser.add_argument("--rebalance-frequency", type=int, default=None)
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
        choices=("standard", "candidate", "holdout", "smoke"),
        help=(
            "Run a repeatable gauntlet; candidate uses four representative scenarios "
            "and holdout reserves 2024-2025 for one final evaluation"
        ),
    )
    parser.add_argument("--max-cases", type=int, default=None, help="Limit gauntlet cases for smoke/debug runs")
    parser.add_argument(
        "--forecast-cache",
        help="SQLite path for persistent ML forecast reuse; defaults beside the gauntlet output",
    )
    parser.add_argument(
        "--forecast-cache-namespace",
        default=None,
        help="Experiment namespace that prevents forecast reuse across incompatible model configurations",
    )
    parser.add_argument(
        "--checkpoint",
        help="JSONL case checkpoint path; defaults beside the gauntlet output",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume completed cases from the JSONL checkpoint and reuse persistent forecasts",
    )
    parser.add_argument(
        "--fetch-market-caps",
        action="store_true",
        help="Fetch market caps for the market_cap_weight baseline when that model is selected",
    )
    args = parser.parse_args(argv)
    if args.rebalance_frequency is None:
        args.rebalance_frequency = 63 if args.gauntlet_preset in ("candidate", "holdout") else 21
    if args.forecast_cache_namespace is None:
        split = _evaluation_split(args.gauntlet_preset) if args.gauntlet_preset else "research"
        args.forecast_cache_namespace = f"adaptive-signal-v1-{split}"

    try:
        if args.gauntlet_preset:
            output_path = Path(args.output) if args.output else _default_gauntlet_output_path()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            forecast_cache_path = (
                Path(args.forecast_cache)
                if args.forecast_cache
                else output_path.parent / "portfolio_gauntlet_forecasts.sqlite3"
            )
            checkpoint_path = (
                Path(args.checkpoint)
                if args.checkpoint
                else output_path.with_name(f"{output_path.name}.checkpoint.jsonl")
            )
            configure_forecast_rank_cache(
                forecast_cache_path,
                namespace=args.forecast_cache_namespace,
            )
            if not args.resume:
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                checkpoint_path.write_text("", encoding="utf-8")
            payload = _run_gauntlet(args, checkpoint_path)
            payload["checkpoint_path"] = str(checkpoint_path.resolve())
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            report_path = _write_gauntlet_report(payload, output_path)
            _print_gauntlet_summary(payload)
            print(f"\nWrote {output_path}")
            print(f"Wrote {report_path}")
            print(f"Checkpoint {checkpoint_path}")
            print(f"Forecast cache {forecast_cache_path}")
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
