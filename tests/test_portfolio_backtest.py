import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import portfolio_backtest
import portfolio_optimization
from forecast_models import (
    ARIMATransformerPredictor,
    NO_VIEW_FORECAST_UNCERTAINTY,
    TransformerForecastModel,
    no_view_prediction,
)
from portfolio_signals import (
    drawdown_score,
    market_cap_weight,
    momentum_6m,
    momentum_12_1,
    risk_parity,
    signal_stack_bl_views,
    volatility_score,
)


def _synthetic_prices(rows=90):
    dates = pd.date_range("2024-01-02", periods=rows, freq="B")
    x = np.arange(rows)
    return pd.DataFrame(
        {
            "AAA": 100.0 * np.exp(0.0010 * x),
            "BBB": 80.0 * np.exp(0.0006 * x + 0.01 * np.sin(x / 5.0)),
            "CCC": 120.0 * np.exp(0.0002 * x + 0.008 * np.cos(x / 7.0)),
        },
        index=dates,
    )


def test_untrained_transformer_predict_returns_no_view():
    model = TransformerForecastModel()

    prediction = model.predict(horizon=21)

    assert prediction["source"] == "no_view"
    assert prediction["expected_return"] is None
    assert prediction["uncertainty"] == pytest.approx(NO_VIEW_FORECAST_UNCERTAINTY)


def test_arima_transformer_ignores_no_view_transformer_component(monkeypatch):
    predictor = ARIMATransformerPredictor()
    predictor.history = np.linspace(100.0, 120.0, 150)
    monkeypatch.setattr(predictor.arima, "forecast", lambda prices, horizon=63: (0.02, 0.10))
    monkeypatch.setattr(
        predictor.transformer,
        "predict",
        lambda horizon=63: no_view_prediction("forced no-view"),
    )

    prediction = predictor.predict(horizon=63)

    assert prediction["source"] != "no_view"
    assert prediction["expected_return"] == pytest.approx(0.02 * (252 / 63))
    assert prediction["components"] == {"ARIMA": pytest.approx(0.08)}


def test_optimizer_maps_no_view_to_prior_only_expected_return(monkeypatch):
    captured = {}
    pipeline_result = {
        "mu": pd.Series({"AAA": 0.0, "BBB": 0.20}),
        "prior_mu": pd.Series({"AAA": 0.11, "BBB": 0.04}),
        "S": pd.DataFrame(
            [[0.04, 0.005], [0.005, 0.03]],
            index=["AAA", "BBB"],
            columns=["AAA", "BBB"],
        ),
        "uncertainties": pd.Series({"AAA": portfolio_optimization.MAX_FORECAST_UNCERTAINTY, "BBB": 0.20}),
        "no_view_tickers": ["AAA"],
        "tickers": ["AAA", "BBB"],
        "latest_prices": {"AAA": 100.0, "BBB": 80.0},
    }

    class FakeEfficientFrontier:
        def __init__(self, mu, S, weight_bounds=None):
            captured["mu"] = mu.copy()

        def add_objective(self, *args, **kwargs):
            pass

        def max_sharpe(self, risk_free_rate=0.0):
            pass

        def clean_weights(self):
            return {"AAA": 0.5, "BBB": 0.5}

        def portfolio_performance(self, risk_free_rate=0.0):
            return (0.08, 0.16, 0.4)

    monkeypatch.setattr(portfolio_optimization, "data_and_forecast_pipeline", lambda *args, **kwargs: pipeline_result)
    monkeypatch.setattr(portfolio_optimization, "EfficientFrontier", FakeEfficientFrontier)
    monkeypatch.setattr(portfolio_optimization, "get_asset_names", lambda tickers: {ticker: ticker for ticker in tickers})

    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=["AAA", "BBB"],
        optimization_method="MPT",
        forecast_method="ARIMA_TRANSFORMER",
    )

    assert captured["mu"]["AAA"] == pytest.approx(0.11)
    assert result["no_view_tickers"] == ["AAA"]
    assert result["failed_forecast_count"] == 1
    assert result["return_confidence"]["AAA"] == pytest.approx(portfolio_optimization.MIN_FORECAST_CONFIDENCE)


