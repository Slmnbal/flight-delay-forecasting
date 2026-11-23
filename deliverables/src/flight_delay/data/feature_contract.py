"""Pre-departure "T hours" feature contract (Pydantic v2).

Purpose: automatically reject the use of fields that are UNKNOWN at prediction time (T hours before
departure) as features. Source: research/veri-kaynaklari.md section 6.3.

Two layers:
  1) Name level: forbidden list (FORBIDDEN_FIELDS + "Div*" prefix) on raw column names.
  2) Contract level (FeatureContract): every feature DECLARES which raw columns it derives from and
     its "knowledge time"; declarations that break the rules are rejected.

LIMITATION (explicit): the contract validates the declaration, not the computation. That a feature
is really computed from information available T hours earlier depends on the computing code and on
a row-level time test (e.g. latest event time used <= CRS departure - T); that test belongs to the
feature-building stage. A derivative that carries no forbidden name but is built from a forbidden
column (e.g. "DepDelay_lag1") is caught only if ``source_columns`` is declared correctly.

Not verified: BTS column names (e.g. the spelling 'DayofMonth', the definition of 'DepTimeBlk') could
not be checked against the official data dictionary; comparisons are case-insensitive and the
downloaded file's header is listed by size_measurement (missing / extra column report).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "FEATURE_CANDIDATES_RAW",
    "FORBIDDEN_FIELDS",
    "FORBIDDEN_PREFIXES",
    "KEY_AUDIT_RAW",
    "MEASUREMENT_SUBSET",
    "TARGET_RAW",
    "FeatureContract",
    "FeatureSpec",
    "LeakageError",
    "forbidden_reason",
    "schedule_features",
    "validate_columns",
]

# ----------------------------------------------------------------------------
# 1) Name-level forbidden list
# ----------------------------------------------------------------------------

# group -> (fields, rationale)
FORBIDDEN_FIELDS: dict[str, tuple[tuple[str, ...], str]] = {
    "actual_departure": (
        ("DepTime", "DepDelay", "DepDelayMinutes", "DepDel15", "DepartureDelayGroups", "FirstDepTime"),
        "Actual departure information is known after (or at) departure.",
    ),
    "actual_flight": (
        (
            "TaxiOut",
            "WheelsOff",
            "WheelsOn",
            "TaxiIn",
            "ArrTime",
            "ActualElapsedTime",
            "AirTime",
            "TotalAddGTime",
            "LongestAddGTime",
        ),
        "Actual flight/arrival times and durations are unknown at prediction time; they reveal the arrival delay directly.",
    ),
    "target_and_derivatives": (
        ("ArrDelay", "ArrDelayMinutes", "ArrDel15", "ArrivalDelayGroups"),
        "Target variable or a direct derivative of it.",
    ),
    "delay_causes": (
        ("CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"),
        "Delay-cause minutes are reported by the carrier after the delay has happened.",
    ),
    "cancellation_diversion": (
        ("Cancelled", "CancellationCode", "Diverted"),
        "Cancellation/diversion is known after the flight; cancellation may be a separate TARGET, never a feature.",
    ),
    "unverified_precaution": (
        ("DepTimeBlk", "ArrTimeBlk"),
        "The BTS definition was not verified (may be CRS based). Forbidden as a precaution; "
        "derive your own from CRSDepTime/CRSArrTime if needed.",
    ),
}

# Every field starting with 'Div' (Div1Airport, DivArrDelay, DivReachedDest, DivAirportLandings ...) is forbidden.
FORBIDDEN_PREFIXES: tuple[tuple[str, str], ...] = (("div", "Diversion fields are known only after the flight."),)

_NAME_TO_GROUP: dict[str, str] = {
    name.lower(): group for group, (names, _) in FORBIDDEN_FIELDS.items() for name in names
}


class LeakageError(ValueError):
    """A forbidden (leakage) field was used as a feature."""


def forbidden_reason(name: str) -> str | None:
    """Return 'group: rationale' if the field is forbidden, else None. Case-insensitive."""
    key = name.strip().lower()
    if key in _NAME_TO_GROUP:
        group = _NAME_TO_GROUP[key]
        return f"{group}: {FORBIDDEN_FIELDS[group][1]}"
    for prefix, rationale in FORBIDDEN_PREFIXES:
        if key.startswith(prefix):
            return f"prefix '{prefix}*': {rationale}"
    return None


def validate_columns(columns: Iterable[str]) -> None:
    """Check the column names of a feature matrix; raise LeakageError if any is forbidden.

    Usage: ``validate_columns(X.columns)`` right before model training.
    """
    violations = [f"{column} -> {reason}" for column in columns if (reason := forbidden_reason(str(column)))]
    if violations:
        raise LeakageError("Forbidden (leakage) fields cannot be used as features:\n  " + "\n  ".join(violations))


# ----------------------------------------------------------------------------
# Load sets (used by size_measurement and the ETL)
# ----------------------------------------------------------------------------

# Schedule information: known T hours before departure -> feature CANDIDATE (still declared in the contract).
FEATURE_CANDIDATES_RAW = (
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
)
# Target / label (CANNOT be features): loaded for modelling and evaluation.
TARGET_RAW = ("ArrDelay", "ArrDel15", "Cancelled", "Diverted")
# Key / audit only: UTC validation, rotation (previous leg) building. Cannot be features.
KEY_AUDIT_RAW = ("Tail_Number", "DepTime", "ArrTime", "DepDelay", "CancellationCode")

# "Model subset" for the size measurement (size_measurement.py)
MEASUREMENT_SUBSET = FEATURE_CANDIDATES_RAW + TARGET_RAW + KEY_AUDIT_RAW


# ----------------------------------------------------------------------------
# 2) Contract level
# ----------------------------------------------------------------------------

Source = Literal["bts_ontime", "iem_asos", "ourairports", "derived"]
KnowledgeTime = Literal[
    "schedule",  # CRS times, route, distance, calendar: known for certain before departure
    "past_realized",  # an event that already happened and is known before T (e.g. previous leg's arrival)
    "observation_before_T",  # observation at least T hours before departure (e.g. METAR)
    "oracle",  # observed weather at/after departure: ONLY for the oracle (upper bound) experiment
]


class FeatureSpec(BaseModel):
    """Declaration of a single feature."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Feature column name (as it appears in the model matrix).")
    source: Source
    knowledge_time: KnowledgeTime
    source_columns: tuple[str, ...] = Field(
        default=(), description="RAW columns used in the derivation (the forbidden check applies to these too)."
    )
    ready_minutes_before: int | None = Field(
        default=None,
        description="At least how many minutes before this flight's CRS departure the information is ready "
        "(required for past_realized and observation_before_T).",
    )
    description: str = ""


