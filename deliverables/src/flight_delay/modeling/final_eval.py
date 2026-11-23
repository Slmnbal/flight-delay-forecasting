"""Evaluation core of the one-time final test and of its rehearsal (plan sections 5.1 - 5.4, 6, 7). No I/O.

Pre-registered rules: ``experiments/son-test-on-kayit.md`` (written before any final-test or rehearsal result) and
``decisions/M3-son-test-oncesi-kararlari.md``. Two stages:

1. ``assemble_inputs`` turns predictions on ALL rows (context + evaluation rows) into per-role evaluation arrays:
   - probabilities: **Platt** = primary (decision M3 item 3; frozen calibrator fitted on the static window: Val-B in
     the final test, the fold's calibration window in the rehearsal), isotonic (secondary, same window), monthly
     rolling Platt (secondary: refitted for every evaluation month m on FlightDate in [m - 57, m - 2]); B1 goes through
     the same steps with ITS OWN calibrators (plan 4.2). Ranking metrics (ROC-AUC, PR-AUC) always use the RAW scores.
   - quantiles: row-sorted model P50/P80/P95, pair-sorted 0.10/0.90 (as in ``run_models``); conformal offsets per
     evaluation month for three schemes: ``rolling`` (primary, plan 5.4: window ``splits.conformal_calibration_window``
     of the month itself = [m - 57, m - 2]), ``static`` (one offset from the static window) and ``public`` (secondary
     "kamu senaryosu": the window of month m - 2, i.e. labels published with a ~2 month delay). k > n (or an empty
     window) gives offset +inf, flagged ``insufficient``; it is never capped.
   - event days (plan 7): evaluation days whose observed ArrDel15 rate exceeds the P95 of the fit window's daily rates.
2. ``evaluate`` computes totals, monthly tables, segments (Origin / hour_block / month; no carrier dimension), the
   Origin x day stratified AUC (M5 diagnosis), the calendar-day block bootstrap (``bootstrap``; B replicates, one seed,
   the SAME replicates for every comparison), the Holm family of plan 5.2 and the acceptance criteria K1 - K6. K7
   (leakage) is evidence about the runs, not about predictions: the caller passes it in.

Every number in the output comes from the arrays given; nothing is tuned here.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import LeakageError
from flight_delay.modeling import bootstrap as bs
from flight_delay.modeling import calibration as cal
from flight_delay.modeling import conformal as cf
from flight_delay.modeling import features as ft
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import targets as tg
from flight_delay.modeling.baselines import _classification_segments, _clean_dict
from flight_delay.modeling.splits import conformal_calibration_window

__all__ = [
    "CLASSIFIER_ROLES",
    "HOLM_FAMILY",
    "PRIMARY_PROBABILITY",
    "STATIC_PROBABILITY",
    "PRIMARY_SCHEME",
    "PUBLIC_LAG_MONTHS",
    "QUANTILE_ROLES",
    "ROLE_ARR_DEL15_PLAN",
    "ROLE_ARR_DEL15_T2",
    "ROLE_CANCELLED_PLAN",
    "ROLE_CANCELLED_T2",
    "ROLE_CANCELLED_T2_CALENDAR",
    "ROLE_QUANTILES_PLAN",
    "ROLE_QUANTILES_T2",
    "SCHEMES",
    "WEATHER_PAIRS",
    "Acceptance",
    "ClassifierBlock",
    "ClassifierRole",
    "EvaluationInputs",
    "QuantileBlock",
    "QuantileRole",
    "assemble_inputs",
    "conformal_offsets",
    "describe_inputs",
    "evaluate",
    "event_rate_threshold",
    "pool",
    "rehearsal_checks",
    "stratified_auc",
    "tolerance_proposal",
]

# --- roles (pre-registration section c) ---
ROLE_ARR_DEL15_T2 = "arr_del15/T2"  # primary operational ArrDel15 (K1, K2, K3)
ROLE_ARR_DEL15_PLAN = "arr_del15/plan_matched"  # plan model with the T2 primary's calendar setting (plan 6)
ROLE_QUANTILES_PLAN = "arr_delay/plan"  # primary quantiles: K4, K5, OR source (plan 8)
ROLE_QUANTILES_T2 = "arr_delay/T2_matched"  # T2 quantiles with the plan primary's calendar setting (plan 6)
ROLE_CANCELLED_PLAN = "cancelled/plan"  # K6 (plan contract, calendar features dropped: D2 decision)
ROLE_CANCELLED_T2 = "cancelled/T2"  # operational cancellation model = D2 (secondary)
ROLE_CANCELLED_T2_CALENDAR = "cancelled/T2_calendar"  # D1 (with calendar; secondary sensitivity of the deviation)
CLASSIFIER_ROLES = (
    ROLE_ARR_DEL15_T2,
    ROLE_ARR_DEL15_PLAN,
    ROLE_CANCELLED_PLAN,
    ROLE_CANCELLED_T2,
    ROLE_CANCELLED_T2_CALENDAR,
)
QUANTILE_ROLES = (ROLE_QUANTILES_PLAN, ROLE_QUANTILES_T2)
WEATHER_PAIRS = ((ROLE_ARR_DEL15_T2, ROLE_ARR_DEL15_PLAN), (ROLE_QUANTILES_T2, ROLE_QUANTILES_PLAN))  # (T2, plan)

# --- primary family of plan 5.2 (Holm, alpha 0.05): (id, role, comparison key vs B1) ---
HOLM_FAMILY: tuple[tuple[str, str, str], ...] = (
    ("1_arr_del15_roc_auc", ROLE_ARR_DEL15_T2, "d_roc_auc"),
    ("2_arr_del15_pr_auc", ROLE_ARR_DEL15_T2, "d_pr_auc"),
    ("3_arr_del15_bss", ROLE_ARR_DEL15_T2, "bss_platt"),
    ("4_pinball_q050", ROLE_QUANTILES_PLAN, "d_pinball_q050"),
    ("5_pinball_q080", ROLE_QUANTILES_PLAN, "d_pinball_q080"),
    ("6_pinball_q095", ROLE_QUANTILES_PLAN, "d_pinball_q095"),
    ("7_cancelled_pr_auc", ROLE_CANCELLED_PLAN, "d_pr_auc"),
)

SCHEMES = ("rolling", "static", "public")
PRIMARY_SCHEME = "rolling"  # plan 5.4
PUBLIC_LAG_MONTHS = 2  # BTS publication delay (assumption, plan 5.4)
STATIC_PROBABILITY = "platt"  # fitted once on Val-B, stored in calibrators.json; secondary in the report
PRIMARY_PROBABILITY = "platt_rolling"  # decision M3 item 3, revised after the rehearsal (2026-11-22)
PROBABILITY_METHODS = ("platt", "isotonic", "platt_rolling")
ONE_SIDED = (0.80, 0.95)
CORE_LEVELS = tg.QUANTILE_LEVELS
INTERVAL = tg.INTERVAL_LEVELS
INTERVAL_KEY = mt.interval_key(*INTERVAL)
EVENT_DAY_QUANTILE = 0.95  # plan 7: "P95 of the training days"

OffsetTable = dict[str, dict[str, dict[str, dict[str, Any]]]]  # scheme -> level key -> 'YYYY-MM' -> record


@dataclass(frozen=True)
class Acceptance:
    """K3 / K5 tolerances (plan 5.3 proposals by default; final values come from the rehearsal rule)."""

    k3_citl_abs_max: float = 0.01
    k3_slope_min: float = 0.90
    k3_slope_max: float = 1.10
    k5_q080: tuple[float, float] = (0.78, 0.82)
    k5_q095: tuple[float, float] = (0.94, 0.96)
    k5_segment_tolerance: float = 0.05
    k5_segment_share_min: float = 0.80
    k5_segment_min_n: int = 500
    source: str = "plan 5.3 proposal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "K3": {
                "citl_abs_max": self.k3_citl_abs_max,
                "slope_min": self.k3_slope_min,
                "slope_max": self.k3_slope_max,
            },
            "K5": {
                "q080": list(self.k5_q080),
                "q095": list(self.k5_q095),
                "segment_tolerance": self.k5_segment_tolerance,
                "segment_share_min": self.k5_segment_share_min,
                "segment_min_n": self.k5_segment_min_n,
            },
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Acceptance:
        k3, k5 = data["K3"], data["K5"]
        return cls(
            k3_citl_abs_max=float(k3["citl_abs_max"]),
            k3_slope_min=float(k3["slope_min"]),
            k3_slope_max=float(k3["slope_max"]),
            k5_q080=(float(k5["q080"][0]), float(k5["q080"][1])),
            k5_q095=(float(k5["q095"][0]), float(k5["q095"][1])),
            k5_segment_tolerance=float(k5["segment_tolerance"]),
            k5_segment_share_min=float(k5["segment_share_min"]),
            k5_segment_min_n=int(k5["segment_min_n"]),
            source=str(data.get("source", "manifest")),
        )

    def same_values(self, other: Acceptance) -> bool:
        mine, theirs = self.to_dict(), other.to_dict()
        mine.pop("source")
        theirs.pop("source")
        return _close(mine, theirs)


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, int | float) and isinstance(b, int | float):
        return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-12)
    return bool(a == b)


# ----------------------------------------------------------------------------
# inputs
# ----------------------------------------------------------------------------


@dataclass
class ClassifierRole:
    """Raw probabilities on ALL rows + frozen calibrators ({'platt', 'isotonic'}) for the model and for B1."""

    role: str
    target: str
    p: np.ndarray
    calibrators: Mapping[str, cal.Calibrator]
    b1_calibrators: Mapping[str, cal.Calibrator]
    threshold: float | None = None
    b1_threshold: float | None = None


@dataclass
class QuantileRole:
    """Raw model quantiles on ALL rows: {0.10, 0.50, 0.80, 0.90, 0.95: array}."""

    role: str
    q: Mapping[float, np.ndarray]
    target: str = tg.ARR_DELAY


@dataclass
class ClassifierBlock:
    role: str
    target: str
    date: np.ndarray  # datetime64[D] of the evaluation rows of the universe
    month: np.ndarray  # 'YYYY-MM'
    origin: np.ndarray
    hour_block: np.ndarray
    y: np.ndarray
    raw: np.ndarray
    b1_raw: np.ndarray
    calibrated: dict[str, np.ndarray]  # method -> probabilities (NaN where a rolling fit failed)
    b1_calibrated: dict[str, np.ndarray]
    threshold: np.ndarray  # frozen F1 threshold per row (NaN = none)
    b1_threshold: np.ndarray
    event_day: np.ndarray
    notes: list[str] = field(default_factory=list)


@dataclass
class QuantileBlock:
    role: str
    date: np.ndarray
    month: np.ndarray
    origin: np.ndarray
    hour_block: np.ndarray
    y: np.ndarray
    raw: dict[float, np.ndarray]  # model: sorted P50/P80/P95 + pair-sorted 0.10/0.90
    b1_raw: dict[float, np.ndarray]
    offsets: OffsetTable
    b1_offsets: OffsetTable


@dataclass
class EvaluationInputs:
    label: str
    mode: str  # 'final_test' | 'rehearsal'
    classifiers: dict[str, ClassifierBlock]
    quantiles: dict[str, QuantileBlock]
    notes: list[str] = field(default_factory=list)


def _days(dates: Any) -> np.ndarray:
    values = pd.to_datetime(pd.Series(np.asarray(dates).ravel()), errors="coerce")
    if bool(values.isna().any()):
        raise ValueError("Missing FlightDate in the evaluation frame")
    return np.asarray(values.dt.normalize().to_numpy(dtype="datetime64[D]"))


def _within(days: np.ndarray, start: dt.date, end: dt.date) -> np.ndarray:
    return np.asarray((days >= np.datetime64(start, "D")) & (days <= np.datetime64(end, "D")), dtype=bool)


def _month_labels(days: np.ndarray) -> np.ndarray:
    return np.asarray(days.astype("datetime64[M]").astype(str))


def _shift_month(month_start: dt.date, delta: int) -> dt.date:
    index = month_start.year * 12 + (month_start.month - 1) + delta
    return dt.date(index // 12, index % 12 + 1, 1)


def _eval_months(days: np.ndarray) -> list[dt.date]:
    return [pd.Timestamp(m).date() for m in np.unique(days.astype("datetime64[M]"))]


def _window(scheme: str, month_start: dt.date) -> tuple[dt.date, dt.date]:
    anchor = month_start if scheme == "rolling" else _shift_month(month_start, -PUBLIC_LAG_MONTHS)
    window = conformal_calibration_window(anchor)
    if window.end >= month_start:  # cannot happen with the split definition; guards later edits
        raise LeakageError(f"{scheme} window {window} reaches into the month {month_start}")
    return window.start, window.end


def _offset_record(scores: np.ndarray, level: float) -> dict[str, Any]:
    n = int(scores.size)
    if n == 0:
        return {"n": 0, "rank": None, "offset": float("inf"), "insufficient": True}
    rank = cf.conformal_rank(n, level)
    return {"n": n, "rank": rank, "offset": cf.conformal_quantile(scores, level), "insufficient": bool(rank > n)}


def conformal_offsets(
    scores: np.ndarray, dates: Any, static_mask: np.ndarray, eval_months: Sequence[dt.date], level: float
) -> dict[str, dict[str, dict[str, Any]]]:
    """{scheme: {'YYYY-MM': record}} for one conformity score vector (rows = the target universe, all periods)."""
    days = _days(dates)
    values = np.asarray(scores, dtype="float64")
    static = np.asarray(static_mask, dtype=bool)
    if values.shape != days.shape or static.shape != days.shape:
        raise ValueError("scores, dates and static_mask differ in length")
    static_record = _offset_record(values[static], level)
    if static.any():
        static_record |= {"window_start": str(days[static].min()), "window_end": str(days[static].max())}
    out: dict[str, dict[str, dict[str, Any]]] = {scheme: {} for scheme in SCHEMES}
    for month in eval_months:
        label = f"{month:%Y-%m}"
        if static.any() and days[static].max() >= np.datetime64(month, "D"):
            raise LeakageError(f"The static calibration window reaches into the evaluation month {label}")
        for scheme in ("rolling", "public"):
            start, end = _window(scheme, month)
            record = _offset_record(values[_within(days, start, end)], level)
            out[scheme][label] = record | {"window_start": str(start), "window_end": str(end)}
        out["static"][label] = dict(static_record)
    return out


def _quantile_offsets(
    y: np.ndarray,
    levels: Mapping[float, np.ndarray],
    days: np.ndarray,
    static: np.ndarray,
    months: Sequence[dt.date],
) -> OffsetTable:
    """One-sided offsets for P80 / P95 and the CQR offset for the 80 % interval, per scheme (universe rows only)."""
    by_level: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for alpha in ONE_SIDED:
        scores = cf.one_sided_scores(y, levels[alpha])
        by_level[mt.quantile_key(alpha)] = conformal_offsets(scores, days, static, months, alpha)
    scores = cf.cqr_scores(y, levels[INTERVAL[0]], levels[INTERVAL[1]])
    coverage_level = round(INTERVAL[1] - INTERVAL[0], 10)
    by_level[INTERVAL_KEY] = conformal_offsets(scores, days, static, months, coverage_level)
    return {scheme: {key: table[scheme] for key, table in by_level.items()} for scheme in SCHEMES}


def event_rate_threshold(fit_dates: Any, fit_arr_del15: Any) -> float | None:
    """P95 of the fit window's daily ArrDel15 rates (completed flights; plan 7 'olay günleri')."""
    frame = pd.DataFrame({"day": _days(fit_dates), "y": np.asarray(fit_arr_del15, dtype="float64")})
    daily = frame.dropna().groupby("day")["y"].mean()
    return float(np.quantile(daily.to_numpy(), EVENT_DAY_QUANTILE)) if len(daily) else None


