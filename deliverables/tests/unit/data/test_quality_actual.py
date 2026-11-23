"""Quality checks for the actual-time fix and the surrogate key (offline, tiny fake data)."""

import numpy as np
import pandas as pd
import pytest

from flight_delay.data import layer, quality

TARGETS = ["ORD", "ATL"]


def _check(report, name):
    return next(c for c in report["checks"] if c["name"] == name)


@pytest.fixture
def month(tmp_path, fake_ontime, process_fake_month):
    clean = fake_ontime.copy()
    # r1 departs 13 hours late: the old nearest-day rule put this on the wrong day (M2)
    clean.loc[0, ["DepTime", "DepDelay", "DepDelayMinutes"]] = [2200.0, 780.0, 780.0]
    clean.loc[0, ["ArrTime", "ArrDelay", "ArrDelayMinutes"]] = [110.0, 780.0, 780.0]
    clean = clean.query("Dest != 'ZZZ'")
    root, summary = process_fake_month(tmp_path, df=clean)
    return layer.read_wide_month(root, 2025, 7), summary


def test_actual_time_checks_pass_for_a_delay_over_12_hours(month):
    df, summary = month
    report = quality.check_month(df, 2025, 7, TARGETS, "origin", summary)
    assert _check(report, "utc_actual_departure_mismatch")["status"] == "passed"
    assert _check(report, "utc_actual_arrival_mismatch")["status"] == "passed"
    assert _check(report, "actual_local_time_mismatch")["status"] == "passed"
    assert _check(report, "actual_local_time_mismatch")["value"]["violations"] == 0
    assert report["status"] == "passed", [c for c in report["checks"] if c["status"] not in ("passed", "skipped")]


def test_local_clock_check_catches_a_wrong_time_zone_or_deptime(month):
    df, _ = month
    wrong = df.copy()
    wrong.loc[wrong["Flight_Number_Reporting_Airline"] == 200, "DepTime"] = 2150  # BTS says 21:50, UTC says 23:50
    check = _check(quality.check_month(wrong, 2025, 7, TARGETS, "origin"), "actual_local_time_mismatch")
    assert check["status"] == "warning"
    assert check["value"]["departure"] == 1 and check["value"]["arrival"] == 0


def test_actual_departure_check_catches_a_shifted_actual_utc(month):
    df, _ = month
    shifted = df.copy()
    shifted["dep_utc"] = shifted["dep_utc"] + pd.Timedelta(days=1)
    assert _check(quality.check_month(shifted, 2025, 7, TARGETS, "origin"), "utc_actual_departure_mismatch")[
        "status"
    ] in (
        "warning",
        "critical",
    )


def test_duplicate_flight_uid_is_critical(month):
    df, _ = month
    duplicated = df.copy()
    duplicated.loc[1, "flight_uid"] = duplicated.loc[0, "flight_uid"]
    assert (
        _check(quality.check_month(duplicated, 2025, 7, TARGETS, "origin"), "duplicate_flight_uid")["status"]
        == "critical"
    )
    assert _check(quality.check_month(df, 2025, 7, TARGETS, "origin"), "duplicate_flight_uid")["status"] == "passed"


def test_content_hash_does_not_depend_on_the_actual_time_columns(month):
    df, _ = month
    changed = df.copy()
    changed["dep_utc"] = pd.NaT
    changed["flight_uid"] = np.arange(len(changed))
    assert quality.content_hash(df) == quality.content_hash(changed)
