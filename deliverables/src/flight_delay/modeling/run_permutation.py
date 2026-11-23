"""Stage-2 leakage review on a SAVED model run, without retraining (plan sections 2.6 and 7). NEVER the final test.

Usage (from the project root ``projects/havayolu-ds/``):
    python -m flight_delay.modeling.run_permutation --run-id run-20261119T181934Z
    python -m flight_delay.modeling.run_permutation --run-dir experiments/models/run-X --model-dir deliverables/models/run-X
    options: --max-rows 300000 --repeats 3 --scheme rows|within_day --models arr_del15-lgbm ... --features ...
             --no-time-travel --no-oof-check --no-hash --layer-dir ... (--oracle-experiment for oracle runs only)

What it does:
1. Reads ``model-results.json`` (config, fit period, gain importance, data fingerprint, Val-B metrics) and
   ``model-spec.json`` (feature names, category lists, history description, and per model: file, target, kind).
   The model file format comes from the spec's ``kind``: ``lightgbm`` = LightGBM text model saved at its best
   iteration (``gbm.TrainedModel.save``), ``logistic`` = pickled scikit-learn Pipeline written by ``run_models``
   (pickle executes code on load: only load files of your own runs).
2. Loads the fit window (history key + label columns only) and Val-B (schedule + label columns). Val-A and the final
   test are not read; the side-table reader refuses final-test months as in the run.
3. Refits ``HistoryFeatures`` on the fit window with the run's settings and STOPS if its description (row counts,
   first / last dates, global rate / quantiles per table) differs from the stored one, or if a file the run read has a
   different size / sha256 now: the permutation must run on the run's matrix, not on a different one.
4. Rebuilds the Val-B matrix with the stored category lists (feature names must match the spec), reproduces the run's
   Val-B metric per model on the full target universe (reported; a model that does not reproduce is not permuted),
   then permutes on the whole-day Val-B sample (``importance.permutation_importance``).
5. Time travel test (history features), two-stage review (``run_models.review_permutations``), outputs in a NEW
   folder ``<run-dir>/permutation/perm-<UTC>/``: ``importance-results.json`` + ``importance-ozet.md``. Nothing that
   exists is overwritten (``model-ozet.md`` of the run stays as it was).

Rough cost (NOT measured): loading the fit window ~ the run's load step (24 months: ~9 M rows, narrow columns);
history refit (+ 2 out-of-fold passes for the time travel test); per model (65 features x repeats) predictions on
~300 k rows. LightGBM prediction time grows with the number of trees, so the full run's models (up to 2000 trees) are
the slow part.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pickle
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import LeakageError
from flight_delay.data.layer import DEFAULT_LAYER_DIR
from flight_delay.modeling import importance as imp
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import run_models as rm
from flight_delay.modeling import targets as tg
from flight_delay.modeling.categories import CategoryEncoder
from flight_delay.modeling.loading import load_periods
from flight_delay.modeling.logistic import LogisticModel
from flight_delay.modeling.matrix import (
    HISTORY_INPUT_COLUMNS,
    MODEL_FLIGHT_COLUMNS,
    MODEL_LABEL_COLUMNS,
    LayerTableReader,
    build_model_matrix,
)
from flight_delay.modeling.run_baselines import _jsonable
from flight_delay.modeling.splits import SPLIT_DATE_COLUMN, VAL_B, Period
from flight_delay.paths import PROJECT_ROOT

__all__ = [
    "REPRODUCTION_TOLERANCE",
    "RESULTS_FILE",
    "SPEC_FILE",
    "SUMMARY_FILE",
    "history_mismatches",
    "load_predictor",
    "main",
    "run_posthoc",
]

RESULTS_FILE = "importance-results.json"
SUMMARY_FILE = "importance-ozet.md"
SPEC_FILE = "model-spec.json"
# float64 metric of the same predictions on the same rows; only summation order can differ
REPRODUCTION_TOLERANCE = 1e-6
_TRAIN_FLIGHT_COLUMNS = (
    "flight_uid",
    "FlightDate",
    "Origin",
    "Dest",
    "Reporting_Airline",
    "crs_dep_local_min",
    "CRSElapsedTime",
    "crs_dep_utc",
    "crs_arr_utc",
)


def _period(entry: Mapping[str, Any], name: str) -> Period:
    start, end = dt.date.fromisoformat(entry["start"]), dt.date.fromisoformat(entry["end"])
    return Period(str(entry.get("name", name)), start, end)


def _resolve_model_file(model_dir: Path, recorded: str) -> Path:
    candidate = model_dir / Path(recorded).name
    if candidate.is_file():
        return candidate
    alternative = Path(recorded) if Path(recorded).is_absolute() else PROJECT_ROOT / recorded
    if alternative.is_file():
        return alternative
    raise FileNotFoundError(f"Model file not found: {recorded} (looked in {model_dir})")


def load_predictor(
    kind: str, path: Path, feature_names: Sequence[str], *, objective: str | None = None
) -> Callable[[np.ndarray], np.ndarray]:
    """Prediction function of a saved model; the format is given by the spec's ``kind``."""
    if kind == "lightgbm":
        booster = lgb.Booster(model_file=str(path))
        binary = objective == "binary"

        def predict(x: np.ndarray, chunk_rows: int = 500_000) -> np.ndarray:
            parts = [np.asarray(booster.predict(x[s : s + chunk_rows])) for s in range(0, x.shape[0], chunk_rows)]
            out = np.concatenate(parts).astype("float64") if parts else np.empty(0, dtype="float64")
            return np.clip(out, 0.0, 1.0) if binary else out

        return predict
    if kind == "logistic":
        with path.open("rb") as handle:
            pipeline = pickle.load(handle)  # own file written by run_models (see the module docstring)
        model = LogisticModel(pipeline=pipeline, feature_names=list(feature_names), n_train=0, seconds=0.0)
        return model.predict
    raise ValueError(f"Unknown model kind {kind!r} in model-spec.json")


