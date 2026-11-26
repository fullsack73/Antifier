#!/usr/bin/env python3
"""Frozen two-year diagnostic: cross-stock MSE+corr Transformer MPT versus GMV."""
import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/backend"))
from tools.backtest_stock_losses import loss_value
from tools.benchmark_stock_attention import build_model, prepare
from tools.compare_improved_forecast_portfolios import net_daily_returns
from portfolio_backtest import (_safe_covariance, _weight_diagnostics,
                                build_rebalance_targets, run_portfolio_model_backtest)
from portfolio_statistics import paired_block_bootstrap
from pypfopt import EfficientFrontier
import numpy as np
import pandas as pd

SETTINGS = dict(train_window=504, rebalance_frequency=63, forecast_horizon=63,
                transaction_cost_bps=10., max_asset_weight=.2, rebalance_band=.02,
                max_turnover=.35, risk_free_rate=.03)
SEEDS = (42, 43, 44)
ORIGINS = tuple(range(503, 945, 63))


def fit_period_forecast(train, seed, horizon=63):
    import tensorflow as tf
    values = np.asarray(train, dtype=float)
    if values.shape != (504, 22):
        raise ValueError("Training requires exactly 504 days and 22 stocks")
    # prepare's future rows are only for scoring; pad them to keep outcomes out of this API.
    if isinstance(horizon, (bool, np.bool_)) or not isinstance(horizon, (int, np.integer)) or horizon <= 0:
        raise ValueError("Require a positive integer forecast horizon")
    padded = np.concatenate([values, np.repeat(values[-1:], horizon, axis=0)])
    x, y, training, validation, latest, scaler, _ = prepare(padded, horizon=horizon)
    model = build_model(22, True, seed)
    model.compile(optimizer=tf.keras.optimizers.Adam(.001),
                  loss=lambda a, p: loss_value(a, p, "mse_corr"))
    try:
        started = time.perf_counter()
        model.fit(x[training], y[training], validation_data=(x[validation], y[validation]),
                  epochs=5, batch_size=8, shuffle=False, verbose=0)
        prediction = model(latest, training=False).numpy().ravel()
        period_log = scaler.inverse_transform(prediction[:, None]).ravel()
        if not np.isfinite(period_log).all():
            raise ValueError("Nonfinite absolute log-return prediction")
        return {"period_log_forecast": period_log.tolist(),
                "fit_seconds": time.perf_counter() - started}
    finally:
        tf.keras.backend.clear_session()


def mpt_weights(period_log, covariance, gmv, solver=EfficientFrontier, horizon=63):
    if isinstance(horizon, (bool, np.bool_)) or not isinstance(horizon, (int, np.integer)) or horizon <= 0:
        raise ValueError("Require a positive integer forecast horizon")
    tickers = list(gmv)
    values = np.asarray(period_log, dtype=float)
    if values.shape != (len(tickers),) or not np.isfinite(values).all():
        raise ValueError("Need one finite forecast per stock")
    with np.errstate(over="ignore"):
        annual = np.expm1(values * 252 / horizon)
    if not np.isfinite(annual).all():
        raise ValueError("Nonfinite annual return conversion")
    mu = pd.Series(annual, index=tickers)
    fallback = None
    try:
        frontier = solver(mu, covariance, weight_bounds=(0., .2))
        frontier.max_sharpe(risk_free_rate=.03)
        weights = {ticker: float(weight) for ticker, weight in
                   zip(tickers, frontier.weights)}
        w = np.array(list(weights.values()))
        if not np.isfinite(w).all() or abs(w.sum() - 1) > 1e-7 or w.min() < -1e-8 or w.max() > .2 + 1e-8:
            raise ValueError("MPT weights violate budget or cap")
    except Exception as exc:
        weights, fallback = dict(gmv), str(exc)
    return weights, {"annual_return_proxy": mu.to_dict(), "mpt_fallback_to_gmv": fallback is not None,
                     "fallback_reason": fallback}


