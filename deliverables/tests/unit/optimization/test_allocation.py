"""Budget versions: closed-form KKT solution, knapsack greedy vs exact MILP, constraint checks (synthetic numbers)."""

from __future__ import annotations

import numpy as np
import pytest

from flight_delay.optimization import allocation as al
from flight_delay.optimization import newsvendor as nv

UNIFORM_100 = [100.0 * a for a in nv.KNOT_LEVELS]  # D ~ U[0, 100]: interpolation is exact
UNIFORM_50 = [50.0 * a for a in nv.KNOT_LEVELS]  # D ~ U[0, 50]


def _expected_residual_uniform(b: np.ndarray, top: float) -> np.ndarray:
    """E[(D - b)+] for D ~ U[0, top], 0 <= b <= top."""
    return (top - b) ** 2 / (2.0 * top)


def test_common_level_allocation_at_the_budget_limit() -> None:
    knots = np.array([UNIFORM_100, UNIFORM_50])
    solution = al.common_level_allocation(knots, [1.0, 1.0], 120.0)  # tau = 0.80 needs 80 + 40
    assert solution.status == "binding"
    assert solution.level == pytest.approx(0.80, abs=1e-6)
    np.testing.assert_allclose(solution.buffers, [80.0, 40.0], atol=1e-4)
    assert solution.used <= 120.0 + 1e-9


def test_common_level_allocation_matches_brute_force() -> None:
    """min (100 - a)^2 / 200 + (50 - b)^2 / 100 s.t. a + b = 120: the KKT solution (common level) is the optimum."""
    a = np.linspace(70.0, 100.0, 30001)
    b = 120.0 - a
    objective = _expected_residual_uniform(a, 100.0) + _expected_residual_uniform(b, 50.0)
    best = a[int(np.argmin(objective))]
    solution = al.common_level_allocation(np.array([UNIFORM_100, UNIFORM_50]), [1.0, 1.0], 120.0)
    assert solution.buffers[0] == pytest.approx(best, abs=0.01)


def test_flight_weights_enter_the_budget() -> None:
    knots = np.array([UNIFORM_100, UNIFORM_50])
    solution = al.common_level_allocation(knots, [3.0, 1.0], 3 * 80.0 + 40.0)
    assert solution.level == pytest.approx(0.80, abs=1e-6)
    assert solution.used == pytest.approx(280.0, abs=1e-3)


def test_budget_above_the_grid_is_not_extrapolated() -> None:
    solution = al.common_level_allocation(np.array([UNIFORM_100, UNIFORM_50]), [1.0, 1.0], 1e6)
    assert solution.status == "grid_top"
    assert solution.level == nv.MAX_LEVEL
    assert solution.used == pytest.approx(95.0 + 47.5)


def test_budget_below_the_grid_and_zero_budget() -> None:
    knots = np.array([[10.0, 20.0, 30.0, 40.0, 50.0]])  # tau = 0.10 already needs 10 minutes
    below = al.common_level_allocation(knots, [1.0], 5.0)
    assert below.status == "below_grid"
    assert below.level is None
    assert np.all(np.isnan(below.buffers))
    zero = al.common_level_allocation(knots, [1.0], 0.0)
    assert zero.status == "zero"
    np.testing.assert_array_equal(zero.buffers, [0.0])


def test_common_level_never_violates_the_budget() -> None:
    rng = np.random.default_rng(0)
    knots = np.sort(rng.normal(10.0, 20.0, size=(200, 5)), axis=1)
    n = rng.integers(1, 100, size=200).astype(float)
    for budget in (500.0, 5_000.0, 20_000.0, 60_000.0):
        solution = al.common_level_allocation(knots, n, budget)
        if solution.status in ("binding", "grid_top"):
            assert float(np.sum(n * solution.buffers)) <= budget + 1e-6
            assert np.all(solution.buffers >= 0)


def test_lower_hull_drops_points_above_the_chord() -> None:
    assert al.lower_hull([0.0, 1.0, 2.0], [10.0, 9.0, 4.0]) == [0, 2]
    assert al.lower_hull([0.0, 1.0, 2.0], [10.0, 5.0, 4.0]) == [0, 1, 2]
    assert al.lower_hull([0.0, 0.0, 3.0], [5.0, 4.0, 4.5]) == [1]  # same cost: lowest value; no improvement later


COSTS = np.array([[0.0, 10.0, 20.0], [0.0, 5.0, 30.0]])
VALUES = np.array([[1.0, 0.5, 0.4], [1.0, 0.6, 0.1]])


@pytest.mark.parametrize(
    ("budget", "value", "lp_value"),
    [
        (15.0, 1.1, 1.1),  # (10, 5) exactly
        (20.0, 1.1, 1.0),  # the 25-minute step of row 1 fits 5 / 25
        (35.0, 1.0, 0.7),  # (20, 5): later increment of row 0 still taken after the fractional one
        (100.0, 0.5, 0.5),  # everything
    ],
)
def test_mckp_greedy_by_hand(budget: float, value: float, lp_value: float) -> None:
    solution = al.mckp_greedy(COSTS, VALUES, budget)
    assert solution.value == pytest.approx(value)
    assert solution.lp_value == pytest.approx(lp_value)
    assert solution.used <= budget + 1e-9
    assert solution.value >= solution.lp_value - 1e-12


def test_mckp_greedy_equals_exact_milp_on_small_instances() -> None:
    pytest.importorskip("scipy")
    rng = np.random.default_rng(1)
    for _ in range(20):
        costs = np.column_stack([np.zeros(6), np.sort(rng.uniform(1, 30, size=(6, 3)), axis=1)])
        values = np.column_stack([np.ones(6), -np.sort(-rng.uniform(0.05, 0.95, size=(6, 3)), axis=1)])
        budget = float(rng.uniform(10, 80))
        greedy = al.mckp_greedy(costs, values, budget)
        exact = al.mckp_milp(costs, values, budget)
        assert exact is not None
        assert greedy.used <= budget + 1e-9
        assert exact.value <= greedy.value + 1e-9  # MILP is optimal
        assert greedy.lp_value <= exact.value + 1e-9  # LP relaxation is a lower bound


def test_arrdel15_candidates_by_hand() -> None:
    buffers, late, censored = al.arrdel15_candidates(np.array([[0.0, 10.0, 20.0, 30.0, 40.0]]))
    np.testing.assert_allclose(buffers[0], [0.0, 0.0, 0.0, 5.0, 15.0, 25.0])
    np.testing.assert_allclose(late[0], [0.35, 0.35, 0.35, 0.20, 0.10, 0.05])
    assert not censored[0]


def test_arrdel15_allocation_respects_the_budget() -> None:
    knots = np.array([[0.0, 10.0, 20.0, 30.0, 40.0], [-10.0, 5.0, 14.0, 16.0, 60.0]])
    solution, buffers, _ = al.arrdel15_allocation(knots, [10.0, 10.0], 60.0)
    assert float(np.sum(np.array([10.0, 10.0]) * buffers)) <= 60.0 + 1e-9
    # cell 2 reaches 0.90 on time with 1 minute (16 - 15), the cheapest improvement
    assert buffers[1] == pytest.approx(1.0)
    assert solution.value >= solution.lp_value - 1e-12
