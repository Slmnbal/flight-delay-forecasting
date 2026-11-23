"""Feature matrix for the T = 2 h information time (plan sections 2.1 - 2.6). Feature code.

Inputs and who may read what (``deliverables/data/LAYER_SCHEMA.md``):
- ``flights`` (schedule only), ``scheduled_density`` and ``weather_t120m`` -> regular features.
- ``weather_oracle`` -> ONLY with ``oracle=True`` (upper-bound experiment, plan section 6); its columns get the
  ``oracle_`` prefix so they can never be mistaken for T-2 h weather. Default: off.
- ``flight_labels`` -> NEVER here. Past statistics come from a fitted ``HistoryFeatures`` object whose ``fit`` saw
  the fit window only and whose ``transform`` reads key columns only. Any forbidden column (feature_contract) in an
  input frame raises ``LeakageError``.

Feature groups (plan section 2.3; plan names -> code names in ``experiments/modelleme-ad-eslemesi.md``):
- A. schedule: CRS hours / minutes, ``hour_block`` (7 blocks; own derivation, DepTimeBlk is not used),
  CRSElapsedTime, Distance, DistanceGroup, Origin and Reporting_Airline (pandas ``category``), calendar from
  FlightDate (month, day of week, day of month, day of year; NOT Year / Quarter), distance to the nearest US federal
  holiday (rule-based table, no new dependency), scheduled traffic from ``scheduled_density``.
- B. past statistics (``HistoryFeatures``): target-encoded rates with back-off, past quantiles, schedule excess,
  taxi-out median, support counts.
- C. weather before T (``weather_t120m``): origin / dest numeric METAR fields, ceiling (lowest BKN / OVC layer),
  IFR flag, present-weather flags, observation age, missing flags. Row-level check: every observation time
  <= crs_dep_utc - T - margin (plan 2.6 ``test_hava_bilgi_zamani_satir_duzeyi``).
- D. oracle weather: same derivation, ``oracle_`` prefix, checked against crs_dep_utc / crs_arr_utc.

Every matrix is returned with a ``FeatureContract`` that declares every column (plan 2.2 / 2.6:
``test_sozlesme_tum_sutunlari_kapsar``); ``validate_columns`` runs on the final columns.

Memory (16 GB machine; rough, NOT measured): the layer has about 13.69 M rows / 36 months, i.e. about 0.38 M per
month (average). Building features month by month and keeping float32 numerics + category keys costs about
4 bytes x ~60 columns = ~0.25 KB per row, i.e. ~2.3 GB for the 24 training months (~9.1 M rows) plus transient
copies during merges (budget 2x). Do not load all 36 months into one frame: read only the needed months and columns
(``flight_delay.modeling.loading``), and fit ``HistoryFeatures`` on a narrow frame (7 key + 6 label columns).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, Self

import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import (
    FeatureContract,
    FeatureSpec,
    LeakageError,
    forbidden_reason,
    validate_columns,
)
from flight_delay.data.time_conversion import local_clock_series
from flight_delay.modeling import targets as tg
from flight_delay.modeling.history import (
    DEFAULT_M,
    DEFAULT_MIN_SUPPORT,
    DEFAULT_MIN_TAIL,
    BackoffQuantileTable,
    SmoothedRateTable,
    out_of_fold,
)

__all__ = [
    "CATEGORICAL_FEATURES",
    "CEILING_UNLIMITED_FT",
    "CONTRACT_KINDS",
    "DEFAULT_HISTORY_READY_MINUTES",
    "DEFAULT_HORIZON_HOURS",
    "DEFAULT_MARGIN_MINUTES",
    "HISTORY_FEATURES",
    "HOLIDAY_WEEK_DAYS",
    "HOUR_BLOCK_EDGES",
    "SCHEDULE_FEATURES",
    "SEASON_BY_MONTH",
    "SEASON_NAMES",
    "WEATHER_NUMERIC",
    "WX_FLAG_PATTERNS",
    "FeatureMatrix",
    "HistoryFeatures",
    "add_key_columns",
    "aggregate_density",
    "build_contract",
    "build_density_features",
    "build_feature_matrix",
    "build_schedule_features",
    "build_weather_features",
    "check_no_forbidden_inputs",
    "check_weather_timing",
    "days_to_nearest_holiday",
    "hour_block",
    "season",
    "us_federal_holidays",
]

DEFAULT_HORIZON_HOURS = 2.0  # T (decision M3, plan section 2.1)
DEFAULT_MARGIN_MINUTES = 10.0  # METAR publication tolerance (plan section 10.2, assumption)
DEFAULT_HISTORY_READY_MINUTES = 1440  # plan section 2.2: at least 1 day between fit end and the evaluation set

# plan section 2.3: [00-06), [06-09), [09-12), [12-15), [15-18), [18-21), [21-24]; 2400 (minute 1440) -> last block
HOUR_BLOCK_EDGES = (0, 6, 9, 12, 15, 18, 21, 24)
SEASON_BY_MONTH = {12: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3}  # plan section 4.1 (B2)
SEASON_NAMES = ("dec_feb", "mar_may", "jun_aug", "sep_nov")
HOLIDAY_WEEK_DAYS = 3  # "holiday week" = within +-3 days of a holiday (assumption; plan names the feature only)

CATEGORICAL_FEATURES = ("Origin", "Reporting_Airline")
SCHEDULE_FEATURES = (
    "crs_dep_hour",
    "crs_dep_minute_of_day",
    "crs_arr_hour",
    "hour_block",
    "CRSElapsedTime",
    "Distance",
    "DistanceGroup",
    "Origin",
    "Reporting_Airline",
    "month",
    "day_of_week",
    "day_of_month",
    "day_of_year",
    "days_to_holiday",
    "holiday_week",
)
DENSITY_FEATURES = ("planned_departures_origin_hour", "planned_arrivals_dest_hour", "planned_departures_origin_day")

WEATHER_NUMERIC = ("tmpf", "dwpf", "sknt", "gust", "vsby", "p01i")
WX_FLAG_PATTERNS = {"wx_ts": "TS", "wx_sn": "SN", "wx_fzra": "FZRA", "wx_ra": "RA", "wx_fg": "FG"}
CEILING_UNLIMITED_FT = 100_000.0  # no BKN / OVC layer reported (sentinel; assumption)
IFR_CEILING_FT = 1000.0  # plan section 2.3 proposal
IFR_VISIBILITY_MI = 3.0
_CEILING_COVERS = (
    "BKN",
    "OVC",
    "VV",
)  # plan section 2.3; VV (vertical visibility, sky obscured) counts as a ceiling (user decision 2026-11-19)
_SIDES = ("origin", "dest")

ContractKind = Literal["plan", "T2", "oracle"]
CONTRACT_KINDS: tuple[str, ...] = ("plan", "T2", "oracle")
_ALLOWED_KNOWLEDGE = {
    "plan": {"schedule", "past_realized"},
    "T2": {"schedule", "past_realized", "observation_before_T"},
    "oracle": {"schedule", "past_realized", "observation_before_T", "oracle"},
}

_FLIGHT_INPUTS = (
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
)


# ----------------------------------------------------------------------------
# guards
# ----------------------------------------------------------------------------


def _float(values: Any) -> np.ndarray:
    """Any numeric-like input (incl. pandas nullable integers with <NA>) -> float64 ndarray with NaN."""
    return np.asarray(pd.to_numeric(pd.Series(values), errors="coerce").astype("float64"), dtype="float64")


def check_no_forbidden_inputs(frame: pd.DataFrame, what: str) -> None:
    """Feature code must not receive outcome columns at all (not only "not use them")."""
    bad = [f"{c} ({reason})" for c in frame.columns if (reason := forbidden_reason(str(c)))]
    if bad:
        raise LeakageError(f"{what} contains outcome / forbidden column(s); feature code must not receive them: {bad}")


# ----------------------------------------------------------------------------
# A. schedule
# ----------------------------------------------------------------------------


def hour_block(local_minutes: Any) -> np.ndarray:
    """Block 0..6 of the local CRS departure minute (0..1440); -1 where the minute is missing."""
    minutes = _float(local_minutes)
    hours = np.floor(minutes / 60.0)
    blocks = np.searchsorted(np.asarray(HOUR_BLOCK_EDGES[1:-1], dtype="float64"), hours, side="right")
    return np.where(np.isnan(minutes), -1, blocks).astype("int8")


def season(month: Any) -> np.ndarray:
    """0 = Dec-Feb, 1 = Mar-May, 2 = Jun-Aug, 3 = Sep-Nov (plan section 4.1, B2)."""
    months = np.asarray(month, dtype="int64")
    lookup = np.array([SEASON_BY_MONTH[m] for m in range(1, 13)], dtype="int8")
    return np.asarray(lookup[months - 1], dtype="int8")


def add_key_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy of ``frame`` with ``hour_block`` (from crs_dep_local_min), ``month`` and ``season`` (from FlightDate)."""
    out = frame.copy()
    out["hour_block"] = hour_block(out["crs_dep_local_min"])
    months = pd.to_datetime(out["FlightDate"]).dt.month.to_numpy()
    out["month"] = months.astype("int8")
    out["season"] = season(months)
    return out


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    following = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = following - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: dt.date) -> dt.date:
    if day.weekday() == 5:  # Saturday -> Friday
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:  # Sunday -> Monday
        return day + dt.timedelta(days=1)
    return day


