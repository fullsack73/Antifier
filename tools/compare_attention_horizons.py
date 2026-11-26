#!/usr/bin/env python3
"""Compare fixed Transformer forecast horizons with unchanged quarterly execution."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/backend"))
from tools.backtest_attention_mpt import ORIGINS, SEEDS, SETTINGS, fit_period_forecast, replay
from tools.benchmark_stock_attention import prepare
from portfolio_statistics import paired_block_bootstrap
import numpy as np
import pandas as pd

HORIZONS = (21, 42, 63, 126)
REFERENCE = ROOT / "logs/attention-mpt-20261124-2hp38yob"


def forecast_metrics(prices, forecasts, horizon):
    # Compare forecasts only at origins with completed outcomes for every candidate.
    origins = [i for i in ORIGINS if i + max(HORIZONS) < len(prices)]
    predictions, outcomes, historical, correlations = [], [], [], []
    for i in origins:
        predicted = np.mean([forecasts[(i, s)]["period_log_forecast"] for s in SEEDS], axis=0)
        actual = np.log(prices.iloc[i + horizon].to_numpy() / prices.iloc[i].to_numpy())
        train = prices.iloc[i - 503:i + 1].to_numpy()
        historical.append(np.diff(np.log(train), axis=0).mean(axis=0) * horizon)
        predictions.append(predicted)
        outcomes.append(actual)
        if np.std(predicted) > 1e-12:
            correlations.append(float(pd.Series(predicted).corr(pd.Series(actual), method="spearman")))
    predicted, actual, baseline = map(np.asarray, (predictions, outcomes, historical))
    mse = float(np.mean((predicted - actual) ** 2))
    zero_mse, historical_mse = float(np.mean(actual ** 2)), float(np.mean((baseline - actual) ** 2))
    return {"common_signal_dates": [str(prices.index[i].date()) for i in origins],
            "stock_date_count": int(actual.size), "period_log_rmse": float(np.sqrt(mse)),
            "period_log_mae": float(np.mean(np.abs(predicted - actual))),
            "mse_skill_vs_zero": 1 - mse / zero_mse if zero_mse > 0 else None,
            "mse_skill_vs_historical_daily_mean": 1 - mse / historical_mse if historical_mse > 0 else None,
            "mean_rank_ic": float(np.mean(correlations)) if correlations else None,
            "rank_ic_date_count": len(correlations),
            "note": "Raw errors have different horizon scales; use portfolio Sharpe as primary, not raw RMSE across horizons"}


def summarize(results):
    baseline = pd.Series(results[63]["daily_returns"]["mpt_ensemble"], dtype=float)
    by_horizon, comparisons = {}, {}
    for h in HORIZONS:
        r = results[h]
        returns = pd.Series(r["daily_returns"]["mpt_ensemble"], dtype=float)
        if not returns.index.equals(baseline.index):
            raise ValueError("Different portfolio return dates across horizons")
        gmv = pd.Series(r["daily_returns"]["gmv"], dtype=float)
        reference_gmv = pd.Series(results[63]["daily_returns"]["gmv"], dtype=float)
        if not gmv.index.equals(reference_gmv.index) or not np.allclose(gmv.values, reference_gmv.values, atol=1e-12, rtol=0):
            raise ValueError("GMV changed across horizon candidates")
        by_horizon[str(h)] = {"ensemble": r["runs"]["mpt_ensemble"]["summary"],
                              "seed_sharpes": {str(s): r["runs"][f"mpt_seed{s}"]["summary"]["sharpe"] for s in SEEDS},
                              "mpt_fallback_counts": r["mpt_fallback_counts"],
                              "forecast_metrics": r["forecast_metrics"]}
        if h != 63:
            comparisons[str(h)] = paired_block_bootstrap(returns, baseline, risk_free_rate=.03,
                block_size=63, samples=2000, seed=42,
                risk_free_daily_returns=pd.Series(1.03 ** (1 / 252) - 1, index=returns.index))
    return {"by_horizon": by_horizon, "gmv": results[63]["runs"]["gmv"]["summary"],
            "paired_bootstrap_vs_63": comparisons,
            "descriptive_best_horizon": max(HORIZONS, key=lambda h: by_horizon[str(h)]["ensemble"]["sharpe"]),
            "promotion_eligible": False,
            "interpretation": "Best of four consumed-history candidates is exploratory, not a validated production optimum"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source, folder = Path(args.csv), Path(args.output_dir)
    prices = pd.read_csv(source, index_col=0, parse_dates=True).astype(float)
    if (prices.shape != (1008, 22) or not isinstance(prices.index, pd.DatetimeIndex)
            or prices.index.hasnans or not prices.index.is_unique or not prices.index.is_monotonic_increasing
            or not prices.columns.is_unique or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()):
        raise ValueError("Require ordered 1008-day positive prices for 22 stocks")
    reference_raw = (REFERENCE / "result.json").read_bytes()
    reference = json.loads(reference_raw)
    price_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if price_hash != reference["price_sha256"]:
        raise ValueError("Reference and experiment prices differ")
    source_names = ("tools/compare_attention_horizons.py", "tools/backtest_attention_mpt.py",
                    "tools/backtest_stock_losses.py", "tools/benchmark_stock_attention.py",
                    "tools/compare_improved_forecast_portfolios.py", "src/backend/direct_horizon_forecast.py",
                    "src/backend/portfolio_backtest.py", "src/backend/portfolio_statistics.py")
    counts = {}
    for h in HORIZONS:
        padded = np.concatenate([prices.iloc[:504].to_numpy(), np.repeat(prices.iloc[503:504].to_numpy(), h, axis=0)])
        prepared = prepare(padded, horizon=h)
        counts[str(h)] = {"training_dates": len(prepared[2]), "validation_dates": len(prepared[3]),
                          "completed_supervised_dates": len(prepared[1])}
    manifest = {"purpose": "consumed_historical_horizon_diagnostic", "promotion_eligible": False,
                "horizons": list(HORIZONS), "execution_order": [63, 21, 42, 126], "seeds": list(SEEDS),
                "settings": SETTINGS, "portfolio_holding_and_metric_horizon": 63,
                "annual_conversion": "expm1(period_log_prediction * 252 / model_forecast_horizon)",
                "model": "cross-stock attention, 0.5 standardized MSE + 0.5 (1-Pearson cross-sectional correlation)",
                "epochs": 5, "learning_rate": .001, "batch_dates": 8, "training_window": 504,
                "sample_counts": counts, "primary": "three-seed mean prediction MPT net Sharpe on the common full two-year execution calendar",
                "forecast_comparison": "common seven origins completed at all horizons; remaining forecasts still used in portfolio replay",
                "bootstrap": {"block_size": 63, "samples": 2000, "seed": 42, "purpose": "descriptive, no fresh selection test"},
                "reference_result_sha256": hashlib.sha256(reference_raw).hexdigest(),
                "reference": str(REFERENCE), "reference_use": "default 63-day regression comparison only, all forecasts retrained",
                "price_sha256": price_hash, "tickers": list(prices.columns),
                "signal_dates": [str(prices.index[i].date()) for i in ORIGINS],
                "execution_start": str(prices.index[504].date()), "end": str(prices.index[-1].date()),
                "sources": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in source_names},
                "packages": {p: importlib.metadata.version(p) for p in
                             ("tensorflow", "numpy", "pandas", "scikit-learn", "PyPortfolioOpt")}}
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "manifest.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("Code, data or configuration drift; cannot resume")
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    results, fits = {}, 0
    for h in (63, 21, 42, 126):
        forecasts = {}
        for i in ORIGINS:
            for seed in SEEDS:
                path = folder / f"fit-h{h}-{i}-{seed}.json"
                if path.exists():
                    forecast = json.loads(path.read_text())
                else:
                    forecast = fit_period_forecast(prices.iloc[i - 503:i + 1], seed, horizon=h)
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(forecast, allow_nan=False) + "\n")
                    temporary.replace(path)
                forecasts[(i, seed)] = forecast
                fits += 1
                print(f"fit {fits}/96 horizon={h} {prices.index[i].date()} seed={seed}", flush=True)
        result = replay(prices, forecasts, horizon=h)
        result["forecast_metrics"] = forecast_metrics(prices, forecasts, h)
        result["model_forecast_horizon"] = h
        if h == 63:
            differences = {name: run["summary"]["sharpe"] - reference["runs"][name]["summary"]["sharpe"]
                           for name, run in result["runs"].items()}
            result["prior_63_sharpe_differences"] = differences
            if max(abs(v) for v in differences.values()) > 1e-5:
                raise ValueError(f"Default 63-day result drift; investigate before comparing horizons: {differences}")
        results[h] = result
        (folder / f"result-h{h}.json").write_text(json.dumps(result, indent=2, allow_nan=False, default=str) + "\n")
    analysis = {**manifest, **summarize(results)}
    (folder / "analysis.json").write_text(json.dumps(analysis, indent=2, allow_nan=False) + "\n")
    print(json.dumps({h: analysis["by_horizon"][str(h)]["ensemble"]["sharpe"] for h in HORIZONS}, indent=2), flush=True)
    print(f"Descriptive best horizon: {analysis['descriptive_best_horizon']}", flush=True)


if __name__ == "__main__":
    main()
