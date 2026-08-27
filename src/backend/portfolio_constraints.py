"""Production portfolio hard-constraint validation and diagnostics."""

import re

import numpy as np
import pandas as pd
from scipy.optimize import linprog

try:
    import cvxpy as cp
except Exception:  # pragma: no cover - PyPortfolioOpt normally installs cvxpy.
    cp = None


VALID_GROUP_DIMENSIONS = {"sector", "industry", "country"}
TICKER_PATTERN = re.compile(r"^[A-Z0-9.^=\-]{1,24}$")
TOLERANCE = 1e-7


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        if np.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    return value


class ConstraintValidationError(ValueError):
    """A user-safe, structured portfolio constraint error."""

    def __init__(
        self,
        code,
        message,
        *,
        constraint=None,
        requested_value=None,
        feasible_bound=None,
        affected_tickers=None,
        affected_groups=None,
    ):
        super().__init__(message)
        self.payload = _json_safe({
            "error": message,
            "error_code": code,
            "constraint": constraint,
            "requested_value": requested_value,
            "feasible_bound": feasible_bound,
            "affected_tickers": sorted(set(affected_tickers or [])),
            "affected_groups": sorted(set(affected_groups or [])),
        })

    def to_dict(self):
        return dict(self.payload)


def _decimal(value, field, *, optional=True):
    if value is None and optional:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ConstraintValidationError(
            "INVALID_CONSTRAINT",
            f"{field} must be a finite decimal between 0 and 1",
            constraint=field,
            requested_value=value,
            feasible_bound={"min": 0.0, "max": 1.0},
        ) from exc
    if not np.isfinite(parsed) or parsed < 0.0 or parsed > 1.0:
        raise ConstraintValidationError(
            "INVALID_CONSTRAINT",
            f"{field} must be a finite decimal between 0 and 1",
            constraint=field,
            requested_value=value,
            feasible_bound={"min": 0.0, "max": 1.0},
        )
    return parsed


def normalize_asset_constraints(value):
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ConstraintValidationError(
            "INVALID_CONSTRAINT",
            "asset_constraints must be an array",
            constraint="asset_constraints",
            requested_value=value,
        )

    normalized = []
    seen = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ConstraintValidationError(
                "INVALID_CONSTRAINT",
                f"asset_constraints[{index}] must be an object",
                constraint=f"asset_constraints[{index}]",
                requested_value=item,
            )
        ticker = str(item.get("ticker") or "").strip().upper()
        if not TICKER_PATTERN.fullmatch(ticker):
            raise ConstraintValidationError(
                "INVALID_TICKER",
                f"asset_constraints[{index}].ticker is invalid",
                constraint=f"asset_constraints[{index}].ticker",
                requested_value=item.get("ticker"),
                affected_tickers=[ticker] if ticker else [],
            )
        if ticker in seen:
            raise ConstraintValidationError(
                "DUPLICATE_CONSTRAINT",
                f"Duplicate asset constraint for {ticker}",
                constraint="asset_constraints",
                affected_tickers=[ticker],
            )
        seen.add(ticker)
        lower = _decimal(item.get("min_weight"), f"asset_constraints[{index}].min_weight")
        upper = _decimal(item.get("max_weight"), f"asset_constraints[{index}].max_weight")
        if lower is None and upper is None:
            raise ConstraintValidationError(
                "INVALID_CONSTRAINT",
                f"Asset constraint for {ticker} needs min_weight or max_weight",
                constraint="asset_constraints",
                affected_tickers=[ticker],
            )
        if lower is not None and upper is not None and lower > upper + TOLERANCE:
            raise ConstraintValidationError(
                "CONSTRAINT_BOUNDS_CONFLICT",
                f"Minimum weight exceeds maximum weight for {ticker}",
                constraint="asset_constraints",
                requested_value={"min_weight": lower, "max_weight": upper},
                feasible_bound={"min_weight_lte": upper},
                affected_tickers=[ticker],
            )
        normalized.append({"ticker": ticker, "min_weight": lower, "max_weight": upper})
    return normalized