def us_federal_holidays(years: Iterable[int]) -> list[dt.date]:
    """US federal holidays (5 U.S.C. 6103 rules), both the actual and the observed date, sorted.

    Rule-based instead of a new dependency (plan section 2.3 suggests a fixed table). Not cross-checked against the
    OPM list in this run (could not access it); the tests pin a few well-known dates.
    """
    days: set[dt.date] = set()
    for year in years:
        fixed = [dt.date(year, 1, 1), dt.date(year, 7, 4), dt.date(year, 11, 11), dt.date(year, 12, 25)]
        if year >= 2021:
            fixed.append(dt.date(year, 6, 19))  # Juneteenth
        for day in fixed:
            days.update({day, _observed(day)})
        days.update(
            {
                _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
                _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
                _last_weekday(year, 5, 0),  # Memorial Day
                _nth_weekday(year, 9, 0, 1),  # Labor Day
                _nth_weekday(year, 10, 0, 2),  # Columbus Day
                _nth_weekday(year, 11, 3, 4),  # Thanksgiving
            }
        )
    return sorted(days)


def days_to_nearest_holiday(dates: pd.Series) -> np.ndarray:
    """Absolute distance in days to the nearest federal holiday (float; NaN for NaT)."""
    days = pd.to_datetime(dates, errors="coerce").dt.normalize()
    valid = days.dropna()
    result = np.full(len(days), np.nan)
    if valid.empty:
        return result
    years = range(int(valid.dt.year.min()) - 1, int(valid.dt.year.max()) + 2)
    holidays = np.array(us_federal_holidays(years), dtype="datetime64[D]")
    values = days.to_numpy(dtype="datetime64[D]")
    mask = ~np.isnat(values)
    position = np.searchsorted(holidays, values[mask])
    before = holidays[np.clip(position - 1, 0, len(holidays) - 1)]
    after = holidays[np.clip(position, 0, len(holidays) - 1)]
    distance = np.minimum(
        np.abs((values[mask] - before).astype("int64")), np.abs((after - values[mask]).astype("int64"))
    )
    result[mask] = distance.astype("float64")
    return result


