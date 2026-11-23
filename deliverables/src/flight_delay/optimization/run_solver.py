"""Solver extension of the buffer run (formulation: ``experiments/or-tampon-formulasyonu.md`` section 17).

EXPLORATORY: the final-test period was already seen for these policies in the first OR run
(``experiments/or/tampon-20261122T173803Z``). Every output of this module carries the label
``keşifsel (post hoc), son test sonucu değildir`` (first line of the summary, first key of the JSON).

Usage (from the project root ``projects/havayolu-ds/``):
    python -m flight_delay.optimization.run_solver --dry-run            # checks + plan only; nothing read or written
    python -m flight_delay.optimization.run_solver                      # development, freeze, final test (post hoc)
    python -m flight_delay.optimization.run_solver --development-only   # development + freeze only

What it adds to ``run_buffer`` (whose default behaviour is unchanged):
1. Minutes LP with Pyomo + HiGHS (``pyomo_models.MinutesLP``), cross-checked against the closed form
   ``allocation.common_level_allocation`` for every budget (objective certificate, buffers, constraint violations).
2. ArrDel15 knapsack as a MILP with Pyomo + HiGHS (time limit, MIP gap), compared with the hull greedy and its LP
   bound.
3. Mixture cell distribution (``mixture``) for the knapsack candidates. Vincentised vs mixture is chosen ONLY on the
   development months 2025-11 .. 2026-02 (``select_cell_distribution``) and frozen before the final test is read.
4. Figures (``plots``) in ``experiments/or/cozucu-<UTC>/grafikler/``.

Order (fail closed): preflight (no data) -> locked models, fit window, development reproduction (as ``run_buffer``)
-> aggregator re-selected and compared with the first run's freeze -> development evaluation and distribution
choice -> ``cozucu-dondurma.json`` written with exclusive create -> final test read (``require_lock_written``) and
evaluated -> results, summary, figures. New folder per run; nothing is overwritten; no Parquet is written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import importlib
import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.layer import DEFAULT_LAYER_DIR
from flight_delay.mlops import reproducibility as repro
from flight_delay.modeling import bootstrap as bs
from flight_delay.modeling import features as ft
from flight_delay.modeling import final_eval as fe
from flight_delay.modeling import final_lock as fl
from flight_delay.modeling import run_final_test as rft
from flight_delay.modeling import run_models as rm
from flight_delay.modeling import run_permutation as rp
from flight_delay.modeling.loading import fingerprint, load_periods
from flight_delay.modeling.matrix import (
    HISTORY_INPUT_COLUMNS,
    MODEL_FLIGHT_COLUMNS,
    MODEL_LABEL_COLUMNS,
    LayerTableReader,
)
from flight_delay.modeling.run_baselines import _format, _jsonable
from flight_delay.modeling.splits import (
    FINAL_TEST,
    FINAL_TEST_LOCK_FILE,
    SPLIT_DATE_COLUMN,
    VAL_A,
    VAL_B,
    assert_no_final_test,
    conformal_calibration_window,
    require_lock_written,
)
from flight_delay.optimization import allocation as al
from flight_delay.optimization import evaluation as ev
from flight_delay.optimization import mixture as mx
from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization import plots as pl
from flight_delay.optimization import policies as pol
from flight_delay.optimization import pyomo_models as pm
from flight_delay.optimization import run_buffer as rb
from flight_delay.paths import PROJECT_ROOT

__all__ = [
    "DISTRIBUTIONS",
    "EXPLORATORY_LABEL",
    "KNAPSACK_POLICY",
    "SolverConfig",
    "absolute_ci",
    "main",
    "make_plots",
    "preflight",
    "render",
    "reproduction_vs_first_run",
    "run",
    "select_cell_distribution",
    "solver_budget_curve",
]

LOG = logging.getLogger("flight_delay.optimization.run_solver")
COMMAND = "python -m flight_delay.optimization.run_solver"
EXPLORATORY_LABEL = "keşifsel (post hoc), son test sonucu değildir"
FIRST_RUN_DIR = rb.OUTPUT_DIR / "tampon-20261122T173803Z"  # first OR run (read only: provenance and reproduction)
FOLDER_PREFIX = "cozucu"
FREEZE_FILE = "cozucu-dondurma.json"
RESULTS_FILE = "cozucu-sonuclari.json"
SUMMARY_FILE = "cozucu-ozet.md"
PLOTS_DIR = "grafikler"
DISTRIBUTIONS = ("vincentize", "mixture")
DEFAULT_DISTRIBUTION = "vincentize"  # incumbent (first run); wins ties
KNAPSACK_POLICY = {"vincentize": "plan_arrdel15_budget", "mixture": "plan_arrdel15_mixture"}
POLICY_LABELS = {
    "plan_budget": "Plan, ortak düzey (dakika hedefi)",
    "b1_budget": "B1, ortak düzey (dakika hedefi)",
    "plan_arrdel15_budget": "Sırt çantası, Vincentize hücre",
    "plan_arrdel15_mixture": "Sırt çantası, karışım hücre",
    pol.POLICY_NONE: "Ek tampon yok",
    pol.POLICY_B1: "B1 hücre kantili",
    pol.POLICY_PLAN: "Plan (ham)",
    pol.POLICY_PLAN_CONFORMAL: "Plan + kayan conformal",
    pol.POLICY_B1_CONFORMAL: "B1 + kayan conformal",
    pol.POLICY_PLAN_FLIGHT: "Plan, uçuş düzeyi",
}
PERIOD_TITLES = {
    "dogrulama": "Geliştirme (2025-11..2026-02)",
    "test": "Son test dönemi (2026-03..2026-08), keşifsel (post hoc)",
}


@dataclass(frozen=True)
class SolverConfig:
    """Everything fixed before the final test is read (recorded in the freeze file)."""

    levels: tuple[float, ...] = nv.DEFAULT_LEVEL_GRID
    budgets_per_flight: tuple[float, ...] = ev.DEFAULT_BUDGETS_PER_FLIGHT
    replicates: int = bs.DEFAULT_REPLICATES
    seed: int = bs.DEFAULT_SEED
    ci_level: float = bs.CI_LEVEL
    solver: str = "highs"
    lp: bool = True
    lp_formulation: str = "segments"
    lp_max_segment_min: float = 2.0
    lp_time_limit_s: float = 600.0
    milp: bool = True
    milp_time_limit_s: float = 120.0
    milp_rel_gap: float = 1e-6
    milp_min_n: int = 0  # 0 = every cell in the MILP; > 0: cells with fewer flights fixed at the greedy choice
    mixture_cells: bool = True
    mixture_candidate_levels: tuple[float, ...] = mx.DEFAULT_CANDIDATE_LEVELS
    selection_tie_arrdel15: float = 1e-4
    plots: bool = True
    development_only: bool = False
    hash_files: bool = True

    def validate(self) -> list[str]:
        problems = self.buffer_config().validate()
        if self.solver != "highs":
            problems.append("solver must be 'highs' (Pyomo appsi_highs)")
        if self.lp_formulation not in pm.FORMULATIONS:
            problems.append(f"lp_formulation must be one of {pm.FORMULATIONS}")
        if not self.lp_max_segment_min > 0:
            problems.append("lp_max_segment_min must be > 0")
        if not (self.lp_time_limit_s > 0 and self.milp_time_limit_s > 0):
            problems.append("time limits must be > 0 s")
        if not 0 <= self.milp_rel_gap < 1:
            problems.append("milp_rel_gap must be in [0, 1)")
        if self.milp_min_n < 0:
            problems.append("milp_min_n must be >= 0")
        try:
            levels = [nv.check_level(a) for a in self.mixture_candidate_levels]
            if levels != sorted(set(levels)):
                problems.append("mixture_candidate_levels must be strictly increasing")
        except nv.GridError as error:
            problems.append(str(error))
        if self.selection_tie_arrdel15 < 0:
            problems.append("selection_tie_arrdel15 must be >= 0")
        return problems

    def buffer_config(self) -> rb.BufferConfig:
        """The ``run_buffer`` settings of the shared steps (levels, budgets, bootstrap); publication is unused here."""
        publish = 0.80 if 0.80 in [float(x) for x in self.levels] else float(self.levels[0])
        return rb.BufferConfig(
            levels=self.levels,
            budgets_per_flight=self.budgets_per_flight,
            publish_level=publish,
            replicates=self.replicates,
            seed=self.seed,
            ci_level=self.ci_level,
            development_only=self.development_only,
            flight_file=False,
            hash_files=self.hash_files,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------
# preflight (no data read)
# ----------------------------------------------------------------------------


def _module_found(name: str) -> bool:
    util = importlib.import_module("importlib.util")
    return util.find_spec(name) is not None


def preflight(
    manifest_path: Path,
    *,
    config: SolverConfig,
    lock_file: Path,
    base: Path,
    output_dir: Path,
    first_run_dir: Path,
    stamp: str,
) -> dict[str, Any]:
    """``run_buffer.preflight`` checks plus this run's own: folder, optional packages, first-run files."""
    problems = config.validate()
    try:
        plan = rb.preflight(
            manifest_path,
            config=config.buffer_config(),
            lock_file=lock_file,
            base=base,
            output_dir=output_dir,
            data_output_dir=rb.DATA_OUTPUT_DIR,
            stamp=stamp,
        )
    except fl.LockVerificationError as error:
        problems.append(str(error))
        plan = {}
    folder = output_dir / f"{FOLDER_PREFIX}-{stamp}"
    if folder.exists():
        problems.append(f"output folder exists, will not overwrite: {folder}")
    if (config.lp or config.milp) and not pm.pyomo_available():
        problems.append("pyomo / highspy not found (needed for --lp / --milp; proposed extra 'optimization')")
    if config.plots and not _module_found("matplotlib"):
        problems.append("matplotlib not found (needed for --plots)")
    first_run: dict[str, Any] = {"folder": str(first_run_dir)}
    for name in (rb.FREEZE_FILE, rb.RESULTS_FILE):
        path = first_run_dir / name
        if path.is_file():
            first_run[name] = {"path": fl._relative(path, base), "sha256": fl.sha256_file(path)}
        else:
            problems.append(f"first-run file missing: {path}")
    if problems:
        raise fl.LockVerificationError("Solver run refused (nothing read, nothing written): " + "; ".join(problems))
    return {
        **{k: v for k, v in plan.items() if not k.startswith("_") and k != "outputs" and k != "config"},
        "_manifest": plan["_manifest"],
        "outputs": {"folder": str(folder)},
        "first_run": first_run,
        "config": config.to_dict(),
        "_folder": folder,
    }


