"""Probability calibration of the classifiers (plan sections 4.2 and 5.1), fitted on Val-B data only.

- Primary method: **isotonic** (plan 4.2: "A'daki güvenilirlik grafiği sapma gösterirse isotonic kalibratör B'de fit
  edilir"). Comparison: **Platt** = logistic recalibration on logit(p), i.e. the same fit as
  ``metrics.calibration_slope_intercept`` (one code for the slope that is reported and the one that is applied).
- The plan rule "the calibrator is applied to the model AND to B1 with the same rule, or to none" is the caller's job
  (``run_calibration`` fits one calibrator per model, B1 included).
- Isotonic: scikit-learn ``IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds='clip')`` is fitted; only
  its breakpoints (``X_thresholds_``, ``y_thresholds_``) are kept and applied with ``np.interp`` (linear between
  breakpoints, constant outside), so a calibrator re-loaded from JSON predicts exactly what the fitted one predicts;
  the test compares this with scikit-learn's own ``predict``.
- A calibrator never sees the evaluation rows: ``fit_*`` take the fit part only; ``evaluate`` reports the metrics on the
  evaluation part before and after, with the SAME metric code as every model (``metrics.classification_metrics``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression

from flight_delay.modeling import metrics as mt

__all__ = [
    "CALIBRATION_METHODS",
    "PRIMARY_METHOD",
    "REPORTED_METRICS",
    "Calibrator",
    "evaluate",
    "fit_calibrator",
    "fit_isotonic",
    "fit_platt",
]

CALIBRATION_METHODS: tuple[str, ...] = ("isotonic", "platt")
PRIMARY_METHOD = "isotonic"  # plan 4.2 (fixed before any calibration result was seen)
REPORTED_METRICS: tuple[str, ...] = (
    "n",
    "prevalence",
    "mean_pred",
    "brier",
    "brier_skill_score",
    "log_loss",
    "ece",
    "calibration_in_the_large",
    "calibration_intercept",
    "calibration_slope",
    "roc_auc",
    "pr_auc",
)
_LOGIT_CLIP = 1e-6  # same clipping as metrics.calibration_slope_intercept


def _logit(p: np.ndarray) -> np.ndarray:
    clipped = np.clip(p, _LOGIT_CLIP, 1.0 - _LOGIT_CLIP)
    return np.asarray(np.log(clipped / (1.0 - clipped)), dtype="float64")


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return np.asarray(np.exp(-np.logaddexp(0.0, -z)), dtype="float64")  # stable 1 / (1 + exp(-z))


@dataclass(frozen=True)
class Calibrator:
    """A fitted calibrator. isotonic: breakpoints ``x`` -> ``y``; platt: ``intercept`` + ``slope`` * logit(p)."""

    method: str
    n_fit: int
    prevalence_fit: float
    x: tuple[float, ...] = ()
    y: tuple[float, ...] = ()
    intercept: float | None = None
    slope: float | None = None

    def predict(self, p: Any) -> np.ndarray:
        values = np.asarray(p, dtype="float64").ravel()
        if self.method == "isotonic":
            out = np.interp(values, np.asarray(self.x), np.asarray(self.y))
        elif self.method == "platt":
            assert self.intercept is not None and self.slope is not None
            out = _sigmoid(self.intercept + self.slope * _logit(values))
        else:
            raise ValueError(f"Unknown calibration method {self.method!r}")
        return np.asarray(np.clip(out, 0.0, 1.0), dtype="float64")

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "n_fit": self.n_fit,
            "prevalence_fit": self.prevalence_fit,
            "x": list(self.x),
            "y": list(self.y),
            "intercept": self.intercept,
            "slope": self.slope,
            "n_breakpoints": len(self.x),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Calibrator:
        return cls(
            method=str(data["method"]),
            n_fit=int(data["n_fit"]),
            prevalence_fit=float(data["prevalence_fit"]),
            x=tuple(float(v) for v in data.get("x", ())),
            y=tuple(float(v) for v in data.get("y", ())),
            intercept=None if data.get("intercept") is None else float(data["intercept"]),
            slope=None if data.get("slope") is None else float(data["slope"]),
        )


def _check(y: Any, p: Any) -> tuple[np.ndarray, np.ndarray]:
    labels = np.asarray(y, dtype="float64").ravel()
    probs = np.asarray(p, dtype="float64").ravel()
    mt.brier_score(labels, probs)  # same input checks as every metric (0/1 labels, p in [0, 1], finite, same length)
    return labels, probs


def fit_isotonic(y: Any, p: Any) -> Calibrator:
    labels, probs = _check(y, p)
    model = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True, out_of_bounds="clip").fit(probs, labels)
    return Calibrator(
        method="isotonic",
        n_fit=int(labels.size),
        prevalence_fit=float(labels.mean()),
        x=tuple(float(v) for v in np.asarray(model.X_thresholds_)),
        y=tuple(float(v) for v in np.asarray(model.y_thresholds_)),
    )


def fit_platt(y: Any, p: Any) -> Calibrator:
    """Logistic recalibration; ValueError if it is undefined (one class, constant p, no convergence)."""
    labels, probs = _check(y, p)
    intercept, slope = mt.calibration_slope_intercept(labels, probs)
    if not (np.isfinite(intercept) and np.isfinite(slope)):
        raise ValueError("Platt scaling is undefined on this fit part (one class, constant p or no convergence)")
    return Calibrator(
        method="platt",
        n_fit=int(labels.size),
        prevalence_fit=float(labels.mean()),
        intercept=float(intercept),
        slope=float(slope),
    )


def fit_calibrator(method: str, y: Any, p: Any) -> Calibrator:
    if method == "isotonic":
        return fit_isotonic(y, p)
    if method == "platt":
        return fit_platt(y, p)
    raise ValueError(f"method must be one of {CALIBRATION_METHODS}: {method!r}")


def _metrics(y: np.ndarray, p: np.ndarray, reference: np.ndarray | None) -> dict[str, float]:
    full = mt.classification_metrics(y, p, y_prob_reference=reference)
    return {k: full[k] for k in REPORTED_METRICS if k in full}


def evaluate(
    calibrator: Calibrator,
    y_eval: Any,
    p_eval: Any,
    *,
    reference_before: Any | None = None,
    reference_after: Any | None = None,
) -> dict[str, Any]:
    """Metrics on the evaluation part before / after calibration, and after - before.

    ``reference_*``: B1 probabilities on the same rows for the Brier skill score (before: raw B1; after: B1 passed
    through ITS OWN calibrator of the same method - plan 4.2 "same rule for the model and B1").
    """
    y, p = _check(y_eval, p_eval)
    calibrated = calibrator.predict(p)
    ref_before = None if reference_before is None else np.asarray(reference_before, dtype="float64")
    ref_after = None if reference_after is None else np.asarray(reference_after, dtype="float64")
    before = _metrics(y, p, ref_before)
    after = _metrics(y, calibrated, ref_after)
    change = {k: after[k] - before[k] for k in before if k in after and k not in ("n", "prevalence")}
    return {"before": before, "after": after, "after_minus_before": change}
