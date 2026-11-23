"""Split-conformal offsets (plan 5.4: ``test_conformal_tek_yonlu_kapsama``) on SYNTHETIC exchangeable data."""

from __future__ import annotations

import math

import numpy as np
import pytest

from flight_delay.modeling import conformal as cf


def test_rank_and_known_values():
    assert cf.conformal_rank(99, 0.8) == 80  # (99 + 1) * 0.8 = 80 exactly, despite floating point
    assert cf.conformal_rank(10, 0.8) == 9  # ceil(8.8)
    assert cf.conformal_rank(4, 0.95) == 5  # > n: not enough calibration rows for this level
    assert cf.conformal_quantile([3.0, 1.0, 2.0, 5.0, 4.0], 0.5) == 3.0  # k = ceil(3) = 3rd smallest
    assert math.isinf(cf.conformal_quantile([1.0, 2.0, 3.0, 4.0], 0.95))
    # one-sided: scores y - q = [1, -1, 2, 0]; k = ceil(5 * 0.5) = 3 -> third smallest = 1
    assert cf.one_sided_offset([2.0, 0.0, 5.0, 3.0], [1.0, 1.0, 3.0, 3.0], 0.5) == 1.0
    # CQR: scores max(lo - y, y - hi) = [-1, 2, -2, 0]; k = ceil(5 * 0.6) = 3 -> third smallest = 0
    assert cf.cqr_offset([1.0, 5.0, 2.0, 3.0], [0.0, 0.0, 0.0, 0.0], [2.0, 3.0, 4.0, 3.0], 0.6) == 0.0
    with pytest.raises(ValueError):
        cf.conformal_quantile([1.0, np.nan], 0.5)
    with pytest.raises(ValueError):
        cf.conformal_rank(0, 0.5)


def _trial(rng: np.random.Generator, n_cal: int, n_test: int) -> tuple[np.ndarray, ...]:
    """A deliberately miscalibrated quantile model on heteroscedastic data (exchangeable rows)."""
    x = rng.uniform(0, 1, n_cal + n_test)
    y = 10 * x + rng.normal(0, 1 + 3 * x)
    q80 = 10 * x  # the median, used as if it were P80: under-covers
    lo, hi = 10 * x - 0.5, 10 * x + 0.5  # far too narrow an 80 % interval
    return x, y, q80, lo, hi


def test_one_sided_offset_reaches_the_level_on_new_rows():
    rng = np.random.default_rng(0)
    n_cal, n_test, alpha = 200, 2000, 0.8
    coverages = []
    for _ in range(300):
        _, y, q80, _, _ = _trial(rng, n_cal, n_test)
        offset = cf.one_sided_offset(y[:n_cal], q80[:n_cal], alpha)
        coverages.append(np.mean(y[n_cal:] <= q80[n_cal:] + offset))
    mean = float(np.mean(coverages))
    # theory: alpha <= E[coverage] < alpha + 1 / (n + 1); +-0.005 for the Monte Carlo error of 300 trials
    assert alpha - 0.005 <= mean <= alpha + 1 / (n_cal + 1) + 0.005
    raw = np.mean(y <= q80)
    assert raw < 0.6  # the raw "P80" was badly under-covering: the adjustment did real work


def test_cqr_reaches_the_level_and_can_shrink_a_too_wide_interval():
    rng = np.random.default_rng(1)
    n_cal, n_test, level = 200, 2000, 0.8
    coverages = []
    for _ in range(300):
        _, y, _, lo, hi = _trial(rng, n_cal, n_test)
        offset = cf.cqr_offset(y[:n_cal], lo[:n_cal], hi[:n_cal], level)
        inside = (y[n_cal:] >= lo[n_cal:] - offset) & (y[n_cal:] <= hi[n_cal:] + offset)
        coverages.append(np.mean(inside))
    mean = float(np.mean(coverages))
    assert level - 0.005 <= mean <= level + 1 / (n_cal + 1) + 0.005
    _, y, _, lo, hi = _trial(np.random.default_rng(2), n_cal, n_test)
    wide = cf.cqr_offset(y, lo - 100, hi + 100, level)
    assert wide < 0  # the raw interval was too wide: CQR narrows it


def test_adjusted_crossing_rate():
    assert cf.adjusted_crossing_rate([1.0, 5.0, 2.0], [2.0, 4.0, 2.0]) == pytest.approx(1 / 3)
    assert cf.adjusted_crossing_rate([], []) == 0.0
    with pytest.raises(ValueError):
        cf.adjusted_crossing_rate([1.0], [1.0, 2.0])
