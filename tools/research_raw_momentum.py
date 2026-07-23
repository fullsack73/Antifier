#!/usr/bin/env python3
"""Evaluate raw 12-1 rank tilt against the current lightweight BL."""

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

from forecast_signal_research import (  # noqa: E402
    paired_rank_signal_block_bootstrap,
)
from portfolio_backtest import (  # noqa: E402
    PRICE_SIGNAL_TARGET_ACTIVE_SHARE,
    run_portfolio_model_backtest,
)
from portfolio_signals import (  # noqa: E402
    MOMENTUM_LOOKBACK_DAYS,
    MOMENTUM_SKIP_DAYS,
)
from portfolio_statistics import paired_block_bootstrap  # noqa: E402
from research_high_momentum import (  # noqa: E402
    _combined_gate,
    _model_periods,
    _signal_result,
)
from research_lightweight_uncertainty import (  # noqa: E402
    _fmt,
    _load_json,
    _load_prices,
    _load_risk_free,
    _sha256,
)
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "momentum_12_1_rank_tilt"
BASELINE = "lightweight_bl"
MODELS = (
    "equal_weight",
    "risk_parity",
    "historical_bl",
    BASELINE,
    CANDIDATE,
)


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
        "portfolio_bootstrap_block_size": int(
            args.portfolio_bootstrap_block_size
        ),
        "signal_bootstrap_block_size": int(
            args.signal_bootstrap_block_size
        ),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
        "candidate": CANDIDATE,
        "baseline": BASELINE,
        "models": list(MODELS),
        "candidate_policy": {
            "signal": "cross_sectional_12_1_momentum_rank",
            "lookback": MOMENTUM_LOOKBACK_DAYS,
            "skip": MOMENTUM_SKIP_DAYS,
            "allocator": "equal_weight_active_share_rank_tilt",
            "target_active_share": float(
                PRICE_SIGNAL_TARGET_ACTIVE_SHARE
            ),
        },
        "baseline_policy": {
            "signal": "current_lightweight_ensemble_point_forecast",
            "allocator": "current_black_litterman",
        },
    }


def _deterministic_gate(summary):
    candidate = summary[CANDIDATE]
    baseline = summary[BASELINE]
    reasons = []
    if candidate["cagr"] <= baseline["cagr"]:
        reasons.append("CAGR does not improve lightweight BL.")
    if (
        candidate["sharpe"] is None
        or baseline["sharpe"] is None
        or candidate["sharpe"] <= baseline["sharpe"]
    ):
        reasons.append("Sharpe does not improve lightweight BL.")
    if candidate["max_drawdown"] < baseline["max_drawdown"]:
        reasons.append("Max drawdown is worse than lightweight BL.")
    for guard in (
        "equal_weight",
        "risk_parity",
        "historical_bl",
    ):
        comparison = summary[guard]
        if (
            comparison["sharpe"] is not None
            and candidate["sharpe"] <= comparison["sharpe"]
        ):
            reasons.append(f"Sharpe does not beat {guard}.")
        if candidate["max_drawdown"] < comparison["max_drawdown"]:
            reasons.append(f"Max drawdown is worse than {guard}.")
    if candidate["avg_controlled_turnover"] > max(
        0.50,
        1.25 * baseline["avg_controlled_turnover"],
    ):
        reasons.append("Turnover exceeds the frozen baseline guard.")
    if candidate.get("failed_forecast_count", 0) > 0:
        reasons.append("Candidate signal coverage is incomplete.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
    }