def _rolling_platt(
    y: np.ndarray, p: np.ndarray, days: np.ndarray, eval_rows: np.ndarray, months: Sequence[dt.date]
) -> tuple[np.ndarray, list[str]]:
    """Platt refitted per evaluation month on [m - 57, m - 2] (universe rows); NaN + note where the fit fails."""
    out = np.full(int(eval_rows.sum()), np.nan)
    eval_p = p[eval_rows]
    eval_months = days[eval_rows].astype("datetime64[M]")
    notes: list[str] = []
    for month in months:
        start, end = _window("rolling", month)
        window = _within(days, start, end)
        in_month = eval_months == np.datetime64(month, "M")
        try:
            calibrator = cal.fit_platt(y[window], p[window])
        except ValueError as error:
            notes.append(f"rolling Platt {month:%Y-%m}: {error}")
            continue
        out[in_month] = calibrator.predict(eval_p[in_month])
    return out, notes


def _constant(value: float | None, size: int) -> np.ndarray:
    return np.full(size, np.nan if value is None else float(value))


def assemble_inputs(
    *,
    label: str,
    mode: str,
    dates: Any,
    origin: Any,
    local_minutes: Any,
    targets: Mapping[str, np.ndarray],
    eval_mask: Any,
    static_mask: Any,
    classifiers: Mapping[str, ClassifierRole],
    quantiles: Mapping[str, QuantileRole],
    b1_rates: Mapping[str, np.ndarray],
    b1_quantiles: Mapping[float, np.ndarray],
    event_threshold: float | None,
) -> EvaluationInputs:
    """Stage 1 (module docstring). All arrays are over the SAME rows (context + evaluation), in the same order."""
    days = _days(dates)
    n = days.size
    evaluation = np.asarray(eval_mask, dtype=bool)
    static = np.asarray(static_mask, dtype=bool)
    if evaluation.shape != (n,) or static.shape != (n,):
        raise ValueError("eval_mask / static_mask must be boolean masks over the rows")
    if not evaluation.any():
        raise ValueError("No evaluation rows")
    if np.any(evaluation & static):
        raise LeakageError("Static calibration rows and evaluation rows overlap")
    if static.any() and days[static].max() >= days[evaluation].min():
        raise LeakageError("The static calibration window must end before the evaluation starts")
    months = _eval_months(days[evaluation])
    first_needed = min(_window(s, m)[0] for s in ("rolling", "public") for m in months)
    if days.min() > np.datetime64(first_needed, "D"):
        raise ValueError(f"Context rows start {days.min()}, the conformal windows need {first_needed}")
    origin_all = np.asarray(origin).astype(str)
    hours_all = ft.hour_block(local_minutes)
    month_all = _month_labels(days)

    event_all = np.zeros(n, dtype=bool)
    if event_threshold is not None and tg.ARR_DEL15 in targets:
        y15 = np.asarray(targets[tg.ARR_DEL15], dtype="float64")
        frame = pd.DataFrame({"day": days[evaluation], "y": y15[evaluation]}).dropna()
        rates = frame.groupby("day")["y"].mean()
        event_days = rates.index[rates.to_numpy() > event_threshold].to_numpy(dtype="datetime64[D]")
        event_all = evaluation & np.isin(days, event_days)

    blocks: dict[str, ClassifierBlock] = {}
    for role, spec in classifiers.items():
        y_all = np.asarray(targets[spec.target], dtype="float64")
        universe = np.isfinite(y_all)
        rows = universe & evaluation
        p = np.asarray(spec.p, dtype="float64")
        b1 = np.asarray(b1_rates[spec.target], dtype="float64")
        if p.shape != (n,) or b1.shape != (n,):
            raise ValueError(f"{role}: predictions must cover every row")
        if not (np.all(np.isfinite(p[universe])) and np.all(np.isfinite(b1[universe]))):
            raise ValueError(f"{role}: non-finite predictions inside the universe")
        calibrated = {m: c.predict(p[rows]) for m, c in spec.calibrators.items() if m in ("platt", "isotonic")}
        b1_calibrated = {m: c.predict(b1[rows]) for m, c in spec.b1_calibrators.items() if m in ("platt", "isotonic")}
        u_days, u_y, u_eval = days[universe], y_all[universe], evaluation[universe]
        calibrated["platt_rolling"], notes = _rolling_platt(u_y, p[universe], u_days, u_eval, months)
        b1_calibrated["platt_rolling"], b1_notes = _rolling_platt(u_y, b1[universe], u_days, u_eval, months)
        if PRIMARY_PROBABILITY not in calibrated or PRIMARY_PROBABILITY not in b1_calibrated:
            raise ValueError(f"{role}: the primary calibrator ({PRIMARY_PROBABILITY}) is missing")
        size = int(rows.sum())
        blocks[role] = ClassifierBlock(
            role=role,
            target=spec.target,
            date=days[rows],
            month=month_all[rows],
            origin=origin_all[rows],
            hour_block=hours_all[rows],
            y=y_all[rows],
            raw=p[rows],
            b1_raw=b1[rows],
            calibrated=calibrated,
            b1_calibrated=b1_calibrated,
            threshold=_constant(spec.threshold, size),
            b1_threshold=_constant(spec.b1_threshold, size),
            event_day=event_all[rows],
            notes=[*notes, *(f"B1: {x}" for x in b1_notes)],
        )

    quantile_blocks: dict[str, QuantileBlock] = {}
    for role, qspec in quantiles.items():
        y_all = np.asarray(targets[qspec.target], dtype="float64")
        universe = np.isfinite(y_all)
        missing = [a for a in (*CORE_LEVELS, *INTERVAL) if a not in qspec.q]
        if missing:
            raise ValueError(f"{role}: quantile levels missing {missing}")
        core = np.sort(np.column_stack([np.asarray(qspec.q[a], dtype="float64") for a in CORE_LEVELS]), axis=1)
        model = {a: core[:, i] for i, a in enumerate(CORE_LEVELS)}
        lo_raw, hi_raw = (np.asarray(qspec.q[a], dtype="float64") for a in INTERVAL)
        model[INTERVAL[0]], model[INTERVAL[1]] = np.minimum(lo_raw, hi_raw), np.maximum(lo_raw, hi_raw)
        reference = {a: np.asarray(b1_quantiles[a], dtype="float64") for a in (*CORE_LEVELS, *INTERVAL)}
        for name, levels in (("model", model), ("B1", reference)):
            if any(v.shape != (n,) or not np.all(np.isfinite(v[universe])) for v in levels.values()):
                raise ValueError(f"{role} ({name}): quantiles must be finite on every row of the universe")
        u_days, u_y, u_static = days[universe], y_all[universe], static[universe]
        rows = universe & evaluation
        quantile_blocks[role] = QuantileBlock(
            role=role,
            date=days[rows],
            month=month_all[rows],
            origin=origin_all[rows],
            hour_block=hours_all[rows],
            y=y_all[rows],
            raw={a: v[rows] for a, v in model.items()},
            b1_raw={a: v[rows] for a, v in reference.items()},
            offsets=_quantile_offsets(u_y, {a: v[universe] for a, v in model.items()}, u_days, u_static, months),
            b1_offsets=_quantile_offsets(u_y, {a: v[universe] for a, v in reference.items()}, u_days, u_static, months),
        )
    return EvaluationInputs(label=label, mode=mode, classifiers=blocks, quantiles=quantile_blocks)


