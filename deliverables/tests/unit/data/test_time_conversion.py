"""time_conversion tests: example flights, '2400', day rollover, DST forward/back, missing/cancelled. Offline.

Expected UTC values were computed by hand (US summer time: EDT=UTC-4, CDT=-5, MDT=-6, PDT=-7;
winter: EST=-5). Note: these tests were not run by their author; a red test on the first run means both
the expected value and the code deserve a second look.
"""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from flight_delay.data import time_conversion as tc

NY, LA, CHI, PHX, HNL = (
    "America/New_York",
    "America/Los_Angeles",
    "America/Chicago",
    "America/Phoenix",
    "Pacific/Honolulu",
)


def dt(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


# ---------------------------------------------------------------- hhmm parsing
@pytest.mark.parametrize(
    "value, expected",
    [
        ("0830", 8 * 60 + 30),
        (830, 8 * 60 + 30),
        (830.0, 8 * 60 + 30),
        ("5", 5),
        (0, 0),
        ("2359", 23 * 60 + 59),
        ("2400", 1440),
        (2400, 1440),
        (2400.0, 1440),
        (None, None),
        ("", None),
        ("  ", None),
        (float("nan"), None),
    ],
)
def test_parse_hhmm(value, expected):
    assert tc.parse_hhmm(value) == expected


@pytest.mark.parametrize("value", ["2575", 2401, 1275, -5, "abc", 12.5, 2500])
def test_parse_hhmm_invalid(value):
    with pytest.raises(ValueError):
        tc.parse_hhmm(value)


# ---------------------------------------------------------------- scalar: basic flights
def test_same_day_east_to_west():
    # JFK 10:00 EDT -> LAX 13:00 PDT, same calendar day
    dep = tc.local_to_utc(date(2024, 7, 15), "1000", NY)
    arr = tc.arrival_utc(date(2024, 7, 15), "1300", LA, dep.utc)
    assert dep.utc == dt(2024, 7, 15, 14, 0)
    assert arr.utc == dt(2024, 7, 15, 20, 0) and arr.day_offset == 0


def test_arrival_past_midnight_red_eye():
    # LAX 23:00 PDT (15 Jul) -> JFK 07:00 EDT next day: arrival is FlightDate+1
    dep = tc.local_to_utc(date(2024, 7, 15), "2300", LA)
    arr = tc.arrival_utc(date(2024, 7, 15), "0700", NY, dep.utc)
    assert dep.utc == dt(2024, 7, 16, 6, 0)
    assert arr.utc == dt(2024, 7, 16, 11, 0)
    assert arr.day_offset == 1
    assert (arr.utc - dep.utc).total_seconds() / 3600 == 5.0


def test_2400_arrival_is_next_day_midnight():
    # JFK 21:30 EDT -> ATL "2400" (= 00:00 EDT the next day). Flight is 2.5 hours.
    dep = tc.local_to_utc(date(2024, 7, 15), "2130", NY)
    arr = tc.arrival_utc(date(2024, 7, 15), "2400", NY, dep.utc)
    assert dep.utc == dt(2024, 7, 16, 1, 30)
    assert arr.utc == dt(2024, 7, 16, 4, 0)
    assert (arr.utc - dep.utc).total_seconds() / 60 == 150


def test_2400_departure():
    result = tc.local_to_utc(date(2024, 7, 15), "2400", NY)
    assert result.utc == dt(2024, 7, 16, 4, 0)  # 16 Jul 00:00 EDT


def test_time_zones_arizona_hawaii():
    assert tc.local_to_utc(date(2024, 7, 15), "1200", PHX).utc == dt(2024, 7, 15, 19, 0)  # no DST, UTC-7
    assert tc.local_to_utc(date(2024, 1, 15), "1200", PHX).utc == dt(2024, 1, 15, 19, 0)
    assert tc.local_to_utc(date(2024, 7, 15), "1200", HNL).utc == dt(2024, 7, 15, 22, 0)  # UTC-10


def test_actual_time_day_rollover_nearest():
    # CRS 23:50 CDT (15 Jul) but actual departure 00:10 -> next day (20 minutes late)
    crs = tc.local_to_utc(date(2024, 7, 15), "2350", CHI)
    actual = tc.nearest_utc(date(2024, 7, 15), "0010", CHI, crs.utc)
    assert actual.utc == dt(2024, 7, 16, 5, 10)
    assert actual.day_offset == 1
    assert (actual.utc - crs.utc).total_seconds() / 60 == 20


def test_actual_time_with_delay_over_12_hours():
    # M2 fix: actual UTC = CRS UTC + delay minutes, so a 13-hour delay lands on the right day.
    crs = tc.local_to_utc(date(2024, 7, 15), "0600", CHI)  # 11:00Z
    actual = tc.actual_utc(crs.utc, 780)  # 13 hours late -> 19:00 CDT = 00:00Z on 16 Jul
    assert actual.utc == dt(2024, 7, 16, 0, 0)


# ---------------------------------------------------------------- DST
def test_dst_forward_nonexistent_time_is_flagged():
    # 2024-03-10: 02:00 EST -> 03:00 EDT. 02:30 local time does NOT exist.
    result = tc.local_to_utc(date(2024, 3, 10), "0230", NY)
    assert result.gap is True and result.ambiguous is False
    assert result.utc == dt(2024, 3, 10, 7, 30)  # policy: offset before the transition (EST) -> 03:30 EDT


def test_dst_forward_neighbouring_times_normal():
    assert tc.local_to_utc(date(2024, 3, 10), "0130", NY).utc == dt(2024, 3, 10, 6, 30)  # EST
    assert tc.local_to_utc(date(2024, 3, 10), "0300", NY).utc == dt(2024, 3, 10, 7, 0)  # EDT
    result = tc.local_to_utc(date(2024, 3, 10), "0130", NY)
    assert not result.gap and not result.ambiguous


def test_dst_forward_day_flight_duration_correct():
    # 01:30 EST departure, 04:30 EDT arrival (same zone): real duration 2 hours, local clock difference 3 hours.
    dep = tc.local_to_utc(date(2024, 3, 10), "0130", NY)
    arr = tc.arrival_utc(date(2024, 3, 10), "0430", NY, dep.utc)
    assert (arr.utc - dep.utc).total_seconds() / 3600 == 2.0


def test_dst_fall_back_ambiguous_time_is_flagged():
    # 2024-11-03: 02:00 EDT -> 01:00 EST. 01:30 happens TWICE. The first occurrence (EDT) is taken.
    result = tc.local_to_utc(date(2024, 11, 3), "0130", NY)
    assert result.ambiguous is True and result.gap is False
    assert result.utc == dt(2024, 11, 3, 5, 30)


def test_dst_fall_back_neighbouring_times_normal():
    before = tc.local_to_utc(date(2024, 11, 3), "0030", NY)
    after = tc.local_to_utc(date(2024, 11, 3), "0230", NY)
    assert before.utc == dt(2024, 11, 3, 4, 30) and not before.ambiguous  # EDT
    assert after.utc == dt(2024, 11, 3, 7, 30) and not after.ambiguous  # EST


# ---------------------------------------------------------------- missing / cancelled / invalid
def test_missing_cancelled_and_invalid():
    assert tc.local_to_utc(date(2024, 7, 15), None, NY).reason == "missing"
    assert tc.local_to_utc(date(2024, 7, 15), float("nan"), NY).reason == "missing"  # cancelled: DepTime is empty
    assert tc.local_to_utc(date(2024, 7, 15), "2575", NY).reason == "invalid"
    assert tc.local_to_utc(date(2024, 7, 15), "1000", None).reason == "tz_missing"
    assert tc.arrival_utc(date(2024, 7, 15), "1300", LA, None).reason == "missing"
    assert tc.arrival_utc(date(2024, 7, 15), None, LA, dt(2024, 7, 15, 14)).reason == "missing"


# ---------------------------------------------------------------- vectorised == scalar
def _mini_df():
    return pd.DataFrame(
        {
            "day": pd.to_datetime(
                [
                    "2024-07-15",
                    "2024-07-15",
                    "2024-07-15",
                    "2024-03-10",
                    "2024-11-03",
                    "2024-03-10",
                    "2024-07-15",
                    "2024-07-15",
                ]
            ),
            "dep": ["1000", "2300", "2130", "0130", "0130", "0230", None, "2575"],
            "arr": ["1300", "0700", "2400", "0430", "0430", "0430", "1300", "1300"],
            "tz_origin": [NY, LA, NY, NY, NY, NY, NY, NY],
            "tz_dest": [LA, NY, NY, NY, NY, NY, LA, LA],
        }
    )


def test_vectorised_matches_scalar():
    df = _mini_df()
    dep = tc.local_to_utc_series(df["day"], df["dep"], df["tz_origin"])
    arr = tc.arrival_utc_series(df["day"], df["arr"], df["tz_dest"], dep["utc"])
    for i, row in df.iterrows():
        scalar = tc.local_to_utc(row["day"].date(), row["dep"], row["tz_origin"])
        if scalar.utc is None:
            assert pd.isna(dep.loc[i, "utc"])
        else:
            assert dep.loc[i, "utc"].to_pydatetime() == scalar.utc
            assert bool(dep.loc[i, "ambiguous"]) == scalar.ambiguous
            assert bool(dep.loc[i, "gap"]) == scalar.gap
            scalar_arr = tc.arrival_utc(row["day"].date(), row["arr"], row["tz_dest"], scalar.utc)
            assert arr.loc[i, "utc"].to_pydatetime() == scalar_arr.utc, f"row {i}"
    # missing and invalid rows are flagged, not dropped
    assert len(dep) == len(df)
    assert not dep.loc[6, "has_input"] and pd.isna(dep.loc[6, "utc"])
    assert dep.loc[7, "invalid"]


def test_vectorised_known_values():
    df = _mini_df()
    dep = tc.local_to_utc_series(df["day"], df["dep"], df["tz_origin"])
    assert dep.loc[0, "utc"] == pd.Timestamp("2024-07-15 14:00", tz="UTC")
    assert dep.loc[3, "utc"] == pd.Timestamp("2024-03-10 06:30", tz="UTC")
    assert dep.loc[4, "ambiguous"] and dep.loc[5, "gap"]
