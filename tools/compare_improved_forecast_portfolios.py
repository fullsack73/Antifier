#!/usr/bin/env python3
"""Offline diagnostic: GMV vs direct-horizon MPT vs fixed GMV alpha overlay."""

import argparse
import copy
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/backend"))
from native_threading import configure_native_threading

configure_native_threading(force=True)
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier

from forecast_failure_diagnostics import TICKERS, digest, file_digest, transformer_forecast
from portfolio_backtest import (
    _efficient_frontier_weights, _safe_covariance, build_rebalance_targets,
    run_portfolio_model_backtest,
)
from portfolio_signals import confidence_gated_gmv_overlay
from portfolio_statistics import holm_bonferroni, paired_block_bootstrap
from research_split import validate_evidence_use
from universe_manifest import normalize_universe_manifest, universe_snapshot
from tools.diagnose_forecast_failures import write_json

DATA = ROOT / "data/research/derived"
INPUTS = {
    "prices": DATA / "nasdaq100_ohlcv_2017_2026.csv",
    "membership": DATA / "nasdaq100_membership_events_2016_2025.csv",
    "consumed_split": DATA / "nasdaq100_patch_transformer_fresh_validation_split_v1.json",
    "registry": ROOT / "data/research/evidence_consumption_v1.jsonl",
    "policy": ROOT / "data/research/research_policy_v1.json",
}
SETTINGS = {"train_window": 504, "rebalance_frequency": 63, "forecast_horizon": 63,
            "transaction_cost_bps": 10., "max_asset_weight": .2, "rebalance_band": .02,
            "max_turnover": .35, "risk_free_rate": .02}
NAMES = ["gmv", "model_mpt", "gmv_model"]
GAMMA = .025


def sources():
    names = ["tools/compare_improved_forecast_portfolios.py", "tools/diagnose_forecast_failures.py",
             "src/backend/forecast_failure_diagnostics.py", "src/backend/portfolio_backtest.py",
             "src/backend/portfolio_signals.py", "src/backend/portfolio_statistics.py",
             "src/backend/forecast_models.py"]
    return {name: file_digest(ROOT / name) for name in names}


def panel(paths):
    raw = pd.read_csv(paths["prices"], usecols=["timestamp", "ticker", "close"])
    raw["timestamp"] = pd.to_datetime(raw.timestamp)
    raw = raw.loc[raw.ticker.isin(TICKERS)]
    if raw.duplicated(["timestamp", "ticker"]).any():
        raise ValueError("Duplicate date/ticker")
    prices = raw.pivot(index="timestamp", columns="ticker", values="close").sort_index().reindex(columns=TICKERS)
    prices = prices.loc[:"2025-12-31"]
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Fixed comparison universe requires complete positive prices")
    return prices