def _hhmm_hour(hhmm: pd.Series) -> np.ndarray:
    values = _float(hhmm)
    return np.where(np.isnan(values), np.nan, np.floor(values / 100.0) % 24)


def build_schedule_features(flights: pd.DataFrame) -> pd.DataFrame:
    """Group A features (plan section 2.3 A) from the ``flights`` table only."""
    check_no_forbidden_inputs(flights, "flights")
    dates = pd.to_datetime(flights["FlightDate"])
    minutes = _float(flights["crs_dep_local_min"])
    distance_to_holiday = days_to_nearest_holiday(dates)
    out = pd.DataFrame(index=flights.index)
    out["crs_dep_hour"] = (np.floor(minutes / 60.0) % 24).astype("float32")
    out["crs_dep_minute_of_day"] = minutes.astype("float32")
    out["crs_arr_hour"] = _hhmm_hour(flights["CRSArrTime"]).astype("float32")
    out["hour_block"] = hour_block(minutes)
    for column in ("CRSElapsedTime", "Distance", "DistanceGroup"):
        out[column] = _float(flights[column]).astype("float32")
    for column in CATEGORICAL_FEATURES:
        out[column] = flights[column].astype("string").astype("category")
    out["month"] = dates.dt.month.astype("int8")
    out["day_of_week"] = (dates.dt.day_of_week + 1).astype("int8")  # 1 = Monday .. 7 = Sunday (BTS convention)
    out["day_of_month"] = dates.dt.day.astype("int8")
    out["day_of_year"] = dates.dt.day_of_year.astype("int16")
    out["days_to_holiday"] = distance_to_holiday.astype("float32")
    out["holiday_week"] = (distance_to_holiday <= HOLIDAY_WEEK_DAYS).astype("int8")
    return out


def aggregate_density(density: pd.DataFrame) -> pd.DataFrame:
    """SUM over all month files per airport x local date x local hour (LAYER_SCHEMA: consumers must do this)."""
    check_no_forbidden_inputs(density, "scheduled_density")
    frame = density[["airport", "local_date", "local_hour", "planned_departures", "planned_arrivals"]].copy()
    frame["airport"] = frame["airport"].astype(str)
    frame["local_date"] = pd.to_datetime(frame["local_date"]).dt.normalize()
    frame["local_hour"] = pd.to_numeric(frame["local_hour"]).astype("int64")
    for column in ("planned_departures", "planned_arrivals"):
        frame[column] = pd.to_numeric(frame[column]).astype("float64")
    return frame.groupby(["airport", "local_date", "local_hour"], as_index=False)[
        ["planned_departures", "planned_arrivals"]
    ].sum()


