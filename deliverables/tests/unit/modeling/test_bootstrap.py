"""Day-block bootstrap and Holm (plan 5.2): weighted statistics equal the materialised resample (SYNTHETIC data)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from flight_delay.modeling import bootstrap as bs
from flight_delay.modeling import metrics as mt


def _data(n: int = 600, days: int = 25, seed: int = 0):
    rng = np.random.default_rng(seed)
    day = rng.integers(0, days, size=n)
    score = np.round(rng.random(n), 2)  # rounded: many ties
    y = (rng.random(n) < 0.2 + 0.6 * score).astype("float64")
    return y, score, day


def _resample(multiplicity: np.ndarray, day: np.ndarray) -> np.ndarray:
    """Row indices of the materialised resample: every row of day d repeated multiplicity[d] times."""
    parts = [np.tile(np.flatnonzero(day == d), int(k)) for d, k in enumerate(multiplicity) if k > 0]
    return np.concatenate(parts)


def test_day_multiplicities_are_reproducible_and_sum_to_the_number_of_days():
    a = bs.day_multiplicities(30, replicates=50, seed=42)
    b = bs.day_multiplicities(30, replicates=50, seed=42)
    c = bs.day_multiplicities(30, replicates=50, seed=43)
    assert a.shape == (50, 30) and np.array_equal(a, b) and not np.array_equal(a, c)
    assert np.all(a.sum(axis=1) == 30) and a.min() >= 0
    assert bs.DEFAULT_REPLICATES == 1000 and bs.DEFAULT_SEED == 42 and bs.HOLM_ALPHA == 0.05
    with pytest.raises(ValueError):
        bs.day_multiplicities(0)


def test_day_index_codes_and_missing_dates():
    codes, days = bs.day_index(pd.to_datetime(["2026-03-02", "2026-03-01", "2026-03-02 17:00"], format="ISO8601"))
    assert codes.tolist() == [1, 0, 1] and [str(d) for d in days] == ["2026-03-01", "2026-03-02"]
    with pytest.raises(ValueError):
        bs.day_index(pd.to_datetime(["2026-03-01", None]))


def test_weighted_auc_and_average_precision_equal_the_materialised_resample():
    y, score, day = _data()
    ranked = bs.RankedScores(y, score, day)
    assert ranked.roc_auc() == pytest.approx(mt.roc_auc(y, score), abs=1e-12)
    assert ranked.average_precision() == pytest.approx(mt.average_precision(y, score), abs=1e-12)
    for m in bs.day_multiplicities(25, replicates=8, seed=1):
        rows = _resample(m, day)
        auc, ap = ranked.both(m)
        assert auc == pytest.approx(mt.roc_auc(y[rows], score[rows]), abs=1e-12)
        assert ap == pytest.approx(mt.average_precision(y[rows], score[rows]), abs=1e-12)


def test_ranked_scores_with_one_class_give_nan():
    ranked = bs.RankedScores(np.zeros(5), np.linspace(0, 1, 5), np.arange(5))
    assert math.isnan(ranked.roc_auc()) and math.isnan(ranked.average_precision())


def test_day_means_equal_the_materialised_resample():
    y, score, day = _data()
    values = (score - y) ** 2
    means = bs.DayMeans(values, day, 25)
    assert means() == pytest.approx(values.mean())
    multiplicities = bs.day_multiplicities(25, replicates=6, seed=3)
    all_at_once = means.replicates(multiplicities)
    for b, m in enumerate(multiplicities):
        rows = _resample(m, day)
        assert means(m) == pytest.approx(values[rows].mean(), abs=1e-12)
        assert all_at_once[b] == pytest.approx(means(m), abs=1e-12)
    with pytest.raises(ValueError):
        bs.DayMeans([np.nan], [0], 1)


def test_weighted_slope_matches_the_unweighted_fit_and_repeated_rows():
    y, score, day = _data(seed=5)
    p = np.clip(score, 0.02, 0.98)
    unweighted = mt.calibration_slope_intercept(y, p)
    weighted = bs.weighted_calibration_slope_intercept(y, p)
    assert weighted[0] == pytest.approx(unweighted[0], abs=1e-8)
    assert weighted[1] == pytest.approx(unweighted[1], abs=1e-8)
    m = bs.day_multiplicities(25, replicates=1, seed=9)[0]
    rows = _resample(m, day)
    repeated = mt.calibration_slope_intercept(y[rows], p[rows])
    assert bs.SlopeStatistic(y, p, day)(m) == pytest.approx(repeated[1], abs=1e-7)
    assert all(math.isnan(v) for v in bs.weighted_calibration_slope_intercept([0, 0, 1], [0.5, 0.5, 0.5]))


def test_summarize_draws_percentile_interval_and_two_sided_p():
    positive = bs.summarize_draws(0.5, np.arange(1, 1001) / 1000.0)
    assert positive.p_value == 0.0 and positive.share_at_or_below_zero == 0.0
    low, high = np.percentile(np.arange(1, 1001) / 1000.0, [2.5, 97.5])
    assert positive.ci_low == pytest.approx(low) and positive.ci_high == pytest.approx(high)
    mixed = bs.summarize_draws(0.1, np.r_[-np.ones(100), np.ones(900)])
    assert mixed.p_value == pytest.approx(0.2)  # 2 * min(0.1, 0.9)
    symmetric = bs.summarize_draws(0.0, np.r_[-np.ones(500), np.ones(500)])
    assert symmetric.p_value == 1.0
    with_nan = bs.summarize_draws(1.0, [np.nan, 1.0, 2.0])
    assert with_nan.replicates == 3 and with_nan.finite_replicates == 2
    empty = bs.summarize_draws(1.0, [np.nan])
    assert math.isnan(empty.p_value) and empty.finite_replicates == 0


def test_generic_bootstrap_uses_the_full_set_for_the_estimate():
    y, score, day = _data()
    ranked = bs.RankedScores(y, score, day)
    multiplicities = bs.day_multiplicities(25, replicates=40, seed=42)
    result = bs.bootstrap(ranked.roc_auc, multiplicities)
    assert result.estimate == pytest.approx(mt.roc_auc(y, score))
    assert result.replicates == 40 and result.ci_low <= result.ci_high


def test_holm_known_values_and_missing_p():
    adjusted = bs.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.005})
    assert list(adjusted) == ["a", "b", "c", "d"]  # input order kept
    assert adjusted["d"]["p_holm"] == pytest.approx(0.02) and adjusted["d"]["rank"] == 1
    assert adjusted["a"]["p_holm"] == pytest.approx(0.03)
    assert adjusted["c"]["p_holm"] == pytest.approx(0.06) and adjusted["b"]["p_holm"] == pytest.approx(0.06)
    assert [adjusted[k]["reject"] for k in "abcd"] == [True, False, False, True]
    missing = bs.holm({"a": 0.01, "b": None})
    assert missing["b"]["p_missing"] and missing["b"]["p_holm"] == 1.0 and not missing["b"]["reject"]
    assert missing["a"]["p_holm"] == pytest.approx(0.02) and missing["a"]["reject"]
