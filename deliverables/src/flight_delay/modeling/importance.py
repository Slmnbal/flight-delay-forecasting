"""Permutation importance on Val-B and the two-stage leakage review (plan sections 2.6 and 7). Evaluation code.

Why: the step-2 smoke run raised the gain alarm (``arr_del15-lgbm``: 52.9 % of the total gain on
``te_route_hour_arrdel15``). Gain is a proxy (it favours features that are split on often / early); plan section 7
prefers permutation importance. This module turns the alarm into a decision in two stages:

1. **Suspicion** (``gbm.leakage_alarm``, unchanged): one feature carries > 50 % of the total gain. That threshold is the
   plan 2.6 "suspicious score" rule applied to gain; it only starts the review, it does not decide anything.
2. **Decision** = permutation on the evaluation set + "time travel" test:
   - ``permutation_importance``: the fitted model is NOT refitted; one feature column of the Val-B matrix is permuted,
     the model predicts again and the metric change is recorded (``repeats`` permutations, mean +- sd). Val-B is the
     evaluation set that no selection used (Val-A chose the number of trees, so it is not used here).
   - ``time_travel_check``: the history features (the only features computed from labels) are recomputed from data
     that was realised before every evaluation row's information time T and must give the same values; labels after
     the fit end (including the evaluated rows' own labels) must not change any value; the out-of-fold encoding of a
     training row must not depend on its own day block.
   - ``review_model``: per suspected feature the verdict is
     ``leak`` (the feature can carry information from after T: time travel failed, or knowledge class ``oracle``),
     ``undecided`` (stage 2 incomplete), ``dominant_past_only`` (permutation collapses the skill but the feature is
     past-only: strong dependence, NOT leakage; report with that note), ``cleared``.

Permutation scheme (choice and reason):
- ``rows`` (default): the column is permuted over all sampled rows (Breiman / scikit-learn definition). The question
  here is "how much does the fitted model rely on this column on Val-B"; no refit happens, so the temporal dependence
  between rows cannot leak anything into the measurement. Its cost: it also breaks the day-level structure (all Val-B
  days are mixed), so day-level features (calendar, weather of the day) lose both their day signal and their
  within-day signal.
- ``within_day``: the column is permuted only among the rows of the same day; the day-level information stays. The
  difference rows - within_day shows how much of a feature's importance is day-level. Offered as a sensitivity check.
- The rows are a sample of WHOLE Val-B days (``sample_rows_by_days``; same rule as ``matrix.sample_days``), so the
  sample keeps the day structure. The sd is over the permutation repeats only: it is permutation noise, NOT sampling
  uncertainty of Val-B (a day-block bootstrap would be needed for that; not done here).

Decision thresholds (conventions, not fitted numbers; all are parameters):
- ``COLLAPSE_REMAINING_SKILL = 0.25``: "permuting the feature brings the metric to the B0 level" is read as "at most a
  quarter of the model's skill over B0 is left" (ROC-AUC: (AUC_perm - 0.5) / (AUC - 0.5); quantiles:
  (pinball_B0 - pinball_perm) / (pinball_B0 - pinball)). B0 = the fit window's global rate / quantile, taken from the
  fitted history tables (identical to the B0 baseline definition).
- ``HARMFUL_SD = 2``: a feature whose permutation IMPROVES the metric by more than 2 sd of the repeats (and by more
  than 0) is listed as "harmful on Val-B" (e.g. a slope learned in another season). Heuristic.
- ``TIME_TRAVEL_TOLERANCE = 1e-5``: history features are stored as float32 (relative precision ~6e-8); rates lie in
  [0, 1] and quantiles in minutes, so 1e-5 is far above float32 rounding of the same computation and far below any
  real difference. Applied as an absolute tolerance on rates and as a relative one on the other columns.
"""

from __future__ import annotations

import datetime as dt
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import LeakageError
from flight_delay.modeling import features as ft
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import targets as tg
from flight_delay.modeling.gbm import LEAKAGE_GAIN_SHARE
from flight_delay.modeling.history import day_blocks
from flight_delay.modeling.matrix import sample_days

