"""Build auditable shadow observations from the production GMV optimizer."""

import copy
from datetime import timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from portfolio_constraints import constraint_diagnostics, prepare_constraint_model
from portfolio_optimization import (
    _fund_transaction_cost,
    get_ticker_group,
    optimize_portfolio,
)
from portfolio_risk_models import portfolio_risk_diagnostics
from research_split import canonical_json_digest
from shadow_forward import get_campaign


BASELINE_FIELDS = {
    "optimization_method": "MIN_VARIANCE",
    "forecast_method_effective": "RISK_ONLY",
    "covariance_estimator": "ledoit_wolf",
}


def _finite_weights(value):
    weights = {
        str(ticker).upper(): float(weight)
        for ticker, weight in dict(value or {}).items()
    }
    if any(not np.isfinite(weight) or weight < 0.0 for weight in weights.values()):
        raise ValueError("Optimizer returned non-finite or negative weights")
    return weights


def _result_digest(result):
    return canonical_json_digest(copy.deepcopy(dict(result or {})))


def _requested_from_run_spec(run_spec):
    requested = list(run_spec.get("tickers") or [])
    if not requested and run_spec.get("ticker_group"):
        requested = get_ticker_group(run_spec["ticker_group"])
    return sorted(set(str(ticker).strip().upper() for ticker in requested if ticker))


def _optimizer_arguments(run_spec, campaign, as_of):
    spec = dict(run_spec or {})
    forbidden = {
        "optimization_method",
        "forecast_method",
        "persist_result",
        "load_if_available",
        "portfolio_id",
        "end_date",
        "include_observation_context",
        "target_return",
        "risk_tolerance",
        "l2_gamma",
        "turnover_penalty",
    } & set(spec)
    if forbidden:
        raise ValueError(
            "Baseline run specification cannot override: "
            + ", ".join(sorted(forbidden))
        )
    if not spec.get("tickers") and not spec.get("ticker_group"):
        raise ValueError("Baseline run specification requires tickers or ticker_group")
    start_date = spec.pop("start_date", None)
    if not start_date:
        raise ValueError("Baseline run specification requires start_date")
    end_date = (as_of.date() + timedelta(days=1)).isoformat()
    conditions = dict(campaign.get("execution_conditions") or {})
    current_weights = spec.get("current_weights")
    if current_weights:
        spec.setdefault("rebalance_band", conditions.get("rebalance_band"))
        spec.setdefault("max_turnover", conditions.get("max_turnover"))
    return {
        **spec,
        "start_date": str(start_date),
        "end_date": end_date,
        "risk_free_rate": float(spec.get("risk_free_rate", 0.0)),
        "optimization_method": "MIN_VARIANCE",
        "forecast_method": "RISK_ONLY",
        "persist_result": False,
        "load_if_available": False,
        "l2_gamma": 0.0,
        "turnover_penalty": 0.0,
        "target_return": None,
        "risk_tolerance": None,
        "include_observation_context": True,
    }


def _failure_observation(campaign, run_spec, result, as_of):
    eligibility = dict(result.get("data_eligibility") or {})
    requested = eligibility.get("requested_tickers") or _requested_from_run_spec(run_spec)
    eligible = eligibility.get("eligible_tickers") or []
    provenance = dict(result.get("market_data_provenance") or {})
    provenance.setdefault("source", "yfinance_adjusted_close")
    provenance.setdefault("coverage", 0.0 if not requested else len(eligible) / len(requested))
    provenance.setdefault("missing_tickers", sorted(set(requested) - set(eligible)))
    status = provenance.get("status")
    if status not in {"network_failure", "data_missing", "calculation_failure"}:
        status = "calculation_failure" if eligible else "data_missing"
    provenance["status"] = status
    provenance["error"] = result.get("error")
    provenance["error_code"] = result.get("error_code")
    return {
        "contract_version": 2,
        "campaign_id": campaign["campaign_id"],
        "as_of_timestamp": as_of.isoformat(),
        "status": status,
        "requested_universe": requested,
        "eligible_universe": eligible,
        "data_provenance": provenance,
        "baseline": None,
        "candidate": None,
    }


