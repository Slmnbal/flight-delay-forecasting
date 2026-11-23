"""weather_join tests: leak-free as-of join, oracle variant, row-level timing test (offline, small fakes)."""

import numpy as np
import pandas as pd
import pytest

from flight_delay.data import layer, metar, weather_join

STATION_MAP = {"ORD": "KORD", "ATL": "KATL"}


def make_metar(rows):
    """rows: (station, 'YYYY-MM-DD HH:MM', tmpf). Other variables stay missing."""
    frame = pd.DataFrame(
        {
            "station": [r[0] for r in rows],
            "iata": [{"KORD": "ORD", "KATL": "ATL"}[r[0]] for r in rows],
            "observed_utc": pd.to_datetime([r[1] for r in rows]).astype("datetime64[ns]"),
        }
    )
    for name in metar.IEM_NUMERIC_VARIABLES:
        frame[name] = np.nan
    for name in metar.IEM_TEXT_VARIABLES:
        frame[name] = pd.Series(pd.NA, index=frame.index, dtype="string")
    frame["tmpf"] = [r[2] for r in rows]
    return frame.sort_values(["station", "observed_utc"]).reset_index(drop=True)


def make_flights(rows):
    """rows: (flight_uid, origin, dest, target_dest, crs_dep_utc, crs_arr_utc)."""
    return pd.DataFrame(
        {
            "flight_uid": [r[0] for r in rows],
            "Origin": [r[1] for r in rows],
            "Dest": [r[2] for r in rows],
            "target_dest": [r[3] for r in rows],
            "crs_dep_utc": pd.to_datetime([r[4] for r in rows]).astype("datetime64[ns]"),
            "crs_arr_utc": pd.to_datetime([r[5] for r in rows]).astype("datetime64[ns]"),
        }
    )


def test_horizon_table_name():
    assert weather_join.horizon_table_name(2.0) == "weather_t120m"
    assert weather_join.horizon_table_name(6) == "weather_t360m"


def test_last_observation_at_or_before_the_cutoff_is_used():
    # departure 14:00Z, T = 2 h, margin 10 min -> cutoff 11:50Z
    metar_table = make_metar(
        [
            ("KORD", "2025-07-01 07:00", 1.0),
            ("KORD", "2025-07-01 11:00", 2.0),
            ("KORD", "2025-07-01 11:50", 3.0),  # exactly at the cutoff: allowed
            ("KORD", "2025-07-01 11:51", 4.0),  # one minute too late: must NOT be used
            ("KORD", "2025-07-01 13:55", 5.0),  # information from the future of the forecast time
        ]
    )
    flights = make_flights([(1, "ORD", "ZZZ", False, "2025-07-01 14:00", "2025-07-01 16:00")])
    joined = weather_join.join_weather(flights, metar_table, STATION_MAP)
    row = joined.iloc[0]
    assert row["origin_tmpf"] == 3.0
    assert row["origin_obs_utc"] == pd.Timestamp("2025-07-01 11:50")
    assert row["origin_target_utc"] == pd.Timestamp("2025-07-01 11:50")
    assert row["origin_obs_age_min"] == 0.0
    assert bool(row["is_oracle"]) is False


def test_observation_older_than_three_hours_is_missing_not_filled():
    metar_table = make_metar([("KORD", "2025-07-01 08:00", 1.0)])  # cutoff 11:50 -> 3h50m old
    flights = make_flights([(1, "ORD", "ZZZ", False, "2025-07-01 14:00", "2025-07-01 16:00")])
    row = weather_join.join_weather(flights, metar_table, STATION_MAP).iloc[0]
    assert pd.isna(row["origin_obs_utc"]) and pd.isna(row["origin_tmpf"]) and pd.isna(row["origin_obs_age_min"])
    # exactly 3 hours old is still accepted (tolerance is inclusive)
    edge = make_metar([("KORD", "2025-07-01 08:50", 1.0)])
    assert weather_join.join_weather(flights, edge, STATION_MAP).iloc[0]["origin_tmpf"] == 1.0


