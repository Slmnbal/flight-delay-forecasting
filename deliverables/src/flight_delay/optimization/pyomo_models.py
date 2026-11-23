"""Pyomo models of the budget problems, solved with HiGHS (``experiments/or-tampon-formulasyonu.md`` section 17).

Pyomo and highspy are OPTIONAL (proposed extra ``optimization = ["pyomo", "highspy"]``): they are imported inside the
functions, never at module level. The solver is ``pyo.SolverFactory("appsi_highs")``. Component names follow the
symbols of the formulation document.

1. Minutes LP (``build_minutes_lp`` / ``MinutesLP``), segment ("delta") form:

       sets      C (cells), K = {(c, k)}: pieces k of the buffer domain of cell c (``piecewise.lp_segments``)
       params    n[c] scheduled flights, L[c] / U[c] buffer bounds, S0[c] = S_c(L_c),
                 ell[c, k] piece length (min), a[c, k] chord slope of S_c (< 0, increasing in k), B budget
       vars      b[c] in [L[c], U[c]] (buffer, min), y[c, k] in [0, ell[c, k]] (minutes taken on piece k)
       objective expected_delay = sum_c n[c] * (S0[c] + sum_k a[c, k] * y[c, k])
       subject   link[c]:  b[c] = L[c] + sum_k y[c, k]
                 budget:   sum_c n[c] * b[c] <= B

   Epigraph form (``formulation="epigraph"``, same optimum): t[c] >= S_c(U_c) and
   epi[c, k]: t[c] >= S_c(p[c, k]) + a[c, k] * (b[c] - p[c, k]) (p = piece start), objective sum_c n[c] * t[c].
   Because S_c is convex the LP takes the pieces in order; its optimum is the chord interpolation of the exact
   problem solved in closed form by ``allocation.common_level_allocation`` (cross-check: ``compare_minutes``).

2. ArrDel15 MILP (``solve_arrdel15_milp``), multiple-choice knapsack:

       sets      C (cells in the model), J = {(c, j)}: undominated candidates j of cell c
       params    n[c], beta[c, j] candidate buffer (min), pi[c, j] = P(D_c - beta[c, j] >= 15), B budget,
                 late_fixed / used_fixed: late flights and minutes of the cells fixed outside the model
       vars      x[c, j] in {0, 1}
       objective expected_late = late_fixed + sum n[c] * pi[c, j] * x[c, j]
       subject   one_choice[c]: sum_j x[c, j] = 1
                 budget:        used_fixed + sum n[c] * beta[c, j] * x[c, j] <= B
"""

from __future__ import annotations

import importlib
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from flight_delay.optimization import allocation as al
from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization import piecewise as pw

__all__ = [
    "FORMULATIONS",
    "SOLVER_NAME",
    "LpSolution",
    "MilpSolution",
    "MinutesLP",
    "SolveReport",
    "SolverUnavailableError",
    "build_minutes_lp",
    "compare_minutes",
    "make_solver",
    "pyomo_available",
    "solve_arrdel15_milp",
]

SOLVER_NAME = "appsi_highs"
FORMULATIONS = ("segments", "epigraph")
_BUDGET_TOLERANCE = 1e-6


class SolverUnavailableError(RuntimeError):
    """Pyomo or the HiGHS interface (highspy) is not installed or not usable."""


def _pyomo() -> Any:
    try:
        return importlib.import_module("pyomo.environ")
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise SolverUnavailableError(
            "pyomo is not installed (proposed extra 'optimization': pyomo, highspy)"
        ) from error


def pyomo_available() -> bool:
    """True if pyomo and highspy can be found (nothing is imported)."""
    util = importlib.import_module("importlib.util")
    return all(util.find_spec(name) is not None for name in ("pyomo", "highspy"))


def make_solver() -> Any:
    """``pyo.SolverFactory("appsi_highs")``; SolverUnavailableError if HiGHS cannot be used."""
    pyo = _pyomo()
    solver = pyo.SolverFactory(SOLVER_NAME)
    try:
        usable = bool(solver.available(exception_flag=False))
    except Exception as error:  # noqa: BLE001 - any failure means the solver cannot be used
        raise SolverUnavailableError(f"{SOLVER_NAME} is not available: {error!r}") from error
    if not usable:
        raise SolverUnavailableError(f"{SOLVER_NAME} is not available (highspy missing?)")
    return solver


