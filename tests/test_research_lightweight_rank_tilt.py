import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "research_lightweight_rank_tilt.py"
SPEC = importlib.util.spec_from_file_location(
    "research_lightweight_rank_tilt",
    TOOL_PATH,
)
research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


def test_lightweight_rank_tilt_research_settings_are_frozen():
    class Args:
        train_window = 504
        rebalance_frequency = 63
        forecast_horizon = 63
        transaction_cost_bps = 10.0
        max_asset_weight = 0.20
        rebalance_band = 0.02
        max_turnover = 0.35
        bootstrap_samples = 2000
        portfolio_bootstrap_block_size = 21
        signal_bootstrap_block_size = 4
        bootstrap_minimum_probability = 0.95

    settings = research._settings(Args())

    assert settings["candidate"] == "lightweight_rank_tilt"
    assert settings["primary_baseline"] == "lightweight_bl"
    assert settings["portfolio_baselines"] == [
        "lightweight_bl",
        "equal_weight",
    ]
    assert settings["construction"] == {
        "point_forecast": "unchanged_lightweight_ensemble",
        "magnitude_policy": "cross_sectional_rank_only",
        "allocator": "equal_weight_active_share_tilt",
        "target_active_share": 0.20,
    }
