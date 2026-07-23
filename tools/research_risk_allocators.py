#!/usr/bin/env python3
"""Compare robust risk allocators on a research-only split."""

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

from portfolio_backtest import (  # noqa: E402
    fetch_backtest_price_data,
    run_portfolio_model_backtest,
)
from portfolio_risk_models import (  # noqa: E402
    ONLINE_ALLOCATOR_ENSEMBLE_POLICY,
)
from portfolio_statistics import (  # noqa: E402
    bootstrap_improvement_gate,
    holm_bonferroni,
    paired_block_bootstrap,
)
from research_split import validate_research_split_run  # noqa: E402


RISK_RESEARCH_MODELS = (
    "equal_weight",
    "min_variance",
    "risk_parity",
    "momentum_6m",
    "robust_min_variance",
    "equal_risk_contribution",
    "hierarchical_risk_parity",
    "regime_minimum_variance",
    "minimum_cvar",
    "cross_validated_min_variance",
    "forecast_ensemble_min_variance",
    "stability_regularized_min_variance",
    "nested_blended_min_variance",
    "resampled_min_variance",
    "scenario_robust_min_variance",
    "volatility_targeted_min_variance",
    "random_matrix_minimum_variance",
    "risk_managed_momentum",
    "dual_horizon_momentum",
    "trend_filtered_minimum_variance",
    "trend_filtered_risk_parity",
    "maximum_diversification",
    "online_allocator_ensemble",
    "historical_bl",
    "hac_historical_bl",
)
RISK_CANDIDATES = (
    "robust_min_variance",
    "equal_risk_contribution",
    "hierarchical_risk_parity",
    "regime_minimum_variance",
    "minimum_cvar",
    "cross_validated_min_variance",
    "forecast_ensemble_min_variance",
    "stability_regularized_min_variance",
    "nested_blended_min_variance",
    "resampled_min_variance",
    "scenario_robust_min_variance",
    "volatility_targeted_min_variance",
    "random_matrix_minimum_variance",
    "risk_managed_momentum",
    "dual_horizon_momentum",
    "trend_filtered_minimum_variance",
    "trend_filtered_risk_parity",
    "maximum_diversification",
    "online_allocator_ensemble",
    "hac_historical_bl",
)
RESERVED_SPLITS = {
    "validation",
    "candidate",
    "standard",
    "holdout",
    "locked_holdout",
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _research_settings(args):
    settings = {
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
    }
    if args.risk_free_data:
        settings["risk_free_policy"] = (
            "fama_french_daily_one_month_tbill"
            if args.risk_free_column == "rf_daily"
            else "fred_dgs3mo_daily_equivalent"
        )
    if args.replication_of:
        settings["replication_policy"] = {
            "prior_split_id": str(args.replication_of),
            "candidate_specification": "unchanged",
            "prior_requirement": "deterministic_gate_passed",
            "replication_requirement": (
                "deterministic_statistical_and_holm_gates_passed"
            ),
        }
    if "random_matrix_minimum_variance" in args.candidates:
        settings["random_matrix_policy"] = {
            "correlation": "marchenko_pastur_noise_eigenvalue_mean",
            "variance": "ledoit_wolf_diagonal",
        }
    if "dual_horizon_momentum" in args.candidates:
        settings["dual_horizon_momentum_policy"] = {
            "component_weights": {
                "momentum_6m": 0.50,
                "momentum_12_1": 0.50,
            },
            "lookbacks": {
                "momentum_6m": 126,
                "momentum_12_1": 252,
                "momentum_12_1_skip": 21,
            },
        }
    if "trend_filtered_minimum_variance" in args.candidates:
        settings["trend_filtered_minimum_variance_policy"] = {
            "trend_measure": "trailing_total_return_gt_zero",
            "trend_lookback": 252,
            "inactive_allocation": "historical_risk_free_cash",
            "covariance": "ledoit_wolf",
        }
    if "trend_filtered_risk_parity" in args.candidates:
        settings["trend_filtered_risk_parity_policy"] = {
            "trend_measure": "trailing_total_return_gt_zero",
            "trend_lookback": 252,
            "inactive_allocation": "historical_risk_free_cash",
            "base_allocator": "inverse_volatility",
        }
    if "maximum_diversification" in args.candidates:
        settings["maximum_diversification_policy"] = {
            "covariance": "ledoit_wolf",
            "objective": (
                "weighted_standalone_volatility_over_portfolio_volatility"
            ),
        }
    if "online_allocator_ensemble" in args.candidates:
        settings["online_allocator_ensemble_policy"] = {
            **ONLINE_ALLOCATOR_ENSEMBLE_POLICY,
            "experts": list(
                ONLINE_ALLOCATOR_ENSEMBLE_POLICY["experts"]
            ),
        }
    if "hac_historical_bl" in args.candidates:
        settings["hac_historical_policy"] = {
            "point_estimate": "historical_cagr",
            "uncertainty": (
                "annualized_newey_west_hac_mean_standard_error"
            ),
            "lag_rule": "floor(4*(T/100)^(2/9))",
            "black_litterman": (
                "same_prior_covariance_and_constraints_as_historical_bl"
            ),
        }
    return settings


def _load_prices(args):
    if args.csv:
        prices = pd.read_csv(args.csv, index_col=0, parse_dates=True)
        if args.tickers:
            prices = prices.loc[:, args.tickers]
        return prices
    if not args.tickers:
        raise ValueError("Provide --csv or --tickers")
    return fetch_backtest_price_data(
        tickers=args.tickers,
        start_date=args.start,
        end_date=args.end,
    )


def _load_price_provenance(args, prices):
    if not args.price_provenance:
        if args.require_locked_split:
            raise ValueError(
                "--require-locked-split requires --price-provenance"
            )
        return {
            "source": "unverified runtime data",
            "promotion_safe": False,
        }
    if not args.csv:
        raise ValueError("--price-provenance requires --csv")
    path = Path(args.price_provenance).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual = _sha256(args.csv)
    if payload.get("price_file_sha256") != actual:
        raise ValueError(
            "Price CSV SHA-256 does not match price provenance"
        )
    if list(payload.get("tickers") or []) != list(prices.columns):
        raise ValueError(
            "Price provenance ticker order does not match price CSV"
        )
    return {
        **payload,
        "file": str(path),
        "file_sha256": _sha256(path),
    }


def _load_split_manifest(args, prices, price_provenance, candidates):
    if not args.split_manifest:
        if args.require_locked_split:
            raise ValueError(
                "--require-locked-split requires --split-manifest"
            )
        return {
            "source": "unlocked CLI arguments",
            "promotion_safe": False,
        }
    path = Path(args.split_manifest).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    validated = validate_research_split_run(
        payload,
        split_id=args.research_split,
        experiment_namespace=args.experiment_namespace,
        objectives=candidates,
        settings=_research_settings(args),
        evaluation_start=prices.index[args.train_window],
        evaluation_end=prices.index[-1],
        universe_manifest_sha256=(
            price_provenance.get("universe_manifest_sha256")
            or price_provenance.get("basket_manifest_sha256")
        ),
        price_file_sha256=price_provenance.get("price_file_sha256"),
        factor_file_sha256=args.risk_free_file_sha256,
        auxiliary_files=args.auxiliary_files,
    )
    return {
        **validated,
        "file": str(path),
        "file_sha256": _sha256(path),
    }


def _load_replication_auxiliary_files(args, candidates):
    if bool(args.replication_of) != bool(args.prior_result):
        raise ValueError(
            "--replication-of and --prior-result must be used together"
        )
    if not args.replication_of:
        return {}

    path = Path(args.prior_result).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("research_split") != args.replication_of:
        raise ValueError(
            "Prior result split does not match --replication-of"
        )
    if list(payload.get("candidates") or []) != list(candidates):
        raise ValueError(
            "Prior result candidates do not match replication candidates"
        )
    deterministic = payload.get("deterministic_risk_gates") or {}
    failed = [
        candidate
        for candidate in candidates
        if deterministic.get(candidate, {}).get("status") != "passed"
    ]
    if failed:
        raise ValueError(
            "Replication requires prior deterministic gate pass: "
            + ", ".join(failed)
        )
    return {"prior_result": _sha256(path)}


def _load_risk_free_data(args):
    if bool(args.risk_free_data) != bool(args.risk_free_provenance):
        raise ValueError(
            "--risk-free-data and --risk-free-provenance must be used "
            "together"
        )
    if not args.risk_free_data:
        args.risk_free_file_sha256 = None
        return None, None
    data_path = Path(args.risk_free_data).expanduser().resolve()
    provenance_path = Path(
        args.risk_free_provenance
    ).expanduser().resolve()
    provenance = json.loads(
        provenance_path.read_text(encoding="utf-8")
    )
    actual = _sha256(data_path)
    if provenance.get("factor_file_sha256") != actual:
        raise ValueError(
            "Risk-free data SHA-256 does not match provenance"
        )
    frame = pd.read_csv(data_path, index_col=0, parse_dates=True)
    if args.risk_free_column not in frame:
        raise ValueError(
            f"Risk-free data requires {args.risk_free_column}"
        )
    series = pd.to_numeric(
        frame[args.risk_free_column],
        errors="coerce",
    ).dropna()
    if series.empty:
        raise ValueError("Risk-free data contains no usable observations")
    args.risk_free_file_sha256 = actual
    return series, {
        **provenance,
        "file": str(provenance_path),
        "file_sha256": _sha256(provenance_path),
    }


def _risk_gate(summary, candidate_name):
    candidate = summary[candidate_name]
    equal = summary["equal_weight"]
    inverse_vol = summary["risk_parity"]
    baseline_name = (
        "momentum_6m"
        if candidate_name in {
            "risk_managed_momentum",
            "dual_horizon_momentum",
            "online_allocator_ensemble",
        }
        else (
            "historical_bl"
            if candidate_name == "hac_historical_bl"
            else (
            "min_variance"
            if candidate_name in {
                "robust_min_variance",
                "regime_minimum_variance",
                "minimum_cvar",
                "cross_validated_min_variance",
                "forecast_ensemble_min_variance",
                "stability_regularized_min_variance",
                "nested_blended_min_variance",
                "resampled_min_variance",
                "scenario_robust_min_variance",
                "volatility_targeted_min_variance",
                "random_matrix_minimum_variance",
                "trend_filtered_minimum_variance",
            }
            else "risk_parity"
            )
        )
    )
    baseline = summary[baseline_name]
    reasons = []
    if candidate_name == "online_allocator_ensemble":
        expert_sharpes = {
            name: summary[name].get("sharpe")
            for name in ONLINE_ALLOCATOR_ENSEMBLE_POLICY["experts"]
        }
        valid_expert_sharpes = [
            float(value)
            for value in expert_sharpes.values()
            if value is not None
        ]
        if (
            candidate.get("sharpe") is None
            or not valid_expert_sharpes
            or float(candidate["sharpe"])
            <= max(valid_expert_sharpes)
        ):
            reasons.append(
                "Sharpe does not exceed every component expert."
            )
    if candidate["annual_volatility"] >= baseline["annual_volatility"]:
        reasons.append(
            f"Realized volatility does not improve {baseline_name}."
        )
    if candidate["max_drawdown"] < baseline["max_drawdown"]:
        reasons.append(f"Max drawdown is worse than {baseline_name}.")
    if (
        candidate["sharpe"] is None
        or baseline["sharpe"] is None
        or candidate["sharpe"] <= baseline["sharpe"]
    ):
        reasons.append(f"Sharpe does not improve {baseline_name}.")
    if (
        candidate["annual_volatility"] > inverse_vol["annual_volatility"]
        and (
            candidate["sharpe"] is None
            or inverse_vol["sharpe"] is None
            or candidate["sharpe"] <= inverse_vol["sharpe"]
        )
    ):
        reasons.append("Risk/return does not improve inverse-vol baseline.")
    if candidate["avg_controlled_turnover"] > 0.50:
        reasons.append("Average controlled turnover exceeds 50%.")
    if (
        candidate_name == "minimum_cvar"
        and (
            candidate.get("daily_cvar_95") is None
            or baseline.get("daily_cvar_95") is None
            or candidate["daily_cvar_95"] >= baseline["daily_cvar_95"]
        )
    ):
        reasons.append(f"Daily CVaR does not improve {baseline_name}.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "baseline": baseline_name,
    }


def _fmt(value):
    return "NA" if value is None else f"{float(value):.4f}"


def _write_report(payload, output_path):
    lines = [
        "# Risk Allocator Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Rows: {payload['data']['row_count']}",
        f"- Tickers: {payload['data']['ticker_count']}",
        f"- Data promotion safe: `{payload['data_promotion_safe']}`",
        f"- Split locked: `{payload['split']['promotion_safe']}`",
        f"- Risk gate passed: `{payload['risk_gate_passed']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Performance",
        "",
        "| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    summary = payload["result"]["summary_by_model"]
    for model in payload["models"]:
        metrics = summary[model]
        gate = payload["risk_gates"].get(model, {})
        bootstrap = payload["paired_bootstrap"].get(model, {})
        probability = bootstrap.get("probability", {})
        lines.append(
            "| {model} | {cagr} | {volatility} | {sharpe} | {sortino} | "
            "{drawdown} | {cvar} | {exposure} | {turnover} | {risk_mae} | "
            "{lower_volatility} | {higher_sharpe} | {gate} |".format(
                model=model,
                cagr=_fmt(metrics["cagr"]),
                volatility=_fmt(metrics["annual_volatility"]),
                sharpe=_fmt(metrics["sharpe"]),
                sortino=_fmt(metrics["sortino"]),
                drawdown=_fmt(metrics["max_drawdown"]),
                cvar=_fmt(metrics["daily_cvar_95"]),
                exposure=_fmt(metrics.get("avg_risky_exposure", 1.0)),
                turnover=_fmt(metrics["avg_controlled_turnover"]),
                risk_mae=_fmt(metrics["risk_forecast_mae"]),
                lower_volatility=_fmt(
                    probability.get("lower_volatility")
                ),
                higher_sharpe=_fmt(
                    probability.get("higher_sharpe")
                ),
                gate=gate.get("status", "baseline"),
            )
        )
    lines.extend([
        "",
        "## Guardrail",
        "",
        "- Research split only; no default or promotion change.",
        "- A risk candidate must improve its closest baseline and survive the inverse-vol guard.",
        "- Freeze a candidate before any validation run.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv")
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--price-provenance")
    parser.add_argument("--risk-free-data")
    parser.add_argument("--risk-free-provenance")
    parser.add_argument(
        "--risk-free-column",
        choices=("rf_daily_dgs3mo", "rf_daily"),
        default="rf_daily_dgs3mo",
    )
    parser.add_argument("--split-manifest")
    parser.add_argument("--replication-of")
    parser.add_argument("--prior-result")
    parser.add_argument("--require-locked-split", action="store_true")
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
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
    parser.add_argument(
        "--candidates",
        nargs="+",
        choices=RISK_CANDIDATES,
        default=list(RISK_CANDIDATES),
        help="Candidate subset; required closest baselines are added",
    )
    args = parser.parse_args(argv)

    try:
        if args.research_split.strip().lower() in RESERVED_SPLITS:
            raise ValueError(
                "Reserved validation/holdout split cannot be used for research"
            )
        prices = _load_prices(args)
        risk_free_daily, risk_free_provenance = _load_risk_free_data(args)
        candidates = list(dict.fromkeys(args.candidates))
        args.auxiliary_files = _load_replication_auxiliary_files(
            args,
            candidates,
        )
        nested_candidates = {
            "forecast_ensemble_min_variance",
            "nested_blended_min_variance",
        }
        if (
            nested_candidates.intersection(candidates)
            and args.train_window < 315
        ):
            raise ValueError(
                "nested covariance/weight candidates require --train-window "
                "at least 315 for a 252/63 completed inner OOS fold"
            )
        price_provenance = _load_price_provenance(args, prices)
        split_manifest = _load_split_manifest(
            args,
            prices,
            price_provenance,
            candidates,
        )
        models = list(dict.fromkeys(
            (
                "equal_weight",
                "min_variance",
                "risk_parity",
                "momentum_6m",
                *(
                    ("historical_bl",)
                    if "hac_historical_bl" in candidates
                    else ()
                ),
                *candidates,
            )
        ))
        result = run_portfolio_model_backtest(
            prices,
            models=models,
            train_window=args.train_window,
            rebalance_frequency=args.rebalance_frequency,
            forecast_horizon=args.rebalance_frequency,
            transaction_cost_bps=args.transaction_cost_bps,
            max_asset_weight=args.max_asset_weight,
            rebalance_band=args.rebalance_band,
            max_turnover=args.max_turnover,
            include_daily_returns=True,
            risk_free_daily_returns=risk_free_daily,
        )
        deterministic_gates = {
            candidate: _risk_gate(result["summary_by_model"], candidate)
            for candidate in candidates
        }
        daily_returns = result["daily_returns_by_model"]
        paired_bootstrap = {}
        statistical_gates = {}
        gates = {}
        for index, candidate in enumerate(candidates):
            baseline = deterministic_gates[candidate]["baseline"]
            bootstrap = paired_block_bootstrap(
                daily_returns[candidate],
                daily_returns[baseline],
                risk_free_rate=result["settings"]["risk_free_rate"],
                block_size=args.bootstrap_block_size,
                samples=args.bootstrap_samples,
                seed=42 + index,
                risk_free_daily_returns=risk_free_daily,
            )
            statistical_gate = bootstrap_improvement_gate(
                bootstrap,
                minimum_probability=args.bootstrap_minimum_probability,
            )
            paired_bootstrap[candidate] = bootstrap
            statistical_gates[candidate] = statistical_gate
            reasons = (
                list(deterministic_gates[candidate]["reasons"])
                + list(statistical_gate["reasons"])
            )
            gates[candidate] = {
                **deterministic_gates[candidate],
                "status": "passed" if not reasons else "rejected",
                "reasons": reasons,
            }
        familywise = holm_bonferroni(
            {
                candidate: max(
                    1.0
                    - paired_bootstrap[candidate]["probability"][
                        "lower_volatility"
                    ],
                    1.0
                    - paired_bootstrap[candidate]["probability"][
                        "higher_sharpe"
                    ],
                )
                for candidate in candidates
                if paired_bootstrap[candidate].get("status") == "ok"
                and paired_bootstrap[candidate]["probability"].get(
                    "higher_sharpe"
                ) is not None
            },
            alpha=0.05,
        )
        for candidate in candidates:
            familywise_result = familywise.get(candidate)
            if (
                familywise_result is None
                or not familywise_result["significant"]
            ):
                gates[candidate]["status"] = "rejected"
                gates[candidate]["reasons"].append(
                    "Improvement is not significant after Holm correction."
                )
        risk_gate_passed = any(
            gate["status"] == "passed" for gate in gates.values()
        )
        data_promotion_safe = bool(
            price_provenance.get("promotion_safe", False)
        )
        payload = {
            "research_split": args.research_split,
            "experiment_namespace": args.experiment_namespace,
            "data_promotion_safe": data_promotion_safe,
            "risk_gate_passed": risk_gate_passed,
            "promotion_eligible": bool(
                data_promotion_safe
                and split_manifest.get("promotion_safe", False)
                and risk_gate_passed
            ),
            "split": split_manifest,
            "data": {
                "source": (
                    str(Path(args.csv).expanduser().resolve())
                    if args.csv
                    else "yfinance"
                ),
                "start_date": prices.index.min().strftime("%Y-%m-%d"),
                "end_date": prices.index.max().strftime("%Y-%m-%d"),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
                "tickers": list(prices.columns),
                "provenance": price_provenance,
                "risk_free_provenance": risk_free_provenance,
            },
            "settings": _research_settings(args),
            "models": models,
            "candidates": candidates,
            "risk_gates": gates,
            "deterministic_risk_gates": deterministic_gates,
            "statistical_risk_gates": statistical_gates,
            "paired_bootstrap": paired_bootstrap,
            "familywise_statistical_gate": familywise,
            "result": result,
        }
        output_path = Path(args.output)
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
