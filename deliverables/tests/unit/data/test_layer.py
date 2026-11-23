"""layer tests (offline, tiny fake CSV). Fake data and factories live in conftest.py."""

import json
import zipfile

import pandas as pd
import pyarrow.parquet as pq
import pyarrow.types as pt
import pytest

from flight_delay.data import layer

TARGETS = ["ORD", "ATL"]


def _read(root, year=2025, month=7):
    """The wide month frame (flights + flight_labels + flight_keys joined on flight_uid)."""
    return layer.read_wide_month(root, year, month)


def test_read_targets_comments_and_duplicates(tmp_path):
    path = tmp_path / "t.txt"
    path.write_text("ord\n# comment\nATL  # trailing comment\n\nORD\n", encoding="utf-8")
    assert layer.read_targets(path) == ["ORD", "ATL"]


def test_read_targets_invalid_code(tmp_path):
    path = tmp_path / "t.txt"
    path.write_text("ORD\nCHICAGO\n", encoding="utf-8")
    with pytest.raises(ValueError):
        layer.read_targets(path)


def test_partition_path_and_summary(tmp_path, process_fake_month):
    root, summary = process_fake_month(tmp_path)
    for table in ("flights", "flight_labels", "flight_keys", "scheduled_density"):
        assert (root / table / "year=2025" / "month=07" / "part-0.parquet").is_file()
        assert not list((root / table / "year=2025" / "month=07").glob("*.tmp"))
    assert (root / "flights" / "year=2025" / "month=07" / "summary.json").is_file()
    assert layer.is_month_processed(root, 2025, 7)
    assert not layer.is_month_processed(root, 2025, 8)
    assert summary["rows_raw"] == 6
    written = json.loads((root / "flights" / "year=2025" / "month=07" / "summary.json").read_text(encoding="utf-8"))
    assert written["rows_layer"] == summary["rows_layer"]


def test_scope_origin_default(tmp_path, process_fake_month):
    root, summary = process_fake_month(tmp_path)
    df = _read(root)
    assert len(df) == 4  # r1, r2, r3, r6 (Origin is a target)
    assert set(df["Origin"]) == {"ORD", "ATL"}
    assert df["target_origin"].all()
    assert summary["rows_layer"] == 4


def test_scope_origin_or_dest(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path, scope="origin_or_dest")
    df = _read(root)
    assert len(df) == 5  # + r4 (LAX->ATL)
    assert set(df.loc[~df["target_origin"], "Origin"]) == {"LAX"}
    assert df.loc[~df["target_origin"], "target_dest"].all()


def test_scope_origin_and_dest(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path, scope="origin_and_dest")
    assert len(_read(root)) == 2  # r1, r2


def test_invalid_scope(tmp_path, write_ontime_csv, empty_airports, manual_tz):
    csv = write_ontime_csv(tmp_path / "raw.csv")
    with pytest.raises(ValueError):
        layer.process_month(csv, 2025, 7, tmp_path / "k", TARGETS, empty_airports, manual_tz, "everything")


def test_zero_rows_error(tmp_path, write_ontime_csv, empty_airports, manual_tz):
    csv = write_ontime_csv(tmp_path / "raw.csv")
    with pytest.raises(ValueError, match="0 rows"):
        layer.process_month(csv, 2025, 7, tmp_path / "k", ["SEA"], empty_airports, manual_tz)


def test_required_column_missing(tmp_path, fake_ontime, write_ontime_csv, empty_airports, manual_tz):
    csv = write_ontime_csv(tmp_path / "raw.csv", fake_ontime.drop(columns=["Tail_Number"]))
    with pytest.raises(ValueError, match="Tail_Number"):
        layer.process_month(csv, 2025, 7, tmp_path / "k", TARGETS, empty_airports, manual_tz)


def test_optional_column_missing_is_filled(tmp_path, fake_ontime, process_fake_month):
    root, summary = process_fake_month(tmp_path, df=fake_ontime.drop(columns=["WeatherDelay"]))
    assert summary["missing_optional_columns"] == ["WeatherDelay"]
    assert _read(root)["WeatherDelay"].isna().all()


def test_column_names_are_case_insensitive(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path, upper_case_columns=True)
    assert "FlightDate" in _read(root).columns


