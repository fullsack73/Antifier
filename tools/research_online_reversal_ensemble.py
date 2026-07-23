#!/usr/bin/env python3
"""Test no-tune online Hedge over momentum and short-term reversal."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
TOOLS = ROOT / "tools"
for directory in (BACKEND, TOOLS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from forecast_signal_research import (  # noqa: E402
    paired_rank_signal_block_bootstrap,
)
from portfolio_signals import (  # noqa: E402
    momentum_rank,
    rank_to_unit_scores,
)
from portfolio_statistics import holm_bonferroni  # noqa: E402
from research_accrual_quality import (  # noqa: E402
    BASELINE,
    _evaluation_positions,
    _load_json,
    _load_prices,
    _period_record,
    _signal_result,
    short_term_reversal_buckets,
)
from research_split import validate_research_split_run  # noqa: E402


CANDIDATE = "online_reversal_momentum_hedge"
FIXED_BASELINE = "short_term_reversal_momentum"
REVERSAL_DIAGNOSTIC = "short_term_reversal"
EXPERTS = ("momentum_12_1", "short_term_reversal")


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _settings(args):
    return {
        "train_window": int(args.train_window),
        "horizon": int(args.horizon),
        "rebalance_step": int(args.rebalance_step),
        "momentum_lookback": 12,
        "momentum_skip": 1,
        "primary_candidate": CANDIDATE,
        "experts": list(EXPERTS),
        "initial_weights": {
            "momentum_12_1": 0.50,
            "short_term_reversal": 0.50,
        },
        "expert_loss": "one_minus_spearman_rank_ic_divided_by_2",
        "learning_rate": "sqrt_8_log_expert_count_over_completed_count",
        "weight_update": "completed_periods_only",
        "fixed_baseline": FIXED_BASELINE,
        "raw_baseline": BASELINE,
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_block_size": int(args.bootstrap_block_size),
        "bootstrap_minimum_probability": float(
            args.bootstrap_minimum_probability
        ),
        "paired_comparisons": [
            FIXED_BASELINE,
            BASELINE,
        ],
    }


def _rank_ic(scores, realized):
    aligned = pd.concat(
        [
            pd.Series(scores, dtype=float).rename("score"),
            pd.Series(realized, dtype=float).rename("realized"),
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if len(aligned) < 2:
        return 0.0
    value = aligned["score"].rank(method="average").corr(
        aligned["realized"].rank(method="average")
    )
    return 0.0 if pd.isna(value) else float(np.clip(value, -1.0, 1.0))


def hedge_weights(cumulative_losses, completed_count):
    """Return parameter-free Hedge weights from completed expert losses."""
    losses = pd.Series(cumulative_losses, dtype=float).reindex(EXPERTS)
    if completed_count <= 0:
        return pd.Series(0.5, index=EXPERTS, dtype=float)
    eta = math.sqrt(
        8.0 * math.log(len(EXPERTS)) / float(completed_count)
    )
    logits = -eta * losses
    logits -= float(logits.max())
    weights = np.exp(logits)
    return weights / float(weights.sum())


def _run_periods(prices, args):
    reversal = rank_to_unit_scores(
        short_term_reversal_buckets(prices.columns),
        higher_is_better=True,
    ).reindex(prices.columns)
    cumulative_losses = pd.Series(0.0, index=EXPERTS, dtype=float)
    completed_count = 0
    candidate_periods = []
    fixed_periods = []
    momentum_periods = []
    reversal_periods = []
    weight_history = []

    for position in _evaluation_positions(prices, args):
        train_prices = prices.iloc[
            position - int(args.train_window):position
        ]
        momentum = momentum_rank(
            train_prices,
            lookback=12,
            skip=1,
        ).reindex(prices.columns)
        weights = hedge_weights(cumulative_losses, completed_count)
        candidate = rank_to_unit_scores(
            weights["momentum_12_1"] * momentum
            + weights["short_term_reversal"] * reversal,
            higher_is_better=True,
        ).reindex(prices.columns)
        fixed = rank_to_unit_scores(
            0.50 * momentum + 0.50 * reversal,
            higher_is_better=True,
        ).reindex(prices.columns)
        realized = (
            prices.iloc[position + int(args.horizon)]
            / prices.iloc[position]
            - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        as_of = prices.index[position]
        forward_end = prices.index[position + int(args.horizon)]

        candidate_periods.append(
            _period_record(as_of, forward_end, candidate, realized)
        )
        fixed_periods.append(
            _period_record(as_of, forward_end, fixed, realized)
        )
        momentum_periods.append(
            _period_record(as_of, forward_end, momentum, realized)
        )
        reversal_periods.append(
            _period_record(as_of, forward_end, reversal, realized)
        )
        weight_history.append({
            "as_of_date": as_of.strftime("%Y-%m-%d"),
            "completed_period_count": int(completed_count),
            "momentum_weight": float(weights["momentum_12_1"]),
            "short_term_reversal_weight": float(
                weights["short_term_reversal"]
            ),
        })

        expert_scores = {
            "momentum_12_1": momentum,
            "short_term_reversal": reversal,
        }
        for name, scores in expert_scores.items():
            ic = _rank_ic(scores, realized)
            cumulative_losses[name] += (1.0 - ic) / 2.0
        completed_count += 1

    return {
        "candidate": candidate_periods,
        "fixed": fixed_periods,
        "momentum": momentum_periods,
        "reversal": reversal_periods,
        "weight_history": weight_history,
    }


def _paired_family_gate(candidate_periods, baselines, args):
    comparisons = {}
    raw_p_values = {}
    for offset, (name, periods) in enumerate(baselines.items()):
        paired = paired_rank_signal_block_bootstrap(
            candidate_periods,
            periods,
            block_size=args.bootstrap_block_size,
            samples=args.bootstrap_samples,
            seed=50 + offset,
        )
        probability = paired.get("probability", {})
        if paired.get("status") != "ok":
            raw_p_value = 1.0
        else:
            raw_p_value = max(
                1.0 - probability["higher_mean_rank_ic"],
                1.0
                - probability["higher_mean_top_bottom_spread"],
            )
        raw_p_values[name] = raw_p_value
        comparisons[name] = {"paired_bootstrap": paired}

    holm = holm_bonferroni(raw_p_values, alpha=0.05)
    reasons = []
    for name, comparison in comparisons.items():
        paired = comparison["paired_bootstrap"]
        probability = paired.get("probability", {})
        comparison_reasons = []
        if paired.get("status") != "ok":
            comparison_reasons.append(
                "Insufficient paired dependent-period observations."
            )
        else:
            if (
                probability["higher_mean_rank_ic"]
                < args.bootstrap_minimum_probability
            ):
                comparison_reasons.append(
                    "Paired rank-IC improvement probability is below 95%."
                )
            if (
                probability["higher_mean_top_bottom_spread"]
                < args.bootstrap_minimum_probability
            ):
                comparison_reasons.append(
                    "Paired spread improvement probability is below 95%."
                )
        if not holm[name]["significant"]:
            comparison_reasons.append(
                "Paired improvement is not significant after Holm correction."
            )
        comparison["holm"] = holm[name]
        comparison["status"] = (
            "passed" if not comparison_reasons else "rejected"
        )
        comparison["reasons"] = comparison_reasons
        reasons.extend(f"{name}: {reason}" for reason in comparison_reasons)
    return {
        "status": "passed" if not reasons else "rejected",
        "reasons": reasons,
        "comparisons": comparisons,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--research-split", required=True)
    parser.add_argument("--experiment-namespace", required=True)
    parser.add_argument("--train-window", type=int, default=72)
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--rebalance-step", type=int, default=1)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-block-size", type=int, default=12)
    parser.add_argument(
        "--bootstrap-minimum-probability",
        type=float,
        default=0.95,
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        prices, provenance, price_path, provenance_path = (
            _load_prices(args)
        )
        positions = _evaluation_positions(prices, args)
        split_path = Path(args.split_manifest).expanduser().resolve()
        split = validate_research_split_run(
            _load_json(split_path),
            split_id=args.research_split,
            experiment_namespace=args.experiment_namespace,
            objectives=[CANDIDATE],
            settings=_settings(args),
            evaluation_start=prices.index[positions[0]],
            evaluation_end=prices.index[positions[-1]],
            universe_manifest_sha256=(
                provenance.get("universe_manifest_sha256")
                or provenance.get("basket_manifest_sha256")
            ),
            price_file_sha256=provenance.get("price_file_sha256"),
            factor_file_sha256=None,
            auxiliary_files={},
        )
        if split["role"] != "research":
            raise ValueError("Online ensemble manifest role must be research")
        periods = _run_periods(prices, args)
        candidate = _signal_result(
            CANDIDATE,
            periods["candidate"],
            args,
            seed=42,
        )
        fixed = _signal_result(
            FIXED_BASELINE,
            periods["fixed"],
            args,
            seed=43,
        )
        momentum = _signal_result(
            BASELINE,
            periods["momentum"],
            args,
            seed=44,
        )
        reversal = _signal_result(
            REVERSAL_DIAGNOSTIC,
            periods["reversal"],
            args,
            seed=45,
        )
        paired_gate = _paired_family_gate(
            periods["candidate"],
            {
                FIXED_BASELINE: periods["fixed"],
                BASELINE: periods["momentum"],
            },
            args,
        )
        promotion_eligible = bool(
            candidate["gate"]["status"] == "passed"
            and paired_gate["status"] == "passed"
            and split.get("promotion_safe", False)
            and provenance.get("promotion_safe", False)
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
                "price_provenance_file": str(provenance_path),
                "row_count": int(len(prices)),
                "ticker_count": int(len(prices.columns)),
            },
            "settings": _settings(args),
            "candidate": candidate,
            "fixed_baseline": fixed,
            "momentum_baseline": momentum,
            "reversal_diagnostic": reversal,
            "paired_family_gate": paired_gate,
            "weight_history": periods["weight_history"],
            "promotion_eligible": promotion_eligible,
        }
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
