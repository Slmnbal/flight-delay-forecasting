"""Targets and their universes (plan section 3). Label code only: reads ``flight_labels`` columns.

| Target (code)  | Plan name            | Universe (rows that enter)                                   | Value                      |
|----------------|----------------------|--------------------------------------------------------------|----------------------------|
| ``arr_del15``  | ArrDel15             | completed flights: Cancelled = 0, Diverted = 0, ArrDel15 and ArrDelay present | BTS ``ArrDel15`` (0/1) |
| ``cancelled``  | iptal                | every scheduled flight (cancelled rows keep their CRS times) | ``Cancelled == 1``         |
| ``arr_delay``  | varış rötarı (kantil) | completed flights with ArrDelay present                      | ``ArrDelay`` minutes (early = negative, no clipping) |
| ``disruption`` | aksaklik (optional)  | every scheduled flight                                       | ArrDel15 or Cancelled or Diverted |

Rows outside a universe get NaN. Diverted flights are outside ``arr_del15`` / ``arr_delay`` (BTS has no ArrDelay for
them) and are NOT cancellations. The quantile models are therefore conditional on "the flight was completed"
(plan section 3.2 note 1); ``conditional_level`` / ``unconditional_exceedance`` implement the plan section 3.3 formulas.
``arr_del15_consistency`` is the data check behind plan section 2.6 ``test_hedef_tutarliligi`` (the BTS definition of
ArrDel15 was not verified, so mismatches are counted, not silently fixed).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "ARR_DEL15",
    "ARR_DEL15_THRESHOLD_MIN",
    "ARR_DELAY",
    "CANCELLED",
    "CLASSIFICATION_TARGETS",
    "DISRUPTION",
    "INTERVAL_LEVELS",
    "LABEL_COLUMNS_NEEDED",
    "QUANTILE_LEVELS",
    "TARGETS",
    "arr_del15_consistency",
    "build_targets",
    "completed_mask",
    "conditional_level",
    "target_values",
    "unconditional_exceedance",
    "universe_mask",
    "universe_summary",
]

ARR_DEL15 = "arr_del15"
CANCELLED = "cancelled"
ARR_DELAY = "arr_delay"
DISRUPTION = "disruption"
TARGETS = (ARR_DEL15, CANCELLED, ARR_DELAY, DISRUPTION)
CLASSIFICATION_TARGETS = (ARR_DEL15, CANCELLED)

QUANTILE_LEVELS: tuple[float, ...] = (0.50, 0.80, 0.95)  # plan section 3.3
INTERVAL_LEVELS: tuple[float, float] = (0.10, 0.90)  # two-sided 80 % interval (plan sections 4.2, 5.1)
ARR_DEL15_THRESHOLD_MIN = 15.0
LABEL_COLUMNS_NEEDED = ("ArrDelay", "ArrDel15", "Cancelled", "Diverted")


def _numeric(labels: pd.DataFrame, column: str) -> np.ndarray:
    if column not in labels.columns:
        raise KeyError(f"Label column missing: {column}")
    # astype first: nullable integers (Int8 with <NA>) become float64 with NaN
    return np.asarray(pd.to_numeric(labels[column], errors="coerce").astype("float64"), dtype="float64")


def completed_mask(labels: pd.DataFrame) -> np.ndarray:
    """Cancelled = 0 and Diverted = 0 (both are key fields in the layer, so they are never empty there)."""
    return np.asarray((_numeric(labels, "Cancelled") == 0) & (_numeric(labels, "Diverted") == 0), dtype=bool)


def universe_mask(labels: pd.DataFrame, target: str) -> np.ndarray:
    """Rows that belong to a target's universe (see the module table)."""
    cancelled = _numeric(labels, "Cancelled")
    diverted = _numeric(labels, "Diverted")
    if target == ARR_DEL15:
        return (
            completed_mask(labels) & ~np.isnan(_numeric(labels, "ArrDel15")) & ~np.isnan(_numeric(labels, "ArrDelay"))
        )
    if target == ARR_DELAY:
        return completed_mask(labels) & ~np.isnan(_numeric(labels, "ArrDelay"))
    if target == CANCELLED:
        return np.asarray(~np.isnan(cancelled), dtype=bool)
    if target == DISRUPTION:
        known = ~np.isnan(cancelled) & ~np.isnan(diverted)
        completed = (cancelled == 0) & (diverted == 0)
        return np.asarray(known & (~completed | ~np.isnan(_numeric(labels, "ArrDel15"))), dtype=bool)
    raise KeyError(f"Unknown target {target!r}; known: {TARGETS}")