def test_optimizer_adds_turnover_penalty_objective_when_current_weights_exist(monkeypatch):
    captured = {"objectives": []}
    pipeline_result = {
        "mu": pd.Series({"AAA": 0.10, "BBB": 0.08}),
        "prior_mu": pd.Series({"AAA": 0.09, "BBB": 0.07}),
        "S": pd.DataFrame(
            [[0.04, 0.005], [0.005, 0.03]],
            index=["AAA", "BBB"],
            columns=["AAA", "BBB"],
        ),
        "uncertainties": pd.Series({"AAA": 0.20, "BBB": 0.20}),
        "no_view_tickers": [],
        "tickers": ["AAA", "BBB"],
        "latest_prices": {"AAA": 100.0, "BBB": 80.0},
    }

    class FakeEfficientFrontier:
        def __init__(self, mu, S, weight_bounds=None):
            pass

        def add_objective(self, func, **kwargs):
            captured["objectives"].append((func, kwargs))

        def max_sharpe(self, risk_free_rate=0.0):
            pass

        def clean_weights(self):
            return {"AAA": 0.5, "BBB": 0.5}

        def portfolio_performance(self, risk_free_rate=0.0):
            return (0.08, 0.16, 0.4)

    monkeypatch.setattr(portfolio_optimization, "data_and_forecast_pipeline", lambda *args, **kwargs: pipeline_result)
    monkeypatch.setattr(portfolio_optimization, "EfficientFrontier", FakeEfficientFrontier)
    monkeypatch.setattr(portfolio_optimization, "get_asset_names", lambda tickers: {ticker: ticker for ticker in tickers})

    result = portfolio_optimization.optimize_portfolio(
        start_date="2024-01-01",
        end_date="2024-12-31",
        risk_free_rate=0.02,
        tickers=["AAA", "BBB"],
        optimization_method="MPT",
        forecast_method="LIGHTWEIGHT",
        current_weights={"AAA": 0.80, "BBB": 0.20},
        turnover_penalty=0.15,
    )

    penalty_objectives = [
        kwargs for _, kwargs in captured["objectives"]
        if kwargs.get("gamma") == pytest.approx(0.15)
    ]
    assert penalty_objectives
    assert penalty_objectives[0]["current_weights"].tolist() == pytest.approx([0.8, 0.2])
    assert result["optimizer_controls"]["turnover_penalty"] == pytest.approx(0.15)


def test_turnover_and_transaction_cost_math():
    turnover, cost = portfolio_backtest.calculate_turnover_and_cost(
        {"AAA": 500.0, "BBB": 500.0},
        {"AAA": 0.60, "BBB": 0.40},
        portfolio_value=1000.0,
        transaction_cost_bps=10.0,
    )

    assert turnover == pytest.approx(0.20)
    assert cost == pytest.approx(0.20)


def test_inverse_vol_risk_parity_weights_sum_cap_and_prefer_lower_vol():
    dates = pd.date_range("2024-01-02", periods=80, freq="B")
    x = np.arange(len(dates))
    prices = pd.DataFrame(
        {
            "LOW": 100.0 * np.exp(0.0004 * x + 0.002 * np.sin(x / 4.0)),
            "MID": 100.0 * np.exp(0.0004 * x + 0.010 * np.sin(x / 3.0)),
            "HIGH": 100.0 * np.exp(0.0004 * x + 0.030 * np.sin(x / 2.0)),
        },
        index=dates,
    )

    weights = risk_parity(prices, max_asset_weight=0.60)

    assert weights.sum() == pytest.approx(1.0)
    assert weights.max() <= 0.600001
    assert weights["LOW"] > weights["HIGH"]