def build_production_baseline_observation(
    campaign,
    run_spec,
    optimizer_result,
    rerun_result,
    *,
    as_of_timestamp,
):
    """Convert two production optimizer results into one baseline-only contract."""
    campaign = dict(campaign or {})
    as_of = pd.Timestamp(as_of_timestamp)
    if as_of.tz is None:
        raise ValueError("as_of_timestamp must be timezone-aware")
    as_of = as_of.tz_convert("UTC")
    result = dict(optimizer_result or {})
    rerun = dict(rerun_result or {})
    if "error" in result:
        return _failure_observation(campaign, run_spec, result, as_of)
    if "error" in rerun:
        failed = _failure_observation(campaign, run_spec, rerun, as_of)
        failed["data_provenance"]["error"] = "Deterministic rerun failed: " + str(rerun["error"])
        return failed

    baseline_spec = campaign.get("baseline_specification") or {}
    for field, expected in BASELINE_FIELDS.items():
        actual = result.get(field)
        if actual is None and field == "covariance_estimator":
            actual = "ledoit_wolf"
        if actual != expected or baseline_spec.get(field) != expected:
            raise ValueError(f"Production baseline mismatch for {field}")
    controls = dict(result.get("optimizer_controls") or {})
    if controls.get("solver_objective") != "ledoit_wolf_minimum_variance":
        raise ValueError("Production baseline must use unregularized Ledoit-Wolf GMV")
    if result.get("forecast_bypassed") is not True:
        raise ValueError("Production baseline must bypass forecasts")
    if controls.get("l2_gamma", 0.0) != 0.0 or controls.get("turnover_penalty", 0.0) != 0.0:
        raise ValueError("Production baseline cannot use regularization or turnover penalty")

    eligibility = dict(result.get("data_eligibility") or {})
    requested = eligibility.get("requested_tickers") or _requested_from_run_spec(run_spec)
    eligible = eligibility.get("eligible_tickers") or list(result.get("weights") or {})
    requested = sorted(set(map(str, requested)))
    eligible = sorted(set(map(str, eligible)))
    provenance = dict(result.get("market_data_provenance") or {})
    if not provenance.get("data_sha256"):
        raise ValueError("Optimizer result is missing the market-data hash")

    target_weights = _finite_weights(result.get("weights"))
    target_cash = float(result.get("cash_weight", 1.0 - sum(target_weights.values())))
    if (
        not np.isfinite(target_cash)
        or target_cash < 0.0
        or abs(sum(target_weights.values()) + target_cash - 1.0) > 1e-6
    ):
        raise ValueError("Optimizer weights and cash must sum to one")
    current_weights = _finite_weights(run_spec.get("current_weights"))
    transaction_cost_bps = float(
        (campaign.get("execution_conditions") or {}).get("transaction_cost_bps", 0.0)
    )
    executed_values, transaction_cost, post_cost_wealth, executed_cash, funding = (
        _fund_transaction_cost(current_weights, target_weights, 1.0, transaction_cost_bps)
    )
    if post_cost_wealth <= 0.0:
        raise ValueError("Production baseline execution has no post-cost wealth")
    executed_weights = {
        str(ticker): float(value / post_cost_wealth)
        for ticker, value in executed_values.items()
        if value > 1e-12
    }
    cash_weight = float(executed_cash / post_cost_wealth)

    context = dict(result.get("_observation_context") or {})
    covariance = pd.DataFrame(context.get("covariance") or {}, dtype=float)
    risk = portfolio_risk_diagnostics(executed_weights, covariance)
    annual_volatility = risk.get("portfolio_risk")
    if annual_volatility is None or not np.isfinite(float(annual_volatility)):
        raise ValueError("Production baseline risk could not be recomputed")

    classifications = dict(result.get("classification_metadata") or {}).get("securities", {})
    model = prepare_constraint_model(
        eligible,
        max_asset_weight=controls.get("requested_max_asset_weight"),
        asset_constraints=controls.get("asset_constraints"),
        group_constraints=controls.get("group_constraints"),
        classifications=classifications,
        min_holding_weight=controls.get("min_holding_weight", 0.0),
    )
    constraint_check = constraint_diagnostics(
        executed_weights,
        model,
        cash_weight=cash_weight,
    )

    prices = {str(k): float(v) for k, v in dict(result.get("prices") or {}).items()}
    missing_prices = sorted(
        ticker for ticker in eligible
        if not np.isfinite(prices.get(ticker, np.nan)) or prices.get(ticker, 0.0) <= 0.0
    )
    price_coverage = 1.0 if not eligible else (len(eligible) - len(missing_prices)) / len(eligible)
    first_digest = _result_digest(result)
    rerun_digest = _result_digest(rerun)
    rerun_weights = _finite_weights(rerun.get("weights"))
    all_tickers = sorted(set(target_weights) | set(rerun_weights))
    max_weight_diff = max(
        [abs(target_weights.get(ticker, 0.0) - rerun_weights.get(ticker, 0.0)) for ticker in all_tickers]
        or [0.0]
    )
    deterministic = (
        first_digest == rerun_digest
        and provenance.get("data_sha256")
        == (rerun.get("market_data_provenance") or {}).get("data_sha256")
        and max_weight_diff <= 1e-12
    )

    status = "complete"
    if provenance.get("status") == "partial" or price_coverage < 1.0:
        status = "partial"
    return {
        "contract_version": 2,
        "campaign_id": campaign["campaign_id"],
        "as_of_timestamp": as_of.isoformat(),
        "status": status,
        "requested_universe": requested,
        "eligible_universe": eligible,
        "data_provenance": provenance,
        "baseline": {
            "optimization_method": "MIN_VARIANCE",
            "forecast_method_effective": "RISK_ONLY",
            "covariance_estimator": "ledoit_wolf",
            "forecast_bypassed": True,
            "signal": {"status": "no_view", "scores": {}},
            "weights": executed_weights,
            "cash_weight": cash_weight,
            "risk_forecast": {
                "annual_volatility": float(annual_volatility),
                "source": "optimizer_ledoit_wolf_covariance_recalculation",
            },
            "execution": {
                "reference_wealth": 1.0,
                "post_cost_wealth": float(post_cost_wealth),
                "current_notionals": current_weights,
                "executed_notionals": {str(k): float(v) for k, v in executed_values.items()},
                "executed_cash": float(executed_cash),
                "traded_notional": float(funding["controlled_trade_value"]),
                "turnover": float(funding["controlled_turnover"]),
                "transaction_cost_rate": transaction_cost_bps / 10_000.0,
                "transaction_cost": float(transaction_cost),
                "prices": prices,
                "price_coverage": float(price_coverage),
                "missing_price_tickers": missing_prices,
                "constraint_specification": {
                    "max_asset_weight": controls.get("requested_max_asset_weight"),
                    "asset_constraints": controls.get("asset_constraints") or [],
                    "group_constraints": controls.get("group_constraints") or [],
                    "min_holding_weight": controls.get("min_holding_weight", 0.0),
                    "classifications": classifications,
                },
                "constraint_diagnostics": constraint_check,
                "deterministic_rerun": {
                    "passed": deterministic,
                    "first_result_sha256": first_digest,
                    "rerun_result_sha256": rerun_digest,
                    "same_data_sha256": provenance.get("data_sha256")
                    == (rerun.get("market_data_provenance") or {}).get("data_sha256"),
                    "max_weight_difference": float(max_weight_diff),
                },
            },
        },
        "candidate": None,
    }


def collect_production_baseline_observation(
    ledger_path,
    campaign_id,
    run_spec,
    *,
    scheduled_for=None,
    now=None,
    optimizer=optimize_portfolio,
):
    """Run the production optimizer twice, without placing orders or writing the ledger."""
    campaign = get_campaign(ledger_path, campaign_id)
    instant = pd.Timestamp(scheduled_for or now or pd.Timestamp.now(tz="UTC"))
    if instant.tz is None:
        raise ValueError("scheduled_for must be timezone-aware")
    local = instant.tz_convert(ZoneInfo(campaign.get("timezone", "UTC")))
    args = _optimizer_arguments(run_spec, campaign, local)
    try:
        first = optimizer(**args)
        second = optimizer(**args)
        return build_production_baseline_observation(
            campaign,
            run_spec,
            first,
            second,
            as_of_timestamp=instant,
        )
    except Exception as exc:
        source = dict(locals().get("first") or {})
        source["error"] = str(exc)
        source["error_code"] = "BASELINE_COLLECTION_FAILED"
        provenance = dict(source.get("market_data_provenance") or {})
        provenance["status"] = "calculation_failure"
        source["market_data_provenance"] = provenance
        return _failure_observation(campaign, run_spec, source, instant)
