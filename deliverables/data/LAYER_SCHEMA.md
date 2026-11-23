# Data layer schema

Status: the layer was built for 2023-09..2026-08 (13.69 M flights, 30 origin airports; see `quality-report.md`). Source of truth for
column lists: `deliverables/src/flight_delay/data/tables.py` (columns) and `layer.py` (`RAW_COLUMNS`,
`OUTPUT_SCHEMA`). Plan reference: `experiments/modelleme-plani.md` section 10 (the plan uses Turkish names; the
decision M3-inceleme keeps the English code names, mapping at the end).

## Conventions

- Parquet (zstd), one file per table and month: `<layer>/<table>/year=YYYY/month=MM/part-0.parquet`
  (`<layer>` = `deliverables/data/layer`). Partition = month of `FlightDate`. Rows are sorted by
  `FlightDate, crs_dep_utc, Origin, Dest, Reporting_Airline, flight number` (stable) before writing.
- **All `*_utc` columns are UTC, stored as timestamps WITHOUT a time zone** (naive, UTC meaning). Local
  schedule fields (`CRSDepTime`, `CRSArrTime`, `FlightDate`) are airport-local wall clock (BTS).
- BTS column names are kept as published (`ArrDelay`, `Cancelled`, ...). Derived columns are snake_case.
- **No row is dropped** except by (1) the scope filter (`origin` = departure airport is one of the 30 targets) and
  (2) the **missing-key drop**: a row where any of `KEY_FIELDS_FILLED` (`FlightDate`, `Reporting_Airline`,
  `Flight_Number_Reporting_Airline`, `Origin`, `Dest`, `CRSDepTime`, `CRSArrTime`, `Cancelled`, `Diverted`; defined in
  `layer.py`, imported by `quality.py`) is empty after the type cast is not written to `flights` / `flight_labels` /
  `flight_keys`. The count is recorded in `summary.json` (`rows_dropped_missing_key`, and per field
  `dropped_missing_key_by_field`; `rows_layer` is the count AFTER the drop) and reported by the quality check
  `dropped_missing_key_rows`. `scheduled_density` is computed from raw rows and is not affected. Other problems are
  flags/NaT with a reason. Cancelled and diverted flights stay.
- DuckDB views (`flight_delay.data.query`): `flights`, `flight_labels`, `scheduled_density` (+ `partition_year`,
  `partition_month`). `flight_keys` is intentionally not exposed.
- Month processed = `flights/.../part-0.parquet` **and** `flights/.../summary.json` exist (summary is written last).

## Who may read what

| Table | Feature code | Label / evaluation code | Export / publish |
|---|---|---|---|
| `flights` | yes (schedule only) | yes | row level: no |
| `scheduled_density` | yes | yes | no |
| `weather_t120m` | yes (non-oracle contract only) | yes | no |
| `flight_labels` | **no** | yes | row level: no |
| `weather_oracle` | **only** the `oracle` contract / experiment | yes | no |
| `flight_keys` (Tail_Number) | no (not used in the core) | no | **never**; local only |

## `flights` (schedule + UTC + flags; no outcome)

