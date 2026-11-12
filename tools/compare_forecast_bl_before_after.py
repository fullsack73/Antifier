#!/usr/bin/env python3
"""Frozen-forecast BL diagnostic; no model training or production mutation."""

import argparse
import copy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/backend"))

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

import portfolio_backtest as backtest
from direct_horizon_forecast import supervised_returns, purged_split
from forecast_failure_diagnostics import digest, file_digest
from portfolio_statistics import holm_bonferroni
from tools import compare_improved_forecast_portfolios as shared
from tools.diagnose_forecast_failures import write_json

PARENTS = {"legacy_bl": ROOT / "logs/forecast_mpt_before_after_20261109",
           "improved_bl": ROOT / "logs/improved_forecast_three_portfolios_20261109"}


def views_for_origin(train, saved, improved):
    views, uncertainty = {}, {}
    for ticker in train:
        prediction = saved["predictions"][ticker]
        if improved:
            _, _, y, ends = supervised_returns(train[ticker].to_numpy(), 63)
            tr, va = purged_split(ends, 63)
            if len(tr) != prediction["train_rows"] or len(va) != prediction["validation_rows"]:
                raise ValueError("Stored validation partition does not match current input")
            scale = float(StandardScaler().fit(y[tr, None]).scale_[0])
            # EarlyStopping restores the weights at minimum normalized validation MSE.
            sigma = np.sqrt(min(prediction["validation_loss"])) * scale * 4
            period = prediction["raw"]
        else:
            sigma = prediction["reported_uncertainty"]
            period = prediction["original_hybrid_component"]
        views[ticker] = float(np.expm1(period * 4))
        uncertainty[ticker] = float(max(.01, sigma))
    if not np.isfinite(list(views.values()) + list(uncertainty.values())).all():
        raise ValueError("Nonfinite BL views or uncertainty")
    return pd.Series(views), pd.Series(uncertainty)


def bl_weights(train, views, uncertainty):
    messages = []
    class Collector(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())
    handler = Collector(level=logging.WARNING)
    backtest.logger.addHandler(handler)
    try:
        with patch.object(backtest, "_forecast_views", return_value=(views, uncertainty, 0, {})):
            weights, diagnostics = backtest._black_litterman_weights(train, "transformer", 63, .2, .02)
    finally:
        backtest.logger.removeHandler(handler)
    diagnostics.update(warnings=messages, annual_uncertainty=uncertainty.to_dict(),
                       mpt_solver_fallback=any("Efficient frontier failed for max_sharpe" in s for s in messages),
                       bl_fallback=any("Backtest BL failed" in s for s in messages))
    return weights, diagnostics


def load_parents():
    manifests, saved, files = {}, {}, {}
    for name, parent in PARENTS.items():
        path = parent / "manifest.json"
        manifest = json.loads(path.read_text())
        if digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest["sha256"]:
            raise ValueError("Parent manifest mismatch")
        if (parent / "run.exit").read_text().strip() != "0":
            raise ValueError("Incomplete parent run")
        files[str(path)] = file_digest(path)
        saved[name] = []
        for task in manifest["tasks"]:
            cp = parent / "checkpoints" / (task["id"] + ".json")
            value = json.loads(cp.read_text())
            if value["manifest_sha256"] != manifest["sha256"] or value["task"] != task or value["status"] != "ok":
                raise ValueError("Parent checkpoint mismatch")
            files[str(cp)] = file_digest(cp)
            saved[name].append(value)
        manifests[name] = manifest
    if manifests["legacy_bl"]["tasks"] != manifests["improved_bl"]["tasks"]:
        raise ValueError("Forecast calendars differ")
    inputs = manifests["improved_bl"]["inputs"]
    for key, value in inputs.items():
        if value["sha256"] != manifests["legacy_bl"]["inputs"][key]["sha256"] or file_digest(value["path"]) != value["sha256"]:
            raise ValueError("Parent input drift")
    return manifests, saved, files


