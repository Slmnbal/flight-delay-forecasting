# Running the data layer

Status: these steps were run to build the 2023-09..2026-08 layer (see `quality-report.md`); the test suite, ruff
and mypy pass. Table design: `LAYER_SCHEMA.md`.

All commands run from the project root `projects/havayolu-ds/` (the git repository root). Steps marked
**NETWORK** need the user's approval; everything else is offline. No step retries by itself: on the first error a
module stops and writes what it did so far.

## 0. Install (once)

```bash
pip install -e "deliverables[dev]"
```

## 1. Tests, lint, types (offline)

```bash
python -m pytest deliverables/tests/unit -q
ruff check deliverables
ruff format --check deliverables     # optional; `ruff format deliverables` fixes layout
(cd deliverables && mypy)
```

Expected shape: no strict xfail any more (the 12-hour limitation test is now a normal passing test); the count is
higher than 249 because of the new test files. Report the real numbers.

## 2. One-month trial (offline; uses the 2025-07 file that is already in `deliverables/data/raw/`)

The old single-table layer from the previous version (`deliverables/data/layer/year=2025/month=07/part-0.parquet`)
is not read by anything now. Remove it by hand so nobody mistakes it for the new layout:

```bash
rm -r deliverables/data/layer/year=2025
```

Build the month (tz overrides, target list and OurAirports file must exist; a missing file is an error. To run
without time zone overrides on purpose add `--no-tz-overrides`):

```bash
python -m flight_delay.data.layer --input deliverables/data/raw/ontime_2025_07.zip --year 2025 --month 7
python -m flight_delay.data.quality --previous deliverables/data/quality-report.json
python -m flight_delay.data.query --summary
```

What to look at in the quality report: `utc_actual_departure_mismatch` / `utc_actual_arrival_mismatch` should now
pass (the previous run had about 582 / 567 rows shifted by 24 h); `actual_local_time_mismatch` is a new, independent
warning-only check (its real rate is unknown until this run); `duplicate_flight_uid` must pass; the month hash is
expected to equal the previous `db292d3cff0542c0` (it covers `flight_id`, `Tail_Number`, `ArrDelay`, `DepDelay`,
`Cancelled`, `crs_dep_utc`, `crs_arr_utc`, none of which changed in meaning) but that is **unverified**. `summary.json`
(in `layer/flights/year=2025/month=07/`) shows `density_rows` and `density_arrivals_without_local_time`.

## 3. IEM weather download (**NETWORK**, needs the user's approval)

First the offline plan (resolves the 30 IEM stations from `raw/iem_istasyonlar.geojson` + `raw/airports.csv`,
stops if any target is not `matched`, prints the requests and the station-years against the 1,000 limit):

```bash
python -m flight_delay.data.download_iem --start 2023-09-01 --end 2026-08-31 --dry-run
```

Small trial first (one station, one month, separate folder; 1 request):

```bash
python -m flight_delay.data.download_iem --start 2025-07-01 --end 2025-07-31 --only ORD \
    --out-dir deliverables/data/raw/iem_asos_trial
python -m flight_delay.data.metar --raw-dir deliverables/data/raw/iem_asos_trial \
    --output deliverables/data/raw/iem_asos_trial/metar.parquet
```

Check the downloaded CSV by eye (header `station,valid,...`, UTC times, "M" for missing) and read the
"UNVERIFIED" list in the `download_iem.py` docstring: the endpoint and parameters were written from memory and were
not checked against the live service. Then the full range (about 120 requests: 30 stations x 4 calendar-year chunks,
5 s between requests, so roughly 10 minutes plus transfer):

```bash
python -m flight_delay.data.download_iem --start 2023-09-01 --end 2026-08-31
python -m flight_delay.data.metar --raw-dir deliverables/data/raw/iem_asos
```

Outputs: `raw/iem_asos/*.csv`, `raw/iem_asos/station_map.json`, `raw/iem_asos/download-iem-summary.json`,
`layer/metar/metar.parquet`, `layer/metar/metar-stats.json`. If a request fails, fix the cause and run the same
command again: files that already exist are skipped. A `--only` run overwrites `station_map.json` with the subset, so
use `--out-dir` for trials (as above) and run the full command last.

## 4. Full 36-month BTS run, 2023-09 .. 2026-08 (**NETWORK**, needs the user's approval)

Downloads one month at a time, processes it into the layer, deletes the raw file, 5 s between downloads, stops at the
first error. Months that are already processed in the new layout (2025-07 from step 2) are skipped, and their raw
zip/csv is deleted because of `--delete-raw`; `--force` re-processes them.

