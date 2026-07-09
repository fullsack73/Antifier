import sys
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from forecast_models import ARIMATransformerPredictor, TransformerForecastModel  # noqa: E402


DEFAULT_FORECAST_HORIZONS = {
    "short": 21,
    "medium": 63,
    "long": 252,
}

DEFAULT_SINGLE_TICKER_MODELS = ("transformer", "arima_transformer")


def _forecast_ensemble_period_log_return(prices, horizon):
    return _forecast_arima_transformer_period_log_return(prices, horizon)


def _forecast_transformer_period_log_return(prices, horizon, transformer_kwargs=None):
    model = TransformerForecastModel(**(transformer_kwargs or {}))
    try:
        model.train(prices)
        return model.forecast(horizon=horizon, annualize=False)
    finally:
        model.cleanup()


def _forecast_arima_transformer_period_log_return(prices, horizon, transformer_kwargs=None):
    predictor = ARIMATransformerPredictor(transformer_kwargs=transformer_kwargs)
    try:
        predictor.train_all(prices)
        prediction = predictor.predict(horizon=horizon)
        annual_log_return = prediction.get("expected_return")
        if annual_log_return is None:
            return None
        annual_log_return = float(annual_log_return)
        return annual_log_return * (horizon / 252)
    finally:
        predictor.cleanup()


def _summarize_forecast_records(records):
    valid_records = [
        record for record in records
        if record.get("predicted_log_return") is not None
        and np.isfinite(record.get("predicted_log_return"))
        and np.isfinite(record.get("actual_log_return"))
    ]
    failures = len(records) - len(valid_records)
    if not valid_records:
        return {
            "n": 0,
            "failures": failures,
            "mae": None,
            "rmse": None,
            "bias": None,
            "directional_accuracy": None,
            "correlation": None,
            "avg_seconds": None,
        }

    predicted = np.array([record["predicted_log_return"] for record in valid_records], dtype=float)
    actual = np.array([record["actual_log_return"] for record in valid_records], dtype=float)
    errors = predicted - actual
    actual_sign = np.sign(actual)
    predicted_sign = np.sign(predicted)
    if len(valid_records) > 1 and np.std(predicted) > 0 and np.std(actual) > 0:
        correlation = float(np.corrcoef(predicted, actual)[0, 1])
    else:
        correlation = None

    return {
        "n": len(valid_records),
        "failures": failures,
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "bias": float(np.mean(errors)),
        "directional_accuracy": float(np.mean(predicted_sign == actual_sign)),
        "correlation": correlation,
        "avg_seconds": float(np.mean([record.get("elapsed_seconds", 0.0) for record in valid_records])),
    }


def _normalize_forecast_horizons(horizons=None):
    if horizons is None:
        return dict(DEFAULT_FORECAST_HORIZONS)

    if isinstance(horizons, dict):
        items = horizons.items()
    else:
        items = []
        for value in horizons:
            if isinstance(value, (list, tuple)) and len(value) == 2:
                items.append((value[0], value[1]))
            else:
                horizon = int(value)
                items.append((f"{horizon}d", horizon))

    normalized = {}
    for label, horizon in items:
        label = str(label)
        horizon = int(horizon)
        if not label:
            raise ValueError("Horizon label must not be empty")
        if horizon < 1:
            raise ValueError(f"Horizon must be at least 1 trading day: {label}={horizon}")
        if label in normalized:
            raise ValueError(f"Duplicate horizon label: {label}")
        normalized[label] = horizon

    if not normalized:
        raise ValueError("At least one forecast horizon is required")
    return normalized


