"""Intervals for small-sample rates and means."""

import math
import random
from collections.abc import Sequence

from pydantic import BaseModel

Z_95 = 1.959963984540054


class Estimate(BaseModel):
    value: float
    low: float
    high: float
    n: int
    successes: int | None = None


def wilson(successes: int, n: int, z: float = Z_95) -> Estimate:
    """Wilson score interval: sane at 0%, 100%, and small n, unlike the normal approximation."""
    if n == 0:
        return Estimate(value=0.0, low=0.0, high=1.0, n=0, successes=0)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    # The bounds are exactly 0 and 1 at the extremes; pin them so float noise can't cross p.
    low = 0.0 if successes == 0 else max(0.0, center - half)
    high = 1.0 if successes == n else min(1.0, center + half)
    return Estimate(value=p, low=low, high=high, n=n, successes=successes)


def bootstrap_mean(values: Sequence[float], resamples: int = 2000, seed: int = 0) -> Estimate:
    """Percentile bootstrap for a mean (cost, latency). Seeded so reports are reproducible."""
    if not values:
        return Estimate(value=0.0, low=0.0, high=0.0, n=0)
    rng = random.Random(seed)  # noqa: S311 - reproducible resampling, not security
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(resamples))
    return Estimate(
        value=sum(values) / n,
        low=means[int(0.025 * resamples)],
        high=means[int(0.975 * resamples) - 1],
        n=n,
    )
