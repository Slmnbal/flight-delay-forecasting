"""metar tests: IEM CSV reading, cleaning rules, duplicates, table build (offline, tiny fake files)."""

import json

import pandas as pd
import pytest

from flight_delay.data import metar

COLUMNS = ["station", "valid", *metar.IEM_VARIABLES]


def _csv(path, rows, comment=None):
    """Write an IEM-like onlycomma file; each row is a dict, unspecified variables are 'M' (IEM's missing marker)."""
    lines = [] if comment is None else [f"#{comment}"]
    lines.append(",".join(COLUMNS))
    for row in rows:
        lines.append(",".join(str(row.get(name, "M")) for name in COLUMNS))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _clean(tmp_path, rows, mapping=None):
    raw = metar.read_iem_csv(_csv(tmp_path / "a.csv", rows, comment="debugging line"))
    return metar.clean_metar(raw, mapping or {"KORD": "ORD"})


def test_read_iem_csv_skips_comment_lines_and_requires_columns(tmp_path):
    frame = metar.read_iem_csv(_csv(tmp_path / "a.csv", [{"station": "KORD", "valid": "2025-07-01 12:00"}], "x"))
    assert len(frame) == 1 and "tmpf" in frame.columns
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected IEM columns"):
        metar.read_iem_csv(bad)


def test_missing_marker_becomes_nan_and_types_are_right(tmp_path):
    table, stats = _clean(
        tmp_path,
        [
            {
                "station": "KORD",
                "valid": "2025-07-01 12:00",
                "tmpf": "75.5",
                "sknt": "8",
                "skyc1": "BKN",
                "skyl1": "2500",
            }
        ],
    )
    row = table.iloc[0]
    assert row["tmpf"] == 75.5 and row["sknt"] == 8.0 and row["skyl1"] == 2500.0
    assert pd.isna(row["dwpf"]) and pd.isna(row["skyc2"]) and pd.isna(row["wxcodes"])
    assert row["skyc1"] == "BKN" and row["iata"] == "ORD"
    assert row["observed_utc"] == pd.Timestamp("2025-07-01 12:00")
    assert str(table["observed_utc"].dtype) == "datetime64[ns]"
    assert stats["rows_in"] == 1 and stats["rows_out"] == 1


def test_impossible_values_become_nan_and_are_counted(tmp_path):
    table, stats = _clean(
        tmp_path,
        [
            {"station": "KORD", "valid": "2025-07-01 12:00", "tmpf": "500", "relh": "101", "vsby": "10"},
            {"station": "KORD", "valid": "2025-07-01 13:00", "tmpf": "70", "relh": "50"},
        ],
    )
    assert pd.isna(table.loc[0, "tmpf"]) and pd.isna(table.loc[0, "relh"]) and table.loc[0, "vsby"] == 10.0
    assert table.loc[1, "tmpf"] == 70.0
    assert stats["out_of_range"] == {"tmpf": 1, "relh": 1}


def test_bad_time_and_unknown_station_rows_are_dropped_and_counted(tmp_path):
    table, stats = _clean(
        tmp_path,
        [
            {"station": "KORD", "valid": "not a time"},
            {"station": "XXXX", "valid": "2025-07-01 12:00"},
            {"station": "KORD", "valid": "2025-07-01 12:00"},
        ],
    )
    assert len(table) == 1
    assert stats["rows_bad_time"] == 1 and stats["rows_unknown_station"] == 1


def test_duplicate_rule_keeps_the_most_complete_row_then_the_later_one(tmp_path):
    table, stats = _clean(
        tmp_path,
        [
            {"station": "KORD", "valid": "2025-07-01 12:00", "tmpf": "70"},
            {"station": "KORD", "valid": "2025-07-01 12:00", "tmpf": "71", "dwpf": "60"},  # more complete: wins
            {"station": "KORD", "valid": "2025-07-01 13:00", "tmpf": "72"},
            {"station": "KORD", "valid": "2025-07-01 13:00", "tmpf": "73"},  # tie: the later row wins
        ],
    )
    assert stats["duplicates_removed"] == 2
    assert table["tmpf"].tolist() == [71.0, 73.0]
    assert table["observed_utc"].is_monotonic_increasing


def test_build_metar_table_writes_parquet_and_stats(tmp_path):
    raw_dir = tmp_path / "iem"
    raw_dir.mkdir()
    _csv(raw_dir / "KORD_a.csv", [{"station": "KORD", "valid": "2025-07-01 12:00", "tmpf": "70"}])
    _csv(raw_dir / "KATL_a.csv", [{"station": "KATL", "valid": "2025-07-01 12:00", "tmpf": "80"}])
    output = tmp_path / "layer" / "metar" / "metar.parquet"
    stats = metar.build_metar_table(raw_dir, {"ORD": "KORD", "ATL": "KATL"}, output)
    table = pd.read_parquet(output)
    assert sorted(table["iata"]) == ["ATL", "ORD"]
    assert stats["per_station"]["ORD"]["rows"] == 1
    assert json.loads((output.parent / "metar-stats.json").read_text(encoding="utf-8"))["rows_out"] == 2
    assert not list(output.parent.glob("*.tmp"))


def test_build_metar_table_stops_if_a_station_has_no_rows_or_no_files(tmp_path):
    raw_dir = tmp_path / "iem"
    raw_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="No IEM csv"):
        metar.build_metar_table(raw_dir, {"ORD": "KORD"}, tmp_path / "m.parquet")
    _csv(raw_dir / "KORD_a.csv", [{"station": "KORD", "valid": "2025-07-01 12:00"}])
    with pytest.raises(ValueError, match="ATL"):
        metar.build_metar_table(raw_dir, {"ORD": "KORD", "ATL": "KATL"}, tmp_path / "m.parquet")