def test_momentum_12_1_excludes_most_recent_month():
    dates = pd.date_range("2024-01-02", periods=260, freq="B")
    aaa = np.linspace(100.0, 220.0, 260)
    bbb = np.full(260, 100.0)
    aaa[-21:] = np.linspace(220.0, 40.0, 21)
    prices = pd.DataFrame({"AAA": aaa, "BBB": bbb}, index=dates)

    scores = momentum_12_1(prices)
    short_scores = momentum_12_1(prices.iloc[-120:])

    assert scores["AAA"] > scores["BBB"]
    assert short_scores.isna().all()


def test_six_month_momentum_low_vol_and_drawdown_scores_rank_cross_sectionally():
    dates = pd.date_range("2024-01-02", periods=150, freq="B")
    x = np.arange(len(dates))
    prices = pd.DataFrame(
        {
            "MOM": 100.0 * np.exp(0.0020 * x),
            "CALM": 100.0 * np.exp(0.0005 * x + 0.002 * np.sin(x / 8.0)),
            "VOL": 100.0 * np.exp(0.0005 * x + 0.050 * np.sin(x / 2.0)),
        },
        index=dates,
    )
    prices.loc[dates[-20:], "VOL"] *= np.linspace(1.0, 0.65, 20)

    momentum_scores = momentum_6m(prices)
    vol_scores = volatility_score(prices)
    dd_scores = drawdown_score(prices)

    assert momentum_scores["MOM"] > momentum_scores["CALM"]
    assert vol_scores["CALM"] > vol_scores["VOL"]
    assert dd_scores["CALM"] > dd_scores["VOL"]


def test_market_cap_weight_uses_caps_when_available_and_empty_when_not():
    weights = market_cap_weight({"AAA": 100.0, "BBB": 300.0}, tickers=["AAA", "BBB"], max_asset_weight=0.80)
    missing = market_cap_weight({}, tickers=["AAA", "BBB"], max_asset_weight=0.80)

    assert weights.sum() == pytest.approx(1.0)
    assert weights["BBB"] > weights["AAA"]
    assert missing.sum() == pytest.approx(0.0)


def test_signal_stack_views_are_weak_prior_adjustments():
    prices = _synthetic_prices(280)
    prior = pd.Series({"AAA": 0.05, "BBB": 0.05, "CCC": 0.05})

    views = signal_stack_bl_views(prices, prior_returns=prior)

    assert set(views.index) == {"AAA", "BBB", "CCC"}
    assert float(views.sub(prior).abs().max()) <= 0.070001


def test_turnover_band_skips_small_trades():
    controlled, diagnostics = portfolio_optimization.apply_trade_controls(
        {"AAA": 500.0, "BBB": 500.0},
        {"AAA": 510.0, "BBB": 490.0},
        portfolio_value=1000.0,
        rebalance_band=0.02,
        max_turnover=None,
    )

    assert diagnostics["skipped_trade_count"] == 2
    assert diagnostics["controlled_turnover"] == 0.0
    assert controlled["AAA"] == pytest.approx(500.0)
    assert controlled["BBB"] == pytest.approx(500.0)


def test_max_turnover_scales_trades_to_cap():
    controlled, diagnostics = portfolio_optimization.apply_trade_controls(
        {"AAA": 500.0, "BBB": 500.0},
        {"AAA": 1000.0, "BBB": 0.0},
        portfolio_value=1000.0,
        rebalance_band=0.0,
        max_turnover=0.20,
    )

    assert diagnostics["turnover"] == pytest.approx(1.0)
    assert diagnostics["controlled_turnover"] == pytest.approx(0.20)
    assert diagnostics["turnover_cap_hit"] is True
    assert controlled["AAA"] == pytest.approx(600.0)
    assert controlled["BBB"] == pytest.approx(400.0)


def test_min_holding_threshold_drops_small_weights_when_feasible():
    filtered = portfolio_optimization.apply_min_holding_threshold(
        {"AAA": 0.90, "BBB": 0.06, "CCC": 0.04},
        min_holding_weight=0.05,
    )

    assert filtered["CCC"] == pytest.approx(0.0)
    assert filtered["AAA"] + filtered["BBB"] == pytest.approx(1.0)


