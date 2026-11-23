"""Baselines of plan section 4.1, all evaluated with the same split rule and the same metric code (``metrics``).

| Name | Classification (ArrDel15, cancellation) | Quantiles (ArrDelay | completed) |
|------|------------------------------------------|-----------------------------------|
| B0   | fit-window overall rate                  | fit-window overall quantiles       |
| B1   | route x hour_block rate, m-estimate shrunk to the parent; back-off route x hour -> origin x hour -> origin -> global | route x hour_block empirical quantiles with the n * (1 - alpha) >= 20 back-off rule |
| B2   | B1 + season level at the bottom (route x hour x season, shrunk to route x hour) | same with season |

The logistic-regression baseline L (plan 4.1) needs scikit-learn, which is not declared in ``pyproject.toml``; it is
left for the next run (report: "required change"). Kabul ölçütleri B1'e göre (plan 5.3); B1 is the reference of the
Brier skill score.

F1 threshold (plan 5.1): chosen on Val-B for every baseline and applied unchanged to every evaluation set; on Val-B
itself it is in-sample and labelled so. Segment tables (plan section 7): Origin, hour_block, month; there is NO carrier
dimension (presentation rule, plan section 7).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.modeling import metrics as mt
from flight_delay.modeling import targets as tg
from flight_delay.modeling.features import add_key_columns
from flight_delay.modeling.history import (
    DEFAULT_M,
    DEFAULT_MIN_SUPPORT,
    DEFAULT_MIN_TAIL,
    BackoffQuantileTable,
    SmoothedRateTable,
)
from flight_delay.modeling.splits import check_temporal_order

__all__ = [
    "BASELINES",
    "BASELINE_QUANTILE_LEVELS",
    "DEFAULT_SEGMENT_MIN_N",
    "FORBIDDEN_SEGMENT_DIMENSIONS",
    "REFERENCE_BASELINE",
    "SEGMENT_DIMENSIONS",
    "THRESHOLD_SET",
    "BaselineSpec",
    "evaluate_baselines",
    "make_quantile_baseline",
    "make_rate_baseline",
]


@dataclass(frozen=True)
class BaselineSpec:
    name: str
    levels: tuple[tuple[str, ...], ...]
    description: str


_B1_LEVELS: tuple[tuple[str, ...], ...] = ((), ("Origin",), ("Origin", "hour_block"), ("Origin", "Dest", "hour_block"))
BASELINES: dict[str, BaselineSpec] = {
    "B0": BaselineSpec("B0", ((),), "fit-window overall rate / quantiles"),
    "B1": BaselineSpec("B1", _B1_LEVELS, "route x hour_block with hierarchical back-off (plan 4.1)"),
    "B2": BaselineSpec(
        "B2", (*_B1_LEVELS, ("Origin", "Dest", "hour_block", "season")), "B1 + season level (plan 4.1, optional)"
    ),
}
REFERENCE_BASELINE = "B1"
BASELINE_QUANTILE_LEVELS: tuple[float, ...] = (0.10, 0.50, 0.80, 0.90, 0.95)  # plan levels + 80 % interval ends
SEGMENT_DIMENSIONS = ("Origin", "hour_block", "month")
FORBIDDEN_SEGMENT_DIMENSIONS = ("Reporting_Airline",)  # plan section 7: no carrier tables
DEFAULT_SEGMENT_MIN_N = 500  # segments below this get n only (assumption; plan 5.3 uses n >= 500 for coverage)
THRESHOLD_SET = "val_b"


def make_rate_baseline(name: str, *, m: float = DEFAULT_M, min_support: int = DEFAULT_MIN_SUPPORT) -> SmoothedRateTable:
    return SmoothedRateTable(BASELINES[name].levels, m=m, min_support=min_support, name=name)


def make_quantile_baseline(
    name: str, *, alphas: Sequence[float] = BASELINE_QUANTILE_LEVELS, min_tail: int = DEFAULT_MIN_TAIL
) -> BackoffQuantileTable:
    return BackoffQuantileTable(BASELINES[name].levels, alphas, min_tail=min_tail, name=name)


def _clean(value: Any) -> Any:
    """float NaN / inf -> None (JSON); numpy scalars -> Python."""
    if isinstance(value, float | np.floating):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def _clean_dict(values: Mapping[str, Any]) -> dict[str, Any]:
    return {k: _clean(v) for k, v in values.items()}


def _classification_segments(
    keys: pd.DataFrame, y: np.ndarray, p: np.ndarray, p_reference: np.ndarray, min_n: int
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for dimension in SEGMENT_DIMENSIONS:
        if dimension in FORBIDDEN_SEGMENT_DIMENSIONS:
            raise ValueError(f"Segment dimension {dimension} is not allowed (plan section 7)")
        rows: list[dict[str, Any]] = []
        values = np.asarray(keys[dimension].astype(str), dtype=str)
        for value in sorted(set(values)):
            mask = values == value
            n = int(mask.sum())
            row: dict[str, Any] = {"segment": str(value), "n": n}
            if n >= min_n:
                ys, ps, refs = y[mask], p[mask], p_reference[mask]
                row.update(
                    {
                        "prevalence": float(ys.mean()),
                        "mean_pred": float(ps.mean()),
                        "calibration_in_the_large": float(ps.mean() - ys.mean()),
                        "brier": mt.brier_score(ys, ps),
                        "brier_skill_score": mt.brier_skill_score(ys, ps, refs),
                        "roc_auc": mt.roc_auc(ys, ps),
                        "pr_auc": mt.average_precision(ys, ps),
                    }
                )
            rows.append(_clean_dict(row))
        out[dimension] = rows
    return out


def _quantile_segments(
    keys: pd.DataFrame, y: np.ndarray, quantiles: Mapping[float, np.ndarray], min_n: int
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for dimension in SEGMENT_DIMENSIONS:
        rows: list[dict[str, Any]] = []
        values = np.asarray(keys[dimension].astype(str), dtype=str)
        for value in sorted(set(values)):
            mask = values == value
            n = int(mask.sum())
            row: dict[str, Any] = {"segment": str(value), "n": n}
            if n >= min_n:
                for alpha in (0.80, 0.95):
                    if alpha in quantiles:
                        key = mt.quantile_key(alpha)
                        row[f"pinball_{key}"] = mt.pinball_loss(y[mask], quantiles[alpha][mask], alpha)
                        row[f"coverage_{key}"] = mt.coverage(y[mask], quantiles[alpha][mask])
            rows.append(_clean_dict(row))
        out[dimension] = rows
    return out


def evaluate_baselines(
    train: pd.DataFrame,
    evaluations: Mapping[str, pd.DataFrame],
    *,
    fit_end: dt.date,
    baselines: Sequence[str] = ("B0", "B1", "B2"),
    m: float = DEFAULT_M,
    min_support: int = DEFAULT_MIN_SUPPORT,
    min_tail: int = DEFAULT_MIN_TAIL,
    segment_min_n: int = DEFAULT_SEGMENT_MIN_N,
    embargo_days: int = 0,
    threshold_set: str = THRESHOLD_SET,
) -> dict[str, Any]:
    """Fit every baseline on ``train`` (fit window only) and score it on each evaluation frame.

    Frames: loader output with keys (FlightDate, Origin, Dest, crs_dep_local_min) and labels (ArrDelay, ArrDel15,
    Cancelled, Diverted). Predictions use key columns only (history tables never read labels in ``transform``).
    """
    if REFERENCE_BASELINE not in baselines:
        raise ValueError(
            f"{REFERENCE_BASELINE} must be evaluated: it is the reference of BSS and of the acceptance criteria"
        )
    unknown = [b for b in baselines if b not in BASELINES]
    if unknown:
        raise KeyError(f"Unknown baselines: {unknown}")
    train_keys = add_key_columns(train)
    eval_keys = {name: add_key_columns(frame) for name, frame in evaluations.items()}
    for frame in eval_keys.values():
        check_temporal_order(train_keys["FlightDate"], frame["FlightDate"], embargo_days=embargo_days)

    result: dict[str, Any] = {"classification": {}, "quantile": {}, "thresholds": {}, "fitted": {}}

    # --- classification targets ---
    for target in tg.CLASSIFICATION_TARGETS:
        y_train = tg.target_values(train, target)
        models = {
            b: make_rate_baseline(b, m=m, min_support=min_support).fit(train_keys, y_train, fit_end=fit_end)
            for b in baselines
        }
        result["fitted"][target] = {b: model.describe() for b, model in models.items()}
        predictions: dict[str, dict[str, np.ndarray]] = {}
        observed: dict[str, np.ndarray] = {}
        inside: dict[str, np.ndarray] = {}
        for set_name, keys in eval_keys.items():
            y = tg.target_values(evaluations[set_name], target)
            inside[set_name] = np.isfinite(y)
            observed[set_name] = y[inside[set_name]]
            predictions[set_name] = {
                b: models[b]
                .transform(keys.loc[inside[set_name]], require_after_fit_end=True)["value"]
                .to_numpy(dtype="float64")
                for b in baselines
            }
        thresholds: dict[str, float | None] = {}
        for b in baselines:
            if threshold_set in observed:
                threshold, _ = mt.best_f1_threshold(observed[threshold_set], predictions[threshold_set][b])
                thresholds[b] = threshold if np.isfinite(threshold) else None
            else:
                thresholds[b] = None
        result["thresholds"][target] = {"chosen_on": threshold_set if threshold_set in observed else None, **thresholds}
        per_set: dict[str, Any] = {}
        for set_name, y in observed.items():
            reference = predictions[set_name][REFERENCE_BASELINE]
            keys_inside = eval_keys[set_name].loc[inside[set_name]]
            per_baseline: dict[str, Any] = {}
            for b in baselines:
                p = predictions[set_name][b]
                total = mt.classification_metrics(y, p, y_prob_reference=reference, threshold=thresholds[b])
                total["threshold_in_sample"] = float(set_name == threshold_set)
                per_baseline[b] = {
                    "total": _clean_dict(total),
                    "segments": _classification_segments(keys_inside, y, p, reference, segment_min_n),
                }
            per_set[set_name] = per_baseline
        result["classification"][target] = per_set

    # --- quantiles of ArrDelay (completed flights) ---
    y_train = tg.target_values(train, tg.ARR_DELAY)
    quantile_models = {
        b: make_quantile_baseline(b, min_tail=min_tail).fit(train_keys, y_train, fit_end=fit_end) for b in baselines
    }
    result["fitted"][tg.ARR_DELAY] = {b: model.describe() for b, model in quantile_models.items()}
    per_set_q: dict[str, Any] = {}
    for set_name, keys in eval_keys.items():
        y = tg.target_values(evaluations[set_name], tg.ARR_DELAY)
        use = np.isfinite(y)
        per_baseline_q: dict[str, Any] = {}
        for b in baselines:
            predicted = quantile_models[b].quantiles(keys.loc[use], require_after_fit_end=True)
            per_baseline_q[b] = {
                "total": _clean_dict(mt.quantile_metrics(y[use], predicted, interval=tg.INTERVAL_LEVELS)),
                "segments": _quantile_segments(keys.loc[use], y[use], predicted, segment_min_n),
            }
        per_set_q[set_name] = per_baseline_q
    result["quantile"][tg.ARR_DELAY] = per_set_q

    result["universe"] = {
        "train": tg.universe_summary(train),
        **{name: tg.universe_summary(frame) for name, frame in evaluations.items()},
    }
    result["arr_del15_consistency"] = {
        "train": tg.arr_del15_consistency(train),
        **{name: tg.arr_del15_consistency(frame) for name, frame in evaluations.items()},
    }
    result["parameters"] = {
        "fit_end": str(fit_end),
        "baselines": list(baselines),
        "m": m,
        "min_support": min_support,
        "min_tail": min_tail,
        "segment_min_n": segment_min_n,
        "embargo_days": embargo_days,
        "threshold_set": threshold_set,
        "quantile_levels": list(BASELINE_QUANTILE_LEVELS),
        "segment_dimensions": list(SEGMENT_DIMENSIONS),
    }
    return result
