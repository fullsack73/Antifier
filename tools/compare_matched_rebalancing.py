#!/usr/bin/env python3
"""Compare h-day Transformer forecasts with h-day rebalancing on one frozen panel."""
import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/backend"))
from tools.backtest_attention_mpt import SEEDS, SETTINGS, fit_period_forecast, mpt_weights
from tools.compare_improved_forecast_portfolios import net_daily_returns
from portfolio_backtest import (_safe_covariance, _weight_diagnostics,
                                build_rebalance_targets, run_portfolio_model_backtest)
from portfolio_statistics import paired_block_bootstrap
import numpy as np
import pandas as pd

HORIZONS = (21, 42, 63, 126)
PARENT = ROOT / "logs/attention-horizons-20261124-9o9oie0_"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def origins(rows, interval):
    if isinstance(interval, bool) or not isinstance(interval, int) or interval not in HORIZONS:
        raise ValueError("Unsupported rebalance interval")
    return [i - 1 for i in range(504, rows - 1, interval)]


def valid_forecast(value, stocks):
    values = np.asarray(value["period_log_forecast"], dtype=float)
    if values.shape != (stocks,) or not np.isfinite(values).all():
        raise ValueError("Incomplete or nonfinite stock forecast")


def replay(prices, forecasts, horizon):
    calendar = origins(len(prices), horizon)
    settings = {**SETTINGS, "rebalance_frequency": horizon, "forecast_horizon": horizon}
    targets = build_rebalance_targets(prices, models=["min_variance"], train_window=504,
        rebalance_frequency=horizon, forecast_horizon=horizon, max_asset_weight=.2,
        risk_free_rate=.03, target_turnover_limit=.35)
    if len(targets["records"]) != len(calendar):
        raise ValueError("Rebalance target calendar mismatch")
    covariances = {i: _safe_covariance(prices.iloc[i - 503:i + 1]) for i in calendar}
    runs, daily, fallback_counts = {}, {}, {}
    for name in ("gmv", "mpt_ensemble", *(f"mpt_seed{s}" for s in SEEDS)):
        own = copy.deepcopy(targets)
        fallback_counts[name] = 0
        for i, record in zip(calendar, own["records"]):
            if (record["train_end_date"] != str(prices.index[i].date())
                    or record["rebalance_date"] != str(prices.index[i + 1].date())):
                raise ValueError("Forecast and next-close execution mismatch")
            target = record["models"]["min_variance"]
            scores, diagnostics = {}, {}
            if name != "gmv":
                seeds = SEEDS if name == "mpt_ensemble" else (int(name.removeprefix("mpt_seed")),)
                period = np.mean([forecasts[(i, s)]["period_log_forecast"] for s in seeds], axis=0)
                weights, diagnostics = mpt_weights(period, covariances[i], target["weights"], horizon=horizon)
                target["weights"] = weights
                scores = dict(zip(prices.columns, period.tolist()))
                fallback_counts[name] += int(diagnostics["mpt_fallback_to_gmv"])
            target["diagnostics"].update(_weight_diagnostics(target["weights"], scores, covariances[i]))
            target["diagnostics"].update(diagnostics, construction=name, signal_scores=scores,
                target_weights=target["weights"], model_forecast_horizon=horizon)
            record["experiment_diagnostics"] = diagnostics
        run = run_portfolio_model_backtest(prices, models=["min_variance"], rebalance_targets=own,
                                           include_daily_returns=True, **settings)
        returns = net_daily_returns(run)
        summary = run["summary_by_model"]["min_variance"]
        sharpe = (returns.mean() - (1.03 ** (1 / 252) - 1)) / returns.std(ddof=0) * np.sqrt(252)
        if not np.isclose(sharpe, summary["sharpe"]):
            raise ValueError("Independent net Sharpe calculation mismatch")
        daily[name] = {str(date): float(value) for date, value in returns.items()}
        runs[name] = {"summary": summary, "records": run["rebalance_records"], "target_records": own["records"]}
    return {"settings": settings, "runs": runs, "daily_returns": daily, "mpt_fallback_counts": fallback_counts}


