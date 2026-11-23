"""csv_io tests (new: the old suite exercised read_csv only indirectly through the size measurement)."""

import zipfile

import pytest

from flight_delay.data import csv_io

CSV = "A,B,\n1,x,\n2,y,\n"  # trailing comma, like BTS


def test_trailing_comma_does_not_create_a_column(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text(CSV, encoding="utf-8")
    df = csv_io.read_csv(path)
    assert list(df.columns) == ["A", "B"] and len(df) == 2


def test_zip_with_single_csv(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text(CSV, encoding="utf-8")
    archive = tmp_path / "t.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(path, "t.csv")
    assert len(csv_io.read_csv(archive)) == 2


def test_zip_with_two_csv_files_is_rejected(tmp_path):
    archive = tmp_path / "t.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.csv", CSV)
        zf.writestr("b.csv", CSV)
    with pytest.raises(ValueError, match="exactly 1 csv"):
        csv_io.read_csv(archive)


def test_column_selector_is_case_insensitive(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text(CSV, encoding="utf-8")
    df = csv_io.read_csv(path, usecols=csv_io.column_selector(["a"]))
    assert list(df.columns) == ["A"]
