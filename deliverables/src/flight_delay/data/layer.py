"""Monthly base data layer: BTS On-Time CSV/zip -> partitioned Parquet tables (NO NETWORK).

Each month is processed SEPARATELY (never all months in memory). Output (per month, hive-style folders):
  <layer>/flights/year=YYYY/month=MM/part-0.parquet            schedule + UTC + flags only (feature side)
  <layer>/flights/year=YYYY/month=MM/summary.json              row counts, tz gaps, density counts, sha256, ...
  <layer>/flight_labels/year=YYYY/month=MM/part-0.parquet      outcomes (ArrDelay, Cancelled, actual UTC, ...)
  <layer>/flight_keys/year=YYYY/month=MM/part-0.parquet        Tail_Number (LOCAL ONLY, never exported)
  <layer>/scheduled_density/year=YYYY/month=MM/part-0.parquet  scheduled traffic of ALL BTS flights (no scope filter)
Table design and column documentation: deliverables/data/LAYER_SCHEMA.md; code: ``tables.py``.
A month counts as "processed" only if the flights Parquet AND summary.json exist (the other tables are
written first; the Parquet is first written to .tmp and then moved into place; summary.json is written last).

SCOPE (which rows are kept in flights / flight_labels / flight_keys) -- the ``scope`` parameter:
  "origin" (DEFAULT): Origin is in the 30 target airports. Rationale: the prediction unit is "a
      departure"; departure airport weather (IEM) and traffic features depend on Origin; the scope
      decision (M3) was made on departure share (64% in July 2025). The scope filter is by ORIGIN
      (M3 plan decision); destination weather is joined only for the 30 targets (weather_join).
  "origin_or_dest": Origin OR Dest is a target. Rationale: for rotation (the previous leg of the same
      tail number, "past_realized" features) the previous leg of a flight departing a target airport
      is mostly a flight ARRIVING at the target; the previous leg's Origin may be outside the targets.
      This mode keeps those too. The row count grows (by how much was NOT MEASURED). In both cases the
      ``target_origin`` / ``target_dest`` flags are written; the data scientist filters by flag later.
  "origin_and_dest": both are targets (only flights between targets; narrow, for trials).
The scheduled_density table is NOT affected by the scope (it is computed before the filter).

TRANSFORMATION RULES (all documented; the ONLY row drops are the scope filter and rule 9, the missing-key drop):
  1. Column names are matched case-insensitively; columns outside RAW_COLUMNS are dropped (column
     pruning). Div* fields and city/state fields are deliberately not taken.
  2. Origin/Dest are stripped and upper-cased.
  3. Types: the RAW_COLUMNS dict. Values that cannot be converted to numbers become NaN and are COUNTED
     (summary.json "non_numeric_counts"). Integer types (Int*) are converted safely; a fractional value
     raises ValueError (no silent rounding). Minute columns are float32 so they can carry NaN (BTS
     minutes are integers; quality.py counts fractional values separately).
  4. UTC: time_conversion. ALL ``*_utc`` columns are UTC and stored as timestamps WITHOUT time zone
     (naive), so DuckDB/pandas need no pytz. SCHEDULE: crs_dep_utc, crs_arr_utc (flights table).
     ACTUAL (flight_labels only; CANNOT be features): dep_utc = crs_dep_utc + DepDelay minutes,
     arr_utc = crs_arr_utc + ArrDelay minutes (M2 fix: no 12-hour assumption). Cancelled flights have
     dep_utc and arr_utc = NaT; diverted flights have arr_utc = NaT; ``dep_utc_reason`` /
     ``arr_utc_reason`` say why ("cancelled" | "diverted" | "crs_utc_missing" | "delay_missing").
  5. An airport whose time zone cannot be mapped is NEVER invented: the related UTC is NaT and
     ``utc_tz_missing=True``.
  6. ``flight_id`` = YYYYMMDD_Airline_FlightNo_Origin_Dest_CRSDepTime (uniqueness is NOT GUARANTEED;
     quality.py counts duplicates). ``flight_uid`` (int64) = stable hash of flight_id + occurrence number.
  7. Sort: FlightDate, crs_dep_utc, Origin, Dest, Reporting_Airline, flight number (stable sort)
     -> the same input gives the same Parquet content.
  8. scheduled_density: computed from ALL raw rows of the month (cancelled included, before the scope
     filter): per airport x local date x local hour, scheduled departures (by Origin, CRS departure local
     time) and scheduled arrivals (by Dest, CRS arrival local time). Arrivals whose local time cannot be
     resolved are counted in summary.json ("density_arrivals_without_local_time"), not guessed.
  9. Missing-key drop (user decision, 2024-08 finding): after the scope filter and the type cast, a row in which ANY
     field of ``KEY_FIELDS_FILLED`` is empty is NOT written to flights / flight_labels / flight_keys. The count
     (``rows_dropped_missing_key``, per field ``dropped_missing_key_by_field``) goes to summary.json and
     download-range-summary.json; quality.py reports it as ``dropped_missing_key_rows``. scheduled_density is NOT
     affected (it is computed from raw rows before this step). ``key_field_missing`` in quality.py stays critical:
     the layer must now never contain an empty key field.

Usage (one month):
  python -m flight_delay.data.layer --input deliverables/data/raw/ontime_2025_07.zip --year 2025 --month 7
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.airports import build_tz_map, load_ourairports
from flight_delay.data.csv_io import column_selector, read_csv
from flight_delay.data.inputs import require_file
from flight_delay.data.tables import (
    DENSITY,
    FLIGHTS,
    KEYS,
    LABELS,
    compute_scheduled_density,
    make_flight_uid,
    split_tables,
    write_parquet_atomic,
)
from flight_delay.data.time_conversion import (
    actual_utc_series,
    arrival_utc_series,
    hhmm_minutes_series,
    local_clock_series,
    local_to_utc_series,
)
from flight_delay.paths import DATA_DIR

__all__ = [
    "DEFAULT_AIRPORTS",
    "DEFAULT_LAYER_DIR",
    "DEFAULT_TARGETS_FILE",
    "DEFAULT_TZ_OVERRIDES",
    "KEY_FIELDS_FILLED",
    "OUTPUT_SCHEMA",
    "PARQUET_NAME",
    "RAW_COLUMNS",
    "REQUIRED_RAW",
    "SCOPE_MODES",
    "SUMMARY_NAME",
    "is_month_processed",
    "load_airports",
    "load_tz_overrides",
    "main",
    "month_dir",
    "process_month",
    "read_targets",
    "read_wide_month",
    "table_dir",
]

DEFAULT_LAYER_DIR = DATA_DIR / "layer"
DEFAULT_TARGETS_FILE = DATA_DIR / "target-airports.txt"
DEFAULT_AIRPORTS = DATA_DIR / "raw" / "airports.csv"
DEFAULT_TZ_OVERRIDES = DATA_DIR / "raw" / "tz_overrides.json"

SCOPE_MODES = ("origin", "origin_or_dest", "origin_and_dest")
PARQUET_NAME = "part-0.parquet"
SUMMARY_NAME = "summary.json"

# Raw column -> target type. "text" | "date" | "float32" | pandas nullable integer name.
# (The feature/forbidden split stays in feature_contract.py: forbidden fields are LOADED here too,
#  because the target/label, rotation and audit need them.)
RAW_COLUMNS: dict[str, str] = {
    "Year": "Int16",
    "Quarter": "Int8",
    "Month": "Int8",
    "DayofMonth": "Int8",
    "DayOfWeek": "Int8",
    "FlightDate": "date",
    "Reporting_Airline": "text",
    "Flight_Number_Reporting_Airline": "Int32",
    "Tail_Number": "text",
    "OriginAirportID": "Int32",
    "Origin": "text",
    "DestAirportID": "Int32",
    "Dest": "text",
    # schedule
    "CRSDepTime": "Int16",
    "CRSArrTime": "Int16",
    "CRSElapsedTime": "float32",
    "Distance": "float32",
    "DistanceGroup": "Int8",
    # actual (cannot be features)
    "DepTime": "Int16",
    "DepDelay": "float32",
    "DepDelayMinutes": "float32",
    "DepDel15": "Int8",
    "TaxiOut": "float32",
    "WheelsOff": "Int16",
    "WheelsOn": "Int16",
    "TaxiIn": "float32",
    "ArrTime": "Int16",
    "ArrDelay": "float32",
    "ArrDelayMinutes": "float32",
    "ArrDel15": "Int8",
    "ActualElapsedTime": "float32",
    "AirTime": "float32",
    # cancellation / diversion
    "Cancelled": "Int8",
    "CancellationCode": "text",
    "Diverted": "Int8",
    # delay causes (reported after the delay; cannot be features)
    "CarrierDelay": "float32",
    "WeatherDelay": "float32",
    "NASDelay": "float32",
    "SecurityDelay": "float32",
    "LateAircraftDelay": "float32",
}

# Single source of the "identity fields must be filled" list. Defined here (quality.py imports layer.py, so the
# constant cannot live in quality.py without a circular import); quality.KEY_FIELDS_FILLED is the same object.
# A row with an empty value in any of these is dropped by process_month (rule 9) and checked by quality.key_field_missing.
KEY_FIELDS_FILLED = [
    "FlightDate",
    "Reporting_Airline",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
    "CRSArrTime",
    "Cancelled",
    "Diverted",
]

# If missing, building the layer STOPS (ValueError). Other columns are filled with NA and written to the summary.
REQUIRED_RAW = (
    "FlightDate",
    "Reporting_Airline",
    "Flight_Number_Reporting_Airline",
    "Tail_Number",
    "Origin",
    "Dest",
    "CRSDepTime",
    "DepTime",
    "CRSArrTime",
    "ArrTime",
    "DepDelay",
    "ArrDelay",
    "Cancelled",
    "Diverted",
    "CRSElapsedTime",
    "Distance",
)


def _kind(definition: str) -> str:
    if definition == "text":
        return "text"
    if definition == "date":
        return "datetime"
    if definition == "float32":
        return "float"
    return "integer"


# Output schema of the WIDE month frame (``read_wide_month`` order; the quality checks run on it):
# name -> kind ("integer"|"float"|"text"|"datetime"|"boolean"). On disk it is split into the tables of tables.py.
OUTPUT_SCHEMA: dict[str, str] = {name: _kind(definition) for name, definition in RAW_COLUMNS.items()}
OUTPUT_SCHEMA.update(
    {
        "flight_uid": "integer",
        "flight_id": "text",
        "target_origin": "boolean",
        "target_dest": "boolean",
        "tz_origin": "text",
        "tz_dest": "text",
        "crs_dep_utc": "datetime",
        "crs_arr_utc": "datetime",
        "dep_utc": "datetime",
        "arr_utc": "datetime",
        "dep_utc_reason": "text",
        "arr_utc_reason": "text",
        "crs_dep_local_min": "integer",
        "crs_arr_day_offset": "integer",
        "crs_dep_dst_ambiguous": "boolean",
        "crs_dep_dst_gap": "boolean",
        "crs_arr_dst_ambiguous": "boolean",
        "crs_arr_dst_gap": "boolean",
        "crs_arr_utc_inconsistent": "boolean",
        "utc_tz_missing": "boolean",
    }
)


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def table_dir(root: Path, table: str, year: int, month: int) -> Path:
    """Hive-style partition folder of one table and month: <root>/<table>/year=YYYY/month=MM."""
    return Path(root) / table / f"year={year:04d}" / f"month={month:02d}"


def month_dir(root: Path, year: int, month: int) -> Path:
    """Partition folder of the PRIMARY table (flights); summary.json lives here too."""
    return table_dir(root, FLIGHTS, year, month)


def is_month_processed(root: Path, year: int, month: int) -> bool:
    folder = month_dir(root, year, month)
    return (folder / PARQUET_NAME).is_file() and (folder / SUMMARY_NAME).is_file()


def read_wide_month(root: Path, year: int, month: int) -> pd.DataFrame:
    """Join flights + flight_labels + flight_keys of one month back into the wide frame (OUTPUT_SCHEMA order).

    For the quality checks and local analysis only. Feature code must read ``flights`` alone.
    """
    flights = pd.read_parquet(table_dir(root, FLIGHTS, year, month) / PARQUET_NAME)
    labels = pd.read_parquet(table_dir(root, LABELS, year, month) / PARQUET_NAME)
    keys = pd.read_parquet(table_dir(root, KEYS, year, month) / PARQUET_NAME)
    wide = flights.merge(labels, on="flight_uid", how="inner", validate="one_to_one").merge(
        keys, on="flight_uid", how="inner", validate="one_to_one"
    )
    return wide[list(OUTPUT_SCHEMA)]


def read_targets(path: Path) -> list[str]:
    """One IATA code per line; text after '#' is a comment. Duplicates are dropped (order kept)."""
    require_file(Path(path), "target airport list", "--targets-file")
    codes: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        code = line.split("#")[0].strip().upper()
        if not code:
            continue
        if not re.fullmatch(r"[A-Z0-9]{3}", code):
            raise ValueError(f"Invalid IATA code: {code!r} ({path})")
        if code not in codes:
            codes.append(code)
    if not codes:
        raise ValueError(f"Target list is empty: {path}")
    return codes


def load_airports(path: Path) -> pd.DataFrame:
    require_file(Path(path), "OurAirports airports.csv", "--ourairports")
    return load_ourairports(Path(path))


def load_tz_overrides(path: Path | None) -> dict[str, str]:
    """Manual time zone corrections {"IATA": "Zone/Name"}.

    ``None`` means "run WITHOUT overrides" (an explicit opt-out: CLI ``--no-tz-overrides``). A path that does
    not exist is an ERROR (M5): corrections must never disappear silently.
    """
    if path is None:
        return {}
    require_file(Path(path), "time zone overrides", "--tz-overrides (or pass --no-tz-overrides on purpose)")
    loaded: dict[str, str] = json.loads(Path(path).read_text(encoding="utf-8"))
    return loaded


def _cast_column(series: pd.Series, name: str, definition: str, counters: dict[str, int]) -> pd.Series:
    if definition == "text":
        text = series.astype("string").str.strip()
        return text.replace("", pd.NA)
    if definition == "date":
        return pd.to_datetime(series, errors="coerce").astype("datetime64[ns]")
    before = int(series.notna().sum())
    numeric = pd.to_numeric(series, errors="coerce")
    not_convertible = before - int(numeric.notna().sum())
    if not_convertible:
        counters[name] = not_convertible
    if definition == "float32":
        return numeric.astype("float32")
    try:
        return numeric.astype("float64").astype(definition)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Column {name} could not be safely converted to {definition} (fractional / out-of-range value): {e}"
        ) from e


def _naive_utc(series: pd.Series) -> pd.Series:
    """tz-aware UTC -> tz-less (UTC-meaning) datetime64[ns]."""
    return series.dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[ns]")


def _flight_id(frame: pd.DataFrame) -> pd.Series:
    day = frame["FlightDate"].dt.strftime("%Y%m%d").astype(str)
    time_part = frame["CRSDepTime"].astype("Int64").astype(str).str.zfill(4)
    identifier = (
        day
        + "_"
        + frame["Reporting_Airline"].astype(str)
        + "_"
        + frame["Flight_Number_Reporting_Airline"].astype(str)
        + "_"
        + frame["Origin"].astype(str)
        + "_"
        + frame["Dest"].astype(str)
        + "_"
        + time_part
    )
    return identifier.astype("string")


def _actual_utc(
    crs_utc: pd.Series, delay: pd.Series, cancelled: np.ndarray, diverted: np.ndarray, skip_diverted: bool
) -> tuple[pd.Series, pd.Series]:
    """Actual UTC = CRS UTC + delay minutes, plus a reason for every NaT (M2 fix).

    Priority of reasons: cancelled, (diverted, arrival only), CRS UTC missing, delay missing.
    Returns (tz-aware UTC series, reason series with <NA> where the actual time exists).
    """
    conditions = [cancelled]
    choices = ["cancelled"]
    if skip_diverted:
        conditions.append(diverted)
        choices.append("diverted")
    conditions += [crs_utc.isna().to_numpy(dtype=bool), delay.isna().to_numpy(dtype=bool)]
    choices += ["crs_utc_missing", "delay_missing"]
    reason = pd.Series(np.select(conditions, choices, default=""), index=crs_utc.index)
    reason = reason.replace("", pd.NA).astype("string")
    actual = actual_utc_series(crs_utc, delay).where(reason.isna())
    return actual, reason


# ----------------------------------------------------------------------------
# core
# ----------------------------------------------------------------------------


def process_month(
    input_path: Path,
    year: int,
    month: int,
    output_root: Path,
    targets: list[str],
    airports: pd.DataFrame,
    tz_overrides: dict[str, str] | None = None,
    scope: str = "origin",
) -> dict[str, Any]:
    """Convert one month's CSV/zip into the layer tables and write Parquet. Returns the summary dict."""
    if scope not in SCOPE_MODES:
        raise ValueError(f"scope must be one of {SCOPE_MODES}, given: {scope!r}")
    if not (1 <= month <= 12):
        raise ValueError(f"Invalid month: {month}")
    input_path = Path(input_path)
    targets = [t.strip().upper() for t in targets]
    target_set = set(targets)

    raw = read_csv(input_path, usecols=column_selector(RAW_COLUMNS))
    lookup = {c.lower(): c for c in RAW_COLUMNS}
    raw.columns = [lookup.get(str(c).strip().lower(), str(c).strip()) for c in raw.columns]
    missing = [c for c in RAW_COLUMNS if c not in raw.columns]
    required_missing = [c for c in missing if c in REQUIRED_RAW]
    if required_missing:
        raise ValueError(f"Required column(s) missing from the file: {required_missing} ({input_path.name})")

    rows_raw = int(len(raw))
    for name in ("Origin", "Dest"):
        raw[name] = raw[name].astype("string").str.strip().str.upper()
    for column in missing:  # optional column absent -> empty
        raw[column] = np.nan

    # --- scheduled UTC / local clock for ALL rows (the density needs every flight; scope filter comes later) ---
    all_codes = sorted(set(raw["Origin"].dropna().astype(str)) | set(raw["Dest"].dropna().astype(str)))
    tz_map, tz_missing = build_tz_map(airports, all_codes, tz_overrides)
    tz_origin_all = raw["Origin"].astype(object).map(tz_map).astype(object)
    tz_dest_all = raw["Dest"].astype(object).map(tz_map).astype(object)
    flight_day = pd.to_datetime(raw["FlightDate"], errors="coerce")
    crs_dep_time = pd.to_numeric(raw["CRSDepTime"], errors="coerce")
    crs_arr_time = pd.to_numeric(raw["CRSArrTime"], errors="coerce")

    dep_all = local_to_utc_series(flight_day, crs_dep_time, tz_origin_all)
    arr_all = arrival_utc_series(flight_day, crs_arr_time, tz_dest_all, dep_all["utc"])
    density, arrivals_without_local = compute_scheduled_density(
        raw["Origin"],
        raw["Dest"],
        local_clock_series(flight_day, crs_dep_time),
        local_clock_series(flight_day, crs_arr_time, arr_all["day_offset"]),
    )

    # --- scope filter ---
    origin_hit = raw["Origin"].isin(target_set).to_numpy(dtype=bool)
    dest_hit = raw["Dest"].isin(target_set).to_numpy(dtype=bool)
    mask = {"origin": origin_hit, "origin_or_dest": origin_hit | dest_hit, "origin_and_dest": origin_hit & dest_hit}[
        scope
    ]
    if int(mask.sum()) == 0:
        raise ValueError(
            f"0 rows left after the scope filter ({input_path.name}, scope={scope}): wrong file or wrong target list?"
        )
    data = raw.loc[mask].reset_index(drop=True)
    dep = dep_all.loc[mask].reset_index(drop=True)
    arr = arr_all.loc[mask].reset_index(drop=True)
    tz_origin = tz_origin_all.loc[mask].reset_index(drop=True)
    tz_dest = tz_dest_all.loc[mask].reset_index(drop=True)
    del raw, dep_all, arr_all

    # --- types (done before the actual-UTC step so the missing-key drop can filter every aligned frame at once) ---
    counters: dict[str, int] = {}
    out = pd.DataFrame({name: _cast_column(data[name], name, kind, counters) for name, kind in RAW_COLUMNS.items()})

    # --- missing-key drop (user decision): a row with an EMPTY identity field (KEY_FIELDS_FILLED, evaluated AFTER
    # the cast, so an unparseable value counts as empty) is not written to the layer; it is COUNTED in summary.json ---
    key_empty = out[KEY_FIELDS_FILLED].isna()
    dropped_by_field = {name: int(key_empty[name].sum()) for name in KEY_FIELDS_FILLED}
    drop_mask = key_empty.any(axis=1).to_numpy(dtype=bool)
    rows_dropped_missing_key = int(drop_mask.sum())
    if rows_dropped_missing_key:
        keep = ~drop_mask
        if not keep.any():
            raise ValueError(
                f"0 rows left after dropping rows with an empty key field ({input_path.name}): wrong or corrupt file?"
            )
        data = data.loc[keep].reset_index(drop=True)
        out = out.loc[keep].reset_index(drop=True)
        dep = dep.loc[keep].reset_index(drop=True)
        arr = arr.loc[keep].reset_index(drop=True)
        tz_origin = tz_origin.loc[keep].reset_index(drop=True)
        tz_dest = tz_dest.loc[keep].reset_index(drop=True)

    # --- actual UTC = scheduled UTC + delay minutes (M2): cancelled / diverted -> NaT with a reason ---
    cancelled = (pd.to_numeric(data["Cancelled"], errors="coerce") == 1).to_numpy(dtype=bool)
    diverted = (pd.to_numeric(data["Diverted"], errors="coerce") == 1).to_numpy(dtype=bool)
    dep_actual, dep_reason = _actual_utc(
        dep["utc"], pd.to_numeric(data["DepDelay"], errors="coerce"), cancelled, diverted, skip_diverted=False
    )
    arr_actual, arr_reason = _actual_utc(
        arr["utc"], pd.to_numeric(data["ArrDelay"], errors="coerce"), cancelled, diverted, skip_diverted=True
    )

    out["flight_id"] = _flight_id(out)
    out["target_origin"] = out["Origin"].isin(target_set).to_numpy(dtype=bool)
    out["target_dest"] = out["Dest"].isin(target_set).to_numpy(dtype=bool)
    out["tz_origin"] = tz_origin.astype("string")
    out["tz_dest"] = tz_dest.astype("string")
    out["crs_dep_utc"] = _naive_utc(dep["utc"]).to_numpy()
    out["crs_arr_utc"] = _naive_utc(arr["utc"]).to_numpy()
    out["dep_utc"] = _naive_utc(dep_actual).to_numpy()
    out["arr_utc"] = _naive_utc(arr_actual).to_numpy()
    out["dep_utc_reason"] = dep_reason  # same RangeIndex as ``out`` (string dtype, <NA> = actual time exists)
    out["arr_utc_reason"] = arr_reason
    out["crs_dep_local_min"] = hhmm_minutes_series(pd.to_numeric(data["CRSDepTime"], errors="coerce")).astype("Int16")
    out["crs_arr_day_offset"] = arr["day_offset"].astype("Int8")  # same index (0..n-1)
    out["crs_dep_dst_ambiguous"] = dep["ambiguous"].to_numpy(dtype=bool)
    out["crs_dep_dst_gap"] = dep["gap"].to_numpy(dtype=bool)
    out["crs_arr_dst_ambiguous"] = arr["ambiguous"].to_numpy(dtype=bool)
    out["crs_arr_dst_gap"] = arr["gap"].to_numpy(dtype=bool)
    out["crs_arr_utc_inconsistent"] = arr["inconsistent"].to_numpy(dtype=bool)
    out["utc_tz_missing"] = (tz_origin.isna() | tz_dest.isna()).to_numpy(dtype=bool)

    out = out.sort_values(
        ["FlightDate", "crs_dep_utc", "Origin", "Dest", "Reporting_Airline", "Flight_Number_Reporting_Airline"],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    out["flight_uid"] = make_flight_uid(out["flight_id"])
    out = out[list(OUTPUT_SCHEMA)]

    rows_outside_month = int(((out["FlightDate"].dt.year != year) | (out["FlightDate"].dt.month != month)).sum())

    # --- write: delete the old summary first; other tables, then flights (atomic); summary last ---
    folder = month_dir(output_root, year, month)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SUMMARY_NAME).unlink(missing_ok=True)
    tables = split_tables(out)
    table_bytes: dict[str, int] = {}
    for name in (LABELS, KEYS):
        table_bytes[name] = write_parquet_atomic(tables[name], table_dir(output_root, name, year, month) / PARQUET_NAME)
    table_bytes[DENSITY] = write_parquet_atomic(density, table_dir(output_root, DENSITY, year, month) / PARQUET_NAME)
    table_bytes[FLIGHTS] = write_parquet_atomic(tables[FLIGHTS], folder / PARQUET_NAME)

    scope_codes = set(data["Origin"].dropna().astype(str)) | set(data["Dest"].dropna().astype(str))
    summary = {
        "year": year,
        "month": month,
        "input_file": input_path.name,
        "scope": scope,
        "target_count": len(targets),
        "targets_sha256": hashlib.sha256(",".join(sorted(targets)).encode()).hexdigest(),
        "rows_raw": rows_raw,
        "rows_layer": int(len(out)),
        # rows removed because a KEY_FIELDS_FILLED field was empty (after the scope filter): total, and per field
        # (a row with several empty fields counts once in the total and once per field). rows_raw >= rows_layer holds.
        "rows_dropped_missing_key": rows_dropped_missing_key,
        "dropped_missing_key_by_field": dropped_by_field,
        "rows_target_origin": int(out["target_origin"].sum()),
        "rows_target_dest": int(out["target_dest"].sum()),
        "rows_outside_month": rows_outside_month,
        "column_count": int(out.shape[1]),
        "missing_optional_columns": missing,
        "non_numeric_counts": counters,
        "tz_missing_airports": sorted(e["iata"] for e in tz_missing if e["iata"] in scope_codes),
        "tz_missing_airports_all_rows": sorted(e["iata"] for e in tz_missing),
        "density_rows": int(len(density)),
        "density_arrivals_without_local_time": arrivals_without_local,
        "parquet_bytes": int(sum(table_bytes.values())),
        "parquet_bytes_by_table": table_bytes,
    }
    (folder / SUMMARY_NAME).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert one month into the layer tables (no network).")
    parser.add_argument("--input", type=Path, required=True, help="BTS CSV or single-csv zip.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS_FILE)
    parser.add_argument("--ourairports", type=Path, default=DEFAULT_AIRPORTS)
    parser.add_argument("--tz-overrides", type=Path, default=DEFAULT_TZ_OVERRIDES)
    parser.add_argument(
        "--no-tz-overrides",
        action="store_true",
        help="Run WITHOUT manual time zone overrides on purpose (otherwise a missing --tz-overrides file is an error).",
    )
    parser.add_argument(
        "--scope",
        choices=SCOPE_MODES,
        default="origin",
        help="origin (default) | origin_or_dest | origin_and_dest (rationale: module docstring).",
    )
    args = parser.parse_args(argv)
    summary = process_month(
        args.input,
        args.year,
        args.month,
        args.layer_dir,
        read_targets(args.targets_file),
        load_airports(args.ourairports),
        load_tz_overrides(None if args.no_tz_overrides else args.tz_overrides),
        args.scope,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
