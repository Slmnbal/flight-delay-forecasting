"""Local hhmm + FlightDate + airport time zone -> UTC conversion (NO NETWORK).

In BTS On-Time, times are LOCAL (hhmm). Joining with weather (IEM, UTC) requires UTC. Cases handled:

  * '2400': midnight = 00:00 of the next day (minute 1440). The day rolls over automatically.
  * Arrival past midnight: the arrival date can differ from FlightDate. It is resolved with the rule
    "after departure, within at most 24 hours" (assumption: US domestic flight time < 24 h; candidate
    day offsets -1, 0, +1, +2 are tried; the smallest offset wins).
  * Actual times: since the M2 fix the layer uses ``actual_utc`` = CRS UTC + delay minutes (BTS
    DepDelay/ArrDelay), which has NO 12-hour assumption. ``nearest_utc`` (nearest candidate day to the
    reference, valid only for |delay| < 12 hours) is kept for callers that have no delay value; the
    layer does not use it any more.
  * DST transitions (zoneinfo/pandas, IANA database):
      - On the SPRING-FORWARD transition the local time does not exist (e.g. 2024-03-10 02:30
        New_York). Policy: PEP 495 fold=0 reading, i.e. the offset BEFORE the transition is used
        (02:30 -> 07:30Z = 03:30 EDT). Flagged with ``gap=True``.
      - On the FALL-BACK transition the local time exists TWICE (e.g. 2024-11-03 01:30 New_York).
        Policy: the FIRST occurrence (fold=0, daylight time) is taken (01:30 -> 05:30Z). Flagged with
        ``ambiguous=True``. hhmm alone cannot tell which one it was; such flights are few and reported.
  * Missing/cancelled: DepTime/ArrTime are empty for cancelled flights -> None/NaT, reason "missing".
    CRS (schedule) times are filled even for cancelled flights. No row is dropped; flags are produced.
  * Invalid value (e.g. '2575', '99'): None/NaT + ``invalid=True``.

Airport -> IANA time zone mapping lives in ``flight_delay.data.airports``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

__all__ = [
    "DEFAULT_ARRIVAL_WINDOW",
    "MINUTES_PER_DAY",
    "UtcResult",
    "actual_utc",
    "actual_utc_series",
    "arrival_utc",
    "arrival_utc_series",
    "hhmm_minutes_series",
    "local_clock_series",
    "local_to_utc",
    "local_to_utc_series",
    "nearest_utc",
    "nearest_utc_series",
    "parse_hhmm",
]

MINUTES_PER_DAY = 1440
DEFAULT_ARRIVAL_WINDOW = timedelta(hours=24)
_DEFAULT_ARRIVAL_WINDOW_PD = pd.Timedelta(hours=24)
_UTC_DTYPE = "datetime64[ns, UTC]"


# =============================================================================
# 1) hhmm parsing
# =============================================================================


def parse_hhmm(value: Any) -> int | None:
    """Convert an hhmm value to 'minutes since start of day'.

    Returns 0..1440 (2400 -> 1440 = 00:00 of the next day) or None if missing.
    Raises ValueError for an invalid (present but meaningless) value.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        value = stripped
    try:
        number = float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid hhmm: {value!r}") from e
    if not math.isfinite(number):
        return None  # NaN/inf: treated as missing
    if number != math.floor(number) or number < 0:
        raise ValueError(f"Invalid hhmm: {value!r}")
    whole = int(number)
    hours, minutes = divmod(whole, 100)
    if minutes > 59 or hours > 24 or (hours == 24 and minutes != 0):
        raise ValueError(f"Invalid hhmm: {value!r}")
    return hours * 60 + minutes


# =============================================================================
# 2) Single-value (scalar) conversion
# =============================================================================


@dataclass(frozen=True)
class UtcResult:
    utc: datetime | None
    ambiguous: bool = False  # two valid local readings on a fall-back transition
    gap: bool = False  # non-existent local time on a spring-forward transition
    reason: str | None = None  # None means no problem; "missing" | "invalid" | "tz_missing" | "inconsistent"
    day_offset: int = 0  # day offset from FlightDate that was chosen (for arrival / actual times)


