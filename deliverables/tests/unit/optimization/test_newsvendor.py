"""Newsvendor core: hand-computable examples (synthetic numbers, not data)."""

from __future__ import annotations

import numpy as np
import pytest

from flight_delay.optimization import newsvendor as nv

KNOTS = np.array([[0.0, 10.0, 20.0, 30.0, 40.0]])  # levels 0.10 / 0.50 / 0.80 / 0.90 / 0.95


def test_critical_ratio_and_implied_ratio() -> None:
    assert nv.critical_ratio(4.0, 1.0) == pytest.approx(0.8)
    assert nv.implied_cost_ratio(0.8) == pytest.approx(4.0)
    assert nv.cost_weights(0.8) == pytest.approx((0.8, 0.2))
    with pytest.raises(ValueError):
        nv.critical_ratio(0.0, 1.0)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (0.10, 0.0),
        (0.50, 10.0),
        (0.80, 20.0),
        (0.95, 40.0),
        (0.85, 25.0),  # midpoint of 0.80 and 0.90
        (0.60, 10.0 + (0.10 / 0.30) * 10.0),
        (0.30, 5.0),  # midpoint of 0.10 and 0.50
    ],
)
def test_interpolate_quantile_linear_in_level(level: float, expected: float) -> None:
    assert nv.interpolate_quantile(KNOTS, level)[0] == pytest.approx(expected)


@pytest.mark.parametrize("level", [0.05, 0.0999, 0.951, 0.99])
def test_levels_outside_the_grid_are_refused(level: float) -> None:
    with pytest.raises(nv.GridError):
        nv.interpolate_quantile(KNOTS, level)


def test_monotone_knots_and_crossing_rate() -> None:
    raw = np.array([[0.0, 10.0, 20.0, 30.0, 40.0], [0.0, 12.0, 11.0, 30.0, 40.0]])
    assert nv.crossing_rate(raw) == pytest.approx(0.5)
    np.testing.assert_allclose(nv.monotone_knots(raw)[1], [0.0, 11.0, 12.0, 30.0, 40.0])
    with pytest.raises(ValueError):
        nv.monotone_knots(np.array([[0.0, np.nan, 1.0, 2.0, 3.0]]))


def test_cdf_inside_and_censored_outside_the_knots() -> None:
    knots = np.repeat(KNOTS, 4, axis=0)
    value, below, above = nv.cdf_at(knots, np.array([15.0, 20.0, -5.0, 45.0]))
    np.testing.assert_allclose(value, [0.65, 0.80, 0.10, 0.95])
    np.testing.assert_array_equal(below, [False, False, True, False])
    np.testing.assert_array_equal(above, [False, False, False, True])


def test_cdf_with_tied_knots_jumps() -> None:
    knots = np.array([[0.0, 10.0, 10.0, 30.0, 40.0]])  # Q flat between 0.50 and 0.80 -> F jumps at 10
    value, _, _ = nv.cdf_at(knots, 10.0)
    assert value[0] == pytest.approx(0.80)
    value, _, _ = nv.cdf_at(knots, 20.0)
    assert value[0] == pytest.approx(0.85)


def test_newsvendor_buffer_is_clipped_at_zero() -> None:
    knots = np.array([[-30.0, -10.0, -2.0, 5.0, 12.0]])
    assert nv.newsvendor_buffer(knots, 0.80)[0] == 0.0
    assert nv.newsvendor_buffer(knots, 0.95)[0] == pytest.approx(12.0)


def test_newsvendor_optimum_matches_brute_force_on_a_uniform_delay() -> None:
    """D ~ U[0, 100]: the knots are exact (Q(a) = 100 a); argmin of the realised cost is Q(tau)."""
    delays = np.linspace(0.0, 100.0, 20001)
    knots = np.array([[100.0 * a for a in nv.KNOT_LEVELS]])
    for level in (0.6, 0.8, 0.9):
        grid = np.linspace(0.0, 100.0, 1001)
        costs = []
        for b in grid:
            outcome = nv.realized_outcomes(delays, np.full(delays.size, b))
            costs.append(nv.realized_cost(outcome["residual"], outcome["unused"], level).mean())
        best = grid[int(np.argmin(costs))]
        assert best == pytest.approx(nv.newsvendor_buffer(knots, level)[0], abs=0.2)


def test_realized_outcomes_by_hand() -> None:
    out = nv.realized_outcomes(np.array([-5.0, 10.0, 30.0, 40.0]), np.full(4, 20.0))
    np.testing.assert_allclose(out["residual"], [0.0, 0.0, 10.0, 20.0])
    np.testing.assert_allclose(out["unused"], [20.0, 10.0, 0.0, 0.0])
    np.testing.assert_allclose(out["late15"], [0.0, 0.0, 0.0, 1.0])
    np.testing.assert_allclose(out["absorbed"], [1.0, 1.0, 0.0, 0.0])
    cost = nv.realized_cost(out["residual"], out["unused"], 0.8)
    np.testing.assert_allclose(cost, [4.0, 2.0, 8.0, 16.0])


def test_realized_outcomes_refuse_missing_delays_and_negative_buffers() -> None:
    with pytest.raises(ValueError):
        nv.realized_outcomes(np.array([np.nan]), np.array([0.0]))
    with pytest.raises(ValueError):
        nv.realized_outcomes(np.array([1.0]), np.array([-1.0]))
