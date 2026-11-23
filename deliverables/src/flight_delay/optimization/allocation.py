"""Network-budget versions of the buffer problem (``experiments/or-tampon-formulasyonu.md`` section 5). No I/O.

Budget: B planned buffer minutes over all scheduled flights of the period, sum_c n_c * b_c <= B (n_c = scheduled
flights of cell c; each flight's block time costs aircraft and crew minutes, so the budget is in flight-minutes).

1. Expected delay minutes (``common_level_allocation``):

       min  sum_c n_c * E[(D_c - b_c)+]   s.t.  sum_c n_c * b_c <= B,  b_c >= 0.

   The objective is separable and convex (d/db E[(D - b)+] = -(1 - F(b))). KKT with multiplier lambda >= 0 gives
   1 - F_c(b_c) = lambda wherever b_c > 0, i.e. b_c = max(0, Q_c(1 - lambda)): every cell uses the SAME quantile
   level tau = 1 - lambda, and tau is found by bisection so that the budget is used (the budget is a monotone,
   continuous function of tau). No tail is needed: the solution only evaluates Q_c inside the grid. If the budget
   exceeds what tau = 0.95 needs, the budget is not binding inside the grid (status ``grid_top``; nothing beyond
   0.95 is invented); if it is below what tau = 0.10 needs, the optimum lies below the grid (``below_grid``).
   The multiplier is the implied cost ratio: c_u / c_o = tau / (1 - tau).

2. Expected ArrDel15 count (``arrdel15_allocation``): min sum_c n_c * P(D_c - b_c >= 15) under the same budget.
   P(D - b >= 15) = 1 - F(15 + b) is piecewise linear in b between the knots but not convex, so this is a
   multiple-choice knapsack (one buffer per cell from the candidates b = 0 and b = q_k - 15 at the knots, where the
   piecewise-linear objective has its breakpoints). ``mckp_greedy`` solves the LP relaxation exactly on the lower
   convex hull of every cell (Sinha-Zoltners) and returns a feasible integer solution: the fractional increment is
   dropped, its cell is frozen, later increments of the other cells are still taken while they fit (the gap to the LP
   bound is reported and bounds the distance to the integer optimum). ``mckp_milp`` (scipy HiGHS, optional) is
   the exact MILP for small instances (tests).
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from flight_delay.optimization import newsvendor as nv

__all__ = [
    "BudgetSolution",
    "KnapsackSolution",
    "arrdel15_allocation",
    "arrdel15_candidates",
    "cell_budget",
    "common_level_allocation",
    "lower_hull",
    "mckp_greedy",
    "mckp_milp",
]

_BUDGET_TOLERANCE = 1e-9


@dataclass(frozen=True)
class BudgetSolution:
    """Common-level solution: ``buffers`` per cell (NaN when ``status == 'below_grid'``)."""

    budget: float
    level: float | None
    used: float
    status: str  # 'binding' | 'grid_top' | 'below_grid' | 'zero'
    buffers: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {"budget": self.budget, "level": self.level, "used": self.used, "status": self.status}


@dataclass(frozen=True)
class KnapsackSolution:
    """Multiple-choice knapsack solution: chosen candidate per cell, objective of the integer solution and LP bound."""

    budget: float
    choice: np.ndarray  # index of the chosen option per row
    chosen_cost: np.ndarray  # cost of the chosen option per row
    used: float
    value: float
    lp_value: float
    fractional_cell: int | None
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "used": self.used,
            "value": self.value,
            "lp_value": self.lp_value,
            "gap": self.value - self.lp_value,
            "fractional_cell": self.fractional_cell,
            "method": self.method,
        }


def _counts(cell_n: Any, size: int) -> np.ndarray:
    n = np.asarray(cell_n, dtype="float64").ravel()
    if n.shape != (size,) or not np.all(np.isfinite(n)) or np.any(n < 0):
        raise ValueError("cell_n must be finite, >= 0 and one value per cell")
    return n


def cell_budget(cell_knots: Any, cell_n: Any, level: float, levels: Sequence[float] = nv.KNOT_LEVELS) -> float:
    """sum_c n_c * max(0, Q_c(level)): planned flight-minutes of the common-level policy."""
    buffers = nv.newsvendor_buffer(cell_knots, level, levels)
    return float(np.sum(_counts(cell_n, buffers.size) * buffers))


def common_level_allocation(
    cell_knots: Any,
    cell_n: Any,
    budget: float,
    *,
    levels: Sequence[float] = nv.KNOT_LEVELS,
    tolerance: float = 1e-7,
    max_iter: int = 200,
) -> BudgetSolution:
    """Exact solution of problem 1 of the module docstring (bisection on the common level)."""
    total = float(budget)
    if not np.isfinite(total) or total < 0:
        raise ValueError("budget must be finite and >= 0")
    knots = nv.monotone_knots(cell_knots, levels)
    n = _counts(cell_n, knots.shape[0])
    low, high = float(levels[0]), float(levels[-1])
    if total == 0.0:
        return BudgetSolution(total, None, 0.0, "zero", np.zeros(knots.shape[0]))
    top = cell_budget(knots, n, high, levels)
    if total >= top - _BUDGET_TOLERANCE:
        return BudgetSolution(total, high, top, "grid_top", nv.newsvendor_buffer(knots, high, levels))
    if cell_budget(knots, n, low, levels) > total + _BUDGET_TOLERANCE:
        return BudgetSolution(total, None, float("nan"), "below_grid", np.full(knots.shape[0], np.nan))
    for _ in range(max_iter):
        if high - low <= tolerance:
            break
        middle = 0.5 * (low + high)
        if cell_budget(knots, n, middle, levels) <= total + _BUDGET_TOLERANCE:
            low = middle
        else:
            high = middle
    buffers = nv.newsvendor_buffer(knots, low, levels)
    return BudgetSolution(total, low, float(np.sum(n * buffers)), "binding", buffers)


def arrdel15_candidates(
    cell_knots: Any, threshold: float = nv.ARR_DEL15_MIN, levels: Sequence[float] = nv.KNOT_LEVELS
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(buffers (m, k + 1), late share 1 - F(threshold + b) (m, k + 1), censored (m,)).

    Column 0 is b = 0; column j + 1 is max(0, q_j - threshold). ``censored``: the late share at b = 0 lies beyond the
    outer knots (below: true share >= value, i.e. optimistic; above: true share <= value), flagged, not invented.
    """
    knots = nv.monotone_knots(cell_knots, levels)
    m = knots.shape[0]
    buffers = np.column_stack([np.zeros(m), np.maximum(0.0, knots - float(threshold))])
    late = np.empty_like(buffers)
    censored = np.zeros(m, dtype=bool)
    for column in range(buffers.shape[1]):
        value, below, above = nv.cdf_at(knots, float(threshold) + buffers[:, column], levels)
        late[:, column] = 1.0 - value
        censored |= below | above
    return buffers, late, censored


