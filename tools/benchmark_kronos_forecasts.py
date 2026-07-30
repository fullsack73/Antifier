#!/usr/bin/env python3
"""Compare pinned Kronos-small with ARIMA/Transformer on identical OHLC."""

import argparse
import hashlib
import json
import resource
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from forecast_signal_research import (  # noqa: E402
    cross_sectional_rank_diagnostics,
    paired_rank_signal_block_bootstrap,
    prediction_distribution_diagnostics,
    rank_signal_block_bootstrap,
    signal_only_gate,
)


KRONOS_REPOSITORY = "https://github.com/shiyu-coder/Kronos"
KRONOS_REPOSITORY_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
KRONOS_MODEL_ID = "NeoQuasar/Kronos-small"
KRONOS_MODEL_REVISION = "901c26c1332695a2a8f243eb2f37243a37bea320"
KRONOS_TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
KRONOS_TOKENIZER_REVISION = "0e0117387f39004a9016484a186a908917e22426"
DEFAULT_NAMESPACES = {
    "arima_transformer_rank": "arima-transformer-rank-v1",
    "transformer_rank": "transformer-rank-v1",
}
REQUIRED_OHLC_COLUMNS = ("timestamp", "ticker", "open", "high", "low", "close")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _series_digest(series):
    series = pd.Series(series, dtype=float).dropna()
    hashed = pd.util.hash_pandas_object(series, index=True).values
    return hashlib.blake2b(hashed.tobytes(), digest_size=16).hexdigest()


def load_cached_forecasts(cache_path, namespaces=None):
    namespaces = namespaces or DEFAULT_NAMESPACES
    connection = sqlite3.connect(str(Path(cache_path).expanduser()))
    try:
        rows = connection.execute(
            "SELECT key_payload, prediction_payload FROM forecast_predictions"
        ).fetchall()
    finally:
        connection.close()

    forecasts = defaultdict(list)
    for key_payload, prediction_payload in rows:
        key = json.loads(key_payload)
        method = key[2]
        if namespaces.get(method) != key[1]:
            continue
        forecasts[method].append({
            "ticker": key[3],
            "horizon": int(key[4]),
            "train_rows": int(key[5]),
            "train_start": pd.Timestamp(key[6]),
            "train_end": pd.Timestamp(key[7]),
            "close_digest": key[8],
            "prediction": json.loads(prediction_payload),
        })

    missing = sorted(set(namespaces) - set(forecasts))
    if missing:
        raise ValueError("Forecast cache missing methods: " + ", ".join(missing))
    return dict(forecasts)


def read_ohlc_csv(path):
    frame = pd.read_csv(path)
    missing = [column for column in REQUIRED_OHLC_COLUMNS if column not in frame]
    if missing:
        raise ValueError("OHLC CSV missing columns: " + ", ".join(missing))
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"]).dt.tz_localize(None)
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    value_columns = ["open", "high", "low", "close"]
    if "volume" in frame:
        value_columns.append("volume")
    frame[value_columns] = frame[value_columns].apply(
        pd.to_numeric, errors="coerce"
    )
    if frame[list(REQUIRED_OHLC_COLUMNS[2:])].isna().any().any():
        raise ValueError("OHLC CSV contains missing required price values")
    return frame.sort_values(["ticker", "timestamp"]).reset_index(drop=True)


def download_ohlc(cached_forecasts, output_path):
    import yfinance as yf
    from portfolio_optimization import _managed_yfinance_session

    rows = next(iter(cached_forecasts.values()))
    tickers = sorted({row["ticker"] for row in rows})
    start = min(row["train_start"] for row in rows).date().isoformat()
    latest_end = max(row["train_end"] for row in rows)
    end = (latest_end + timedelta(days=180)).date().isoformat()

    with _managed_yfinance_session() as session:
        raw = yf.download(
            tickers,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
            threads=False,
            group_by="ticker",
            session=session,
        )

    parts = []
    for ticker in tickers:
        if not isinstance(raw.columns, pd.MultiIndex) or ticker not in raw:
            continue
        ticker_frame = raw[ticker].rename(columns=str.lower)
        required = ["open", "high", "low", "close"]
        if any(column not in ticker_frame for column in required):
            continue
        columns = required + (["volume"] if "volume" in ticker_frame else [])
        ticker_frame = ticker_frame[columns].dropna(subset=required).reset_index()
        ticker_frame = ticker_frame.rename(columns={ticker_frame.columns[0]: "timestamp"})
        ticker_frame["ticker"] = ticker
        parts.append(ticker_frame)
    if not parts:
        raise ValueError("yfinance returned no usable OHLC rows")

    frame = pd.concat(parts, ignore_index=True)
    missing = sorted(set(tickers) - set(frame["ticker"]))
    if missing:
        raise ValueError("yfinance OHLC missing tickers: " + ", ".join(missing))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return read_ohlc_csv(output_path)


