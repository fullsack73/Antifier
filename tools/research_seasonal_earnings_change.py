#!/usr/bin/env python3
"""Evaluate a fixed PIT seasonal-earnings signal against 12-1 momentum."""

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

from forecast_signal_research import (  # noqa: E402
    cross_sectional_rank_diagnostics,
    paired_rank_signal_block_bootstrap,
    rank_signal_block_bootstrap,
    signal_only_gate,
)
from portfolio_signals import momentum_rank, rank_to_unit_scores  # noqa: E402
from research_split import validate_research_split_run  # noqa: E402
from universe_manifest import (  # noqa: E402
    normalize_universe_manifest,
    universe_snapshot,
)


CANDIDATE = "seasonal_earnings_momentum"
DIAGNOSTIC = "seasonal_earnings_change"
BASELINE = "momentum_12_1"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _settings(args):
    return {
        "train_window": 252,
        "horizon": 63,
        "rebalance_step": 21,
        "momentum_lookback": 252,
        "momentum_skip": 21,
        "momentum_weight": 0.5,
        "seasonal_earnings_weight": 0.5,
        "seasonal_earnings_definition": (
            "(current_quarter_net_income-"
            "prior_year_same_quarter_net_income)/assets"
        ),
        "bootstrap_samples": int(args.bootstrap_samples),
        "bootstrap_block_size": 3,
        "bootstrap_minimum_probability": 0.95,
        "fresh_period": False,
    }


def _load_verified(path, provenance_path, digest_field):
    path = Path(path).expanduser().resolve()
    provenance_path = Path(provenance_path).expanduser().resolve()
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get(digest_field) != _sha256(path):
        raise ValueError(f"{path.name} SHA-256 does not match provenance")
    return path, provenance_path, provenance


def _period(as_of, forward_end, scores, realized):
    return {
        "period_id": as_of.strftime("%Y-%m-%d"),
        "as_of_date": as_of.strftime("%Y-%m-%d"),
        "forward_end_date": forward_end.strftime("%Y-%m-%d"),
        "scores": scores.dropna().astype(float).to_dict(),
        "realized_returns": realized.dropna().astype(float).to_dict(),
    }


def _distribution(periods):
    coverages = []
    ties = []
    for period in periods:
        scores = pd.Series(period["scores"], dtype=float)
        realized = pd.Series(period["realized_returns"], dtype=float)
        valid = scores.index.intersection(realized.dropna().index)
        coverages.append(len(valid) / len(scores) if len(scores) else 0.0)
        ties.append(
            0.0
            if not len(valid)
            else 1.0 - scores.loc[valid].nunique() / len(valid)
        )
    return {
        "coverage_rate": float(np.mean(coverages)),
        "active_universe_coverage_rate": float(np.mean(coverages)),
        "boundary_saturation_rate": None,
        "tie_rate": float(np.mean(ties)),
    }


def _signal(name, periods, args, seed):
    rank = cross_sectional_rank_diagnostics(periods)
    bootstrap = rank_signal_block_bootstrap(
        periods,
        block_size=3,
        samples=args.bootstrap_samples,
        seed=seed,
    )
    distribution = _distribution(periods)
    return {
        "name": name,
        "rank_diagnostics": rank,
        "distribution_diagnostics": distribution,
        "bootstrap": bootstrap,
        "gate": signal_only_gate(
            rank,
            distribution,
            rank_bootstrap=bootstrap,
        ),
        "periods": periods,
    }


