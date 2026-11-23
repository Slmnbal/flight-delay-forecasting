"""Download ASOS/METAR observations of the 30 target airports from the Iowa Environmental Mesonet (IEM).

THIS MODULE MAKES NETWORK CALLS (only ``fetch_url`` does). The main session runs it with the user's approval;
agents do not. Everything else here (planning, URL building, validation, station matching) is offline.

What it does:
  1. Resolves the IEM station id of every target airport OFFLINE from the IEM station list file and OurAirports
     (``iem_matching.match_stations``); stops if any target is not ``matched``.
  2. Plans ONE request per station and calendar-year chunk of the date range (a 3-year range = 4 chunks per
     station = 120 requests for 30 stations). Hard stop if the planned station-years exceed the IEM limit
     (1,000 station-years; research report [D]); one station per request keeps every request tiny.
  3. Downloads the requests one after another, WAITING ``--wait-sec`` between two real downloads (default 5 s;
     the author's choice, not an IEM rule), STOPS AT THE FIRST ERROR (no retry), writes the summary after every
     request, and skips chunks whose file already exists (so an interrupted run can be continued by hand).
  4. Writes ``<out-dir>/<station>_<start>_<end>.csv`` (UTC timestamps, only ``IEM_VARIABLES``),
     ``<out-dir>/station_map.json`` ({IATA: IEM station id}) and ``<out-dir>/download-iem-summary.json``
     (URL, bytes, sha256, data rows per request).

UNVERIFIED (nothing here was run against the real service; check before the first real run):
  * ENDPOINT and PARAMETER NAMES below follow the IEM ``asos.py`` request page as remembered by the author:
    station (repeatable), data (repeatable), year1/month1/day1 .. year2/month2/day2, tz, format=onlycomma,
    latlon, elev, missing, trace, direct, report_type (repeatable). None of them was checked this session.
  * Whether the end date is inclusive or exclusive: this module asks for ``end + 1 day`` (exclusive reading);
    if the service treats it as inclusive, the extra day only duplicates observations of the next chunk, and
    ``metar.clean_metar`` removes duplicates.
  * ``report_type`` 3 (routine) and 4 (special) = METAR and SPECI; if the parameter is unknown to the service
    it is ignored and the default set is returned.
  * ``trace=0.0001`` asks for trace precipitation as the number 0.0001 instead of the letter "T".
  * "1,000 station-years" is understood as a per-request limit (stations x years); the module also applies it
    to the whole plan, which is stricter than necessary.
  * IEM asks automated clients to be polite; the delay and the single-station requests are the author's reading.
  Attribution: the data source is the Iowa Environmental Mesonet (cite it in the project documents).

Usage:
  python -m flight_delay.data.download_iem --start 2023-09-01 --end 2026-08-31 --dry-run     # offline plan only
  python -m flight_delay.data.download_iem --start 2025-07-01 --end 2025-07-31 --only ORD     # small trial
  python -m flight_delay.data.download_iem --start 2023-09-01 --end 2026-08-31               # full range
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from flight_delay.data.airports import load_ourairports
from flight_delay.data.iem_matching import match_stations, read_station_list
from flight_delay.data.inputs import require_file
from flight_delay.data.layer import DEFAULT_AIRPORTS, DEFAULT_TARGETS_FILE, read_targets
from flight_delay.data.metar import IEM_VARIABLES
from flight_delay.paths import DATA_DIR

__all__ = [
    "BASE_URL",
    "DEFAULT_OUT_DIR",
    "DEFAULT_STATIONS_FILE",
    "MAX_STATION_YEARS",
    "StationRequest",
    "build_request_url",
    "check_station_year_limit",
    "fetch_url",
    "main",
    "plan_requests",
    "resolve_stations",
    "run",
    "station_years",
    "validate_csv_text",
    "year_chunks",
]

# UNVERIFIED endpoint (see the module docstring).
BASE_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
MAX_STATION_YEARS = 1000  # IEM limit as stated in the research report [D]
DEFAULT_WAIT_SEC = 5.0
TIMEOUT_SEC = 300
MAX_RESPONSE_BYTES = 200 * 1024 * 1024  # safety limit for one station-year (assumption; real files are far smaller)
USER_AGENT = "flight-delay-research-downloader/0.1 (personal portfolio project)"

DEFAULT_OUT_DIR = DATA_DIR / "raw" / "iem_asos"
DEFAULT_STATIONS_FILE = DATA_DIR / "raw" / "iem_istasyonlar.geojson"
SUMMARY_NAME = "download-iem-summary.json"
STATION_MAP_NAME = "station_map.json"

Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class StationRequest:
    """One download: one station, dates ``start`` .. ``end`` INCLUSIVE (UTC days)."""

    iata: str
    station: str
    start: date
    end: date

    @property
    def filename(self) -> str:
        return f"{self.station}_{self.start:%Y%m%d}_{self.end:%Y%m%d}.csv"

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


# ----------------------------------------------------------------------------
# offline planning
# ----------------------------------------------------------------------------


def year_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] (inclusive) at calendar-year boundaries."""
    if end < start:
        raise ValueError(f"end ({end}) cannot be before start ({start}).")
    chunks: list[tuple[date, date]] = []
    current = start
    while current <= end:
        year_end = date(current.year, 12, 31)
        chunk_end = min(year_end, end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def build_request_url(
    station: str,
    start: date,
    end: date,
    variables: tuple[str, ...] = IEM_VARIABLES,
    base_url: str = BASE_URL,
) -> str:
    """Request URL for one station and the days ``start`` .. ``end`` inclusive (UNVERIFIED parameters)."""
    end_exclusive = end + timedelta(days=1)
    params: list[tuple[str, str]] = [("station", station)]
    params += [("data", name) for name in variables]
    params += [
        ("year1", str(start.year)),
        ("month1", str(start.month)),
        ("day1", str(start.day)),
        ("year2", str(end_exclusive.year)),
        ("month2", str(end_exclusive.month)),
        ("day2", str(end_exclusive.day)),
        ("tz", "Etc/UTC"),
        ("format", "onlycomma"),
        ("latlon", "no"),
        ("elev", "no"),
        ("missing", "M"),
        ("trace", "0.0001"),
        ("direct", "no"),
        ("report_type", "3"),
        ("report_type", "4"),
    ]
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def plan_requests(station_map: dict[str, str], start: date, end: date) -> list[StationRequest]:
    """One request per station and calendar-year chunk, ordered by IATA code then date."""
    chunks = year_chunks(start, end)
    return [StationRequest(iata, station_map[iata], a, b) for iata in sorted(station_map) for a, b in chunks]


def station_years(requests: list[StationRequest]) -> float:
    """Planned volume in station-years (sum of request days / 365.25)."""
    return sum(r.days for r in requests) / 365.25


def check_station_year_limit(requests: list[StationRequest], limit: int = MAX_STATION_YEARS) -> float:
    """Raise ``ValueError`` if the plan exceeds the limit; return the planned station-years."""
    volume = station_years(requests)
    if volume > limit:
        raise ValueError(
            f"Planned {volume:.1f} station-years exceed the limit of {limit}; narrow the range or stations."
        )
    return volume


def resolve_stations(
    targets: list[str], ourairports_csv: Path, stations_file: Path, study_start: date | None
) -> dict[str, str]:
    """{IATA: IEM station id} for every target, OFFLINE (iem_matching). Raises if any target is not 'matched'."""
    require_file(ourairports_csv, "OurAirports airports.csv", "--ourairports")
    require_file(stations_file, "IEM station list (geojson/csv)", "--stations-file")
    results = match_stations(
        targets, load_ourairports(ourairports_csv), read_station_list(stations_file), study_start=study_start
    )
    bad = [f"{m.iata}: {m.status} {m.note}".strip() for m in results if m.status != "matched" or not m.station]
    if bad:
        raise ValueError("IEM station matching is not clean; fix before downloading: " + "; ".join(bad))
    return {m.iata: str(m.station) for m in results}


def validate_csv_text(text: str, station: str) -> int:
    """Check an IEM response and return its number of data rows.

    Must have the header ``station,valid,...``, at least one data row, and every row must belong to ``station``.
    Anything else (HTML error page, empty answer, other station) raises ``ValueError``.
    """
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        raise ValueError("Empty response.")
    header = [part.strip().lower() for part in lines[0].split(",")]
    if header[:2] != ["station", "valid"]:
        raise ValueError(f"Unexpected response header (error page?): {lines[0][:80]!r}")
    rows = lines[1:]
    if not rows:
        raise ValueError(f"No observations returned for station {station}.")
    foreign = [line for line in rows if line.split(",", 1)[0].strip().upper() != station.upper()]
    if foreign:
        raise ValueError(f"{len(foreign)} row(s) belong to another station than {station}: {foreign[0][:80]!r}")
    return len(rows)


# ----------------------------------------------------------------------------
# NETWORK (the only function that goes online)
# ----------------------------------------------------------------------------


def fetch_url(url: str) -> bytes:
    """GET ``url`` and return the body (size-limited). NETWORK CALL; no retry."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
        body: bytes = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Response exceeded the expected size limit; stopped.")
    return body


# ----------------------------------------------------------------------------
# core (the fetcher is injected -> testable without network)
# ----------------------------------------------------------------------------


def _write_summary(path: Path | None, summary: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def run(
    requests: list[StationRequest],
    out_dir: Path,
    *,
    fetch: Fetcher = fetch_url,
    wait_sec: float = DEFAULT_WAIT_SEC,
    sleep: Callable[[float], None] = time.sleep,
    summary_path: Path | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Download the requests in order. Stops at the first error (no retry). Returns the summary dict."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "requests": [],
        "has_error": False,
        "parameters": {"wait_sec": wait_sec, "request_count": len(requests), "variables": list(IEM_VARIABLES)},
        "station_years_planned": round(station_years(requests), 3),
    }
    fetched = 0
    for request in requests:
        label = f"{request.station} {request.start}..{request.end}"
        record: dict[str, Any] = {
            "iata": request.iata,
            "station": request.station,
            "start": str(request.start),
            "end": str(request.end),
            "file": request.filename,
            "status": None,
        }
        summary["requests"].append(record)
        target = out_dir / request.filename
        try:
            if target.is_file():
                record["status"] = "skipped_exists"
                log(f"[{label}] skipped (file exists)")
                continue
            if fetched > 0 and wait_sec > 0:
                sleep(wait_sec)
            url = build_request_url(request.station, request.start, request.end)
            record["url"] = url
            log(f"[{label}] downloading...")
            body = fetch(url)
            fetched += 1
            text = body.decode("utf-8")  # strict: a decoding problem is an error, not a replacement character
            rows = validate_csv_text(text, request.station)
            partial = target.with_name(target.name + ".part")
            partial.write_bytes(body)
            partial.replace(target)
            record.update(
                {"status": "downloaded", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "rows": rows}
            )
        except Exception as e:  # stop at the first error and report it (no retry)
            record["status"] = "error"
            record["error"] = f"{type(e).__name__}: {e}"
            summary["has_error"] = True
            log(f"[{label}] ERROR: {record['error']} -- stopping (no retry).")
            break
        finally:
            _write_summary(summary_path, summary)
    summary["not_attempted"] = max(0, len(requests) - len(summary["requests"]))
    _write_summary(summary_path, summary)
    return summary


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Date format must be YYYY-MM-DD, given: {text!r}") from e


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="IEM ASOS/METAR downloader for the target airports (NETWORK CALLS; needs the user's approval)."
    )
    parser.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD (UTC day, inclusive).")
    parser.add_argument("--end", type=_parse_date, required=True, help="YYYY-MM-DD (UTC day, inclusive).")
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS_FILE)
    parser.add_argument("--ourairports", type=Path, default=DEFAULT_AIRPORTS)
    parser.add_argument("--stations-file", type=Path, default=DEFAULT_STATIONS_FILE, help="IEM station list file.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--only", default=None, help="Comma-separated IATA subset of the targets (small trial).")
    parser.add_argument("--wait-sec", type=float, default=DEFAULT_WAIT_SEC)
    parser.add_argument("--max-station-years", type=int, default=MAX_STATION_YEARS)
    parser.add_argument("--dry-run", action="store_true", help="Only print the plan; no network, no files written.")
    args = parser.parse_args(argv)

    targets = read_targets(args.targets_file)
    if args.only:
        wanted = [code.strip().upper() for code in args.only.split(",") if code.strip()]
        unknown = [code for code in wanted if code not in targets]
        if unknown:
            parser.error(f"--only contains airports that are not in the target list: {unknown}")
        targets = wanted
    station_map = resolve_stations(targets, args.ourairports, args.stations_file, args.start)
    requests = plan_requests(station_map, args.start, args.end)
    volume = check_station_year_limit(requests, args.max_station_years)

    if args.dry_run:
        print(f"{len(requests)} requests, {volume:.1f} station-years (limit {args.max_station_years}).")
        for request in requests:
            print(f"{request.iata} {request.station} {request.start}..{request.end} -> {request.filename}")
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / STATION_MAP_NAME).write_text(
        json.dumps(station_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = run(requests, args.out_dir, wait_sec=args.wait_sec, summary_path=args.out_dir / SUMMARY_NAME)
    statuses: dict[str, int] = {}
    for record in summary["requests"]:
        statuses[record["status"]] = statuses.get(record["status"], 0) + 1
    print(f"Summary: {statuses}; not attempted: {summary['not_attempted']}; details: {args.out_dir / SUMMARY_NAME}")
    return 1 if summary["has_error"] else 0


if __name__ == "__main__":
    sys.exit(main())