# ----------------------------------------------------------------------------
# knapsack candidates and the extended budget curve
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class KnapsackCandidates:
    buffers: np.ndarray  # (cells, candidates)
    late: np.ndarray  # model P(D - b >= 15) per candidate
    censored_at_zero: np.ndarray  # share of censored flights (mixture) or cell flag (Vincentised) at b = 0
    info: dict[str, Any]


def knapsack_candidates(
    flight_knots: np.ndarray, cells: pol.Cells, plan_cell_knots: np.ndarray, config: SolverConfig
) -> dict[str, KnapsackCandidates]:
    """Candidates per cell distribution: Vincentised (knots, as the first run) and, if enabled, the mixture."""
    buffers, late, censored = al.arrdel15_candidates(plan_cell_knots)
    out = {
        "vincentize": KnapsackCandidates(
            buffers,
            late,
            censored.astype("float64"),
            {"candidates_per_cell": int(buffers.shape[1]), "cells_censored_at_zero_buffer": int(censored.sum())},
        )
    }
    if config.mixture_cells:
        started = time.perf_counter()
        mixture = mx.mixture_arrdel15_candidates(
            flight_knots, cells.codes, cells.n_cells, candidate_levels=config.mixture_candidate_levels
        )
        info = mixture.describe() | {"seconds": round(time.perf_counter() - started, 1)}
        out["mixture"] = KnapsackCandidates(mixture.buffers, mixture.late, mixture.censored_share[:, 0], info)
    return out


def absolute_ci(design: ev.DayDesign, values: Any, ci_level: float = bs.CI_LEVEL) -> dict[str, Any]:
    """Day-block bootstrap interval of the mean of one per-completed-row quantity (same multiplicities)."""
    means = bs.DayMeans(values, design.codes, design.n_days)
    return bs.summarize_draws(means(None), means.replicates(design.multiplicities), level=ci_level).to_dict()


def _ratio(level: float | None) -> float | None:
    return None if level is None or level >= 1.0 else nv.implied_cost_ratio(level)