def _merge_offsets(parts: Sequence[OffsetTable]) -> OffsetTable:
    merged: OffsetTable = {}
    for part in parts:
        for scheme, levels in part.items():
            for key, months in levels.items():
                target = merged.setdefault(scheme, {}).setdefault(key, {})
                overlap = set(target) & set(months)
                if overlap:
                    raise ValueError(f"Blocks overlap in months {sorted(overlap)}")
                target.update(months)
    return merged


def _concat(blocks: Sequence[Any], name: str) -> np.ndarray:
    return np.concatenate([getattr(b, name) for b in blocks])


def pool(parts: Sequence[EvaluationInputs], label: str) -> EvaluationInputs:
    """Concatenate evaluation blocks with disjoint months (rehearsal K3 + K4); every row keeps its own fold's
    predictions, calibrators, thresholds and offsets."""
    if not parts:
        raise ValueError("Nothing to pool")
    roles_c = set.intersection(*(set(p.classifiers) for p in parts))
    roles_q = set.intersection(*(set(p.quantiles) for p in parts))
    classifiers: dict[str, ClassifierBlock] = {}
    for role in sorted(roles_c):
        blocks = [p.classifiers[role] for p in parts]
        methods = set.intersection(*(set(b.calibrated) for b in blocks))
        b1_methods = set.intersection(*(set(b.b1_calibrated) for b in blocks))
        classifiers[role] = ClassifierBlock(
            role=role,
            target=blocks[0].target,
            date=_concat(blocks, "date"),
            month=_concat(blocks, "month"),
            origin=_concat(blocks, "origin"),
            hour_block=_concat(blocks, "hour_block"),
            y=_concat(blocks, "y"),
            raw=_concat(blocks, "raw"),
            b1_raw=_concat(blocks, "b1_raw"),
            calibrated={m: np.concatenate([b.calibrated[m] for b in blocks]) for m in sorted(methods)},
            b1_calibrated={m: np.concatenate([b.b1_calibrated[m] for b in blocks]) for m in sorted(b1_methods)},
            threshold=_concat(blocks, "threshold"),
            b1_threshold=_concat(blocks, "b1_threshold"),
            event_day=_concat(blocks, "event_day"),
            notes=[n for b in blocks for n in b.notes],
        )
    quantile_blocks: dict[str, QuantileBlock] = {}
    for role in sorted(roles_q):
        qblocks = [p.quantiles[role] for p in parts]
        quantile_blocks[role] = QuantileBlock(
            role=role,
            date=_concat(qblocks, "date"),
            month=_concat(qblocks, "month"),
            origin=_concat(qblocks, "origin"),
            hour_block=_concat(qblocks, "hour_block"),
            y=_concat(qblocks, "y"),
            raw={a: np.concatenate([b.raw[a] for b in qblocks]) for a in qblocks[0].raw},
            b1_raw={a: np.concatenate([b.b1_raw[a] for b in qblocks]) for a in qblocks[0].b1_raw},
            offsets=_merge_offsets([b.offsets for b in qblocks]),
            b1_offsets=_merge_offsets([b.b1_offsets for b in qblocks]),
        )
    return EvaluationInputs(
        label=label,
        mode=parts[0].mode,
        classifiers=classifiers,
        quantiles=quantile_blocks,
        notes=[f"pooled from: {', '.join(p.label for p in parts)}"],
    )


