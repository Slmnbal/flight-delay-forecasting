"""Piecewise-linear solver inputs: exact in-grid shortfall, LP pieces, dominance (synthetic numbers, by hand)."""

from __future__ import annotations

import numpy as np
import pytest

from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization import piecewise as pw

UNIFORM_100 = [100.0 * a for a in nv.KNOT_LEVELS]  # D ~ U[0, 100]: (10, 50, 80, 90, 95), interpolation exact


def test_grid_shortfall_uniform_by_hand() -> None:
    """S(b) = E[(D - b)+] - E[(D - 95)+] = (100 - b)^2 / 200 - 25 / 200 for D ~ U[0, 100]."""
    b = np.array([10.0, 50.0, 80.0, 95.0, 120.0])
    knots = np.tile(UNIFORM_100, (b.size, 1))
    expected = np.maximum((100.0 - np.minimum(b, 95.0)) ** 2 / 200.0 - 0.125, 0.0)
    np.testing.assert_allclose(pw.grid_shortfall(knots, b), expected, atol=1e-12)
    assert pw.grid_shortfall(knots[:1], [80.0])[0] == pytest.approx(1.875)


def test_grid_shortfall_refuses_below_the_first_knot() -> None:
    with pytest.raises(nv.GridError):
        pw.grid_shortfall([UNIFORM_100], [5.0])


def test_grid_shortfall_matches_numeric_integral() -> None:
    rng = np.random.default_rng(3)
    knots = np.sort(rng.normal(10.0, 25.0, size=(40, 5)), axis=1)
    b = knots[:, 0] + rng.uniform(0, 1, 40) * (knots[:, -1] - knots[:, 0])
    exact = pw.grid_shortfall(knots, b)
    for i in range(0, 40, 7):
        x = np.linspace(b[i], knots[i, -1], 20001)
        f, _, _ = nv.cdf_at(np.tile(knots[i], (x.size, 1)), x)
        y = 1.0 - f
        integral = float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(x)))
        assert exact[i] == pytest.approx(integral, abs=1e-4)


def test_lp_segments_cover_the_domain_with_convex_exact_chords() -> None:
    rng = np.random.default_rng(5)
    knots = np.sort(rng.normal(5.0, 30.0, size=(25, 5)), axis=1)
    knots[0] = [-40.0, -30.0, -20.0, -10.0, -5.0]  # q95 < 0: L = U = 0, no piece
    seg = pw.lp_segments(knots, max_segment_min=1.5)
    assert seg.count[0] == 0 and seg.lower[0] == seg.upper[0] == 0.0
    assert np.all(seg.length <= 1.5 + 1e-12) and np.all(seg.length > 0)
    np.testing.assert_allclose(np.bincount(seg.cell, weights=seg.length, minlength=25), seg.upper - seg.lower)
    for c in range(25):
        mine = seg.cell == c
        if mine.sum() < 2:
            continue
        assert np.all(np.diff(seg.slope[mine]) >= -1e-12)  # convex: slopes increase
        ends = seg.value_start[mine] + seg.slope[mine] * seg.length[mine]
        np.testing.assert_allclose(ends[:-1], seg.value_start[mine][1:], atol=1e-9)  # chords exact at piece ends
    mid = seg.start + 0.5 * seg.length
    chord = seg.value_start + seg.slope * 0.5 * seg.length
    gap = chord - pw.grid_shortfall(knots[seg.cell], mid)
    assert np.all(gap >= -1e-9)
    np.testing.assert_allclose(gap, seg.chord_error, atol=1e-9)  # maximum chord error at the midpoint


def test_lp_segments_base_and_bounds() -> None:
    seg = pw.lp_segments([UNIFORM_100], max_segment_min=10.0)
    assert seg.lower[0] == 10.0 and seg.upper[0] == 95.0
    assert seg.base[0] == pytest.approx(90.0**2 / 200.0 - 0.125)
    assert seg.slope[0] == pytest.approx(-(1.0 - 0.15))  # piece [10, 20]: F(15) = 0.15


def test_undominated_options_by_hand() -> None:
    costs = np.array([[0.0, 0.0, 5.0, 10.0, 10.0]])
    values = np.array([[1.0, 0.9, 0.9, 0.5, 0.4]])
    np.testing.assert_array_equal(pw.undominated_options(costs, values), [[False, True, False, False, True]])