def normalize_group_constraints(value):
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ConstraintValidationError(
            "INVALID_CONSTRAINT",
            "group_constraints must be an array",
            constraint="group_constraints",
            requested_value=value,
        )

    normalized = []
    seen = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ConstraintValidationError(
                "INVALID_CONSTRAINT",
                f"group_constraints[{index}] must be an object",
                constraint=f"group_constraints[{index}]",
                requested_value=item,
            )
        dimension = str(item.get("dimension") or "").strip().lower()
        group = str(item.get("group") or "").strip()
        if dimension not in VALID_GROUP_DIMENSIONS:
            raise ConstraintValidationError(
                "INVALID_CONSTRAINT",
                f"group_constraints[{index}].dimension must be sector, industry, or country",
                constraint=f"group_constraints[{index}].dimension",
                requested_value=item.get("dimension"),
            )
        if not group:
            raise ConstraintValidationError(
                "INVALID_CONSTRAINT",
                f"group_constraints[{index}].group is required",
                constraint=f"group_constraints[{index}].group",
            )
        key = (dimension, group.casefold())
        if key in seen:
            raise ConstraintValidationError(
                "DUPLICATE_CONSTRAINT",
                f"Duplicate {dimension} constraint for {group}",
                constraint="group_constraints",
                affected_groups=[f"{dimension}:{group}"],
            )
        seen.add(key)
        lower = _decimal(item.get("min_weight"), f"group_constraints[{index}].min_weight")
        upper = _decimal(item.get("max_weight"), f"group_constraints[{index}].max_weight")
        if lower is None and upper is None:
            raise ConstraintValidationError(
                "INVALID_CONSTRAINT",
                f"Group constraint for {dimension}:{group} needs min_weight or max_weight",
                constraint="group_constraints",
                affected_groups=[f"{dimension}:{group}"],
            )
        if lower is not None and upper is not None and lower > upper + TOLERANCE:
            raise ConstraintValidationError(
                "CONSTRAINT_BOUNDS_CONFLICT",
                f"Minimum weight exceeds maximum weight for {dimension}:{group}",
                constraint="group_constraints",
                requested_value={"min_weight": lower, "max_weight": upper},
                feasible_bound={"min_weight_lte": upper},
                affected_groups=[f"{dimension}:{group}"],
            )
        normalized.append({
            "dimension": dimension,
            "group": group,
            "min_weight": lower,
            "max_weight": upper,
        })
    return normalized


def normalize_current_weights(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConstraintValidationError(
            "INVALID_CURRENT_WEIGHTS",
            "current_weights must be an object",
            constraint="current_weights",
            requested_value=value,
        )
    normalized = {}
    for raw_ticker, raw_weight in value.items():
        ticker = str(raw_ticker or "").strip().upper()
        if not TICKER_PATTERN.fullmatch(ticker):
            raise ConstraintValidationError(
                "INVALID_TICKER",
                "current_weights contains an invalid ticker",
                constraint="current_weights",
                requested_value=raw_ticker,
                affected_tickers=[ticker] if ticker else [],
            )
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError) as exc:
            raise ConstraintValidationError(
                "INVALID_CURRENT_WEIGHTS",
                f"current_weights.{ticker} must be finite and non-negative",
                constraint="current_weights",
                requested_value=raw_weight,
                affected_tickers=[ticker],
            ) from exc
        if not np.isfinite(weight) or weight < 0.0:
            raise ConstraintValidationError(
                "INVALID_CURRENT_WEIGHTS",
                f"current_weights.{ticker} must be finite and non-negative",
                constraint="current_weights",
                requested_value=raw_weight,
                affected_tickers=[ticker],
            )
        normalized[ticker] = weight
    if sum(normalized.values()) > 1.0 + TOLERANCE:
        raise ConstraintValidationError(
            "INVALID_CURRENT_WEIGHTS",
            "current_weights must sum to at most 1",
            constraint="current_weights",
            requested_value=sum(normalized.values()),
            feasible_bound={"maximum_sum": 1.0},
            affected_tickers=list(normalized),
        )
    return normalized


def _linear_matrices(lower, upper, groups):
    asset_count = len(lower)
    a_ub = []
    b_ub = []
    for group in groups:
        selector = np.zeros(asset_count, dtype=float)
        selector[group["indices"]] = 1.0
        if group["max_weight"] is not None:
            a_ub.append(selector)
            b_ub.append(group["max_weight"])
        if group["min_weight"] is not None:
            a_ub.append(-selector)
            b_ub.append(-group["min_weight"])
    return (
        None if not a_ub else np.asarray(a_ub, dtype=float),
        None if not b_ub else np.asarray(b_ub, dtype=float),
        [(float(lo), float(hi)) for lo, hi in zip(lower, upper)],
    )


