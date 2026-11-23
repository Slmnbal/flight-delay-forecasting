"""Evaluation metrics of plan section 5.1, implemented with numpy only (no new dependency).

Classification (ArrDel15, cancellation): ROC-AUC, PR-AUC (average precision) + prevalence, Brier and Brier skill
score against a reference (B1), log-loss, reliability table with 10 equal-frequency bins, ECE, logistic
recalibration slope / intercept, calibration-in-the-large (mean prediction - observed rate), precision / recall / F1
at a threshold and the F1-maximising threshold.
Quantiles: pinball loss per alpha, MAE (for the median), raw coverage P(y <= q), two-sided interval coverage and mean
width, quantile crossing rate.

Definitions follow scikit-learn where one exists (``roc_auc_score`` with average ranks for ties,
``average_precision_score`` = sum over distinct thresholds of (R_n - R_{n-1}) * P_n), so the numbers can be
cross-checked; the known-value tests use the scikit-learn documentation examples. Every model and baseline goes through
these same functions (baseline-modeling: one metric code).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "average_precision",
    "best_f1_threshold",
    "brier_score",
    "brier_skill_score",
    "calibration_in_the_large",
    "calibration_slope_intercept",
    "classification_metrics",
    "coverage",
    "expected_calibration_error",
    "interval_coverage",
    "interval_key",
    "interval_metrics",
    "log_loss",
    "mean_absolute_error",
    "mean_interval_width",
    "pinball_loss",
    "precision_recall_f1",
    "quantile_crossing_rate",
    "quantile_key",
    "quantile_metrics",
    "reliability_table",
    "roc_auc",
]

_EPS = 1e-15


def quantile_key(alpha: float) -> str:
    """0.8 -> 'q080', 0.95 -> 'q095' (plan section 8 naming)."""
    return f"q{round(alpha * 100):03d}"


def _binary(y_true: Any, y_prob: Any) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y_true, dtype="float64").ravel()
    p = np.asarray(y_prob, dtype="float64").ravel()
    if y.shape != p.shape:
        raise ValueError(f"y_true and y_prob differ in length: {y.shape} vs {p.shape}")
    if y.size == 0:
        raise ValueError("Empty input")
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(p)):
        raise ValueError("NaN / inf in y_true or y_prob (filter the target universe first)")
    if not np.all((y == 0) | (y == 1)):
        raise ValueError("y_true must be 0/1")
    if np.any((p < 0) | (p > 1)):
        raise ValueError("y_prob must be in [0, 1]")
    return y, p


def _real(y_true: Any, y_pred: Any) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y_true, dtype="float64").ravel()
    q = np.asarray(y_pred, dtype="float64").ravel()
    if y.shape != q.shape:
        raise ValueError(f"Inputs differ in length: {y.shape} vs {q.shape}")
    if y.size == 0:
        raise ValueError("Empty input")
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(q)):
        raise ValueError("NaN / inf in the input (filter the target universe first)")
    return y, q


# ----------------------------------------------------------------------------
# classification
# ----------------------------------------------------------------------------


def roc_auc(y_true: Any, y_prob: Any) -> float:
    """ROC-AUC via the Mann-Whitney statistic with average ranks for ties; NaN if only one class is present."""
    y, p = _binary(y_true, y_prob)
    n_pos = float(y.sum())
    n_neg = float(y.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    sorted_p = p[order]
    _, first, counts = np.unique(sorted_p, return_index=True, return_counts=True)
    average_rank = first + (counts - 1) / 2.0 + 1.0  # 1-based
    ranks = np.empty(y.size, dtype="float64")
    ranks[order] = np.repeat(average_rank, counts)
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _distinct_threshold_counts(y: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each distinct score (descending): threshold, cumulative TP, cumulative FP when predicting p >= threshold."""
    order = np.argsort(-p, kind="mergesort")
    y_sorted, p_sorted = y[order], p[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1.0 - y_sorted)
    last_of_group = np.r_[np.nonzero(np.diff(p_sorted))[0], y.size - 1]
    return p_sorted[last_of_group], tp[last_of_group], fp[last_of_group]