def local_to_utc(day: date, hhmm: Any, tz_name: str | None, day_offset: int = 0) -> UtcResult:
    """Convert one local time to UTC (DST policy in the module docstring)."""
    if tz_name is None or (isinstance(tz_name, float) and math.isnan(tz_name)):
        return UtcResult(None, reason="tz_missing")
    try:
        minutes = parse_hhmm(hhmm)
    except ValueError:
        return UtcResult(None, reason="invalid")
    if minutes is None:
        return UtcResult(None, reason="missing")

    zone = ZoneInfo(tz_name)
    naive = datetime.combine(day, time(0)) + timedelta(minutes=minutes + MINUTES_PER_DAY * day_offset)
    first = naive.replace(tzinfo=zone, fold=0).astimezone(UTC)
    second = naive.replace(tzinfo=zone, fold=1).astimezone(UTC)
    ambiguous = gap = False
    if first != second:
        # If the round trip does not give back the same local time, it is a spring-forward gap.
        round_trip = first.astimezone(zone).replace(tzinfo=None)
        gap = round_trip != naive
        ambiguous = not gap
    return UtcResult(first, ambiguous=ambiguous, gap=gap, day_offset=day_offset)


def arrival_utc(
    day: date,
    hhmm: Any,
    tz_name: str | None,
    departure_utc: datetime | None,
    window: timedelta = DEFAULT_ARRIVAL_WINDOW,
) -> UtcResult:
    """Find the arrival UTC: the single candidate that falls after departure and within ``window``.

    On flights that cross midnight and cross time zones the arrival date differs from FlightDate.
    """
    if departure_utc is None:
        return UtcResult(None, reason="missing")
    first_error: UtcResult | None = None
    for offset in (-1, 0, 1, 2):
        result = local_to_utc(day, hhmm, tz_name, day_offset=offset)
        if result.utc is None:
            first_error = result  # missing/invalid/tz_missing: the same for any candidate day
            break
        if departure_utc <= result.utc < departure_utc + window:
            return result
    if first_error is not None:
        return first_error
    return UtcResult(None, reason="inconsistent")


def nearest_utc(day: date, hhmm: Any, tz_name: str | None, reference_utc: datetime | None) -> UtcResult:
    """For actual times: choose the candidate day nearest to the reference (e.g. CRS departure UTC)."""
    if reference_utc is None:
        return UtcResult(None, reason="missing")
    best: UtcResult | None = None
    for offset in (-1, 0, 1):
        result = local_to_utc(day, hhmm, tz_name, day_offset=offset)
        if result.utc is None:
            return result
        if best is None or best.utc is None or abs(result.utc - reference_utc) < abs(best.utc - reference_utc):
            best = result
    assert best is not None  # the loop above always sets it (or returns early)
    return best


def actual_utc(crs_utc: datetime | None, delay_minutes: Any) -> UtcResult:
    """Actual UTC = scheduled UTC + delay minutes (no 12-hour assumption; negative delay = early).

    ``reason`` is "missing" if either input is missing (cancelled flight, unknown time zone, ...).
    """
    if crs_utc is None:
        return UtcResult(None, reason="missing")
    if delay_minutes is None or delay_minutes is pd.NA or delay_minutes is pd.NaT:
        return UtcResult(None, reason="missing")
    minutes = float(delay_minutes)
    if not math.isfinite(minutes):
        return UtcResult(None, reason="missing")
    return UtcResult(crs_utc + timedelta(minutes=minutes))


# =============================================================================
# 3) Vectorised (pandas) conversion
# =============================================================================


