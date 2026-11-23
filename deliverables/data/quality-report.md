# Data layer quality report

This file was produced by `quality.py` from a run (it was not written by hand).
Scope mode: `origin`; pandas 3.1.1; **Overall status: WARNING**

Thresholds live in the THRESHOLDS dict in `quality.py` (the author's defaults; not validated on real data).

## Month summary

| Month | Rows | Status | Critical | Warnings | Hash |
|---|---:|---|---:|---:|---|
| 2023-09 | 372829 | passed | 0 | 0 | `7a16608372d1162b` |
| 2023-10 | 391716 | warning | 0 | 2 | `65a27a61b8c13a77` |
| 2023-11 | 369394 | warning | 0 | 1 | `48ade389b56b936e` |
| 2023-12 | 371837 | warning | 0 | 3 | `1b6e473dacd31ca3` |
| 2024-01 | 356179 | warning | 0 | 1 | `1e084853971de558` |
| 2024-02 | 338127 | passed | 0 | 0 | `fe50a3a32244e686` |
| 2024-03 | 384343 | warning | 0 | 3 | `db1cea10250ebe68` |
| 2024-04 | 379691 | warning | 0 | 2 | `488105df2bde7f34` |
| 2024-05 | 398225 | warning | 0 | 1 | `8c177ffeca584186` |
| 2024-06 | 393787 | passed | 0 | 0 | `41dae7e02ed47384` |
| 2024-07 | 408551 | warning | 0 | 3 | `8eae75e0d126edd4` |
| 2024-08 | 400860 | warning | 0 | 1 | `577c6de93cec8086` |
| 2024-09 | 379066 | passed | 0 | 0 | `2e8d9c71286e0fd2` |
| 2024-10 | 399435 | passed | 0 | 0 | `c5709cd3613953ce` |
| 2024-11 | 373812 | warning | 0 | 1 | `0f28262537a26a4c` |
| 2024-12 | 382450 | passed | 0 | 0 | `0ed4349ddc8525c7` |
| 2025-01 | 352215 | warning | 0 | 2 | `148c8ae1b6808efe` |
| 2025-02 | 328288 | warning | 0 | 1 | `0201ed0647ecec0e` |
| 2025-03 | 389075 | warning | 0 | 2 | `1f811ca43621d39b` |
| 2025-04 | 378937 | passed | 0 | 0 | `e5b91a48fde2a765` |
| 2025-05 | 392150 | warning | 0 | 2 | `9fd5108b4b2a3295` |
| 2025-06 | 392659 | warning | 0 | 1 | `d7dc84da238d071d` |
| 2025-07 | 405322 | passed | 0 | 0 | `db292d3cff0542c0` |
| 2025-08 | 388162 | passed | 0 | 0 | `c0f77093556b2a9c` |
| 2025-09 | 365245 | passed | 0 | 0 | `8ff7dc21b80121e3` |
| 2025-10 | 393123 | warning | 0 | 1 | `67afcae7e35041e3` |
| 2025-11 | 370313 | warning | 0 | 2 | `85ff3ac72deb9427` |
| 2025-12 | 377327 | passed | 0 | 0 | `0b4a4f63c99f7878` |
| 2026-01 | 354304 | warning | 0 | 3 | `04ffa95f574f8614` |
| 2026-02 | 334815 | passed | 0 | 0 | `94f270c90747c590` |
| 2026-03 | 396712 | warning | 0 | 2 | `862885b557bff822` |
| 2026-04 | 388497 | warning | 0 | 3 | `27eff837808d1980` |
| 2026-05 | 395189 | passed | 0 | 0 | `683b602f120e812a` |
| 2026-06 | 390003 | warning | 0 | 1 | `252eb2c2ac921fec` |
| 2026-07 | 405825 | warning | 0 | 2 | `59496bb79ea2facc` |
| 2026-08 | 392776 | warning | 0 | 1 | `18b3268e01433b49` |

## Period checks

- **period_month_gap**: passed -- There must be no missing month between the first and last month (a whole missing period is critical). Value: `{"first": "2023-09", "last": "2026-08", "month_count": 36, "missing_months": []}`
- **period_row_deviation**: passed -- A month's row count deviates more than 30% from the median (may be seasonality; may signal missing data). Value: `{"median_rows": 386252.5, "deviating_months_relative": {}}`

## Critical and warning findings (per month)

- 2023-10 **warning** `crs_duration_upper_bound`: CRSElapsedTime > 1000 min (the author's plausible upper bound). Value: `{"violations": 1, "total": 391716, "ratio": 3e-06}`
- 2023-10 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 1, "total": 780364, "ratio": 1e-06, "departure": 0, "arrival": 1}`
- 2023-11 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 20, "total": 737604, "ratio": 2.7e-05, "departure": 7, "arrival": 13}`
- 2023-12 **warning** `non_positive_duration_distance`: Distance and CRSElapsedTime must be > 0. Value: `{"violations": 1, "total": 743674, "ratio": 1e-06, "per_column": {"Distance": 0, "CRSElapsedTime": 1}}`
- 2023-12 **warning** `crs_duration_upper_bound`: CRSElapsedTime > 1000 min (the author's plausible upper bound). Value: `{"violations": 1, "total": 371837, "ratio": 3e-06}`
- 2023-12 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 3, "total": 740391, "ratio": 4e-06, "departure": 1, "arrival": 2}`
- 2024-01 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 2, "total": 712358, "ratio": 3e-06}`
- 2024-03 **warning** `non_positive_duration_distance`: Distance and CRSElapsedTime must be > 0. Value: `{"violations": 1, "total": 768686, "ratio": 1e-06, "per_column": {"Distance": 0, "CRSElapsedTime": 1}}`
- 2024-03 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 2, "total": 768686, "ratio": 3e-06}`
- 2024-03 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 175, "total": 761334, "ratio": 0.00023, "departure": 27, "arrival": 148}`
- 2024-04 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 4, "total": 759382, "ratio": 5e-06}`
- 2024-04 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 2, "total": 753416, "ratio": 3e-06, "departure": 0, "arrival": 2}`
- 2024-05 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 1, "total": 784180, "ratio": 1e-06, "departure": 1, "arrival": 0}`
- 2024-07 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 2, "total": 817102, "ratio": 2e-06}`
- 2024-07 **warning** `utc_duration_non_positive`: UTC arrival must be after UTC departure. Value: `{"violations": 12, "total": 408551, "ratio": 2.9e-05}`
- 2024-07 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 2, "total": 790666, "ratio": 3e-06, "departure": 0, "arrival": 2}`
- 2024-08 **warning** `dropped_missing_key_rows`: Rows dropped by the layer because a key field ['FlightDate', 'Reporting_Airline', 'Flight_Number_Reporting_Airline', 'Origin', 'Dest', 'CRSDepTime', 'CRSArrTime', 'Cancelled', 'Diverted'] was empty (any drop is a warning; ratio above the critical bound is critical). Value: `{"violations": 1, "total": 400861, "ratio": 2e-06, "per_field": {"FlightDate": 0, "Reporting_Airline": 0, "Flight_Number_Reporting_Airline": 1, "Origin": 0, "Dest": 0, "CRSDepTime": 0, "CRSArrTime": 0, "Cancelled": 0, "Diverted": 0}}`
- 2024-11 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 8, "total": 743935, "ratio": 1.1e-05, "departure": 3, "arrival": 5}`
- 2025-01 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 2, "total": 704430, "ratio": 3e-06}`
- 2025-01 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 2, "total": 683569, "ratio": 3e-06, "departure": 0, "arrival": 2}`
- 2025-02 **warning** `crs_duration_upper_bound`: CRSElapsedTime > 1000 min (the author's plausible upper bound). Value: `{"violations": 2, "total": 328288, "ratio": 6e-06}`
- 2025-03 **warning** `crs_duration_upper_bound`: CRSElapsedTime > 1000 min (the author's plausible upper bound). Value: `{"violations": 1, "total": 389075, "ratio": 3e-06}`
- 2025-03 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 13, "total": 768790, "ratio": 1.7e-05, "departure": 1, "arrival": 12}`
- 2025-05 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 2, "total": 784300, "ratio": 3e-06}`
- 2025-05 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 6, "total": 775002, "ratio": 8e-06, "departure": 0, "arrival": 6}`
- 2025-06 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 9, "total": 770934, "ratio": 1.2e-05, "departure": 0, "arrival": 9}`
- 2025-10 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 2, "total": 786246, "ratio": 3e-06}`
- 2025-11 **warning** `non_positive_duration_distance`: Distance and CRSElapsedTime must be > 0. Value: `{"violations": 3, "total": 740626, "ratio": 4e-06, "per_column": {"Distance": 0, "CRSElapsedTime": 3}}`
- 2025-11 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 14, "total": 721002, "ratio": 1.9e-05, "departure": 4, "arrival": 10}`
- 2026-01 **warning** `non_positive_duration_distance`: Distance and CRSElapsedTime must be > 0. Value: `{"violations": 3, "total": 708608, "ratio": 4e-06, "per_column": {"Distance": 0, "CRSElapsedTime": 3}}`
- 2026-01 **warning** `crs_duration_upper_bound`: CRSElapsedTime > 1000 min (the author's plausible upper bound). Value: `{"violations": 1, "total": 354304, "ratio": 3e-06}`
- 2026-01 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 10, "total": 673631, "ratio": 1.5e-05, "departure": 0, "arrival": 10}`
- 2026-03 **warning** `non_positive_duration_distance`: Distance and CRSElapsedTime must be > 0. Value: `{"violations": 1, "total": 793424, "ratio": 1e-06, "per_column": {"Distance": 0, "CRSElapsedTime": 1}}`
- 2026-03 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 113, "total": 768521, "ratio": 0.000147, "departure": 17, "arrival": 96}`
- 2026-04 **warning** `non_positive_duration_distance`: Distance and CRSElapsedTime must be > 0. Value: `{"violations": 1, "total": 776994, "ratio": 1e-06, "per_column": {"Distance": 0, "CRSElapsedTime": 1}}`
- 2026-04 **warning** `crs_duration_upper_bound`: CRSElapsedTime > 1000 min (the author's plausible upper bound). Value: `{"violations": 2, "total": 388497, "ratio": 5e-06}`
- 2026-04 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 2, "total": 769391, "ratio": 3e-06, "departure": 0, "arrival": 2}`
- 2026-06 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 6, "total": 765507, "ratio": 8e-06, "departure": 0, "arrival": 6}`
- 2026-07 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 2, "total": 811650, "ratio": 2e-06}`
- 2026-07 **warning** `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency). Value: `{"violations": 7, "total": 786251, "ratio": 9e-06, "departure": 0, "arrival": 7}`
- 2026-08 **warning** `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only). Value: `{"violations": 2, "total": 785552, "ratio": 3e-06}`

## Missing-key drop record

Every month has a drop record (`dropped_missing_key_rows`; see findings if any row was dropped).

## Missing-value ratios (only columns that have missing values)

Empty actual-flight fields are EXPECTED for cancelled flights; cause minutes are filled only for delays >= 15 min.

| Column | Lowest monthly ratio | Highest monthly ratio |
|---|---:|---:|
| Tail_Number | 0.0002 | 0.0111 |
| CRSElapsedTime | 0.0000 | 0.0000 |
| DepTime | 0.0010 | 0.0474 |
| DepDelay | 0.0010 | 0.0475 |
| DepDelayMinutes | 0.0010 | 0.0475 |
| DepDel15 | 0.0010 | 0.0475 |
| TaxiOut | 0.0011 | 0.0480 |
| WheelsOff | 0.0011 | 0.0480 |
| WheelsOn | 0.0012 | 0.0487 |
| TaxiIn | 0.0012 | 0.0487 |
| ArrTime | 0.0012 | 0.0487 |
| ArrDelay | 0.0021 | 0.0504 |
| ArrDelayMinutes | 0.0021 | 0.0504 |
| ArrDel15 | 0.0021 | 0.0504 |
| ActualElapsedTime | 0.0021 | 0.0504 |
| AirTime | 0.0021 | 0.0504 |
| CancellationCode | 0.9517 | 0.9989 |
| CarrierDelay | 0.6907 | 0.8625 |
| WeatherDelay | 0.6907 | 0.8625 |
| NASDelay | 0.6907 | 0.8625 |
| SecurityDelay | 0.6907 | 0.8625 |
| LateAircraftDelay | 0.6907 | 0.8625 |
| dep_utc | 0.0011 | 0.0483 |
| arr_utc | 0.0021 | 0.0504 |
| dep_utc_reason | 0.9517 | 0.9989 |
| arr_utc_reason | 0.9496 | 0.9979 |

## Check glossary

- `schema_missing_column`: All expected columns must be present.
- `schema_extra_column`: A column that is not in the schema exists (schema version drift?).
- `schema_type_mismatch`: Column kinds (integer/float/text/datetime/boolean) must match the schema.
- `zero_rows`: A month cannot be empty.
- `row_count_matches_summary`: The Parquet row count must equal summary.json (half-written / corrupt write check).
- `rows_raw_vs_layer`: Info: rows removed by the scope filter and by the missing-key drop (see dropped_missing_key_rows).
- `dropped_missing_key_rows`: Rows dropped by the layer because a key field ['FlightDate', 'Reporting_Airline', 'Flight_Number_Reporting_Airline', 'Origin', 'Dest', 'CRSDepTime', 'CRSArrTime', 'Cancelled', 'Diverted'] was empty (any drop is a warning; ratio above the critical bound is critical).
- `rows_vs_previous_run`: A second run on the same input must give the same row count.
- `duplicate_flight_key`: Extra rows that repeat the flight key ['FlightDate', 'Reporting_Airline', 'Flight_Number_Reporting_Airline', 'Origin', 'Dest', 'CRSDepTime'].
- `duplicate_flight_uid`: flight_uid is the surrogate key shared by flights / flight_labels / flight_keys and must be unique.
- `date_outside_month`: Rows whose FlightDate is outside 2023-09 (or missing).
- `year_month_column_mismatch`: The Year/Month column does not match the partition (year/month).
- `rows_outside_target_scope`: scope=origin: rows outside the target list.
- `invalid_hhmm_crs`: CRSDepTime/CRSArrTime is not a valid hhmm (0000-2400, min<=59).
- `invalid_hhmm_actual`: DepTime/ArrTime is not a valid hhmm.
- `key_field_missing`: Key fields must be filled: ['FlightDate', 'Reporting_Airline', 'Flight_Number_Reporting_Airline', 'Origin', 'Dest', 'CRSDepTime', 'CRSArrTime', 'Cancelled', 'Diverted']
- `invalid_flag_value`: Cancelled/Diverted can only be 0 or 1.
- `negative_minutes`: Duration / delay-minute / cause columns cannot be negative.
- `non_positive_duration_distance`: Distance and CRSElapsedTime must be > 0.
- `crs_duration_upper_bound`: CRSElapsedTime > 1000 min (the author's plausible upper bound).
- `delay_plausible_range`: DepDelay/ArrDelay outside (-180.0, 3000.0) min (a real outlier is possible; warning only).
- `delay_fractional`: BTS delay minutes are integers; fractional values are not expected.
- `delay_minutes_inconsistent`: DepDelayMinutes = max(DepDelay,0) and ArrDelayMinutes = max(ArrDelay,0) must hold.
- `arr_del15_flag_inconsistent`: ArrDel15 (the target label) must equal ArrDelayMinutes >= 15.
- `cancelled_but_arr_delay_present`: A cancelled flight's ArrDelay must be empty.
- `not_cancelled_arr_delay_missing`: A flight that is neither cancelled nor diverted must have ArrDelay (the target label).
- `not_cancelled_dep_time_missing`: A flight that was not cancelled must have DepTime.
- `utc_departure_missing`: CRSDepTime is filled but crs_dep_utc is empty (the target airport's time zone must be known).
- `utc_arrival_missing`: CRSArrTime is filled but crs_arr_utc is empty (Dest time zone could not be mapped or the window is inconsistent).
- `utc_tz_missing_rows`: Rows whose Origin or Dest time zone could not be mapped (UTC NaT).
- `utc_duration_non_positive`: UTC arrival must be after UTC departure.
- `utc_duration_crs_mismatch`: |UTC duration - CRSElapsedTime| > 60 min (a sign of a time zone / day rollover error; BTS's own inconsistency is possible too).
- `utc_actual_departure_mismatch`: (dep_utc - crs_dep_utc) must agree with DepDelay. Since the M2 fix dep_utc is built from DepDelay, so this guards the arithmetic itself; the independent check is actual_local_time_mismatch.
- `utc_actual_arrival_mismatch`: (arr_utc - crs_arr_utc) must agree with ArrDelay (diverted flights excluded).
- `actual_local_time_mismatch`: Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; possible causes: time zone or DST error, BTS inconsistency).