@dataclass(frozen=True)
class SolveReport:
    """What the solver reported: termination, best feasible objective (upper bound) and best bound (lower)."""

    termination: str
    has_solution: bool
    objective: float | None
    bound: float | None
    mip_gap: float | None
    seconds: float
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "termination": self.termination,
            "has_solution": self.has_solution,
            "objective": self.objective,
            "bound": self.bound,
            "mip_gap": self.mip_gap,
            "seconds": round(self.seconds, 3),
            "message": self.message,
        }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _solve(solver: Any, model: Any, *, time_limit: float, options: Mapping[str, Any]) -> SolveReport:
    """One solve through the legacy interface of ``appsi_highs`` (solution and duals loaded into the model)."""
    started = time.perf_counter()
    extra = {"options": dict(options)} if options else {}
    try:
        results = solver.solve(model, timelimit=float(time_limit), load_solutions=True, **extra)
    except RuntimeError as error:  # appsi raises when no feasible solution can be loaded
        return SolveReport("no_feasible_solution", False, None, None, None, time.perf_counter() - started, str(error))
    seconds = time.perf_counter() - started
    condition = str(results.solver.termination_condition)
    upper = _finite(getattr(results.problem, "upper_bound", None))
    lower = _finite(getattr(results.problem, "lower_bound", None))
    gap = None
    if upper is not None and lower is not None:
        gap = abs(upper - lower) / max(abs(upper), 1e-10)
    return SolveReport(condition, True, upper, lower, gap, seconds)


# ----------------------------------------------------------------------------
# 1. minutes LP
# ----------------------------------------------------------------------------


def build_minutes_lp(segments: pw.Segments, cell_n: Any, *, formulation: str = "segments") -> Any:
    """Pyomo model of problem 1 of the module docstring (budget ``B`` is a mutable parameter, initially 0)."""
    if formulation not in FORMULATIONS:
        raise ValueError(f"formulation must be one of {FORMULATIONS}: {formulation!r}")
    pyo = _pyomo()
    n = np.asarray(cell_n, dtype="float64").ravel()
    if n.shape != (segments.n_cells,):
        raise ValueError("one flight count per cell is required")
    cells = range(segments.n_cells)
    pairs = list(zip(segments.cell.tolist(), segments.k.tolist(), strict=True))
    count = segments.count.tolist()

    model = pyo.ConcreteModel(name=f"minutes_budget_lp_{formulation}")
    model.C = pyo.Set(initialize=cells, ordered=True, doc="cells")
    model.K = pyo.Set(dimen=2, initialize=pairs, ordered=True, doc="pieces (c, k) of the buffer domain")
    model.n = pyo.Param(model.C, initialize=dict(enumerate(n.tolist())), doc="scheduled flights")
    model.L = pyo.Param(model.C, initialize=dict(enumerate(segments.lower.tolist())), doc="buffer at level 0.10")
    model.U = pyo.Param(model.C, initialize=dict(enumerate(segments.upper.tolist())), doc="buffer at level 0.95")
    model.ell = pyo.Param(model.K, initialize=dict(zip(pairs, segments.length.tolist(), strict=True)), doc="length")
    model.a = pyo.Param(model.K, initialize=dict(zip(pairs, segments.slope.tolist(), strict=True)), doc="slope")
    model.B = pyo.Param(mutable=True, initialize=0.0, doc="budget (flight-minutes)")
    model.b = pyo.Var(model.C, bounds=lambda m, c: (m.L[c], m.U[c]), doc="buffer (minutes)")
    model.budget = pyo.Constraint(expr=pyo.quicksum(model.n[c] * model.b[c] for c in model.C) <= model.B)
    if formulation == "segments":
        model.S0 = pyo.Param(model.C, initialize=dict(enumerate(segments.base.tolist())), doc="S_c(L_c)")
        model.y = pyo.Var(model.K, bounds=lambda m, c, k: (0.0, m.ell[c, k]), doc="minutes taken on piece k")
        model.link = pyo.Constraint(
            model.C, rule=lambda m, c: m.b[c] == m.L[c] + pyo.quicksum(m.y[c, k] for k in range(count[c]))
        )
        model.expected_delay = pyo.Objective(
            expr=pyo.quicksum(model.n[c] * model.S0[c] for c in model.C)
            + pyo.quicksum(model.n[c] * model.a[c, k] * model.y[c, k] for c, k in model.K),
            sense=pyo.minimize,
        )
    else:
        model.p = pyo.Param(model.K, initialize=dict(zip(pairs, segments.start.tolist(), strict=True)), doc="start")
        model.S_p = pyo.Param(
            model.K, initialize=dict(zip(pairs, segments.value_start.tolist(), strict=True)), doc="S_c(p[c, k])"
        )
        floor = dict(enumerate(_shortfall_at_upper(segments).tolist()))  # S_c(U_c) = min of S_c on the domain
        model.t = pyo.Var(model.C, bounds=lambda m, c: (floor[c], None), doc="epigraph of S_c")
        model.epi = pyo.Constraint(
            model.K, rule=lambda m, c, k: m.t[c] >= m.S_p[c, k] + m.a[c, k] * (m.b[c] - m.p[c, k])
        )
        model.expected_delay = pyo.Objective(
            expr=pyo.quicksum(model.n[c] * model.t[c] for c in model.C), sense=pyo.minimize
        )
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
    return model