def describe_inputs(inputs: EvaluationInputs) -> dict[str, Any]:
    """Row counts per role (for the outputs)."""
    return {
        "classifiers": {r: {"target": b.target, "n": int(b.y.size)} for r, b in inputs.classifiers.items()},
        "quantiles": {r: {"n": int(b.y.size)} for r, b in inputs.quantiles.items()},
    }


# ----------------------------------------------------------------------------
# metric helpers
# ----------------------------------------------------------------------------


def stratified_auc(y: Any, score: Any, strata: Any) -> dict[str, Any]:
    """ROC-AUC over (positive, negative) pairs of the SAME stratum (Origin x day, M5): sum_s U_s / sum_s P_s N_s.

    Average ranks for ties inside a stratum (Mann-Whitney); strata with one class only contribute no pair.
    """
    labels, scores = mt._binary(y, score)
    keys = np.asarray(strata).ravel()
    if keys.shape != labels.shape:
        raise ValueError("strata and y differ in length")
    codes = np.asarray(pd.factorize(pd.Series(keys))[0], dtype="int64")
    order = np.lexsort((scores, codes))
    s_codes, s_scores, s_y = codes[order], scores[order], labels[order]
    new_stratum = np.r_[True, s_codes[1:] != s_codes[:-1]]
    new_group = new_stratum | np.r_[True, s_scores[1:] != s_scores[:-1]]
    stratum_id = np.cumsum(new_stratum) - 1
    group_id = np.cumsum(new_group) - 1
    position = np.arange(labels.size)
    within = position - position[new_stratum][stratum_id]  # 0-based position inside the stratum
    group_first = within[new_group]
    group_count = np.bincount(group_id)
    rank = group_first[group_id] + (group_count[group_id] - 1) / 2.0 + 1.0
    rank_sum = np.bincount(stratum_id, weights=rank * s_y)
    n_pos = np.bincount(stratum_id, weights=s_y)
    n_all = np.bincount(stratum_id).astype("float64")
    n_neg = n_all - n_pos
    usable = (n_pos > 0) & (n_neg > 0)
    pairs = float(np.sum(n_pos[usable] * n_neg[usable]))
    u = rank_sum[usable] - n_pos[usable] * (n_pos[usable] + 1) / 2.0
    return {
        "auc": float(u.sum() / pairs) if pairs > 0 else None,
        "strata": int(n_all.size),
        "strata_with_both_classes": int(usable.sum()),
        "pairs": pairs,
        "rows_in_usable_strata": int(n_all[usable].sum()),
    }


def _strata(origin: np.ndarray, date: np.ndarray) -> np.ndarray:
    origin_codes = np.asarray(pd.factorize(pd.Series(origin))[0], dtype="int64")
    _, day_codes = np.unique(date, return_inverse=True)
    day_codes = np.asarray(day_codes, dtype="int64").ravel()
    return origin_codes * (int(day_codes.max()) + 1 if day_codes.size else 1) + day_codes


def _f1(y: np.ndarray, p: np.ndarray, threshold: np.ndarray) -> dict[str, Any]:
    usable = np.isfinite(threshold)
    if not usable.all():
        return {"precision": None, "recall": None, "f1": None, "rows_without_threshold": int((~usable).sum())}
    predicted = p >= threshold
    tp = float(np.sum(predicted & (y == 1)))
    fp = float(np.sum(predicted & (y == 0)))
    fn = float(np.sum(~predicted & (y == 1)))
    return {
        "precision": tp / (tp + fp) if tp + fp > 0 else None,
        "recall": tp / (tp + fn) if tp + fn > 0 else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn > 0 else None,
        "threshold_min": float(threshold.min()),
        "threshold_max": float(threshold.max()),
    }


def _calibration_block(y: np.ndarray, p: np.ndarray, reference: np.ndarray) -> dict[str, Any]:
    """Probability-quality metrics (no ranking metrics: those come from the raw scores, decision M3 item 3)."""
    finite = np.isfinite(p) & np.isfinite(reference)
    if not np.any(finite):
        return {"n": 0}
    full = mt.classification_metrics(y[finite], p[finite], y_prob_reference=reference[finite])
    out: dict[str, Any] = {k: v for k, v in full.items() if k not in ("roc_auc", "pr_auc")}
    out["rows_left_out"] = int((~finite).sum())
    return _clean_dict(out)


def _pinball_rows(y: np.ndarray, q: np.ndarray, alpha: float) -> np.ndarray:
    diff = y - q
    return np.asarray(np.maximum(alpha * diff, (alpha - 1.0) * diff), dtype="float64")


def _offset_vector(month: np.ndarray, records: Mapping[str, Mapping[str, Any]]) -> np.ndarray:
    labels, inverse = np.unique(month, return_inverse=True)
    missing = [str(m) for m in labels if str(m) not in records]
    if missing:
        raise ValueError(f"No conformal offset for months {missing}")
    values = np.asarray([float(records[str(m)]["offset"]) for m in labels], dtype="float64")
    return np.asarray(values[np.asarray(inverse).ravel()], dtype="float64")