| Column | Type | Meaning |
|---|---|---|
| `flight_uid` | int64 | Stable surrogate key shared by flights / flight_labels / flight_keys: pandas `hash_pandas_object` of `flight_id + "#" + n` (n = occurrence of that `flight_id`), shifted to 63 bits. Plan name `ucus_id`. |
| `flight_id` | string | Natural key `YYYYMMDD_Airline_FlightNo_Origin_Dest_CRSDepTime` (uniqueness NOT guaranteed; quality counts duplicates). |
| `Year`, `Quarter`, `Month`, `DayofMonth`, `DayOfWeek` | Int16/Int8 | BTS calendar fields. (`Year` is not a model feature per the plan.) |
| `FlightDate` | datetime64[ns] | Local scheduled departure date. |
| `Reporting_Airline`, `Flight_Number_Reporting_Airline` | string, Int32 | Carrier code and flight number (flight number is local, not a model feature). |
| `OriginAirportID`, `Origin`, `DestAirportID`, `Dest` | Int32, string | Airports (IATA, upper case). |
| `CRSDepTime`, `CRSArrTime` | Int16 | Scheduled local hhmm (2400 allowed). |
| `CRSElapsedTime`, `Distance` | float32 | Scheduled block time (min), distance (miles). |
| `DistanceGroup` | Int8 | BTS distance group. |
| `target_origin`, `target_dest` | bool | Origin / Dest is one of the 30 targets (`target-airports.txt`). Plan name `hedef_30` lives on the airport level. |
| `tz_origin`, `tz_dest` | string | IANA zone used for the conversion (<NA> if it could not be mapped; never invented). |
| `crs_dep_utc`, `crs_arr_utc` | timestamp (naive UTC) | Scheduled departure / arrival in UTC. Arrival is resolved as the candidate day after departure within 24 h. NaT if a zone is missing or the window is inconsistent. Plan: `crs_kalkis_utc`, `crs_varis_utc`. |
| `crs_dep_local_min` | Int16 | Minutes since local midnight of the scheduled departure (2400 -> 1440). Plan: `crs_kalkis_yerel_dk`. |
| `crs_arr_day_offset` | Int8 | Days between `FlightDate` and the local arrival date (0, 1, 2, -1). Plan: `varis_gun_ofseti`. |
| `crs_dep_dst_ambiguous`, `crs_dep_dst_gap`, `crs_arr_dst_ambiguous`, `crs_arr_dst_gap` | bool | DST fall-back ambiguity (first occurrence used) / spring-forward gap (offset before the transition used). Plan: `utc_belirsiz`, `utc_bosluk`. |
| `crs_arr_utc_inconsistent` | bool | Arrival could not be placed within 24 h after departure. |
| `utc_tz_missing` | bool | Origin or Dest zone unknown. |

## `flight_labels` (outcomes; physically separate; NOT given to feature code)

Key `flight_uid` (same row set as `flights`). Everything that happened after the scheduled departure:

`DepTime`, `DepDelay`, `DepDelayMinutes`, `DepDel15`, `TaxiOut`, `WheelsOff`, `WheelsOn`, `TaxiIn`, `ArrTime`,
`ArrDelay`, `ArrDelayMinutes`, `ArrDel15`, `ActualElapsedTime`, `AirTime`, `Cancelled`, `CancellationCode`,
`Diverted`, `CarrierDelay`, `WeatherDelay`, `NASDelay`, `SecurityDelay`, `LateAircraftDelay` (BTS types as in
`RAW_COLUMNS`; minutes are float32 so they can carry NaN), plus the derived actual UTC columns:

| Column | Type | Meaning |
|---|---|---|
| `dep_utc` | timestamp (naive UTC) | **`crs_dep_utc` + `DepDelay` minutes** (M2 fix: no 12-hour assumption; negative delay = early; elapsed time, so DST-correct). NaT for cancelled flights or if `DepDelay` / `crs_dep_utc` is missing. |
| `arr_utc` | timestamp (naive UTC) | **`crs_arr_utc` + `ArrDelay` minutes**. NaT for cancelled **and diverted** flights or if `ArrDelay` / `crs_arr_utc` is missing. |
| `dep_utc_reason`, `arr_utc_reason` | string | `<NA>` if the actual time exists, else `cancelled` \| `diverted` (arrival only) \| `crs_utc_missing` \| `delay_missing` (checked in this order). |

`CancellationCode` is for analysis only (plan section 10.1). Diverted flights have no `ArrDelay` in BTS, so they are
outside the ArrDel15 target universe; they remain in the table.

## `flight_keys` (LOCAL ONLY)

`flight_uid`, `Tail_Number`. Not used by the core model (the plan keeps rotation features out of the core), never
exported or published.

## `scheduled_density` (computed from ALL BTS flights before the scope filter)

One row per airport x local date x local hour that has at least one scheduled movement.

| Column | Type | Meaning |
|---|---|---|
| `airport` | string | IATA code (any BTS airport, not only the 30). |
| `local_date` | datetime64[ns] | Local calendar date at that airport. |
| `local_hour` | Int8 | Local hour 0..23. |
| `planned_departures` | Int32 | Scheduled departures with Origin = airport, local CRS departure date/hour (2400 counts as 00:00 of the next day). |
| `planned_arrivals` | Int32 | Scheduled arrivals with Dest = airport, local CRS arrival date/hour (date resolved from the UTC window, so past-midnight arrivals count on the next local date). |

- Inputs: **every raw row of the month**, cancelled flights included, **before** the 30-airport filter (non-target
  origins and arrivals into targets from non-target origins are counted). Independent of `--scope`.
