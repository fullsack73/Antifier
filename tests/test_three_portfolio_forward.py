import copy
import io
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
PAST_SPEC = (
    ROOT
    / "data"
    / "research"
    / "derived"
    / "three_portfolio_past_forward_spec_v1.json"
)

from tools.three_portfolio_forward import (  # noqa: E402
    DEFAULT_SPEC,
    download_prices,
    evaluate,
    load_spec,
    verify_inputs,
)
from research_split import canonical_json_digest  # noqa: E402


def _synthetic_prices(spec, periods=253):
    tickers = sorted({
        ticker
        for portfolio in spec["portfolios"].values()
        for ticker in portfolio["weights"]
    })
    dates = pd.bdate_range(spec["first_eligible_date"], periods=periods)
    step = np.arange(periods, dtype=float)
    return pd.DataFrame({
        ticker: 100.0 * np.exp(
            (0.00015 + index * 0.000002) * step
            + 0.01 * np.sin(step / (7.0 + index % 5))
        )
        for index, ticker in enumerate(tickers)
    }, index=dates)


def test_tracked_spec_and_frozen_inputs_are_valid():
    spec = load_spec()
    assert verify_inputs(spec) is True
    assert spec["news_provenance"]["classification"] == (
        "non_reproducible_diagnostic"
    )


def test_past_spec_is_a_retrospective_forward_holdout():
    spec = load_spec(PAST_SPEC)

    assert verify_inputs(spec) is True
    assert spec["formation_date"] == "2024-08-30"
    assert spec["first_eligible_date"] == "2024-08-30"
    assert spec["evaluation_mode"] == "retrospective_forward_holdout"
    assert spec["preregistered_before_outcome"] is False


def test_spec_hash_detects_drift(tmp_path):
    changed = json.loads(DEFAULT_SPEC.read_text(encoding="utf-8"))
    changed["annual_cash_return"] = 0.04
    target = tmp_path / "changed.json"
    target.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_spec(target)

    changed["spec_sha256"] = canonical_json_digest({
        key: value for key, value in changed.items() if key != "spec_sha256"
    })
    target.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="Locked forward setting changed"):
        load_spec(target)


def test_preformation_status_has_no_forward_observations():
    result = evaluate(load_spec(), pd.DataFrame(), as_of="2026-08-30")
    assert result["status"] == "forward_pending"
    assert result["completed_return_observations"] == 0
    assert result["next_milestone"] == 63
    assert result["milestone_results"] == {}


def test_missing_frozen_ticker_is_rejected():
    spec = load_spec()
    prices = _synthetic_prices(spec, periods=64).drop(columns="GOOG")
    with pytest.raises(ValueError, match="missing frozen tickers: GOOG"):
        evaluate(spec, prices, as_of=prices.index[-1].date())


def test_live_download_requests_adjusted_usd_close(monkeypatch):
    payloads = iter([
        {"chart": {"error": None, "result": [{
            "meta": {"currency": "USD"},
            "timestamp": [1788134400, 1788220800],
            "indicators": {"adjclose": [{"adjclose": [100.0, 101.0]}]},
        }]}},
        {"chart": {"error": None, "result": [{
            "meta": {"currency": "USD"},
            "timestamp": [1788134400, 1788220800],
            "indicators": {"adjclose": [{"adjclose": [200.0, 202.0]}]},
        }]}},
    ])

    class Response(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    def fake_urlopen(request, timeout):
        assert "includeAdjustedClose=true" in request.full_url
        assert timeout == 20
        return Response(json.dumps(next(payloads)))

    monkeypatch.setattr(
        "tools.three_portfolio_forward.urlopen",
        fake_urlopen,
    )
    result = download_prices(
        ["AAA", "BBB"],
        date(2026, 8, 31),
        date(2026, 9, 1),
    )

    assert list(result.columns) == ["AAA", "BBB"]
    assert result.iloc[-1].to_dict() == {"AAA": 101.0, "BBB": 202.0}


def test_all_milestones_are_deterministic_and_never_promote():
    spec = copy.deepcopy(load_spec())
    spec["bootstrap"]["samples"] = 100
    prices = _synthetic_prices(spec)
    first = evaluate(spec, prices, as_of=prices.index[-1].date())
    second = evaluate(spec, prices, as_of=prices.index[-1].date())

    assert first == second
    assert first["status"] == "complete"
    assert first["completed_return_observations"] == 252
    assert first["mature_milestones"] == [63, 126, 252]
    assert first["next_milestone"] is None
    assert first["news_adjusted_classification"] == (
        "non_reproducible_diagnostic"
    )
    assert first["no_automatic_promotion"] is True
    assert first["available_period_result"]["return_observations"] == 252
    assert first["available_period_result"]["descriptive_only"] is True
    assert first["available_period_result"]["promotion_gate_applied"] is False
    for milestone in ("63", "126", "252"):
        result = first["milestone_results"][milestone]
        assert set(result["portfolios"]) == {
            "gmv",
            "news_adjusted_gmv",
            "llm_only",
        }
        assert result["manual_review_only"] is True
        assert set(result["comparisons_to_gmv"]) == {
            "news_adjusted_gmv",
            "llm_only",
        }
        assert all(
            comparison["gate"]["status"] in {"passed", "rejected"}
            for comparison in result["comparisons_to_gmv"].values()
        )
