"""quality tests (offline, tiny fake data)."""

import json

import pandas as pd
import pytest

from flight_delay.data import layer, quality

TARGETS = ["ORD", "ATL"]


@pytest.fixture
def clean_month(tmp_path, fake_ontime, process_fake_month):
    """Process fake data without the unknown-time-zone flight; return (root, layer DataFrame, summary)."""
    clean = fake_ontime.query("Dest != 'ZZZ'")  # clean scenario: no missing time zones
    root, summary = process_fake_month(tmp_path, df=clean, name="raw_2025_7.csv")
    frame = layer.read_wide_month(root, 2025, 7)
    return root, frame, summary


def _status(report, name):
    return next(c["status"] for c in report["checks"] if c["name"] == name)


def _not_passed(report):
    return [(c["name"], c["status"], c["value"]) for c in report["checks"] if c["status"] not in ("passed", "skipped")]


def test_clean_data_passes(clean_month):
    _, df, summary = clean_month
    report = quality.check_month(df, 2025, 7, TARGETS, "origin", summary)
    assert report["status"] == "passed", _not_passed(report)
    assert report["rows"] == 3


def test_every_check_has_a_threshold(clean_month):
    _, df, summary = clean_month
    report = quality.check_month(df, 2025, 7, TARGETS, "origin", summary)
    for check in report["checks"]:
        if check["status"] != "skipped" and check["name"] in quality.THRESHOLDS:
            assert check["threshold"] is not None


def test_duplicate_is_caught(clean_month):
    _, df, _ = clean_month
    doubled = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    report = quality.check_month(doubled, 2025, 7, TARGETS, "origin")
    assert _status(report, "duplicate_flight_key") == "critical"  # 1/4 > 1%
    check = next(x for x in report["checks"] if x["name"] == "duplicate_flight_key")
    assert check["value"]["violations"] == 1


def test_date_outside_month_is_critical(clean_month):
    _, df, _ = clean_month
    report = quality.check_month(df, 2025, 8, TARGETS, "origin")
    assert _status(report, "date_outside_month") == "critical"
    assert report["status"] == "critical"


def test_invalid_flag_is_critical(clean_month):
    _, df, _ = clean_month
    df = df.copy()
    df["Cancelled"] = df["Cancelled"].astype("Int8")
    df.loc[0, "Cancelled"] = 2
    report = quality.check_month(df, 2025, 7, TARGETS, "origin")
    assert _status(report, "invalid_flag_value") == "critical"


def test_negative_minutes_is_warning_or_critical(clean_month):
    _, df, _ = clean_month
    df = df.copy()
    df.loc[0, "TaxiOut"] = -5.0
    report = quality.check_month(df, 2025, 7, TARGETS, "origin")
    assert _status(report, "negative_minutes") in ("warning", "critical")


def test_outlier_delay_is_warning(clean_month):
    _, df, _ = clean_month
    df = df.copy()
    df.loc[0, "ArrDelay"] = 9000.0
    report = quality.check_month(df, 2025, 7, TARGETS, "origin")
    assert _status(report, "delay_plausible_range") == "warning"  # no critical level


def test_rows_outside_target_scope_is_critical(clean_month):
    _, df, _ = clean_month
    report = quality.check_month(df, 2025, 7, ["SEA"], "origin")
    assert _status(report, "rows_outside_target_scope") == "critical"


def test_scope_check_is_skipped_without_targets(clean_month):
    _, df, _ = clean_month
    report = quality.check_month(df, 2025, 7, None, "origin")
    assert _status(report, "rows_outside_target_scope") == "skipped"


def test_cancellation_consistency(clean_month):
    _, df, _ = clean_month
    df = df.copy()
    index = df.index[df["Cancelled"] == 1][0]
    df.loc[index, "ArrDelay"] = 30.0
    report = quality.check_month(df, 2025, 7, TARGETS, "origin")
    assert _status(report, "cancelled_but_arr_delay_present") == "critical"  # 1/1 cancelled


def test_utc_duration_mismatch(clean_month):
    _, df, _ = clean_month
    df = df.copy()
    df["CRSElapsedTime"] = df["CRSElapsedTime"] + 200
    report = quality.check_month(df, 2025, 7, TARGETS, "origin")
    assert _status(report, "utc_duration_crs_mismatch") == "critical"


def test_utc_missing_airport(tmp_path, fake_ontime, process_fake_month):
    # including the ZZZ row: crs_arr_utc is empty -> utc_arrival_missing violation; departure UTC stays filled
    root, summary = process_fake_month(tmp_path, df=fake_ontime)
    df = layer.read_wide_month(root, 2025, 7)
    report = quality.check_month(df, 2025, 7, TARGETS, "origin", summary)
    assert _status(report, "utc_departure_missing") == "passed"
    assert _status(report, "utc_arrival_missing") == "critical"  # 1/4 > 1%
    assert _status(report, "utc_tz_missing_rows") == "critical"
    check = next(x for x in report["checks"] if x["name"] == "utc_arrival_missing")
    assert check["value"]["tz_missing_dest"] == ["ZZZ"]


