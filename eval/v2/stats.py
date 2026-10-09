"""Statistics for study v2, standard library only (methods critique, fix 8).

Facts sit in tasks and tasks in families (``halden-trial-near`` and ``halden-trial-far`` share a
source), so the **family** is the unit of analysis. Each contrast is a list of per-family
differences (condition b minus condition a, in percentage points of the outcome).

- ``sign_flip``: two-sided permutation test of the mean difference, flipping each family's sign.
  Exact up to 16 families, Monte Carlo above. Valid with few clusters, where bootstrap intervals
  undercover.
- ``bootstrap_ci``: percentile interval from resampling families, reported as a description of
  the effect's spread, not as the test.
- ``holm``: Holm–Bonferroni adjusted p-values for the secondary contrasts.
- ``mcnemar``: exact two-sided McNemar test on paired binary outcomes (sensitivity analysis).
- ``equivalent``: two one-sided tests by interval inclusion: the 90% interval inside ±margin.
- ``power``: simulated power of ``sign_flip`` for a given number of families and repeats, using
  family-level rates from the pilot.
"""

import itertools
import math
import random
from collections.abc import Sequence


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def sign_flip(diffs: Sequence[float], iterations: int = 100_000, seed: int = 7) -> float:
    """Two-sided p-value for mean(diffs) == 0 under random sign flips of whole families."""
    diffs = [d for d in diffs if not math.isnan(d)]
    n = len(diffs)
    if n == 0:
        return float("nan")
    observed = abs(sum(diffs))
    if n <= 16:
        flips = itertools.product((1, -1), repeat=n)
        total = 2 ** n
        extreme = sum(abs(sum(s * d for s, d in zip(signs, diffs, strict=True))) >= observed - 1e-12
                      for signs in flips)
        return extreme / total
    rng = random.Random(seed)
    extreme = sum(abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed - 1e-12
                  for _ in range(iterations))
    return (extreme + 1) / (iterations + 1)


def bootstrap_ci(diffs: Sequence[float], level: float = 0.95, iterations: int = 10_000,
                 seed: int = 7) -> tuple[float, float]:
    diffs = [d for d in diffs if not math.isnan(d)]
    if not diffs:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = sorted(mean([rng.choice(diffs) for _ in diffs]) for _ in range(iterations))
    lo = means[int((1 - level) / 2 * iterations)]
    hi = means[min(iterations - 1, int((1 + level) / 2 * iterations))]
    return (lo, hi)


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-adjusted p-values, monotone, capped at 1."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        adjusted[name] = running
    return adjusted


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value: b pairs with only a = 1, c pairs with only b = 1."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def equivalent(diffs: Sequence[float], margin: float) -> tuple[bool, tuple[float, float]]:
    """TOST by interval inclusion: the 90% family-bootstrap interval lies inside (-margin, margin)."""
    lo, hi = bootstrap_ci(diffs, level=0.90)
    return (-margin < lo and hi < margin, (lo, hi))


def power(family_rates: Sequence[tuple[float, float, int]], families: int, repeats: int,
          delta: float, alpha: float = 0.05, simulations: int = 400, seed: int = 11) -> float:
    """Simulated power of ``sign_flip`` to detect ``delta`` (a proportion, e.g. 0.15).

    ``family_rates`` are pilot families as (rate in condition a, rate in condition b under the
    null, facts per run). Each simulated study draws ``families`` of them with replacement, adds
    ``delta`` to condition b's rate, draws ``repeats`` runs per condition, and tests the
    per-family differences."""
    rng = random.Random(seed)
    hits = 0
    for _ in range(simulations):
        diffs = []
        for _ in range(families):
            rate_a, rate_b, facts = rng.choice(list(family_rates))
            rate_b = min(1.0, max(0.0, rate_b + delta))
            k = max(1, facts)
            a = sum(rng.random() < rate_a for _ in range(k * repeats)) / (k * repeats)
            b = sum(rng.random() < rate_b for _ in range(k * repeats)) / (k * repeats)
            diffs.append(b - a)
        if sign_flip(diffs, iterations=2000, seed=rng.randrange(10 ** 6)) < alpha:
            hits += 1
    return hits / simulations
