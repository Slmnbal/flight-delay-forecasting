"""The one-time final test (plan sections 1.5, 5, 6) and its rehearsal on the rolling folds K3 / K4 (M3 item 4).

Usage (from the project root ``projects/havayolu-ds/``):
    python -m flight_delay.modeling.run_final_test --rehearsal --manifest experiments/son-test-dondurma-taslak.json
    python -m flight_delay.modeling.run_final_test --final --manifest experiments/son-test-dondurma.json   # ONCE

Rules: ``experiments/son-test-on-kayit.md`` (pre-registration, written before any result) and
``decisions/M3-son-test-oncesi-kararlari.md``. Evaluation code: ``final_eval``; manifest / lock: ``final_lock``.

Final test (``--final``), in this order, failing closed at every step:
1. ``splits.require_final_test_access(True, lock)``: refused if the lock record already exists (looked at once).
2. Freeze manifest: sha256 of every referenced file, every frozen value equal to what its run recorded, the
   pre-registered role rules, B = 1000 / seed 42 / Holm 0.05, the K3 / K5 tolerances equal to the passed rehearsal's
   proposal, clean git tree and no code change since the manifest's commit, LightGBM files with best_iteration trees.
3. Development data only (fit window + context 2025-11-05 .. 2026-02-28): history refit equal to every run's stored
   description, layer files equal to the runs' fingerprints, every model's and B1's Val-B metric reproduced, the frozen
   Platt calibrators reproduced on Val-B. Any problem: stop, NO lock is written, no final-test file is opened.
4. The lock record is written (exclusive create), THEN the final-test partitions are opened
   (``load_periods(allow_final_test=True)``, ``LayerTableReader(allow_final_test=True, lock_file=...)``).
5. ``final_eval``: K1 - K7, day-block bootstrap (B 1000, seed 42), Holm, monthly rolling conformal (+ static and the
   2-month-lag "public" scenario), monthly rolling Platt primary (static Platt secondary), plan -> T2 weather contribution, Origin x day stratified AUC.
   Outputs: ``experiments/son-test/son-test-<UTC>/`` (JSON + Turkish summary). Results are written as they are.

Rehearsal (``--rehearsal``): the same evaluation code on 2025-03 .. 2025-08 (K3 / K4 evaluation windows) with models
RETRAINED per fold, so nothing it scores was seen in training (the locked models were trained through 2025-08):
    fit = 2023-09-01 .. (start of early stopping - 1 day)   [the fold's fit window minus the last 6 months]
    early stopping = 4 months (same length as Val-A), calibration = the 2 months right before the fold (= Val-B)
    evaluation = the fold's 3 months (K3: 2025-03..05, K4: 2025-06..08)
The fold's fit window ends right before its evaluation; its last 2 months are kept for the calibrators / F1
thresholds / static conformal (a calibrator fitted on rows the model was trained on would be in-sample) and the 4 before
them for early stopping (the role Val-A plays). Same infrastructure as the search folds (``splits.ROLLING_FOLDS``;
category lists, history statistics and B1 refitted on each fold's fit window, out-of-fold for its own rows), the frozen
runs' parameters, round caps and patience. Caveat written into every output: the parameters were SEARCHED on these
fold windows (run-20261119T182216Z), so performance numbers are optimistic; the rehearsal checks the code path and
the winter -> summer coverage / calibration behaviour and fixes the K3 / K5 tolerances by the pre-registered rule.
It never writes the lock and never opens a final-test partition. Output: ``experiments/son-test-prova/prova-<UTC>/``.

Rough cost (NOT measured): rehearsal = up to 15 LightGBM models per fold on 12 (K3) / 15 (K4) fit months; final test =
predictions only (~3.9 M rows: context + test) plus 1000 bootstrap replicates of ~10 ranking statistics.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import gc
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import LeakageError
from flight_delay.data.layer import DEFAULT_LAYER_DIR
from flight_delay.mlops import reproducibility as repro
from flight_delay.modeling import bootstrap as bs
from flight_delay.modeling import calibration as cal
from flight_delay.modeling import features as ft
from flight_delay.modeling import final_eval as fe
from flight_delay.modeling import final_lock as fl
from flight_delay.modeling import gbm
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import run_models as rm
from flight_delay.modeling import run_permutation as rp
from flight_delay.modeling import targets as tg
from flight_delay.modeling.baselines import BASELINE_QUANTILE_LEVELS, make_quantile_baseline, make_rate_baseline
from flight_delay.modeling.categories import CategoryEncoder
from flight_delay.modeling.loading import fingerprint, load_periods
from flight_delay.modeling.matrix import (
    HISTORY_INPUT_COLUMNS,
    MODEL_FLIGHT_COLUMNS,
    MODEL_LABEL_COLUMNS,
    LayerTableReader,
    build_model_matrix,
    sample_days,
)
from flight_delay.modeling.run_baselines import _format, _jsonable
from flight_delay.modeling.splits import (
    FINAL_TEST_LOCK_FILE,
    SPLIT_DATE_COLUMN,
    TRAIN,
    VAL_B,
    Period,
    check_temporal_order,
    get_fold,
    get_period,
    require_final_test_access,
    require_lock_written,
)
from flight_delay.paths import PROJECT_ROOT

__all__ = [
    "CALIBRATION_MONTHS",
    "EARLY_STOPPING_MONTHS",
    "FINAL_OUTPUT_DIR",
    "REHEARSAL_FOLDS",
    "REHEARSAL_OUTPUT_DIR",
    "RehearsalPeriods",
    "context_period",
    "main",
    "rehearsal_periods",
    "render",
    "run_final",
    "run_rehearsal",
]

COMMAND = "python -m flight_delay.modeling.run_final_test"
FINAL_OUTPUT_DIR = PROJECT_ROOT / "experiments" / "son-test"
REHEARSAL_OUTPUT_DIR = PROJECT_ROOT / "experiments" / "son-test-prova"
RESULTS_FILE = {"final_test": "son-test-sonuclari.json", "rehearsal": "prova-sonuclari.json"}
SUMMARY_FILE = {"final_test": "son-test-ozet.md", "rehearsal": "prova-ozet.md"}
REHEARSAL_FOLDS = ("K3", "K4")
EARLY_STOPPING_MONTHS = 4  # = length of Val-A (plan 1.2)
CALIBRATION_MONTHS = 2  # = length of Val-B (plan 1.2); "the 2 months right before the fold"
_QUANTILE_SEARCH_KEY = "arr_delay_q080"
_BINARY_SEARCH_KEY = "arr_del15"  # cancellation reuses the ArrDel15 search result (run_models)


# ----------------------------------------------------------------------------
# periods
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class RehearsalPeriods:
    fold: str
    fit: Period
    early_stopping: Period
    calibration: Period
    evaluation: Period

    def to_dict(self) -> dict[str, Any]:
        return {
            name: {"start": str(p.start), "end": str(p.end)}
            for name, p in (
                ("fit", self.fit),
                ("early_stopping", self.early_stopping),
                ("calibration", self.calibration),
                ("evaluation", self.evaluation),
            )
        }


def _month_start(day: dt.date, delta: int) -> dt.date:
    index = day.year * 12 + (day.month - 1) + delta
    return dt.date(index // 12, index % 12 + 1, 1)


def rehearsal_periods(fold_name: str, max_fit_months: int | None = None) -> RehearsalPeriods:
    """Module docstring layout; ``max_fit_months`` keeps only the last N fit months (smoke runs)."""
    fold = get_fold(fold_name)
    evaluation = fold.evaluation
    calibration = Period(
        f"{fold_name}_calibration",
        _month_start(evaluation.start, -CALIBRATION_MONTHS),
        evaluation.start - dt.timedelta(days=1),
    )
    early = Period(
        f"{fold_name}_early_stopping",
        _month_start(calibration.start, -EARLY_STOPPING_MONTHS),
        calibration.start - dt.timedelta(days=1),
    )
    full_fit = Period(f"{fold_name}_fit", fold.fit.start, early.start - dt.timedelta(days=1))
    fit = rm.last_months(full_fit, max_fit_months)
    ordered = fit.end < early.start and early.end < calibration.start and calibration.end < evaluation.start
    if not ordered or evaluation.end > TRAIN.end or fit.start < fold.fit.start:
        raise LeakageError(f"Rehearsal periods of {fold_name} are not ordered inside the training window")
    return RehearsalPeriods(fold_name, fit, early, calibration, evaluation)


def context_period(evaluation: Period, end: dt.date) -> Period:
    """Rows before the evaluation needed by the rolling and the public conformal windows (and Platt)."""
    months = [dt.date(y, m, 1) for y, m in evaluation.months()]
    start = min(fe._window(scheme, m)[0] for scheme in ("rolling", "public") for m in months)
    return Period(f"context_{evaluation.name}", start, end)


# ----------------------------------------------------------------------------
# frozen runs
# ----------------------------------------------------------------------------


@dataclass
class LoadedEntry:
    entry: fl.Entry
    results: dict[str, Any]
    spec: dict[str, Any]
    model_paths: dict[str, Path]

    @property
    def config(self) -> dict[str, Any]:
        config: dict[str, Any] = self.results["metadata"]["config"]
        return config


def _load_entries(manifest: fl.Manifest, base: Path, roles: Sequence[str] | None = None) -> dict[str, LoadedEntry]:
    selected = list(roles) if roles else list(manifest.entries)
    unknown = [r for r in selected if r not in manifest.entries]
    if unknown:
        raise KeyError(f"Roles {unknown} are not in the manifest ({sorted(manifest.entries)})")
    out: dict[str, LoadedEntry] = {}
    for role in selected:
        entry = manifest.entries[role]
        out[role] = LoadedEntry(
            entry=entry,
            results=json.loads(entry.results.resolve(base).read_text(encoding="utf-8")),
            spec=json.loads(entry.spec.resolve(base).read_text(encoding="utf-8")),
            model_paths={key: ref.resolve(base) for key, (ref, _) in entry.models.items()},
        )
    return out


def _combos(loaded: Mapping[str, LoadedEntry]) -> dict[tuple[str, tuple[str, ...]], list[str]]:
    """(contract, dropped features) -> roles: one model matrix per combination."""
    combos: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for role, item in loaded.items():
        key = (item.entry.contract, tuple(item.entry.dropped_features))
        combos.setdefault(key, []).append(role)
    return combos


def _alpha(key: str) -> float | None:
    if not key.startswith("arr_delay_q") or not key.endswith("-lgbm"):
        return None
    return int(key[len("arr_delay_q") : -len("-lgbm")]) / 100.0


def _task(key: str, config: Mapping[str, Any]) -> tuple[gbm.GBMTask, str]:
    """(LightGBM task, target) of a locked model key with the run's settings."""
    alpha = _alpha(key)
    if alpha is not None:
        return {**gbm.QUANTILE_TASKS, **gbm.INTERVAL_TASKS}[alpha], tg.ARR_DELAY
    target = key[: -len("-lgbm")]
    task = gbm.BINARY_TASKS[target]
    metric = str(config.get("cancel_early_stopping_metric", task.metric))
    if target == tg.CANCELLED and metric != task.metric:
        task = gbm.with_early_stopping_metric(task, metric)
    return task, target