__all__ = [
    "CLASSIFICATION",
    "COLLAPSE_REMAINING_SKILL",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_REPEATS",
    "HARMFUL_SD",
    "PERMUTATION_SET",
    "QUANTILE",
    "RATE_FEATURES",
    "SCHEMES",
    "TIME_TRAVEL_TOLERANCE",
    "PermutationConfig",
    "b0_reference",
    "naive_rate",
    "permutation_importance",
    "permute_values",
    "render_review",
    "review_model",
    "review_run",
    "sample_rows_by_days",
    "score",
    "tamper_labels",
    "time_travel_check",
]

CLASSIFICATION = "binary"
QUANTILE = "quantile"
SCHEMES = ("rows", "within_day")
PERMUTATION_SET = "val_b"
DEFAULT_MAX_ROWS = 300_000
DEFAULT_REPEATS = 3
COLLAPSE_REMAINING_SKILL = 0.25
HARMFUL_SD = 2.0
TIME_TRAVEL_TOLERANCE = 1e-5
_HIGHER_IS_BETTER = frozenset({"roc_auc"})

# te_* features: (levels from coarse to fine, target). The level lists are the feature definitions in ``features``;
# the recomputation below (``naive_rate``) is written independently of ``history.SmoothedRateTable``.
RATE_FEATURES: dict[str, tuple[tuple[tuple[str, ...], ...], str]] = {
    "te_route_hour_arrdel15": (ft._ROUTE_HOUR, tg.ARR_DEL15),
    "te_dest_hour_arrdel15": (ft._DEST_HOUR, tg.ARR_DEL15),
    "te_carrier_origin_arrdel15": (ft._CARRIER_ORIGIN, tg.ARR_DEL15),
    "te_route_cancel": (ft._ROUTE, tg.CANCELLED),
}
_HISTORY_COLUMNS = (*ft._HISTORY_KEYS, *ft._HISTORY_LABELS)


@dataclass(frozen=True)
class PermutationConfig:
    """Sample size, repeats, seed, scheme; ``features`` = subset to permute (None = every model feature)."""

    max_rows: int = DEFAULT_MAX_ROWS
    repeats: int = DEFAULT_REPEATS
    seed: int = 42
    scheme: str = "rows"
    features: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.scheme not in SCHEMES:
            raise ValueError(f"scheme must be one of {SCHEMES}: {self.scheme!r}")
        if self.repeats < 1 or self.max_rows < 1:
            raise ValueError("repeats and max_rows must be >= 1")


# ----------------------------------------------------------------------------
# permutation importance
# ----------------------------------------------------------------------------


def sample_rows_by_days(dates: Any, max_rows: int, *, seed: int = 42) -> np.ndarray:
    """Boolean mask of whole days with about ``max_rows`` rows in total (all rows if there are fewer)."""
    series = pd.Series(pd.to_datetime(np.asarray(dates)))
    if len(series) <= max_rows:
        return np.ones(len(series), dtype=bool)
    return sample_days(series, max_rows / len(series), seed=seed)


def _day_codes(days: Any) -> np.ndarray:
    normalized = pd.Series(pd.to_datetime(np.asarray(days))).dt.normalize()
    codes, _ = pd.factorize(normalized, sort=True)
    return np.asarray(codes, dtype="int64")


def permute_values(values: np.ndarray, day_codes: np.ndarray, rng: np.random.Generator, scheme: str) -> np.ndarray:
    """``rows``: one permutation over all rows; ``within_day``: rows are only exchanged inside their day."""
    if scheme == "rows":
        return np.asarray(values[rng.permutation(values.size)])
    if scheme == "within_day":
        by_day = np.argsort(day_codes, kind="stable")
        shuffled = np.lexsort((rng.random(values.size), day_codes))  # primary key: day, then random order
        out = np.empty_like(values)
        out[by_day] = values[shuffled]
        return out
    raise ValueError(f"scheme must be one of {SCHEMES}: {scheme!r}")


def score(kind: str, y: np.ndarray, predicted: np.ndarray, alpha: float | None = None) -> dict[str, float]:
    """Classification: log-loss and ROC-AUC; quantile: pinball loss at the model's alpha (same metric code)."""
    if kind == CLASSIFICATION:
        return {"log_loss": mt.log_loss(y, predicted), "roc_auc": mt.roc_auc(y, predicted)}
    if kind == QUANTILE:
        if alpha is None:
            raise ValueError("A quantile model needs alpha")
        return {f"pinball_{mt.quantile_key(alpha)}": mt.pinball_loss(y, predicted, alpha)}
    raise ValueError(f"kind must be {CLASSIFICATION!r} or {QUANTILE!r}: {kind!r}")