def solver_budget_curve(
    design: ev.DayDesign,
    cells: pol.Cells,
    cell_knots: Mapping[str, np.ndarray],
    candidates: Mapping[str, KnapsackCandidates],
    config: SolverConfig,
    *,
    label: str = "",
) -> dict[str, Any]:
    """Equal-budget comparison with the solver checks (module docstring 1-3). ``cell_knots`` needs 'plan', 'b1'."""
    counts = cells.counts()
    scheduled = float(counts.sum())
    rows = np.arange(cells.n_cells)
    started = time.perf_counter()
    lp_model: pm.MinutesLP | None = None
    out: dict[str, Any] = {}
    if config.lp:
        lp_model = pm.MinutesLP(
            cell_knots["plan"], counts, formulation=config.lp_formulation, max_segment_min=config.lp_max_segment_min
        )
        out["lp_model"] = {
            "sizes": lp_model.sizes,
            "segments": lp_model.segments.describe(),
            "build_seconds": round(lp_model.build_seconds, 1),
            "chord_error_bound": lp_model.chord_error_bound(),
            "peak_rss_gb_after_build": rm._peak_rss_gb(),
        }
        LOG.info("%s: LP built %s (%.0f s)", label, lp_model.sizes, lp_model.build_seconds)
    milp_solver = pm.make_solver() if config.milp else None
    curve: dict[str, Any] = {}
    for beta in config.budgets_per_flight:
        budget = float(beta) * scheduled
        plan = al.common_level_allocation(cell_knots["plan"], counts, budget)
        b1 = al.common_level_allocation(cell_knots["b1"], counts, budget)
        buffers: dict[str, np.ndarray] = {}
        allocations: dict[str, Any] = {}
        expected: dict[str, dict[str, float]] = {}
        for name, solution in (("plan_budget", plan), ("b1_budget", b1)):
            allocations[name] = solution.to_dict() | {"implied_c_u_over_c_o": _ratio(solution.level)}
            if solution.status != "below_grid":
                buffers[name] = solution.buffers[cells.codes]
        if lp_model is not None:
            lp = lp_model.solve(budget, time_limit=config.lp_time_limit_s)
            check = pm.compare_minutes(lp, plan, cell_knots["plan"], counts, lp_model.segments)
            allocations["plan_budget"]["lp_cross_check"] = check | {"lp": lp.to_dict()}
            if not check.get("agrees"):
                LOG.warning("%s: LP vs closed form disagree at %g min/flight: %s", label, beta, check)
        for distribution, cand in candidates.items():
            policy = KNAPSACK_POLICY[distribution]
            cost, value = counts[:, None] * cand.buffers, counts[:, None] * cand.late
            greedy = al.mckp_greedy(cost, value, budget)
            chosen = cand.buffers[rows, greedy.choice]
            buffers[policy] = chosen[cells.codes]
            late_cell = cand.late[rows, greedy.choice]
            expected[policy] = {
                "expected_rate_completed_rows": float(np.mean(late_cell[cells.codes][design.completed])),
                "expected_rate_scheduled": float(greedy.value / scheduled),
            }
            entry: dict[str, Any] = greedy.to_dict() | {
                "distribution": distribution,
                "cells_censored_at_zero_buffer": int(np.sum(cand.censored_at_zero > 0)),
            }
            if milp_solver is not None:
                active = counts >= config.milp_min_n if config.milp_min_n > 0 else None
                milp = pm.solve_arrdel15_milp(
                    cand.buffers,
                    cand.late,
                    counts,
                    budget,
                    time_limit=config.milp_time_limit_s,
                    mip_rel_gap=config.milp_rel_gap,
                    active=active,
                    fixed_choice=greedy.choice,
                    solver=milp_solver,
                )
                record = milp.to_dict()
                if milp.choice is not None and milp.value is not None:
                    milp_buffers = cand.buffers[rows, milp.choice]
                    differ = int(np.sum(np.abs(milp_buffers - chosen) > 1e-9))
                    record |= {
                        "value_minus_greedy": milp.value - greedy.value,
                        "value_minus_lp_bound": milp.value - greedy.lp_value,
                        "cells_with_different_buffer": differ,
                    }
                    if milp.valid and differ:
                        buffers[f"{policy}_milp"] = milp_buffers[cells.codes]
                entry["milp"] = record
            allocations[policy] = entry
        comparisons = [(p, "b1_budget") for p in buffers if p != "b1_budget"]
        comparisons.append((KNAPSACK_POLICY["mixture"], KNAPSACK_POLICY["vincentize"]))
        scored = ev.score_policies(
            design, buffers, level=None, comparisons=comparisons, ci_level=config.ci_level, monthly=False
        )
        intervals: dict[str, Any] = {}
        for name, values in buffers.items():
            outcome = nv.realized_outcomes(design.delay, values[design.completed])
            intervals[name] = {
                "arr_del15_rate": absolute_ci(design, outcome["late15"], config.ci_level),
                "residual_mean_min": absolute_ci(design, outcome["residual"], config.ci_level),
            }
        for policy, record_expected in expected.items():
            realized = scored["policies"][policy]["arr_del15_rate"]
            record_expected["realized_rate"] = realized
            record_expected["gap_realized_minus_expected"] = realized - record_expected["expected_rate_completed_rows"]
        curve[f"b{beta:g}"] = {
            "budget_per_flight_min": float(beta),
            "budget_total_min": budget,
            "allocations": allocations,
            "absolute_ci": intervals,
            "expected_vs_realized": expected,
            **scored,
        }
        LOG.info("%s: solver budget %g min/flight done (%.0f s)", label, beta, time.perf_counter() - started)
        del buffers
    out["curve"] = curve
    out["seconds"] = round(time.perf_counter() - started, 1)
    return out


# ----------------------------------------------------------------------------
# development-only choice of the cell distribution
# ----------------------------------------------------------------------------


def select_cell_distribution(period: Mapping[str, Any], *, tie: float = 1e-4) -> tuple[str, dict[str, Any]]:
    """Vincentised vs mixture for the knapsack, from DEVELOPMENT results only (refuses final-test days).

    Rule (lexicographic, frozen before the final test): (1) lower mean realised ArrDel15 over the budget grid if
    the difference exceeds ``tie``; (2) otherwise lower mean |realised - expected|; (3) otherwise Vincentised.
    """
    design = period["design"]
    assert_no_final_test(pd.Series([design["first_day"], design["last_day"]]))
    curve = period["solver"]["curve"]
    stats: dict[str, dict[str, float]] = {}
    for distribution, policy in KNAPSACK_POLICY.items():
        entries = [e for e in curve.values() if policy in e["expected_vs_realized"]]
        if not entries:
            continue
        realized = [float(e["expected_vs_realized"][policy]["realized_rate"]) for e in entries]
        gaps = [abs(float(e["expected_vs_realized"][policy]["gap_realized_minus_expected"])) for e in entries]
        stats[distribution] = {
            "realized_arr_del15_mean": float(np.mean(realized)),
            "abs_gap_mean": float(np.mean(gaps)),
            "budgets": float(len(entries)),
        }
    rule = (
        f"development only; (1) lower mean realised ArrDel15 over budgets if |difference| > {tie:g}; "
        "(2) lower mean |realised - expected|; (3) vincentize"
    )
    if not stats:
        raise ValueError("no knapsack result in the development period")
    if len(stats) == 1:
        chosen, reason = next(iter(stats)), "only one distribution evaluated"
    else:
        v, m = stats["vincentize"], stats["mixture"]
        difference = m["realized_arr_del15_mean"] - v["realized_arr_del15_mean"]
        if abs(difference) > tie:
            chosen, reason = ("mixture" if difference < 0 else "vincentize"), "realised ArrDel15"
        elif abs(m["abs_gap_mean"] - v["abs_gap_mean"]) > 1e-12:
            chosen = "mixture" if m["abs_gap_mean"] < v["abs_gap_mean"] else "vincentize"
            reason = "expected vs realised gap (realised ArrDel15 tied)"
        else:
            chosen, reason = DEFAULT_DISTRIBUTION, "tie"
    return chosen, {"rule": rule, "candidates": stats, "chosen": chosen, "reason": reason}


