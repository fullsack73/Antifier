import pytest

from tools.compare_adaptive_hybrid import cross_error_weight
from tools.compare_hybrid_history import mix_at_origin


def test_history_lengths_use_only_completed_outcomes_and_distinct_sample_sizes():
    origin = 1259
    records = {(origin, "TEST"): {"arima": 2., "transformer": 1., "realized": 100.}}
    for lag in range(1, 13):
        records[(origin - lag * 63, "TEST")] = {"arima": 2. if lag <= 3 else 0.,
                                                "transformer": 1., "realized": 0.}
    result = mix_at_origin(records, origin, "TEST")
    assert result["ignored_3"] == pytest.approx(1.35)
    assert result["ignored_12"] == pytest.approx(1.5)
    assert result["cross_3"] == pytest.approx(1.25)
    # Current and future outcomes cannot determine the current weights.
    records[(origin, "TEST")]["realized"] = -100.
    records[(origin + 63, "TEST")] = {"arima": 1e6, "transformer": -1e6, "realized": 1e6}
    assert mix_at_origin(records, origin, "TEST")["weights"] == result["weights"]
    assert cross_error_weight([[2., 1.]] * 12) == .25
