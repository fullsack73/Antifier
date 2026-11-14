#!/usr/bin/env python3
"""Offline, budgeted forecast failure attribution; no production promotion."""

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))
from native_threading import configure_native_threading

configure_native_threading(force=True)
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import pandas as pd

from forecast_failure_diagnostics import (
    CONTROL_TICKERS, PIT_COLUMNS, SEEDS, TICKERS, arima_forecast,
    build_transformer, digest, file_digest, original_transformer, period_outputs,
    ridge_predict, summarize, target_at, transformer_forecast,
)
from cross_sectional_forecast import POOLED_FEATURE_COLUMNS, pooled_price_features
from forecast_models import TransformerForecastModel
from portfolio_alpha_v2 import normalize_point_in_time_features, point_in_time_snapshot
from universe_manifest import normalize_universe_manifest, universe_snapshot

DERIVED = ROOT / "data" / "research" / "derived"
INPUTS = {
    "ohlcv": DERIVED / "nasdaq100_ohlcv_2017_2026.csv",
    "membership": DERIVED / "nasdaq100_membership_events_2016_2025.csv",
    "pit": DERIVED / "nasdaq100_sec_pit_features_2017_2025.csv",
    "market": DERIVED / "us_market_factors_2007_2025.csv",
    "policy": ROOT / "data/research/research_policy_v1.json",
    "consumed_registry": ROOT / "data/research/evidence_consumption_v1.jsonl",
    "consumed_split": DERIVED / "nasdaq100_patch_transformer_fresh_validation_split_v1.json",
}
STAGES = {"A": 45 * 60, "B": 45 * 60, "C": 210 * 60, "D": 120 * 60}
COMPARISONS = [
    ("canonical_transformer", "original_transformer"),
    ("canonical_hybrid", "original_hybrid"),
    ("canonical_arima", "historical_mean"),
    ("canonical_arima", "fixed_ar1"),
    ("p1_d0", "p0_d0"), ("p0_d1", "p0_d0"),
    ("p1_d1", "p0_d1"), ("p1_d1", "p1_d0"),
    ("epochs50", "p0_d0"), ("window1008", "p0_d0"),
    ("ridge_market_504", "ridge_price_504"),
    ("ridge_pit_504", "ridge_market_504"),
    ("ridge_price_1008", "ridge_price_504"),
    ("factor_position", "factor_reference"),
    ("factor_direct", "factor_reference"),
    ("factor_interaction", "factor_zero"),
] + [(m, b) for m in ["canonical_arima", "canonical_transformer", "canonical_hybrid"]
     for b in ["zero", "historical_mean", "ridge_price_504"]]


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    def clean(item):
        if isinstance(item, dict):
            return {k: clean(v) for k, v in item.items()}
        if isinstance(item, (tuple, list)):
            return [clean(v) for v in item]
        if isinstance(item, np.generic):
            return clean(item.item())
        if isinstance(item, float) and not np.isfinite(item):
            return None
        return item
    temp.write_text(json.dumps(clean(value), indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def load_inputs(paths):
    long = pd.read_csv(paths["ohlcv"], usecols=["timestamp", "ticker", "close"])
    long["timestamp"] = pd.to_datetime(long.timestamp)
    if long.duplicated(["timestamp", "ticker"]).any():
        raise ValueError("Duplicate OHLCV timestamps/tickers")
    prices = long.pivot(index="timestamp", columns="ticker", values="close").sort_index()
    prices = prices.loc[:"2025-12-31"].reindex(columns=TICKERS)
    if not prices.index.is_unique or prices.empty:
        raise ValueError("Missing price calendar")
    if ((prices <= 0) & prices.notna()).any().any():
        raise ValueError("Nonpositive prices")
    membership = normalize_universe_manifest(pd.read_csv(paths["membership"]))
    pit = normalize_point_in_time_features(pd.read_csv(paths["pit"]))
    market = pd.read_csv(paths["market"], index_col=0, parse_dates=True).sort_index()
    if market.index.has_duplicates:
        raise ValueError("Duplicate market factor dates")
    return prices, membership, pit, market


def source_hashes():
    paths = [Path(__file__), ROOT / "src/backend/forecast_failure_diagnostics.py",
             ROOT / "src/backend/forecast_models.py", ROOT / "src/backend/cross_sectional_forecast.py",
             ROOT / "src/backend/portfolio_alpha_v2.py", ROOT / "src/backend/universe_manifest.py",
             ROOT / "src/backend/portfolio_statistics.py"]
    return {str(p.relative_to(ROOT)): file_digest(p) for p in paths}


def prepare(output):
    output.mkdir(parents=True, exist_ok=True)
    prices, membership, _, _ = load_inputs(INPUTS)
    from research_split import validate_evidence_use
    evidence = validate_evidence_use(json.loads(INPUTS["consumed_split"].read_text()),
                                     requested_use="diagnostic", acknowledge_consumed=True)
    first = prices.index.searchsorted(pd.Timestamp("2019-01-01"))
    origins = list(range(first, len(prices) - 63, 63))
    selected = [origins[i] for i in np.linspace(0, len(origins) - 1, min(12, len(origins)), dtype=int)]
    tasks = [{"stage": "A", "kind": "integrity"}]
    tasks += [{"stage": "B", "kind": "synthetic", "process": process, "data_seed": seed}
              for process in ["noise", "ar1", "order", "external"] for seed in [101, 102, 103]]
    # Breadth-first baseline, then complete factorial bundles in fixed time order.
    tasks += [{"stage": "C", "kind": "baseline", "cutoff": i, "ticker": ticker}
              for i in origins for ticker in TICKERS]
    tasks += [{"stage": "C", "kind": "controls", "cutoff": i, "ticker": ticker, "seed": seed}
              for i in selected for ticker in CONTROL_TICKERS for seed in SEEDS]
    tasks += [{"stage": "D", "kind": "information", "window": w} for w in [504, 1008]]
    for task in tasks:
        task["id"] = digest(task)
    manifest = {
        "schema_version": 1, "purpose": "diagnostic_only", "promotion_eligible": False,
        "consumed_validation_acknowledged": True, "primary_horizon": 63,
        "evidence_use": evidence,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {k: {"path": str(p), "sha256": file_digest(p)} for k, p in INPUTS.items()},
        "sources": source_hashes(), "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_diff_sha256": digest(subprocess.check_output(["git", "diff"], cwd=ROOT, text=True)),
        "environment": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
                        "cpu_count": os.cpu_count(), "native_threads": 1,
                        "packages": {m: importlib.metadata.version(m) for m in
                                     ["numpy", "pandas", "tensorflow", "pmdarima", "scikit-learn", "statsmodels"]}},
        "settings": {"tickers": TICKERS, "control_tickers": CONTROL_TICKERS,
                     "seeds": SEEDS, "data_seeds": [101, 102, 103], "horizons": [1, 21, 63, 252],
                     "train_window": 504, "long_window": 1008, "ridge_penalty": 5,
                     "bootstrap_samples": 2000, "bootstrap_seed": 42, "block_origins": 2,
                     "total_seconds": 28800, "report_reserve_seconds": 3600,
                     "stages_seconds": STAGES, "lookback": 60,
                     "synthetic_gate": {"mse_ratio_max": 0.9, "required_processes": ["ar1", "order"]}},
        "origins": [str(prices.index[i].date()) for i in origins],
        "control_origins": [str(prices.index[i].date()) for i in selected],
        "comparisons": COMPARISONS, "tasks": tasks,
        "limitations": ["Consumed public adjusted-price diagnostic; no fresh validation or promotion",
                        "Missing/delisted securities not replaced", "Teacher forcing uses future information"],
    }
    manifest["sha256"] = digest(manifest)
    path = output / "manifest.json"
    if path.exists():
        raise ValueError("Manifest already exists; use run to resume without rewriting it")
    write_json(path, manifest)
    return manifest


def verify_manifest(manifest):
    body = {k: v for k, v in manifest.items() if k != "sha256"}
    if digest(body) != manifest["sha256"]:
        raise ValueError("Manifest drift")
    if manifest["sources"] != source_hashes():
        raise ValueError("Source drift: start a separate diagnostic campaign")
    for name, version in manifest.get("environment", {}).get("packages", {}).items():
        if importlib.metadata.version(name) != version:
            raise ValueError("Dependency drift: " + name)
    for value in manifest["inputs"].values():
        if file_digest(value["path"]) != value["sha256"]:
            raise ValueError("Input data drift: " + value["path"])


def record(model, origin, ticker, actual, prediction, seed=42, horizon=63, **extra):
    if not np.isfinite([actual, prediction]).all():
        raise ValueError("Nonfinite forecast or actual")
    return {"status": "ok", "model": model, "origin": str(origin), "ticker": ticker,
            "seed": seed, "horizon": horizon, "actual": float(actual), "prediction": float(prediction), **extra}


def integrity_checks():
    import tensorflow as tf
    from forecast_failure_diagnostics import purged_split, supervised_returns

    p = np.exp(np.arange(700) * 0.001)
    assert abs(target_at(p, 504, 63) - .063) < 1e-10
    r, x, y, ends = supervised_returns(p, 63)
    tr, va = purged_split(ends, 63)
    assert ends[tr[-1]] + 63 <= ends[va[0]]
    def fail(*args, **kwargs):
        raise RuntimeError("forced_arima_failure")
    fallback = arima_forecast(p, loader=lambda: fail)
    short = arima_forecast(p[:5])
    assert fallback["path"] == "trend_fallback" and short["path"] == "short_input_constant"
    limiting = period_outputs(2., 2., 63)
    assert limiting["original_standalone"] != limiting["original_hybrid_component"]
    differences = {}
    tensor = np.random.default_rng(42).normal(size=(1, 60, 1)).astype("float32")
    for position in [False, True]:
        model = build_transformer(position)
        differences[str(position)] = abs(float(np.asarray(model(tensor, training=False))[0, 0]) -
                                         float(np.asarray(model(tensor[:, ::-1], training=False))[0, 0]))
        tf.keras.backend.clear_session()
    assert differences["False"] < 1e-5
    assert differences["True"] > 1e-7
    # Exercise the same dated slicing used by the real-data runner.
    dates = pd.bdate_range("2017-01-01", periods=len(p))
    panel = pd.DataFrame({"AAPL": p}, index=dates)
    membership = pd.DataFrame([{"effective_date": dates[0], "ticker": "AAPL", "in_universe": True}])
    before = usable_history(panel, membership, 504, "AAPL", 504)
    panel.loc[dates[568]:, "AAPL"] *= 10
    assert np.array_equal(before, usable_history(panel, membership, 504, "AAPL", 504))
    pit = pd.DataFrame([{"ticker": "AAPL", "available_date": dates[i], "sector": "Tech", "market_cap": 1e9,
                         "quality": q, "profitability": .2, "valuation": .3, "liquidity": .4}
                        for i, q in [(400, .1), (600, 10.)]])
    snapshot = point_in_time_snapshot(pit, dates[504])
    pit.loc[1, "quality"] = -100
    pd.testing.assert_frame_equal(snapshot, point_in_time_snapshot(pit, dates[504]))
    return {"checks_passed": True, "position_differences": differences, "forced_arima": fallback,
            "short_arima": short, "limiting_example": limiting,
            "findings": ["Existing unpositioned attention+average pooling is permutation invariant",
                         "Standalone and hybrid output clipping differ",
                         "ARIMA can silently substitute trend or constant",
                         "ARIMA path dispersion is not predictive error variance"]}


def synthetic_task(task):
    rng = np.random.default_rng(task["data_seed"])
    n = 1600
    innovations = rng.normal(0, .003, n)
    z = rng.normal(size=n)
    returns = innovations.copy()
    process = task["process"]
    for i in range(2, n):
        if process == "ar1":
            returns[i] += .9 * returns[i - 1]
        elif process == "order":
            returns[i] += .8 * returns[i - 1] - .6 * returns[i - 2]
        elif process == "external":
            returns[i] += .04 * z[i]
    prices = np.exp(np.r_[0., np.cumsum(returns)])
    cutoff = 1200
    history = prices[:cutoff + 1]
    # Evaluate a full held-out block of one-step targets, not one lucky outcome.
    predictions, models = {}, {}
    from forecast_failure_diagnostics import purged_split, supervised_returns
    from sklearn.preprocessing import StandardScaler
    import tensorflow as tf
    _, x, y, ends = supervised_returns(history, 1)
    tr, va = purged_split(ends, 1)
    xs = StandardScaler().fit(x[tr].reshape(-1, 1))
    ys = StandardScaler().fit(y[tr, None])
    test_x = np.array([returns[i - 60:i] for i in range(cutoff, n)])[..., None]
    actual = returns[cutoff:]
    reference = float(np.mean((actual - returns[:cutoff].mean()) ** 2))
    legacy = TransformerForecastModel(random_state=42)
    try:
        legacy.train(history)
        if legacy.model is None:
            raise ValueError("Legacy synthetic Transformer training failed")
        legacy_test = test_x[:, -legacy.lookback:, :]
        pred = legacy.scaler.inverse_transform(np.asarray(legacy.model(
            legacy.scaler.transform(legacy_test.reshape(-1, 1)).reshape(legacy_test.shape), training=False))).ravel()
        models["legacy_transformer_mse_ratio"] = float(np.mean((pred - actual) ** 2) / reference)
    finally:
        legacy.cleanup()
    for seed in SEEDS:
        model = build_transformer(True, seed)
        try:
            h = model.fit(xs.transform(x[tr].reshape(-1, 1)).reshape(x[tr].shape),
                          ys.transform(y[tr, None]), epochs=50, batch_size=32, verbose=0,
                          shuffle=False, validation_data=(xs.transform(x[va].reshape(-1, 1)).reshape(x[va].shape), ys.transform(y[va, None])),
                          callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=7, restore_best_weights=True)])
            pred = ys.inverse_transform(np.asarray(model(xs.transform(test_x.reshape(-1, 1)).reshape(test_x.shape), training=False))).ravel()
            predictions[str(seed)] = {"mse": float(np.mean((pred - actual) ** 2)),
                                      "mse_ratio": float(np.mean((pred - actual) ** 2) / reference),
                                      "train_loss": h.history["loss"], "val_loss": h.history["val_loss"]}
            if h.history["loss"][-1] >= .95 * h.history["loss"][0]:
                tiny_x = xs.transform(x[tr[:32]].reshape(-1, 1)).reshape(-1, 60, 1)
                tiny_y = ys.transform(y[tr[:32], None])
                before = float(model.evaluate(tiny_x, tiny_y, verbose=0))
                tiny_h = model.fit(tiny_x, tiny_y, epochs=100, verbose=0, shuffle=False)
                predictions[str(seed)]["tiny_overfit"] = {"before": before, "after": float(tiny_h.history["loss"][-1])}
        finally:
            tf.keras.backend.clear_session()
    if process in ["ar1", "order", "noise"]:
        # Forecast ARIMA one step for the entire holdout using fixed fitted parameters.
        from forecast_models import _load_auto_arima
        fitted = _load_auto_arima()(returns[:cutoff], seasonal=False, suppress_warnings=True,
                                   error_action="ignore", max_p=3, max_q=3, max_d=2)
        pred = []
        for value in actual:
            pred.append(float(fitted.predict(1)[0]))
            # append without parameter refitting to avoid hundreds of auto_arima searches.
            fitted.arima_res_ = fitted.arima_res_.append([value], refit=False)
        models["arima_mse_ratio"] = float(np.mean((np.array(pred) - actual) ** 2) / reference)
    oracle = np.zeros_like(actual)
    if process == "ar1":
        oracle = .9 * returns[cutoff - 1:n - 1]
    elif process == "order":
        oracle = .8 * returns[cutoff - 1:n - 1] - .6 * returns[cutoff - 2:n - 2]
    elif process == "external":
        oracle = .04 * z[cutoff:]
        visible = ridge_predict(z[:cutoff, None], returns[:cutoff], z[cutoff:, None])
        models["external_visible_mse_ratio"] = float(np.mean((visible - actual) ** 2) / reference)
    return {"process": process, "data_seed": task["data_seed"], "transformer": predictions,
            "oracle_mse_ratio": float(np.mean((oracle - actual) ** 2) / reference), **models}


