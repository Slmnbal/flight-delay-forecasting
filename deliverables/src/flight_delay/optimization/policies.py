"""Buffer policies, cells and output tables (``experiments/or-tampon-formulasyonu.md`` sections 3, 6, 7). No I/O.

Cell = route (Origin, Dest) x hour_block (local CRS departure, ``features.hour_block``) x season
(``features.season``), plan section 8. A cell gets ONE buffer per period and policy; it is computed from the
SCHEDULED flights of the cell (cancelled ones included: the schedule is known when the buffer is planned) and from
model / baseline quantiles only. No function that builds a buffer takes realised outcomes as an argument.

Cell distribution: the knots of the cell's flights are aggregated level by level (``aggregate_knots``): ``mean``
(default) is the quantile average (Vincentisation), ``median`` the coordinate-wise median; both keep the knots
ascending. This is not the mixture quantile of the cell (approximation A6: the mixture needs tails beyond 0.95).

Policies (buffer per row = buffer of the row's cell unless stated):
- ``none``: b = 0 (current schedule).
- ``b1``: B1 baseline empirical route x hour_block quantile at tau (training window, hierarchical back-off).
- ``plan``: locked plan model, cell aggregate, b = max(0, Q_c(tau)).
- ``plan_conformal``: b = max(0, Q_c(tau) + c_m(tau)), c_m = monthly rolling one-sided conformal offset of the plan
  model at level tau (window ``splits.conformal_calibration_window``, same as ``final_eval``); one value per cell and
  month.
- ``b1_conformal`` (fairness check): the same conformal step applied to B1.
- ``plan_flight`` (secondary): flight-level b = max(0, Q_i(tau)) without cell aggregation.
- ``t2`` (secondary, optional): T2 quantiles (weather at T - 2 h: NOT available when a schedule is planned).

Selection guard: the only free policy choice (the aggregator) is made by ``select_aggregator``, which refuses any row
on or after the final-test start (``splits.assert_no_final_test``).

Presentation rules (M2, plan section 7, red team M10): output tables never contain a carrier, tail-number or
flight-number column (``assert_no_forbidden_columns``). The carrier is used only inside ``cell_table`` to flag cells
where one carrier operates more than 90 % of the flights (the flag is a boolean; no carrier identity leaves the
function). Cells with n < 50 scheduled flights or with that flag get ``tampon_onerisi_dk = NaN`` (null).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.modeling import conformal as cf
from flight_delay.modeling import features as ft
from flight_delay.modeling import final_eval as fe
from flight_delay.modeling.splits import assert_no_final_test
from flight_delay.optimization import newsvendor as nv

__all__ = [
    "AGGREGATORS",
    "CELL_KEYS",
    "DEFAULT_AGGREGATOR",
    "FORBIDDEN_COLUMN_PARTS",
    "HOUR_BLOCK_LABELS",
    "POLICY_B1",
    "POLICY_B1_CONFORMAL",
    "POLICY_NONE",
    "POLICY_PLAN",
    "POLICY_PLAN_CONFORMAL",
    "POLICY_PLAN_FLIGHT",
    "POLICY_T2",
    "PUBLISH_MIN_N",
    "SEASON_LABELS",
    "SINGLE_CARRIER_SHARE_MAX",
    "Cells",
    "PolicyInputs",
    "aggregate_knots",
    "assert_no_forbidden_columns",
    "cell_mean",
    "cell_table",
    "flight_table",
    "level_key",
    "make_cells",
    "offset_vector",
    "policy_buffers",
    "rolling_offsets",
    "select_aggregator",
    "top_carrier_share",
]

CELL_KEYS = ("Origin", "Dest", "hour_block", "season")
HOUR_BLOCK_LABELS: tuple[str, ...] = tuple(
    f"{a:02d}-{b:02d}" for a, b in zip(ft.HOUR_BLOCK_EDGES[:-1], ft.HOUR_BLOCK_EDGES[1:], strict=True)
)
SEASON_LABELS: tuple[str, ...] = ("kis", "ilkbahar", "yaz", "sonbahar")  # features.season codes 0..3 (interface enum)
AGGREGATORS = ("mean", "median")
DEFAULT_AGGREGATOR = "mean"
PUBLISH_MIN_N = 50  # plan section 8 / interface: cells with fewer scheduled flights are not published
SINGLE_CARRIER_SHARE_MAX = 0.90  # red team M10: one carrier above this share -> the cell is carrier performance
FORBIDDEN_COLUMN_PARTS = ("airline", "carrier", "tail", "flight_number")

POLICY_NONE = "none"
POLICY_B1 = "b1"
POLICY_B1_CONFORMAL = "b1_conformal"
POLICY_PLAN = "plan"
POLICY_PLAN_CONFORMAL = "plan_conformal"
POLICY_PLAN_FLIGHT = "plan_flight"
POLICY_T2 = "t2"


def level_key(level: float) -> str:
    """'t080' for 0.80 (column / JSON key)."""
    return f"t{round(float(level) * 100):03d}"


@dataclass(frozen=True)
class Cells:
    """Cell code per row and one key row per cell (sorted by Origin, Dest, hour_block, season)."""

    codes: np.ndarray
    keys: pd.DataFrame

    @property
    def n_cells(self) -> int:
        return len(self.keys)

    def counts(self) -> np.ndarray:
        return np.bincount(self.codes, minlength=self.n_cells).astype("float64")


def make_cells(origin: Any, dest: Any, local_minutes: Any, dates: Any) -> Cells:
    months = pd.to_datetime(pd.Series(np.asarray(dates).ravel())).dt.month.to_numpy()
    frame = pd.DataFrame(
        {
            "Origin": np.asarray(origin).astype(str),
            "Dest": np.asarray(dest).astype(str),
            "hour_block": ft.hour_block(local_minutes).astype("int64"),
            "season": ft.season(months).astype("int64"),
        }
    )
    grouped = frame.groupby(list(CELL_KEYS), sort=True, dropna=False)
    codes = np.asarray(grouped.ngroup().to_numpy(), dtype="int64")
    keys = grouped.size().reset_index()[list(CELL_KEYS)]
    return Cells(codes=codes, keys=keys)


def aggregate_knots(knots: Any, codes: Any, n_cells: int, how: str = DEFAULT_AGGREGATOR) -> np.ndarray:
    """(n_cells, k) cell knots from row knots (ascending rows); 'mean' or 'median' per level."""
    q = nv.monotone_knots(knots)
    c = np.asarray(codes, dtype="int64").ravel()
    if c.shape != (q.shape[0],):
        raise ValueError("codes and knots differ in length")
    counts = np.bincount(c, minlength=n_cells)
    if np.any(counts == 0):
        raise ValueError("Every cell needs at least one row")
    if how == "mean":
        out = np.column_stack([np.bincount(c, weights=q[:, j], minlength=n_cells) for j in range(q.shape[1])])
        out = out / counts[:, None]
    elif how == "median":
        out = pd.DataFrame(q).groupby(c, sort=True).median().reindex(range(n_cells)).to_numpy(dtype="float64")
    else:
        raise ValueError(f"aggregator must be one of {AGGREGATORS}: {how!r}")
    return np.sort(out, axis=1)


def rolling_offsets(
    y: Any, knots: Any, dates: Any, eval_months: Sequence[Any], levels: Sequence[float]
) -> dict[float, dict[str, dict[str, Any]]]:
    """{level: {'YYYY-MM': record}}: monthly rolling one-sided conformal offsets of Q(level) (``final_eval``)."""
    values = np.asarray(y, dtype="float64").ravel()
    q = nv.monotone_knots(knots)
    days = np.asarray(dates).ravel()
    if values.shape != (q.shape[0],) or days.shape != values.shape:
        raise ValueError("y, knots and dates differ in length")
    universe = np.isfinite(values)
    static = np.zeros(int(universe.sum()), dtype=bool)  # only the rolling scheme is used here
    out: dict[float, dict[str, dict[str, Any]]] = {}
    for level in levels:
        bound = nv.interpolate_quantile(q[universe], level)
        scores = cf.one_sided_scores(values[universe], bound)
        table = fe.conformal_offsets(scores, days[universe], static, list(eval_months), float(level))
        out[float(level)] = table[fe.PRIMARY_SCHEME]
    return out


def offset_vector(month: Any, records: Mapping[str, Mapping[str, Any]]) -> np.ndarray:
    """Offset per row from its month (``final_eval._offset_vector``); non-finite offsets are refused."""
    vector = fe._offset_vector(np.asarray(month).astype(str), records)
    if not np.all(np.isfinite(vector)):
        raise ValueError("A conformal offset is +inf (too few calibration rows): the conformal policy is undefined")
    return vector


@dataclass(frozen=True)
class PolicyInputs:
    """Evaluation rows of one period: cells, month label, ascending knots and conformal offsets. No outcomes."""

    cells: Cells
    month: np.ndarray
    plan_knots: np.ndarray
    b1_knots: np.ndarray
    plan_offsets: Mapping[float, Mapping[str, Mapping[str, Any]]] | None = None
    b1_offsets: Mapping[float, Mapping[str, Mapping[str, Any]]] | None = None
    t2_knots: np.ndarray | None = None

    def cell_knots(self, aggregator: str) -> dict[str, np.ndarray]:
        n = self.cells.n_cells
        out = {
            POLICY_PLAN: aggregate_knots(self.plan_knots, self.cells.codes, n, aggregator),
            POLICY_B1: aggregate_knots(self.b1_knots, self.cells.codes, n, aggregator),
        }
        if self.t2_knots is not None:
            out[POLICY_T2] = aggregate_knots(self.t2_knots, self.cells.codes, n, aggregator)
        return out


def policy_buffers(
    inputs: PolicyInputs,
    level: float,
    aggregator: str = DEFAULT_AGGREGATOR,
    *,
    cell_knots: Mapping[str, np.ndarray] | None = None,
    policies: Sequence[str] | None = None,
) -> dict[str, np.ndarray]:
    """Buffer (minutes, >= 0) per evaluation row for every policy of the module docstring at critical ratio ``level``."""
    nv.check_level(level)
    knots = dict(cell_knots) if cell_knots is not None else inputs.cell_knots(aggregator)
    codes = inputs.cells.codes
    wanted = set(policies) if policies is not None else None

    def want(name: str) -> bool:
        return wanted is None or name in wanted

    plan_q = nv.interpolate_quantile(knots[POLICY_PLAN], level)[codes]
    b1_q = nv.interpolate_quantile(knots[POLICY_B1], level)[codes]
    out: dict[str, np.ndarray] = {}
    if want(POLICY_NONE):
        out[POLICY_NONE] = np.zeros(codes.size)
    if want(POLICY_B1):
        out[POLICY_B1] = np.maximum(0.0, b1_q)
    if want(POLICY_PLAN):
        out[POLICY_PLAN] = np.maximum(0.0, plan_q)
    if want(POLICY_PLAN_CONFORMAL) and inputs.plan_offsets is not None:
        offsets = offset_vector(inputs.month, inputs.plan_offsets[float(level)])
        out[POLICY_PLAN_CONFORMAL] = np.maximum(0.0, plan_q + offsets)
    if want(POLICY_B1_CONFORMAL) and inputs.b1_offsets is not None:
        offsets = offset_vector(inputs.month, inputs.b1_offsets[float(level)])
        out[POLICY_B1_CONFORMAL] = np.maximum(0.0, b1_q + offsets)
    if want(POLICY_PLAN_FLIGHT):
        out[POLICY_PLAN_FLIGHT] = nv.newsvendor_buffer(inputs.plan_knots, level)
    if want(POLICY_T2) and POLICY_T2 in knots:
        out[POLICY_T2] = np.maximum(0.0, nv.interpolate_quantile(knots[POLICY_T2], level)[codes])
    return out


def select_aggregator(
    dates: Any,
    delay: Any,
    inputs: PolicyInputs,
    levels: Sequence[float],
    candidates: Sequence[str] = AGGREGATORS,
) -> tuple[str, dict[str, Any]]:
    """Development-only choice of the cell aggregator: lowest mean realised cost of the ``plan`` policy averaged over
    ``levels`` (ties -> ``DEFAULT_AGGREGATOR``). Refuses any final-test row (FinalTestAccessError)."""
    assert_no_final_test(pd.Series(np.asarray(dates).ravel()))
    values = np.asarray(delay, dtype="float64").ravel()
    if values.shape != inputs.cells.codes.shape:
        raise ValueError("delay and the policy rows differ in length")
    completed = np.isfinite(values)
    table: dict[str, Any] = {}
    for how in candidates:
        knots = inputs.cell_knots(how)
        per_level = {}
        for level in levels:
            buffer = policy_buffers(inputs, level, how, cell_knots=knots, policies=(POLICY_PLAN,))[POLICY_PLAN]
            outcome = nv.realized_outcomes(values[completed], buffer[completed])
            cost = nv.realized_cost(outcome["residual"], outcome["unused"], level)
            per_level[level_key(level)] = float(np.mean(cost))
        overall = float(np.mean(list(per_level.values())))
        table[how] = {"cost_mean_by_level": per_level, "cost_mean_over_levels": overall}
    best = min(
        candidates, key=lambda h: (round(table[h]["cost_mean_over_levels"], 12), 0 if h == DEFAULT_AGGREGATOR else 1)
    )
    return best, {
        "rule": "lowest mean realised plan-policy cost over the level grid on development rows only; ties -> mean",
        "candidates": table,
        "chosen": best,
        "rows_completed": int(completed.sum()),
    }


def assert_no_forbidden_columns(frame: pd.DataFrame) -> None:
    """No carrier / tail-number / flight-number column in an output table (presentation rules)."""
    bad = [str(c) for c in frame.columns if any(part in str(c).lower() for part in FORBIDDEN_COLUMN_PARTS)]
    if bad:
        raise ValueError(f"Output table contains forbidden column(s): {bad}")


def _group_median(values: np.ndarray, codes: np.ndarray, n_cells: int) -> np.ndarray:
    series = pd.Series(values).groupby(codes, sort=True).median()
    return np.asarray(series.reindex(range(n_cells)).to_numpy(dtype="float64"))


def _group_mean(values: np.ndarray, codes: np.ndarray, n_cells: int, mask: np.ndarray | None = None) -> np.ndarray:
    use = np.ones(values.size, dtype=bool) if mask is None else mask
    sums = np.bincount(codes[use], weights=values[use], minlength=n_cells)
    counts = np.bincount(codes[use], minlength=n_cells).astype("float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.asarray(np.where(counts > 0, sums / counts, np.nan))


def top_carrier_share(codes: np.ndarray, carrier: Any, n_cells: int) -> np.ndarray:
    """Share of the most frequent carrier per cell (only the share leaves this function)."""
    frame = pd.DataFrame({"cell": codes, "carrier": pd.Series(np.asarray(carrier).ravel()).astype(str)})
    per = frame.groupby(["cell", "carrier"], sort=False).size()
    top = per.groupby(level=0).max().reindex(range(n_cells)).to_numpy(dtype="float64")
    return np.asarray(top / np.bincount(codes, minlength=n_cells))


def cell_table(
    *,
    cells: Cells,
    carrier: Any,
    delay: Any,
    cancelled: Any,
    diverted: Any,
    crs_elapsed: Any,
    cell_knots: Mapping[str, np.ndarray],
    buffer_columns: Mapping[str, np.ndarray],
    recommendation: np.ndarray,
    recommendation_source: str,
    p_cancel: Any | None = None,
    min_n: int = PUBLISH_MIN_N,
    carrier_share_max: float = SINGLE_CARRIER_SHARE_MAX,
    digits: int = 1,
) -> pd.DataFrame:
    """One row per cell (source of the interface field ``tampon_onerisi_dk``). No carrier column.

    ``buffer_columns``: column name -> one value per cell (``cell_mean`` of a policy's row buffers);
    ``recommendation``: one value per cell of the publication policy (``recommendation_source`` names it).
    """
    codes, n = cells.codes, cells.n_cells
    d = np.asarray(delay, dtype="float64").ravel()
    completed = np.isfinite(d)
    counts = cells.counts()
    is_cancelled = (np.asarray(cancelled, dtype="float64").ravel() == 1).astype("float64")
    is_diverted = (np.asarray(diverted, dtype="float64").ravel() == 1).astype("float64")
    hours = [int(h) for h in cells.keys["hour_block"]]
    late_before = (d >= nv.ARR_DEL15_MIN).astype("float64")
    table = pd.DataFrame(
        {
            "origin": cells.keys["Origin"].astype(str).to_numpy(),
            "dest": cells.keys["Dest"].astype(str).to_numpy(),
            "saat_blogu": [HOUR_BLOCK_LABELS[h] if 0 <= h < len(HOUR_BLOCK_LABELS) else None for h in hours],
            "mevsim": [SEASON_LABELS[int(s)] for s in cells.keys["season"]],
            "n_ucus": counts.astype("int64"),
            "n_tamamlanan": np.bincount(codes[completed], minlength=n).astype("int64"),
            "n_iptal": np.bincount(codes, weights=is_cancelled, minlength=n).astype("int64"),
            "n_sapma": np.bincount(codes, weights=is_diverted, minlength=n).astype("int64"),
            "crs_elapsed_medyan_dk": _group_median(np.asarray(crs_elapsed, dtype="float64"), codes, n),
            "gozlenen_arrdel15_tamponsuz": _group_mean(late_before, codes, n, completed),
        }
    )
    for name, knots in cell_knots.items():
        for j, level in enumerate(nv.KNOT_LEVELS):
            table[f"{name}_q{round(level * 100):03d}_dk"] = knots[:, j]
    for name, values in buffer_columns.items():
        column = np.asarray(values, dtype="float64").ravel()
        if column.shape != (n,):
            raise ValueError(f"{name}: one value per cell is required")
        table[name] = column
    if p_cancel is not None:
        table["p_iptal_model_ortalama"] = _group_mean(np.asarray(p_cancel, dtype="float64"), codes, n)
    single = top_carrier_share(codes, carrier, n) > carrier_share_max
    table["tek_tasiyici_yogun"] = single
    table["yayimlanabilir"] = (counts >= min_n) & ~single
    proposed = np.round(np.asarray(recommendation, dtype="float64").ravel(), digits)
    if proposed.shape != (n,):
        raise ValueError("recommendation: one value per cell is required")
    table["tampon_onerisi_dk"] = np.where(table["yayimlanabilir"].to_numpy(), proposed, np.nan)
    table["tampon_onerisi_kaynak"] = recommendation_source
    assert_no_forbidden_columns(table)
    return table


def cell_mean(values: Any, cells: Cells) -> np.ndarray:
    """Mean of a per-row quantity per cell (all scheduled rows of the cell)."""
    return _group_mean(np.asarray(values, dtype="float64").ravel(), cells.codes, cells.n_cells)


def flight_table(columns: Mapping[str, Any]) -> pd.DataFrame:
    """Flight-level output (local only): explicit columns, equal lengths, no forbidden column."""
    lengths = {name: len(np.asarray(values).ravel()) for name, values in columns.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"Columns differ in length: {lengths}")
    frame = pd.DataFrame({name: np.asarray(values).ravel() for name, values in columns.items()})
    assert_no_forbidden_columns(frame)
    return frame
