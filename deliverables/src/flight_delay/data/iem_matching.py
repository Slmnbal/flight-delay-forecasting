"""IEM ASOS station code <-> IATA matching check (assumption A4) -- NO NETWORK.

This script never goes online. The user downloads the IEM station list BY HAND and passes it as a
file (CSV or GeoJSON). Expected source: IEM network station lists (e.g. the US ASOS networks under
mesonet.agron.iastate.edu/sites/networks.php; the exact export address and column names were NOT
VERIFIED -- so the column name candidates are flexible; if none is recognised the script prints the
columns it saw and stops).

Matching rule (for every target IATA, in order):
  1) station code == IATA              (in the US, IEM mostly uses the 3-letter FAA/IATA code [assumption])
  2) station code == 'K' + IATA        (ICAO form, contiguous US)
  3) station code == OurAirports ICAO/ident
The station's coordinates must be within MAX_KM of the OurAirports coordinates (to catch a wrong-airport
match; the 10 km threshold is the author's choice, NOT a verified standard).
Optionally: does the station archive start before the study start?

Statuses: matched | location_mismatch | archive_insufficient | not_found

Usage:
  python -m flight_delay.data.iem_matching --stations <iem.csv|geojson> \\
      --ourairports <airports.csv> --targets ORD,ATL,DEN --study-start 2024-01-01
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from flight_delay.data.airports import load_ourairports
from flight_delay.paths import DATA_DIR

__all__ = [
    "ARCHIVE_CANDIDATES",
    "CHECKLIST",
    "ID_CANDIDATES",
    "LAT_CANDIDATES",
    "LON_CANDIDATES",
    "MAX_KM",
    "Match",
    "haversine_km",
    "main",
    "match_stations",
    "read_station_list",
    "report_markdown",
]

MAX_KM = 10.0

ID_CANDIDATES = ("stid", "sid", "station", "station_id", "stationid", "id", "faa", "iem_id")
LAT_CANDIDATES = ("lat", "latitude", "y")
LON_CANDIDATES = ("lon", "lng", "longitude", "x")
ARCHIVE_CANDIDATES = ("archive_begin", "archive_start", "begin", "start", "sts")


@dataclass
class Match:
    iata: str
    status: str
    station: str | None = None
    rule: str | None = None
    distance_km: float | None = None
    archive_start: str | None = None
    note: str = ""


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _find(columns: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    return next((columns[a] for a in candidates if a in columns), None)


def read_station_list(path: Path) -> pd.DataFrame:
    """Convert an IEM station list (csv or geojson) to standard columns: code, lat, lon, archive."""
    path = Path(path)
    if path.suffix.lower() in (".json", ".geojson"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for feature in payload.get("features", []):
            props = dict(feature.get("properties", {}))
            coordinates = (feature.get("geometry") or {}).get("coordinates") or [None, None]
            props.setdefault("lon", coordinates[0])
            props.setdefault("lat", coordinates[1])
            rows.append(props)
        frame = pd.DataFrame(rows)
    else:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    columns = {str(c).strip().lower(): c for c in frame.columns}
    id_col = _find(columns, ID_CANDIDATES)
    lat_col = _find(columns, LAT_CANDIDATES)
    lon_col = _find(columns, LON_CANDIDATES)
    if not (id_col and lat_col and lon_col):
        raise ValueError(
            "Station list: code/lat/lon columns were not recognised. Columns seen: "
            f"{list(frame.columns)}. Edit the ID_CANDIDATES/LAT_CANDIDATES/LON_CANDIDATES lists."
        )
    archive_col = _find(columns, ARCHIVE_CANDIDATES)
    return (
        pd.DataFrame(
            {
                "code": frame[id_col].astype(str).str.strip().str.upper(),
                "lat": pd.to_numeric(frame[lat_col], errors="coerce"),
                "lon": pd.to_numeric(frame[lon_col], errors="coerce"),
                "archive": frame[archive_col].astype(str).str.strip() if archive_col else "",
            }
        )
        .drop_duplicates("code", keep="first")
        .reset_index(drop=True)
    )


def _archive_date(text: str) -> date | None:
    try:
        return pd.to_datetime(text, errors="raise").date() if text else None
    except (ValueError, TypeError):
        return None


def match_stations(
    targets: list[str],
    airports: pd.DataFrame,
    stations: pd.DataFrame,
    max_km: float = MAX_KM,
    study_start: date | None = None,
) -> list[Match]:
    """Produce a match result for every target IATA (none is silently skipped)."""
    station_index = stations.set_index("code")
    airport_index = airports.set_index("iata")
    results: list[Match] = []
    for iata in [t.strip().upper() for t in targets]:
        if iata not in airport_index.index:
            results.append(Match(iata, "not_found", note="not in OurAirports (coordinates cannot be verified)"))
            continue
        airport = airport_index.loc[iata]
        icao = str(airport.get("icao", "") or "")
        candidates = [(iata, "iata"), ("K" + iata, "K+iata")]
        if icao:
            candidates.append((icao, "ourairports_icao"))
        chosen = next(((code, rule) for code, rule in candidates if code in station_index.index), None)
        if chosen is None:
            results.append(Match(iata, "not_found", note=f"codes tried: {[c for c, _ in candidates]}"))
            continue
        code, rule = chosen
        station = station_index.loc[code]
        distance = None
        if (
            pd.notna(station["lat"])
            and pd.notna(station["lon"])
            and pd.notna(airport["lat"])
            and pd.notna(airport["lon"])
        ):
            distance = round(
                haversine_km(
                    float(airport["lat"]), float(airport["lon"]), float(station["lat"]), float(station["lon"])
                ),
                2,
            )
        archive = str(station["archive"]) if "archive" in station.index else ""
        status, note = "matched", ""
        if distance is None:
            status, note = "location_mismatch", "coordinates missing; location could not be verified"
        elif distance > max_km:
            status, note = "location_mismatch", f"station is {distance} km from the airport (> {max_km} km)"
        elif study_start is not None:
            archive_start = _archive_date(archive)
            if archive_start is None:
                note = "archive start could not be read; check by hand"
            elif archive_start > study_start:
                status, note = "archive_insufficient", f"archive starts on {archive_start} (> {study_start})"
        results.append(Match(iata, status, code, rule, distance, archive or None, note))
    return results


CHECKLIST = """\
## IEM matching checklist (A4)
- [ ] The station list file was downloaded from IEM by hand; columns were recognised (the script did not fail).
- [ ] Every target airport has status 'matched' (or the reason is written down and a decision was made).
- [ ] 'location_mismatch' rows were inspected by hand (wrong airport / another station with the same code?).
- [ ] 'archive_insufficient' rows were removed or the study period was narrowed.
- [ ] 'not_found' rows were removed from the target list; the remaining airport count is >= the scope rule's lower bound.
- [ ] Weather data will be requested in UTC (IEM time zone option: UTC); BTS local time was converted to UTC with time_conversion.
- [ ] The IEM request limit (1,000 station-years) is not exceeded: airports x years <= 1,000 (research report [D]).
- [ ] An attribution note was added: IEM (Iowa Environmental Mesonet) is cited as the source.
"""


def report_markdown(results: list[Match]) -> str:
    lines = [
        "| IATA | Status | Station | Rule | Distance (km) | Archive start | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in results:
        lines.append(
            f"| {m.iata} | {m.status} | {m.station or ''} | {m.rule or ''} | "
            f"{'' if m.distance_km is None else m.distance_km} | {m.archive_start or ''} | {m.note} |"
        )
    counts = pd.Series([m.status for m in results]).value_counts().to_dict() if results else {}
    return "\n".join(lines) + f"\n\nStatus counts: {counts}\n\n" + CHECKLIST


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IEM station <-> IATA matching check (no network).")
    parser.add_argument("--stations", type=Path, required=True)
    parser.add_argument("--ourairports", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--targets", help="Comma-separated IATA codes (e.g. ORD,ATL).")
    group.add_argument("--targets-file", type=Path, help="One IATA code per line.")
    parser.add_argument("--study-start", default=None, help="YYYY-MM-DD; for the archive start check.")
    parser.add_argument("--max-km", type=float, default=MAX_KM)
    parser.add_argument("--output-json", type=Path, default=DATA_DIR / "iem-matching-result.json")
    parser.add_argument("--output-md", type=Path, default=DATA_DIR / "iem-matching-result.md")
    args = parser.parse_args(argv)

    if args.targets:
        targets = [x for x in args.targets.split(",") if x.strip()]
    else:
        targets = [line.strip() for line in args.targets_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    study_start = date.fromisoformat(args.study_start) if args.study_start else None
    results = match_stations(
        targets, load_ourairports(args.ourairports), read_station_list(args.stations), args.max_km, study_start
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps([asdict(m) for m in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = report_markdown(results)
    args.output_md.write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
