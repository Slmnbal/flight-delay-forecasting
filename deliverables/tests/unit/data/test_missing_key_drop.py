"""Missing-key drop (layer rule 9) and the quality check ``dropped_missing_key_rows`` (offline, tiny fake data)."""

import json

import numpy as np
import pandas as pd
import pytest

from flight_delay.data import layer, quality

TARGETS = ["ORD", "ATL"]
TABLES = ("flights", "flight_labels", "flight_keys")


def _broken_frame(fake_ontime: pd.DataFrame) -> pd.DataFrame:
    """r2 (ATL->ORD): empty flight number; r6 (ORD->ZZZ): empty airline AND empty Diverted. In scope: r1, r2, r3, r6."""
    frame = fake_ontime.copy()
    frame.loc[1, "Flight_Number_Reporting_Airline"] = np.nan
    frame.loc[5, "Reporting_Airline"] = np.nan
    frame.loc[5, "Diverted"] = np.nan
    return frame


def _sub(tmp_path, name):
    """A fresh sub-folder (the CSV factory does not create parent folders)."""
    folder = tmp_path / name
    folder.mkdir()
    return folder


def _status(report, name):
    return next(c["status"] for c in report["checks"] if c["name"] == name)


def _check(report, name):
    return next(c for c in report["checks"] if c["name"] == name)


def test_key_list_has_a_single_source():
    assert quality.KEY_FIELDS_FILLED is layer.KEY_FIELDS_FILLED


def test_rows_with_empty_key_are_dropped_and_counted(tmp_path, fake_ontime, process_fake_month):
    root, summary = process_fake_month(tmp_path, df=_broken_frame(fake_ontime))
    assert summary["rows_raw"] == 6
    assert summary["rows_dropped_missing_key"] == 2
    by_field = summary["dropped_missing_key_by_field"]
    assert set(by_field) == set(layer.KEY_FIELDS_FILLED)
    assert by_field["Flight_Number_Reporting_Airline"] == 1
    assert by_field["Reporting_Airline"] == 1
    assert by_field["Diverted"] == 1
    assert sum(1 for v in by_field.values() if v) == 3
    assert summary["rows_layer"] == 2  # r1 and r3 remain (in scope = 4, minus 2 dropped)
    written = json.loads((layer.month_dir(root, 2025, 7) / layer.SUMMARY_NAME).read_text(encoding="utf-8"))
    assert written["rows_dropped_missing_key"] == 2
    assert written["rows_layer"] == 2


def test_no_empty_key_remains_and_tables_stay_consistent(tmp_path, fake_ontime, process_fake_month):
    root, summary = process_fake_month(tmp_path, df=_broken_frame(fake_ontime))
    wide = layer.read_wide_month(root, 2025, 7)  # one-to-one merge on flight_uid: fails if tables disagree
    assert len(wide) == summary["rows_layer"] == 2
    assert not wide[layer.KEY_FIELDS_FILLED].isna().any().any()
    uids = {}
    for table in TABLES:
        frame = pd.read_parquet(layer.table_dir(root, table, 2025, 7) / layer.PARQUET_NAME)
        assert len(frame) == 2
        uids[table] = set(frame["flight_uid"])
    assert uids["flights"] == uids["flight_labels"] == uids["flight_keys"]
    assert set(wide["Flight_Number_Reporting_Airline"]) == {100, 300}


def test_full_rows_are_unchanged_by_the_drop(tmp_path, fake_ontime, process_fake_month):
    """Rows that are complete must be identical to a run in which the other rows are not broken."""
    clean_root, clean_summary = process_fake_month(_sub(tmp_path, "clean"), df=fake_ontime)
    broken_root, _ = process_fake_month(_sub(tmp_path, "broken"), df=_broken_frame(fake_ontime))
    clean = layer.read_wide_month(clean_root, 2025, 7)
    broken = layer.read_wide_month(broken_root, 2025, 7)
    assert clean_summary["rows_dropped_missing_key"] == 0
    assert set(clean_summary["dropped_missing_key_by_field"].values()) == {0}
    survivors = clean[clean["flight_id"].isin(broken["flight_id"])].reset_index(drop=True)
    assert len(survivors) == len(broken) == 2
    pd.testing.assert_frame_equal(survivors, broken.reset_index(drop=True), check_dtype=True)


def test_scheduled_density_is_not_affected(tmp_path, fake_ontime, process_fake_month):
    clean_root, _ = process_fake_month(_sub(tmp_path, "clean"), df=fake_ontime)
    broken_root, _ = process_fake_month(_sub(tmp_path, "broken"), df=_broken_frame(fake_ontime))
    path = "scheduled_density/year=2025/month=07/part-0.parquet"
    pd.testing.assert_frame_equal(pd.read_parquet(clean_root / path), pd.read_parquet(broken_root / path))