def _result(estimate: float, draws: np.ndarray, level: float) -> dict[str, Any]:
    return _clean_dict(bs.summarize_draws(estimate, draws, level=level).to_dict())


# ----------------------------------------------------------------------------
# stage 2
# ----------------------------------------------------------------------------


def _event_summary(block: ClassifierBlock) -> dict[str, Any]:
    events: dict[str, Any] = {}
    platt, b1_platt = block.calibrated[PRIMARY_PROBABILITY], block.b1_calibrated[PRIMARY_PROBABILITY]
    for name, mask in (("event_days", block.event_day), ("other_days", ~block.event_day)):
        if not mask.any():
            events[name] = {"n": 0}
            continue
        ys = block.y[mask]
        both = 0 < ys.sum() < ys.size
        events[name] = _clean_dict(
            {
                "n": int(mask.sum()),
                "days": int(np.unique(block.date[mask]).size),
                "prevalence": float(ys.mean()),
                "mean_pred_platt": float(platt[mask].mean()),
                "brier_platt": mt.brier_score(ys, platt[mask]),
                "brier_platt_B1": mt.brier_score(ys, b1_platt[mask]),
                "roc_auc_raw": mt.roc_auc(ys, block.raw[mask]) if both else None,
                "roc_auc_raw_B1": mt.roc_auc(ys, block.b1_raw[mask]) if both else None,
            }
        )
    return events


def _classifier_totals(block: ClassifierBlock, min_n: int) -> dict[str, Any]:
    y = block.y
    raw = mt.classification_metrics(y, block.raw, y_prob_reference=block.b1_raw)
    raw_b1 = mt.classification_metrics(y, block.b1_raw, y_prob_reference=block.b1_raw)
    section: dict[str, Any] = {
        "n": int(y.size),
        "prevalence": float(y.mean()),
        "raw": {"model": _clean_dict(raw), "B1": _clean_dict(raw_b1)},
        "f1_at_frozen_threshold": {
            "model": _clean_dict(_f1(y, block.raw, block.threshold)),
            "B1": _clean_dict(_f1(y, block.b1_raw, block.b1_threshold)),
            "note": "raw scores; threshold chosen on the static window (Val-B / fold calibration window)",
        },
        "probability": {},
        "notes": list(block.notes),
    }
    for method in PROBABILITY_METHODS:
        if method in block.calibrated and method in block.b1_calibrated:
            section["probability"][method] = {
                "model": _calibration_block(y, block.calibrated[method], block.b1_calibrated[method]),
                "B1": _calibration_block(y, block.b1_calibrated[method], block.b1_calibrated[method]),
            }
    strata = _strata(block.origin, block.date)
    model_strat, b1_strat = stratified_auc(y, block.raw, strata), stratified_auc(y, block.b1_raw, strata)
    both_defined = model_strat["auc"] is not None and b1_strat["auc"] is not None
    section["stratified_auc_origin_day"] = {
        "model": model_strat,
        "B1": b1_strat,
        "delta": model_strat["auc"] - b1_strat["auc"] if both_defined else None,
        "label": "keşifsel (M5): yalnızca aynı Origin ve gün içindeki çiftler",
    }
    monthly = []
    for month in sorted(set(block.month.tolist())):
        rows = block.month == month
        ys = block.y[rows]
        entry: dict[str, Any] = {"month": month, "n": int(rows.sum()), "prevalence": float(ys.mean())}
        both = 0 < ys.sum() < ys.size
        entry["roc_auc_raw"] = mt.roc_auc(ys, block.raw[rows]) if both else None
        entry["roc_auc_raw_B1"] = mt.roc_auc(ys, block.b1_raw[rows]) if both else None
        entry["citl_raw"] = float(block.raw[rows].mean() - ys.mean())
        for method, values in block.calibrated.items():
            finite = rows & np.isfinite(values)
            if finite.any():
                entry[f"citl_{method}"] = float(values[finite].mean() - block.y[finite].mean())
                entry[f"brier_{method}"] = mt.brier_score(block.y[finite], values[finite])
        monthly.append(_clean_dict(entry))
    section["monthly"] = monthly
    keys = pd.DataFrame({"Origin": block.origin, "hour_block": block.hour_block, "month": block.month})
    section["segments_platt"] = _classification_segments(
        keys, y, block.calibrated[PRIMARY_PROBABILITY], block.b1_calibrated[PRIMARY_PROBABILITY], min_n
    )
    section["event_days"] = _event_summary(block)
    return section


def _segment_shares(
    origin: np.ndarray, month: np.ndarray, covered: np.ndarray, target: float, acceptance: Acceptance
) -> tuple[int, float | None]:
    frame = pd.DataFrame({"o": origin, "m": month, "c": covered.astype("float64")})
    grouped = frame.groupby(["o", "m"], sort=True)["c"].agg(["size", "mean"])
    eligible = grouped.loc[grouped["size"] >= acceptance.k5_segment_min_n]
    if eligible.empty:
        return 0, None
    within = (eligible["mean"] - target).abs() <= acceptance.k5_segment_tolerance
    return int(len(eligible)), float(within.mean())


def _coverage_section(
    block: QuantileBlock, levels: Mapping[float, np.ndarray], offsets: OffsetTable, acceptance: Acceptance
) -> dict[str, Any]:
    y = block.y
    months = sorted(set(block.month.tolist()))
    out: dict[str, Any] = {}
    for scheme in SCHEMES:
        entry: dict[str, Any] = {}
        adjusted: dict[float, np.ndarray] = {}
        for alpha in ONE_SIDED:
            key = mt.quantile_key(alpha)
            bound = levels[alpha] + _offset_vector(block.month, offsets[scheme][key])
            adjusted[alpha] = bound
            covered = y <= bound
            n_segments, share = _segment_shares(block.origin, block.month, covered, alpha, acceptance)
            entry[key] = {
                "coverage": float(covered.mean()),
                "pinball_after": mt.pinball_loss(y, bound, alpha) if np.all(np.isfinite(bound)) else None,
                "months_insufficient": sorted(m for m, r in offsets[scheme][key].items() if r["insufficient"]),
                "segments_origin_month": n_segments,
                "segment_share_within_tolerance": share,
                "monthly_coverage": {m: float(covered[block.month == m].mean()) for m in months},
            }
        entry["adjusted_crossing_rate_q080_q095"] = cf.adjusted_crossing_rate(adjusted[0.80], adjusted[0.95])
        off = _offset_vector(block.month, offsets[scheme][INTERVAL_KEY])
        lo, hi = levels[INTERVAL[0]] - off, levels[INTERVAL[1]] + off
        finite = bool(np.all(np.isfinite(off)))
        entry[INTERVAL_KEY] = {
            "method": "CQR (numpy)",
            "coverage": float(np.mean((y >= lo) & (y <= hi))),
            "mean_width_min": mt.mean_interval_width(lo, hi) if finite else None,
            "months_insufficient": sorted(m for m, r in offsets[scheme][INTERVAL_KEY].items() if r["insufficient"]),
        }
        out[scheme] = entry
    out["offsets"] = {
        scheme: {
            key: {
                month: {
                    **record,
                    "offset": record["offset"] if math.isfinite(record["offset"]) else None,
                    "offset_is_inf": not math.isfinite(record["offset"]),
                }
                for month, record in by_month.items()
            }
            for key, by_month in table.items()
        }
        for scheme, table in offsets.items()
    }
    return out