def prepare_constraint_model(
    tickers,
    *,
    max_asset_weight=0.2,
    asset_constraints=None,
    group_constraints=None,
    classifications=None,
    expected_returns=None,
    covariance=None,
    target_return=None,
    risk_tolerance=None,
    min_holding_weight=0.0,
    current_weights=None,
    max_turnover=None,
):
    tickers = [str(ticker).upper() for ticker in tickers]
    asset_constraints = normalize_asset_constraints(asset_constraints)
    group_constraints = normalize_group_constraints(group_constraints)
    asset_count = len(tickers)
    cap_was_requested = max_asset_weight is not None
    cap = (
        max(0.2, 1.0 / max(1, asset_count) + 1e-6)
        if max_asset_weight is None
        else _decimal(max_asset_weight, "max_asset_weight", optional=False)
    )
    if cap <= 0.0:
        raise ConstraintValidationError(
            "INVALID_CONSTRAINT",
            "max_asset_weight must be greater than 0",
            constraint="max_asset_weight",
            requested_value=max_asset_weight,
            feasible_bound={"exclusive_min": 0.0, "max": 1.0},
        )
    if cap_was_requested and asset_count * cap < 1.0 - TOLERANCE:
        raise ConstraintValidationError(
            "MAX_ASSET_WEIGHT_INFEASIBLE",
            "max_asset_weight is too low for the eligible asset count",
            constraint="max_asset_weight",
            requested_value=cap,
            feasible_bound={"minimum": 1.0 / max(1, asset_count)},
            affected_tickers=tickers,
        )

    min_holding = _decimal(min_holding_weight, "min_holding_weight", optional=False)
    if min_holding > cap + TOLERANCE:
        raise ConstraintValidationError(
            "MIN_HOLDING_WEIGHT_INFEASIBLE",
            "min_holding_weight exceeds max_asset_weight",
            constraint="min_holding_weight",
            requested_value=min_holding,
            feasible_bound={"maximum": cap},
            affected_tickers=tickers,
        )

    index = {ticker: position for position, ticker in enumerate(tickers)}
    lower = np.zeros(asset_count, dtype=float)
    upper = np.full(asset_count, cap, dtype=float)
    for item in asset_constraints:
        ticker = item["ticker"]
        if ticker not in index:
            raise ConstraintValidationError(
                "CONSTRAINT_TICKER_UNAVAILABLE",
                f"Constrained ticker {ticker} is not in the eligible universe",
                constraint="asset_constraints",
                affected_tickers=[ticker],
            )
        position = index[ticker]
        if item["min_weight"] is not None:
            lower[position] = item["min_weight"]
        if item["max_weight"] is not None:
            upper[position] = min(upper[position], item["max_weight"])
        if lower[position] > upper[position] + TOLERANCE:
            raise ConstraintValidationError(
                "CONSTRAINT_BOUNDS_CONFLICT",
                f"Asset bounds conflict with the common cap for {ticker}",
                constraint="asset_constraints",
                requested_value=item,
                feasible_bound={"maximum": float(upper[position])},
                affected_tickers=[ticker],
            )

    lower_sum = float(lower.sum())
    upper_sum = float(upper.sum())
    if lower_sum > 1.0 + TOLERANCE:
        raise ConstraintValidationError(
            "ASSET_LOWER_BOUNDS_INFEASIBLE",
            "The sum of asset minimum weights exceeds 1",
            constraint="asset_constraints",
            requested_value=lower_sum,
            feasible_bound={"maximum_sum": 1.0},
            affected_tickers=[tickers[i] for i in np.flatnonzero(lower > 0)],
        )
    if upper_sum < 1.0 - TOLERANCE:
        raise ConstraintValidationError(
            "ASSET_UPPER_BOUNDS_INFEASIBLE",
            "The sum of asset maximum weights is below 1",
            constraint="asset_constraints",
            requested_value=upper_sum,
            feasible_bound={"minimum_sum": 1.0},
            affected_tickers=tickers,
        )

    classifications = classifications or {}
    groups = []
    for item in group_constraints:
        dimension = item["dimension"]
        group_name = item["group"]
        missing = [ticker for ticker in tickers if not str(classifications.get(ticker, {}).get(dimension) or "").strip()]
        if missing:
            raise ConstraintValidationError(
                "METADATA_UNAVAILABLE",
                f"Complete {dimension} metadata is required for group constraints",
                constraint="group_constraints",
                affected_tickers=missing,
                affected_groups=[f"{dimension}:{group_name}"],
            )
        members = [
            position
            for position, ticker in enumerate(tickers)
            if str(classifications[ticker][dimension]).strip().casefold() == group_name.casefold()
        ]
        if not members:
            raise ConstraintValidationError(
                "GROUP_NOT_FOUND",
                f"No eligible ticker belongs to {dimension}:{group_name}",
                constraint="group_constraints",
                affected_groups=[f"{dimension}:{group_name}"],
            )
        member_lower = float(lower[members].sum())
        member_upper = float(upper[members].sum())
        if item["min_weight"] is not None and item["min_weight"] > member_upper + TOLERANCE:
            raise ConstraintValidationError(
                "GROUP_LOWER_BOUND_INFEASIBLE",
                f"The minimum weight for {dimension}:{group_name} exceeds its asset capacity",
                constraint="group_constraints",
                requested_value=item["min_weight"],
                feasible_bound={"maximum": member_upper},
                affected_tickers=[tickers[i] for i in members],
                affected_groups=[f"{dimension}:{group_name}"],
            )
        if item["max_weight"] is not None and item["max_weight"] < member_lower - TOLERANCE:
            raise ConstraintValidationError(
                "GROUP_UPPER_BOUND_INFEASIBLE",
                f"The maximum weight for {dimension}:{group_name} conflicts with asset minimums",
                constraint="group_constraints",
                requested_value=item["max_weight"],
                feasible_bound={"minimum": member_lower},
                affected_tickers=[tickers[i] for i in members],
                affected_groups=[f"{dimension}:{group_name}"],
            )
        groups.append({**item, "indices": members, "tickers": [tickers[i] for i in members]})

    a_ub, b_ub, bounds = _linear_matrices(lower, upper, groups)
    feasibility = linprog(
        np.zeros(asset_count),
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=np.ones((1, asset_count)),
        b_eq=np.array([1.0]),
        bounds=bounds,
        method="highs",
    )
    if not feasibility.success:
        raise ConstraintValidationError(
            "CONSTRAINTS_INFEASIBLE",
            "The requested asset and group constraints cannot be satisfied together",
            constraint="hard_constraints",
            affected_tickers=tickers,
            affected_groups=[f"{item['dimension']}:{item['group']}" for item in groups],
        )

    model = {
        "tickers": tickers,
        "lower_bounds": lower,
        "upper_bounds": upper,
        "groups": groups,
        "asset_constraints": asset_constraints,
        "max_asset_weight": cap,
        "max_asset_weight_requested": max_asset_weight,
        "min_holding_weight": min_holding,
    }

    if target_return is not None and expected_returns is not None:
        returns = pd.Series(expected_returns, dtype=float).reindex(tickers).values
        maximum = linprog(
            -returns,
            A_ub=a_ub,
            b_ub=b_ub,
            A_eq=np.ones((1, asset_count)),
            b_eq=np.array([1.0]),
            bounds=bounds,
            method="highs",
        )
        feasible_return = None if not maximum.success else float(-maximum.fun)
        if feasible_return is not None and float(target_return) > feasible_return + TOLERANCE:
            raise ConstraintValidationError(
                "TARGET_RETURN_INFEASIBLE",
                "target_return exceeds the maximum feasible return under the requested constraints",
                constraint="target_return",
                requested_value=float(target_return),
                feasible_bound={"maximum": feasible_return},
                affected_tickers=tickers,
            )

    if risk_tolerance is not None and covariance is not None and cp is not None:
        weights = cp.Variable(asset_count)
        constraints = _cvx_constraints(weights, model)
        matrix = pd.DataFrame(covariance, index=tickers, columns=tickers).values
        problem = cp.Problem(cp.Minimize(cp.quad_form(weights, cp.psd_wrap(matrix))), constraints)
        try:
            problem.solve(warm_start=True)
        except Exception:
            problem = None
        if problem is not None and problem.status in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
            minimum_risk = float(np.sqrt(max(0.0, problem.value)))
            if float(risk_tolerance) < minimum_risk - TOLERANCE:
                raise ConstraintValidationError(
                    "RISK_TOLERANCE_INFEASIBLE",
                    "risk_tolerance is below the minimum feasible portfolio risk",
                    constraint="risk_tolerance",
                    requested_value=float(risk_tolerance),
                    feasible_bound={"minimum": minimum_risk},
                    affected_tickers=tickers,
                )

    if current_weights is not None and max_turnover is not None:
        turnover_cap = float(max_turnover)
        current = pd.Series(current_weights, dtype=float)
        eligible_current = current.reindex(tickers).fillna(0.0).values
        unmodeled_current = current.drop(labels=tickers, errors="ignore")
        unmodeled_required_turnover = float(
            (unmodeled_current - model["max_asset_weight"]).clip(lower=0.0).sum()
        )
        objective = np.concatenate([np.zeros(asset_count), np.ones(asset_count)])
        expanded_a = []
        expanded_b = []
        if a_ub is not None:
            expanded_a.extend(
                np.hstack([a_ub, np.zeros((len(a_ub), asset_count))])
            )
            expanded_b.extend(b_ub)
        expanded_a.append(np.concatenate([np.ones(asset_count), np.zeros(asset_count)]))
        expanded_b.append(1.0)
        for position in range(asset_count):
            row = np.zeros(asset_count * 2)
            row[position] = 1.0
            row[asset_count + position] = -1.0
            expanded_a.append(row)
            expanded_b.append(eligible_current[position])
            row = np.zeros(asset_count * 2)
            row[position] = -1.0
            row[asset_count + position] = -1.0
            expanded_a.append(row)
            expanded_b.append(-eligible_current[position])
        minimum_turnover = linprog(
            objective,
            A_ub=np.asarray(expanded_a, dtype=float),
            b_ub=np.asarray(expanded_b, dtype=float),
            bounds=bounds + [(0.0, None)] * asset_count,
            method="highs",
        )
        if minimum_turnover.success:
            minimum_value = float(minimum_turnover.fun + unmodeled_required_turnover)
            if turnover_cap < minimum_value - TOLERANCE:
                raise ConstraintValidationError(
                    "MAX_TURNOVER_INFEASIBLE",
                    "max_turnover is below the minimum trade required by the hard constraints",
                    constraint="max_turnover",
                    requested_value=turnover_cap,
                    feasible_bound={"minimum": minimum_value},
                    affected_tickers=list(current.index),
                )
    return model


