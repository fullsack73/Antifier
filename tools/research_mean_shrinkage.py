#!/usr/bin/env python3
"""Evaluate a locked expected-return shrinkage candidate."""

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
    bootstrap_improvement_gate,
    holm_bonferroni,
    paired_block_bootstrap,
)
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "james_stein_bl"
BASELINE = "historical_bl"
MODELS = (
    "equal_weight",
    "min_variance",
    "risk_parity",
    BASELINE,
    CANDIDATE,
)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _settings(args):
    return {
        "train_window": int(args.train_window),
        "rebalance_frequency": int(args.rebalance_frequency),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "max_asset_weight": float(args.max_asset_weight),
        "rebalance_band": float(args.rebalance_band),
        "max_turnover": float(args.max_turnover),
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_block_size": int(args.bootstrap_block_size),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
        "risk_free_policy": "fred_dgs3mo_daily_equivalent",
        "candidate_policy": {
            "estimator": "jorion_bayes_stein",
            "shrinkage_target": (
                "global_minimum_variance_expected_return"
            ),
            "shrinkage_intensity": "closed_form_parameter_free",
            "annualization": "arithmetic_daily_mean_times_252",
            "black_litterman": (
                "same_prior_covariance_uncertainty_and_constraints_"
                "as_historical_bl"
            ),
        },
    }


def _load_prices(csv_path, provenance_path):
    prices_path = Path(csv_path).expanduser().resolve()
    provenance_file = Path(provenance_path).expanduser().resolve()
    prices = pd.read_csv(
        prices_path,
        index_col=0,
        parse_dates=True,
    )
    provenance = json.loads(
        provenance_file.read_text(encoding="utf-8")
    )
    if provenance.get("price_file_sha256") != _sha256(prices_path):
        raise ValueError(
            "Price CSV SHA-256 does not match provenance"
        )
    if list(provenance.get("tickers") or []) != list(prices.columns):
        raise ValueError(
            "Price provenance ticker order does not match CSV"
        )
    if not provenance.get("promotion_safe", False):
        raise ValueError("Price provenance is not promotion safe")
    return prices, {
        **provenance,
        "file": str(provenance_file),
        "file_sha256": _sha256(provenance_file),
    }


def _load_risk_free(data_path, provenance_path):
    factor_path = Path(data_path).expanduser().resolve()
    provenance_file = Path(provenance_path).expanduser().resolve()
    provenance = json.loads(
        provenance_file.read_text(encoding="utf-8")
    )
    if provenance.get("factor_file_sha256") != _sha256(factor_path):
        raise ValueError(
            "Risk-free CSV SHA-256 does not match provenance"
        )
    frame = pd.read_csv(
        factor_path,
        index_col=0,
        parse_dates=True,
    )
    if "rf_daily_dgs3mo" not in frame:
        raise ValueError(
            "Risk-free CSV requires rf_daily_dgs3mo"
        )
    risk_free = pd.to_numeric(
        frame["rf_daily_dgs3mo"],
        errors="coerce",
    ).dropna()
    if risk_free.empty:
        raise ValueError("Risk-free CSV has no usable observations")
    return risk_free, {
        **provenance,
        "file": str(provenance_file),
        "file_sha256": _sha256(provenance_file),
    }


def _load_split(
    args,
    prices,
    price_provenance,
    risk_free_provenance,
):
    path = Path(args.split_manifest).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    validated = validate_research_split_run(
        payload,
        split_id=args.research_split,
        experiment_namespace=args.experiment_namespace,
        objectives=[CANDIDATE],
        settings=_settings(args),
        evaluation_start=prices.index[args.train_window],
        evaluation_end=prices.index[-1],
        universe_manifest_sha256=(
            price_provenance["basket_manifest_sha256"]
        ),
        price_file_sha256=price_provenance["price_file_sha256"],
        factor_file_sha256=(
            risk_free_provenance["factor_file_sha256"]
        ),
        auxiliary_files={},
    )
    if validated["role"] != "research":
        raise ValueError(
            "Research runner accepts only a locked research split"
        )
    if not validated["promotion_safe"]:
        raise ValueError("Research split is not locked")
    return {
        **validated,
        "file": str(path),
        "file_sha256": _sha256(path),
    }


def deterministic_gate(summary):
    candidate = summary[CANDIDATE]
    baseline = summary[BASELINE]
    reasons = []
    if (
        candidate["annual_volatility"]
        >= baseline["annual_volatility"]
    ):
        reasons.append(
            "Realized volatility does not improve historical_bl."
        )
    if candidate["max_drawdown"] < baseline["max_drawdown"]:
        reasons.append(
            "Max drawdown is worse than historical_bl."
        )
    if (
        candidate["sharpe"] is None
        or baseline["sharpe"] is None
        or candidate["sharpe"] <= baseline["sharpe"]
    ):
        reasons.append("Sharpe does not improve historical_bl.")
    turnover_limit = max(
        0.50,
        2.0 * float(baseline["avg_controlled_turnover"]),
    )
    if candidate["avg_controlled_turnover"] > turnover_limit:
        reasons.append(
            "Average controlled turnover exceeds the frozen limit."
        )
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "baseline": BASELINE,
        "turnover_limit": float(turnover_limit),
    }