def gate_results(checkpoints):
    a = [c for c in checkpoints if c["task"]["stage"] == "A"]
    integrity = bool(a and a[0]["status"] == "ok" and a[0]["result"].get("checks_passed"))
    results = [c["result"] for c in checkpoints if c["task"]["stage"] == "B" and c["status"] == "ok"]
    complete = all({r["data_seed"] for r in results if r["process"] == process} == {101, 102, 103}
                   for process in ["noise", "ar1", "order", "external"])
    visible = [r["external_visible_mse_ratio"] for r in results if r["process"] == "external"]
    external_passed = len(visible) == 3 and float(np.mean(visible)) < .1
    gate = {"integrity": integrity, "all_synthetic_controls_completed": complete,
            "external_information_recovered": bool(external_passed)}
    for model in ["transformer", "arima"]:
        passing = integrity and complete and external_passed
        detail = {}
        for process in ["ar1", "order"]:
            subset = [r for r in results if r["process"] == process]
            ratios = ([p["mse_ratio"] for r in subset for p in r["transformer"].values()]
                      if model == "transformer" else [r["arima_mse_ratio"] for r in subset])
            passed = bool({r["data_seed"] for r in subset} == {101, 102, 103} and ratios and np.mean(ratios) < .9)
            detail[process] = {"data_seeds_completed": len(subset), "mean_mse_ratio": float(np.mean(ratios)) if ratios else None, "passed": passed}
            passing = passing and passed
        gate[model] = {"passed": bool(passing), "processes": detail}
    return gate