def _quantile_segments(block: QuantileBlock, min_n: int) -> dict[str, list[dict[str, Any]]]:
    y = block.y
    segments: dict[str, list[dict[str, Any]]] = {}
    for dimension, values in (("Origin", block.origin), ("hour_block", block.hour_block), ("month", block.month)):
        rows_out = []
        text = np.asarray(values).astype(str)
        for value in sorted(set(text.tolist())):
            mask = text == value
            row: dict[str, Any] = {"segment": value, "n": int(mask.sum())}
            if mask.sum() >= min_n:
                for alpha in CORE_LEVELS:
                    key = mt.quantile_key(alpha)
                    row[f"pinball_{key}"] = mt.pinball_loss(y[mask], block.raw[alpha][mask], alpha)
                    row[f"pinball_{key}_B1"] = mt.pinball_loss(y[mask], block.b1_raw[alpha][mask], alpha)
                for alpha in ONE_SIDED:
                    row[f"coverage_raw_{mt.quantile_key(alpha)}"] = float(np.mean(y[mask] <= block.raw[alpha][mask]))
            rows_out.append(_clean_dict(row))
        segments[dimension] = rows_out
    return segments


def _quantile_totals(block: QuantileBlock, acceptance: Acceptance, min_n: int) -> dict[str, Any]:
    y = block.y
    model = mt.quantile_metrics(y, {a: block.raw[a] for a in CORE_LEVELS})
    model.update(mt.interval_metrics(y, block.raw[INTERVAL[0]], block.raw[INTERVAL[1]], INTERVAL))
    reference = mt.quantile_metrics(y, {a: block.b1_raw[a] for a in CORE_LEVELS})
    reference.update(mt.interval_metrics(y, block.b1_raw[INTERVAL[0]], block.b1_raw[INTERVAL[1]], INTERVAL))
    conformal = {
        "model": _coverage_section(block, block.raw, block.offsets, acceptance),
        "B1": _coverage_section(block, block.b1_raw, block.b1_offsets, acceptance),
    }
    monthly = []
    for month in sorted(set(block.month.tolist())):
        rows = block.month == month
        entry: dict[str, Any] = {"month": month, "n": int(rows.sum())}
        for alpha in ONE_SIDED:
            key = mt.quantile_key(alpha)
            entry[f"coverage_raw_{key}"] = float(np.mean(y[rows] <= block.raw[alpha][rows]))
            entry[f"coverage_raw_{key}_B1"] = float(np.mean(y[rows] <= block.b1_raw[alpha][rows]))
            for scheme in SCHEMES:
                by_month = conformal["model"][scheme][key]["monthly_coverage"]
                entry[f"coverage_{scheme}_{key}"] = by_month[month]
        for alpha in CORE_LEVELS:
            key = mt.quantile_key(alpha)
            entry[f"pinball_{key}"] = mt.pinball_loss(y[rows], block.raw[alpha][rows], alpha)
            entry[f"pinball_{key}_B1"] = mt.pinball_loss(y[rows], block.b1_raw[alpha][rows], alpha)
        monthly.append(_clean_dict(entry))
    return {
        "n": int(y.size),
        "raw": {"model": _clean_dict(model), "B1": _clean_dict(reference)},
        "conformal": conformal,
        "monthly": monthly,
        "segments": _quantile_segments(block, min_n),
    }


def evaluate(
    inputs: EvaluationInputs,
    *,
    acceptance: Acceptance,
    leakage: Mapping[str, Any] | None = None,
    replicates: int = bs.DEFAULT_REPLICATES,
    seed: int = bs.DEFAULT_SEED,
    level: float = bs.CI_LEVEL,
    holm_alpha: float = bs.HOLM_ALPHA,
    segment_min_n: int = 500,
    slope_roles: Sequence[str] = (ROLE_ARR_DEL15_T2,),
) -> dict[str, Any]:
    """Stage 2 (module docstring): one JSON-ready dict."""
    all_dates = [b.date for b in inputs.classifiers.values()] + [b.date for b in inputs.quantiles.values()]
    if not all_dates:
        raise ValueError("Nothing to evaluate")
    days = np.unique(np.concatenate(all_dates))
    n_days = int(days.size)
    multiplicities = bs.day_multiplicities(n_days, replicates=replicates, seed=seed)

    def codes(date: np.ndarray) -> np.ndarray:
        return np.asarray(np.searchsorted(days, date), dtype="int64")

    # --- replicate tables: every statistic on the same day multiplicities ---
    ranked: dict[str, bs.RankedScores] = {}
    means: dict[str, bs.DayMeans] = {}
    for role, block in inputs.classifiers.items():
        c = codes(block.date)
        ranked[role] = bs.RankedScores(block.y, block.raw, c)
        b1_key = f"B1[{block.target}]"
        if b1_key not in ranked:
            ranked[b1_key] = bs.RankedScores(block.y, block.b1_raw, c)
        platt, b1_platt = block.calibrated[PRIMARY_PROBABILITY], block.b1_calibrated[PRIMARY_PROBABILITY]
        means[f"{role}:brier_platt"] = bs.DayMeans((platt - block.y) ** 2, c, n_days)
        means[f"{role}|B1:brier_platt"] = bs.DayMeans((b1_platt - block.y) ** 2, c, n_days)
        means[f"{role}:citl_platt"] = bs.DayMeans(platt - block.y, c, n_days)
    for role, qblock in inputs.quantiles.items():
        c = codes(qblock.date)
        for alpha in CORE_LEVELS:
            key = mt.quantile_key(alpha)
            means[f"{role}:pinball_{key}"] = bs.DayMeans(_pinball_rows(qblock.y, qblock.raw[alpha], alpha), c, n_days)
            means[f"{role}|B1:pinball_{key}"] = bs.DayMeans(
                _pinball_rows(qblock.y, qblock.b1_raw[alpha], alpha), c, n_days
            )
        for alpha in ONE_SIDED:
            key = mt.quantile_key(alpha)
            off = _offset_vector(qblock.month, qblock.offsets[PRIMARY_SCHEME][key])
            covered = (qblock.y <= qblock.raw[alpha] + off).astype("float64")
            means[f"{role}:coverage_{PRIMARY_SCHEME}_{key}"] = bs.DayMeans(covered, c, n_days)

    full: dict[str, float] = {}
    draws: dict[str, np.ndarray] = {}
    for name, scorer in ranked.items():
        full[f"{name}:roc_auc"], full[f"{name}:pr_auc"] = scorer.both(None)
        table = np.array([scorer.both(m) for m in multiplicities], dtype="float64")
        draws[f"{name}:roc_auc"], draws[f"{name}:pr_auc"] = table[:, 0], table[:, 1]
    for name, mean in means.items():
        full[name] = mean(None)
        draws[name] = mean.replicates(multiplicities)

    def diff(a: str, b: str) -> dict[str, Any]:
        return _result(full[a] - full[b], draws[a] - draws[b], level)

    def skill(a: str, b: str) -> dict[str, Any]:
        estimate = 1.0 - full[a] / full[b] if full[b] > 0 else float("nan")
        with np.errstate(divide="ignore", invalid="ignore"):
            return _result(estimate, 1.0 - draws[a] / draws[b], level)

    comparisons: dict[str, Any] = {}
    classification: dict[str, Any] = {}
    for role, block in inputs.classifiers.items():
        b1_key = f"B1[{block.target}]"
        comparisons[role] = {
            "vs_B1": {
                "d_roc_auc": diff(f"{role}:roc_auc", f"{b1_key}:roc_auc"),
                "d_pr_auc": diff(f"{role}:pr_auc", f"{b1_key}:pr_auc"),
                "bss_platt": skill(f"{role}:brier_platt", f"{role}|B1:brier_platt"),
            }
        }
        section = _classifier_totals(block, segment_min_n)
        section["bootstrap"] = {
            "citl_platt": _result(full[f"{role}:citl_platt"], draws[f"{role}:citl_platt"], level),
        }
        if role in slope_roles:
            slope = bs.SlopeStatistic(block.y, block.calibrated[PRIMARY_PROBABILITY], codes(block.date))
            result = bs.bootstrap(slope, multiplicities, level=level)
            section["bootstrap"]["slope_platt"] = _clean_dict(result.to_dict())
        classification[role] = section
    quantile: dict[str, Any] = {}
    for role, qblock in inputs.quantiles.items():
        keys = [mt.quantile_key(a) for a in CORE_LEVELS]
        comparisons[role] = {
            "vs_B1": {f"d_pinball_{k}": diff(f"{role}:pinball_{k}", f"{role}|B1:pinball_{k}") for k in keys}
        }
        section = _quantile_totals(qblock, acceptance, segment_min_n)
        coverage_keys = [f"coverage_{PRIMARY_SCHEME}_{mt.quantile_key(a)}" for a in ONE_SIDED]
        section["bootstrap"] = {k: _result(full[f"{role}:{k}"], draws[f"{role}:{k}"], level) for k in coverage_keys}
        quantile[role] = section

    comparisons["weather_contribution"] = _weather(inputs, diff)
    family: dict[str, float | None] = {}
    available: dict[str, Any] = {}
    for name, role, key in HOLM_FAMILY:
        entry = comparisons.get(role, {}).get("vs_B1", {}).get(key)
        family[name] = None if entry is None else entry.get("p_value")
        available[name] = {"role": role, "comparison": key, "available": entry is not None}
    holm = bs.holm(family, alpha=holm_alpha)
    for name in holm:
        holm[name] |= available[name]

    criteria = _criteria(comparisons, holm, classification, quantile, acceptance, leakage)
    return _clean_nested_dict(
        {
            "label": inputs.label,
            "mode": inputs.mode,
            "days": {"n": n_days, "first": str(days[0]), "last": str(days[-1])},
            "rows": describe_inputs(inputs),
            "bootstrap": {
                "unit": "calendar day (FlightDate)",
                "replicates": replicates,
                "seed": seed,
                "level": level,
                "interval": "percentile",
                "p_value": "2 * min(share(d* <= 0), share(d* >= 0)), capped at 1",
            },
            "acceptance": acceptance.to_dict(),
            "classification": classification,
            "quantile": quantile,
            "comparisons": comparisons,
            "holm": {"alpha": holm_alpha, "family": holm},
            "criteria": criteria,
            "all_passed": all(c["passed"] is True for c in criteria.values()),
            "notes": list(inputs.notes),
        }
    )


