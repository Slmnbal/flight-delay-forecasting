"""Main models (plan sections 4.1 - 4.3) on Val-A / Val-B against B1. NEVER the final test.

Usage (from the project root ``projects/havayolu-ds/``):
    python -m flight_delay.modeling.run_models --max-train-months 3 --tuning-trials 2 --tuning-budget-min 5 \\
        --num-boost-round 200 --mlflow off                                   # smoke run
    python -m flight_delay.modeling.run_models                                # full run (T2 contract)
    python -m flight_delay.modeling.run_models --contract plan               # plan contract (no weather; OR source)
    python -m flight_delay.modeling.run_models --contract oracle --oracle-experiment   # upper-bound experiment only

What it does (one fit window = the training period, plan 1.2: no refit on Val-A):
1. Split guard: only train / Val-A / Val-B (and the rolling folds inside train) are read; there is no final-test
   option, the loader refuses final-test periods and the side-table reader refuses final-test months.
2. Hyperparameter search (plan 4.3): ``ParameterSampler`` candidates evaluated on the rolling folds K3 / K4. Per fold:
   category lists and history statistics are fitted on the fold's fit window only (out-of-fold for its rows), the
   model is fitted on a 25 % whole-day sample of the fit window, early-stopped and scored on the fold's evaluation
   window (mean log-loss for ArrDel15; mean P80 pinball for the quantiles). Small and time-limited: ``--tuning-trials``
   candidates or ``--tuning-budget-min`` minutes, whichever ends first (a started trial is finished).
3. Final fit on the whole training window; number of trees by early stopping on **Val-A** (patience 100, plan 4.3).
   Val-B is NOT used for early stopping or selection: it only chooses the F1 threshold (plan 5.1) and later the
   calibration / conformal window. Consequence: LightGBM's Val-A numbers are slightly optimistic (Val-A chose the
   number of trees); Val-B is the cleaner comparison. L does not use Val-A at all.
4. Models: LightGBM binary ArrDel15 and cancellation (cancellation reuses the ArrDel15 search result - assumption,
   to stay within the budget), LightGBM quantile P50 / P80 / P95 on completed flights (all three use the P80 search
   result, plan 4.3), logistic baseline L for both classification targets (day-sampled fit, plan 4.1).
   Quantile crossing is fixed by sorting each row (plan 3.3); raw and sorted crossing rates are reported.
5. Same metric code as the baselines (``metrics``), B1 recomputed on the same rows with the same code as
   ``run_baselines`` (should match ``experiments/baselines/run-*/``), segments Origin / hour_block / month (no carrier
   dimension, plan 7), gain importance per model with the > 50 % single-feature alarm. That alarm is stage 1
   (suspicion) of the leakage rule; the decision is stage 2 (``importance``: Val-B permutation + time travel test),
   either in the same run (``--permutation``) or later on the saved run without retraining
   (``python -m flight_delay.modeling.run_permutation --run-id run-...``).
   L clips its numeric inputs to the fit-sample range (``logistic.RangeClipper``; ``--logistic-no-clip`` = step-2).
6. Outputs: ``experiments/models/run-<UTC>/model-results.json`` + ``model-ozet.md`` (Turkish, difference table vs
   B1); model files in ``deliverables/models/run-<UTC>/`` (LightGBM text + pickled sklearn Pipelines + model-spec.json;
   meant to be git-ignored: the run records ``git check-ignore`` for that folder). Oracle runs go to an ``oracle/``
   subfolder, are labelled in every output and use separate MLflow topics (plan 6).

Options added after run-20261119T182216Z (all OFF by default, so a default run is unchanged; decisions and evidence:
``experiments/kalibrasyon-conformal-kararlari.md``):
- ``--interval-models``: also train the alpha 0.10 / 0.90 quantile models (plan 4.2) and B1's 0.10 / 0.90 quantiles;
  every quantile block then carries ``interval80_coverage`` / ``interval80_mean_width_min`` (plan 5.1; required by the
  ``arr-delay-quantile`` MLflow topic in ``mlops/project.yaml``, so MLflow logging of quantiles needs this option). The
  interval ends are sorted as a pair, separately from P50/P80/P95, so the main quantiles stay comparable with earlier
  runs.
- ``--quantile-num-boost-round N``: round cap of the quantile models only (q050 hit the 2000 cap); ``hit_round_cap`` is
  now computed from the rounds actually trained (see ``gbm``).
- ``--cancel-early-stopping-metric {binary_logloss,auc,average_precision}``: early stopping metric of the cancellation
  LightGBM (still on Val-A); ``--record-curves`` keeps the Val-A curves (+ AUC / average precision for the binary models)
  and, for the binary models, Val-A metrics by month at fixed rounds (diagnosis of the 15-round stop).
- ``--drop-date-features``: leave ``matrix.DATE_FEATURES`` out of every matrix (permutation finding; experiment only).
- ``--tuning-from-run RUN_ID``: no search; reuse the parameters another run selected (same contract), so an experiment
  changes one thing at a time and saves the search time. ``--tuning-from-other-contract`` allows a run of ANOTHER
  contract as the source (decision M3 2026-11-21 item 1: the plan-contract models use the T2 search result of
  run-20261119T182216Z); the source contract is recorded in ``tuning.from_run_contract``.
Calibration and conformal adjustment run AFTER a run, on its saved models: ``python -m
flight_delay.modeling.run_calibration --run-id run-...`` (Val-B only).

Rough cost (NOT measured; the run records real seconds and peak RSS): ~11.4 M rows read; training matrix
~9.1 M x ~65 float32 = ~2.4 GB, Val-A + Val-B ~0.6 GB, one training-row copy per model (~2.4 GB) plus LightGBM bins
(~0.6 GB): peak roughly 7-9 GB on the full T2 run. Time is dominated by LightGBM: tuning <= budget (default 45 min),
5 final models on ~9 M rows up to 2000 rounds each, i.e. tens of minutes to ~2 h depending on where early stopping
lands. Use the smoke options first.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import hashlib
import importlib.util
import json
import math
import os
import pickle
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import LeakageError
from flight_delay.data.layer import DEFAULT_LAYER_DIR
from flight_delay.mlops import reproducibility as repro
from flight_delay.modeling import features as ft
from flight_delay.modeling import gbm
from flight_delay.modeling import importance as imp
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import targets as tg
from flight_delay.modeling.baselines import (
    _classification_segments,
    _clean_dict,
    _quantile_segments,
    make_quantile_baseline,
    make_rate_baseline,
)
from flight_delay.modeling.categories import CategoryEncoder
from flight_delay.modeling.history import DEFAULT_M, DEFAULT_MIN_SUPPORT, DEFAULT_MIN_TAIL
from flight_delay.modeling.loading import fingerprint, load_periods
from flight_delay.modeling.logistic import DEFAULT_CLIP_QUANTILE, LogisticModel, fit_logistic
from flight_delay.modeling.matrix import (
    DATE_FEATURES,
    HISTORY_INPUT_COLUMNS,
    MODEL_FLIGHT_COLUMNS,
    MODEL_LABEL_COLUMNS,
    LayerTableReader,
    ModelMatrix,
    build_model_matrix,
    sample_days,
    segment_keys,
)
from flight_delay.modeling.run_baselines import _format, _jsonable
from flight_delay.modeling.splits import (
    SPLIT_DATE_COLUMN,
    TRAIN,
    TRAIN_EVAL_EMBARGO_DAYS,
    VAL_A,
    VAL_B,
    Period,
    check_temporal_order,
    get_fold,
    trim_end,
    validate_layout,
)
from flight_delay.paths import PROJECT_ROOT

__all__ = [
    "CURVE_CHECKPOINTS",
    "DEFAULT_MODEL_DIR",
    "DEFAULT_OUTPUT_DIR",
    "EARLY_STOPPING_SET",
    "EVALUATION_SETS",
    "MODEL_CHOICES",
    "RESULTS_NAME",
    "SUMMARY_NAME",
    "THRESHOLD_SET",
    "RunConfig",
    "check_contract_option",
    "history_factory",
    "last_months",
    "leakage_banner",
    "load_selected_parameters",
    "main",
    "plan_periods",
    "quantile_levels",
    "render_summary",
    "review_permutations",
    "run",
]

EVALUATION_SETS = ("val_a", "val_b")
EARLY_STOPPING_SET = "val_a"  # plan 4.3: number of trees by early stopping on A
THRESHOLD_SET = "val_b"  # plan 5.1: F1 threshold chosen on B
MODEL_CHOICES = ("arr_del15", "cancelled", "quantiles", "logistic")
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "experiments" / "models"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "deliverables" / "models"
RESULTS_NAME = "model-results.json"
SUMMARY_NAME = "model-ozet.md"
_CLASSIFICATION_DELTAS = ("roc_auc", "pr_auc", "brier", "log_loss", "ece", "calibration_in_the_large")
_MLFLOW_TOPICS = {tg.ARR_DEL15: "arrdel15", tg.CANCELLED: "cancelled", tg.ARR_DELAY: "arr-delay-quantile"}
# rounds at which --record-curves scores the binary models on Val-A by month (15 = where cancellation stopped)
CURVE_CHECKPOINTS: tuple[int, ...] = (10, 15, 25, 50, 100, 200, 400, 800, 1600)
_INTERVAL_NAME = mt.interval_key(*tg.INTERVAL_LEVELS)


def _default_threads() -> int:
    return min(8, os.cpu_count() or 1)


@dataclass(frozen=True)
class RunConfig:
    """All options of a run (recorded in the results). Defaults follow the plan; "assumption" where it is silent."""

    contract: str = "T2"
    oracle_experiment: bool = False
    max_train_months: int | None = None  # smoke: keep only the last N months of every fit window
    models: tuple[str, ...] = MODEL_CHOICES
    tuning: bool = True
    tuning_trials: int = 8  # plan 4.3 proposes 30; kept small on purpose (task: small, time-limited)
    tuning_budget_minutes: float = 45.0
    tuning_folds: tuple[str, ...] = ("K3", "K4")  # plan 4.3
    tuning_day_fraction: float = 0.25  # plan 4.3: whole days, 25 %
    tuning_num_boost_round: int = 1000  # assumption
    tuning_early_stopping_rounds: int = 50  # assumption (final fit: 100, plan 4.3)
    num_boost_round: int = 2000  # assumption (cap; the results say whether it was hit)
    early_stopping_rounds: int = 100  # plan 4.3
    num_threads: int = field(default_factory=_default_threads)
    logistic_day_fraction: float = 0.15  # assumption (memory: dense one-hot + scaled numerics)
    logistic_c: float = 1.0
    logistic_max_iter: int = 500
    logistic_clip_quantile: float | None = DEFAULT_CLIP_QUANTILE  # None = step-2 behaviour (no fit-range clipping)
    permutation: bool = False  # stage-2 leakage review in the same run (also: python -m ...run_permutation)
    permutation_max_rows: int = imp.DEFAULT_MAX_ROWS
    permutation_repeats: int = imp.DEFAULT_REPEATS
    permutation_scheme: str = "rows"
    time_travel: bool = True  # only used with permutation
    m: float = DEFAULT_M
    min_support: int = DEFAULT_MIN_SUPPORT
    min_tail: int = DEFAULT_MIN_TAIL
    n_blocks: int = 5  # plan 2.4 item 2
    segment_min_n: int = 500
    embargo_days: int = TRAIN_EVAL_EMBARGO_DAYS
    seed: int = 42
    param_overrides: Mapping[str, Any] = field(default_factory=dict)  # tests only (tiny data)
    # --- options after run-20261119T182216Z (defaults = the earlier behaviour) ---
    interval_models: bool = False  # alpha 0.10 / 0.90 models + interval80 metrics (plan 4.2 / 5.1)
    quantile_num_boost_round: int | None = None  # round cap of the quantile models; None = num_boost_round
    cancel_early_stopping_metric: str = "binary_logloss"  # plan 4.3 objective metric; alternatives: auc, avg. precision
    record_curves: bool = False  # Val-A curves + month checkpoints of the binary models (diagnostics)
    drop_features: tuple[str, ...] = ()  # e.g. matrix.DATE_FEATURES (--drop-date-features)
    tuning_from_run: str | None = None  # reuse another run's selected parameters (no search)
    tuning_from_other_contract: bool = False  # the --tuning-from-run source may have another contract (plan models)


def quantile_levels(config: RunConfig) -> tuple[float, ...]:
    """Quantile levels trained in a run: P50/P80/P95 (+ the 80 % interval ends with ``interval_models``)."""
    return tuple(sorted((*tg.QUANTILE_LEVELS, *(tg.INTERVAL_LEVELS if config.interval_models else ()))))


def load_selected_parameters(
    run_id: str, output_dir: Path, contract: str, *, allow_other_contract: bool = False
) -> dict[str, Any]:
    """``tuning.selected`` of an earlier run (``--tuning-from-run``); its contract must be the same unless
    ``allow_other_contract`` (``--tuning-from-other-contract``)."""
    path = output_dir / run_id / RESULTS_NAME
    if not path.is_file():
        raise FileNotFoundError(f"No results of {run_id} in {output_dir} (needed by --tuning-from-run)")
    stored = json.loads(path.read_text(encoding="utf-8"))
    source_contract = stored["metadata"]["contract"]
    if source_contract != contract and not allow_other_contract:
        raise ValueError(
            f"{run_id} used contract {source_contract!r}, this run {contract!r} "
            "(pass --tuning-from-other-contract to reuse it on purpose)"
        )
    label = f"from {run_id}" if source_contract == contract else f"from {run_id} (contract {source_contract})"
    return {
        key: {"params": dict(block["params"]), "trial": block.get("trial"), "selected_by": label}
        for key, block in stored["tuning"]["selected"].items()
    }


def _check_new_options(cfg: RunConfig, mlflow_mode: str) -> None:
    if cfg.cancel_early_stopping_metric not in gbm.BINARY_EARLY_STOPPING_METRICS:
        raise ValueError(f"cancel_early_stopping_metric must be one of {gbm.BINARY_EARLY_STOPPING_METRICS}")
    if cfg.quantile_num_boost_round is not None and cfg.quantile_num_boost_round < 1:
        raise ValueError("quantile_num_boost_round must be >= 1")
    if cfg.tuning_from_other_contract and not cfg.tuning_from_run:
        raise ValueError("tuning_from_other_contract needs tuning_from_run (--tuning-from-run RUN_ID)")
    if (
        "quantiles" in cfg.models
        and not cfg.interval_models
        and (mlflow_mode == "on" or (mlflow_mode == "auto" and importlib.util.find_spec("mlflow") is not None))
    ):
        # fail before hours of training, not in the MLflow contract check at the very end
        raise ValueError(
            "The MLflow topic arr-delay-quantile requires interval80 metrics (mlops/project.yaml): pass "
            "--interval-models, or --mlflow off."
        )


def check_contract_option(contract: str, oracle_experiment: bool) -> None:
    """Oracle weather needs BOTH ``--contract oracle`` and ``--oracle-experiment`` (default off, plan 6)."""
    if contract not in ft.CONTRACT_KINDS:
        raise ValueError(f"contract must be one of {ft.CONTRACT_KINDS}: {contract!r}")
    if contract == "oracle" and not oracle_experiment:
        raise LeakageError(
            "The oracle contract uses weather that is NOT available at forecast time; it is an upper-bound experiment "
            "only and needs the explicit --oracle-experiment flag (plan section 6)."
        )
    if oracle_experiment and contract != "oracle":
        raise ValueError("--oracle-experiment is only meaningful with --contract oracle")


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def last_months(period: Period, n: int | None) -> Period:
    """The last ``n`` calendar months of a fit window (smoke runs); the period itself if ``n`` is None."""
    if n is None:
        return period
    if n < 1:
        raise ValueError("max_train_months must be >= 1")
    year, month = _shift_month(period.end.year, period.end.month, -(n - 1))
    start = max(period.start, dt.date(year, month, 1))
    return period if start == period.start else Period(f"{period.name}_last{n}m", start, period.end)


def plan_periods(config: RunConfig) -> tuple[Period, dict[str, Period], list[tuple[str, Period, Period]]]:
    """(fit window, {val_a, val_b}, [(fold, fold fit, fold evaluation)]). Never the final test."""
    fit = last_months(trim_end(TRAIN, config.embargo_days), config.max_train_months)
    evaluations = {"val_a": VAL_A, "val_b": VAL_B}
    folds: list[tuple[str, Period, Period]] = []
    if config.tuning:
        for name in config.tuning_folds:
            fold = get_fold(name)
            fold_fit = last_months(trim_end(fold.fit, config.embargo_days), config.max_train_months)
            folds.append((name, fold_fit, fold.evaluation))
    return fit, evaluations, folds


def _peak_rss_gb() -> float | None:
    """Peak resident memory of this process (macOS reports bytes, Linux KiB)."""
    try:
        import resource
    except ImportError:  # pragma: no cover - not on Unix
        return None
    peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return round(peak * (1.0 if sys.platform == "darwin" else 1024.0) / 1e9, 3)


def _git_ignored(path: Path) -> bool | None:
    """True / False from ``git check-ignore``; None if git is not available."""
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", str(path)], cwd=PROJECT_ROOT, capture_output=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(completed.returncode)


def _slice(frame: pd.DataFrame, period: Period) -> pd.DataFrame:
    return frame.loc[period.contains(frame[SPLIT_DATE_COLUMN])].reset_index(drop=True)


def _targets(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    return {t: tg.target_values(frame, t) for t in (tg.ARR_DEL15, tg.CANCELLED, tg.ARR_DELAY)}


def _fit_history(frame: pd.DataFrame, fit_end: dt.date, config: RunConfig) -> tuple[ft.HistoryFeatures, pd.DataFrame]:
    history = ft.HistoryFeatures(m=config.m, min_support=config.min_support, min_tail=config.min_tail)
    encoded = history.fit_transform_out_of_fold(
        frame[list(HISTORY_INPUT_COLUMNS)], fit_end=fit_end, n_blocks=config.n_blocks
    )
    return history, encoded


def history_factory(m: float, min_support: int, min_tail: int) -> Callable[[], ft.HistoryFeatures]:
    """Unfitted ``HistoryFeatures`` with a run's settings (time travel test, post-hoc permutation)."""
    return partial(ft.HistoryFeatures, m=m, min_support=min_support, min_tail=min_tail)


