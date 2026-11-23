"""Probability calibration (ArrDel15, cancellation) and conformal adjustment (ArrDelay quantiles) of a SAVED run,
without retraining (plan sections 4.2, 5.1, 5.4). Val-B only: Val-A and the final test are never read.

Usage (from the project root ``projects/havayolu-ds/``):
    python -m flight_delay.modeling.run_calibration --run-id run-20261119T182216Z
    python -m flight_delay.modeling.run_calibration --run-dir experiments/models/run-X --model-dir deliverables/models/run-X
    options: --segment-min-n 500 --no-hash --layer-dir ... (--oracle-experiment for oracle runs only)

Design (fixed before any calibration result was seen; decisions: ``experiments/kalibrasyon-conformal-kararlari.md``):
1. Calibrators and conformal offsets are FITTED on Val-B rows only (plan 1.2: B = calibration). Val-A chose the number
   of trees (early stopping) and is not used here at all.
2. Honest evaluation inside Val-B, in time order (no shuffling, no "future fits past" fold): fit part = Val-B
   intersected with the plan's rolling conformal window of February 2026 (``splits.conformal_calibration_window``:
   2025-12-06 .. 2026-01-30, i.e. 2026-01-01 .. 2026-01-30 inside Val-B; the 1-day embargo leaves 2026-01-31 out of
   both parts); evaluation part = 2026-02-01 .. 2026-02-28. Metrics before / after are reported on the evaluation part
   only; the fit part's in-sample numbers are labelled so. One fit / one evaluation month is the only time-ordered split
   that two Val-B months allow; a reverse fold (fit February, evaluate January) would fit on the future and is not
   used. Limitation: January and February are both winter, the test months are spring / summer (plan 1.2).
3. Classification: isotonic (primary, plan 4.2) and Platt (comparison) for LightGBM, L AND B1 (plan 4.2: same rule for
   the model and B1); B1 fitted on the run's fit window with the run's settings, exactly as in ``run_models``. Metrics:
   Brier, BSS (vs B1 at the same stage), log-loss, ECE, calibration-in-the-large, logistic slope / intercept, ROC-AUC,
   PR-AUC (isotonic ties can move the ranking metrics slightly). Segment: Origin (n >= ``segment_min_n``).
4. Quantiles: one-sided split conformal for P80 / P95 (plan 5.4) and CQR for the two-sided 80 % interval when the run
   has the alpha 0.10 / 0.90 models (``run_models --interval-models``); otherwise the CQR is reported as not available.
   The model's quantiles are row-sorted as in the run (plan 3.3) before the adjustment; B1 quantiles as defined.
   Coverage before / after, pinball before / after, mean interval width; Origin segments with the share of airports
   within +-5 points of the target (the K5 rule, here on one evaluation month).
5. "Static" calibrators / offsets fitted on the WHOLE Val-B are stored (``calibrators.json``) for the final-test script
   (plan 1.5: the calibration method is frozen before the lock); they are not evaluated here (no later development
   data). The plan's primary conformal method for the test is the monthly rolling window (computed by that script).
6. Before anything is fitted, every model must reproduce the run's Val-B metric (same check as ``run_permutation``);
   a model that does not is skipped. Outputs in a NEW folder ``<run-dir>/calibration/cal-<UTC>/``; nothing that exists
   is overwritten.

Rough cost (NOT measured): the fit-window load + history refit of ``run_permutation`` (its run: 3.0 + 4.6 s), the
B1 tables, and one prediction pass per model on Val-B (~0.69 M rows).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import LeakageError
from flight_delay.data.layer import DEFAULT_LAYER_DIR
from flight_delay.modeling import calibration as cal
from flight_delay.modeling import conformal as cf
from flight_delay.modeling import features as ft
from flight_delay.modeling import gbm
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import run_models as rm
from flight_delay.modeling import run_permutation as rp
from flight_delay.modeling import targets as tg
from flight_delay.modeling.baselines import BASELINE_QUANTILE_LEVELS, make_quantile_baseline, make_rate_baseline
from flight_delay.modeling.categories import CategoryEncoder
from flight_delay.modeling.loading import load_periods
from flight_delay.modeling.matrix import (
    HISTORY_INPUT_COLUMNS,
    MODEL_FLIGHT_COLUMNS,
    MODEL_LABEL_COLUMNS,
    LayerTableReader,
    build_model_matrix,
)
from flight_delay.modeling.run_baselines import _format, _jsonable
from flight_delay.modeling.splits import SPLIT_DATE_COLUMN, VAL_B, Period, conformal_calibration_window

__all__ = [
    "CALIBRATORS_FILE",
    "EVALUATION_MONTH_START",
    "RESULTS_FILE",
    "SUMMARY_FILE",
    "honest_split",
    "main",
    "render",
    "run_posthoc",
]

RESULTS_FILE = "calibration-results.json"
SUMMARY_FILE = "calibration-ozet.md"
CALIBRATORS_FILE = "calibrators.json"
EVALUATION_MONTH_START = dt.date(2026, 2, 1)  # the second Val-B month
COVERAGE_TOLERANCE = 0.05  # plan 5.3 K5: segment within +-5 points of the target
_ONE_SIDED = (0.80, 0.95)
_INTERVAL = mt.interval_key(*tg.INTERVAL_LEVELS)
_CLASSIFIERS = (("LightGBM", "lgbm"), ("L", "logreg"))


def honest_split(dates: Any) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """(fit mask, evaluation mask, description) of the time-ordered split inside Val-B (module docstring item 2)."""
    window = conformal_calibration_window(EVALUATION_MONTH_START)
    fit = Period("val_b_fit", max(window.start, VAL_B.start), min(window.end, VAL_B.end))
    evaluation = Period("val_b_eval", EVALUATION_MONTH_START, VAL_B.end)
    fit_mask, eval_mask = fit.contains(dates), evaluation.contains(dates)
    if np.any(fit_mask & eval_mask):
        raise LeakageError("Calibration fit and evaluation parts overlap")
    description = {
        "fit": {"start": str(fit.start), "end": str(fit.end)},
        "evaluation": {"start": str(evaluation.start), "end": str(evaluation.end)},
        "embargo_days_left_out": (evaluation.start - fit.end).days - 1,
        "rule": "Val-B ∩ conformal_calibration_window(2026-02-01) -> fit; 2026-02 -> evaluation",
    }
    return fit_mask, eval_mask, description


def _origin_groups(origin: np.ndarray, min_n: int) -> list[tuple[str, np.ndarray]]:
    groups: list[tuple[str, np.ndarray]] = []
    for value in sorted(set(origin.tolist())):
        mask = origin == value
        if int(mask.sum()) >= min_n:
            groups.append((str(value), mask))
    return groups


def _calibration_segments(
    y: np.ndarray, before: np.ndarray, after: np.ndarray, origin: np.ndarray, min_n: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value, mask in _origin_groups(origin, min_n):
        rows.append(
            {
                "segment": value,
                "n": int(mask.sum()),
                "prevalence": float(y[mask].mean()),
                "calibration_in_the_large_before": float(before[mask].mean() - y[mask].mean()),
                "calibration_in_the_large_after": float(after[mask].mean() - y[mask].mean()),
                "brier_before": mt.brier_score(y[mask], before[mask]),
                "brier_after": mt.brier_score(y[mask], after[mask]),
            }
        )
    return rows


def _coverage_segments(
    covered_before: np.ndarray, covered_after: np.ndarray, origin: np.ndarray, level: float, min_n: int
) -> dict[str, Any]:
    rows = [
        {
            "segment": value,
            "n": int(mask.sum()),
            "coverage_before": float(covered_before[mask].mean()),
            "coverage_after": float(covered_after[mask].mean()),
        }
        for value, mask in _origin_groups(origin, min_n)
    ]

    def share(key: str) -> float | None:
        if not rows:
            return None
        return float(np.mean([abs(cast(float, r[key]) - level) <= COVERAGE_TOLERANCE for r in rows]))

    return {
        "dimension": "Origin",
        "min_n": min_n,
        "target": level,
        "tolerance": COVERAGE_TOLERANCE,
        "share_within_tolerance_before": share("coverage_before"),
        "share_within_tolerance_after": share("coverage_after"),
        "rows": rows,
    }


# ----------------------------------------------------------------------------
# classification
# ----------------------------------------------------------------------------


def calibrate_classifier(
    y: np.ndarray,
    p: np.ndarray,
    b1: np.ndarray,
    fit: np.ndarray,
    evaluation: np.ndarray,
    origin: np.ndarray,
    *,
    min_n: int,
    is_b1: bool = False,
) -> dict[str, Any]:
    """Per method: calibrator fitted on ``fit`` rows, metrics on ``evaluation`` rows before / after (+ B1 at the same
    stage for the BSS), in-sample fit-part metrics, Origin segments; plus the static (whole Val-B) calibrators."""
    out: dict[str, Any] = {"n_fit": int(fit.sum()), "n_eval": int(evaluation.sum()), "methods": {}, "static": {}}
    for method in cal.CALIBRATION_METHODS:
        try:
            calibrator = cal.fit_calibrator(method, y[fit], p[fit])
            b1_calibrator = calibrator if is_b1 else cal.fit_calibrator(method, y[fit], b1[fit])
        except ValueError as error:
            out["methods"][method] = {"failed": str(error)}
            continue
        result = cal.evaluate(
            calibrator,
            y[evaluation],
            p[evaluation],
            reference_before=b1[evaluation],
            reference_after=b1_calibrator.predict(b1[evaluation]),
        )
        after_eval = calibrator.predict(p[evaluation])
        result["fit_part_in_sample_after"] = {
            k: v
            for k, v in mt.classification_metrics(y[fit], calibrator.predict(p[fit])).items()
            if k in ("n", "prevalence", "mean_pred", "brier", "ece", "calibration_in_the_large", "calibration_slope")
        }
        result["calibrator"] = {k: v for k, v in calibrator.to_dict().items() if k not in ("x", "y")}
        result["segments"] = _calibration_segments(y[evaluation], p[evaluation], after_eval, origin[evaluation], min_n)
        out["methods"][method] = result
    for method in cal.CALIBRATION_METHODS:  # static: every Val-B row of the universe (embargo day included)
        try:
            out["static"][method] = cal.fit_calibrator(method, y, p).to_dict()
        except ValueError as error:
            out["static"][method] = {"failed": str(error)}
    return out


# ----------------------------------------------------------------------------
# quantiles
# ----------------------------------------------------------------------------


def conformalize(
    y: np.ndarray,
    quantiles: Mapping[float, np.ndarray],
    fit: np.ndarray,
    evaluation: np.ndarray,
    origin: np.ndarray,
    *,
    min_n: int,
) -> dict[str, Any]:
    """One-sided offsets for P80 / P95 and the CQR offset for the 80 % interval (if both ends are there)."""
    out: dict[str, Any] = {"n_fit": int(fit.sum()), "n_eval": int(evaluation.sum()), "one_sided": {}, "static": {}}
    adjusted: dict[float, np.ndarray] = {}
    for alpha in _ONE_SIDED:
        if alpha not in quantiles:
            continue
        q = np.asarray(quantiles[alpha], dtype="float64")
        offset = cf.one_sided_offset(y[fit], q[fit], alpha)
        q_eval, y_eval = q[evaluation], y[evaluation]
        after = q_eval + offset
        adjusted[alpha] = after
        key = mt.quantile_key(alpha)
        finite = bool(np.isfinite(offset))
        out["one_sided"][key] = {
            "offset_min": offset,
            "rank": cf.conformal_rank(int(fit.sum()), alpha),
            "coverage_fit_before": mt.coverage(y[fit], q[fit]),
            "coverage_before": mt.coverage(y_eval, q_eval),
            "coverage_after": float(np.mean(y_eval <= after)),
            "pinball_before": mt.pinball_loss(y_eval, q_eval, alpha),
            "pinball_after": mt.pinball_loss(y_eval, after, alpha) if finite else None,
            "segments": _coverage_segments(y_eval <= q_eval, y_eval <= after, origin[evaluation], alpha, min_n),
        }
        out["static"][key] = {"offset_min": cf.one_sided_offset(y, q, alpha), "n_fit": int(y.size)}
    if 0.80 in adjusted and 0.95 in adjusted:
        out["adjusted_crossing_rate_q080_q095"] = cf.adjusted_crossing_rate(adjusted[0.80], adjusted[0.95])
    low, high = tg.INTERVAL_LEVELS
    if low in quantiles and high in quantiles:
        lo, hi = np.asarray(quantiles[low], dtype="float64"), np.asarray(quantiles[high], dtype="float64")
        coverage_level = round(high - low, 10)
        offset = cf.cqr_offset(y[fit], lo[fit], hi[fit], coverage_level)
        y_eval, lo_eval, hi_eval = y[evaluation], lo[evaluation], hi[evaluation]
        lo_after, hi_after = lo_eval - offset, hi_eval + offset
        finite = bool(np.isfinite(offset))
        covered_before = (y_eval >= lo_eval) & (y_eval <= hi_eval)
        covered_after = (y_eval >= lo_after) & (y_eval <= hi_after)
        out[_INTERVAL] = {
            "method": "CQR (numpy; plan 5.4)",
            "offset_min": offset,
            "rank": cf.conformal_rank(int(fit.sum()), coverage_level),
            "coverage_fit_before": mt.interval_coverage(y[fit], lo[fit], hi[fit]),
            "coverage_before": float(covered_before.mean()),
            "coverage_after": float(covered_after.mean()),
            "mean_width_min_before": mt.mean_interval_width(lo_eval, hi_eval),
            "mean_width_min_after": mt.mean_interval_width(lo_after, hi_after) if finite else None,
            "segments": _coverage_segments(covered_before, covered_after, origin[evaluation], coverage_level, min_n),
        }
        out["static"][_INTERVAL] = {"offset_min": cf.cqr_offset(y, lo, hi, coverage_level), "n_fit": int(y.size)}
    else:
        out[_INTERVAL] = {
            "not_available": "the run has no alpha 0.10 / 0.90 models (run_models --interval-models)",
        }
    return out


# ----------------------------------------------------------------------------
# the post-hoc run
# ----------------------------------------------------------------------------


def _model_key(record_key: str) -> float | None:
    """'arr_delay_q080-lgbm' -> 0.8 (None for other keys)."""
    if not record_key.startswith("arr_delay_q") or not record_key.endswith("-lgbm"):
        return None
    return int(record_key[len("arr_delay_q") : -len("-lgbm")]) / 100.0


def run_posthoc(
    run_dir: Path,
    model_dir: Path,
    *,
    layer_root: Path | None = None,
    segment_min_n: int | None = None,
    hash_files: bool = True,
    oracle_experiment: bool = False,
    now: dt.datetime | None = None,
) -> Path:
    """Calibration + conformal adjustment for a saved run; returns the new output folder."""
    started = time.perf_counter()
    results = json.loads((run_dir / rm.RESULTS_NAME).read_text(encoding="utf-8"))
    spec = json.loads((model_dir / rp.SPEC_FILE).read_text(encoding="utf-8"))
    run_id = results["metadata"]["run_id"]
    if spec["run_id"] != run_id:
        raise ValueError(f"model-spec.json belongs to {spec['run_id']}, the results to {run_id}")
    if spec.get("oracle") and not oracle_experiment:
        raise LeakageError("Oracle run: calibration reads oracle weather; pass --oracle-experiment (plan section 6)")
    run_config = results["metadata"]["config"]
    min_n = int(segment_min_n if segment_min_n is not None else run_config.get("segment_min_n", 500))
    created = now or dt.datetime.now(dt.UTC)
    out_dir = run_dir / "calibration" / f"cal-{created:%Y%m%dT%H%M%SZ}"
    if out_dir.exists():
        raise FileExistsError(f"Folder exists, will not overwrite: {out_dir}")
    fit_period = rp._period(results["periods"]["fit"], "fit")
    stored_b = results["periods"].get("val_b", {})
    if (stored_b.get("start"), stored_b.get("end")) != (str(VAL_B.start), str(VAL_B.end)):
        raise ValueError(f"Val-B of the run {stored_b} differs from the split definition {VAL_B}")
    timings: dict[str, float] = {}
    clock = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal clock
        timings[name] = round(time.perf_counter() - clock, 1)
        clock = time.perf_counter()

    loaded_train = load_periods(
        layer_root,
        [fit_period],
        flight_columns=rp._TRAIN_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=hash_files,
    )
    loaded_b = load_periods(
        layer_root,
        [VAL_B],
        flight_columns=MODEL_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=hash_files,
    )
    train = rm._slice(loaded_train.frame, fit_period)
    evaluation = rm._slice(loaded_b.frame, VAL_B)
    loaded_train.frame = pd.DataFrame()
    loaded_b.frame = pd.DataFrame()
    lap("load")

    factory = rm.history_factory(float(run_config["m"]), int(run_config["min_support"]), int(run_config["min_tail"]))
    history = factory().fit(train[list(HISTORY_INPUT_COLUMNS)], fit_end=fit_period.end)
    problems = rp.history_mismatches(spec["history"], _jsonable(history.describe()))
    if problems:
        raise RuntimeError("Refitted history differs from the saved run (data or code changed): " + "; ".join(problems))

    # B1 exactly as run_models builds it (fit window only, the run's m / min_support / min_tail)
    train_keys = ft.add_key_columns(train)
    eval_keys = ft.add_key_columns(evaluation)
    y_train = rm._targets(train)
    b1_rates = {
        target: make_rate_baseline("B1", m=float(run_config["m"]), min_support=int(run_config["min_support"]))
        .fit(train_keys, y_train[target], fit_end=fit_period.end)
        .transform(eval_keys, require_after_fit_end=True)["value"]
        .to_numpy(dtype="float64")
        for target in tg.CLASSIFICATION_TARGETS
    }
    b1_quantiles = (
        make_quantile_baseline("B1", alphas=BASELINE_QUANTILE_LEVELS, min_tail=int(run_config["min_tail"]))
        .fit(train_keys, y_train[tg.ARR_DELAY], fit_end=fit_period.end)
        .quantiles(eval_keys, require_after_fit_end=True)
    )
    del train, train_keys, eval_keys, y_train
    lap("history_and_b1")

    encoder = CategoryEncoder.from_dict(spec["categories"])
    reader = LayerTableReader(layer_root, hash_files=hash_files)
    matrix = build_model_matrix(
        evaluation,
        kind=spec["contract"],
        reader=reader,
        encoder=encoder,
        history=history,
        drop=tuple(run_config.get("drop_features") or ()),
    )
    if matrix.feature_names != list(spec["feature_names"]):
        raise ValueError("Rebuilt Val-B feature columns differ from model-spec.json")
    read_files = [*loaded_train.files, *loaded_b.files, *reader.files]
    mismatched = rp._file_mismatches(results["data_fingerprint"]["files"], read_files)
    if mismatched:
        raise RuntimeError("Layer files differ from the run's fingerprint: " + "; ".join(mismatched[:10]))
    y_all = rm._targets(evaluation)
    dates = evaluation[SPLIT_DATE_COLUMN].to_numpy()
    origin = evaluation["Origin"].astype(str).to_numpy()
    fit_mask, eval_mask, split = honest_split(evaluation[SPLIT_DATE_COLUMN])
    del evaluation
    lap("matrix")

    available = {k: v for k, v in spec["models"].items() if k in results["models"]}
    reproduction: dict[str, Any] = {}

    def predictions(key: str) -> np.ndarray | None:
        """Predictions on the target universe if the saved model reproduces the run's Val-B metric, else None."""
        record = results["models"][key]
        target = available[key]["target"]
        predict: Callable[[np.ndarray], np.ndarray] = rp.load_predictor(
            available[key]["kind"],
            rp._resolve_model_file(model_dir, available[key]["file"]),
            matrix.feature_names,
            objective=record.get("objective", "binary"),
        )
        universe = np.isfinite(y_all[target])
        predicted = predict(matrix.x[universe])
        metric, run_value = rp._run_metric(results, record, "val_b")
        y = y_all[target][universe]
        if target == tg.ARR_DELAY:
            now_value = mt.pinball_loss(y, predicted, float(record["alpha"]))
        else:
            now_value = mt.roc_auc(y, predicted)
        same = run_value is not None and abs(now_value - float(run_value)) <= rp.REPRODUCTION_TOLERANCE
        reproduction[key] = {"metric": metric, "run": run_value, "now": now_value, "reproduces_run": bool(same)}
        return predicted if same else None

    classification: dict[str, Any] = {}
    calibrators: dict[str, Any] = {}
    for target in tg.CLASSIFICATION_TARGETS:
        if target not in results.get("classification", {}):
            continue
        universe = np.isfinite(y_all[target])
        y = y_all[target][universe]
        b1 = b1_rates[target][universe]
        b1_run = results["classification"][target]["B1"]["sets"]["val_b"]["total"].get("roc_auc")
        b1_now = mt.roc_auc(y, b1)
        reproduction[f"{target}-B1"] = {  # reported; B1 is rebuilt here, a mismatch is shown, not hidden
            "metric": "roc_auc",
            "run": b1_run,
            "now": b1_now,
            "reproduces_run": b1_run is not None and abs(b1_now - float(b1_run)) <= rp.REPRODUCTION_TOLERANCE,
        }
        f, e, o = fit_mask[universe], eval_mask[universe], origin[universe]
        per_model: dict[str, Any] = {"B1": calibrate_classifier(y, b1, b1, f, e, o, min_n=min_n, is_b1=True)}
        for label, suffix in _CLASSIFIERS:
            key = f"{target}-{suffix}"
            if key not in available or "skipped" in results["models"][key]:
                continue
            p = predictions(key)
            if p is None:
                per_model[label] = {"skipped": "does not reproduce the run's Val-B metric"}
                continue
            per_model[label] = calibrate_classifier(y, p, b1, f, e, o, min_n=min_n)
        for label, block in per_model.items():
            if "static" in block:
                calibrators[f"{target}/{label}"] = block.pop("static")
        classification[target] = per_model
    lap("classification")

    quantile: dict[str, Any] = {}
    quantile_keys: dict[float, str] = {}
    for key in available:
        alpha = _model_key(key)
        if alpha is not None:
            quantile_keys[alpha] = key
    if quantile_keys:
        universe = np.isfinite(y_all[tg.ARR_DELAY])
        y = y_all[tg.ARR_DELAY][universe]
        f, e, o = fit_mask[universe], eval_mask[universe], origin[universe]
        raw: dict[float, np.ndarray] = {}
        for alpha, key in sorted(quantile_keys.items()):
            p = predictions(key)
            if p is not None:
                raw[alpha] = p
        core = {a: q for a, q in raw.items() if a in tg.QUANTILE_LEVELS}
        model_q: dict[float, np.ndarray] = {}
        if set(core) == set(tg.QUANTILE_LEVELS):
            model_q, _ = gbm.order_quantiles(core)  # the run's row-wise sorting (plan 3.3)
        low, high = tg.INTERVAL_LEVELS
        if low in raw and high in raw:  # the run sorts the interval ends as a pair
            model_q[low], model_q[high] = np.minimum(raw[low], raw[high]), np.maximum(raw[low], raw[high])
        b1_q = {a: np.asarray(q, dtype="float64")[universe] for a, q in b1_quantiles.items()}
        quantile = {
            "LightGBM": conformalize(y, model_q, f, e, o, min_n=min_n)
            if model_q
            else {"skipped": "quantile models missing or not reproducing the run"},
            "B1": conformalize(y, b1_q, f, e, o, min_n=min_n),
        }
        for label, block in quantile.items():
            if "static" in block:
                calibrators[f"{tg.ARR_DELAY}/{label}"] = block.pop("static")
    lap("quantiles")

    output: dict[str, Any] = {
        "metadata": {
            "run_id": run_id,
            "created_utc": created.isoformat(),
            "command": "python -m flight_delay.modeling.run_calibration",
            "run_dir": rm._relative(run_dir),
            "model_dir": rm._relative(model_dir),
            "retrained": False,
            "final_test_read": False,
            "val_a_read": False,
            "segment_min_n": min_n,
            "primary_calibration_method": cal.PRIMARY_METHOD,
            "seconds_total": round(time.perf_counter() - started, 1),
            "peak_rss_gb": rm._peak_rss_gb(),
            "timings_seconds": timings,
            "files_checked_against_run": len(read_files),
            "rows_val_b": int(dates.size),
        },
        "split": split,
        "reproduction": reproduction,
        "classification": classification,
        "quantile": quantile,
    }
    output = _jsonable(output)
    out_dir.mkdir(parents=True)
    (out_dir / RESULTS_FILE).write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")
    fitted_on = {"start": str(VAL_B.start), "end": str(VAL_B.end)}
    static = _jsonable({"run_id": run_id, "fitted_on": fitted_on, **calibrators})
    (out_dir / CALIBRATORS_FILE).write_text(json.dumps(static, ensure_ascii=False, allow_nan=False), "utf-8")
    (out_dir / SUMMARY_FILE).write_text(render(output), encoding="utf-8")
    return out_dir