def _drop(metric: str, base: float, permuted: float) -> float:
    """Positive = permuting the feature made the model worse (the feature matters)."""
    return base - permuted if metric in _HIGHER_IS_BETTER else permuted - base


def b0_reference(history_description: Mapping[str, Any], target: str, alpha: float | None = None) -> float | None:
    """B0 constant of a target from the fitted history tables (fit window global rate / quantile); None if absent."""
    tables = history_description.get("tables", {})
    if target == tg.ARR_DEL15:
        value = tables.get("route_hour_arrdel15", {}).get("global_mean")
    elif target == tg.CANCELLED:
        value = tables.get("route_cancel", {}).get("global_mean")
    elif target == tg.ARR_DELAY and alpha is not None:
        value = tables.get("route_hour_delay", {}).get("global_quantiles", {}).get(mt.quantile_key(alpha))
    else:
        value = None
    return float(value) if value is not None and math.isfinite(float(value)) else None


def _remaining_skill(
    kind: str, base: Mapping[str, float], reference: Mapping[str, float], metric: str, drop: float
) -> float | None:
    """Share of the model's skill over B0 that is left after the permutation (None if the model has no skill)."""
    if kind == CLASSIFICATION:
        skill = base["roc_auc"] - 0.5
        return (base["roc_auc"] - drop - 0.5) / skill if metric == "roc_auc" and skill > 0 else None
    b0 = reference.get(metric)
    if b0 is None:
        return None
    skill = b0 - base[metric]
    return (b0 - (base[metric] + drop)) / skill if skill > 0 else None


def permutation_importance(
    predict: Callable[[np.ndarray], np.ndarray],
    x: np.ndarray,
    y: np.ndarray,
    *,
    feature_names: Sequence[str],
    kind: str,
    days: Any,
    config: PermutationConfig,
    alpha: float | None = None,
    reference: float | None = None,
    set_name: str = PERMUTATION_SET,
) -> dict[str, Any]:
    """Mean +- sd metric change per permuted feature (no refit). ``reference`` = B0 constant (rate or quantile).

    The caller passes evaluation rows only, already restricted to the target universe and to the day sample.
    """
    started = time.perf_counter()
    labels = np.asarray(y, dtype="float64").ravel()
    if x.ndim != 2 or x.shape[0] != labels.size or x.shape[1] != len(feature_names):
        raise ValueError(f"x {x.shape}, y {labels.shape} and {len(feature_names)} feature names do not match")
    if labels.size == 0 or not np.all(np.isfinite(labels)):
        raise ValueError("Permutation needs finite labels (filter the target universe first)")
    codes = _day_codes(days)
    if codes.size != labels.size:
        raise ValueError("days must be aligned with x")
    names = list(feature_names)
    selected = list(config.features) if config.features is not None else names
    unknown = [f for f in selected if f not in names]
    if unknown:
        raise KeyError(f"Unknown feature(s) to permute: {unknown}")
    base = score(kind, labels, predict(x), alpha)
    primary = "roc_auc" if kind == CLASSIFICATION else next(iter(base))
    reference_scores: dict[str, float] = {}
    if reference is not None:
        constant = np.full(labels.size, reference)
        reference_scores = score(kind, labels, constant, alpha)
    work = np.array(x, copy=True)
    rows: list[dict[str, Any]] = []
    for name in selected:
        j = names.index(name)
        original = work[:, j].copy()
        drops: dict[str, list[float]] = {metric: [] for metric in base}
        for repeat in range(config.repeats):
            rng = np.random.default_rng([config.seed, j, repeat])  # stable per (feature position, repeat)
            work[:, j] = permute_values(original, codes, rng, config.scheme)
            permuted = score(kind, labels, predict(work), alpha)
            for metric in base:
                drops[metric].append(_drop(metric, base[metric], permuted[metric]))
        work[:, j] = original
        entry: dict[str, Any] = {"feature": name}
        for metric, values in drops.items():
            array = np.asarray(values, dtype="float64")
            entry[metric] = {
                "mean_drop": float(array.mean()),
                "sd_drop": float(array.std(ddof=1)) if array.size > 1 else 0.0,
                "drops": [float(v) for v in array],
            }
        entry["remaining_skill_share"] = _remaining_skill(
            kind, base, reference_scores, primary, entry[primary]["mean_drop"]
        )
        rows.append(entry)
    rows.sort(key=lambda r: (-r[primary]["mean_drop"], r["feature"]))
    return {
        "set": set_name,
        "kind": kind,
        "alpha": alpha,
        "n_rows": int(labels.size),
        "n_days": int(np.unique(codes).size),
        "scheme": config.scheme,
        "repeats": config.repeats,
        "seed": config.seed,
        "primary_metric": primary,
        "base": base,
        "reference_B0": {"constant": reference, **reference_scores},
        "features": rows,
        "seconds": round(time.perf_counter() - started, 1),
    }