def build_density_features(flights: pd.DataFrame, density_aggregated: pd.DataFrame) -> pd.DataFrame:
    """Scheduled traffic at the CRS local departure hour (origin), arrival hour (dest) and departure day (origin).

    Lookups that find no density row stay NaN (never guessed). Input: the output of ``aggregate_density``.
    """
    check_no_forbidden_inputs(flights, "flights")
    offset = pd.Series(_float(flights["crs_arr_day_offset"]), index=flights.index)
    departure_local = local_clock_series(flights["FlightDate"], flights["CRSDepTime"])
    arrival_local = local_clock_series(flights["FlightDate"], flights["CRSArrTime"], offset)

    def lookup(airport: pd.Series, local: pd.Series, column: str) -> np.ndarray:
        keys = pd.DataFrame(
            {
                "airport": airport.astype(str).to_numpy(),
                "local_date": local.dt.normalize().to_numpy(),
                "local_hour": local.dt.hour.astype("float64").to_numpy(),
            }
        )
        right = density_aggregated[["airport", "local_date", "local_hour", column]].copy()
        right["local_hour"] = right["local_hour"].astype("float64")
        joined = keys.merge(right, how="left", on=["airport", "local_date", "local_hour"], validate="many_to_one")
        return np.asarray(joined[column], dtype="float64")

    daily = density_aggregated.groupby(["airport", "local_date"], as_index=False)["planned_departures"].sum()
    day_keys = pd.DataFrame(
        {"airport": flights["Origin"].astype(str).to_numpy(), "local_date": departure_local.dt.normalize().to_numpy()}
    )
    day_values = day_keys.merge(daily, how="left", on=["airport", "local_date"], validate="many_to_one")
    out = pd.DataFrame(index=flights.index)
    out["planned_departures_origin_hour"] = lookup(flights["Origin"], departure_local, "planned_departures").astype(
        "float32"
    )
    out["planned_arrivals_dest_hour"] = lookup(flights["Dest"], arrival_local, "planned_arrivals").astype("float32")
    out["planned_departures_origin_day"] = day_values["planned_departures"].to_numpy(dtype="float32")
    return out


# ----------------------------------------------------------------------------
# C / D. weather
# ----------------------------------------------------------------------------


def check_weather_timing(
    weather: pd.DataFrame,
    flights: pd.DataFrame,
    *,
    oracle: bool,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    margin_minutes: float = DEFAULT_MARGIN_MINUTES,
) -> None:
    """Row-level information-time check (plan 2.6). ``weather`` must be aligned with ``flights`` (same order).

    T table: every non-empty ``*_obs_utc`` <= crs_dep_utc - T - margin, and ``is_oracle`` is False everywhere.
    Oracle table: ``is_oracle`` is True everywhere; origin obs <= crs_dep_utc, dest obs <= crs_arr_utc.
    """
    if "is_oracle" not in weather.columns:
        raise LeakageError("Weather table without the is_oracle column: cannot tell T-table from oracle table")
    flags = weather["is_oracle"].astype("boolean")
    if flags.isna().any():
        raise LeakageError("is_oracle has empty values")
    if oracle and not bool(flags.all()):
        raise LeakageError("oracle=True but the table is not the oracle table (is_oracle is not True everywhere)")
    if not oracle and bool(flags.any()):
        raise LeakageError("Oracle weather rows were given as T-2 h weather; use oracle=True (upper-bound experiment)")
    dep = pd.to_datetime(flights["crs_dep_utc"]).reset_index(drop=True)
    arr = pd.to_datetime(flights["crs_arr_utc"]).reset_index(drop=True)
    if oracle:
        cutoffs = {"origin": dep, "dest": arr}
    else:
        cutoff = dep - pd.Timedelta(hours=horizon_hours) - pd.Timedelta(minutes=margin_minutes)
        cutoffs = {"origin": cutoff, "dest": cutoff}
    problems: list[str] = []
    for side in _SIDES:
        observed = pd.to_datetime(weather[f"{side}_obs_utc"]).reset_index(drop=True)
        present = observed.notna()
        too_late = present & (cutoffs[side].isna() | (observed > cutoffs[side]))
        if bool(too_late.any()):
            problems.append(f"{side}: {int(too_late.sum())} row(s) observed after the information time")
    if problems:
        raise LeakageError("Weather information-time violation: " + "; ".join(problems))