def _score_forecaster_metrics(metrics, primary_metric="rmse", secondary_metric="mae"):
    lower_is_better = {"mae", "rmse", "bias", "abs_bias", "failures", "avg_seconds"}
    higher_is_better = {"directional_accuracy", "correlation", "n"}

    def metric_value(metric_name):
        normalized_name = str(metric_name).lower()
        if normalized_name in {"bias", "abs_bias"}:
            value = metrics.get("bias")
            value = None if value is None else abs(value)
        else:
            value = metrics.get(normalized_name)

        if value is None or not np.isfinite(value):
            return float("inf")
        if normalized_name in higher_is_better:
            return -float(value)
        if normalized_name in lower_is_better:
            return float(value)
        raise ValueError(f"Unsupported model selection metric: {metric_name}")

    if not metrics or metrics.get("n", 0) <= 0:
        return (1, float("inf"), float("inf"), float("inf"), float("inf"))

    directional_accuracy = metrics.get("directional_accuracy")
    directional_tie_breaker = (
        -float(directional_accuracy)
        if directional_accuracy is not None and np.isfinite(directional_accuracy)
        else float("inf")
    )

    failures = metrics.get("failures", 0)
    failures = float(failures) if np.isfinite(failures) else float("inf")

    return (
        0,
        metric_value(primary_metric),
        metric_value(secondary_metric),
        directional_tie_breaker,
        failures,
    )


def _rank_forecasters(comparison, primary_metric="rmse", secondary_metric="mae"):
    ranking = []
    for model_name, payload in comparison.items():
        metrics = payload.get("metrics", {})
        score = _score_forecaster_metrics(
            metrics,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
        )
        ranking.append({
            "model": model_name,
            "metrics": metrics,
            "score": score,
        })

    ranking.sort(key=lambda item: (item["score"], item["model"]))
    for rank, item in enumerate(ranking, start=1):
        item["rank"] = rank
    return ranking


def _best_forecaster(comparison, primary_metric="rmse", secondary_metric="mae"):
    ranking = _rank_forecasters(
        comparison,
        primary_metric=primary_metric,
        secondary_metric=secondary_metric,
    )
    if not ranking or ranking[0]["score"][0] != 0:
        return None
    return {
        "model": ranking[0]["model"],
        "metrics": ranking[0]["metrics"],
        "rank": ranking[0]["rank"],
    }


def compare_forecasters_on_series(
    prices,
    horizon=21,
    min_train_size=252,
    step=None,
    max_windows=5,
    models=("ensemble", "transformer", "arima_transformer"),
    transformer_kwargs=None,
):
    prices = np.asarray(prices, dtype=float)
    prices = prices[np.isfinite(prices) & (prices > 0)]
    step = step or horizon
    min_train_size = max(100, int(min_train_size))
    horizon = max(1, int(horizon))

    if len(prices) < min_train_size + horizon + 1:
        raise ValueError(
            f"Need at least {min_train_size + horizon + 1} valid prices for comparison; got {len(prices)}"
        )

    last_cutoff = len(prices) - horizon - 1
    cutoffs = list(range(min_train_size - 1, last_cutoff + 1, max(1, int(step))))
    if max_windows:
        cutoffs = cutoffs[-int(max_windows):]

    results = {model_name: {"records": []} for model_name in models}

    for cutoff in cutoffs:
        train_prices = prices[:cutoff + 1]
        actual_log_return = float(np.log(prices[cutoff + horizon] / prices[cutoff]))

        for model_name in models:
            started_at = time.perf_counter()
            predicted = None
            error = None
            try:
                normalized_name = model_name.lower()
                if normalized_name in {"ensemble", "deep_learning", "deep-learning"}:
                    predicted = _forecast_ensemble_period_log_return(train_prices, horizon)
                elif normalized_name == "transformer":
                    predicted = _forecast_transformer_period_log_return(
                        train_prices,
                        horizon,
                        transformer_kwargs=transformer_kwargs,
                    )
                elif normalized_name in {"arima_transformer", "arima+transformer", "arima-transformer"}:
                    predicted = _forecast_arima_transformer_period_log_return(
                        train_prices,
                        horizon,
                        transformer_kwargs=transformer_kwargs,
                    )
                else:
                    raise ValueError(f"Unsupported model for comparison: {model_name}")
            except Exception as exc:
                error = str(exc)

            results[model_name]["records"].append({
                "cutoff_index": int(cutoff),
                "horizon": int(horizon),
                "actual_log_return": actual_log_return,
                "predicted_log_return": None if predicted is None else float(predicted),
                "elapsed_seconds": float(time.perf_counter() - started_at),
                "error": error,
            })

    for model_name, payload in results.items():
        payload["metrics"] = _summarize_forecast_records(payload["records"])

    return results


