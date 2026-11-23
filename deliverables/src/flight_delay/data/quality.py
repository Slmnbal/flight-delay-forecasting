"""Layer data quality checks (NO NETWORK) -> per-month report JSON + summary Markdown.

Results are produced at run time; no result number is written in this file.
Statuses: "passed" | "warning" | "critical" | "skipped". Exit code: 0 (no critical), 2 (critical present).
On a critical violation the pipeline STOPS (reported to the DS / CEO); warnings are written with cause
and impact. This module drops no row; it only measures (the layer itself drops rows with an empty key field,
and ``dropped_missing_key_rows`` reports that count from summary.json; "skipped" + ``unknown`` = not recorded).

THRESHOLDS: the THRESHOLDS values below are the AUTHOR'S choice (defaults; not validated on real data).
Review them after the first real run. (warning, critical) = upper bound of the violation RATIO;
None = that level does not exist. E.g. (0.0, 0.01): any violation is a warning, > 1% is critical.

Checks:
  schema (missing/extra columns, type match), row count (zero, raw <-> layer summary, previous run),
  duplicates (flight key), ranges (date outside month, hhmm, flags, negative/outlier minutes,
  duration), internal consistency (cancellation/delay/ArrDel15), UTC consistency (UTC duration <->
  CRSElapsedTime, actual UTC <-> DepDelay/ArrDelay), missing ratios, period (month gaps, row deviation).

Usage:
  python -m flight_delay.data.quality
  python -m flight_delay.data.quality --previous deliverables/data/quality-report.json   # row count comparison
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.inputs import require_file
from flight_delay.data.layer import (
    DEFAULT_LAYER_DIR,
    DEFAULT_TARGETS_FILE,
    KEY_FIELDS_FILLED,
    OUTPUT_SCHEMA,
    PARQUET_NAME,
    SCOPE_MODES,
    SUMMARY_NAME,
    read_targets,
    read_wide_month,
)
from flight_delay.data.tables import FLIGHTS
from flight_delay.paths import DATA_DIR

__all__ = [
    "KEY_FIELDS_FILLED",
    "THRESHOLDS",
    "check_month",
    "check_period",
    "content_hash",
    "find_months",
    "main",
    "render_markdown",
    "run_checks",
]

DEFAULT_JSON = DATA_DIR / "quality-report.json"
DEFAULT_MD = DATA_DIR / "quality-report.md"

FLIGHT_KEY = ["FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime"]
NEVER_NEGATIVE = [
    "DepDelayMinutes",
    "ArrDelayMinutes",
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
    "TaxiOut",
    "TaxiIn",
    "AirTime",
    "ActualElapsedTime",
]
MUST_BE_POSITIVE = ["Distance", "CRSElapsedTime"]
DELAY_RANGE = (-180.0, 3000.0)  # min; the author's plausible range (an outlier can be real -> warning only)
CRS_DURATION_UPPER_MIN = 1000.0  # min; the author's upper bound for scheduled US domestic duration
UTC_DIFF_MIN = 60.0  # accepted difference between UTC duration and CRSElapsedTime
ACTUAL_DIFF_MIN = 1.0  # accepted difference between (dep_utc - crs_dep_utc) and DepDelay
PERIOD_DEVIATION_RATIO = 0.30  # relative deviation of a month's row count from the median (warning)

# name -> (warning_upper_bound, critical_upper_bound)  [level applies if the violation ratio > bound]
THRESHOLDS: dict[str, tuple[float | None, float | None]] = {
    "duplicate_flight_key": (0.0, 0.01),
    "duplicate_flight_uid": (None, 0.0),
    "date_outside_month": (None, 0.0),
    "year_month_column_mismatch": (None, 0.0),
    "rows_outside_target_scope": (None, 0.0),
    "invalid_hhmm_crs": (0.0, 0.001),
    "invalid_hhmm_actual": (0.0, 0.001),
    # key_field_missing stays strict (critical on any empty key field): since process_month drops such rows, the
    # layer must contain none. A hit here means the drop did not run (old layer) or the layer was written by other code.
    "key_field_missing": (None, 0.0),
    # Rows process_month dropped for an empty key field, as a share of the rows that existed before the drop
    # (in scope). Any drop is a warning (it must stay visible). 0.001 (0.1%) is the author's choice: the one
    # known case (2024-08) was 1 row in ~3.6M (~0.00003%), so 0.1% is thousands of times larger than the known
    # background rate; a ratio above it hints at a damaged source file rather than a sporadic BTS blank.
    "dropped_missing_key_rows": (0.0, 0.001),
    "invalid_flag_value": (None, 0.0),
    "negative_minutes": (0.0, 0.01),
    "non_positive_duration_distance": (0.0, 0.01),
    "crs_duration_upper_bound": (0.0, 0.01),
    "delay_plausible_range": (0.0, None),
    "delay_fractional": (0.0, None),
    "delay_minutes_inconsistent": (0.0, 0.01),
    "arr_del15_flag_inconsistent": (0.0, 0.01),
    "cancelled_but_arr_delay_present": (0.0, 0.01),
    "not_cancelled_arr_delay_missing": (0.005, 0.05),
    "not_cancelled_dep_time_missing": (0.005, 0.05),
    "utc_departure_missing": (None, 0.0),
    "utc_arrival_missing": (0.0, 0.01),
    "utc_tz_missing_rows": (0.0, 0.01),
    "utc_duration_non_positive": (0.0, 0.001),
    "utc_duration_crs_mismatch": (0.001, 0.01),
    "utc_actual_departure_mismatch": (0.001, 0.01),
    "utc_actual_arrival_mismatch": (0.001, 0.01),
    # independent of the delay arithmetic: local clock reading of the actual UTC vs the BTS DepTime/ArrTime
    # (author's choice: informational, warning only; review after the first full run)
    "actual_local_time_mismatch": (0.0, None),
}


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("float64")


def _flag(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)


def _kind_of(series: pd.Series) -> str:
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    return "text"


def _result(name: str, status: str, value: dict[str, Any], description: str, threshold: Any = None) -> dict[str, Any]:
    return {"name": name, "status": status, "value": value, "threshold": threshold, "description": description}


def _ratio_check(
    name: str, violations: int, total: int, description: str, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    warning_bound, critical_bound = THRESHOLDS[name]
    ratio = (violations / total) if total else 0.0
    if violations > 0 and critical_bound is not None and ratio > critical_bound:
        status = "critical"
    elif violations > 0 and warning_bound is not None and ratio > warning_bound:
        status = "warning"
    else:
        status = "passed"
    value: dict[str, Any] = {"violations": int(violations), "total": int(total), "ratio": round(float(ratio), 6)}
    if extra:
        value.update(extra)
    return _result(name, status, value, description, {"warning": warning_bound, "critical": critical_bound})


def _hhmm_invalid(series: pd.Series) -> pd.Series:
    values = _num(series)
    hours = np.floor(values / 100)
    minutes = values - hours * 100
    valid = (
        (values >= 0)
        & (values == np.floor(values))
        & (minutes <= 59)
        & ((hours < 24) | ((hours == 24) & (minutes == 0)))
    )
    return values.notna() & ~valid


def _local_hhmm(utc: pd.Series, tz: pd.Series) -> pd.Series:
    """Naive-UTC timestamps -> local clock reading as hhmm (float; NaN where the time or time zone is missing)."""
    result = pd.Series(np.nan, index=utc.index, dtype="float64")
    valid = utc.notna() & tz.notna()
    for name, group in utc[valid].groupby(tz[valid].astype(str)):
        local = group.dt.tz_localize("UTC").dt.tz_convert(str(name))
        result.loc[group.index] = (local.dt.hour * 100 + local.dt.minute).to_numpy(dtype="float64")
    return result


def content_hash(df: pd.DataFrame) -> str:
    """Order-independent content digest (same input -> same value; may change if environment/versions change)."""
    columns = [
        c
        for c in ("flight_id", "Tail_Number", "ArrDelay", "DepDelay", "Cancelled", "crs_dep_utc", "crs_arr_utc")
        if c in df.columns
    ]
    if not columns or len(df) == 0:
        return "0" * 16
    hashes = pd.util.hash_pandas_object(df[columns], index=False).to_numpy(dtype="uint64")
    return format(int(hashes.sum(dtype=np.uint64)), "016x")


def _overall_status(checks: list[dict[str, Any]]) -> str:
    if any(c["status"] == "critical" for c in checks):
        return "critical"
    if any(c["status"] == "warning" for c in checks):
        return "warning"
    return "passed"


# ----------------------------------------------------------------------------
# month check
# ----------------------------------------------------------------------------


def check_month(
    df: pd.DataFrame,
    year: int,
    month: int,
    targets: list[str] | None = None,
    scope: str = "origin",
    summary: dict[str, Any] | None = None,
    previous_rows: int | None = None,
) -> dict[str, Any]:
    """Check one month's layer DataFrame; return the report dict."""
    n = int(len(df))
    checks: list[dict[str, Any]] = []

    # ---- schema ----
    missing = [c for c in OUTPUT_SCHEMA if c not in df.columns]
    extra = [c for c in df.columns if c not in OUTPUT_SCHEMA]
    mismatched = {
        c: {"expected": OUTPUT_SCHEMA[c], "actual": _kind_of(df[c])}
        for c in OUTPUT_SCHEMA
        if c in df.columns and _kind_of(df[c]) != OUTPUT_SCHEMA[c]
    }
    checks.append(
        _result(
            "schema_missing_column",
            "critical" if missing else "passed",
            {"missing": missing},
            "All expected columns must be present.",
            {"critical": 0},
        )
    )
    checks.append(
        _result(
            "schema_extra_column",
            "warning" if extra else "passed",
            {"extra": extra},
            "A column that is not in the schema exists (schema version drift?).",
            {"warning": 0},
        )
    )
    checks.append(
        _result(
            "schema_type_mismatch",
            "critical" if mismatched else "passed",
            {"mismatched": mismatched},
            "Column kinds (integer/float/text/datetime/boolean) must match the schema.",
            {"critical": 0},
        )
    )
    checks.append(
        _result(
            "zero_rows", "critical" if n == 0 else "passed", {"rows": n}, "A month cannot be empty.", {"critical": 0}
        )
    )
    if missing or n == 0:
        checks.append(
            _result(
                "other_checks", "skipped", {}, "Schema is incomplete or the month is empty; other checks were not run."
            )
        )
        return {
            "year": year,
            "month": month,
            "rows": n,
            "status": _overall_status(checks),
            "checks": checks,
            "missing_ratios": {},
            "hash": content_hash(df),
        }

    # ---- row count ----
    if summary is not None and summary.get("rows_layer") is not None:
        difference = n - int(summary["rows_layer"])
        checks.append(
            _result(
                "row_count_matches_summary",
                "critical" if difference else "passed",
                {"parquet": n, "summary_json": int(summary["rows_layer"])},
                "The Parquet row count must equal summary.json (half-written / corrupt write check).",
                {"critical": 0},
            )
        )
        checks.append(
            _result(
                "rows_raw_vs_layer",
                "passed",
                {
                    "rows_raw": summary.get("rows_raw"),
                    "rows_layer": summary.get("rows_layer"),
                    "scope": summary.get("scope"),
                },
                "Info: rows removed by the scope filter and by the missing-key drop (see dropped_missing_key_rows).",
            )
        )
    dropped = summary.get("rows_dropped_missing_key") if summary is not None else None
    if dropped is None:
        # Old summary (written before the drop rule existed) or no summary: NOT silently "passed".
        checks.append(
            _result(
                "dropped_missing_key_rows",
                "skipped",
                {
                    "unknown": True,
                    "reason": "summary.json has no rows_dropped_missing_key (month processed before the rule)",
                },
                "UNKNOWN: rows dropped for an empty key field are not recorded for this month; re-process the month.",
            )
        )
    else:
        checks.append(
            _ratio_check(
                "dropped_missing_key_rows",
                int(dropped),
                n + int(dropped),
                f"Rows dropped by the layer because a key field {KEY_FIELDS_FILLED} was empty "
                "(any drop is a warning; ratio above the critical bound is critical).",
                {"per_field": summary.get("dropped_missing_key_by_field") if summary is not None else None},
            )
        )
    if previous_rows is not None:
        checks.append(
            _result(
                "rows_vs_previous_run",
                "warning" if previous_rows != n else "passed",
                {"previous": int(previous_rows), "current": n},
                "A second run on the same input must give the same row count.",
                {"warning": 0},
            )
        )

    # ---- duplicates ----
    duplicates = int(df.duplicated(subset=FLIGHT_KEY, keep="first").sum())
    checks.append(
        _ratio_check("duplicate_flight_key", duplicates, n, f"Extra rows that repeat the flight key {FLIGHT_KEY}.")
    )
    checks.append(
        _ratio_check(
            "duplicate_flight_uid",
            int(df.duplicated(subset=["flight_uid"], keep="first").sum()),
            n,
            "flight_uid is the surrogate key shared by flights / flight_labels / flight_keys and must be unique.",
        )
    )

    # ---- date / month ----
    flight_date = df["FlightDate"]
    outside = int((~((flight_date.dt.year == year) & (flight_date.dt.month == month))).sum())
    checks.append(
        _ratio_check(
            "date_outside_month", outside, n, f"Rows whose FlightDate is outside {year}-{month:02d} (or missing)."
        )
    )
    ym_mismatch = int((_flag(_num(df["Year"]) != year) | _flag(_num(df["Month"]) != month)).sum())
    checks.append(
        _ratio_check(
            "year_month_column_mismatch",
            ym_mismatch,
            n,
            "The Year/Month column does not match the partition (year/month).",
        )
    )

    # ---- scope ----
    if targets:
        target_set = {t.upper() for t in targets}
        origin_in, dest_in = df["Origin"].isin(target_set), df["Dest"].isin(target_set)
        in_scope = {"origin": origin_in, "origin_or_dest": origin_in | dest_in, "origin_and_dest": origin_in & dest_in}[
            scope
        ]
        checks.append(
            _ratio_check(
                "rows_outside_target_scope",
                int((~in_scope).sum()),
                n,
                f"scope={scope}: rows outside the target list.",
            )
        )
    else:
        checks.append(_result("rows_outside_target_scope", "skipped", {}, "No target list was given."))

    # ---- hhmm ----
    invalid_crs = int((_hhmm_invalid(df["CRSDepTime"]) | _hhmm_invalid(df["CRSArrTime"])).sum())
    checks.append(
        _ratio_check(
            "invalid_hhmm_crs", invalid_crs, n, "CRSDepTime/CRSArrTime is not a valid hhmm (0000-2400, min<=59)."
        )
    )
    invalid_actual = int((_hhmm_invalid(df["DepTime"]) | _hhmm_invalid(df["ArrTime"])).sum())
    checks.append(_ratio_check("invalid_hhmm_actual", invalid_actual, n, "DepTime/ArrTime is not a valid hhmm."))

    # ---- key fields + missing ratios ----
    missing_counts = {c: int(df[c].isna().sum()) for c in KEY_FIELDS_FILLED}
    checks.append(
        _ratio_check(
            "key_field_missing",
            sum(missing_counts.values()),
            n * len(KEY_FIELDS_FILLED),
            f"Key fields must be filled: {KEY_FIELDS_FILLED}",
            {"per_column": missing_counts},
        )
    )
    missing_ratios = {c: round(float(df[c].isna().sum()) / n, 6) for c in df.columns}

    # ---- flags ----
    cancelled_values, diverted_values = _num(df["Cancelled"]), _num(df["Diverted"])
    bad_flags = int(
        (cancelled_values.notna() & ~cancelled_values.isin([0.0, 1.0])).sum()
        + (diverted_values.notna() & ~diverted_values.isin([0.0, 1.0])).sum()
    )
    checks.append(_ratio_check("invalid_flag_value", bad_flags, n, "Cancelled/Diverted can only be 0 or 1."))

    # ---- minute ranges ----
    negatives = {c: int((_num(df[c]) < 0).sum()) for c in NEVER_NEGATIVE}
    checks.append(
        _ratio_check(
            "negative_minutes",
            sum(negatives.values()),
            n * len(NEVER_NEGATIVE),
            "Duration / delay-minute / cause columns cannot be negative.",
            {"per_column": negatives},
        )
    )
    non_positive = {c: int((_num(df[c]) <= 0).sum()) for c in MUST_BE_POSITIVE}
    checks.append(
        _ratio_check(
            "non_positive_duration_distance",
            sum(non_positive.values()),
            n * len(MUST_BE_POSITIVE),
            "Distance and CRSElapsedTime must be > 0.",
            {"per_column": non_positive},
        )
    )
    checks.append(
        _ratio_check(
            "crs_duration_upper_bound",
            int((_num(df["CRSElapsedTime"]) > CRS_DURATION_UPPER_MIN).sum()),
            n,
            f"CRSElapsedTime > {CRS_DURATION_UPPER_MIN:g} min (the author's plausible upper bound).",
        )
    )
    dep_delay, arr_delay = _num(df["DepDelay"]), _num(df["ArrDelay"])
    outliers = int(
        ((dep_delay < DELAY_RANGE[0]) | (dep_delay > DELAY_RANGE[1])).sum()
        + ((arr_delay < DELAY_RANGE[0]) | (arr_delay > DELAY_RANGE[1])).sum()
    )
    checks.append(
        _ratio_check(
            "delay_plausible_range",
            outliers,
            n * 2,
            f"DepDelay/ArrDelay outside {DELAY_RANGE} min (a real outlier is possible; warning only).",
        )
    )
    fractional = int(
        (dep_delay.notna() & (dep_delay != np.floor(dep_delay))).sum()
        + (arr_delay.notna() & (arr_delay != np.floor(arr_delay))).sum()
    )
    checks.append(
        _ratio_check(
            "delay_fractional", fractional, n * 2, "BTS delay minutes are integers; fractional values are not expected."
        )
    )

    # ---- internal consistency ----
    dep_minutes, arr_minutes = _num(df["DepDelayMinutes"]), _num(df["ArrDelayMinutes"])
    dep_mask, arr_mask = dep_delay.notna() & dep_minutes.notna(), arr_delay.notna() & arr_minutes.notna()
    inconsistent = int(
        ((dep_minutes - dep_delay.clip(lower=0)).abs() > 0)[dep_mask].sum()
        + ((arr_minutes - arr_delay.clip(lower=0)).abs() > 0)[arr_mask].sum()
    )
    checks.append(
        _ratio_check(
            "delay_minutes_inconsistent",
            inconsistent,
            int(dep_mask.sum() + arr_mask.sum()),
            "DepDelayMinutes = max(DepDelay,0) and ArrDelayMinutes = max(ArrDelay,0) must hold.",
        )
    )
    arr_del15 = _num(df["ArrDel15"])
    flag_mask = arr_del15.notna() & arr_minutes.notna()
    flag_wrong = int(((arr_del15 == 1) != (arr_minutes >= 15))[flag_mask].sum())
    checks.append(
        _ratio_check(
            "arr_del15_flag_inconsistent",
            flag_wrong,
            int(flag_mask.sum()),
            "ArrDel15 (the target label) must equal ArrDelayMinutes >= 15.",
        )
    )
    cancelled = cancelled_values == 1
    diverted = diverted_values == 1
    checks.append(
        _ratio_check(
            "cancelled_but_arr_delay_present",
            int((cancelled & arr_delay.notna()).sum()),
            int(cancelled.sum()),
            "A cancelled flight's ArrDelay must be empty.",
        )
    )
    checks.append(
        _ratio_check(
            "not_cancelled_arr_delay_missing",
            int((~cancelled & ~diverted & arr_delay.isna()).sum()),
            int((~cancelled & ~diverted).sum()),
            "A flight that is neither cancelled nor diverted must have ArrDelay (the target label).",
        )
    )
    checks.append(
        _ratio_check(
            "not_cancelled_dep_time_missing",
            int((~cancelled & _num(df["DepTime"]).isna()).sum()),
            int((~cancelled).sum()),
            "A flight that was not cancelled must have DepTime.",
        )
    )

    # ---- UTC consistency ----
    checks.append(
        _ratio_check(
            "utc_departure_missing",
            int((df["CRSDepTime"].notna() & df["crs_dep_utc"].isna()).sum()),
            n,
            "CRSDepTime is filled but crs_dep_utc is empty (the target airport's time zone must be known).",
        )
    )
    checks.append(
        _ratio_check(
            "utc_arrival_missing",
            int((df["CRSArrTime"].notna() & df["crs_arr_utc"].isna()).sum()),
            n,
            "CRSArrTime is filled but crs_arr_utc is empty (Dest time zone could not be mapped or the window is inconsistent).",
            {
                "tz_missing_dest": sorted(
                    set(df.loc[df["crs_arr_utc"].isna() & df["CRSArrTime"].notna(), "Dest"].dropna().astype(str))
                )[:50]
            },
        )
    )
    checks.append(
        _ratio_check(
            "utc_tz_missing_rows",
            int(_flag(df["utc_tz_missing"]).sum()),
            n,
            "Rows whose Origin or Dest time zone could not be mapped (UTC NaT).",
        )
    )
    duration = (df["crs_arr_utc"] - df["crs_dep_utc"]).dt.total_seconds() / 60
    checks.append(
        _ratio_check(
            "utc_duration_non_positive",
            int((duration <= 0).sum()),
            int(duration.notna().sum()),
            "UTC arrival must be after UTC departure.",
        )
    )
    diff = (duration - _num(df["CRSElapsedTime"])).abs()
    valid_diff = diff.notna()
    median_diff = round(float(diff[valid_diff].median()), 2) if valid_diff.any() else None
    share_zero = round(float((diff[valid_diff] == 0).mean()), 4) if valid_diff.any() else None
    checks.append(
        _ratio_check(
            "utc_duration_crs_mismatch",
            int((diff > UTC_DIFF_MIN).sum()),
            int(valid_diff.sum()),
            f"|UTC duration - CRSElapsedTime| > {UTC_DIFF_MIN:g} min (a sign of a time zone / day rollover error; "
            "BTS's own inconsistency is possible too).",
            {"median_diff_min": median_diff, "share_diff_0": share_zero},
        )
    )
    dep_diff = ((df["dep_utc"] - df["crs_dep_utc"]).dt.total_seconds() / 60 - dep_delay).abs()
    checks.append(
        _ratio_check(
            "utc_actual_departure_mismatch",
            int((dep_diff > ACTUAL_DIFF_MIN).sum()),
            int(dep_diff.notna().sum()),
            "(dep_utc - crs_dep_utc) must agree with DepDelay. Since the M2 fix dep_utc is built from DepDelay, so "
            "this guards the arithmetic itself; the independent check is actual_local_time_mismatch.",
        )
    )
    arr_diff = ((df["arr_utc"] - df["crs_arr_utc"]).dt.total_seconds() / 60 - arr_delay).abs()
    arr_diff = arr_diff.where(~diverted)
    checks.append(
        _ratio_check(
            "utc_actual_arrival_mismatch",
            int((arr_diff > ACTUAL_DIFF_MIN).sum()),
            int(arr_diff.notna().sum()),
            "(arr_utc - crs_arr_utc) must agree with ArrDelay (diverted flights excluded).",
        )
    )
    # Independent of the delay arithmetic: the local clock reading of dep_utc / arr_utc must equal BTS DepTime /
    # ArrTime (2400 counts as 0000). Catches time zone errors, DST handling errors and BTS-internal inconsistency.
    dep_local = _local_hhmm(df["dep_utc"], df["tz_origin"])
    arr_local = _local_hhmm(df["arr_utc"], df["tz_dest"])
    dep_clock, arr_clock = _num(df["DepTime"]), _num(df["ArrTime"])
    dep_clock, arr_clock = dep_clock.mask(dep_clock == 2400, 0.0), arr_clock.mask(arr_clock == 2400, 0.0)
    dep_compared, arr_compared = dep_local.notna() & dep_clock.notna(), arr_local.notna() & arr_clock.notna()
    dep_clock_wrong = int((dep_compared & (dep_local != dep_clock)).sum())
    arr_clock_wrong = int((arr_compared & (arr_local != arr_clock)).sum())
    checks.append(
        _ratio_check(
            "actual_local_time_mismatch",
            dep_clock_wrong + arr_clock_wrong,
            int(dep_compared.sum() + arr_compared.sum()),
            "Local clock reading of dep_utc / arr_utc differs from BTS DepTime / ArrTime (informational; "
            "possible causes: time zone or DST error, BTS inconsistency).",
            {"departure": dep_clock_wrong, "arrival": arr_clock_wrong},
        )
    )

    return {
        "year": year,
        "month": month,
        "rows": n,
        "status": _overall_status(checks),
        "checks": checks,
        "missing_ratios": missing_ratios,
        "hash": content_hash(df),
    }