def prepare(output):
    if (output / "manifest.json").exists():
        raise ValueError("Manifest already exists; use run to resume")
    prices = panel(INPUTS)
    members = normalize_universe_manifest(pd.read_csv(INPUTS["membership"]))
    first = prices.index.searchsorted(pd.Timestamp("2019-01-01"))
    origins = [i for i in range(first, len(prices) - 63, 63) if i >= 504]
    if not origins:
        raise ValueError("No completed forecast origins")
    for i in origins:
        if not set(TICKERS).issubset(universe_snapshot(members, prices.index[i])):
            raise ValueError("Fixed universe not active at " + str(prices.index[i]))
    evidence = validate_evidence_use(json.loads(INPUTS["consumed_split"].read_text()),
                                     requested_use="diagnostic", acknowledge_consumed=True)
    tasks = [{"origin": str(prices.index[i].date()), "index": int(i)} for i in origins]
    for task in tasks:
        task["id"] = digest(task)
    result = {
        "purpose": "diagnostic_only", "promotion_eligible": False,
        "created_at": datetime.now(timezone.utc).isoformat(), "evidence_use": evidence,
        "explicit_user_comparison": True,
        "signal_gate_override": "User explicitly requested historical three-way diagnostic; no candidate promotion",
        "inputs": {k: {"path": str(p), "sha256": file_digest(p)} for k, p in INPUTS.items()},
        "sources": sources(), "settings": SETTINGS, "tickers": TICKERS, "gamma": GAMMA,
        "forecast": {"position": False, "direct": True, "epochs": 5, "seed": 42,
                     "lookback": 60, "training_end": "last close strictly before rebalance date",
                     "expected_return_conversion": "expm1(period_log_return * 252/63); geometric annual return proxy"},
        "model_mpt": {"objective": "max_sharpe", "failure_policy": "exact same GMV target; report every fallback"},
        "gmv_model": {"construction": "centered rank overlay using existing confidence_gated_gmv_overlay",
                      "strength": 1., "gamma": GAMMA},
        "bootstrap": {"samples": 2000, "block_daily_observations": 21, "seed": 42,
                      "comparisons": ["model_mpt_vs_gmv", "gmv_model_vs_gmv"],
                      "endpoints": ["higher_return", "higher_sharpe", "lower_volatility"], "correction": "Holm across all six"},
        "tasks": tasks, "budget_seconds": 7200,
        "environment": {"python": sys.version, "packages": {p: importlib.metadata.version(p) for p in
                        ["numpy", "pandas", "tensorflow", "scikit-learn", "PyPortfolioOpt"]}},
        "limitations": ["Consumed public adjusted-price data; no fresh holdout",
                        "Fixed basket of current-known securities; not survivorship-safe alpha evidence",
                        "Single seed 42, no post-result model/gamma search",
                        "Close-price execution convention of existing backtest engine; no live slippage calibration",
                        "Improved standalone MPT also uses the same risk covariance; standalone refers to its return signal",
                        "Annualizing a log-return point forecast gives a geometric proxy, not a calibrated conditional arithmetic mean"],
    }
    result["sha256"] = digest(result)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "manifest.json", result)
    return result


def verify(manifest):
    if digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest["sha256"]:
        raise ValueError("Manifest drift")
    if sources() != manifest["sources"]:
        raise ValueError("Source drift")
    for v in manifest["inputs"].values():
        if file_digest(v["path"]) != v["sha256"]:
            raise ValueError("Input drift")
    for name, version in manifest["environment"]["packages"].items():
        if importlib.metadata.version(name) != version:
            raise ValueError("Dependency drift")


def weights_for_origin(train, scores, solver=EfficientFrontier):
    scores = pd.Series(scores, dtype=float).reindex(train.columns)
    if scores.isna().any() or not np.isfinite(scores).all():
        raise ValueError("Every asset needs a finite forecast")
    covariance = _safe_covariance(train)
    gmv = _efficient_frontier_weights(pd.Series(0., index=train.columns), covariance, .2, "min_volatility", .02)
    annual_mu = np.expm1(scores * 4)
    if not np.isfinite(annual_mu).all():
        raise ValueError("Nonfinite annual return conversion")
    fallback = None
    try:
        frontier = solver(annual_mu, covariance, weight_bounds=(0., .2))
        frontier.max_sharpe(risk_free_rate=.02)
        model = dict(frontier.clean_weights())
        model = {k: float(model.get(k, 0.)) for k in train.columns}
        total = sum(model.values())
        if total <= 0:
            raise ValueError("Empty MPT weights")
        model = {k: v / total for k, v in model.items()}
    except Exception as exc:
        model = dict(gmv)
        fallback = str(exc)
    overlay, diagnostics = confidence_gated_gmv_overlay(gmv, scores, {"active": True, "strength": 1.},
                                                       max_asset_weight=.2, target_active_share=GAMMA)
    weights = {"gmv": gmv, "model_mpt": model, "gmv_model": overlay.to_dict()}
    for w in weights.values():
        values = np.array([w.get(k, 0.) for k in train.columns])
        if not np.isfinite(values).all() or abs(values.sum() - 1.) > 1e-6 or values.min() < -1e-8 or values.max() > .20001:
            raise ValueError("Target weights violate simplex/cap")
    return weights, {"mpt_fallback_to_gmv": fallback is not None, "fallback_reason": fallback,
                     "annual_mu": annual_mu.to_dict(), "overlay": diagnostics}