def build_aligned_origins(cached_forecasts, ohlc, strict_digest=True):
    by_ticker = {
        ticker: group.set_index("timestamp").sort_index()
        for ticker, group in ohlc.groupby("ticker")
    }
    origins = defaultdict(list)
    mismatches = []

    for row in cached_forecasts["arima_transformer_rank"]:
        ticker = row["ticker"]
        frame = by_ticker.get(ticker)
        if frame is None:
            mismatches.append(f"{ticker}: missing OHLC")
            continue
        train = frame.loc[row["train_start"]:row["train_end"]]
        train = train.tail(row["train_rows"])
        if len(train) != row["train_rows"]:
            mismatches.append(
                f"{ticker}@{row['train_end'].date()}: incomplete training window"
            )
            continue
        if _series_digest(train["close"]) != row["close_digest"]:
            mismatches.append(
                f"{ticker}@{row['train_end'].date()}: close digest mismatch"
            )
            if strict_digest:
                continue
        future = frame.loc[frame.index > row["train_end"]].head(row["horizon"])
        if len(future) != row["horizon"]:
            mismatches.append(
                f"{ticker}@{row['train_end'].date()}: incomplete horizon"
            )
            continue
        required = ["open", "high", "low", "close"]
        if train[required].isna().any().any():
            mismatches.append(
                f"{ticker}@{row['train_end'].date()}: incomplete OHLC"
            )
            continue
        columns = required + (["volume"] if "volume" in train else [])
        origins[(row["train_start"], row["train_end"], row["horizon"])].append({
            "ticker": ticker,
            "train": train[columns].copy(),
            "future_timestamps": pd.Series(future.index),
            "realized_return": float(
                future["close"].iloc[-1] / train["close"].iloc[-1] - 1.0
            ),
            "arima_transformer_rank": None,
            "transformer_rank": None,
        })

    result = []
    for (start, end, horizon), rows in sorted(origins.items()):
        if len(rows) < 2:
            continue
        tickers = sorted(row["ticker"] for row in rows)
        universe = hashlib.sha256(",".join(tickers).encode()).hexdigest()[:12]
        result.append({
            "period_id": f"{end.date()}-{universe}",
            "case_id": universe,
            "train_start": start,
            "train_end": end,
            "horizon": horizon,
            "rows": sorted(rows, key=lambda row: row["ticker"]),
        })
    return result, mismatches


def run_baseline_origins(origins, cache_path):
    from portfolio_backtest import (
        _forecast_rank_executor,
        _forecast_rank_views,
        configure_forecast_rank_cache,
        forecast_rank_cache_stats,
    )

    configure_forecast_rank_cache(
        cache_path,
        namespace="kronos-small-zero-shot-candidate-4case-baselines-v1",
    )
    try:
        with _forecast_rank_executor(
            ("arima_transformer_rank_bl", "transformer_rank_bl"),
            max(len(origin["rows"]) for origin in origins),
        ) as executor:
            for index, origin in enumerate(origins, start=1):
                prices = pd.concat(
                    {
                        row["ticker"]: row["train"]["close"]
                        for row in origin["rows"]
                    },
                    axis=1,
                )
                for method in ("arima_transformer_rank", "transformer_rank"):
                    scores, _, _, _ = _forecast_rank_views(
                        prices,
                        method,
                        origin["horizon"],
                        forecast_executor=executor,
                    )
                    for row in origin["rows"]:
                        row[method] = scores.get(row["ticker"])
                print(
                    f"[baseline {index}/{len(origins)}] {origin['period_id']}",
                    flush=True,
                )
        stats = forecast_rank_cache_stats()
        connection = sqlite3.connect(str(cache_path))
        try:
            created_start, created_end = connection.execute(
                "SELECT MIN(created_at), MAX(created_at) FROM forecast_predictions"
            ).fetchone()
        finally:
            connection.close()
        stats["cold_fill_span_seconds"] = (
            pd.Timestamp(created_end) - pd.Timestamp(created_start)
        ).total_seconds()
        return stats
    finally:
        configure_forecast_rank_cache(None)


