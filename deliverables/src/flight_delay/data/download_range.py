"""Download the months of a date range one after another (and optionally process each into the layer, then delete the raw file).

MAKES NETWORK CALLS (through download_ontime.download); the main session runs it with the user's approval.

WHICH MONTHS (which 36): decided by the data scientist -> ``--start`` and ``--end`` are REQUIRED, with no default.
(Status: "waiting for the data scientist's approval"; the split design is in experiments/modelleme-plani.md.)

Behaviour:
  * Month list: start and end INCLUSIVE (e.g. 2023-09 .. 2026-08 = 36 months).
  * Skipping: if the layer is already processed (Parquet + summary.json) the month is skipped; if the raw
    file (zip/csv) already exists it is NOT downloaded again (it is processed from the existing file).
  * --process: each month is processed with layer.process_month right after download.
  * --delete-raw: (implies --process) after successful processing the month's zip + csv are deleted
    (to save disk; download-record-*.json stays). If processing fails the raw file is NOT deleted.
  * Error: STOPS at that month (no retry), writes the summary, exit code 1. A partial download that is not
    a valid zip (HTML error page etc.) is deleted so the next run does not mistake it for "raw exists".
  * Wait between requests: --wait-sec (default 5 s) between two REAL downloads. This value is the author's
    choice; no official BTS rate limit was verified.
  * Summary: deliverables/data/download-range-summary.json is updated after every month (progress stays even if interrupted).

Usage:
  python -m flight_delay.data.download_range --start 2025-07 --end 2025-07 --process --delete-raw   # small trial
  python -m flight_delay.data.download_range --start <YYYY-MM> --end <YYYY-MM> --delete-raw          # the DS range
  python -m flight_delay.data.download_range --start <..> --end <..> --dry-run                       # plan only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flight_delay.data import download_ontime, layer
from flight_delay.paths import DATA_DIR

__all__ = [
    "DEFAULT_MAX_MONTHS",
    "DEFAULT_RAW_DIR",
    "DEFAULT_SUMMARY",
    "DEFAULT_WAIT_SEC",
    "delete_raw_files",
    "main",
    "month_range",
    "parse_month",
    "plan_months",
    "raw_input_path",
    "run",
    "zip_path",
]

DEFAULT_RAW_DIR = DATA_DIR / "raw"
DEFAULT_SUMMARY = DATA_DIR / "download-range-summary.json"
DEFAULT_WAIT_SEC = 5.0
DEFAULT_MAX_MONTHS = 36

Downloader = Callable[[int, int, Path], dict[str, Any]]
Processor = Callable[[Path, int, int], dict[str, Any]]


# ----------------------------------------------------------------------------
# month list
# ----------------------------------------------------------------------------


def parse_month(text: str) -> tuple[int, int]:
    """'2023-09' (or '2023-9') -> (2023, 9)."""
    match = re.fullmatch(r"\s*(\d{4})-(\d{1,2})\s*", text or "")
    if not match:
        raise ValueError(f"Month format must be YYYY-MM, given: {text!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not (1 <= month <= 12):
        raise ValueError(f"Invalid month: {text!r}")
    return year, month


def month_range(start: str, end: str) -> list[tuple[int, int]]:
    """Chronological list of (year, month), start and end INCLUSIVE."""
    year, month = parse_month(start)
    end_year, end_month = parse_month(end)
    if (end_year, end_month) < (year, month):
        raise ValueError(f"end ({end}) cannot be before start ({start}).")
    months: list[tuple[int, int]] = []
    while (year, month) <= (end_year, end_month):
        months.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


# ----------------------------------------------------------------------------
# raw file helpers
# ----------------------------------------------------------------------------


def zip_path(raw_dir: Path, year: int, month: int) -> Path:
    return Path(raw_dir) / f"ontime_{year}_{month:02d}.zip"


def raw_input_path(raw_dir: Path, year: int, month: int) -> Path | None:
    """The month's raw file if present: the zip first (download_ontime name), else the BTS csv name (..._YEAR_MONTH.csv)."""
    archive = zip_path(raw_dir, year, month)
    if archive.is_file():
        return archive
    candidates = sorted(Path(raw_dir).glob(f"*_{year}_{month}.csv"))
    return candidates[0] if candidates else None


