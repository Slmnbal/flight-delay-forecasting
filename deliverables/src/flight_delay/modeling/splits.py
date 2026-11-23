"""Time-based splits of the modeling plan: the SINGLE source of the split dates.

Plan: ``experiments/modelleme-plani.md`` section 1 (plan module name ``bolme.py``; code name ``splits.py``).

- Split key: ``FlightDate`` (local scheduled departure date), as written in plan section 1.1. The layer partitions
  (``year=/month=``) are also by the month of ``FlightDate``, so a split month maps to exactly one partition and the
  final-test partitions never have to be opened during development. ``crs_dep_utc`` is NOT the split key (see the
  run report: a late-evening local departure on the last training day can have a UTC timestamp on the next day).
- Periods are inclusive on both ends and contiguous; ``validate_layout`` checks order, overlap and gaps (run at import).
- Final test (plan section 1.5, "look once"): every accessor refuses the final-test period unless the caller passes
  ``allow_final_test=True`` AND the lock file ``experiments/son-test-kilidi.json`` does not exist yet. Writing the lock
  file is the job of the (later) one-time final-test script, not of this module.
- Embargo (plan section 1.4): between training and Val-A the plan judges the label overlap negligible, so the default
  embargo is 0 days (``TRAIN_EVAL_EMBARGO_DAYS``); ``embargo_days`` can trim the tail of a fit window. The rolling
  conformal calibration window has a fixed 1-day embargo: for month m, FlightDate in [m - 57 days, m - 2 days].
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import LeakageError
from flight_delay.paths import PROJECT_ROOT

__all__ = [
    "CONFORMAL_WINDOW_END_OFFSET_DAYS",
    "CONFORMAL_WINDOW_START_OFFSET_DAYS",
    "DATA_END",
    "DATA_START",
    "DEVELOPMENT_END",
    "DEVELOPMENT_SPLITS",
    "FINAL_TEST",
    "FINAL_TEST_LOCK_FILE",
    "ROLLING_FOLDS",
    "SPLITS",
    "SPLIT_DATE_COLUMN",
    "TRAIN",
    "TRAIN_EVAL_EMBARGO_DAYS",
    "VAL_A",
    "VAL_B",
    "FinalTestAccessError",
    "Fold",
    "Period",
    "assert_no_final_test",
    "assign_split",
    "check_temporal_order",
    "conformal_calibration_window",
    "development_only",
    "get_fold",
    "get_period",
    "require_final_test_access",
    "require_lock_written",
    "select_split",
    "split_months",
    "trim_end",
    "validate_layout",
]

SPLIT_DATE_COLUMN = "FlightDate"


class FinalTestAccessError(PermissionError):
    """The final test period was requested without the explicit flag, or it has already been looked at."""


def _as_datetime(dates: pd.Series | Iterable[object]) -> pd.Series:
    """Dates normalised to midnight (datetime64[ns]); unparseable values become NaT."""
    series = dates if isinstance(dates, pd.Series) else pd.Series(list(dates))
    return pd.to_datetime(series, errors="coerce").dt.normalize()


@dataclass(frozen=True)
class Period:
    """A closed date interval [start, end] on ``FlightDate``."""

    name: str
    start: dt.date
    end: dt.date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"Period {self.name}: end {self.end} is before start {self.start}")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, dates: pd.Series | Iterable[object]) -> np.ndarray:
        """Boolean mask: date in [start, end]. NaT is never inside."""
        values = _as_datetime(dates)
        inside = (values >= pd.Timestamp(self.start)) & (values <= pd.Timestamp(self.end))
        return np.asarray(inside, dtype=bool)

    def months(self) -> list[tuple[int, int]]:
        """(year, month) of every calendar month the period touches, in order."""
        result: list[tuple[int, int]] = []
        year, month = self.start.year, self.start.month
        while (year, month) <= (self.end.year, self.end.month):
            result.append((year, month))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return result

    def month_labels(self) -> list[str]:
        return [f"{y:04d}-{m:02d}" for y, m in self.months()]


@dataclass(frozen=True)
class Fold:
    """Rolling-origin fold (plan section 1.3): fit on an expanding window, evaluate on the next 3 months."""

    name: str
    fit: Period
    evaluation: Period
    core: bool


# --- plan section 1.2 (inclusive dates) ---
TRAIN = Period("train", dt.date(2023, 9, 1), dt.date(2025, 8, 31))
VAL_A = Period("val_a", dt.date(2025, 9, 1), dt.date(2025, 12, 31))
VAL_B = Period("val_b", dt.date(2026, 1, 1), dt.date(2026, 2, 28))
FINAL_TEST = Period("final_test", dt.date(2026, 3, 1), dt.date(2026, 8, 31))

SPLITS: dict[str, Period] = {p.name: p for p in (TRAIN, VAL_A, VAL_B, FINAL_TEST)}
DEVELOPMENT_SPLITS: tuple[str, ...] = (TRAIN.name, VAL_A.name, VAL_B.name)
DATA_START = TRAIN.start
DATA_END = FINAL_TEST.end
DEVELOPMENT_END = VAL_B.end  # plan section 1.5 item 4: development code never sees FlightDate > 2026-02-28

# --- plan section 1.3 (all inside the training window) ---
_FIT_START = TRAIN.start
ROLLING_FOLDS: tuple[Fold, ...] = (
    Fold(
        "K1",
        Period("K1_fit", _FIT_START, dt.date(2024, 8, 31)),
        Period("K1_eval", dt.date(2024, 9, 1), dt.date(2024, 11, 30)),
        core=False,
    ),
    Fold(
        "K2",
        Period("K2_fit", _FIT_START, dt.date(2024, 11, 30)),
        Period("K2_eval", dt.date(2024, 12, 1), dt.date(2025, 2, 28)),
        core=False,
    ),
    Fold(
        "K3",
        Period("K3_fit", _FIT_START, dt.date(2025, 2, 28)),
        Period("K3_eval", dt.date(2025, 3, 1), dt.date(2025, 5, 31)),
        core=True,
    ),
    Fold(
        "K4",
        Period("K4_fit", _FIT_START, dt.date(2025, 5, 31)),
        Period("K4_eval", dt.date(2025, 6, 1), dt.date(2025, 8, 31)),
        core=True,
    ),
)

# --- plan section 1.4 ---
TRAIN_EVAL_EMBARGO_DAYS = 0  # the plan judges the train -> Val-A label overlap negligible (a few hours, first day)
CONFORMAL_WINDOW_START_OFFSET_DAYS = 57
CONFORMAL_WINDOW_END_OFFSET_DAYS = 2  # = 1 full day of embargo before the month starts

# --- plan section 1.5 ---
FINAL_TEST_LOCK_FILE = PROJECT_ROOT / "experiments" / "son-test-kilidi.json"


def validate_layout(periods: Iterable[Period] | None = None) -> None:
    """Periods must be ordered, non-overlapping and contiguous (next start = previous end + 1 day)."""
    ordered = list(periods) if periods is not None else list(SPLITS.values())
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.start <= previous.end:
            raise ValueError(f"Periods overlap or are out of order: {previous} / {current}")
        if current.start != previous.end + dt.timedelta(days=1):
            raise ValueError(
                f"Gap between periods: {previous.name} ends {previous.end}, {current.name} starts {current.start}"
            )
    for fold in ROLLING_FOLDS:
        if not (fold.fit.end < fold.evaluation.start and fold.evaluation.end <= TRAIN.end):
            raise ValueError(f"Fold {fold.name} must fit before it evaluates and stay inside the training window")


def require_final_test_access(allow_final_test: bool, lock_file: Path | None = None) -> None:
    """Raise FinalTestAccessError unless the flag is set and the lock file does not exist yet (plan section 1.5)."""
    if not allow_final_test:
        raise FinalTestAccessError(
            "The final test period (2026-03-01 .. 2026-08-31) is closed during development. Only the one-time "
            "final-test script may pass allow_final_test=True (plan section 1.5)."
        )
    lock = FINAL_TEST_LOCK_FILE if lock_file is None else Path(lock_file)
    if lock.exists():
        raise FinalTestAccessError(
            f"The final test has already been evaluated (lock file exists: {lock}). It is looked at only once."
        )


def require_lock_written(lock_file: Path | None = None) -> Path:
    """Raise FinalTestAccessError unless the one-time lock record exists (it is written BEFORE final-test data is read).

    Used by readers that open final-test partitions (``matrix.LayerTableReader(allow_final_test=True)``,
    ``run_final_test``): the order is ``require_final_test_access`` (no lock yet) -> write the lock -> read the data.
    """
    lock = FINAL_TEST_LOCK_FILE if lock_file is None else Path(lock_file)
    if not lock.is_file():
        raise FinalTestAccessError(
            f"Final-test data may only be read after the one-time lock record is written: {lock} does not exist."
        )
    return lock


def get_period(name: str, *, allow_final_test: bool = False, lock_file: Path | None = None) -> Period:
    """Period by name ('train', 'val_a', 'val_b', 'final_test'); the final test needs the explicit flag."""
    if name not in SPLITS:
        raise KeyError(f"Unknown split {name!r}; known: {sorted(SPLITS)}")
    if name == FINAL_TEST.name:
        require_final_test_access(allow_final_test, lock_file)
    return SPLITS[name]


def get_fold(name: str) -> Fold:
    for fold in ROLLING_FOLDS:
        if fold.name == name:
            return fold
    raise KeyError(f"Unknown fold {name!r}; known: {[f.name for f in ROLLING_FOLDS]}")


def split_months(name: str, *, allow_final_test: bool = False, lock_file: Path | None = None) -> list[tuple[int, int]]:
    """Layer partitions (year, month) to read for a split. The final test needs the explicit flag."""
    return get_period(name, allow_final_test=allow_final_test, lock_file=lock_file).months()


def trim_end(period: Period, embargo_days: int) -> Period:
    """Fit window with its last ``embargo_days`` days removed (a gap before the next period)."""
    if embargo_days < 0:
        raise ValueError(f"embargo_days must be >= 0: {embargo_days}")
    if embargo_days == 0:
        return period
    return Period(f"{period.name}_embargo{embargo_days}d", period.start, period.end - dt.timedelta(days=embargo_days))


def assign_split(dates: pd.Series | Iterable[object]) -> pd.Series:
    """Split label per date ('train' | 'val_a' | 'val_b' | 'final_test'; <NA> outside the 36 months).

    A label only; it does not open any data. Loaders must still go through ``get_period`` / ``split_months``.
    """
    values = _as_datetime(dates)
    labels = pd.Series(pd.NA, index=values.index, dtype="string")
    for period in SPLITS.values():
        labels[period.contains(values)] = period.name
    return labels


def select_split(
    frame: pd.DataFrame,
    name: str,
    *,
    date_column: str = SPLIT_DATE_COLUMN,
    allow_final_test: bool = False,
    lock_file: Path | None = None,
    embargo_days: int = 0,
) -> pd.DataFrame:
    """Rows of ``frame`` inside a split (order preserved, never shuffled); optional tail embargo for fit windows."""
    period = trim_end(get_period(name, allow_final_test=allow_final_test, lock_file=lock_file), embargo_days)
    return frame.loc[period.contains(frame[date_column])]


def assert_no_final_test(dates: pd.Series | Iterable[object]) -> None:
    """Raise FinalTestAccessError if any date is on or after the final-test start (development guard)."""
    values = _as_datetime(dates)
    late = values >= pd.Timestamp(FINAL_TEST.start)
    if bool(late.any()):
        raise FinalTestAccessError(
            f"{int(late.sum())} row(s) with FlightDate >= {FINAL_TEST.start} reached development code."
        )


def development_only(frame: pd.DataFrame, date_column: str = SPLIT_DATE_COLUMN) -> pd.DataFrame:
    """Rows with DATA_START <= FlightDate <= DEVELOPMENT_END (plan section 1.5 item 4); NaT rows are dropped."""
    window = Period("development", DATA_START, DEVELOPMENT_END)
    kept = frame.loc[window.contains(frame[date_column])]
    assert_no_final_test(kept[date_column])
    return kept


def check_temporal_order(
    fit_dates: pd.Series | Iterable[object],
    eval_dates: pd.Series | Iterable[object],
    *,
    embargo_days: int = 0,
) -> None:
    """Raise LeakageError unless max(fit) + embargo_days < min(eval) (whole days; at least one day apart)."""
    fit = _as_datetime(fit_dates).dropna()
    evaluation = _as_datetime(eval_dates).dropna()
    if fit.empty or evaluation.empty:
        return
    last_fit, first_eval = fit.max(), evaluation.min()
    if last_fit + pd.Timedelta(days=embargo_days) >= first_eval:
        raise LeakageError(
            f"Fit data ends {last_fit.date()} but evaluation starts {first_eval.date()} "
            f"(required: fit end + {embargo_days} day(s) embargo < evaluation start)."
        )


def conformal_calibration_window(month_start: dt.date) -> Period:
    """Rolling conformal calibration window for the month starting at ``month_start`` (plan sections 1.4 and 5.4)."""
    if month_start.day != 1:
        raise ValueError(f"month_start must be the first day of a month: {month_start}")
    return Period(
        f"conformal_{month_start:%Y-%m}",
        month_start - dt.timedelta(days=CONFORMAL_WINDOW_START_OFFSET_DAYS),
        month_start - dt.timedelta(days=CONFORMAL_WINDOW_END_OFFSET_DAYS),
    )


validate_layout()
