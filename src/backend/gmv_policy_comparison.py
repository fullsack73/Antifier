"""Preregistered calendar-forward comparison of production GMV operations."""

import copy
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_constraints import constraint_diagnostics, prepare_constraint_model
from portfolio_optimization import (
    _fund_transaction_cost,
    apply_trade_controls,
    optimize_portfolio,
)
from portfolio_risk_models import portfolio_risk_diagnostics
from research_split import canonical_json_digest, load_research_policy


POLICIES = ("buy_and_hold", "fixed_target", "rolling_reoptimization")


class RebalanceNotDue(ValueError):
    """Raised when fewer than the locked trading observations have elapsed."""
SPEC_VERSION = 1
DEFAULTS = {
    "train_window": 504,
    "rebalance_frequency": 63,
    "outcome_horizon": 63,
    "initial_wealth": 10000.0,
    "transaction_cost_bps": 10.0,
    "rebalance_band": 0.02,
    "max_turnover": 0.35,
    "max_asset_weight": 0.20,
    "min_holding_weight": 0.0,
    "risk_free_rate": 0.02,
    "fractional_units": True,
    "bootstrap_block_size": 21,
    "bootstrap_samples": 2000,
    "bootstrap_seed": 42,
    "confidence_level": 0.95,
    "minimum_mature_observations": 8,
}


def _spec_digest(spec):
    return canonical_json_digest({
        key: value for key, value in dict(spec).items()
        if key != "comparison_spec_sha256"
    })


def create_comparison_spec(requested_universe, *, universe_source_sha256, code_revision):
    """Create the one permitted forward-only comparison specification."""
    universe = sorted(set(str(ticker).strip().upper() for ticker in requested_universe if ticker))
    if not universe:
        raise ValueError("Comparison specification requires a requested universe")
    policy = load_research_policy()
    spec = {
        "schema_version": SPEC_VERSION,
        "comparison_id": "production-gmv-policy-forward-v1",
        "evidence_status": "forward_only_no_untouched_historical_evidence",
        "historical_backfill_allowed": False,
        "policies": list(POLICIES),
        "production_baseline": policy["production_baseline"],
        "requested_universe": universe,
        "requested_universe_sha256": canonical_json_digest(universe),
        "universe_source": "snp.csv current snapshot frozen at registration",
        "universe_source_sha256": str(universe_source_sha256),
        "data_contract": {
            "source": "yfinance_adjusted_close",
            "base_currency": "USD",
            "auto_adjust": True,
            "unit_semantics": "synthetic_fractional_total_return_units",
            "eligible_universe_policy": "formation_504_observation_coverage_then_frozen",
            "missing_price_policy": "no_partial_trade_retry_after_due_date",
        },
        "settings": dict(DEFAULTS),
        "constraints": {
            "long_only": True,
            "max_asset_weight": DEFAULTS["max_asset_weight"],
            "asset_constraints": [],
            "group_constraints": [],
            "min_holding_weight": DEFAULTS["min_holding_weight"],
        },
        "statistics": {
            "primary_endpoint": "realized_annual_volatility",
            "paired_comparisons": [
                ["fixed_target", "buy_and_hold"],
                ["rolling_reoptimization", "buy_and_hold"],
                ["rolling_reoptimization", "fixed_target"],
            ],
            "method": "paired_circular_block_bootstrap",
            "block_size": DEFAULTS["bootstrap_block_size"],
            "samples": DEFAULTS["bootstrap_samples"],
            "seed": DEFAULTS["bootstrap_seed"],
            "confidence_level": DEFAULTS["confidence_level"],
            "multiple_testing": "holm_bonferroni_one_sided_volatility",
            "conflict_policy": "inconclusive",
        },
        "code_revision": str(code_revision),
        "no_automatic_promotion": True,
        "manual_review_only": True,
    }
    spec["comparison_spec_sha256"] = _spec_digest(spec)
    return spec


