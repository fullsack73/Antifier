#!/usr/bin/env python3
"""Compare three cross-sectional losses by net portfolio Sharpe on frozen data."""
import argparse
import copy
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src/backend"))
from tools.benchmark_stock_attention import build_model, prepare
from tools.compare_improved_forecast_portfolios import net_daily_returns
from portfolio_backtest import (_safe_covariance, _weight_diagnostics,
                                build_rebalance_targets, run_portfolio_model_backtest)
from portfolio_statistics import paired_block_bootstrap
import numpy as np
import pandas as pd

KINDS = ("mse", "mse_corr", "mse_rank")
SETTINGS = dict(train_window=504, rebalance_frequency=63, forecast_horizon=63,
                transaction_cost_bps=10., max_asset_weight=.2, rebalance_band=.02,
                max_turnover=.35, risk_free_rate=.02)


def loss_value(actual, predicted, kind):
    import tensorflow as tf
    mse = tf.reduce_mean(tf.square(predicted - actual))
    if kind == "mse":
        return mse
    if kind == "mse_corr":
        a = actual - tf.reduce_mean(actual, axis=-1, keepdims=True)
        p = predicted - tf.reduce_mean(predicted, axis=-1, keepdims=True)
        variance_a = tf.reduce_mean(a * a, axis=-1)
        correlation = tf.reduce_mean(a * p, axis=-1) / tf.sqrt(variance_a * tf.reduce_mean(p * p, axis=-1) + 1e-6)
        extra = tf.reduce_mean(tf.where(variance_a > 1e-8, 1 - correlation, tf.zeros_like(correlation)))
    elif kind == "mse_rank":
        differences = actual[:, :, None] - actual[:, None, :]
        predicted_differences = predicted[:, :, None] - predicted[:, None, :]
        upper = tf.linalg.band_part(tf.ones_like(differences), 0, -1)
        mask = upper * tf.cast(tf.not_equal(differences, 0), actual.dtype)
        penalties = tf.nn.softplus(-tf.sign(differences) * predicted_differences)
        extra = tf.reduce_mean(tf.reduce_sum(penalties * mask, axis=(1, 2)) /
                               tf.maximum(tf.reduce_sum(mask, axis=(1, 2)), 1.))
    else:
        raise ValueError("Unknown loss")
    return .5 * mse + .5 * extra


def fit_scores(window, kind, seed):
    import tensorflow as tf
    x, y, train, validation, latest, _, _ = prepare(window)
    y = ((y - y.mean(axis=1, keepdims=True)) / np.maximum(y.std(axis=1, keepdims=True), 1e-6)).astype("float32")
    model = build_model(x.shape[1], False, seed)
    model.compile(optimizer=tf.keras.optimizers.Adam(.001), loss=lambda a, p: loss_value(a, p, kind))
    try:
        started = time.perf_counter()
        model.fit(x[train], y[train], validation_data=(x[validation], y[validation]),
                  epochs=5, batch_size=8, shuffle=False, verbose=0)
        scores = model(latest, training=False).numpy().ravel()
        if not np.isfinite(scores).all():
            raise ValueError("Nonfinite scores")
        return {"scores": scores.tolist(), "fit_seconds": time.perf_counter() - started}
    finally:
        tf.keras.backend.clear_session()


def selection_weights(scores, tickers):
    values = pd.Series(scores, index=tickers, dtype=float)
    if len(values) < 5 or not np.isfinite(values).all():
        raise ValueError("Need at least five finite stock scores")
    # Stable ticker order resolves tied predictions without using future outcomes.
    selected = values.sort_index().sort_values(ascending=False, kind="stable").head(5).index
    return {ticker: .2 if ticker in selected else 0. for ticker in tickers}