def _minutes_series(hhmm: pd.Series) -> tuple[pd.Series, pd.Series]:
    """hhmm series -> (minutes (float; invalid/missing = NaN), invalid flag)."""
    numbers = pd.to_numeric(hhmm, errors="coerce").astype("float64")
    hours = np.floor(numbers / 100)
    mins = numbers - hours * 100
    valid = (
        numbers.notna()
        & (numbers >= 0)
        & (numbers == np.floor(numbers))
        & (mins <= 59)
        & ((hours < 24) | ((hours == 24) & (mins == 0)))
    )
    minutes = (hours * 60 + mins).where(valid)
    # Values that cannot be converted to a number but look filled (e.g. 'abc') are invalid too.
    filled = hhmm.notna() & (hhmm.astype(str).str.strip() != "")
    invalid = filled & ~valid
    return minutes, invalid


def _group_utc(naive: pd.Series, tz_name: str) -> pd.DataFrame:
    """Convert naive local times of ONE time zone (no NaT) to UTC."""
    n = len(naive)
    first = np.ones(n, dtype=bool)  # True = first occurrence (daylight time) -> consistent with fold=0
    second = np.zeros(n, dtype=bool)
    shift = pd.Timedelta(hours=1)  # spring-forward gap: shift 1 hour forward (= the fold=0 result)
    utc_first = naive.dt.tz_localize(tz_name, ambiguous=first, nonexistent=shift)
    utc_second = naive.dt.tz_localize(tz_name, ambiguous=second, nonexistent=shift)
    gap = naive.dt.tz_localize(tz_name, ambiguous=first, nonexistent="NaT").isna()
    ambiguous = (utc_first != utc_second) & ~gap
    return pd.DataFrame({"utc": utc_first.dt.tz_convert("UTC"), "ambiguous": ambiguous, "gap": gap})


def local_to_utc_series(day: pd.Series, hhmm: pd.Series, tz: pd.Series, day_offset: int = 0) -> pd.DataFrame:
    """Vectorised local -> UTC. The series must share the SAME (unique) index.

    Returns DataFrame[utc, ambiguous, gap, invalid, has_input]
      has_input=False -> date/hhmm/tz is missing (e.g. DepTime of a cancelled flight) and utc is NaT.
    """
    if not day.index.equals(hhmm.index) or not day.index.equals(tz.index):
        raise ValueError("day, hhmm and tz must share the same index.")
    if not day.index.is_unique:
        raise ValueError("The index must be unique (use reset_index).")
    day = pd.to_datetime(day).dt.normalize()
    minutes, invalid = _minutes_series(hhmm)
    naive = day + pd.to_timedelta(minutes + MINUTES_PER_DAY * day_offset, unit="m")
    has_tz = tz.notna()
    has_input = naive.notna() & has_tz

    parts = []
    for tz_name, subset in naive[has_input].groupby(tz[has_input], sort=True):
        parts.append(_group_utc(subset, str(tz_name)))
    if parts:
        result = pd.concat(parts).reindex(day.index)
        result["utc"] = result["utc"].astype(_UTC_DTYPE)
        result["ambiguous"] = result["ambiguous"].fillna(False).astype(bool)
        result["gap"] = result["gap"].fillna(False).astype(bool)
    else:
        result = pd.DataFrame(
            {
                "utc": pd.Series(pd.NaT, index=day.index, dtype=_UTC_DTYPE),
                "ambiguous": False,
                "gap": False,
            },
            index=day.index,
        )
    result["invalid"] = invalid.reindex(day.index).fillna(False).astype(bool)
    result["has_input"] = has_input.reindex(day.index).fillna(False).astype(bool)
    return result