class FeatureContract(BaseModel):
    """The complete feature list and information horizon for a model / experiment."""

    model_config = ConfigDict(extra="forbid")

    horizon_hours: float = Field(gt=0, description="T: how many hours before departure the prediction is made.")
    oracle_experiment: bool = Field(
        default=False, description="If True, 'oracle' weather features are allowed (upper-bound experiment)."
    )
    features: list[FeatureSpec]

    @model_validator(mode="after")
    def _check_rules(self) -> Self:
        horizon_min = round(self.horizon_hours * 60)
        errors: list[str] = []

        names = [f.name.strip().lower() for f in self.features]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            errors.append(f"Duplicate feature name: {duplicates}")

        for feature in self.features:
            # (a) the feature's own name cannot be forbidden
            if reason := forbidden_reason(feature.name):
                errors.append(f"[{feature.name}] name is forbidden -> {reason}")

            # (b) forbidden source columns: only for a 'past_realized' derivative that is ready before T
            forbidden_sources = [(c, r) for c in feature.source_columns if (r := forbidden_reason(c))]
            if forbidden_sources:
                past_ok = (
                    feature.knowledge_time == "past_realized"
                    and feature.source == "derived"
                    and feature.ready_minutes_before is not None
                    and feature.ready_minutes_before >= horizon_min
                )
                if not past_ok:
                    detail = "; ".join(c for c, _ in forbidden_sources)
                    errors.append(
                        f"[{feature.name}] uses forbidden raw column(s): {detail}. Allowed only from an earlier "
                        f"event with source='derived', knowledge_time='past_realized' and "
                        f"ready_minutes_before>={horizon_min}."
                    )

            # (c) knowledge-time rules
            if feature.knowledge_time in ("past_realized", "observation_before_T") and (
                feature.ready_minutes_before is None or feature.ready_minutes_before < horizon_min
            ):
                errors.append(
                    f"[{feature.name}] ready_minutes_before must be >= {horizon_min} min (T={self.horizon_hours} "
                    f"hours); given: {feature.ready_minutes_before}"
                )
            if feature.knowledge_time == "observation_before_T" and feature.source != "iem_asos":
                errors.append(f"[{feature.name}] 'observation_before_T' is defined only for source='iem_asos'.")
            if feature.knowledge_time == "oracle":
                if feature.source != "iem_asos":
                    errors.append(f"[{feature.name}] 'oracle' is valid only for IEM weather observations.")
                if not self.oracle_experiment:
                    errors.append(
                        f"[{feature.name}] an 'oracle' feature cannot be used unless the contract sets "
                        "oracle_experiment=True (observed weather is only a labelled upper-bound experiment)."
                    )
            if feature.knowledge_time == "schedule" and feature.source == "iem_asos":
                errors.append(f"[{feature.name}] a weather observation is not 'schedule' information.")

        if errors:
            raise ValueError("Feature contract violations:\n  " + "\n  ".join(errors))
        return self

    def feature_names(self) -> list[str]:
        return [f.name for f in self.features]


def schedule_features() -> list[FeatureSpec]:
    """Safe starting set: schedule information only (CRS times, route, calendar)."""
    return [
        FeatureSpec(name=name, source="bts_ontime", knowledge_time="schedule", source_columns=(name,))
        for name in FEATURE_CANDIDATES_RAW
        if name != "FlightDate"  # the raw date is not a feature itself; calendar derivatives are built instead
    ]
