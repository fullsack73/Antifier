#!/usr/bin/env python3
"""Validate frozen trend-filtered risk parity on a locked four-case split."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from portfolio_backtest import run_portfolio_model_backtest  # noqa: E402
from portfolio_risk_models import risk_allocator_case_gate  # noqa: E402
from portfolio_statistics import (  # noqa: E402
    bootstrap_improvement_gate,
    holm_bonferroni,
    paired_block_bootstrap,
)
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "trend_filtered_risk_parity"
BASELINE = "risk_parity"
MODELS = (BASELINE, CANDIDATE)
VALIDATION_CASES = (
    {
        "id": "defensive_consumption_health",
        "tickers": (
            "Food", "Soda", "Beer", "Smoke", "Hshld", "Hlth",
            "MedEq", "Drugs", "Util", "Telcm", "Meals", "Rtail",
        ),
    },
    {
        "id": "industrial_cyclical",
        "tickers": (
            "Agric", "Toys", "Fun", "Books", "Clths", "Chems",
            "Rubbr", "BldMt", "Cnstr", "Steel", "Mach", "ElcEq",
            "Autos", "Aero", "Ships", "Trans",
        ),
    },
    {
        "id": "technology_services",
        "tickers": (
            "PerSv", "BusSv", "Hardw", "Softw", "Chips", "LabEq",
            "Telcm", "MedEq", "ElcEq", "Aero", "Whlsl", "Other",
        ),
    },
    {
        "id": "real_assets_financials",
        "tickers": (
            "Gold", "Mines", "Coal", "Oil", "Util", "Banks",
            "Insur", "RlEst", "Fin", "Paper", "Boxes", "Other",
        ),
    },
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
        "frozen_candidate_policy": {
            "source_split_id": str(args.frozen_from),
            "candidate": CANDIDATE,
            "candidate_specification": "unchanged",
        },
        "candidate_policy": {
            "trend_measure": "trailing_total_return_gt_zero",
            "trend_lookback": 252,
            "inactive_allocation": "historical_risk_free_cash",
            "base_allocator": "inverse_volatility",
        },
        "validation_cases": [
            {
                "id": case["id"],
                "tickers": list(case["tickers"]),
            }
            for case in VALIDATION_CASES
        ],
    }


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_frozen_result(args):
    path = Path(args.frozen_result).expanduser().resolve()
    payload = _load_json(path)
    if payload.get("research_split") != args.frozen_from:
        raise ValueError(
            "Frozen result split does not match --frozen-from"
        )
    if payload.get("candidates") != [CANDIDATE]:
        raise ValueError("Frozen result candidate does not match")
    if not payload.get("promotion_eligible"):
        raise ValueError("Frozen result is not promotion eligible")
    return payload, path, _sha256(path)


def _load_prices(args):
    path = Path(args.csv).expanduser().resolve()
    provenance_path = Path(
        args.price_provenance
    ).expanduser().resolve()
    provenance = _load_json(provenance_path)
    actual = _sha256(path)
    if provenance.get("price_file_sha256") != actual:
        raise ValueError("Price CSV SHA-256 does not match provenance")
    prices = pd.read_csv(path, index_col=0, parse_dates=True)
    if list(provenance.get("tickers") or []) != list(prices.columns):
        raise ValueError("Price provenance ticker order mismatch")
    required = {
        ticker
        for case in VALIDATION_CASES
        for ticker in case["tickers"]
    }
    missing = sorted(required - set(prices.columns))
    if missing:
        raise ValueError(
            "Validation price panel is missing: " + ", ".join(missing)
        )
    return prices, provenance, path, provenance_path


def _load_risk_free(args):
    path = Path(args.risk_free_data).expanduser().resolve()
    provenance_path = Path(
        args.risk_free_provenance
    ).expanduser().resolve()
    provenance = _load_json(provenance_path)
    actual = _sha256(path)
    if provenance.get("factor_file_sha256") != actual:
        raise ValueError(
            "Risk-free CSV SHA-256 does not match provenance"
        )
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    if "rf_daily_dgs3mo" not in frame:
        raise ValueError("Risk-free data requires rf_daily_dgs3mo")
    series = pd.to_numeric(
        frame["rf_daily_dgs3mo"],
        errors="coerce",
    ).dropna()
    if series.empty:
        raise ValueError("Risk-free data contains no usable rows")
    return series, provenance, path, provenance_path


def _run_backtest(prices, risk_free, args):
    return run_portfolio_model_backtest(
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


def _write_report(payload, output_path):
    lines = [
        "# Frozen Trend Risk Parity Validation",
        "",
        f"- Split: `{payload['validation_split']}`",
        f"- Frozen from: `{payload['frozen_from']}`",
        f"- Passed cases: {payload['passed_case_count']} / 4",
        f"- Aggregate gate: `{payload['aggregate_gate']['status']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Cases",
        "",
        "| Case | Candidate vol | Baseline vol | Candidate Sharpe | Baseline Sharpe | Candidate DD | Baseline DD | Gate |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for run in payload["case_runs"]:
        summary = run["result"]["summary_by_model"]
        candidate = summary[CANDIDATE]
        baseline = summary[BASELINE]
        lines.append(
            "| {case} | {candidate_vol:.4f} | {baseline_vol:.4f} | "
            "{candidate_sharpe:.4f} | {baseline_sharpe:.4f} | "
            "{candidate_dd:.4f} | {baseline_dd:.4f} | {gate} |".format(
                case=run["case"]["id"],
                candidate_vol=candidate["annual_volatility"],
                baseline_vol=baseline["annual_volatility"],
                candidate_sharpe=candidate["sharpe"],
                baseline_sharpe=baseline["sharpe"],
                candidate_dd=candidate["max_drawdown"],
                baseline_dd=baseline["max_drawdown"],
                gate=run["gate"]["status"],
            )
        )
    probability = payload["aggregate_bootstrap"]["probability"]
    lines.extend([
        "",
        "## Aggregate",
        "",
        f"- P(lower volatility): `{probability['lower_volatility']:.4f}`",
        f"- P(higher Sharpe): `{probability['higher_sharpe']:.4f}`",
        (
            "- Holm-adjusted p-value: "
            f"`{payload['aggregate_holm']['adjusted_p_value']:.4f}`"
        ),
        "",
        "## Decision",
        "",
        "- All four deterministic cases and the aggregate statistical gate must pass.",
        "- Locked holdout remains sealed unless validation passes.",
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
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--validation-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--frozen-from", required=True)
    parser.add_argument("--frozen-result", required=True)
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
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
        frozen, frozen_path, frozen_sha = _load_frozen_result(args)
        prices, price_provenance, price_path, price_provenance_path = (
            _load_prices(args)
        )
        risk_free, risk_free_provenance, risk_free_path, rf_provenance_path = (
            _load_risk_free(args)
        )
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.validation_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[CANDIDATE],
            settings=_settings(args),
            evaluation_start=prices.index[args.train_window],
            evaluation_end=prices.index[-1],
            universe_manifest_sha256=price_provenance.get(
                "basket_manifest_sha256"
            ),
            price_file_sha256=price_provenance.get(
                "price_file_sha256"
            ),
            factor_file_sha256=risk_free_provenance.get(
                "factor_file_sha256"
            ),
            auxiliary_files={"frozen_result": frozen_sha},
        )
        if split["role"] != "validation":
            raise ValueError("Validation manifest role must be validation")

        full_result = _run_backtest(prices, risk_free, args)
        full_gate = risk_allocator_case_gate(
            full_result["summary_by_model"],
            candidate_name=CANDIDATE,
            baseline_name=BASELINE,
        )
        bootstrap = paired_block_bootstrap(
            full_result["daily_returns_by_model"][CANDIDATE],
            full_result["daily_returns_by_model"][BASELINE],
            risk_free_rate=full_result["settings"]["risk_free_rate"],
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=42,
            risk_free_daily_returns=risk_free,
        )
        statistical_gate = bootstrap_improvement_gate(
            bootstrap,
            minimum_probability=args.bootstrap_minimum_probability,
        )
        raw_p_value = max(
            1.0 - bootstrap["probability"]["lower_volatility"],
            1.0 - bootstrap["probability"]["higher_sharpe"],
        )
        holm = holm_bonferroni(
            {CANDIDATE: raw_p_value},
            alpha=0.05,
        )[CANDIDATE]
        aggregate_reasons = (
            list(full_gate["reasons"])
            + list(statistical_gate["reasons"])
        )
        if not holm["significant"]:
            aggregate_reasons.append(
                "Improvement is not significant after Holm correction."
            )
        aggregate_gate = {
            "status": (
                "passed" if not aggregate_reasons else "rejected"
            ),
            "reasons": aggregate_reasons,
        }

        case_runs = []
        for case in VALIDATION_CASES:
            case_prices = prices.loc[:, list(case["tickers"])]
            result = _run_backtest(case_prices, risk_free, args)
            gate = risk_allocator_case_gate(
                result["summary_by_model"],
                candidate_name=CANDIDATE,
                baseline_name=BASELINE,
            )
            result.pop("daily_returns_by_model", None)
            case_runs.append({
                "case": {
                    "id": case["id"],
                    "tickers": list(case["tickers"]),
                },
                "gate": gate,
                "result": result,
            })

        passed_case_count = sum(
            run["gate"]["status"] == "passed"
            for run in case_runs
        )
        validation_passed = bool(
            passed_case_count == len(VALIDATION_CASES)
            and aggregate_gate["status"] == "passed"
        )
        payload = {
            "validation_split": args.validation_split,
            "experiment_namespace": args.experiment_namespace,
            "frozen_from": args.frozen_from,
            "frozen_result": {
                "file": str(frozen_path),
                "sha256": frozen_sha,
                "promotion_eligible": frozen["promotion_eligible"],
            },
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
                    rf_provenance_path
                ),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
            },
            "settings": _settings(args),
            "candidate": CANDIDATE,
            "baseline": BASELINE,
            "passed_case_count": int(passed_case_count),
            "case_count": int(len(VALIDATION_CASES)),
            "aggregate_gate": aggregate_gate,
            "aggregate_statistical_gate": statistical_gate,
            "aggregate_holm": holm,
            "aggregate_bootstrap": bootstrap,
            "case_runs": case_runs,
            "full_result": full_result,
            "validation_passed": validation_passed,
            "promotion_eligible": bool(
                validation_passed
                and split.get("promotion_safe", False)
                and price_provenance.get("promotion_safe", False)
            ),
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