def _shortfall_at_upper(segments: pw.Segments) -> np.ndarray:
    """S_c(U_c): end of the last piece (chords are exact at piece ends); S_c(L_c) for cells without pieces (L = U)."""
    out = np.asarray(segments.base, dtype="float64").copy()
    if segments.n_segments:
        last = np.cumsum(segments.count) - 1
        has = segments.count > 0
        idx = last[has]
        out[has] = segments.value_start[idx] + segments.slope[idx] * segments.length[idx]
    return out


@dataclass(frozen=True)
class LpSolution:
    """LP result for one budget. ``objective_true`` = sum_c n_c S_c(b_c) evaluated exactly at the LP buffers."""

    budget: float
    status: str  # 'binding' | 'grid_top' | 'below_grid' | 'zero' | 'no_solution'
    buffers: np.ndarray | None
    used: float | None
    objective_lp: float | None
    objective_true: float | None
    implied_level: float | None
    report: SolveReport | None
    formulation: str
    sizes: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "status": self.status,
            "used": self.used,
            "objective_lp": self.objective_lp,
            "objective_true": self.objective_true,
            "implied_level": self.implied_level,
            "solver": None if self.report is None else self.report.to_dict(),
            "formulation": self.formulation,
            "sizes": self.sizes,
        }


class MinutesLP:
    """Problem 1 for one set of cells: the Pyomo model is built once; ``solve`` changes only ``B`` and re-solves."""

    def __init__(
        self,
        cell_knots: Any,
        cell_n: Any,
        *,
        formulation: str = "segments",
        max_segment_min: float = 2.0,
        levels: Sequence[float] = nv.KNOT_LEVELS,
    ) -> None:
        started = time.perf_counter()
        self.knots = nv.monotone_knots(cell_knots, levels)
        self.levels = tuple(levels)
        self.n = al._counts(cell_n, self.knots.shape[0])
        self.formulation = formulation
        self.segments = pw.lp_segments(self.knots, max_segment_min=max_segment_min, levels=levels)
        self.model = build_minutes_lp(self.segments, self.n, formulation=formulation)
        self.solver = make_solver()
        self.build_seconds = time.perf_counter() - started
        variables = self.segments.n_cells + (
            self.segments.n_segments if formulation == "segments" else self.segments.n_cells
        )
        constraints = 1 + (self.segments.n_cells if formulation == "segments" else self.segments.n_segments)
        self.sizes = {
            "cells": self.segments.n_cells,
            "pieces": self.segments.n_segments,
            "variables": int(variables),
            "constraints": int(constraints),
        }

    def chord_error_bound(self) -> float:
        """sum_c n_c * max_k chord error: LP objective <= exact optimum + this bound."""
        return float(np.sum(self.n * self.segments.max_chord_error))

    def solve(self, budget: float, *, time_limit: float = 300.0) -> LpSolution:
        pyo = _pyomo()
        total = float(budget)
        if not np.isfinite(total) or total < 0:
            raise ValueError("budget must be finite and >= 0")
        if total == 0.0:
            return LpSolution(
                total, "zero", np.zeros(self.n.size), 0.0, None, None, None, None, self.formulation, self.sizes
            )
        if float(np.sum(self.n * self.segments.lower)) > total + _BUDGET_TOLERANCE:
            return LpSolution(total, "below_grid", None, None, None, None, None, None, self.formulation, self.sizes)
        self.model.B.set_value(total)
        report = _solve(self.solver, self.model, time_limit=time_limit, options={})
        if not report.has_solution:
            return LpSolution(total, "no_solution", None, None, None, None, None, report, self.formulation, self.sizes)
        buffers = np.fromiter((pyo.value(self.model.b[c]) for c in self.model.C), dtype="float64", count=self.n.size)
        buffers = np.clip(buffers, self.segments.lower, self.segments.upper)  # solver round-off only
        used = float(np.sum(self.n * buffers))
        status = "binding" if used >= total - max(1e-6 * total, 1e-6) else "grid_top"
        dual = _finite(self.model.dual.get(self.model.budget)) if hasattr(self.model, "dual") else None
        implied = None if dual is None else 1.0 - abs(dual)  # d objective / d B = -(1 - tau)
        objective_lp = _finite(pyo.value(self.model.expected_delay))
        objective_true = float(np.sum(self.n * pw.grid_shortfall(self.knots, buffers, self.levels)))
        return LpSolution(
            total, status, buffers, used, objective_lp, objective_true, implied, report, self.formulation, self.sizes
        )


