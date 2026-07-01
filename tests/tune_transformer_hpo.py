#!/usr/bin/env python3
"""Run a small Transformer HPO sweep against walk-forward forecast metrics."""

import argparse
import json
from pathlib import Path

import pandas as pd

from forecast_model_comparison_utils import compare_forecasters_on_frame


DEFAULT_CONFIGS = [
    {
        "name": "baseline",
        "lookback": 60,
        "d_model": 32,
        "num_heads": 2,
        "ff_dim": 64,
        "dropout": 0.1,
        "epochs": 5,
        "batch_size": 32,
        "learning_rate": 0.001,
        "dense_units": 32,
        "num_blocks": 1,
        "patience": 2,
        "forecast_clip": 0.2,
    },
    {
        "name": "short_context",
        "lookback": 30,
        "d_model": 32,
        "num_heads": 2,
        "ff_dim": 64,
        "dropout": 0.05,
        "epochs": 5,
        "batch_size": 32,
        "learning_rate": 0.001,
        "dense_units": 32,
        "num_blocks": 1,
        "patience": 2,
        "forecast_clip": 0.15,
    },
    {
        "name": "wide_context",
        "lookback": 60,
        "d_model": 64,
        "num_heads": 4,
        "ff_dim": 128,
        "dropout": 0.1,
        "epochs": 5,
        "batch_size": 32,
        "learning_rate": 0.0007,
        "dense_units": 64,
        "num_blocks": 1,
        "patience": 2,
        "forecast_clip": 0.15,
    },
    {
        "name": "short_wide",
        "lookback": 30,
        "d_model": 64,
        "num_heads": 4,
        "ff_dim": 128,
        "dropout": 0.05,
        "epochs": 5,
        "batch_size": 32,
        "learning_rate": 0.0007,
        "dense_units": 64,
        "num_blocks": 1,
        "patience": 2,
        "forecast_clip": 0.15,
    },
    {
        "name": "regularized",
        "lookback": 60,
        "d_model": 32,
        "num_heads": 2,
        "ff_dim": 128,
        "dropout": 0.2,
        "epochs": 6,
        "batch_size": 32,
        "learning_rate": 0.0005,
        "dense_units": 32,
        "num_blocks": 1,
        "patience": 2,
        "forecast_clip": 0.12,
    },
    {
        "name": "small_fast",
        "lookback": 20,
        "d_model": 16,
        "num_heads": 2,
        "ff_dim": 32,
        "dropout": 0.05,
        "epochs": 5,
        "batch_size": 32,
        "learning_rate": 0.001,
        "dense_units": 16,
        "num_blocks": 1,
        "patience": 2,
        "forecast_clip": 0.15,
    },
    {
        "name": "two_block",
        "lookback": 45,
        "d_model": 32,
        "num_heads": 2,
        "ff_dim": 64,
        "dropout": 0.1,
        "epochs": 6,
        "batch_size": 32,
        "learning_rate": 0.0007,
        "dense_units": 32,
        "num_blocks": 2,
        "patience": 2,
        "forecast_clip": 0.12,
    },
]


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


def _load_configs(path):
    if not path:
        return DEFAULT_CONFIGS
    with open(path, "r", encoding="utf-8") as handle:
        configs = json.load(handle)
    if not isinstance(configs, list):
        raise ValueError("Config file must contain a JSON list")
    return configs


def _score_key(result):
    metrics = result["metrics"]
    mae = metrics["mae"] if metrics["mae"] is not None else float("inf")
    rmse = metrics["rmse"] if metrics["rmse"] is not None else float("inf")
    return mae, rmse


def _print_table(results):
    headers = ["rank", "name", "n", "fail", "MAE", "RMSE", "dir_acc", "corr", "avg_sec"]
    rows = []
    for idx, result in enumerate(results, start=1):
        metrics = result["metrics"]
        rows.append([
            idx,
            result["config"]["name"],
            metrics["n"],
            metrics["failures"],
            _fmt(metrics["mae"]),
            _fmt(metrics["rmse"]),
            _fmt(metrics["directional_accuracy"]),
            _fmt(metrics["correlation"]),
            _fmt(metrics["avg_seconds"]),
        ])

    widths = [max(len(str(row[i])) for row in [headers] + rows) for i in range(len(headers))]
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
    parser.add_argument("--horizon", type=int, default=21)
    parser.add_argument("--min-train-size", type=int, default=252)
    parser.add_argument("--step", type=int, default=None)
    parser.add_argument("--max-windows", type=int, default=3)
    parser.add_argument(
        "--model",
        choices=["transformer", "arima_transformer"],
        default="transformer",
        help="Forecast path to optimize. Use arima_transformer for production portfolio defaults.",
    )
    parser.add_argument("--configs", help="Optional JSON list of Transformer configs")
    parser.add_argument("--output", default="logs/transformer_hpo_results.json")
    args = parser.parse_args()

    prices = _load_prices(args)
    configs = _load_configs(args.configs)
    results = []

    for config in configs:
        name = config.get("name", f"config_{len(results) + 1}")
        transformer_kwargs = {k: v for k, v in config.items() if k != "name"}
        print(f"Running {name}...")
        comparison = compare_forecasters_on_frame(
            prices,
            horizon=args.horizon,
            min_train_size=args.min_train_size,
            step=args.step,
            max_windows=args.max_windows,
            models=(args.model,),
            transformer_kwargs=transformer_kwargs,
        )
        results.append({
            "config": {"name": name, **transformer_kwargs},
            "metrics": comparison["summary"][args.model],
        })

    results.sort(key=_score_key)
    payload = {
        "best": results[0] if results else None,
        "results": results,
        "settings": {
            "tickers": args.tickers,
            "csv": args.csv,
            "start": args.start,
            "end": args.end,
            "horizon": args.horizon,
            "min_train_size": args.min_train_size,
            "step": args.step,
            "max_windows": args.max_windows,
            "model": args.model,
        },
    }

    _print_table(results)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nBest config: {payload['best']['config']['name']}")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