# ----------------------------------------------------------------------------
# reproduction of the first run (information, not a gate)
# ----------------------------------------------------------------------------

_REPRO_METRICS = ("buffer_planned_mean_min", "residual_mean_min", "arr_del15_rate", "cost_mean")


def reproduction_vs_first_run(new: Mapping[str, Any], old: Mapping[str, Any] | None) -> dict[str, Any]:
    """Largest absolute difference of the shared policy metrics (levels and budget curve) of one period."""
    if not old:
        return {"checked": False, "reason": "period not in the first run"}
    diffs: dict[str, float] = {}
    for block in ("levels", "budget_curve"):
        for key, entry in (new.get(block) or {}).items():
            previous = ((old.get(block) or {}).get(key) or {}).get("policies") or {}
            for policy, row in (entry.get("policies") or {}).items():
                for metric in _REPRO_METRICS:
                    a, b = row.get(metric), (previous.get(policy) or {}).get(metric)
                    if a is not None and b is not None:
                        diffs[f"{block}:{key}:{policy}:{metric}"] = abs(float(a) - float(b))
    largest = sorted(diffs.items(), key=lambda item: -item[1])[:5]
    return {
        "checked": bool(diffs),
        "compared": len(diffs),
        "max_abs_diff": max(diffs.values()) if diffs else None,
        "largest": dict(largest),
    }


# ----------------------------------------------------------------------------
# data steps (same building blocks and order as run_buffer.run)
# ----------------------------------------------------------------------------


@dataclass
class Prepared:
    loaded: dict[str, Any]
    fit: Any
    history: Any
    b1_rate_tables: Any
    b1_quantile_table: Any
    dev_arrays: dict[str, Any]
    dev_rows: dict[str, Any]
    dev_months: list[dt.date]
    dev_offsets: dict[str, Any]
    reproduction: Any
    cancel_calibrator: Any
    files: list[Any]


def _prepare(manifest: fl.Manifest, cfg: SolverConfig, layer_root: Path | None, base: Path, clock: Any) -> Prepared:
    """Locked models, fit window, development predictions and reproduction checks (``run_buffer.run`` steps)."""
    bcfg = cfg.buffer_config()
    loaded = rft._load_entries(manifest, base, rb._roles(bcfg))
    problems = rft._check_boosters(loaded)
    if problems:
        raise fl.LockVerificationError("Solver run refused: " + "; ".join(problems))
    settings = rft._settings(loaded)
    fit = settings["fit"]
    clock.lap("manifest_and_models")
    loaded_train = load_periods(
        layer_root,
        [fit],
        flight_columns=rp._TRAIN_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=cfg.hash_files,
    )
    train = rm._slice(loaded_train.frame, fit)
    loaded_train.frame = pd.DataFrame()
    history = ft.HistoryFeatures(m=settings["m"], min_support=settings["min_support"], min_tail=settings["min_tail"])
    history.fit(train[list(HISTORY_INPUT_COLUMNS)], fit_end=fit.end)
    described = _jsonable(history.describe())
    mismatches = [
        f"{role}: {'; '.join(found[:5])}"
        for role, item in loaded.items()
        if (found := rp.history_mismatches(item.spec["history"], described))
    ]
    if mismatches:
        raise fl.LockVerificationError("Refitted history differs from the locked runs: " + " | ".join(mismatches))
    b1_rate_tables, b1_quantile_table = rft._b1_tables(train, fit.end, settings)
    del train
    gc.collect()
    clock.lap("fit_window")
    loaded_dev = load_periods(
        layer_root,
        [VAL_A, VAL_B],
        flight_columns=MODEL_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=cfg.hash_files,
    )
    dev = rm._slice(loaded_dev.frame, rb.DEVELOPMENT)
    loaded_dev.frame = pd.DataFrame()
    assert_no_final_test(dev[SPLIT_DATE_COLUMN])
    dev_reader = LayerTableReader(layer_root, hash_files=cfg.hash_files)
    dev_predictions = rft._predict_saved(loaded, dev, dev_reader, history)
    dev_rates, dev_b1_q = rft._b1_predict(b1_rate_tables, b1_quantile_table, dev)
    clock.lap("development_predictions")
    dev_problems, reproduction, calibrators = rft._development_checks(
        loaded, dev, dev_predictions, dev_rates, dev_b1_q, base
    )
    run_files = [f for item in loaded.values() for f in item.results["data_fingerprint"]["files"]]
    read_files = [*loaded_train.files, *loaded_dev.files, *dev_reader.files]
    dev_problems += [f"layer: {p}" for p in rp._file_mismatches(run_files, read_files)]
    if dev_problems:
        raise fl.LockVerificationError("Development reproduction failed: " + "; ".join(dev_problems[:20]))
    cancel_pair: tuple[dict[str, Any], dict[str, Any]] = calibrators.get(fe.ROLE_CANCELLED_PLAN) or ({}, {})
    cancel_calibrator = cancel_pair[0].get(fe.STATIC_PROBABILITY)
    dev_arrays = rb._arrays(dev, dev_predictions, dev_b1_q, cancel_calibrator, False)
    del dev, dev_predictions, dev_rates
    gc.collect()
    dev_months = rb.development_eval_months(fit.end)
    dev_offsets = rb._offsets(dev_arrays, dev_months, cfg.levels)
    dev_rows = rb._take(dev_arrays, dev_arrays["dates"] >= np.datetime64(dev_months[0], "D"))
    return Prepared(
        loaded=loaded,
        fit=fit,
        history=history,
        b1_rate_tables=b1_rate_tables,
        b1_quantile_table=b1_quantile_table,
        dev_arrays=dev_arrays,
        dev_rows=dev_rows,
        dev_months=dev_months,
        dev_offsets=dev_offsets,
        reproduction=reproduction,
        cancel_calibrator=cancel_calibrator,
        files=read_files,
    )


