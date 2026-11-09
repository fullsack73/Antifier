#!/usr/bin/env python3
"""Compare legacy recursive and saved improved direct-horizon MPT, offline."""

import argparse
import copy
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/backend"))

import numpy as np
from forecast_failure_diagnostics import digest, file_digest, original_transformer
from portfolio_backtest import build_rebalance_targets, run_portfolio_model_backtest
from portfolio_statistics import holm_bonferroni, paired_block_bootstrap
from tools import compare_improved_forecast_portfolios as shared
from tools.diagnose_forecast_failures import write_json

DEFAULT_PARENT = ROOT / "logs/improved_forecast_three_portfolios_20261109"
METRICS = ["cagr", "annual_volatility", "sharpe", "max_drawdown", "net_cumulative_return",
           "avg_controlled_turnover", "transaction_costs", "final_value"]


def sources():
    return {**shared.sources(), "tools/compare_forecast_mpt_before_after.py": file_digest(__file__)}


def read_parent(parent):
    manifest = json.loads((parent / "manifest.json").read_text())
    if digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest["sha256"]:
        raise ValueError("Parent manifest drift")
    if (parent / "run.exit").read_text().strip() != "0":
        raise ValueError("Parent run is not complete")
    result = json.loads((parent / "result.json").read_text())
    if result["manifest_sha256"] != manifest["sha256"]:
        raise ValueError("Parent result contract mismatch")
    expected_forecast = {"position": False, "direct": True, "epochs": 5, "seed": 42, "lookback": 60}
    if any(manifest["forecast"][k] != v for k, v in expected_forecast.items()):
        raise ValueError("Parent improved forecast settings changed")
    if manifest["settings"] != shared.SETTINGS:
        raise ValueError("Parent execution settings changed")
    for value in manifest["inputs"].values():
        if file_digest(value["path"]) != value["sha256"]:
            raise ValueError("Parent input drift")
    saved_sources = result.get("analysis_source_hashes", manifest["sources"])
    if shared.sources() != saved_sources:
        raise ValueError("Parent analysis/model source drift")
    checkpoints = []
    for task in manifest["tasks"]:
        value = json.loads((parent / "checkpoints" / (task["id"] + ".json")).read_text())
        if value["task"] != task or value["manifest_sha256"] != manifest["sha256"] or value["status"] != "ok":
            raise ValueError("Parent checkpoint mismatch")
        checkpoints.append(value)
    return manifest, result, checkpoints


def prepare(output, parent):
    if (output / "manifest.json").exists():
        raise ValueError("Manifest exists; use run to resume")
    parent_manifest, result, _ = read_parent(parent)
    files = [parent / "manifest.json", parent / "result.json", parent / "run.exit"]
    files += [parent / "checkpoints" / (t["id"] + ".json") for t in parent_manifest["tasks"]]
    manifest = {
        "purpose": "diagnostic_only", "promotion_eligible": False,
        "created_at": datetime.now(timezone.utc).isoformat(), "parent": str(parent),
        "parent_manifest_sha256": parent_manifest["sha256"],
        "parent_files": {str(p): file_digest(p) for p in files},
        "inputs": parent_manifest["inputs"], "sources": sources(),
        "tasks": parent_manifest["tasks"], "tickers": parent_manifest["tickers"],
        "settings": shared.SETTINGS, "environment": parent_manifest["environment"],
        "legacy_forecast": {"class": "TransformerForecastModel", "horizon": 63, "seed": 42,
                            "epochs": 5, "output": "predict annual clipped log return converted to period log return",
                            "input_contract": "same 504 closing prices strictly before rebalance date"},
        "improved_forecast": parent_manifest["forecast"],
        "common_allocation": {"objective": "max_sharpe", "annual_mu": "expm1(period_log_return * 4)",
                              "covariance": "ledoit_wolf", "fallback": "GMV with explicit count"},
        "improved_reference": result["summary"]["model_mpt"],
        "improved_fallback_count": result["mpt_fallback_count"],
        "statistics": {"samples": 2000, "block_size": 21, "seed": 42,
                       "comparison": "improved_vs_legacy", "holm_family": ["higher_return", "higher_sharpe", "lower_volatility"]},
        "budget_seconds": 7200,
        "limitations": parent_manifest["limitations"] + [
            "Before/after forecast-path package comparison, not isolated direct-target causal attribution",
            "Legacy is the old Transformer forecast inside the same MPT, not the old rank-BL gauntlet",
            "No standalone ARIMA/hybrid or hyperparameter/seed search in this comparison"],
    }
    manifest["sha256"] = digest(manifest)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "manifest.json", manifest)
    return manifest


