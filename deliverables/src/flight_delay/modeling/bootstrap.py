"""Calendar-day block bootstrap of paired metric differences and the Holm correction (plan section 5.2), numpy only.

- Resampling unit: the calendar day (``FlightDate``). One replicate draws D days with replacement from the D evaluation
  days; every flight of a drawn day enters as often as the day was drawn. Flights of one day share weather and network
  effects, so rows are not independent (plan 5.2). Both models are scored on the SAME replicate (paired difference).
- A replicate is a vector m of day multiplicities (length D, sum D). ``day_multiplicities`` draws B of them with
  ``numpy.random.default_rng(seed)`` (plan: B = 1000, seed 42). Every statistic here takes m and is computed as a
  weighted statistic with row weight m[day(row)]; this is EXACTLY the statistic of the materialised resample (the rows
  of a day repeated m times), which the tests check against ``metrics``. No resample is copied.
- ROC-AUC (average ranks for ties, i.e. P(s+ > s-) + P(tie) / 2) and average precision (scikit-learn definition: sum
  over distinct scores of (R_n - R_{n-1}) * P_n) need the rows sorted by score only once (``RankedScores``); per
  replicate only weighted counts per distinct score are summed. Means (Brier, pinball, coverage, mean prediction - y)
  use per-day sums (``DayMeans``), so a replicate costs O(D).
- Interval: percentile, the (1 - level) / 2 and (1 + level) / 2 quantiles of the replicate values (``numpy.percentile``,
  linear interpolation). Two-sided p-value of "difference = 0": p = 2 * min(share(d* <= 0), share(d* >= 0)), capped at
  1 (plan 5.2). With B = 1000 the smallest non-zero p is 0.002; p = 0 means no replicate had the other sign and is
  reported as p < 1/B. Replicates where a statistic is undefined (e.g. no positive drawn) are dropped and counted.
- Holm (step-down) adjusted p-values for one family; a hypothesis is rejected where the adjusted p <= alpha.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.modeling import metrics as mt

__all__ = [
    "CI_LEVEL",
    "DEFAULT_REPLICATES",
    "DEFAULT_SEED",
    "HOLM_ALPHA",
    "BootstrapResult",
    "DayMeans",
    "RankedScores",
    "SlopeStatistic",
    "bootstrap",
    "day_index",
    "day_multiplicities",
    "holm",
    "summarize_draws",
    "weighted_calibration_slope_intercept",
]

DEFAULT_REPLICATES = 1000  # plan 5.2
DEFAULT_SEED = 42  # plan 5.2
CI_LEVEL = 0.95
HOLM_ALPHA = 0.05  # plan 5.2
_LOGIT_CLIP = 1e-6  # same clipping as metrics.calibration_slope_intercept


def day_index(dates: Any) -> tuple[np.ndarray, np.ndarray]:
    """(day code per row in 0..D-1, the D sorted distinct days as datetime64[D]). Missing dates are an error."""
    values = pd.to_datetime(pd.Series(np.asarray(dates).ravel()), errors="coerce")
    if bool(values.isna().any()):
        raise ValueError("Missing dates: every evaluation row needs its FlightDate")
    days = values.dt.normalize().to_numpy(dtype="datetime64[D]")
    unique, codes = np.unique(days, return_inverse=True)
    return np.asarray(codes, dtype="int64").ravel(), unique


def day_multiplicities(n_days: int, *, replicates: int = DEFAULT_REPLICATES, seed: int = DEFAULT_SEED) -> np.ndarray:
    """(replicates, n_days) int64: how often each day is drawn in each replicate (each row sums to n_days)."""
    if n_days < 1:
        raise ValueError("Need at least one day")
    if replicates < 1:
        raise ValueError("Need at least one replicate")
    rng = np.random.default_rng(seed)
    out = np.empty((replicates, n_days), dtype="int64")
    for b in range(replicates):
        out[b] = np.bincount(rng.integers(0, n_days, size=n_days), minlength=n_days)
    return out


def _codes(day: Any, size: int) -> np.ndarray:
    codes = np.asarray(day, dtype="int64").ravel()
    if codes.shape != (size,):
        raise ValueError(f"day codes and values differ in length: {codes.shape} vs {size}")
    if codes.size and codes.min() < 0:
        raise ValueError("day codes must be >= 0")
    return codes


class RankedScores:
    """Rows of one score vector sorted once; weighted ROC-AUC and average precision for any day multiplicities."""

    def __init__(self, y_true: Any, y_score: Any, day: Any) -> None:
        labels, scores = mt._binary(y_true, y_score)
        codes = _codes(day, labels.size)
        order = np.argsort(scores, kind="mergesort")
        sorted_scores = scores[order]
        self._y = labels[order]
        self._day = codes[order]
        starts = np.r_[True, sorted_scores[1:] != sorted_scores[:-1]]
        self._group = np.cumsum(starts) - 1  # ascending distinct-score groups
        self._n_groups = int(self._group[-1]) + 1
        self.n = int(labels.size)

    def _counts(self, multiplicities: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
        if multiplicities is None:
            weights = np.ones(self.n, dtype="float64")
        else:
            weights = np.asarray(multiplicities, dtype="float64")[self._day]
        positive = np.bincount(self._group, weights=weights * self._y, minlength=self._n_groups)
        negative = np.bincount(self._group, weights=weights * (1.0 - self._y), minlength=self._n_groups)
        return positive, negative

    @staticmethod
    def _auc(positive: np.ndarray, negative: np.ndarray) -> float:
        n_pos, n_neg = float(positive.sum()), float(negative.sum())
        if n_pos == 0 or n_neg == 0:
            return float("nan")
        below = np.cumsum(negative) - negative
        return float(np.sum(positive * (below + 0.5 * negative)) / (n_pos * n_neg))

    @staticmethod
    def _average_precision(positive: np.ndarray, negative: np.ndarray) -> float:
        tp = np.cumsum(positive[::-1])
        fp = np.cumsum(negative[::-1])
        n_pos = float(tp[-1]) if tp.size else 0.0
        if n_pos == 0:
            return float("nan")
        predicted = tp + fp
        precision = np.divide(tp, predicted, out=np.zeros_like(tp), where=predicted > 0)
        recall = tp / n_pos
        return float(np.sum(np.diff(np.r_[0.0, recall]) * precision))

    def roc_auc(self, multiplicities: np.ndarray | None = None) -> float:
        return self._auc(*self._counts(multiplicities))

    def average_precision(self, multiplicities: np.ndarray | None = None) -> float:
        return self._average_precision(*self._counts(multiplicities))

    def both(self, multiplicities: np.ndarray | None = None) -> tuple[float, float]:
        """(ROC-AUC, average precision) from one pass over the rows."""
        positive, negative = self._counts(multiplicities)
        return self._auc(positive, negative), self._average_precision(positive, negative)


class DayMeans:
    """Weighted mean of a per-row value: sum_d m_d S_d / sum_d m_d n_d (S_d, n_d: sum and row count of day d)."""

    def __init__(self, values: Any, day: Any, n_days: int) -> None:
        array = np.asarray(values, dtype="float64").ravel()
        if not np.all(np.isfinite(array)):
            raise ValueError("Non-finite values (filter the universe first)")
        codes = _codes(day, array.size)
        if codes.size and codes.max() >= n_days:
            raise ValueError("day code outside 0..n_days-1")
        self.sums = np.bincount(codes, weights=array, minlength=n_days)
        self.counts = np.bincount(codes, minlength=n_days).astype("float64")

    def __call__(self, multiplicities: np.ndarray | None = None) -> float:
        if multiplicities is None:
            total = float(self.counts.sum())
            return float(self.sums.sum() / total) if total > 0 else float("nan")
        weights = np.asarray(multiplicities, dtype="float64")
        denominator = float(weights @ self.counts)
        return float(weights @ self.sums / denominator) if denominator > 0 else float("nan")

    def replicates(self, multiplicities: np.ndarray) -> np.ndarray:
        """All replicate values at once (B,)."""
        weights = np.asarray(multiplicities, dtype="float64")
        denominator = weights @ self.counts
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.asarray(np.where(denominator > 0, (weights @ self.sums) / denominator, np.nan), dtype="float64")


def weighted_calibration_slope_intercept(
    y_true: Any, y_prob: Any, weights: Any | None = None, *, max_iter: int = 100, tol: float = 1e-10
) -> tuple[float, float]:
    """``metrics.calibration_slope_intercept`` with row weights (same damped Newton, same start, same clipping).

    With integer weights the result is the fit on the rows repeated that many times; with no weights it equals the
    unweighted function. (NaN, NaN) where the fit is undefined (constant logit, one class, no convergence).
    """
    y, p = mt._binary(y_true, y_prob)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype="float64").ravel()
    if w.shape != y.shape or not np.all(np.isfinite(w)) or np.any(w < 0):
        raise ValueError("weights must be finite, >= 0 and as long as y")
    keep = w > 0
    if not np.any(keep):
        return float("nan"), float("nan")
    y, p, w = y[keep], p[keep], w[keep]
    clipped = np.clip(p, _LOGIT_CLIP, 1.0 - _LOGIT_CLIP)
    x = np.log(clipped / (1.0 - clipped))
    if np.ptp(x) < 1e-12 or y.min() == y.max():
        return float("nan"), float("nan")
    rate = float(np.sum(w * y) / np.sum(w))
    beta = np.array([np.log(rate / (1.0 - rate)), 0.0])

    def log_likelihood(b: np.ndarray) -> float:
        z = b[0] + b[1] * x
        return float(np.sum(w * (y * z - np.logaddexp(0.0, z))))

    current = log_likelihood(beta)
    for _ in range(max_iter):
        mu = mt._sigmoid(beta[0] + beta[1] * x)
        residual = w * (y - mu)
        gradient = np.array([residual.sum(), (residual * x).sum()])
        h = w * mu * (1.0 - mu)
        hx = h * x
        hessian = np.array([[h.sum(), hx.sum()], [hx.sum(), (hx * x).sum()]])
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            return float("nan"), float("nan")
        if not np.all(np.isfinite(step)):
            return float("nan"), float("nan")
        scale = 1.0
        while True:
            candidate = beta + scale * step
            value = log_likelihood(candidate)
            if value >= current - 1e-12 * max(1.0, abs(current)):
                break
            scale *= 0.5
            if scale < 1e-10:
                return float("nan"), float("nan")
        beta, current = candidate, value
        if np.max(np.abs(scale * step)) < tol:
            return float(beta[0]), float(beta[1])
    return float("nan"), float("nan")


class SlopeStatistic:
    """Calibration slope (logistic recalibration) of one probability vector for day multiplicities."""

    def __init__(self, y_true: Any, y_prob: Any, day: Any) -> None:
        self._y, self._p = mt._binary(y_true, y_prob)
        self._day = _codes(day, self._y.size)

    def __call__(self, multiplicities: np.ndarray | None = None) -> float:
        weights = None if multiplicities is None else np.asarray(multiplicities, dtype="float64")[self._day]
        return weighted_calibration_slope_intercept(self._y, self._p, weights)[1]


@dataclass(frozen=True)
class BootstrapResult:
    """Point estimate on the full set, percentile interval, two-sided p-value of 0 and replicate counts."""

    estimate: float
    ci_low: float
    ci_high: float
    p_value: float
    level: float
    replicates: int
    finite_replicates: int
    share_at_or_below_zero: float
    share_at_or_above_zero: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_draws(estimate: float, draws: Any, *, level: float = CI_LEVEL) -> BootstrapResult:
    """Percentile interval and p-value (module docstring) from replicate values ``draws``."""
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1): {level}")
    values = np.asarray(draws, dtype="float64").ravel()
    finite = values[np.isfinite(values)]
    nan = float("nan")
    if finite.size == 0:
        return BootstrapResult(float(estimate), nan, nan, nan, level, int(values.size), 0, nan, nan)
    tail = (1.0 - level) / 2.0 * 100.0
    low, high = np.percentile(finite, [tail, 100.0 - tail])
    below = float(np.mean(finite <= 0.0))
    above = float(np.mean(finite >= 0.0))
    return BootstrapResult(
        estimate=float(estimate),
        ci_low=float(low),
        ci_high=float(high),
        p_value=min(1.0, 2.0 * min(below, above)),
        level=level,
        replicates=int(values.size),
        finite_replicates=int(finite.size),
        share_at_or_below_zero=below,
        share_at_or_above_zero=above,
    )


def bootstrap(
    statistic: Callable[[np.ndarray | None], float], multiplicities: np.ndarray, *, level: float = CI_LEVEL
) -> BootstrapResult:
    """Generic day-block bootstrap of one statistic: ``statistic(None)`` is the full-set value."""
    draws = np.array([statistic(m) for m in np.asarray(multiplicities)], dtype="float64")
    return summarize_draws(float(statistic(None)), draws, level=level)


def holm(p_values: Mapping[str, float | None], *, alpha: float = HOLM_ALPHA) -> dict[str, dict[str, Any]]:
    """Holm step-down adjusted p-values; a missing / NaN p counts as 1 (never rejected) and is flagged."""
    names = list(p_values)
    m = len(names)
    clean: list[float] = []
    missing: list[bool] = []
    for name in names:
        value = p_values[name]
        if value is None or not math.isfinite(float(value)):
            missing.append(True)
            clean.append(1.0)
        else:
            missing.append(False)
            clean.append(float(value))
    order = sorted(range(m), key=lambda i: (clean[i], i))
    out: dict[str, dict[str, Any]] = {}
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * clean[i]))
        out[names[i]] = {
            "p_value": None if missing[i] else clean[i],
            "p_holm": running,
            "rank": rank + 1,
            "reject": bool(running <= alpha),
            "p_missing": missing[i],
        }
    return {name: out[name] for name in names}
