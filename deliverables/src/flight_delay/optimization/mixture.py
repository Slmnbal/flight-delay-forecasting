"""Mixture cell distribution (exploratory; ``experiments/or-tampon-formulasyonu.md`` section 17.3). No I/O.

The first run's cell distribution averages the flights' quantiles level by level (Vincentisation, A6). The mixture
distribution of a cell averages the flights' CDFs instead:

    F_c^mix(x) = (1 / n_c) * sum_{i in c} F_i(x)

with every F_i under the same linear interpolation between its five knots (A5). No tail is invented: for x below a
flight's first knot F_i(x) is only known to be <= 0.10 and above its last knot only >= 0.95; the boundary value is
used (``newsvendor.cdf_at`` convention) and the share of such CENSORED flights is returned with every value.

Quantiles of the mixture (``mixture_quantile``) are found by bisection on F_c^mix (monotone); ArrDel15 knapsack
candidates (``mixture_arrdel15_candidates``) are b = 0 and b = max(0, Q_c^mix(alpha) - 15) on a fixed level grid
(the exact breakpoints of F_c^mix are all knots of all flights of the cell: too many, so the candidate set is
limited to the grid and this is reported as an approximation).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from flight_delay.optimization import newsvendor as nv

__all__ = [
    "DEFAULT_CANDIDATE_LEVELS",
    "MixtureCandidates",
    "MixtureValue",
    "mixture_arrdel15_candidates",
    "mixture_cdf",
    "mixture_quantile",
]

DEFAULT_CANDIDATE_LEVELS: tuple[float, ...] = tuple(round(0.10 + 0.05 * i, 2) for i in range(18))  # 0.10 .. 0.95


@dataclass(frozen=True)
class MixtureValue:
    """F_c^mix at one point per cell and the share of the cell's flights censored below / above their knots."""

    value: np.ndarray
    below_share: np.ndarray
    above_share: np.ndarray

    @property
    def censored_share(self) -> np.ndarray:
        return np.asarray(self.below_share + self.above_share, dtype="float64")


def _codes(codes: Any, rows: int, n_cells: int) -> tuple[np.ndarray, np.ndarray]:
    c = np.asarray(codes, dtype="int64").ravel()
    if c.shape != (rows,):
        raise ValueError("codes and flight knots differ in length")
    counts = np.bincount(c, minlength=n_cells).astype("float64")
    if counts.size != n_cells or np.any(counts == 0):
        raise ValueError("Every cell needs at least one flight (codes in 0 .. n_cells - 1)")
    return c, counts


def mixture_cdf(
    flight_knots: Any, codes: Any, n_cells: int, x: Any, levels: Sequence[float] = nv.KNOT_LEVELS
) -> MixtureValue:
    """F_c^mix(x_c) for one point x_c per cell (module docstring)."""
    q = nv.monotone_knots(flight_knots, levels)
    c, counts = _codes(codes, q.shape[0], n_cells)
    return _cdf_sorted(q, c, counts, n_cells, x, levels)


def _cdf_sorted(
    q: np.ndarray, c: np.ndarray, counts: np.ndarray, n_cells: int, x: Any, levels: Sequence[float]
) -> MixtureValue:
    """``mixture_cdf`` on knots that are already ascending and validated codes (no re-sort inside bisection)."""
    points = np.asarray(x, dtype="float64").ravel()
    if points.shape != (n_cells,):
        raise ValueError("one point per cell is required")
    value, below, above = nv.cdf_at(q, points[c], levels)
    return MixtureValue(
        value=np.bincount(c, weights=value, minlength=n_cells) / counts,
        below_share=np.bincount(c, weights=below.astype("float64"), minlength=n_cells) / counts,
        above_share=np.bincount(c, weights=above.astype("float64"), minlength=n_cells) / counts,
    )


def mixture_quantile(
    flight_knots: Any,
    codes: Any,
    n_cells: int,
    level: float,
    *,
    iterations: int = 50,
    levels: Sequence[float] = nv.KNOT_LEVELS,
) -> np.ndarray:
    """Q_c^mix(level) = inf{x: F_c^mix(x) >= level} per cell by bisection (level inside the knot grid).

    Bracket: [min_i q_i1, max_i q_i5] of the cell, where F_c^mix = 0.10 and 0.95 under the censoring convention.
    """
    alpha = nv.check_level(level, levels)
    q = nv.monotone_knots(flight_knots, levels)
    c, counts = _codes(codes, q.shape[0], n_cells)
    low = np.full(n_cells, np.inf)
    high = np.full(n_cells, -np.inf)
    np.minimum.at(low, c, q[:, 0])
    np.maximum.at(high, c, q[:, -1])
    if alpha <= levels[0]:
        return low
    for _ in range(int(iterations)):
        middle = 0.5 * (low + high)
        reached = _cdf_sorted(q, c, counts, n_cells, middle, levels).value >= alpha
        high = np.where(reached, middle, high)
        low = np.where(reached, low, middle)
    return np.asarray(high, dtype="float64")


@dataclass(frozen=True)
class MixtureCandidates:
    """Knapsack candidates per cell: column 0 is b = 0, column l + 1 is max(0, Q^mix(levels[l]) - threshold)."""

    buffers: np.ndarray  # (cells, 1 + L)
    late: np.ndarray  # 1 - F^mix(threshold + b)
    censored_share: np.ndarray  # share of the cell's flights outside their knots at threshold + b
    candidate_levels: tuple[float, ...]

    def describe(self) -> dict[str, Any]:
        return {
            "cells": int(self.buffers.shape[0]),
            "candidates_per_cell": int(self.buffers.shape[1]),
            "candidate_levels": list(self.candidate_levels),
            "cells_with_censored_flights_at_zero_buffer": int(np.sum(self.censored_share[:, 0] > 0)),
            "censored_share_at_zero_buffer_mean": float(np.mean(self.censored_share[:, 0]))
            if self.buffers.size
            else None,
        }


def mixture_arrdel15_candidates(
    flight_knots: Any,
    codes: Any,
    n_cells: int,
    *,
    candidate_levels: Sequence[float] = DEFAULT_CANDIDATE_LEVELS,
    threshold: float = nv.ARR_DEL15_MIN,
    iterations: int = 50,
    levels: Sequence[float] = nv.KNOT_LEVELS,
) -> MixtureCandidates:
    """ArrDel15 knapsack candidates under the mixture distribution (module docstring)."""
    chosen = tuple(nv.check_level(a, levels) for a in candidate_levels)
    q = nv.monotone_knots(flight_knots, levels)
    c, _ = _codes(codes, q.shape[0], n_cells)
    columns = [np.zeros(n_cells)]
    for alpha in chosen:
        quantile = mixture_quantile(q, c, n_cells, alpha, iterations=iterations, levels=levels)
        columns.append(np.maximum(0.0, quantile - float(threshold)))
    buffers = np.column_stack(columns)
    late = np.empty_like(buffers)
    censored = np.empty_like(buffers)
    for column in range(buffers.shape[1]):
        result = mixture_cdf(q, c, n_cells, float(threshold) + buffers[:, column], levels)
        late[:, column] = 1.0 - result.value
        censored[:, column] = result.censored_share
    return MixtureCandidates(buffers=buffers, late=late, censored_share=censored, candidate_levels=chosen)