def run(output):
    if (output / "manifest.json").exists():
        raise ValueError("Use a new output directory; do not overwrite a frozen BL comparison")
    parents, saved, files = load_parents()
    parent = parents["improved_bl"]
    prices = shared.panel({k: v["path"] for k, v in parent["inputs"].items()})
    manifest = {"purpose": "diagnostic_only", "promotion_eligible": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "parent_manifests": {k: v["sha256"] for k, v in parents.items()}, "parent_files": files,
                "inputs": parent["inputs"], "tasks": parent["tasks"], "settings": shared.SETTINGS,
                "sources": {**shared.sources(), "tools/compare_forecast_bl_before_after.py": file_digest(__file__),
                            "src/backend/direct_horizon_forecast.py": file_digest(ROOT / "src/backend/direct_horizon_forecast.py")},
                "bl": {"tau": .05, "risk_aversion": 2.5, "prior": "equal_cap_market_implied",
                       "views": "absolute annual-simple return", "confidence": "existing uncertainty shrinkage and omega",
                       "improved_uncertainty": "reconstruct best validation MSE using purged train-target scaler"},
                "bootstrap": {"samples": 2000, "block_size": 21, "seed": 42, "holm_endpoints": ["higher_return", "higher_sharpe", "lower_volatility"]},
                "limitations": parent["limitations"] + [
                    "True historical BL with common equal-cap market prior; not exact production historical path",
                    "Production skips BL without historical market caps and falls back to forecast MPT",
                    "Saved forecasts generated before production integration; provenance retained, no source guard weakened",
                    "Improved uncertainty reconstructed from best normalized validation MSE, not an OOS calibrated interval",
                    "Both mean forecasts and uncertainty change; not a prediction-only causal comparison"]}
    manifest["sha256"] = digest(manifest)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "manifest.json", manifest)
    tasks = manifest["tasks"]
    first, last = tasks[0]["index"], tasks[-1]["index"]
    data = prices.iloc[first - 504:last + 64]
    targets = backtest.build_rebalance_targets(data, models=["min_variance"], train_window=504,
                                              rebalance_frequency=63, forecast_horizon=63,
                                              max_asset_weight=.2, risk_free_rate=.02, target_turnover_limit=.35)
    if [t["rebalance_date"] for t in targets["records"]] != [t["origin"] for t in tasks]:
        raise ValueError("Execution/forecast calendar mismatch")
    runs, details = {}, {}
    for name in ["legacy_bl", "improved_bl"]:
        own = copy.deepcopy(targets)
        details[name] = []
        for task, target, cached in zip(tasks, own["records"], saved[name]):
            i = task["index"]
            train = prices.iloc[i - 504:i]
            if digest(train.to_numpy().tolist()) != cached["train_prices_sha256"]:
                raise ValueError("Saved forecast training panel mismatch")
            views, uncertainty = views_for_origin(train, cached, name == "improved_bl")
            weights, diagnostics = bl_weights(train, views, uncertainty)
            target["models"]["min_variance"] = {"weights": weights, "diagnostics": diagnostics}
            details[name].append({"origin": task["origin"], "weights": weights, **diagnostics})
        runs[name] = backtest.run_portfolio_model_backtest(data, models=["min_variance"], rebalance_targets=own,
                                                        include_daily_returns=True, **shared.SETTINGS)
    daily = {k: shared.net_daily_returns(v) for k, v in runs.items()}
    if list(daily["legacy_bl"].index) != list(daily["improved_bl"].index):
        raise ValueError("Daily calendars differ")
    bootstrap = shared.paired_block_bootstrap(daily["improved_bl"], daily["legacy_bl"], risk_free_rate=.02,
                                             block_size=21, samples=2000, seed=42)
    summary = {k: v["summary_by_model"]["min_variance"] for k, v in runs.items()}
    metrics = ["cagr", "annual_volatility", "sharpe", "max_drawdown", "net_cumulative_return", "final_value"]
    result = {"purpose": "diagnostic_only", "promotion_eligible": False, "manifest_sha256": manifest["sha256"],
              "start": tasks[0]["origin"], "end": saved["improved_bl"][-1]["period_end"],
              "origins": len(tasks), "daily_observations": len(daily["legacy_bl"]), "summary": summary,
              "improved_minus_legacy": {m: summary["improved_bl"][m] - summary["legacy_bl"][m] for m in metrics},
              "paired_bootstrap": bootstrap,
              "holm": holm_bonferroni({k: 1 - v if v is not None else 1. for k, v in bootstrap["probability"].items()}),
              "bl_diagnostics": details, "daily_returns": {k: v.to_dict() for k, v in daily.items()},
              "rebalance_records": {k: v["rebalance_records"] for k, v in runs.items()}, "limitations": manifest["limitations"]}
    write_json(output / "result.json", result)
    lines = ["# Black–Litterman 기존/개선 예측 비교", "", "- 동일비중 시장 prior의 historical BL diagnostic",
             f"- {result['start']} ~ {result['end']}, {result['origins']}회 재조정", "",
             "| 방식 | CAGR | 변동성 | Sharpe | 최대낙폭 | 누적수익률 |", "|---|---:|---:|---:|---:|---:|"]
    for name, s in summary.items():
        lines.append(f"| {name} | {s['cagr']:.4%} | {s['annual_volatility']:.4%} | {s['sharpe']:.4f} | {s['max_drawdown']:.4%} | {s['net_cumulative_return']:.4%} |")
    lines += ["", "## 불확실성", "", json.dumps(result["holm"], indent=2), "",
              "- 미래 승률이나 독립 holdout 결과가 아닙니다. Bootstrap 수익률 endpoint는 CAGR이 아닙니다.",
              "- 현재 production의 historical market-cap 미확보 시 MPT 대체 경로와 구분합니다."]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"summary": summary, "difference": result["improved_minus_legacy"], "holm": result["holm"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.output.resolve())
    except Exception:
        if args.output.exists():
            (args.output / "run.exit").write_text("1\n")
        raise
    else:
        (args.output / "run.exit").write_text("0\n")
