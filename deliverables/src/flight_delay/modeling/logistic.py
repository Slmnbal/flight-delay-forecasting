"""Logistic-regression baseline L (plan section 4.1) as a scikit-learn Pipeline.

- Input: the SAME model matrix as LightGBM (same features, same out-of-fold history encodings, same fixed category
  codes), rebuilt as a DataFrame. Deviation from the plan text (recorded in the run report): plan 4.1 / 2.4 item 4
  put a ``TargetEncoder`` inside the Pipeline; here the target encodings are the ``HistoryFeatures`` columns, which are
  already out-of-fold on the training rows (5 contiguous day blocks, plan 2.4 item 2) and fit-window-only on the
  evaluation rows. That keeps L and LightGBM on identical inputs; no encoder sees evaluation labels either way.
- One-hot: Origin, Reporting_Airline (fixed code lists of the CategoryEncoder), hour_block (0..6), month (1..12),
  day_of_week (1..7), with EXPLICIT category lists and ``handle_unknown='ignore'`` (unknown -> all-zero row).
- Numeric: ``RangeClipper`` -> ``SimpleImputer(strategy='median', add_indicator=True)`` -> ``StandardScaler``; all
  fitted inside the Pipeline on the training sample only.
- ``RangeClipper`` (added after the smoke run, see below): every numeric column is clipped to the range it had in the
  fit sample (default: min / max; NaN stays NaN for the imputer's indicator). A linear model extrapolates a slope
  learned inside the fit range without limit; LightGBM does not (a tree is constant outside the range it saw).
  Smoke-run evidence (run-20261119T181934Z, fit window 2025-06..08 only): cancellation L ROC-AUC by month was
  Sep 0.734, Oct 0.511, Nov 0.512, Dec 0.441, Jan 0.235, Feb 0.243 - it decays with the distance from the summer fit
  window, which a code error (label / class order / row alignment) would not do; the same code path gave a sane
  ArrDel15 L. Summer-only data cannot teach a winter relation (snow flags are constant 0 in the fit sample, so their
  coefficients are 0), while temperature / dew point / day_of_year values of January lie far outside the fit range and
  carry their summer slopes there. Clipping bounds that extrapolation; it does not create winter knowledge (the full
  run's 24-month window does). ``clip_quantile=None`` restores the step-2 behaviour (no clipping).
- Model: ``LogisticRegression(solver='lbfgs')`` (default L2; ``penalty`` is not passed because recent scikit-learn
  versions deprecate it in favour of ``l1_ratio`` - not checked against the 1.9.1 documentation in this run).
- Size: plan 4.1 allows a day-sampled fit for large data; the caller passes a whole-day sample of the fit window
  (``matrix.sample_days``). ConvergenceWarnings are captured and reported, not hidden.
"""

from __future__ import annotations

import time
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from flight_delay.modeling.categories import CategoryEncoder

__all__ = [
    "DEFAULT_CLIP_QUANTILE",
    "FIXED_ONE_HOT",
    "LogisticModel",
    "RangeClipper",
    "build_pipeline",
    "fit_logistic",
    "to_frame",
]

# 0.0 = clip to the observed min / max of the fit sample. Not a tuned number: min / max is the only choice that never
# moves a training value (a quantile > 0 would also flatten rare 0/1 flags whose share is below the quantile).
DEFAULT_CLIP_QUANTILE: float | None = 0.0

# integer-coded features with a known, fixed level set (hour_block: features.HOUR_BLOCK_EDGES -> 7 blocks)
FIXED_ONE_HOT: dict[str, list[float]] = {
    "hour_block": [float(b) for b in range(7)],
    "month": [float(m) for m in range(1, 13)],
    "day_of_week": [float(d) for d in range(1, 8)],
}


def _one_hot_levels(feature_names: Sequence[str], encoder: CategoryEncoder) -> dict[str, list[float]]:
    levels: dict[str, list[float]] = {}
    for column in encoder.columns:
        if column in feature_names:
            levels[column] = [float(i) for i in range(len(encoder.categories[column]))]
    for column, values in FIXED_ONE_HOT.items():
        if column in feature_names:
            levels[column] = values
    return levels