def history_mismatches(stored: Mapping[str, Any], refit: Mapping[str, Any]) -> list[str]:
    """Differences between the stored and the refitted ``HistoryFeatures.describe()`` (empty = same)."""
    problems: list[str] = []
    if str(stored.get("fit_end")) != str(refit.get("fit_end")):
        problems.append(f"fit_end {stored.get('fit_end')} != {refit.get('fit_end')}")
    for name, table in refit.get("tables", {}).items():
        old = stored.get("tables", {}).get(name)
        if old is None:
            problems.append(f"{name}: missing in the stored description")
            continue
        for key in ("n_fit", "fit_first_date", "fit_last_date"):
            if old.get(key) != table.get(key):
                problems.append(f"{name}.{key}: {old.get(key)} != {table.get(key)}")
        values = {"global_mean": (old.get("global_mean"), table.get("global_mean"))}
        for q, v in (table.get("global_quantiles") or {}).items():
            values[f"global_quantiles.{q}"] = ((old.get("global_quantiles") or {}).get(q), v)
        for key, (a, b) in values.items():
            if a is None and b is None:
                continue
            fa = float("nan") if a is None else float(a)
            fb = float("nan") if b is None else float(b)
            if not (math.isnan(fa) and math.isnan(fb)) and not math.isclose(fa, fb, rel_tol=1e-9, abs_tol=1e-12):
                problems.append(f"{name}.{key}: {a} != {b}")
    return problems


def _file_mismatches(run_files: Sequence[Mapping[str, Any]], read_files: Sequence[Mapping[str, Any]]) -> list[str]:
    recorded = {str(r["path"]): r for r in run_files}
    problems: list[str] = []
    for record in read_files:
        old = recorded.get(str(record["path"]))
        if old is None:
            problems.append(f"{record['path']}: not read by the run")
            continue
        if int(old["bytes"]) != int(record["bytes"]):
            problems.append(f"{record['path']}: size {old['bytes']} != {record['bytes']}")
        elif "sha256" in old and "sha256" in record and old["sha256"] != record["sha256"]:
            problems.append(f"{record['path']}: sha256 differs")
    return problems


def _run_metric(results: Mapping[str, Any], record: Mapping[str, Any], set_name: str) -> tuple[str, float | None]:
    """(metric name, value) the run reported for this model on ``set_name`` (unsorted pinball for quantiles)."""
    target = record["target"]
    if target == tg.ARR_DELAY:
        alpha = float(record["alpha"])
        metric = f"pinball_{mt.quantile_key(alpha)}"
        entry = results["quantile"][tg.ARR_DELAY]["LightGBM"]["sets"][set_name]
        return metric, entry.get("total_before_sorting", {}).get(metric)
    name = "L" if record["kind"] == "logistic" else "LightGBM"
    return "roc_auc", results["classification"][target][name]["sets"][set_name]["total"].get("roc_auc")


