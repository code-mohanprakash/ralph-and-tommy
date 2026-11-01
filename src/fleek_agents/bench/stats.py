"""Error bars, done the way lab eval guides recommend, in plain Python.

- Runs of the same scenario aren't independent, so intervals resample whole scenarios
  (a cluster bootstrap), not single runs.
- A rate with zero failures still gets an upper bound: 0 in n means under 1 - 0.05^(1/n),
  about 3/n (the "rule of three").
- A tactic is compared with its paired control on the same scenario, with an exact sign test.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from math import comb, sqrt
from random import Random

Z95 = 1.959964


@dataclass(frozen=True)
class Estimate:
    value: float
    low: float
    high: float
    n: int  # how many scenarios (clusters) it rests on

    def as_percent(self) -> str:
        return f"{self.value:.0%} ({self.low:.0%} to {self.high:.0%})"


def wilson(hits: int, n: int) -> Estimate:
    """A 95% interval for a rate, sensible even near 0% or 100%."""
    if n == 0:
        return Estimate(0.0, 0.0, 1.0, 0)
    p = hits / n
    centre = (p + Z95**2 / (2 * n)) / (1 + Z95**2 / n)
    half = Z95 * sqrt(p * (1 - p) / n + Z95**2 / (4 * n * n)) / (1 + Z95**2 / n)
    low = 0.0 if hits == 0 else max(0.0, centre - half)  # exact ends: no rounding past them
    high = 1.0 if hits == n else min(1.0, centre + half)
    return Estimate(p, low, high, n)


def zero_failure_bound(n: int) -> float:
    """The 95% upper bound on a rate when 0 of n tries failed (about 3/n)."""
    return 1.0 if n == 0 else 1 - 0.05 ** (1 / n)


def cluster_mean(values: Sequence[tuple[str, float]], *, resamples: int = 2000) -> Estimate:
    """Mean of (cluster, value) pairs with a 95% interval from resampling whole clusters."""
    groups: dict[str, list[float]] = defaultdict(list)
    for cluster, value in values:
        groups[cluster].append(value)
    if not groups:
        return Estimate(0.0, 0.0, 0.0, 0)
    means = [sum(v) / len(v) for v in groups.values()]
    overall = sum(means) / len(means)
    if len(means) == 1:
        return Estimate(overall, overall, overall, 1)
    rng = Random(1)  # fixed, so the same data always gets the same interval
    samples = sorted(sum(rng.choice(means) for _ in means) / len(means) for _ in range(resamples))
    low = samples[int(0.025 * resamples)]
    high = samples[int(0.975 * resamples) - 1]
    return Estimate(overall, low, high, len(means))


def sign_test(differences: Sequence[float]) -> float:
    """Two-sided exact sign test: how likely this many ups vs downs is by chance. Ties dropped."""
    ups = sum(d > 0 for d in differences)
    downs = sum(d < 0 for d in differences)
    n = ups + downs
    if n == 0:
        return 1.0
    k = min(ups, downs)
    tail = float(sum(comb(n, i) for i in range(k + 1))) / float(2**n)
    return min(1.0, 2 * tail)


def pass_k(results: Sequence[tuple[str, bool]]) -> Estimate:
    """Share of scenarios where every run passed (tau-bench's pass^k), with a 95% interval."""
    groups: dict[str, list[bool]] = defaultdict(list)
    for cluster, ok in results:
        groups[cluster].append(ok)
    passed = sum(all(v) for v in groups.values())
    return wilson(passed, len(groups))
