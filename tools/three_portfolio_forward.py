#!/usr/bin/env python3
"""Evaluate the frozen three-portfolio campaign without historical backfill."""

import argparse
import hashlib
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from portfolio_statistics import (  # noqa: E402
    bootstrap_improvement_gate,
    paired_block_bootstrap,
)
from research_split import canonical_json_digest  # noqa: E402


DEFAULT_SPEC = (
    ROOT
    / "data"
    / "research"
    / "derived"
    / "three_portfolio_forward_spec_v1.json"
)
LOCKED_SETTINGS = {
    "annual_cash_return": 0.035,
    "annualization_days": 252,
    "milestones_return_observations": [63, 126, 252],
    "data_contract": {
        "source": "yahoo_finance_adjusted_close",
        "client": "yahoo_chart_v8",
        "include_adjusted_close": True,
        "base_currency": "USD",
        "alignment": "common_dates_forward_fill_after_first_observation",
        "unit_semantics": "synthetic_fractional_buy_and_hold_units",
        "rebalance_policy": "none",
    },
    "bootstrap": {
        "method": "paired_circular_block",
        "block_size": 21,
        "samples": 5000,
        "seed": 20260830,
        "minimum_probability": 0.95,
    },
    "historical_backfill_allowed": False,
    "manual_review_only": True,
    "no_automatic_promotion": True,
}


def _file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_spec(path=DEFAULT_SPEC):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = payload.get("spec_sha256")
    actual = canonical_json_digest({
        key: value for key, value in payload.items() if key != "spec_sha256"
    })
    if expected != actual:
        raise ValueError("Forward specification hash mismatch")
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported forward specification schema_version")
    if payload.get("historical_backfill_allowed") is not False:
        raise ValueError("Historical backfill must remain disabled")
    if payload.get("no_automatic_promotion") is not True:
        raise ValueError("Automatic promotion must remain disabled")
    for key, expected_value in LOCKED_SETTINGS.items():
        if payload.get(key) != expected_value:
            raise ValueError(f"Locked forward setting changed: {key}")
    for key in ("campaign_id", "formation_date", "first_eligible_date"):
        if not payload.get(key):
            raise ValueError(f"Missing forward specification field: {key}")
    formation_date = date.fromisoformat(payload["formation_date"])
    first_eligible_date = date.fromisoformat(payload["first_eligible_date"])
    if first_eligible_date < formation_date:
        raise ValueError("first_eligible_date precedes formation_date")
    evaluation_mode = payload.get("evaluation_mode", "calendar_forward")
    if evaluation_mode not in {
        "calendar_forward",
        "retrospective_forward_holdout",
    }:
        raise ValueError("Unsupported evaluation_mode")
    if (
        evaluation_mode == "retrospective_forward_holdout"
        and payload.get("preregistered_before_outcome") is not False
    ):
        raise ValueError("Retrospective holdout cannot claim prior registration")
    if set(payload["portfolios"]) != {"gmv", "news_adjusted_gmv", "llm_only"}:
        raise ValueError("Locked portfolio set changed")
    for name, portfolio in payload["portfolios"].items():
        weights = pd.Series(portfolio["weights"], dtype=float)
        if weights.empty or not np.isfinite(weights).all() or (weights < 0).any():
            raise ValueError(f"Invalid weights for {name}")
        total = float(weights.sum()) + float(portfolio["cash_weight"])
        if not np.isclose(total, 1.0, atol=1e-12):
            raise ValueError(f"Weights and cash do not sum to one for {name}")
    return payload


def verify_inputs(spec, root=ROOT):
    for name, portfolio in spec["portfolios"].items():
        source = Path(root) / portfolio["input_path"]
        if not source.is_file():
            raise ValueError(f"Missing frozen input for {name}: {source}")
        if _file_sha256(source) != portfolio["input_sha256"]:
            raise ValueError(f"Frozen input hash mismatch for {name}")
        source_weights = json.loads(source.read_text(encoding="utf-8"))["weights"]
        if source_weights != portfolio["weights"]:
            raise ValueError(f"Frozen input weights mismatch for {name}")
    return True


def load_price_csv(path):
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    return frame.apply(pd.to_numeric, errors="coerce")


