"""Known-value tests for the plan section 5.1 metrics (hand-computed or scikit-learn documentation examples)."""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from flight_delay.modeling import metrics as mt

Y = [0, 0, 1, 1]
P = [0.1, 0.4, 0.35, 0.8]  # scikit-learn docs example: roc_auc 0.75, average precision 0.8333...


def test_roc_auc_known_value_and_ties():
    assert mt.roc_auc(Y, P) == pytest.approx(0.75)
    assert mt.roc_auc([0, 1], [0.5, 0.5]) == pytest.approx(0.5)
    assert mt.roc_auc([0, 0, 1], [0.1, 0.2, 0.9]) == pytest.approx(1.0)
    assert math.isnan(mt.roc_auc([1, 1], [0.2, 0.3]))


def test_average_precision_known_value():
    assert mt.average_precision(Y, P) == pytest.approx(0.5 + 0.5 * 2 / 3)
    assert mt.average_precision([0, 1], [0.5, 0.5]) == pytest.approx(0.5)  # one threshold: precision 0.5
    assert math.isnan(mt.average_precision([0, 0], [0.1, 0.2]))


def test_brier_log_loss_and_skill():
    assert mt.brier_score([0, 1], [0.2, 0.6]) == pytest.approx(0.1)
    assert mt.log_loss([1, 0], [0.5, 0.5]) == pytest.approx(math.log(2))
    assert mt.brier_skill_score([0, 1], [0.2, 0.6], [0.5, 0.5]) == pytest.approx(1 - 0.1 / 0.25)