def _write_report(payload, output_path):
    summary = payload["result"]["summary_by_model"]
    candidate = payload["candidate_signal"]["rank_diagnostics"]
    baseline = payload["baseline_signal"]["rank_diagnostics"]
    paired_signal = payload["paired_signal"].get(
        "probability",
        {},
    )
    paired_portfolio = payload["paired_portfolio"].get(
        "probability",
        {},
    )
    lines = [
        "# Raw Momentum Rank-Tilt Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Gate: `{payload['combined_gate']['status']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Signal",
        "",
        "| Signal | Periods | Mean rank IC | Positive IC | "
        "Mean top-bottom |",
        "|---|---:|---:|---:|---:|",
        "| Lightweight point forecast | {periods} | {ic} | "
        "{positive} | {spread} |".format(
            periods=baseline["period_count"],
            ic=_fmt(baseline["mean_rank_ic"]),
            positive=_fmt(baseline["positive_rank_ic_rate"]),
            spread=_fmt(baseline["mean_top_bottom_spread"]),
        ),
        "| Raw 12-1 momentum | {periods} | {ic} | "
        "{positive} | {spread} |".format(
            periods=candidate["period_count"],
            ic=_fmt(candidate["mean_rank_ic"]),
            positive=_fmt(candidate["positive_rank_ic_rate"]),
            spread=_fmt(candidate["mean_top_bottom_spread"]),
        ),
        "",
        f"- P(higher IC): "
        f"`{_fmt(paired_signal.get('higher_mean_rank_ic'))}`",
        f"- P(higher spread): "
        f"`{_fmt(paired_signal.get('higher_mean_top_bottom_spread'))}`",
        "",
        "## Portfolio",
        "",
        "| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |",
        "|---|---:|---:|---:|---:|---:|",
    ]
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
    lines.extend([
        "",
        f"- P(higher return vs lightweight): "
        f"`{_fmt(paired_portfolio.get('higher_return'))}`",
        f"- P(higher Sharpe vs lightweight): "
        f"`{_fmt(paired_portfolio.get('higher_sharpe'))}`",
        "",
        "## Guardrail",
        "",
        "- The raw momentum specification was frozen before this run.",
        "- The closest baseline is the current lightweight BL default.",
        "- Validation remains sealed unless absolute signal, paired "
        "signal, portfolio, guard, and Holm gates all pass.",
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
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--train-window", type=int, default=504)
    parser.add_argument("--rebalance-frequency", type=int, default=63)
    parser.add_argument("--forecast-horizon", type=int, default=63)
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=10.0,
    )
    parser.add_argument("--max-asset-weight", type=float, default=0.10)
    parser.add_argument("--rebalance-band", type=float, default=0.02)
    parser.add_argument("--max-turnover", type=float, default=0.35)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument(
        "--portfolio-bootstrap-block-size",
        type=int,
        default=21,
    )
    parser.add_argument(
        "--signal-bootstrap-block-size",
        type=int,
        default=4,
    )
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
        candidate_periods, candidate_distribution = _model_periods(
            result,
            CANDIDATE,
        )
        baseline_periods, baseline_distribution = _model_periods(
            result,
            BASELINE,
        )
        candidate_signal = _signal_result(
            candidate_periods,
            candidate_distribution,
            args,
            51,
        )
        baseline_signal = _signal_result(
            baseline_periods,
            baseline_distribution,
            args,
            52,
        )
        paired_signal = paired_rank_signal_block_bootstrap(
            candidate_periods,
            baseline_periods,
            block_size=args.signal_bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=53,
        )
        paired_portfolio = paired_block_bootstrap(
            result["daily_returns_by_model"][CANDIDATE],
            result["daily_returns_by_model"][BASELINE],
            risk_free_rate=result["settings"]["risk_free_rate"],
            block_size=args.portfolio_bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=54,
            risk_free_daily_returns=risk_free,
        )
        deterministic = _deterministic_gate(
            result["summary_by_model"]
        )
        combined, holm = _combined_gate(
            candidate_signal,
            paired_signal,
            paired_portfolio,
            deterministic,
            args.bootstrap_minimum_probability,
        )
        promotion_eligible = bool(
            split["promotion_safe"]
            and combined["status"] == "passed"
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
            "candidate_signal": candidate_signal,
            "baseline_signal": baseline_signal,
            "paired_signal": paired_signal,
            "paired_portfolio": paired_portfolio,
            "deterministic_portfolio_gate": deterministic,
            "holm_gate": holm,
            "combined_gate": combined,
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