def run_posthoc(
    run_dir: Path,
    model_dir: Path,
    *,
    layer_root: Path | None = None,
    config: imp.PermutationConfig | None = None,
    models: Sequence[str] | None = None,
    time_travel: bool = True,
    oof_check: bool = True,
    hash_files: bool = True,
    oracle_experiment: bool = False,
    now: dt.datetime | None = None,
) -> Path:
    """Permutation + time travel + review for a saved run; returns the new output folder."""
    started = time.perf_counter()
    results = json.loads((run_dir / rm.RESULTS_NAME).read_text(encoding="utf-8"))
    spec = json.loads((model_dir / SPEC_FILE).read_text(encoding="utf-8"))
    run_id = results["metadata"]["run_id"]
    if spec["run_id"] != run_id:
        raise ValueError(f"model-spec.json belongs to {spec['run_id']}, the results to {run_id}")
    if spec.get("oracle") and not oracle_experiment:
        raise LeakageError("Oracle run: the review reads oracle weather; pass --oracle-experiment (plan section 6)")
    run_config = results["metadata"]["config"]
    cfg = config or imp.PermutationConfig(seed=int(run_config.get("seed", 42)))
    created = now or dt.datetime.now(dt.UTC)
    out_dir = run_dir / "permutation" / f"perm-{created:%Y%m%dT%H%M%SZ}"
    if out_dir.exists():
        raise FileExistsError(f"Folder exists, will not overwrite: {out_dir}")
    available = {k: v for k, v in spec["models"].items() if k in results["models"]}
    selected = list(models) if models else list(available)
    unknown = [k for k in selected if k not in available]
    if unknown:
        raise KeyError(f"Unknown model(s) {unknown}; saved: {sorted(available)}")

    fit = _period(results["periods"]["fit"], "fit")
    stored_b = results["periods"].get(imp.PERMUTATION_SET, {})
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
        [fit],
        flight_columns=_TRAIN_FLIGHT_COLUMNS,
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
    train = rm._slice(loaded_train.frame, fit)
    evaluation = rm._slice(loaded_b.frame, VAL_B)
    loaded_train.frame = pd.DataFrame()  # only the file lists are still needed
    loaded_b.frame = pd.DataFrame()
    lap("load")

    factory = rm.history_factory(float(run_config["m"]), int(run_config["min_support"]), int(run_config["min_tail"]))
    history = factory().fit(train[list(HISTORY_INPUT_COLUMNS)], fit_end=fit.end)
    problems = history_mismatches(spec["history"], _jsonable(history.describe()))
    if problems:
        raise RuntimeError("Refitted history differs from the saved run (data or code changed): " + "; ".join(problems))
    lap("history")
    tt: dict[str, Any] | None = None
    if time_travel:
        tt = imp.time_travel_check(
            train,
            evaluation,
            fit_end=fit.end,
            history_factory=factory,
            n_blocks=int(run_config.get("n_blocks", 5)),
            oof_check=oof_check,
        )
        lap("time_travel")
    del train

    encoder = CategoryEncoder.from_dict(spec["categories"])
    reader = LayerTableReader(layer_root, hash_files=hash_files)
    matrix = build_model_matrix(
        evaluation,
        kind=spec["contract"],
        reader=reader,
        encoder=encoder,
        history=history,
        drop=tuple(run_config.get("drop_features") or ()),  # runs before the option have no such key: nothing dropped
    )
    if matrix.feature_names != list(spec["feature_names"]):
        raise ValueError("Rebuilt Val-B feature columns differ from model-spec.json")
    read_files = [*loaded_train.files, *loaded_b.files, *reader.files]
    mismatched = _file_mismatches(results["data_fingerprint"]["files"], read_files)
    if mismatched:
        raise RuntimeError("Layer files differ from the run's fingerprint: " + "; ".join(mismatched[:10]))
    y_all = rm._targets(evaluation)
    dates = evaluation[SPLIT_DATE_COLUMN].to_numpy()
    sample = imp.sample_rows_by_days(dates, cfg.max_rows, seed=cfg.seed)
    del evaluation
    lap("matrix")

    names = matrix.feature_names
    history_description = spec["history"]
    permutation: dict[str, Any] = {}
    reproduction: dict[str, Any] = {}
    for key in selected:
        record = results["models"][key]
        kind, target = available[key]["kind"], available[key]["target"]
        alpha = float(record["alpha"]) if target == tg.ARR_DELAY else None
        objective = record.get("objective", "binary")
        predict = load_predictor(
            kind, _resolve_model_file(model_dir, available[key]["file"]), names, objective=objective
        )
        universe = np.isfinite(y_all[target])
        metric, run_value = _run_metric(results, record, imp.PERMUTATION_SET)
        task_kind = imp.QUANTILE if alpha is not None else imp.CLASSIFICATION
        now_value = imp.score(task_kind, y_all[target][universe], predict(matrix.x[universe]), alpha)[metric]
        same = run_value is not None and abs(now_value - float(run_value)) <= REPRODUCTION_TOLERANCE
        reproduction[key] = {"metric": metric, "run": run_value, "now": now_value, "reproduces_run": bool(same)}
        if not same:
            continue  # not the run's model / matrix: no permutation (review stays 'undecided' for gain suspects)
        rows = universe & sample
        permutation[key] = imp.permutation_importance(
            predict,
            matrix.x[rows],
            y_all[target][rows],
            feature_names=names,
            kind=task_kind,
            days=dates[rows],
            config=cfg,
            alpha=alpha,
            reference=imp.b0_reference(history_description, target, alpha),
        )
        lap(f"permutation_{key}")
    contract_json = matrix.contract.model_dump(mode="json")
    review = rm.review_permutations(permutation, results["models"], tt, contract_json)

    output: dict[str, Any] = {
        "metadata": {
            "run_id": run_id,
            "created_utc": created.isoformat(),
            "command": "python -m flight_delay.modeling.run_permutation",
            "run_dir": rm._relative(run_dir),
            "model_dir": rm._relative(model_dir),
            "retrained": False,
            "final_test_read": False,
            "val_a_read": False,
            "models_selected": selected,
            "seconds_total": round(time.perf_counter() - started, 1),
            "peak_rss_gb": rm._peak_rss_gb(),
            "timings_seconds": timings,
            "files_checked_against_run": len(read_files),
        },
        "reproduction": reproduction,
        "permutation_importance": {"set": imp.PERMUTATION_SET, "config": asdict(cfg), "models": permutation},
        "time_travel": tt,
        "leakage_review": review,
    }
    output = _jsonable(output)
    out_dir.mkdir(parents=True)
    (out_dir / RESULTS_FILE).write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), "utf-8")
    (out_dir / SUMMARY_FILE).write_text(render(output, _jsonable(results)), encoding="utf-8")
    return out_dir