def _load_final_test(
    prepared: Prepared, cfg: SolverConfig, layer_root: Path | None, lock_file: Path
) -> tuple[dict[str, Any], dict[str, Any], list[Any]]:
    """Final-test rows and their rolling conformal offsets (after the lock check; ``run_buffer.run`` steps)."""
    require_lock_written(lock_file)
    loaded_test = load_periods(
        layer_root,
        [FINAL_TEST],
        flight_columns=MODEL_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=cfg.hash_files,
        allow_final_test=True,
    )
    test = rm._slice(loaded_test.frame, FINAL_TEST)
    loaded_test.frame = pd.DataFrame()
    reader = LayerTableReader(layer_root, hash_files=cfg.hash_files, allow_final_test=True, lock_file=lock_file)
    predictions = rft._predict_saved(prepared.loaded, test, reader, prepared.history)
    _, test_b1_q = rft._b1_predict(prepared.b1_rate_tables, prepared.b1_quantile_table, test)
    arrays = rb._arrays(test, predictions, test_b1_q, prepared.cancel_calibrator, False)
    del test, predictions
    gc.collect()
    months = rb._test_months()
    context_start = min(conformal_calibration_window(m).start for m in months)
    context = rb._take(prepared.dev_arrays, prepared.dev_arrays["dates"] >= np.datetime64(context_start, "D"))
    joined = rb._concat(context, arrays, ("delay", "dates", "plan_knots", "b1_knots"))
    offsets = rb._offsets(joined, months, cfg.levels)
    return arrays, offsets, [*loaded_test.files, *reader.files]


def _period(
    label: str, rows: Mapping[str, Any], offsets: Mapping[str, Any], aggregator: str, cfg: SolverConfig
) -> dict[str, Any]:
    """``run_buffer`` evaluation of the period (levels, first-run budget curve) plus the solver budget curve."""
    base = rb._evaluate_period(label, rows, offsets, aggregator, cfg.buffer_config(), build_tables=False).summary
    cells = pol.make_cells(rows["origin"], rows["dest"], rows["minutes"], rows["dates"])
    inputs = pol.PolicyInputs(
        cells=cells, month=rows["month"], plan_knots=rows["plan_knots"], b1_knots=rows["b1_knots"]
    )
    cell_knots = inputs.cell_knots(aggregator)
    design = ev.DayDesign(rows["dates"], rows["delay"], rows["month"], replicates=cfg.replicates, seed=cfg.seed)
    candidates = knapsack_candidates(rows["plan_knots"], cells, cell_knots[pol.POLICY_PLAN], cfg)
    LOG.info("%s: knapsack candidates ready (%s)", label, {k: v.info for k, v in candidates.items()})
    solver = solver_budget_curve(design, cells, cell_knots, candidates, cfg, label=label)
    return {
        **base,
        "candidates": {k: v.info for k, v in candidates.items()},
        "solver": solver,
    }


# ----------------------------------------------------------------------------
# run
# ----------------------------------------------------------------------------


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(_jsonable(dict(payload)), ensure_ascii=False, indent=2, allow_nan=False)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def run(
    manifest_path: Path = rb.DEFAULT_MANIFEST,
    *,
    config: SolverConfig | None = None,
    layer_root: Path | None = None,
    base: Path = PROJECT_ROOT,
    lock_file: Path = FINAL_TEST_LOCK_FILE,
    output_dir: Path = rb.OUTPUT_DIR,
    first_run_dir: Path = FIRST_RUN_DIR,
    now: dt.datetime | None = None,
) -> Path:
    """Full run (module docstring). Returns the output folder."""
    cfg = config or SolverConfig()
    created = now or dt.datetime.now(dt.UTC)
    stamp = f"{created:%Y%m%dT%H%M%SZ}"
    plan = preflight(
        manifest_path,
        config=cfg,
        lock_file=lock_file,
        base=base,
        output_dir=output_dir,
        first_run_dir=first_run_dir,
        stamp=stamp,
    )
    folder: Path = plan["_folder"]
    clock = rb._Clock()
    prepared = _prepare(plan["_manifest"], cfg, layer_root, base, clock)
    first_freeze = json.loads((first_run_dir / rb.FREEZE_FILE).read_text(encoding="utf-8"))
    first_results = json.loads((first_run_dir / rb.RESULTS_FILE).read_text(encoding="utf-8"))
    dev_rows = prepared.dev_rows
    dev_inputs = pol.PolicyInputs(
        cells=pol.make_cells(dev_rows["origin"], dev_rows["dest"], dev_rows["minutes"], dev_rows["dates"]),
        month=dev_rows["month"],
        plan_knots=dev_rows["plan_knots"],
        b1_knots=dev_rows["b1_knots"],
    )
    aggregator, aggregator_selection = pol.select_aggregator(
        dev_rows["dates"], dev_rows["delay"], dev_inputs, cfg.levels
    )
    if aggregator != first_freeze.get("aggregator"):
        raise fl.LockVerificationError(
            f"Aggregator {aggregator!r} differs from the first run's frozen {first_freeze.get('aggregator')!r}"
        )
    del dev_inputs
    dev_period = _period("dogrulama", dev_rows, prepared.dev_offsets, aggregator, cfg)
    distribution, distribution_selection = select_cell_distribution(dev_period, tie=cfg.selection_tie_arrdel15)
    LOG.info("development: cell distribution %s chosen (%s)", distribution, distribution_selection["reason"])
    clock.lap("development_evaluation")

    # --- freeze (before any final-test row is read) ---
    folder.mkdir(parents=True)
    freeze: dict[str, Any] = {
        "etiket": EXPLORATORY_LABEL,
        "exploratory_post_hoc": True,
        "schema": "flight_delay/or-solver-freeze/v1",
        "created_utc": created.isoformat(),
        "written_before_final_test_read": True,
        "manifest": plan["manifest"],
        "lock": plan["lock"],
        "roles": plan["roles"],
        "git": repro.git_info(base),
        "config": cfg.to_dict(),
        "aggregator": aggregator,
        "aggregator_equals_first_run": True,
        "cell_distribution": distribution,
        "cell_distribution_selection": distribution_selection,
        "first_run": plan["first_run"],
        "development_eval_months": [f"{m:%Y-%m}" for m in prepared.dev_months],
    }
    _write_json_exclusive(folder / FREEZE_FILE, freeze)
    LOG.info("freeze written: %s", folder / FREEZE_FILE)

    output: dict[str, Any] = {
        "etiket": EXPLORATORY_LABEL,
        "exploratory_post_hoc": True,
        "metadata": {
            "created_utc": created.isoformat(),
            "command": COMMAND,
            "freeze_file": fl._relative(folder / FREEZE_FILE, base),
            "manifest": plan["manifest"],
            "lock": plan["lock"],
            "roles": plan["roles"],
            "git": freeze["git"],
            "library_versions": repro.library_versions(),
            "solver_versions": _solver_versions(),
            "fit_window": {"start": str(prepared.fit.start), "end": str(prepared.fit.end)},
            "config": cfg.to_dict(),
            "aggregator": aggregator,
            "cell_distribution": distribution,
            "first_run": plan["first_run"],
            "final_test_read": False,
        },
        "verification": {
            "development_reproduction": prepared.reproduction,
            "first_run_reproduction": {
                "dogrulama": reproduction_vs_first_run(dev_period, first_results["periods"].get("dogrulama"))
            },
        },
        "selection": {"aggregator": aggregator_selection, "cell_distribution": distribution_selection},
        "periods": {"dogrulama": dev_period},
    }
    if not cfg.development_only:
        test_arrays, test_offsets, test_files = _load_final_test(prepared, cfg, layer_root, lock_file)
        clock.lap("final_test_predictions")
        test_period = _period("test", test_arrays, test_offsets, aggregator, cfg)
        clock.lap("final_test_evaluation")
        output["metadata"]["final_test_read"] = True
        output["metadata"]["final_test_files"] = fingerprint(test_files)
        output["periods"]["test"] = test_period
        output["verification"]["first_run_reproduction"]["test"] = reproduction_vs_first_run(
            test_period, first_results["periods"].get("test")
        )
    output["metadata"]["timings_seconds"] = clock.timings
    output["metadata"]["seconds_total"] = round(time.perf_counter() - clock.started, 1)
    output["metadata"]["peak_rss_gb"] = rm._peak_rss_gb()
    clean = _jsonable(output)
    if cfg.plots:
        clean["metadata"]["plots"] = [fl._relative(p, base) for p in make_plots(clean, folder / PLOTS_DIR)]
    _write_json_exclusive(folder / RESULTS_FILE, clean)
    with (folder / SUMMARY_FILE).open("x", encoding="utf-8") as handle:
        handle.write(render(clean))
    LOG.info("results: %s", folder / RESULTS_FILE)
    return folder