def usable_history(prices, membership, cutoff, ticker, window, horizon=63):
    date = prices.index[cutoff]
    if ticker not in universe_snapshot(membership, date):
        raise ValueError("not_in_dated_universe")
    if cutoff + 1 < window:
        raise ValueError("insufficient_history")
    values = prices[ticker].iloc[cutoff + 1 - window:cutoff + 1].to_numpy()
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("missing_training_price")
    target_at(prices[ticker], cutoff, horizon)
    return values


def baseline_task(task, inputs, gates):
    prices, membership, _, _ = inputs
    i, ticker = task["cutoff"], task["ticker"]
    try:
        history = usable_history(prices, membership, i, ticker, 504)
    except ValueError as exc:
        return {"records": [], "availability": str(exc)}
    from forecast_models import _load_auto_arima
    trained = TransformerForecastModel() if gates["transformer"]["passed"] else None
    if trained is not None:
        trained.train(history)
    fitted_arima = []

    def cached_fit(values, **kwargs):
        if not fitted_arima:
            fitted_arima.append(_load_auto_arima()(values, **kwargs))
        return fitted_arima[0]

    try:
        return baseline_predictions(prices, i, ticker, history, gates, trained, lambda: cached_fit)
    finally:
        if trained is not None:
            trained.cleanup()