def _git_head(repo_path):
    return subprocess.check_output(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def load_kronos_predictor(repo_path, device):
    repo_path = Path(repo_path).expanduser().resolve()
    commit = _git_head(repo_path)
    if commit != KRONOS_REPOSITORY_COMMIT:
        raise ValueError(
            f"Kronos repo must be pinned at {KRONOS_REPOSITORY_COMMIT}; got {commit}"
        )
    sys.path.insert(0, str(repo_path))
    try:
        import torch
        from huggingface_hub import snapshot_download
        from model import Kronos, KronosPredictor, KronosTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Install requirements-kronos-research.txt in a research environment"
        ) from exc

    model_path = snapshot_download(
        KRONOS_MODEL_ID,
        revision=KRONOS_MODEL_REVISION,
    )
    tokenizer_path = snapshot_download(
        KRONOS_TOKENIZER_ID,
        revision=KRONOS_TOKENIZER_REVISION,
    )
    tokenizer = KronosTokenizer.from_pretrained(tokenizer_path)
    model = Kronos.from_pretrained(model_path)
    tokenizer.eval()
    model.eval()
    predictor = KronosPredictor(
        model,
        tokenizer,
        device=device,
        max_context=512,
    )
    weight_bytes = sum(
        path.stat().st_size
        for root in (Path(model_path), Path(tokenizer_path))
        for path in root.rglob("*")
        if path.is_file()
    )
    return predictor, torch, {
        "repository": KRONOS_REPOSITORY,
        "repository_commit": commit,
        "model_id": KRONOS_MODEL_ID,
        "model_revision": KRONOS_MODEL_REVISION,
        "tokenizer_id": KRONOS_TOKENIZER_ID,
        "tokenizer_revision": KRONOS_TOKENIZER_REVISION,
        "downloaded_bytes": weight_bytes,
        "device": predictor.device,
        "torch_version": torch.__version__,
    }


def _checkpoint_signature(ohlc_path, comparison_cache_path, device):
    return {
        "version": 1,
        "ohlc_sha256": _sha256(ohlc_path),
        "baseline_cache_namespace": (
            "kronos-small-zero-shot-candidate-4case-baselines-v1"
        ),
        "comparison_cache": str(Path(comparison_cache_path).resolve()),
        "repository_commit": KRONOS_REPOSITORY_COMMIT,
        "model_revision": KRONOS_MODEL_REVISION,
        "tokenizer_revision": KRONOS_TOKENIZER_REVISION,
        "device": device,
        "temperature": 1.0,
        "top_p": 0.9,
        "sample_count": 1,
        "seed": 42,
    }


def _load_checkpoint(path, signature):
    completed = {}
    path = Path(path)
    if not path.exists():
        return completed
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["signature"] != signature:
            raise ValueError("Kronos checkpoint signature mismatch")
        completed[entry["origin"]["period_id"]] = entry["origin"]
    return completed


def run_kronos_origins(
    origins,
    predictor,
    torch,
    checkpoint_path,
    signature,
):
    completed = _load_checkpoint(checkpoint_path, signature)
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    for index, origin in enumerate(origins, start=1):
        if origin["period_id"] in completed:
            continue
        rows = origin["rows"]
        torch.manual_seed(42)
        started = time.perf_counter()
        predictions = predictor.predict_batch(
            df_list=[row["train"] for row in rows],
            x_timestamp_list=[
                pd.Series(row["train"].index) for row in rows
            ],
            y_timestamp_list=[
                row["future_timestamps"] for row in rows
            ],
            pred_len=origin["horizon"],
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )
        scores = {
            row["ticker"]: float(
                prediction["close"].iloc[-1] / row["train"]["close"].iloc[-1]
                - 1.0
            )
            for row, prediction in zip(rows, predictions)
        }
        payload = {
            "period_id": origin["period_id"],
            "case_id": origin["case_id"],
            "train_end": origin["train_end"].isoformat(),
            "horizon": origin["horizon"],
            "elapsed_seconds": time.perf_counter() - started,
            "scores": scores,
        }
        entry = {"signature": signature, "origin": payload}
        with checkpoint_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
            handle.flush()
        completed[payload["period_id"]] = payload
        print(f"[{index}/{len(origins)}] {payload['period_id']}", flush=True)
    return completed