- Arrivals whose local time cannot be resolved (unknown time zone / inconsistent window) are **not counted and not
  guessed**; the number is `density_arrivals_without_local_time` in `summary.json`.
- Partitioned by the month of the source file. Flights that leave on the last day of a month and arrive after
  midnight add rows dated in the next month, so **consumers must `SUM ... GROUP BY airport, local_date, local_hour`
  over all months** before using a value.
- Only carriers that report to BTS are counted (consistent but incomplete traffic; plan section 2.3).

## `metar` (`<layer>/metar/metar.parquet`, not partitioned; built by `flight_delay.data.metar`)

`station` (IEM id), `iata`, `observed_utc` (naive UTC), then `tmpf, dwpf, relh, drct, sknt, gust, vsby, alti, p01i,
skyl1..skyl4` (float64) and `skyc1..skyc4, wxcodes` (string). One row per station and `observed_utc`
(duplicate rule: most complete row, then the later one). Impossible values are NaN (ranges in `metar.NUMERIC_RANGES`,
counts in `metar-stats.json`). Report type (METAR/SPECI) is not kept. Derived features (ceiling, IFR flag,
weather-code flags) are the data scientist's job.

## `weather_t120m` and `weather_oracle` (`<layer>/<table>/year=/month=/part-0.parquet`)

Key `flight_uid`; built by `flight_delay.data.weather_join` (month by month, same row set as `flights`).
`T` = 2 h (decision M3), so the T-table name is `weather_t{T in minutes}m` = `weather_t120m` (changes if `--horizon-hours`
changes).

| Column | Meaning |
|---|---|
| `origin_target_utc`, `dest_target_utc` | The time each lookup was made for. T-table: **both = `crs_dep_utc - T - 10 min`**. Oracle: origin = `crs_dep_utc`, dest = `crs_arr_utc`. |
| `origin_obs_utc`, `dest_obs_utc` | Time of the observation found: last observation of the station at or before the target time, at most 3 h older (NaT otherwise). |
| `origin_obs_age_min`, `dest_obs_age_min` | Target minus observation time, minutes (`>= 0`, `<= 180`). |
| `origin_<var>`, `dest_<var>` | The METAR variables of that observation (as in `metar`). |
| `is_oracle` | `False` in `weather_t120m`, `True` in `weather_oracle`. |

- Destination weather exists **only for the 30 targets** (`target_dest` and a station in the map); otherwise empty.
- The T-table uses the same cutoff for origin and destination (the forecast is made T before departure).
- `weather_oracle` is an **upper-bound experiment table** ("not available at forecast time"). It is a separate
  table, every row is labelled `is_oracle = True`, and it must only enter a `FeatureContract(oracle_experiment=True)`.
  Actual (realized) times are never used.
- Row-level guarantee (tested and re-checked before writing): every non-empty `*_obs_utc <= *_target_utc`, age <= 3 h,
  and in the T-table `*_target_utc <= crs_dep_utc - T - margin`.
- Parameters (T = 2 h, margin = 10 min METAR publication tolerance, look-back = 3 h) are CLI options; 10 min is an
  assumption from the plan.

## Plan name -> code name (modeling plan section 10.1)

| Plan | Code |
|---|---|
| `ucuslar` | `flights` |
| `ucus_etiketleri` | `flight_labels` |
| `ucus_anahtar` | `flight_keys` |
| `planli_yogunluk` (`planli_kalkis`, `planli_varis`) | `scheduled_density` (`planned_departures`, `planned_arrivals`) |
| `metar` (`gozlem_utc`, `istasyon`) | `metar` (`observed_utc`, `station`) |
| `hava_T2`, `hava_oracle` | `weather_t120m`, `weather_oracle` |
| `ucus_id` | `flight_uid` |
| `crs_kalkis_utc`, `crs_varis_utc`, `tz_origin`, `tz_dest` | `crs_dep_utc`, `crs_arr_utc`, `tz_origin`, `tz_dest` |
| `havalimani` table | not built here (airport list = `target-airports.txt` + `raw/iem_asos/station_map.json`) |

## Known limits

- The `quality` check `actual_local_time_mismatch` compares the local clock reading of `dep_utc` / `arr_utc` with BTS
  `DepTime` / `ArrTime`; its warning-only threshold is the author's choice and the real mismatch rate is unknown.
- `flight_uid` collisions (63-bit hash) are not impossible; `read_wide_month` (one-to-one merge) and the quality check
  `duplicate_flight_uid` would stop the run.