class RangeClipper(BaseEstimator, TransformerMixin):
    """Clip each column to [q, 1 - q] of the fit data (``quantile=0``: min / max); NaN passes through unchanged.

    A column without any finite value in the fit data is left unclipped (bounds -inf / +inf).
    """

    def __init__(self, quantile: float = 0.0) -> None:
        self.quantile = quantile

    def fit(self, x: Any, y: Any = None) -> RangeClipper:
        if not 0.0 <= self.quantile < 0.5:
            raise ValueError(f"quantile must be in [0, 0.5): {self.quantile}")
        values = np.asarray(x, dtype="float64")
        if values.ndim != 2:
            raise ValueError("RangeClipper expects a 2-D input")
        if hasattr(x, "columns"):
            self.feature_names_in_ = np.asarray([str(c) for c in x.columns], dtype=object)
        self.n_features_in_ = values.shape[1]
        lower = np.full(values.shape[1], -np.inf)
        upper = np.full(values.shape[1], np.inf)
        for j in range(values.shape[1]):
            column = values[:, j]
            finite = column[np.isfinite(column)]
            if finite.size:
                if self.quantile == 0.0:
                    lower[j], upper[j] = float(finite.min()), float(finite.max())
                else:
                    lower[j], upper[j] = np.quantile(finite, [self.quantile, 1.0 - self.quantile])
        self.lower_ = lower
        self.upper_ = upper
        return self

    def transform(self, x: Any) -> np.ndarray:
        values = np.asarray(x, dtype="float64")
        if values.ndim != 2 or values.shape[1] != self.n_features_in_:
            raise ValueError(f"Expected {self.n_features_in_} columns, got shape {values.shape}")
        return np.asarray(np.clip(values, self.lower_, self.upper_), dtype="float64")  # NaN stays NaN

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        if input_features is not None:
            return np.asarray([str(c) for c in input_features], dtype=object)
        if hasattr(self, "feature_names_in_"):
            return np.asarray(self.feature_names_in_, dtype=object)
        return np.asarray([f"x{i}" for i in range(self.n_features_in_)], dtype=object)

    def share_outside(self, x: Any) -> np.ndarray:
        """Per column: share of the finite values of ``x`` that lie outside the fit range (diagnostic)."""
        values = np.asarray(x, dtype="float64")
        finite = np.isfinite(values)
        outside = finite & ((values < self.lower_) | (values > self.upper_))
        counts = finite.sum(axis=0)
        return np.asarray(np.where(counts > 0, outside.sum(axis=0) / np.maximum(counts, 1), 0.0), dtype="float64")


def to_frame(x: np.ndarray, feature_names: Sequence[str]) -> pd.DataFrame:
    """DataFrame view of a model matrix (float64 so the one-hot category comparison is exact)."""
    return pd.DataFrame(np.asarray(x, dtype="float64"), columns=list(feature_names))


def build_pipeline(
    feature_names: Sequence[str],
    encoder: CategoryEncoder,
    *,
    c: float = 1.0,
    max_iter: int = 500,
    clip_quantile: float | None = DEFAULT_CLIP_QUANTILE,
) -> Pipeline:
    """``clip_quantile``: None = no clipping (step-2 behaviour); 0.0 = fit-sample min / max (default)."""
    levels = _one_hot_levels(feature_names, encoder)
    categorical = list(levels)
    numeric = [name for name in feature_names if name not in levels]
    one_hot = OneHotEncoder(
        categories=[np.asarray(levels[name], dtype="float64") for name in categorical],
        handle_unknown="ignore",
        sparse_output=False,
        dtype=np.float64,
    )
    steps: list[tuple[str, Any]] = []
    if clip_quantile is not None:
        steps.append(("clip", RangeClipper(quantile=clip_quantile)))  # before the imputer: NaN must stay NaN
    steps += [("impute", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler())]
    numeric_steps = Pipeline(steps)
    columns = ColumnTransformer(
        [("categorical", one_hot, categorical), ("numeric", numeric_steps, numeric)],
        remainder="drop",
        verbose_feature_names_out=True,
    )
    return Pipeline([("columns", columns), ("model", LogisticRegression(C=c, max_iter=max_iter, solver="lbfgs"))])