def summarize(origins, kronos_results):
    periods = defaultdict(list)
    all_scores = defaultdict(list)
    expected = defaultdict(int)

    for origin in origins:
        realized = {
            row["ticker"]: row["realized_return"] for row in origin["rows"]
        }
        model_scores = {
            "arima_transformer_rank": {
                row["ticker"]: row["arima_transformer_rank"]
                for row in origin["rows"]
            },
            "transformer_rank": {
                row["ticker"]: row["transformer_rank"]
                for row in origin["rows"]
            },
            "kronos_small_zero_shot": kronos_results.get(
                origin["period_id"], {}
            ).get("scores", {}),
        }
        for model, scores in model_scores.items():
            periods[model].append({
                "period_id": origin["period_id"],
                "case_id": origin["case_id"],
                "scores": scores,
                "realized_returns": realized,
            })
            expected[model] += len(realized)
            all_scores[model].extend(
                {"expected_return": value, "uncertainty": None}
                for value in scores.values()
            )

    models = {}
    for model, model_periods in periods.items():
        rank = cross_sectional_rank_diagnostics(model_periods)
        distribution = prediction_distribution_diagnostics(all_scores[model])
        distribution["active_universe_coverage_rate"] = (
            distribution["valid_count"] / expected[model]
            if expected[model]
            else 0.0
        )
        bootstrap = rank_signal_block_bootstrap(model_periods)
        case_gates = {}
        for case_id in sorted({period["case_id"] for period in model_periods}):
            case_periods = [
                period for period in model_periods
                if period["case_id"] == case_id
            ]
            case_rank = cross_sectional_rank_diagnostics(case_periods)
            case_gates[case_id] = signal_only_gate(
                case_rank,
                distribution,
                minimum_periods=min(4, len(case_periods)),
            )
        overall_gate = signal_only_gate(rank, distribution, bootstrap)
        passed_cases = sum(
            gate["status"] == "passed" for gate in case_gates.values()
        )
        if passed_cases != len(case_gates):
            overall_gate = {
                **overall_gate,
                "status": "rejected",
                "reasons": overall_gate["reasons"] + [
                    f"Passed {passed_cases}/{len(case_gates)} universe gates."
                ],
            }
        models[model] = {
            "rank_diagnostics": rank,
            "distribution_diagnostics": distribution,
            "rank_bootstrap": bootstrap,
            "case_gates": case_gates,
            "signal_gate": overall_gate,
        }

    models["kronos_small_zero_shot"]["paired_vs_arima_transformer"] = (
        paired_rank_signal_block_bootstrap(
            periods["kronos_small_zero_shot"],
            periods["arima_transformer_rank"],
        )
    )
    models["kronos_small_zero_shot"]["paired_vs_transformer"] = (
        paired_rank_signal_block_bootstrap(
            periods["kronos_small_zero_shot"],
            periods["transformer_rank"],
        )
    )
    return models, dict(periods)


def benchmark_decision(kronos_result, minimum_probability=0.95):
    if kronos_result["signal_gate"]["status"] != "passed":
        return "rejected"
    comparisons = (
        kronos_result["paired_vs_arima_transformer"],
        kronos_result["paired_vs_transformer"],
    )
    probabilities = [
        comparison.get("probability", {}).get(metric, 0.0)
        for comparison in comparisons
        for metric in ("higher_mean_rank_ic", "higher_mean_top_bottom_spread")
    ]
    if all(value >= minimum_probability for value in probabilities):
        return "passed"
    return "signal_passed_incremental_unconfirmed"


