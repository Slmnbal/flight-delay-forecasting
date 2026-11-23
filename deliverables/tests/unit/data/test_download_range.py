"""download_range tests: month list, skipping, raw deletion, stopping on error (OFFLINE; fake downloader)."""

import json
import zipfile

import pytest

from flight_delay.data import download_range as dr
from flight_delay.data import layer


# ----------------------------------------------------------------------------
# month list
# ----------------------------------------------------------------------------
def test_parse_month():
    assert dr.parse_month("2023-09") == (2023, 9)
    assert dr.parse_month("2023-9") == (2023, 9)


@pytest.mark.parametrize("bad", ["2023", "2023-13", "2023-00", "23-05", "abc", "", "2023/05"])
def test_parse_month_invalid(bad):
    with pytest.raises(ValueError):
        dr.parse_month(bad)


def test_month_range_36_months():
    months = dr.month_range("2023-09", "2026-08")
    assert len(months) == 36
    assert months[0] == (2023, 9) and months[-1] == (2026, 8)
    assert months == sorted(months) and len(set(months)) == 36


def test_month_range_year_boundary_and_single_month():
    assert dr.month_range("2024-11", "2025-02") == [(2024, 11), (2024, 12), (2025, 1), (2025, 2)]
    assert dr.month_range("2025-07", "2025-07") == [(2025, 7)]


def test_month_range_reversed():
    with pytest.raises(ValueError):
        dr.month_range("2025-08", "2025-07")


def test_cli_no_default_range_is_required():
    with pytest.raises(SystemExit):
        dr.main([])


def test_cli_max_months_limit(tmp_path):
    with pytest.raises(SystemExit):
        dr.main(
            [
                "--start",
                "2020-01",
                "--end",
                "2025-12",
                "--dry-run",
                "--raw-dir",
                str(tmp_path),
                "--layer-dir",
                str(tmp_path),
            ]
        )


# ----------------------------------------------------------------------------
# fake downloader / processor
# ----------------------------------------------------------------------------
class _FakeInput:
    name = "x.zip"


class FakeDownloader:
    def __init__(self, error_month=None, corrupt_month=None):
        self.calls = []
        self.error_month = error_month
        self.corrupt_month = corrupt_month

    def __call__(self, year, month, folder):
        self.calls.append((year, month))
        folder.mkdir(parents=True, exist_ok=True)
        archive = dr.zip_path(folder, year, month)
        if (year, month) == self.corrupt_month:
            archive.write_text("<html>error page</html>")  # not a valid zip
            raise RuntimeError("The downloaded file is not a valid zip")
        if (year, month) == self.error_month:
            raise OSError("network error")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(f"On_Time_(1987_present)_{year}_{month}.csv", "a,b\n1,2\n")
        (folder / f"On_Time_(1987_present)_{year}_{month}.csv").write_text("a,b\n1,2\n")
        return {"year": year, "month": month}


class FakeProcessor:
    def __init__(self, root, error_month=None):
        self.root = root
        self.calls = []
        self.error_month = error_month

    def __call__(self, input_path, year, month):
        self.calls.append((year, month, input_path.name))
        if (year, month) == self.error_month:
            raise ValueError("processing error")
        folder = layer.month_dir(self.root, year, month)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / layer.PARQUET_NAME).write_bytes(b"x")
        (folder / layer.SUMMARY_NAME).write_text("{}")
        return {"rows_raw": 10, "rows_layer": 5}


def _run(tmp_path, months, downloader, processor=None, **options):
    sleeps = []
    summary = dr.run(
        months,
        tmp_path / "raw",
        tmp_path / "layer",
        downloader=downloader,
        processor=processor,
        sleep=sleeps.append,
        log=lambda s: None,
        summary_path=tmp_path / "summary.json",
        **options,
    )
    return summary, sleeps


def test_processed_month_is_skipped_and_existing_raw_is_not_downloaded(tmp_path):
    root = tmp_path / "layer"
    processor = FakeProcessor(root)
    processor(_FakeInput(), 2025, 1)  # 2025-01 was processed earlier
    processor.calls.clear()
    raw = tmp_path / "raw"
    raw.mkdir()
    with zipfile.ZipFile(dr.zip_path(raw, 2025, 2), "w") as zf:  # 2025-02 raw exists, not processed
        zf.writestr("x_2025_2.csv", "a\n1\n")
    downloader = FakeDownloader()
    summary, _ = _run(tmp_path, [(2025, 1), (2025, 2), (2025, 3)], downloader, processor)
    statuses = {(r["year"], r["month"]): r["status"] for r in summary["months"]}
    assert statuses == {(2025, 1): "skipped_processed", (2025, 2): "processed", (2025, 3): "processed"}
    assert downloader.calls == [(2025, 3)]  # only the month without a raw file was downloaded
    assert [c[:2] for c in processor.calls] == [(2025, 2), (2025, 3)]
    assert not summary["has_error"]


