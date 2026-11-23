"""Download ONE month of BTS On-Time (Reporting Carrier) data.

TOGETHER WITH download_range (which calls it) THIS IS THE ONLY NETWORK-CALLING CODE IN THE PROJECT
(iem_matching, time_conversion, size_measurement are offline). The main session runs it with the
user's approval; agents do not.

What it does:
  1. Downloads the monthly "prezipped" file (all fields, one month, zip containing a CSV).
  2. Validates the zip (BTS sometimes returns an HTML error page).
  3. Extracts the CSV under deliverables/data/raw/.
  4. Writes download-record-<YEAR>-<MONTH>.json (URL, bytes, sha256) -> reproducibility.

Raw data does NOT go into git (see the .gitignore suggestion in the run guide).

NOT-VERIFIED WARNING (critical):
  URL_PATTERN follows the known pattern for TranStats "prezipped" files, but it is not independently
  verified (the record therefore keeps ``url_pattern_verified: false`` until a human flips it). The
  BTS site also has occasional certificate/redirect problems. If the download fails, MANUAL ROUTE:
    - Open the TranStats "Reporting Carrier On-Time Performance (1987-present)" download page in a
      browser (field list page: https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ ; the link to
      the download page is in its "Download" section -- exact address not verified).
    - Choose Filter Year = <YEAR>, Filter Period = <MONTH>.
    - Use the "Prezipped File" link (all fields) OR tick the needed fields and press "Download"
      (only the needed columns; column names stay the same).
    - Put the zip/CSV into deliverables/data/raw/; size_measurement reads zip files too.

Usage:
  python -m flight_delay.data.download_ontime --year 2025 --month 7
  python -m flight_delay.data.download_ontime --manual-help
  python -m flight_delay.data.download_ontime --year 2025 --month 7 --url "<manually verified URL>"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from flight_delay.paths import DATA_DIR

__all__ = [
    "DEFAULT_TARGET_DIR",
    "MANUAL_DOWNLOAD_HELP",
    "URL_PATTERN",
    "build_url",
    "download",
    "main",
]

DEFAULT_TARGET_DIR = DATA_DIR / "raw"

# NOT VERIFIED: monthly prezipped file pattern. {month} is unpadded (1..12).
URL_PATTERN = (
    "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)

# Safety limits (assumption; a monthly zip is expected to be far below this).
MAX_ZIP_BYTES = 600 * 1024 * 1024
TIMEOUT_SEC = 120
USER_AGENT = "havayolu-ds-data-downloader/0.1 (personal portfolio project)"

MANUAL_DOWNLOAD_HELP = """\
MANUAL DOWNLOAD (if the URL pattern was not verified / the download failed):
  1. Open this field list page in a browser and follow its "Download" link:
       https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ
     (Table: Reporting Carrier On-Time Performance (1987-present); the download page address
      was not verified in this session.)
  2. Pick exactly ONE month with Filter Year and Filter Period (suggestion: a summer peak month,
     e.g. 2025-07; the choice is the user's. A peak month gives a conservative / upper-end measurement).
  3. Download all fields with "Prezipped File", or tick the fields you need and download.
  4. Put the file (zip or csv) into deliverables/data/raw/. Then:
       python -m flight_delay.data.size_measurement --input <file>
"""


def build_url(year: int, month: int, pattern: str = URL_PATTERN) -> str:
    """Build the download URL for a year/month (offline; testable)."""
    if not (1987 <= year <= 2100):
        raise ValueError(f"Invalid year: {year}")
    if not (1 <= month <= 12):
        raise ValueError(f"Invalid month: {month}")
    return pattern.format(year=year, month=month)


def _download(url: str, target_file: Path) -> tuple[int, str]:
    """Download a URL in chunks; return (bytes, sha256). Leaves no partial file behind."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    partial = target_file.with_suffix(target_file.suffix + ".part")
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response, open(partial, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ZIP_BYTES:
                    raise RuntimeError("Download exceeded the expected size limit; stopped.")
                digest.update(chunk)
                handle.write(chunk)
        partial.replace(target_file)
    finally:
        if partial.exists():
            partial.unlink()
    return total, digest.hexdigest()


def _extract_csv(zip_path: Path, target_dir: Path) -> Path:
    """Safely extract the SINGLE csv in the zip (path traversal / zip-slip is prevented)."""
    if not zipfile.is_zipfile(zip_path):
        raise RuntimeError(
            "The downloaded file is not a valid zip (probably an error/redirect page). "
            "The URL pattern may be wrong; see --manual-help for the manual download route."
        )
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RuntimeError(f"Expected exactly 1 csv inside the zip, found: {csv_names}")
        member = csv_names[0]
        name = Path(member).name  # drop folder components -> no zip-slip
        target = target_dir / name
        with archive.open(member) as source, open(target, "wb") as output:
            shutil.copyfileobj(source, output)
    return target


def download(year: int, month: int, target_dir: Path, url: str | None = None, force: bool = False) -> dict[str, Any]:
    """Download and extract one month; return the record dict."""
    target_dir.mkdir(parents=True, exist_ok=True)
    url = url or build_url(year, month)
    zip_path = target_dir / f"ontime_{year}_{month:02d}.zip"
    if zip_path.exists() and not force:
        raise FileExistsError(f"{zip_path} already exists; use --force to overwrite.")
    size, sha = _download(url, zip_path)
    csv_path = _extract_csv(zip_path, target_dir)
    record = {
        "year": year,
        "month": month,
        "url": url,
        "url_pattern_verified": False,  # stays False until a human verifies it
        "zip_file": zip_path.name,
        "zip_bytes": size,
        "zip_sha256": sha,
        "csv_file": csv_path.name,
        "csv_bytes": csv_path.stat().st_size,
    }
    (target_dir / f"download-record-{year}-{month:02d}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BTS On-Time single-month downloader (network call only here).")
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR, help="Raw data folder (not in git).")
    parser.add_argument("--url", default=None, help="Give the URL by hand (if the pattern does not work).")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing zip.")
    parser.add_argument("--manual-help", action="store_true", help="Only print the manual download route.")
    args = parser.parse_args(argv)

    if args.manual_help:
        print(MANUAL_DOWNLOAD_HELP)
        return 0
    if args.year is None or args.month is None:
        parser.error("--year and --month are required (or --manual-help).")

    url = args.url or build_url(args.year, args.month)
    print(f"URL to download (pattern NOT VERIFIED): {url}")
    try:
        record = download(args.year, args.month, args.target_dir, url=args.url, force=args.force)
    except (urllib.error.URLError, RuntimeError, FileExistsError, OSError) as e:
        # No automatic retry (rule): report the error and stop.
        print(f"ERROR: {e}\n", file=sys.stderr)
        print(MANUAL_DOWNLOAD_HELP, file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
