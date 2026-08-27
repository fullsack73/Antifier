import json

import numpy as np
import pandas as pd
import pytest

import app as app_module
import portfolio_optimization
from portfolio_constraints import (
    ConstraintValidationError,
    normalize_asset_constraints,
    normalize_current_weights,
    prepare_constraint_model,
)
from portfolio_risk_models import portfolio_risk_diagnostics


TICKERS = ["AAA", "BBB", "CCC", "DDD"]
CLASSIFICATIONS = {
    "AAA": {"name": "AAA", "sector": "Technology", "industry": "Software", "country": "US"},
    "BBB": {"name": "BBB", "sector": "Technology", "industry": "Hardware", "country": "US"},
    "CCC": {"name": "CCC", "sector": "Healthcare", "industry": "Biotech", "country": "US"},
    "DDD": {"name": "DDD", "sector": "Healthcare", "industry": "Medical", "country": "CA"},
}


def _pipeline():
    return {
        "mu": pd.Series({"AAA": 0.12, "BBB": 0.10, "CCC": 0.08, "DDD": 0.06}),
        "prior_mu": pd.Series({"AAA": 0.09, "BBB": 0.08, "CCC": 0.07, "DDD": 0.06}),
        "S": pd.DataFrame(
            np.diag([0.04, 0.03, 0.02, 0.01]),
            index=TICKERS,
            columns=TICKERS,
        ),
        "uncertainties": pd.Series(0.2, index=TICKERS),
        "no_view_tickers": [],
        "tickers": TICKERS,
        "latest_prices": {ticker: 100.0 for ticker in TICKERS},
    }


def _metadata(securities=None, status="complete"):
    securities = CLASSIFICATIONS if securities is None else securities
    return {
        "source": "yfinance.info",
        "as_of": "2026-08-27T00:00:00Z",
        "status": status,
        "requested_tickers": TICKERS,
        "securities": securities,
        "missing_tickers": sorted(set(TICKERS) - set(securities)),
        "coverage": {},
    }


def _patch_optimizer(monkeypatch, metadata=None):
    monkeypatch.setattr(
        portfolio_optimization,
        "data_and_forecast_pipeline",
        lambda *args, **kwargs: _pipeline(),
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "_latest_market_caps_are_point_in_time_compatible",
        lambda end_date: True,
    )
    monkeypatch.setattr(
        portfolio_optimization,
        "get_asset_metadata",
        lambda tickers: _metadata() if metadata is None else metadata,
    )
    monkeypatch.setattr(portfolio_optimization, "get_market_caps", lambda tickers: {})


@pytest.mark.parametrize("method", ["MIN_VARIANCE", "BL", "MPT"])
def test_all_production_methods_apply_asset_and_group_constraints(monkeypatch, method):
    _patch_optimizer(monkeypatch)
    result = portfolio_optimization.optimize_portfolio(
        start_date="2026-01-01",
        end_date="2026-08-20",
        risk_free_rate=0.02,
        tickers=TICKERS,
        optimization_method=method,
        max_asset_weight=0.5,
        min_holding_weight=0.05,
        asset_constraints=[{"ticker": "AAA", "min_weight": 0.1, "max_weight": 0.3}],
        group_constraints=[{
            "dimension": "sector",
            "group": "Technology",
            "min_weight": 0.4,
            "max_weight": 0.6,
        }],
    )

    assert "error" not in result
    weights = pd.Series(result["weights"])
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert 0.1 - 1e-6 <= weights["AAA"] <= 0.3 + 1e-6
    assert 0.4 - 1e-6 <= weights[["AAA", "BBB"]].sum() <= 0.6 + 1e-6
    assert weights.max() <= 0.5 + 1e-6
    assert result["constraint_diagnostics"]["all_satisfied"]
    assert result["classification_metadata"]["source"] == "yfinance.info"


def test_multiple_constraints_and_risk_diagnostics_use_returned_weights(monkeypatch):
    _patch_optimizer(monkeypatch)
    result = portfolio_optimization.optimize_portfolio(
        start_date="2026-01-01",
        end_date="2026-08-20",
        risk_free_rate=0.02,
        tickers=TICKERS,
        optimization_method="MIN_VARIANCE",
        max_asset_weight=0.45,
        asset_constraints=[{"ticker": "AAA", "min_weight": 0.1, "max_weight": 0.25}],
        group_constraints=[
            {"dimension": "sector", "group": "Technology", "min_weight": 0.35, "max_weight": 0.55},
            {"dimension": "country", "group": "CA", "min_weight": 0.15, "max_weight": 0.4},
        ],
    )

    diagnostics = result["risk_diagnostics"]
    assert diagnostics["status"] == "complete"
    assert diagnostics["component_risk_contribution_sum"] == pytest.approx(result["risk"])
    assert diagnostics["percentage_risk_contribution_sum"] == pytest.approx(1.0)
    assert diagnostics["concentration"]["hhi"] > 0
    assert diagnostics["covariance"]["condition_number"] == pytest.approx(4.0)
    assert diagnostics["classification_exposures"]["country"]["CA"] == pytest.approx(result["weights"]["DDD"])