def _weather(inputs: EvaluationInputs, diff: Any) -> dict[str, Any]:
    """Plan 6: weather contribution = metric(T2) - metric(plan) on the same rows (paired, same replicates)."""
    weather: dict[str, Any] = {}
    t2, plan = WEATHER_PAIRS[0]
    if t2 in inputs.classifiers and plan in inputs.classifiers:
        a, b = inputs.classifiers[t2], inputs.classifiers[plan]
        if not (np.array_equal(a.y, b.y) and np.array_equal(a.date, b.date)):
            raise ValueError("Weather contribution needs the same evaluation rows for the T2 and plan models")
        weather["arr_del15"] = {
            "d_roc_auc": diff(f"{t2}:roc_auc", f"{plan}:roc_auc"),
            "d_pr_auc": diff(f"{t2}:pr_auc", f"{plan}:pr_auc"),
            "d_brier_platt": diff(f"{t2}:brier_platt", f"{plan}:brier_platt"),
            "definition": f"{t2} − {plan} (Brier: negative = weather helps)",
        }
    t2q, planq = WEATHER_PAIRS[1]
    if t2q in inputs.quantiles and planq in inputs.quantiles:
        weather["arr_delay"] = {
            "d_pinball_q080": diff(f"{t2q}:pinball_q080", f"{planq}:pinball_q080"),
            "definition": f"{t2q} − {planq} (negative = weather helps)",
        }
    weather["oracle"] = "not part of the final test (no oracle model is locked); the captured share is not reported"
    return weather


def _clean_nested_dict(value: dict[str, Any]) -> dict[str, Any]:
    cleaned = _clean_nested(value)
    assert isinstance(cleaned, dict)
    return cleaned


def _clean_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean_nested(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean_nested(v) for v in value]
    if isinstance(value, bool | np.bool_):
        return bool(value)
    if isinstance(value, float | np.floating):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def _criterion(passed: bool | None, description: str, **details: Any) -> dict[str, Any]:
    return {"passed": passed, "description": description, "details": details}