def average_precision(y_true: Any, y_prob: Any) -> float:
    """PR-AUC as average precision (scikit-learn definition); NaN if there is no positive."""
    y, p = _binary(y_true, y_prob)
    n_pos = float(y.sum())
    if n_pos == 0:
        return float("nan")
    _, tp, fp = _distinct_threshold_counts(y, p)
    precision = tp / (tp + fp)
    recall = tp / n_pos
    recall_previous = np.r_[0.0, recall[:-1]]
    return float(np.sum((recall - recall_previous) * precision))


def brier_score(y_true: Any, y_prob: Any) -> float:
    y, p = _binary(y_true, y_prob)
    return float(np.mean((p - y) ** 2))


def brier_skill_score(y_true: Any, y_prob: Any, y_prob_reference: Any) -> float:
    """1 - Brier(model) / Brier(reference); NaN if the reference Brier is 0."""
    reference = brier_score(y_true, y_prob_reference)
    if reference == 0:
        return float("nan")
    return float(1.0 - brier_score(y_true, y_prob) / reference)


def log_loss(y_true: Any, y_prob: Any) -> float:
    """Mean negative log-likelihood; probabilities are clipped to [1e-15, 1 - 1e-15]."""
    y, p = _binary(y_true, y_prob)
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def calibration_in_the_large(y_true: Any, y_prob: Any) -> float:
    """Mean prediction minus observed rate (positive = over-prediction)."""
    y, p = _binary(y_true, y_prob)
    return float(p.mean() - y.mean())


def reliability_table(y_true: Any, y_prob: Any, n_bins: int = 10) -> pd.DataFrame:
    """Equal-frequency bins by sorted prediction (stable sort; ties may fall into neighbouring bins).

    Columns: bin, n, mean_pred, observed_rate.
    """
    y, p = _binary(y_true, y_prob)
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    order = np.argsort(p, kind="mergesort")
    bins = np.empty(y.size, dtype="int64")
    bins[order] = (np.arange(y.size) * n_bins) // y.size
    frame = pd.DataFrame({"bin": bins, "y": y, "p": p})
    table = frame.groupby("bin").agg(n=("y", "size"), mean_pred=("p", "mean"), observed_rate=("y", "mean"))
    return table.reset_index()


def expected_calibration_error(y_true: Any, y_prob: Any, n_bins: int = 10) -> float:
    """sum_b (n_b / N) * |mean_pred_b - observed_rate_b| over the equal-frequency bins."""
    table = reliability_table(y_true, y_prob, n_bins)
    weights = table["n"].to_numpy(dtype="float64") / float(table["n"].sum())
    gaps = np.abs(table["mean_pred"].to_numpy(dtype="float64") - table["observed_rate"].to_numpy(dtype="float64"))
    return float(np.sum(weights * gaps))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    """Numerically stable logistic function: never evaluates exp of a positive argument (no overflow warning)."""
    out = np.empty_like(z, dtype="float64")
    positive = z >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-z[positive]))
    exp_z = np.exp(z[~positive])
    out[~positive] = exp_z / (1.0 + exp_z)
    return out


def _log_likelihood(y: np.ndarray, z: np.ndarray) -> float:
    """Bernoulli log-likelihood with logits ``z``: sum(y * z - log(1 + exp(z))), via the stable ``logaddexp``."""
    return float(np.sum(y * z - np.logaddexp(0.0, z)))