@dataclass
class LogisticModel:
    pipeline: Pipeline
    feature_names: list[str]
    n_train: int
    seconds: float
    convergence_warnings: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)

    def predict(self, x: np.ndarray, *, chunk_rows: int = 250_000) -> np.ndarray:
        parts = [
            np.asarray(self.pipeline.predict_proba(to_frame(x[s : s + chunk_rows], self.feature_names))[:, 1])
            for s in range(0, x.shape[0], chunk_rows)
        ]
        out = np.concatenate(parts) if parts else np.empty(0)
        return np.asarray(np.clip(out, 0.0, 1.0), dtype="float64")

    def extrapolation(self, x: np.ndarray, *, top: int = 10) -> list[dict[str, Any]]:
        """Numeric features whose values in ``x`` lie outside the fit-sample range (share of finite values), largest
        first; empty if the pipeline has no ``RangeClipper`` (``clip_quantile=None``)."""
        columns = self.pipeline.named_steps["columns"]
        numeric_names: list[str] = []
        clipper: RangeClipper | None = None
        for name, transformer, selected in columns.transformers_:
            if name == "numeric":
                numeric_names = [str(s) for s in selected]
                clipper = transformer.named_steps.get("clip")
        if clipper is None or not numeric_names:
            return []
        index = [self.feature_names.index(n) for n in numeric_names]
        shares = clipper.share_outside(np.asarray(x[:, index], dtype="float64"))
        rows = [
            {
                "feature": name,
                "share_outside_fit_range": float(share),
                "fit_min": float(clipper.lower_[j]),
                "fit_max": float(clipper.upper_[j]),
            }
            for j, (name, share) in enumerate(zip(numeric_names, shares, strict=True))
            if share > 0
        ]
        return sorted(rows, key=lambda r: (-cast(float, r["share_outside_fit_range"]), str(r["feature"])))[:top]

    def summary(self) -> dict[str, Any]:
        model = self.pipeline.named_steps["model"]
        iterations = np.asarray(getattr(model, "n_iter_", [np.nan]), dtype="float64")
        return {
            "n_train": self.n_train,
            "seconds": round(self.seconds, 2),
            "n_iter": float(iterations.max()),
            "convergence_warnings": list(self.convergence_warnings),
            "params": dict(self.params),
            "n_model_columns": int(np.asarray(model.coef_).shape[1]),
        }


def fit_logistic(
    x: np.ndarray,
    y: np.ndarray,
    feature_names: Sequence[str],
    encoder: CategoryEncoder,
    *,
    c: float = 1.0,
    max_iter: int = 500,
    clip_quantile: float | None = DEFAULT_CLIP_QUANTILE,
) -> LogisticModel:
    """``c`` = inverse regularisation strength (scikit-learn ``C``); ``clip_quantile`` see ``build_pipeline``."""
    labels = np.asarray(y, dtype="float64").ravel()
    if labels.size != x.shape[0] or not np.all((labels == 0) | (labels == 1)):
        raise ValueError("y must be 0/1 and aligned with x")
    pipeline = build_pipeline(feature_names, encoder, c=c, max_iter=max_iter, clip_quantile=clip_quantile)
    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        pipeline.fit(to_frame(x, feature_names), labels.astype("int64"))
    messages = [str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning)]
    for other in caught:  # everything else is passed on unchanged (e.g. an all-NaN column dropped by the imputer)
        if not issubclass(other.category, ConvergenceWarning):
            warnings.warn(other.message, other.category, stacklevel=2)
    return LogisticModel(
        pipeline=pipeline,
        feature_names=list(feature_names),
        n_train=int(labels.size),
        seconds=time.perf_counter() - started,
        convergence_warnings=messages,
        params={"C": c, "max_iter": max_iter, "solver": "lbfgs", "clip_quantile": clip_quantile},
    )