# ----------------------------------------------------------------------------
# period check
# ----------------------------------------------------------------------------


def check_period(months: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cross-month checks: month gaps (critical) and row-count deviation (warning)."""
    checks: list[dict[str, Any]] = []
    if not months:
        return [_result("period_empty", "critical", {}, "No month was found.", {"critical": 0})]
    present = sorted((m["year"], m["month"]) for m in months)
    year, month = present[0]
    expected = []
    while (year, month) <= present[-1]:
        expected.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    gaps = [f"{y}-{m:02d}" for y, m in expected if (y, m) not in set(present)]
    checks.append(
        _result(
            "period_month_gap",
            "critical" if gaps else "passed",
            {
                "first": f"{present[0][0]}-{present[0][1]:02d}",
                "last": f"{present[-1][0]}-{present[-1][1]:02d}",
                "month_count": len(present),
                "missing_months": gaps,
            },
            "There must be no missing month between the first and last month (a whole missing period is critical).",
            {"critical": 0},
        )
    )
    row_counts = [m["rows"] for m in months if m["rows"] > 0]
    if len(row_counts) >= 3:
        median = float(np.median(row_counts))
        deviating = {
            f"{m['year']}-{m['month']:02d}": round(m["rows"] / median - 1, 3)
            for m in months
            if median and abs(m["rows"] / median - 1) > PERIOD_DEVIATION_RATIO
        }
        checks.append(
            _result(
                "period_row_deviation",
                "warning" if deviating else "passed",
                {"median_rows": median, "deviating_months_relative": deviating},
                f"A month's row count deviates more than {int(PERIOD_DEVIATION_RATIO * 100)}% from the median "
                "(may be seasonality; may signal missing data).",
                {"warning": PERIOD_DEVIATION_RATIO},
            )
        )
    else:
        checks.append(
            _result(
                "period_row_deviation",
                "skipped",
                {"month_count": len(row_counts)},
                "At least 3 months are needed for the median.",
            )
        )
    return checks


# ----------------------------------------------------------------------------
# whole layer
# ----------------------------------------------------------------------------


def find_months(layer_root: Path) -> list[tuple[int, int, Path]]:
    """Find (year, month, flights parquet path) for every processed partition under the layer root."""
    found = []
    for path in sorted(Path(layer_root).glob(f"{FLIGHTS}/year=*/month=*/{PARQUET_NAME}")):
        year_match = re.fullmatch(r"year=(\d{4})", path.parent.parent.name)
        month_match = re.fullmatch(r"month=(\d{2})", path.parent.name)
        if year_match and month_match:
            found.append((int(year_match.group(1)), int(month_match.group(1)), path))
    return sorted(found)


def run_checks(
    layer_root: Path,
    targets: list[str] | None = None,
    scope: str = "origin",
    previous_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check every month in the layer and the period; return the full report."""
    previous = {(m["year"], m["month"]): m["rows"] for m in (previous_report or {}).get("months", [])}
    months = []
    for year, month, path in find_months(layer_root):
        summary_path = path.parent / SUMMARY_NAME
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else None
        df = read_wide_month(layer_root, year, month)
        months.append(check_month(df, year, month, targets, scope, summary, previous.get((year, month))))
        del df
    period = check_period(months)
    all_checks = [c for m in months for c in m["checks"]] + period
    return {
        "meta": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "scope": scope,
            "target_count": len(targets) if targets else None,
        },
        "thresholds": {name: {"warning": w, "critical": c} for name, (w, c) in THRESHOLDS.items()},
        "months": months,
        "period_checks": period,
        "overall_status": _overall_status(all_checks),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Data layer quality report",
        "",
        "This file was produced by `quality.py` from a run (it was not written by hand).",
        f"Scope mode: `{report['meta']['scope']}`; pandas {report['meta']['pandas']}; "
        f"**Overall status: {report['overall_status'].upper()}**",
        "",
        "Thresholds live in the THRESHOLDS dict in `quality.py` (the author's defaults; not validated on real data).",
        "",
        "## Month summary",
        "",
        "| Month | Rows | Status | Critical | Warnings | Hash |",
        "|---|---:|---|---:|---:|---|",
    ]
    for m in report["months"]:
        critical = sum(1 for c in m["checks"] if c["status"] == "critical")
        warnings = sum(1 for c in m["checks"] if c["status"] == "warning")
        lines.append(
            f"| {m['year']}-{m['month']:02d} | {m['rows']} | {m['status']} | {critical} | {warnings} | `{m['hash']}` |"
        )
    lines += ["", "## Period checks", ""]
    for c in report["period_checks"]:
        lines.append(
            f"- **{c['name']}**: {c['status']} -- {c['description']} Value: `{json.dumps(c['value'], ensure_ascii=False)}`"
        )
    lines += ["", "## Critical and warning findings (per month)", ""]
    any_finding = False
    for m in report["months"]:
        for c in m["checks"]:
            if c["status"] in ("critical", "warning"):
                any_finding = True
                lines.append(
                    f"- {m['year']}-{m['month']:02d} **{c['status']}** `{c['name']}`: {c['description']} "
                    f"Value: `{json.dumps(c['value'], ensure_ascii=False)}`"
                )
    if not any_finding:
        lines.append("No findings.")
    unknown_months = [
        f"{m['year']}-{m['month']:02d}"
        for m in report["months"]
        for c in m["checks"]
        if c["name"] == "dropped_missing_key_rows" and c["status"] == "skipped"
    ]
    lines += ["", "## Missing-key drop record", ""]
    if unknown_months:
        lines.append(f"UNKNOWN (no drop record in summary.json; re-process to know): {', '.join(unknown_months)}")
    else:
        lines.append("Every month has a drop record (`dropped_missing_key_rows`; see findings if any row was dropped).")
    # missing ratios: per-column lowest/highest monthly ratio (only columns with > 0)
    per_column: dict[str, list[float]] = {}
    for m in report["months"]:
        for column, ratio in m["missing_ratios"].items():
            per_column.setdefault(column, []).append(ratio)
    lines += [
        "",
        "## Missing-value ratios (only columns that have missing values)",
        "",
        "Empty actual-flight fields are EXPECTED for cancelled flights; cause minutes are filled only for delays >= 15 min.",
        "",
        "| Column | Lowest monthly ratio | Highest monthly ratio |",
        "|---|---:|---:|",
    ]
    for column, ratios in per_column.items():
        if max(ratios) > 0:
            lines.append(f"| {column} | {min(ratios):.4f} | {max(ratios):.4f} |")
    lines += ["", "## Check glossary", ""]
    sample = report["months"][0]["checks"] if report["months"] else []
    for c in sample:
        lines.append(f"- `{c['name']}`: {c['description']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Layer data quality check (no network).")
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS_FILE)
    parser.add_argument("--scope", choices=SCOPE_MODES, default="origin")
    parser.add_argument(
        "--no-targets",
        action="store_true",
        help="Skip the target-scope check on purpose (otherwise a missing --targets-file is an error).",
    )
    parser.add_argument(
        "--previous",
        type=Path,
        default=None,
        help="Previous quality-report.json (row count comparison). If given, the file must exist.",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args(argv)

    targets = None if args.no_targets else read_targets(args.targets_file)  # read_targets raises if the file is missing
    previous = (
        json.loads(require_file(args.previous, "previous quality report", "--previous").read_text(encoding="utf-8"))
        if args.previous
        else None
    )
    report = run_checks(args.layer_dir, targets, args.scope, previous)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"Overall status: {report['overall_status']}; months: {len(report['months'])}")
    print(f"Written: {args.output_json}\n         {args.output_md}")
    return 2 if report["overall_status"] == "critical" else 0


if __name__ == "__main__":
    sys.exit(main())