def lower_hull(costs: Any, values: Any) -> list[int]:
    """Indices of the lower convex hull of (cost, value) points, starting at the cheapest point, value decreasing."""
    c = np.asarray(costs, dtype="float64").ravel()
    v = np.asarray(values, dtype="float64").ravel()
    order = sorted(range(c.size), key=lambda i: (c[i], v[i], i))
    kept: list[int] = []
    for i in order:  # one point per cost (lowest value), then only strictly better values
        if kept and c[i] == c[kept[-1]]:
            continue
        if kept and v[i] >= v[kept[-1]]:
            continue
        kept.append(i)
    hull: list[int] = []
    for i in kept:
        while len(hull) >= 2:
            a, b = hull[-2], hull[-1]
            cross = (c[b] - c[a]) * (v[i] - v[a]) - (v[b] - v[a]) * (c[i] - c[a])
            if cross <= 0:
                hull.pop()
            else:
                break
        hull.append(i)
    return hull


def mckp_greedy(costs: Any, values: Any, budget: float) -> KnapsackSolution:
    """LP relaxation of the multiple-choice knapsack (min value, sum cost <= budget, one option per row) by the
    convex-hull greedy (``lp_value``) and a feasible integer solution (module docstring, problem 2)."""
    c = np.asarray(costs, dtype="float64")
    v = np.asarray(values, dtype="float64")
    if c.ndim != 2 or c.shape != v.shape:
        raise ValueError("costs and values must be (rows, options) of the same shape")
    if not (np.all(np.isfinite(c)) and np.all(np.isfinite(v))) or np.any(c < 0):
        raise ValueError("costs must be finite and >= 0, values finite")
    total = float(budget)
    rows = c.shape[0]
    choice = np.zeros(rows, dtype="int64")
    increments: list[tuple[float, int, int, int, float, float]] = []
    for r in range(rows):
        hull = lower_hull(c[r], v[r])
        choice[r] = hull[0]
        for step in range(1, len(hull)):
            dc = float(c[r, hull[step]] - c[r, hull[step - 1]])
            dv = float(v[r, hull[step - 1]] - v[r, hull[step]])
            increments.append((dv / dc, r, step, hull[step], dc, dv))
    used = float(np.sum(c[np.arange(rows), choice]))
    if used > total + _BUDGET_TOLERANCE:
        raise ValueError("The cheapest option of every row already exceeds the budget")
    value = float(np.sum(v[np.arange(rows), choice]))
    lp_value: float | None = None
    fractional: int | None = None
    blocked: set[int] = set()
    for _efficiency, r, _step, index, dc, dv in sorted(increments, key=lambda t: (-t[0], t[1], t[2])):
        if r in blocked:
            continue  # a row's hull steps are taken in order only
        if used + dc <= total + _BUDGET_TOLERANCE:
            choice[r] = index
            used += dc
            value -= dv
        else:
            if lp_value is None:  # the first increment that does not fit closes the LP relaxation
                lp_value = value - (total - used) / dc * dv
                fractional = r
            blocked.add(r)
    if lp_value is None:
        lp_value = value
    return KnapsackSolution(total, choice, c[np.arange(rows), choice], used, value, lp_value, fractional, "hull_greedy")