def validate_comparison_spec(spec):
    payload = copy.deepcopy(dict(spec or {}))
    if int(payload.get("schema_version", 0)) != SPEC_VERSION:
        raise ValueError("Unsupported GMV comparison specification version")
    if tuple(payload.get("policies") or ()) != POLICIES:
        raise ValueError("GMV comparison policies changed")
    if payload.get("production_baseline") != load_research_policy()["production_baseline"]:
        raise ValueError("GMV comparison production baseline changed")
    if payload.get("historical_backfill_allowed") is not False:
        raise ValueError("Historical backfill must remain forbidden")
    settings = dict(payload.get("settings") or {})
    for key, expected in DEFAULTS.items():
        if settings.get(key) != expected:
            raise ValueError(f"GMV comparison setting changed: {key}")
    universe = list(payload.get("requested_universe") or [])
    if universe != sorted(set(universe)) or not universe:
        raise ValueError("Requested universe must be non-empty, sorted, and unique")
    if payload.get("requested_universe_sha256") != canonical_json_digest(universe):
        raise ValueError("Requested universe hash mismatch")
    if payload.get("no_automatic_promotion") is not True:
        raise ValueError("Automatic promotion must remain disabled")
    actual = _spec_digest(payload)
    if payload.get("comparison_spec_sha256") != actual:
        raise ValueError("GMV comparison specification hash mismatch")
    return payload


def _result_digest(result):
    return canonical_json_digest(copy.deepcopy(dict(result or {})))


def _weights(result):
    values = {str(k): float(v) for k, v in dict(result.get("weights") or {}).items()}
    if not values or any(not np.isfinite(v) or v < -1e-12 for v in values.values()):
        raise ValueError("Production GMV returned invalid weights")
    cash = float(result.get("cash_weight", 1.0 - sum(values.values())))
    if not np.isfinite(cash) or cash < -1e-12 or abs(sum(values.values()) + cash - 1.0) > 1e-6:
        raise ValueError("Production GMV weights and cash must sum to one")
    return values, max(0.0, cash)


def _validate_optimizer_pair(first, second, spec, *, frozen_universe=None):
    for result in (first, second):
        if "error" in result:
            raise ValueError(str(result["error"]))
        if result.get("optimization_method") != "MIN_VARIANCE":
            raise ValueError("Comparison requires production MIN_VARIANCE")
        if result.get("forecast_method_effective") != "RISK_ONLY":
            raise ValueError("Comparison requires effective RISK_ONLY")
        if result.get("forecast_bypassed") is not True:
            raise ValueError("Comparison requires forecast bypass")
        if (result.get("optimizer_controls") or {}).get("solver_objective") != "ledoit_wolf_minimum_variance":
            raise ValueError("Comparison requires unregularized Ledoit-Wolf GMV")
    first_weights, first_cash = _weights(first)
    second_weights, second_cash = _weights(second)
    all_tickers = set(first_weights) | set(second_weights)
    max_difference = max(
        [abs(first_weights.get(t, 0.0) - second_weights.get(t, 0.0)) for t in all_tickers]
        + [abs(first_cash - second_cash)]
    )
    first_hash = _result_digest(first)
    second_hash = _result_digest(second)
    first_data = (first.get("market_data_provenance") or {}).get("data_sha256")
    second_data = (second.get("market_data_provenance") or {}).get("data_sha256")
    if first_hash != second_hash or first_data != second_data or max_difference > 1e-12:
        raise ValueError("Production GMV deterministic rerun failed")
    eligibility = dict(first.get("data_eligibility") or {})
    eligible = sorted(set(map(str, eligibility.get("eligible_tickers") or first_weights)))
    if frozen_universe is not None and eligible != sorted(frozen_universe):
        raise ValueError("Frozen eligible universe coverage changed")
    context = dict(first.get("_observation_context") or {})
    covariance = pd.DataFrame(context.get("covariance") or {}, dtype=float)
    if covariance.empty:
        raise ValueError("Production observation covariance is missing")
    row_count = int((first.get("market_data_provenance") or {}).get("row_count", 0))
    if row_count != int(spec["settings"]["train_window"]):
        raise ValueError(
            f"Comparison requires exactly {spec['settings']['train_window']} training observations; got {row_count}"
        )
    return {
        "weights": first_weights,
        "cash_weight": first_cash,
        "eligible_universe": eligible,
        "covariance": covariance,
        "first_result_sha256": first_hash,
        "rerun_result_sha256": second_hash,
        "data_sha256": first_data,
        "max_weight_difference": max_difference,
    }


