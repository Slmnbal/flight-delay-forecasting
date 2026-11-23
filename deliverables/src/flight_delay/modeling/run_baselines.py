"""Evaluate the baselines (B0, B1, B2) on Val-A and Val-B (and optionally rolling folds K1..K4). NEVER the final test.

Usage (from the project root ``projects/havayolu-ds/``):
    python -m flight_delay.modeling.run_baselines                      # val_a + val_b, MLflow if installed
    python -m flight_delay.modeling.run_baselines --sets val_a val_b K3 K4 --mlflow off

Output: ``experiments/baselines/run-<UTC timestamp>/baseline-results.json`` and ``baseline-ozet.md`` (Turkish
summary). An existing run folder is never overwritten. There is deliberately no option for the final test.

Flow: validate the split layout -> read only the months of the requested periods (flights: 6 columns, labels: 5
columns; final-test partitions are never opened) -> fit each baseline on its fit window (train for Val-A / Val-B,
the fold's fit window for K*) -> score with ``metrics`` -> JSON + md -> optional MLflow runs
(``flight_delay.mlops.tracking``; ``--mlflow auto`` skips with a message if MLflow is not installed).

Rough cost (NOT measured): 30 months x ~0.38 M rows = ~11.4 M rows x ~40 bytes = ~0.5 GB for the loaded frame, peak
~2-3 GB with the key copies and group-by tables; minutes, dominated by Parquet reading and the quantile group-bys.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flight_delay.data.layer import DEFAULT_LAYER_DIR
from flight_delay.mlops import reproducibility as repro
from flight_delay.modeling import targets as tg
from flight_delay.modeling.baselines import evaluate_baselines
from flight_delay.modeling.history import DEFAULT_M, DEFAULT_MIN_SUPPORT, DEFAULT_MIN_TAIL
from flight_delay.modeling.loading import (
    BASELINE_FLIGHT_COLUMNS,
    BASELINE_LABEL_COLUMNS,
    fingerprint,
    load_periods,
)
from flight_delay.modeling.splits import (
    SPLIT_DATE_COLUMN,
    TRAIN,
    TRAIN_EVAL_EMBARGO_DAYS,
    VAL_A,
    VAL_B,
    Period,
    get_fold,
    trim_end,
    validate_layout,
)
from flight_delay.paths import PROJECT_ROOT

__all__ = ["EVALUATION_CHOICES", "Job", "main", "plan_jobs", "render_summary", "run"]

EVALUATION_CHOICES = ("val_a", "val_b", "K1", "K2", "K3", "K4")
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "experiments" / "baselines"
RESULTS_NAME = "baseline-results.json"
SUMMARY_NAME = "baseline-ozet.md"
_MLFLOW_TOPICS = {tg.ARR_DEL15: "arrdel15", tg.CANCELLED: "cancelled", tg.ARR_DELAY: "arr-delay-quantile"}


@dataclass(frozen=True)
class Job:
    """One fit window and the evaluation periods scored with it."""

    fit: Period
    evaluations: dict[str, Period]


def plan_jobs(set_names: Sequence[str], embargo_days: int = TRAIN_EVAL_EMBARGO_DAYS) -> list[Job]:
    """val_a / val_b share the training fit (plan 1.2: no refit on A); every fold has its own fit window."""
    unknown = [s for s in set_names if s not in EVALUATION_CHOICES]
    if unknown:
        raise ValueError(f"Unknown evaluation set(s) {unknown}; allowed: {EVALUATION_CHOICES} (never the final test)")
    jobs: list[Job] = []
    validation = {s: {"val_a": VAL_A, "val_b": VAL_B}[s] for s in set_names if s in ("val_a", "val_b")}
    if validation:
        jobs.append(Job(trim_end(TRAIN, embargo_days), validation))
    for name in set_names:
        if name.startswith("K"):
            fold = get_fold(name)
            jobs.append(Job(trim_end(fold.fit, embargo_days), {name: fold.evaluation}))
    return jobs


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):  # numpy scalar
        return _jsonable(value.item())
    return value


def _format(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_summary(results: dict[str, Any]) -> str:
    """Short Turkish markdown summary; every number comes from ``results`` (this run's output)."""
    meta = results["metadata"]
    lines = [
        "# Baseline değerlendirmesi (B0, B1, B2)",
        "",
        f"- Çalıştırma: `{meta['run_id']}` · oluşturma (UTC): {meta['created_utc']} · git: `{meta['git'].get('commit')}`"
        f" (kirli: {meta['git'].get('dirty')})",
        f"- Okunan aylar: {meta['months_read'][0]} .. {meta['months_read'][-1]} ({len(meta['months_read'])} ay); "
        "**son test (2026-03..08) okunmadı**.",
        f"- Veri parmak izi (okunan dosyalar): `{meta['data_fingerprint_digest']}`",
        f"- Parametreler: m = {meta['parameters']['m']}, min_support = {meta['parameters']['min_support']}, "
        f"min_tail = {meta['parameters']['min_tail']}, embargo = {meta['parameters']['embargo_days']} gün, "
        f"segment n eşiği = {meta['parameters']['segment_min_n']}",
        f"- MLflow: {meta.get('mlflow_status', '-')}",
        "- Plan: `experiments/modelleme-plani.md` §1 (bölme), §3 (hedefler), §4.1 (baseline), §5.1 (metrikler).",
        "",
        "Notlar: F1 eşiği her baseline için Val-B'de seçildi; Val-B'deki F1 örneklem içidir. Segment tabloları JSON'da "
        "(Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). GA/bootstrap bu çalıştırmada yok (plan §5.2 "
        "son test içindir).",
        "",
    ]
    for job in results["jobs"]:
        lines += [f"## Fit penceresi {job['fit_period']['start']} .. {job['fit_period']['end']}", ""]
        for target, title in ((tg.ARR_DEL15, "ArrDel15"), (tg.CANCELLED, "İptal")):
            lines += [
                f"### {title} (sınıflandırma)",
                "",
                "| Küme | Baseline | n | Yaygınlık | ROC-AUC | PR-AUC | Brier | BSS (B1'e göre) | Log-loss | ECE | Ort. tahmin − gözlenen | F1 (eşik B'den) |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|",
            ]
            for set_name, per_baseline in job["classification"][target].items():
                for baseline, block in per_baseline.items():
                    t = block["total"]
                    lines.append(
                        f"| {set_name} | {baseline} | {_format(t.get('n'), 0)} | {_format(t.get('prevalence'))} | "
                        f"{_format(t.get('roc_auc'))} | {_format(t.get('pr_auc'))} | {_format(t.get('brier'))} | "
                        f"{_format(t.get('brier_skill_score'))} | {_format(t.get('log_loss'))} | {_format(t.get('ece'))} | "
                        f"{_format(t.get('calibration_in_the_large'))} | {_format(t.get('f1_at_threshold'))} |"
                    )
            lines.append("")
        lines += [
            "### Varış rötarı kantilleri (tamamlanan uçuşlar, dk)",
            "",
            "| Küme | Baseline | n | Pinball P50 | Pinball P80 | Pinball P95 | MAE P50 | Kapsama P80 | Kapsama P95 | %80 aralık kapsama | %80 aralık genişlik | Kesişme oranı |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for set_name, per_baseline in job["quantile"][tg.ARR_DELAY].items():
            for baseline, block in per_baseline.items():
                t = block["total"]
                lines.append(
                    f"| {set_name} | {baseline} | {_format(t.get('n'), 0)} | {_format(t.get('pinball_q050'), 3)} | "
                    f"{_format(t.get('pinball_q080'), 3)} | {_format(t.get('pinball_q095'), 3)} | "
                    f"{_format(t.get('mae_q050'), 3)} | {_format(t.get('coverage_q080'))} | "
                    f"{_format(t.get('coverage_q095'))} | {_format(t.get('interval80_coverage'))} | "
                    f"{_format(t.get('interval80_mean_width_min'), 1)} | {_format(t.get('crossing_rate'))} |"
                )
        lines += ["", "ArrDel15 tutarlılığı (BTS ArrDel15 ile ArrDelay >= 15 karşılaştırması):", ""]
        for set_name, check in job["arr_del15_consistency"].items():
            lines.append(
                f"- {set_name}: karşılaştırılan {check['compared_rows']}, uyumsuz {check['mismatch_rows']}, "
                f"tamamlanmış ama ArrDel15 boş {check['completed_arr_del15_missing']}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _log_mlflow(results: dict[str, Any], data_fp: dict[str, Any], json_path: Path, mode: str) -> str:
    """One MLflow run per (job, target, baseline). Returns a status text for the summary."""
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
    months = results["metadata"]["months_read"]
    data = DataVersion(start_month=months[0], end_month=months[-1], label="development")
    count = 0
    for job in results["jobs"]:
        groups = [(t, job["classification"][t]) for t in tg.CLASSIFICATION_TARGETS] + [
            (tg.ARR_DELAY, job["quantile"][tg.ARR_DELAY])
        ]
        for target, per_set in groups:
            for baseline in job["parameters"]["baselines"]:
                with start_run(settings, "baseline", _MLFLOW_TOPICS[target], baseline.lower(), data, data_fp) as run:
                    run.parameter("target", target)
                    run.parameter("fit_start", job["fit_period"]["start"])
                    run.parameter("fit_end", job["fit_period"]["end"])
                    run.parameter("evaluation_sets", ",".join(per_set))
                    for name in ("m", "min_support", "min_tail", "embargo_days", "segment_min_n"):
                        run.parameter(name, job["parameters"][name])
                    for set_name, per_baseline in per_set.items():
                        for metric, value in per_baseline[baseline]["total"].items():
                            if isinstance(value, int | float) and math.isfinite(float(value)):
                                run.metric(f"{set_name}_{metric}", float(value))
                    run.artifact_file(json_path)
                count += 1
    return f"{count} koşu kaydedildi (deney öneki {settings.mlflow.experiment_prefix}/baseline/...)"


def run(
    *,
    layer_root: Path | None = None,
    output_dir: Path | None = None,
    set_names: Sequence[str] = ("val_a", "val_b"),
    m: float = DEFAULT_M,
    min_support: int = DEFAULT_MIN_SUPPORT,
    min_tail: int = DEFAULT_MIN_TAIL,
    segment_min_n: int = 500,
    embargo_days: int = TRAIN_EVAL_EMBARGO_DAYS,
    mlflow_mode: str = "auto",
    hash_files: bool = True,
    now: dt.datetime | None = None,
) -> Path:
    """Run the evaluation and write the outputs; returns the run folder."""
    validate_layout()
    jobs = plan_jobs(set_names, embargo_days)
    created = now or dt.datetime.now(dt.UTC)
    run_id = f"run-{created:%Y%m%dT%H%M%SZ}"
    folder = Path(output_dir or DEFAULT_OUTPUT_DIR) / run_id
    if folder.exists():
        raise FileExistsError(f"Run folder exists, will not overwrite: {folder}")

    periods = [p for job in jobs for p in (job.fit, *job.evaluations.values())]
    loaded = load_periods(
        layer_root,
        periods,
        flight_columns=BASELINE_FLIGHT_COLUMNS,
        label_columns=BASELINE_LABEL_COLUMNS,
        hash_files=hash_files,
    )
    frame = loaded.frame
    data_fp = fingerprint(loaded.files)

    job_results: list[dict[str, Any]] = []
    for job in jobs:
        train = frame.loc[job.fit.contains(frame[SPLIT_DATE_COLUMN])].reset_index(drop=True)
        evaluations = {
            name: frame.loc[period.contains(frame[SPLIT_DATE_COLUMN])].reset_index(drop=True)
            for name, period in job.evaluations.items()
        }
        result = evaluate_baselines(
            train,
            evaluations,
            fit_end=job.fit.end,
            m=m,
            min_support=min_support,
            min_tail=min_tail,
            segment_min_n=segment_min_n,
            embargo_days=embargo_days,
        )
        result["fit_period"] = {"name": job.fit.name, "start": str(job.fit.start), "end": str(job.fit.end)}
        result["evaluation_periods"] = {
            name: {"start": str(p.start), "end": str(p.end)} for name, p in job.evaluations.items()
        }
        job_results.append(result)

    results: dict[str, Any] = {
        "metadata": {
            "run_id": run_id,
            "created_utc": created.isoformat(),
            "command": "python -m flight_delay.modeling.run_baselines",
            "evaluation_sets": list(set_names),
            "months_read": [f"{y:04d}-{mo:02d}" for y, mo in loaded.months],
            "rows_loaded": int(len(frame)),
            "data_fingerprint_digest": data_fp["digest"],
            "git": repro.git_info(PROJECT_ROOT),
            "library_versions": repro.library_versions(),
            "parameters": {
                "m": m,
                "min_support": min_support,
                "min_tail": min_tail,
                "segment_min_n": segment_min_n,
                "embargo_days": embargo_days,
            },
            "mlflow_mode": mlflow_mode,
            "final_test_read": False,
        },
        "data_fingerprint": data_fp,
        "jobs": job_results,
    }
    folder.mkdir(parents=True)
    json_path = folder / RESULTS_NAME
    json_path.write_text(
        json.dumps(_jsonable(results), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    results["metadata"]["mlflow_status"] = _log_mlflow(results, data_fp, json_path, mlflow_mode)
    (folder / SUMMARY_NAME).write_text(render_summary(_jsonable(results)), encoding="utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate baselines B0/B1/B2 on Val-A / Val-B (never the final test).")
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sets", nargs="+", choices=EVALUATION_CHOICES, default=["val_a", "val_b"])
    parser.add_argument("--m", type=float, default=DEFAULT_M, help="m-estimate strength (plan 2.4: start 20).")
    parser.add_argument("--min-support", type=int, default=DEFAULT_MIN_SUPPORT)
    parser.add_argument(
        "--min-tail", type=int, default=DEFAULT_MIN_TAIL, help="n * (1 - alpha) >= min_tail (plan 4.1)."
    )
    parser.add_argument("--segment-min-n", type=int, default=500)
    parser.add_argument("--embargo-days", type=int, default=TRAIN_EVAL_EMBARGO_DAYS)
    parser.add_argument("--mlflow", choices=("auto", "on", "off"), default="auto")
    parser.add_argument("--no-hash", action="store_true", help="Skip sha256 of the files read (faster).")
    args = parser.parse_args(argv)
    folder = run(
        layer_root=args.layer_dir,
        output_dir=args.output_dir,
        set_names=args.sets,
        m=args.m,
        min_support=args.min_support,
        min_tail=args.min_tail,
        segment_min_n=args.segment_min_n,
        embargo_days=args.embargo_days,
        mlflow_mode=args.mlflow,
        hash_files=not args.no_hash,
    )
    print(f"Results: {folder / RESULTS_NAME}\nSummary: {folder / SUMMARY_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
