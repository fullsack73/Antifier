#!/usr/bin/env python3
"""Compare pooled cross-sectional objectives on a research-only split."""

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

from cross_sectional_forecast import (  # noqa: E402
    POOLED_OBJECTIVES,
    compare_pooled_objectives,
)
from portfolio_backtest import fetch_backtest_price_data  # noqa: E402
from research_split import validate_research_split_run  # noqa: E402
from universe_manifest import (  # noqa: E402
    manifest_tickers_during,
    normalize_universe_manifest,
    universe_manifest_digest,
    validate_universe_provenance,
)


RESERVED_SPLIT_NAMES = {
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
        "horizon": int(args.horizon),
        "rebalance_step": int(
            args.horizon
            if args.rebalance_step is None
            else args.rebalance_step
        ),
        "minimum_feature_history": 253,
        "minimum_training_periods": int(
            args.minimum_training_periods
        ),
        "maximum_training_periods": int(
            args.maximum_training_periods
        ),
        "minimum_observations": int(args.minimum_observations),
        "ridge_penalty": float(args.ridge_penalty),
        "nested_ridge_penalties": [
            float(value) for value in args.nested_ridge_penalties
        ],
        "nested_validation_periods": int(
            args.nested_validation_periods
        ),
        "nominal_uncertainty_coverage": 0.8,
    }
    if args.market_factor_data:
        settings["market_beta_policy"] = (
            "fama_french_market_total_return"
        )
    return settings


def _load_prices(args, universe_manifest=None):
    if args.csv:
        prices = pd.read_csv(args.csv, index_col=0, parse_dates=True)
        requested_tickers = args.tickers
        if universe_manifest is not None and not requested_tickers:
            requested_tickers = manifest_tickers_during(
                universe_manifest,
                args.start or prices.index.min(),
                args.end or prices.index.max(),
            )
        if requested_tickers:
            missing = [
                ticker for ticker in requested_tickers
                if ticker not in prices.columns
            ]
            if missing:
                raise ValueError(f"CSV is missing tickers: {missing}")
            prices = prices.loc[:, requested_tickers]
        return prices
    tickers = args.tickers
    if universe_manifest is not None:
        if not args.start or not args.end:
            raise ValueError(
                "--start and --end are required with a remote universe manifest"
            )
        tickers = manifest_tickers_during(
            universe_manifest,
            args.start,
            args.end,
        )
    if not tickers:
        raise ValueError("Provide --csv, --tickers, or --universe-manifest")
    return fetch_backtest_price_data(
        tickers=tickers,
        start_date=args.start,
        end_date=args.end,
    )


def _load_universe(args):
    if not args.universe_manifest:
        return None, {
            "source": "static price columns",
            "survivorship_policy": "not_asserted",
            "promotion_safe": False,
        }
    if not args.universe_provenance:
        raise ValueError(
            "--universe-manifest requires --universe-provenance"
        )
    manifest = normalize_universe_manifest(
        pd.read_csv(args.universe_manifest)
    )
    provenance = validate_universe_provenance(
        json.loads(
            Path(args.universe_provenance).read_text(encoding="utf-8")
        ),
        require_promotion_safe=args.require_promotion_safe_universe,
    )
    provenance["manifest_sha256"] = universe_manifest_digest(manifest)
    return manifest, provenance