def bootstrap(candidate, baseline):
    candidate, baseline = pd.Series(candidate, dtype=float), pd.Series(baseline, dtype=float)
    if not candidate.index.equals(baseline.index):
        raise ValueError("Different daily execution calendars")
    return paired_block_bootstrap(candidate, baseline, risk_free_rate=.03, block_size=63,
        samples=2000, seed=42, risk_free_daily_returns=pd.Series(1.03 ** (1 / 252) - 1, index=candidate.index))


def summarize(results, fixed):
    output = {}
    common_dates = list(results[63]["daily_returns"]["mpt_ensemble"])
    for h in HORIZONS:
        r = results[h]
        if any(list(values) != common_dates for values in r["daily_returns"].values()):
            raise ValueError("Matched schedules do not cover the same daily observations")
        output[str(h)] = {"ensemble": r["runs"]["mpt_ensemble"]["summary"],
            "gmv_same_schedule": r["runs"]["gmv"]["summary"],
            "seed_sharpes": {str(s): r["runs"][f"mpt_seed{s}"]["summary"]["sharpe"] for s in SEEDS},
            "mpt_fallback_counts": r["mpt_fallback_counts"],
            "paired_vs_gmv_same_schedule": bootstrap(r["daily_returns"]["mpt_ensemble"], r["daily_returns"]["gmv"]),
            "paired_vs_fixed63_rebalancing": bootstrap(r["daily_returns"]["mpt_ensemble"], fixed[h]["daily_returns"]["mpt_ensemble"]),
            "fixed63_rebalancing_sharpe": fixed[h]["runs"]["mpt_ensemble"]["summary"]["sharpe"],
            "paired_vs_63_day_pair": bootstrap(r["daily_returns"]["mpt_ensemble"], results[63]["daily_returns"]["mpt_ensemble"])}
    return {"by_horizon": output,
            "descriptive_best_horizon": max(HORIZONS, key=lambda h: output[str(h)]["ensemble"]["sharpe"]),
            "promotion_eligible": False, "daily_observations": len(common_dates)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    source, folder = Path(args.csv), Path(args.output_dir)
    prices = pd.read_csv(source, index_col=0, parse_dates=True).astype(float)
    if (prices.shape != (1008, 22) or not isinstance(prices.index, pd.DatetimeIndex)
            or prices.index.hasnans or not prices.index.is_unique or not prices.index.is_monotonic_increasing
            or not prices.columns.is_unique or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()):
        raise ValueError("Need ordered 1008-day positive prices for 22 stocks")
    parent = json.loads((PARENT / "manifest.json").read_text())
    if (PARENT / "run.exit").read_text().strip() != "0" or parent["price_sha256"] != digest(source):
        raise ValueError("Parent experiment incomplete or different prices")
    for name, sha in parent["sources"].items():
        if digest(ROOT / name) != sha:
            raise ValueError("Cannot reuse forecasts after source drift: " + name)
    for name, version in parent["packages"].items():
        if importlib.metadata.version(name) != version:
            raise ValueError("Cannot reuse forecasts after dependency drift: " + name)
    if (parent["settings"] != SETTINGS or parent["seeds"] != list(SEEDS)
            or parent["epochs"] != 5 or parent["batch_dates"] != 8 or parent["learning_rate"] != .001):
        raise ValueError("Parent training or execution settings differ")
    tasks = []
    for h in HORIZONS:
        for i in origins(len(prices), h):
            for seed in SEEDS:
                name = f"fit-h{h}-{i}-{seed}.json"
                previous = PARENT / name
                tasks.append({"horizon": h, "origin": i, "signal_date": str(prices.index[i].date()),
                    "seed": seed, "name": name, "reused": previous.exists(),
                    "parent_sha256": digest(previous) if previous.exists() else None})
    source_names = ("tools/compare_matched_rebalancing.py", *parent["sources"])
    manifest = {"purpose": "consumed_historical_matched_rebalancing_diagnostic", "promotion_eligible": False,
        "price_sha256": digest(source), "parent_manifest_sha256": digest(PARENT / "manifest.json"),
        "parent": str(PARENT), "horizons": list(HORIZONS), "seeds": list(SEEDS), "base_settings": SETTINGS,
        "paired_parameters": "forecast_horizon == rebalance_frequency; 21,42,63,126 trading days",
        "primary": "net Sharpe of three-seed mean log-forecast MPT on common two-year daily calendar",
        "model": parent["model"], "epochs": 5, "learning_rate": .001, "batch_dates": 8,
        "rebalance_counts": {str(h): len(origins(len(prices), h)) for h in HORIZONS},
        "execution": "preceding-close signal, next-close execution; last holding interval is one day shorter",
        "turnover_policy": "same 35% per-rebalance cap, not an equal annual turnover budget; initial buy exempt",
        "bootstrap": {"block_size": 63, "samples": 2000, "seed": 42, "purpose": "descriptive"},
        "execution_start": str(prices.index[504].date()), "end": str(prices.index[-1].date()),
        "fixed_schedule_result_hashes": {str(h): digest(PARENT / f"result-h{h}.json") for h in HORIZONS},
        "tasks": tasks, "total_fits": len(tasks), "reused_fits": sum(t["reused"] for t in tasks),
        "new_fits": sum(not t["reused"] for t in tasks),
        "sources": {n: digest(ROOT / n) for n in source_names}, "packages": parent["packages"]}
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "manifest.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("Manifest drift; refuse to resume")
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    for task in tasks:
        if task["reused"]:
            raw = (PARENT / task["name"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != task["parent_sha256"]:
                raise ValueError("Parent checkpoint changed")
            valid_forecast(json.loads(raw), len(prices.columns))
            path = folder / task["name"]
            if path.exists() and path.read_bytes() != raw:
                raise ValueError("Reused checkpoint drift")
            path.write_bytes(raw)
    if args.prepare_only:
        print(json.dumps({k: manifest[k] for k in ("total_fits", "reused_fits", "new_fits", "rebalance_counts")}), flush=True)
        return
    results, completed = {}, 0
    for h in (63, 126, 21, 42):
        forecasts = {}
        for task in (t for t in tasks if t["horizon"] == h):
            path = folder / task["name"]
            if path.exists():
                forecast = json.loads(path.read_text())
            else:
                i = task["origin"]
                forecast = fit_period_forecast(prices.iloc[i - 503:i + 1], task["seed"], horizon=h)
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(forecast, allow_nan=False) + "\n")
                temporary.replace(path)
            valid_forecast(forecast, len(prices.columns))
            forecasts[(task["origin"], task["seed"])] = forecast
            completed += 1
            print(f"forecast {completed}/{len(tasks)} h={h} {task['signal_date']} seed={task['seed']} reused={task['reused']}", flush=True)
        results[h] = replay(prices, forecasts, h)
        if h == 63:
            previous = json.loads((PARENT / "result-h63.json").read_text())
            for name, run in results[h]["runs"].items():
                if not np.isclose(run["summary"]["sharpe"], previous["runs"][name]["summary"]["sharpe"], atol=1e-10, rtol=0):
                    raise ValueError("63/63 baseline replay mismatch")
        (folder / f"result-h{h}.json").write_text(json.dumps(results[h], indent=2, allow_nan=False, default=str) + "\n")
    fixed = {h: json.loads((PARENT / f"result-h{h}.json").read_text()) for h in HORIZONS}
    analysis = {**manifest, **summarize(results, fixed)}
    (folder / "analysis.json").write_text(json.dumps(analysis, indent=2, allow_nan=False) + "\n")
    print(json.dumps({h: analysis["by_horizon"][str(h)]["ensemble"]["sharpe"] for h in HORIZONS}, indent=2), flush=True)
    print(f"Descriptive best matched interval: {analysis['descriptive_best_horizon']}", flush=True)


if __name__ == "__main__":
    main()