def _settings(loaded: Mapping[str, LoadedEntry]) -> dict[str, Any]:
    values = {json.dumps(fl.run_settings(item.results), sort_keys=True) for item in loaded.values()}
    if len(values) != 1:
        raise fl.LockVerificationError("Locked runs differ in fit window or history settings")
    first = next(iter(loaded.values()))
    config = first.config
    return {
        "fit": rp._period(first.results["periods"]["fit"], "fit"),
        "m": float(config["m"]),
        "min_support": int(config["min_support"]),
        "min_tail": int(config["min_tail"]),
        "n_blocks": int(config.get("n_blocks", 5)),
        "seed": int(config.get("seed", 42)),
        "segment_min_n": int(config.get("segment_min_n", 500)),
    }


def _check_boosters(loaded: Mapping[str, LoadedEntry]) -> list[str]:
    problems: list[str] = []
    for role, item in loaded.items():
        for key, path in item.model_paths.items():
            trees = int(lgb.Booster(model_file=str(path)).num_trees())
            if trees != item.entry.models[key][1]:
                problems.append(f"{role}: {key} has {trees} trees, best_iteration is {item.entry.models[key][1]}")
    return problems


def _b1_tables(train: pd.DataFrame, fit_end: dt.date, settings: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    keys = ft.add_key_columns(train)
    y = rm._targets(train)
    rates = {
        target: make_rate_baseline("B1", m=settings["m"], min_support=settings["min_support"]).fit(
            keys, y[target], fit_end=fit_end
        )
        for target in tg.CLASSIFICATION_TARGETS
    }
    quantiles = make_quantile_baseline("B1", alphas=BASELINE_QUANTILE_LEVELS, min_tail=settings["min_tail"]).fit(
        keys, y[tg.ARR_DELAY], fit_end=fit_end
    )
    return rates, quantiles


def _b1_predict(
    rates: Mapping[str, Any], quantiles: Any, frame: pd.DataFrame
) -> tuple[dict[str, np.ndarray], dict[float, np.ndarray]]:
    keys = ft.add_key_columns(frame)
    out_rates = {
        t: table.transform(keys, require_after_fit_end=True)["value"].to_numpy(dtype="float64")
        for t, table in rates.items()
    }
    levels = quantiles.quantiles(keys, require_after_fit_end=True)
    out_q = {float(a): np.asarray(v, dtype="float64") for a, v in levels.items()}
    return out_rates, out_q


def _assemble(
    *,
    label: str,
    mode: str,
    frame: pd.DataFrame,
    eval_mask: np.ndarray,
    static_mask: np.ndarray,
    loaded: Mapping[str, LoadedEntry],
    predictions: Mapping[str, Mapping[str, np.ndarray]],
    calibrators: Mapping[str, tuple[dict[str, cal.Calibrator], dict[str, cal.Calibrator]]],
    thresholds: Mapping[str, tuple[float | None, float | None]],
    b1_rates: Mapping[str, np.ndarray],
    b1_quantiles: Mapping[float, np.ndarray],
    event_threshold: float | None,
) -> fe.EvaluationInputs:
    classifiers: dict[str, fe.ClassifierRole] = {}
    quantiles: dict[str, fe.QuantileRole] = {}
    for role in loaded:
        rule = fl.ROLES[role]
        if rule.kind == "classifier":
            model_cal, b1_cal = calibrators[role]
            threshold, b1_threshold = thresholds[role]
            classifiers[role] = fe.ClassifierRole(
                role=role,
                target=rule.target,
                p=predictions[role][f"{rule.target}-lgbm"],
                calibrators=model_cal,
                b1_calibrators=b1_cal,
                threshold=threshold,
                b1_threshold=b1_threshold,
            )
        else:
            quantiles[role] = fe.QuantileRole(
                role=role, q={float(_alpha(k) or 0.0): v for k, v in predictions[role].items()}
            )
    return fe.assemble_inputs(
        label=label,
        mode=mode,
        dates=frame[SPLIT_DATE_COLUMN].to_numpy(),
        origin=frame["Origin"].astype(str).to_numpy(),
        local_minutes=frame["crs_dep_local_min"].to_numpy(dtype="float64", na_value=np.nan),
        targets=rm._targets(frame),
        eval_mask=eval_mask,
        static_mask=static_mask,
        classifiers=classifiers,
        quantiles=quantiles,
        b1_rates=b1_rates,
        b1_quantiles=b1_quantiles,
        event_threshold=event_threshold,
    )


def _new_folder(root: Path, prefix: str, created: dt.datetime) -> Path:
    folder = root / f"{prefix}-{created:%Y%m%dT%H%M%SZ}"
    if folder.exists():
        raise FileExistsError(f"Folder exists, will not overwrite: {folder}")
    return folder


def _write_outputs(folder: Path, output: dict[str, Any], mode: str) -> Path:
    clean = _jsonable(output)
    folder.mkdir(parents=True)
    path = folder / RESULTS_FILE[mode]
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (folder / SUMMARY_FILE[mode]).write_text(render(clean), encoding="utf-8")
    return folder


# ----------------------------------------------------------------------------
# the final test
# ----------------------------------------------------------------------------


def _predict_saved(
    loaded: Mapping[str, LoadedEntry],
    frame: pd.DataFrame,
    reader: LayerTableReader,
    history: ft.HistoryFeatures,
) -> dict[str, dict[str, np.ndarray]]:
    """Predictions of every locked model on ``frame`` (one matrix per contract / dropped-feature combination)."""
    out: dict[str, dict[str, np.ndarray]] = {role: {} for role in loaded}
    for (contract, dropped), roles in _combos(loaded).items():
        first = loaded[roles[0]].spec
        for role in roles:
            if loaded[role].spec["categories"] != first["categories"]:
                raise fl.LockVerificationError(f"{role}: category lists differ from {roles[0]} (same combination)")
        encoder = CategoryEncoder.from_dict(first["categories"])
        matrix = build_model_matrix(frame, kind=contract, reader=reader, encoder=encoder, history=history, drop=dropped)
        for role in roles:
            item = loaded[role]
            if matrix.feature_names != list(item.spec["feature_names"]):
                raise fl.LockVerificationError(f"{role}: rebuilt feature columns differ from model-spec.json")
            for key, path in item.model_paths.items():
                objective = item.results["models"][key].get("objective", "binary")
                predict = rp.load_predictor("lightgbm", path, matrix.feature_names, objective=objective)
                out[role][key] = predict(matrix.x)
        del matrix
        gc.collect()
    return out


def _development_checks(
    loaded: Mapping[str, LoadedEntry],
    frame: pd.DataFrame,
    predictions: Mapping[str, Mapping[str, np.ndarray]],
    b1_rates: Mapping[str, np.ndarray],
    b1_quantiles: Mapping[float, np.ndarray],
    base: Path,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """Val-B reproduction of every model and of B1, and of the frozen Platt calibrators (before the lock)."""
    problems: list[str] = []
    reproduction: dict[str, Any] = {}
    calibrators: dict[str, Any] = {}
    in_b = VAL_B.contains(frame[SPLIT_DATE_COLUMN])
    y_all = rm._targets(frame)
    for role, item in loaded.items():
        for key in item.model_paths:
            record = item.results["models"][key]
            target = str(record["target"])
            rows = in_b & np.isfinite(y_all[target])
            metric, run_value = rp._run_metric(item.results, record, "val_b")
            p = predictions[role][key][rows]
            y = y_all[target][rows]
            now = mt.pinball_loss(y, p, float(record["alpha"])) if target == tg.ARR_DELAY else mt.roc_auc(y, p)
            same = run_value is not None and abs(now - float(run_value)) <= rp.REPRODUCTION_TOLERANCE
            reproduction[f"{role}:{key}"] = {"metric": metric, "run": run_value, "now": now, "reproduces_run": same}
            if not same:
                problems.append(f"{role}: {key} does not reproduce the run's Val-B {metric} ({run_value} vs {now})")
        for target in tg.CLASSIFICATION_TARGETS:
            stored = (item.results["classification"].get(target) or {}).get("B1")
            if stored is None:
                continue
            rows = in_b & np.isfinite(y_all[target])
            now = mt.roc_auc(y_all[target][rows], b1_rates[target][rows])
            run_value = stored["sets"]["val_b"]["total"].get("roc_auc")
            same = run_value is not None and abs(now - float(run_value)) <= rp.REPRODUCTION_TOLERANCE
            reproduction[f"{role}:B1:{target}"] = {
                "metric": "roc_auc",
                "run": run_value,
                "now": now,
                "reproduces_run": same,
            }
            if not same:
                problems.append(f"{role}: B1 {target} does not reproduce the run's Val-B ROC-AUC")
        stored_q = (item.results.get("quantile", {}).get(tg.ARR_DELAY) or {}).get("B1")
        if stored_q is not None:
            rows = in_b & np.isfinite(y_all[tg.ARR_DELAY])
            now = mt.pinball_loss(y_all[tg.ARR_DELAY][rows], b1_quantiles[0.80][rows], 0.80)
            run_value = stored_q["sets"]["val_b"]["total"].get("pinball_q080")
            same = run_value is not None and abs(now - float(run_value)) <= rp.REPRODUCTION_TOLERANCE
            reproduction[f"{role}:B1:arr_delay"] = {
                "metric": "pinball_q080",
                "run": run_value,
                "now": now,
                "reproduces_run": same,
            }
            if not same:
                problems.append(f"{role}: B1 quantiles do not reproduce the run's Val-B pinball P80")
        if item.entry.calibrator is None:
            continue
        stored_cal = json.loads(item.entry.calibrator["file"].resolve(base).read_text(encoding="utf-8"))
        target = fl.ROLES[role].target
        rows = in_b & np.isfinite(y_all[target])
        y = y_all[target][rows]
        pairs = (
            ("model", item.entry.calibrator["key"], predictions[role][f"{target}-lgbm"][rows]),
            ("B1", item.entry.calibrator["b1_key"], b1_rates[target][rows]),
        )
        loaded_cal: dict[str, dict[str, cal.Calibrator]] = {}
        for who, key, p in pairs:
            methods = {m: cal.Calibrator.from_dict(d) for m, d in stored_cal[key].items() if "failed" not in d}
            refit = cal.fit_platt(y, p)
            frozen = methods.get(fe.STATIC_PROBABILITY)
            ok = (
                frozen is not None
                and frozen.n_fit == refit.n_fit
                and abs(float(frozen.intercept or 0.0) - float(refit.intercept or 0.0)) <= 1e-8
                and abs(float(frozen.slope or 0.0) - float(refit.slope or 0.0)) <= 1e-8
            )
            reproduction[f"{role}:calibrator:{who}"] = {
                "frozen": None if frozen is None else {"intercept": frozen.intercept, "slope": frozen.slope},
                "refit_on_val_b": {"intercept": refit.intercept, "slope": refit.slope, "n_fit": refit.n_fit},
                "reproduces_run": ok,
            }
            if not ok:
                problems.append(f"{role}: frozen Platt calibrator ({who}) is not the Val-B fit of this model")
            loaded_cal[who] = methods
        calibrators[role] = (loaded_cal["model"], loaded_cal["B1"])
    return problems, reproduction, calibrators


def run_final(
    manifest_path: Path,
    *,
    layer_root: Path | None = None,
    base: Path = PROJECT_ROOT,
    output_dir: Path | None = None,
    lock_file: Path | None = None,
    git: fl.GitProbe | None = None,
    now: dt.datetime | None = None,
) -> Path:
    """THE final test (module docstring). Returns the output folder."""
    started = time.perf_counter()
    created = now or dt.datetime.now(dt.UTC)
    lock = Path(lock_file) if lock_file is not None else FINAL_TEST_LOCK_FILE
    require_final_test_access(True, lock)  # existing guard: refused when the lock record exists
    test_period = get_period("final_test", allow_final_test=True, lock_file=lock)
    manifest = fl.load_manifest(manifest_path)
    problems = fl.verify_files(manifest, base)
    if not problems:
        problems += fl.check_entries_against_runs(manifest, base)
        problems += fl.check_role_rules(manifest, final=True, base=base)
        problems += fl.check_rehearsal(manifest, base)
    git_problems, git_info = fl.check_git(manifest, git or fl.GitProbe(base))
    problems += git_problems
    if problems:
        raise fl.LockVerificationError("Final test refused (nothing was read, no lock written): " + "; ".join(problems))
    assert manifest.acceptance is not None
    loaded = _load_entries(manifest, base)
    problems = _check_boosters(loaded)
    if problems:
        raise fl.LockVerificationError("Final test refused: " + "; ".join(problems))
    folder = _new_folder(Path(output_dir or FINAL_OUTPUT_DIR), "son-test", created)
    settings = _settings(loaded)
    fit: Period = settings["fit"]
    timings: dict[str, float] = {}
    clock = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal clock
        timings[name] = round(time.perf_counter() - clock, 1)
        clock = time.perf_counter()

    # --- development data only ---
    loaded_train = load_periods(
        layer_root, [fit], flight_columns=rp._TRAIN_FLIGHT_COLUMNS, label_columns=MODEL_LABEL_COLUMNS, hash_files=True
    )
    train = rm._slice(loaded_train.frame, fit)
    loaded_train.frame = pd.DataFrame()
    history = ft.HistoryFeatures(m=settings["m"], min_support=settings["min_support"], min_tail=settings["min_tail"])
    history.fit(train[list(HISTORY_INPUT_COLUMNS)], fit_end=fit.end)
    described = _jsonable(history.describe())
    for role, item in loaded.items():
        mismatch = rp.history_mismatches(item.spec["history"], described)
        if mismatch:
            problems.append(f"{role}: refitted history differs from the run: {'; '.join(mismatch[:5])}")
    b1_rate_tables, b1_quantile_table = _b1_tables(train, fit.end, settings)
    event_threshold = fe.event_rate_threshold(train[SPLIT_DATE_COLUMN], tg.target_values(train, tg.ARR_DEL15))
    del train
    gc.collect()
    lap("fit_window")
    context = context_period(test_period, VAL_B.end)
    loaded_context = load_periods(
        layer_root, [context], flight_columns=MODEL_FLIGHT_COLUMNS, label_columns=MODEL_LABEL_COLUMNS, hash_files=True
    )
    context_frame = rm._slice(loaded_context.frame, context)
    loaded_context.frame = pd.DataFrame()
    dev_reader = LayerTableReader(layer_root, hash_files=True)
    context_predictions = _predict_saved(loaded, context_frame, dev_reader, history)
    context_rates, context_quantiles = _b1_predict(b1_rate_tables, b1_quantile_table, context_frame)
    dev_problems, reproduction, calibrators = _development_checks(
        loaded, context_frame, context_predictions, context_rates, context_quantiles, base
    )
    problems += dev_problems
    run_files = [f for item in loaded.values() for f in item.results["data_fingerprint"]["files"]]
    read_files = [*loaded_train.files, *loaded_context.files, *dev_reader.files]
    problems += [f"layer: {p}" for p in rp._file_mismatches(run_files, read_files)]
    lap("development_checks")
    if problems:
        raise fl.LockVerificationError(
            "Final test refused after the development checks (no lock written, no final-test file opened): "
            + "; ".join(problems[:20])
        )
    leakage = fl.leakage_evidence(manifest, base)

    # --- the lock record, then the final-test data ---
    fl.write_lock_record(lock, fl.lock_record(manifest, git_info, created, f"{COMMAND} --final"))
    require_lock_written(lock)
    loaded_test = load_periods(
        layer_root,
        [test_period],
        flight_columns=MODEL_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=True,
        allow_final_test=True,
    )
    test_frame = rm._slice(loaded_test.frame, test_period)
    loaded_test.frame = pd.DataFrame()
    test_reader = LayerTableReader(layer_root, hash_files=True, allow_final_test=True, lock_file=lock)
    test_predictions = _predict_saved(loaded, test_frame, test_reader, history)
    test_rates, test_quantiles = _b1_predict(b1_rate_tables, b1_quantile_table, test_frame)
    lap("final_test_predictions")

    frame = pd.concat([context_frame, test_frame], ignore_index=True)
    eval_mask = np.r_[np.zeros(len(context_frame), dtype=bool), np.ones(len(test_frame), dtype=bool)]
    static_mask = VAL_B.contains(frame[SPLIT_DATE_COLUMN]) & ~eval_mask
    predictions = {
        role: {k: np.concatenate([context_predictions[role][k], test_predictions[role][k]]) for k in keys}
        for role, keys in context_predictions.items()
    }
    rates = {t: np.concatenate([context_rates[t], test_rates[t]]) for t in context_rates}
    quantile_levels = {a: np.concatenate([context_quantiles[a], test_quantiles[a]]) for a in context_quantiles}
    thresholds = {
        role: (item.entry.f1_threshold, item.entry.b1_f1_threshold)
        for role, item in loaded.items()
        if fl.ROLES[role].kind == "classifier"
    }
    inputs = _assemble(
        label="final test 2026-03..08",
        mode="final_test",
        frame=frame,
        eval_mask=eval_mask,
        static_mask=static_mask,
        loaded=loaded,
        predictions=predictions,
        calibrators=calibrators,
        thresholds=thresholds,
        b1_rates=rates,
        b1_quantiles=quantile_levels,
        event_threshold=event_threshold,
    )
    del frame, predictions, context_predictions, test_predictions
    gc.collect()
    evaluation = fe.evaluate(
        inputs,
        acceptance=manifest.acceptance,
        leakage=leakage,
        replicates=bs.DEFAULT_REPLICATES,
        seed=bs.DEFAULT_SEED,
        level=bs.CI_LEVEL,
        holm_alpha=manifest.holm_alpha,
        segment_min_n=settings["segment_min_n"],
    )
    lap("evaluation")
    output = {
        "metadata": {
            "mode": "final_test",
            "label": "SON TEST (tek seferlik)",
            "created_utc": created.isoformat(),
            "command": f"{COMMAND} --final",
            "manifest": {"path": fl._relative(manifest.path, base), "sha256": manifest.sha256},
            "lock_file": fl._relative(lock, base),
            "lock_sha256": fl.sha256_file(lock),
            "git": git_info,
            "library_versions": repro.library_versions(),
            "entries_fingerprint": fl.entries_fingerprint(manifest),
            "periods": {
                "fit": {"start": str(fit.start), "end": str(fit.end)},
                "context": {"start": str(context.start), "end": str(context.end)},
                "static_calibration": {"start": str(VAL_B.start), "end": str(VAL_B.end)},
                "final_test": {"start": str(test_period.start), "end": str(test_period.end)},
            },
            "event_rate_threshold": event_threshold,
            "final_test_files": fingerprint([*loaded_test.files, *test_reader.files]),
            "development_files_checked": len(read_files),
            "seconds_total": round(time.perf_counter() - started, 1),
            "timings_seconds": timings,
            "peak_rss_gb": rm._peak_rss_gb(),
        },
        "verification": {"reproduction": reproduction, "leakage": leakage},
        "blocks": {"final_test": evaluation},
    }
    return _write_outputs(folder, output, "final_test")


# ----------------------------------------------------------------------------
# the rehearsal
# ----------------------------------------------------------------------------


def _summary(calibrators: Mapping[str, cal.Calibrator]) -> dict[str, Any]:
    """The Platt calibrator without breakpoint lists (for the outputs)."""
    return {k: v for k, v in calibrators[fe.STATIC_PROBABILITY].to_dict().items() if k not in ("x", "y")}


def _fit_calibrators(y: np.ndarray, p: np.ndarray) -> dict[str, cal.Calibrator]:
    out = {fe.STATIC_PROBABILITY: cal.fit_platt(y, p)}  # primary: a failure stops the rehearsal loudly
    with contextlib.suppress(ValueError):  # isotonic is secondary
        out["isotonic"] = cal.fit_isotonic(y, p)
    return out


def _rehearsal_fold(
    periods: RehearsalPeriods,
    loaded: Mapping[str, LoadedEntry],
    settings: Mapping[str, Any],
    *,
    layer_root: Path | None,
    fit_day_fraction: float,
    num_threads: int,
    hash_files: bool,
) -> tuple[fe.EvaluationInputs, dict[str, Any]]:
    after = Period(f"{periods.fold}_after_fit", periods.early_stopping.start, periods.evaluation.end)
    data = load_periods(
        layer_root,
        [periods.fit, after],
        flight_columns=MODEL_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=hash_files,
    )
    train = rm._slice(data.frame, periods.fit)
    rest = rm._slice(data.frame, after)
    data.frame = pd.DataFrame()
    check_temporal_order(train[SPLIT_DATE_COLUMN], rest[SPLIT_DATE_COLUMN])
    encoder = CategoryEncoder().fit(train, fit_end=periods.fit.end)
    history = ft.HistoryFeatures(m=settings["m"], min_support=settings["min_support"], min_tail=settings["min_tail"])
    encoded = history.fit_transform_out_of_fold(
        train[list(HISTORY_INPUT_COLUMNS)], fit_end=periods.fit.end, n_blocks=settings["n_blocks"]
    )
    b1_rate_tables, b1_quantile_table = _b1_tables(train, periods.fit.end, settings)
    b1_rates, b1_quantiles = _b1_predict(b1_rate_tables, b1_quantile_table, rest)
    event_threshold = fe.event_rate_threshold(train[SPLIT_DATE_COLUMN], tg.target_values(train, tg.ARR_DEL15))
    y_train, y_rest = rm._targets(train), rm._targets(rest)
    fit_rows = (
        sample_days(train[SPLIT_DATE_COLUMN], fit_day_fraction, seed=settings["seed"])
        if fit_day_fraction < 1.0
        else np.ones(len(train), dtype=bool)
    )
    dates = rest[SPLIT_DATE_COLUMN]
    es_mask = periods.early_stopping.contains(dates)
    cal_mask = periods.calibration.contains(dates)
    eval_mask = periods.evaluation.contains(dates)
    reader = LayerTableReader(layer_root, hash_files=hash_files)
    predictions: dict[str, dict[str, np.ndarray]] = {role: {} for role in loaded}
    trained: dict[tuple[str, str], np.ndarray] = {}
    models: list[dict[str, Any]] = []
    for (contract, dropped), roles in _combos(loaded).items():
        m_train = build_model_matrix(
            train, kind=contract, reader=reader, encoder=encoder, history_frame=encoded, rows=fit_rows, drop=dropped
        )
        m_rest = build_model_matrix(rest, kind=contract, reader=reader, encoder=encoder, history=history, drop=dropped)
        for role in roles:
            item = loaded[role]
            if m_train.feature_names != list(item.spec["feature_names"]):
                raise fl.LockVerificationError(f"{role}: rehearsal feature columns differ from model-spec.json")
            config = item.config
            for key in item.model_paths:
                cache = (item.entry.run_id, key)
                if cache in trained:
                    predictions[role][key] = trained[cache]
                    continue
                task, target = _task(key, config)
                search_key = _QUANTILE_SEARCH_KEY if task.is_quantile else _BINARY_SEARCH_KEY
                tunable = item.results["tuning"]["selected"][search_key]["params"]
                params = gbm.make_params(
                    task, tunable, num_threads=num_threads, overrides=config.get("param_overrides") or {}
                )
                cap = int(config["num_boost_round"])
                if task.is_quantile and config.get("quantile_num_boost_round"):
                    cap = int(config["quantile_num_boost_round"])
                y_fit = y_train[target][fit_rows]
                fit_ok = np.isfinite(y_fit)
                valid = es_mask & np.isfinite(y_rest[target])
                model = gbm.train_model(
                    task,
                    m_train.x[fit_ok],
                    y_fit[fit_ok],
                    x_valid=m_rest.x[valid],
                    y_valid=y_rest[target][valid],
                    params=params,
                    feature_names=m_train.feature_names,
                    categorical_indices=m_train.categorical_indices,
                    num_boost_round=cap,
                    early_stopping_rounds=int(config["early_stopping_rounds"]),
                )
                trained[cache] = predictions[role][key] = gbm.predict(model, m_rest.x)
                models.append(
                    {
                        "role": role,
                        "run_id": item.entry.run_id,
                        "model": key,
                        "best_iteration": model.best_iteration,
                        "rounds_trained": model.rounds_trained,
                        "round_cap": cap,
                        "hit_round_cap": model.hit_round_cap,
                        "best_iteration_locked_model": item.entry.models[key][1],
                        "seconds": round(model.seconds, 1),
                        "n_train": model.n_train,
                        "n_early_stopping": model.n_valid,
                    }
                )
                del model
                gc.collect()
        del m_train, m_rest
        gc.collect()
    calibrators: dict[str, tuple[dict[str, cal.Calibrator], dict[str, cal.Calibrator]]] = {}
    thresholds: dict[str, tuple[float | None, float | None]] = {}
    for role in loaded:
        rule = fl.ROLES[role]
        if rule.kind != "classifier":
            continue
        rows = cal_mask & np.isfinite(y_rest[rule.target])
        y = y_rest[rule.target][rows]
        p, b1 = predictions[role][f"{rule.target}-lgbm"][rows], b1_rates[rule.target][rows]
        calibrators[role] = (_fit_calibrators(y, p), _fit_calibrators(y, b1))
        threshold, _ = mt.best_f1_threshold(y, p)
        b1_threshold, _ = mt.best_f1_threshold(y, b1)
        thresholds[role] = (
            threshold if np.isfinite(threshold) else None,
            b1_threshold if np.isfinite(b1_threshold) else None,
        )
    inputs = _assemble(
        label=f"rehearsal {periods.fold}",
        mode="rehearsal",
        frame=rest,
        eval_mask=eval_mask,
        static_mask=cal_mask,
        loaded=loaded,
        predictions=predictions,
        calibrators=calibrators,
        thresholds=thresholds,
        b1_rates=b1_rates,
        b1_quantiles=b1_quantiles,
        event_threshold=event_threshold,
    )
    info = {
        "periods": periods.to_dict(),
        "fit_day_fraction": fit_day_fraction,
        "rows": {"fit": int(fit_rows.sum()), "after_fit": len(rest), "evaluation": int(eval_mask.sum())},
        "models": models,
        "calibrators": {
            role: {"model_platt": _summary(model_cal), "B1_platt": _summary(b1_cal)}
            for role, (model_cal, b1_cal) in calibrators.items()
        },
        "thresholds": {role: {"model": t[0], "B1": t[1]} for role, t in thresholds.items()},
        "event_rate_threshold": event_threshold,
        "files": fingerprint([*data.files, *reader.files]),
    }
    return inputs, info


def run_rehearsal(
    manifest_path: Path,
    *,
    layer_root: Path | None = None,
    base: Path = PROJECT_ROOT,
    output_dir: Path | None = None,
    folds: Sequence[str] = REHEARSAL_FOLDS,
    roles: Sequence[str] | None = None,
    max_fit_months: int | None = None,
    fit_day_fraction: float = 1.0,
    num_threads: int | None = None,
    hash_files: bool = True,
    replicates: int = bs.DEFAULT_REPLICATES,
    now: dt.datetime | None = None,
) -> Path:
    """Rehearsal (module docstring): never the final test, never the lock. Returns the output folder."""
    started = time.perf_counter()
    created = now or dt.datetime.now(dt.UTC)
    unknown = [f for f in folds if f not in REHEARSAL_FOLDS]
    if unknown:
        raise ValueError(f"Rehearsal folds must be among {REHEARSAL_FOLDS}: {unknown}")
    if not 0.0 < fit_day_fraction <= 1.0:
        raise ValueError("fit_day_fraction must be in (0, 1]")
    manifest = fl.load_manifest(manifest_path)
    problems = fl.verify_files(manifest, base)
    if not problems:
        problems += fl.check_entries_against_runs(manifest, base)
        problems += fl.check_role_rules(manifest, final=False, base=base)
    if problems:
        raise fl.LockVerificationError("Rehearsal refused: " + "; ".join(problems))
    loaded = _load_entries(manifest, base, roles)
    settings = _settings(loaded)
    used = manifest.acceptance or fe.Acceptance()
    plan_base = dataclasses.replace(
        fe.Acceptance(),
        k5_segment_tolerance=used.k5_segment_tolerance,
        k5_segment_share_min=used.k5_segment_share_min,
        k5_segment_min_n=used.k5_segment_min_n,
    )
    folder = _new_folder(Path(output_dir or REHEARSAL_OUTPUT_DIR), "prova", created)
    threads = num_threads or rm._default_threads()
    leakage = fl.leakage_evidence(manifest, base) if manifest.leakage else None
    fold_inputs: list[fe.EvaluationInputs] = []
    fold_info: dict[str, Any] = {}
    evaluations: dict[str, Any] = {}
    timings: dict[str, float] = {}
    for fold in folds:
        clock = time.perf_counter()
        periods = rehearsal_periods(fold, max_fit_months)
        inputs, info = _rehearsal_fold(
            periods,
            loaded,
            settings,
            layer_root=layer_root,
            fit_day_fraction=fit_day_fraction,
            num_threads=threads,
            hash_files=hash_files,
        )
        evaluations[fold] = fe.evaluate(
            inputs,
            acceptance=used,
            leakage=leakage,
            replicates=replicates,
            seed=bs.DEFAULT_SEED,
            segment_min_n=settings["segment_min_n"],
        )
        fold_inputs.append(inputs)
        fold_info[fold] = info
        timings[fold] = round(time.perf_counter() - clock, 1)
    if len(fold_inputs) > 1:
        clock = time.perf_counter()
        pooled = fe.pool(fold_inputs, label=f"rehearsal pooled {'+'.join(folds)}")
        evaluations["pooled"] = fe.evaluate(
            pooled,
            acceptance=used,
            leakage=leakage,
            replicates=replicates,
            seed=bs.DEFAULT_SEED,
            segment_min_n=settings["segment_min_n"],
        )
        timings["pooled"] = round(time.perf_counter() - clock, 1)
    del fold_inputs
    gc.collect()
    pooled_name = "pooled" if "pooled" in evaluations else folds[-1]
    fingerprints = fl.entries_fingerprint(manifest)
    output = {
        "metadata": {
            "mode": "rehearsal",
            "label": "PROVA – son test DEĞİL (eğitim penceresi içindeki K3/K4 değerlendirme pencereleri)",
            "created_utc": created.isoformat(),
            "command": f"{COMMAND} --rehearsal",
            "manifest": {"path": fl._relative(manifest.path, base), "sha256": manifest.sha256},
            "roles": list(loaded),
            "entries_fingerprint": {role: fingerprints[role] for role in loaded},
            "git": repro.git_info(base),
            "library_versions": repro.library_versions(),
            "final_test_read": False,
            "lock_written": False,
            "smoke": max_fit_months is not None or fit_day_fraction < 1.0 or tuple(folds) != REHEARSAL_FOLDS,
            "max_fit_months": max_fit_months,
            "fit_day_fraction": fit_day_fraction,
            "bootstrap_replicates": replicates,
            "acceptance_used": used.to_dict(),
            "seconds_total": round(time.perf_counter() - started, 1),
            "timings_seconds": timings,
            "peak_rss_gb": rm._peak_rss_gb(),
            "caveat": "Hyperparameters were searched on these fold windows (run-20261119T182216Z): performance "
            "numbers are optimistic and are not results. The rehearsal checks the code path, the winter -> summer "
            "coverage / calibration behaviour and fixes the K3 / K5 tolerances (pre-registration d).",
        },
        "folds": fold_info,
        "blocks": evaluations,
        "rehearsal_checks": fe.rehearsal_checks(evaluations),
        "tolerance_proposal": fe.tolerance_proposal(evaluations[pooled_name], plan=plan_base)
        | {"from_block": pooled_name},
    }
    if replicates != bs.DEFAULT_REPLICATES:
        output["rehearsal_checks"]["passed"] = False
        output["rehearsal_checks"]["note"] = f"B = {replicates} != {bs.DEFAULT_REPLICATES}: not valid for the lock"
    return _write_outputs(folder, output, "rehearsal")


# ----------------------------------------------------------------------------
# Turkish summary
# ----------------------------------------------------------------------------

_VERDICT = {True: "geçti", False: "GEÇMEDİ", None: "değerlendirilemedi"}


def _ci(entry: Mapping[str, Any] | None, digits: int = 4) -> str:
    if not entry or entry.get("estimate") is None:
        return "-"
    low, high = entry.get("ci_low"), entry.get("ci_high")
    bounds = "" if low is None or high is None else f" [{low:+.{digits}f}; {high:+.{digits}f}]"
    return f"{entry['estimate']:+.{digits}f}{bounds}"


def _p(value: Any, replicates: int) -> str:
    if value is None:
        return "-"
    return f"< {1.0 / replicates:.3f}" if value == 0 else f"{value:.3f}"


def _block_lines(name: str, block: Mapping[str, Any]) -> list[str]:
    replicates = int(block["bootstrap"]["replicates"])
    lines = [
        f"## {name}: {block['label']}",
        "",
        f"- Günler: {block['days']['n']} ({block['days']['first']} .. {block['days']['last']}) · gün blok bootstrap "
        f"B = {replicates}, tohum {block['bootstrap']['seed']}, yüzdelik GA %{block['bootstrap']['level'] * 100:.0f}",
        f"- Tüm kabul ölçütleri geçti mi: **{'evet' if block['all_passed'] else 'hayır'}**",
        "",
        "### Kabul ölçütleri (plan §5.3)",
        "",
        "| Ölçüt | Sonuç | Tanım |",
        "|---|---|---|",
    ]
    for key, criterion in block["criteria"].items():
        lines.append(f"| {key} | {_VERDICT[criterion['passed']]} | {criterion['description']} |")
    lines += [
        "",
        "### Birincil aile (plan §5.2, Holm α = " + f"{block['holm']['alpha']})",
        "",
        "| # | Rol | Karşılaştırma | Δ [%95 GA] | p | p (Holm) | Anlamlı |",
        "|---|---|---|---|---|---|---|",
    ]
    for hid, row in block["holm"]["family"].items():
        entry = (block["comparisons"].get(row["role"]) or {}).get("vs_B1", {}).get(row["comparison"])
        lines.append(
            f"| {hid} | {row['role']} | {row['comparison']} | {_ci(entry)} | {_p(row['p_value'], replicates)} | "
            f"{_p(row['p_holm'], replicates)} | {'evet' if row['reject'] else 'hayır'} |"
        )
    weather = block["comparisons"].get("weather_contribution", {})
    lines += ["", "### Hava katkısı (plan §6; T2 − plan, aynı uçuşlar; ikincil)", ""]
    for target, entries in weather.items():
        if not isinstance(entries, Mapping):
            lines.append(f"- {target}: {entries}")
            continue
        parts = [f"{k} {_ci(v)}" for k, v in entries.items() if isinstance(v, Mapping)]
        lines.append(f"- {target}: " + " · ".join(parts))
    primary = block["classification"].get(fe.ROLE_ARR_DEL15_T2)
    if primary:
        lines += [
            "",
            "### ArrDel15 T2: olasılık kalitesi (aylık kayan Platt birincil, sabit Platt ikincil; sıralama metrikleri ham skorla)",
            "",
            "| Yöntem | Brier | BSS (aynı yöntemle B1) | Log-loss | ECE | CITL | Eğim |",
            "|---|---|---|---|---|---|---|",
        ]
        raw = primary["raw"]["model"]
        lines.append(
            f"| ham | {_format(raw.get('brier'))} | {_format(raw.get('brier_skill_score'))} | "
            f"{_format(raw.get('log_loss'))} | {_format(raw.get('ece'))} | "
            f"{_format(raw.get('calibration_in_the_large'))} | {_format(raw.get('calibration_slope'), 3)} |"
        )
        for method, entry in primary["probability"].items():
            m = entry["model"]
            lines.append(
                f"| {method} | {_format(m.get('brier'))} | {_format(m.get('brier_skill_score'))} | "
                f"{_format(m.get('log_loss'))} | {_format(m.get('ece'))} | "
                f"{_format(m.get('calibration_in_the_large'))} | {_format(m.get('calibration_slope'), 3)} |"
            )
        lines += [
            "",
            f"- ROC-AUC (ham) {_format(raw.get('roc_auc'))}, PR-AUC (ham) {_format(raw.get('pr_auc'))}, yaygınlık "
            f"{_format(primary['prevalence'])}; Origin × gün tabakalı AUC (keşifsel, M5): model "
            f"{_format(primary['stratified_auc_origin_day']['model']['auc'])}, B1 "
            f"{_format(primary['stratified_auc_origin_day']['B1']['auc'])}",
            "",
            "| Ay | n | Yaygınlık | CITL ham | CITL Platt | CITL kayan Platt | ROC-AUC ham |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in primary["monthly"]:
            lines.append(
                f"| {row['month']} | {row['n']} | {_format(row.get('prevalence'))} | {_format(row.get('citl_raw'))} | "
                f"{_format(row.get('citl_platt'))} | {_format(row.get('citl_platt_rolling'))} | "
                f"{_format(row.get('roc_auc_raw'))} |"
            )
    plan_q = block["quantile"].get(fe.ROLE_QUANTILES_PLAN)
    if plan_q:
        lines += [
            "",
            "### Plan kantilleri: conformal kapsama (birincil: aylık kayan)",
            "",
            "| Şema | P80 kapsama | P95 kapsama | Segment payı P80 | Segment payı P95 | Yetersiz ay (k > n) | "
            "%80 aralık (CQR) kapsama |",
            "|---|---|---|---|---|---|---|",
        ]
        for scheme in fe.SCHEMES:
            entry = plan_q["conformal"]["model"][scheme]
            insufficient = sorted({*entry["q080"]["months_insufficient"], *entry["q095"]["months_insufficient"]})
            lines.append(
                f"| {scheme} | {_format(entry['q080']['coverage'])} | {_format(entry['q095']['coverage'])} | "
                f"{_format(entry['q080']['segment_share_within_tolerance'])} | "
                f"{_format(entry['q095']['segment_share_within_tolerance'])} | {', '.join(insufficient) or '-'} | "
                f"{_format(entry[fe.INTERVAL_KEY]['coverage'])} |"
            )
        raw_q = plan_q["raw"]["model"]
        lines += [
            f"- Ham kapsama: P80 {_format(raw_q.get('coverage_q080'))}, P95 {_format(raw_q.get('coverage_q095'))} "
            "(statik = tek ofset; public = 2 ay gecikmeli 'kamu senaryosu', ikincil)",
            "",
            "| Ay | n | P80 ham | P80 kayan | P80 statik | P80 public | P95 ham | P95 kayan | P95 statik | "
            "P95 public |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in plan_q["monthly"]:
            lines.append(
                f"| {row['month']} | {row['n']} | {_format(row.get('coverage_raw_q080'))} | "
                f"{_format(row.get('coverage_rolling_q080'))} | {_format(row.get('coverage_static_q080'))} | "
                f"{_format(row.get('coverage_public_q080'))} | {_format(row.get('coverage_raw_q095'))} | "
                f"{_format(row.get('coverage_rolling_q095'))} | {_format(row.get('coverage_static_q095'))} | "
                f"{_format(row.get('coverage_public_q095'))} |"
            )
    lines += ["", "### İkincil karşılaştırmalar (B1'e göre; keşifsel, Holm dışı)", ""]
    for role, entry in block["comparisons"].items():
        if role == "weather_contribution" or any(role == r for _, r, _ in fe.HOLM_FAMILY):
            continue
        parts = [f"{k} {_ci(v)}" for k, v in entry.get("vs_B1", {}).items()]
        lines.append(f"- `{role}`: " + " · ".join(parts))
    return [*lines, ""]


def render(output: Mapping[str, Any]) -> str:
    """Turkish markdown; every number from ``output``. Criteria are written as passed / not passed, nothing else."""
    meta = output["metadata"]
    final = meta["mode"] == "final_test"
    lines: list[str] = []
    if final:
        lines += [
            "# SON TEST SONUÇLARI (tek seferlik, 2026-03..08)",
            "",
            f"- Oluşturma (UTC): {meta['created_utc']} · kilit kaydı: `{meta['lock_file']}` "
            f"(sha256 `{meta['lock_sha256'][:12]}`) · kilit girdisi: `{meta['manifest']['path']}`",
            f"- git: `{meta['git'].get('head')}` (kirli: {meta['git'].get('dirty')}) · süre {meta['seconds_total']} sn",
            "- Kurallar: `experiments/son-test-on-kayit.md` (önceden kayıt). Olasılıklar Platt (Val-B'de fit), "
            "isotonic ikincil; sıralama metrikleri ham skorla. Sonuçlar olduğu gibi yazılır; testte ayar yapılmaz.",
            "- Val-B sayıları (ör. iptal D2'nin Val-B AUC'si) başlık metriği değildir; başlık yalnızca bu tablodur.",
            "",
        ]
    else:
        lines += [
            "> **PROVA – SON TEST DEĞİL.** Değerlendirme pencereleri eğitim penceresinin içinde (K3: 2025-03..05, "
            "K4: 2025-06..08); modeller katın öncesinde yeniden eğitildi. Parametreler bu kat pencerelerinde arandığı "
            "için performans sayıları iyimserdir ve sonuç değildir.",
            "",
            "# Son test provası",
            "",
            f"- Oluşturma (UTC): {meta['created_utc']} · kilit girdisi: `{meta['manifest']['path']}` · roller: "
            f"{', '.join(meta['roles'])} · B = {meta['bootstrap_replicates']} · süre {meta['seconds_total']} sn",
            f"- Son test okundu mu: {meta['final_test_read']} · kilit yazıldı mı: {meta['lock_written']}",
            "",
            "## Prova kontrolleri (kod yolu; performans kapı değildir)",
            "",
        ]
        checks = output["rehearsal_checks"]
        lines.append(f"- Genel: **{'geçti' if checks['passed'] else 'GEÇMEDİ'}** {checks.get('note', '')}".rstrip())
        for name, check in checks["blocks"].items():
            failed = [k for k, v in check["criteria_computed"].items() if not v]
            verdict = "geçti" if check["passed"] else "GEÇMEDİ"
            lines.append(
                f"- {name}: {verdict} (hesaplanamayan ölçüt: {failed or 'yok'}; "
                f"Holm tam: {check['holm_complete_and_monotone']}; "
                f"GA'lar sonlu: {check['bootstrap_intervals_finite']}; "
                f"yetersiz conformal ayı: {check['rolling_conformal_months_insufficient'] or 'yok'})"
            )
        proposal = output["tolerance_proposal"]
        lines += ["", "## K3 / K5 tolerans önerisi (önceden kayıt d: max(plan, bootstrap yarı genişliği ↑0,005))", ""]
        if proposal.get("acceptance") is None:
            lines.append(f"- Öneri yok: {proposal.get('reason')}")
        else:
            acc = proposal["acceptance"]
            k3 = acc["K3"]
            lines += [
                f"- Kaynak blok: {proposal['from_block']} · yarı genişlikler: "
                + ", ".join(f"{k} {_format(v)}" for k, v in proposal["half_widths"].items()),
                f"- K3: |CITL| ≤ {k3['citl_abs_max']}, eğim [{k3['slope_min']}; {k3['slope_max']}]",
                f"- K5: P80 {acc['K5']['q080']}, P95 {acc['K5']['q095']} (segment kuralı değişmez)",
            ]
        lines.append("")
        for fold, info in output.get("folds", {}).items():
            p = info["periods"]
            lines.append(
                f"- {fold}: fit {p['fit']['start']}..{p['fit']['end']}, erken durdurma {p['early_stopping']['start']}.."
                f"{p['early_stopping']['end']}, kalibrasyon {p['calibration']['start']}..{p['calibration']['end']}, "
                f"değerlendirme {p['evaluation']['start']}..{p['evaluation']['end']} · {len(info['models'])} model"
            )
        lines.append("")
    for name, block in output["blocks"].items():
        lines += _block_lines(name, block)
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-time final test (--final) or its rehearsal (--rehearsal).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--final", action="store_true", help="THE final test: reads 2026-03..08 once, writes the lock.")
    mode.add_argument("--rehearsal", action="store_true", help="Rehearsal on K3 / K4 (2025-03..08); no lock.")
    parser.add_argument("--manifest", type=Path, required=True, help="Freeze manifest (final_lock).")
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--folds", nargs="+", choices=REHEARSAL_FOLDS, default=None, help="Rehearsal only.")
    parser.add_argument("--roles", nargs="+", default=None, help="Rehearsal only: a subset of the manifest roles.")
    parser.add_argument("--max-fit-months", type=int, default=None, help="Rehearsal smoke only.")
    parser.add_argument("--fit-day-fraction", type=float, default=None, help="Rehearsal only: whole-day sample.")
    parser.add_argument("--num-threads", type=int, default=None, help="Rehearsal only (training threads).")
    parser.add_argument("--no-hash", action="store_true", help="Rehearsal only: sizes instead of sha256.")
    args = parser.parse_args(argv)
    rehearsal_only = {
        "--folds": args.folds,
        "--roles": args.roles,
        "--max-fit-months": args.max_fit_months,
        "--fit-day-fraction": args.fit_day_fraction,
        "--num-threads": args.num_threads,
        "--no-hash": args.no_hash or None,
    }
    if args.final:
        given = [k for k, v in rehearsal_only.items() if v is not None]
        if given:
            parser.error(f"{given} are rehearsal options; the final test has no options to tune")
        folder = run_final(args.manifest, layer_root=args.layer_dir, output_dir=args.output_dir)
        mode_name = "final_test"
    else:
        folder = run_rehearsal(
            args.manifest,
            layer_root=args.layer_dir,
            output_dir=args.output_dir,
            folds=tuple(args.folds or REHEARSAL_FOLDS),
            roles=args.roles,
            max_fit_months=args.max_fit_months,
            fit_day_fraction=args.fit_day_fraction or 1.0,
            num_threads=args.num_threads,
            hash_files=not args.no_hash,
        )
        mode_name = "rehearsal"
    print(f"Results: {folder / RESULTS_FILE[mode_name]}\nSummary: {folder / SUMMARY_FILE[mode_name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