def replay(prices, forecasts, horizon=63):
    targets = build_rebalance_targets(prices, models=["min_variance"], train_window=504,
                                      rebalance_frequency=63, forecast_horizon=63,
                                      max_asset_weight=.2, risk_free_rate=.03, target_turnover_limit=.35)
    if len(targets["records"]) != 8:
        raise ValueError("Require eight common quarterly rebalances")
    covariances = {i: _safe_covariance(prices.iloc[i - 503:i + 1]) for i in ORIGINS}
    runs, daily, fallback_counts = {}, {}, {}
    for name in ("gmv", "mpt_ensemble", *(f"mpt_seed{s}" for s in SEEDS)):
        own = copy.deepcopy(targets)
        fallback_counts[name] = 0
        for i, record in zip(ORIGINS, own["records"]):
            if record["train_end_date"] != str(prices.index[i].date()):
                raise ValueError("Signal and execution calendar mismatch")
            target = record["models"]["min_variance"]
            diagnostics = {"construction": name}
            scores = {}
            if name != "gmv":
                seeds = SEEDS if name == "mpt_ensemble" else (int(name.removeprefix("mpt_seed")),)
                period_log = np.mean([forecasts[(i, s)]["period_log_forecast"] for s in seeds], axis=0)
                weights, diagnostics = mpt_weights(period_log, covariances[i], target["weights"], horizon=horizon)
                diagnostics["model_forecast_horizon"] = horizon
                target["weights"] = weights
                scores = dict(zip(prices.columns, period_log.tolist()))
                fallback_counts[name] += int(diagnostics["mpt_fallback_to_gmv"])
            target["diagnostics"].update(_weight_diagnostics(target["weights"], scores, covariances[i]))
            target["diagnostics"].update(diagnostics, construction=name,
                                         signal_scores=scores, target_weights=target["weights"])
            record["experiment_diagnostics"] = diagnostics
        run = run_portfolio_model_backtest(prices, models=["min_variance"], rebalance_targets=own,
                                           include_daily_returns=True, **SETTINGS)
        returns = net_daily_returns(run)
        daily[name] = returns
        recalculated = float((returns.mean() - (1.03 ** (1 / 252) - 1)) / returns.std(ddof=0) * np.sqrt(252))
        summary = run["summary_by_model"]["min_variance"]
        if not np.isclose(recalculated, summary["sharpe"]):
            raise ValueError("Independent Sharpe calculation mismatch")
        runs[name] = {"summary": summary, "records": run["rebalance_records"],
                      "target_records": own["records"]}
    if any(not series.index.equals(daily["gmv"].index) for series in daily.values()):
        raise ValueError("Return calendars differ")
    bootstrap = {name: paired_block_bootstrap(series, daily["gmv"], risk_free_rate=.03,
                 block_size=63, samples=2000, seed=42,
                 risk_free_daily_returns=pd.Series(1.03 ** (1 / 252) - 1, index=series.index))
                 for name, series in daily.items() if name != "gmv"}
    return {"runs": runs, "daily_returns": {name: {str(d): float(v) for d, v in series.items()}
                                            for name, series in daily.items()},
            "mpt_fallback_counts": fallback_counts, "paired_bootstrap_vs_gmv": bootstrap}


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
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"purpose": "consumed_historical_diagnostic_only", "promotion_eligible": False,
                "settings": SETTINGS, "seeds": list(SEEDS), "epochs": 5, "batch_dates": 8, "learning_rate": .001,
                "architecture": "temporal attention plus cross-stock attention after temporal pooling",
                "target": "absolute 63-day log return, global train-only standardization",
                "loss": "0.5 standardized MSE + 0.5 (1 - date-wise cross-sectional Pearson correlation)",
                "annual_conversion": "expm1(period_log_forecast * 252/63); geometric proxy, not calibrated arithmetic conditional mean",
                "primary": "MPT of equally averaged three-seed log-return predictions vs GMV; individual seeds diagnostic",
                "objective": "max Sharpe; long only, fully invested; exact GMV target on optimization failure, every fallback reported",
                "execution": "preceding close signal, next trading close execution; 63 trading days approximate three months",
                "execution_start": str(prices.index[504].date()), "end": str(prices.index[-1].date()),
                "tickers": list(prices.columns), "origin_dates": [str(prices.index[i].date()) for i in ORIGINS],
                "price_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "bootstrap": {"block_size": 63, "samples": 2000, "seed": 42, "purpose": "descriptive Sharpe difference"},
                "sources": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in
                            ("tools/backtest_attention_mpt.py", "tools/backtest_stock_losses.py",
                             "tools/benchmark_stock_attention.py", "tools/compare_improved_forecast_portfolios.py",
                             "src/backend/direct_horizon_forecast.py",
                             "src/backend/portfolio_backtest.py", "src/backend/portfolio_statistics.py")},
                "packages": {p: importlib.metadata.version(p) for p in
                             ("tensorflow", "numpy", "pandas", "scikit-learn", "PyPortfolioOpt")}}
    path = folder / "manifest.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("Code, data or settings drift; cannot resume")
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    forecasts = {}
    for i in ORIGINS:
        for seed in SEEDS:
            path = folder / f"fit-{i}-{seed}.json"
            if path.exists():
                result = json.loads(path.read_text())
            else:
                result = fit_period_forecast(prices.iloc[i - 503:i + 1], seed)
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(result, allow_nan=False) + "\n")
                temporary.replace(path)
            forecasts[(i, seed)] = result
            print(f"fit {len(forecasts)}/24 {prices.index[i].date()} seed={seed}", flush=True)
    result = {**manifest, **replay(prices, forecasts)}
    (folder / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False, default=str) + "\n")
    print(json.dumps({name: run["summary"]["sharpe"] for name, run in result["runs"].items()}, indent=2), flush=True)
    print("MPT fallback counts: " + json.dumps(result["mpt_fallback_counts"]), flush=True)


if __name__ == "__main__":
    main()