def _solver_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    metadata = importlib.import_module("importlib.metadata")
    for name in ("pyomo", "highspy", "matplotlib", "scipy"):
        try:
            out[name] = str(metadata.version(name))
        except Exception:  # noqa: BLE001 - not installed
            out[name] = None
    return out


# ----------------------------------------------------------------------------
# figures
# ----------------------------------------------------------------------------


def _series(
    ys: Sequence[Any], label: str, *, low: Any = None, high: Any = None, dashed: bool = False
) -> dict[str, Any]:
    return {"y": list(ys), "low": low, "high": high, "label": label, "style": "dashed" if dashed else "solid"}


def plot_inputs(period: Mapping[str, Any]) -> dict[str, Any]:
    """Plain series for the three figures of one period (from the results JSON)."""
    curve = period["solver"]["curve"]
    budgets = [float(e["budget_per_flight_min"]) for e in curve.values()]
    names = ["plan_budget", "b1_budget", *KNAPSACK_POLICY.values()]
    late: dict[str, Any] = {}
    residual: dict[str, Any] = {}
    for name in names:
        if not all(name in e["policies"] for e in curve.values()):
            continue
        ci = [e["absolute_ci"][name] for e in curve.values()]
        late[name] = _series(
            [e["policies"][name]["arr_del15_rate"] for e in curve.values()],
            POLICY_LABELS[name],
            low=[c["arr_del15_rate"]["ci_low"] for c in ci],
            high=[c["arr_del15_rate"]["ci_high"] for c in ci],
        )
        residual[name] = _series(
            [e["policies"][name]["residual_mean_min"] for e in curve.values()],
            POLICY_LABELS[name],
            low=[c["residual_mean_min"]["ci_low"] for c in ci],
            high=[c["residual_mean_min"]["ci_high"] for c in ci],
        )
    gap: dict[str, Any] = {}
    for distribution, policy in KNAPSACK_POLICY.items():
        if not all(policy in e["expected_vs_realized"] for e in curve.values()):
            continue
        ci = [e["absolute_ci"][policy]["arr_del15_rate"] for e in curve.values()]
        name = "Vincentize" if distribution == "vincentize" else "karışım"
        gap[f"{policy}_expected"] = _series(
            [e["expected_vs_realized"][policy]["expected_rate_completed_rows"] for e in curve.values()],
            f"Beklenen (model), {name}",
            dashed=True,
        )
        gap[f"{policy}_realized"] = _series(
            [e["expected_vs_realized"][policy]["realized_rate"] for e in curve.values()],
            f"Gerçekleşen, {name}",
            low=[c["ci_low"] for c in ci],
            high=[c["ci_high"] for c in ci],
        )
    levels = list(period["levels"].values())
    taus = [float(e["level"]) for e in levels]
    tau_cost: dict[str, Any] = {}
    tau_added: dict[str, Any] = {}
    tau_late: dict[str, Any] = {}
    for policy in (pol.POLICY_NONE, pol.POLICY_B1, pol.POLICY_PLAN, pol.POLICY_PLAN_CONFORMAL, pol.POLICY_PLAN_FLIGHT):
        if not all(policy in e["policies"] for e in levels):
            continue
        rows = [e["policies"][policy] for e in levels]
        label = POLICY_LABELS[policy]
        tau_cost[policy] = _series([r.get("cost_mean") for r in rows], label)
        tau_added[policy] = _series([r["buffer_planned_mean_min"] for r in rows], label)
        tau_late[policy] = _series([r["arr_del15_rate"] for r in rows], label)
    return {
        "budget": {"x": budgets, "arr_del15": late, "residual": residual},
        "gap": {"x": budgets, "series": gap},
        "tau": {"x": taus, "cost": tau_cost, "added": tau_added, "arr_del15": tau_late},
    }