def test_force_reprocesses_a_processed_month(tmp_path):
    root = tmp_path / "layer"
    processor = FakeProcessor(root)
    folder = layer.month_dir(root, 2025, 1)
    folder.mkdir(parents=True)
    (folder / layer.PARQUET_NAME).write_bytes(b"x")
    (folder / layer.SUMMARY_NAME).write_text("{}")
    downloader = FakeDownloader()
    summary, _ = _run(tmp_path, [(2025, 1)], downloader, processor, force=True)
    assert summary["months"][0]["status"] == "processed"


def test_wait_only_between_real_downloads(tmp_path):
    downloader = FakeDownloader()
    summary, sleeps = _run(tmp_path, [(2025, 1), (2025, 2), (2025, 3)], downloader, wait_sec=2.5)
    assert downloader.calls == [(2025, 1), (2025, 2), (2025, 3)]
    assert sleeps == [2.5, 2.5]  # no wait before the first download
    assert [r["status"] for r in summary["months"]] == ["downloaded"] * 3


def test_delete_raw_removes_files_after_processing(tmp_path):
    root = tmp_path / "layer"
    downloader, processor = FakeDownloader(), FakeProcessor(root)
    summary, _ = _run(tmp_path, [(2025, 1)], downloader, processor, delete_raw=True)
    raw = tmp_path / "raw"
    assert not dr.zip_path(raw, 2025, 1).exists()
    assert not list(raw.glob("*.csv"))
    assert sorted(summary["months"][0]["deleted_raw"]) == sorted(
        ["ontime_2025_01.zip", "On_Time_(1987_present)_2025_1.csv"]
    )
    assert layer.is_month_processed(root, 2025, 1)


def test_delete_raw_keeps_files_if_processing_fails(tmp_path):
    root = tmp_path / "layer"
    downloader, processor = FakeDownloader(), FakeProcessor(root, error_month=(2025, 1))
    summary, _ = _run(tmp_path, [(2025, 1), (2025, 2)], downloader, processor, delete_raw=True)
    assert dr.zip_path(tmp_path / "raw", 2025, 1).exists()  # kept -> can be retried without downloading
    assert summary["has_error"] and summary["months"][0]["status"] == "error"
    assert "ValueError" in summary["months"][0]["error"]


def test_delete_raw_without_processor_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        dr.run([(2025, 1)], tmp_path, tmp_path, delete_raw=True)


def test_stops_on_error_and_writes_summary(tmp_path):
    downloader = FakeDownloader(error_month=(2025, 2))
    summary, _ = _run(tmp_path, [(2025, 1), (2025, 2), (2025, 3), (2025, 4)], downloader)
    assert downloader.calls == [(2025, 1), (2025, 2)]  # months 3 and 4 were not tried; no retry
    assert [r["status"] for r in summary["months"]] == ["downloaded", "error"]
    assert summary["has_error"] is True
    assert summary["unprocessed_months"] == ["2025-02", "2025-03", "2025-04"]
    on_disk = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert on_disk["has_error"] is True and on_disk["unprocessed_months"] == summary["unprocessed_months"]


def test_corrupt_zip_is_deleted(tmp_path):
    downloader = FakeDownloader(corrupt_month=(2025, 1))
    summary, _ = _run(tmp_path, [(2025, 1)], downloader)
    assert not dr.zip_path(tmp_path / "raw", 2025, 1).exists()
    assert summary["months"][0]["corrupt_zip_deleted"] == "ontime_2025_01.zip"


def test_plan_has_no_side_effects(tmp_path):
    root = tmp_path / "layer"
    FakeProcessor(root)(_FakeInput(), 2025, 1)
    raw = tmp_path / "raw"
    raw.mkdir()
    dr.zip_path(raw, 2025, 2).write_bytes(b"z")
    plan = dr.plan_months([(2025, 1), (2025, 2), (2025, 3)], raw, root)
    assert [x["plan"] for x in plan] == ["skip_processed", "raw_exists_will_process", "will_download"]


def test_raw_csv_name_does_not_mix_months(tmp_path):
    (tmp_path / "On_Time_(1987_present)_2025_11.csv").write_text("x")
    assert dr.raw_input_path(tmp_path, 2025, 1) is None  # "_2025_1.csv" must not match "_2025_11.csv"
    assert dr.raw_input_path(tmp_path, 2025, 11).name.endswith("_2025_11.csv")
