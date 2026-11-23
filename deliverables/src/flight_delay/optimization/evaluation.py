"""Out-of-sample evaluation of buffer policies with the REALISED arrival delays (formulation section 8). No I/O.

- Rows: every scheduled flight of the evaluation period. Planned buffer minutes are summed over all scheduled flights
  (the schedule is set before cancellations are known); realised quantities only over completed flights (finite
  ArrDelay). Cancelled / diverted flights have no arrival delay: they are counted, not costed.
- Per policy and critical ratio tau: mean / total normalised cost tau * residual + (1 - tau) * unused, residual delay
  minutes, unused buffer minutes, ArrDel15 rate after the buffer (D - b >= 15), share of delays fully absorbed (D <= b).
- Paired differences (policy - reference) with the calendar-day block bootstrap of ``flight_delay.modeling.bootstrap``
  (B replicates, one seed, the SAME day multiplicities for every comparison of a period; percentile interval).
- Budget curve: for planned budgets beta minutes per scheduled flight, the common-level allocation of B1 and of the plan
  model and the ArrDel15 knapsack of the plan model are compared at EQUAL planned minutes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from flight_delay.modeling import bootstrap as bs
from flight_delay.optimization import allocation as al
from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization.policies import Cells, level_key

__all__ = ["DEFAULT_BUDGETS_PER_FLIGHT", "DayDesign", "evaluate_budget_curve", "evaluate_policies", "score_policies"]

DEFAULT_BUDGETS_PER_FLIGHT: tuple[float, ...] = (1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0)  # minutes per scheduled flight
_METRICS = ("cost", "residual", "unused", "late15", "absorbed")


class DayDesign:
    """Completed-row mask, day codes and the bootstrap day multiplicities of one evaluation period."""

    def __init__(self, dates: Any, delay: Any, month: Any, *, replicates: int, seed: int) -> None:
        self.delay_all = np.asarray(delay, dtype="float64").ravel()
        self.completed = np.isfinite(self.delay_all)
        if not self.completed.any():
            raise ValueError("No completed flight in the evaluation period")
        all_dates = np.asarray(dates).ravel()
        if all_dates.shape != self.delay_all.shape:
            raise ValueError("dates and delay differ in length")
        self.codes, self.days = bs.day_index(all_dates[self.completed])
        self.n_days = int(self.days.size)
        self.multiplicities = bs.day_multiplicities(self.n_days, replicates=replicates, seed=seed)
        self.replicates, self.seed = int(replicates), int(seed)
        self.delay = self.delay_all[self.completed]
        months = np.asarray(month).astype(str).ravel()[self.completed]
        self.month_labels, inverse = np.unique(months, return_inverse=True)
        self.month_codes = np.asarray(inverse, dtype="int64").ravel()

    def describe(self) -> dict[str, Any]:
        return {
            "days": self.n_days,
            "first_day": str(self.days[0]),
            "last_day": str(self.days[-1]),
            "bootstrap": {"unit": "calendar day (FlightDate)", "replicates": self.replicates, "seed": self.seed},
        }


def _per_row(design: DayDesign, buffer_all: np.ndarray, level: float | None) -> dict[str, np.ndarray]:
    outcome = nv.realized_outcomes(design.delay, buffer_all[design.completed])
    if level is not None:
        outcome["cost"] = nv.realized_cost(outcome["residual"], outcome["unused"], level)
    return outcome


def _monthly(design: DayDesign, rows: Mapping[str, np.ndarray], buffer: np.ndarray) -> dict[str, dict[str, float]]:
    counts = np.bincount(design.month_codes, minlength=design.month_labels.size).astype("float64")
    out: dict[str, dict[str, float]] = {}
    sums = {
        name: np.bincount(design.month_codes, weights=values, minlength=design.month_labels.size)
        for name, values in (*rows.items(), ("buffer", buffer))
    }
    for i, label in enumerate(design.month_labels):
        out[str(label)] = {"n": float(counts[i]), **{f"{k}_mean": float(v[i] / counts[i]) for k, v in sums.items()}}
    return out


def score_policies(
    design: DayDesign,
    buffers: Mapping[str, Any],
    *,
    level: float | None,
    comparisons: Sequence[tuple[str, str]] = (),
    ci_level: float = bs.CI_LEVEL,
    monthly: bool = True,
) -> dict[str, Any]:
    """Metrics per policy and bootstrap differences for one tau (``level``; None = no cost, e.g. budget curves)."""
    per_row: dict[str, dict[str, np.ndarray]] = {}
    policies: dict[str, Any] = {}
    for name, values in buffers.items():
        buffer_all = np.asarray(values, dtype="float64").ravel()
        if buffer_all.shape != design.delay_all.shape:
            raise ValueError(f"{name}: one buffer per scheduled row is required")
        rows = _per_row(design, buffer_all, level)
        per_row[name] = rows
        entry: dict[str, Any] = {
            "buffer_planned_total_min": float(buffer_all.sum()),
            "buffer_planned_mean_min": float(buffer_all.mean()),
            "buffer_completed_mean_min": float(buffer_all[design.completed].mean()),
            "residual_total_min": float(rows["residual"].sum()),
            "residual_mean_min": float(rows["residual"].mean()),
            "unused_mean_min": float(rows["unused"].mean()),
            "arr_del15_rate": float(rows["late15"].mean()),
            "absorbed_rate": float(rows["absorbed"].mean()),
        }
        if "cost" in rows:
            entry["cost_mean"] = float(rows["cost"].mean())
            entry["cost_total"] = float(rows["cost"].sum())
        if monthly:
            entry["monthly"] = _monthly(design, rows, buffer_all[design.completed])
        policies[name] = entry
    compared: dict[str, Any] = {}
    for policy, reference in comparisons:
        if policy not in per_row or reference not in per_row:
            continue
        block: dict[str, Any] = {}
        for metric in _METRICS:
            if metric not in per_row[policy] or metric not in per_row[reference]:
                continue
            diff = per_row[policy][metric] - per_row[reference][metric]
            means = bs.DayMeans(diff, design.codes, design.n_days)
            result = bs.summarize_draws(means(None), means.replicates(design.multiplicities), level=ci_level)
            block[f"d_{metric}"] = result.to_dict()
        reference_cost = policies[reference].get("cost_mean")
        if reference_cost:
            block["relative_cost_change"] = block["d_cost"]["estimate"] / reference_cost
        compared[f"{policy}-{reference}"] = block
    return {"policies": policies, "comparisons": compared}


def evaluate_policies(
    design: DayDesign,
    buffers_by_level: Mapping[float, Mapping[str, Any]],
    *,
    comparisons: Sequence[tuple[str, str]],
    ci_level: float = bs.CI_LEVEL,
) -> dict[str, Any]:
    """``score_policies`` for every tau of the grid (keys 't050' ...), with c_u / c_o implied by each tau."""
    out: dict[str, Any] = {}
    for level, buffers in buffers_by_level.items():
        scored = score_policies(design, buffers, level=float(level), comparisons=comparisons, ci_level=ci_level)
        c_u, c_o = nv.cost_weights(level)
        out[level_key(level)] = {
            "level": float(level),
            "cost_weights": {"c_u": c_u, "c_o": c_o, "c_u_over_c_o": nv.implied_cost_ratio(level)},
            **scored,
        }
    return out


def evaluate_budget_curve(
    design: DayDesign,
    cells: Cells,
    cell_knots: Mapping[str, np.ndarray],
    *,
    budgets_per_flight: Sequence[float] = DEFAULT_BUDGETS_PER_FLIGHT,
    ci_level: float = bs.CI_LEVEL,
) -> dict[str, Any]:
    """Equal-budget comparison (module docstring). ``cell_knots`` needs 'plan' and 'b1'."""
    counts = cells.counts()
    scheduled = float(counts.sum())
    out: dict[str, Any] = {}
    for beta in budgets_per_flight:
        budget = float(beta) * scheduled
        plan = al.common_level_allocation(cell_knots["plan"], counts, budget)
        b1 = al.common_level_allocation(cell_knots["b1"], counts, budget)
        knapsack, knapsack_cells, censored = al.arrdel15_allocation(cell_knots["plan"], counts, budget)
        buffers: dict[str, np.ndarray] = {"plan_arrdel15_budget": knapsack_cells[cells.codes]}
        for name, solution in (("plan_budget", plan), ("b1_budget", b1)):
            if solution.status != "below_grid":
                buffers[name] = solution.buffers[cells.codes]
        scored = score_policies(
            design,
            buffers,
            level=None,
            comparisons=(("plan_budget", "b1_budget"), ("plan_arrdel15_budget", "b1_budget")),
            ci_level=ci_level,
            monthly=False,
        )
        out[f"b{beta:g}"] = {
            "budget_per_flight_min": float(beta),
            "budget_total_min": budget,
            "allocations": {
                "plan_budget": plan.to_dict() | {"implied_c_u_over_c_o": _ratio(plan.level)},
                "b1_budget": b1.to_dict() | {"implied_c_u_over_c_o": _ratio(b1.level)},
                "plan_arrdel15_budget": knapsack.to_dict() | {"cells_censored_at_zero_buffer": censored},
            },
            **scored,
        }
    return out


def _ratio(level: float | None) -> float | None:
    if level is None or level >= 1.0:
        return None
    return nv.implied_cost_ratio(level)