# ----------------------------------------------------------------------------
# time travel test for the history features
# ----------------------------------------------------------------------------


def tamper_labels(frame: pd.DataFrame, rows: np.ndarray) -> pd.DataFrame:
    """Copy of ``frame`` with adversarially changed labels on ``rows`` (flip 0/1 labels, shift durations)."""
    out = frame.copy()
    mask = np.asarray(rows, dtype=bool)
    for column, change in (
        ("ArrDel15", lambda v: 1.0 - v),
        ("Cancelled", lambda v: 1.0 - v),
        ("ArrDelay", lambda v: v + 60.0),
        ("ActualElapsedTime", lambda v: v + 30.0),
        ("TaxiOut", lambda v: v + 30.0),
    ):
        if column in out.columns:
            values = pd.to_numeric(out[column], errors="coerce").astype("float64").to_numpy(copy=True)
            values[mask] = change(values[mask])
            out[column] = values
    return out


def naive_rate(
    train: pd.DataFrame,
    apply: pd.DataFrame,
    levels: Sequence[tuple[str, ...]],
    target: str,
    *,
    m: float,
    min_support: int,
) -> np.ndarray:
    """Hierarchical m-estimate recomputed from scratch (groupby + index lookup; no merge, no shared table code)."""
    y = tg.target_values(train, target)
    use = np.isfinite(y)
    keys_train = ft.add_key_columns(train[list(ft._HISTORY_KEYS)])
    keys_apply = ft.add_key_columns(apply[list(ft._HISTORY_KEYS)])
    value = np.full(len(apply), float(y[use].mean()) if use.any() else np.nan)
    for level in levels:
        columns = list(level)
        if not columns:
            continue
        left = keys_train.loc[use, columns].reset_index(drop=True)
        valid = left.notna().all(axis=1).to_numpy()
        stats_frame = pd.DataFrame({c: left.loc[valid, c].astype(str).to_numpy() for c in columns})
        stats_frame["_y"] = y[use][valid]
        stats = stats_frame.groupby(columns, sort=False)["_y"].agg(["sum", "count"])
        right = keys_apply[columns].reset_index(drop=True)
        right_valid = right.notna().all(axis=1).to_numpy()
        arrays = [right[c].astype(str).to_numpy() for c in columns]
        index = pd.Index(arrays[0]) if len(columns) == 1 else pd.MultiIndex.from_arrays(arrays)
        looked = stats.reindex(index)
        n = np.where(right_valid, looked["count"].fillna(0).to_numpy(dtype="float64"), 0.0)
        total = np.where(right_valid, looked["sum"].fillna(0).to_numpy(dtype="float64"), 0.0)
        denominator = n + m
        smoothed = np.where(denominator > 0, (total + m * value) / np.where(denominator > 0, denominator, 1.0), value)
        value = np.where(n >= min_support, smoothed, value)
    return np.asarray(value, dtype="float64")


def _max_difference(a: Any, b: Any, *, relative: bool) -> float:
    left = np.asarray(a, dtype="float64").ravel()
    right = np.asarray(b, dtype="float64").ravel()
    both_nan = np.isnan(left) & np.isnan(right)
    one_nan = np.isnan(left) ^ np.isnan(right)
    if one_nan.any():
        return float("inf")
    diff = np.where(both_nan, 0.0, np.abs(left - right))
    if relative:
        diff = diff / np.maximum(1.0, np.where(both_nan, 1.0, np.abs(left)))
    return float(diff.max()) if diff.size else 0.0


def _is_rate(feature: str) -> bool:
    return feature.startswith("te_")