def worker(output, manifest, index):
    verify(manifest)
    task = manifest["tasks"][index]
    prices = panel({k: v["path"] for k, v in manifest["inputs"].items()})
    i = task["index"]
    train = prices.iloc[i - 504:i]
    predictions = {}
    for ticker in TICKERS:
        predictions[ticker] = transformer_forecast(train[ticker].to_numpy(), horizon=63,
                                                   position=False, direct=True, seed=42, epochs=5)
    scores = {ticker: p["raw"] for ticker, p in predictions.items()}
    weights, diagnostics = weights_for_origin(train, scores)
    result = {"manifest_sha256": manifest["sha256"], "task": task, "status": "ok",
              "train_start": str(train.index[0].date()), "train_end": str(train.index[-1].date()),
              "train_prices_sha256": digest(train.to_numpy().tolist()), "period_end": str(prices.index[i + 63].date()),
              "predictions": predictions, "weights": weights, "diagnostics": diagnostics}
    write_json(output / "checkpoints" / (task["id"] + ".json"), result)


def net_daily_returns(run):
    """Anchor exported daily returns to starting wealth including initial fees."""
    daily = pd.Series(run["daily_returns_by_model"]["min_variance"], dtype=float).copy()
    expected = 1 + run["summary_by_model"]["min_variance"]["net_cumulative_return"]
    if not run.get("daily_returns_include_initial_cost") and not np.isclose((1 + daily).prod(), expected, rtol=1e-10, atol=1e-10):
        first = run["rebalance_records"][0]
        daily.iloc[0] = ((1 + daily.iloc[0]) * first["portfolio_value_after_cost"] /
                         first["portfolio_value_before_cost"] - 1)
    if not np.isclose((1 + daily).prod(), expected, rtol=1e-10, atol=1e-10):
        raise ValueError("Daily return compound does not match net wealth")
    return daily


def replay(prices, manifest, checkpoints):
    tasks = manifest["tasks"]
    if len(checkpoints) != len(tasks):
        raise ValueError("Refuse portfolio comparison with missing forecast origins")
    by_date = {c["task"]["origin"]: c for c in checkpoints}
    first, last = tasks[0]["index"], tasks[-1]["index"]
    prices = prices.iloc[first - 504:last + 64]
    targets = build_rebalance_targets(prices, models=["min_variance"], train_window=504,
                                      rebalance_frequency=63, forecast_horizon=63, max_asset_weight=.2,
                                      risk_free_rate=.02, target_turnover_limit=.35)
    if [t["rebalance_date"] for t in targets["records"]] != [t["origin"] for t in tasks]:
        raise ValueError("Forecast/rebalance calendar mismatch")
    runs = {}
    for name in NAMES:
        own = copy.deepcopy(targets)
        for t in own["records"]:
            saved = by_date[t["rebalance_date"]]
            model = t["models"]["min_variance"]
            model["weights"] = saved["weights"][name]
            model["diagnostics"].update(construction_method=name, signal_scores={k: v["raw"] for k, v in saved["predictions"].items()})
        runs[name] = run_portfolio_model_backtest(prices, models=["min_variance"],
                                                rebalance_targets=own, include_daily_returns=True, **SETTINGS)
    daily_returns = {name: net_daily_returns(run) for name, run in runs.items()}
    calendars = [list(d.index) for d in daily_returns.values()]
    if not all(c == calendars[0] for c in calendars):
        raise ValueError("Daily return calendars differ")
    bootstraps = {}
    for name in ["model_mpt", "gmv_model"]:
        series = {k: daily_returns[k] for k in [name, "gmv"]}
        bootstraps[name] = paired_block_bootstrap(series[name], series["gmv"], risk_free_rate=.02, block_size=21, samples=2000, seed=42)
    p_values = {f"{name}:{metric}": (1 - b["probability"][metric] if b.get("probability", {}).get(metric) is not None else 1.) for name, b in bootstraps.items()
                for metric in ["higher_return", "higher_sharpe", "lower_volatility"]}
    corrected = holm_bonferroni(p_values)
    # Keep complete execution accounting for review, not only headline returns.
    result = {"purpose": "diagnostic_only", "promotion_eligible": False, "manifest_sha256": manifest["sha256"],
              "analysis_source_hashes": sources(), "daily_returns_include_initial_cost": True,
              "start": tasks[0]["origin"], "end": checkpoints[-1]["period_end"], "origins": len(tasks),
              "daily_observations": len(calendars[0]), "settings": SETTINGS, "gamma": GAMMA,
              "mpt_fallback_count": sum(c["diagnostics"]["mpt_fallback_to_gmv"] for c in checkpoints),
              "summary": {k: v["summary_by_model"]["min_variance"] for k, v in runs.items()},
              "paired_bootstrap_vs_gmv": bootstraps, "holm": corrected,
              "rebalance_records": {k: v["rebalance_records"] for k, v in runs.items()},
              "daily_returns": {k: v.to_dict() for k, v in daily_returns.items()},
              "limitations": manifest["limitations"]}
    return result