def _cvx_constraints(weights, model):
    constraints = [
        cp.sum(weights) == 1.0,
        weights >= model["lower_bounds"],
        weights <= model["upper_bounds"],
    ]
    for group in model["groups"]:
        actual = cp.sum(weights[group["indices"]])
        if group["min_weight"] is not None:
            constraints.append(actual >= group["min_weight"])
        if group["max_weight"] is not None:
            constraints.append(actual <= group["max_weight"])
    return constraints


def solver_weight_bounds(model):
    return list(zip(model["lower_bounds"], model["upper_bounds"]))


def add_group_constraints(frontier, model):
    for group in model["groups"]:
        selector = np.zeros(len(model["tickers"]), dtype=float)
        selector[group["indices"]] = 1.0
        lower = group["min_weight"]
        upper = group["max_weight"]
        if lower is not None:
            frontier.add_constraint(lambda weights, selector=selector, lower=lower: weights @ selector >= lower)
        if upper is not None:
            frontier.add_constraint(lambda weights, selector=selector, upper=upper: weights @ selector <= upper)


def project_thresholded_weights(weights, model):
    """Project a deterministic min-holding support onto all linear constraints."""
    if cp is None:
        raise ConstraintValidationError(
            "CONSTRAINT_REPAIR_UNAVAILABLE",
            "Constraint-preserving minimum holding cleanup is unavailable",
            constraint="min_holding_weight",
        )
    reference = pd.Series(weights, dtype=float).reindex(model["tickers"]).fillna(0.0).clip(lower=0.0)
    threshold = model["min_holding_weight"]
    active = set(np.flatnonzero(reference.values >= max(threshold, TOLERANCE)))
    active.update(np.flatnonzero(model["lower_bounds"] > TOLERANCE))
    candidates = [index for index in np.argsort(-reference.values) if index not in active]

    while True:
        variable = cp.Variable(len(model["tickers"]))
        constraints = _cvx_constraints(variable, model)
        for position in range(len(model["tickers"])):
            if position not in active:
                constraints.append(variable[position] == 0.0)
            elif threshold > 0.0:
                constraints.append(variable[position] >= max(threshold, model["lower_bounds"][position]))
        problem = cp.Problem(cp.Minimize(cp.sum_squares(variable - reference.values)), constraints)
        try:
            problem.solve(warm_start=True)
        except Exception:
            pass
        if problem.status in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} and variable.value is not None:
            return {
                ticker: float(max(0.0, value))
                for ticker, value in zip(model["tickers"], variable.value)
            }
        if not candidates:
            break
        active.add(candidates.pop(0))
    raise ConstraintValidationError(
        "MIN_HOLDING_WEIGHT_INFEASIBLE",
        "min_holding_weight cannot be satisfied together with the hard constraints",
        constraint="min_holding_weight",
        requested_value=threshold,
        affected_tickers=model["tickers"],
    )