def test_destination_weather_uses_the_same_cutoff_and_only_for_targets():
    metar_table = make_metar(
        [
            ("KORD", "2025-07-01 11:30", 10.0),
            ("KATL", "2025-07-01 11:20", 20.0),  # before the cutoff: used
            ("KATL", "2025-07-01 15:55", 21.0),  # near the ARRIVAL time: must not be used by the T-table
        ]
    )
    flights = make_flights(
        [
            (1, "ORD", "ATL", True, "2025-07-01 14:00", "2025-07-01 16:10"),
            (2, "ORD", "LAX", False, "2025-07-01 14:00", "2025-07-01 18:00"),  # destination is not a target
        ]
    )
    joined = weather_join.join_weather(flights, metar_table, STATION_MAP).set_index("flight_uid")
    assert joined.loc[1, "dest_tmpf"] == 20.0
    assert joined.loc[1, "dest_target_utc"] == joined.loc[1, "origin_target_utc"]
    assert pd.isna(joined.loc[2, "dest_obs_utc"]) and pd.isna(joined.loc[2, "dest_tmpf"])


def test_oracle_uses_departure_and_arrival_times_and_is_labelled():
    metar_table = make_metar(
        [
            ("KORD", "2025-07-01 13:55", 5.0),
            ("KORD", "2025-07-01 14:05", 6.0),  # after departure: not allowed even for the oracle
            ("KATL", "2025-07-01 16:05", 7.0),
            ("KATL", "2025-07-01 16:15", 8.0),  # after scheduled arrival
        ]
    )
    flights = make_flights([(1, "ORD", "ATL", True, "2025-07-01 14:00", "2025-07-01 16:10")])
    row = weather_join.join_weather(flights, metar_table, STATION_MAP, oracle=True).iloc[0]
    assert row["origin_tmpf"] == 5.0 and row["dest_tmpf"] == 7.0
    assert bool(row["is_oracle"]) is True
    assert row["origin_target_utc"] == pd.Timestamp("2025-07-01 14:00")
    assert row["dest_target_utc"] == pd.Timestamp("2025-07-01 16:10")


def test_flights_without_time_or_station_get_empty_weather():
    metar_table = make_metar([("KORD", "2025-07-01 11:00", 1.0)])
    flights = make_flights(
        [
            (1, "ORD", "ZZZ", False, "2025-07-01 14:00", "2025-07-01 16:00"),
            (2, "SEA", "ZZZ", False, "2025-07-01 14:00", "2025-07-01 16:00"),
        ]
    )
    flights.loc[0, "crs_dep_utc"] = pd.NaT
    joined = weather_join.join_weather(flights, metar_table, STATION_MAP)
    assert joined["origin_obs_utc"].isna().all()  # row 1: no cutoff time; row 2: station not in the map
    assert len(joined) == 2


def test_row_level_timing_against_a_brute_force_search():
    rng = np.random.default_rng(42)
    base = pd.Timestamp("2025-07-01")
    rows = []
    for station in ("KORD", "KATL"):
        minutes = np.sort(rng.integers(0, 3 * 24 * 60, size=150))
        rows += [(station, str(base + pd.Timedelta(minutes=int(m))), float(i)) for i, m in enumerate(minutes)]
    metar_table = make_metar(rows)
    departures = base + pd.to_timedelta(rng.integers(0, 3 * 24 * 60, size=120), unit="m")
    flights = make_flights(
        [
            (i, "ORD" if i % 2 else "ATL", "ATL" if i % 3 else "ORD", True, str(d), str(d + pd.Timedelta(hours=2)))
            for i, d in enumerate(departures)
        ]
    )
    options = {"horizon_hours": 2.0, "margin_minutes": 10.0, "lookback_hours": 3.0}
    joined = weather_join.join_weather(flights, metar_table, STATION_MAP, **options)
    weather_join.check_join_timing(joined, flights, **options)  # raises on any violation
    cutoff = flights["crs_dep_utc"] - pd.Timedelta(minutes=130)
    for side, column in (("origin", "Origin"), ("dest", "Dest")):
        for i in range(len(flights)):
            station = STATION_MAP[flights.loc[i, column]]
            observed = metar_table[(metar_table["station"] == station) & (metar_table["observed_utc"] <= cutoff[i])]
            observed = observed[observed["observed_utc"] >= cutoff[i] - pd.Timedelta(hours=3)]
            got = joined.loc[i, f"{side}_obs_utc"]
            if observed.empty:
                assert pd.isna(got)
            else:
                assert got == observed["observed_utc"].max()
                assert got <= joined.loc[i, f"{side}_target_utc"]