def _constraint_model(result, eligible, spec):
    controls = dict(result.get("optimizer_controls") or {})
    return prepare_constraint_model(
        eligible,
        max_asset_weight=spec["constraints"]["max_asset_weight"],
        asset_constraints=controls.get("asset_constraints") or [],
        group_constraints=controls.get("group_constraints") or [],
        classifications=(result.get("classification_metadata") or {}).get("securities", {}),
        min_holding_weight=spec["constraints"]["min_holding_weight"],
    )


def _execute_policy(
    policy_id,
    quantities,
    cash,
    prices,
    target_weights,
    target_cash,
    covariance,
    constraint_model,
    settings,
    *,
    initial=False,
    action="rebalance",
    immutable_target=None,
):
    tickers = sorted(prices)
    price_series = pd.Series(prices, dtype=float).reindex(tickers)
    quantity_series = pd.Series(quantities or {}, dtype=float).reindex(tickers).fillna(0.0)
    if price_series.isna().any() or (price_series <= 0.0).any():
        raise ValueError("Full frozen-universe prices are required; partial trade forbidden")
    current_values = quantity_series * price_series
    pre_trade_wealth = float(current_values.sum() + float(cash))
    if pre_trade_wealth <= 0.0:
        raise ValueError("Policy pre-trade wealth must be positive")
    raw_target_values = pd.Series(target_weights, dtype=float).reindex(tickers).fillna(0.0) * pre_trade_wealth
    if action == "observe_only":
        controlled_values = current_values.copy()
        controls = {
            "turnover": 0.0,
            "controlled_turnover": 0.0,
            "skipped_trade_count": 0,
            "turnover_cap_hit": False,
            "initial_allocation": False,
        }
    else:
        controlled_values, controls = apply_trade_controls(
            current_values,
            raw_target_values,
            portfolio_value=pre_trade_wealth,
            rebalance_band=0.0 if initial else settings["rebalance_band"],
            max_turnover=None if initial else settings["max_turnover"],
        )
        controls["initial_allocation"] = bool(initial)
    executed_values, cost, post_cost_wealth, executed_cash, funding = _fund_transaction_cost(
        current_values,
        controlled_values,
        pre_trade_wealth,
        settings["transaction_cost_bps"],
    )
    executed_values = executed_values.reindex(tickers).fillna(0.0)
    executed_quantities = (executed_values / price_series).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    executed_weights = executed_values / post_cost_wealth
    cash_weight = float(executed_cash / post_cost_wealth)
    risk = portfolio_risk_diagnostics(executed_weights.to_dict(), covariance)
    annual_volatility = risk.get("portfolio_risk")
    if annual_volatility is None or not np.isfinite(float(annual_volatility)):
        raise ValueError("Policy risk forecast could not be calculated")
    target_series = pd.Series(target_weights, dtype=float).reindex(tickers).fillna(0.0)
    target_deviation = float((executed_weights - target_series).abs().sum() + abs(cash_weight - target_cash))
    target_constraints = constraint_diagnostics(target_series.to_dict(), constraint_model, cash_weight=target_cash)
    holding_constraints = constraint_diagnostics(executed_weights.to_dict(), constraint_model, cash_weight=cash_weight)
    traded = float((executed_values - current_values).abs().sum())
    turnover = traded / pre_trade_wealth
    checks = {
        "holding_value_identity": all(
            abs(executed_quantities[t] * price_series[t] - executed_values[t]) <= max(1e-8, pre_trade_wealth * 1e-12)
            for t in tickers
        ),
        "turnover_identity": abs(turnover - float(funding["controlled_turnover"])) <= 1e-10,
        "transaction_cost_identity": abs(cost - traded * settings["transaction_cost_bps"] / 10000.0) <= 1e-10,
        "wealth_identity": abs(post_cost_wealth - (pre_trade_wealth - cost)) <= 1e-10,
        "post_cost_holdings_identity": abs(float(executed_values.sum()) + executed_cash - post_cost_wealth) <= 1e-8,
        "weight_cash_identity": abs(float(executed_weights.sum()) + cash_weight - 1.0) <= 1e-10,
        "long_only": bool((executed_values >= -1e-12).all() and executed_cash >= -1e-12),
        "turnover_cap": bool(initial or turnover <= settings["max_turnover"] + 1e-10),
        # Buy-and-hold has no decision target after formation. Price drift may
        # cross a cap and is reported separately instead of inventing a trade.
        "target_constraints": bool(
            action == "observe_only" or target_constraints["all_satisfied"]
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError("Policy accounting failed: " + ", ".join(failed))
    return {
        "policy_id": policy_id,
        "action": action,
        "pre_trade_quantities": {t: float(quantity_series[t]) for t in tickers},
        "pre_trade_notionals": {t: float(current_values[t]) for t in tickers},
        "pre_trade_cash": float(cash),
        "pre_trade_wealth": pre_trade_wealth,
        "target_weights": {t: float(target_series[t]) for t in tickers},
        "target_cash_weight": float(target_cash),
        "immutable_target": copy.deepcopy(immutable_target),
        "executed_quantities": {t: float(executed_quantities[t]) for t in tickers},
        "executed_notionals": {t: float(executed_values[t]) for t in tickers},
        "executed_cash": float(executed_cash),
        "post_cost_wealth": float(post_cost_wealth),
        "weights": {t: float(executed_weights[t]) for t in tickers},
        "cash_weight": cash_weight,
        "gross_traded_notional": traded,
        "turnover": turnover,
        "transaction_cost_rate": settings["transaction_cost_bps"] / 10000.0,
        "transaction_cost": float(cost),
        "prices": {t: float(price_series[t]) for t in tickers},
        "risk_forecast": {"annual_volatility": float(annual_volatility), "source": "current_ledoit_wolf_covariance"},
        "target_l1_deviation": target_deviation,
        "concentration_hhi": float((executed_weights ** 2).sum()),
        "target_constraint_diagnostics": target_constraints,
        "holding_constraint_diagnostics": holding_constraints,
        "holding_drift_violation": not bool(holding_constraints["all_satisfied"]),
        "solver_fallback_count": 0,
        "controls": controls,
        "checks": checks,
    }


def build_comparison_observation(
    campaign,
    spec,
    optimizer_result,
    rerun_result,
    *,
    as_of_timestamp,
    prior_observation=None,
):
    """Build one policy-state transition without writing the ledger."""
    spec = validate_comparison_spec(spec)
    as_of = pd.Timestamp(as_of_timestamp)
    if as_of.tz is None:
        raise ValueError("as_of_timestamp must be timezone-aware")
    prior = dict(prior_observation or {})
    frozen = prior.get("eligible_universe") or None
    verified = _validate_optimizer_pair(
        optimizer_result,
        rerun_result,
        spec,
        frozen_universe=frozen,
    )
    if prior:
        prior_through = (prior.get("data_provenance") or {}).get("available_through")
        observation_dates = list(
            (optimizer_result.get("_observation_context") or {}).get("observation_dates") or []
        )
        if prior_through and observation_dates:
            elapsed = sum(
                pd.Timestamp(value).date() > pd.Timestamp(prior_through).date()
                for value in observation_dates
            )
            required = int(spec["settings"]["rebalance_frequency"])
            if elapsed < required:
                raise RebalanceNotDue(
                    f"Rebalance not due: {elapsed} of {required} trading observations elapsed"
                )
    eligible = verified["eligible_universe"]
    prices = {str(k): float(v) for k, v in dict(optimizer_result.get("prices") or {}).items() if str(k) in eligible}
    missing = sorted(t for t in eligible if t not in prices or not np.isfinite(prices[t]) or prices[t] <= 0.0)
    if missing:
        raise ValueError("Missing frozen-universe execution prices: " + ", ".join(missing))
    model = _constraint_model(optimizer_result, eligible, spec)
    settings = spec["settings"]
    raw_weights = verified["weights"]
    raw_cash = verified["cash_weight"]
    if not prior:
        initial = _execute_policy(
            "initial_shared_allocation",
            {},
            settings["initial_wealth"],
            prices,
            raw_weights,
            raw_cash,
            verified["covariance"],
            model,
            settings,
            initial=True,
            immutable_target={
                "weights": raw_weights,
                "cash_weight": raw_cash,
                "sha256": canonical_json_digest({"weights": raw_weights, "cash_weight": raw_cash}),
            },
        )
        policies = {}
        for policy_id in POLICIES:
            policies[policy_id] = copy.deepcopy(initial)
            policies[policy_id]["policy_id"] = policy_id
            policies[policy_id]["action"] = "initial_shared_allocation"
    else:
        previous = dict(prior.get("policies") or {})
        if set(previous) != set(POLICIES):
            raise ValueError("Prior comparison observation is missing policy state")
        immutable = copy.deepcopy(previous["fixed_target"].get("immutable_target"))
        if not immutable:
            raise ValueError("Fixed target immutable state is missing")
        policies = {}
        for policy_id in POLICIES:
            old = previous[policy_id]
            quantities = old["executed_quantities"]
            cash = old["executed_cash"]
            if policy_id == "buy_and_hold":
                notionals = {t: float(quantities.get(t, 0.0)) * prices[t] for t in eligible}
                wealth = sum(notionals.values()) + float(cash)
                current_weights = {t: notionals[t] / wealth for t in eligible}
                target_weights = current_weights
                target_cash = float(cash) / wealth
                action = "observe_only"
            elif policy_id == "fixed_target":
                target_weights = immutable["weights"]
                target_cash = immutable["cash_weight"]
                action = "rebalance_to_immutable_target"
            else:
                target_weights = raw_weights
                target_cash = raw_cash
                action = "rolling_production_gmv"
            policies[policy_id] = _execute_policy(
                policy_id,
                quantities,
                cash,
                prices,
                target_weights,
                target_cash,
                verified["covariance"],
                model,
                settings,
                action=action,
                immutable_target=immutable,
            )
            if policy_id == "buy_and_hold":
                reference = immutable
                actual = policies[policy_id]
                actual_weights = pd.Series(actual["weights"], dtype=float)
                reference_weights = pd.Series(reference["weights"], dtype=float).reindex(actual_weights.index).fillna(0.0)
                actual["target_l1_deviation"] = float(
                    (actual_weights - reference_weights).abs().sum()
                    + abs(actual["cash_weight"] - reference["cash_weight"])
                )
    provenance = dict(optimizer_result.get("market_data_provenance") or {})
    requested = spec["requested_universe"]
    return {
        "contract_version": 3,
        "campaign_id": campaign["campaign_id"],
        "comparison_spec_sha256": spec["comparison_spec_sha256"],
        "as_of_timestamp": as_of.tz_convert("UTC").isoformat(),
        "status": "complete",
        "requested_universe": requested,
        "eligible_universe": eligible,
        "data_provenance": {
            **provenance,
            "coverage": len(eligible) / len(requested),
            "missing_tickers": sorted(set(requested) - set(eligible)),
        },
        "common_prices": prices,
        "common_covariance_sha256": canonical_json_digest(
            verified["covariance"].sort_index().sort_index(axis=1).to_dict()
        ),
        "optimizer_rerun": {
            "first_result_sha256": verified["first_result_sha256"],
            "rerun_result_sha256": verified["rerun_result_sha256"],
            "max_weight_difference": verified["max_weight_difference"],
            "passed": True,
        },
        "policies": policies,
        "no_automatic_promotion": True,
    }


def build_failed_comparison_observation(
    campaign,
    spec,
    *,
    as_of_timestamp,
    error,
    status="calculation_failure",
    prior_observation=None,
    optimizer_result=None,
):
    """Preserve a no-trade retry record without advancing the complete state."""
    spec = validate_comparison_spec(spec)
    if status not in {"network_failure", "data_missing", "calculation_failure"}:
        raise ValueError("Unsupported comparison failure status")
    prior = dict(prior_observation or {})
    result = dict(optimizer_result or {})
    eligibility = dict(result.get("data_eligibility") or {})
    eligible = list(prior.get("eligible_universe") or eligibility.get("eligible_tickers") or [])
    requested = list(spec["requested_universe"])
    eligible = sorted(set(map(str, eligible)).intersection(requested))
    provenance = dict(result.get("market_data_provenance") or {})
    provenance.update({
        "coverage": len(eligible) / len(requested),
        "missing_tickers": sorted(set(requested) - set(eligible)),
        "failure_status": status,
        "error": str(error),
        "no_trade": True,
        "retry_from_last_complete": prior.get("as_of_timestamp"),
    })
    as_of = pd.Timestamp(as_of_timestamp)
    if as_of.tz is None:
        raise ValueError("as_of_timestamp must be timezone-aware")
    return {
        "contract_version": 3,
        "campaign_id": campaign["campaign_id"],
        "comparison_spec_sha256": spec["comparison_spec_sha256"],
        "as_of_timestamp": as_of.tz_convert("UTC").isoformat(),
        "status": status,
        "requested_universe": requested,
        "eligible_universe": eligible,
        "data_provenance": provenance,
        "policies": None,
        "no_automatic_promotion": True,
    }


def collect_live_comparison_inputs(spec, *, as_of_timestamp, optimizer=optimize_portfolio):
    """Run production GMV twice for an exact preselected 504-row window."""
    spec = validate_comparison_spec(spec)
    as_of = pd.Timestamp(as_of_timestamp)
    if as_of.tz is None:
        raise ValueError("as_of_timestamp must be timezone-aware")
    end_date = (as_of.tz_convert("UTC").date() + timedelta(days=1)).isoformat()
    # A broad discovery call exposes only opt-in observation dates. The target
    # is then recomputed twice on the exact final 504 observations.
    start_date = (as_of.date() - timedelta(days=760)).isoformat()
    args = {
        "start_date": start_date,
        "end_date": end_date,
        "risk_free_rate": spec["settings"]["risk_free_rate"],
        "tickers": spec["requested_universe"],
        "forecast_method": "RISK_ONLY",
        "optimization_method": "MIN_VARIANCE",
        "forecast_horizon": spec["settings"]["outcome_horizon"],
        "min_history": spec["settings"]["train_window"],
        "max_asset_weight": spec["settings"]["max_asset_weight"],
        "min_holding_weight": spec["settings"]["min_holding_weight"],
        "persist_result": False,
        "load_if_available": False,
        "l2_gamma": 0.0,
        "turnover_penalty": 0.0,
        "include_observation_context": True,
    }
    discovery = optimizer(**args)
    if "error" in discovery:
        return discovery, copy.deepcopy(discovery)
    dates = list((discovery.get("_observation_context") or {}).get("observation_dates") or [])
    window = int(spec["settings"]["train_window"])
    if len(dates) < window:
        raise ValueError(f"Live comparison requires {window} aligned observations; got {len(dates)}")
    args["start_date"] = dates[-window]
    first = optimizer(**args)
    second = optimizer(**args)
    return first, second


def load_spec(path):
    return validate_comparison_spec(json.loads(Path(path).read_text(encoding="utf-8")))