def _get(mapping: Mapping[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _positive(entry: Mapping[str, Any] | None) -> bool | None:
    if entry is None or entry.get("estimate") is None or entry.get("ci_low") is None:
        return None
    return bool(entry["estimate"] > 0 and entry["ci_low"] > 0)


def _negative(entry: Mapping[str, Any] | None) -> bool | None:
    if entry is None or entry.get("estimate") is None or entry.get("ci_high") is None:
        return None
    return bool(entry["estimate"] < 0 and entry["ci_high"] < 0)


def _all(values: Sequence[bool | None]) -> bool | None:
    if any(v is None for v in values):
        return None
    return all(bool(v) for v in values)


def _k5(rolling: Mapping[str, Any] | None, acceptance: Acceptance) -> tuple[bool | None, dict[str, Any]]:
    if rolling is None:
        return None, {}
    c80, c95 = float(rolling["q080"]["coverage"]), float(rolling["q095"]["coverage"])
    s80 = rolling["q080"]["segment_share_within_tolerance"]
    s95 = rolling["q095"]["segment_share_within_tolerance"]
    low80, high80 = acceptance.k5_q080
    low95, high95 = acceptance.k5_q095
    overall = low80 <= c80 <= high80 and low95 <= c95 <= high95
    passed: bool | None = None
    if s80 is not None and s95 is not None:
        passed = bool(overall and s80 >= acceptance.k5_segment_share_min and s95 >= acceptance.k5_segment_share_min)
    insufficient = {*rolling["q080"]["months_insufficient"], *rolling["q095"]["months_insufficient"]}
    details = {
        "coverage_q080": c80,
        "coverage_q095": c95,
        "segment_share_q080": s80,
        "segment_share_q095": s95,
        "months_insufficient": sorted(insufficient),
    }
    return passed, details


def _criteria(
    comparisons: Mapping[str, Any],
    holm: Mapping[str, Any],
    classification: Mapping[str, Any],
    quantile: Mapping[str, Any],
    acceptance: Acceptance,
    leakage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """K1 - K7 of plan 5.3 with the pre-registered readings (``experiments/son-test-on-kayit.md``)."""
    out: dict[str, Any] = {}
    auc = _get(comparisons, ROLE_ARR_DEL15_T2, "vs_B1", "d_roc_auc")
    ap = _get(comparisons, ROLE_ARR_DEL15_T2, "vs_B1", "d_pr_auc")
    holm_auc = _get(holm, "1_arr_del15_roc_auc", "reject") if auc is not None else None
    holm_ap = _get(holm, "2_arr_del15_pr_auc", "reject") if ap is not None else None
    out["K1"] = _criterion(
        _all([_positive(auc), _positive(ap), holm_auc, holm_ap]),
        "ArrDel15 T2 vs B1: ΔROC-AUC > 0 ve ΔPR-AUC > 0; ikisinde de GA alt sınırı > 0 ve Holm sonrası anlamlı",
        d_roc_auc=auc,
        d_pr_auc=ap,
        holm_roc_auc=holm_auc,
        holm_pr_auc=holm_ap,
    )
    bss = _get(comparisons, ROLE_ARR_DEL15_T2, "vs_B1", "bss_platt")
    out["K2"] = _criterion(
        _positive(bss), "ArrDel15 BSS (aylık kayan Platt: model vs B1) > 0 ve GA alt sınırı > 0", bss_platt=bss
    )
    platt = _get(classification, ROLE_ARR_DEL15_T2, "probability", PRIMARY_PROBABILITY, "model")
    k3: bool | None = None
    citl = None if platt is None else platt.get("calibration_in_the_large")
    slope = None if platt is None else platt.get("calibration_slope")
    if citl is not None and slope is not None:
        k3 = abs(citl) <= acceptance.k3_citl_abs_max and acceptance.k3_slope_min <= slope <= acceptance.k3_slope_max
    out["K3"] = _criterion(
        k3,
        f"ArrDel15 aylık kayan Platt: |CITL| ≤ {acceptance.k3_citl_abs_max} ve eğim "
        f"[{acceptance.k3_slope_min}; {acceptance.k3_slope_max}] ({acceptance.source})",
        calibration_in_the_large=citl,
        calibration_slope=slope,
    )
    k4_parts: list[bool | None] = []
    k4_details: dict[str, Any] = {}
    for alpha, holm_name in zip(CORE_LEVELS, ("4_pinball_q050", "5_pinball_q080", "6_pinball_q095"), strict=True):
        key = f"d_pinball_{mt.quantile_key(alpha)}"
        entry = _get(comparisons, ROLE_QUANTILES_PLAN, "vs_B1", key)
        reject = _get(holm, holm_name, "reject") if entry is not None else None
        k4_parts += [_negative(entry), reject]
        k4_details[key] = entry
        k4_details[f"holm_{mt.quantile_key(alpha)}"] = reject
    out["K4"] = _criterion(
        _all(k4_parts),
        "Plan kantilleri vs B1 (ham): α 0,50/0,80/0,95 için Δpinball < 0, GA üst sınırı < 0 ve Holm sonrası anlamlı",
        **k4_details,
    )
    k5, k5_details = _k5(_get(quantile, ROLE_QUANTILES_PLAN, "conformal", "model", PRIMARY_SCHEME), acceptance)
    out["K5"] = _criterion(
        k5,
        f"Plan kantilleri, aylık kayan conformal: P80 kapsama {list(acceptance.k5_q080)}, "
        f"P95 {list(acceptance.k5_q095)}; Origin × ay (n ≥ {acceptance.k5_segment_min_n}) segmentlerinin "
        f"≥ {acceptance.k5_segment_share_min:.0%}'i hedefin ±{acceptance.k5_segment_tolerance} içinde "
        f"({acceptance.source})",
        **k5_details,
    )
    cancel = _get(comparisons, ROLE_CANCELLED_PLAN, "vs_B1", "d_pr_auc")
    out["K6"] = _criterion(
        _positive(cancel), "İptal plan vs B1: ΔPR-AUC > 0 ve GA alt sınırı > 0 (ham skor)", d_pr_auc=cancel
    )
    if leakage is None:
        out["K7"] = _criterion(None, "Sızıntı: §2.6 testleri ve şüpheli skor incelemesi (kanıt verilmedi)")
    else:
        out["K7"] = _criterion(
            leakage.get("passed"),
            "Sızıntı: §2.6 testleri geçti (beyan) ve kilitli modellerde çözülmemiş şüphe yok",
            **{k: v for k, v in leakage.items() if k != "passed"},
        )
    return out


# ----------------------------------------------------------------------------
# rehearsal: checks and the tolerance rule (pre-registration section d)
# ----------------------------------------------------------------------------


def _round_up(value: float, step: float = 0.005) -> float:
    return round(math.ceil(value / step - 1e-9) * step, 6)


def _half_width(entry: Mapping[str, Any] | None) -> float | None:
    if entry is None or any(entry.get(k) is None for k in ("estimate", "ci_low", "ci_high")):
        return None
    return float(max(entry["estimate"] - entry["ci_low"], entry["ci_high"] - entry["estimate"]))


def tolerance_proposal(pooled: Mapping[str, Any], plan: Acceptance | None = None) -> dict[str, Any]:
    """K3 / K5 tolerances from the pooled rehearsal (the test's calendar months, one year earlier): the plan proposal,
    widened to the day-block bootstrap 95 % half-width where that is larger (rounded UP to 0.005). Only the noise
    (interval width) is used, never the rehearsal's own miss (estimate - target), so the rule cannot be steered towards
    a pass. The segment part of K5 is not changed."""
    base = plan or Acceptance()
    widths = {
        "citl_platt": _half_width(_get(pooled, "classification", ROLE_ARR_DEL15_T2, "bootstrap", "citl_platt")),
        "slope_platt": _half_width(_get(pooled, "classification", ROLE_ARR_DEL15_T2, "bootstrap", "slope_platt")),
        "coverage_rolling_q080": _half_width(
            _get(pooled, "quantile", ROLE_QUANTILES_PLAN, "bootstrap", "coverage_rolling_q080")
        ),
        "coverage_rolling_q095": _half_width(
            _get(pooled, "quantile", ROLE_QUANTILES_PLAN, "bootstrap", "coverage_rolling_q095")
        ),
    }
    missing = [k for k, v in widths.items() if v is None]
    if missing:
        return {"acceptance": None, "half_widths": widths, "reason": f"missing bootstrap intervals: {missing}"}
    citl = float(widths["citl_platt"] or 0.0)
    slope_tol = max((base.k3_slope_max - base.k3_slope_min) / 2.0, _round_up(float(widths["slope_platt"] or 0.0)))
    tol80 = max((base.k5_q080[1] - base.k5_q080[0]) / 2.0, _round_up(float(widths["coverage_rolling_q080"] or 0.0)))
    tol95 = max((base.k5_q095[1] - base.k5_q095[0]) / 2.0, _round_up(float(widths["coverage_rolling_q095"] or 0.0)))
    proposal = Acceptance(
        k3_citl_abs_max=max(base.k3_citl_abs_max, _round_up(citl)),
        k3_slope_min=round(1.0 - slope_tol, 6),
        k3_slope_max=round(1.0 + slope_tol, 6),
        k5_q080=(round(0.80 - tol80, 6), round(min(1.0, 0.80 + tol80), 6)),
        k5_q095=(round(0.95 - tol95, 6), round(min(1.0, 0.95 + tol95), 6)),
        k5_segment_tolerance=base.k5_segment_tolerance,
        k5_segment_share_min=base.k5_segment_share_min,
        k5_segment_min_n=base.k5_segment_min_n,
        source="rehearsal rule (pre-registration d): max(plan, rounded-up bootstrap half-width)",
    )
    return {"acceptance": proposal.to_dict(), "half_widths": widths, "plan": base.to_dict()}


def rehearsal_checks(evaluations: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Code-path checks of the rehearsal (pre-registration d); model performance is NOT a gate."""
    checks: dict[str, Any] = {}
    for name, evaluation in evaluations.items():
        criteria = evaluation.get("criteria", {})
        computed = {k: criteria.get(k, {}).get("passed") is not None for k in ("K1", "K2", "K3", "K4", "K5", "K6")}
        family = evaluation.get("holm", {}).get("family", {})
        holm_ok = bool(family) and all(
            not row["p_missing"] and row["p_holm"] >= (row["p_value"] or 0.0) - 1e-12 for row in family.values()
        )
        intervals_ok = True
        for role, role_entry in evaluation.get("comparisons", {}).items():
            if role == "weather_contribution":
                continue
            for entry in (role_entry.get("vs_B1") or {}).values():
                low, high = entry.get("ci_low"), entry.get("ci_high")
                if low is None or high is None or low > high:
                    intervals_ok = False
        rolling = _get(evaluation, "quantile", ROLE_QUANTILES_PLAN, "conformal", "model", PRIMARY_SCHEME) or {}
        insufficient: set[str] = set()
        coverages: list[Any] = []
        for key in ("q080", "q095"):
            level_entry = rolling.get(key) or {}
            insufficient.update(level_entry.get("months_insufficient", []))
            coverages.append(level_entry.get("coverage"))
        coverage_ok = bool(rolling) and all(c is not None and 0.0 <= c <= 1.0 for c in coverages)
        checks[name] = {
            "criteria_computed": computed,
            "holm_complete_and_monotone": holm_ok,
            "bootstrap_intervals_finite": intervals_ok,
            "rolling_conformal_months_insufficient": sorted(insufficient),
            "coverage_in_unit_interval": coverage_ok,
            "passed": all(computed.values()) and holm_ok and intervals_ok and not insufficient and coverage_ok,
        }
    return {"blocks": checks, "passed": bool(checks) and all(c["passed"] for c in checks.values())}
