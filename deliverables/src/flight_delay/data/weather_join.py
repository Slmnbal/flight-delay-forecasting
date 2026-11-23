"""Leak-free weather join: flights x METAR observations (NO NETWORK).

Information time (modeling plan sections 2 and 10.2; T = 2 h per decision M3):
  T-table  ``weather_t120m``  (name = ``weather_t{T in minutes}m``): for every flight the LAST observation of the
           station at or before ``cutoff = crs_dep_utc - T - margin`` (margin = 10 min, tolerance for the
           METAR publication delay; an assumption, configurable), looking back at most ``lookback`` (3 h).
           Origin AND destination use the SAME cutoff (the forecast is made T before departure, so the
           destination weather is NOT taken at arrival time). Destination weather exists only for the 30 target
           airports (``target_dest`` and a station in the map); otherwise it is empty.
  Oracle   ``weather_oracle``: origin observation at or before ``crs_dep_utc``, destination observation at or
           before ``crs_arr_utc`` (same 3 h look-back). It uses information that is NOT available at forecast time
           and is only an upper bound for the weather experiment: it is stored in a SEPARATE table, every row has
           ``is_oracle = True`` and it must never be fed to a non-oracle feature contract. Actual (realized)
           times are never used, even for the oracle.
All times are UTC (tz-less datetime64[ns], like the rest of the layer). Rows without a usable station, time or
observation get NaT / NaN (never filled).

Implementation: ``pandas.merge_asof(direction="backward", by=station, tolerance=lookback)`` per side.
``check_join_timing`` verifies row by row that no observation lies after its target time (it runs
inside ``build_weather_tables`` before anything is written).

Usage:
  python -m flight_delay.data.weather_join --metar deliverables/data/layer/metar/metar.parquet \\
      --station-map deliverables/data/raw/iem_asos/station_map.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.download_range import parse_month
from flight_delay.data.inputs import require_file
from flight_delay.data.layer import DEFAULT_LAYER_DIR, PARQUET_NAME, table_dir
from flight_delay.data.metar import IEM_NUMERIC_VARIABLES, IEM_TEXT_VARIABLES, IEM_VARIABLES, METAR_TABLE
from flight_delay.data.quality import find_months
from flight_delay.data.tables import write_parquet_atomic

__all__ = [
    "DEFAULT_HORIZON_HOURS",
    "DEFAULT_LOOKBACK_HOURS",
    "DEFAULT_MARGIN_MINUTES",
    "ORACLE_TABLE",
    "TimingError",
    "build_weather_tables",
    "check_join_timing",
    "horizon_table_name",
    "join_weather",
    "main",
]

DEFAULT_HORIZON_HOURS = 2.0  # T (M3 decision)
DEFAULT_MARGIN_MINUTES = 10.0  # METAR publication delay tolerance (assumption from the plan; parameter)
DEFAULT_LOOKBACK_HOURS = 3.0  # an older observation is treated as missing (plan section 10.2)
ORACLE_TABLE = "weather_oracle"

_FLIGHT_COLUMNS = ["flight_uid", "Origin", "Dest", "target_dest", "crs_dep_utc", "crs_arr_utc"]


class TimingError(ValueError):
    """An observation is newer than the time it was supposed to be known at (information leak)."""


def horizon_table_name(horizon_hours: float) -> str:
    """``weather_t120m`` for T = 2 h."""
    return f"weather_t{round(horizon_hours * 60)}m"


def _asof_side(
    stations: pd.Series, targets: pd.Series, metar: pd.DataFrame, prefix: str, lookback: pd.Timedelta
) -> pd.DataFrame:
    """Last observation at or before ``targets`` per station; result is aligned with the input rows.

    ``stations`` (object, NaN = no station) and ``targets`` (naive UTC, NaT = unknown) share one index.
    Columns: ``{prefix}target_utc``, ``{prefix}obs_utc``, ``{prefix}obs_age_min``, ``{prefix}{variable}``.
    """
    count = len(stations)
    usable = (stations.notna() & targets.notna()).to_numpy(dtype=bool)
    left = pd.DataFrame(
        {
            "_pos": np.flatnonzero(usable),
            "station": stations[usable].to_numpy(dtype=object),
            "target": targets[usable].astype("datetime64[ns]").to_numpy(),
        }
    )
    left["station"] = left["station"].astype(str)  # the SAME normalisation on both sides: merge_asof needs equal dtypes
    left = left.sort_values("target", kind="mergesort")
    right = metar[["station", "observed_utc", *IEM_VARIABLES]].copy()
    right["station"] = right["station"].astype(str)
    right["observed_utc"] = right["observed_utc"].astype("datetime64[ns]")
    right = right.sort_values("observed_utc", kind="mergesort")
    merged = pd.merge_asof(
        left,
        right,
        left_on="target",
        right_on="observed_utc",
        by="station",
        direction="backward",
        tolerance=lookback,
        allow_exact_matches=True,
    )
    merged["age_min"] = (merged["target"] - merged["observed_utc"]).dt.total_seconds() / 60
    aligned = merged.set_index("_pos").reindex(range(count))
    result = pd.DataFrame(index=stations.index)
    result[f"{prefix}target_utc"] = targets.astype("datetime64[ns]").to_numpy()
    result[f"{prefix}obs_utc"] = aligned["observed_utc"].astype("datetime64[ns]").to_numpy()
    result[f"{prefix}obs_age_min"] = aligned["age_min"].to_numpy()
    for name in IEM_NUMERIC_VARIABLES:
        result[f"{prefix}{name}"] = aligned[name].astype("float64").to_numpy()
    for name in IEM_TEXT_VARIABLES:
        result[f"{prefix}{name}"] = aligned[name].astype("string").set_axis(result.index)  # keeps the string dtype
    return result


def join_weather(
    flights: pd.DataFrame,
    metar: pd.DataFrame,
    station_map: dict[str, str],
    *,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    margin_minutes: float = DEFAULT_MARGIN_MINUTES,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    oracle: bool = False,
) -> pd.DataFrame:
    """Join the weather to the flights (module docstring). Returns one row per flight, key ``flight_uid``.

    ``flights`` needs: flight_uid, Origin, Dest, target_dest, crs_dep_utc, crs_arr_utc.
    ``metar`` needs: station, observed_utc and the IEM variables. ``station_map`` is {IATA: IEM station id}.
    """
    missing = [c for c in _FLIGHT_COLUMNS if c not in flights.columns]
    if missing:
        raise ValueError(f"flights is missing columns: {missing}")
    if horizon_hours < 0 or margin_minutes < 0 or lookback_hours <= 0:
        raise ValueError("horizon_hours and margin_minutes must be >= 0 and lookback_hours > 0.")
    lookback = pd.Timedelta(hours=lookback_hours)
    flights = flights.reset_index(drop=True)
    origin_station = flights["Origin"].astype(object).map(station_map)
    dest_station = (
        flights["Dest"].astype(object).map(station_map).where(flights["target_dest"].fillna(False).astype(bool))
    )
    crs_dep = flights["crs_dep_utc"].astype("datetime64[ns]")
    crs_arr = flights["crs_arr_utc"].astype("datetime64[ns]")
    if oracle:
        origin_target, dest_target = crs_dep, crs_arr
    else:
        cutoff = crs_dep - pd.Timedelta(hours=horizon_hours) - pd.Timedelta(minutes=margin_minutes)
        origin_target, dest_target = cutoff, cutoff
    origin = _asof_side(origin_station, origin_target, metar, "origin_", lookback)
    dest = _asof_side(dest_station, dest_target, metar, "dest_", lookback)
    result = pd.concat([flights[["flight_uid"]], origin, dest], axis=1)
    result["is_oracle"] = bool(oracle)
    return result


def check_join_timing(
    joined: pd.DataFrame,
    flights: pd.DataFrame,
    *,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    margin_minutes: float = DEFAULT_MARGIN_MINUTES,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    oracle: bool = False,
) -> None:
    """Row-level timing test (raises ``TimingError``).

    For every row and side: observation time <= target time and target time - observation time <= look-back.
    T-table: the target time must also be <= crs_dep_utc - T - margin (i.e. the cutoff was not widened).
    Oracle: origin target == crs_dep_utc and destination target == crs_arr_utc.
    """
    lookback = pd.Timedelta(hours=lookback_hours)
    base = flights[["flight_uid", "crs_dep_utc", "crs_arr_utc"]].reset_index(drop=True)
    merged = joined.reset_index(drop=True).merge(base, on="flight_uid", how="left", validate="one_to_one")
    for side in ("origin", "dest"):
        observed = merged[f"{side}_obs_utc"]
        target = merged[f"{side}_target_utc"]
        found = observed.notna()
        if bool((observed[found] > target[found]).any()):
            raise TimingError(f"{side}: an observation is newer than its target time (information leak).")
        if bool(((target[found] - observed[found]) > lookback).any()):
            raise TimingError(f"{side}: an observation is older than the look-back window ({lookback}).")
        if bool((observed.notna() & target.isna()).any()):
            raise TimingError(f"{side}: an observation exists without a target time.")
    if oracle:
        if bool((merged["origin_target_utc"].notna() & (merged["origin_target_utc"] != merged["crs_dep_utc"])).any()):
            raise TimingError("oracle origin target time is not crs_dep_utc.")
        if bool((merged["dest_target_utc"].notna() & (merged["dest_target_utc"] != merged["crs_arr_utc"])).any()):
            raise TimingError("oracle destination target time is not crs_arr_utc.")
    else:
        limit = merged["crs_dep_utc"] - pd.Timedelta(hours=horizon_hours) - pd.Timedelta(minutes=margin_minutes)
        for side in ("origin", "dest"):
            target = merged[f"{side}_target_utc"]
            if bool((target.notna() & (target > limit)).any()):
                raise TimingError(f"{side}: target time is later than crs_dep_utc - T - margin (information leak).")


def build_weather_tables(
    layer_root: Path,
    metar_path: Path,
    station_map: dict[str, str],
    *,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    margin_minutes: float = DEFAULT_MARGIN_MINUTES,
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    only: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """For every processed month: write the T-table and the oracle table; verify the timing row by row.

    ``only=(year, month)`` builds just that month (e.g. after one month was re-processed). Safe to re-run
    (output is overwritten atomically; same input -> same content). Returns a summary dict.
    """
    metar = pd.read_parquet(require_file(Path(metar_path), "metar table", "--metar"))
    months = find_months(Path(layer_root))
    if only is not None:
        months = [item for item in months if (item[0], item[1]) == only]
        if not months:
            raise FileNotFoundError(f"Month {only[0]}-{only[1]:02d} is not processed under {layer_root}.")
    if not months:
        raise FileNotFoundError(f"No processed months under {layer_root} (run flight_delay.data.layer first).")
    t_name = horizon_table_name(horizon_hours)
    options = {"horizon_hours": horizon_hours, "margin_minutes": margin_minutes, "lookback_hours": lookback_hours}
    summary: dict[str, Any] = {"table": t_name, "oracle_table": ORACLE_TABLE, "parameters": options, "months": []}
    for year, month, path in months:
        flights = pd.read_parquet(path, columns=_FLIGHT_COLUMNS)
        record: dict[str, Any] = {"year": year, "month": month, "rows": int(len(flights))}
        for oracle, name in ((False, t_name), (True, ORACLE_TABLE)):
            joined = join_weather(flights, metar, station_map, oracle=oracle, **options)
            check_join_timing(joined, flights, oracle=oracle, **options)
            write_parquet_atomic(joined, table_dir(Path(layer_root), name, year, month) / PARQUET_NAME)
            record[name] = {
                "origin_found": int(joined["origin_obs_utc"].notna().sum()),
                "dest_found": int(joined["dest_obs_utc"].notna().sum()),
            }
        summary["months"].append(record)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the leak-free weather tables from the layer + metar (no network)."
    )
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--metar", type=Path, default=DEFAULT_LAYER_DIR / METAR_TABLE / "metar.parquet")
    parser.add_argument("--station-map", type=Path, required=True, help="station_map.json written by download_iem.")
    parser.add_argument("--horizon-hours", type=float, default=DEFAULT_HORIZON_HOURS, help="T (default 2).")
    parser.add_argument("--margin-minutes", type=float, default=DEFAULT_MARGIN_MINUTES)
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument(
        "--only",
        default=None,
        metavar="YYYY-MM",
        help="Build only this month (after re-processing one month). Summary goes to weather-summary-YYYY-MM.json.",
    )
    parser.add_argument(
        "--output-json", type=Path, default=None, help="Summary file (default: <layer-dir>/weather-summary.json)."
    )
    args = parser.parse_args(argv)
    only = None
    if args.only:
        try:
            only = parse_month(args.only)
        except ValueError as e:
            parser.error(str(e))
    require_file(args.station_map, "IEM station map", "--station-map")
    station_map: dict[str, str] = json.loads(args.station_map.read_text(encoding="utf-8"))
    summary = build_weather_tables(
        args.layer_dir,
        args.metar,
        station_map,
        horizon_hours=args.horizon_hours,
        margin_minutes=args.margin_minutes,
        lookback_hours=args.lookback_hours,
        only=only,
    )
    default_name = f"weather-summary-{only[0]}-{only[1]:02d}.json" if only else "weather-summary.json"
    output = args.output_json or (args.layer_dir / default_name)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written: {output} (months: {len(summary['months'])}; tables: {summary['table']}, {ORACLE_TABLE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
