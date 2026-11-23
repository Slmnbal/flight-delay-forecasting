"""IEM ASOS/METAR CSV files -> cleaned ``metar`` table (NO NETWORK).

Input: the CSV files written by ``download_iem`` (IEM ``asos.py`` output, ``format=onlycomma``, UTC).
Output: ``<layer>/metar/metar.parquet`` (+ ``metar-stats.json`` next to it): one row per station and
observation time, columns ``station, iata, observed_utc`` + the weather variables (``IEM_VARIABLES``).

CLEANING RULES (all counted in the stats file; no value is invented):
  1. IEM marks missing values with "M" (``missing=M`` request option) -> NaN / <NA>. Rows with an unparseable
     ``valid`` timestamp cannot be placed in time: they are DROPPED and counted ("rows_bad_time").
  2. Rows of a station that is not in the station map are dropped and counted ("rows_unknown_station").
  3. Physically impossible numeric values become NaN (IEM states that it applies very little quality control).
     The plausible ranges in ``NUMERIC_RANGES`` are the AUTHOR'S choice (not a validated standard);
     counts per variable are in the stats ("out_of_range").
  4. Duplicates (same station and ``observed_utc``; e.g. a METAR and a SPECI in the same minute, or the
     overlap of two downloaded files): keep ONE row, the one with the most non-missing values; ties ->
     the row that comes later in file order (files are read in sorted file-name order).
  5. ``observed_utc`` is tz-less (UTC-meaning) datetime64[ns], like all ``*_utc`` columns of the layer.
  6. Report type (METAR vs SPECI) is not kept: it is not a column of the requested IEM output.

Usage:
  python -m flight_delay.data.metar --raw-dir deliverables/data/raw/iem_asos
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.inputs import require_file
from flight_delay.data.layer import DEFAULT_LAYER_DIR
from flight_delay.data.tables import write_parquet_atomic

__all__ = [
    "IEM_NUMERIC_VARIABLES",
    "IEM_TEXT_VARIABLES",
    "IEM_VARIABLES",
    "METAR_TABLE",
    "NUMERIC_RANGES",
    "build_metar_table",
    "clean_metar",
    "main",
    "read_iem_csv",
]

METAR_TABLE = "metar"

# IEM variable names (the asos.py ``data`` parameter). Only what the modeling plan needs (section 10.1).
IEM_NUMERIC_VARIABLES = (
    "tmpf",  # air temperature, deg F
    "dwpf",  # dew point, deg F
    "relh",  # relative humidity, %
    "drct",  # wind direction, deg
    "sknt",  # wind speed, knots
    "gust",  # wind gust, knots
    "vsby",  # visibility, miles
    "alti",  # altimeter, inches of mercury
    "p01i",  # precipitation of the last hour, inches
    "skyl1",  # sky level 1 height, feet
    "skyl2",
    "skyl3",
    "skyl4",
)
IEM_TEXT_VARIABLES = ("skyc1", "skyc2", "skyc3", "skyc4", "wxcodes")  # sky cover codes, present-weather codes
IEM_VARIABLES = IEM_NUMERIC_VARIABLES + IEM_TEXT_VARIABLES

# Plausible physical ranges (inclusive). AUTHOR'S CHOICE, not verified against a standard; values outside become NaN.
NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "tmpf": (-90.0, 140.0),
    "dwpf": (-100.0, 140.0),
    "relh": (0.0, 100.0),
    "drct": (0.0, 360.0),
    "sknt": (0.0, 250.0),
    "gust": (0.0, 300.0),
    "vsby": (0.0, 100.0),
    "alti": (25.0, 33.0),
    "p01i": (0.0, 10.0),
    "skyl1": (0.0, 100000.0),
    "skyl2": (0.0, 100000.0),
    "skyl3": (0.0, 100000.0),
    "skyl4": (0.0, 100000.0),
}

_TIME_FORMAT = "%Y-%m-%d %H:%M"


def read_iem_csv(path: Path) -> pd.DataFrame:
    """Read one IEM ``onlycomma`` CSV as text (comment lines starting with '#' are skipped)."""
    frame = pd.read_csv(path, comment="#", dtype=str, keep_default_na=False)
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    missing = [c for c in ("station", "valid") if c not in frame.columns]
    if missing:
        raise ValueError(f"{path.name}: expected IEM columns missing: {missing}; columns seen: {list(frame.columns)}")
    return frame


def clean_metar(raw: pd.DataFrame, station_to_iata: dict[str, str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply the cleaning rules (module docstring). Returns (table sorted by station, observed_utc; stats)."""
    stats: dict[str, Any] = {"rows_in": int(len(raw))}
    frame = pd.DataFrame(index=raw.index)
    frame["station"] = raw["station"].astype(str).str.strip().str.upper()
    frame["observed_utc"] = pd.to_datetime(raw["valid"].astype(str).str.strip(), format=_TIME_FORMAT, errors="coerce")
    frame["observed_utc"] = frame["observed_utc"].astype("datetime64[ns]")
    known = {k.upper(): v for k, v in station_to_iata.items()}
    frame["iata"] = frame["station"].map(known)
    for name in IEM_VARIABLES:
        if name in raw.columns:
            frame[name] = raw[name]
        else:
            frame[name] = pd.NA

    stats["rows_bad_time"] = int(frame["observed_utc"].isna().sum())
    stats["rows_unknown_station"] = int((frame["iata"].isna() & frame["observed_utc"].notna()).sum())
    frame = frame[frame["observed_utc"].notna() & frame["iata"].notna()].copy()

    out_of_range: dict[str, int] = {}
    for name in IEM_NUMERIC_VARIABLES:
        values = pd.to_numeric(frame[name].astype("string"), errors="coerce").astype("float64")  # "M" -> NaN
        low, high = NUMERIC_RANGES[name]
        impossible = values.notna() & ((values < low) | (values > high))
        if int(impossible.sum()):
            out_of_range[name] = int(impossible.sum())
        frame[name] = values.mask(impossible)
    for name in IEM_TEXT_VARIABLES:
        text = frame[name].astype("string").str.strip()
        frame[name] = text.mask(((text == "M") | (text == "")).fillna(False))
    stats["out_of_range"] = out_of_range

    # duplicate rule: most non-missing values wins; tie -> later row in file order
    frame["_filled"] = frame[list(IEM_VARIABLES)].notna().sum(axis=1)
    frame["_order"] = np.arange(len(frame))
    frame = frame.sort_values(["station", "observed_utc", "_filled", "_order"], kind="mergesort")
    duplicate = frame.duplicated(["station", "observed_utc"], keep="last")
    stats["duplicates_removed"] = int(duplicate.sum())
    frame = frame[~duplicate].drop(columns=["_filled", "_order"]).reset_index(drop=True)
    stats["rows_out"] = int(len(frame))
    return frame[["station", "iata", "observed_utc", *IEM_VARIABLES]], stats