def test_structural_and_target_feasibility_errors_are_structured():
    with pytest.raises(ConstraintValidationError) as error:
        prepare_constraint_model(
            ["AAA", "BBB"],
            max_asset_weight=0.4,
        )
    assert error.value.to_dict()["error_code"] == "MAX_ASSET_WEIGHT_INFEASIBLE"
    assert error.value.to_dict()["feasible_bound"] == {"minimum": 0.5}

    with pytest.raises(ConstraintValidationError) as error:
        prepare_constraint_model(
            ["AAA", "BBB"],
            max_asset_weight=1.0,
            asset_constraints=[
                {"ticker": "AAA", "min_weight": 0.6},
                {"ticker": "BBB", "min_weight": 0.6},
            ],
        )
    assert error.value.to_dict()["error_code"] == "ASSET_LOWER_BOUNDS_INFEASIBLE"

    with pytest.raises(ConstraintValidationError) as error:
        prepare_constraint_model(
            ["AAA", "BBB"],
            max_asset_weight=1.0,
            expected_returns=pd.Series({"AAA": 0.1, "BBB": 0.05}),
            target_return=0.2,
        )
    assert error.value.to_dict()["error_code"] == "TARGET_RETURN_INFEASIBLE"
    assert error.value.to_dict()["feasible_bound"]["maximum"] == pytest.approx(0.1)


def test_risk_tolerance_preflight_reports_minimum_feasible_bound():
    with pytest.raises(ConstraintValidationError) as error:
        prepare_constraint_model(
            ["AAA", "BBB"],
            max_asset_weight=1.0,
            covariance=pd.DataFrame(np.diag([0.04, 0.01]), index=["AAA", "BBB"], columns=["AAA", "BBB"]),
            risk_tolerance=0.01,
        )
    payload = error.value.to_dict()
    assert payload["error_code"] == "RISK_TOLERANCE_INFEASIBLE"
    assert payload["feasible_bound"]["minimum"] > 0.01


@pytest.mark.parametrize(
    "value,code",
    [
        ({"AAA": float("nan")}, "INVALID_CURRENT_WEIGHTS"),
        ({"AAA": float("inf")}, "INVALID_CURRENT_WEIGHTS"),
        ({"AAA": -0.1}, "INVALID_CURRENT_WEIGHTS"),
        ({"BAD TICKER": 0.1}, "INVALID_TICKER"),
    ],
)
def test_current_weight_validation_rejects_nonfinite_negative_and_bad_tickers(value, code):
    with pytest.raises(ConstraintValidationError) as error:
        normalize_current_weights(value)
    payload = error.value.to_dict()
    assert payload["error_code"] == code
    json.dumps(payload, allow_nan=False)


def test_constraint_validation_rejects_invalid_units():
    with pytest.raises(ConstraintValidationError):
        normalize_asset_constraints([{"ticker": "AAA", "min_weight": 10}])
    with pytest.raises(ConstraintValidationError):
        normalize_asset_constraints([{"ticker": "AAA", "max_weight": float("nan")}])


def test_group_metadata_missing_and_historical_metadata_are_explicit(monkeypatch):
    _patch_optimizer(monkeypatch, metadata=_metadata({"AAA": CLASSIFICATIONS["AAA"]}, status="partial"))
    missing = portfolio_optimization.optimize_portfolio(
        start_date="2026-01-01",
        end_date="2026-08-20",
        risk_free_rate=0.02,
        tickers=TICKERS,
        group_constraints=[{"dimension": "sector", "group": "Technology", "max_weight": 0.6}],
    )
    assert missing["error_code"] == "METADATA_UNAVAILABLE"
    assert missing["affected_tickers"] == ["BBB", "CCC", "DDD"]

    monkeypatch.setattr(
        portfolio_optimization,
        "_latest_market_caps_are_point_in_time_compatible",
        lambda end_date: False,
    )
    historical = portfolio_optimization.optimize_portfolio(
        start_date="2019-01-01",
        end_date="2020-01-01",
        risk_free_rate=0.02,
        tickers=TICKERS,
        group_constraints=[{"dimension": "sector", "group": "Technology", "max_weight": 0.6}],
    )
    assert historical["error_code"] == "POINT_IN_TIME_METADATA_REQUIRED"
    assert historical["classification_metadata"]["status"] == "point_in_time_unavailable"


def test_external_metadata_failure_is_reported_as_unavailable(monkeypatch):
    def fail_metadata_fetch(*args, **kwargs):
        raise RuntimeError("provider credential detail must stay internal")

    monkeypatch.setattr(portfolio_optimization.yf, "Tickers", fail_metadata_fetch)
    metadata = portfolio_optimization.get_asset_metadata(["METADATAFAIL"])

    assert metadata["status"] == "unavailable"
    assert metadata["missing_tickers"] == ["METADATAFAIL"]
    assert metadata["coverage"]["sector"]["coverage_rate"] == 0.0


