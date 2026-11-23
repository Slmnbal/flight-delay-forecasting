"""Table split of the data layer (NO NETWORK): column groups, density, atomic Parquet writing.

Physical tables (modeling plan section 10.1; one Parquet file per month under ``<layer>/<table>/year=YYYY/month=MM/``):

  flights             schedule + UTC + DST/time-zone flags ONLY (the feature side; contains no outcome)
  flight_labels       everything that happened after departure (ArrDelay, ArrDel15, Cancelled, Diverted, actual
                      times, actual UTC, cause minutes, ...). Not given to feature code.
  flight_keys         Tail_Number only. LOCAL ONLY, never exported or published.
  scheduled_density   airport x local date x local hour: scheduled departures / arrivals, computed from ALL
                      BTS flights BEFORE the target-airport scope filter (cancelled flights included).

``flight_uid`` (int64) is the stable surrogate key shared by flights, flight_labels and flight_keys.
Full column documentation: deliverables/data/LAYER_SCHEMA.md.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "DENSITY",
    "DENSITY_COLUMNS",
    "FLIGHTS",
    "FLIGHTS_COLUMNS",
    "KEYS",
    "KEY_COLUMNS",
    "LABELS",
    "LABEL_COLUMNS",
    "compute_scheduled_density",
    "make_flight_uid",
    "split_tables",
    "write_parquet_atomic",
]

FLIGHTS = "flights"
LABELS = "flight_labels"
KEYS = "flight_keys"
DENSITY = "scheduled_density"

FLIGHTS_COLUMNS = [
    "flight_uid",
    "flight_id",
    "Year",
    "Quarter",
    "Month",
    "DayofMonth",
    "DayOfWeek",
    "FlightDate",
    "Reporting_Airline",
    "Flight_Number_Reporting_Airline",
    "OriginAirportID",
    "Origin",
    "DestAirportID",
    "Dest",
    "CRSDepTime",
    "CRSArrTime",
    "CRSElapsedTime",
    "Distance",
    "DistanceGroup",
    "target_origin",
    "target_dest",
    "tz_origin",
    "tz_dest",
    "crs_dep_utc",
    "crs_arr_utc",
    "crs_dep_local_min",
    "crs_arr_day_offset",
    "crs_dep_dst_ambiguous",
    "crs_dep_dst_gap",
    "crs_arr_dst_ambiguous",
    "crs_arr_dst_gap",
    "crs_arr_utc_inconsistent",
    "utc_tz_missing",
]

LABEL_COLUMNS = [
    "flight_uid",
    "DepTime",
    "DepDelay",
    "DepDelayMinutes",
    "DepDel15",
    "TaxiOut",
    "WheelsOff",
    "WheelsOn",
    "TaxiIn",
    "ArrTime",
    "ArrDelay",
    "ArrDelayMinutes",
    "ArrDel15",
    "ActualElapsedTime",
    "AirTime",
    "Cancelled",
    "CancellationCode",
    "Diverted",
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
    "dep_utc",
    "arr_utc",
    "dep_utc_reason",
    "arr_utc_reason",
]

KEY_COLUMNS = ["flight_uid", "Tail_Number"]

DENSITY_COLUMNS = ["airport", "local_date", "local_hour", "planned_departures", "planned_arrivals"]


def split_tables(wide: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split the wide month frame into flights / flight_labels / flight_keys (no row is dropped)."""
    return {FLIGHTS: wide[FLIGHTS_COLUMNS], LABELS: wide[LABEL_COLUMNS], KEYS: wide[KEY_COLUMNS]}


def make_flight_uid(flight_id: pd.Series) -> pd.Series:
    """Stable non-negative int64 surrogate key from the text ``flight_id``.

    The natural key is not guaranteed unique (quality.py counts duplicates), so the n-th occurrence of the
    same ``flight_id`` (in current row order) gets the suffix ``#n``. The hash is pandas' fixed-key
    ``hash_pandas_object`` (deterministic across runs; 63 bits, so a collision is not impossible but the
    merge in ``read_wide_month`` and the quality check ``duplicate_flight_uid`` would catch it).
    """
    occurrence = flight_id.groupby(flight_id).cumcount()
    keyed = flight_id.astype(str) + "#" + occurrence.astype(str)
    hashed = pd.util.hash_pandas_object(keyed, index=False).to_numpy(dtype="uint64")
    return pd.Series((hashed >> np.uint64(1)).astype("int64"), index=flight_id.index)


def compute_scheduled_density(
    origin: pd.Series, dest: pd.Series, dep_local: pd.Series, arr_local: pd.Series
) -> tuple[pd.DataFrame, int]:
    """Scheduled departures / arrivals per airport x local date x local hour.

    ``dep_local`` / ``arr_local`` are the naive LOCAL scheduled datetimes at Origin / Dest (NaT if unknown).
    Call this with ALL flights of the month (cancelled included, before any scope filter).
    Returns ``(table, arrivals_without_local_time)``; the second number counts flights whose arrival local
    time could not be resolved (unknown time zone or inconsistent window): they are NOT counted as arrivals
    (never guessed) and the count goes to summary.json.
    """
    departures = pd.DataFrame(
        {"airport": origin, "local_date": dep_local.dt.normalize(), "local_hour": dep_local.dt.hour}
    ).dropna()
    arrivals = pd.DataFrame(
        {"airport": dest, "local_date": arr_local.dt.normalize(), "local_hour": arr_local.dt.hour}
    ).dropna()
    unresolved = int(arr_local.isna().sum())
    keys = ["airport", "local_date", "local_hour"]
    for frame in (departures, arrivals):
        frame["local_hour"] = frame["local_hour"].astype("int64")
        frame["airport"] = frame["airport"].astype(str)
    dep_counts = departures.groupby(keys).size().rename("planned_departures")
    arr_counts = arrivals.groupby(keys).size().rename("planned_arrivals")
    table = pd.concat([dep_counts, arr_counts], axis=1).fillna(0).reset_index()
    if len(table) == 0:
        table = pd.DataFrame(columns=DENSITY_COLUMNS)
    table = table.sort_values(keys, kind="mergesort").reset_index(drop=True)
    table["local_date"] = table["local_date"].astype("datetime64[ns]")
    table["local_hour"] = table["local_hour"].astype("Int8")
    table["planned_departures"] = table["planned_departures"].astype("Int32")
    table["planned_arrivals"] = table["planned_arrivals"].astype("Int32")
    return table[DENSITY_COLUMNS], unresolved


def write_parquet_atomic(frame: pd.DataFrame, target: Path) -> int:
    """Write ``frame`` to ``target`` (zstd) via a .tmp file + os.replace; return the file size in bytes."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    frame.to_parquet(temporary, engine="pyarrow", compression="zstd", index=False)
    os.replace(temporary, target)
    return int(target.stat().st_size)
