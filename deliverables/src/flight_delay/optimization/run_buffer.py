"""Block-time buffer optimisation run (formulation: ``experiments/or-tampon-formulasyonu.md``).

Usage (from the project root ``projects/havayolu-ds/``):
    python -m flight_delay.optimization.run_buffer --dry-run          # checks + plan only, nothing is read or written
    python -m flight_delay.optimization.run_buffer                    # full run (development phase, freeze, test)
    python -m flight_delay.optimization.run_buffer --development-only # development phase + freeze only

Order (fail closed at every step):
1. Freeze manifest ``experiments/son-test-dondurma.json``: sha256 of every referenced file (``final_lock``); the lock
   record ``experiments/son-test-kilidi.json`` must exist and name this manifest (the final test was run once, its
   results are frozen; this run never writes or changes the lock or any ML result).
2. Locked roles: ``arr_delay/plan`` (OR source, plan 8 / decision M3 C1) and ``cancelled/plan`` (information only);
   ``arr_delay/T2_matched`` only with ``--with-t2`` (secondary; weather at T - 2 h is not known when a schedule is
   planned). History statistics and B1 are refitted on the fit window and checked against the runs (as in
   ``run_final_test``); every model's Val-B metric is reproduced (``run_final_test._development_checks``).
3. Development phase (2025-09-01 .. 2026-02-28, evaluation months whose rolling conformal window lies after the fit
   window: 2025-11 .. 2026-02): the only free choice (cell aggregator) is made here (``policies.select_aggregator``
   refuses final-test rows); development metrics are written.
4. Freeze: ``politika-dondurma.json`` (levels, budgets, aggregator, publication policy, cell rule) is written with
   exclusive create BEFORE any final-test row is read.
5. Final-test phase (2026-03 .. 2026-08): read only after ``splits.require_lock_written``; the frozen policies are
   evaluated, nothing is tuned. Rolling conformal context rows come from the development frame (2026-01-03 ..).
6. Outputs (new folders, never overwritten): ``experiments/or/tampon-<UTC>/`` (freeze, results JSON, Turkish summary)
   and ``deliverables/data/or/tampon-<UTC>/`` (cell Parquet; flight Parquet only if git ignores that folder).

Rough cost (NOT measured): predictions of 6 boosters on ~2.4 M development + ~2.3 M test rows with plan-contract
matrices (the final test spent 1331 s predicting 7 roles incl. T2 weather matrices on 2.3 M rows and peaked at 6.0 GB);
expected 20 - 45 min and 6 - 9 GB peak RSS. Progress is logged to stderr.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
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
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import run_final_test as rft
from flight_delay.modeling import run_models as rm
from flight_delay.modeling import run_permutation as rp
from flight_delay.modeling import targets as tg
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
    Period,
    assert_no_final_test,
    conformal_calibration_window,
    require_lock_written,
)
from flight_delay.optimization import evaluation as ev
from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization import policies as pol
from flight_delay.paths import DATA_DIR, PROJECT_ROOT

__all__ = [
    "DEVELOPMENT",
    "BufferConfig",
    "development_eval_months",
    "flight_file_git_ignored",
    "main",
    "preflight",
    "render",
    "run",
]

LOG = logging.getLogger("flight_delay.optimization.run_buffer")
COMMAND = "python -m flight_delay.optimization.run_buffer"
DEFAULT_MANIFEST = PROJECT_ROOT / "experiments" / "son-test-dondurma.json"
FINAL_TEST_RUN = "son-test-20261122T105048Z"  # the one final-test run (lock record of 2026-11-22)
DEFAULT_FINAL_RESULTS = PROJECT_ROOT / "experiments" / "son-test" / FINAL_TEST_RUN / "son-test-sonuclari.json"
OUTPUT_DIR = PROJECT_ROOT / "experiments" / "or"
DATA_OUTPUT_DIR = DATA_DIR / "or"
DEVELOPMENT = Period("or_development", VAL_A.start, VAL_B.end)
REQUIRED_ROLES = (fe.ROLE_QUANTILES_PLAN, fe.ROLE_CANCELLED_PLAN)
PUBLISH_POLICIES = (pol.POLICY_PLAN, pol.POLICY_PLAN_CONFORMAL)
FREEZE_FILE = "politika-dondurma.json"
RESULTS_FILE = "tampon-sonuclari.json"
SUMMARY_FILE = "tampon-ozet.md"
CELL_FILE = "hucre-tamponlari.parquet"
FLIGHT_FILE = "ucus-tamponlari.parquet"


@dataclass(frozen=True)
class BufferConfig:
    """Everything fixed before the final test is read (recorded in the freeze file)."""

    levels: tuple[float, ...] = nv.DEFAULT_LEVEL_GRID
    budgets_per_flight: tuple[float, ...] = ev.DEFAULT_BUDGETS_PER_FLIGHT
    publish_level: float = 0.80
    publish_policy: str = pol.POLICY_PLAN
    replicates: int = bs.DEFAULT_REPLICATES
    seed: int = bs.DEFAULT_SEED
    ci_level: float = bs.CI_LEVEL
    with_t2: bool = False
    development_only: bool = False
    flight_file: bool = True
    hash_files: bool = True
    min_n: int = pol.PUBLISH_MIN_N
    carrier_share_max: float = pol.SINGLE_CARRIER_SHARE_MAX

    def validate(self) -> list[str]:
        problems: list[str] = []
        try:
            levels = [nv.check_level(level) for level in self.levels]
        except nv.GridError as error:
            return [str(error)]
        if levels != sorted(set(levels)):
            problems.append("levels must be strictly increasing")
        if float(self.publish_level) not in [float(x) for x in self.levels]:
            problems.append(f"publish_level {self.publish_level} must be one of the levels")
        if self.publish_policy not in PUBLISH_POLICIES:
            problems.append(f"publish_policy must be one of {PUBLISH_POLICIES}")
        if self.replicates < 1:
            problems.append("replicates must be >= 1")
        if any(b <= 0 for b in self.budgets_per_flight):
            problems.append("budgets must be > 0 minutes per flight")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def development_eval_months(fit_end: dt.date) -> list[dt.date]:
    """Development months whose rolling conformal window starts after the fit window (out-of-sample scores)."""
    months = [dt.date(y, m, 1) for y, m in DEVELOPMENT.months()]
    chosen = [m for m in months if conformal_calibration_window(m).start > fit_end]
    if not chosen or conformal_calibration_window(chosen[0]).start < DEVELOPMENT.start:
        raise ValueError("No development month has its conformal window inside the development period")
    return chosen


def _test_months() -> list[dt.date]:
    return [dt.date(y, m, 1) for y, m in FINAL_TEST.months()]


# ----------------------------------------------------------------------------
# preflight (no data read)
# ----------------------------------------------------------------------------


def _roles(config: BufferConfig) -> tuple[str, ...]:
    return (*REQUIRED_ROLES, fe.ROLE_QUANTILES_T2) if config.with_t2 else REQUIRED_ROLES


def preflight(
    manifest_path: Path,
    *,
    config: BufferConfig,
    lock_file: Path,
    base: Path,
    output_dir: Path,
    data_output_dir: Path,
    stamp: str,
) -> dict[str, Any]:
    """Checks that need no layer data; raises LockVerificationError with every problem found."""
    problems = config.validate()
    manifest = fl.load_manifest(manifest_path)
    problems += fl.verify_files(manifest, base)
    missing = [r for r in _roles(config) if r not in manifest.entries]
    if missing:
        problems.append(f"roles missing from the manifest: {missing}")
    lock_info: dict[str, Any] = {"path": str(lock_file), "exists": lock_file.is_file()}
    if lock_file.is_file():
        record = json.loads(lock_file.read_text(encoding="utf-8"))
        lock_info["manifest_sha256"] = (record.get("manifest") or {}).get("sha256")
        lock_info["sha256"] = fl.sha256_file(lock_file)
        if lock_info["manifest_sha256"] != manifest.sha256:
            problems.append("the lock record names a different freeze manifest (sha256)")
    elif not config.development_only:
        problems.append(f"lock record missing ({lock_file}): the final test has not been run; use --development-only")
    folder = output_dir / f"tampon-{stamp}"
    data_folder = data_output_dir / f"tampon-{stamp}"
    for path in (folder, data_folder):
        if path.exists():
            problems.append(f"output folder exists, will not overwrite: {path}")
    if problems:
        raise fl.LockVerificationError("Buffer run refused (nothing read, nothing written): " + "; ".join(problems))
    return {
        "manifest": {"path": fl._relative(manifest.path, base), "sha256": manifest.sha256},
        "lock": lock_info,
        "roles": list(_roles(config)),
        "periods": {
            "development": {"start": str(DEVELOPMENT.start), "end": str(DEVELOPMENT.end)},
            "final_test": None
            if config.development_only
            else {"start": str(FINAL_TEST.start), "end": str(FINAL_TEST.end)},
        },
        "outputs": {"folder": str(folder), "data_folder": str(data_folder)},
        "config": config.to_dict(),
        "_manifest": manifest,
        "_folder": folder,
        "_data_folder": data_folder,
    }


# ----------------------------------------------------------------------------
# arrays of one period
# ----------------------------------------------------------------------------


def _quantile_knots(predictions: Mapping[str, np.ndarray]) -> tuple[np.ndarray, float]:
    raw = np.column_stack([np.asarray(predictions[key], dtype="float64") for key in fl.QUANTILE_MODEL_KEYS])
    return nv.monotone_knots(raw), nv.crossing_rate(raw)


def _b1_knots(b1_quantiles: Mapping[float, np.ndarray]) -> tuple[np.ndarray, float]:
    raw = np.column_stack([np.asarray(b1_quantiles[a], dtype="float64") for a in nv.KNOT_LEVELS])
    return nv.monotone_knots(raw), nv.crossing_rate(raw)


def _arrays(
    frame: pd.DataFrame,
    predictions: Mapping[str, Mapping[str, np.ndarray]],
    b1_quantiles: Mapping[float, np.ndarray],
    cancel_calibrator: Any | None,
    with_t2: bool,
) -> dict[str, Any]:
    days = pd.to_datetime(frame[SPLIT_DATE_COLUMN]).dt.normalize().to_numpy(dtype="datetime64[D]")
    plan, plan_crossing = _quantile_knots(predictions[fe.ROLE_QUANTILES_PLAN])
    b1, b1_crossing = _b1_knots(b1_quantiles)
    p_raw = np.asarray(predictions[fe.ROLE_CANCELLED_PLAN][f"{tg.CANCELLED}-lgbm"], dtype="float64")
    out: dict[str, Any] = {
        "flight_uid": frame["flight_uid"].to_numpy(),
        "dates": days,
        "month": days.astype("datetime64[M]").astype(str),
        "origin": frame["Origin"].astype(str).to_numpy(),
        "dest": frame["Dest"].astype(str).to_numpy(),
        "minutes": frame["crs_dep_local_min"].to_numpy(dtype="float64", na_value=np.nan),
        "crs_elapsed": pd.to_numeric(frame["CRSElapsedTime"], errors="coerce").to_numpy(dtype="float64"),
        "carrier": frame["Reporting_Airline"].astype(str).to_numpy(),  # used only for the M10 flag
        "delay": tg.target_values(frame, tg.ARR_DELAY),
        "cancelled": pd.to_numeric(frame["Cancelled"], errors="coerce").to_numpy(dtype="float64"),
        "diverted": pd.to_numeric(frame["Diverted"], errors="coerce").to_numpy(dtype="float64"),
        "plan_knots": plan,
        "b1_knots": b1,
        "p_cancel": cancel_calibrator.predict(p_raw) if cancel_calibrator is not None else p_raw,
        "crossing": {"plan": plan_crossing, "b1": b1_crossing},
    }
    if with_t2:
        out["t2_knots"], out["crossing"]["t2"] = _quantile_knots(predictions[fe.ROLE_QUANTILES_T2])
    return out


def _take(arrays: Mapping[str, Any], mask: np.ndarray) -> dict[str, Any]:
    return {k: (v[mask] if isinstance(v, np.ndarray) else v) for k, v in arrays.items()}


def _concat(first: Mapping[str, Any], second: Mapping[str, Any], keys: Sequence[str]) -> dict[str, np.ndarray]:
    return {k: np.concatenate([first[k], second[k]]) for k in keys}


# ----------------------------------------------------------------------------
# one evaluation period
# ----------------------------------------------------------------------------

_COMPARISONS = (
    (pol.POLICY_B1, pol.POLICY_NONE),
    (pol.POLICY_PLAN, pol.POLICY_NONE),
    (pol.POLICY_PLAN_CONFORMAL, pol.POLICY_NONE),
    (pol.POLICY_PLAN, pol.POLICY_B1),
    (pol.POLICY_PLAN_CONFORMAL, pol.POLICY_B1),
    (pol.POLICY_PLAN_CONFORMAL, pol.POLICY_B1_CONFORMAL),
    (pol.POLICY_PLAN_CONFORMAL, pol.POLICY_PLAN),
    (pol.POLICY_PLAN_FLIGHT, pol.POLICY_PLAN),
    (pol.POLICY_T2, pol.POLICY_PLAN),
)


@dataclass
class PeriodResult:
    summary: dict[str, Any]
    cell_frame: pd.DataFrame | None = None
    flight_columns: dict[str, Any] | None = None


def _counts(arrays: Mapping[str, Any]) -> dict[str, int]:
    delay = arrays["delay"]
    cancelled, diverted = arrays["cancelled"] == 1, arrays["diverted"] == 1
    return {
        "scheduled": int(delay.size),
        "completed_with_arr_delay": int(np.isfinite(delay).sum()),
        "cancelled": int(cancelled.sum()),
        "diverted": int(diverted.sum()),
        "completed_without_arr_delay": int((~np.isfinite(delay) & ~cancelled & ~diverted).sum()),
    }


def _evaluate_period(
    label: str,
    rows: Mapping[str, Any],
    offsets: Mapping[str, Mapping[float, Mapping[str, Mapping[str, Any]]]],
    aggregator: str,
    config: BufferConfig,
    *,
    build_tables: bool,
) -> PeriodResult:
    """Frozen policies on the evaluation rows of one period (no choice is made here)."""
    started = time.perf_counter()
    cells = pol.make_cells(rows["origin"], rows["dest"], rows["minutes"], rows["dates"])
    inputs = pol.PolicyInputs(
        cells=cells,
        month=rows["month"],
        plan_knots=rows["plan_knots"],
        b1_knots=rows["b1_knots"],
        plan_offsets=offsets["plan"],
        b1_offsets=offsets["b1"],
        t2_knots=rows.get("t2_knots"),
    )
    cell_knots = inputs.cell_knots(aggregator)
    design = ev.DayDesign(rows["dates"], rows["delay"], rows["month"], replicates=config.replicates, seed=config.seed)
    by_level: dict[str, Any] = {}
    buffer_columns: dict[str, np.ndarray] = {}
    recommendation: np.ndarray | None = None
    publish_buffers: dict[str, np.ndarray] = {}
    for level in config.levels:
        buffers = pol.policy_buffers(inputs, level, aggregator, cell_knots=cell_knots)
        scored = ev.score_policies(design, buffers, level=level, comparisons=_COMPARISONS, ci_level=config.ci_level)
        c_u, c_o = nv.cost_weights(level)
        by_level[pol.level_key(level)] = {
            "level": level,
            "cost_weights": {"c_u": c_u, "c_o": c_o, "c_u_over_c_o": nv.implied_cost_ratio(level)},
            **scored,
        }
        if build_tables:
            for policy in (pol.POLICY_PLAN, pol.POLICY_B1, pol.POLICY_PLAN_CONFORMAL):
                if policy in buffers:
                    buffer_columns[f"tampon_{policy}_{pol.level_key(level)}_dk"] = pol.cell_mean(buffers[policy], cells)
            if float(level) == float(config.publish_level):
                recommendation = pol.cell_mean(buffers[config.publish_policy], cells)
                publish_buffers = {k: buffers[k] for k in (pol.POLICY_PLAN, pol.POLICY_PLAN_CONFORMAL) if k in buffers}
        LOG.info("%s: level %.2f evaluated (%.0f s)", label, level, time.perf_counter() - started)
        del buffers
    budget = ev.evaluate_budget_curve(
        design, cells, cell_knots, budgets_per_flight=config.budgets_per_flight, ci_level=config.ci_level
    )
    LOG.info("%s: budget curve evaluated (%.0f s)", label, time.perf_counter() - started)
    counts = cells.counts()
    summary: dict[str, Any] = {
        "label": label,
        "counts": _counts(rows),
        "design": design.describe(),
        "cells": {
            "n": cells.n_cells,
            "with_n_ge_min": int((counts >= config.min_n).sum()),
            "flights_in_cells_with_n_ge_min": int(counts[counts >= config.min_n].sum()),
        },
        "quantile_crossing_rate_before_sort": rows["crossing"],
        "levels": by_level,
        "budget_curve": budget,
        "seconds": round(time.perf_counter() - started, 1),
    }
    result = PeriodResult(summary)
    if build_tables:
        assert recommendation is not None
        result.cell_frame = pol.cell_table(
            cells=cells,
            carrier=rows["carrier"],
            delay=rows["delay"],
            cancelled=rows["cancelled"],
            diverted=rows["diverted"],
            crs_elapsed=rows["crs_elapsed"],
            cell_knots=cell_knots,
            buffer_columns=buffer_columns,
            recommendation=recommendation,
            recommendation_source=f"{config.publish_policy}@{pol.level_key(config.publish_level)}",
            p_cancel=rows["p_cancel"],
            min_n=config.min_n,
            carrier_share_max=config.carrier_share_max,
        )
        published = result.cell_frame["yayimlanabilir"].to_numpy()
        summary["cells"]["publishable"] = int(published.sum())
        summary["cells"]["flagged_single_carrier"] = int(result.cell_frame["tek_tasiyici_yogun"].sum())
        columns: dict[str, Any] = {
            "ucus_id": rows["flight_uid"],
            "donem": np.full(rows["delay"].size, label),
            "flight_date": rows["dates"],
            "origin": rows["origin"],
            "dest": rows["dest"],
            "saat_blogu_kod": cells.keys["hour_block"].to_numpy()[cells.codes],
            "mevsim_kod": cells.keys["season"].to_numpy()[cells.codes],
            "crs_elapsed_dk": rows["crs_elapsed"],
            "gerceklesen_arr_delay": rows["delay"],
            "iptal": rows["cancelled"],
            "sapma": rows["diverted"],
            "p_iptal_model": rows["p_cancel"],
        }
        for j, level in enumerate(nv.KNOT_LEVELS):
            columns[f"plan_q{round(level * 100):03d}"] = rows["plan_knots"][:, j].astype("float32")
            columns[f"b1_q{round(level * 100):03d}"] = rows["b1_knots"][:, j].astype("float32")
        for name, values in publish_buffers.items():
            columns[f"tampon_{name}_{pol.level_key(config.publish_level)}"] = values.astype("float32")
        result.flight_columns = columns
    return result


def _offsets(
    context_and_eval: Mapping[str, np.ndarray], months: Sequence[dt.date], levels: Sequence[float]
) -> dict[str, dict[float, dict[str, dict[str, Any]]]]:
    return {
        name: pol.rolling_offsets(
            context_and_eval["delay"], context_and_eval[f"{name}_knots"], context_and_eval["dates"], months, levels
        )
        for name in ("plan", "b1")
    }


def offsets_reproduction(
    computed: Mapping[float, Mapping[str, Mapping[str, Any]]], final_results: Path | None
) -> dict[str, Any]:
    """Compare the plan offsets at 0.80 / 0.95 with the frozen final-test results (information, not a gate)."""
    if final_results is None or not Path(final_results).is_file():
        return {"checked": False, "reason": f"file not found: {final_results}"}
    data = json.loads(Path(final_results).read_text(encoding="utf-8"))
    try:
        stored = data["blocks"]["final_test"]["quantile"][fe.ROLE_QUANTILES_PLAN]["conformal"]["model"]["offsets"]
        rolling = stored[fe.PRIMARY_SCHEME]
    except (KeyError, TypeError) as error:
        return {"checked": False, "reason": f"offsets not found in {final_results}: {error!r}"}
    diffs: dict[str, float] = {}
    for level in (0.80, 0.95):
        if level not in computed:
            continue
        key = mt.quantile_key(level)
        for month, record in computed[level].items():
            old = (rolling.get(key) or {}).get(month, {}).get("offset")
            if old is not None and np.isfinite(record["offset"]):
                diffs[f"{key}:{month}"] = abs(float(record["offset"]) - float(old))
    return {
        "checked": bool(diffs),
        "file": str(final_results),
        "max_abs_diff_min": max(diffs.values()) if diffs else None,
        "differences": diffs,
        "note": "five-level joint row sort here vs separate sorts in final_eval: small differences are possible "
        "only on rows with crossing quantile models",
    }


# ----------------------------------------------------------------------------
# run
# ----------------------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.last = self.started
        self.timings: dict[str, float] = {}

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.timings[name] = round(now - self.last, 1)
        self.last = now
        elapsed = now - self.started
        LOG.info("%s done (%.0f s, total %.0f s, peak RSS %s GB)", name, self.timings[name], elapsed, rm._peak_rss_gb())


def flight_file_git_ignored(data_folder: Path, checker: Callable[[Path], bool | None] | None = None) -> bool | None:
    """``git check-ignore`` on the flight-level FILE path itself (the ignore rule is ``*.parquet``, a file pattern;
    the folder path is not ignored, so checking the folder wrongly refused the file). None if git is unavailable."""
    return (checker or rm._git_ignored)(Path(data_folder) / FLIGHT_FILE)


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(_jsonable(dict(payload)), ensure_ascii=False, indent=2, allow_nan=False)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def run(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    config: BufferConfig | None = None,
    layer_root: Path | None = None,
    base: Path = PROJECT_ROOT,
    lock_file: Path = FINAL_TEST_LOCK_FILE,
    output_dir: Path = OUTPUT_DIR,
    data_output_dir: Path = DATA_OUTPUT_DIR,
    final_results: Path | None = DEFAULT_FINAL_RESULTS,
    now: dt.datetime | None = None,
) -> Path:
    """Full run (module docstring). Returns the experiments output folder."""
    cfg = config or BufferConfig()
    created = now or dt.datetime.now(dt.UTC)
    stamp = f"{created:%Y%m%dT%H%M%SZ}"
    plan = preflight(
        manifest_path,
        config=cfg,
        lock_file=lock_file,
        base=base,
        output_dir=output_dir,
        data_output_dir=data_output_dir,
        stamp=stamp,
    )
    manifest: fl.Manifest = plan["_manifest"]
    folder: Path = plan["_folder"]
    data_folder: Path = plan["_data_folder"]
    clock = _Clock()
    loaded = rft._load_entries(manifest, base, _roles(cfg))
    problems = rft._check_boosters(loaded)
    if problems:
        raise fl.LockVerificationError("Buffer run refused: " + "; ".join(problems))
    settings = rft._settings(loaded)
    fit: Period = settings["fit"]
    clock.lap("manifest_and_models")

    # --- fit window: history statistics and B1 (refitted exactly as in the runs) ---
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

    # --- development phase ---
    loaded_dev = load_periods(
        layer_root,
        [VAL_A, VAL_B],
        flight_columns=MODEL_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=cfg.hash_files,
    )
    dev = rm._slice(loaded_dev.frame, DEVELOPMENT)
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
    dev_arrays = _arrays(dev, dev_predictions, dev_b1_q, cancel_calibrator, cfg.with_t2)
    del dev, dev_predictions, dev_rates
    gc.collect()
    dev_months = development_eval_months(fit.end)
    dev_eval = dev_arrays["dates"] >= np.datetime64(dev_months[0], "D")
    dev_offsets = _offsets(dev_arrays, dev_months, cfg.levels)
    dev_rows = _take(dev_arrays, dev_eval)
    dev_inputs = pol.PolicyInputs(
        cells=pol.make_cells(dev_rows["origin"], dev_rows["dest"], dev_rows["minutes"], dev_rows["dates"]),
        month=dev_rows["month"],
        plan_knots=dev_rows["plan_knots"],
        b1_knots=dev_rows["b1_knots"],
    )
    aggregator, selection = pol.select_aggregator(dev_rows["dates"], dev_rows["delay"], dev_inputs, cfg.levels)
    LOG.info("development: aggregator %s chosen", aggregator)
    dev_result = _evaluate_period("dogrulama", dev_rows, dev_offsets, aggregator, cfg, build_tables=False)
    clock.lap("development_evaluation")

    # --- freeze (before any final-test row is read) ---
    folder.mkdir(parents=True)
    freeze: dict[str, Any] = {
        "schema": "flight_delay/or-buffer-freeze/v1",
        "created_utc": created.isoformat(),
        "written_before_final_test_read": True,
        "manifest": plan["manifest"],
        "lock": plan["lock"],
        "roles": plan["roles"],
        "git": repro.git_info(base),
        "config": cfg.to_dict(),
        "aggregator": aggregator,
        "selection": selection,
        "cell_definition": list(pol.CELL_KEYS),
        "conformal": {
            "scheme": fe.PRIMARY_SCHEME,
            "window": "[m - 57 d, m - 2 d] (splits.conformal_calibration_window)",
        },
        "development_eval_months": [f"{m:%Y-%m}" for m in dev_months],
    }
    _write_json_exclusive(folder / FREEZE_FILE, freeze)
    LOG.info("freeze written: %s", folder / FREEZE_FILE)

    output: dict[str, Any] = {
        "metadata": {
            "created_utc": created.isoformat(),
            "command": COMMAND,
            "freeze_file": fl._relative(folder / FREEZE_FILE, base),
            "manifest": plan["manifest"],
            "lock": plan["lock"],
            "roles": plan["roles"],
            "git": freeze["git"],
            "library_versions": repro.library_versions(),
            "fit_window": {"start": str(fit.start), "end": str(fit.end)},
            "config": cfg.to_dict(),
            "aggregator": aggregator,
            "final_test_read": False,
        },
        "verification": {"development_reproduction": reproduction},
        "selection": selection,
        "periods": {"dogrulama": dev_result.summary},
    }
    if not cfg.development_only:
        # --- final-test phase: evaluation of the frozen policies only ---
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
        test_reader = LayerTableReader(
            layer_root, hash_files=cfg.hash_files, allow_final_test=True, lock_file=lock_file
        )
        test_predictions = rft._predict_saved(loaded, test, test_reader, history)
        _, test_b1_q = rft._b1_predict(b1_rate_tables, b1_quantile_table, test)
        test_arrays = _arrays(test, test_predictions, test_b1_q, cancel_calibrator, cfg.with_t2)
        del test, test_predictions
        gc.collect()
        clock.lap("final_test_predictions")
        months = _test_months()
        context_start = min(conformal_calibration_window(m).start for m in months)
        context = _take(dev_arrays, dev_arrays["dates"] >= np.datetime64(context_start, "D"))
        joined = _concat(context, test_arrays, ("delay", "dates", "plan_knots", "b1_knots"))
        test_offsets = _offsets(joined, months, cfg.levels)
        del joined, context
        test_result = _evaluate_period("test", test_arrays, test_offsets, aggregator, cfg, build_tables=True)
        clock.lap("final_test_evaluation")
        output["metadata"]["final_test_read"] = True
        output["metadata"]["final_test_files"] = fingerprint([*loaded_test.files, *test_reader.files])
        output["verification"]["conformal_offsets_vs_final_test"] = offsets_reproduction(
            test_offsets["plan"], final_results
        )
        output["periods"]["test"] = test_result.summary
        data_folder.mkdir(parents=True)
        assert test_result.cell_frame is not None
        test_result.cell_frame.to_parquet(data_folder / CELL_FILE, index=False, engine="pyarrow")
        output["metadata"]["cell_file"] = fl._relative(data_folder / CELL_FILE, base)
        ignored = flight_file_git_ignored(data_folder)
        output["metadata"]["data_folder_git_ignored"] = rm._git_ignored(data_folder)  # information only
        output["metadata"]["flight_file_git_ignored"] = ignored
        if cfg.flight_file and ignored is True and test_result.flight_columns is not None:
            pol.flight_table(test_result.flight_columns).to_parquet(data_folder / FLIGHT_FILE, index=False)
            output["metadata"]["flight_file"] = fl._relative(data_folder / FLIGHT_FILE, base)
        else:
            output["metadata"]["flight_file"] = None
            LOG.warning("flight-level file not written (git ignored: %s, requested: %s)", ignored, cfg.flight_file)
    output["metadata"]["timings_seconds"] = clock.timings
    output["metadata"]["seconds_total"] = round(time.perf_counter() - clock.started, 1)
    output["metadata"]["peak_rss_gb"] = rm._peak_rss_gb()
    clean = _jsonable(output)
    _write_json_exclusive(folder / RESULTS_FILE, clean)
    with (folder / SUMMARY_FILE).open("x", encoding="utf-8") as handle:
        handle.write(render(clean))
    LOG.info("results: %s", folder / RESULTS_FILE)
    return folder


# ----------------------------------------------------------------------------
# Turkish summary
# ----------------------------------------------------------------------------

_POLICY_NAMES = {
    pol.POLICY_NONE: "(i) ek tampon yok",
    pol.POLICY_B1: "(ii) B1 hücre kantili",
    pol.POLICY_PLAN: "(iii) plan modeli (ham)",
    pol.POLICY_PLAN_CONFORMAL: "(iv) plan + kayan conformal",
    pol.POLICY_B1_CONFORMAL: "(v) B1 + kayan conformal (adillik)",
    pol.POLICY_PLAN_FLIGHT: "(vi) plan, uçuş düzeyi (ikincil)",
    pol.POLICY_T2: "(vii) T2 (ikincil; bilgi zamanı uymaz)",
}


def _ci(entry: Mapping[str, Any] | None, digits: int = 3) -> str:
    if not entry or entry.get("estimate") is None:
        return "-"
    low, high = entry.get("ci_low"), entry.get("ci_high")
    bounds = "" if low is None or high is None else f" [{low:+.{digits}f}; {high:+.{digits}f}]"
    return f"{entry['estimate']:+.{digits}f}{bounds}"


def _period_lines(name: str, block: Mapping[str, Any], publish_key: str) -> list[str]:
    counts = block["counts"]
    lines = [
        f"## Dönem: {name}",
        "",
        f"- Günler: {block['design']['days']} ({block['design']['first_day']} .. {block['design']['last_day']}) · "
        f"tarifeli {counts['scheduled']} · tamamlanan (ArrDelay var) {counts['completed_with_arr_delay']} · iptal "
        f"{counts['cancelled']} · sapma {counts['diverted']} · ArrDelay'siz diğer {counts['completed_without_arr_delay']}",
        f"- Hücre: {block['cells']['n']} (n ≥ eşik: {block['cells']['with_n_ge_min']}; yayımlanabilir: "
        f"{block['cells'].get('publishable', '-')}, tek taşıyıcı yoğun: {block['cells'].get('flagged_single_carrier', '-')})",
        f"- Kantil kesişme oranı (sıralama öncesi): {block['quantile_crossing_rate_before_sort']}",
        "",
    ]
    for key, entry in block["levels"].items():
        weights = entry["cost_weights"]
        lines += [
            f"### τ = {entry['level']:.2f} (c_u/c_o = {weights['c_u_over_c_o']:.2f}; varsayım)"
            + (" — yayım düzeyi" if key == publish_key else ""),
            "",
            "| Politika | Ek tampon dk/uçuş | Kalan rötar dk/uçuş | Kullanılmayan dk/uçuş | ArrDel15 | Tam emilen | "
            "Maliyet/uçuş |",
            "|---|---|---|---|---|---|---|",
        ]
        for policy, row in entry["policies"].items():
            lines.append(
                f"| {_POLICY_NAMES.get(policy, policy)} | {_format(row['buffer_planned_mean_min'], 2)} | "
                f"{_format(row['residual_mean_min'], 2)} | {_format(row['unused_mean_min'], 2)} | "
                f"{_format(row['arr_del15_rate'])} | {_format(row['absorbed_rate'])} | {_format(row.get('cost_mean'), 3)} |"
            )
        lines += [
            "",
            "| Karşılaştırma | Δ maliyet/uçuş [%95 GA] | Δ kalan rötar dk | Δ ArrDel15 | Göreli Δ maliyet |",
            "|---|---|---|---|---|",
        ]
        for pair, comparison in entry["comparisons"].items():
            relative = comparison.get("relative_cost_change")
            lines.append(
                f"| {pair} | {_ci(comparison.get('d_cost'))} | {_ci(comparison.get('d_residual'), 2)} | "
                f"{_ci(comparison.get('d_late15'), 4)} | {'-' if relative is None else f'{relative:+.3f}'} |"
            )
        lines.append("")
    lines += [
        "### Eşit bütçe (uçuş başı planlanan ek dakika; aynı dakikada karşılaştırma)",
        "",
        "| Bütçe dk/uçuş | Plan τ (durum) | B1 τ (durum) | Δ kalan rötar plan−B1 [GA] | Δ ArrDel15 plan−B1 [GA] | "
        "Δ ArrDel15 sırt çantası−B1 [GA] | Sırt çantası LP açığı |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in block["budget_curve"].values():
        alloc = entry["allocations"]
        comp = entry["comparisons"]
        plan_level = alloc["plan_budget"]["level"]
        b1_level = alloc["b1_budget"]["level"]
        lines.append(
            f"| {entry['budget_per_flight_min']:g} | {_format(plan_level, 3)} ({alloc['plan_budget']['status']}) | "
            f"{_format(b1_level, 3)} ({alloc['b1_budget']['status']}) | "
            f"{_ci((comp.get('plan_budget-b1_budget') or {}).get('d_residual'), 2)} | "
            f"{_ci((comp.get('plan_budget-b1_budget') or {}).get('d_late15'), 4)} | "
            f"{_ci((comp.get('plan_arrdel15_budget-b1_budget') or {}).get('d_late15'), 4)} | "
            f"{_format(alloc['plan_arrdel15_budget']['gap'], 1)} |"
        )
    return [*lines, ""]


def render(output: Mapping[str, Any]) -> str:
    """Turkish markdown; every number comes from ``output``."""
    meta = output["metadata"]
    config = meta["config"]
    publish_key = pol.level_key(config["publish_level"])
    lines = [
        "# Blok süre tamponu – OR değerlendirmesi",
        "",
        "> Maliyetler VARSAYIMDIR: yalnızca oran c_u/c_o = τ/(1−τ) seçilir; maliyet c_u = τ, c_o = 1−τ ile normalize "
        "ağırlıklı dakikadır, fiyat değildir. Varsayım A1: 1 dk tampon = 1 dk daha az varış rötarı (uçuş değişmez; "
        "model yeniden tahmin ettirilmez). Kantiller tamamlanan uçuşa koşulludur. Son test dönemi yalnızca dondurulmuş "
        "politikaları değerlendirmek için okunur; testte hiçbir şey ayarlanmaz.",
        "",
        f"- Oluşturma (UTC): {meta['created_utc']} · dondurma: `{meta['freeze_file']}` · kilit girdisi: "
        f"`{meta['manifest']['path']}` · roller: {', '.join(meta['roles'])}",
        f"- Hücre toplayıcı (geliştirmede seçildi): **{meta['aggregator']}** · yayım: "
        f"{config['publish_policy']} @ τ = {config['publish_level']} · bootstrap B = {config['replicates']}, tohum "
        f"{config['seed']}",
        f"- Son test okundu mu: {meta['final_test_read']} · süre {meta.get('seconds_total')} sn · tepe bellek "
        f"{meta.get('peak_rss_gb')} GB",
        "",
        "## Geliştirme seçimi (yalnızca 2025-11..2026-02)",
        "",
        "| Toplayıcı | Izgara ortalama maliyet/uçuş |",
        "|---|---|",
    ]
    for how, entry in output["selection"]["candidates"].items():
        lines.append(f"| {how} | {_format(entry['cost_mean_over_levels'], 4)} |")
    lines.append("")
    check = output["verification"].get("conformal_offsets_vs_final_test")
    if check:
        lines += [
            f"- Conformal ofsetleri son test kaydıyla: kontrol {check.get('checked')}, en büyük fark "
            f"{_format(check.get('max_abs_diff_min'), 6)} dk",
            "",
        ]
    for name, block in output["periods"].items():
        lines += _period_lines(name, block, publish_key)
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _floats(values: Sequence[str] | None, default: tuple[float, ...]) -> tuple[float, ...]:
    return default if not values else tuple(round(float(v), 4) for v in values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Block-time buffer optimisation on the locked plan models.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--lock-file", type=Path, default=FINAL_TEST_LOCK_FILE)
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--data-output-dir", type=Path, default=DATA_OUTPUT_DIR)
    parser.add_argument("--final-test-results", type=Path, default=DEFAULT_FINAL_RESULTS)
    parser.add_argument("--levels", nargs="+", default=None, help="critical ratios inside [0.10, 0.95]")
    parser.add_argument("--budgets", nargs="+", default=None, help="planned extra minutes per scheduled flight")
    parser.add_argument("--publish-level", type=float, default=0.80)
    parser.add_argument("--publish-policy", choices=PUBLISH_POLICIES, default=pol.POLICY_PLAN)
    parser.add_argument("--replicates", type=int, default=bs.DEFAULT_REPLICATES)
    parser.add_argument("--with-t2", action="store_true", help="secondary T2 comparison (loads weather tables)")
    parser.add_argument("--development-only", action="store_true", help="development phase and freeze only")
    parser.add_argument("--no-flight-file", action="store_true")
    parser.add_argument("--no-hash", action="store_true", help="file sizes instead of sha256 in fingerprints")
    parser.add_argument("--dry-run", action="store_true", help="checks and plan only; nothing read or written")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = BufferConfig(
        levels=_floats(args.levels, nv.DEFAULT_LEVEL_GRID),
        budgets_per_flight=_floats(args.budgets, ev.DEFAULT_BUDGETS_PER_FLIGHT),
        publish_level=round(float(args.publish_level), 4),
        publish_policy=args.publish_policy,
        replicates=args.replicates,
        with_t2=args.with_t2,
        development_only=args.development_only,
        flight_file=not args.no_flight_file,
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
            data_output_dir=args.data_output_dir,
            stamp=stamp,
        )
        public = {k: v for k, v in plan.items() if not k.startswith("_")}
        public["development_eval_months_if_fit_ends_2025_08_31"] = [
            f"{m:%Y-%m}" for m in development_eval_months(dt.date(2025, 8, 31))
        ]
        print(json.dumps(_jsonable(public), ensure_ascii=False, indent=2))
        return 0
    folder = run(
        args.manifest,
        config=config,
        layer_root=args.layer_dir,
        lock_file=args.lock_file,
        output_dir=args.output_dir,
        data_output_dir=args.data_output_dir,
        final_results=args.final_test_results,
    )
    print(f"Results: {folder / RESULTS_FILE}\nSummary: {folder / SUMMARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
