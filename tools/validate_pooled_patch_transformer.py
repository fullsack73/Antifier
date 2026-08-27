#!/usr/bin/env python3
"""Run the frozen pooled Patch Transformer on a locked fresh validation split."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from cross_sectional_forecast import walk_forward_pooled_ridge  # noqa: E402
from pooled_patch_transformer import (  # noqa: E402
    PatchTransformerConfig,
    _resolve_positions,
    compare_patch_transformer_runs,
    load_kronos_checkpoint,
    walk_forward_pooled_patch_transformer,
)
from research_split import validate_research_split_run  # noqa: E402
from universe_manifest import (  # noqa: E402
    normalize_universe_manifest,
    universe_manifest_digest,
    universe_snapshot,
    validate_universe_provenance,
)
from tools.benchmark_kronos_forecasts import (  # noqa: E402
    KRONOS_MODEL_REVISION,
    KRONOS_REPOSITORY,
    KRONOS_REPOSITORY_COMMIT,
    KRONOS_TOKENIZER_REVISION,
    _load_checkpoint,
    load_kronos_predictor,
    run_kronos_origins,
)
from tools.research_pooled_patch_transformer import (  # noqa: E402
    _close_panel,
    _fixed_gamma_gmv_experiment,
    _kronos_baseline,
    _read_ohlcv,
)


FROZEN_CONFIG = PatchTransformerConfig()
FRESH_OBJECTIVES = ["pooled_patch_transformer_with_kronos"]
FRESH_SETTINGS = {
    "target_kind": "relative",
    "include_pit_context": False,
    "horizons": [21, 63],
    "rebalance_step": 63,
    "lookback": 504,
    "patch_size": 5,
    "d_model": 32,
    "num_heads": 4,
    "ff_dim": 64,
    "num_blocks": 2,
    "dense_units": 32,
    "dropout": 0.15,
    "learning_rate": 5e-4,
    "weight_decay": 1e-4,
    "epochs": 12,
    "batch_size": 32,
    "patience": 3,
    "validation_periods": 2,
    "random_state": 42,
    "minimum_training_periods": 8,
    "maximum_training_periods": 12,
    "minimum_observations": 60,
    "baselines": [
        "relative_ridge",
        "frozen_kronos_score",
        "ledoit_wolf_gmv",
    ],
    "signal_gate_probability": 0.95,
    "gmv_overlay_active_share": 0.05,
    "max_asset_weight": 0.20,
    "transaction_cost_bps": 10.0,
    "rebalance_band": 0.02,
    "max_turnover": 0.35,
    "kronos": {
        "repository_commit": KRONOS_REPOSITORY_COMMIT,
        "model_revision": KRONOS_MODEL_REVISION,
        "tokenizer_revision": KRONOS_TOKENIZER_REVISION,
        "device": "mps",
        "temperature": 1.0,
        "top_p": 0.9,
        "sample_count": 1,
        "seed": 42,
        "inference_batch_size": 16,
    },
}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _verified_inputs(args):
    paths = {
        name: Path(value).expanduser().resolve()
        for name, value in {
            "ohlcv": args.ohlcv_csv,
            "ohlcv_provenance": args.ohlcv_provenance,
            "universe": args.universe_manifest,
            "universe_provenance": args.universe_provenance,
            "factor": args.factor_data,
            "factor_provenance": args.factor_provenance,
            "split": args.split_manifest,
        }.items()
    }
    ohlcv_provenance = _read_json(paths["ohlcv_provenance"])
    universe_provenance = validate_universe_provenance(
        _read_json(paths["universe_provenance"]),
        require_promotion_safe=True,
    )
    factor_provenance = _read_json(paths["factor_provenance"])
    universe = normalize_universe_manifest(pd.read_csv(paths["universe"]))
    digests = {name: _sha256(path) for name, path in paths.items() if name != "split"}
    universe_digest = universe_manifest_digest(universe)
    if digests["ohlcv"] != ohlcv_provenance.get("price_file_sha256"):
        raise ValueError("OHLCV SHA-256 does not match its provenance")
    if universe_digest != universe_provenance.get("manifest_sha256"):
        raise ValueError("Universe manifest digest does not match its provenance")
    if digests["factor"] != factor_provenance.get("feature_file_sha256"):
        raise ValueError("PIT factor SHA-256 does not match its provenance")
    if not (
        ohlcv_provenance.get("promotion_safe")
        and factor_provenance.get("promotion_safe")
    ):
        raise ValueError("Fresh validation requires promotion-safe data provenance")

    manifest = _read_json(paths["split"])
    split = validate_research_split_run(
        manifest,
        split_id="nasdaq100-patch-transformer-fresh-validation-2024-2025-v1",
        experiment_namespace="pooled-patch-transformer-fresh-validation-v1",
        objectives=FRESH_OBJECTIVES,
        settings=FRESH_SETTINGS,
        evaluation_start="2024-01-01",
        evaluation_end="2025-12-31",
        universe_manifest_sha256=universe_digest,
        price_file_sha256=digests["ohlcv"],
        factor_file_sha256=digests["factor"],
        auxiliary_files={
            "ohlcv_provenance": digests["ohlcv_provenance"],
            "universe_provenance": digests["universe_provenance"],
            "factor_provenance": digests["factor_provenance"],
        },
    )
    return paths, universe, split, digests


def _origin_inputs(prices, universe, split):
    all_positions = _resolve_positions(
        prices,
        FROZEN_CONFIG,
        rebalance_step=FRESH_SETTINGS["rebalance_step"],
    )
    all_positions = [
        position
        for position in all_positions
        if prices.index[position] <= pd.Timestamp(split["evaluation_end"])
    ]
    evaluation_positions = [
        position
        for position in all_positions
        if prices.index[position] >= pd.Timestamp(split["evaluation_start"])
    ]
    if not evaluation_positions:
        raise ValueError("Fresh split contains no evaluation origins")
    first_evaluation = evaluation_positions[0]
    completed_training_positions = [
        position
        for position in all_positions
        if position + max(FROZEN_CONFIG.horizons) <= first_evaluation
    ]
    positions = (
        completed_training_positions[
            -FRESH_SETTINGS["maximum_training_periods"]:
        ]
        + evaluation_positions
    )
    if len(positions) - len(evaluation_positions) < FRESH_SETTINGS[
        "minimum_training_periods"
    ]:
        raise ValueError("Fresh split has insufficient completed training origins")
    dates = [prices.index[position] for position in positions]
    universes = {date: universe_snapshot(universe, date) for date in dates}
    return positions, dates, universes


def _build_kronos_origins(ohlcv, prices, positions, universes, split_id):
    fields = ["open", "high", "low", "close", "volume"]
    by_ticker = {
        ticker: group.set_index("timestamp").sort_index()
        for ticker, group in ohlcv.groupby("ticker")
    }
    origins = []
    horizon = max(FROZEN_CONFIG.horizons)
    for position in positions:
        as_of = prices.index[position]
        window = prices.index[position - FROZEN_CONFIG.lookback + 1:position + 1]
        future_dates = prices.index[position + 1:position + horizon + 1]
        rows = []
        for ticker in universes[as_of]:
            source = by_ticker.get(ticker)
            if source is None:
                continue
            available_fields = [field for field in fields if field in source]
            train = source.reindex(window).loc[:, available_fields]
            required = ["open", "high", "low", "close"]
            if train[required].isna().any().any():
                continue
            if "volume" not in train:
                train["volume"] = 0.0
            realized_close = source["close"].reindex(future_dates).ffill()
            if len(realized_close) != horizon or realized_close.isna().any():
                continue
            rows.append({
                "ticker": ticker,
                "train": train.loc[:, fields],
                "future_timestamps": pd.Series(future_dates),
                "realized_return": float(
                    realized_close.iloc[-1] / train["close"].iloc[-1] - 1.0
                ),
            })
        if len(rows) >= 2:
            origins.append({
                "period_id": as_of.strftime("%Y-%m-%d"),
                "case_id": split_id,
                "train_start": window[0],
                "train_end": as_of,
                "horizon": horizon,
                "rows": rows,
            })
    return origins


def _checkpoint_signature(split, ohlcv_sha256):
    return {
        "version": 2,
        "split_id": split["split_id"],
        "split_manifest_sha256": split["manifest_sha256"],
        "ohlc_sha256": ohlcv_sha256,
        **FRESH_SETTINGS["kronos"],
    }


def _write_markdown(payload, path):
    candidate = payload["models"]["pooled_patch_transformer_with_kronos"]
    lines = [
        "# Pooled Patch Transformer Fresh Validation",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Promotion eligible: `{payload['promotion_eligible']}`",
        f"- Split: `{payload['split']['split_id']}`",
        f"- Evaluation origins: {candidate['fit_count']}",
        f"- Minimum universe coverage: {payload['minimum_universe_coverage']:.2%}",
        "",
        "| Model | Mean rank IC | Top-bottom spread | Signal gate |",
        "|---|---:|---:|---|",
    ]
    for name, model in payload["models"].items():
        model_rank = model["rank_diagnostics"]
        signal_gate = model.get("signal_gate") or {}
        lines.append(
            f"| {name} | {model_rank['mean_rank_ic'] or 0.0:.4f} | "
            f"{model_rank['mean_top_bottom_spread'] or 0.0:.4f} | "
            f"{signal_gate.get('status', 'not_applicable')} |"
        )
    lines.extend(["", "## Paired signal gates", ""])
    for name, result in payload["paired"].items():
        probability = result.get("probability") or {}
        lines.append(
            f"- {name}: IC {probability.get('higher_mean_rank_ic', 0.0):.2%}, "
            f"spread {probability.get('higher_mean_top_bottom_spread', 0.0):.2%}; "
            f"`{result['gate']['status']}`"
        )
    portfolio = payload["portfolio_validation"]
    lines.extend([
        "",
        "## GMV overlay validation",
        "",
        f"- Status: `{portfolio['status']}`",
    ])
    if portfolio["status"] == "not_run":
        lines.append(f"- Reason: {portfolio['reason']}")
    else:
        lines.append(f"- Portfolio gate: `{portfolio['portfolio_gate']['status']}`")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ohlcv-csv", required=True)
    parser.add_argument("--ohlcv-provenance", required=True)
    parser.add_argument("--universe-manifest", required=True)
    parser.add_argument("--universe-provenance", required=True)
    parser.add_argument("--factor-data", required=True)
    parser.add_argument("--factor-provenance", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--kronos-repo", required=True)
    parser.add_argument("--kronos-checkpoint", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    paths, universe, split, digests = _verified_inputs(args)
    ohlcv = _read_ohlcv(paths["ohlcv"])
    prices = _close_panel(ohlcv)
    positions, dates, universes = _origin_inputs(prices, universe, split)
    origins = _build_kronos_origins(
        ohlcv,
        prices,
        positions,
        universes,
        split["split_id"],
    )
    signature = _checkpoint_signature(split, digests["ohlcv"])
    completed = _load_checkpoint(args.kronos_checkpoint, signature)
    missing_origins = [
        origin for origin in origins if origin["period_id"] not in completed
    ]
    if missing_origins:
        predictor, torch, kronos_model = load_kronos_predictor(
            args.kronos_repo,
            FRESH_SETTINGS["kronos"]["device"],
        )
        run_kronos_origins(
            origins,
            predictor,
            torch,
            args.kronos_checkpoint,
            signature,
            batch_size=FRESH_SETTINGS["kronos"]["inference_batch_size"],
        )
    else:
        kronos_model = {
            "repository": KRONOS_REPOSITORY,
            **FRESH_SETTINGS["kronos"],
            "checkpoint_reused_without_model_load": True,
        }
    kronos, kronos_meta = load_kronos_checkpoint(
        args.kronos_checkpoint,
        expected_horizon=max(FROZEN_CONFIG.horizons),
    )

    common = {
        "ohlcv_data": ohlcv,
        "config": FROZEN_CONFIG,
        "target_kind": FRESH_SETTINGS["target_kind"],
        "kronos_features": kronos,
        "origin_dates": dates,
        "origin_universes": universes,
        "evaluation_start": split["evaluation_start"],
        "evaluation_end": split["evaluation_end"],
        "minimum_training_periods": FRESH_SETTINGS["minimum_training_periods"],
        "maximum_training_periods": FRESH_SETTINGS["maximum_training_periods"],
        "minimum_observations": FRESH_SETTINGS["minimum_observations"],
    }
    candidate = walk_forward_pooled_patch_transformer(
        prices,
        include_kronos=True,
        **common,
    )
    kronos_baseline = _kronos_baseline(candidate, kronos)
    ridge_baseline = walk_forward_pooled_ridge(
        prices,
        objective="relative_ridge",
        horizon=max(FROZEN_CONFIG.horizons),
        rebalance_step=FRESH_SETTINGS["rebalance_step"],
        minimum_feature_history=FROZEN_CONFIG.lookback + 1,
        minimum_training_periods=FRESH_SETTINGS["minimum_training_periods"],
        maximum_training_periods=FRESH_SETTINGS["maximum_training_periods"],
        minimum_observations=40,
        ridge_penalty=5.0,
        universe_manifest=universe,
        evaluation_start=split["evaluation_start"],
        evaluation_end=split["evaluation_end"],
    )
    paired = {
        "candidate_vs_relative_ridge": compare_patch_transformer_runs(
            candidate,
            ridge_baseline,
        ),
        "candidate_vs_frozen_kronos": compare_patch_transformer_runs(
            candidate,
            kronos_baseline,
        ),
    }
    signal_passed = bool(
        candidate["signal_gate"]["status"] == "passed"
        and all(result["gate"]["status"] == "passed" for result in paired.values())
    )
    if signal_passed:
        portfolio = _fixed_gamma_gmv_experiment(
            prices,
            candidate,
            gamma=FRESH_SETTINGS["gmv_overlay_active_share"],
            max_asset_weight=FRESH_SETTINGS["max_asset_weight"],
            transaction_cost_bps=FRESH_SETTINGS["transaction_cost_bps"],
            rebalance_band=FRESH_SETTINGS["rebalance_band"],
            max_turnover=FRESH_SETTINGS["max_turnover"],
        )
        portfolio["status"] = "completed"
        portfolio["promotion_safe"] = bool(split["promotion_safe"])
        portfolio["overlay_policy"] = "frozen 5% active-share rank tilt"
    else:
        portfolio = {
            "status": "not_run",
            "reason": "absolute and paired 95% signal gates did not all pass",
        }
    portfolio_passed = bool(
        portfolio.get("portfolio_gate", {}).get("status") == "passed"
    )
    promotion_eligible = bool(
        split["promotion_safe"] and signal_passed and portfolio_passed
    )
    decision = (
        "passed" if promotion_eligible else
        "portfolio_rejected" if signal_passed else
        "signal_rejected"
    )
    minimum_coverage = min(
        record["coverage_rate"] for record in candidate["records"]
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "locked fresh validation; no tuning or model selection",
        "decision": decision,
        "promotion_eligible": promotion_eligible,
        "split": split,
        "data": {
            "ohlcv": str(paths["ohlcv"]),
            "ohlcv_sha256": digests["ohlcv"],
            "universe_manifest": str(paths["universe"]),
            "universe_manifest_sha256": universe_manifest_digest(universe),
            "factor_data": str(paths["factor"]),
            "factor_file_sha256": digests["factor"],
            "pit_factor_locked_but_not_used_by_frozen_candidate": True,
        },
        "kronos": {**kronos_model, **kronos_meta},
        "minimum_universe_coverage": minimum_coverage,
        "models": {
            "relative_ridge": ridge_baseline,
            "frozen_kronos_score": kronos_baseline,
            "pooled_patch_transformer_with_kronos": candidate,
        },
        "paired": paired,
        "portfolio_validation": portfolio,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    _write_markdown(payload, output.with_suffix(".md"))
    print(json.dumps({
        "decision": decision,
        "promotion_eligible": promotion_eligible,
        "signal_gate": candidate["signal_gate"]["status"],
        "paired_gates": {
            name: result["gate"]["status"] for name, result in paired.items()
        },
        "portfolio_status": portfolio["status"],
        "output": str(output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
