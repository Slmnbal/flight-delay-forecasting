"""Mixture cell distribution: the average of the flights' CDFs, censoring flags, quantiles and candidates (by hand)."""

from __future__ import annotations

import numpy as np
import pytest

from flight_delay.optimization import allocation as al
from flight_delay.optimization import mixture as mx
from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization import policies as pol

FLIGHT_A = [0.0, 10.0, 20.0, 30.0, 40.0]
FLIGHT_B = [20.0, 30.0, 40.0, 50.0, 60.0]
TWO = np.array([FLIGHT_A, FLIGHT_B])
ONE_CELL = np.array([0, 0])


def test_two_flight_cell_by_hand_and_differs_from_vincentisation() -> None:
    # x = 35: F_A = 0.90 + 0.5 * 0.05 = 0.925, F_B = 0.50 + 0.5 * 0.30 = 0.65 -> mixture 0.7875
    result = mx.mixture_cdf(TWO, ONE_CELL, 1, [35.0])
    assert result.value[0] == pytest.approx(0.7875)
    assert result.censored_share[0] == 0.0
    vincent = pol.aggregate_knots(TWO, ONE_CELL, 1, "mean")  # (10, 20, 30, 40, 50)
    assert nv.cdf_at(vincent, [35.0])[0][0] == pytest.approx(0.85)  # narrower than the mixture


def test_censoring_is_flagged_not_invented() -> None:
    # x = 45 is above flight A's last knot: F_A is only >= 0.95 (boundary value used); F_B = 0.85
    above = mx.mixture_cdf(TWO, ONE_CELL, 1, [45.0])
    assert above.value[0] == pytest.approx(0.90)
    assert above.above_share[0] == 0.5 and above.below_share[0] == 0.0
    # x = 15 is below flight B's first knot: F_B <= 0.10; F_A = 0.65
    below = mx.mixture_cdf(TWO, ONE_CELL, 1, [15.0])
    assert below.value[0] == pytest.approx(0.375)
    assert below.below_share[0] == 0.5


def test_mixture_quantile_inverts_the_cdf() -> None:
    assert mx.mixture_quantile(TWO, ONE_CELL, 1, 0.7875)[0] == pytest.approx(35.0, abs=1e-6)
    assert mx.mixture_quantile(TWO, ONE_CELL, 1, 0.10)[0] == pytest.approx(0.0)
    assert mx.mixture_quantile(TWO, ONE_CELL, 1, 0.50)[0] == pytest.approx(22.0, abs=1e-6)  # (0.82 + 0.18) / 2
    assert mx.mixture_quantile(TWO, ONE_CELL, 1, 0.95)[0] == pytest.approx(60.0, abs=1e-6)  # F_B reaches 0.95
    with pytest.raises(nv.GridError):
        mx.mixture_quantile(TWO, ONE_CELL, 1, 0.97)


def test_single_flight_cells_equal_the_flight_distribution() -> None:
    rng = np.random.default_rng(2)
    knots = np.sort(rng.normal(10.0, 20.0, size=(6, 5)), axis=1)
    codes = np.arange(6)
    for level in (0.25, 0.5, 0.85):
        np.testing.assert_allclose(
            mx.mixture_quantile(knots, codes, 6, level), nv.interpolate_quantile(knots, level), atol=1e-6
        )


def test_candidates_by_hand() -> None:
    cand = mx.mixture_arrdel15_candidates(TWO, ONE_CELL, 1, candidate_levels=(0.50, 0.7875))
    np.testing.assert_allclose(cand.buffers[0], [0.0, 7.0, 20.0], atol=1e-6)  # Q(0.50) - 15, Q(0.7875) - 15
    assert cand.late[0, 0] == pytest.approx(0.625)  # 1 - 0.375 at x = 15
    assert cand.censored_share[0, 0] == 0.5
    assert cand.late[0, 2] == pytest.approx(1.0 - 0.7875, abs=1e-6)
    assert cand.describe()["cells_with_censored_flights_at_zero_buffer"] == 1


def test_candidates_feed_the_knapsack_within_budget() -> None:
    rng = np.random.default_rng(4)
    knots = np.sort(rng.normal(10.0, 25.0, size=(60, 5)), axis=1)
    codes = np.repeat(np.arange(6), 10)
    cand = mx.mixture_arrdel15_candidates(knots, codes, 6)
    assert cand.buffers.shape == (6, 1 + len(mx.DEFAULT_CANDIDATE_LEVELS))
    n = np.full(6, 10.0)
    solution = al.mckp_greedy(n[:, None] * cand.buffers, n[:, None] * cand.late, 200.0)
    assert solution.used <= 200.0 + 1e-9
    assert np.all(np.diff(cand.late[:, 1:], axis=1) <= 1e-12)  # higher level -> fewer late flights
