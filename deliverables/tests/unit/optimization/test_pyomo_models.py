"""Pyomo + HiGHS models: LP = closed form (both formulations), MILP = by hand / scipy MILP / greedy bounds."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("pyomo")
pytest.importorskip("highspy")

from flight_delay.optimization import allocation as al  # noqa: E402
from flight_delay.optimization import newsvendor as nv  # noqa: E402
from flight_delay.optimization import pyomo_models as pm  # noqa: E402

UNIFORM_100 = [100.0 * a for a in nv.KNOT_LEVELS]
UNIFORM_50 = [50.0 * a for a in nv.KNOT_LEVELS]


@pytest.mark.parametrize("formulation", pm.FORMULATIONS)
def test_lp_equals_closed_form_by_hand(formulation: str) -> None:
    knots = np.array([UNIFORM_100, UNIFORM_50])
    lp_model = pm.MinutesLP(knots, [1.0, 1.0], formulation=formulation, max_segment_min=0.5)
    lp = lp_model.solve(120.0, time_limit=30.0)
    closed = al.common_level_allocation(knots, [1.0, 1.0], 120.0)
    assert lp.status == "binding"
    assert lp.buffers is not None
    np.testing.assert_allclose(lp.buffers, [80.0, 40.0], atol=1.0)
    assert lp.used is not None and lp.used <= 120.0 + 1e-6
    check = pm.compare_minutes(lp, closed, knots, [1.0, 1.0], lp_model.segments)
    assert check["agrees"], check
    if lp.implied_level is not None:  # dual of the budget row: -(1 - tau)
        assert lp.implied_level == pytest.approx(0.80, abs=0.02)


def test_lp_equals_closed_form_on_random_cells_and_formulations_agree() -> None:
    rng = np.random.default_rng(7)
    knots = np.sort(rng.normal(8.0, 25.0, size=(40, 5)), axis=1)
    n = rng.integers(1, 60, size=40).astype(float)
    segments = pm.MinutesLP(knots, n, formulation="segments", max_segment_min=1.0)
    epigraph = pm.MinutesLP(knots, n, formulation="epigraph", max_segment_min=1.0)
    top = al.cell_budget(knots, n, 0.95)
    for share in (0.2, 0.5, 0.8):
        budget = share * top
        closed = al.common_level_allocation(knots, n, budget)
        first = segments.solve(budget, time_limit=30.0)
        second = epigraph.solve(budget, time_limit=30.0)
        if closed.status != "binding":
            assert first.status == second.status == closed.status
            continue
        for lp, model in ((first, segments), (second, epigraph)):
            check = pm.compare_minutes(lp, closed, knots, n, model.segments, buffer_factor=4.0)
            assert check["certificate_lower_ok"] and check["certificate_upper_ok"], check
            assert sum(check["violations"].values()) == 0, check
            assert check["agrees"], check
        assert first.objective_lp is not None and second.objective_lp is not None
        assert first.objective_lp == pytest.approx(second.objective_lp, rel=1e-6)


def test_lp_statuses_match_the_closed_form() -> None:
    knots = np.array([[10.0, 20.0, 30.0, 40.0, 50.0]])
    lp_model = pm.MinutesLP(knots, [1.0], max_segment_min=1.0)
    assert lp_model.solve(5.0).status == "below_grid"  # tau = 0.10 already needs 10 minutes
    assert al.common_level_allocation(knots, [1.0], 5.0).status == "below_grid"
    top = lp_model.solve(1e6)
    assert top.status == "grid_top" and top.buffers is not None
    np.testing.assert_allclose(top.buffers, [50.0])
    assert lp_model.solve(0.0).status == "zero"


COSTS = np.array([[0.0, 10.0, 20.0], [0.0, 5.0, 30.0]])
VALUES = np.array([[1.0, 0.5, 0.4], [1.0, 0.6, 0.1]])


@pytest.mark.parametrize(("budget", "value"), [(15.0, 1.1), (20.0, 1.1), (35.0, 1.0), (100.0, 0.5)])
def test_milp_by_hand(budget: float, value: float) -> None:
    solution = pm.solve_arrdel15_milp(COSTS, VALUES, [1.0, 1.0], budget, time_limit=30.0)
    assert solution.valid
    assert solution.value == pytest.approx(value)
    assert solution.used is not None and solution.used <= budget + 1e-9
    assert solution.report is not None and solution.report.has_solution


def test_milp_equals_scipy_milp_and_is_bounded_by_greedy() -> None:
    pytest.importorskip("scipy")
    rng = np.random.default_rng(1)
    solver = pm.make_solver()
    for _ in range(15):
        costs = np.column_stack([np.zeros(6), np.sort(rng.uniform(1, 30, size=(6, 3)), axis=1)])
        values = np.column_stack([np.ones(6), -np.sort(-rng.uniform(0.05, 0.95, size=(6, 3)), axis=1)])
        budget = float(rng.uniform(10, 80))
        pyomo_solution = pm.solve_arrdel15_milp(costs, values, np.ones(6), budget, solver=solver)
        exact = al.mckp_milp(costs, values, budget)
        greedy = al.mckp_greedy(costs, values, budget)
        assert exact is not None and pyomo_solution.valid and pyomo_solution.value is not None
        assert pyomo_solution.value == pytest.approx(exact.value, abs=1e-9)
        assert greedy.lp_value - 1e-9 <= pyomo_solution.value <= greedy.value + 1e-9


def test_milp_flight_weights_and_restriction() -> None:
    buffers = np.array([[0.0, 2.0, 6.0], [0.0, 1.0, 4.0], [0.0, 3.0, 3.0]])
    late = np.array([[0.4, 0.2, 0.1], [0.5, 0.3, 0.05], [0.3, 0.1, 0.2]])  # row 2: option 2 dominated
    n = np.array([10.0, 5.0, 1.0])
    full = pm.solve_arrdel15_milp(buffers, late, n, 40.0)
    assert full.valid and full.used is not None and full.used <= 40.0 + 1e-9
    assert full.restriction["candidates_after_dominance"] == 8
    fixed = np.array([1, 0, 0])
    restricted = pm.solve_arrdel15_milp(buffers, late, n, 40.0, active=[True, True, False], fixed_choice=fixed)
    assert restricted.valid and restricted.choice is not None
    assert restricted.choice[2] == 0  # inactive cell kept at the given choice
    assert restricted.restriction["cells_fixed_inactive"] == 1
    assert restricted.value is not None and full.value is not None and restricted.value >= full.value - 1e-9
    with pytest.raises(ValueError, match="fixed_choice"):
        pm.solve_arrdel15_milp(buffers, late, n, 40.0, active=[True, True, False])
