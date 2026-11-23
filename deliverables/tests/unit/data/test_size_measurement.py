"""size_measurement tests with a tiny FAKE csv (not real BTS data). Offline."""

import json
import zipfile

import pandas as pd
import pytest

pytest.importorskip("pyarrow")

from flight_delay.data import size_measurement as sm  # noqa: E402

FAKE = (
    "Year,Month,DayofMonth,FlightDate,Reporting_Airline,Origin,Dest,CRSDepTime,DepTime,CRSArrTime,"
    "ArrTime,ArrDelay,Cancelled,Distance,Div1Airport,\n"
    "2024,7,1,2024-07-01,AA,JFK,LAX,1000,1010,1300,1320,20,0,2475,,\n"
    "2024,7,1,2024-07-01,AA,JFK,ORD,1100,,1300,,,1,740,,\n"
    "2024,7,1,2024-07-01,DL,ATL,JFK,0900,0905,1100,1055,-5,0,760,,\n"
    "2024,7,2,2024-07-02,DL,ATL,LAX,2300,2310,0100,0115,15,0,1946,,\n"
    "2024,7,2,2024-07-02,UA,ORD,SFO,1500,1500,1730,1725,-5,0,1846,,\n"
)


def _write(tmp_path):
    path = tmp_path / "fake.csv"
    path.write_text(FAKE, encoding="utf-8")
    return path


def test_measure_basic_counts_and_files(tmp_path):
    csv = _write(tmp_path)
    result = sm.measure(csv, tmp_path / "pq", keep_parquet=True)
    assert result["all_columns"]["rows"] == 5
    assert result["all_columns"]["columns"] == 15  # the trailing comma must not add a column (index_col=False)
    assert result["all_columns"]["memory_deep_bytes"] > 0
    assert result["all_columns"]["parquet_bytes"] > 0
    assert (tmp_path / "pq" / "measure_all.parquet").exists()
    assert result["subset"]["rows"] == 5
    assert "Origin" in result["subset"]["column_dtypes"]
    assert "Div1Airport" not in result["subset"]["column_dtypes"]  # not in the subset
    assert "ArrDelay" in result["all_columns"]["column_dtypes"]
    # expected columns that the CSV lacks are reported (never silently skipped)
    assert "Tail_Number" in result["subset_missing_columns"]


def test_measure_temporary_parquet_is_deleted(tmp_path):
    result = sm.measure(_write(tmp_path), tmp_path / "pq", keep_parquet=False)
    assert not list((tmp_path / "pq").glob("*.parquet"))
    assert result["all_columns"]["parquet_bytes"] > 0  # measured before deletion


def test_coverage_summary_and_missing_ratios(tmp_path):
    result = sm.measure(_write(tmp_path), tmp_path / "pq")
    coverage = result["coverage_summary"]
    assert coverage["unique_origins"] == 3
    # tie on count: code order decides: ATL (2) and JFK (2) -> ATL first
    assert coverage["top_30_origins"][0] == {"code": "ATL", "rows": 2}
    assert coverage["top_30_origins"][1] == {"code": "JFK", "rows": 2}
    assert result["missing_ratios_subset"]["DepTime"] == pytest.approx(0.2)  # cancelled flight: DepTime is empty
    assert result["missing_ratios_subset"]["Cancelled"] == 0.0


def test_second_run_gives_same_numbers(tmp_path):
    csv = _write(tmp_path)
    first = sm.measure(csv, tmp_path / "p1")
    second = sm.measure(csv, tmp_path / "p2")
    for key in ("rows", "columns", "memory_deep_bytes", "column_dtypes"):
        assert first["all_columns"][key] == second["all_columns"][key]
        assert first["subset"][key] == second["subset"][key]
    assert first["coverage_summary"] == second["coverage_summary"]


def test_zip_input(tmp_path):
    csv = _write(tmp_path)
    archive = tmp_path / "fake.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(csv, "fake.csv")
    assert sm.measure(archive, tmp_path / "pq")["all_columns"]["rows"] == 5


def test_cli_writes_json(tmp_path):
    output = tmp_path / "size-measurement.json"
    assert sm.main(["--input", str(_write(tmp_path)), "--output", str(output)]) == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["all_columns"]["rows"] == 5 and "meta" in data
    assert isinstance(pd.__version__, str)
