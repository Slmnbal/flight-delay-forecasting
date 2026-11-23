"""Past statistics with hierarchical back-off (plan sections 2.3 B, 2.4 and 4.1). Label-reading code.

Two tables share one rule set:

- ``SmoothedRateTable`` (target encoding / B1 rates): levels from coarse to fine, e.g.
  ``() -> (Origin,) -> (Origin, hour_block) -> (Origin, Dest, hour_block)``. Each level is an m-estimate shrunk
  towards the level above: ``(n * mean + m * parent) / (n + m)`` (plan section 2.4 item 3). An unseen key (n = 0) or a
  key with ``n < min_support`` keeps the parent value, i.e. the back-off is automatic.
- ``BackoffQuantileTable`` (B1 quantiles, past quantile features): empirical quantiles (linear interpolation,
  numpy / pandas default) of the finest level whose support satisfies ``n * min(alpha, 1 - alpha) >= min_tail``
  (plan section 4.1: n (1 - alpha) >= 20, so n >= 40 / 100 / 400 for P50 / P80 / P95; using ``min(alpha, 1 - alpha)``
  extends the rule to the lower tail, e.g. alpha = 0.10 -> n >= 200 (assumption, the plan only states upper levels)).

Leakage rules (plan section 2.6):
- ``fit`` refuses rows dated after ``fit_end`` (``test_istatistik_donemi``) and records the window it saw.
- ``transform`` reads ONLY the key columns (``test_transform_etiketsiz``); it never touches a label.
- ``transform(..., require_after_fit_end=True)`` refuses evaluation rows that are not strictly after ``fit_end``.
- ``out_of_fold`` encodes training rows from other contiguous day blocks (plan 2.4 item 2, ``mode="oof"``) or only
  from earlier blocks (``mode="expanding"``, the past-only robustness check). Blocks are whole days; nothing is
  shuffled.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Sequence
from typing import Any, Literal, Self

import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import LeakageError
from flight_delay.modeling.metrics import quantile_key

__all__ = [
    "DEFAULT_M",
    "DEFAULT_MIN_SUPPORT",
    "DEFAULT_MIN_TAIL",
    "BackoffQuantileTable",
    "SmoothedRateTable",
    "day_blocks",
    "out_of_fold",
    "required_count",
]

DEFAULT_M = 20.0  # plan section 2.4 item 3 (starting value; chosen on Val-A later)
DEFAULT_MIN_SUPPORT = 1
DEFAULT_MIN_TAIL = 20  # plan section 4.1

Levels = Sequence[tuple[str, ...]]


def _validate_levels(levels: Levels) -> tuple[tuple[str, ...], ...]:
    checked = tuple(tuple(level) for level in levels)
    if not checked or checked[0] != ():
        raise ValueError("The first level must be the global level ()")
    for coarse, fine in zip(checked, checked[1:], strict=False):
        if not set(coarse) < set(fine):
            raise ValueError(f"Each level must strictly refine the previous one: {coarse} -> {fine}")
    return checked


def _key_columns(levels: tuple[tuple[str, ...], ...]) -> list[str]:
    ordered: list[str] = []
    for level in levels:
        ordered.extend(column for column in level if column not in ordered)
    return ordered


def _dates(frame: pd.DataFrame, date_column: str) -> pd.Series:
    if date_column not in frame.columns:
        raise KeyError(f"Date column missing: {date_column}")
    return pd.to_datetime(frame[date_column], errors="coerce").dt.normalize()


def _check_fit_window(frame: pd.DataFrame, date_column: str, fit_end: dt.date) -> tuple[str | None, str | None]:
    dates = _dates(frame, date_column)
    if dates.isna().any():
        raise ValueError(f"{int(dates.isna().sum())} row(s) without {date_column} in the fit data")
    if len(dates) and dates.max() > pd.Timestamp(fit_end):
        raise LeakageError(
            f"Fit data contains rows after fit_end={fit_end} (latest {dates.max().date()}): statistics may only be "
            "computed from the fit window."
        )
    if not len(dates):
        return None, None
    return str(dates.min().date()), str(dates.max().date())


def _check_after(frame: pd.DataFrame, date_column: str, fit_end: dt.date | None) -> None:
    if fit_end is None:
        raise RuntimeError("Table is not fitted")
    dates = _dates(frame, date_column)
    if len(dates) and (dates.isna().any() or dates.min() <= pd.Timestamp(fit_end)):
        raise LeakageError(
            f"Evaluation rows must be strictly after fit_end={fit_end} (earliest {dates.min()}); use out_of_fold for "
            "rows inside the fit window."
        )


def _finite_target(target: Any, length: int) -> np.ndarray:
    values = np.asarray(target, dtype="float64").ravel()
    if values.size != length:
        raise ValueError(f"target length {values.size} != frame length {length}")
    return values


def required_count(alpha: float, min_tail: int = DEFAULT_MIN_TAIL) -> int:
    """Smallest n with n * min(alpha, 1 - alpha) >= min_tail (rounded to avoid float artefacts: 0.8 -> 100)."""
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1): {alpha}")
    return math.ceil(round(min_tail / min(alpha, 1.0 - alpha), 9))


class SmoothedRateTable:
    """Hierarchical m-estimate of a mean (rate) with automatic back-off; see the module docstring."""

    def __init__(
        self,
        levels: Levels,
        *,
        m: float = DEFAULT_M,
        min_support: int = DEFAULT_MIN_SUPPORT,
        name: str = "rate",
    ) -> None:
        if m < 0:
            raise ValueError("m must be >= 0")
        if min_support < 1:
            raise ValueError("min_support must be >= 1")
        self.levels = _validate_levels(levels)
        self.key_columns = _key_columns(self.levels)
        self.m = float(m)
        self.min_support = int(min_support)
        self.name = name
        self.fit_end: dt.date | None = None
        self.fit_first_date: str | None = None
        self.fit_last_date: str | None = None
        self.n_fit = 0
        self.global_mean = float("nan")
        self._tables: list[pd.DataFrame] = []

    def fit(self, frame: pd.DataFrame, target: Any, *, fit_end: dt.date, date_column: str = "FlightDate") -> Self:
        """Learn the level tables from rows with a finite target; refuses rows after ``fit_end``."""
        self.fit_first_date, self.fit_last_date = _check_fit_window(frame, date_column, fit_end)
        values = _finite_target(target, len(frame))
        use = np.isfinite(values)
        data = frame.loc[use, self.key_columns].copy()
        data["_y"] = values[use]
        self.fit_end = fit_end
        self.n_fit = int(use.sum())
        self.global_mean = float(data["_y"].mean()) if self.n_fit else float("nan")
        self._tables = []
        for level in self.levels[1:]:
            grouped = data.groupby(list(level), observed=True, sort=False)["_y"].agg(["sum", "size"])
            self._tables.append(grouped.rename(columns={"sum": "_sum", "size": "_n"}).reset_index())
        return self

    def transform(
        self, frame: pd.DataFrame, *, require_after_fit_end: bool = False, date_column: str = "FlightDate"
    ) -> pd.DataFrame:
        """Columns ``value``, ``support`` (n of the level used) and ``level`` (index into ``levels``).

        Reads only ``key_columns`` (and the date column when ``require_after_fit_end``); labels are never read.
        """
        if self.fit_end is None:
            raise RuntimeError("Table is not fitted")
        if require_after_fit_end:
            _check_after(frame, date_column, self.fit_end)
        keys = frame[self.key_columns].reset_index(drop=True)
        size = len(keys)
        value = np.full(size, self.global_mean, dtype="float64")
        support = np.full(size, float(self.n_fit), dtype="float64")
        level_used = np.zeros(size, dtype="int8")
        tables = self._tables if self.n_fit else []  # empty fit (first expanding block): everything stays NaN
        for index, (level, table) in enumerate(zip(self.levels[1:], tables, strict=False), start=1):
            joined = keys[list(level)].merge(table, how="left", on=list(level), validate="many_to_one")
            n = joined["_n"].fillna(0).to_numpy(dtype="float64")
            total = joined["_sum"].fillna(0).to_numpy(dtype="float64")
            use = n >= self.min_support
            denominator = n + self.m
            smoothed = np.divide(total + self.m * value, denominator, out=np.full(size, np.nan), where=denominator > 0)
            value = np.where(use, smoothed, value)
            support = np.where(use, n, support)
            level_used = np.where(use, index, level_used).astype("int8")
        return pd.DataFrame({"value": value, "support": support, "level": level_used}, index=frame.index)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "levels": [list(level) for level in self.levels],
            "m": self.m,
            "min_support": self.min_support,
            "fit_end": str(self.fit_end) if self.fit_end else None,
            "fit_first_date": self.fit_first_date,
            "fit_last_date": self.fit_last_date,
            "n_fit": self.n_fit,
            "global_mean": self.global_mean,
        }


class BackoffQuantileTable:
    """Empirical quantiles per key with the support rule n * min(alpha, 1 - alpha) >= min_tail; see the module."""

    def __init__(
        self,
        levels: Levels,
        alphas: Sequence[float] = (0.50, 0.80, 0.95),
        *,
        min_tail: int = DEFAULT_MIN_TAIL,
        name: str = "quantile",
    ) -> None:
        self.levels = _validate_levels(levels)
        self.key_columns = _key_columns(self.levels)
        self.alphas = tuple(sorted(float(a) for a in alphas))
        for alpha in self.alphas:
            required_count(alpha, min_tail)  # validates alpha
        self.min_tail = int(min_tail)
        self.name = name
        self.fit_end: dt.date | None = None
        self.fit_first_date: str | None = None
        self.fit_last_date: str | None = None
        self.n_fit = 0
        self.global_quantiles: dict[float, float] = {}
        self._tables: list[pd.DataFrame] = []

    def fit(self, frame: pd.DataFrame, target: Any, *, fit_end: dt.date, date_column: str = "FlightDate") -> Self:
        self.fit_first_date, self.fit_last_date = _check_fit_window(frame, date_column, fit_end)
        values = _finite_target(target, len(frame))
        use = np.isfinite(values)
        data = frame.loc[use, self.key_columns].copy()
        data["_y"] = values[use]
        self.fit_end = fit_end
        self.n_fit = int(use.sum())
        if self.n_fit:
            computed = np.quantile(data["_y"].to_numpy(), self.alphas)
            self.global_quantiles = {a: float(q) for a, q in zip(self.alphas, computed, strict=True)}
        else:
            self.global_quantiles = {a: float("nan") for a in self.alphas}
        self._tables = []
        for level in self.levels[1:]:
            grouped = data.groupby(list(level), observed=True, sort=False)["_y"]
            if self.n_fit:
                quantiles = grouped.quantile(list(self.alphas)).unstack(-1)
                quantiles.columns = [f"_{quantile_key(a)}" for a in self.alphas]
                table = quantiles.join(grouped.size().rename("_n")).reset_index()
            else:
                table = pd.DataFrame(columns=[*level, *[f"_{quantile_key(a)}" for a in self.alphas], "_n"])
            self._tables.append(table)
        return self

    def transform(
        self, frame: pd.DataFrame, *, require_after_fit_end: bool = False, date_column: str = "FlightDate"
    ) -> pd.DataFrame:
        """Per alpha: ``q050`` (value), ``support_q050`` (n of the level used), ``level_q050``. Keys only."""
        if self.fit_end is None:
            raise RuntimeError("Table is not fitted")
        if require_after_fit_end:
            _check_after(frame, date_column, self.fit_end)
        keys = frame[self.key_columns].reset_index(drop=True)
        size = len(keys)
        values = {a: np.full(size, self.global_quantiles[a], dtype="float64") for a in self.alphas}
        supports = {a: np.full(size, float(self.n_fit), dtype="float64") for a in self.alphas}
        levels_used = {a: np.zeros(size, dtype="int8") for a in self.alphas}
        tables = self._tables if self.n_fit else []  # empty fit: everything stays NaN
        for index, (level, table) in enumerate(zip(self.levels[1:], tables, strict=False), start=1):
            joined = keys[list(level)].merge(table, how="left", on=list(level), validate="many_to_one")
            n = pd.to_numeric(joined["_n"], errors="coerce").fillna(0).to_numpy(dtype="float64")
            for alpha in self.alphas:
                use = n >= required_count(alpha, self.min_tail)
                level_value = pd.to_numeric(joined[f"_{quantile_key(alpha)}"], errors="coerce").to_numpy(
                    dtype="float64"
                )
                values[alpha] = np.where(use, level_value, values[alpha])
                supports[alpha] = np.where(use, n, supports[alpha])
                levels_used[alpha] = np.where(use, index, levels_used[alpha]).astype("int8")
        columns: dict[str, np.ndarray] = {}
        for alpha in self.alphas:
            key = quantile_key(alpha)
            columns[key] = values[alpha]
            columns[f"support_{key}"] = supports[alpha]
            columns[f"level_{key}"] = levels_used[alpha]
        return pd.DataFrame(columns, index=frame.index)

    def quantiles(self, frame: pd.DataFrame, **kwargs: Any) -> dict[float, np.ndarray]:
        """alpha -> predicted quantile array (convenience for the metric code)."""
        out = self.transform(frame, **kwargs)
        return {a: out[quantile_key(a)].to_numpy(dtype="float64") for a in self.alphas}

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "levels": [list(level) for level in self.levels],
            "alphas": list(self.alphas),
            "min_tail": self.min_tail,
            "required_counts": {quantile_key(a): required_count(a, self.min_tail) for a in self.alphas},
            "fit_end": str(self.fit_end) if self.fit_end else None,
            "fit_first_date": self.fit_first_date,
            "fit_last_date": self.fit_last_date,
            "n_fit": self.n_fit,
            "global_quantiles": {quantile_key(a): q for a, q in self.global_quantiles.items()},
        }


def day_blocks(dates: pd.Series, n_blocks: int) -> np.ndarray:
    """Block id per row: the sorted distinct days are cut into ``n_blocks`` contiguous groups (no shuffling)."""
    if n_blocks < 2:
        raise ValueError("n_blocks must be >= 2")
    days = pd.to_datetime(dates, errors="coerce").dt.normalize()
    if days.isna().any():
        raise ValueError("Dates with NaT cannot be assigned to a block")
    unique_days = np.sort(days.unique())
    if len(unique_days) < n_blocks:
        raise ValueError(f"Only {len(unique_days)} distinct day(s) for {n_blocks} blocks")
    block_of_day = np.empty(len(unique_days), dtype="int64")
    for block, chunk in enumerate(np.array_split(np.arange(len(unique_days)), n_blocks)):
        block_of_day[chunk] = block
    return np.asarray(block_of_day[np.searchsorted(unique_days, days.to_numpy())], dtype="int64")


FitTransform = Callable[[pd.DataFrame, pd.DataFrame, dt.date], pd.DataFrame]


def out_of_fold(
    frame: pd.DataFrame,
    fit_transform: FitTransform,
    *,
    fit_end: dt.date,
    n_blocks: int = 5,
    mode: Literal["oof", "expanding"] = "oof",
    date_column: str = "FlightDate",
) -> pd.DataFrame:
    """Encode the rows of a fit window without using their own labels (plan section 2.4 item 2).

    ``fit_transform(fit_part, apply_part, fit_end_of_part)`` must fit on ``fit_part`` and return the encoding of
    ``apply_part`` (same index). ``mode="oof"``: each block is encoded from all other blocks. ``mode="expanding"``:
    only from earlier blocks (fit_end = the day before the block starts), so the first block gets an empty fit.
    """
    if mode not in ("oof", "expanding"):
        raise ValueError(f"mode must be 'oof' or 'expanding': {mode!r}")
    blocks = day_blocks(frame[date_column], n_blocks)
    days = pd.to_datetime(frame[date_column]).dt.normalize()
    parts: list[pd.DataFrame] = []
    for block in range(n_blocks):
        in_block = blocks == block
        if mode == "oof":
            fit_mask, part_end = ~in_block, fit_end
        else:
            fit_mask = blocks < block
            part_end = (days[in_block].min() - pd.Timedelta(days=1)).date()
        encoded = fit_transform(frame.loc[fit_mask], frame.loc[in_block], part_end)
        parts.append(encoded)
    return pd.concat(parts).reindex(frame.index)