def _mean_estimator_summary(records):
    diagnostics = [
        record.get("mean_estimator")
        for record in records
        if record.get("model") == CANDIDATE
        and isinstance(record.get("mean_estimator"), dict)
    ]
    intensities = np.asarray(
        [
            item["shrinkage_intensity"]
            for item in diagnostics
            if item.get("shrinkage_intensity") is not None
        ],
        dtype=float,
    )
    if len(intensities) == 0:
        return {
            "rebalance_count": 0,
            "mean_shrinkage_intensity": None,
        }
    return {
        "rebalance_count": int(len(intensities)),
        "mean_shrinkage_intensity": float(np.mean(intensities)),
        "minimum_shrinkage_intensity": float(np.min(intensities)),
        "maximum_shrinkage_intensity": float(np.max(intensities)),
        "median_shrinkage_intensity": float(np.median(intensities)),
    }


def _fmt(value):
    return "NA" if value is None else f"{float(value):.4f}"


def _write_report(payload, output_path):
    lines = [
        "# James–Stein Mean Shrinkage Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Candidate: `{CANDIDATE}`",
        f"- Closest baseline: `{BASELINE}`",
        f"- Locked research split: `{payload['split']['locked']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Performance",
        "",
        "| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    summary = payload["result"]["summary_by_model"]
    for model in MODELS:
        metrics = summary[model]
        lines.append(
            "| {model} | {cagr} | {volatility} | {sharpe} | "
            "{drawdown} | {turnover} |".format(
                model=model,
                cagr=_fmt(metrics["cagr"]),
                volatility=_fmt(metrics["annual_volatility"]),
                sharpe=_fmt(metrics["sharpe"]),
                drawdown=_fmt(metrics["max_drawdown"]),
                turnover=_fmt(metrics["avg_controlled_turnover"]),
            )
        )
    probability = payload["paired_bootstrap"].get(
        "probability",
        {},
    )
    estimator = payload["mean_estimator"]
    lines.extend([
        "",
        "## Gate",
        "",
        f"- Deterministic: `{payload['deterministic_gate']['status']}`",
        f"- Statistical: `{payload['statistical_gate']['status']}`",
        f"- Holm significant: `{payload['holm_gate']['significant']}`",
        (
            "- P(lower volatility): "
            f"`{_fmt(probability.get('lower_volatility'))}`"
        ),
        (
            "- P(higher Sharpe): "
            f"`{_fmt(probability.get('higher_sharpe'))}`"
        ),
        (
            "- Mean shrinkage intensity: "
            f"`{_fmt(estimator['mean_shrinkage_intensity'])}`"
        ),
        "",
        "## Decision",
        "",
        (
            "- Freeze candidate for untouched validation."
            if payload["promotion_eligible"]
            else (
                "- Reject candidate; do not open validation or change "
                "the production default."
            )
        ),
        "",
        "The candidate changes only the historical expected-return "
        "estimator. Covariance, Black–Litterman policy, constraints, "
        "execution controls, and costs match the baseline.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--risk-free-data", required=True)
    parser.add_argument("--risk-free-provenance", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=10.0,
    )
    parser.add_argument("--max-asset-weight", type=float, default=0.10)
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
        prices, price_provenance = _load_prices(
            args.csv,
            args.price_provenance,
        )
        risk_free, risk_free_provenance = _load_risk_free(
            args.risk_free_data,
            args.risk_free_provenance,
        )
        split = _load_split(
            args,
            prices,
            price_provenance,
            risk_free_provenance,
        )
        result = run_portfolio_model_backtest(
            prices,
            models=MODELS,
            train_window=args.train_window,
            rebalance_frequency=args.rebalance_frequency,
            forecast_horizon=args.rebalance_frequency,
            transaction_cost_bps=args.transaction_cost_bps,
            max_asset_weight=args.max_asset_weight,
            rebalance_band=args.rebalance_band,
            max_turnover=args.max_turnover,
            include_daily_returns=True,
            risk_free_daily_returns=risk_free,
        )
        deterministic = deterministic_gate(
            result["summary_by_model"]
        )
        daily = result["daily_returns_by_model"]
        bootstrap = paired_block_bootstrap(
            daily[CANDIDATE],
            daily[BASELINE],
            risk_free_rate=result["settings"]["risk_free_rate"],
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=42,
            risk_free_daily_returns=risk_free,
        )
        statistical = bootstrap_improvement_gate(
            bootstrap,
            minimum_probability=args.bootstrap_minimum_probability,
        )
        probabilities = bootstrap.get("probability", {})
        raw_p_value = max(
            1.0 - float(
                probabilities.get("lower_volatility", 0.0)
            ),
            1.0 - float(
                probabilities.get("higher_sharpe", 0.0)
            ),
        )
        holm = holm_bonferroni(
            {CANDIDATE: raw_p_value},
            alpha=0.05,
        )[CANDIDATE]
        gate_passed = bool(
            deterministic["status"] == "passed"
            and statistical["status"] == "passed"
            and holm["significant"]
        )
        payload = {
            "research_split": args.research_split,
            "experiment_namespace": args.experiment_namespace,
            "candidate": CANDIDATE,
            "baseline": BASELINE,
            "promotion_eligible": gate_passed,
            "split": split,
            "settings": _settings(args),
            "data": {
                "price_file": str(
                    Path(args.csv).expanduser().resolve()
                ),
                "start_date": prices.index.min().strftime(
                    "%Y-%m-%d"
                ),
                "end_date": prices.index.max().strftime(
                    "%Y-%m-%d"
                ),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
                "price_provenance": price_provenance,
                "risk_free_provenance": risk_free_provenance,
            },
            "deterministic_gate": deterministic,
            "paired_bootstrap": bootstrap,
            "statistical_gate": statistical,
            "holm_gate": holm,
            "mean_estimator": _mean_estimator_summary(
                result["rebalance_records"]
            ),
            "result": result,
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