def report(output, result):
    write_json(output / "result.json", result)
    lines = ["# GMV / 개선 예측 MPT / GMV + 개선 예측 비교", "", "- diagnostic_only, production 승격 불가",
             f"- 평가: {result['start']} ~ {result['end']}, {result['origins']}회 리밸런싱",
             f"- MPT의 GMV 대체: {result['mpt_fallback_count']}회", "",
             "| 방법 | CAGR | 변동성 | Sharpe | 최대낙폭 | 누적수익률 | 평균 거래회전율 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for name, s in result["summary"].items():
        sharpe = "NA" if s["sharpe"] is None else f"{s['sharpe']:.4f}"
        lines.append(f"| {name} | {s['cagr']:.4%} | {s['annual_volatility']:.4%} | {sharpe} | {s['max_drawdown']:.4%} | {s['net_cumulative_return']:.4%} | {s['avg_controlled_turnover']:.4%} |")
    lines += ["", "## GMV 대비 paired bootstrap", ""]
    for name, b in result["paired_bootstrap_vs_gmv"].items():
        lines.append(f"- {name}: {json.dumps(b['probability'], ensure_ascii=False)}")
    lines += ["", "- 위 확률은 재표집된 차이의 부호 비율이며 미래 승률이 아닙니다.",
              "- 반환 차이 bootstrap은 연환산 평균수익률을 비교하며 CAGR 차이 검정이 아닙니다.",
              "- 여섯 비교의 Holm 보정과 비용/거래 회계는 result.json에 보존합니다."]
    lines += ["", "## 한계", ""] + ["- " + s for s in result["limitations"]]
    (output / "report.md").write_text("\n".join(lines) + "\n")


def run(output, manifest):
    verify(manifest)
    (output / "checkpoints").mkdir(exist_ok=True)
    state_file = output / "run_state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state["manifest_sha256"] != manifest["sha256"]:
            raise ValueError("Run state mismatch")
    else:
        state = {"started_at": time.time(), "manifest_sha256": manifest["sha256"]}
        write_json(state_file, state)
    checkpoints = []
    for index, task in enumerate(manifest["tasks"]):
        path = output / "checkpoints" / (task["id"] + ".json")
        if not path.exists():
            remaining = 7200 - (time.time() - state["started_at"])
            if remaining < 120:
                raise RuntimeError("Budget exhausted; no partial-origin performance comparison produced")
            print(json.dumps({"event": "forecast_start", "task": task}), flush=True)
            with (output / "worker.log").open("a") as log:
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "worker", "--output", str(output), "--index", str(index)],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=remaining - 60)
        value = json.loads(path.read_text())
        if value["manifest_sha256"] != manifest["sha256"] or value["task"] != task or value["status"] != "ok":
            raise ValueError("Checkpoint mismatch")
        checkpoints.append(value)
        print(json.dumps({"event": "forecast_done", "origin": task["origin"], "completed": len(checkpoints)}), flush=True)
    prices = panel({k: v["path"] for k, v in manifest["inputs"].items()})
    report(output, replay(prices, manifest, checkpoints))
    print("Three-way diagnostic completed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "worker"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.command == "prepare":
        m = prepare(output)
        print(json.dumps({"manifest": str(output / 'manifest.json'), "sha256": m['sha256'], "origins": len(m['tasks'])}))
        return
    manifest = json.loads((output / "manifest.json").read_text())
    if args.command == "worker":
        worker(output, manifest, args.index)
        return
    import fcntl
    def interrupt(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        with (output / "run.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(output, manifest)
    except BaseException as exc:
        (output / "run.exit").write_text("130\n" if isinstance(exc, KeyboardInterrupt) else "1\n")
        raise
    else:
        (output / "run.exit").write_text("0\n")


if __name__ == "__main__":
    main()
