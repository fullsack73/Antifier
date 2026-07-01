#!/usr/bin/env python3
"""Compare ensemble and Transformer forecast accuracy with walk-forward windows."""

import argparse
import json
from pathlib import Path

import pandas as pd

from forecast_model_comparison_utils import (
    compare_forecasters_on_frame,
    compare_single_ticker_forecasters,
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

    if not args.tickers:
        raise ValueError("Provide --tickers or --csv")

    import yfinance as yf

    data = yf.download(
        args.tickers,
        start=args.start,
        end=args.end,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )

    if data.empty:
        raise ValueError("No price data returned")

    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            return data["Close"]
        return data.xs("Close", level=1, axis=1)

    return data[["Close"]].rename(columns={"Close": args.tickers[0]})


def _print_summary(summary):
    headers = ["model", "n", "fail", "MAE", "RMSE", "bias", "dir_acc", "corr", "avg_sec"]
    rows = []
    for model_name, metrics in summary.items():
        rows.append([
            model_name,
            metrics["n"],
            metrics["failures"],
            _fmt(metrics["mae"]),
            _fmt(metrics["rmse"]),
            _fmt(metrics["bias"]),
            _fmt(metrics["directional_accuracy"]),
            _fmt(metrics["correlation"]),
            _fmt(metrics["avg_seconds"]),
        ])

    widths = [
        max(len(str(row[i])) for row in [headers] + rows)
        for i in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(widths[i]) for i, value in enumerate(row)))


def _parse_horizons(values):
    if not values:
        return None

    horizons = {}
    for value in values:
        if "=" in value:
            label, horizon = value.split("=", 1)
        else:
            horizon = value
            label = f"{int(horizon)}d"
        horizons[label] = int(horizon)
    return horizons


def _print_horizon_summary(results_by_ticker):
    headers = ["ticker", "window", "days", "best_model", "n", "MAE", "RMSE", "dir_acc", "corr"]
    rows = []
    for ticker, result in results_by_ticker.items():
        for label, best in result["best_by_horizon"].items():
            horizon_payload = result["horizons"][label]
            metrics = {} if best is None else best["metrics"]
            rows.append([
                ticker,
                label,
                horizon_payload["horizon"],
                "NA" if best is None else best["model"],
                metrics.get("n", 0),
                _fmt(metrics.get("mae")),
                _fmt(metrics.get("rmse")),
                _fmt(metrics.get("directional_accuracy")),
                _fmt(metrics.get("correlation")),
            ])

    widths = [
        max(len(str(row[i])) for row in [headers] + rows)
        for i in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(widths[i]) for i, value in enumerate(row)))


def _fmt(value):
    if value is None:
        return "NA"
    return f"{value:.6f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*", help="Ticker symbols to download with yfinance")
    parser.add_argument("--csv", help="CSV with date index and ticker price columns")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--horizon", type=int, default=21, help="Forecast horizon in trading days")
    parser.add_argument(
        "--by-horizon",
        action="store_true",
        help="Compare each ticker across short/medium/long horizons and select the best model per horizon",
    )
    parser.add_argument(
        "--horizons",
        nargs="*",
        help="Optional horizons for --by-horizon, e.g. short=21 medium=63 long=252",
    )
    parser.add_argument("--min-train-size", type=int, default=252)
    parser.add_argument("--step", type=int, default=None)
    parser.add_argument("--max-windows", type=int, default=5)
    parser.add_argument("--transformer-epochs", type=int, default=5)
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="Models to compare: ensemble transformer arima_transformer",
    )
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    prices = _load_prices(args)
    models = args.models or (
        ["transformer", "arima_transformer"]
        if args.by_horizon
        else ["ensemble", "transformer", "arima_transformer"]
    )

    if args.by_horizon:
        result = {
            str(ticker): compare_single_ticker_forecasters(
                str(ticker),
                prices[ticker].dropna().values,
                horizons=_parse_horizons(args.horizons),
                min_train_size=args.min_train_size,
                step=args.step,
                max_windows=args.max_windows,
                models=models,
                transformer_kwargs={"epochs": args.transformer_epochs},
            )
            for ticker in prices.columns
        }
        _print_horizon_summary(result)
    else:
        result = compare_forecasters_on_frame(
            prices,
            horizon=args.horizon,
            min_train_size=args.min_train_size,
            step=args.step,
            max_windows=args.max_windows,
            models=models,
            transformer_kwargs={"epochs": args.transformer_epochs},
        )

        _print_summary(result["summary"])

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nWrote {output_path}")


if __name__ == "__main__":
    main()