def verify(manifest):
    if digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest["sha256"]:
        raise ValueError("Manifest drift")
    if sources() != manifest["sources"]:
        raise ValueError("Source drift")
    for path, expected in manifest["parent_files"].items():
        if file_digest(path) != expected:
            raise ValueError("Parent artifact drift")
    for value in manifest["inputs"].values():
        if file_digest(value["path"]) != value["sha256"]:
            raise ValueError("Input drift")
    for package, version in manifest["environment"]["packages"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError("Dependency drift")


def worker(output, manifest, index):
    verify(manifest)
    task = manifest["tasks"][index]
    parent_path = Path(manifest["parent"]) / "checkpoints" / (task["id"] + ".json")
    improved = json.loads(parent_path.read_text())
    prices = shared.panel({k: v["path"] for k, v in manifest["inputs"].items()})
    i = task["index"]
    train = prices.iloc[i - 504:i]
    if digest(train.to_numpy().tolist()) != improved["train_prices_sha256"]:
        raise ValueError("Legacy/improved training input mismatch")
    predictions = {ticker: original_transformer(train[ticker].to_numpy(), horizon=63, seed=42)
                   for ticker in manifest["tickers"]}
    # This field reproduces predict()'s annual clipping, not forecast(annualize=False).
    scores = {ticker: prediction["original_hybrid_component"] for ticker, prediction in predictions.items()}
    weights, diagnostics = shared.weights_for_origin(train, scores)
    value = {"manifest_sha256": manifest["sha256"], "task": task, "status": "ok",
             "train_prices_sha256": improved["train_prices_sha256"],
             "train_start": improved["train_start"], "train_end": improved["train_end"],
             "period_end": improved["period_end"], "predictions": predictions,
             "legacy_period_scores": scores, "weights": weights["model_mpt"], "diagnostics": diagnostics}
    write_json(output / "checkpoints" / (task["id"] + ".json"), value)


def replay(prices, manifest, legacy, improved):
    tasks = manifest["tasks"]
    expected_dates = [t["origin"] for t in tasks]
    if [c["task"]["origin"] for c in legacy] != expected_dates or [c["task"]["origin"] for c in improved] != expected_dates:
        raise ValueError("Missing or reordered forecast origins")
    first, last = tasks[0]["index"], tasks[-1]["index"]
    prices = prices.iloc[first - 504:last + 64]
    targets = build_rebalance_targets(prices, models=["min_variance"], train_window=504,
                                      rebalance_frequency=63, forecast_horizon=63, max_asset_weight=.2,
                                      risk_free_rate=.02, target_turnover_limit=.35)
    if [t["rebalance_date"] for t in targets["records"]] != expected_dates:
        raise ValueError("Execution calendar mismatch")
    runs = {}
    for name, saved in [("legacy_mpt", legacy), ("improved_mpt", improved)]:
        own = copy.deepcopy(targets)
        for target, checkpoint in zip(own["records"], saved):
            model = target["models"]["min_variance"]
            model["weights"] = checkpoint["weights"] if name == "legacy_mpt" else checkpoint["weights"]["model_mpt"]
            scores = (checkpoint["legacy_period_scores"] if name == "legacy_mpt" else
                      {k: v["raw"] for k, v in checkpoint["predictions"].items()})
            model["diagnostics"].update(construction_method=name, signal_scores=scores)
        runs[name] = run_portfolio_model_backtest(prices, models=["min_variance"], rebalance_targets=own,
                                                include_daily_returns=True, **shared.SETTINGS)
    summary = {name: run["summary_by_model"]["min_variance"] for name, run in runs.items()}
    for metric in METRICS:
        expected = manifest["improved_reference"].get(metric)
        actual = summary["improved_mpt"].get(metric)
        if expected is None and actual is None:
            continue
        if expected is None or actual is None or not np.isclose(actual, expected, rtol=1e-10, atol=1e-10):
            raise ValueError("Saved improved MPT did not reproduce: " + metric)
    daily = {name: shared.net_daily_returns(run) for name, run in runs.items()}
    if list(daily["legacy_mpt"].index) != list(daily["improved_mpt"].index):
        raise ValueError("Daily return calendars differ")
    bootstrap = paired_block_bootstrap(daily["improved_mpt"], daily["legacy_mpt"], risk_free_rate=.02,
                                       block_size=21, samples=2000, seed=42)
    corrected = holm_bonferroni({metric: 1 - value if value is not None else 1.
                                for metric, value in bootstrap["probability"].items()})
    return {"purpose": "diagnostic_only", "promotion_eligible": False, "manifest_sha256": manifest["sha256"],
            "parent_manifest_sha256": manifest["parent_manifest_sha256"],
            "start": tasks[0]["origin"], "end": improved[-1]["period_end"], "origins": len(tasks),
            "daily_observations": len(daily["legacy_mpt"]), "summary": summary,
            "improved_minus_legacy": {m: summary["improved_mpt"][m] - summary["legacy_mpt"][m]
                                      if summary["improved_mpt"].get(m) is not None and summary["legacy_mpt"].get(m) is not None else None
                                      for m in METRICS},
            "fallback_counts": {"legacy_mpt": sum(c["diagnostics"]["mpt_fallback_to_gmv"] for c in legacy),
                                "improved_mpt": manifest["improved_fallback_count"]},
            "paired_bootstrap_improved_vs_legacy": bootstrap, "holm": corrected,
            "daily_returns": {k: v.to_dict() for k, v in daily.items()},
            "rebalance_records": {k: v["rebalance_records"] for k, v in runs.items()},
            "improved_reference_reproduced": True, "limitations": manifest["limitations"]}


def report(output, result):
    write_json(output / "result.json", result)
    lines = ["# 기존 반복 예측 MPT 대비 개선 직접 예측 MPT", "", "- diagnostic_only / 승격 근거 아님",
             f"- 기간: {result['start']} ~ {result['end']}, origin {result['origins']}개",
             "- 개선 모델은 이전 결과를 재사용했고 같은 성과의 재현을 검산했습니다.", "",
             "| 방식 | CAGR | 변동성 | Sharpe | 최대낙폭 | 누적수익률 |", "|---|---:|---:|---:|---:|---:|"]
    for name, row in result["summary"].items():
        sharpe = "NA" if row["sharpe"] is None else f"{row['sharpe']:.4f}"
        lines.append(f"| {name} | {row['cagr']:.4%} | {row['annual_volatility']:.4%} | {sharpe} | {row['max_drawdown']:.4%} | {row['net_cumulative_return']:.4%} |")
    lines += ["", "## 개선 − 기존", "", "```json",
              json.dumps(result["improved_minus_legacy"], indent=2), "```",
              "", f"- GMV 대체 횟수: {result['fallback_counts']}",
              "- Bootstrap 반환 차이는 연환산 평균수익률이며 CAGR 차이 검정이 아닙니다.",
              "- Bootstrap 부호 비율을 미래 승률로 해석하지 않습니다.",
              "- 두 예측 경로 전체의 비교이며 direct target만의 단독 인과 효과가 아닙니다.",
              "", "## 한계", ""] + ["- " + s for s in result["limitations"]]
    (output / "report.md").write_text("\n".join(lines) + "\n")


def run(output, manifest):
    verify(manifest)
    (output / "checkpoints").mkdir(exist_ok=True)
    state_path = output / "run_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state["manifest_sha256"] != manifest["sha256"]:
            raise ValueError("Run state mismatch")
    else:
        state = {"manifest_sha256": manifest["sha256"], "started_at": time.time()}
        write_json(state_path, state)
    legacy = []
    for index, task in enumerate(manifest["tasks"]):
        path = output / "checkpoints" / (task["id"] + ".json")
        if not path.exists():
            remaining = manifest["budget_seconds"] - (time.time() - state["started_at"])
            if remaining < 120:
                raise RuntimeError("Budget exhausted; no partial period comparison")
            print(json.dumps({"event": "legacy_start", "task": task}), flush=True)
            with (output / "worker.log").open("a") as log:
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "worker", "--output", str(output), "--index", str(index)],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=remaining - 60)
        value = json.loads(path.read_text())
        if value["manifest_sha256"] != manifest["sha256"] or value["task"] != task or value["status"] != "ok":
            raise ValueError("Legacy checkpoint mismatch")
        legacy.append(value)
        print(json.dumps({"event": "legacy_done", "origin": task["origin"], "completed": len(legacy)}), flush=True)
    _, _, improved = read_parent(Path(manifest["parent"]))
    prices = shared.panel({k: v["path"] for k, v in manifest["inputs"].items()})
    report(output, replay(prices, manifest, legacy, improved))
    print("Before/after MPT diagnostic completed", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "worker"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--index", type=int)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.command == "prepare":
        manifest = prepare(output, args.parent.resolve())
        print(json.dumps({"manifest": str(output / 'manifest.json'), "sha256": manifest['sha256'], "origins": len(manifest['tasks'])}))
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