def baseline_predictions(prices, i, ticker, history, gates, trained, arima_loader):
    origin = str(prices.index[i].date())
    records, diagnostics = [], {}
    arima = None
    for horizon in [63, 1, 21, 252]:
        if i + horizon >= len(prices):
            continue
        try:
            actual = target_at(prices[ticker], i, horizon)
        except ValueError:
            continue
        suffix = "" if horizon == 63 else f"_h{horizon}"
        records += [record("zero" + suffix, origin, ticker, actual, 0., horizon=horizon),
                    record("historical_mean" + suffix, origin, ticker, actual,
                           np.diff(np.log(history)).mean() * horizon, horizon=horizon)]
        if gates["arima"]["passed"]:
            arima = arima_forecast(history, horizon, loader=arima_loader)
            diagnostics["arima" + suffix] = arima
            records += [record("canonical_arima" + suffix, origin, ticker, actual, arima["raw"], horizon=horizon),
                        record("original_arima" + suffix, origin, ticker, actual, arima["raw"], horizon=horizon)]
            if horizon == 63:
                fixed = arima_forecast(history, horizon, fixed=True)
                records.append(record("fixed_ar1", origin, ticker, actual, fixed["raw"]))
        if gates["transformer"]["passed"]:
            tf_result = original_transformer(history, horizon, trained_model=trained)
            diagnostics["transformer" + suffix] = tf_result
            records += [record("original_transformer" + suffix, origin, ticker, actual, tf_result["original_standalone"], horizon=horizon),
                        record("canonical_transformer" + suffix, origin, ticker, actual, tf_result["raw"], horizon=horizon)]
            if arima is not None:
                records += [record("original_hybrid" + suffix, origin, ticker, actual,
                                   (arima["raw"] + tf_result["original_hybrid_component"]) / 2, horizon=horizon),
                            record("canonical_hybrid" + suffix, origin, ticker, actual,
                                   (arima["raw"] + tf_result["raw"]) / 2, horizon=horizon)]
    for r in records:
        r.update(target_date=str(prices.index[i + r["horizon"]].date()),
                 train_start=str(prices.index[i - 503].date()), train_end=origin)
    return {"records": records, "diagnostics": diagnostics}


