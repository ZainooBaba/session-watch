"""Refresh timing, with optional normally distributed jitter."""
import math
import random


def validate_schedule(config):
    fixed = config.get("interval_seconds", 60)
    if not isinstance(fixed, (int, float)) or not math.isfinite(fixed) or fixed < 1:
        raise ValueError("interval_seconds must be a finite number of at least 1")
    settings = config.get("refresh")
    if settings is None:
        return
    if settings.get("distribution") != "truncated_normal":
        raise ValueError("refresh.distribution must be truncated_normal")
    names = ("min_seconds", "max_seconds", "mean_seconds", "stddev_seconds")
    values = [settings.get(name) for name in names]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Refresh bounds, mean, and standard deviation must be finite numbers")
    low, high, mean, stddev = values
    if not 1 <= low < high or not low <= mean <= high or stddev <= 0:
        raise ValueError("Refresh requires 1 <= min < max, min <= mean <= max, and stddev > 0")
    if stddev > (high - low) * 10:
        raise ValueError("Refresh standard deviation is too large for the configured bounds")


def next_interval(config, rng=random):
    """Reject out-of-bounds samples rather than piling them up at the limits."""
    settings = config.get("refresh")
    if settings is None:
        return config.get("interval_seconds", 60)
    while True:
        value = rng.gauss(settings["mean_seconds"], settings["stddev_seconds"])
        if settings["min_seconds"] <= value <= settings["max_seconds"]:
            return value
