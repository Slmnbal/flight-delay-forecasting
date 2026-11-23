"""Layer tables tests: physical split, density from ALL flights, actual UTC from delay minutes (offline)."""

import numpy as np
import pandas as pd

from flight_delay.data import layer, tables


def _table(root, name, year=2025, month=7):
    return pd.read_parquet(layer.table_dir(root, name, year, month) / layer.PARQUET_NAME)


def _by_flight_number(frame):
    return frame.set_index("Flight_Number_Reporting_Airline")


def test_tables_are_physically_separate(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    flights, labels, keys = (_table(root, n) for n in (tables.FLIGHTS, tables.LABELS, tables.KEYS))
    assert list(flights.columns) == tables.FLIGHTS_COLUMNS
    assert list(labels.columns) == tables.LABEL_COLUMNS
    assert list(keys.columns) == tables.KEY_COLUMNS
    assert len(flights) == len(labels) == len(keys) == 4
    assert set(flights["flight_uid"]) == set(labels["flight_uid"]) == set(keys["flight_uid"])
    assert flights["flight_uid"].is_unique
    assert "ArrDelay" not in flights.columns and "Tail_Number" not in flights.columns
    assert "Tail_Number" not in labels.columns


def test_keys_table_carries_the_tail_number(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    wide = layer.read_wide_month(root, 2025, 7)
    assert set(wide["Tail_Number"]) == {"N100AA", "N200UA", "N300DL", "N600AA"}


def test_flight_uid_is_reproducible_across_runs(tmp_path, process_fake_month, empty_airports, manual_tz):
    root, _ = process_fake_month(tmp_path)
    first = _table(root, tables.FLIGHTS)["flight_uid"].tolist()
    layer.process_month(tmp_path / "raw.csv", 2025, 7, root, ["ORD", "ATL"], empty_airports, manual_tz)
    assert _table(root, tables.FLIGHTS)["flight_uid"].tolist() == first


def test_actual_utc_with_delay_over_12_hours(tmp_path, fake_ontime, process_fake_month):
    # M2: r1 departs 13 hours late. CRS 09:00 CDT = 14:00Z; actual = 03:00Z next day (22:00 CDT).
    frame = fake_ontime.copy()
    frame.loc[0, ["DepTime", "DepDelay", "DepDelayMinutes"]] = [2200.0, 780.0, 780.0]
    frame.loc[0, ["ArrTime", "ArrDelay", "ArrDelayMinutes"]] = [110.0, 780.0, 780.0]  # 12:10 EDT + 13 h = 01:10 EDT
    root, _ = process_fake_month(tmp_path, df=frame)
    r1 = _by_flight_number(layer.read_wide_month(root, 2025, 7)).loc[100]
    assert r1["crs_dep_utc"] == pd.Timestamp("2025-07-01 14:00")
    assert r1["dep_utc"] == pd.Timestamp("2025-07-02 03:00")
    assert r1["arr_utc"] == pd.Timestamp("2025-07-02 05:10")  # 16:10Z + 13 h
    assert pd.isna(r1["dep_utc_reason"]) and pd.isna(r1["arr_utc_reason"])


def test_actual_utc_is_crs_utc_plus_delay_including_early_arrival(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path, scope="origin_or_dest")  # keeps r4 (LAX->ATL, ArrDelay -5)
    rows = _by_flight_number(layer.read_wide_month(root, 2025, 7))
    assert (rows.loc[100, "dep_utc"] - rows.loc[100, "crs_dep_utc"]).total_seconds() / 60 == 15  # DepDelay 15
    assert (rows.loc[100, "arr_utc"] - rows.loc[100, "crs_arr_utc"]).total_seconds() / 60 == 20  # ArrDelay 20
    assert rows.loc[400, "arr_utc"] == pd.Timestamp("2025-07-02 17:55")  # CRS 18:00Z, 5 minutes early


def test_cancelled_and_diverted_have_nat_with_a_reason(tmp_path, fake_ontime, process_fake_month):
    frame = fake_ontime.copy()
    # r2 becomes a diverted flight: departed (DepDelay stays), no ArrDelay / ArrTime
    frame.loc[1, ["Diverted", "ArrDelay", "ArrDelayMinutes", "ArrDel15", "ArrTime"]] = [
        1.0,
        np.nan,
        np.nan,
        np.nan,
        np.nan,
    ]
    root, _ = process_fake_month(tmp_path, df=frame)
    rows = _by_flight_number(layer.read_wide_month(root, 2025, 7))
    cancelled = rows.loc[300]
    assert pd.isna(cancelled["dep_utc"]) and pd.isna(cancelled["arr_utc"])
    assert cancelled["dep_utc_reason"] == "cancelled" and cancelled["arr_utc_reason"] == "cancelled"
    diverted = rows.loc[200]
    assert diverted["dep_utc"] == pd.Timestamp("2025-07-02 03:50")  # 03:00Z + DepDelay 50
    assert pd.isna(diverted["dep_utc_reason"])
    assert pd.isna(diverted["arr_utc"]) and diverted["arr_utc_reason"] == "diverted"


def test_missing_delay_and_missing_crs_utc_reasons(tmp_path, fake_ontime, process_fake_month):
    frame = fake_ontime.copy()
    frame.loc[0, ["DepDelay", "DepDelayMinutes"]] = [np.nan, np.nan]  # r1: not cancelled but no DepDelay
    root, _ = process_fake_month(tmp_path, df=frame)  # r6 (ZZZ) has no destination time zone
    rows = _by_flight_number(layer.read_wide_month(root, 2025, 7))
    assert pd.isna(rows.loc[100, "dep_utc"]) and rows.loc[100, "dep_utc_reason"] == "delay_missing"
    assert pd.isna(rows.loc[600, "arr_utc"]) and rows.loc[600, "arr_utc_reason"] == "crs_utc_missing"


def _count(density, airport, day, hour, column):
    rows = density[
        (density["airport"] == airport) & (density["local_date"] == pd.Timestamp(day)) & (density["local_hour"] == hour)
    ]
    return int(rows[column].sum())


def test_density_is_computed_from_all_flights_before_the_scope_filter(tmp_path, process_fake_month):
    root, summary = process_fake_month(tmp_path)  # scope origin: only 4 of the 6 flights stay in flights
    assert summary["rows_layer"] == 4
    density = _table(root, tables.DENSITY)
    assert list(density.columns) == tables.DENSITY_COLUMNS
    # every one of the 6 raw flights is counted as a departure (non-target origin LAX and the cancelled flight too)
    assert int(density["planned_departures"].sum()) == 6
    assert _count(density, "LAX", "2025-07-02", 6, "planned_departures") == 1  # r4, origin is not a target
    assert _count(density, "LAX", "2025-07-02", 7, "planned_departures") == 1  # r5, neither end is a target
    assert _count(density, "ORD", "2025-07-02", 15, "planned_departures") == 1  # r3, CANCELLED, still scheduled
    # arrivals: a target destination receives flights from non-target origins as well
    assert _count(density, "ATL", "2025-07-02", 14, "planned_arrivals") == 1  # r4 from LAX
    assert _count(density, "ORD", "2025-07-02", 0, "planned_arrivals") == 1  # r2 arrives after midnight (local date +1)
    assert _count(density, "LAX", "2025-07-02", 17, "planned_arrivals") == 1  # r3 cancelled, local arrival 17:45


def test_density_arrival_without_time_zone_is_counted_not_guessed(tmp_path, process_fake_month):
    root, summary = process_fake_month(tmp_path)
    density = _table(root, tables.DENSITY)
    assert summary["density_arrivals_without_local_time"] == 1  # r6 ORD->ZZZ (ZZZ time zone unknown)
    assert int(density["planned_arrivals"].sum()) == 5
    assert not density["airport"].eq("ZZZ").any()
    assert summary["density_rows"] == len(density)


def test_density_does_not_depend_on_scope(tmp_path, process_fake_month):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    root_a, _ = process_fake_month(tmp_path / "a", scope="origin")
    root_b, _ = process_fake_month(tmp_path / "b", scope="origin_and_dest")
    pd.testing.assert_frame_equal(_table(root_a, tables.DENSITY), _table(root_b, tables.DENSITY))
