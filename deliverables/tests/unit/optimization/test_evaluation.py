"""Realised metrics, paired day-block bootstrap and the equal-budget curve (synthetic rows, not data)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from flight_delay.optimization import evaluation as ev
from flight_delay.optimization import policies as pol


def _design(delay: list[float], replicates: int = 50) -> ev.DayDesign:
    dates = pd.to_datetime(["2026-03-01", "2026-03-01", "2026-03-02", "2026-03-02", "2026-03-03"][: len(delay)])
    month = np.array(["2026-03"] * len(delay))
    return ev.DayDesign(dates.to_numpy(), np.array(delay), month, replicates=replicates, seed=42)


def test_score_policies_by_hand_with_a_cancelled_flight() -> None:
    design = _design([10.0, 40.0, np.nan, -5.0, 25.0])  # third flight cancelled: planned, not costed
    buffers = {"none": np.zeros(5), "flat": np.full(5, 20.0)}
    scored = ev.score_policies(design, buffers, level=0.8, comparisons=(("flat", "none"),))
    flat = scored["policies"]["flat"]
    assert flat["buffer_planned_total_min"] == pytest.approx(100.0)  # 5 scheduled flights
    assert flat["buffer_completed_mean_min"] == pytest.approx(20.0)
    assert flat["residual_mean_min"] == pytest.approx((0 + 20 + 0 + 5) / 4)
    assert flat["unused_mean_min"] == pytest.approx((10 + 0 + 20 + 0) / 4)
    assert flat["arr_del15_rate"] == pytest.approx(0.25)  # only 40 - 20 = 20 >= 15
    none = scored["policies"]["none"]
    assert none["arr_del15_rate"] == pytest.approx(0.5)  # 40 and 25 are late, 10 and -5 are not
    assert none["cost_mean"] == pytest.approx(0.8 * (10 + 40 + 0 + 25) / 4)
    comparison = scored["comparisons"]["flat-none"]
    expected = flat["cost_mean"] - none["cost_mean"]
    assert comparison["d_cost"]["estimate"] == pytest.approx(expected)
    assert comparison["d_cost"]["replicates"] == 50


def test_budget_curve_never_exceeds_the_budget() -> None:
    rng = np.random.default_rng(7)
    n = 400
    dates = pd.to_datetime("2026-03-01") + pd.to_timedelta(rng.integers(0, 20, size=n), unit="D")
    origin = rng.choice(["A", "B", "C"], size=n)
    cells = pol.make_cells(origin, np.full(n, "X"), rng.choice([420, 780], size=n), dates)
    base = np.sort(rng.normal(5.0, 15.0, size=(cells.n_cells, 5)), axis=1)
    knots = {"plan": base, "b1": base + 3.0}
    delay = rng.normal(8.0, 20.0, size=n)
    design = ev.DayDesign(dates.to_numpy(), delay, np.array(["2026-03"] * n), replicates=30, seed=1)
    curve = ev.evaluate_budget_curve(design, cells, knots, budgets_per_flight=(1.0, 5.0, 10.0))
    for entry in curve.values():
        for name, row in entry["policies"].items():
            assert row["buffer_planned_total_min"] <= entry["budget_total_min"] + 1e-6, name
        assert entry["allocations"]["plan_arrdel15_budget"]["gap"] >= -1e-9