# ----------------------------------------------------------------------------
# Turkish summary
# ----------------------------------------------------------------------------


def _metric_row(label: str, method: str, block: Mapping[str, Any]) -> str:
    b, a = block["before"], block["after"]
    cells = [
        f"{_format(b.get(k), 4)} → {_format(a.get(k), 4)}"
        for k in ("brier", "ece", "calibration_in_the_large", "calibration_slope", "log_loss", "roc_auc")
    ]
    head = f"| {label} | {method} | {_format(b.get('n'), 0)} | {_format(b.get('prevalence'))} | "
    return head + " | ".join(cells) + " |"


def _shares(segments: Mapping[str, Any]) -> str:
    before = _format(segments["share_within_tolerance_before"], 2)
    return f"{before} → {_format(segments['share_within_tolerance_after'], 2)}"


def _segment_line(label: str, segments: Sequence[Mapping[str, Any]]) -> str | None:
    if not segments:
        return None
    worst = max(segments, key=lambda r: abs(float(r["calibration_in_the_large_after"])))
    return (
        f"- {label}: Origin segmenti {len(segments)}; en büyük |ort. tahmin − gözlenen| (sonra) "
        f"{worst['segment']} {_format(worst['calibration_in_the_large_after'])} "
        f"(önce {_format(worst['calibration_in_the_large_before'])}, n {worst['n']})"
    )


