import random
from unittest.mock import Mock
import pytest
from session_watch.schedule import next_interval, validate_schedule

CONFIG = {"refresh": {"distribution": "truncated_normal", "min_seconds": 60,
                     "max_seconds": 120, "mean_seconds": 90, "stddev_seconds": 15}}


def test_fixed_schedule_is_backward_compatible():
    assert next_interval({}) == 60
    assert next_interval({"interval_seconds": 75}) == 75


def test_out_of_range_samples_are_redrawn():
    rng = Mock()
    rng.gauss.side_effect = [40, 130, 88]
    assert next_interval(CONFIG, rng) == 88
    assert rng.gauss.call_count == 3


def test_normal_schedule_bounds_and_center():
    validate_schedule(CONFIG)
    rng = random.Random(42)
    values = [next_interval(CONFIG, rng) for _ in range(10000)]
    assert min(values) >= 60 and max(values) <= 120
    assert 89 < sum(values) / len(values) < 91
    assert sum(75 <= v <= 105 for v in values) > 6500


@pytest.mark.parametrize("overrides", [
    {"min_seconds": 120}, {"mean_seconds": 130}, {"stddev_seconds": 0},
    {"stddev_seconds": 10000}, {"mean_seconds": float('nan')}, {"distribution": "uniform"},
])
def test_invalid_settings_rejected(overrides):
    with pytest.raises(ValueError):
        validate_schedule({"refresh": {**CONFIG["refresh"], **overrides}})