def calibration_slope_intercept(
    y_true: Any, y_prob: Any, *, max_iter: int = 100, tol: float = 1e-10
) -> tuple[float, float]:
    """Logistic recalibration: fit logit P(y=1) = a + b * logit(p) by damped Newton; returns (intercept a, slope b).

    Perfect calibration gives (0, 1). Returns (NaN, NaN) if logit(p) is constant (e.g. the B0 baseline), if only one
    class is present, or if Newton does not converge (e.g. separable data).

    Numerics (fix of the smoke-run ``RuntimeWarning: overflow encountered in exp``): stable sigmoid / log-likelihood,
    start at (logit(mean y), 0) instead of (0, 1), and step halving so that every accepted step does not decrease the
    (concave) log-likelihood. The maximum is unique when it exists, so finite results of the old undamped version are
    unchanged up to ``tol``; cases where the old version overshot and diverged (it then returned NaN, e.g. strongly
    mis-ranked predictions with a negative slope) now converge.
    """
    y, p = _binary(y_true, y_prob)
    clipped = np.clip(p, 1e-6, 1.0 - 1e-6)
    x = np.log(clipped / (1.0 - clipped))
    if np.ptp(x) < 1e-12 or y.min() == y.max():
        return float("nan"), float("nan")
    design = np.column_stack([np.ones_like(x), x])
    rate = float(y.mean())
    beta = np.array([np.log(rate / (1.0 - rate)), 0.0])
    current = _log_likelihood(y, design @ beta)
    for _ in range(max_iter):
        mu = _sigmoid(design @ beta)
        weight = mu * (1.0 - mu)
        gradient = design.T @ (y - mu)
        hessian = (design * weight[:, None]).T @ design
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            return float("nan"), float("nan")
        if not np.all(np.isfinite(step)):
            return float("nan"), float("nan")
        scale = 1.0
        while True:
            candidate = beta + scale * step
            value = _log_likelihood(y, design @ candidate)
            if value >= current - 1e-12 * max(1.0, abs(current)):
                break
            scale *= 0.5
            if scale < 1e-10:
                return float("nan"), float("nan")
        beta, current = candidate, value
        if np.max(np.abs(scale * step)) < tol:
            return float(beta[0]), float(beta[1])
    return float("nan"), float("nan")


def precision_recall_f1(y_true: Any, y_prob: Any, threshold: float) -> dict[str, float]:
    """Predict positive when p >= threshold. Precision is NaN if nothing is predicted positive."""
    y, p = _binary(y_true, y_prob)
    predicted = p >= threshold
    tp = float(np.sum(predicted & (y == 1)))
    fp = float(np.sum(predicted & (y == 0)))
    fn = float(np.sum(~predicted & (y == 1)))
    precision = tp / (tp + fp) if tp + fp > 0 else float("nan")
    recall = tp / (tp + fn) if tp + fn > 0 else float("nan")
    f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn > 0 else float("nan")
    return {"threshold": float(threshold), "precision": precision, "recall": recall, "f1": f1}


def best_f1_threshold(y_true: Any, y_prob: Any) -> tuple[float, float]:
    """(threshold, F1) maximising F1 over the distinct predicted values (ties: the highest threshold)."""
    y, p = _binary(y_true, y_prob)
    n_pos = float(y.sum())
    if n_pos == 0:
        return float("nan"), float("nan")
    thresholds, tp, fp = _distinct_threshold_counts(y, p)
    f1 = 2 * tp / (2 * tp + fp + (n_pos - tp))
    best = int(np.argmax(f1))
    return float(thresholds[best]), float(f1[best])


def classification_metrics(
    y_true: Any,
    y_prob: Any,
    *,
    y_prob_reference: Any | None = None,
    threshold: float | None = None,
    n_bins: int = 10,
) -> dict[str, float]:
    """All plan section 5.1 classification metrics in one flat dict (NaN where undefined)."""
    y, p = _binary(y_true, y_prob)
    intercept, slope = calibration_slope_intercept(y, p)
    result: dict[str, float] = {
        "n": float(y.size),
        "prevalence": float(y.mean()),
        "mean_pred": float(p.mean()),
        "roc_auc": roc_auc(y, p),
        "pr_auc": average_precision(y, p),
        "brier": brier_score(y, p),
        "log_loss": log_loss(y, p),
        "ece": expected_calibration_error(y, p, n_bins),
        "calibration_in_the_large": calibration_in_the_large(y, p),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
    }
    if y_prob_reference is not None:
        result["brier_skill_score"] = brier_skill_score(y, p, y_prob_reference)
    if threshold is not None and np.isfinite(threshold):
        scores = precision_recall_f1(y, p, threshold)
        result.update({f"{name}_at_threshold": value for name, value in scores.items()})
    return result


# ----------------------------------------------------------------------------
# quantiles
# ----------------------------------------------------------------------------