def delete_raw_files(raw_dir: Path, year: int, month: int) -> list[str]:
    """Delete the month's zip and csv files; return the deleted names (download-record stays)."""
    deleted: list[str] = []
    candidates = [zip_path(raw_dir, year, month), *sorted(Path(raw_dir).glob(f"*_{year}_{month}.csv"))]
    for path in candidates:
        if path.is_file():
            path.unlink()
            deleted.append(path.name)
    return deleted


def _write_summary(path: Path | None, summary: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------
# core (downloader/processor are injected -> testable without network)
# ----------------------------------------------------------------------------


def run(
    months: list[tuple[int, int]],
    raw_dir: Path,
    layer_root: Path,
    *,
    downloader: Downloader = download_ontime.download,
    processor: Processor | None = None,
    delete_raw: bool = False,
    wait_sec: float = DEFAULT_WAIT_SEC,
    sleep: Callable[[float], None] = time.sleep,
    force: bool = False,
    summary_path: Path | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Process the months in order. Stops at the first error. Returns the summary dict."""
    if delete_raw and processor is None:
        raise ValueError("delete_raw requires a processor (--process): an unprocessed raw file cannot be deleted.")
    raw_dir, layer_root = Path(raw_dir), Path(layer_root)
    summary: dict[str, Any] = {
        "months": [],
        "has_error": False,
        "parameters": {
            "delete_raw": delete_raw,
            "process": processor is not None,
            "wait_sec": wait_sec,
            "force": force,
            "month_count": len(months),
        },
    }
    downloaded_count = 0
    for year, month in months:
        record: dict[str, Any] = {"year": year, "month": month, "status": None}
        summary["months"].append(record)
        label = f"{year}-{month:02d}"
        try:
            already_processed = (
                processor is not None and layer.is_month_processed(layer_root, year, month) and not force
            )
            if already_processed:
                record["status"] = "skipped_processed"
                if delete_raw:
                    record["deleted_raw"] = delete_raw_files(raw_dir, year, month)
                log(f"[{label}] skipped (layer already processed)")
                continue

            input_path = raw_input_path(raw_dir, year, month)
            if input_path is None:
                if downloaded_count > 0 and wait_sec > 0:
                    sleep(wait_sec)
                log(f"[{label}] downloading...")
                downloader(year, month, raw_dir)
                downloaded_count += 1
                record["downloaded"] = True
                input_path = raw_input_path(raw_dir, year, month)
                if input_path is None:
                    raise RuntimeError("Download finished but the raw file was not found.")
            else:
                record["downloaded"] = False
                log(f"[{label}] raw file already exists, not downloading again: {input_path.name}")

            if processor is not None:
                month_summary = processor(input_path, year, month)
                record["status"] = "processed"
                if isinstance(month_summary, dict):
                    record["rows_raw"] = month_summary.get("rows_raw")
                    record["rows_layer"] = month_summary.get("rows_layer")
                    record["rows_dropped_missing_key"] = month_summary.get("rows_dropped_missing_key")
                    record["dropped_missing_key_by_field"] = month_summary.get("dropped_missing_key_by_field")
                if delete_raw:
                    record["deleted_raw"] = delete_raw_files(raw_dir, year, month)
                log(f"[{label}] processed" + (f" (deleted raw: {record['deleted_raw']})" if delete_raw else ""))
            else:
                record["status"] = "downloaded" if record["downloaded"] else "raw_exists"
        except Exception as e:  # stop at the first error and report it (no retry)
            record["status"] = "error"
            record["error"] = f"{type(e).__name__}: {e}"
            archive = zip_path(raw_dir, year, month)
            if archive.is_file() and not zipfile.is_zipfile(archive):
                archive.unlink()
                record["corrupt_zip_deleted"] = archive.name
            summary["has_error"] = True
            log(f"[{label}] ERROR: {record['error']} -- stopping (no retry).")
            break
        finally:
            _write_summary(summary_path, summary)

    summary["unprocessed_months"] = [
        f"{r['year']}-{r['month']:02d}" for r in summary["months"] if r["status"] == "error"
    ] + [f"{y}-{m:02d}" for (y, m) in months[len(summary["months"]) :]]
    _write_summary(summary_path, summary)
    return summary


def plan_months(months: list[tuple[int, int]], raw_dir: Path, layer_root: Path) -> list[dict[str, Any]]:
    """Offline and side-effect free: say what would be done for each month."""
    plan = []
    for year, month in months:
        if layer.is_month_processed(layer_root, year, month):
            action = "skip_processed"
        elif raw_input_path(raw_dir, year, month) is not None:
            action = "raw_exists_will_process"
        else:
            action = "will_download"
        plan.append({"year": year, "month": month, "plan": action})
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BTS On-Time: month-range downloader (NETWORK CALL; needs the user's approval)."
    )
    parser.add_argument("--start", required=True, help="YYYY-MM (inclusive). Range awaits the DS; no default.")
    parser.add_argument("--end", required=True, help="YYYY-MM (inclusive).")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--layer-dir", type=Path, default=layer.DEFAULT_LAYER_DIR)
    parser.add_argument(
        "--process", action="store_true", help="Process each month into the layer right after download."
    )
    parser.add_argument(
        "--delete-raw", action="store_true", help="Delete the raw zip/csv after processing (implies --process)."
    )
    parser.add_argument("--force", action="store_true", help="Re-process already processed months too.")
    parser.add_argument("--scope", choices=layer.SCOPE_MODES, default="origin")
    parser.add_argument("--targets-file", type=Path, default=layer.DEFAULT_TARGETS_FILE)
    parser.add_argument("--ourairports", type=Path, default=layer.DEFAULT_AIRPORTS)
    parser.add_argument("--tz-overrides", type=Path, default=layer.DEFAULT_TZ_OVERRIDES)
    parser.add_argument(
        "--no-tz-overrides",
        action="store_true",
        help="Process WITHOUT manual time zone overrides on purpose (otherwise a missing --tz-overrides file is an error).",
    )
    parser.add_argument("--wait-sec", type=float, default=DEFAULT_WAIT_SEC)
    parser.add_argument(
        "--max-months",
        type=int,
        default=DEFAULT_MAX_MONTHS,
        help="Upper bound that prevents an accidentally huge range (default 36).",
    )
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--dry-run", action="store_true", help="Only print the plan; no network / file operations.")
    args = parser.parse_args(argv)

    try:
        months = month_range(args.start, args.end)
    except ValueError as e:
        parser.error(str(e))
    if len(months) > args.max_months:
        parser.error(
            f"{len(months)} months requested; --max-months={args.max_months}. Raise --max-months to widen on purpose."
        )
    process = args.process or args.delete_raw

    if args.dry_run:
        for item in plan_months(months, args.raw_dir, args.layer_dir):
            print(f"{item['year']}-{item['month']:02d}: {item['plan']}")
        return 0

    processor: Processor | None = None
    if process:
        targets = layer.read_targets(args.targets_file)
        airports = layer.load_airports(args.ourairports)
        overrides = layer.load_tz_overrides(None if args.no_tz_overrides else args.tz_overrides)

        def _process(input_path: Path, year: int, month: int) -> dict[str, Any]:
            return layer.process_month(
                input_path, year, month, args.layer_dir, targets, airports, overrides, args.scope
            )

        processor = _process

    summary = run(
        months,
        args.raw_dir,
        args.layer_dir,
        processor=processor,
        delete_raw=args.delete_raw,
        wait_sec=args.wait_sec,
        force=args.force,
        summary_path=args.summary_path,
    )
    statuses: dict[str, int] = {}
    for record in summary["months"]:
        statuses[record["status"]] = statuses.get(record["status"], 0) + 1
    print(f"Summary: {statuses}; unprocessed: {summary['unprocessed_months']}; details: {args.summary_path}")
    return 1 if summary["has_error"] else 0


if __name__ == "__main__":
    sys.exit(main())
