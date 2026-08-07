#!/usr/bin/env python3
"""Run the research-only pooled Patch Transformer on frozen local origins."""

import argparse
import copy
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from pooled_patch_transformer import (  # noqa: E402
    PatchTransformerConfig,
    compare_patch_transformer_runs,
    load_kronos_checkpoint,
    walk_forward_pooled_patch_transformer,
)
from forecast_signal_research import (  # noqa: E402
    cross_sectional_rank_diagnostics,
    prediction_distribution_diagnostics,
    rank_signal_block_bootstrap,
    signal_only_gate,
)
from portfolio_backtest import _model_weights  # noqa: E402
from portfolio_backtest import (  # noqa: E402
    build_rebalance_targets,
    run_portfolio_model_backtest,
)
from portfolio_statistics import (  # noqa: E402
    bootstrap_improvement_gate,
    paired_block_bootstrap,
)
from portfolio_signals import (  # noqa: E402
    cap_and_normalize_weights,
    confidence_gated_gmv_overlay,
)


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_ohlcv(path):
    frame = pd.read_csv(path)
    required = {"timestamp", "ticker", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("OHLCV CSV is missing: " + ", ".join(missing))
    frame["timestamp"] = pd.to_datetime(frame["timestamp"]).dt.tz_localize(None)
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    return frame.sort_values(["timestamp", "ticker"]).reset_index(drop=True)


def _close_panel(ohlcv):
    return ohlcv.pivot(index="timestamp", columns="ticker", values="close").sort_index()


def _origin_inputs(kronos):
    dates = sorted(pd.to_datetime(kronos["as_of_date"].unique()))
    universes = {
        pd.Timestamp(as_of): sorted(
            kronos.loc[kronos["as_of_date"] == as_of, "ticker"].unique()
        )
        for as_of in dates
    }
    return dates, universes


def _signal_candidate(model, records, *, source=None):
    periods = [
        {
            "period_id": row["period_id"],
            "scores": row["scores"],
            "realized_returns": row["realized_returns"],
        }
        for row in records
    ]
    predictions = [
        {"ticker": ticker, "expected_return": value, "uncertainty": None}
        for row in records
        for ticker, value in row["scores"].items()
    ]
    rank = cross_sectional_rank_diagnostics(periods)
    distribution = prediction_distribution_diagnostics(predictions)
    expected_count = sum(len(row["realized_returns"]) for row in records)
    distribution["active_universe_coverage_rate"] = (
        0.0 if not expected_count else len(predictions) / expected_count
    )
    bootstrap = rank_signal_block_bootstrap(periods)
    return {
        "model": model,
        "source": source,
        "records": records,
        "fit_count": 0,
        "fit_seconds": 0.0,
        "rank_diagnostics": rank,
        "distribution_diagnostics": distribution,
        "rank_bootstrap": bootstrap,
        "signal_gate": signal_only_gate(rank, distribution, bootstrap),
    }


def _kronos_baseline(candidate, kronos):
    lookup = kronos.set_index(["as_of_date", "ticker"])["kronos_score"]
    records = []
    for row in candidate["records"]:
        as_of = pd.Timestamp(row["as_of_date"])
        scores = {}
        realized = {}
        for ticker, value in row["realized_returns"].items():
            key = (as_of, ticker)
            if key not in lookup.index:
                continue
            scores[ticker] = float(lookup.loc[key])
            realized[ticker] = float(value)
        records.append({
            "period_id": row["period_id"],
            "as_of_date": row["as_of_date"],
            "forward_end_date": row["forward_end_date"],
            "scores": scores,
            "realized_returns": realized,
        })
    return _signal_candidate(
        "frozen_kronos_score",
        records,
        source="Kronos checkpoint",
    )


def _cached_forecast_signal_candidates(
    cache_path,
    reference_candidate,
    *,
    namespace,
):
    """Recover exact-origin ARIMA/Transformer signals from the frozen cache."""
    cache_path = Path(cache_path).expanduser().resolve()
    if not cache_path.exists():
        raise ValueError(f"Forecast cache does not exist: {cache_path}")
    connection = sqlite3.connect(str(cache_path))
    try:
        rows = connection.execute(
            "SELECT key_payload, prediction_payload FROM forecast_predictions"
        ).fetchall()
    finally:
        connection.close()

    lookups = {
        "transformer": {},
        "arima_transformer": {},
        "arima": {},
    }
    for key_payload, prediction_payload in rows:
        key = json.loads(key_payload)
        if len(key) < 8 or key[1] != namespace:
            continue
        method = key[2]
        if method not in {"transformer_rank", "arima_transformer_rank"}:
            continue
        prediction = json.loads(prediction_payload)
        date_ticker = (
            pd.Timestamp(key[7]).strftime("%Y-%m-%d"),
            str(key[3]).strip().upper(),
        )
        if method == "transformer_rank":
            values = {"transformer": prediction.get("expected_return")}
        else:
            values = {
                "arima_transformer": prediction.get("expected_return"),
                "arima": (prediction.get("components") or {}).get("ARIMA"),
            }
        for model, value in values.items():
            if value is not None and np.isfinite(float(value)):
                lookups[model][date_ticker] = float(value)

    candidates = {}
    for model, lookup in lookups.items():
        records = []
        for reference in reference_candidate["records"]:
            as_of_date = pd.Timestamp(reference["as_of_date"]).strftime(
                "%Y-%m-%d"
            )
            tickers = list(reference["scores"])
            missing = [
                ticker
                for ticker in tickers
                if (as_of_date, ticker) not in lookup
            ]
            if missing:
                raise ValueError(
                    f"{model} cache missing {as_of_date}: " + ", ".join(missing)
                )
            records.append({
                "period_id": reference["period_id"],
                "as_of_date": reference["as_of_date"],
                "forward_end_date": reference["forward_end_date"],
                "scores": {
                    ticker: lookup[(as_of_date, ticker)] for ticker in tickers
                },
                "realized_returns": {
                    ticker: float(reference["realized_returns"][ticker])
                    for ticker in tickers
                },
            })
        candidates[model] = _signal_candidate(
            model,
            records,
            source=f"forecast cache namespace {namespace}",
        )
    return candidates, {
        "path": str(cache_path),
        "sha256": _sha256(cache_path),
        "namespace": namespace,
        "row_count": len(rows),
    }


def _overlay_preview(prices, candidate, max_asset_weight):
    if not candidate["records"]:
        return None
    latest = candidate["records"][-1]
    as_of = pd.Timestamp(latest["as_of_date"])
    tickers = list(latest["scores"])
    training = prices.loc[:as_of, tickers].tail(504).dropna(axis=1, how="any")
    tickers = list(training.columns)
    if len(tickers) < 2:
        return None
    effective_cap = max(float(max_asset_weight), 1.0 / len(tickers) + 1e-9)
    gmv, diagnostics = _model_weights(
        "min_variance",
        training,
        candidate["primary_horizon"],
        effective_cap,
        0.0,
    )
    gate = candidate.get("latest_sequential_gate") or {
        "active": False,
        "strength": 0.0,
    }
    gmv_baseline = cap_and_normalize_weights(
        pd.Series(gmv, dtype=float),
        max_asset_weight=effective_cap,
    )
    overlay, overlay_diagnostics = confidence_gated_gmv_overlay(
        gmv_baseline,
        pd.Series(latest["scores"], dtype=float).reindex(tickers),
        gate,
        max_asset_weight=effective_cap,
        target_active_share=0.05,
    )
    return {
        "as_of_date": latest["as_of_date"],
        "tickers": tickers,
        "max_asset_weight": effective_cap,
        "gmv_weights": {
            key: float(value) for key, value in gmv_baseline.items()
        },
        "overlay_weights": {
            key: float(value) for key, value in overlay.items()
        },
        "exact_gmv_fallback": bool(
            np.allclose(
                gmv_baseline.reindex(tickers),
                overlay.reindex(tickers),
                atol=1e-12,
            )
        ),
        "gate": gate,
        "overlay": overlay_diagnostics,
        "gmv": diagnostics,
    }


def _fixed_gamma_gmv_experiment(
    prices,
    candidate,
    *,
    gamma,
    max_asset_weight,
    transaction_cost_bps,
    rebalance_band,
    max_turnover,
):
    """Replay one fixed DL tilt through the existing execution engine."""
    if not 0.0 <= float(gamma) < 0.5:
        raise ValueError("gamma must be in [0, 0.5)")
    grouped = {}
    for record in candidate.get("records", []):
        grouped.setdefault(tuple(record["scores"]), []).append(record)

    cases = []
    daily_returns = {"gmv": {}, "gmv_dl_tilt": {}}
    raw_active_shares = []
    executed_active_shares = []
    for case_index, (ticker_tuple, records) in enumerate(grouped.items(), start=1):
        records = sorted(records, key=lambda row: row["as_of_date"])
        tickers = list(ticker_tuple)
        first_position = prices.index.get_loc(pd.Timestamp(records[0]["as_of_date"]))
        last_position = prices.index.get_loc(pd.Timestamp(records[-1]["forward_end_date"]))
        case_prices = prices.iloc[first_position - 504:last_position + 1].loc[:, tickers]
        effective_cap = max(
            float(max_asset_weight),
            1.0 / len(tickers) + 1e-9,
        )
        baseline_targets = build_rebalance_targets(
            case_prices,
            models=["min_variance"],
            train_window=504,
            rebalance_frequency=63,
            forecast_horizon=63,
            max_asset_weight=effective_cap,
            risk_free_rate=0.0,
            target_turnover_limit=max_turnover,
        )
        scores_by_date = {
            row["as_of_date"]: row["scores"] for row in records
        }
        target_dates = [row["rebalance_date"] for row in baseline_targets["records"]]
        if target_dates != list(scores_by_date):
            raise ValueError("Patch scores do not align with GMV rebalance dates")

        tilted_targets = copy.deepcopy(baseline_targets)
        for target in tilted_targets["records"]:
            model_target = target["models"]["min_variance"]
            weights, diagnostics = confidence_gated_gmv_overlay(
                model_target["weights"],
                scores_by_date[target["rebalance_date"]],
                {"active": True, "strength": 1.0},
                max_asset_weight=effective_cap,
                target_active_share=gamma,
            )
            raw_active_shares.append(diagnostics["realized_active_share"])
            model_target["weights"] = weights.to_dict()
            model_target["diagnostics"].update({
                "construction_method": "gmv_plus_fixed_dl_rank_tilt",
                "gamma": float(gamma),
                "signal_scores": scores_by_date[target["rebalance_date"]],
                "gmv_overlay": diagnostics,
            })

        runs = {}
        for name, targets in (
            ("gmv", baseline_targets),
            ("gmv_dl_tilt", tilted_targets),
        ):
            runs[name] = run_portfolio_model_backtest(
                case_prices,
                models=["min_variance"],
                train_window=504,
                rebalance_frequency=63,
                forecast_horizon=63,
                transaction_cost_bps=transaction_cost_bps,
                max_asset_weight=effective_cap,
                rebalance_band=rebalance_band,
                max_turnover=max_turnover,
                risk_free_rate=0.0,
                rebalance_targets=targets,
                include_daily_returns=True,
            )
            daily_returns[name].update({
                f"case_{case_index}:{date}": value
                for date, value in runs[name]["daily_returns_by_model"][
                    "min_variance"
                ].items()
            })

        baseline_records = runs["gmv"]["rebalance_records"]
        tilted_records = runs["gmv_dl_tilt"]["rebalance_records"]
        for baseline_record, tilted_record in zip(
            baseline_records,
            tilted_records,
        ):
            baseline_weights = pd.Series(
                baseline_record["controlled_weights"],
                dtype=float,
            )
            tilted_weights = pd.Series(
                tilted_record["controlled_weights"],
                dtype=float,
            )
            executed_active_shares.append(
                float(
                    0.5
                    * (
                        tilted_weights.reindex(tickers).fillna(0.0)
                        - baseline_weights.reindex(tickers).fillna(0.0)
                    ).abs().sum()
                )
            )

        metric_names = (
            "cagr",
            "annual_volatility",
            "sharpe",
            "max_drawdown",
            "net_cumulative_return",
            "avg_controlled_turnover",
            "transaction_cost_return_drag",
        )
        cases.append({
            "case_id": f"case_{case_index}",
            "tickers": tickers,
            "period_count": len(records),
            "start_date": records[0]["as_of_date"],
            "end_date": records[-1]["forward_end_date"],
            "models": {
                name: {
                    metric: result["summary_by_model"]["min_variance"].get(metric)
                    for metric in metric_names
                }
                for name, result in runs.items()
            },
        })

    bootstrap = paired_block_bootstrap(
        pd.Series(daily_returns["gmv_dl_tilt"]),
        pd.Series(daily_returns["gmv"]),
        risk_free_rate=0.0,
        block_size=21,
    )
    return {
        "status": "diagnostic_only",
        "promotion_safe": False,
        "formula": "w=project_capped_simplex(w_GMV+gamma*alpha_tilt)",
        "alpha_tilt_normalization": "centered cross-sectional rank; L1 norm 2",
        "gamma": float(gamma),
        "transaction_cost_bps": float(transaction_cost_bps),
        "rebalance_band": float(rebalance_band),
        "max_turnover": float(max_turnover),
        "case_count": len(cases),
        "period_count": sum(case["period_count"] for case in cases),
        "mean_raw_active_share": (
            None if not raw_active_shares else float(np.mean(raw_active_shares))
        ),
        "mean_executed_active_share": (
            None
            if not executed_active_shares
            else float(np.mean(executed_active_shares))
        ),
        "cases": cases,
        "paired_daily_bootstrap_vs_gmv": bootstrap,
        "portfolio_gate": bootstrap_improvement_gate(bootstrap),
    }


def _fixed_gamma_model_comparison(
    prices,
    candidates,
    *,
    gamma,
    max_asset_weight,
    transaction_cost_bps,
    rebalance_band,
    max_turnover,
):
    models = {}
    for name, candidate in candidates.items():
        models[name] = {
            "signal": {
                "rank_diagnostics": candidate["rank_diagnostics"],
                "signal_gate": candidate["signal_gate"],
            },
            "portfolio": _fixed_gamma_gmv_experiment(
                prices,
                candidate,
                gamma=gamma,
                max_asset_weight=max_asset_weight,
                transaction_cost_bps=transaction_cost_bps,
                rebalance_band=rebalance_band,
                max_turnover=max_turnover,
            ),
        }

    ranking = []
    for name, result in models.items():
        portfolio = result["portfolio"]
        bootstrap = portfolio["paired_daily_bootstrap_vs_gmv"]
        observed = bootstrap.get("observed", {})
        candidate_metrics = observed.get("candidate", {})
        difference = observed.get("difference", {})
        ranking.append({
            "model": name,
            "annualized_return": candidate_metrics.get("annualized_return"),
            "annualized_volatility": candidate_metrics.get(
                "annualized_volatility"
            ),
            "sharpe": candidate_metrics.get("sharpe"),
            "return_difference_vs_gmv": difference.get("annualized_return"),
            "volatility_difference_vs_gmv": difference.get(
                "annualized_volatility"
            ),
            "sharpe_difference_vs_gmv": difference.get("sharpe"),
            "probability": bootstrap.get("probability", {}),
            "portfolio_gate": portfolio["portfolio_gate"]["status"],
        })
    ranking.sort(
        key=lambda row: (
            row["sharpe"] is not None,
            row["sharpe"] if row["sharpe"] is not None else -np.inf,
        ),
        reverse=True,
    )
    for position, row in enumerate(ranking, start=1):
        row["rank_by_sharpe"] = position
    return {
        "status": "diagnostic_only",
        "promotion_safe": False,
        "selection_allowed": False,
        "gamma": float(gamma),
        "models": models,
        "ranking": ranking,
    }


def _metric(value):
    return "NA" if value is None else f"{value:.4f}"


def _write_markdown(payload, path):
    lines = [
        "# Pooled Patch Transformer Diagnostic",
        "",
        f"- Decision: `{payload['decision']}`",
        "- Role: research-only; consumed validation origins; not promotion-safe",
        f"- Origins: {payload['inputs']['origin_count']}",
        f"- Kronos scores: {payload['inputs']['kronos_score_count']}",
        "",
        "| Model | Rank IC | Positive IC | Top-bottom | Gate | Fits | Seconds |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    for name in (
        "arima",
        "transformer",
        "arima_transformer",
        "frozen_kronos_score",
        "patch_without_kronos",
        "patch_with_kronos",
    ):
        if name not in payload["models"]:
            continue
        result = payload["models"][name]
        rank = result["rank_diagnostics"]
        lines.append(
            f"| {name} | {_metric(rank['mean_rank_ic'])} | "
            f"{_metric(rank['positive_rank_ic_rate'])} | "
            f"{_metric(rank['mean_top_bottom_spread'])} | "
            f"{result['signal_gate']['status']} | {result['fit_count']} | "
            f"{result['fit_seconds']:.1f} |"
        )
    lines.extend([
        "",
        "## Paired evidence",
        "",
    ])
    for name, result in payload["paired"].items():
        probability = result.get("probability") or {}
        lines.append(
            f"- {name}: rank IC "
            f"{_metric(probability.get('higher_mean_rank_ic'))}, spread "
            f"{_metric(probability.get('higher_mean_top_bottom_spread'))}; "
            f"gate `{result['gate']['status']}`"
        )
    overlay = payload.get("latest_overlay_preview")
    if overlay is not None:
        lines.extend([
            "",
            "## Latest GMV overlay",
            "",
            f"- Signal gate: `{overlay['gate']['status']}`",
            f"- Exact GMV fallback: `{overlay['exact_gmv_fallback']}`",
            f"- Realized active share: {overlay['overlay']['realized_active_share']:.4f}",
        ])
    experiment = payload.get("gmv_alpha_tilt_experiment")
    if experiment is not None:
        probability = experiment["paired_daily_bootstrap_vs_gmv"].get(
            "probability",
            {},
        )
        lines.extend([
            "",
            "## Patch+Kronos fixed-gamma GMV + DL tilt",
            "",
            f"- Gamma: `{experiment['gamma']:.4f}`",
            f"- Mean raw/executed active share: "
            f"{experiment['mean_raw_active_share']:.4f} / "
            f"{experiment['mean_executed_active_share']:.4f}",
            f"- P(higher return): {_metric(probability.get('higher_return'))}",
            f"- P(higher Sharpe): {_metric(probability.get('higher_sharpe'))}",
            f"- P(lower volatility): {_metric(probability.get('lower_volatility'))}",
            f"- Portfolio gate: `{experiment['portfolio_gate']['status']}`",
        ])
    comparison = payload.get("gmv_alpha_tilt_model_comparison")
    if comparison is not None:
        lines.extend([
            "",
            "## Fixed-gamma signal model comparison",
            "",
            "| Rank | Signal | Return diff | Vol diff | Sharpe diff | "
            "P(return) | P(Sharpe) | Gate |",
            "|---:|---|---:|---:|---:|---:|---:|---|",
        ])
        for row in comparison["ranking"]:
            probability = row["probability"]
            lines.append(
                f"| {row['rank_by_sharpe']} | {row['model']} | "
                f"{_metric(row['return_difference_vs_gmv'])} | "
                f"{_metric(row['volatility_difference_vs_gmv'])} | "
                f"{_metric(row['sharpe_difference_vs_gmv'])} | "
                f"{_metric(probability.get('higher_return'))} | "
                f"{_metric(probability.get('higher_sharpe'))} | "
                f"{row['portfolio_gate']} |"
            )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ohlcv-csv", required=True)
    parser.add_argument("--kronos-checkpoint", required=True)
    parser.add_argument(
        "--forecast-cache",
        help="Frozen ARIMA/Transformer cache; defaults to checkpoint signature.",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--lookback", type=int, default=504)
    parser.add_argument("--patch-size", type=int, default=5)
    parser.add_argument("--horizons", nargs="+", type=int, default=[21, 63])
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--minimum-training-periods", type=int, default=8)
    parser.add_argument("--maximum-training-periods", type=int, default=12)
    parser.add_argument("--minimum-observations", type=int, default=60)
    parser.add_argument("--max-asset-weight", type=float, default=0.20)
    parser.add_argument("--gamma", type=float, default=0.025)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--rebalance-band", type=float, default=0.02)
    parser.add_argument("--max-turnover", type=float, default=0.35)
    parser.add_argument(
        "--acknowledge-consumed-validation",
        action="store_true",
        help="Required because the bundled Kronos origins are already consumed.",
    )
    args = parser.parse_args(argv)
    if not args.acknowledge_consumed_validation:
        raise ValueError(
            "This runner requires --acknowledge-consumed-validation; "
            "its output cannot be used for promotion."
        )

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    ohlcv_path = Path(args.ohlcv_csv).expanduser().resolve()
    ohlcv = _read_ohlcv(ohlcv_path)
    prices = _close_panel(ohlcv)
    primary_horizon = max(args.horizons)
    kronos, kronos_meta = load_kronos_checkpoint(
        args.kronos_checkpoint,
        expected_horizon=primary_horizon,
    )
    ohlcv_sha256 = _sha256(ohlcv_path)
    expected_ohlcv_sha256 = str(
        kronos_meta["signature"].get("ohlc_sha256") or ""
    )
    if expected_ohlcv_sha256 and ohlcv_sha256 != expected_ohlcv_sha256:
        raise ValueError(
            "OHLCV CSV SHA-256 does not match the Kronos checkpoint signature"
        )
    dates, universes = _origin_inputs(kronos)
    config = PatchTransformerConfig(
        lookback=args.lookback,
        patch_size=args.patch_size,
        horizons=tuple(args.horizons),
        epochs=args.epochs,
    )
    common = {
        "ohlcv_data": ohlcv,
        "config": config,
        "target_kind": "relative",
        "kronos_features": kronos,
        "origin_dates": dates,
        "origin_universes": universes,
        "minimum_training_periods": args.minimum_training_periods,
        "maximum_training_periods": args.maximum_training_periods,
        "minimum_observations": args.minimum_observations,
    }
    without_kronos = walk_forward_pooled_patch_transformer(
        prices,
        include_kronos=False,
        **common,
    )
    with_kronos = walk_forward_pooled_patch_transformer(
        prices,
        include_kronos=True,
        **common,
    )
    kronos_baseline = _kronos_baseline(with_kronos, kronos)
    forecast_cache_path = (
        args.forecast_cache
        or kronos_meta["signature"].get("comparison_cache")
    )
    forecast_cache_namespace = kronos_meta["signature"].get(
        "baseline_cache_namespace"
    )
    if not forecast_cache_path or not forecast_cache_namespace:
        raise ValueError(
            "Kronos signature must identify the frozen forecast cache/namespace"
        )
    cached_candidates, forecast_cache_meta = (
        _cached_forecast_signal_candidates(
            forecast_cache_path,
            with_kronos,
            namespace=forecast_cache_namespace,
        )
    )
    signal_candidates = {
        **cached_candidates,
        "frozen_kronos_score": kronos_baseline,
        "patch_without_kronos": without_kronos,
        "patch_with_kronos": with_kronos,
    }
    model_comparison = _fixed_gamma_model_comparison(
        prices,
        signal_candidates,
        gamma=args.gamma,
        max_asset_weight=args.max_asset_weight,
        transaction_cost_bps=args.transaction_cost_bps,
        rebalance_band=args.rebalance_band,
        max_turnover=args.max_turnover,
    )
    paired = {
        "with_kronos_vs_without_kronos": compare_patch_transformer_runs(
            with_kronos,
            without_kronos,
        ),
        "with_kronos_vs_kronos_score": compare_patch_transformer_runs(
            with_kronos,
            kronos_baseline,
        ),
    }
    decision = "rejected"
    if with_kronos["signal_gate"]["status"] == "passed":
        decision = (
            "passed"
            if all(result["gate"]["status"] == "passed" for result in paired.values())
            else "signal_passed_incremental_unconfirmed"
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "research-only pooled Patch Transformer diagnostic",
        "promotion_safe": False,
        "consumed_validation_acknowledged": True,
        "decision": decision,
        "inputs": {
            "ohlcv_csv": str(ohlcv_path),
            "ohlcv_sha256": ohlcv_sha256,
            "ohlcv_rows": int(len(ohlcv)),
            "ticker_count": int(ohlcv["ticker"].nunique()),
            "origin_count": kronos_meta["origin_count"],
            "kronos_score_count": kronos_meta["score_count"],
            "kronos": kronos_meta,
            "forecast_cache": forecast_cache_meta,
        },
        "models": signal_candidates,
        "paired": paired,
        "latest_overlay_preview": _overlay_preview(
            prices,
            with_kronos,
            args.max_asset_weight,
        ),
        "gmv_alpha_tilt_experiment": model_comparison["models"]
        ["patch_with_kronos"]["portfolio"],
        "gmv_alpha_tilt_model_comparison": model_comparison,
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    markdown = output.with_suffix(".md")
    _write_markdown(payload, markdown)
    print(json.dumps({
        "decision": decision,
        "output": str(output),
        "markdown": str(markdown),
        "without_kronos": without_kronos["rank_diagnostics"],
        "with_kronos": with_kronos["rank_diagnostics"],
        "overlay_fallback": (
            payload["latest_overlay_preview"]["exact_gmv_fallback"]
            if payload["latest_overlay_preview"] is not None
            else None
        ),
        "gmv_alpha_tilt": {
            "gamma": payload["gmv_alpha_tilt_experiment"]["gamma"],
            "gate": payload["gmv_alpha_tilt_experiment"]["portfolio_gate"]["status"],
            "probability": payload["gmv_alpha_tilt_experiment"][
                "paired_daily_bootstrap_vs_gmv"
            ].get("probability"),
        },
        "gmv_alpha_tilt_ranking": model_comparison["ranking"],
    }, indent=2))


if __name__ == "__main__":
    main()