def _load_factor_data(args):
    if not args.factor_data:
        if args.factor_provenance:
            raise ValueError(
                "--factor-provenance requires --factor-data"
            )
        return None, None
    if not args.factor_provenance:
        raise ValueError(
            "--factor-data requires --factor-provenance"
        )
    factor_path = Path(args.factor_data).expanduser().resolve()
    provenance_path = Path(args.factor_provenance).expanduser().resolve()
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    actual_digest = _sha256(factor_path)
    expected_digest = str(provenance.get("feature_file_sha256") or "")
    if not expected_digest:
        raise ValueError(
            "Factor provenance requires feature_file_sha256"
        )
    if actual_digest != expected_digest:
        raise ValueError(
            "Factor data SHA-256 does not match provenance"
        )
    universe = dict(provenance.get("universe") or {})
    return pd.read_csv(factor_path), {
        "source": provenance.get("source"),
        "ingestion_mode": provenance.get("ingestion_mode"),
        "feature_file": str(factor_path),
        "feature_file_sha256": actual_digest,
        "provenance_file": str(provenance_path),
        "universe": universe,
        "prices": dict(provenance.get("prices") or {}),
        "promotion_safe": bool(
            universe.get("promotion_safe", False)
            and provenance.get("promotion_safe", False)
        ),
    }


