"""Coherent cross rates from shared currency levels; no estimated FX model."""

import math
import random
from collections.abc import Mapping


SYNTHETIC_LEVELS = {"USD": 1.0, "CHF": 0.9, "EUR": 0.8, "GBP": 0.7}


def generate_currency_states(
    seed: int, count: int = 5, baseline: Mapping[str, float] | None = None
) -> list[dict[str, float]]:
    """Make reproducible demo states. Bounds/independence are not FX forecasts."""
    initial = dict(SYNTHETIC_LEVELS if baseline is None else baseline)
    validate_levels(initial)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("count must be a positive integer")
    rng = random.Random(seed)
    return [
        {
            currency: value if currency == "USD" else value * (1 + rng.uniform(-0.05, 0.05))
            for currency, value in sorted(initial.items())
        }
        for _ in range(count)
    ]


def validate_levels(levels: Mapping[str, float]) -> None:
    if levels.get("USD") != 1.0:
        raise ValueError("USD level must equal 1: levels are currency units per USD.")
    if any(not math.isfinite(value) or value <= 0 for value in levels.values()):
        raise ValueError("Every currency level must be finite and positive.")


def cross_rate(levels: Mapping[str, float], base: str, quote: str) -> float:
    """Return quote-currency units for one base-currency unit."""
    validate_levels(levels)
    return levels[quote] / levels[base]