def replay(prices, forecasts):
    targets = build_rebalance_targets(prices, models=["min_variance"], train_window=504,
                                      rebalance_frequency=63, forecast_horizon=63,
                                      max_asset_weight=.2, risk_free_rate=.02, target_turnover_limit=.35)
    assert len(targets["records"]) == 8
    for i, record in zip(range(503, len(prices) - 63, 63), targets["records"]):
        if record["train_end_date"] != str(prices.index[i].date()):
            raise ValueError("Training and execution calendar mismatch")
    runs, daily = {}, {}
    covariances = {origin: _safe_covariance(prices.iloc[origin - 503:origin + 1])
                   for origin in range(503, len(prices) - 63, 63)}
    names = [("gmv", None, None), ("equal_weight", None, None)]
    names += [(f"{kind}_seed{seed}", kind, seed) for seed in (42, 43, 44) for kind in KINDS]
    for name, kind, seed in names:
        own = copy.deepcopy(targets)
        for origin, record in zip(range(503, len(prices) - 63, 63), own["records"]):
            target = record["models"]["min_variance"]
            if kind is not None:
                target["weights"] = selection_weights(forecasts[(origin, seed, kind)]["scores"], prices.columns)
            elif name == "equal_weight":
                target["weights"] = {ticker: 1 / len(prices.columns) for ticker in prices.columns}
            scores = (dict(zip(prices.columns, forecasts[(origin, seed, kind)]["scores"]))
                      if kind is not None else {})
            target["diagnostics"].update(_weight_diagnostics(target["weights"], scores, covariances[origin]))
            target["diagnostics"].update(construction=name, target_weights=target["weights"], signal_scores=scores)
        run = run_portfolio_model_backtest(prices, models=["min_variance"], rebalance_targets=own,
                                           include_daily_returns=True, **SETTINGS)
        returns = net_daily_returns(run)
        daily[name] = {str(date): float(value) for date, value in returns.items()}
        runs[name] = {"summary": run["summary_by_model"]["min_variance"], "records": run["rebalance_records"]}
    comparisons = {f"{kind}_seed{seed}": paired_block_bootstrap(
        pd.Series(daily[f"{kind}_seed{seed}"]), pd.Series(daily[f"mse_seed{seed}"]),
        risk_free_rate=.02, block_size=63, samples=2000, seed=42,
        risk_free_daily_returns=pd.Series((1.02 ** (1 / 252) - 1), index=list(daily[f"mse_seed{seed}"])))
        for seed in (42, 43, 44) for kind in ("mse_corr", "mse_rank")}
    mean_sharpe = {kind: float(np.mean([runs[f"{kind}_seed{s}"]["summary"]["sharpe"] for s in (42, 43, 44)])) for kind in KINDS}
    return {"runs": runs, "daily_returns": daily, "paired_bootstrap_vs_mse": comparisons,
            "mean_sharpe_by_loss": mean_sharpe, "descriptive_best_loss": max(mean_sharpe, key=mean_sharpe.get)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    source = Path(args.csv)
    raw = source.read_bytes()
    import io
    prices = pd.read_csv(io.BytesIO(raw), index_col=0, parse_dates=True).astype(float)
    if (prices.shape != (1008, 22) or not isinstance(prices.index, pd.DatetimeIndex)
            or prices.index.hasnans or not prices.index.is_unique or not prices.index.is_monotonic_increasing
            or not prices.columns.is_unique or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()):
        raise ValueError("Need ordered 1008-day, 22-stock finite positive prices")
    folder = Path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"purpose": "consumed_historical_diagnostic_only", "promotion_eligible": False,
                "price_sha256": hashlib.sha256(raw).hexdigest(), "settings": SETTINGS,
                "losses": list(KINDS), "loss_mix": [.5, .5], "seeds": [42, 43, 44], "epochs": 5,
                "target": "date-wise cross-sectional standardized 63-day log return",
                "construction": "top 5 equal weight, long only, same controls for all losses",
                "execution": "signal uses preceding close, execute at next trading close; final holding interval may be shorter",
                "primary_endpoint": "mean seed-specific net daily excess-return Sharpe, risk free annual 2%",
                "bootstrap": {"block_size": 63, "samples": 2000, "purpose": "descriptive paired Sharpe difference interval"},
                "sources": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in
                            ("tools/backtest_stock_losses.py", "tools/benchmark_stock_attention.py",
                             "src/backend/direct_horizon_forecast.py", "src/backend/portfolio_backtest.py",
                             "src/backend/portfolio_statistics.py", "tools/compare_improved_forecast_portfolios.py")},
                "packages": {p: importlib.metadata.version(p) for p in ("tensorflow", "numpy", "pandas", "scikit-learn", "PyPortfolioOpt")}}
    path = folder / "manifest.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("Code, data or settings changed; cannot resume")
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    forecasts = {}
    for origin in range(503, len(prices) - 63, 63):
        window = prices.iloc[origin - 503:origin + 64]
        for seed in (42, 43, 44):
            for kind in KINDS:
                checkpoint = folder / f"fit-{origin}-{seed}-{kind}.json"
                if checkpoint.exists():
                    result = json.loads(checkpoint.read_text())
                else:
                    result = fit_scores(window, kind, seed)
                    temporary = checkpoint.with_suffix(".tmp")
                    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
                    temporary.replace(checkpoint)
                forecasts[(origin, seed, kind)] = result
                print(f"fit {len(forecasts)}/72 {prices.index[origin].date()} seed={seed} {kind}", flush=True)
    result = {**manifest, **replay(prices, forecasts)}
    (folder / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False, default=str) + "\n")
    print(json.dumps(result["mean_sharpe_by_loss"], indent=2), flush=True)


if __name__ == "__main__":
    main()