def _ceiling(weather: pd.DataFrame, side: str) -> np.ndarray:
    size = len(weather)
    ceiling = np.full(size, np.inf)
    for layer in range(1, 5):
        cover = weather[f"{side}_skyc{layer}"].astype("string").str.strip().str.upper()
        height = _float(weather[f"{side}_skyl{layer}"])
        is_ceiling = cover.isin(_CEILING_COVERS).fillna(False).to_numpy(dtype=bool) & ~np.isnan(height)
        ceiling = np.where(is_ceiling, np.minimum(ceiling, height), ceiling)
    return np.where(np.isinf(ceiling), CEILING_UNLIMITED_FT, ceiling)


def build_weather_features(
    weather: pd.DataFrame,
    flights: pd.DataFrame,
    *,
    oracle: bool = False,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    margin_minutes: float = DEFAULT_MARGIN_MINUTES,
) -> pd.DataFrame:
    """Group C (T table) or D (oracle table, prefix ``oracle_``) features aligned with ``flights``."""
    check_no_forbidden_inputs(weather, "weather")
    aligned = flights[["flight_uid"]].merge(weather, how="left", on="flight_uid", validate="one_to_one")
    if aligned["is_oracle"].isna().any():
        raise LeakageError("Some flights have no row in the weather table (the layer writes one row per flight)")
    check_weather_timing(aligned, flights, oracle=oracle, horizon_hours=horizon_hours, margin_minutes=margin_minutes)
    prefix = "oracle_" if oracle else ""
    out: dict[str, np.ndarray] = {}
    for side in _SIDES:
        name = f"{prefix}{side}_"
        observed = pd.to_datetime(aligned[f"{side}_obs_utc"]).notna().to_numpy(dtype=bool)
        for variable in WEATHER_NUMERIC:
            out[f"{name}{variable}"] = _float(aligned[f"{side}_{variable}"]).astype("float32")
        out[f"{name}obs_age_min"] = _float(aligned[f"{side}_obs_age_min"]).astype("float32")
        ceiling = np.where(observed, _ceiling(aligned, side), np.nan)
        out[f"{name}ceiling_ft"] = ceiling.astype("float32")
        visibility = out[f"{name}vsby"].astype("float64")
        ifr = (ceiling < IFR_CEILING_FT) | (visibility < IFR_VISIBILITY_MI)
        out[f"{name}ifr_flag"] = np.where(observed, ifr.astype("float64"), np.nan).astype("float32")
        codes = aligned[f"{side}_wxcodes"].astype("string").str.upper()
        for flag, pattern in WX_FLAG_PATTERNS.items():
            hit = codes.str.contains(pattern, regex=False).fillna(False).to_numpy(dtype=bool)
            out[f"{name}{flag}"] = np.where(observed, hit.astype("float64"), np.nan).astype("float32")
        out[f"{name}weather_missing"] = (~observed).astype("int8")
    out[f"{prefix}dest_weather_available"] = pd.to_datetime(aligned["dest_obs_utc"]).notna().to_numpy().astype("int8")
    return pd.DataFrame(out, index=flights.index)


# ----------------------------------------------------------------------------
# B. past statistics
# ----------------------------------------------------------------------------

_ROUTE_HOUR = ((), ("Origin",), ("Origin", "hour_block"), ("Origin", "Dest", "hour_block"))
_DEST_HOUR = ((), ("Dest",), ("Dest", "hour_block"))
_CARRIER_ORIGIN = ((), ("Origin",), ("Origin", "Reporting_Airline"))
_ROUTE = ((), ("Origin",), ("Origin", "Dest"))
_ROUTE_HOUR_ELAPSED = ((), ("Origin", "Dest"), ("Origin", "Dest", "hour_block"))  # back-off: assumption
_ORIGIN_HOUR = ((), ("Origin",), ("Origin", "hour_block"))