def test_all_rows_dropped_is_an_error(tmp_path, fake_ontime, write_ontime_csv, empty_airports, manual_tz):
    frame = fake_ontime.copy()
    frame["Reporting_Airline"] = np.nan
    csv = write_ontime_csv(tmp_path / "raw.csv", frame)
    with pytest.raises(ValueError, match="empty key field"):
        layer.process_month(csv, 2025, 7, tmp_path / "k", TARGETS, empty_airports, manual_tz)


def test_rerun_gives_same_result(tmp_path, fake_ontime, process_fake_month):
    _, first = process_fake_month(_sub(tmp_path, "a"), df=_broken_frame(fake_ontime))
    _, second = process_fake_month(_sub(tmp_path, "b"), df=_broken_frame(fake_ontime))
    assert first["rows_dropped_missing_key"] == second["rows_dropped_missing_key"] == 2
    assert first["rows_layer"] == second["rows_layer"]


# ---- quality check -----------------------------------------------------------------------------------------------


@pytest.fixture
def clean_frame(tmp_path, fake_ontime, process_fake_month):
    clean = fake_ontime.query("Dest != 'ZZZ'")
    root, summary = process_fake_month(tmp_path, df=clean, name="raw_2025_7.csv")
    return layer.read_wide_month(root, 2025, 7), summary  # 3 rows


def test_quality_passed_when_nothing_dropped(clean_frame):
    frame, summary = clean_frame
    assert summary["rows_dropped_missing_key"] == 0
    report = quality.check_month(frame, 2025, 7, TARGETS, "origin", summary)
    check = _check(report, "dropped_missing_key_rows")
    assert check["status"] == "passed"
    assert check["value"]["violations"] == 0
    assert report["status"] == "passed"


def test_quality_warning_when_few_rows_dropped(clean_frame):
    frame, summary = clean_frame
    summary = {**summary, "rows_dropped_missing_key": 1, "dropped_missing_key_by_field": {"Origin": 1}}
    # the 3-row frame would give 1/4 = 0.25 (critical); a larger frame is needed to land under the 0.001 bound
    big = pd.concat([frame] * 400, ignore_index=True)  # 1200 rows -> 1/1201 = 0.00083 <= 0.001
    report = quality.check_month(big, 2025, 7, TARGETS, "origin", {**summary, "rows_layer": len(big)})
    check = _check(report, "dropped_missing_key_rows")
    assert check["status"] == "warning"
    assert check["value"]["violations"] == 1
    assert check["value"]["per_field"] == {"Origin": 1}
    assert 0 < check["value"]["ratio"] <= quality.THRESHOLDS["dropped_missing_key_rows"][1]


def test_quality_critical_above_threshold(clean_frame):
    frame, summary = clean_frame
    summary = {**summary, "rows_dropped_missing_key": 1}
    report = quality.check_month(frame, 2025, 7, TARGETS, "origin", summary)  # 1 / 4 = 0.25 > 0.001
    assert _status(report, "dropped_missing_key_rows") == "critical"
    assert report["status"] == "critical"


def test_quality_unknown_when_record_has_no_field(clean_frame):
    frame, summary = clean_frame
    old_summary = {k: v for k, v in summary.items() if not k.startswith(("rows_dropped", "dropped_"))}
    report = quality.check_month(frame, 2025, 7, TARGETS, "origin", old_summary)
    check = _check(report, "dropped_missing_key_rows")
    assert check["status"] == "skipped"  # NOT "passed"
    assert check["value"]["unknown"] is True
    no_summary = quality.check_month(frame, 2025, 7, TARGETS, "origin", None)
    assert _check(no_summary, "dropped_missing_key_rows")["value"]["unknown"] is True


def test_key_field_missing_stays_critical(clean_frame):
    frame, summary = clean_frame
    frame = frame.copy()
    frame["Flight_Number_Reporting_Airline"] = frame["Flight_Number_Reporting_Airline"].astype("Int32")
    frame.loc[0, "Flight_Number_Reporting_Airline"] = pd.NA
    report = quality.check_month(frame, 2025, 7, TARGETS, "origin", summary)
    assert quality.THRESHOLDS["key_field_missing"] == (None, 0.0)
    assert _status(report, "key_field_missing") == "critical"


def test_markdown_lists_unknown_months(clean_frame):
    frame, summary = clean_frame
    old_summary = {k: v for k, v in summary.items() if not k.startswith(("rows_dropped", "dropped_"))}
    month = quality.check_month(frame, 2025, 7, TARGETS, "origin", old_summary)
    report = {
        "meta": {"scope": "origin", "pandas": pd.__version__},
        "overall_status": month["status"],
        "months": [month],
        "period_checks": [],
    }
    assert "UNKNOWN" in quality.render_markdown(report)
    assert "2025-07" in quality.render_markdown(report)