def constraint_diagnostics(weights, model, *, cash_weight=0.0):
    series = pd.Series(weights, dtype=float).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    records = []

    def record(name, actual, lower=None, upper=None, tickers=None, groups=None):
        lower_slack = None if lower is None else float(actual - lower)
        upper_slack = None if upper is None else float(upper - actual)
        satisfied = bool(
            (lower is None or lower_slack >= -TOLERANCE)
            and (upper is None or upper_slack >= -TOLERANCE)
        )
        binding = bool(
            satisfied
            and (
                (lower_slack is not None and abs(lower_slack) <= 1e-5)
                or (upper_slack is not None and abs(upper_slack) <= 1e-5)
            )
        )
        records.append({
            "constraint": name,
            "actual_value": float(actual),
            "lower_bound": lower,
            "upper_bound": upper,
            "lower_slack": lower_slack,
            "upper_slack": upper_slack,
            "binding": binding,
            "satisfied": satisfied,
            "affected_tickers": tickers or [],
            "affected_groups": groups or [],
        })

    risky_total = float(series.sum())
    record("total_weight", risky_total + float(cash_weight), lower=1.0, upper=1.0)
    record(
        "max_asset_weight",
        float(series.max()) if not series.empty else 0.0,
        upper=model["max_asset_weight"],
        tickers=[str(ticker) for ticker in series.index[series == series.max()]] if not series.empty else [],
    )
    for item in model["asset_constraints"]:
        record(
            f"asset:{item['ticker']}",
            float(series.get(item["ticker"], 0.0)),
            lower=item["min_weight"],
            upper=item["max_weight"],
            tickers=[item["ticker"]],
        )
    for item in model["groups"]:
        record(
            f"group:{item['dimension']}:{item['group']}",
            float(series.reindex(item["tickers"]).fillna(0.0).sum()),
            lower=item["min_weight"],
            upper=item["max_weight"],
            tickers=item["tickers"],
            groups=[f"{item['dimension']}:{item['group']}"],
        )
    if model["min_holding_weight"] > 0.0:
        positive = series[series > TOLERANCE]
        record(
            "min_holding_weight",
            float(positive.min()) if not positive.empty else 0.0,
            lower=model["min_holding_weight"] if not positive.empty else None,
            tickers=[str(ticker) for ticker in positive.index],
        )
    violations = [item for item in records if not item["satisfied"]]
    return {
        "status": "satisfied" if not violations else "violated",
        "all_satisfied": not violations,
        "constraints": records,
        "violation_count": len(violations),
    }


def ensure_constraints_satisfied(weights, model, *, cash_weight=0.0):
    diagnostics = constraint_diagnostics(weights, model, cash_weight=cash_weight)
    if diagnostics["all_satisfied"]:
        return diagnostics
    violation = next(item for item in diagnostics["constraints"] if not item["satisfied"])
    raise ConstraintValidationError(
        "POST_CONTROL_CONSTRAINT_VIOLATION",
        "The returned weights would violate a hard constraint after threshold or turnover controls",
        constraint=violation["constraint"],
        requested_value={
            "lower_bound": violation["lower_bound"],
            "upper_bound": violation["upper_bound"],
        },
        feasible_bound={"actual_value": violation["actual_value"]},
        affected_tickers=violation["affected_tickers"],
        affected_groups=violation["affected_groups"],
    )
