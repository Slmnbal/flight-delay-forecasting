"""Newsvendor core of the block-time buffer problem (``experiments/or-tampon-formulasyonu.md`` sections 2-4). No I/O.

Decision: an extra block-time buffer b >= 0 (minutes) added to the scheduled block time of a cell. Assumption A1: one
buffer minute removes exactly one minute of arrival delay (the flight itself is unchanged), so the arrival delay after
the buffer is D - b. Model predictions are NOT recomputed with the new block time (red team M8): the buffer only
shifts the predicted distribution.

Cost of one completed flight (c_u: per minute of remaining arrival delay, c_o: per unused buffer minute):

    cost(b, D) = c_u * (D - b)+  +  c_o * U(b, D),     U(b, D) = b - min(D+, b)   (buffer minutes not used)

Since U = b - D+ + (D - b)+ for b >= 0, cost = c_o * b + (c_u + c_o) * (D - b)+ - c_o * D+; the last term does not
depend on b, so E[cost] is minimised by F(b*) = c_u / (c_u + c_o) (the critical ratio tau), clipped at b* >= 0:
b* = max(0, Q(tau)). Only the ratio matters for b*; costs are reported with the normalisation c_u = tau,
c_o = 1 - tau (weighted minutes; the absolute scale is an assumption, not a price).

Distribution: the locked plan model gives five quantiles (``KNOT_LEVELS``). Between knots the quantile function is
LINEAR in the level (approximation A5). Outside [0.10, 0.95] nothing is assumed: levels outside the grid are refused
(``GridError``) and CDF values beyond the outer knots are returned as censored bounds with a flag.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

__all__ = [
    "ARR_DEL15_MIN",
    "DEFAULT_LEVEL_GRID",
    "KNOT_LEVELS",
    "MAX_LEVEL",
    "MIN_LEVEL",
    "GridError",
    "cdf_at",
    "check_level",
    "cost_weights",
    "critical_ratio",
    "crossing_rate",
    "implied_cost_ratio",
    "interpolate_quantile",
    "monotone_knots",
    "newsvendor_buffer",
    "realized_cost",
    "realized_outcomes",
]

KNOT_LEVELS: tuple[float, ...] = (0.10, 0.50, 0.80, 0.90, 0.95)  # locked plan quantile models (son-test-dondurma)
MIN_LEVEL = KNOT_LEVELS[0]
MAX_LEVEL = KNOT_LEVELS[-1]
DEFAULT_LEVEL_GRID: tuple[float, ...] = tuple(round(0.50 + 0.05 * i, 2) for i in range(10))  # 0.50 .. 0.95
ARR_DEL15_MIN = 15.0  # BTS ArrDel15 = ArrDelay >= 15 (targets.ARR_DEL15_THRESHOLD_MIN)
_TOLERANCE = 1e-12


class GridError(ValueError):
    """A quantile level outside the knot grid was requested (no tail is invented)."""


def check_level(level: float, levels: Sequence[float] = KNOT_LEVELS) -> float:
    """``level`` as float if it lies in [levels[0], levels[-1]]; GridError otherwise."""
    value = float(level)
    if not (levels[0] - _TOLERANCE <= value <= levels[-1] + _TOLERANCE):
        raise GridError(
            f"Level {value} is outside the quantile grid [{levels[0]}, {levels[-1]}]: refused (no tail extrapolation)"
        )
    return min(max(value, float(levels[0])), float(levels[-1]))


def _knots(knots: Any, levels: Sequence[float]) -> np.ndarray:
    array = np.asarray(knots, dtype="float64")
    if array.ndim == 1:
        array = array[None, :]
    if array.ndim != 2 or array.shape[1] != len(levels):
        raise ValueError(f"knots must have shape (n, {len(levels)}), got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError("Non-finite quantile knots")
    return array


def monotone_knots(knots: Any, levels: Sequence[float] = KNOT_LEVELS) -> np.ndarray:
    """Rows sorted ascending (rearrangement of crossing quantile models; all five levels together)."""
    return np.sort(_knots(knots, levels), axis=1)


def crossing_rate(knots: Any, levels: Sequence[float] = KNOT_LEVELS) -> float:
    """Share of rows whose raw knots are not ascending (reported before ``monotone_knots``)."""
    array = _knots(knots, levels)
    return float(np.mean(np.any(np.diff(array, axis=1) < 0, axis=1))) if array.shape[0] else 0.0


def interpolate_quantile(knots: Any, level: float, levels: Sequence[float] = KNOT_LEVELS) -> np.ndarray:
    """Q(level) per row: linear interpolation in the level between the two neighbouring knots (rows ascending)."""
    value = check_level(level, levels)
    q = _knots(knots, levels)
    grid = np.asarray(levels, dtype="float64")
    j = int(np.searchsorted(grid, value, side="right")) - 1
    j = min(max(j, 0), grid.size - 2)
    weight = (value - grid[j]) / (grid[j + 1] - grid[j])
    return np.asarray(q[:, j] + weight * (q[:, j + 1] - q[:, j]), dtype="float64")


def cdf_at(knots: Any, x: Any, levels: Sequence[float] = KNOT_LEVELS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """F(x) per row under the same linear interpolation: (value, below, above).

    ``below``: x < first knot, the value levels[0] is only an UPPER bound of F(x). ``above``: x > last knot, the
    value levels[-1] is only a LOWER bound. Ties between knots (flat quantile function) are handled (jump in F).
    """
    q = _knots(knots, levels)
    n, k = q.shape
    points = np.broadcast_to(np.asarray(x, dtype="float64"), (n,)).astype("float64")
    grid = np.asarray(levels, dtype="float64")
    count = np.sum(q <= points[:, None], axis=1)
    j = np.clip(count - 1, 0, k - 2)
    rows = np.arange(n)
    lo, hi = q[rows, j], q[rows, j + 1]
    width = hi - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        fraction = np.where(width > 0, (points - lo) / np.where(width > 0, width, 1.0), 1.0)
    fraction = np.clip(fraction, 0.0, 1.0)
    value = grid[j] + fraction * (grid[j + 1] - grid[j])
    below = points < q[:, 0]
    above = points > q[:, -1]
    value = np.where(below, grid[0], np.where(above, grid[-1], value))
    return np.asarray(value, dtype="float64"), np.asarray(below, dtype=bool), np.asarray(above, dtype=bool)


def critical_ratio(underage_cost: float, overage_cost: float) -> float:
    """tau = c_u / (c_u + c_o) (both > 0)."""
    c_u, c_o = float(underage_cost), float(overage_cost)
    if not (c_u > 0 and c_o > 0):
        raise ValueError("Both costs must be > 0")
    return c_u / (c_u + c_o)


def cost_weights(level: float) -> tuple[float, float]:
    """(c_u, c_o) = (tau, 1 - tau): the normalisation used for reported costs (c_u + c_o = 1)."""
    value = float(level)
    if not 0.0 < value < 1.0:
        raise ValueError(f"level must be in (0, 1): {value}")
    return value, 1.0 - value


def implied_cost_ratio(level: float) -> float:
    """c_u / c_o implied by a critical ratio tau: tau / (1 - tau) (e.g. 0.80 -> 4)."""
    c_u, c_o = cost_weights(level)
    return c_u / c_o


def newsvendor_buffer(knots: Any, level: float, levels: Sequence[float] = KNOT_LEVELS) -> np.ndarray:
    """b* = max(0, Q(tau)) per row (rows = flights or cells with ascending knots)."""
    return np.asarray(np.maximum(0.0, interpolate_quantile(knots, level, levels)), dtype="float64")


def realized_outcomes(delay: Any, buffer: Any, threshold: float = ARR_DEL15_MIN) -> dict[str, np.ndarray]:
    """Realised per-flight quantities for completed flights (finite delay) under buffer b >= 0.

    residual = (D - b)+ (arrival delay left), unused = b - min(D+, b), late15 = (D - b >= 15),
    absorbed = (D <= b) (the buffer covered the whole delay).
    """
    d = np.asarray(delay, dtype="float64").ravel()
    b = np.asarray(buffer, dtype="float64").ravel()
    if d.shape != b.shape:
        raise ValueError("delay and buffer differ in length")
    if not np.all(np.isfinite(d)):
        raise ValueError("Non-finite delays: pass completed flights only (cancelled / diverted have no ArrDelay)")
    if not np.all(np.isfinite(b)) or np.any(b < 0):
        raise ValueError("Buffers must be finite and >= 0")
    after = d - b
    return {
        "residual": np.maximum(after, 0.0),
        "unused": b - np.minimum(np.maximum(d, 0.0), b),
        "late15": (after >= threshold).astype("float64"),
        "absorbed": (d <= b).astype("float64"),
    }


def realized_cost(residual: Any, unused: Any, level: float) -> np.ndarray:
    """tau * residual + (1 - tau) * unused (normalised weighted minutes, ``cost_weights``)."""
    c_u, c_o = cost_weights(level)
    return np.asarray(c_u * np.asarray(residual, dtype="float64") + c_o * np.asarray(unused, dtype="float64"))