def test_pipeline_failure_does_not_expose_internal_exception(monkeypatch):
    def fail_pipeline(*args, **kwargs):
        raise RuntimeError("secret solver and filesystem detail")

    monkeypatch.setattr(
        portfolio_optimization,
        "data_and_forecast_pipeline",
        fail_pipeline,
    )
    result = portfolio_optimization.optimize_portfolio(
        start_date="2026-01-01",
        end_date="2026-08-20",
        risk_free_rate=0.02,
        tickers=TICKERS,
    )

    assert result == {
        "error": "Market data and forecast preparation failed.",
        "error_code": "PIPELINE_FAILED",
    }


def test_success_payload_is_strict_json_without_nan_or_numpy_values(monkeypatch):
    _patch_optimizer(monkeypatch)
    result = portfolio_optimization.optimize_portfolio(
        start_date="2026-01-01",
        end_date="2026-08-20",
        risk_free_rate=0.02,
        tickers=TICKERS,
        optimization_method="MIN_VARIANCE",
        max_asset_weight=0.5,
    )

    assert "error" not in result
    json.dumps(result, allow_nan=False)


def test_turnover_preflight_rejects_a_cap_that_cannot_be_reached(monkeypatch):
    _patch_optimizer(monkeypatch)
    result = portfolio_optimization.optimize_portfolio(
        start_date="2026-01-01",
        end_date="2026-08-20",
        risk_free_rate=0.02,
        tickers=TICKERS,
        optimization_method="MIN_VARIANCE",
        max_asset_weight=0.5,
        current_weights={"AAA": 0.1, "BBB": 0.1, "CCC": 0.1, "DDD": 0.7},
        rebalance_band=0.0,
        max_turnover=0.1,
    )
    assert result["error_code"] == "MAX_TURNOVER_INFEASIBLE"
    assert result["constraint"] == "max_turnover"
    assert result["feasible_bound"]["minimum"] > 0.1


def test_rebalance_band_is_revalidated_after_trade_controls(monkeypatch):
    _patch_optimizer(monkeypatch)
    result = portfolio_optimization.optimize_portfolio(
        start_date="2026-01-01",
        end_date="2026-08-20",
        risk_free_rate=0.02,
        tickers=TICKERS,
        optimization_method="MIN_VARIANCE",
        max_asset_weight=0.5,
        current_weights={"AAA": 0.1, "BBB": 0.1, "CCC": 0.1, "DDD": 0.7},
        rebalance_band=0.5,
    )
    assert result["error_code"] == "POST_CONTROL_CONSTRAINT_VIOLATION"
    assert result["constraint"] == "max_asset_weight"


def test_unmodeled_risk_diagnostics_do_not_invent_contributions():
    result = portfolio_risk_diagnostics(
        {"AAA": 0.5, "OLD": 0.5},
        pd.DataFrame([[0.04]], index=["AAA"], columns=["AAA"]),
    )
    assert result["status"] == "unavailable_unmodeled_exposure"
    assert result["risk_contributions"] == {}
    assert result["calculation_coverage"] == pytest.approx(0.5)


def test_optimizer_endpoint_passes_new_fields_to_background_worker(monkeypatch):
    app_module.OPTIMIZATION_JOBS.clear()
    calls = []

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(app_module, "start_optimization_reaper_once", lambda: None)
    monkeypatch.setattr(app_module.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(
        app_module,
        "optimize_portfolio",
        lambda **kwargs: calls.append(kwargs) or {"weights": {"AAA": 1.0}},
    )
    response = app_module.app.test_client().post(
        "/api/optimize-portfolio",
        json={
            "request_id": "constraint-passthrough",
            "ticker_group": "DOW",
            "start_date": "2026-01-01",
            "end_date": "2026-08-20",
            "risk_free_rate": 0.02,
            "l2_gamma": 0.3,
            "max_asset_weight": 0.4,
            "min_holding_weight": 0.05,
            "turnover_penalty": 0.2,
            "rebalance_band": 0.02,
            "max_turnover": 0.35,
            "current_weights": {"AAA": 1.0},
            "asset_constraints": [{"ticker": "AAA", "max_weight": 0.4}],
            "group_constraints": [{"dimension": "sector", "group": "Technology", "max_weight": 0.6}],
        },
    )
    assert response.status_code == 200
    assert calls[0]["l2_gamma"] == pytest.approx(0.3)
    assert calls[0]["max_asset_weight"] == pytest.approx(0.4)
    assert calls[0]["asset_constraints"][0]["ticker"] == "AAA"
    assert calls[0]["group_constraints"][0]["dimension"] == "sector"