def test_timing_check_detects_a_leak():
    metar_table = make_metar([("KORD", "2025-07-01 11:00", 1.0)])
    flights = make_flights([(1, "ORD", "ZZZ", False, "2025-07-01 14:00", "2025-07-01 16:00")])
    joined = weather_join.join_weather(flights, metar_table, STATION_MAP)
    weather_join.check_join_timing(joined, flights)
    leaked = joined.copy()
    leaked.loc[0, "origin_obs_utc"] = pd.Timestamp("2025-07-01 12:30")  # after the 11:50 cutoff
    with pytest.raises(weather_join.TimingError, match="newer"):
        weather_join.check_join_timing(leaked, flights)
    widened = joined.copy()
    widened.loc[0, "origin_target_utc"] = pd.Timestamp("2025-07-01 13:00")  # cutoff pushed later than dep - T - margin
    with pytest.raises(weather_join.TimingError, match="later than"):
        weather_join.check_join_timing(widened, flights)
    # the same table is not a valid oracle table (targets are not the scheduled times)
    with pytest.raises(weather_join.TimingError, match="oracle"):
        weather_join.check_join_timing(joined, flights, oracle=True)


def test_build_weather_tables_end_to_end(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)  # fake flights: ORD/ATL origins on 2025-07-01 .. 07-03
    metar_path = tmp_path / "metar.parquet"
    rows = [
        (station, str(pd.Timestamp("2025-07-01") + pd.Timedelta(minutes=30 * k)), float(k))
        for station in ("KORD", "KATL")
        for k in range(0, 200)  # every 30 minutes for more than 4 days: covers the last fake departure (07-03)
    ]
    make_metar(rows).to_parquet(metar_path)
    summary = weather_join.build_weather_tables(root, metar_path, STATION_MAP)
    assert summary["table"] == "weather_t120m" and summary["months"][0]["rows"] == 4
    flights = pd.read_parquet(layer.month_dir(root, 2025, 7) / layer.PARQUET_NAME)
    t_table = pd.read_parquet(layer.table_dir(root, "weather_t120m", 2025, 7) / layer.PARQUET_NAME)
    oracle = pd.read_parquet(layer.table_dir(root, "weather_oracle", 2025, 7) / layer.PARQUET_NAME)
    assert len(t_table) == len(oracle) == len(flights)
    assert not t_table["is_oracle"].any() and oracle["is_oracle"].all()
    weather_join.check_join_timing(t_table, flights)  # row-level test on what was written
    weather_join.check_join_timing(oracle, flights, oracle=True)
    assert t_table["origin_obs_utc"].notna().all()  # 30-minute observations: always something within 3 h


def test_build_weather_tables_only_one_month(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    metar_path = tmp_path / "metar.parquet"
    rows = [
        (station, str(pd.Timestamp("2025-07-01") + pd.Timedelta(minutes=30 * k)), float(k))
        for station in ("KORD", "KATL")
        for k in range(0, 200)
    ]
    make_metar(rows).to_parquet(metar_path)
    summary = weather_join.build_weather_tables(root, metar_path, STATION_MAP, only=(2025, 7))
    assert [(m["year"], m["month"]) for m in summary["months"]] == [(2025, 7)]
    with pytest.raises(FileNotFoundError, match="2025-08"):
        weather_join.build_weather_tables(root, metar_path, STATION_MAP, only=(2025, 8))
