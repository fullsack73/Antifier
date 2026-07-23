#!/usr/bin/env python3
"""Evaluate a risk-only allocator as a default candidate."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
TOOLS = ROOT / "tools"
for path in (BACKEND, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from portfolio_backtest import run_portfolio_model_backtest  # noqa: E402
from portfolio_statistics import (  # noqa: E402
    holm_bonferroni,
    paired_block_bootstrap,
)
from research_lightweight_uncertainty import (  # noqa: E402
    _fmt,
    _load_json,
    _load_prices,
    _load_risk_free,
    _sha256,
)
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "min_variance"
STATISTICAL_BASELINES = (
    "lightweight_bl",
    "risk_parity",
)
GUARD_BASELINES = (
    "equal_weight",
    "historical_bl",
)
MODELS = (
    *GUARD_BASELINES,
    *STATISTICAL_BASELINES,
    CANDIDATE,
)
CANDIDATE_POLICIES = {
    "min_variance": {
        "objective": "long_only_minimum_variance",
        "covariance": "ledoit_wolf_constant_variance",
        "expected_returns": "unused",
        "forecast_model": "unused",
    },
    "nested_clustered_minimum_variance": {
        "objective": (
            "long_only_nested_clustered_minimum_variance"
        ),
        "covariance": "ledoit_wolf_constant_variance",
        "clustering": "average_linkage_correlation_distance",
        "cluster_selection": (
            "maximum_training_silhouette_2_to_min_10_n_minus_1"
        ),
        "intra_cluster_allocator": "minimum_variance",
        "inter_cluster_allocator": "minimum_variance",
        "expected_returns": "unused",
        "forecast_model": "unused",
    },
    "constant_correlation_minimum_variance": {
        "objective": "long_only_minimum_variance",
        "covariance": "ledoit_wolf_constant_correlation",
        "shrinkage_target": "constant_correlation",
        "expected_returns": "unused",
        "forecast_model": "unused",
    },
}


def _settings(
    args,
    candidate=CANDIDATE,
    statistical_baselines=STATISTICAL_BASELINES,
    guard_baselines=GUARD_BASELINES,
    models=MODELS,
):
    settings = {
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
        "candidate": candidate,
        "statistical_baselines": list(statistical_baselines),
        "guard_baselines": list(guard_baselines),
        "models": list(models),
        "candidate_policy": CANDIDATE_POLICIES[candidate],
    }
    if getattr(args, "replication_of", None):
        settings["replication_policy"] = {
            "prior_split_id": str(args.replication_of),
            "candidate_specification": "unchanged",
            "prior_requirement": "deterministic_gate_passed",
            "replication_requirement": (
                "deterministic_statistical_and_holm_gates_passed"
            ),
        }
    return settings


def _deterministic_gate(
    summary,
    candidate_name=CANDIDATE,
    statistical_baselines=STATISTICAL_BASELINES,
    guard_baselines=GUARD_BASELINES,
):
    candidate = summary[candidate_name]
    reasons = []
    for baseline in (
        *statistical_baselines,
        *guard_baselines,
    ):
        comparison = summary[baseline]
        if (
            candidate["annual_volatility"]
            >= comparison["annual_volatility"]
        ):
            reasons.append(
                f"Volatility does not improve {baseline}."
            )
        if (
            candidate["sharpe"] is None
            or comparison["sharpe"] is None
            or candidate["sharpe"] <= comparison["sharpe"]
        ):
            reasons.append(f"Sharpe does not improve {baseline}.")
        if candidate["max_drawdown"] < comparison["max_drawdown"]:
            reasons.append(
                f"Max drawdown is worse than {baseline}."
            )
    if candidate["avg_controlled_turnover"] > 0.50:
        reasons.append("Average controlled turnover exceeds 50%.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }


def _statistical_gate(
    result,
    risk_free,
    args,
    candidate=CANDIDATE,
    statistical_baselines=STATISTICAL_BASELINES,
):
    paired = {}
    hypotheses = {}
    for index, baseline in enumerate(statistical_baselines):
        comparison = paired_block_bootstrap(
            result["daily_returns_by_model"][candidate],
            result["daily_returns_by_model"][baseline],
            risk_free_rate=result["settings"]["risk_free_rate"],
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=81 + index,
            risk_free_daily_returns=risk_free,
        )
        paired[baseline] = comparison
        probability = comparison.get("probability", {})
        hypotheses[
            f"{baseline}:lower_volatility"
        ] = probability.get("lower_volatility")
        hypotheses[
            f"{baseline}:higher_sharpe"
        ] = probability.get("higher_sharpe")

    reasons = []
    p_values = {
        name: (
            None if probability is None else 1.0 - probability
        )
        for name, probability in hypotheses.items()
    }
    for name, probability in hypotheses.items():
        if (
            probability is None
            or probability < args.bootstrap_minimum_probability
        ):
            reasons.append(
                f"{name} probability is below "
                f"{args.bootstrap_minimum_probability:.0%}."
            )
    holm = holm_bonferroni(
        p_values,
        alpha=1.0 - args.bootstrap_minimum_probability,
    )
    for name in hypotheses:
        if name not in holm or not holm[name]["significant"]:
            reasons.append(f"{name} fails Holm correction.")
    return paired, holm, {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "hypothesis_probabilities": hypotheses,
    }


def _write_report(
    payload,
    output_path,
    models=MODELS,
    statistical_baselines=STATISTICAL_BASELINES,
):
    summary = payload["result"]["summary_by_model"]
    candidate = payload["settings"]["candidate"]
    titles = {
        "min_variance": "Plain Minimum-Variance Promotion Research",
        "nested_clustered_minimum_variance": (
            "Nested Clustered Minimum-Variance Promotion Research"
        ),
        "constant_correlation_minimum_variance": (
            "Constant-Correlation Minimum-Variance Promotion Research"
        ),
    }
    title = titles[candidate]
    lines = [
        f"# {title}",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Gate: `{payload['promotion_gate']['status']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Portfolio",
        "",
        "| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in models:
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
    for baseline in statistical_baselines:
        probability = payload["paired_bootstrap"][baseline].get(
            "probability",
            {},
        )
        lines.extend([
            "",
            f"## Paired vs {baseline}",
            "",
            f"- P(lower volatility): "
            f"`{_fmt(probability.get('lower_volatility'))}`",
            f"- P(higher Sharpe): "
            f"`{_fmt(probability.get('higher_sharpe'))}`",
        ])
    lines.extend([
        "",
        "## Guardrail",
        "",
        "- Candidate uses no return forecast or expected-return model.",
        "- Configured guard baselines are deterministic checks.",
        "- Validation remains sealed unless deterministic and "
        f"{2 * len(statistical_baselines)}-hypothesis Holm gates pass.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return report_path


def _candidate_risk_diagnostics(result, candidate):
    diagnostics = [
        record["risk_model"]
        for record in result.get("rebalance_records", [])
        if (
            record.get("model") == candidate
            and isinstance(record.get("risk_model"), dict)
        )
    ]
    if not diagnostics:
        return None
    cluster_counts = [
        int(item["cluster_count"])
        for item in diagnostics
        if item.get("cluster_count") is not None
    ]
    selected_silhouettes = []
    for item in diagnostics:
        scores = item.get("silhouette_scores", {})
        requested = item.get(
            "requested_cluster_count",
            item.get("cluster_count"),
        )
        score = scores.get(str(requested))
        if score is not None:
            selected_silhouettes.append(float(score))
    distribution = {
        str(cluster_count): int(cluster_counts.count(cluster_count))
        for cluster_count in sorted(set(cluster_counts))
    }
    optimizer_success = [
        bool(item.get("optimizer_success"))
        for item in diagnostics
    ]
    fallback = [
        bool(item.get("fallback"))
        for item in diagnostics
    ]
    cap_distances = [
        float(item["cap_projection_l1_distance"])
        for item in diagnostics
        if item.get("cap_projection_l1_distance") is not None
    ]
    pre_cap_maxima = [
        float(item["pre_cap_maximum_weight"])
        for item in diagnostics
        if item.get("pre_cap_maximum_weight") is not None
    ]
    shrinkage_intensities = [
        float(item["shrinkage_intensity"])
        for item in diagnostics
        if item.get("shrinkage_intensity") is not None
    ]
    methods = {
        method: int(
            sum(item.get("method") == method for item in diagnostics)
        )
        for method in sorted({
            item.get("method")
            for item in diagnostics
            if item.get("method")
        })
    }
    return {
        "rebalance_count": int(len(diagnostics)),
        "method_distribution": methods,
        "cluster_count_distribution": distribution,
        "mean_cluster_count": (
            None
            if not cluster_counts
            else float(sum(cluster_counts) / len(cluster_counts))
        ),
        "mean_selected_silhouette": (
            None
            if not selected_silhouettes
            else float(
                sum(selected_silhouettes)
                / len(selected_silhouettes)
            )
        ),
        "optimizer_success_rate": float(
            sum(optimizer_success) / len(optimizer_success)
        ),
        "fallback_rate": float(sum(fallback) / len(fallback)),
        "mean_pre_cap_maximum_weight": (
            None
            if not pre_cap_maxima
            else float(sum(pre_cap_maxima) / len(pre_cap_maxima))
        ),
        "mean_cap_projection_l1_distance": (
            None
            if not cap_distances
            else float(sum(cap_distances) / len(cap_distances))
        ),
        "mean_shrinkage_intensity": (
            None
            if not shrinkage_intensities
            else float(
                sum(shrinkage_intensities)
                / len(shrinkage_intensities)
            )
        ),
        "minimum_shrinkage_intensity": (
            None
            if not shrinkage_intensities
            else float(min(shrinkage_intensities))
        ),
        "maximum_shrinkage_intensity": (
            None
            if not shrinkage_intensities
            else float(max(shrinkage_intensities))
        ),
        "first_clusters": diagnostics[0].get("clusters"),
        "last_clusters": diagnostics[-1].get("clusters"),
    }


def _load_replication(args, candidate):
    if bool(args.replication_of) != bool(args.prior_result):
        raise ValueError(
            "--replication-of and --prior-result must be used together"
        )
    if not args.replication_of:
        return None, {}

    path = Path(args.prior_result).expanduser().resolve()
    prior = _load_json(path)
    if prior.get("research_split") != args.replication_of:
        raise ValueError(
            "Prior result split does not match --replication-of"
        )
    prior_settings = prior.get("settings") or {}
    if prior_settings.get("candidate") != candidate:
        raise ValueError("Prior result candidate does not match")
    if prior_settings.get("candidate_policy") != CANDIDATE_POLICIES[
        candidate
    ]:
        raise ValueError(
            "Prior result candidate policy does not match unchanged policy"
        )
    prior_gate = prior.get("promotion_gate") or {}
    if (
        (prior_gate.get("deterministic") or {}).get("status")
        != "passed"
    ):
        raise ValueError(
            "Replication requires prior deterministic gate pass"
        )
    digest = _sha256(path)
    return {
        "prior_split_id": args.replication_of,
        "prior_result_file": str(path),
        "prior_result_sha256": digest,
        "candidate_specification": "unchanged",
        "prior_deterministic_gate": "passed",
    }, {"prior_result": digest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--risk-free-data", required=True)
    parser.add_argument("--risk-free-provenance", required=True)
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--replication-of")
    parser.add_argument("--prior-result")
    parser.add_argument(
        "--candidate",
        choices=tuple(CANDIDATE_POLICIES),
        default=CANDIDATE,
    )
    parser.add_argument(
        "--statistical-baselines",
        nargs="+",
        default=list(STATISTICAL_BASELINES),
    )
    parser.add_argument(
        "--guard-baselines",
        nargs="+",
        default=list(GUARD_BASELINES),
    )
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
    parser.add_argument("--forecast-horizon", type=int, default=63)
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=10.0,
    )
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
        candidate = args.candidate
        statistical_baselines = tuple(args.statistical_baselines)
        guard_baselines = tuple(args.guard_baselines)
        if candidate in (*statistical_baselines, *guard_baselines):
            raise ValueError("Candidate cannot also be a baseline")
        if len(set((*statistical_baselines, *guard_baselines))) != (
            len(statistical_baselines) + len(guard_baselines)
        ):
            raise ValueError("Baseline model names must be unique")
        models = (
            *guard_baselines,
            *statistical_baselines,
            candidate,
        )
        replication, replication_auxiliary = _load_replication(
            args,
            candidate,
        )
        prices, price_path, price_provenance_path, price_provenance = (
            _load_prices(args)
        )
        (
            risk_free,
            risk_free_path,
            risk_free_provenance_path,
            risk_free_provenance,
        ) = _load_risk_free(args, prices)
        settings = _settings(
            args,
            candidate=candidate,
            statistical_baselines=statistical_baselines,
            guard_baselines=guard_baselines,
            models=models,
        )
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.research_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[candidate],
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
                **replication_auxiliary,
            },
        )
        if split["role"] != "research":
            raise ValueError("Manifest role must be research")

        result = run_portfolio_model_backtest(
            prices,
            models=models,
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
            result["summary_by_model"],
            candidate_name=candidate,
            statistical_baselines=statistical_baselines,
            guard_baselines=guard_baselines,
        )
        paired, holm, statistical = _statistical_gate(
            result,
            risk_free,
            args,
            candidate=candidate,
            statistical_baselines=statistical_baselines,
        )
        reasons = (
            list(deterministic["reasons"])
            + list(statistical["reasons"])
        )
        promotion_gate = {
            "status": "passed" if not reasons else "rejected",
            "reasons": reasons,
            "deterministic": deterministic,
            "statistical": statistical,
        }
        promotion_eligible = bool(
            split["promotion_safe"]
            and promotion_gate["status"] == "passed"
        )
        candidate_risk_diagnostics = _candidate_risk_diagnostics(
            result,
            candidate,
        )
        result_for_output = {
            key: value
            for key, value in result.items()
            if key not in {
                "rebalance_records",
                "daily_returns_by_model",
            }
        }
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
            "replication": replication,
            "paired_bootstrap": paired,
            "holm_gate": holm,
            "promotion_gate": promotion_gate,
            "promotion_eligible": promotion_eligible,
            "candidate_risk_diagnostics": (
                candidate_risk_diagnostics
            ),
            "result": result_for_output,
        }
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        report_path = _write_report(
            payload,
            output_path,
            models=models,
            statistical_baselines=statistical_baselines,
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
