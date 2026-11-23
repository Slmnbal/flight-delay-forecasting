"""Fixed category lists for categorical features, learned from the fit window only (step-1 risk: months differ).

Why: the loader converts string keys to ``category`` per month and unions them, so the pandas category list of a
frame depends on WHICH months were read (Val-A / Val-B months included). A model must not see a different code for
the same airport because another month was loaded. ``CategoryEncoder`` therefore:

- ``fit``: takes the values observed in the fit-window rows (not the dtype's category list), keeps those with at least
  ``min_count`` rows, sorts them -> one fixed list per column; code = position in that list.
- ``codes``: float32 codes; a value that is not in the list ("unknown", e.g. an airport or carrier that first appears
  in Val-A) and a missing value both become NaN. LightGBM treats NaN in a categorical feature as missing and routes it
  with the categories that were not chosen in a split (documented LightGBM behaviour; not re-checked against the
  4.7.0 documentation in this run). The logistic baseline one-hot encodes the same codes with the SAME explicit list
  and ``handle_unknown='ignore'`` -> all-zero row for unknowns.
- ``unknown_report``: per column the number / share of unknown and missing values and up to 10 unknown values, so the
  run report shows how often this happens (nothing is silently mapped to a known category).
- ``to_dict`` / ``from_dict``: stored next to the model files, so a saved model can be applied later with the same
  codes.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from typing import Any, Self

import numpy as np
import pandas as pd

__all__ = ["DEFAULT_CATEGORICAL_COLUMNS", "CategoryEncoder"]

DEFAULT_CATEGORICAL_COLUMNS = ("Origin", "Reporting_Airline")  # features.CATEGORICAL_FEATURES (plan section 2.3 A)
_MAX_LISTED_UNKNOWN = 10


def _as_text(values: pd.Series) -> pd.Series:
    """String view of a column (category / object / string); missing stays <NA>."""
    return values.astype("string").str.strip()


def _as_objects(values: pd.Series) -> pd.Series:
    """Python str / <NA> objects (avoids comparing the pandas 'str' and 'string' dtypes with each other)."""
    return _as_text(values).astype(object)


class CategoryEncoder:
    """Fixed, fit-window-only category lists; see the module docstring."""

    def __init__(self, columns: Iterable[str] = DEFAULT_CATEGORICAL_COLUMNS, *, min_count: int = 1) -> None:
        if min_count < 1:
            raise ValueError("min_count must be >= 1")
        self.columns = tuple(columns)
        self.min_count = int(min_count)
        self.categories: dict[str, list[str]] = {}
        self.fit_start: str | None = None
        self.fit_end: str | None = None
        self.n_fit = 0

    @property
    def fitted(self) -> bool:
        return bool(self.categories)

    def fit(self, frame: pd.DataFrame, *, fit_end: dt.date | None = None, date_column: str = "FlightDate") -> Self:
        """Learn the lists from the rows of ``frame`` (the fit window). Rows after ``fit_end`` are refused."""
        missing = [c for c in self.columns if c not in frame.columns]
        if missing:
            raise KeyError(f"CategoryEncoder.fit needs columns: {missing}")
        if date_column in frame.columns and len(frame):
            dates = pd.to_datetime(frame[date_column], errors="coerce")
            if fit_end is not None and bool((dates > pd.Timestamp(fit_end)).any()):
                raise ValueError(f"Category lists may only be learned from the fit window (rows after {fit_end})")
            self.fit_start = str(dates.min().date())
            self.fit_end = str(dates.max().date())
        self.n_fit = int(len(frame))
        self.categories = {}
        for column in self.columns:
            counts = _as_text(frame[column]).value_counts(dropna=True)
            kept = sorted(str(value) for value, count in counts.items() if int(count) >= self.min_count)
            if not kept:
                raise ValueError(f"No category of {column!r} in the fit window")
            self.categories[column] = kept
        return self

    def _check(self) -> None:
        if not self.fitted:
            raise RuntimeError("CategoryEncoder is not fitted")

    def codes(self, values: pd.Series, column: str) -> np.ndarray:
        """float32 code (position in the fixed list); NaN for unknown and missing values."""
        self._check()
        coded = pd.Categorical(_as_objects(values), dtype=self.dtype(column)).codes  # unknown / missing -> -1
        out = np.asarray(coded, dtype="float32")
        out[out < 0] = np.nan
        return out

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Copy of ``frame`` with each encoded column as pandas ``category`` with the FIXED list (unknown -> NaN)."""
        self._check()
        out = frame.copy()
        for column in self.columns:
            if column in out.columns:
                out[column] = pd.Categorical(_as_objects(out[column]), dtype=self.dtype(column))
        return out

    def dtype(self, column: str) -> pd.CategoricalDtype:
        """The fixed categorical dtype of a column (object categories, unordered)."""
        self._check()
        return pd.CategoricalDtype(pd.Index(self.categories[column], dtype=object), ordered=False)

    def unknown_report(self, frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
        """Per column: rows, unknown (value not in the list), missing, unknown share, up to 10 unknown values."""
        self._check()
        report: dict[str, dict[str, Any]] = {}
        for column in self.columns:
            if column not in frame.columns:
                continue
            text = _as_text(frame[column])
            missing = text.isna()
            known = text.isin(self.categories[column]).fillna(False).to_numpy(dtype=bool)
            unknown = ~known & ~missing.to_numpy(dtype=bool)
            unknown_values = sorted({str(v) for v in text[unknown].unique()})
            rows = int(len(text))
            report[column] = {
                "rows": rows,
                "unknown": int(unknown.sum()),
                "missing": int(missing.sum()),
                "unknown_share": float(unknown.sum() / rows) if rows else 0.0,
                "unknown_values": unknown_values[:_MAX_LISTED_UNKNOWN],
                "unknown_values_total": len(unknown_values),
            }
        return report

    def to_dict(self) -> dict[str, Any]:
        self._check()
        return {
            "columns": list(self.columns),
            "min_count": self.min_count,
            "categories": {c: list(v) for c, v in self.categories.items()},
            "fit_start": self.fit_start,
            "fit_end": self.fit_end,
            "n_fit": self.n_fit,
            "unknown_rule": "value not in the list or missing -> NaN code (LightGBM: missing; one-hot: all zeros)",
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CategoryEncoder:
        encoder = cls(data["columns"], min_count=int(data.get("min_count", 1)))
        encoder.categories = {str(c): [str(v) for v in values] for c, values in data["categories"].items()}
        encoder.fit_start = data.get("fit_start")
        encoder.fit_end = data.get("fit_end")
        encoder.n_fit = int(data.get("n_fit", 0))
        return encoder