def time_travel_check(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    fit_end: dt.date,
    history_factory: Callable[[], ft.HistoryFeatures],
    horizon_hours: float = ft.DEFAULT_HORIZON_HOURS,
    n_blocks: int = 5,
    oof_check: bool = True,
    tolerance: float = TIME_TRAVEL_TOLERANCE,
) -> dict[str, Any]:
    """Past-only proof for the history features on the evaluation rows (and the OOF boundary on training rows).

    ``train``: the fit-window rows (key + label columns; plus ``crs_arr_utc`` for the information-time gap);
    ``evaluation``: evaluation rows with ``crs_dep_utc``. ``history_factory`` builds an unfitted ``HistoryFeatures``
    with the run's settings. Checks (each recorded; ``passed`` per feature = all applicable checks hold):

    - ``fit_refuses_future_rows``: fitting on fit-window + evaluation rows raises ``LeakageError``.
    - ``information_gap_minutes``: earliest (crs_dep_utc - T) of the evaluation rows minus the latest time a fit-window
      label was realised (actual arrival = crs_arr_utc + max(ArrDelay, 0); cancellations at crs_dep_utc). >= 0 means
      every label the statistics use was known before every evaluation row's information time T.
    - ``future_labels``: tampering every evaluation label (incl. the evaluated rows' own) changes no feature value.
    - ``recomputed_from_past`` (te_* rates): an independent recomputation from the fit-window rows gives the same value.
    - ``past_labels_change_values`` (control, not required): tampering fit-window labels changes the value.
    - ``own_block`` (OOF, training rows): tampering the labels of one day block leaves that block's encoding unchanged.
      Note: mode ``oof`` encodes a training row from all OTHER blocks, later blocks included (plan 2.4 item 2); that is
      future data relative to the training row, i.e. a train / serve difference, not evaluation leakage.
    """
    started = time.perf_counter()
    columns = list(_HISTORY_COLUMNS)
    train_dates = pd.to_datetime(train["FlightDate"]).dt.normalize()
    eval_dates = pd.to_datetime(evaluation["FlightDate"]).dt.normalize()
    if len(train_dates) and train_dates.max() > pd.Timestamp(fit_end):
        raise ValueError("train contains rows after fit_end")
    if len(eval_dates) and eval_dates.min() <= pd.Timestamp(fit_end):
        raise ValueError("evaluation rows must lie after fit_end")
    result: dict[str, Any] = {
        "fit_end": str(fit_end),
        "tolerance": tolerance,
        "n_train": len(train),
        "n_evaluation": len(evaluation),
    }

    probe = pd.concat([train[columns].tail(1000), evaluation[columns].head(1000)], ignore_index=True)
    try:
        history_factory().fit(probe, fit_end=fit_end)
        result["fit_refuses_future_rows"] = False
    except LeakageError:
        result["fit_refuses_future_rows"] = True

    gap: float | None = None
    if {"crs_arr_utc", "crs_dep_utc"} <= set(train.columns) and "crs_dep_utc" in evaluation.columns:
        delay = pd.to_numeric(train["ArrDelay"], errors="coerce").fillna(0.0).clip(lower=0.0)
        realised = pd.to_datetime(train["crs_arr_utc"]) + pd.to_timedelta(delay, unit="m")
        cancelled = pd.to_numeric(train["Cancelled"], errors="coerce").fillna(0.0).to_numpy() == 1
        realised = realised.where(~cancelled, pd.to_datetime(train["crs_dep_utc"]))
        earliest_t = pd.to_datetime(evaluation["crs_dep_utc"]).min() - pd.Timedelta(hours=horizon_hours)
        gap = float((earliest_t - realised.max()).total_seconds() / 60.0)
    result["information_gap_minutes"] = gap

    fitted = history_factory().fit(train[columns], fit_end=fit_end)
    reference = fitted.transform(evaluation[columns], require_after_fit_end=True)
    tampered_eval = tamper_labels(evaluation[columns], np.ones(len(evaluation), dtype=bool))
    after = history_factory().fit(train[columns], fit_end=fit_end).transform(tampered_eval, require_after_fit_end=True)
    tampered_train = tamper_labels(train[columns], np.ones(len(train), dtype=bool))
    control = history_factory().fit(tampered_train, fit_end=fit_end).transform(evaluation[columns])

    own_block: dict[str, float] = {}
    oof_info: dict[str, Any] = {"checked": False}
    if oof_check:
        blocks = day_blocks(train["FlightDate"], n_blocks)
        block = n_blocks // 2
        encoded = history_factory().fit_transform_out_of_fold(train[columns], fit_end=fit_end, n_blocks=n_blocks)
        tampered_block = tamper_labels(train[columns], blocks == block)
        encoded_t = history_factory().fit_transform_out_of_fold(tampered_block, fit_end=fit_end, n_blocks=n_blocks)
        rows = blocks == block
        for feature in ft.HISTORY_FEATURES:
            own_block[feature] = _max_difference(
                encoded.loc[rows, feature], encoded_t.loc[rows, feature], relative=not _is_rate(feature)
            )
        changed_elsewhere = any(
            _max_difference(encoded.loc[~rows, f], encoded_t.loc[~rows, f], relative=not _is_rate(f)) > tolerance
            for f in ft.HISTORY_FEATURES
        )
        oof_info = {
            "checked": True,
            "block_tampered": int(block),
            "n_blocks": n_blocks,
            "other_blocks_changed": bool(changed_elsewhere),
            "mode": "oof (other blocks, later blocks included; plan 2.4 item 2)",
        }
    result["oof"] = oof_info

    settings = {"m": fitted.m, "min_support": fitted.min_support}
    per_feature: dict[str, dict[str, Any]] = {}
    for feature in ft.HISTORY_FEATURES:
        relative = not _is_rate(feature)
        entry: dict[str, Any] = {
            "future_labels_max_diff": _max_difference(reference[feature], after[feature], relative=relative),
            "past_labels_change_values": _max_difference(reference[feature], control[feature], relative=relative)
            > tolerance,
        }
        if feature in RATE_FEATURES:
            levels, target = RATE_FEATURES[feature]
            recomputed = naive_rate(
                train, evaluation, levels[1:], target, m=float(settings["m"]), min_support=int(settings["min_support"])
            )
            entry["recomputed_from_past_max_diff"] = _max_difference(reference[feature], recomputed, relative=False)
        if feature in own_block:
            entry["own_block_max_diff"] = own_block[feature]
        checks = [
            bool(result["fit_refuses_future_rows"]),
            entry["future_labels_max_diff"] <= tolerance,
            gap is None or gap >= 0,
        ]
        if "recomputed_from_past_max_diff" in entry:
            checks.append(entry["recomputed_from_past_max_diff"] <= tolerance)
        if "own_block_max_diff" in entry:
            checks.append(entry["own_block_max_diff"] <= tolerance)
        entry["passed"] = bool(all(checks))
        per_feature[feature] = entry
    result["features"] = per_feature
    result["passed_all"] = bool(all(e["passed"] for e in per_feature.values()))
    result["seconds"] = round(time.perf_counter() - started, 1)
    return result