def test_schema_order_and_extra_columns_dropped(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    df = _read(root)
    assert list(df.columns) == list(layer.OUTPUT_SCHEMA)
    assert "OriginCityName" not in df.columns


def test_parquet_types(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    schema = pq.read_schema(layer.month_dir(root, 2025, 7) / layer.PARQUET_NAME)  # flights
    label_schema = pq.read_schema(layer.table_dir(root, "flight_labels", 2025, 7) / layer.PARQUET_NAME)
    assert pt.is_integer(schema.field("CRSDepTime").type)
    assert pt.is_integer(schema.field("flight_uid").type)
    assert pt.is_floating(label_schema.field("ArrDelay").type)
    assert pt.is_timestamp(label_schema.field("dep_utc").type)
    assert pt.is_timestamp(schema.field("FlightDate").type)
    assert pt.is_timestamp(schema.field("crs_dep_utc").type)
    assert schema.field("crs_dep_utc").type.tz is None  # naive-UTC contract
    assert pt.is_boolean(schema.field("target_origin").type)
    assert pt.is_string(schema.field("Origin").type) or pt.is_large_string(schema.field("Origin").type)


def test_flight_id(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    ids = set(_read(root)["flight_id"])
    assert "20250701_AA_100_ORD_ATL_0900" in ids
    assert "20250701_UA_200_ATL_ORD_2300" in ids


def test_utc_values(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    df = _read(root).set_index("Flight_Number_Reporting_Airline")
    r1 = df.loc[100]
    assert r1["crs_dep_utc"] == pd.Timestamp("2025-07-01 14:00")
    assert r1["crs_arr_utc"] == pd.Timestamp("2025-07-01 16:10")
    assert r1["dep_utc"] == pd.Timestamp("2025-07-01 14:15")
    assert r1["arr_utc"] == pd.Timestamp("2025-07-01 16:30")
    r2 = df.loc[200]  # arrival past midnight
    assert r2["crs_dep_utc"] == pd.Timestamp("2025-07-02 03:00")
    assert r2["crs_arr_utc"] == pd.Timestamp("2025-07-02 05:35")
    assert r2["arr_utc"] == pd.Timestamp("2025-07-02 06:25")
    assert r2["crs_arr_day_offset"] == 1


def test_cancelled_row_is_kept_and_actual_utc_is_empty(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    r3 = _read(root).set_index("Flight_Number_Reporting_Airline").loc[300]
    assert r3["Cancelled"] == 1
    assert pd.isna(r3["dep_utc"]) and pd.isna(r3["arr_utc"])
    assert r3["crs_dep_utc"] == pd.Timestamp("2025-07-02 20:00")
    assert r3["crs_arr_utc"] == pd.Timestamp("2025-07-03 00:45")


def test_missing_time_zone_is_not_invented(tmp_path, process_fake_month):
    root, summary = process_fake_month(tmp_path)
    r6 = _read(root).set_index("Flight_Number_Reporting_Airline").loc[600]
    assert pd.isna(r6["crs_arr_utc"])
    assert not pd.isna(r6["crs_dep_utc"])
    assert bool(r6["utc_tz_missing"])
    assert summary["tz_missing_airports"] == ["ZZZ"]


def test_dtypes(tmp_path, process_fake_month):
    root, _ = process_fake_month(tmp_path)
    df = _read(root)
    assert str(df["CRSDepTime"].dtype) == "Int16"
    assert str(df["Cancelled"].dtype) == "Int8"
    assert str(df["ArrDelay"].dtype) == "float32"


def test_fractional_integer_column_is_an_error(tmp_path, fake_ontime, write_ontime_csv, empty_airports, manual_tz):
    df = fake_ontime
    df["CRSDepTime"] = df["CRSDepTime"].astype(float)
    df.loc[0, "CRSDepTime"] = 900.5
    csv = write_ontime_csv(tmp_path / "raw.csv", df)
    with pytest.raises(ValueError, match="CRSDepTime"):
        layer.process_month(csv, 2025, 7, tmp_path / "k", TARGETS, empty_airports, manual_tz)


def test_rows_outside_month_are_counted_not_dropped(tmp_path, process_fake_month):
    _, summary = process_fake_month(tmp_path, year=2025, month=8)  # file is July, parameter is August
    assert summary["rows_outside_month"] == summary["rows_layer"] == 4


def test_zip_input(tmp_path, write_ontime_csv, empty_airports, manual_tz):
    csv = write_ontime_csv(tmp_path / "raw.csv")
    archive = tmp_path / "ontime_2025_07.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(csv, "raw.csv")
    summary = layer.process_month(archive, 2025, 7, tmp_path / "layer", TARGETS, empty_airports, manual_tz)
    assert summary["rows_layer"] == 4


def test_second_run_gives_same_result(tmp_path, process_fake_month, empty_airports, manual_tz):
    root, first = process_fake_month(tmp_path)
    a = _read(root)
    second = layer.process_month(tmp_path / "raw.csv", 2025, 7, root, TARGETS, empty_airports, manual_tz)
    b = _read(root)
    pd.testing.assert_frame_equal(a, b)
    assert first["rows_layer"] == second["rows_layer"]
    assert first["targets_sha256"] == second["targets_sha256"]