def controls_task(task, inputs):
    prices, membership, _, _ = inputs
    i, ticker, seed = task["cutoff"], task["ticker"], task["seed"]
    try:
        history = usable_history(prices, membership, i, ticker, 504)
    except ValueError as exc:
        return {"records": [], "availability": str(exc)}
    actual = target_at(prices[ticker], i, 63)
    origin = str(prices.index[i].date())
    future = np.diff(np.log(prices[ticker].iloc[i:i + 64].to_numpy()))
    records, diagnostics = [], {}
    for name, position, direct, epochs, window in [
        ("p0_d0", False, False, 5, 504), ("p1_d0", True, False, 5, 504),
        ("p0_d1", False, True, 5, 504), ("p1_d1", True, True, 5, 504),
        ("epochs50", False, False, 50, 504), ("window1008", False, False, 5, 1008),
    ]:
        try:
            values = usable_history(prices, membership, i, ticker, window)
        except ValueError as exc:
            diagnostics[name] = {"status": "unavailable", "reason": str(exc)}
            continue
        result = transformer_forecast(values, position=position, direct=direct, epochs=epochs, seed=seed,
                                      future=future if name == "p0_d0" else None)
        diagnostics[name] = result
        records.append(record(name, origin, ticker, actual, result["raw"], seed=seed,
                              target_date=str(prices.index[i + 63].date()),
                              train_start=str(prices.index[i + 1 - window].date()), train_end=origin))
        if name == "p0_d0":
            records.append(record("teacher_forced_future_diagnostic", origin, ticker, actual,
                                  result["teacher_forced_diagnostic"], seed=seed, uses_future=True))
    # Factor contrasts in squared-error space, including the interaction.
    errors = {r["model"]: (r["prediction"] - actual) ** 2 for r in records}
    if all(k in errors for k in ["p0_d0", "p1_d0", "p0_d1", "p1_d1"]):
        contrasts = {"position": .5 * (errors["p1_d0"] + errors["p1_d1"] - errors["p0_d0"] - errors["p0_d1"]),
                     "direct": .5 * (errors["p0_d1"] + errors["p1_d1"] - errors["p0_d0"] - errors["p1_d0"]),
                     "interaction": errors["p1_d1"] - errors["p1_d0"] - errors["p0_d1"] + errors["p0_d0"]}
    else:
        contrasts = {}
    return {"records": records, "diagnostics": diagnostics, "factor_mse_contrasts": contrasts}


def information_rows(inputs):
    prices, membership, pit, market = inputs
    rows = []
    # Dense completed labels for ridge; all feature construction stops at as-of.
    for i in range(252, len(prices) - 63, 21):
        date = prices.index[i]
        history = prices.iloc[:i + 1]
        features = pooled_price_features(history)
        snapshot = point_in_time_snapshot(pit, date, tickers=TICKERS).reindex(TICKERS)
        m = market.loc[:date].tail(63)
        market_values = [m[c].mean() for c in ["mkt_rf", "smb", "hml", "rf_daily"]]
        for ticker in TICKERS:
            if ticker not in universe_snapshot(membership, date):
                continue
            try:
                actual = target_at(prices[ticker], i, 63)
            except ValueError:
                continue
            rows.append({"index": i, "ticker": ticker, "target_end": i + 63, "actual": actual,
                         "price": features.loc[ticker, list(POOLED_FEATURE_COLUMNS)].tolist(),
                         "market": market_values, "pit": snapshot.loc[ticker, PIT_COLUMNS].tolist()})
    return rows


