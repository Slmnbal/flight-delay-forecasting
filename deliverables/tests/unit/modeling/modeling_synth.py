"""SYNTHETIC frames for the modeling tests (not real data). Imported by the test modules as ``modeling_synth``.

pytest's default (prepend) import mode puts this folder on sys.path because it has no ``__init__.py``; the module
name is unique on purpose (other test folders have their own ``conftest.py``).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.layer import PARQUET_NAME, table_dir
from flight_delay.data.tables import FLIGHTS, LABELS

FLIGHT_COLUMNS = [
    "flight_uid",
    "FlightDate",
    "Origin",
    "Dest",
    "Reporting_Airline",
    "CRSDepTime",
    "CRSArrTime",
    "CRSElapsedTime",
    "Distance",
    "DistanceGroup",
    "crs_dep_utc",
    "crs_arr_utc",
    "crs_dep_local_min",
    "crs_arr_day_offset",
]
LABEL_COLUMNS = ["flight_uid", "ArrDelay", "ArrDel15", "Cancelled", "Diverted", "ActualElapsedTime", "TaxiOut"]


def _defaults(index: int) -> dict[str, Any]:
    return {
        "flight_uid": index + 1,
        "FlightDate": "2025-08-01",
        "Origin": "ORD",
        "Dest": "ATL",
        "Reporting_Airline": "AA",
        "CRSDepTime": 900,
        "CRSArrTime": 1210,
        "CRSElapsedTime": 130.0,
        "Distance": 606.0,
        "DistanceGroup": 3,
        "crs_arr_day_offset": 0,
        "ArrDelay": 0.0,
        "ArrDel15": 0.0,
        "Cancelled": 0,
        "Diverted": 0,
        "ActualElapsedTime": 130.0,
        "TaxiOut": 15.0,
    }


def build_frame(records: Sequence[dict[str, Any]]) -> pd.DataFrame:
    """Wide synthetic frame (flights + labels columns); missing fields take the defaults above.

    crs_dep_local_min comes from CRSDepTime; crs_dep_utc = local time + 5 h (fixed fake offset);
    crs_arr_utc = crs_dep_utc + CRSElapsedTime.
    """
    rows = []
    for index, record in enumerate(records):
        row = _defaults(index)
        row.update(record)
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame["FlightDate"] = pd.to_datetime(frame["FlightDate"])
    hhmm = frame["CRSDepTime"].astype(int)
    frame["crs_dep_local_min"] = ((hhmm // 100) * 60 + hhmm % 100).astype("Int16")
    local = frame["FlightDate"] + pd.to_timedelta(frame["crs_dep_local_min"].astype(float), unit="m")
    frame["crs_dep_utc"] = local + pd.Timedelta(hours=5)
    frame["crs_arr_utc"] = frame["crs_dep_utc"] + pd.to_timedelta(frame["CRSElapsedTime"].astype(float), unit="m")
    frame["ArrDel15"] = frame["ArrDel15"].astype("float32")
    return frame


def random_frame(start: str, end: str, *, per_day: int = 6, seed: int = 42) -> pd.DataFrame:
    """Deterministic random flights over [start, end]: 3 origins x 2 dests, 7 hours, roughly a quarter delayed."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    origins = ["ORD", "ATL", "DEN"]
    dests = ["LAX", "JFK"]
    hours = [600, 800, 1100, 1400, 1700, 2000, 2300]
    records: list[dict[str, Any]] = []
    for day in days:
        for _ in range(per_day):
            delay = float(np.round(rng.gamma(1.2, 12.0) - 10.0))
            cancelled = int(rng.random() < 0.05)
            diverted = int(not cancelled and rng.random() < 0.01)
            completed = not cancelled and not diverted
            records.append(
                {
                    "FlightDate": day.strftime("%Y-%m-%d"),
                    "Origin": origins[int(rng.integers(len(origins)))],
                    "Dest": dests[int(rng.integers(len(dests)))],
                    "Reporting_Airline": ["AA", "UA"][int(rng.integers(2))],
                    "CRSDepTime": hours[int(rng.integers(len(hours)))],
                    "ArrDelay": delay if completed else np.nan,
                    "ArrDel15": float(delay >= 15) if completed else np.nan,
                    "Cancelled": cancelled,
                    "Diverted": diverted,
                    "ActualElapsedTime": 130.0 + delay / 4 if completed else np.nan,
                    "TaxiOut": 15.0 if not cancelled else np.nan,
                }
            )
    return build_frame(records)


def flights_only(frame: pd.DataFrame) -> pd.DataFrame:
    """The schedule side only (what feature code may receive)."""
    return frame[FLIGHT_COLUMNS].copy()


def write_layer(root: Path, frame: pd.DataFrame) -> None:
    """Write a synthetic frame as monthly flights / flight_labels partitions."""
    months = frame["FlightDate"].dt.to_period("M")
    for period in sorted(months.unique()):
        part = frame.loc[months == period]
        flights_path = table_dir(root, FLIGHTS, period.year, period.month) / PARQUET_NAME
        labels_path = table_dir(root, LABELS, period.year, period.month) / PARQUET_NAME
        flights_path.parent.mkdir(parents=True, exist_ok=True)
        labels_path.parent.mkdir(parents=True, exist_ok=True)
        part[FLIGHT_COLUMNS].to_parquet(flights_path, index=False)
        part[LABEL_COLUMNS].to_parquet(labels_path, index=False)


def weather_frame(flights: pd.DataFrame, *, oracle: bool = False, minutes_before_cutoff: float = 30.0) -> pd.DataFrame:
    """Weather table aligned with ``flights`` whose observations lie ``minutes_before_cutoff`` before the cutoff.

    T table cutoff = crs_dep_utc - 2 h - 10 min; oracle cutoff = crs_dep_utc (origin) / crs_arr_utc (dest).
    A negative ``minutes_before_cutoff`` puts the observation AFTER the cutoff (leak) for the tests.
    """
    dep = pd.to_datetime(flights["crs_dep_utc"]).reset_index(drop=True)
    arr = pd.to_datetime(flights["crs_arr_utc"]).reset_index(drop=True)
    shift = pd.Timedelta(minutes=minutes_before_cutoff)
    if oracle:
        origin_target, dest_target = dep, arr
    else:
        origin_target = dest_target = dep - pd.Timedelta(hours=2) - pd.Timedelta(minutes=10)
    out = pd.DataFrame({"flight_uid": flights["flight_uid"].to_numpy()})
    for side, target in (("origin", origin_target), ("dest", dest_target)):
        out[f"{side}_target_utc"] = target
        out[f"{side}_obs_utc"] = target - shift
        out[f"{side}_obs_age_min"] = minutes_before_cutoff
        for variable, value in (
            ("tmpf", 70.0),
            ("dwpf", 50.0),
            ("sknt", 10.0),
            ("gust", np.nan),
            ("vsby", 10.0),
            ("p01i", 0.0),
        ):
            out[f"{side}_{variable}"] = value
        for variable in ("relh", "drct", "alti"):
            out[f"{side}_{variable}"] = 1.0
        out[f"{side}_skyc1"] = pd.array(["BKN"] * len(out), dtype="string")
        out[f"{side}_skyl1"] = 800.0
        for layer in (2, 3, 4):
            out[f"{side}_skyc{layer}"] = pd.array([None] * len(out), dtype="string")
            out[f"{side}_skyl{layer}"] = np.nan
        out[f"{side}_wxcodes"] = pd.array(["-TSRA BR"] * len(out), dtype="string")
    out["is_oracle"] = oracle
    return out