def test_backtest_max_turnover_sensitivity_caps_controlled_turnover():
    prices = _synthetic_prices(280)
    tight = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("momentum_6m",),
        train_window=126,
        rebalance_frequency=10,
        forecast_horizon=5,
        max_turnover=0.20,
    )
    loose = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("momentum_6m",),
        train_window=126,
        rebalance_frequency=10,
        forecast_horizon=5,
        max_turnover=0.50,
    )

    assert tight["summary_by_model"]["momentum_6m"]["avg_controlled_turnover"] <= 0.20 + 1e-9
    assert loose["summary_by_model"]["momentum_6m"]["avg_controlled_turnover"] <= 0.50 + 1e-9


def test_backtest_records_use_prior_prices_only(monkeypatch):
    seen_windows = []

    def fake_model_weights(model_name, train_prices, forecast_horizon, max_asset_weight, risk_free_rate, **kwargs):
        seen_windows.append((train_prices.index[0], train_prices.index[-1]))
        return {"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3}, {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
        }

    monkeypatch.setattr(portfolio_backtest, "_model_weights", fake_model_weights)

    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(45),
        models=("equal_weight",),
        train_window=15,
        rebalance_frequency=10,
        forecast_horizon=5,
    )

    assert seen_windows
    for record in result["rebalance_records"]:
        assert pd.Timestamp(record["train_end_date"]) < pd.Timestamp(record["rebalance_date"])


def test_synthetic_backtest_runs_all_model_families(monkeypatch):
    monkeypatch.setattr(
        portfolio_backtest,
        "forecast_single_ticker_with_arima_transformer",
        lambda ticker, prices, horizon=63: {"expected_return": 0.04, "uncertainty": 0.20},
    )
    monkeypatch.setattr(
        portfolio_backtest,
        "forecast_single_ticker_with_transformer",
        lambda ticker, prices, horizon=63: {"expected_return": None, "uncertainty": 5.0, "source": "no_view"},
    )

    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(80),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
        transaction_cost_bps=10,
    )

    assert set(result.keys()) == {
        "settings",
        "models",
        "summary_by_model",
        "rebalance_records",
        "promotion_decision",
        "warnings",
    }
    assert set(result["models"]) == set(portfolio_backtest.DEFAULT_BACKTEST_MODELS)
    assert result["summary_by_model"]["equal_weight"]["rebalance_count"] > 0
    assert result["summary_by_model"]["transformer_bl"]["failed_forecast_count"] > 0
    assert "controlled_turnover" in result["summary_by_model"]["equal_weight"]
    assert "skipped_trade_count" in result["summary_by_model"]["equal_weight"]
    assert "turnover_cap_hit_count" in result["summary_by_model"]["equal_weight"]


def test_synthetic_backtest_runs_risk_parity_and_momentum_bl():
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(280),
        models=("risk_parity", "momentum_bl"),
        train_window=252,
        rebalance_frequency=10,
        forecast_horizon=5,
        transaction_cost_bps=10,
    )

    assert result["models"] == ["risk_parity", "momentum_bl"]
    assert result["summary_by_model"]["risk_parity"]["rebalance_count"] > 0
    assert result["summary_by_model"]["momentum_bl"]["rebalance_count"] > 0
    assert "controlled_turnover" in result["rebalance_records"][0]


def test_synthetic_backtest_runs_new_baselines_and_gauntlet_aggregate():
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(280),
        models=(
            "equal_weight",
            "historical_bl",
            "risk_parity",
            "momentum_bl",
            "momentum_6m",
            "low_volatility",
            "market_cap_weight",
            "momentum_12_1",
            "signal_stack_bl",
        ),
        train_window=126,
        rebalance_frequency=10,
        forecast_horizon=5,
        transaction_cost_bps=10,
        market_caps={"AAA": 3_000_000, "BBB": 2_000_000, "CCC": 1_000_000},
    )
    aggregate = portfolio_backtest.aggregate_gauntlet_promotion([
        {"case": {"basket": "synthetic", "regime": "bull"}, "result": result}
    ])

    assert result["summary_by_model"]["momentum_6m"]["rebalance_count"] > 0
    assert result["summary_by_model"]["low_volatility"]["rebalance_count"] > 0
    assert result["summary_by_model"]["market_cap_weight"]["market_cap_available_count"] > 0
    assert aggregate["usable_count"] == 1