def compare_minutes(
    lp: LpSolution,
    closed_form: al.BudgetSolution,
    cell_knots: Any,
    cell_n: Any,
    segments: pw.Segments,
    *,
    levels: Sequence[float] = nv.KNOT_LEVELS,
    buffer_factor: float = 2.0,
) -> dict[str, Any]:
    """Cross-check of the LP with the closed form (formulation 17.1).

    Certificate: exact optimum <= LP objective <= exact optimum + chord bound (LP solves the chord interpolation,
    which lies above S and is exact at the piece ends). Buffers agree if |b_LP - b_CF| <= ``buffer_factor`` times
    the longest piece of the cell. Constraint violations (budget, bounds) must be 0.
    """
    knots = nv.monotone_knots(cell_knots, levels)
    n = al._counts(cell_n, knots.shape[0])
    out: dict[str, Any] = {
        "lp_status": lp.status,
        "closed_form_status": closed_form.status,
        "closed_form_level": closed_form.level,
        "lp_implied_level": lp.implied_level,
    }
    if lp.buffers is None or closed_form.status == "below_grid":
        out["agrees"] = lp.status == closed_form.status == "below_grid"
        out["reason"] = "no buffers to compare"
        return out
    cf = np.asarray(closed_form.buffers, dtype="float64")
    diff = np.abs(lp.buffers - cf)
    tolerance = buffer_factor * segments.max_length + 1e-6
    exact_cf = float(np.sum(n * pw.grid_shortfall(knots, cf, levels)))
    bound = float(np.sum(n * segments.max_chord_error))
    scale = max(1.0, abs(exact_cf))
    objective_lp = lp.objective_lp if lp.objective_lp is not None else lp.objective_true
    # the bisection leaves (B - used) <= tolerance unused; its value is at most 1 per flight-minute (1 - tau < 1)
    slack = max(0.0, lp.budget - float(closed_form.used))
    lower_ok = objective_lp is not None and objective_lp >= exact_cf - slack - 1e-7 * scale
    upper_ok = objective_lp is not None and objective_lp <= exact_cf + bound + 1e-7 * scale
    violations = {
        "budget": int((lp.used or 0.0) > lp.budget + max(1e-7 * lp.budget, 1e-6)),
        "below_lower_bound": int(np.sum(lp.buffers < segments.lower - 1e-6)),
        "above_upper_bound": int(np.sum(lp.buffers > segments.upper + 1e-6)),
        "negative": int(np.sum(lp.buffers < -1e-9)),
    }
    within = diff <= tolerance
    out.update(
        {
            "objective_closed_form_exact": exact_cf,
            "objective_lp": objective_lp,
            "objective_lp_buffers_exact": lp.objective_true,
            "chord_error_bound": bound,
            "objective_relative_difference": None if objective_lp is None else (objective_lp - exact_cf) / scale,
            "certificate_lower_ok": bool(lower_ok),
            "certificate_upper_ok": bool(upper_ok),
            "buffer_abs_diff_max": float(diff.max()) if diff.size else 0.0,
            "buffer_abs_diff_mean": float(diff.mean()) if diff.size else 0.0,
            "buffer_abs_diff_p99": float(np.quantile(diff, 0.99)) if diff.size else 0.0,
            "buffer_tolerance_rule": f"|b_LP - b_CF| <= {buffer_factor:g} x longest piece of the cell",
            "cells_within_tolerance_share": float(within.mean()) if diff.size else 1.0,
            "used_lp": lp.used,
            "used_closed_form": closed_form.used,
            "level_difference": None
            if lp.implied_level is None or closed_form.level is None
            else lp.implied_level - closed_form.level,
            "violations": violations,
        }
    )
    out["agrees"] = bool(lower_ok and upper_ok and all(v == 0 for v in violations.values()) and bool(np.all(within)))
    return out