def test_missing_schema_column_is_critical_and_others_skipped(clean_month):
    _, df, _ = clean_month
    report = quality.check_month(df.drop(columns=["ArrDelay"]), 2025, 7, TARGETS, "origin")
    assert _status(report, "schema_missing_column") == "critical"
    assert _status(report, "other_checks") == "skipped"


def test_schema_type_mismatch(clean_month):
    _, df, _ = clean_month
    df = df.copy()
    df["Distance"] = df["Distance"].astype(str)
    report = quality.check_month(df, 2025, 7, TARGETS, "origin")
    assert _status(report, "schema_type_mismatch") == "critical"


def test_row_count_summary_mismatch(clean_month):
    _, df, summary = clean_month
    report = quality.check_month(df.iloc[:-1], 2025, 7, TARGETS, "origin", summary)
    assert _status(report, "row_count_matches_summary") == "critical"


def test_previous_run_row_difference(clean_month):
    _, df, summary = clean_month
    same = quality.check_month(df, 2025, 7, TARGETS, "origin", summary, previous_rows=len(df))
    different = quality.check_month(df, 2025, 7, TARGETS, "origin", summary, previous_rows=len(df) + 5)
    assert _status(same, "rows_vs_previous_run") == "passed"
    assert _status(different, "rows_vs_previous_run") == "warning"


def test_empty_month_is_critical():
    report = quality.check_month(pd.DataFrame(columns=list(layer.OUTPUT_SCHEMA)), 2025, 7)
    assert _status(report, "zero_rows") == "critical"


def test_content_hash_is_deterministic_and_order_independent(clean_month):
    _, df, _ = clean_month
    assert quality.content_hash(df) == quality.content_hash(df.sort_values("flight_id", ascending=False))
    changed = df.copy()
    changed.loc[0, "ArrDelay"] = 99.0
    assert quality.content_hash(df) != quality.content_hash(changed)


def test_period_month_gap_is_critical():
    months = [{"year": 2025, "month": m, "rows": 100} for m in (1, 2, 4)]
    checks = {x["name"]: x for x in quality.check_period(months)}
    assert checks["period_month_gap"]["status"] == "critical"
    assert checks["period_month_gap"]["value"]["missing_months"] == ["2025-03"]


def test_period_year_boundary_has_no_gap():
    months = [{"year": 2024, "month": 12, "rows": 100}, {"year": 2025, "month": 1, "rows": 100}]
    checks = {x["name"]: x for x in quality.check_period(months)}
    assert checks["period_month_gap"]["status"] == "passed"


def test_period_row_deviation_is_warning():
    months = [{"year": 2025, "month": m, "rows": r} for m, r in ((1, 100), (2, 100), (3, 100), (4, 10))]
    checks = {x["name"]: x for x in quality.check_period(months)}
    assert checks["period_row_deviation"]["status"] == "warning"
    assert "2025-04" in checks["period_row_deviation"]["value"]["deviating_months_relative"]


def test_period_empty_is_critical():
    assert quality.check_period([])[0]["status"] == "critical"


def test_end_to_end_report_files(clean_month):
    root, _, _ = clean_month
    report = quality.run_checks(root, TARGETS, "origin")
    assert report["overall_status"] == "passed", report["overall_status"]
    assert len(report["months"]) == 1 and report["months"][0]["rows"] == 3
    # JSON serialisable and markdown is produced
    json.dumps(report, ensure_ascii=False)
    markdown = quality.render_markdown(report)
    assert "# Data layer quality report" in markdown and "2025-07" in markdown
    # second run: same hash, no row-count warning
    second = quality.run_checks(root, TARGETS, "origin", previous_report=report)
    assert second["months"][0]["hash"] == report["months"][0]["hash"]
    assert second["overall_status"] == "passed"


def test_cli_exit_code_and_files(tmp_path, clean_month):
    root, _, _ = clean_month
    targets_file = tmp_path / "targets.txt"
    targets_file.write_text("ORD\nATL\n", encoding="utf-8")
    out_json, out_md = tmp_path / "r.json", tmp_path / "r.md"
    code = quality.main(
        [
            "--layer-dir",
            str(root),
            "--targets-file",
            str(targets_file),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
        ]
    )
    assert code == 0 and out_json.is_file() and out_md.is_file()
    # change the target list -> rows outside scope -> critical -> exit code 2
    targets_file.write_text("SEA\n", encoding="utf-8")
    assert (
        quality.main(
            [
                "--layer-dir",
                str(root),
                "--targets-file",
                str(targets_file),
                "--output-json",
                str(out_json),
                "--output-md",
                str(out_md),
            ]
        )
        == 2
    )