def test_forecast_rank_views_reuse_same_train_window_predictions(monkeypatch):
    calls = {"count": 0}
    prices = _synthetic_prices(140)

    def fake_transformer(ticker, ticker_prices, horizon=63):
        calls["count"] += 1
        return {"expected_return": 0.02 if ticker == "AAA" else 0.01, "uncertainty": 0.20}

    portfolio_backtest._FORECAST_RANK_CACHE.clear()
    monkeypatch.setattr(portfolio_backtest, "forecast_single_ticker_with_transformer", fake_transformer)

    portfolio_backtest._forecast_rank_views(prices, "transformer_rank", forecast_horizon=5)
    portfolio_backtest._forecast_rank_views(prices, "transformer_rank", forecast_horizon=5)

    assert calls["count"] == len(prices.columns)


def test_forecast_rank_views_reuse_persistent_predictions_after_memory_clear(monkeypatch, tmp_path):
    calls = {"count": 0}
    prices = _synthetic_prices(140)

    def fake_transformer(ticker, ticker_prices, horizon=63):
        calls["count"] += 1
        return {"expected_return": 0.02, "uncertainty": 0.20, "source": "test"}

    monkeypatch.setattr(portfolio_backtest, "forecast_single_ticker_with_transformer", fake_transformer)
    cache_path = tmp_path / "forecast-cache.sqlite3"
    portfolio_backtest.configure_forecast_rank_cache(cache_path)
    try:
        portfolio_backtest._forecast_rank_views(prices, "transformer_rank", forecast_horizon=5)
        portfolio_backtest._FORECAST_RANK_CACHE.clear()
        portfolio_backtest._forecast_rank_views(prices, "transformer_rank", forecast_horizon=5)

        stats = portfolio_backtest.forecast_rank_cache_stats()
        assert calls["count"] == len(prices.columns)
        assert stats["persistent_hits"] == len(prices.columns)
        assert stats["persistent_entries"] == len(prices.columns)
    finally:
        portfolio_backtest.configure_forecast_rank_cache(None)