def render(output: Mapping[str, Any]) -> str:
    """Turkish markdown of the post-hoc calibration (every number from ``output``)."""
    meta, split = output["metadata"], output["split"]
    lines = [
        f"# Kalibrasyon ve conformal ayar (sonradan, yeniden eğitim yok) – `{meta['run_id']}`",
        "",
        f"- Oluşturma (UTC): {meta['created_utc']} · koşu: `{meta['run_dir']}` · modeller: `{meta['model_dir']}`",
        "- Okunan: fit penceresi (geçmiş istatistikleri ve B1 için) + Val-B; **Val-A ve son test okunmadı**; model "
        "yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı "
        f"({meta['files_checked_against_run']} dosya).",
        f"- Zaman sıralı ayrım (Val-B içinde): fit {split['fit']['start']} .. {split['fit']['end']}, değerlendirme "
        f"{split['evaluation']['start']} .. {split['evaluation']['end']}, aradaki {split['embargo_days_left_out']} gün "
        "embargo (plan §1.4). Önce/sonra sayıları yalnızca değerlendirme kısmındandır (koşunun Val-B toplamı "
        "Ocak+Şubat'tı).",
        f"- Birincil kalibratör: **{meta['primary_calibration_method']}** (plan §4.2); Platt karşılaştırma. B1 aynı "
        "kuralla kalibre edildi; BSS her aşamada aynı aşamadaki B1'e göre.",
        f"- Süre: {meta['seconds_total']} sn · tepe bellek (RSS): {meta['peak_rss_gb']} GB · adımlar: "
        f"{meta['timings_seconds']}",
        "",
        "## Koşunun Val-B metriğini yeniden üretme",
        "",
        "| Model | Metrik | Koşu | Şimdi | Aynı mı |",
        "|---|---|---|---|---|",
    ]
    for key, entry in output["reproduction"].items():
        lines.append(
            f"| {key} | {entry['metric']} | {_format(entry['run'], 6)} | {_format(entry['now'], 6)} | "
            f"{'evet' if entry['reproduces_run'] else 'HAYIR'} |"
        )
    lines.append("")
    for target, title in ((tg.ARR_DEL15, "ArrDel15"), (tg.CANCELLED, "İptal")):
        if target not in output["classification"]:
            continue
        lines += [
            f"## {title}: olasılık kalibrasyonu (değerlendirme ayı, önce → sonra)",
            "",
            "| Model | Yöntem | n | Yaygınlık | Brier | ECE | Ort. tahmin − gözlenen | Kal. eğimi | Log-loss "
            "| ROC-AUC |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        segment_lines: list[str] = []
        for label, block in output["classification"][target].items():
            if "skipped" in block:
                lines.append(f"| {label} | - | - | - | atlandı: {block['skipped']} | | | | | |")
                continue
            for method, result in block["methods"].items():
                if "failed" in result:
                    lines.append(f"| {label} | {method} | - | - | başarısız: {result['failed']} | | | | | |")
                    continue
                lines.append(_metric_row(label, method, result))
                if method == meta["primary_calibration_method"]:
                    line = _segment_line(f"{label} ({method})", result.get("segments", []))
                    if line:
                        segment_lines.append(line)
        lines += ["", *segment_lines, ""]
    quantile = output.get("quantile") or {}
    if quantile:
        lines += [
            "## Varış rötarı: conformal ayar (değerlendirme ayı)",
            "",
            "| Model | Düzey | Ofset (dk) | Kapsama önce | Kapsama sonra | Pinball/genişlik önce | sonra | "
            "Havalimanı ±5 puan içinde (önce → sonra) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for label, block in quantile.items():
            if "skipped" in block:
                lines.append(f"| {label} | - | atlandı: {block['skipped']} | | | | | |")
                continue
            for key, entry in block["one_sided"].items():
                lines.append(
                    f"| {label} | {key} (tek yönlü) | {_format(entry['offset_min'], 2)} | "
                    f"{_format(entry['coverage_before'])} | {_format(entry['coverage_after'])} | "
                    f"{_format(entry['pinball_before'], 3)} | {_format(entry['pinball_after'], 3)} | "
                    f"{_shares(entry['segments'])} |"
                )
            entry = block.get(_INTERVAL, {})
            if "not_available" in entry:
                lines.append(f"| {label} | {_INTERVAL} (CQR) | yok: {entry['not_available']} | | | | | |")
            elif entry:
                width_before = _format(entry["mean_width_min_before"], 1)
                width_after = _format(entry["mean_width_min_after"], 1)
                lines.append(
                    f"| {label} | {_INTERVAL} (CQR) | {_format(entry['offset_min'], 2)} | "
                    f"{_format(entry['coverage_before'])} | {_format(entry['coverage_after'])} | "
                    f"{width_before} dk | {width_after} dk | {_shares(entry['segments'])} |"
                )
            if "adjusted_crossing_rate_q080_q095" in block:
                lines.append(
                    f"| {label} | q080+c > q095+c | {_format(block['adjusted_crossing_rate_q080_q095'])} | | | | | |"
                )
        lines += [
            "",
            "Hedefler: P80 0,80 · P95 0,95 · %80 aralık 0,80. Kabul ölçütü K5 son testte ve **aylık kayan** pencereyle "
            "değerlendirilir; buradaki tek ay yalnızca yöntemin dürüst bir ön kontrolüdür. Statik (tüm Val-B) "
            f"kalibratörler ve ofsetler `{CALIBRATORS_FILE}` dosyasında; burada değerlendirilmedi.",
            "",
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibration + conformal adjustment of a saved run (Val-B only).")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--run-id", help="run-<UTC>: experiments/models/<id> + deliverables/models/<id>")
    where.add_argument("--run-dir", type=Path, help="Results folder (with model-results.json); needs --model-dir")
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--segment-min-n", type=int, default=None, help="Default: the run's segment_min_n.")
    parser.add_argument("--no-hash", action="store_true", help="Compare file sizes only (faster).")
    parser.add_argument("--oracle-experiment", action="store_true", help="Required for oracle runs (plan 6).")
    args = parser.parse_args(argv)
    sub = ("oracle",) if args.oracle_experiment else ()
    if args.run_id:
        run_dir = rm.DEFAULT_OUTPUT_DIR.joinpath(*sub, args.run_id)
        model_dir = args.model_dir or rm.DEFAULT_MODEL_DIR.joinpath(*sub, args.run_id)
    else:
        if args.model_dir is None:
            parser.error("--run-dir needs --model-dir")
        run_dir, model_dir = args.run_dir, args.model_dir
    folder = run_posthoc(
        run_dir,
        model_dir,
        layer_root=args.layer_dir,
        segment_min_n=args.segment_min_n,
        hash_files=not args.no_hash,
        oracle_experiment=args.oracle_experiment,
    )
    print(f"Results: {folder / RESULTS_FILE}\nSummary: {folder / SUMMARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