# ----------------------------------------------------------------------------
# two-stage review
# ----------------------------------------------------------------------------

_SCHEDULE_NOTE = "schedule: known when the timetable is published (feature contract)"
_WEATHER_NOTE = "observation before T: row-level check features.check_weather_timing (raises otherwise)"


def _past_only(feature: str, knowledge: str | None, time_travel: Mapping[str, Any] | None) -> tuple[bool | None, str]:
    if knowledge == "past_realized":
        if time_travel is None or feature not in time_travel.get("features", {}):
            return None, "history feature: time travel test not run"
        passed = bool(time_travel["features"][feature]["passed"])
        return passed, "history feature: time travel test " + ("passed" if passed else "FAILED")
    if knowledge == "schedule":
        return True, _SCHEDULE_NOTE
    if knowledge == "observation_before_T":
        return True, _WEATHER_NOTE
    if knowledge == "oracle":
        return False, "oracle weather: observed after T by definition (upper-bound experiment only)"
    return None, f"unknown knowledge class {knowledge!r}"


def review_model(
    model_key: str,
    *,
    gain_importance: Sequence[Mapping[str, Any]] | None,
    permutation: Mapping[str, Any] | None,
    time_travel: Mapping[str, Any] | None,
    knowledge: Mapping[str, str],
    gain_threshold: float = LEAKAGE_GAIN_SHARE,
    collapse_share: float = COLLAPSE_REMAINING_SKILL,
    harmful_sd: float = HARMFUL_SD,
) -> dict[str, Any]:
    """Stage 1 (gain share) -> suspects; stage 2 (permutation + time travel) -> verdict per suspect and per model."""
    suspects: dict[str, list[str]] = {}
    gain_share: dict[str, float] = {}
    if gain_importance:
        top = gain_importance[0]
        gain_share = {str(r["feature"]): float(r["gain_share"]) for r in gain_importance}
        if float(top["gain_share"]) > gain_threshold:
            suspects.setdefault(str(top["feature"]), []).append(f"gain share > {gain_threshold:.0%}")
    perm_rows: dict[str, Mapping[str, Any]] = {}
    harmful: list[dict[str, Any]] = []
    primary = None
    if permutation is not None:
        primary = str(permutation["primary_metric"])
        perm_rows = {str(r["feature"]): r for r in permutation["features"]}
        for name, row in perm_rows.items():
            remaining = row.get("remaining_skill_share")
            if remaining is not None and remaining <= collapse_share:
                suspects.setdefault(name, []).append(f"permutation leaves <= {collapse_share:.0%} of the skill over B0")
            mean, sd = row[primary]["mean_drop"], row[primary]["sd_drop"]
            if mean < 0 and mean < -harmful_sd * sd:
                harmful.append({"feature": name, "mean_drop": mean, "sd_drop": sd})
    verdicts: list[dict[str, Any]] = []
    for feature, reasons in suspects.items():
        perm_row = perm_rows.get(feature)
        remaining = perm_row.get("remaining_skill_share") if perm_row else None
        collapse = None if remaining is None else bool(remaining <= collapse_share)
        past_only, note = _past_only(feature, knowledge.get(feature), time_travel)
        if past_only is False:
            verdict = "leak"
        elif permutation is None or past_only is None or (perm_row is None):
            verdict = "undecided"
        elif collapse:
            verdict = "dominant_past_only"
        else:
            verdict = "cleared"
        verdicts.append(
            {
                "feature": feature,
                "reasons": reasons,
                "gain_share": gain_share.get(feature),
                "permutation_mean_drop": perm_row[primary]["mean_drop"] if perm_row and primary else None,
                "permutation_sd_drop": perm_row[primary]["sd_drop"] if perm_row and primary else None,
                "remaining_skill_share": remaining,
                "collapse": collapse,
                "knowledge_time": knowledge.get(feature),
                "past_only": past_only,
                "past_only_evidence": note,
                "verdict": verdict,
            }
        )
    order = ("leak", "undecided", "dominant_past_only", "cleared")
    found = [v["verdict"] for v in verdicts]
    status = next((s for s in order if s in found), "no_suspicion")
    no_skill = permutation is not None and float(permutation["base"].get("roc_auc", 1.0)) <= 0.5
    return {
        "model": model_key,
        "status": status,
        "reportable": status in ("no_suspicion", "cleared", "dominant_past_only"),
        "suspects": verdicts,
        "harmful_on_evaluation_set": sorted(harmful, key=lambda r: r["mean_drop"]),
        "model_has_no_skill_over_B0": no_skill,
        "stage_1": f"gain share > {gain_threshold:.0%} (suspicion only)",
        "stage_2": "permutation on Val-B + time travel test" if permutation is not None else "not run",
        "thresholds": {"collapse_remaining_skill": collapse_share, "harmful_sd": harmful_sd},
    }