# ----------------------------------------------------------------------------
# 2. ArrDel15 MILP
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class MilpSolution:
    """MILP result: ``choice`` (column per row, all rows), objective of the rounded solution and solver report."""

    budget: float
    choice: np.ndarray | None
    used: float | None
    value: float | None
    report: SolveReport | None
    sizes: dict[str, int]
    violations: dict[str, int]
    restriction: dict[str, Any]
    build_seconds: float

    @property
    def valid(self) -> bool:
        return self.choice is not None and all(v == 0 for v in self.violations.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "used": self.used,
            "value": self.value,
            "valid": self.valid,
            "solver": None if self.report is None else self.report.to_dict(),
            "sizes": self.sizes,
            "violations": self.violations,
            "restriction": self.restriction,
            "build_seconds": round(self.build_seconds, 3),
        }


def solve_arrdel15_milp(
    buffers: Any,
    late: Any,
    cell_n: Any,
    budget: float,
    *,
    time_limit: float = 60.0,
    mip_rel_gap: float = 1e-6,
    active: Any | None = None,
    fixed_choice: Any | None = None,
    solver: Any | None = None,
) -> MilpSolution:
    """Problem 2 of the module docstring with HiGHS (Pyomo).

    ``buffers`` / ``late``: (cells, candidates) candidate buffers beta and late shares pi; ``cell_n``: flights per
    cell. Dominated candidates are removed first (``piecewise.undominated_options``; the optimum is unchanged). Rows
    with ``active == False`` are fixed at ``fixed_choice`` (size restriction, documented in the result); rows with a
    single undominated candidate are fixed at it.
    """
    pyo = _pyomo()
    started = time.perf_counter()
    beta = np.asarray(buffers, dtype="float64")
    pi = np.asarray(late, dtype="float64")
    if beta.ndim != 2 or beta.shape != pi.shape:
        raise ValueError("buffers and late must be (cells, candidates) of the same shape")
    rows = beta.shape[0]
    n = al._counts(cell_n, rows)
    cost, value = n[:, None] * beta, n[:, None] * pi
    if not (np.all(np.isfinite(cost)) and np.all(np.isfinite(value))) or np.any(beta < 0):
        raise ValueError("candidate buffers must be finite and >= 0, late shares finite")
    keep = pw.undominated_options(cost, value)
    is_active = np.ones(rows, dtype=bool) if active is None else np.asarray(active, dtype=bool).ravel()
    if is_active.shape != (rows,):
        raise ValueError("active: one flag per cell")
    fixed = np.argmin(np.where(keep, cost, np.inf), axis=1)  # cheapest undominated candidate
    if fixed_choice is not None:
        given = np.asarray(fixed_choice, dtype="int64").ravel()
        if given.shape != (rows,):
            raise ValueError("fixed_choice: one candidate per cell")
        fixed = np.where(is_active, fixed, given)
    elif not is_active.all():
        raise ValueError("fixed_choice is required when some cells are inactive")
    in_model = is_active & (keep.sum(axis=1) > 1)
    single = is_active & ~in_model
    fixed = np.where(single, np.argmax(keep, axis=1), fixed)
    out_rows = np.flatnonzero(~in_model)
    used_fixed = float(np.sum(cost[out_rows, fixed[out_rows]]))
    late_fixed = float(np.sum(value[out_rows, fixed[out_rows]]))
    model_rows = np.flatnonzero(in_model)
    pairs = [(int(r), int(j)) for r in model_rows for j in np.flatnonzero(keep[r])]
    restriction = {
        "cells": rows,
        "cells_in_model": int(model_rows.size),
        "cells_fixed_inactive": int((~is_active).sum()),
        "cells_fixed_single_candidate": int(single.sum()),
        "candidates_before_dominance": int(beta.size),
        "candidates_after_dominance": int(keep.sum()),
    }
    sizes = {"binaries": len(pairs), "constraints": int(model_rows.size) + 1}

    model = pyo.ConcreteModel(name="arrdel15_mckp_milp")
    model.C = pyo.Set(initialize=model_rows.tolist(), ordered=True, doc="cells in the model")
    model.J = pyo.Set(dimen=2, initialize=pairs, ordered=True, doc="undominated candidates (c, j)")
    model.n = pyo.Param(model.C, initialize={int(r): float(n[r]) for r in model_rows}, doc="scheduled flights")
    model.beta = pyo.Param(model.J, initialize={p: float(beta[p]) for p in pairs}, doc="candidate buffer (min)")
    model.pi = pyo.Param(model.J, initialize={p: float(pi[p]) for p in pairs}, doc="P(D - beta >= 15)")
    model.B = pyo.Param(initialize=float(budget), doc="budget (flight-minutes)")
    model.used_fixed = pyo.Param(initialize=used_fixed, doc="minutes of the fixed cells")
    model.late_fixed = pyo.Param(initialize=late_fixed, doc="expected late flights of the fixed cells")
    model.x = pyo.Var(model.J, domain=pyo.Binary, doc="1 if candidate j is chosen for cell c")
    by_cell: dict[int, list[int]] = {}
    for r, j in pairs:
        by_cell.setdefault(r, []).append(j)
    model.one_choice = pyo.Constraint(model.C, rule=lambda m, c: pyo.quicksum(m.x[c, j] for j in by_cell[c]) == 1)
    model.budget = pyo.Constraint(
        expr=model.used_fixed + pyo.quicksum(model.n[c] * model.beta[c, j] * model.x[c, j] for c, j in model.J)
        <= model.B
    )
    model.expected_late = pyo.Objective(
        expr=model.late_fixed + pyo.quicksum(model.n[c] * model.pi[c, j] * model.x[c, j] for c, j in model.J),
        sense=pyo.minimize,
    )
    build_seconds = time.perf_counter() - started
    if used_fixed > float(budget) + _BUDGET_TOLERANCE:
        return MilpSolution(
            float(budget), None, None, None, None, sizes, {"fixed_cells_exceed_budget": 1}, restriction, build_seconds
        )
    choice = fixed.copy()
    picks = np.zeros(rows, dtype="int64")
    if not pairs:
        report = SolveReport("trivial", True, late_fixed, late_fixed, 0.0, 0.0)
    else:
        options = {"mip_rel_gap": float(mip_rel_gap)}
        report = _solve(solver or make_solver(), model, time_limit=time_limit, options=options)
        if not report.has_solution:
            return MilpSolution(float(budget), None, None, None, report, sizes, {}, restriction, build_seconds)
        for r, j in pairs:
            if (pyo.value(model.x[r, j], exception=False) or 0.0) > 0.5:
                choice[r] = j
                picks[r] += 1
    picked_wrong = int(np.sum(picks[model_rows] != 1))
    used = float(np.sum(cost[np.arange(rows), choice]))
    total_value = float(np.sum(value[np.arange(rows), choice]))
    violations = {
        "one_choice": picked_wrong,
        "budget": int(used > float(budget) + max(1e-7 * float(budget), 1e-6)),
    }
    return MilpSolution(float(budget), choice, used, total_value, report, sizes, violations, restriction, build_seconds)