def test_precomputed_rebalance_targets_are_reused_across_execution_sensitivities(monkeypatch):
    calls = {"count": 0}
    prices = _synthetic_prices(80)

    def fake_model_weights(model_name, train_prices, forecast_horizon, max_asset_weight, risk_free_rate, **kwargs):
        calls["count"] += 1
        return {"AAA": 0.60, "BBB": 0.30, "CCC": 0.10}, {
            "failed_forecast_count": 0,
            "avg_forecast_confidence": None,
        }

    monkeypatch.setattr(portfolio_backtest, "_model_weights", fake_model_weights)
    targets = portfolio_backtest.build_rebalance_targets(
        prices,
        models=("equal_weight",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
    )
    target_generation_calls = calls["count"]

    tight = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("equal_weight",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
        rebalance_band=0.02,
        max_turnover=0.20,
        rebalance_targets=targets,
    )
    loose = portfolio_backtest.run_portfolio_model_backtest(
        prices,
        models=("equal_weight",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
        rebalance_band=0.05,
        max_turnover=0.50,
        rebalance_targets=targets,
    )

    assert calls["count"] == target_generation_calls
    assert tight["settings"]["reused_rebalance_targets"] is True
    assert loose["settings"]["reused_rebalance_targets"] is True


def test_rank_candidate_records_cross_sectional_information_coefficient(monkeypatch):
    expected_returns = {"AAA": 0.05, "BBB": 0.03, "CCC": 0.01}

    def fake_arima_transformer(ticker, ticker_prices, horizon=63):
        return {
            "expected_return": expected_returns[ticker],
            "uncertainty": 0.20,
            "source": "test",
        }

    portfolio_backtest.configure_forecast_rank_cache(None)
    monkeypatch.setattr(
        portfolio_backtest,
        "forecast_single_ticker_with_arima_transformer",
        fake_arima_transformer,
    )
    result = portfolio_backtest.run_portfolio_model_backtest(
        _synthetic_prices(80),
        models=("arima_transformer_rank_bl",),
        train_window=20,
        rebalance_frequency=10,
        forecast_horizon=5,
    )
    metrics = result["summary_by_model"]["arima_transformer_rank_bl"]

    assert metrics["forecast_rank_ic_count"] > 0
    assert metrics["avg_forecast_rank_ic"] > 0
    assert metrics["positive_forecast_rank_ic_rate"] > 0.5
    assert all(
        record["forecast_rank_ic"] is not None
        for record in result["rebalance_records"]
    )


def test_backtest_cli_writes_json_and_invalid_args_fail(tmp_path):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "backtest.json"
    _synthetic_prices(280).to_csv(csv_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    ok = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "backtest_portfolio_models.py"),
            "--csv",
            str(csv_path),
            "--models",
            "risk_parity",
            "momentum_bl",
            "--train-window",
            "252",
            "--rebalance-frequency",
            "10",
            "--forecast-horizon",
            "5",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert ok.returncode == 0, ok.stderr
    payload = json.loads(output_path.read_text())
    assert payload["models"] == ["risk_parity", "momentum_bl"]
    assert "summary_by_model" in payload

    bad = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "backtest_portfolio_models.py")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert bad.returncode != 0


def test_backtest_cli_gauntlet_smoke_writes_json_and_report(tmp_path):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "gauntlet.json"
    _synthetic_prices(280).to_csv(csv_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    ok = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "backtest_portfolio_models.py"),
            "--gauntlet-preset",
            "smoke",
            "--csv",
            str(csv_path),
            "--models",
            "equal_weight",
            "risk_parity",
            "momentum_6m",
            "low_volatility",
            "momentum_12_1",
            "historical_bl",
            "momentum_bl",
            "signal_stack_bl",
            "--train-window",
            "126",
            "--rebalance-frequency",
            "10",
            "--forecast-horizon",
            "5",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert ok.returncode == 0, ok.stderr
    payload = json.loads(output_path.read_text())
    assert payload["preset"] == "smoke"
    assert payload["completed_count"] == 1
    assert payload["promotion_gauntlet"]["usable_count"] == 1
    assert payload["settings"]["execution_sensitivity_reuses_targets"] is True
    assert payload["runs"][0]["result"]["settings"]["reused_rebalance_targets"] is True
    assert Path(payload["checkpoint_path"]).exists()
    assert (tmp_path / "portfolio_gauntlet_forecasts.sqlite3").exists()
    assert output_path.with_suffix(".md").exists()


def test_backtest_cli_candidate_preset_checkpoints_and_resumes(tmp_path):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "candidate.json"
    _synthetic_prices(80).to_csv(csv_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    command = [
        sys.executable,
        str(ROOT / "tools" / "backtest_portfolio_models.py"),
        "--gauntlet-preset",
        "candidate",
        "--csv",
        str(csv_path),
        "--models",
        "equal_weight",
        "--train-window",
        "20",
        "--rebalance-frequency",
        "10",
        "--forecast-horizon",
        "5",
        "--output",
        str(output_path),
    ]

    first = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    payload = json.loads(output_path.read_text())
    assert payload["preset"] == "candidate"
    assert payload["completed_count"] == 4
    assert {
        (run["case"]["basket_key"], run["case"]["regime"])
        for run in payload["runs"]
    } == {
        ("sp500_sample", "bull"),
        ("tech", "crash"),
        ("defensive", "inflation_rate_shock"),
        ("mixed_etf", "sideways"),
    }

    checkpoint_path = Path(payload["checkpoint_path"])
    first_checkpoint_lines = checkpoint_path.read_text().splitlines()
    resumed = subprocess.run(
        [*command, "--resume"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert len(checkpoint_path.read_text().splitlines()) == len(first_checkpoint_lines)