HISTORY_FEATURES = (
    "te_route_hour_arrdel15",
    "te_dest_hour_arrdel15",
    "te_carrier_origin_arrdel15",
    "hist_route_hour_p50",
    "hist_route_hour_p80",
    "hist_route_hour_p95",
    "te_route_cancel",
    "schedule_excess_min",
    "hist_taxiout_origin_hour_median",
    "support_n_route_hour_arrdel15",
    "support_n_dest_hour_arrdel15",
    "support_n_carrier_origin_arrdel15",
    "support_n_route_hour_p80",
    "support_n_route_cancel",
    "support_n_route_hour_elapsed",
    "support_n_origin_hour_taxiout",
)
_HISTORY_SOURCES: dict[str, tuple[str, ...]] = {
    "te_route_hour_arrdel15": ("ArrDel15",),
    "te_dest_hour_arrdel15": ("ArrDel15",),
    "te_carrier_origin_arrdel15": ("ArrDel15",),
    "hist_route_hour_p50": ("ArrDelay",),
    "hist_route_hour_p80": ("ArrDelay",),
    "hist_route_hour_p95": ("ArrDelay",),
    "te_route_cancel": ("Cancelled",),
    "schedule_excess_min": ("CRSElapsedTime", "ActualElapsedTime"),
    "hist_taxiout_origin_hour_median": ("TaxiOut",),
    "support_n_route_hour_arrdel15": ("ArrDel15",),
    "support_n_dest_hour_arrdel15": ("ArrDel15",),
    "support_n_carrier_origin_arrdel15": ("ArrDel15",),
    "support_n_route_hour_p80": ("ArrDelay",),
    "support_n_route_cancel": ("Cancelled",),
    "support_n_route_hour_elapsed": ("ActualElapsedTime",),
    "support_n_origin_hour_taxiout": ("TaxiOut",),
}
_HISTORY_KEYS = ("FlightDate", "Origin", "Dest", "Reporting_Airline", "crs_dep_local_min", "CRSElapsedTime")
_HISTORY_LABELS = ("ArrDel15", "ArrDelay", "Cancelled", "Diverted", "ActualElapsedTime", "TaxiOut")


class HistoryFeatures:
    """Plan section 2.3 B statistics, fitted ONLY on a fit window (plan 2.4). ``transform`` reads keys only."""

    def __init__(
        self, *, m: float = DEFAULT_M, min_support: int = DEFAULT_MIN_SUPPORT, min_tail: int = DEFAULT_MIN_TAIL
    ) -> None:
        self.m, self.min_support, self.min_tail = m, min_support, min_tail
        self.fit_end: dt.date | None = None
        self._rates = {
            "route_hour_arrdel15": SmoothedRateTable(_ROUTE_HOUR, m=m, min_support=min_support),
            "dest_hour_arrdel15": SmoothedRateTable(_DEST_HOUR, m=m, min_support=min_support),
            "carrier_origin_arrdel15": SmoothedRateTable(_CARRIER_ORIGIN, m=m, min_support=min_support),
            "route_cancel": SmoothedRateTable(_ROUTE, m=m, min_support=min_support),
        }
        self._quantiles = {
            "route_hour_delay": BackoffQuantileTable(_ROUTE_HOUR, tg.QUANTILE_LEVELS, min_tail=min_tail),
            "route_hour_elapsed": BackoffQuantileTable(_ROUTE_HOUR_ELAPSED, (0.5,), min_tail=min_tail),
            "origin_hour_taxiout": BackoffQuantileTable(_ORIGIN_HOUR, (0.5,), min_tail=min_tail),
        }

    def fit(self, frame: pd.DataFrame, *, fit_end: dt.date) -> Self:
        """``frame``: fit-window rows with the key columns and the label columns (loader output)."""
        missing = [c for c in (*_HISTORY_KEYS, *_HISTORY_LABELS) if c not in frame.columns]
        if missing:
            raise KeyError(f"HistoryFeatures.fit needs columns: {missing}")
        keyed = add_key_columns(frame[list(_HISTORY_KEYS)])
        arr_del15 = tg.target_values(frame, tg.ARR_DEL15)
        completed = tg.completed_mask(frame)
        elapsed = np.where(completed, _float(frame["ActualElapsedTime"]), np.nan)
        not_cancelled = _float(frame["Cancelled"]) == 0
        taxiout = np.where(not_cancelled, _float(frame["TaxiOut"]), np.nan)
        for name in ("route_hour_arrdel15", "dest_hour_arrdel15", "carrier_origin_arrdel15"):
            self._rates[name].fit(keyed, arr_del15, fit_end=fit_end)
        self._rates["route_cancel"].fit(keyed, tg.target_values(frame, tg.CANCELLED), fit_end=fit_end)
        self._quantiles["route_hour_delay"].fit(keyed, tg.target_values(frame, tg.ARR_DELAY), fit_end=fit_end)
        self._quantiles["route_hour_elapsed"].fit(keyed, elapsed, fit_end=fit_end)
        self._quantiles["origin_hour_taxiout"].fit(keyed, taxiout, fit_end=fit_end)
        self.fit_end = fit_end
        return self

    def transform(self, frame: pd.DataFrame, *, require_after_fit_end: bool = True) -> pd.DataFrame:
        """Features for any rows; reads only the key columns. Evaluation rows must lie after ``fit_end``."""
        if self.fit_end is None:
            raise RuntimeError("HistoryFeatures is not fitted")
        keyed = add_key_columns(frame[list(_HISTORY_KEYS)])
        options: dict[str, Any] = {"require_after_fit_end": require_after_fit_end}
        out = pd.DataFrame(index=frame.index)
        for name in ("route_hour_arrdel15", "dest_hour_arrdel15", "carrier_origin_arrdel15"):
            encoded = self._rates[name].transform(keyed, **options)
            out[f"te_{name}"] = encoded["value"].astype("float32")
            out[f"support_n_{name}"] = encoded["support"].astype("float32")
        delay = self._quantiles["route_hour_delay"].transform(keyed, **options)
        for key, label in (("q050", "p50"), ("q080", "p80"), ("q095", "p95")):
            out[f"hist_route_hour_{label}"] = delay[key].astype("float32")
        out["support_n_route_hour_p80"] = delay["support_q080"].astype("float32")
        cancel = self._rates["route_cancel"].transform(keyed, **options)
        out["te_route_cancel"] = cancel["value"].astype("float32")
        out["support_n_route_cancel"] = cancel["support"].astype("float32")
        elapsed = self._quantiles["route_hour_elapsed"].transform(keyed, **options)
        median_elapsed = np.where(elapsed["level_q050"].to_numpy() > 0, elapsed["q050"].to_numpy(), np.nan)  # no global
        scheduled = _float(keyed["CRSElapsedTime"])
        out["schedule_excess_min"] = (scheduled - median_elapsed).astype("float32")
        out["support_n_route_hour_elapsed"] = elapsed["support_q050"].astype("float32")
        taxi = self._quantiles["origin_hour_taxiout"].transform(keyed, **options)
        out["hist_taxiout_origin_hour_median"] = taxi["q050"].astype("float32")
        out["support_n_origin_hour_taxiout"] = taxi["support_q050"].astype("float32")
        return out[list(HISTORY_FEATURES)]

    def fit_transform_out_of_fold(
        self, frame: pd.DataFrame, *, fit_end: dt.date, n_blocks: int = 5, mode: Literal["oof", "expanding"] = "oof"
    ) -> pd.DataFrame:
        """Encoding of the fit-window rows themselves (plan 2.4 item 2); also fits ``self`` on the whole window."""

        def fit_part(fit_rows: pd.DataFrame, apply_rows: pd.DataFrame, part_end: dt.date) -> pd.DataFrame:
            part = HistoryFeatures(m=self.m, min_support=self.min_support, min_tail=self.min_tail)
            return part.fit(fit_rows, fit_end=part_end).transform(apply_rows, require_after_fit_end=False)

        encoded = out_of_fold(frame, fit_part, fit_end=fit_end, n_blocks=n_blocks, mode=mode)
        self.fit(frame, fit_end=fit_end)
        return encoded

    def describe(self) -> dict[str, Any]:
        tables: dict[str, Any] = {n: t.describe() for n, t in self._rates.items()}
        tables.update({n: t.describe() for n, t in self._quantiles.items()})
        return {"fit_end": str(self.fit_end) if self.fit_end else None, "tables": tables}