def render(output: Mapping[str, Any], results: Mapping[str, Any]) -> str:
    """Turkish markdown of a post-hoc review (every number from ``output`` / the run's results)."""
    meta = output["metadata"]
    lines = [
        *rm.leakage_banner(results, output["leakage_review"]),
        f"# Sızıntı incelemesi (sonradan, yeniden eğitim yok) – `{meta['run_id']}`",
        "",
        f"- Oluşturma (UTC): {meta['created_utc']} · koşu: `{meta['run_dir']}` · modeller: `{meta['model_dir']}`",
        "- Okunan: fit penceresi (geçmiş istatistikleri için) + Val-B; **Val-A ve son test okunmadı**; model yeniden "
        "eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı "
        f"({meta['files_checked_against_run']} dosya).",
        f"- Süre: {meta['seconds_total']} sn · tepe bellek (RSS): {meta['peak_rss_gb']} GB · adımlar: "
        f"{meta['timings_seconds']}",
        "",
        "## Koşunun Val-B metriğini yeniden üretme (tüm hedef evreni)",
        "",
        "| Model | Metrik | Koşu | Şimdi | Aynı mı |",
        "|---|---|---|---|---|",
    ]
    for key, entry in output["reproduction"].items():
        lines.append(
            f"| {key} | {entry['metric']} | {imp._fmt(entry['run'], 6)} | {imp._fmt(entry['now'], 6)} | "
            f"{imp._fmt(entry['reproduces_run'])} |"
        )
    lines += ["", "Yeniden üretilemeyen model permüte edilmez (başka matris / model olurdu).", ""]
    lines += imp.render_review(
        output["leakage_review"], output["permutation_importance"]["models"], output.get("time_travel")
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage-2 leakage review of a saved run (no retraining, Val-B only).")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--run-id", help="run-<UTC>: experiments/models/<id> + deliverables/models/<id>")
    where.add_argument("--run-dir", type=Path, help="Results folder (with model-results.json); needs --model-dir")
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--max-rows", type=int, default=imp.DEFAULT_MAX_ROWS)
    parser.add_argument("--repeats", type=int, default=imp.DEFAULT_REPEATS)
    parser.add_argument("--seed", type=int, default=None, help="Default: the run's seed.")
    parser.add_argument("--scheme", choices=imp.SCHEMES, default="rows")
    parser.add_argument("--models", nargs="+", default=None, help="Model keys (default: every saved model).")
    parser.add_argument("--features", nargs="+", default=None, help="Features to permute (default: all).")
    parser.add_argument("--no-time-travel", action="store_true")
    parser.add_argument("--no-oof-check", action="store_true", help="Skip the 2 out-of-fold passes of the test.")
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
    seed = args.seed
    if seed is None:
        stored = json.loads((run_dir / rm.RESULTS_NAME).read_text(encoding="utf-8"))
        seed = int(stored["metadata"]["config"].get("seed", 42))
    config = imp.PermutationConfig(
        max_rows=args.max_rows,
        repeats=args.repeats,
        seed=seed,
        scheme=args.scheme,
        features=tuple(args.features) if args.features else None,
    )
    folder = run_posthoc(
        run_dir,
        model_dir,
        layer_root=args.layer_dir,
        config=config,
        models=args.models,
        time_travel=not args.no_time_travel,
        oof_check=not args.no_oof_check,
        hash_files=not args.no_hash,
        oracle_experiment=args.oracle_experiment,
    )
    print(f"Results: {folder / RESULTS_FILE}\nSummary: {folder / SUMMARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