def make_plots(output: Mapping[str, Any], folder: Path) -> list[Path]:
    """Figures (a) budget curve, (b) tau sensitivity, (c) knapsack expected vs realised for every period."""
    written: list[Path] = []
    for label, period in output["periods"].items():
        data = plot_inputs(period)
        title = PERIOD_TITLES.get(label, label)
        note = None if label == "dogrulama" else f"Etiket: {EXPLORATORY_LABEL}. Bantlar: %95 gün blok bootstrap GA."
        budget = data["budget"]
        written.append(
            pl.plot_budget_curve(
                folder / f"butce-egrisi-{label}.png",
                {"x": budget["x"], "series": budget["arr_del15"]},
                {"x": budget["x"], "series": budget["residual"]},
                title=f"Bütçe eğrisi – {title}",
                note=note or "Bantlar: %95 gün blok bootstrap GA.",
            )
        )
        tau = data["tau"]
        written.append(
            pl.plot_level_sensitivity(
                folder / f"tau-duyarliligi-{label}.png",
                {"x": tau["x"], "series": tau["cost"]},
                {"x": tau["x"], "series": tau["added"]},
                {"x": tau["x"], "series": tau["arr_del15"]},
                title=f"τ duyarlılığı – {title}",
                note=note or "Maliyet oranı varsayımdır (c_u = τ, c_o = 1 − τ).",
            )
        )
        if data["gap"]["series"]:
            written.append(
                pl.plot_expected_vs_realized(
                    folder / f"sirt-cantasi-beklenen-gerceklesen-{label}.png",
                    data["gap"],
                    title=f"Sırt çantası: beklenen ve gerçekleşen ArrDel15 – {title}",
                    note=note or "Bant: gerçekleşen için %95 gün blok bootstrap GA.",
                )
            )
    return written


# ----------------------------------------------------------------------------
# Turkish summary
# ----------------------------------------------------------------------------


def _ci(entry: Mapping[str, Any] | None, digits: int = 4) -> str:
    if not entry or entry.get("estimate") is None:
        return "-"
    low, high = entry.get("ci_low"), entry.get("ci_high")
    bounds = "" if low is None or high is None else f" [{low:.{digits}f}; {high:.{digits}f}]"
    return f"{entry['estimate']:.{digits}f}{bounds}"


def _num(value: Any, digits: int = 4) -> str:
    return "-" if value is None else _format(float(value), digits)