def review_permutations(
    permutation_results: Mapping[str, Any],
    model_records: Mapping[str, Any],
    time_travel: Mapping[str, Any] | None,
    contract_json: Mapping[str, Any],
) -> dict[str, Any]:
    """Two-stage review of every model with a permutation result; models that were not permuted but raised the gain
    alarm are reviewed too (verdict 'undecided')."""
    knowledge = {str(f["name"]): str(f["knowledge_time"]) for f in contract_json["features"]}
    reviews: dict[str, Any] = {}
    for key, record in model_records.items():
        if "skipped" in record or (key not in permutation_results and not record.get("gain_importance")):
            continue
        reviews[key] = imp.review_model(
            key,
            gain_importance=record.get("gain_importance"),
            permutation=permutation_results.get(key),
            time_travel=time_travel,
            knowledge=knowledge,
        )
    return imp.review_run(reviews)


# ----------------------------------------------------------------------------
# hyperparameter search on the rolling folds
# ----------------------------------------------------------------------------


@dataclass
class _Fold:
    name: str
    fit: Period
    evaluation: Period
    fit_matrix: ModelMatrix
    eval_matrix: ModelMatrix
    y_fit: dict[str, np.ndarray]
    y_eval: dict[str, np.ndarray]
    sampled_days: int