def information_task(task, inputs, manifest):
    prices, membership, pit, market = inputs
    rows = information_rows(inputs)
    records, coverage = [], []
    window = task["window"]
    for origin in manifest["origins"]:
        i = prices.index.get_loc(pd.Timestamp(origin))
        train = [r for r in rows if i - window <= r["index"] and r["target_end"] <= i]
        if len(train) < 60 or i < window - 1:
            continue
        features = pooled_price_features(prices.iloc[:i + 1])
        snap = point_in_time_snapshot(pit, origin, tickers=TICKERS).reindex(TICKERS)
        m = market.loc[:origin].tail(63)
        mv = [m[c].mean() for c in ["mkt_rf", "smb", "hml", "rf_daily"]]
        test = []
        for ticker in TICKERS:
            try:
                usable_history(prices, membership, i, ticker, 504)
                actual = target_at(prices[ticker], i, 63)
            except ValueError:
                continue
            test.append({"ticker": ticker, "actual": actual,
                         "price": features.loc[ticker, list(POOLED_FEATURE_COLUMNS)].tolist(),
                         "market": mv, "pit": snap.loc[ticker, PIT_COLUMNS].tolist()})
        if not test:
            continue
        for name, groups in [("price", ["price"]), ("market", ["price", "market"]),
                             ("pit", ["price", "market", "pit"])]:
            def matrix(items):
                return np.asarray([sum([r[g] for g in groups], []) for r in items], dtype=float)
            pred = ridge_predict(matrix(train), [r["actual"] for r in train], matrix(test))
            for r, prediction in zip(test, pred):
                records.append(record(f"ridge_{name}_{window}", origin, r["ticker"], r["actual"], prediction,
                                      target_date=str(prices.index[i + 63].date()),
                                      pit_available=bool(np.isfinite(r["pit"]).all())))
        coverage.append({"origin": origin, "training_rows": len(train), "test_rows": len(test),
                         "pit_complete_rows": sum(np.isfinite(r["pit"]).all() for r in test),
                         "latest_training_target": str(prices.index[max(r["target_end"] for r in train)].date())})
    return {"records": records, "coverage": coverage}


def execute_task(task, manifest, gates):
    if task["kind"] == "integrity":
        return integrity_checks()
    if task["kind"] == "synthetic":
        return synthetic_task(task)
    inputs = load_inputs({k: v["path"] for k, v in manifest["inputs"].items()})
    if task["kind"] == "baseline":
        return baseline_task(task, inputs, gates)
    if task["kind"] == "controls":
        return controls_task(task, inputs)
    return information_task(task, inputs, manifest)


def checkpoint_path(output, task):
    return output / "checkpoints" / (task["id"] + ".json")


def read_checkpoints(output, manifest):
    checkpoints = []
    for task in manifest["tasks"]:
        path = checkpoint_path(output, task)
        if path.exists():
            value = json.loads(path.read_text())
            if value["manifest_sha256"] != manifest["sha256"] or value["task"] != task:
                raise ValueError("Checkpoint contract mismatch")
            checkpoints.append(value)
    return checkpoints