def test_calibration_in_the_large_sign():
    assert mt.calibration_in_the_large([0, 1, 0, 0], [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.25)


def test_reliability_table_and_ece():
    y, p = [0, 1, 0, 1], [0.1, 0.3, 0.6, 0.8]
    table = mt.reliability_table(y, p, n_bins=2)
    assert table["n"].tolist() == [2, 2]
    assert table["mean_pred"].tolist() == pytest.approx([0.2, 0.7])
    assert table["observed_rate"].tolist() == pytest.approx([0.5, 0.5])
    assert mt.expected_calibration_error(y, p, n_bins=2) == pytest.approx(0.25)


def test_calibration_slope_intercept_is_identity_when_calibrated():
    # p = 0.2 with 1 of 5 positive and p = 0.5 with 1 of 2 positive: the saturated fit gives a = 0, b = 1 exactly
    y = [1, 0, 0, 0, 0, 1, 0]
    p = [0.2] * 5 + [0.5] * 2
    intercept, slope = mt.calibration_slope_intercept(y, p)
    assert intercept == pytest.approx(0.0, abs=1e-8)
    assert slope == pytest.approx(1.0, abs=1e-8)


def test_calibration_fit_is_warning_free_and_solves_the_score_equations_for_inverted_extreme_predictions():
    # smoke-run case: strongly mis-ranked, extreme probabilities (negative slope); overlapping, so the MLE exists
    rng = np.random.default_rng(0)
    y = (rng.random(20_000) < 0.04).astype("float64")
    logit = np.where(y == 1, rng.normal(-6.0, 3.0, y.size), rng.normal(2.0, 3.0, y.size))
    p = 1.0 / (1.0 + np.exp(-logit))
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any RuntimeWarning (overflow in exp) fails the test
        intercept, slope = mt.calibration_slope_intercept(y, p)
        assert np.all(mt._sigmoid(np.array([-1000.0, 0.0, 1000.0])) == np.array([0.0, 0.5, 1.0]))
    assert math.isfinite(slope) and slope < 0
    x = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    mu = 1.0 / (1.0 + np.exp(-(intercept + slope * x)))
    assert abs(np.sum(y - mu)) < 1e-6 and abs(np.sum(x * (y - mu))) < 1e-5  # gradient of the log-likelihood = 0


def test_calibration_slope_is_nan_for_constant_predictions():
    intercept, slope = mt.calibration_slope_intercept([0, 1, 0], [0.3, 0.3, 0.3])
    assert math.isnan(intercept) and math.isnan(slope)


def test_precision_recall_f1_and_best_threshold():
    scores = mt.precision_recall_f1([1, 1, 0, 0], [0.9, 0.6, 0.7, 0.1], threshold=0.65)
    assert scores["precision"] == pytest.approx(0.5)
    assert scores["recall"] == pytest.approx(0.5)
    assert scores["f1"] == pytest.approx(0.5)
    threshold, f1 = mt.best_f1_threshold([1, 1, 0, 0], [0.9, 0.6, 0.7, 0.1])
    assert threshold == pytest.approx(0.6)  # predicts 3 positives: P = 2/3, R = 1 -> F1 = 0.8
    assert f1 == pytest.approx(0.8)


def test_classification_metrics_bundle():
    result = mt.classification_metrics(Y, P, y_prob_reference=[0.5] * 4, threshold=0.5)
    assert result["n"] == 4 and result["prevalence"] == 0.5
    assert result["roc_auc"] == pytest.approx(0.75)
    assert "brier_skill_score" in result and "f1_at_threshold" in result


def test_input_validation():
    with pytest.raises(ValueError):
        mt.roc_auc([0, 1], [0.2])
    with pytest.raises(ValueError):
        mt.brier_score([0, 2], [0.1, 0.2])
    with pytest.raises(ValueError):
        mt.brier_score([0, 1], [0.1, np.nan])
    with pytest.raises(ValueError):
        mt.pinball_loss([1.0], [1.0], alpha=1.0)


def test_pinball_loss_known_values():
    assert mt.pinball_loss([10.0, 5.0], [8.0, 8.0], alpha=0.8) == pytest.approx((0.8 * 2 + 0.2 * 3) / 2)
    assert mt.pinball_loss([3.0], [3.0], alpha=0.95) == 0.0
    # for alpha = 0.5 pinball = MAE / 2
    assert mt.pinball_loss([0.0, 4.0], [1.0, 1.0], alpha=0.5) == pytest.approx(
        mt.mean_absolute_error([0.0, 4.0], [1.0, 1.0]) / 2
    )


def test_coverage_interval_width_and_crossing():
    y = [1.0, 5.0, 10.0, 20.0]
    assert mt.coverage(y, [2.0, 5.0, 9.0, 30.0]) == pytest.approx(0.75)  # y <= q counts equality
    assert mt.interval_coverage(y, [0.0, 6.0, 0.0, 0.0], [2.0, 9.0, 10.0, 19.0]) == pytest.approx(0.5)
    assert mt.mean_interval_width([0.0, 0.0], [10.0, 20.0]) == pytest.approx(15.0)
    assert mt.quantile_crossing_rate({0.5: [1.0, 5.0], 0.8: [2.0, 4.0]}) == pytest.approx(0.5)


def test_quantile_metrics_keys():
    y = np.array([0.0, 10.0, 20.0, 30.0])
    result = mt.quantile_metrics(y, {0.1: y - 1, 0.5: y, 0.8: y + 1, 0.9: y + 2})
    assert result["pinball_q050"] == 0.0 and result["mae_q050"] == 0.0
    assert result["coverage_q080"] == 1.0
    assert result["interval80_coverage"] == 1.0
    assert result["interval80_mean_width_min"] == pytest.approx(3.0)
    assert result["crossing_rate"] == 0.0
    assert mt.quantile_key(0.95) == "q095" and mt.quantile_key(0.1) == "q010"


def test_interval_metrics_use_the_same_names_and_values_as_quantile_metrics():
    rng = np.random.default_rng(3)
    y = rng.normal(size=200) * 10
    lower, upper = y - rng.uniform(-2, 8, 200), y + rng.uniform(-2, 8, 200)
    interval = mt.interval_metrics(y, lower, upper)
    full = mt.quantile_metrics(y, {0.1: lower, 0.9: upper})
    for key in ("pinball_q010", "pinball_q090", "coverage_q010", "coverage_q090"):
        assert interval[key] == pytest.approx(full[key])
    assert interval["interval80_coverage"] == pytest.approx(full["interval80_coverage"])
    assert interval["interval80_mean_width_min"] == pytest.approx(full["interval80_mean_width_min"])
    assert interval["interval80_crossing_rate"] == pytest.approx(float(np.mean(lower > upper)))
    assert mt.interval_key(0.10, 0.90) == "interval80" and mt.interval_key(0.025, 0.975) == "interval95"
    with pytest.raises(ValueError):
        mt.interval_key(0.9, 0.1)
