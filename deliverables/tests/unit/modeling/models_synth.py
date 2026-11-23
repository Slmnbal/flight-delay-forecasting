"""SYNTHETIC side tables (scheduled_density, weather_t120m, weather_oracle) for the step-2 model tests (not real data).

Imported by the test modules as ``models_synth`` (same import mechanism as ``modeling_synth``).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from modeling_synth import flights_only, weather_frame

from flight_delay.data.layer import PARQUET_NAME, table_dir
from flight_delay.data.tables import DENSITY, FLIGHTS, LABELS
from flight_delay.data.weather_join import ORACLE_TABLE

WEATHER_T_TABLE = "weather_t120m"
ALL_TABLES = (FLIGHTS, LABELS, DENSITY, WEATHER_T_TABLE, ORACLE_TABLE)

# tiny-data LightGBM settings for the tests only (the real runs use the plan's search space)
SMALL_PARAMS = {"min_child_samples": 5, "min_data_per_group": 5, "cat_smooth": 1, "num_leaves": 7, "max_bin": 31}


def _path(root: Path, table: str, year: int, month: int) -> Path:
    path = table_dir(root, table, year, month) / PARQUET_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def density_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Scheduled departures per Origin x date x hour and arrivals per Dest x date x hour (same-day arrivals)."""
    dep = frame.assign(local_hour=frame["CRSDepTime"].astype(int) // 100 % 24)
    arr = frame.assign(local_hour=frame["CRSArrTime"].astype(int) // 100 % 24)
    departures = dep.groupby(["Origin", "FlightDate", "local_hour"]).size().rename("planned_departures").reset_index()
    arrivals = arr.groupby(["Dest", "FlightDate", "local_hour"]).size().rename("planned_arrivals").reset_index()
    departures = departures.rename(columns={"Origin": "airport", "FlightDate": "local_date"})
    arrivals = arrivals.rename(columns={"Dest": "airport", "FlightDate": "local_date"})
    out = departures.merge(arrivals, how="outer", on=["airport", "local_date", "local_hour"]).fillna(0)
    out["airport"] = out["airport"].astype(str)
    out["local_hour"] = out["local_hour"].astype("int8")
    out["planned_departures"] = out["planned_departures"].astype("int32")
    out["planned_arrivals"] = out["planned_arrivals"].astype("int32")
    return out[["airport", "local_date", "local_hour", "planned_departures", "planned_arrivals"]]


def write_side_tables(root: Path, frame: pd.DataFrame, *, weather: bool = True, oracle: bool = False) -> None:
    """Monthly density (+ weather_t120m, + weather_oracle) partitions for a synthetic wide frame."""
    months = frame["FlightDate"].dt.to_period("M")
    for period in sorted(months.unique()):
        part = frame.loc[months == period]
        density_frame(part).to_parquet(_path(root, DENSITY, period.year, period.month), index=False)
        flights = flights_only(part).reset_index(drop=True)
        if weather:
            weather_frame(flights).to_parquet(_path(root, WEATHER_T_TABLE, period.year, period.month), index=False)
        if oracle:
            weather_frame(flights, oracle=True).to_parquet(
                _path(root, ORACLE_TABLE, period.year, period.month), index=False
            )


def corrupt(root: Path, table: str, year: int, month: int) -> Path:
    """A file that is NOT Parquet: any attempt to read it fails loudly."""
    path = _path(root, table, year, month)
    path.write_bytes(b"not a parquet file - this partition must never be opened")
    return path
