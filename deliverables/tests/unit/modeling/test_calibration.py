"""Probability calibrators on SYNTHETIC data with a known miscalibration (fast, numpy + scikit-learn)."""

from __future__ import annotations

import json

import numpy as np
import pytest
from sklearn.isotonic import IsotonicRegression

from flight_delay.modeling import calibration as cal
from flight_delay.modeling import metrics as mt


def _miscalibrated(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """True probabilities from a logit; the 'model' reports logit / 2 - 1 (too flat and too low: slope 2 needed)."""
    rng = np.random.default_rng(seed)
    z = rng.normal(-1.0, 1.5, n)
    y = (rng.random(n) < 1.0 / (1.0 + np.exp(-z))).astype("float64")
    p_model = 1.0 / (1.0 + np.exp(-(z / 2.0 - 1.0)))
    return y, p_model


def test_isotonic_breakpoints_reproduce_scikit_learn_and_survive_json():
    y, p = _miscalibrated(3000, 1)
    calibrator = cal.fit_isotonic(y, p)
    reference = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True, out_of_bounds="clip").fit(p, y)
    _, p_new = _miscalibrated(1000, 2)
    p_new = np.r_[p_new, 0.0, 1.0]  # outside the fit range: clipped to the end values
    np.testing.assert_allclose(calibrator.predict(p_new), reference.predict(p_new), atol=1e-12)
    loaded = cal.Calibrator.from_dict(json.loads(json.dumps(calibrator.to_dict())))
    np.testing.assert_array_equal(loaded.predict(p_new), calibrator.predict(p_new))
    assert np.all(np.diff(calibrator.predict(np.sort(p_new))) >= 0)  # monotone
    assert calibrator.n_fit == 3000 and calibrator.to_dict()["n_breakpoints"] == len(calibrator.x)


def test_platt_recovers_the_known_slope_and_fixes_calibration_out_of_sample():
    y_fit, p_fit = _miscalibrated(20000, 3)
    y_eval, p_eval = _miscalibrated(20000, 4)  # fresh rows: honest evaluation
    platt = cal.fit_platt(y_fit, p_fit)
    assert platt.slope == pytest.approx(2.0, abs=0.1)
    result = cal.evaluate(platt, y_eval, p_eval)
    before, after = result["before"], result["after"]
    assert abs(after["calibration_in_the_large"]) < abs(before["calibration_in_the_large"])
    assert after["ece"] < before["ece"] and after["brier"] < before["brier"]
    assert after["calibration_slope"] == pytest.approx(1.0, abs=0.1)
    assert after["roc_auc"] == pytest.approx(before["roc_auc"])  # a monotone map keeps the ranking
    assert result["after_minus_before"]["brier"] == pytest.approx(after["brier"] - before["brier"])


def test_isotonic_improves_out_of_sample_and_brier_skill_uses_the_given_reference():
    y_fit, p_fit = _miscalibrated(20000, 5)
    y_eval, p_eval = _miscalibrated(20000, 6)
    iso = cal.fit_calibrator("isotonic", y_fit, p_fit)
    reference = np.full_like(p_eval, float(y_fit.mean()))
    result = cal.evaluate(iso, y_eval, p_eval, reference_before=reference, reference_after=reference)
    assert result["after"]["ece"] < result["before"]["ece"]
    assert result["after"]["brier_skill_score"] == pytest.approx(
        mt.brier_skill_score(y_eval, iso.predict(p_eval), reference)
    )
    assert set(cal.REPORTED_METRICS) - {"brier_skill_score"} <= set(result["before"])


def test_calibrators_refuse_bad_input_and_unknown_methods():
    with pytest.raises(ValueError):
        cal.fit_platt(np.zeros(10), np.linspace(0.1, 0.9, 10))  # one class: undefined
    with pytest.raises(ValueError):
        cal.fit_isotonic([0.0, 1.0, 2.0], [0.1, 0.2, 0.3])  # labels must be 0/1
    with pytest.raises(ValueError):
        cal.fit_calibrator("beta", [0.0, 1.0], [0.2, 0.8])
    assert cal.PRIMARY_METHOD == "isotonic" and cal.PRIMARY_METHOD in cal.CALIBRATION_METHODS