def arrival_utc_series(
    day: pd.Series,
    hhmm: pd.Series,
    tz: pd.Series,
    departure_utc: pd.Series,
    window: pd.Timedelta = _DEFAULT_ARRIVAL_WINDOW_PD,
) -> pd.DataFrame:
    """Vectorised arrival UTC resolution (same rule as the scalar ``arrival_utc``).

    Returns DataFrame[utc, ambiguous, gap, day_offset, invalid, has_input, inconsistent]
    """
    candidates = {k: local_to_utc_series(day, hhmm, tz, day_offset=k) for k in (-1, 0, 1, 2)}
    index = day.index
    utc = pd.Series(pd.NaT, index=index, dtype=_UTC_DTYPE)
    ambiguous = pd.Series(False, index=index)
    gap = pd.Series(False, index=index)
    offset = pd.Series(np.nan, index=index, dtype="float64")
    # Write from the largest offset to the smallest -> the smallest valid offset writes last and wins.
    for k in (2, 1, 0, -1):
        cand = candidates[k]
        fits = cand["utc"].notna() & (cand["utc"] >= departure_utc) & (cand["utc"] < departure_utc + window)
        utc = cand["utc"].where(fits, utc)
        ambiguous = cand["ambiguous"].where(fits, ambiguous)
        gap = cand["gap"].where(fits, gap)
        offset = pd.Series(float(k), index=index).where(fits, offset)
    base = candidates[0]
    result = pd.DataFrame(
        {
            "utc": utc.astype(_UTC_DTYPE),
            "ambiguous": ambiguous.astype(bool),
            "gap": gap.astype(bool),
            "day_offset": offset,
            "invalid": base["invalid"],
            "has_input": base["has_input"],
        }
    )
    result["inconsistent"] = result["utc"].isna() & result["has_input"] & ~result["invalid"] & departure_utc.notna()
    return result


def actual_utc_series(crs_utc: pd.Series, delay_minutes: pd.Series) -> pd.Series:
    """Vectorised ``actual_utc``: CRS UTC (tz-aware) + delay minutes; NaT where either is missing."""
    delay = pd.to_timedelta(pd.to_numeric(delay_minutes, errors="coerce").astype("float64"), unit="m")
    return (crs_utc + delay).astype(_UTC_DTYPE)


def hhmm_minutes_series(hhmm: pd.Series) -> pd.Series:
    """hhmm series -> minutes since start of day (float; 2400 -> 1440; missing/invalid -> NaN)."""
    minutes, _ = _minutes_series(hhmm)
    return minutes


def local_clock_series(day: pd.Series, hhmm: pd.Series, day_offset: pd.Series | int = 0) -> pd.Series:
    """Naive LOCAL datetime = date + hhmm + day_offset days (NaT if hhmm is missing/invalid or the offset is NaN).

    No time zone is involved: it is the wall-clock reading at the airport (used for the local date/hour
    of scheduled traffic). ``day_offset`` can be the ``day_offset`` column of ``arrival_utc_series``.
    """
    base = pd.to_datetime(day).dt.normalize()
    minutes = hhmm_minutes_series(hhmm)
    return base + pd.to_timedelta(minutes + MINUTES_PER_DAY * day_offset, unit="m")


def nearest_utc_series(day: pd.Series, hhmm: pd.Series, tz: pd.Series, reference_utc: pd.Series) -> pd.DataFrame:
    """For actual times: the candidate day nearest to the reference (offsets -1, 0, +1)."""
    index = day.index
    best_diff = pd.Series(pd.NaT, index=index, dtype="timedelta64[ns]")
    utc = pd.Series(pd.NaT, index=index, dtype=_UTC_DTYPE)
    ambiguous = pd.Series(False, index=index)
    gap = pd.Series(False, index=index)
    base: pd.DataFrame | None = None
    for k in (-1, 0, 1):
        cand = local_to_utc_series(day, hhmm, tz, day_offset=k)
        if k == 0:
            base = cand
        diff = (cand["utc"] - reference_utc).abs()
        better = diff.notna() & (best_diff.isna() | (diff < best_diff))
        utc = cand["utc"].where(better, utc)
        ambiguous = cand["ambiguous"].where(better, ambiguous)
        gap = cand["gap"].where(better, gap)
        best_diff = diff.where(better, best_diff)
    assert base is not None  # offset 0 is always in the loop
    return pd.DataFrame(
        {
            "utc": utc.astype(_UTC_DTYPE),
            "ambiguous": ambiguous.astype(bool),
            "gap": gap.astype(bool),
            "invalid": base["invalid"],
            "has_input": base["has_input"],
        }
    )