def download_prices(tickers, start_date, end_date):
    start_timestamp = int(
        datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp()
    )
    end_timestamp = int(
        datetime.combine(
            end_date + timedelta(days=1),
            datetime.min.time(),
            tzinfo=timezone.utc,
        ).timestamp()
    )
    series = {}
    for ticker in tickers:
        query = urlencode({
            "period1": start_timestamp,
            "period2": end_timestamp,
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        })
        request = Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            + quote(ticker, safe="")
            + "?"
            + query,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        last_error = None
        for attempt in range(2):
            try:
                with urlopen(request, timeout=20) as response:
                    payload = json.load(response)
                chart = payload["chart"]
                if chart.get("error") or not chart.get("result"):
                    raise ValueError(f"Yahoo returned no chart for {ticker}")
                result = chart["result"][0]
                if result.get("meta", {}).get("currency") != "USD":
                    raise ValueError(f"Yahoo returned non-USD prices for {ticker}")
                timestamps = result.get("timestamp") or []
                adjusted = (
                    result.get("indicators", {}).get("adjclose") or [{}]
                )[0].get("adjclose") or []
                if len(timestamps) != len(adjusted):
                    raise ValueError(f"Yahoo adjusted-close length mismatch for {ticker}")
                index = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None).normalize()
                series[ticker] = pd.Series(adjusted, index=index, dtype=float)
                break
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.25)
        else:
            raise RuntimeError(
                f"Yahoo adjusted-close download failed for {ticker}: {last_error}"
            ) from last_error
    return pd.DataFrame(series).reindex(columns=tickers)


def _price_digest(frame):
    normalized = pd.DataFrame(frame).sort_index().reindex(
        sorted(frame.columns), axis=1
    )
    return canonical_json_digest({
        "dates": [pd.Timestamp(value).strftime("%Y-%m-%d") for value in normalized.index],
        "columns": list(normalized.columns),
        "values": [
            [float(value).hex() for value in row]
            for row in normalized.to_numpy(dtype=float)
        ],
    })


def _portfolio_path(prices, portfolio, annual_cash_return):
    weights = pd.Series(portfolio["weights"], dtype=float).reindex(
        prices.columns
    ).fillna(0.0)
    relative = prices.divide(prices.iloc[0])
    elapsed_years = (prices.index - prices.index[0]).days / 365.0
    cash = float(portfolio["cash_weight"]) * (
        (1.0 + float(annual_cash_return)) ** elapsed_years
    )
    return relative.mul(weights, axis=1).sum(axis=1) + cash


def _metrics(values, risk_free_rate, annualization_days):
    returns = values.pct_change().dropna()
    annual_volatility = float(
        returns.std(ddof=0) * np.sqrt(annualization_days)
    )
    daily_risk_free = (1.0 + risk_free_rate) ** (1.0 / annualization_days) - 1.0
    annual_excess = float((returns - daily_risk_free).mean() * annualization_days)
    drawdown = values / values.cummax() - 1.0
    return {
        "total_return": float(values.iloc[-1] / values.iloc[0] - 1.0),
        "cagr": float(
            (values.iloc[-1] / values.iloc[0])
            ** (annualization_days / len(returns))
            - 1.0
        ),
        "annual_volatility": annual_volatility,
        "sharpe": (
            None
            if annual_volatility <= 1e-12
            else float(annual_excess / annual_volatility)
        ),
        "max_drawdown": float(drawdown.min()),
        "final_value": float(values.iloc[-1]),
    }