def pinball_loss(y_true: Any, y_quantile: Any, alpha: float) -> float:
    """Mean of max(alpha * (y - q), (alpha - 1) * (y - q))."""
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1): {alpha}")
    y, q = _real(y_true, y_quantile)
    diff = y - q
    return float(np.mean(np.maximum(alpha * diff, (alpha - 1.0) * diff)))


def mean_absolute_error(y_true: Any, y_pred: Any) -> float:
    y, q = _real(y_true, y_pred)
    return float(np.mean(np.abs(y - q)))


def coverage(y_true: Any, y_upper: Any) -> float:
    """Raw one-sided coverage P(y <= q)."""
    y, q = _real(y_true, y_upper)
    return float(np.mean(y <= q))


def interval_coverage(y_true: Any, lower: Any, upper: Any) -> float:
    y, lo = _real(y_true, lower)
    _, hi = _real(y_true, upper)
    return float(np.mean((y >= lo) & (y <= hi)))


def mean_interval_width(lower: Any, upper: Any) -> float:
    lo, hi = _real(lower, upper)
    return float(np.mean(hi - lo))


def quantile_crossing_rate(quantiles: Mapping[float, Any]) -> float:
    """Share of rows where a lower-alpha quantile exceeds a higher-alpha one."""
    alphas = sorted(quantiles)
    if len(alphas) < 2:
        return 0.0
    matrix = np.column_stack([np.asarray(quantiles[a], dtype="float64").ravel() for a in alphas])
    return float(np.mean(np.any(np.diff(matrix, axis=1) < 0, axis=1)))


def interval_key(low: float, high: float) -> str:
    """(0.10, 0.90) -> 'interval80' (the name used by ``quantile_metrics`` and the MLflow topic)."""
    if not 0.0 < low < high < 1.0:
        raise ValueError(f"Need 0 < low < high < 1: {low}, {high}")
    return f"interval{round((high - low) * 100)}"


def interval_metrics(
    y_true: Any, lower: Any, upper: Any, levels: tuple[float, float] = (0.10, 0.90)
) -> dict[str, float]:
    """Metrics of a two-sided interval [lower, upper] built from the ``levels`` quantiles, with the SAME key names as
    ``quantile_metrics`` (pinball / raw coverage per end, ``interval80_coverage``, ``interval80_mean_width_min``) plus
    ``interval80_crossing_rate`` (share of rows with lower > upper; their width is negative)."""
    low, high = levels
    name = interval_key(low, high)
    y, lo = _real(y_true, lower)
    _, hi = _real(y_true, upper)
    return {
        f"pinball_{quantile_key(low)}": pinball_loss(y, lo, low),
        f"coverage_{quantile_key(low)}": coverage(y, lo),
        f"pinball_{quantile_key(high)}": pinball_loss(y, hi, high),
        f"coverage_{quantile_key(high)}": coverage(y, hi),
        f"{name}_coverage": interval_coverage(y, lo, hi),
        f"{name}_mean_width_min": mean_interval_width(lo, hi),
        f"{name}_crossing_rate": float(np.mean(lo > hi)),
    }


def quantile_metrics(
    y_true: Any, quantiles: Mapping[float, Any], interval: tuple[float, float] = (0.10, 0.90)
) -> dict[str, float]:
    """Plan section 5.1 quantile metrics: per alpha pinball + raw coverage, MAE for 0.5, interval coverage / width."""
    y = np.asarray(y_true, dtype="float64").ravel()
    result: dict[str, float] = {"n": float(y.size)}
    for alpha in sorted(quantiles):
        key = quantile_key(alpha)
        result[f"pinball_{key}"] = pinball_loss(y, quantiles[alpha], alpha)
        result[f"coverage_{key}"] = coverage(y, quantiles[alpha])
    if 0.5 in quantiles:
        result["mae_q050"] = mean_absolute_error(y, quantiles[0.5])
    low, high = interval
    if low in quantiles and high in quantiles:
        width = round((high - low) * 100)
        result[f"interval{width}_coverage"] = interval_coverage(y, quantiles[low], quantiles[high])
        result[f"interval{width}_mean_width_min"] = mean_interval_width(quantiles[low], quantiles[high])
    result["crossing_rate"] = quantile_crossing_rate(quantiles)
    return result