def write_markdown(payload, path):
    def metric(value, suffix=""):
        return "NA" if value is None else f"{value:.4f}{suffix}"

    lines = [
        "# Kronos Signal-only Benchmark",
        "",
        f"- Status: `{payload['decision']}`",
        f"- Origins: {payload['origin_count']}",
        f"- Universes: {payload['case_count']}",
        f"- Device: `{payload['kronos']['device']}`",
        f"- Kronos inference: {payload['kronos_inference_seconds']:.1f}s",
        f"- Baseline cold-cache fill: {payload['input']['baseline_cache_stats']['cold_fill_span_seconds']:.1f}s",
        "",
        "| Model | Rank IC | Positive IC | Top-bottom | Coverage | Tie rate | Gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for model, result in payload["models"].items():
        rank = result["rank_diagnostics"]
        distribution = result["distribution_diagnostics"]
        lines.append(
            f"| {model} | {metric(rank['mean_rank_ic'])} | "
            f"{metric(rank['positive_rank_ic_rate'] * 100, '%') if rank['positive_rank_ic_rate'] is not None else 'NA'} | "
            f"{metric(rank['mean_top_bottom_spread'])} | "
            f"{metric(distribution['active_universe_coverage_rate'] * 100, '%')} | "
            f"{metric(distribution['tie_rate'] * 100, '%') if distribution['tie_rate'] is not None else 'NA'} | "
            f"{result['signal_gate']['status']} |"
        )
    lines.extend(["", "## Kronos gate", ""])
    reasons = payload["models"]["kronos_small_zero_shot"]["signal_gate"]["reasons"]
    lines.extend(f"- {reason}" for reason in reasons or ["Passed."])
    lines.extend(["", "## Incremental evidence", ""])
    for baseline, key in (
        ("ARIMA + Transformer", "paired_vs_arima_transformer"),
        ("Transformer", "paired_vs_transformer"),
    ):
        probability = payload["models"]["kronos_small_zero_shot"][key][
            "probability"
        ]
        lines.append(
            f"- vs {baseline}: higher rank IC "
            f"{probability['higher_mean_rank_ic']:.1%}; higher spread "
            f"{probability['higher_mean_top_bottom_spread']:.1%}"
        )
    if payload["decision"] == "signal_passed_incremental_unconfirmed":
        lines.append("- Absolute gate passed; paired uplift stayed below 95%.")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _peak_rss_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform != "darwin":
        value *= 1024
    return value / (1024 * 1024)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-cache", required=True)
    parser.add_argument("--comparison-cache")
    parser.add_argument("--ohlc-csv")
    parser.add_argument("--kronos-repo", required=True)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--checkpoint")
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = load_cached_forecasts(args.forecast_cache)
    ohlc_path = Path(args.ohlc_csv) if args.ohlc_csv else output.with_suffix(".ohlc.csv")
    if args.ohlc_csv:
        ohlc = read_ohlc_csv(ohlc_path)
    elif ohlc_path.exists():
        ohlc = read_ohlc_csv(ohlc_path)
    else:
        ohlc = download_ohlc(cache, ohlc_path)

    origins, mismatches = build_aligned_origins(
        cache,
        ohlc,
        strict_digest=False,
    )
    if len({origin["case_id"] for origin in origins}) != 4:
        raise ValueError("Expected four aligned candidate universes")

    try:
        import torch as _torch  # noqa: F401
        import huggingface_hub as _huggingface_hub  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Install requirements-kronos-research.txt in a research environment"
        ) from exc

    comparison_cache = (
        Path(args.comparison_cache)
        if args.comparison_cache
        else output.with_suffix(".baseline.sqlite3")
    )
    baseline_cache_stats = run_baseline_origins(origins, comparison_cache)
    predictor, torch, kronos_metadata = load_kronos_predictor(
        args.kronos_repo,
        args.device,
    )
    checkpoint = Path(args.checkpoint) if args.checkpoint else output.with_suffix(
        ".checkpoint.jsonl"
    )
    signature = _checkpoint_signature(
        ohlc_path,
        comparison_cache,
        args.device,
    )
    if not args.resume:
        checkpoint.write_text("", encoding="utf-8")
    started = time.perf_counter()
    kronos_results = run_kronos_origins(
        origins,
        predictor,
        torch,
        checkpoint,
        signature,
    )
    models, periods = summarize(origins, kronos_results)
    decision = benchmark_decision(models["kronos_small_zero_shot"])
    kronos_inference_seconds = sum(
        result["elapsed_seconds"] for result in kronos_results.values()
    )
    kronos_prediction_count = sum(
        len(result["scores"]) for result in kronos_results.values()
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purpose": "research signal-only gate; no production promotion",
        "decision": decision,
        "origin_count": len(origins),
        "case_count": len({origin["case_id"] for origin in origins}),
        "case_universes": {
            origin["case_id"]: [row["ticker"] for row in origin["rows"]]
            for origin in origins
        },
        "orchestration_elapsed_seconds": time.perf_counter() - started,
        "process_peak_rss_mib": _peak_rss_mib(),
        "kronos_inference_seconds": kronos_inference_seconds,
        "kronos_prediction_count": kronos_prediction_count,
        "kronos_predictions_per_second": (
            kronos_prediction_count / kronos_inference_seconds
        ),
        "kronos": kronos_metadata,
        "input": {
            "forecast_cache": str(Path(args.forecast_cache).resolve()),
            "forecast_cache_sha256": _sha256(args.forecast_cache),
            "baseline_comparison_cache": str(comparison_cache.resolve()),
            "baseline_cache_stats": baseline_cache_stats,
            "ohlc_csv": str(ohlc_path.resolve()),
            "ohlc_sha256": _sha256(ohlc_path),
            "alignment_mismatches": mismatches,
        },
        "models": models,
        "periods": periods,
        "checkpoint": str(checkpoint.resolve()),
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_markdown(payload, output.with_suffix(".md"))
    print(f"Kronos benchmark decision: {decision}")
    print(f"Wrote {output}")
    print(f"Wrote {output.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
