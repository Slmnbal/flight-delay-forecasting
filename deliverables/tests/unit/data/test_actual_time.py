"""Actual UTC = CRS UTC + delay minutes (M2) and the local-clock helpers (offline)."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from flight_delay.data import time_conversion as tc


def dt(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def test_actual_utc_scalar():
    assert tc.actual_utc(dt(2024, 7, 15, 11), 780).utc == dt(2024, 7, 16, 0)  # 13 h late crosses the day
    assert tc.actual_utc(dt(2024, 7, 15, 11), -20).utc == dt(2024, 7, 15, 10, 40)  # early
    assert tc.actual_utc(dt(2024, 7, 15, 11), 0).utc == dt(2024, 7, 15, 11)
    assert tc.actual_utc(dt(2024, 7, 15, 11), 2000).utc == dt(2024, 7, 16, 20, 20)  # > 24 h late


def test_actual_utc_scalar_missing():
    assert tc.actual_utc(None, 10).reason == "missing"
    assert tc.actual_utc(dt(2024, 7, 15, 11), None).reason == "missing"
    assert tc.actual_utc(dt(2024, 7, 15, 11), float("nan")).reason == "missing"
    assert tc.actual_utc(dt(2024, 7, 15, 11), pd.NA).reason == "missing"


def test_actual_utc_series_matches_scalar_and_keeps_nat():
    crs = pd.Series(pd.to_datetime(["2024-07-15 11:00", "2024-07-15 11:00", None, "2024-03-10 06:30"])).dt.tz_localize(
        "UTC"
    )
    delay = pd.Series([780.0, -20.0, 10.0, np.nan], dtype="float32")
    result = tc.actual_utc_series(crs, delay)
    assert result.iloc[0] == pd.Timestamp("2024-07-16 00:00", tz="UTC")
    assert result.iloc[1] == pd.Timestamp("2024-07-15 10:40", tz="UTC")
    assert pd.isna(result.iloc[2]) and pd.isna(result.iloc[3])
    assert str(result.dtype) == "datetime64[ns, UTC]"


def test_actual_utc_over_dst_is_elapsed_time_not_clock_difference():
    # 01:30 EST on 2024-03-10 (06:30Z) + 120 min = 08:30Z = 04:30 EDT (the wall clock jumped an hour).
    assert tc.actual_utc(dt(2024, 3, 10, 6, 30), 120).utc == dt(2024, 3, 10, 8, 30)


def test_hhmm_minutes_series():
    minutes = tc.hhmm_minutes_series(pd.Series([900, 2400, 35, None, 2575]))
    assert minutes.iloc[:3].tolist() == [540.0, 1440.0, 35.0]
    assert pd.isna(minutes.iloc[3]) and pd.isna(minutes.iloc[4])


def test_local_clock_series_rolls_over_with_day_offset():
    day = pd.Series(pd.to_datetime(["2025-07-01", "2025-07-01", "2025-07-01", "2025-07-01"]))
    hhmm = pd.Series([35, 900, 2400, None])
    offset = pd.Series([1.0, 0.0, 0.0, 0.0])
    result = tc.local_clock_series(day, hhmm, offset)
    assert result.iloc[0] == pd.Timestamp("2025-07-02 00:35")
    assert result.iloc[1] == pd.Timestamp("2025-07-01 09:00")
    assert result.iloc[2] == pd.Timestamp("2025-07-02 00:00")  # 2400 = midnight of the next day
    assert pd.isna(result.iloc[3])
    assert pd.isna(tc.local_clock_series(day.iloc[:1], hhmm.iloc[:1], pd.Series([np.nan])).iloc[0])
