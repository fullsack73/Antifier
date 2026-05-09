#!/usr/bin/env python3
"""Compare ensemble and Transformer forecast accuracy with walk-forward windows."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND))

from forecast_models import compare_forecasters_on_frame  # noqa: E402


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
    parser.add_argument("--min-train-size", type=int, default=252)
    parser.add_argument("--step", type=int, default=None)
    parser.add_argument("--max-windows", type=int, default=5)
    parser.add_argument("--transformer-epochs", type=int, default=5)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["ensemble", "transformer", "arima_transformer"],
        help="Models to compare: ensemble transformer arima_transformer",
    )
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    prices = _load_prices(args)
    result = compare_forecasters_on_frame(
        prices,
        horizon=args.horizon,
        min_train_size=args.min_train_size,
        step=args.step,
        max_windows=args.max_windows,
        models=args.models,
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