def mckp_milp(costs: Any, values: Any, budget: float) -> KnapsackSolution | None:
    """Exact multiple-choice knapsack with scipy.optimize.milp (HiGHS); None if scipy is not installed or the solver
    fails. Dense matrices: meant for small instances (tests, spot checks)."""
    try:
        optimize: Any = importlib.import_module("scipy.optimize")
    except ImportError:
        return None
    c = np.asarray(costs, dtype="float64")
    v = np.asarray(values, dtype="float64")
    rows, options = c.shape
    size = rows * options
    one_per_row = np.zeros((rows, size))
    for r in range(rows):
        one_per_row[r, r * options : (r + 1) * options] = 1.0
    result = optimize.milp(
        c=v.ravel(),
        constraints=[
            optimize.LinearConstraint(one_per_row, 1.0, 1.0),
            optimize.LinearConstraint(c.ravel()[None, :], -np.inf, float(budget)),
        ],
        integrality=np.ones(size),
        bounds=optimize.Bounds(0.0, 1.0),
    )
    if not bool(result.success):
        return None
    x = np.asarray(result.x, dtype="float64").reshape(rows, options)
    choice = np.argmax(x, axis=1)
    chosen_cost = c[np.arange(rows), choice]
    value = float(np.sum(v[np.arange(rows), choice]))
    return KnapsackSolution(
        float(budget), choice, chosen_cost, float(chosen_cost.sum()), value, float(result.fun), None, "milp"
    )


def arrdel15_allocation(
    cell_knots: Any,
    cell_n: Any,
    budget: float,
    *,
    threshold: float = nv.ARR_DEL15_MIN,
    levels: Sequence[float] = nv.KNOT_LEVELS,
) -> tuple[KnapsackSolution, np.ndarray, int]:
    """Problem 2 of the module docstring: (solution, buffers per cell, number of censored cells)."""
    buffers, late, censored = arrdel15_candidates(cell_knots, threshold, levels)
    n = _counts(cell_n, buffers.shape[0])
    solution = mckp_greedy(n[:, None] * buffers, n[:, None] * late, budget)
    chosen = buffers[np.arange(buffers.shape[0]), solution.choice]
    return solution, chosen, int(censored.sum())
