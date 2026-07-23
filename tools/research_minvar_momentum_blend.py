#!/usr/bin/env python3
"""Evaluate fixed minimum-variance and momentum diversification."""

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

from portfolio_backtest import (  # noqa: E402
    MINVAR_MOMENTUM_COMPONENT_WEIGHTS,
    PRICE_SIGNAL_TARGET_ACTIVE_SHARE,
    run_portfolio_model_backtest,
)
from portfolio_signals import (  # noqa: E402
    MOMENTUM_LOOKBACK_DAYS,
    MOMENTUM_SKIP_DAYS,
)
from portfolio_statistics import paired_block_bootstrap  # noqa: E402
from research_high_momentum import (  # noqa: E402
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
from research_risk_momentum_blend import _joint_gate  # noqa: E402
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "minvar_momentum_blend"
BASELINES = (
    "min_variance",
    "momentum_12_1_rank_tilt",
)
MODELS = (
    "equal_weight",
    *BASELINES,
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
        "baselines": list(BASELINES),
        "models": list(MODELS),
        "construction_policy": {
            "component_weights": dict(
                MINVAR_MOMENTUM_COMPONENT_WEIGHTS
            ),
            "risk_component": (
                "ledoit_wolf_long_only_minimum_variance"
            ),
            "momentum_signal": "cross_sectional_12_1_rank",
            "momentum_lookback": MOMENTUM_LOOKBACK_DAYS,
            "momentum_skip": MOMENTUM_SKIP_DAYS,
            "momentum_allocator": (
                "equal_weight_active_share_rank_tilt"
            ),
            "momentum_target_active_share": float(
                PRICE_SIGNAL_TARGET_ACTIVE_SHARE
            ),
            "blend_policy": "fixed_weight_convex_combination",
        },
    }


def _deterministic_gate(summary):
    candidate = summary[CANDIDATE]
    reasons = []
    for baseline in BASELINES:
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
    equal = summary["equal_weight"]
    if (
        equal["sharpe"] is not None
        and candidate["sharpe"] <= equal["sharpe"]
    ):
        reasons.append("Sharpe does not beat equal weight.")
    turnover_guard = max(
        0.50,
        1.25
        * max(
            summary[baseline]["avg_controlled_turnover"]
            for baseline in BASELINES
        ),
    )
    if candidate["avg_controlled_turnover"] > turnover_guard:
        reasons.append("Turnover exceeds the frozen component guard.")
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "turnover_guard": float(turnover_guard),
    }


def _write_report(payload, output_path):
    summary = payload["result"]["summary_by_model"]
    signal = payload["signal"]["rank_diagnostics"]
    signal_probability = payload["signal"]["bootstrap"].get(
        "probability",
        {},
    )
    lines = [
        "# Minimum-Variance–Momentum Blend Research",
        "",
        f"- Split: `{payload['research_split']}`",
        f"- Namespace: `{payload['experiment_namespace']}`",
        f"- Gate: `{payload['joint_gate']['status']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        "",
        "## Momentum signal",
        "",
        f"- Periods: `{signal['period_count']}`",
        f"- Mean rank IC: `{_fmt(signal['mean_rank_ic'])}`",
        f"- Mean top-bottom spread: "
        f"`{_fmt(signal['mean_top_bottom_spread'])}`",
        f"- P(IC>0): "
        f"`{_fmt(signal_probability.get('positive_mean_rank_ic'))}`",
        f"- P(spread>0): "
        f"`{_fmt(signal_probability.get('positive_mean_top_bottom_spread'))}`",
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
    for baseline in BASELINES:
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
        "- Component weights are fixed 50/50 without a tuning grid.",
        "- Candidate must improve both component baselines.",
        "- Validation remains sealed unless signal, dual-baseline, "
        "deterministic, and six-hypothesis Holm gates all pass.",
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
    parser.add_argument("--max-asset-weight", type=float, default=0.20)
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
        periods, distribution = _model_periods(
            result,
            CANDIDATE,
        )
        signal = _signal_result(
            periods,
            distribution,
            args,
            71,
        )
        paired = {}
        for index, baseline in enumerate(BASELINES):
            paired[baseline] = paired_block_bootstrap(
                result["daily_returns_by_model"][CANDIDATE],
                result["daily_returns_by_model"][baseline],
                risk_free_rate=result["settings"]["risk_free_rate"],
                block_size=args.portfolio_bootstrap_block_size,
                samples=args.bootstrap_samples,
                seed=72 + index,
                risk_free_daily_returns=risk_free,
            )
        deterministic = _deterministic_gate(
            result["summary_by_model"]
        )
        joint, holm = _joint_gate(
            signal,
            paired,
            deterministic,
            args.bootstrap_minimum_probability,
        )
        promotion_eligible = bool(
            split["promotion_safe"]
            and joint["status"] == "passed"
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
            "signal": signal,
            "paired_bootstrap": paired,
            "deterministic_gate": deterministic,
            "holm_gate": holm,
            "joint_gate": joint,
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
