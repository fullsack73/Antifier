"""Research-only forecast attribution. Never used by production allocation."""

from native_threading import configure_native_threading

configure_native_threading()

import hashlib
import json
import warnings
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from forecast_models import ARIMA, TransformerForecastModel
from direct_horizon_forecast import build_transformer, supervised_returns, purged_split
from portfolio_statistics import holm_bonferroni


TICKERS = "AAPL MSFT AMZN GOOGL META NVDA ADBE AMGN COST INTC CSCO QCOM".split()
CONTROL_TICKERS = "AAPL MSFT AMZN GOOGL NVDA INTC".split()
SEEDS = [42, 43, 44]
PIT_COLUMNS = ["quality", "profitability", "valuation", "liquidity"]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def period_outputs(raw, daily_limited, horizon):
    """Expose both existing output conventions without hiding their mismatch."""
    return {
        "raw": float(raw), "daily_limited": float(daily_limited),
        "original_standalone": float(np.clip(daily_limited, -0.95, 2.0)),
        "original_hybrid_component": float(np.clip(daily_limited * 252 / horizon, -0.69, 0.69) * horizon / 252),
        "canonical": float(raw),
    }


def target_at(prices, cutoff, horizon):
    values = np.asarray(prices, dtype=float)
    window = values[cutoff:cutoff + horizon + 1]
    if len(window) != horizon + 1 or not np.isfinite(window).all() or (window <= 0).any():
        raise ValueError("Target requires consecutive finite positive prices")
    return float(np.log(window[-1] / window[0]))


def transformer_forecast(prices, horizon=63, position=False, direct=False,
                         seed=42, epochs=5, future=None):
    import tensorflow as tf

    returns, x, y, ends = supervised_returns(prices, horizon if direct else 1)
    tr, va = purged_split(ends, horizon if direct else 1)
    # Both target and input scalers see only the purged training partition.
    xs = StandardScaler().fit(x[tr].reshape(-1, 1))
    ys = StandardScaler().fit(y[tr, None])
    scaled_x = xs.transform(x.reshape(-1, 1)).reshape(x.shape).astype("float32")
    scaled_y = ys.transform(y[:, None]).astype("float32")
    model = build_transformer(position, seed)
    try:
        history = model.fit(
            scaled_x[tr], scaled_y[tr], validation_data=(scaled_x[va], scaled_y[va]),
            epochs=epochs, batch_size=32, shuffle=False, verbose=0,
            callbacks=[tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=7 if epochs == 50 else 2, restore_best_weights=True)],
        )
        sequence = returns[-60:].copy()
        raw = limited = teacher = 0.0
        daily_path = []
        steps = 1 if direct else horizon
        teacher_sequence = sequence.copy()
        for day in range(steps):
            tensor = xs.transform(sequence[:, None])[None].astype("float32")
            pred = float(ys.inverse_transform(np.asarray(model(tensor, training=False)).reshape(1, 1))[0, 0])
            raw += pred
            clipped = float(np.clip(pred, -0.2, 0.2)) if not direct else pred
            limited += clipped
            daily_path.append(pred)
            sequence = np.r_[sequence[1:], clipped]
            if future is not None and not direct:
                tensor_tf = xs.transform(teacher_sequence[:, None])[None].astype("float32")
                teacher += float(ys.inverse_transform(np.asarray(model(tensor_tf, training=False)).reshape(1, 1))[0, 0])
                teacher_sequence = np.r_[teacher_sequence[1:], future[day]]
        tensor = xs.transform(returns[-60:, None])[None].astype("float32")
        reversed_tensor = tensor[:, ::-1, :]
        sensitivity = abs(float(np.asarray(model(tensor, training=False))[0, 0]) -
                          float(np.asarray(model(reversed_tensor, training=False))[0, 0]))
        return {
            **period_outputs(raw, limited, horizon), "daily_path": daily_path,
            "teacher_forced_diagnostic": teacher if future is not None and not direct else None,
            "teacher_forced_uses_future": future is not None and not direct,
            "position_sensitivity_scaled": sensitivity,
            "epochs_run": len(history.history["loss"]),
            "train_loss": history.history["loss"], "validation_loss": history.history["val_loss"],
            "train_rows": len(tr), "validation_rows": len(va),
            "last_training_target_end": int(ends[tr[-1]] + (horizon if direct else 1)),
            "validation_origin": int(ends[va[0]]),
        }
    finally:
        tf.keras.backend.clear_session()


