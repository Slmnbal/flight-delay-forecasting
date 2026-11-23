"""tables tests: column split, surrogate key, scheduled density, atomic Parquet writing (offline)."""

import pandas as pd
import pyarrow.parquet as pq

from flight_delay.data import layer, tables


def test_table_columns_partition_the_wide_schema():
    flights, labels, keys = set(tables.FLIGHTS_COLUMNS), set(tables.LABEL_COLUMNS), set(tables.KEY_COLUMNS)
    assert flights | labels | keys == set(layer.OUTPUT_SCHEMA)
    assert flights & labels == {"flight_uid"}
    assert flights & keys == {"flight_uid"}
    assert labels & keys == {"flight_uid"}


def test_flights_table_has_no_outcome_columns():
    outcome = {
        "ArrDelay",
        "ArrDelayMinutes",
        "ArrDel15",
        "Cancelled",
        "Diverted",
        "DepDelay",
        "DepTime",
        "ArrTime",
        "TaxiOut",
        "ActualElapsedTime",
        "dep_utc",
        "arr_utc",
        "Tail_Number",
        "CancellationCode",
    }
    assert not outcome & set(tables.FLIGHTS_COLUMNS)
    assert tables.KEY_COLUMNS == ["flight_uid", "Tail_Number"]


def test_flight_uid_is_stable_unique_and_non_negative():
    ids = pd.Series(["a", "b", "a", "a", "c"], dtype="string")
    first = tables.make_flight_uid(ids)
    again = tables.make_flight_uid(ids.copy())
    assert first.tolist() == again.tolist()  # deterministic
    assert first.is_unique  # the n-th repeat of "a" gets its own key
    assert (first >= 0).all()
    assert str(first.dtype) == "int64"
    assert (
        tables.make_flight_uid(pd.Series(["b"], dtype="string")).iloc[0] == first.iloc[1]
    )  # row order elsewhere is irrelevant


def test_scheduled_density_counts_departures_and_arrivals():
    dep_local = pd.to_datetime(["2025-07-01 09:00", "2025-07-01 09:30", "2025-07-01 23:50", "2025-07-02 00:00"])
    arr_local = pd.to_datetime(["2025-07-01 12:10", pd.NaT, "2025-07-02 00:35", "2025-07-02 02:00"])
    table, unresolved = tables.compute_scheduled_density(
        pd.Series(["ORD", "ORD", "ATL", "ORD"]),
        pd.Series(["ATL", "ZZZ", "ORD", "ATL"]),
        pd.Series(dep_local),
        pd.Series(arr_local),
    )
    assert unresolved == 1  # the flight to ZZZ has no local arrival time: not counted, not guessed
    assert list(table.columns) == tables.DENSITY_COLUMNS

    def count(airport, day, hour, column):
        rows = table[
            (table["airport"] == airport) & (table["local_date"] == pd.Timestamp(day)) & (table["local_hour"] == hour)
        ]
        return int(rows[column].sum())

    assert count("ORD", "2025-07-01", 9, "planned_departures") == 2
    assert count("ORD", "2025-07-02", 0, "planned_departures") == 1
    assert count("ATL", "2025-07-01", 12, "planned_arrivals") == 1
    assert count("ORD", "2025-07-02", 0, "planned_arrivals") == 1
    assert count("ATL", "2025-07-02", 2, "planned_arrivals") == 1
    assert int(table["planned_departures"].sum()) == 4
    assert int(table["planned_arrivals"].sum()) == 3
    assert not table["airport"].eq("ZZZ").any()


def test_write_parquet_atomic_leaves_no_tmp_file(tmp_path):
    target = tmp_path / "a" / "b" / "part-0.parquet"
    size = tables.write_parquet_atomic(pd.DataFrame({"x": [1, 2, 3]}), target)
    assert size == target.stat().st_size > 0
    assert not list(target.parent.glob("*.tmp"))
    assert pq.read_table(target).num_rows == 3
