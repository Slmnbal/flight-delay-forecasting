"""Split-conformal adjustment of quantile predictions (plan section 5.4), numpy only.

- One-sided upper bound (plan 5.4, the OR need): score s = y - q_alpha(x) on the calibration set, offset
  c = the k-th smallest score with k = ceil((n + 1) * alpha); adjusted bound q_alpha(x) + c. Under exchangeability of
  calibration and new rows P(y <= q + c) >= alpha (and < alpha + 1 / (n + 1) without ties). If k > n the offset is
  +inf (too few calibration rows for that level) - reported, never silently capped.
- Two-sided 80 % interval, CQR (conformalized quantile regression, Romano et al. 2019): score
  s = max(lo(x) - y, y - hi(x)) with the alpha 0.10 / 0.90 models, offset c = k-th smallest with
  k = ceil((n + 1) * 0.80); interval [lo - c, hi + c]. c can be negative (the raw interval was too wide).
- Why numpy instead of MAPIE (plan 5.4 named MAPIE for the CQR): the models are already fitted LightGBM boosters and
  the method is the formula above; our own function is about ten lines, has a synthetic coverage test, and avoids
  wrapping boosters into scikit-learn estimators for a library API that this run could not check (the installed
  ``mapie`` package could not be read from this environment). A cross-check against MAPIE is an open item.
- Monotone after adjustment: the same offset is added to every row, so q080 + c80 <= q095 + c95 is NOT guaranteed
  (c80 may exceed c95 - (q095 - q080) on some rows); ``adjusted_crossing_rate`` reports it.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from flight_delay.modeling import metrics as mt

__all__ = [
    "adjusted_crossing_rate",
    "conformal_rank",
    "conformal_quantile",
    "cqr_offset",
    "cqr_scores",
    "one_sided_offset",
    "one_sided_scores",
]

_RANK_TOLERANCE = 1e-9  # (n + 1) * level is computed in floating point; 100 * 0.8 must give rank 80, not 81


def conformal_rank(n: int, level: float) -> int:
    """k = ceil((n + 1) * level), the order statistic of the split-conformal quantile (may exceed n)."""
    if n < 1:
        raise ValueError("Need at least one calibration score")
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1): {level}")
    return int(math.ceil((n + 1) * level - _RANK_TOLERANCE))


def conformal_quantile(scores: Any, level: float) -> float:
    """k-th smallest score (k = ``conformal_rank``); +inf if k > n."""
    values = np.asarray(scores, dtype="float64").ravel()
    if not np.all(np.isfinite(values)):
        raise ValueError("Non-finite conformity scores (filter the target universe first)")
    k = conformal_rank(values.size, level)
    if k > values.size:
        return float("inf")
    return float(np.partition(values, k - 1)[k - 1])


def one_sided_scores(y: Any, upper: Any) -> np.ndarray:
    values, q = mt._real(y, upper)
    return np.asarray(values - q, dtype="float64")


def one_sided_offset(y: Any, upper: Any, alpha: float) -> float:
    """Offset c with P(y <= upper + c) >= alpha (plan 5.4)."""
    return conformal_quantile(one_sided_scores(y, upper), alpha)


def cqr_scores(y: Any, lower: Any, upper: Any) -> np.ndarray:
    values, lo = mt._real(y, lower)
    _, hi = mt._real(y, upper)
    return np.asarray(np.maximum(lo - values, values - hi), dtype="float64")


def cqr_offset(y: Any, lower: Any, upper: Any, coverage: float) -> float:
    """Offset c with P(lower - c <= y <= upper + c) >= coverage (CQR)."""
    return conformal_quantile(cqr_scores(y, lower, upper), coverage)


def adjusted_crossing_rate(lower_bound: Any, higher_bound: Any) -> float:
    """Share of rows where the adjusted lower-level bound exceeds the adjusted higher-level one."""
    lo = np.asarray(lower_bound, dtype="float64").ravel()
    hi = np.asarray(higher_bound, dtype="float64").ravel()
    if lo.shape != hi.shape:
        raise ValueError("Bounds differ in length")
    return float(np.mean(lo > hi)) if lo.size else 0.0