def original_transformer(prices, horizon=63, seed=42, trained_model=None):
    model = trained_model or TransformerForecastModel(random_state=seed)
    try:
        if trained_model is None:
            model.train(np.asarray(prices))
        prediction = model.predict(horizon)
        if prediction["expected_return"] is None:
            raise ValueError("Original Transformer returned no view")
        diag = prediction["diagnostics"]
        raw = diag["raw_annual_log_return"] * horizon / 252
        limited = diag["pre_annual_clip_log_return"] * horizon / 252
        return {**period_outputs(raw, limited, horizon), "diagnostics": diag,
                "reported_uncertainty": prediction["uncertainty"]}
    finally:
        if trained_model is None:
            model.cleanup()


def arima_forecast(prices, horizon=63, fixed=False, loader=None):
    """Trace the actual house ARIMA, including its otherwise silent fallbacks."""
    import forecast_models
    from statsmodels.tsa.arima.model import ARIMA as StatsARIMA

    prices = np.asarray(prices, dtype=float)
    info = {"path": "short_input_constant" if len(prices) < 10 else "arima", "warnings": []}
    original_loader = loader or forecast_models._load_auto_arima
    original_linregress = forecast_models.linregress

    def traced_trend(*args, **kwargs):
        try:
            return original_linregress(*args, **kwargs)
        except Exception as exc:
            info.update(path="constant_fallback", trend_error=str(exc))
            raise

    def traced_fit(values, **kwargs):
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                fitted = original_loader()(values, **kwargs)
            residual = np.asarray(fitted.resid(), dtype=float)
            info.update(order=list(fitted.order), with_intercept=bool(fitted.with_intercept),
                        converged=bool(fitted.arima_res_.mle_retvals.get("converged", False)),
                        residual_std=float(np.std(residual)),
                        residual_lag1=float(pd.Series(residual).autocorr()),
                        warnings=[str(w.message) for w in caught])
            path, intervals = fitted.predict(n_periods=horizon, return_conf_int=True)
            info.update(predicted_daily_path=np.asarray(path).tolist(),
                        daily_confidence_intervals=np.asarray(intervals).tolist())
            return fitted
        except Exception as exc:
            info.update(path="trend_fallback", arima_error=str(exc))
            raise

    if fixed:
        r = np.diff(np.log(prices))
        fitted = StatsARIMA(r, order=(1, 0, 0), trend="c").fit()
        path = np.asarray(fitted.forecast(horizon))
        return {"raw": float(path.sum()), "path": "fixed_ar1", "daily_path": path.tolist()}
    with patch.object(forecast_models, "_load_auto_arima", lambda: traced_fit), \
            patch.object(forecast_models, "linregress", traced_trend):
        value, uncertainty = ARIMA().forecast(prices, horizon)
    return {"raw": float(value), "reported_uncertainty": float(uncertainty), **info}