def _prepare_fold(
    frame: pd.DataFrame, name: str, fit: Period, evaluation: Period, config: RunConfig, reader: LayerTableReader
) -> _Fold:
    fit_frame = _slice(frame, fit)
    eval_frame = _slice(frame, evaluation)
    check_temporal_order(fit_frame[SPLIT_DATE_COLUMN], eval_frame[SPLIT_DATE_COLUMN], embargo_days=config.embargo_days)
    encoder = CategoryEncoder().fit(fit_frame, fit_end=fit.end)  # fold's own lists: preprocessing per fit window
    history, encoded = _fit_history(fit_frame, fit.end, config)
    sample = sample_days(fit_frame[SPLIT_DATE_COLUMN], config.tuning_day_fraction, seed=config.seed)
    fit_matrix = build_model_matrix(
        fit_frame,
        kind=config.contract,
        reader=reader,
        encoder=encoder,
        history_frame=encoded,
        rows=sample,
        drop=config.drop_features,
    )
    eval_matrix = build_model_matrix(
        eval_frame, kind=config.contract, reader=reader, encoder=encoder, history=history, drop=config.drop_features
    )
    y_fit = {t: v[sample] for t, v in _targets(fit_frame).items()}
    days = int(pd.to_datetime(fit_frame.loc[sample, SPLIT_DATE_COLUMN]).dt.normalize().nunique())
    return _Fold(name, fit, evaluation, fit_matrix, eval_matrix, y_fit, _targets(eval_frame), days)


def _fold_score(
    fold: _Fold, task: gbm.GBMTask, target: str, params: dict[str, Any], config: RunConfig
) -> dict[str, Any]:
    y_fit, y_eval = fold.y_fit[target], fold.y_eval[target]
    fit_rows, eval_rows = np.isfinite(y_fit), np.isfinite(y_eval)
    model = gbm.train_model(
        task,
        fold.fit_matrix.x[fit_rows],
        y_fit[fit_rows],
        x_valid=fold.eval_matrix.x[eval_rows],
        y_valid=y_eval[eval_rows],
        params=params,
        feature_names=fold.fit_matrix.feature_names,
        categorical_indices=fold.fit_matrix.categorical_indices,
        num_boost_round=config.tuning_num_boost_round,
        early_stopping_rounds=config.tuning_early_stopping_rounds,
    )
    predicted = gbm.predict(model, fold.eval_matrix.x[eval_rows])
    if task.is_quantile:
        assert task.alpha is not None
        score = mt.pinball_loss(y_eval[eval_rows], predicted, task.alpha)
    else:
        score = mt.log_loss(y_eval[eval_rows], predicted)
    return {
        "fold": fold.name,
        "score": score,
        "best_iteration": model.best_iteration,
        "hit_round_cap": model.hit_round_cap,
        "seconds": round(model.seconds, 2),
        "n_fit": model.n_train,
        "n_eval": model.n_valid,
    }


def _search(
    frame: pd.DataFrame,
    folds_plan: Sequence[tuple[str, Period, Period]],
    config: RunConfig,
    reader: LayerTableReader,
    tasks: Mapping[str, tuple[gbm.GBMTask, str]],
) -> dict[str, Any]:
    """Random search on the folds; returns the trials and the selected tunable parameters per search key."""
    started = time.perf_counter()
    folds = [_prepare_fold(frame, name, fit, evaluation, config, reader) for name, fit, evaluation in folds_plan]
    prepared_seconds = time.perf_counter() - started
    candidates = gbm.candidate_parameters(config.tuning_trials, seed=config.seed)
    budget = config.tuning_budget_minutes * 60.0
    trials: list[dict[str, Any]] = []
    stopped_by_budget = False
    for index, candidate in enumerate(candidates):
        if time.perf_counter() - started > budget:
            stopped_by_budget = True
            break
        trial: dict[str, Any] = {"trial": index, "params": candidate}
        for key, (task, target) in tasks.items():
            params = gbm.make_params(task, candidate, num_threads=config.num_threads, overrides=config.param_overrides)
            scores = [_fold_score(fold, task, target, params, config) for fold in folds]
            trial[key] = {"folds": scores, "mean_score": float(np.mean([s["score"] for s in scores]))}
        trials.append(trial)
    selected: dict[str, Any] = {}
    for key in tasks:
        finite = [t for t in trials if math.isfinite(t[key]["mean_score"])]
        if finite:
            best = finite[int(np.argmin([t[key]["mean_score"] for t in finite]))]  # ties: the earlier trial
            selected[key] = {"params": best["params"], "trial": best["trial"], "selected_by": "fold search"}
        else:
            selected[key] = {"params": dict(gbm.DEFAULT_TUNABLE), "trial": None, "selected_by": "default (no trial)"}
    result = {
        "folds": [
            {
                "name": f.name,
                "fit": {"start": str(f.fit.start), "end": str(f.fit.end)},
                "evaluation": {"start": str(f.evaluation.start), "end": str(f.evaluation.end)},
                "fit_rows_sampled": int(f.fit_matrix.x.shape[0]),
                "fit_days_sampled": f.sampled_days,
                "eval_rows": int(f.eval_matrix.x.shape[0]),
            }
            for f in folds
        ],
        "objective": {
            k: (f"mean pinball alpha={t.alpha}" if t.is_quantile else "mean log-loss") for k, (t, _) in tasks.items()
        },
        "candidates": len(candidates),
        "trials_done": len(trials),
        "stopped_by_budget": stopped_by_budget,
        "budget_minutes": config.tuning_budget_minutes,
        "seconds_preparing_folds": round(prepared_seconds, 1),
        "seconds_total": round(time.perf_counter() - started, 1),
        "trials": trials,
        "selected": selected,
    }
    del folds
    gc.collect()
    return result


# ----------------------------------------------------------------------------
# scoring (same metric code as the baselines)
# ----------------------------------------------------------------------------


def _score_classifier(
    observed: Mapping[str, np.ndarray],
    predicted: Mapping[str, np.ndarray],
    reference: Mapping[str, np.ndarray],
    keys: Mapping[str, pd.DataFrame],
    min_n: int,
) -> dict[str, Any]:
    threshold, _ = mt.best_f1_threshold(observed[THRESHOLD_SET], predicted[THRESHOLD_SET])
    chosen = threshold if math.isfinite(threshold) else None
    sets: dict[str, Any] = {}
    for name, y in observed.items():
        total = mt.classification_metrics(y, predicted[name], y_prob_reference=reference[name], threshold=chosen)
        total["threshold_in_sample"] = float(name == THRESHOLD_SET)
        sets[name] = {
            "total": _clean_dict(total),
            "segments": _classification_segments(keys[name], y, predicted[name], reference[name], min_n),
        }
    return {"threshold": {"chosen_on": THRESHOLD_SET, "value": chosen}, "sets": sets}


def _split_levels(
    predicted: Mapping[str, Mapping[float, np.ndarray]],
) -> tuple[dict[str, dict[float, np.ndarray]], dict[str, dict[float, np.ndarray]] | None]:
    """(P50/P80/P95 per set, the 80 % interval ends per set or None if they were not trained)."""
    low, high = tg.INTERVAL_LEVELS
    core = {n: {a: q for a, q in levels.items() if a in tg.QUANTILE_LEVELS} for n, levels in predicted.items()}
    has_interval = all(low in levels and high in levels for levels in predicted.values()) and bool(predicted)
    interval = {n: {low: levels[low], high: levels[high]} for n, levels in predicted.items()} if has_interval else None
    return core, interval