def compare_forecasters_by_horizon(
    prices,
    horizons=None,
    min_train_size=252,
    step=None,
    max_windows=5,
    models=DEFAULT_SINGLE_TICKER_MODELS,
    transformer_kwargs=None,
    primary_metric="rmse",
    secondary_metric="mae",
):
    horizon_map = _normalize_forecast_horizons(horizons)
    horizon_results = {}
    best_by_horizon = {}

    for label, horizon in horizon_map.items():
        try:
            comparison = compare_forecasters_on_series(
                prices,
                horizon=horizon,
                min_train_size=min_train_size,
                step=step or horizon,
                max_windows=max_windows,
                models=models,
                transformer_kwargs=transformer_kwargs,
            )
        except ValueError as exc:
            horizon_results[label] = {
                "horizon": int(horizon),
                "comparison": {},
                "ranking": [],
                "best_model": None,
                "best_metrics": None,
                "error": str(exc),
            }
            best_by_horizon[label] = None
            continue

        ranking = _rank_forecasters(
            comparison,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
        )
        best = _best_forecaster(
            comparison,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
        )

        horizon_results[label] = {
            "horizon": int(horizon),
            "comparison": comparison,
            "ranking": ranking,
            "best_model": None if best is None else best["model"],
            "best_metrics": None if best is None else best["metrics"],
        }
        best_by_horizon[label] = None if best is None else {
            "model": best["model"],
            "horizon": int(horizon),
            "metrics": best["metrics"],
        }

    return {
        "horizons": horizon_results,
        "best_by_horizon": best_by_horizon,
        "selection_metric": {
            "primary": primary_metric,
            "secondary": secondary_metric,
            "tie_breaker": "directional_accuracy",
        },
        "models": list(models),
    }


def compare_single_ticker_forecasters(
    ticker,
    prices,
    horizons=None,
    min_train_size=252,
    step=None,
    max_windows=5,
    models=DEFAULT_SINGLE_TICKER_MODELS,
    transformer_kwargs=None,
    primary_metric="rmse",
    secondary_metric="mae",
):
    result = compare_forecasters_by_horizon(
        prices,
        horizons=horizons,
        min_train_size=min_train_size,
        step=step,
        max_windows=max_windows,
        models=models,
        transformer_kwargs=transformer_kwargs,
        primary_metric=primary_metric,
        secondary_metric=secondary_metric,
    )
    result["ticker"] = ticker
    return result


def compare_forecasters_on_frame(
    price_frame,
    horizon=21,
    min_train_size=252,
    step=None,
    max_windows=5,
    models=("ensemble", "transformer", "arima_transformer"),
    transformer_kwargs=None,
):
    import pandas as pd

    if not isinstance(price_frame, pd.DataFrame):
        raise TypeError("price_frame must be a pandas DataFrame")

    per_ticker = {}
    all_records = {model_name: [] for model_name in models}

    for ticker in price_frame.columns:
        series = price_frame[ticker].dropna().values
        try:
            ticker_result = compare_forecasters_on_series(
                series,
                horizon=horizon,
                min_train_size=min_train_size,
                step=step,
                max_windows=max_windows,
                models=models,
                transformer_kwargs=transformer_kwargs,
            )
        except ValueError as exc:
            per_ticker[ticker] = {"error": str(exc)}
            continue

        per_ticker[ticker] = ticker_result
        for model_name in models:
            for record in ticker_result[model_name]["records"]:
                merged_record = dict(record)
                merged_record["ticker"] = ticker
                all_records[model_name].append(merged_record)

    summary = {
        model_name: _summarize_forecast_records(records)
        for model_name, records in all_records.items()
    }

    return {
        "summary": summary,
        "per_ticker": per_ticker,
    }
