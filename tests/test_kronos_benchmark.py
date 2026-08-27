import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import benchmark_kronos_forecasts as benchmark


def _cache_row(namespace, method, ticker, prices, prediction):
    digest = benchmark._series_digest(prices)
    key = [
        "2026-07-23-v2-diagnostics",
        namespace,
        method,
        ticker,
        2,
        len(prices),
        str(prices.index[0]),
        str(prices.index[-1]),
        digest,
    ]
    return json.dumps(key), json.dumps({"expected_return": prediction})


def _write_cache(path, prices_by_ticker):
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE forecast_predictions (
            cache_key TEXT PRIMARY KEY,
            key_payload TEXT NOT NULL,
            prediction_payload TEXT NOT NULL
        )
        """
    )
    for ticker, prices in prices_by_ticker.items():
        for method, namespace, prediction in (
            ("arima_transformer_rank", "arima-transformer-rank-v1", 0.2),
            ("transformer_rank", "transformer-rank-v1", 0.1),
        ):
            key, payload = _cache_row(
                namespace, method, ticker, prices, prediction
            )
            connection.execute(
                "INSERT INTO forecast_predictions VALUES (?, ?, ?)",
                (f"{method}-{ticker}", key, payload),
            )
    connection.commit()
    connection.close()


def test_build_aligned_origins_reuses_exact_close_digest(tmp_path):
    dates = pd.date_range("2020-01-01", periods=6, freq="D")
    histories = {
        "AAA": pd.Series([10, 11, 12, 13], index=dates[:4], dtype=float),
        "BBB": pd.Series([20, 19, 18, 17], index=dates[:4], dtype=float),
    }
    cache_path = tmp_path / "forecasts.sqlite3"
    _write_cache(cache_path, histories)
    cached = benchmark.load_cached_forecasts(cache_path)
    rows = []
    for ticker, history in histories.items():
        for timestamp, close in pd.Series(
            list(history) + [history.iloc[-1] + 1, history.iloc[-1] + 2],
            index=dates,
        ).items():
            rows.append({
                "timestamp": timestamp,
                "ticker": ticker,
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
            })

    origins, mismatches = benchmark.build_aligned_origins(
        cached, pd.DataFrame(rows)
    )

    assert not mismatches
    assert len(origins) == 1
    assert {row["ticker"] for row in origins[0]["rows"]} == {"AAA", "BBB"}
    assert origins[0]["horizon"] == 2
    assert origins[0]["rows"][0]["arima_transformer_rank"] is None


def test_read_ohlc_csv_refuses_missing_ohlc(tmp_path):
    path = tmp_path / "close-only.csv"
    pd.DataFrame({
        "timestamp": ["2020-01-01"],
        "ticker": ["AAA"],
        "close": [10.0],
    }).to_csv(path, index=False)

    with pytest.raises(ValueError, match="missing columns"):
        benchmark.read_ohlc_csv(path)


def test_summarize_compares_all_three_models(monkeypatch):
    monkeypatch.setattr(
        benchmark,
        "rank_signal_block_bootstrap",
        lambda periods: {"status": "insufficient_data", "observation_count": 1},
    )
    origin = {
        "period_id": "p1",
        "case_id": "case",
        "rows": [
            {
                "ticker": "AAA",
                "realized_return": 0.2,
                "arima_transformer_rank": 0.1,
                "transformer_rank": -0.1,
            },
            {
                "ticker": "BBB",
                "realized_return": -0.2,
                "arima_transformer_rank": -0.1,
                "transformer_rank": 0.1,
            },
        ],
    }

    models, periods = benchmark.summarize(
        [origin],
        {"p1": {"scores": {"AAA": 0.3, "BBB": -0.3}}},
    )

    assert set(models) == {
        "arima_transformer_rank",
        "transformer_rank",
        "kronos_small_zero_shot",
    }
    assert models["kronos_small_zero_shot"]["rank_diagnostics"][
        "mean_rank_ic"
    ] == pytest.approx(1.0)
    assert periods["transformer_rank"][0]["scores"]["AAA"] == -0.1


def test_benchmark_decision_requires_paired_incremental_evidence():
    result = {
        "signal_gate": {"status": "passed"},
        "paired_vs_arima_transformer": {
            "probability": {
                "higher_mean_rank_ic": 0.99,
                "higher_mean_top_bottom_spread": 0.91,
            }
        },
        "paired_vs_transformer": {
            "probability": {
                "higher_mean_rank_ic": 0.99,
                "higher_mean_top_bottom_spread": 0.99,
            }
        },
    }

    assert benchmark.benchmark_decision(result) == (
        "signal_passed_incremental_unconfirmed"
    )


def test_run_kronos_origins_chunks_large_cross_section(tmp_path):
    class Torch:
        @staticmethod
        def manual_seed(_seed):
            return None

    class Predictor:
        def __init__(self):
            self.batch_sizes = []

        def predict_batch(self, df_list, **kwargs):
            self.batch_sizes.append(len(df_list))
            return [frame.copy() for frame in df_list]

    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    rows = [
        {
            "ticker": ticker,
            "train": pd.DataFrame({"close": [10.0, 11.0]}, index=dates[:2]),
            "future_timestamps": pd.Series(dates[2:]),
        }
        for ticker in "ABCDE"
    ]
    origin = {
        "period_id": "p1",
        "case_id": "case",
        "train_end": dates[1],
        "horizon": 1,
        "rows": rows,
    }
    predictor = Predictor()

    result = benchmark.run_kronos_origins(
        [origin],
        predictor,
        Torch,
        tmp_path / "checkpoint.jsonl",
        {"version": 1},
        batch_size=2,
    )

    assert predictor.batch_sizes == [2, 2, 1]
    assert set(result["p1"]["scores"]) == set("ABCDE")
