"""Piecewise-linear inputs of the solver models (``experiments/or-tampon-formulasyonu.md`` section 17). numpy only.

Distribution of a cell (A5): the quantile function is linear in the level between the five knots q_1..q_5 at
alpha_1..alpha_5 = 0.10 .. 0.95, so the CDF F is linear in x on every knot interval [q_j, q_j+1]. Outside
[q_1, q_5] nothing is assumed.

Objective of the minutes problem: E[(D - b)+] = T + S(b) for q_1 <= b <= q_5, with

    S(b) = integral_b^{q_5} (1 - F(x)) dx          (``grid_shortfall``; exact, piecewise quadratic)
    T    = E[(D - q_5)+]                            (tail beyond 0.95: NOT identified, constant in b)

so every solution comparison uses sum_c n_c S_c(b_c); the per-cell constant T_c cancels.

Domain of the buffer (same as the closed form ``allocation.common_level_allocation``): L_c = max(0, q_c1) <= b_c <=
U_c = max(0, q_c5), i.e. the buffers of the levels 0.10 and 0.95.

LP segments (``lp_segments``): [L_c, U_c] is cut at the knots and every knot interval into equal pieces no longer
than ``max_segment_min`` minutes. On a piece of length l the chord slope of S is exactly -(1 - F(midpoint)) (F is
linear there) and the chord lies above S by at most l * dF / 8 (dF = F increase over the piece; S'' = density). The
slopes increase along a cell (S is convex), so the LP fills the pieces in order without integer variables.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from flight_delay.optimization import newsvendor as nv

__all__ = [
    "Segments",
    "buffer_bounds",
    "grid_shortfall",
    "lp_segments",
    "undominated_options",
]

_TOLERANCE = 1e-9


def buffer_bounds(cell_knots: Any, levels: Sequence[float] = nv.KNOT_LEVELS) -> tuple[np.ndarray, np.ndarray]:
    """(L, U) = (max(0, q_1), max(0, q_5)) per cell: the buffer domain inside the knot grid."""
    q = nv.monotone_knots(cell_knots, levels)
    return np.maximum(0.0, q[:, 0]), np.maximum(0.0, q[:, -1])


def grid_shortfall(cell_knots: Any, buffers: Any, levels: Sequence[float] = nv.KNOT_LEVELS) -> np.ndarray:
    """S(b) = integral_b^{q_5} (1 - F(x)) dx per row (module docstring); 0 for b >= q_5; refused for b < q_1."""
    q = nv.monotone_knots(cell_knots, levels)
    b = np.asarray(buffers, dtype="float64").ravel()
    if b.shape != (q.shape[0],):
        raise ValueError("one buffer per knot row is required")
    if not np.all(np.isfinite(b)):
        raise ValueError("buffers must be finite")
    if np.any(b < q[:, 0] - _TOLERANCE):
        raise nv.GridError("A buffer below the first knot: E[(D - b)+] is not identified there (no tail invented)")
    grid = np.asarray(levels, dtype="float64")
    total = np.zeros(b.size)
    for j in range(q.shape[1] - 1):
        lo, hi = q[:, j], q[:, j + 1]
        start = np.clip(b, lo, hi)
        width = hi - lo
        with np.errstate(divide="ignore", invalid="ignore"):
            f_start = np.where(
                width > 0,
                grid[j] + (start - lo) / np.where(width > 0, width, 1.0) * (grid[j + 1] - grid[j]),
                grid[j + 1],
            )
        total += (hi - start) * (1.0 - 0.5 * (f_start + grid[j + 1]))
    return np.asarray(total, dtype="float64")


@dataclass(frozen=True)
class Segments:
    """LP pieces of every cell, ordered by cell and position (module docstring).

    Per piece: ``cell``, local index ``k`` (0, 1, ... inside its cell), ``start`` (minutes), ``length``, chord
    ``slope`` of S, ``value_start`` = S(start) and ``chord_error`` = length * dF / 8. Per cell: ``lower`` (L),
    ``upper`` (U), ``base`` = S(L), ``count`` (pieces), ``max_length`` and ``max_chord_error``.
    """

    cell: np.ndarray
    k: np.ndarray
    start: np.ndarray
    length: np.ndarray
    slope: np.ndarray
    value_start: np.ndarray
    chord_error: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    base: np.ndarray
    count: np.ndarray
    max_length: np.ndarray
    max_chord_error: np.ndarray
    max_segment_min: float

    @property
    def n_cells(self) -> int:
        return int(self.lower.size)

    @property
    def n_segments(self) -> int:
        return int(self.cell.size)

    def describe(self) -> dict[str, Any]:
        return {
            "cells": self.n_cells,
            "segments": self.n_segments,
            "segments_per_cell_mean": float(self.n_segments / max(self.n_cells, 1)),
            "segments_per_cell_max": int(self.count.max()) if self.count.size else 0,
            "max_segment_min": self.max_segment_min,
        }


def lp_segments(cell_knots: Any, *, max_segment_min: float = 2.0, levels: Sequence[float] = nv.KNOT_LEVELS) -> Segments:
    """Pieces of [L_c, U_c] for the LP (module docstring)."""
    step = float(max_segment_min)
    if not (np.isfinite(step) and step > 0):
        raise ValueError("max_segment_min must be > 0")
    q = nv.monotone_knots(cell_knots, levels)
    m, k = q.shape
    grid = np.asarray(levels, dtype="float64")
    lower, upper = np.maximum(0.0, q[:, 0]), np.maximum(0.0, q[:, -1])
    lo = np.clip(q[:, :-1], lower[:, None], upper[:, None])  # (m, k - 1) knot intervals clipped to the domain
    hi = np.clip(q[:, 1:], lower[:, None], upper[:, None])
    width = hi - lo
    pieces = np.where(width > _TOLERANCE, np.ceil(width / step - 1e-9), 0).astype("int64")
    pieces = np.where((width > _TOLERANCE) & (pieces < 1), 1, pieces)
    flat_pieces = pieces.ravel()  # row-major: cell-major, then knot interval
    interval = np.repeat(np.arange(flat_pieces.size), flat_pieces)
    first = np.cumsum(flat_pieces) - flat_pieces
    within = np.arange(interval.size) - first[interval]
    cell = interval // (k - 1)
    j = interval % (k - 1)
    piece_length = (width.ravel() / np.where(flat_pieces > 0, flat_pieces, 1))[interval]
    start = lo.ravel()[interval] + within * piece_length
    q_lo, q_hi = q[cell, j], q[cell, j + 1]
    density = (grid[j + 1] - grid[j]) / (q_hi - q_lo)  # q_hi > q_lo wherever a piece exists
    f_mid = grid[j] + (start + 0.5 * piece_length - q_lo) * density
    slope = -(1.0 - f_mid)
    chord_error = piece_length * (piece_length * density) / 8.0
    value_start = grid_shortfall(q[cell], start, levels) if cell.size else np.zeros(0)
    count = np.bincount(cell, minlength=m).astype("int64")
    k_local = np.arange(cell.size) - (np.cumsum(count) - count)[cell]
    max_length = np.zeros(m)
    max_error = np.zeros(m)
    if cell.size:
        np.maximum.at(max_length, cell, piece_length)
        np.maximum.at(max_error, cell, chord_error)
    return Segments(
        cell=np.asarray(cell, dtype="int64"),
        k=np.asarray(k_local, dtype="int64"),
        start=np.asarray(start, dtype="float64"),
        length=np.asarray(piece_length, dtype="float64"),
        slope=np.asarray(slope, dtype="float64"),
        value_start=np.asarray(value_start, dtype="float64"),
        chord_error=np.asarray(chord_error, dtype="float64"),
        lower=lower,
        upper=upper,
        base=grid_shortfall(q, lower, levels),
        count=count,
        max_length=max_length,
        max_chord_error=max_error,
        max_segment_min=step,
    )


def undominated_options(costs: Any, values: Any) -> np.ndarray:
    """Mask (rows, options) of the options that are not dominated inside their row (multiple-choice knapsack, min).

    Option j is dropped if another option i of the row has cost_i <= cost_j and value_i <= value_j (ties: the first
    after sorting by cost, value, index is kept). Replacing a dominated choice by its dominator never raises cost or
    value, so the integer optimum is unchanged. The cheapest option of every row is always kept.
    """
    c = np.asarray(costs, dtype="float64")
    v = np.asarray(values, dtype="float64")
    if c.ndim != 2 or c.shape != v.shape:
        raise ValueError("costs and values must be (rows, options) of the same shape")
    index = np.broadcast_to(np.arange(c.shape[1]), c.shape)
    order = np.lexsort((index, v, c), axis=1)
    v_sorted = np.take_along_axis(v, order, axis=1)
    running = np.minimum.accumulate(v_sorted, axis=1)
    previous = np.column_stack([np.full(c.shape[0], np.inf), running[:, :-1]]) if c.shape[1] else running
    keep_sorted = v_sorted < previous
    mask = np.zeros(c.shape, dtype=bool)
    np.put_along_axis(mask, order, keep_sorted, axis=1)
    return mask