def build_metar_table(raw_dir: Path, station_map: dict[str, str], output: Path) -> dict[str, Any]:
    """Read every CSV in ``raw_dir`` (sorted by name), clean, write ``output`` (Parquet) and the stats JSON.

    ``station_map`` is {IATA: IEM station id}. Every station of the map must have at least one row,
    otherwise a ``ValueError`` is raised (a silent hole in the weather data would be worse).
    """
    raw_dir = Path(raw_dir)
    files = sorted(raw_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No IEM csv files in {raw_dir} (run flight_delay.data.download_iem first).")
    raw = pd.concat([read_iem_csv(path) for path in files], ignore_index=True)
    table, stats = clean_metar(raw, {station: iata for iata, station in station_map.items()})
    absent = sorted(set(station_map) - set(table["iata"].dropna().astype(str)))
    if absent:
        raise ValueError(f"No observations for these airports (check the downloads): {absent}")
    per_station = table.groupby("iata")["observed_utc"].agg(["count", "min", "max"])
    stats["files"] = [path.name for path in files]
    stats["per_station"] = {
        str(iata): {"rows": int(row["count"]), "first_utc": str(row["min"]), "last_utc": str(row["max"])}
        for iata, row in per_station.iterrows()
    }
    write_parquet_atomic(table, output)
    Path(output).with_name("metar-stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean the downloaded IEM files into the metar table (no network).")
    parser.add_argument("--raw-dir", type=Path, required=True, help="Folder with the download_iem CSV files.")
    parser.add_argument("--station-map", type=Path, default=None, help="station_map.json (default: <raw-dir>/...).")
    parser.add_argument("--output", type=Path, default=DEFAULT_LAYER_DIR / METAR_TABLE / "metar.parquet")
    args = parser.parse_args(argv)
    map_path = args.station_map or (args.raw_dir / "station_map.json")
    require_file(map_path, "IEM station map", "--station-map")
    station_map: dict[str, str] = json.loads(Path(map_path).read_text(encoding="utf-8"))
    stats = build_metar_table(args.raw_dir, station_map, args.output)
    print(json.dumps({k: v for k, v in stats.items() if k != "per_station"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