def _score_quantiles(
    observed: Mapping[str, np.ndarray],
    predicted: Mapping[str, Mapping[float, np.ndarray]],
    keys: Mapping[str, pd.DataFrame],
    min_n: int,
    *,
    sort: bool,
) -> dict[str, Any]:
    """P50/P80/P95 metrics (sorted per row with ``sort``, plan 3.3) and, if the alpha 0.10 / 0.90 predictions are
    there, the interval80 metrics. The interval ends are ordered as a PAIR (lower = min, upper = max), separately from
    the main quantiles, so P50/P80/P95 do not depend on whether the interval models were trained."""
    core, interval = _split_levels(predicted)
    low, high = tg.INTERVAL_LEVELS
    sets: dict[str, Any] = {}
    for name, y in observed.items():
        raw = {a: np.asarray(q, dtype="float64") for a, q in core[name].items()}
        if sort:
            used, raw_rate = gbm.order_quantiles(raw)
        else:
            used, raw_rate = raw, mt.quantile_crossing_rate(raw)
        total = mt.quantile_metrics(y, used, interval=tg.INTERVAL_LEVELS)
        total["crossing_rate_raw"] = raw_rate
        before = mt.quantile_metrics(y, raw, interval=tg.INTERVAL_LEVELS) if sort else None
        if interval is not None:
            lo_raw = np.asarray(interval[name][low], dtype="float64")
            hi_raw = np.asarray(interval[name][high], dtype="float64")
            lo, hi = (np.minimum(lo_raw, hi_raw), np.maximum(lo_raw, hi_raw)) if sort else (lo_raw, hi_raw)
            raw_interval = mt.interval_metrics(y, lo_raw, hi_raw, tg.INTERVAL_LEVELS)
            total.update(mt.interval_metrics(y, lo, hi, tg.INTERVAL_LEVELS))
            total[f"{_INTERVAL_NAME}_crossing_rate_raw"] = raw_interval[f"{_INTERVAL_NAME}_crossing_rate"]
            if before is not None:
                before.update(raw_interval)
        entry: dict[str, Any] = {
            "total": _clean_dict(total),
            "segments": _quantile_segments(keys[name], y, used, min_n),
            "ordering": "row-wise np.sort (plan 3.3)" if sort else "none (reference as defined)",
        }
        if before is not None:
            entry["total_before_sorting"] = _clean_dict(before)
        sets[name] = entry
    return {"sets": sets}


def _add_deltas(scored: dict[str, Any], reference: dict[str, Any], keys: Sequence[str]) -> None:
    """model - B1 per set for the given total metrics (negative is better for losses)."""
    for name, entry in scored["sets"].items():
        ref_total = reference["sets"][name]["total"]
        entry["delta_vs_B1"] = {
            k: (entry["total"][k] - ref_total[k])
            if entry["total"].get(k) is not None and ref_total.get(k) is not None
            else None
            for k in keys
        }


def _quantile_delta_keys(interval: bool = False) -> list[str]:
    keys = [f"pinball_{mt.quantile_key(a)}" for a in tg.QUANTILE_LEVELS] + ["mae_q050"]
    if interval:
        keys += [f"pinball_{mt.quantile_key(a)}" for a in tg.INTERVAL_LEVELS]
        keys += [f"{_INTERVAL_NAME}_coverage", f"{_INTERVAL_NAME}_mean_width_min"]
    return keys