# ----------------------------------------------------------------------------
# contract + matrix
# ----------------------------------------------------------------------------


def _spec(name: str, *, horizon_hours: float, margin_minutes: float, history_ready_minutes: int) -> FeatureSpec:
    if name in _HISTORY_SOURCES:
        return FeatureSpec(
            name=name,
            source="derived",
            knowledge_time="past_realized",
            source_columns=_HISTORY_SOURCES[name],
            ready_minutes_before=history_ready_minutes,
            description="Statistic of the fit window only (plan 2.4).",
        )
    if name.startswith("oracle_"):
        return FeatureSpec(name=name, source="iem_asos", knowledge_time="oracle", description="Upper-bound only.")
    if name.startswith(("origin_", "dest_")):
        return FeatureSpec(
            name=name,
            source="iem_asos",
            knowledge_time="observation_before_T",
            ready_minutes_before=round(horizon_hours * 60 + margin_minutes),
            description="METAR observed <= crs_dep_utc - T - margin.",
        )
    if name in DENSITY_FEATURES:
        return FeatureSpec(
            name=name, source="derived", knowledge_time="schedule", source_columns=("CRSDepTime", "CRSArrTime")
        )
    if name in SCHEDULE_FEATURES:
        source_columns = {
            "crs_dep_hour": ("CRSDepTime",),
            "crs_dep_minute_of_day": ("CRSDepTime",),
            "crs_arr_hour": ("CRSArrTime",),
            "hour_block": ("CRSDepTime",),
            "days_to_holiday": ("FlightDate",),
            "holiday_week": ("FlightDate",),
            "month": ("FlightDate",),
            "day_of_week": ("FlightDate",),
            "day_of_month": ("FlightDate",),
            "day_of_year": ("FlightDate",),
        }.get(name, (name,))
        if source_columns == (name,):
            return FeatureSpec(name=name, source="bts_ontime", knowledge_time="schedule", source_columns=source_columns)
        return FeatureSpec(name=name, source="derived", knowledge_time="schedule", source_columns=source_columns)
    raise LeakageError(f"Column {name!r} is not a declared feature (plan 2.6: every feature must be in the contract)")