def ridge_predict(train_x, train_y, test_x):
    """Train-only median imputation with explicit missing flags; fixed penalty."""
    train_x = np.asarray(train_x, dtype=float)
    test_x = np.asarray(test_x, dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        medians = np.nanmedian(np.where(np.isfinite(train_x), train_x, np.nan), axis=0)
    medians = np.nan_to_num(medians)

    def impute(x):
        missing = ~np.isfinite(x)
        return np.c_[np.where(missing, medians, x), missing.astype(float)]

    scaler = StandardScaler().fit(impute(train_x))
    model = Ridge(alpha=5).fit(scaler.transform(impute(train_x)), train_y)
    return model.predict(scaler.transform(impute(test_x)))


def mixture_decomposition(actual, arima, transformer):
    ea = np.asarray(arima) - actual
    et = np.asarray(transformer) - actual
    ba, bt = float(ea.mean()), float(et.mean())
    covariance = float(np.mean((ea - ba) * (et - bt)))
    reconstructed = ((ba + bt) / 2) ** 2 + (np.var(ea) + np.var(et) + 2 * covariance) / 4
    return {"arima_bias": ba, "transformer_bias": bt,
            "arima_error_variance": float(np.var(ea)), "transformer_error_variance": float(np.var(et)),
            "error_covariance": covariance, "reconstructed_mse": float(reconstructed),
            "observed_mse": float(np.mean(((ea + et) / 2) ** 2)),
            "arima_mse": float(np.mean(ea ** 2)), "transformer_mse": float(np.mean(et ** 2))}


def paired_mse_bootstrap(frame, candidate, baseline, samples=2000):
    """Cluster every ticker/seed by origin, then resample date blocks together."""
    pair = frame.pivot_table(index=["origin", "ticker", "seed"], columns="model", values="error_squared")
    if candidate not in pair or baseline not in pair:
        return {"status": "insufficient_data"}
    pair = pair[[candidate, baseline]].dropna()
    delta = (pair[candidate] - pair[baseline]).groupby(level="origin").mean().sort_index()
    if len(delta) < 8:
        return {"status": "insufficient_data", "origins": len(delta)}
    values = delta.to_numpy()
    rng = np.random.default_rng(42)
    starts = rng.integers(len(values), size=(samples, (len(values) + 1) // 2))
    indices = ((starts[..., None] + np.arange(2)) % len(values)).reshape(samples, -1)[:, :len(values)]
    means = values[indices].mean(axis=1)
    # Centered bootstrap approximates the one-sided null of no MSE reduction.
    p = float((1 + np.sum(means - values.mean() <= values.mean())) / (samples + 1))
    return {"status": "ok", "origins": len(values), "paired_rows": len(pair),
            "mse_difference": float(values.mean()), "lower_95": float(np.quantile(means, .025)),
            "upper_95": float(np.quantile(means, .975)), "p_value": p}


def summarize(records, comparisons):
    valid = [r for r in records if r.get("status") == "ok" and r.get("actual") is not None]
    if not valid:
        return {"metrics": {}, "comparisons": {}, "mixtures": {}}
    frame = pd.DataFrame(valid)
    frame["error"] = frame.prediction - frame.actual
    frame["error_squared"] = frame.error ** 2
    metrics = {}
    for model, group in frame.groupby("model"):
        by_date = group.groupby("origin").error_squared.mean()
        ic, spread = [], []
        for _, date_rows in group.groupby(["origin", "seed"]):
            if len(date_rows) >= 5 and date_rows.prediction.nunique() > 1:
                ic.append(float(spearmanr(date_rows.prediction, date_rows.actual).statistic))
                ranked = date_rows.sort_values("prediction")
                n = max(1, len(ranked) // 5)
                spread.append(float(ranked.tail(n).actual.mean() - ranked.head(n).actual.mean()))
        metrics[model] = {"rows": len(group), "origins": len(by_date), "date_equal_mse": float(by_date.mean()),
                          "mae": float(group.groupby("origin").error.apply(lambda x: x.abs().mean()).mean()),
                          "bias": float(group.groupby("origin").error.mean().mean()),
                          "direction_accuracy": float((np.sign(group.prediction) == np.sign(group.actual)).mean()),
                          "mean_rank_ic": float(np.mean(ic)) if ic else None,
                          "top_bottom": float(np.mean(spread)) if spread else None}
        # R² denominators use exactly the same rows, never a different coverage set.
        for base in ["zero", "historical_mean", "ridge_price_504"]:
            piv = group[["origin", "ticker", "seed", "error_squared"]].merge(
                frame[frame.model == base][["origin", "ticker", "seed", "error_squared"]],
                on=["origin", "ticker", "seed"], suffixes=("_candidate", "_baseline"))
            if not piv.empty:
                means = piv.groupby("origin")[["error_squared_candidate", "error_squared_baseline"]].mean().mean()
                den = means.error_squared_baseline
                metrics[model]["oos_r2_vs_" + base] = float(1 - means.error_squared_candidate / den) if den > 0 else None
    tests = {f"{c}_vs_{b}": paired_mse_bootstrap(frame, c, b) for c, b in comparisons}
    # Count even unavailable preregistered hypotheses in the correction family.
    corrected = holm_bonferroni({k: v.get("p_value", 1.0) for k, v in tests.items()})
    for name, value in tests.items():
        value["holm"] = corrected[name]
    mixtures = {}
    for prefix in ["original", "canonical"]:
        # Original hybrid uses the annual-clipped component, not standalone output.
        names = [prefix + "_arima", prefix + ("_transformer_component" if prefix == "original" else "_transformer")]
        piv = frame.pivot_table(index=["origin", "ticker", "seed", "actual"], columns="model", values="prediction")
        if all(n in piv for n in names):
            pair = piv[names].dropna()
            if len(pair):
                mixtures[prefix] = mixture_decomposition(pair.index.get_level_values("actual").to_numpy(),
                                                        pair[names[0]].to_numpy(), pair[names[1]].to_numpy())
    return {"metrics": metrics, "comparisons": tests, "mixtures": mixtures}