def _run(prices, features, universe, start, end):
    periods = {"candidate": [], "diagnostic": [], "baseline": []}
    for position in range(252, len(prices) - 63, 21):
        as_of = prices.index[position]
        if as_of < start or as_of > end:
            continue
        forward_end = prices.index[position + 63]
        active = [
            ticker
            for ticker in universe_snapshot(universe, as_of)
            if ticker in prices.columns
        ]
        momentum = momentum_rank(
            prices.loc[:as_of, active].iloc[-252:],
            lookback=252,
            skip=21,
        )
        snapshot = (
            features.loc[features["available_date"] <= as_of]
            .sort_values("available_date")
            .drop_duplicates("ticker", keep="last")
            .set_index("ticker")
        )
        seasonal = rank_to_unit_scores(
            snapshot["seasonal_earnings_change"].reindex(active),
            higher_is_better=True,
        )
        candidate = rank_to_unit_scores(
            0.5 * momentum + 0.5 * seasonal,
            higher_is_better=True,
        )
        realized = (
            prices.loc[forward_end, active] / prices.loc[as_of, active] - 1.0
        ).replace([np.inf, -np.inf], np.nan)
        periods["candidate"].append(
            _period(as_of, forward_end, candidate, realized)
        )
        periods["diagnostic"].append(
            _period(as_of, forward_end, seasonal, realized)
        )
        periods["baseline"].append(
            _period(as_of, forward_end, momentum, realized)
        )
    if not periods["candidate"]:
        raise ValueError("No evaluation periods in locked interval")
    return periods


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--price-provenance", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--feature-provenance", required=True)
    parser.add_argument("--universe-manifest", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=4000)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        price_path, price_provenance_path, price_provenance = _load_verified(
            args.csv, args.price_provenance, "price_file_sha256"
        )
        feature_path, feature_provenance_path, feature_provenance = (
            _load_verified(
                args.features,
                args.feature_provenance,
                "feature_file_sha256",
            )
        )
        universe_path = Path(args.universe_manifest).expanduser().resolve()
        split_path = Path(args.split_manifest).expanduser().resolve()
        split_payload = json.loads(split_path.read_text(encoding="utf-8"))
        settings = _settings(args)
        split = validate_research_split_run(
            split_payload,
            split_id="nasdaq100-seasonal-earnings-research-2018-2019-v1",
            experiment_namespace="alpha-v24-seasonal-earnings",
            objectives=[CANDIDATE],
            settings=settings,
            evaluation_start="2018-01-03",
            evaluation_end="2019-09-05",
            universe_manifest_sha256=(
                price_provenance["universe_manifest_sha256"]
            ),
            price_file_sha256=price_provenance["price_file_sha256"],
            factor_file_sha256=feature_provenance["feature_file_sha256"],
            auxiliary_files={},
        )
        prices = pd.read_csv(price_path, index_col=0, parse_dates=True)
        features = pd.read_csv(
            feature_path,
            parse_dates=["available_date"],
        )
        universe = normalize_universe_manifest(pd.read_csv(universe_path))
        periods = _run(
            prices,
            features,
            universe,
            pd.Timestamp(split["evaluation_start"]),
            pd.Timestamp(split["evaluation_end"]),
        )
        candidate = _signal(CANDIDATE, periods["candidate"], args, 41)
        diagnostic = _signal(DIAGNOSTIC, periods["diagnostic"], args, 42)
        baseline = _signal(BASELINE, periods["baseline"], args, 43)
        paired = paired_rank_signal_block_bootstrap(
            periods["candidate"],
            periods["baseline"],
            block_size=3,
            samples=args.bootstrap_samples,
            seed=44,
        )
        probability = paired.get("probability", {})
        paired_passed = bool(
            paired.get("status") == "ok"
            and probability.get("higher_mean_rank_ic", 0.0) >= 0.95
            and probability.get("higher_mean_top_bottom_spread", 0.0)
            >= 0.95
        )
        payload = {
            "research_split": split["split_id"],
            "experiment_namespace": split["experiment_namespace"],
            "split": {
                **split,
                "file": str(split_path),
                "file_sha256": _sha256(split_path),
            },
            "data": {
                "price_file": str(price_path),
                "price_provenance_file": str(price_provenance_path),
                "feature_file": str(feature_path),
                "feature_provenance_file": str(feature_provenance_path),
                "universe_manifest": str(universe_path),
            },
            "settings": settings,
            "candidate": candidate,
            "diagnostic": diagnostic,
            "baseline": baseline,
            "paired_bootstrap": paired,
            "paired_gate": {
                "status": "passed" if paired_passed else "rejected"
            },
            "promotion_eligible": False,
            "promotion_blockers": [
                "Candidate and paired statistical gates did not pass.",
                "Evaluation interval was reused and is exploratory only.",
            ],
        }
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