```bash
python -m flight_delay.data.download_range --start 2023-09 --end 2026-08 --delete-raw --dry-run
python -m flight_delay.data.download_range --start 2023-09 --end 2026-08 --delete-raw
```

Check `deliverables/data/download-range-summary.json` (`has_error`, `unprocessed_months`). Whether the 2026-08 file is
complete (modeling plan section 1.1) is checked by the `period_row_deviation` finding of the next step plus the
number of distinct `FlightDate` values of that month (`python -m flight_delay.data.query --sql "SELECT
count(DISTINCT FlightDate) FROM flights WHERE partition_year = 2026 AND partition_month = 8"`); if it is incomplete
all dates shift one month back (data scientist decision).

### 4a. Re-process one month after the missing-key rule (2024-08; **NETWORK**, needs the user's approval)

Since the layer drops rows with an empty key field (`KEY_FIELDS_FILLED`; see `LAYER_SCHEMA.md`), the 2024-08 layer
(1 row with an empty `Flight_Number_Reporting_Airline`, found by `key_field_missing`) must be rebuilt. The raw file of
that month was deleted, so it is downloaded again (`--force` re-processes although the layer exists). Every other
month stays as it is (their `summary.json` has no drop record: the quality report lists them as `unknown`, see step 5).

```bash
python -m flight_delay.data.download_range --start 2024-08 --end 2024-08 --delete-raw --force --dry-run
python -m flight_delay.data.download_range --start 2024-08 --end 2024-08 --delete-raw --force \
  --summary-path deliverables/data/download-range-summary-2024-08.json
python -m flight_delay.data.weather_join --station-map deliverables/data/raw/iem_asos/station_map.json --only 2024-08
python -m flight_delay.data.quality --previous deliverables/data/quality-report.json
```

Expected: `download-range-summary-2024-08.json` (own file, so the 36-month `download-range-summary.json` is not
overwritten) shows `rows_dropped_missing_key: 1` for 2024-08; `rows_layer` is one less than
before. In the new quality report: `key_field_missing` passes, `dropped_missing_key_rows` is a **warning** for 2024-08
(1 row, ratio far below 0.1%), and `rows_vs_previous_run` is a warning for 2024-08 (one row fewer than in the previous
report; expected, the cause is the drop). `--only` writes `layer/weather-summary-2024-08.json`, so the full
`weather-summary.json` is not overwritten. Re-processing the other 35 months to get a drop record for them is optional
(needs 35 more downloads); until then they are reported as `unknown`, not `passed`.

## 5. Quality report (offline)

```bash
python -m flight_delay.data.quality --previous deliverables/data/quality-report.json
```

Writes `quality-report.json` and `quality-report.md`; exit code 2 means a critical finding (stop and report). A second
run on the same layer must give the same row counts and hashes (`rows_vs_previous_run` passes).

`dropped_missing_key_rows` reports the rows the layer dropped for an empty key field (from `summary.json`): 0 =
passed, > 0 up to 0.1% of the rows = warning, above 0.1% = critical; a month whose `summary.json` has no such field
(processed before the rule) is shown as `skipped` with `unknown: true` and listed in the "Missing-key drop record"
section of `quality-report.md` (never silently passed). `key_field_missing` stays critical.

## 6. Weather tables (offline; after steps 3 and 4)

```bash
python -m flight_delay.data.weather_join --station-map deliverables/data/raw/iem_asos/station_map.json
```

Writes `layer/weather_t120m/` and `layer/weather_oracle/` per month and `layer/weather-summary.json`. Before writing,
every month is checked row by row (observation time <= target time, age <= 3 h, T-table cutoff <= `crs_dep_utc - T -
10 min`); a violation stops the run with `TimingError`. Options: `--horizon-hours` (T, default 2),
`--margin-minutes` (default 10), `--lookback-hours` (default 3). The oracle table is labelled (`is_oracle = True`) and
is only for the oracle experiment.

## Layout produced

```
deliverables/data/layer/
  flights/year=YYYY/month=MM/{part-0.parquet, summary.json}
  flight_labels/year=YYYY/month=MM/part-0.parquet
  flight_keys/year=YYYY/month=MM/part-0.parquet          (local only, never exported)
  scheduled_density/year=YYYY/month=MM/part-0.parquet
  metar/{metar.parquet, metar-stats.json}
  weather_t120m/year=YYYY/month=MM/part-0.parquet
  weather_oracle/year=YYYY/month=MM/part-0.parquet
  weather-summary.json
```

Raw data and the layer are not committed to git (add `deliverables/data/raw/` and `deliverables/data/layer/` to
`.gitignore` if not already there).