def render_report(output, manifest):
    checkpoints = read_checkpoints(output, manifest)
    records = [r for c in checkpoints if c["status"] == "ok" for r in c["result"].get("records", [])]
    for checkpoint in checkpoints:
        result = checkpoint.get("result", {})
        component = result.get("diagnostics", {}).get("transformer", {}).get("original_hybrid_component")
        if component is None:
            continue
        hybrid = next((r for r in result.get("records", []) if r["model"] == "original_hybrid"), None)
        if hybrid is not None:
            records.append({**hybrid, "model": "original_transformer_component", "prediction": component,
                            "derived_from_saved_component": True})
    # Factorial contrasts are already signed differences of MSE, not predictions.
    factor_values = []
    for c in checkpoints:
        for name, value in c.get("result", {}).get("factor_mse_contrasts", {}).items():
            t = c["task"]
            factor_values.append({"name": name, "origin": manifest["origins"][0] if "cutoff" not in t else t["cutoff"],
                                  "ticker": t.get("ticker"), "seed": t.get("seed"), "value": value})
    primary = [r for r in records if r["horizon"] == 63]
    summary = summarize(primary, manifest["comparisons"])
    # Signed factorial effects use the same clustered paired bootstrap routine.
    from forecast_failure_diagnostics import paired_mse_bootstrap
    factor_frame = []
    for r in factor_values:
        for model, value in [("factor_" + r["name"], r["value"]), ("reference", 0.)]:
            factor_frame.append({"origin": r["origin"], "ticker": r["ticker"], "seed": r["seed"],
                                 "model": model, "error_squared": value})
    if factor_frame:
        for name in ["position", "direct", "interaction"]:
            comparison_name = "factor_" + name + "_vs_" + ("factor_zero" if name == "interaction" else "factor_reference")
            summary["comparisons"][comparison_name] = paired_mse_bootstrap(pd.DataFrame(factor_frame), "factor_" + name, "reference")
        from portfolio_statistics import holm_bonferroni
        holm = holm_bonferroni({k: v.get("p_value", 1.) for k, v in summary["comparisons"].items()})
        for k, v in summary["comparisons"].items():
            v["holm"] = holm[k]
    slices = {}
    for label, start, end in [("2019_2021", "2019", "2022"), ("2022_2023", "2022", "2024"), ("2024_2025", "2024", "2026")]:
        slices[label] = summarize([r for r in primary if start <= r["origin"] < end], [])
    for ticker in TICKERS:
        slices[ticker] = summarize([r for r in primary if r["ticker"] == ticker], [])
    for seed in SEEDS:
        slices["seed_" + str(seed)] = summarize([r for r in primary if r["seed"] == seed], [])
    slices["pit_complete"] = summarize([r for r in primary if r.get("pit_available")], [])
    arima_paths = {}
    for c in checkpoints:
        for name, diagnostics in c.get("result", {}).get("diagnostics", {}).items():
            if name.startswith("arima"):
                path = diagnostics.get("path", "unknown")
                arima_paths[path] = arima_paths.get(path, 0) + 1
    for path in arima_paths:
        eligible = {(r["origin"], r["ticker"]) for c in checkpoints
                    if c.get("result", {}).get("diagnostics", {}).get("arima", {}).get("path") == path
                    for r in c["result"].get("records", [])}
        slices["arima_path_" + path] = summarize([r for r in primary if (r["origin"], r["ticker"]) in eligible], [])
    statuses = {}
    for c in checkpoints:
        statuses[c["status"]] = statuses.get(c["status"], 0) + 1
    gates = gate_results(checkpoints)
    findings = [{"classification": "구현으로 확인", "finding": finding}
                for c in checkpoints if c["task"]["stage"] == "A" and c["status"] == "ok"
                for finding in c["result"]["findings"]]
    for name, comparison in summary["comparisons"].items():
        if comparison.get("status") == "ok":
            confirmed = comparison["mse_difference"] < 0 and comparison["upper_95"] < 0 and comparison["holm"]["significant"]
            controlled = name.startswith(("p0_", "p1_", "factor_", "epochs50_", "window1008_", "ridge_market_", "ridge_pit_", "ridge_price_1008_"))
            classification = ("통제 실험에서 기여 확인" if controlled else "가설과 부합") if confirmed else "증거 부족"
            findings.append({"classification": classification,
                             "comparison": name, "mse_difference": comparison["mse_difference"]})
    for model in ["arima", "transformer"]:
        if not gates[model]["passed"]:
            findings.append({"classification": "증거 부족", "model": model,
                             "finding": "Synthetic gate failed or incomplete; do not infer absence of market information"})
    result = {"purpose": "diagnostic_only", "promotion_eligible": False, "manifest_sha256": manifest["sha256"],
              "report_source_hashes": source_hashes(),
              "tasks_total": len(manifest["tasks"]), "task_status_counts": statuses,
              "pending_tasks": len(manifest["tasks"]) - len(checkpoints), "gates": gates,
              "summary": summary, "slices": slices, "findings": findings, "arima_path_counts": arima_paths,
              "secondary_horizons": {str(h): summarize([r for r in records if r["horizon"] == h], []) for h in [1, 21, 252]},
              "factor_mse_contrasts": factor_values,
              "limitations": manifest["limitations"] + ["Significance is diagnostic on consumed history, not fresh validation",
                                                        "Incomplete comparison bundles cannot establish a causal contribution"]}
    write_json(output / "result.json", result)
    lines = ["# 수익률 예측 실패 원인 분리 진단", "", "- 용도: diagnostic_only / production 승격 불가",
             f"- Manifest: `{manifest['sha256']}`", f"- 작업 상태: {statuses}", f"- 대기: {result['pending_tasks']}",
             "", "## 합성 대조군", "", "```json", json.dumps(gates, ensure_ascii=False, indent=2), "```",
             "", "## 63일 예측 오차", "", "| 모델 | 행 | 시점 | 날짜 동일가중 MSE | MAE | 편향 |", "|---|---:|---:|---:|---:|---:|"]
    for name, m in summary["metrics"].items():
        lines.append(f"| {name} | {m['rows']} | {m['origins']} | {m['date_equal_mse']:.7f} | {m['mae']:.5f} | {m['bias']:.5f} |")
    lines += ["", "## 원인별 판정", ""]
    for finding in findings:
        lines.append(f"- **{finding['classification']}**: {finding.get('finding', finding.get('comparison'))}")
    lines += ["", "## 해석 한계", "", "- 미완료·실패·예산 초과는 예측력 부재를 의미하지 않습니다.",
              "- 원인별 신뢰구간·Holm 보정·구간/종목/seed 결과와 혼합 오차 분해는 result.json에 보존합니다.",
              "- 실제 미래 값을 입력한 teacher forcing은 미래정보 진단이며 배포 가능한 예측이 아닙니다."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def run_campaign(output, manifest):
    verify_manifest(manifest)
    (output / "checkpoints").mkdir(exist_ok=True)
    state_path = output / "run_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state["manifest_sha256"] != manifest["sha256"]:
            raise ValueError("Run-state contract mismatch")
    else:
        state = {"manifest_sha256": manifest["sha256"], "started_at": time.time(), "stage_spent": {s: 0. for s in STAGES}, "durations": {}}
        write_json(state_path, state)
    # Recover an interrupted worker's spent wall time rather than granting a new budget.
    if state.get("in_flight"):
        flight = state.pop("in_flight")
        state["stage_spent"][flight["stage"]] += max(0., time.time() - flight["started_at"])
        write_json(state_path, state)
    try:
        for task in manifest["tasks"]:
            path = checkpoint_path(output, task)
            if path.exists():
                continue
            cps = read_checkpoints(output, manifest)
            gates = gate_results(cps)
            status = None
            if task["stage"] in ["C", "D"] and not gates["integrity"]:
                status = "blocked_integrity"
            if task["kind"] == "controls" and not gates["transformer"]["passed"]:
                status = "blocked_synthetic_gate"
            if task["kind"] in ["baseline", "information"] and not any(gates[m]["passed"] for m in ["arima", "transformer"]):
                status = "blocked_synthetic_gate"
            elapsed = time.time() - state["started_at"]
            stage_left = STAGES[task["stage"]] - state["stage_spent"][task["stage"]]
            overall_left = 25200 - elapsed
            timings = state["durations"].get(task["kind"], [])
            estimate = max(timings[-5:]) * 1.5 if timings else 60.
            remaining = min(stage_left, overall_left)
            if remaining < estimate:
                status = status or "budget_not_run"
            checkpoint = {"manifest_sha256": manifest["sha256"], "task": task, "status": status, "result": {}}
            if status:
                write_json(path, checkpoint)
                continue
            request = output / "request.json"
            response = output / "response.json"
            if response.exists():
                response.unlink()
            write_json(request, {"task": task, "gates": gates})
            started = time.monotonic()
            state["in_flight"] = {"stage": task["stage"], "started_at": time.time()}
            write_json(state_path, state)
            print(json.dumps({"event": "task_start", "stage": task["stage"], "task": task, "gates": gates}), flush=True)
            try:
                with (output / "worker.log").open("a") as log:
                    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "worker", "--output", str(output)],
                                          stdout=log, stderr=subprocess.STDOUT, timeout=max(1., remaining))
                if proc.returncode == 0 and response.exists():
                    checkpoint.update(json.loads(response.read_text()))
                else:
                    checkpoint.update(status="failed", error=f"worker_exit={proc.returncode}; see worker.log")
            except subprocess.TimeoutExpired:
                checkpoint.update(status="budget_not_run", error="Task exceeded remaining stage budget; worker terminated")
            duration = time.monotonic() - started
            checkpoint["elapsed_seconds"] = duration
            write_json(path, checkpoint)
            state["stage_spent"][task["stage"]] += duration
            state["durations"].setdefault(task["kind"], []).append(duration)
            state.pop("in_flight", None)
            write_json(state_path, state)
            print(json.dumps({"event": "task_end", "id": task["id"], "status": checkpoint["status"], "seconds": duration}), flush=True)
            if task["kind"] in ["integrity", "information"] or task["stage"] == "B":
                render_report(output, manifest)
    finally:
        render_report(output, manifest)
    print("Diagnostic campaign finished; inspect report.md and result.json", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "worker", "report", "preflight"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    if args.command == "prepare":
        manifest = prepare(output)
        print(json.dumps({"manifest": str(output / 'manifest.json'), "sha256": manifest['sha256'], "tasks": len(manifest['tasks'])}))
        return
    if args.command == "preflight":
        prices, membership, pit, market = load_inputs(INPUTS)
        print(json.dumps({"dates": len(prices), "tickers": list(prices), "membership_rows": len(membership),
                          "pit_rows": len(pit), "market_rows": len(market), "sources": source_hashes()}))
        return
    manifest = json.loads((output / "manifest.json").read_text())
    if args.command == "run":
        import fcntl
        import signal
        def interrupt(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupt)
        try:
            with (output / "run.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                run_campaign(output, manifest)
        except KeyboardInterrupt:
            (output / "run.exit").write_text("130\n")
            raise SystemExit(130)
        except Exception:
            (output / "run.exit").write_text("1\n")
            raise
        else:
            (output / "run.exit").write_text("0\n")
    elif args.command == "report":
        render_report(output, manifest)
    else:
        verify_manifest(manifest)
        request = json.loads((output / "request.json").read_text())
        try:
            result = execute_task(request["task"], manifest, request["gates"])
            write_json(output / "response.json", {"status": "ok", "result": result})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            write_json(output / "response.json", {"status": "failed", "error": str(exc), "result": {}})


if __name__ == "__main__":
    main()