def review_run(models: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Run-level status from the per-model reviews (worst status wins)."""
    order = ("leak", "undecided", "dominant_past_only", "cleared", "no_suspicion")
    statuses = [m["status"] for m in models.values()]
    status = next((s for s in order if s in statuses), "no_suspicion")
    return {"status": status, "reportable": status in order[2:], "models": dict(models)}


_VERDICT_TR = {
    "leak": "SIZINTI (karar: raporlanmaz)",
    "undecided": "karar yok (2. aşama eksik; şüphe sürüyor)",
    "dominant_past_only": "güçlü bağımlılık, geçmiş-only (sızıntı değil; notla raporlanır)",
    "cleared": "şüphe kalktı",
    "no_suspicion": "şüphe yok",
}


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "evet" if value else "hayır"
    if isinstance(value, float):
        return "-" if not math.isfinite(value) else f"{value:.{digits}f}"
    return str(value)


def render_review(
    review: Mapping[str, Any],
    permutation: Mapping[str, Mapping[str, Any]],
    time_travel: Mapping[str, Any] | None,
    *,
    top: int = 10,
) -> list[str]:
    """Turkish markdown lines (every number from the given results)."""
    lines = [
        "## Sızıntı incelemesi (2 aşama: kazanç = şüphe; permütasyon + zaman yolculuğu = karar)",
        "",
        f"- Koşu düzeyi karar: **{_VERDICT_TR.get(review['status'], review['status'])}** · raporlanabilir: "
        f"{_fmt(review['reportable'])}",
        f"- Eşikler (kural, uydurulmuş sayı değil): çökme = B0 üstü becerinin en fazla %"
        f"{COLLAPSE_REMAINING_SKILL * 100:.0f}'i kalırsa; zararlı = permütasyon metriği {HARMFUL_SD:g} sd'den fazla "
        f"iyileştirirse; zaman yolculuğu toleransı {TIME_TRAVEL_TOLERANCE:g}.",
        "- sd yalnızca permütasyon tekrarlarının gürültüsüdür; Val-B örneklem belirsizliği değildir.",
        "",
    ]
    if time_travel is not None:
        lines += [
            f"- Zaman yolculuğu: tümü geçti: {_fmt(time_travel['passed_all'])} · fit gelecek satırı reddediyor: "
            f"{_fmt(time_travel['fit_refuses_future_rows'])} · bilgi aralığı (dk, ≥ 0 olmalı): "
            f"{_fmt(time_travel['information_gap_minutes'], 1)} · OOF kendi blok kontrolü: "
            f"{_fmt(time_travel['oof'].get('checked'))}",
            "",
        ]
    for key, model in review["models"].items():
        lines.append(f"### `{key}` – {_VERDICT_TR.get(model['status'], model['status'])}")
        lines.append("")
        block = permutation.get(key)
        if block is not None:
            primary = block["primary_metric"]
            lines.append(
                f"- Val-B örneklemi: {block['n_rows']} satır / {block['n_days']} gün · şema {block['scheme']} · "
                f"{block['repeats']} tekrar · tohum {block['seed']} · taban {primary} {_fmt(block['base'][primary])} "
                f"· B0 {primary} {_fmt(block['reference_B0'].get(primary))} · {block['seconds']} sn"
            )
            if model.get("model_has_no_skill_over_B0"):
                lines.append("- **Model Val-B'de B0'dan iyi sıralamıyor (ROC-AUC ≤ 0.5): önem sayıları anlamsız.**")
            lines += ["", f"| Özellik | Δ {primary} (ort.) | sd | Kalan beceri payı |", "|---|---|---|---|"]
            for row in block["features"][:top]:
                lines.append(
                    f"| {row['feature']} | {_fmt(row[primary]['mean_drop'])} | {_fmt(row[primary]['sd_drop'])} | "
                    f"{_fmt(row.get('remaining_skill_share'), 3)} |"
                )
            lines.append("")
        for verdict in model["suspects"]:
            lines.append(
                f"- Şüpheli `{verdict['feature']}` ({'; '.join(verdict['reasons'])}): kazanç payı "
                f"{_fmt(verdict['gain_share'], 3)}, kalan beceri payı {_fmt(verdict['remaining_skill_share'], 3)}, "
                f"geçmiş-only: {_fmt(verdict['past_only'])} ({verdict['past_only_evidence']}) → "
                f"**{_VERDICT_TR.get(verdict['verdict'], verdict['verdict'])}**"
            )
        if model["harmful_on_evaluation_set"]:
            names = ", ".join(r["feature"] for r in model["harmful_on_evaluation_set"][:top])
            lines.append(f"- Val-B'de zararlı (permütasyon metriği iyileştiriyor): {names}")
        lines.append("")
    lines.append(
        "Δ: pozitif = özelliği karıştırmak modeli kötüleştirdi (özellik önemli); log-loss / pinball artışı, ROC-AUC "
        "düşüşü. Kalan beceri payı: ROC-AUC için (AUC_perm − 0.5) / (AUC − 0.5); kantil için "
        "(pinball_B0 − pinball_perm) / (pinball_B0 − pinball)."
    )
    lines.append("")
    return lines