def _load_market_factor_data(args):
    if bool(args.market_factor_data) != bool(
        args.market_factor_provenance
    ):
        raise ValueError(
            "--market-factor-data and --market-factor-provenance "
            "must be used together"
        )
    if not args.market_factor_data:
        return None, None
    path = Path(args.market_factor_data).expanduser().resolve()
    provenance_path = Path(
        args.market_factor_provenance
    ).expanduser().resolve()
    provenance = json.loads(
        provenance_path.read_text(encoding="utf-8")
    )
    actual = _sha256(path)
    if provenance.get("factor_file_sha256") != actual:
        raise ValueError(
            "Market-factor data SHA-256 does not match provenance"
        )
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    required = {"mkt_rf", "rf_daily"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(
            "Market-factor data is missing: " + ", ".join(missing)
        )
    market = (
        pd.to_numeric(frame["mkt_rf"], errors="coerce")
        + pd.to_numeric(frame["rf_daily"], errors="coerce")
    ).dropna()
    return market, {
        **provenance,
        "file": str(provenance_path),
        "file_sha256": _sha256(provenance_path),
    }


def _load_price_provenance(args):
    if not args.csv:
        if args.price_provenance:
            raise ValueError(
                "--price-provenance requires --csv"
            )
        return None
    if not args.price_provenance:
        if args.require_promotion_safe_universe:
            raise ValueError(
                "Promotion-safe universe research requires "
                "--price-provenance with --csv"
            )
        return None
    price_path = Path(args.csv).expanduser().resolve()
    provenance_path = Path(args.price_provenance).expanduser().resolve()
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    actual_digest = _sha256(price_path)
    expected_digest = str(provenance.get("price_file_sha256") or "")
    if not expected_digest:
        raise ValueError(
            "Price provenance requires price_file_sha256"
        )
    if actual_digest != expected_digest:
        raise ValueError(
            "Price CSV SHA-256 does not match provenance"
        )
    return {
        **provenance,
        "provenance_file": str(provenance_path),
        "promotion_safe": True,
    }


def _load_split_manifest(
    args,
    universe_provenance,
    price_provenance,
    factor_provenance,
    market_factor_provenance,
):
    if not args.split_manifest:
        if args.require_promotion_safe_universe:
            raise ValueError(
                "Promotion-safe research requires --split-manifest"
            )
        return {
            "source": "unlocked CLI arguments",
            "promotion_safe": False,
        }
    if not args.evaluation_start or not args.evaluation_end:
        raise ValueError(
            "--split-manifest requires --evaluation-start and "
            "--evaluation-end"
        )
    path = Path(args.split_manifest).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    validated = validate_research_split_run(
        payload,
        split_id=args.research_split,
        experiment_namespace=args.experiment_namespace,
        objectives=args.objectives,
        settings=_research_settings(args),
        evaluation_start=args.evaluation_start,
        evaluation_end=args.evaluation_end,
        universe_manifest_sha256=universe_provenance.get(
            "manifest_sha256"
        ),
        price_file_sha256=(
            None
            if price_provenance is None
            else price_provenance.get("price_file_sha256")
        ),
        factor_file_sha256=(
            None
            if factor_provenance is None
            else factor_provenance.get("feature_file_sha256")
        ),
        auxiliary_files=(
            {}
            if market_factor_provenance is None
            else {
                "market_factor_file_sha256": (
                    market_factor_provenance["factor_file_sha256"]
                )
            }
        ),
    )
    return {
        **validated,
        "file": str(path),
        "file_sha256": _sha256(path),
    }


def _validate_data_lineage(
    universe_provenance,
    price_provenance,
    factor_provenance,
    market_factor_provenance=None,
):
    expected_universe = str(
        universe_provenance.get("manifest_sha256") or ""
    ).strip()
    issues = []
    price_universe = (
        ""
        if price_provenance is None
        else str(
            price_provenance.get("universe_manifest_sha256") or ""
        ).strip()
    )
    if price_provenance is not None and price_universe != expected_universe:
        issues.append(
            "price provenance universe hash does not match the loaded "
            "universe manifest"
        )
    if factor_provenance is not None:
        factor_universe = str(
            factor_provenance.get("universe", {}).get(
                "manifest_sha256"
            )
            or ""
        ).strip()
        if factor_universe != expected_universe:
            issues.append(
                "factor provenance universe hash does not match the loaded "
                "universe manifest"
            )
        expected_price = (
            ""
            if price_provenance is None
            else str(
                price_provenance.get("price_file_sha256") or ""
            ).strip()
        )
        factor_price = str(
            factor_provenance.get("prices", {}).get(
                "price_file_sha256"
            )
            or ""
        ).strip()
        if factor_price != expected_price:
            issues.append(
                "factor provenance price hash does not match the loaded "
                "price data"
            )
    if issues:
        raise ValueError("Data lineage mismatch: " + "; ".join(issues))
    return {
        "universe_manifest_sha256": expected_universe,
        "price_file_sha256": (
            None
            if price_provenance is None
            else price_provenance.get("price_file_sha256")
        ),
        "factor_file_sha256": (
            None
            if factor_provenance is None
            else factor_provenance.get("feature_file_sha256")
        ),
        "market_factor_file_sha256": (
            None
            if market_factor_provenance is None
            else market_factor_provenance.get("factor_file_sha256")
        ),
        "status": "verified",
    }


def _fmt(value, digits=4):
    if value is None:
        return "NA"
    return f"{float(value):.{digits}f}"


def _write_markdown(payload, output_path):
    lines = [
        "# Cross-sectional Forecast Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Price rows: {payload['data']['row_count']}",
        f"- Tickers: {payload['data']['ticker_count']}",
        f"- Selection: `{payload['comparison']['selection_status']}`",
        f"- Data promotion safe: `{payload['data_promotion_safe']}`",
        f"- Split locked: `{payload['split']['promotion_safe']}`",
        f"- Signal gate passed: `{payload['signal_gate_passed']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Signal-only comparison",
        "",
        "| Objective | Gate | Periods | Rank IC | P(IC>0) | Positive IC | Top-bottom | P(Spread>0) | Coverage | OOS radius | Fits | Seconds | Peak MiB |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for objective, run in payload["comparison"]["runs"].items():
        rank = run["rank_diagnostics"]
        uncertainty = run.get("uncertainty_diagnostics") or {}
        bootstrap = run.get("rank_bootstrap") or {}
        probability = bootstrap.get("probability") or {}
        cost = run["cost"]
        lines.append(
            "| {objective} | {gate} | {periods} | {rank_ic} | {p_ic} | "
            "{positive} | {spread} | {p_spread} | {coverage} | {radius} | {fits} | "
            "{seconds} | {memory} |".format(
                objective=objective,
                gate=run["signal_only_gate"]["status"],
                periods=rank["period_count"],
                rank_ic=_fmt(rank["mean_rank_ic"]),
                p_ic=_fmt(probability.get("positive_mean_rank_ic")),
                positive=_fmt(rank["positive_rank_ic_rate"]),
                spread=_fmt(rank["mean_top_bottom_spread"]),
                p_spread=_fmt(
                    probability.get("positive_mean_top_bottom_spread")
                ),
                coverage=_fmt(
                    run["distribution_diagnostics"].get(
                        "active_universe_coverage_rate",
                        rank["mean_coverage_rate"],
                    )
                ),
                radius=_fmt(
                    uncertainty.get("calibrated_absolute_error_radius")
                ),
                fits=cost["fit_count"],
                seconds=_fmt(cost["elapsed_seconds"], digits=2),
                memory=_fmt(
                    cost["peak_memory_bytes"] / (1024 * 1024),
                    digits=2,
                ),
            )
        )
    paired = payload["comparison"].get("paired_improvement") or {}
    if paired:
        lines.extend([
            "",
            "## Paired candidate improvement",
            "",
            "| Comparison | Gate | Δ rank IC | P(higher IC) | "
            "Δ spread | P(higher spread) |",
            "|---|---|---:|---:|---:|---:|",
        ])
        for name, result in paired.items():
            observed = result.get("observed_difference") or {}
            probability = result.get("probability") or {}
            lines.append(
                "| {name} | {gate} | {rank_ic} | {p_ic} | "
                "{spread} | {p_spread} |".format(
                    name=name,
                    gate=result.get("gate", {}).get(
                        "status",
                        "rejected",
                    ),
                    rank_ic=_fmt(observed.get("mean_rank_ic")),
                    p_ic=_fmt(
                        probability.get("higher_mean_rank_ic")
                    ),
                    spread=_fmt(
                        observed.get("mean_top_bottom_spread")
                    ),
                    p_spread=_fmt(
                        probability.get(
                            "higher_mean_top_bottom_spread"
                        )
                    ),
                )
            )
    lines.extend([
        "",
        "## Guardrail",
        "",
        "- Research split only; no portfolio construction or promotion decision.",
        "- Freeze one candidate before any validation run.",
        "- Do not use validation or locked-holdout outcomes for objective tuning.",
    ])
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="Research price CSV")
    parser.add_argument(
        "--price-provenance",
        help="JSON provenance containing the research price CSV SHA-256",
    )
    parser.add_argument("--tickers", nargs="*", help="Research-only ticker set")
    parser.add_argument("--start", help="Price start date YYYY-MM-DD")
    parser.add_argument("--end", help="Price end date YYYY-MM-DD")
    parser.add_argument(
        "--evaluation-start",
        help="First signal date; earlier prices remain training history",
    )
    parser.add_argument(
        "--evaluation-end",
        help="Last signal date",
    )
    parser.add_argument(
        "--research-split",
        required=True,
        help="Unique split label; validation/holdout labels are rejected",
    )
    parser.add_argument(
        "--experiment-namespace",
        required=True,
        help="Unique model/target namespace",
    )
    parser.add_argument(
        "--split-manifest",
        help=(
            "Immutable split/data/objective contract with a self-declared "
            "SHA-256"
        ),
    )
    parser.add_argument(
        "--objectives",
        nargs="+",
        choices=POOLED_OBJECTIVES,
        default=[
            "absolute_ridge",
            "relative_ridge",
            "pairwise_ridge",
            "listwise_rank_ridge",
        ],
    )
    parser.add_argument("--factor-data", help="PIT factor CSV for residual target")
    parser.add_argument(
        "--factor-provenance",
        help="JSON provenance containing the PIT factor CSV SHA-256",
    )
    parser.add_argument("--market-factor-data")
    parser.add_argument("--market-factor-provenance")
    parser.add_argument(
        "--universe-manifest",
        help="Dated effective_date,ticker,in_universe CSV",
    )
    parser.add_argument(
        "--universe-provenance",
        help="JSON provenance for the dated universe manifest",
    )
    parser.add_argument(
        "--require-promotion-safe-universe",
        action="store_true",
    )
    parser.add_argument("--horizon", type=int, default=63)
    parser.add_argument("--rebalance-step", type=int, default=None)
    parser.add_argument("--minimum-training-periods", type=int, default=8)
    parser.add_argument("--maximum-training-periods", type=int, default=12)
    parser.add_argument("--minimum-observations", type=int, default=40)
    parser.add_argument("--ridge-penalty", type=float, default=5.0)
    parser.add_argument(
        "--nested-ridge-penalties",
        nargs="+",
        type=float,
        default=[1.0, 5.0, 20.0, 100.0],
    )
    parser.add_argument(
        "--nested-validation-periods",
        type=int,
        default=3,
    )
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args(argv)

    try:
        split = args.research_split.strip().lower()
        if split in RESERVED_SPLIT_NAMES:
            raise ValueError(
                "Reserved validation/holdout split name cannot be used for research"
            )
        factor_objectives = {
            "factor_residual_price_ridge",
            "factor_residual_ridge",
            "factor_residual_nested_ridge",
            "factor_residual_market_nested_ridge",
            "factor_residual_quality_ridge",
        }
        if factor_objectives.intersection(args.objectives) and not (
            args.factor_data
        ):
            raise ValueError(
                "factor-residual objectives require --factor-data"
            )
        universe_manifest, universe_provenance = _load_universe(args)
        price_provenance = _load_price_provenance(args)
        prices = _load_prices(args, universe_manifest=universe_manifest)
        factor_data, factor_provenance = _load_factor_data(args)
        market_factor_returns, market_factor_provenance = (
            _load_market_factor_data(args)
        )
        data_lineage = _validate_data_lineage(
            universe_provenance,
            price_provenance,
            factor_provenance,
            market_factor_provenance,
        )
        split_manifest = _load_split_manifest(
            args,
            universe_provenance,
            price_provenance,
            factor_provenance,
            market_factor_provenance,
        )
        comparison = compare_pooled_objectives(
            prices,
            objectives=args.objectives,
            horizon=args.horizon,
            rebalance_step=args.rebalance_step,
            minimum_training_periods=args.minimum_training_periods,
            maximum_training_periods=args.maximum_training_periods,
            minimum_observations=args.minimum_observations,
            ridge_penalty=args.ridge_penalty,
            nested_ridge_penalties=args.nested_ridge_penalties,
            nested_validation_periods=args.nested_validation_periods,
            market_factor_returns=market_factor_returns,
            point_in_time_features=factor_data,
            universe_manifest=universe_manifest,
            evaluation_start=args.evaluation_start,
            evaluation_end=args.evaluation_end,
        )
        data_promotion_safe = bool(
            universe_provenance.get("promotion_safe", False)
            and (
                price_provenance is not None
                and price_provenance.get("promotion_safe", False)
            )
            and (
                factor_provenance is None
                or factor_provenance["promotion_safe"]
            )
            and (
                market_factor_provenance is None
                or market_factor_provenance.get(
                    "promotion_safe",
                    False,
                )
            )
        )
        signal_gate_passed = bool(comparison["passed_objectives"])
        promotion_eligible = bool(
            data_promotion_safe
            and split_manifest.get("promotion_safe", False)
            and signal_gate_passed
        )
        payload = {
            "research_split": args.research_split,
            "experiment_namespace": args.experiment_namespace,
            "data_promotion_safe": data_promotion_safe,
            "signal_gate_passed": signal_gate_passed,
            "promotion_eligible": promotion_eligible,
            "split": split_manifest,
            "data_lineage": data_lineage,
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
            },
            "universe": universe_provenance,
            "factor_data": factor_provenance,
            "market_factor_data": market_factor_provenance,
            "comparison": comparison,
        }
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        report_path = _write_markdown(payload, output_path)
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