def evaluate(spec, price_data, as_of=None):
    as_of = date.fromisoformat(str(as_of or date.today()))
    first_eligible = date.fromisoformat(spec["first_eligible_date"])
    tickers = sorted({
        ticker
        for portfolio in spec["portfolios"].values()
        for ticker in portfolio["weights"]
    })
    frame = pd.DataFrame(price_data).copy()
    if frame.empty:
        frame = pd.DataFrame(columns=tickers, dtype=float)
    else:
        frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
        frame = frame.sort_index()
        frame = frame.loc[~frame.index.duplicated(keep="last")]
        frame = frame.loc[frame.index.date >= first_eligible].reindex(columns=tickers)
        frame = frame.replace([np.inf, -np.inf], np.nan)
        missing = [ticker for ticker in tickers if frame[ticker].notna().sum() == 0]
        if missing:
            raise ValueError("Price panel is missing frozen tickers: " + ", ".join(missing))
        frame = frame.mask(frame <= 0.0).ffill().dropna(how="any")
        frame = frame.loc[frame.index.date <= as_of]
    return_count = max(0, len(frame) - 1)
    milestones = list(map(int, spec["milestones_return_observations"]))
    mature = [value for value in milestones if return_count >= value]
    result = {
        "schema_version": 1,
        "campaign_id": spec["campaign_id"],
        "spec_sha256": spec["spec_sha256"],
        "input_sha256": {
            name: portfolio["input_sha256"]
            for name, portfolio in spec["portfolios"].items()
        },
        "as_of": as_of.isoformat(),
        "status": "complete" if len(mature) == len(milestones) else "forward_pending",
        "common_price_observations": int(len(frame)),
        "completed_return_observations": int(return_count),
        "mature_milestones": mature,
        "next_milestone": next(
            (value for value in milestones if value not in mature), None
        ),
        "available_through": (
            None if frame.empty else frame.index[-1].strftime("%Y-%m-%d")
        ),
        "price_sha256": None if frame.empty else _price_digest(frame),
        "news_provenance_status": spec["news_provenance"]["status"],
        "news_adjusted_classification": spec["news_provenance"]["classification"],
        "evaluation_mode": spec.get("evaluation_mode", "calendar_forward"),
        "preregistered_before_outcome": spec.get(
            "preregistered_before_outcome",
            True,
        ),
        "milestone_results": {},
        "no_automatic_promotion": True,
    }
    for milestone in mature:
        window = frame.iloc[: milestone + 1]
        paths = {
            name: _portfolio_path(
                window,
                portfolio,
                spec["annual_cash_return"],
            )
            for name, portfolio in spec["portfolios"].items()
        }
        returns = {name: values.pct_change().dropna() for name, values in paths.items()}
        comparisons = {}
        for candidate in ("news_adjusted_gmv", "llm_only"):
            bootstrap = paired_block_bootstrap(
                returns[candidate],
                returns["gmv"],
                risk_free_rate=spec["annual_cash_return"],
                block_size=spec["bootstrap"]["block_size"],
                samples=spec["bootstrap"]["samples"],
                seed=spec["bootstrap"]["seed"],
            )
            comparisons[candidate] = {
                "bootstrap": bootstrap,
                "gate": bootstrap_improvement_gate(
                    bootstrap,
                    minimum_probability=spec["bootstrap"]["minimum_probability"],
                ),
            }
        result["milestone_results"][str(milestone)] = {
            "start_date": window.index[0].strftime("%Y-%m-%d"),
            "end_date": window.index[-1].strftime("%Y-%m-%d"),
            "price_sha256": _price_digest(window),
            "portfolios": {
                name: _metrics(
                    values,
                    spec["annual_cash_return"],
                    spec["annualization_days"],
                )
                for name, values in paths.items()
            },
            "comparisons_to_gmv": comparisons,
            "manual_review_only": True,
        }
    if return_count:
        paths = {
            name: _portfolio_path(
                frame,
                portfolio,
                spec["annual_cash_return"],
            )
            for name, portfolio in spec["portfolios"].items()
        }
        result["available_period_result"] = {
            "start_date": frame.index[0].strftime("%Y-%m-%d"),
            "end_date": frame.index[-1].strftime("%Y-%m-%d"),
            "return_observations": return_count,
            "portfolios": {
                name: _metrics(
                    values,
                    spec["annual_cash_return"],
                    spec["annualization_days"],
                )
                for name, values in paths.items()
            },
            "descriptive_only": True,
            "promotion_gate_applied": False,
        }
    result["result_sha256"] = canonical_json_digest(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=str(DEFAULT_SPEC))
    parser.add_argument("--prices", help="Offline adjusted-close CSV")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        spec = load_spec(args.spec)
        verify_inputs(spec)
        as_of = date.fromisoformat(args.as_of)
        if args.prices:
            prices = load_price_csv(args.prices)
        elif as_of < date.fromisoformat(spec["first_eligible_date"]):
            prices = pd.DataFrame()
        else:
            tickers = sorted({
                ticker
                for portfolio in spec["portfolios"].values()
                for ticker in portfolio["weights"]
            })
            prices = download_prices(
                tickers,
                date.fromisoformat(spec["first_eligible_date"]),
                as_of,
            )
        result = evaluate(spec, prices, as_of=args.as_of)
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(target)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
