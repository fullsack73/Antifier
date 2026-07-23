import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "research_lightweight_uncertainty.py"
SPEC = importlib.util.spec_from_file_location(
    "research_lightweight_uncertainty",
    TOOL_PATH,
)
research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


def test_lightweight_uncertainty_research_settings_are_frozen():
    class Args:
        train_window = 504
        rebalance_frequency = 63
        forecast_horizon = 63
        transaction_cost_bps = 10.0
        max_asset_weight = 0.20
        rebalance_band = 0.02
        max_turnover = 0.35
        bootstrap_samples = 2000
        bootstrap_block_size = 21
        bootstrap_minimum_probability = 0.95

    settings = research._settings(Args())

    assert settings["candidate"] == "calibrated_lightweight_bl"
    assert settings["baseline"] == "lightweight_bl"
    assert settings["calibration"] == {
        "method": "completed_oos_residual_rmse",
        "min_origin_history": 126,
        "max_origins": 6,
        "origin_step": "forecast_horizon",
        "uncertainty_prior": 0.20,
        "uncertainty_prior_weight": 0.50,
        "point_forecast": "unchanged_lightweight_ensemble",
    }