def build_contract(
    kind: str,
    columns: Iterable[str],
    *,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    margin_minutes: float = DEFAULT_MARGIN_MINUTES,
    history_ready_minutes: int = DEFAULT_HISTORY_READY_MINUTES,
) -> FeatureContract:
    """FeatureContract for 'plan' | 'T2' | 'oracle' (plan section 2.2); rejects classes the kind does not allow."""
    if kind not in _ALLOWED_KNOWLEDGE:
        raise ValueError(f"kind must be one of {CONTRACT_KINDS}: {kind!r}")
    specs = [
        _spec(
            c, horizon_hours=horizon_hours, margin_minutes=margin_minutes, history_ready_minutes=history_ready_minutes
        )
        for c in columns
    ]
    not_allowed = [s.name for s in specs if s.knowledge_time not in _ALLOWED_KNOWLEDGE[kind]]
    if not_allowed:
        raise LeakageError(f"Contract {kind!r} does not allow: {not_allowed}")
    return FeatureContract(horizon_hours=horizon_hours, oracle_experiment=(kind == "oracle"), features=specs)


@dataclass(frozen=True)
class FeatureMatrix:
    frame: pd.DataFrame
    contract: FeatureContract
    kind: str


def build_feature_matrix(
    flights: pd.DataFrame,
    *,
    density: pd.DataFrame | None = None,
    weather_t: pd.DataFrame | None = None,
    history: HistoryFeatures | None = None,
    history_frame: pd.DataFrame | None = None,
    weather_oracle: pd.DataFrame | None = None,
    oracle: bool = False,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    margin_minutes: float = DEFAULT_MARGIN_MINUTES,
    history_ready_minutes: int = DEFAULT_HISTORY_READY_MINUTES,
    require_after_fit_end: bool = True,
) -> FeatureMatrix:
    """Assemble X for one block of flights (e.g. one month) and validate it against its contract.

    Contract kind: 'oracle' if ``oracle``; else 'T2' if ``weather_t`` is given; else 'plan'.
    ``weather_oracle`` without ``oracle=True`` raises LeakageError (oracle is off by default).
    ``history_frame``: precomputed history features for these rows (e.g. ``fit_transform_out_of_fold`` output for
    training rows); otherwise ``history.transform(flights)`` is used.
    """
    check_no_forbidden_inputs(flights, "flights")
    missing = [c for c in _FLIGHT_INPUTS if c not in flights.columns]
    if missing:
        raise KeyError(f"flights is missing columns: {missing}")
    if weather_oracle is not None and not oracle:
        raise LeakageError("weather_oracle was given but oracle=False: oracle weather needs the explicit oracle option")
    if oracle and weather_oracle is None:
        raise ValueError("oracle=True needs the weather_oracle table")
    parts = [build_schedule_features(flights)]
    if density is not None:
        parts.append(build_density_features(flights, aggregate_density(density)))
    if weather_t is not None:
        parts.append(
            build_weather_features(
                weather_t, flights, oracle=False, horizon_hours=horizon_hours, margin_minutes=margin_minutes
            )
        )
    if oracle and weather_oracle is not None:
        parts.append(build_weather_features(weather_oracle, flights, oracle=True))
    if history_frame is not None:
        parts.append(history_frame.loc[flights.index, list(HISTORY_FEATURES)])
    elif history is not None:
        parts.append(history.transform(flights, require_after_fit_end=require_after_fit_end))
    frame = pd.concat(parts, axis=1)
    kind = "oracle" if oracle else ("T2" if weather_t is not None else "plan")
    validate_columns(frame.columns)
    contract = build_contract(
        kind,
        list(frame.columns),
        horizon_hours=horizon_hours,
        margin_minutes=margin_minutes,
        history_ready_minutes=history_ready_minutes,
    )
    if contract.feature_names() != list(frame.columns):
        raise LeakageError("Contract and matrix columns differ")
    return FeatureMatrix(frame=frame, contract=contract, kind=kind)
