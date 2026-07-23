#!/usr/bin/env python3
"""Audit completed-OOS uncertainty calibration for lightweight BL."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from portfolio_backtest import run_portfolio_model_backtest  # noqa: E402
from portfolio_statistics import (  # noqa: E402
    holm_bonferroni,
    paired_block_bootstrap,
)
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "calibrated_lightweight_bl"
BASELINE = "lightweight_bl"
MODELS = (
    "equal_weight",
    "risk_parity",
    "historical_bl",
    BASELINE,
    CANDIDATE,
)
CALIBRATION_SPECIFICATION = {
    "method": "completed_oos_residual_rmse",
    "min_origin_history": 126,
    "max_origins": 6,
    "origin_step": "forecast_horizon",
    "uncertainty_prior": 0.20,
    "uncertainty_prior_weight": 0.50,
    "point_forecast": "unchanged_lightweight_ensemble",
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _settings(args):
    return {
        "train_window": int(args.train_window),
        "rebalance_frequency": int(args.rebalance_frequency),
        "forecast_horizon": int(args.forecast_horizon),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "max_asset_weight": float(args.max_asset_weight),
        "rebalance_band": float(args.rebalance_band),
        "max_turnover": float(args.max_turnover),
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_block_size": int(args.bootstrap_block_size),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
        "candidate": CANDIDATE,
        "baseline": BASELINE,
        "models": list(MODELS),
        "calibration": CALIBRATION_SPECIFICATION,
    }


def _load_prices(args):
    path = Path(args.csv).expanduser().resolve()
    provenance_path = Path(
        args.price_provenance
    ).expanduser().resolve()
    prices = pd.read_csv(path, index_col=0, parse_dates=True)
    prices = prices.sort_index().replace([np.inf, -np.inf], np.nan)
    if prices.empty or prices.isna().any().any():
        raise ValueError("Research prices must be complete and non-empty")
    provenance = _load_json(provenance_path)
    if provenance.get("price_file_sha256") != _sha256(path):
        raise ValueError("Price provenance SHA does not match CSV")
    if list(provenance.get("tickers") or []) != list(prices.columns):
        raise ValueError("Price provenance ticker order does not match CSV")
    if not provenance.get("promotion_safe", False):
        raise ValueError("Price provenance is not promotion safe")
    return prices, path, provenance_path, provenance


def _load_risk_free(args, prices):
    path = Path(args.risk_free_data).expanduser().resolve()
    provenance_path = Path(
        args.risk_free_provenance
    ).expanduser().resolve()
    frame = pd.read_csv(path, index_col=0, parse_dates=True).sort_index()
    if "rf_daily" not in frame:
        raise ValueError("Risk-free data requires rf_daily")
    series = (
        pd.to_numeric(frame["rf_daily"], errors="coerce")
        .reindex(prices.index)
    )
    if series.isna().any():
        raise ValueError("Risk-free data does not cover every price date")
    provenance = _load_json(provenance_path)
    if provenance.get("factor_file_sha256") != _sha256(path):
        raise ValueError("Risk-free provenance SHA does not match CSV")
    if not provenance.get("promotion_safe", False):
        raise ValueError("Risk-free provenance is not promotion safe")
    return series, path, provenance_path, provenance


def _deterministic_gate(summary):
    candidate = summary[CANDIDATE]
    baseline = summary[BASELINE]
    reasons = []
    if candidate["sharpe"] <= baseline["sharpe"]:
        reasons.append("Sharpe does not improve current lightweight BL.")
    if candidate["cagr"] <= baseline["cagr"]:
        reasons.append("CAGR does not improve current lightweight BL.")
    if candidate["max_drawdown"] < baseline["max_drawdown"]:
        reasons.append("Max drawdown is worse than current lightweight BL.")
    if candidate["avg_controlled_turnover"] > max(
        0.50,
        baseline["avg_controlled_turnover"] * 1.25,
    ):
        reasons.append("Turnover exceeds the predeclared baseline guard.")
    for guard in ("equal_weight", "risk_parity", "historical_bl"):
        guard_metrics = summary[guard]
        if candidate["sharpe"] <= guard_metrics["sharpe"]:
            reasons.append(f"Sharpe does not beat {guard}.")
        if candidate["max_drawdown"] < guard_metrics["max_drawdown"]:
            reasons.append(f"Max drawdown is worse than {guard}.")
    if candidate.get("failed_forecast_count", 0) > 0:
        reasons.append("Candidate produced no-view forecasts.")
    if (
        candidate.get("avg_signal_rank_ic") is None
        or candidate["avg_signal_rank_ic"] <= 0.0
    ):
        reasons.append("Candidate mean signal rank IC is not positive.")
    if (
        candidate.get("positive_signal_rank_ic_rate") is None
        or candidate["positive_signal_rank_ic_rate"] < 0.50
    ):
        reasons.append("Candidate positive rank-IC rate is below 50%.")
    if (
        candidate.get("avg_top_bottom_spread") is None
        or candidate["avg_top_bottom_spread"] <= 0.0
    ):
        reasons.append("Candidate top-bottom spread is not positive.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }


def _calibration_summary(result):
    rows = []
    for rebalance in result.get("rebalance_records", []):
        if rebalance.get("model") != CANDIDATE:
            continue
        diagnostics = (
            rebalance.get(
                "lightweight_uncertainty_calibration",
                {},
            )
            or {}
        )
        for ticker, item in diagnostics.items():
            rows.append({
                "rebalance_date": rebalance.get("rebalance_date"),
                "ticker": ticker,
                "observation_count": int(
                    item.get("observation_count", 0)
                ),
                "raw_oos_rmse": item.get("raw_oos_rmse"),
                "oos_bias": item.get("oos_bias"),
            })
    rmse = np.asarray(
        [
            row["raw_oos_rmse"]
            for row in rows
            if row["raw_oos_rmse"] is not None
            and np.isfinite(row["raw_oos_rmse"])
        ],
        dtype=float,
    )
    counts = np.asarray(
        [row["observation_count"] for row in rows],
        dtype=float,
    )
    return {
        "ticker_rebalance_count": int(len(rows)),
        "mean_observation_count": (
            None if len(counts) == 0 else float(counts.mean())
        ),
        "minimum_observation_count": (
            None if len(counts) == 0 else int(counts.min())
        ),
        "mean_raw_oos_rmse": (
            None if len(rmse) == 0 else float(rmse.mean())
        ),
        "median_raw_oos_rmse": (
            None if len(rmse) == 0 else float(np.median(rmse))
        ),
        "raw_oos_rmse_p90": (
            None if len(rmse) == 0 else float(np.quantile(rmse, 0.90))
        ),
    }


def _fmt(value):
    return "NA" if value is None else f"{float(value):.4f}"


def _write_report(payload, output_path):
    summary = payload["result"]["summary_by_model"]
    probability = payload["paired_bootstrap"].get("probability", {})
    lines = [
        "# Lightweight OOS-Uncertainty Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Rows/tickers: `{payload['data']['row_count']}` / "
        f"`{payload['data']['ticker_count']}`",
        f"- Deterministic gate: `{payload['deterministic_gate']['status']}`",
        f"- Statistical gate: `{payload['statistical_gate']['status']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Performance",
        "",
        "| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover | "
        "Mean rank IC | Top-bottom |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        metrics = summary[model]
        lines.append(
            "| {model} | {cagr} | {volatility} | {sharpe} | "
            "{drawdown} | {turnover} | {rank_ic} | {spread} |".format(
                model=model,
                cagr=_fmt(metrics.get("cagr")),
                volatility=_fmt(metrics.get("annual_volatility")),
                sharpe=_fmt(metrics.get("sharpe")),
                drawdown=_fmt(metrics.get("max_drawdown")),
                turnover=_fmt(metrics.get("avg_controlled_turnover")),
                rank_ic=_fmt(metrics.get("avg_signal_rank_ic")),
                spread=_fmt(metrics.get("avg_top_bottom_spread")),
            )
        )
    lines.extend([
        "",
        "## Paired Evidence",
        "",
        f"- P(higher return): "
        f"`{_fmt(probability.get('higher_return'))}`",
        f"- P(higher Sharpe): "
        f"`{_fmt(probability.get('higher_sharpe'))}`",
        f"- Holm return adjusted p: "
        f"`{_fmt(payload['holm_gate'].get('higher_return', {}).get('adjusted_p_value'))}`",
        f"- Holm Sharpe adjusted p: "
        f"`{_fmt(payload['holm_gate'].get('higher_sharpe', {}).get('adjusted_p_value'))}`",
        "",
        "## Calibration",
        "",
        f"- Mean completed observations: "
        f"`{_fmt(payload['calibration_summary']['mean_observation_count'])}`",
        f"- Mean raw OOS RMSE: "
        f"`{_fmt(payload['calibration_summary']['mean_raw_oos_rmse'])}`",
        f"- Median raw OOS RMSE: "
        f"`{_fmt(payload['calibration_summary']['median_raw_oos_rmse'])}`",
        "",
        "## Guardrail",
        "",
        "- Point forecasts and ensemble weights are unchanged.",
        "- Only targets completed inside each training window calibrate uncertainty.",
        "- Validation and holdout remain sealed unless every research gate passes.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--risk-free-data", required=True)
    parser.add_argument("--risk-free-provenance", required=True)
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
    parser.add_argument("--forecast-horizon", type=int, default=63)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--max-asset-weight", type=float, default=0.20)
    parser.add_argument("--rebalance-band", type=float, default=0.02)
    parser.add_argument("--max-turnover", type=float, default=0.35)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-block-size", type=int, default=21)
    parser.add_argument(
        "--bootstrap-minimum-probability",
        type=float,
        default=0.95,
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        prices, price_path, price_provenance_path, price_provenance = (
            _load_prices(args)
        )
        (
            risk_free,
            risk_free_path,
            risk_free_provenance_path,
            risk_free_provenance,
        ) = _load_risk_free(args, prices)
        settings = _settings(args)
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.research_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[CANDIDATE],
            settings=settings,
            evaluation_start=prices.index[args.train_window],
            evaluation_end=prices.index[-1],
            universe_manifest_sha256=price_provenance[
                "basket_manifest_sha256"
            ],
            price_file_sha256=price_provenance["price_file_sha256"],
            factor_file_sha256=risk_free_provenance[
                "factor_file_sha256"
            ],
            auxiliary_files={
                "price_provenance": _sha256(
                    price_provenance_path
                ),
                "risk_free_provenance": _sha256(
                    risk_free_provenance_path
                ),
            },
        )
        if split["role"] != "research":
            raise ValueError("Manifest role must be research")

        result = run_portfolio_model_backtest(
            prices,
            models=MODELS,
            train_window=args.train_window,
            rebalance_frequency=args.rebalance_frequency,
            forecast_horizon=args.forecast_horizon,
            transaction_cost_bps=args.transaction_cost_bps,
            max_asset_weight=args.max_asset_weight,
            rebalance_band=args.rebalance_band,
            max_turnover=args.max_turnover,
            include_daily_returns=True,
            risk_free_daily_returns=risk_free,
        )
        deterministic = _deterministic_gate(
            result["summary_by_model"]
        )
        daily_returns = result["daily_returns_by_model"]
        paired = paired_block_bootstrap(
            daily_returns[CANDIDATE],
            daily_returns[BASELINE],
            risk_free_rate=result["settings"]["risk_free_rate"],
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=42,
            risk_free_daily_returns=risk_free,
        )
        probability = paired.get("probability", {})
        holm = holm_bonferroni(
            {
                "higher_return": (
                    None
                    if probability.get("higher_return") is None
                    else 1.0 - probability["higher_return"]
                ),
                "higher_sharpe": (
                    None
                    if probability.get("higher_sharpe") is None
                    else 1.0 - probability["higher_sharpe"]
                ),
            },
            alpha=1.0 - args.bootstrap_minimum_probability,
        )
        statistical_reasons = []
        for objective in ("higher_return", "higher_sharpe"):
            if (
                probability.get(objective) is None
                or probability[objective]
                < args.bootstrap_minimum_probability
            ):
                statistical_reasons.append(
                    f"{objective} probability is below "
                    f"{args.bootstrap_minimum_probability:.0%}."
                )
            if (
                objective not in holm
                or not holm[objective]["significant"]
            ):
                statistical_reasons.append(
                    f"{objective} fails Holm correction."
                )
        statistical = {
            "status": (
                "passed"
                if not statistical_reasons
                else "rejected"
            ),
            "reasons": statistical_reasons,
        }
        calibration = _calibration_summary(result)
        result_for_output = {
            key: value
            for key, value in result.items()
            if key != "rebalance_records"
        }
        promotion_eligible = bool(
            split["promotion_safe"]
            and deterministic["status"] == "passed"
            and statistical["status"] == "passed"
        )
        payload = {
            "research_split": args.research_split,
            "experiment_namespace": args.experiment_namespace,
            "split": {
                **split,
                "file": str(split_path),
                "file_sha256": _sha256(split_path),
            },
            "data": {
                "price_file": str(price_path),
                "price_provenance_file": str(
                    price_provenance_path
                ),
                "risk_free_file": str(risk_free_path),
                "risk_free_provenance_file": str(
                    risk_free_provenance_path
                ),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
                "tickers": list(prices.columns),
            },
            "settings": settings,
            "deterministic_gate": deterministic,
            "paired_bootstrap": paired,
            "holm_gate": holm,
            "statistical_gate": statistical,
            "calibration_summary": calibration,
            "rebalance_record_count": int(
                len(result.get("rebalance_records", []))
            ),
            "promotion_eligible": promotion_eligible,
            "result": result_for_output,
        }
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        report_path = _write_report(payload, output_path)
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