def _brief(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    if y.size == 0:
        return {"n": 0}
    return {
        "n": int(y.size),
        "prevalence": float(y.mean()),
        "mean_pred": float(p.mean()),
        "log_loss": mt.log_loss(y, p),
        "roc_auc": mt.roc_auc(y, p),
    }


def _checkpoints_by_month(
    model: gbm.TrainedModel, x: np.ndarray, y: np.ndarray, months: np.ndarray
) -> list[dict[str, Any]]:
    """Val-A metrics overall and by calendar month after fixed numbers of rounds (needs ``keep_full_booster``):
    shows WHICH month drives the early-stopping metric and whether the mean prediction drifts (diagnostics only)."""
    wanted = {*CURVE_CHECKPOINTS, model.best_iteration, model.rounds_trained}
    rounds = sorted(r for r in wanted if 1 <= r <= model.rounds_trained)
    labels = [str(m) for m in sorted(set(months.tolist()))]
    month_text = months.astype(str)
    out: list[dict[str, Any]] = []
    for r in rounds:
        p = gbm.predict_at(model, x, r)
        out.append(
            {
                "round": r,
                "all": _clean_dict(_brief(y, p)),
                "by_month": {m: _clean_dict(_brief(y[month_text == m], p[month_text == m])) for m in labels},
            }
        )
    return out


# ----------------------------------------------------------------------------
# the run
# ----------------------------------------------------------------------------


def _save_pickle(obj: object, path: Path) -> Path:
    if path.exists():
        raise FileExistsError(f"Model file exists, will not overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(obj, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return path


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def run(
    *,
    layer_root: Path | None = None,
    output_dir: Path | None = None,
    model_dir: Path | None = None,
    config: RunConfig | None = None,
    mlflow_mode: str = "auto",
    hash_files: bool = True,
    now: dt.datetime | None = None,
) -> Path:
    """Run search + final fits + evaluation and write the outputs; returns the results folder."""
    cfg = config or RunConfig()
    check_contract_option(cfg.contract, cfg.oracle_experiment)
    unknown_models = [m for m in cfg.models if m not in MODEL_CHOICES]
    if unknown_models:
        raise ValueError(f"Unknown model choice(s) {unknown_models}; allowed: {MODEL_CHOICES}")
    _check_new_options(cfg, mlflow_mode)
    validate_layout()
    oracle = cfg.contract == "oracle"
    created = now or dt.datetime.now(dt.UTC)
    run_id = f"run-{created:%Y%m%dT%H%M%SZ}"
    sub = ("oracle",) if oracle else ()
    results_root = Path(output_dir or DEFAULT_OUTPUT_DIR).joinpath(*sub)
    reused = (
        load_selected_parameters(
            cfg.tuning_from_run, results_root, cfg.contract, allow_other_contract=cfg.tuning_from_other_contract
        )
        if cfg.tuning_from_run
        else None
    )
    reused_contract = (
        json.loads((results_root / str(cfg.tuning_from_run) / RESULTS_NAME).read_text(encoding="utf-8"))["metadata"][
            "contract"
        ]
        if cfg.tuning_from_run
        else None
    )
    folder = Path(output_dir or DEFAULT_OUTPUT_DIR).joinpath(*sub, run_id)
    models_folder = Path(model_dir or DEFAULT_MODEL_DIR).joinpath(*sub, run_id)
    for path in (folder, models_folder):
        if path.exists():
            raise FileExistsError(f"Folder exists, will not overwrite: {path}")
    timings: dict[str, float] = {}
    clock = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal clock
        timings[name] = round(time.perf_counter() - clock, 1)
        clock = time.perf_counter()

    fit, evaluation_periods, folds_plan = plan_periods(cfg)
    periods = [fit, *evaluation_periods.values()] + [p for _, f, e in folds_plan for p in (f, e)]
    loaded = load_periods(
        layer_root,
        periods,
        flight_columns=MODEL_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=hash_files,
    )
    reader = LayerTableReader(layer_root, hash_files=hash_files)
    months_read = [f"{y:04d}-{mo:02d}" for y, mo in loaded.months]
    rows_loaded = int(len(loaded.frame))
    lap("load")

    # --- search (rolling folds inside the training window) ---
    search_tasks: dict[str, tuple[gbm.GBMTask, str]] = {}
    if any(m in cfg.models for m in ("arr_del15", "cancelled")):
        search_tasks["arr_del15"] = (gbm.BINARY_TASKS["arr_del15"], tg.ARR_DEL15)
    if "quantiles" in cfg.models:
        search_tasks["arr_delay_q080"] = (gbm.QUANTILE_TASKS[0.80], tg.ARR_DELAY)
    tuning: dict[str, Any]
    if reused is not None:
        missing = [k for k in search_tasks if k not in reused]
        if missing:
            raise KeyError(f"{cfg.tuning_from_run} has no selected parameters for {missing}")
        tuning = {
            "trials_done": 0,
            "from_run": cfg.tuning_from_run,
            "from_run_contract": reused_contract,
            "selected": {k: reused[k] for k in search_tasks},
        }
    elif cfg.tuning and folds_plan and search_tasks:
        tuning = _search(loaded.frame, folds_plan, cfg, reader, search_tasks)
    else:
        tuning = {
            "trials_done": 0,
            "selected": {
                k: {"params": dict(gbm.DEFAULT_TUNABLE), "trial": None, "selected_by": "default (search off)"}
                for k in search_tasks
            },
        }
    lap("search")

    # --- final matrices: fit window + Val-A / Val-B ---
    train = _slice(loaded.frame, fit)
    evaluations = {name: _slice(loaded.frame, p) for name, p in evaluation_periods.items()}
    loaded.frame = pd.DataFrame()  # free the 30-month frame; only the file list is still needed
    gc.collect()
    for frame in evaluations.values():
        check_temporal_order(train[SPLIT_DATE_COLUMN], frame[SPLIT_DATE_COLUMN], embargo_days=cfg.embargo_days)

    # B1 reference on the same rows, same code as run_baselines
    train_keys = ft.add_key_columns(train)
    eval_keys = {name: ft.add_key_columns(frame) for name, frame in evaluations.items()}
    y_train = _targets(train)
    y_eval = {name: _targets(frame) for name, frame in evaluations.items()}
    b1_rates: dict[str, dict[str, np.ndarray]] = {}
    for target in tg.CLASSIFICATION_TARGETS:
        table = make_rate_baseline("B1", m=cfg.m, min_support=cfg.min_support).fit(
            train_keys, y_train[target], fit_end=fit.end
        )
        b1_rates[target] = {
            name: table.transform(keys, require_after_fit_end=True)["value"].to_numpy(dtype="float64")
            for name, keys in eval_keys.items()
        }
    b1_quantile_table = make_quantile_baseline("B1", alphas=quantile_levels(cfg), min_tail=cfg.min_tail).fit(
        train_keys, y_train[tg.ARR_DELAY], fit_end=fit.end
    )
    b1_quantiles = {
        name: b1_quantile_table.quantiles(keys, require_after_fit_end=True) for name, keys in eval_keys.items()
    }
    del train_keys, eval_keys
    lap("b1_reference")

    encoder = CategoryEncoder().fit(train, fit_end=fit.end)
    unknown = {
        "train": encoder.unknown_report(train),
        **{name: encoder.unknown_report(frame) for name, frame in evaluations.items()},
    }
    history, encoded = _fit_history(train, fit.end, cfg)
    lap("history")
    time_travel: dict[str, Any] | None = None
    if cfg.permutation and cfg.time_travel:
        time_travel = imp.time_travel_check(
            train,
            evaluations[imp.PERMUTATION_SET],
            fit_end=fit.end,
            history_factory=history_factory(cfg.m, cfg.min_support, cfg.min_tail),
            n_blocks=cfg.n_blocks,
        )
        gc.collect()
        lap("time_travel")
    m_train = build_model_matrix(
        train, kind=cfg.contract, reader=reader, encoder=encoder, history_frame=encoded, drop=cfg.drop_features
    )
    del encoded
    gc.collect()
    m_eval = {
        name: build_model_matrix(
            frame, kind=cfg.contract, reader=reader, encoder=encoder, history=history, drop=cfg.drop_features
        )
        for name, frame in evaluations.items()
    }
    seg = {name: segment_keys(frame) for name, frame in evaluations.items()}
    perm_dates: np.ndarray | None = None
    perm_rows: np.ndarray | None = None
    if cfg.permutation:
        perm_dates = evaluations[imp.PERMUTATION_SET][SPLIT_DATE_COLUMN].to_numpy()
        perm_rows = imp.sample_rows_by_days(perm_dates, cfg.permutation_max_rows, seed=cfg.seed)
    logistic_rows = sample_days(train[SPLIT_DATE_COLUMN], cfg.logistic_day_fraction, seed=cfg.seed)
    universe = {
        "train": tg.universe_summary(train),
        **{name: tg.universe_summary(frame) for name, frame in evaluations.items()},
    }
    del train, evaluations
    gc.collect()
    lap("matrices")
    names = m_train.feature_names
    dropped = list(m_train.dropped)
    contract_json = m_train.contract.model_dump(mode="json")
    if dropped:  # the digest describes the features the models saw (unchanged when nothing is dropped)
        contract_json["features"] = [f for f in contract_json["features"] if f["name"] in names]
    contract_digest = hashlib.sha256(json.dumps(contract_json, sort_keys=True).encode("utf-8")).hexdigest()

    classification: dict[str, Any] = {}
    quantile: dict[str, Any] = {}
    model_records: dict[str, Any] = {}
    alarms: list[dict[str, Any]] = []

    def inside(target: str) -> dict[str, np.ndarray]:
        return {name: np.isfinite(y_eval[name][target]) for name in EVALUATION_SETS}

    perm_cfg = (
        imp.PermutationConfig(
            max_rows=cfg.permutation_max_rows,
            repeats=cfg.permutation_repeats,
            seed=cfg.seed,
            scheme=cfg.permutation_scheme,
        )
        if cfg.permutation
        else None
    )
    permutation_results: dict[str, Any] = {}
    history_description = history.describe()

    def permute(key: str, predict: Callable[[np.ndarray], np.ndarray], target: str, alpha: float | None = None) -> None:
        """Stage-2 permutation on the Val-B day sample, right after the model is trained (optional)."""
        if perm_cfg is None or perm_rows is None or perm_dates is None:
            return
        rows_b = inside(target)[imp.PERMUTATION_SET] & perm_rows
        permutation_results[key] = imp.permutation_importance(
            predict,
            m_eval[imp.PERMUTATION_SET].x[rows_b],
            y_eval[imp.PERMUTATION_SET][target][rows_b],
            feature_names=names,
            kind=imp.QUANTILE if alpha is not None else imp.CLASSIFICATION,
            days=perm_dates[rows_b],
            config=perm_cfg,
            alpha=alpha,
            reference=imp.b0_reference(history_description, target, alpha),
        )

    def save_gbm(model: gbm.TrainedModel, key: str) -> dict[str, Any]:
        path = model.save(models_folder / f"{key}-lgbm.txt")
        importance = gbm.gain_importance(model)
        alarm = gbm.leakage_alarm(importance)
        if alarm["raised"]:
            alarms.append({"model": key, **alarm})
        return {
            **model.summary(),
            "file": _relative(path),
            "gain_importance": importance,
            "leakage_alarm": alarm,
            "early_stopping_set": EARLY_STOPPING_SET,
        }

    # --- classification: B1, L, LightGBM ---
    binary_targets = [t for t in tg.CLASSIFICATION_TARGETS if t in cfg.models or "logistic" in cfg.models]
    for target in binary_targets:
        rows = inside(target)
        observed = {n: y_eval[n][target][rows[n]] for n in EVALUATION_SETS}
        keys = {n: seg[n].loc[rows[n]].reset_index(drop=True) for n in EVALUATION_SETS}
        reference = {n: b1_rates[target][n][rows[n]] for n in EVALUATION_SETS}
        per_model: dict[str, Any] = {"B1": _score_classifier(observed, reference, reference, keys, cfg.segment_min_n)}
        train_rows = np.isfinite(y_train[target])
        if target in cfg.models:
            task = gbm.BINARY_TASKS[target]
            if target == tg.CANCELLED and cfg.cancel_early_stopping_metric != task.metric:
                task = gbm.with_early_stopping_metric(task, cfg.cancel_early_stopping_metric)
            tunable = tuning["selected"]["arr_del15"]["params"]  # cancellation reuses it (assumption)
            params = gbm.make_params(task, tunable, num_threads=cfg.num_threads, overrides=cfg.param_overrides)
            model = gbm.train_model(
                task,
                m_train.x[train_rows],
                y_train[target][train_rows],
                x_valid=m_eval[EARLY_STOPPING_SET].x[rows[EARLY_STOPPING_SET]],
                y_valid=observed[EARLY_STOPPING_SET],
                params=params,
                feature_names=names,
                categorical_indices=m_train.categorical_indices,
                num_boost_round=cfg.num_boost_round,
                early_stopping_rounds=cfg.early_stopping_rounds,
                record_curves=cfg.record_curves,
                keep_full_booster=cfg.record_curves,
            )
            gc.collect()
            predicted = {n: gbm.predict(model, m_eval[n].x[rows[n]]) for n in EVALUATION_SETS}
            permute(f"{target}-lgbm", partial(gbm.predict, model), target)
            scored = _score_classifier(observed, predicted, reference, keys, cfg.segment_min_n)
            _add_deltas(scored, per_model["B1"], _CLASSIFICATION_DELTAS)
            per_model["LightGBM"] = scored
            model_records[f"{target}-lgbm"] = {"target": target, "kind": "lightgbm", **save_gbm(model, target)}
            if cfg.record_curves:
                model_records[f"{target}-lgbm"]["val_a_checkpoints"] = _checkpoints_by_month(
                    model,
                    m_eval[EARLY_STOPPING_SET].x[rows[EARLY_STOPPING_SET]],
                    observed[EARLY_STOPPING_SET],
                    keys[EARLY_STOPPING_SET]["month"].to_numpy(),
                )
            del model
        if "logistic" in cfg.models and np.unique(y_train[target][train_rows & logistic_rows]).size < 2:
            model_records[f"{target}-logreg"] = {"target": target, "kind": "logistic", "skipped": "one class in sample"}
        elif "logistic" in cfg.models:
            fit_rows = train_rows & logistic_rows
            logistic: LogisticModel = fit_logistic(
                m_train.x[fit_rows],
                y_train[target][fit_rows],
                names,
                encoder,
                c=cfg.logistic_c,
                max_iter=cfg.logistic_max_iter,
                clip_quantile=cfg.logistic_clip_quantile,
            )
            predicted = {n: logistic.predict(m_eval[n].x[rows[n]]) for n in EVALUATION_SETS}
            permute(f"{target}-logreg", logistic.predict, target)
            extrapolation = {n: logistic.extrapolation(m_eval[n].x[rows[n]]) for n in EVALUATION_SETS}
            scored = _score_classifier(observed, predicted, reference, keys, cfg.segment_min_n)
            _add_deltas(scored, per_model["B1"], _CLASSIFICATION_DELTAS)
            per_model["L"] = scored
            path = _save_pickle(logistic.pipeline, models_folder / f"{target}-logreg.pkl")
            model_records[f"{target}-logreg"] = {
                "target": target,
                "kind": "logistic",
                **logistic.summary(),
                "file": _relative(path),
                "fit_sample": f"whole-day sample {cfg.logistic_day_fraction:.0%} of the fit window",
                "early_stopping_set": None,
                "extrapolation_top10": extrapolation,  # numeric features outside the fit-sample range (clipped)
            }
            del logistic
        gc.collect()
        classification[target] = per_model
    lap("classification")

    # --- quantiles of ArrDelay (completed flights) ---
    if "quantiles" in cfg.models:
        rows = inside(tg.ARR_DELAY)
        observed = {n: y_eval[n][tg.ARR_DELAY][rows[n]] for n in EVALUATION_SETS}
        keys = {n: seg[n].loc[rows[n]].reset_index(drop=True) for n in EVALUATION_SETS}
        reference_q = {n: {a: q[rows[n]] for a, q in b1_quantiles[n].items()} for n in EVALUATION_SETS}
        b1_scored = _score_quantiles(observed, reference_q, keys, cfg.segment_min_n, sort=False)
        train_rows = np.isfinite(y_train[tg.ARR_DELAY])
        tunable = tuning["selected"]["arr_delay_q080"]["params"]
        raw: dict[str, dict[float, np.ndarray]] = {n: {} for n in EVALUATION_SETS}
        x_fit = m_train.x[train_rows]
        y_fit = y_train[tg.ARR_DELAY][train_rows]
        quantile_rounds = cfg.quantile_num_boost_round or cfg.num_boost_round
        quantile_tasks = {**gbm.QUANTILE_TASKS, **gbm.INTERVAL_TASKS}
        for alpha in quantile_levels(cfg):
            task = quantile_tasks[alpha]
            params = gbm.make_params(task, tunable, num_threads=cfg.num_threads, overrides=cfg.param_overrides)
            model = gbm.train_model(
                task,
                x_fit,
                y_fit,
                x_valid=m_eval[EARLY_STOPPING_SET].x[rows[EARLY_STOPPING_SET]],
                y_valid=observed[EARLY_STOPPING_SET],
                params=params,
                feature_names=names,
                categorical_indices=m_train.categorical_indices,
                num_boost_round=quantile_rounds,
                early_stopping_rounds=cfg.early_stopping_rounds,
                record_curves=cfg.record_curves,
            )
            for n in EVALUATION_SETS:
                raw[n][alpha] = gbm.predict(model, m_eval[n].x[rows[n]])
            permute(f"{task.name}-lgbm", partial(gbm.predict, model), tg.ARR_DELAY, alpha)
            record = save_gbm(model, task.name)
            model_records[f"{task.name}-lgbm"] = {"target": tg.ARR_DELAY, "kind": "lightgbm", **record}
            del model
            gc.collect()
        del x_fit, y_fit
        scored_q = _score_quantiles(observed, raw, keys, cfg.segment_min_n, sort=True)
        _add_deltas(scored_q, b1_scored, _quantile_delta_keys(cfg.interval_models))
        quantile[tg.ARR_DELAY] = {"B1": b1_scored, "LightGBM": scored_q}
    lap("quantiles")
    del m_train
    m_eval = {}  # free the matrices; rebinding (not del) keeps the permute() closure name defined
    gc.collect()
    leakage_review: dict[str, Any] | None = None
    if cfg.permutation:
        leakage_review = review_permutations(permutation_results, model_records, time_travel, contract_json)

    spec = {
        "run_id": run_id,
        "contract": cfg.contract,
        "oracle": oracle,
        "feature_names": names,
        "dropped_features": dropped,
        "categorical_feature_indices": [names.index(c) for c in encoder.columns if c in names],
        "categories": encoder.to_dict(),
        "fit_period": {"start": str(fit.start), "end": str(fit.end)},
        "history": history.describe(),
        "models": {
            k: {"file": v["file"], "target": v["target"], "kind": v["kind"]}
            for k, v in model_records.items()
            if "file" in v
        },
    }
    models_folder.mkdir(parents=True, exist_ok=True)
    (models_folder / "model-spec.json").write_text(json.dumps(_jsonable(spec), indent=2, ensure_ascii=False), "utf-8")

    data_fp = fingerprint(loaded.files + reader.files)
    results: dict[str, Any] = {
        "metadata": {
            "run_id": run_id,
            "created_utc": created.isoformat(),
            "command": "python -m flight_delay.modeling.run_models",
            "contract": cfg.contract,
            "oracle": oracle,
            "oracle_label": "UPPER BOUND - not available at forecast time (plan 6)" if oracle else None,
            "months_read": months_read,
            "rows_loaded": rows_loaded,
            "final_test_read": False,
            "data_fingerprint_digest": data_fp["digest"],
            "side_tables_missing": reader.missing,
            "density_neighbours_skipped": sorted(set(reader.density_neighbours_skipped)),
            "git": repro.git_info(PROJECT_ROOT),
            "library_versions": repro.library_versions(),
            "config": _jsonable(asdict(cfg) | {"param_overrides": dict(cfg.param_overrides)}),
            "early_stopping_set": EARLY_STOPPING_SET,
            "threshold_set": THRESHOLD_SET,
            "model_dir": _relative(models_folder),
            "model_dir_git_ignored": _git_ignored(models_folder),
            "mlflow_mode": mlflow_mode,
        },
        "periods": {
            "fit": {"name": fit.name, "start": str(fit.start), "end": str(fit.end)},
            **{n: {"start": str(p.start), "end": str(p.end)} for n, p in evaluation_periods.items()},
        },
        "features": {
            "names": names,
            "count": len(names),
            "categorical": [n for n in encoder.columns if n in names],
            "dropped": dropped,
            "contract_kind": cfg.contract,
            "contract_sha256": contract_digest,
        },
        "categories": {"encoder": encoder.to_dict(), "unknown": unknown},
        "history": history.describe(),
        "universe": universe,
        "tuning": tuning,
        "classification": classification,
        "quantile": quantile,
        "models": model_records,
        "leakage_alarm": {"raised": bool(alarms), "stage": "1 - suspicion (gain share)", "models": alarms},
        **(
            {
                "permutation_importance": {
                    "set": imp.PERMUTATION_SET,
                    "config": asdict(perm_cfg) if perm_cfg is not None else None,
                    "models": permutation_results,
                },
                "time_travel": time_travel,
                "leakage_review": leakage_review,
            }
            if cfg.permutation
            else {}
        ),
        "timings_seconds": timings,
        "peak_rss_gb": _peak_rss_gb(),
        "data_fingerprint": data_fp,
    }
    folder.mkdir(parents=True)
    json_path = folder / RESULTS_NAME
    json_path.write_text(json.dumps(_jsonable(results), ensure_ascii=False, indent=2, allow_nan=False), "utf-8")
    results["metadata"]["mlflow_status"] = _log_mlflow(results, data_fp, json_path, models_folder, mlflow_mode)
    (folder / SUMMARY_NAME).write_text(render_summary(_jsonable(results)), encoding="utf-8")
    return folder


# ----------------------------------------------------------------------------
# MLflow and the Turkish summary
# ----------------------------------------------------------------------------


def _log_mlflow(results: dict[str, Any], data_fp: dict[str, Any], json_path: Path, models: Path, mode: str) -> str:
    """One MLflow run per trained model (stage 'modeling'); oracle runs use '<topic>-oracle' topics."""
    if mode == "off":
        return "kapalı (--mlflow off)"
    from flight_delay.mlops.settings import load_settings
    from flight_delay.mlops.tracking import DataVersion, MLflowMissingError, load_mlflow, start_run

    try:
        load_mlflow()
    except MLflowMissingError:
        if mode == "auto":
            return "atlandı (mlflow kurulu değil)"
        raise
    settings = load_settings()
    meta = results["metadata"]
    data = DataVersion(start_month=meta["months_read"][0], end_month=meta["months_read"][-1], label="development")
    suffix = "-oracle" if meta["oracle"] else ""
    contract_slug = str(meta["contract"]).lower()
    count = 0
    for key, record in results["models"].items():
        if "skipped" in record:
            continue
        target = record["target"]
        model_slug = ("lgbm" if record["kind"] == "lightgbm" else "logreg") + f"-{contract_slug}"
        if target == tg.ARR_DELAY:
            model_slug += "-" + key.split("_")[-1].split("-")[0]  # q050 / q080 / q095
        block = (
            results["quantile"][tg.ARR_DELAY]["LightGBM"]
            if target == tg.ARR_DELAY
            else results["classification"][target]["LightGBM" if record["kind"] == "lightgbm" else "L"]
        )
        with start_run(settings, "modeling", _MLFLOW_TOPICS[target] + suffix, model_slug, data, data_fp) as run:
            run.parameter("target", target)
            run.parameter("contract", meta["contract"])
            run.parameter("oracle", str(meta["oracle"]).lower())
            run.parameter("fit_start", results["periods"]["fit"]["start"])
            run.parameter("fit_end", results["periods"]["fit"]["end"])
            run.parameter("early_stopping_set", str(record.get("early_stopping_set")))
            run.parameter("early_stopping_metric", str(record.get("early_stopping_metric")))
            run.parameter("features_sha256", results["features"]["contract_sha256"])
            run.parameter("dropped_features", ",".join(results["features"].get("dropped", [])) or "none")
            for name, value in record.get("params", {}).items():
                run.parameter(f"hp.{name}", value)
            if "best_iteration" in record:
                run.parameter("best_iteration", record["best_iteration"])
            for set_name, entry in block["sets"].items():
                for metric, value in entry["total"].items():
                    if isinstance(value, int | float) and math.isfinite(float(value)):
                        run.metric(f"{set_name}_{metric}", float(value))
                for metric, value in entry.get("delta_vs_B1", {}).items():
                    if isinstance(value, int | float) and math.isfinite(float(value)):
                        run.metric(f"{set_name}_delta_vs_b1_{metric}", float(value))
            run.artifact_file(json_path)
            model_file = PROJECT_ROOT / record["file"]
            if model_file.is_file():
                run.artifact_file(model_file, subfolder="model")
            spec = models / "model-spec.json"
            if spec.is_file():
                run.artifact_file(spec, subfolder="model")
        count += 1
    return f"{count} koşu kaydedildi (deney öneki {settings.mlflow.experiment_prefix}/modeling/...)"


def _delta(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    return f"{value:+.{digits}f}"


_POSTHOC_COMMAND = "python -m flight_delay.modeling.run_permutation --run-id {run_id}"


def leakage_banner(results: Mapping[str, Any], review: Mapping[str, Any] | None = None) -> list[str]:
    """Banner of the two-stage leakage rule: gain share = suspicion (stage 1); permutation + time travel = decision.

    ``review``: a stage-2 result computed later (post-hoc command); default: the run's own ``leakage_review``.
    """
    review = review if review is not None else results.get("leakage_review")
    gain = results.get("leakage_alarm", {})
    run_id = results.get("metadata", {}).get("run_id", "<run-id>")
    if review is None:
        if not gain.get("raised"):
            return []
        names = ", ".join(f"`{m['model']}`: {m['top_feature']} {m['top_gain_share']:.1%}" for m in gain["models"])
        return [
            f"> **SIZINTI ŞÜPHESİ (1. aşama, kazanç payı > %50):** {names}. Bu tek başına karar değildir: kazanç önemi "
            "sık ve erken bölünen özellikleri kayırır. Karar 2. aşamada verilir (Val-B permütasyonu + zaman yolculuğu "
            f"testi): `{_POSTHOC_COMMAND.format(run_id=run_id)}` ya da `--permutation`. Karar çıkana kadar bu "
            "sonuçlar kesin diye sunulmaz (data-leakage-prevention). Ayrıntı: JSON `leakage_alarm`.",
            "",
        ]
    status = review["status"]
    if status == "leak":
        leaks = [
            f"`{key}`: {s['feature']}"
            for key, model in review["models"].items()
            for s in model["suspects"]
            if s["verdict"] == "leak"
        ]
        return [
            f"> **SIZINTI (2. aşama kararı):** {', '.join(leaks)} T anından sonraki bilgiyi taşıyabiliyor. Bu modellerin "
            "sonuçları raporlanmaz; özellik düzeltilene ya da çıkarılana kadar CEO'ya taşınır.",
            "",
        ]
    if status == "undecided":
        return [
            "> **SIZINTI ŞÜPHESİ SÜRÜYOR:** 2. aşama en az bir şüpheli özellik için tamamlanmadı (permütasyon ya da zaman "
            "yolculuğu eksik). Sonuçlar kesin diye sunulmaz. Ayrıntı: `leakage_review`.",
            "",
        ]
    lines = [
        f"> Sızıntı incelemesi (2 aşama) tamamlandı: **sızıntı bulunmadı** (durum `{status}`). Kazanç şüphesi "
        "permütasyon ve zaman yolculuğu testiyle değerlendirildi; ayrıntı aşağıda ve JSON `leakage_review`'da.",
    ]
    if status == "dominant_past_only":
        lines.append(
            "> Not: en az bir modelde tek bir geçmiş-only özellik becerinin büyük kısmını taşıyor (sızıntı değil, güçlü "
            "bağımlılık); segment kırılımıyla birlikte okunmalı."
        )
    return [*lines, ""]


def render_summary(results: dict[str, Any]) -> str:
    """Turkish markdown summary; every number comes from ``results`` (this run's output)."""
    meta = results["metadata"]
    tuning = results["tuning"]
    lines: list[str] = []
    if meta.get("oracle"):
        lines += [
            "> **ORACLE DENEYİ – ÜST SINIR.** Tarifeli kalkış/varış anındaki gözlenmiş hava kullanıldı; bu bilgi tahmin "
            "anında elde edilemez. Başlık sonucu, kabul ölçütü ya da arayüz metriği olarak kullanılmaz (plan §6).",
            "",
        ]
    lines += leakage_banner(results)
    lines += [
        f"# Ana modeller – {meta['contract']} sözleşmesi (Val-A / Val-B, B1'e göre)",
        "",
        f"- Çalıştırma: `{meta['run_id']}` · UTC: {meta['created_utc']} · git: `{meta['git'].get('commit')}` "
        f"(kirli: {meta['git'].get('dirty')})",
        f"- Okunan aylar: {meta['months_read'][0]} .. {meta['months_read'][-1]} ({len(meta['months_read'])} ay); "
        "**son test (2026-03..08) okunmadı**.",
        f"- Fit penceresi: {results['periods']['fit']['start']} .. {results['periods']['fit']['end']} · "
        f"özellik sayısı: {results['features']['count']} · sözleşme özeti: `{results['features']['contract_sha256'][:12]}`",
        f"- Erken durdurma: **{meta['early_stopping_set']}** (plan §4.3; LightGBM'in Val-A sonuçları bu yüzden hafif "
        f"iyimser) · F1 eşiği: **{meta['threshold_set']}** (Val-B'de örneklem içi).",
        "- Val-B'nin kullanımları (red-team M1): bu koşuda F1 eşiği; koşudan sonra kalibratör ve conformal ofset fit'i "
        "(`run_calibration`), permütasyon önemi (`run_permutation`) ve takvim özelliği hipotezinin kaynağı. Bu yüzden "
        "Val-B sayıları da seçimlerden tamamen bağımsız değildir (F1 örneklem içidir; takvim hipotezi Val-B'den "
        "doğduğu için takvimsiz modellerin Val-B sayıları iyimserdir); bağımsız ölçüm yalnızca son testtir.",
        f"- Arama: {tuning.get('trials_done', 0)} deneme"
        + (
            f" / {tuning['candidates']} aday, bütçe {tuning['budget_minutes']} dk, bütçeyle durdu: "
            f"{tuning['stopped_by_budget']}, süre {tuning['seconds_total']} sn"
            if "candidates" in tuning
            else (
                f" (arama yok; parametreler `{tuning['from_run']}` koşusundan"
                + (
                    f", kaynak sözleşme {tuning['from_run_contract']})"
                    if tuning.get("from_run_contract") not in (None, meta["contract"])
                    else ")"
                )
                if tuning.get("from_run")
                else " (arama kapalı; varsayılan parametreler)"
            )
        ),
        f"- Çıkarılan özellikler: {', '.join(results['features'].get('dropped') or []) or 'yok'} · iptal erken durdurma "
        f"metriği: `{meta['config'].get('cancel_early_stopping_metric', 'binary_logloss')}` · kantil tur tavanı: "
        f"{meta['config'].get('quantile_num_boost_round') or meta['config'].get('num_boost_round')} · aralık modelleri "
        f"(α 0,10/0,90): {'evet' if meta['config'].get('interval_models') else 'hayır'}",
        f"- Süreler (sn): {results['timings_seconds']} · tepe bellek (RSS): {results['peak_rss_gb']} GB",
        f"- Model dosyaları: `{meta['model_dir']}` · git'te yok sayılıyor mu: {meta['model_dir_git_ignored']}",
        f"- MLflow: {meta.get('mlflow_status', '-')}",
        "",
        "Notlar: Farklar nokta tahminidir; GA ve anlamlılık (gün blok bootstrap, plan §5.2) son test içindir. "
        "Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). Kantiller satır "
        "başına sıralandı (plan §3.3); B1 kantilleri tanımlandığı gibi (sıralamasız).",
        "",
    ]
    for key, block in tuning.get("selected", {}).items():
        lines.append(f"- Seçilen parametreler ({key}, {block['selected_by']}): `{json.dumps(block['params'])}`")
    lines.append("")
    for target, title in ((tg.ARR_DEL15, "ArrDel15"), (tg.CANCELLED, "İptal")):
        if target not in results["classification"]:
            continue
        lines += [
            f"## {title} (sınıflandırma)",
            "",
            "| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | "
            "Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for set_name in EVALUATION_SETS:
            for model_name, scored in results["classification"][target].items():
                entry = scored["sets"][set_name]
                t, d = entry["total"], entry.get("delta_vs_B1", {})
                lines.append(
                    f"| {set_name} | {model_name} | {_format(t.get('n'), 0)} | {_format(t.get('prevalence'))} | "
                    f"{_format(t.get('roc_auc'))} | {_delta(d.get('roc_auc'))} | {_format(t.get('pr_auc'))} | "
                    f"{_delta(d.get('pr_auc'))} | {_format(t.get('brier'))} | {_format(t.get('brier_skill_score'))} | "
                    f"{_format(t.get('log_loss'))} | {_delta(d.get('log_loss'))} | {_format(t.get('ece'))} | "
                    f"{_format(t.get('calibration_in_the_large'))} | {_format(t.get('calibration_slope'), 3)} | "
                    f"{_format(t.get('f1_at_threshold'))} |"
                )
        lines.append("")
    if tg.ARR_DELAY in results["quantile"]:
        lines += [
            "## Varış rötarı kantilleri (tamamlanan uçuşlar, dk)",
            "",
            "| Küme | Model | n | Pinball P50 | Δ | Pinball P80 | Δ | Pinball P95 | Δ | MAE P50 | Kapsama P80 | "
            "Kapsama P95 | Kesişme (ham) | Kesişme (sonra) |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for set_name in EVALUATION_SETS:
            for model_name, scored in results["quantile"][tg.ARR_DELAY].items():
                entry = scored["sets"][set_name]
                t, d = entry["total"], entry.get("delta_vs_B1", {})
                lines.append(
                    f"| {set_name} | {model_name} | {_format(t.get('n'), 0)} | {_format(t.get('pinball_q050'), 3)} | "
                    f"{_delta(d.get('pinball_q050'), 3)} | {_format(t.get('pinball_q080'), 3)} | "
                    f"{_delta(d.get('pinball_q080'), 3)} | {_format(t.get('pinball_q095'), 3)} | "
                    f"{_delta(d.get('pinball_q095'), 3)} | {_format(t.get('mae_q050'), 3)} | "
                    f"{_format(t.get('coverage_q080'))} | {_format(t.get('coverage_q095'))} | "
                    f"{_format(t.get('crossing_rate_raw'))} | {_format(t.get('crossing_rate'))} |"
                )
        lines += ["", "Δ = model − B1; kayıplarda (log-loss, pinball, Brier) negatif daha iyidir.", ""]
        interval_rows = [
            (set_name, model_name, scored["sets"][set_name]["total"])
            for set_name in EVALUATION_SETS
            for model_name, scored in results["quantile"][tg.ARR_DELAY].items()
            if scored["sets"][set_name]["total"].get(f"{_INTERVAL_NAME}_coverage") is not None
        ]
        if interval_rows:
            lines += [
                "### İki yönlü %80 aralık (α 0,10 / 0,90; ham, conformal öncesi)",
                "",
                "| Küme | Model | Kapsama | Ort. genişlik (dk) | Pinball P10 | Pinball P90 | Kesişme (ham) |",
                "|---|---|---|---|---|---|---|",
            ]
            for set_name, model_name, t in interval_rows:
                crossing = t.get(f"{_INTERVAL_NAME}_crossing_rate_raw", t.get(f"{_INTERVAL_NAME}_crossing_rate"))
                lines.append(
                    f"| {set_name} | {model_name} | {_format(t.get(f'{_INTERVAL_NAME}_coverage'))} | "
                    f"{_format(t.get(f'{_INTERVAL_NAME}_mean_width_min'), 1)} | {_format(t.get('pinball_q010'), 3)} | "
                    f"{_format(t.get('pinball_q090'), 3)} | {_format(crossing)} |"
                )
            lines += [
                "",
                "Hedef kapsama 0,80 (plan §5.3 ikincil: [0,78; 0,82]); conformal ayar `run_calibration`'da.",
                "",
            ]
    lines += ["## Modeller ve özellik önemi (kazanç; ilk 8)", ""]
    for key, record in results["models"].items():
        if "skipped" in record:
            lines.append(f"- `{key}`: atlandı ({record['skipped']})")
        elif record["kind"] == "lightgbm":
            top = ", ".join(f"{r['feature']} {r['gain_share']:.1%}" for r in record["gain_importance"][:8])
            lines.append(
                f"- `{key}`: en iyi iterasyon {record['best_iteration']} / eğitilen tur "
                f"{record.get('rounds_trained', '-')} (tavan {record['num_boost_round_cap']}, tavana ulaştı: "
                f"{record['hit_round_cap']}, durdurma metriği {record.get('early_stopping_metric')}), "
                f"{record['seconds']} sn · {top}"
            )
            for metric, curve in (record.get("valid_curves") or {}).items():
                lines.append(
                    f"  - Val-A eğrisi `{metric}`: en iyi tur {curve['best_round']}, değer {_format(curve['best_value'])}"
                )
        else:
            clip = record.get("params", {}).get("clip_quantile")
            lines.append(
                f"- `{key}`: lojistik, {record['n_train']} satır ({record['fit_sample']}), {record['seconds']} sn, "
                f"yakınsama uyarısı: {len(record['convergence_warnings'])}, fit aralığına kırpma: "
                f"{'kapalı' if clip is None else ('min/maks' if clip == 0 else f'q={clip}')}"
            )
            for set_name, rows in (record.get("extrapolation_top10") or {}).items():
                if rows:
                    shown = ", ".join(f"{r['feature']} {r['share_outside_fit_range']:.1%}" for r in rows[:5])
                    lines.append(f"  - {set_name}: fit aralığı dışında (kırpıldı): {shown}")
    lines.append("")
    if results.get("leakage_review") is not None:
        lines += imp.render_review(
            results["leakage_review"], results["permutation_importance"]["models"], results.get("time_travel")
        )
    else:
        lines += [
            "Kazanç önemi sık bölünen/yüksek kardinaliteli özellikleri kayırır; permütasyon önemi (plan §7) bu koşuda "
            f"hesaplanmadı: `{_POSTHOC_COMMAND.format(run_id=meta['run_id'])}`.",
            "",
        ]
    lines += [
        "## Bilinmeyen kategoriler (eğitim penceresinde olmayan değerler → eksik)",
        "",
    ]
    for set_name, report in results["categories"]["unknown"].items():
        parts = [f"{col}: {r['unknown']} satır ({r['unknown_share']:.4%})" for col, r in report.items()]
        lines.append(f"- {set_name}: " + "; ".join(parts))
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Main models on Val-A / Val-B vs B1 (never the final test).")
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--contract", choices=ft.CONTRACT_KINDS, default="T2")
    parser.add_argument("--oracle-experiment", action="store_true", help="Required for --contract oracle (plan 6).")
    parser.add_argument("--models", nargs="+", choices=MODEL_CHOICES, default=list(MODEL_CHOICES))
    parser.add_argument("--max-train-months", type=int, default=None, help="Smoke: last N months of each fit window.")
    parser.add_argument("--tuning", choices=("on", "off"), default="on")
    parser.add_argument("--tuning-trials", type=int, default=RunConfig.tuning_trials)
    parser.add_argument("--tuning-budget-min", type=float, default=RunConfig.tuning_budget_minutes)
    parser.add_argument("--tuning-folds", nargs="+", choices=("K1", "K2", "K3", "K4"), default=["K3", "K4"])
    parser.add_argument("--tuning-day-fraction", type=float, default=RunConfig.tuning_day_fraction)
    parser.add_argument("--tuning-num-boost-round", type=int, default=RunConfig.tuning_num_boost_round)
    parser.add_argument("--num-boost-round", type=int, default=RunConfig.num_boost_round)
    parser.add_argument("--early-stopping-rounds", type=int, default=RunConfig.early_stopping_rounds)
    parser.add_argument("--num-threads", type=int, default=_default_threads())
    parser.add_argument("--logistic-day-fraction", type=float, default=RunConfig.logistic_day_fraction)
    parser.add_argument("--segment-min-n", type=int, default=RunConfig.segment_min_n)
    parser.add_argument(
        "--logistic-no-clip", action="store_true", help="L without fit-range clipping (step-2 behaviour)."
    )
    parser.add_argument(
        "--permutation", action="store_true", help="Stage-2 leakage review: Val-B permutation + time travel test."
    )
    parser.add_argument("--permutation-max-rows", type=int, default=RunConfig.permutation_max_rows)
    parser.add_argument("--permutation-repeats", type=int, default=RunConfig.permutation_repeats)
    parser.add_argument("--permutation-scheme", choices=imp.SCHEMES, default=RunConfig.permutation_scheme)
    parser.add_argument("--no-time-travel", action="store_true", help="With --permutation: skip the time travel test.")
    parser.add_argument(
        "--interval-models", action="store_true", help="Also train alpha 0.10 / 0.90 (interval80 metrics, plan 4.2)."
    )
    parser.add_argument(
        "--quantile-num-boost-round", type=int, default=None, help="Round cap of the quantile models only."
    )
    parser.add_argument(
        "--cancel-early-stopping-metric",
        choices=gbm.BINARY_EARLY_STOPPING_METRICS,
        default=RunConfig.cancel_early_stopping_metric,
        help="Val-A early stopping metric of the cancellation LightGBM (default: the plan's binary_logloss).",
    )
    parser.add_argument(
        "--record-curves", action="store_true", help="Keep Val-A curves (+ month checkpoints for binary models)."
    )
    parser.add_argument(
        "--drop-date-features", action="store_true", help=f"Leave out {', '.join(DATE_FEATURES)} (experiment)."
    )
    parser.add_argument("--tuning-from-run", default=None, help="run-<UTC>: reuse its selected parameters, no search.")
    parser.add_argument(
        "--tuning-from-other-contract",
        action="store_true",
        help="Allow a --tuning-from-run source with another contract (plan models reuse the T2 search; decision M3).",
    )
    parser.add_argument("--mlflow", choices=("auto", "on", "off"), default="auto")
    parser.add_argument("--no-hash", action="store_true", help="Skip sha256 of the files read (faster).")
    args = parser.parse_args(argv)
    config = RunConfig(
        contract=args.contract,
        oracle_experiment=args.oracle_experiment,
        max_train_months=args.max_train_months,
        models=tuple(args.models),
        tuning=args.tuning == "on",
        tuning_trials=args.tuning_trials,
        tuning_budget_minutes=args.tuning_budget_min,
        tuning_folds=tuple(args.tuning_folds),
        tuning_day_fraction=args.tuning_day_fraction,
        tuning_num_boost_round=args.tuning_num_boost_round,
        num_boost_round=args.num_boost_round,
        early_stopping_rounds=args.early_stopping_rounds,
        num_threads=args.num_threads,
        logistic_day_fraction=args.logistic_day_fraction,
        logistic_clip_quantile=None if args.logistic_no_clip else DEFAULT_CLIP_QUANTILE,
        segment_min_n=args.segment_min_n,
        permutation=args.permutation,
        permutation_max_rows=args.permutation_max_rows,
        permutation_repeats=args.permutation_repeats,
        permutation_scheme=args.permutation_scheme,
        time_travel=not args.no_time_travel,
        interval_models=args.interval_models,
        quantile_num_boost_round=args.quantile_num_boost_round,
        cancel_early_stopping_metric=args.cancel_early_stopping_metric,
        record_curves=args.record_curves,
        drop_features=DATE_FEATURES if args.drop_date_features else (),
        tuning_from_run=args.tuning_from_run,
        tuning_from_other_contract=args.tuning_from_other_contract,
    )
    folder = run(
        layer_root=args.layer_dir,
        output_dir=args.output_dir,
        model_dir=args.model_dir,
        config=config,
        mlflow_mode=args.mlflow,
        hash_files=not args.no_hash,
    )
    print(f"Results: {folder / RESULTS_NAME}\nSummary: {folder / SUMMARY_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