def _period_lines(label: str, period: Mapping[str, Any]) -> list[str]:
    solver = period["solver"]
    title = PERIOD_TITLES.get(label, label)
    lines = [f"## Dönem: {title}", ""]
    if label != "dogrulama":
        lines += [f"> Bu dönemin bütün sayıları **{EXPLORATORY_LABEL}**.", ""]
    lines += [
        f"- Hücre: {period['cells']['n']} · günler: {period['design']['days']} "
        f"({period['design']['first_day']} .. {period['design']['last_day']})",
        f"- Sırt çantası adayları: {json.dumps(period.get('candidates', {}), ensure_ascii=False)}",
    ]
    model = solver.get("lp_model")
    if model:
        lines.append(
            f"- LP boyutu: {model['sizes']} · kurulum {model['build_seconds']} sn · kiriş hata sınırı "
            f"{_num(model['chord_error_bound'], 1)} uçuş·dk"
        )
    lines += [
        "",
        "### Dakika bütçesi: Pyomo LP (HiGHS) ve kapalı biçim",
        "",
        "| Bütçe dk/uçuş | Kapalı biçim τ (durum) | LP τ (dual) | LP durumu | Maks. |Δb| dk | Tolerans içi pay | "
        "Göreli amaç farkı | Sertifika (alt/üst) | Kısıt ihlali | Uyum | LP sn |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in solver["curve"].values():
        check = entry["allocations"]["plan_budget"].get("lp_cross_check")
        if not check:
            continue
        lp = check.get("lp") or {}
        seconds = (lp.get("solver") or {}).get("seconds")
        violations = check.get("violations") or {}
        lines.append(
            f"| {entry['budget_per_flight_min']:g} | {_num(check.get('closed_form_level'))} "
            f"({check.get('closed_form_status')}) | {_num(check.get('lp_implied_level'))} | {check.get('lp_status')} | "
            f"{_num(check.get('buffer_abs_diff_max'), 3)} | {_num(check.get('cells_within_tolerance_share'))} | "
            f"{_num(check.get('objective_relative_difference'), 6)} | {check.get('certificate_lower_ok', '-')}/"
            f"{check.get('certificate_upper_ok', '-')} | {sum(violations.values()) if violations else '-'} | "
            f"{check.get('agrees')} | {_num(seconds, 1)} |"
        )
    lines += [
        "",
        "### ArrDel15 sırt çantası: açgözlü, LP alt sınırı ve Pyomo MILP (HiGHS)",
        "",
        "| Bütçe dk/uçuş | Dağılım | Açgözlü (beklenen geç uçuş) | LP alt sınırı | MILP | MILP − açgözlü | "
        "MIP gap | Sonlanma | Farklı hücre | Model hücre / ikili | MILP sn |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in solver["curve"].values():
        for distribution, policy in KNAPSACK_POLICY.items():
            alloc = entry["allocations"].get(policy)
            if not alloc:
                continue
            milp = alloc.get("milp") or {}
            report = milp.get("solver") or {}
            restriction = milp.get("restriction") or {}
            sizes = milp.get("sizes") or {}
            lines.append(
                f"| {entry['budget_per_flight_min']:g} | {distribution} | {_num(alloc.get('value'), 2)} | "
                f"{_num(alloc.get('lp_value'), 2)} | {_num(milp.get('value'), 2)} | "
                f"{_num(milp.get('value_minus_greedy'), 3)} | {_num(report.get('mip_gap'), 8)} | "
                f"{report.get('termination', '-')} | {milp.get('cells_with_different_buffer', '-')} | "
                f"{restriction.get('cells_in_model', '-')} / {sizes.get('binaries', '-')} | "
                f"{_num(report.get('seconds'), 1)} |"
            )
    lines += [
        "",
        "### Eşit bütçe: gerçekleşen sonuçlar [%95 GA] ve sırt çantası beklenen vs gerçekleşen",
        "",
        "| Bütçe dk/uçuş | Politika | Ek tampon dk/uçuş | ArrDel15 [GA] | Kalan rötar dk/uçuş [GA] | Beklenen ArrDel15 | "
        "Gerçekleşen − beklenen |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in solver["curve"].values():
        for name, row in entry["policies"].items():
            ci = entry["absolute_ci"].get(name) or {}
            exp = entry["expected_vs_realized"].get(name) or {}
            lines.append(
                f"| {entry['budget_per_flight_min']:g} | {POLICY_LABELS.get(name, name)} | "
                f"{_num(row['buffer_planned_mean_min'], 2)} | {_ci(ci.get('arr_del15_rate'))} | "
                f"{_ci(ci.get('residual_mean_min'), 2)} | {_num(exp.get('expected_rate_completed_rows'))} | "
                f"{_num(exp.get('gap_realized_minus_expected'))} |"
            )
    lines += [
        "",
        "| Bütçe dk/uçuş | Karşılaştırma | Δ ArrDel15 [GA] | Δ kalan rötar dk [GA] |",
        "|---|---|---|---|",
    ]
    for entry in solver["curve"].values():
        for pair, comparison in entry["comparisons"].items():
            lines.append(
                f"| {entry['budget_per_flight_min']:g} | {pair} | {_ci(comparison.get('d_late15'))} | "
                f"{_ci(comparison.get('d_residual'), 2)} |"
            )
    return [*lines, ""]


def render(output: Mapping[str, Any]) -> str:
    """Turkish markdown; the exploratory label is the first line; every number comes from ``output``."""
    meta = output["metadata"]
    lines = [
        f"**Etiket: {output['etiket']}.**",
        "",
        "# Blok süre tamponu – çözücü uzantısı (Pyomo + HiGHS)",
        "",
        "> Son test dönemi bu politikalar için ilk OR koşusunda (`tampon-20261122T173803Z`) görüldü; buradaki test "
        "sayıları keşifseldir ve son test sonucu yerine geçmez. Maliyetler varsayımdır; A1: 1 dk tampon = 1 dk daha az "
        "varış rötarı (model yeniden tahmin ettirilmez). Hücre dağılımı seçimi yalnızca geliştirme döneminde yapıldı ve "
        "test okunmadan önce donduruldu.",
        "",
        f"- Oluşturma (UTC): {meta['created_utc']} · dondurma: `{meta['freeze_file']}` · toplayıcı: "
        f"{meta['aggregator']} · hücre dağılımı (geliştirmede seçildi): **{meta['cell_distribution']}**",
        f"- Çözücü sürümleri: {meta.get('solver_versions')} · son test okundu mu: {meta['final_test_read']} · süre "
        f"{meta.get('seconds_total')} sn · tepe bellek {meta.get('peak_rss_gb')} GB",
        "",
        "## Geliştirme seçimi: hücre dağılımı (yalnızca 2025-11..2026-02)",
        "",
        f"- Kural: {output['selection']['cell_distribution']['rule']}",
        f"- Seçilen: **{output['selection']['cell_distribution']['chosen']}** "
        f"({output['selection']['cell_distribution']['reason']})",
        "",
        "| Dağılım | Ortalama gerçekleşen ArrDel15 | Ortalama |gerçekleşen − beklenen| |",
        "|---|---|---|",
    ]
    for name, stats in output["selection"]["cell_distribution"]["candidates"].items():
        lines.append(f"| {name} | {_num(stats['realized_arr_del15_mean'])} | {_num(stats['abs_gap_mean'])} |")
    lines.append("")
    for label, check in output["verification"].get("first_run_reproduction", {}).items():
        lines.append(
            f"- İlk koşuyla yeniden üretim ({label}): kontrol {check.get('checked')}, karşılaştırılan "
            f"{check.get('compared', '-')}, en büyük fark {_num(check.get('max_abs_diff'), 9)}"
        )
    lines.append("")
    for label, period in output["periods"].items():
        lines += _period_lines(label, period)
    plots = meta.get("plots")
    if plots:
        lines += ["## Grafikler", "", *[f"- `{p}`" for p in plots], ""]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _floats(values: Sequence[str] | None, default: tuple[float, ...]) -> tuple[float, ...]:
    return default if not values else tuple(round(float(v), 4) for v in values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Solver extension of the buffer run (Pyomo + HiGHS; exploratory).")
    parser.add_argument("--manifest", type=Path, default=rb.DEFAULT_MANIFEST)
    parser.add_argument("--lock-file", type=Path, default=FINAL_TEST_LOCK_FILE)
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--output-dir", type=Path, default=rb.OUTPUT_DIR)
    parser.add_argument("--first-run-dir", type=Path, default=FIRST_RUN_DIR)
    parser.add_argument("--levels", nargs="+", default=None, help="critical ratios inside [0.10, 0.95]")
    parser.add_argument("--budgets", nargs="+", default=None, help="planned extra minutes per scheduled flight")
    parser.add_argument("--replicates", type=int, default=bs.DEFAULT_REPLICATES)
    parser.add_argument("--solver", choices=("highs",), default="highs", help="Pyomo appsi_highs")
    parser.add_argument("--no-lp", action="store_true", help="skip the minutes LP cross-check")
    parser.add_argument("--lp-formulation", choices=pm.FORMULATIONS, default="segments")
    parser.add_argument("--lp-max-segment", type=float, default=2.0, help="longest LP piece (minutes)")
    parser.add_argument("--lp-time-limit", type=float, default=600.0, help="seconds per LP solve")
    parser.add_argument("--no-milp", action="store_true", help="skip the ArrDel15 MILP")
    parser.add_argument("--milp-time-limit", type=float, default=120.0, help="seconds per MILP solve")
    parser.add_argument("--milp-gap", type=float, default=1e-6, help="HiGHS mip_rel_gap")
    parser.add_argument("--milp-min-n", type=int, default=0, help="cells with fewer flights fixed at the greedy choice")
    parser.add_argument("--mixture-cells", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--plots", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--development-only", action="store_true", help="development phase and freeze only")
    parser.add_argument("--no-hash", action="store_true", help="file sizes instead of sha256 in fingerprints")
    parser.add_argument("--dry-run", action="store_true", help="checks and plan only; nothing read or written")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = SolverConfig(
        levels=_floats(args.levels, nv.DEFAULT_LEVEL_GRID),
        budgets_per_flight=_floats(args.budgets, ev.DEFAULT_BUDGETS_PER_FLIGHT),
        replicates=args.replicates,
        solver=args.solver,
        lp=not args.no_lp,
        lp_formulation=args.lp_formulation,
        lp_max_segment_min=args.lp_max_segment,
        lp_time_limit_s=args.lp_time_limit,
        milp=not args.no_milp,
        milp_time_limit_s=args.milp_time_limit,
        milp_rel_gap=args.milp_gap,
        milp_min_n=args.milp_min_n,
        mixture_cells=args.mixture_cells,
        plots=args.plots,
        development_only=args.development_only,
        hash_files=not args.no_hash,
    )
    if args.dry_run:
        stamp = f"{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}"
        plan = preflight(
            args.manifest,
            config=config,
            lock_file=args.lock_file,
            base=PROJECT_ROOT,
            output_dir=args.output_dir,
            first_run_dir=args.first_run_dir,
            stamp=stamp,
        )
        public = {k: v for k, v in plan.items() if not k.startswith("_")}
        public["etiket"] = EXPLORATORY_LABEL
        print(json.dumps(_jsonable(public), ensure_ascii=False, indent=2))
        return 0
    folder = run(
        args.manifest,
        config=config,
        layer_root=args.layer_dir,
        lock_file=args.lock_file,
        output_dir=args.output_dir,
        first_run_dir=args.first_run_dir,
    )
    print(f"Results: {folder / RESULTS_FILE}\nSummary: {folder / SUMMARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