def target_values(labels: pd.DataFrame, target: str) -> np.ndarray:
    """Target value per row (float64); NaN outside the universe."""
    inside = universe_mask(labels, target)
    if target == ARR_DEL15:
        values = _numeric(labels, "ArrDel15")
    elif target == ARR_DELAY:
        values = _numeric(labels, "ArrDelay")
    elif target == CANCELLED:
        values = (_numeric(labels, "Cancelled") == 1).astype("float64")
    else:  # DISRUPTION
        late = _numeric(labels, "ArrDel15") == 1
        values = (late | (_numeric(labels, "Cancelled") == 1) | (_numeric(labels, "Diverted") == 1)).astype("float64")
    return np.where(inside, values, np.nan)


def build_targets(labels: pd.DataFrame) -> pd.DataFrame:
    """``flight_uid`` + one column per target (NaN outside its universe)."""
    out = pd.DataFrame({"flight_uid": labels["flight_uid"].to_numpy()}, index=labels.index)
    for target in TARGETS:
        out[target] = target_values(labels, target)
    return out


def universe_summary(labels: pd.DataFrame) -> dict[str, int]:
    """Row counts: total, per universe, cancelled, diverted."""
    summary = {"rows": int(len(labels))}
    for target in TARGETS:
        summary[f"universe_{target}"] = int(universe_mask(labels, target).sum())
    summary["cancelled"] = int((_numeric(labels, "Cancelled") == 1).sum())
    summary["diverted"] = int((_numeric(labels, "Diverted") == 1).sum())
    return summary


def arr_del15_consistency(labels: pd.DataFrame) -> dict[str, Any]:
    """Compare BTS ArrDel15 with (ArrDelay >= 15) on completed flights; count missing values."""
    completed = completed_mask(labels)
    flag = _numeric(labels, "ArrDel15")
    delay = _numeric(labels, "ArrDelay")
    both = completed & ~np.isnan(flag) & ~np.isnan(delay)
    derived = (delay >= ARR_DEL15_THRESHOLD_MIN).astype("float64")
    mismatch = both & (flag != derived)
    return {
        "completed_rows": int(completed.sum()),
        "compared_rows": int(both.sum()),
        "mismatch_rows": int(mismatch.sum()),
        "completed_arr_del15_missing": int((completed & np.isnan(flag)).sum()),
        "completed_arr_delay_missing": int((completed & np.isnan(delay)).sum()),
    }


def conditional_level(alpha: float, p_disrupted: np.ndarray | float) -> np.ndarray:
    """Conditional quantile level for an unconditional alpha: alpha / (1 - p); NaN where alpha >= 1 - p (plan 3.3)."""
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1): {alpha}")
    p = np.asarray(p_disrupted, dtype="float64")
    if np.any((p < 0) | (p > 1)):
        raise ValueError("p_disrupted must be in [0, 1]")
    with np.errstate(divide="ignore", invalid="ignore"):
        level = alpha / (1.0 - p)
    return np.where(alpha < 1.0 - p, level, np.nan)


def unconditional_exceedance(p_disrupted: np.ndarray | float, conditional_exceedance: np.ndarray | float) -> np.ndarray:
    """P(delay > q) = p + (1 - p) * (1 - F(q)); a cancellation / diversion counts as an infinite delay (plan 3.3)."""
    p = np.asarray(p_disrupted, dtype="float64")
    exceed = np.asarray(conditional_exceedance, dtype="float64")
    return np.asarray(p + (1.0 - p) * exceed, dtype="float64")
