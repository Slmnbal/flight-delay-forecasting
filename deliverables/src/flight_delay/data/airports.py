"""OurAirports loader and IATA -> IANA time zone map (NO NETWORK).

Airport -> IANA time zone mapping:
  The OurAirports airports.csv is ASSUMED to have NO time zone column (NOT VERIFIED: check the file
  header yourself). Hence the priority order:
    1) manual override JSON {"IATA": "Zone/Name"} (highest priority),
    2) a time zone column in the file, if any (candidate names: timezone, tz, tz_database_time_zone, time_zone),
    3) ``timezonefinder`` from latitude_deg/longitude_deg (OPTIONAL dependency; skipped if not installed).
  Airports that cannot be mapped are NEVER invented; they are returned in the ``missing`` list.
"""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

__all__ = ["TZ_COLUMN_CANDIDATES", "build_tz_map", "load_ourairports"]

TZ_COLUMN_CANDIDATES = ("timezone", "tz", "tz_database_time_zone", "time_zone")
_TYPE_ORDER = {"large_airport": 0, "medium_airport": 1, "small_airport": 2}


def load_ourairports(path: Path) -> pd.DataFrame:
    """Read OurAirports airports.csv; return the rows that have an IATA code.

    Output columns: iata, icao, type, service, lat, lon, tz_field (if present in the file, else NaN).
    If the same IATA appears on several rows (closed/old records) a deterministic rule applies:
    type (large < medium < small < other), then scheduled_service == 'yes', then ident order.
    """
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    columns = {c.lower(): c for c in frame.columns}
    required = ("iata_code", "latitude_deg", "longitude_deg")
    missing = [c for c in required if c not in columns]
    if missing:
        raise ValueError(f"Expected columns missing from the OurAirports file: {missing}")

    def column(name: str) -> pd.Series:
        return frame[columns[name]] if name in columns else pd.Series("", index=frame.index)

    tz_column = next((columns[a] for a in TZ_COLUMN_CANDIDATES if a in columns), None)
    result = pd.DataFrame(
        {
            "iata": column("iata_code").str.strip().str.upper(),
            "icao": column("ident").str.strip().str.upper(),
            "type": column("type").str.strip(),
            "service": column("scheduled_service").str.strip().str.lower(),
            "lat": pd.to_numeric(column("latitude_deg"), errors="coerce"),
            "lon": pd.to_numeric(column("longitude_deg"), errors="coerce"),
            "tz_field": frame[tz_column].str.strip() if tz_column else np.nan,
        }
    )
    result = result[result["iata"] != ""].copy()
    result["_type_rank"] = result["type"].map(_TYPE_ORDER).fillna(9)
    result["_service_rank"] = (result["service"] != "yes").astype(int)
    result = result.sort_values(["iata", "_type_rank", "_service_rank", "icao"], kind="mergesort")
    result = result.drop_duplicates("iata", keep="first").drop(columns=["_type_rank", "_service_rank"])
    return result.reset_index(drop=True)


def build_tz_map(
    airports: pd.DataFrame,
    target_iata: list[str] | None = None,
    manual: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """IATA -> IANA time zone. Returns (map, missing).

    Priority: manual > file column > timezonefinder (if installed). Nothing is invented:
    every airport that cannot be resolved (or is invalid) is returned in ``missing`` with a reason.
    """
    manual = {k.strip().upper(): v for k, v in (manual or {}).items()}
    finder = None
    try:  # optional dependency
        from timezonefinder import TimezoneFinder

        finder = TimezoneFinder()
    except ImportError:
        pass

    rows = airports.set_index("iata", drop=False)
    targets = [h.strip().upper() for h in target_iata] if target_iata else list(rows.index)
    tz_map: dict[str, str] = {}
    missing: list[dict[str, str]] = []
    for iata in targets:
        candidate: str | None = None
        source = None
        if iata in manual:
            candidate, source = manual[iata], "manual"
        elif iata in rows.index:
            row = rows.loc[iata]
            tz_field = row.get("tz_field")
            if isinstance(tz_field, str) and tz_field.strip():
                candidate, source = tz_field.strip(), "file_column"
            elif finder is not None and pd.notna(row["lat"]) and pd.notna(row["lon"]):
                candidate = finder.timezone_at(lat=float(row["lat"]), lng=float(row["lon"]))
                source = "timezonefinder"
        else:
            missing.append({"iata": iata, "reason": "not in OurAirports"})
            continue
        if not candidate:
            reason = "time zone could not be derived (no column; timezonefinder not installed or no result)"
            missing.append({"iata": iata, "reason": reason})
            continue
        try:
            ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            missing.append({"iata": iata, "reason": f"invalid IANA name: {candidate!r} ({source})"})
            continue
        tz_map[iata] = candidate
    return tz_map, missing
