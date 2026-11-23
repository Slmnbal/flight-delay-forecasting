"""Export the static-site JSON files (GitHub Pages) of ``experiments/arayuz-sozlesmesi.json``.

Usage (from the project root ``projects/havayolu-ds/``):
    python -m flight_delay.modeling.run_interface_export --dry-run        # checks + summary files in memory; nothing written
    python -m flight_delay.modeling.run_interface_export --summary-only   # no layer data read; no rotalar/*.json
    python -m flight_delay.modeling.run_interface_export                  # full export (re-predicts with the locked models)

Sources (read only; nothing is trained, tuned or re-weighted):
1. the one-time final-test results ``experiments/son-test/son-test-20261122T105048Z/son-test-sonuclari.json``
   (totals, monthly tables, Origin / hour-block / month segments, comparisons, Holm, K1 - K7);
2. the OR cell table ``deliverables/data/or/tampon-20261122T173803Z/hucre-tamponlari.parquet`` (cells, scheduled
   flight counts, cancellations, CRS block time, publication flag incl. the M10 single-carrier rule, buffer proposal);
3. OurAirports ``airports.csv`` (name, coordinates) + ``airports.build_tz_map`` (IANA zone, same function as the layer);
4. full mode only ("option a"): the locked models of ``experiments/son-test-dondurma.json`` re-predict the final test
   exactly as ``run_final_test`` did (same building blocks, called, not copied: ``run_final_test._load_entries``,
   ``_predict_saved``, ``_development_checks``, ``_assemble`` -> ``final_eval.assemble_inputs``) for the fields the
   two files above do not contain: per-cell T2 ArrDel15 probability (monthly rolling Platt), per-cell medians of the
   plan quantiles and of their rolling conformal upper bounds, per-cell / per-origin conformal coverage, reliability
   bins and the monthly two-sided interval coverage. Before anything is exported the re-prediction must reproduce
   the final-test JSON (counts, mean probability, Brier, ECE, coverages, conformal offsets, file digest) and the OR
   table (cells, counts, cell knots); any difference stops the run and nothing is written.

Order (fail closed): preflight (sha256 of the freeze manifest's files, lock record names that manifest, the results
and the OR run name the same manifest / lock, schema scan, output folder must not exist) -> payloads -> forbidden-key
check, schema validation of every file (own definition + root ``oneOf``), size limits, manifest -> staging folder ->
rename to ``--out`` (never overwrites). A run record ``experiments/arayuz-ciktisi/arayuz-<UTC>.json`` (checks, hidden
cell counts, file hashes; no flight-level data) is written with exclusive create.

Rough cost of the full mode (NOT measured): the final test spent 1331 s predicting 7 roles on context + test rows and
peaked at 6.0 GB; this run predicts 3 roles (one T2 and one plan matrix) on the same rows plus the Val-B reproduction:
expected 15 - 40 min and 5 - 8 GB peak RSS. ``--summary-only`` / ``--dry-run`` read no layer data (seconds).
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data import layer
from flight_delay.data.airports import build_tz_map
from flight_delay.data.layer import DEFAULT_AIRPORTS, DEFAULT_LAYER_DIR, DEFAULT_TARGETS_FILE, DEFAULT_TZ_OVERRIDES
from flight_delay.modeling import features as ft
from flight_delay.modeling import final_eval as fe
from flight_delay.modeling import final_lock as fl
from flight_delay.modeling import interface_export as ie
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
from flight_delay.modeling.run_baselines import _jsonable
from flight_delay.modeling.splits import (
    FINAL_TEST,
    FINAL_TEST_LOCK_FILE,
    SPLIT_DATE_COLUMN,
    VAL_B,
    Period,
    assert_no_final_test,
    require_lock_written,
)
from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization import policies as pol
from flight_delay.paths import DATA_DIR, DELIVERABLES_DIR, PROJECT_ROOT

__all__ = ["ModelTables", "Preflight", "build_payloads", "compute_model_tables", "main", "preflight"]

LOG = logging.getLogger("flight_delay.modeling.run_interface_export")
COMMAND = "python -m flight_delay.modeling.run_interface_export"
FINAL_TEST_RUN = "son-test-20261122T105048Z"
OR_RUN = "tampon-20261122T173803Z"
DEFAULT_OUT = DELIVERABLES_DIR / "src" / "web" / "veri"
DEFAULT_RESULTS = PROJECT_ROOT / "experiments" / "son-test" / FINAL_TEST_RUN / "son-test-sonuclari.json"
DEFAULT_MANIFEST = PROJECT_ROOT / "experiments" / "son-test-dondurma.json"
DEFAULT_OR_FOLDER = PROJECT_ROOT / "experiments" / "or" / OR_RUN
DEFAULT_OR_CELLS = DATA_DIR / "or" / OR_RUN / "hucre-tamponlari.parquet"
DEFAULT_LOG_DIR = PROJECT_ROOT / "experiments" / "arayuz-ciktisi"
ROLES = (fe.ROLE_ARR_DEL15_T2, fe.ROLE_QUANTILES_PLAN, fe.ROLE_CANCELLED_PLAN)
TOLERANCE = 1e-9  # same arrays, same code path: the stored totals must come back exactly (float noise only)
OR_KNOT_TOLERANCE_MIN = 1e-6


# ----------------------------------------------------------------------------
# preflight (no layer data)
# ----------------------------------------------------------------------------


@dataclass
class Preflight:
    validator: ie.SchemaValidator
    results: dict[str, Any]
    manifest: fl.Manifest
    targets: list[str]
    airports: list[dict[str, Any]]
    or_table: pd.DataFrame | None
    aggregator: str | None
    record: dict[str, Any] = field(default_factory=dict)


def airport_records(targets: Sequence[str], airports_csv: Path, tz_overrides: Path | None) -> list[dict[str, Any]]:
    """Name, coordinates and IANA zone of every target airport; anything missing is an error (nothing invented)."""
    table = layer.load_airports(Path(airports_csv))
    names = pd.read_csv(airports_csv, dtype=str, keep_default_na=False, usecols=["ident", "name"])
    name_by_ident = dict(zip(names["ident"].str.strip().str.upper(), names["name"].str.strip(), strict=True))
    tz_map, tz_missing = build_tz_map(table, list(targets), layer.load_tz_overrides(tz_overrides))
    rows = table.set_index("iata", drop=False)
    problems = [f"{m['iata']}: {m['reason']}" for m in tz_missing]
    out = []
    for code in targets:
        if code not in rows.index:
            problems.append(f"{code}: not in OurAirports")
            continue
        row = rows.loc[code]
        name = name_by_ident.get(str(row["icao"]), "")
        lat, lon = float(row["lat"]), float(row["lon"])
        if not name:
            problems.append(f"{code}: no name in OurAirports")
        if not (np.isfinite(lat) and np.isfinite(lon)):
            problems.append(f"{code}: no coordinates in OurAirports")
        if code in tz_map:
            out.append({"iata": code, "ad": name, "enlem": lat, "boylam": lon, "saat_dilimi": tz_map[code]})
    if problems:
        raise ie.ExportError("airport information incomplete (give --tz-overrides for zones): " + "; ".join(problems))
    return out


def preflight(
    *,
    results_path: Path,
    manifest_path: Path,
    lock_file: Path,
    schema_path: Path,
    airports_csv: Path,
    tz_overrides: Path | None,
    targets_file: Path,
    out_dir: Path,
    or_folder: Path | None,
    or_cells: Path | None,
    base: Path = PROJECT_ROOT,
) -> Preflight:
    """Checks that read no layer data. Raises ExportError listing every problem found."""
    problems: list[str] = []
    validator = ie.SchemaValidator.from_file(schema_path)  # SchemaError on an unsupported keyword
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    manifest = fl.load_manifest(manifest_path)
    problems += fl.verify_files(manifest, base)
    meta = results.get("metadata") or {}
    if meta.get("mode") != "final_test":
        problems.append("results are not the final test (metadata.mode)")
    if (meta.get("manifest") or {}).get("sha256") != manifest.sha256:
        problems.append("the final-test results name a different freeze manifest")
    lock_sha = None
    if not Path(lock_file).is_file():
        problems.append(f"lock record missing: {lock_file}")
    else:
        lock_sha = fl.sha256_file(Path(lock_file))
        record = json.loads(Path(lock_file).read_text(encoding="utf-8"))
        if (record.get("manifest") or {}).get("sha256") != manifest.sha256:
            problems.append("the lock record names a different freeze manifest")
        if meta.get("lock_sha256") != lock_sha:
            problems.append("the final-test results name a different lock record (sha256)")
    or_table: pd.DataFrame | None = None
    aggregator: str | None = None
    if or_folder is not None and or_cells is not None:
        or_results = json.loads((Path(or_folder) / "tampon-sonuclari.json").read_text(encoding="utf-8"))
        or_meta = or_results.get("metadata") or {}
        if (or_meta.get("manifest") or {}).get("sha256") != manifest.sha256:
            problems.append("the OR run names a different freeze manifest")
        if or_meta.get("final_test_read") is not True:
            problems.append("the OR run did not evaluate the final test")
        freeze = json.loads((Path(or_folder) / "politika-dondurma.json").read_text(encoding="utf-8"))
        aggregator = freeze.get("aggregator")
        if aggregator not in pol.AGGREGATORS:
            problems.append(f"OR freeze: unknown aggregator {aggregator!r}")
        or_table = pd.read_parquet(or_cells)
        try:
            ie.check_or_table(or_table)
        except ValueError as error:
            problems.append(str(error))
    if Path(out_dir).exists():
        problems.append(f"output folder exists, will not overwrite: {out_dir}")
    targets = layer.read_targets(Path(targets_file))
    try:
        airports = airport_records(targets, airports_csv, tz_overrides)
    except ie.ExportError as error:
        problems.append(str(error))
        airports = []
    if problems:
        raise ie.ExportError(
            "Interface export refused (nothing read from the layer, nothing written): " + "; ".join(problems)
        )
    record = {
        "results": {"path": fl._relative(Path(results_path), base), "sha256": fl.sha256_file(Path(results_path))},
        "manifest": {"path": fl._relative(Path(manifest_path), base), "sha256": manifest.sha256},
        "lock": {"path": fl._relative(Path(lock_file), base), "sha256": lock_sha},
        "schema": {"path": fl._relative(Path(schema_path), base), "sha256": fl.sha256_file(Path(schema_path))},
        "or_cells": None
        if or_cells is None
        else {
            "path": fl._relative(Path(or_cells), base),
            "sha256": fl.sha256_file(Path(or_cells)),
            "aggregator": aggregator,
        },
        "targets": targets,
    }
    return Preflight(validator, results, manifest, targets, airports, or_table, aggregator, record)


# ----------------------------------------------------------------------------
# option (a): locked models on the final test
# ----------------------------------------------------------------------------


@dataclass
class ModelTables:
    routes: pd.DataFrame
    origin_coverage: dict[str, dict[str, Any]]
    reliability: list[dict[str, Any]]
    interval_monthly: list[dict[str, Any]]
    checks: dict[str, Any]
    info: dict[str, Any]


class _Clock:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.last = self.started
        self.timings: dict[str, float] = {}

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.timings[name] = round(now - self.last, 1)
        self.last = now
        LOG.info(
            "%s done (%.0f s, total %.0f s, peak RSS %s GB)",
            name,
            self.timings[name],
            now - self.started,
            rm._peak_rss_gb(),
        )


def _gate(checks: list[dict[str, Any]], name: str, now: Any, stored: Any, tolerance: float = TOLERANCE) -> None:
    checks.append(ie.check_close(name, now, stored, tolerance))


def compute_model_tables(
    plan: Preflight, *, layer_root: Path | None, lock_file: Path, base: Path = PROJECT_ROOT
) -> ModelTables:
    """Option (a) of the task: re-predict the final test with the locked models (``run_final_test`` building blocks)
    and aggregate per cell / origin / month / bin. Raises ExportError unless every reproduction check passes."""
    if plan.or_table is None or plan.aggregator is None:
        raise ie.ExportError("the OR cell table is required for the full export")
    clock = _Clock()
    results = plan.results
    stored = results["blocks"]["final_test"]
    loaded = rft._load_entries(plan.manifest, base, ROLES)
    problems = rft._check_boosters(loaded)
    if problems:
        raise ie.ExportError("locked models: " + "; ".join(problems))
    settings = rft._settings(loaded)
    fit: Period = settings["fit"]

    # --- fit window: history statistics and B1, exactly as in the final test ---
    loaded_train = load_periods(
        layer_root, [fit], flight_columns=rp._TRAIN_FLIGHT_COLUMNS, label_columns=MODEL_LABEL_COLUMNS, hash_files=True
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
        raise ie.ExportError("refitted history differs from the locked runs: " + " | ".join(mismatches))
    b1_rate_tables, b1_quantile_table = rft._b1_tables(train, fit.end, settings)
    del train
    gc.collect()
    clock.lap("fit_window")

    # --- context (development rows): Val-B reproduction of every model and of the frozen calibrators ---
    context = rft.context_period(FINAL_TEST, VAL_B.end)
    loaded_context = load_periods(
        layer_root, [context], flight_columns=MODEL_FLIGHT_COLUMNS, label_columns=MODEL_LABEL_COLUMNS, hash_files=True
    )
    context_frame = rm._slice(loaded_context.frame, context)
    loaded_context.frame = pd.DataFrame()
    assert_no_final_test(context_frame[SPLIT_DATE_COLUMN])
    dev_reader = LayerTableReader(layer_root, hash_files=True)
    context_predictions = rft._predict_saved(loaded, context_frame, dev_reader, history)
    context_rates, context_quantiles = rft._b1_predict(b1_rate_tables, b1_quantile_table, context_frame)
    dev_problems, reproduction, calibrators = rft._development_checks(
        loaded, context_frame, context_predictions, context_rates, context_quantiles, base
    )
    run_files = [f for item in loaded.values() for f in item.results["data_fingerprint"]["files"]]
    read_files = [*loaded_train.files, *loaded_context.files, *dev_reader.files]
    dev_problems += [f"layer: {p}" for p in rp._file_mismatches(run_files, read_files)]
    if dev_problems:
        raise ie.ExportError("development reproduction failed: " + "; ".join(dev_problems[:20]))
    clock.lap("development_checks")

    # --- final-test rows (the lock record exists; nothing is tuned on them) ---
    require_lock_written(lock_file)
    loaded_test = load_periods(
        layer_root,
        [FINAL_TEST],
        flight_columns=MODEL_FLIGHT_COLUMNS,
        label_columns=MODEL_LABEL_COLUMNS,
        hash_files=True,
        allow_final_test=True,
    )
    test_frame = rm._slice(loaded_test.frame, FINAL_TEST)
    loaded_test.frame = pd.DataFrame()
    test_reader = LayerTableReader(layer_root, hash_files=True, allow_final_test=True, lock_file=lock_file)
    test_predictions = rft._predict_saved(loaded, test_frame, test_reader, history)
    test_rates, test_quantiles = rft._b1_predict(b1_rate_tables, b1_quantile_table, test_frame)
    files_now = fingerprint([*loaded_test.files, *test_reader.files])
    checks: list[dict[str, Any]] = []
    stored_files = results["metadata"]["final_test_files"]
    checks.append(
        {
            "name": "final_test_files:digest",
            "now": files_now["digest"],
            "stored": stored_files["digest"],
            "ok": files_now["digest"] == stored_files["digest"],
        }
    )
    clock.lap("final_test_predictions")

    # --- OR reproduction: same cells, counts and plan cell knots (all scheduled rows, OR aggregator) ---
    dates = pd.to_datetime(test_frame[SPLIT_DATE_COLUMN]).dt.normalize().to_numpy(dtype="datetime64[D]")
    minutes = test_frame["crs_dep_local_min"].to_numpy(dtype="float64", na_value=np.nan)
    cells = pol.make_cells(
        test_frame["Origin"].astype(str).to_numpy(), test_frame["Dest"].astype(str).to_numpy(), minutes, dates
    )
    plan_raw = np.column_stack(
        [np.asarray(test_predictions[fe.ROLE_QUANTILES_PLAN][k], dtype="float64") for k in fl.QUANTILE_MODEL_KEYS]
    )
    knots = pol.aggregate_knots(nv.monotone_knots(plan_raw), cells.codes, cells.n_cells, plan.aggregator)
    labels = ie.cell_key_labels(cells.keys)
    or_check = ie.compare_with_or(labels, cells.counts(), knots, plan.or_table, tolerance=OR_KNOT_TOLERANCE_MIN)
    del plan_raw, knots
    origin_codes, origin_names = pd.factorize(test_frame["Origin"].astype(str))
    share = pol.top_carrier_share(
        np.asarray(origin_codes, dtype="int64"),
        test_frame["Reporting_Airline"].astype(str).to_numpy(),
        len(origin_names),
    )
    single_carrier_origins = sorted(
        str(o) for o, s in zip(origin_names, share, strict=True) if s > pol.SINGLE_CARRIER_SHARE_MAX
    )
    # user decision 2026-11-23: M10 also at airport level -> these airports are published without rates (a note)
    if single_carrier_origins:
        LOG.info("airports with one carrier above the M10 share (rates not published): %s", single_carrier_origins)
    test_targets = rm._targets(test_frame)

    # --- final_eval inputs, assembled exactly as in the final test ---
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
    inputs = rft._assemble(
        label="interface export (final test 2026-03..08)",
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
        event_threshold=None,
    )
    del frame, predictions, context_predictions, test_predictions, context_frame, test_frame
    gc.collect()
    clock.lap("assemble")

    # --- ArrDel15 (T2, rolling Platt) and cancellation (plan) blocks: same rows as the final test ---
    t2 = inputs.classifiers[fe.ROLE_ARR_DEL15_T2]
    mask15 = np.isfinite(test_targets[tg.ARR_DEL15])
    if t2.y.size != int(mask15.sum()) or not np.array_equal(t2.y, test_targets[tg.ARR_DEL15][mask15]):
        raise ie.ExportError("T2 evaluation rows are not the test rows of the ArrDel15 universe")
    p15 = np.asarray(t2.calibrated[fe.PRIMARY_PROBABILITY], dtype="float64")
    b15 = np.asarray(t2.b1_calibrated[fe.PRIMARY_PROBABILITY], dtype="float64")
    cancel = inputs.classifiers[fe.ROLE_CANCELLED_PLAN]
    pc = np.asarray(cancel.calibrated[fe.PRIMARY_PROBABILITY], dtype="float64")
    bc = np.asarray(cancel.b1_calibrated[fe.PRIMARY_PROBABILITY], dtype="float64")
    for name, values in (("T2", p15), ("T2 B1", b15), ("cancelled", pc), ("cancelled B1", bc)):
        if not np.all(np.isfinite(values)):
            raise ie.ExportError(f"{name}: rolling Platt left rows without a probability")
    cls = stored["classification"]
    for role, block, model_p, b1_p in ((fe.ROLE_ARR_DEL15_T2, t2, p15, b15), (fe.ROLE_CANCELLED_PLAN, cancel, pc, bc)):
        prob = cls[role]["probability"][fe.PRIMARY_PROBABILITY]
        _gate(checks, f"{role}:n", block.y.size, cls[role]["n"], 0)
        _gate(checks, f"{role}:prevalence", float(block.y.mean()), cls[role]["prevalence"])
        _gate(checks, f"{role}:platt_rolling:mean_pred", float(model_p.mean()), prob["model"]["mean_pred"])
        _gate(checks, f"{role}:platt_rolling:brier", mt.brier_score(block.y, model_p), prob["model"]["brier"])
        _gate(
            checks, f"{role}:platt_rolling:ece", mt.expected_calibration_error(block.y, model_p), prob["model"]["ece"]
        )
        _gate(checks, f"{role}:B1:platt_rolling:ece", mt.expected_calibration_error(block.y, b1_p), prob["B1"]["ece"])
    reliability = [
        ie.reliability_entry("arrdel15", "lgbm_T2", t2.y, p15),
        ie.reliability_entry("arrdel15", "B1", t2.y, b15),
        ie.reliability_entry("iptal", "lgbm_plan", cancel.y, pc),
        ie.reliability_entry("iptal", "B1", cancel.y, bc),
    ]
    _gate(
        checks,
        "arr_del15/T2:ece_from_bins",
        ie.ece_from_bins(ie.reliability_bins(t2.y, p15)),
        cls[fe.ROLE_ARR_DEL15_T2]["probability"][fe.PRIMARY_PROBABILITY]["model"]["ece"],
    )

    # --- plan quantiles with the rolling conformal offsets of the final test ---
    qb = inputs.quantiles[fe.ROLE_QUANTILES_PLAN]
    mask_q = np.isfinite(test_targets[tg.ARR_DELAY])
    if qb.y.size != int(mask_q.sum()) or not np.array_equal(qb.y, test_targets[tg.ARR_DELAY][mask_q]):
        raise ie.ExportError("plan quantile evaluation rows are not the test rows of the ArrDelay universe")
    rolling = qb.offsets[fe.PRIMARY_SCHEME]
    k80, k95 = mt.quantile_key(0.80), mt.quantile_key(0.95)
    c80 = qb.raw[0.80] + fe._offset_vector(qb.month, rolling[k80])
    c95 = qb.raw[0.95] + fe._offset_vector(qb.month, rolling[k95])
    interval_offset = fe._offset_vector(qb.month, rolling[fe.INTERVAL_KEY])
    lower, upper = qb.raw[fe.INTERVAL[0]] - interval_offset, qb.raw[fe.INTERVAL[1]] + interval_offset
    for name, values in (("P80 conformal", c80), ("P95 conformal", c95), ("interval", np.r_[lower, upper])):
        if not np.all(np.isfinite(values)):
            raise ie.ExportError(f"{name}: non-finite bound (a conformal offset is +inf)")
    qs = stored["quantile"][fe.ROLE_QUANTILES_PLAN]
    stored_rolling = qs["conformal"]["model"][fe.PRIMARY_SCHEME]
    _gate(checks, "arr_delay/plan:n", qb.y.size, qs["n"], 0)
    _gate(
        checks,
        "arr_delay/plan:coverage_raw_q080",
        float(np.mean(qb.y <= qb.raw[0.80])),
        qs["raw"]["model"]["coverage_q080"],
    )
    _gate(checks, "arr_delay/plan:rolling:q080", float(np.mean(qb.y <= c80)), stored_rolling[k80]["coverage"])
    _gate(checks, "arr_delay/plan:rolling:q095", float(np.mean(qb.y <= c95)), stored_rolling[k95]["coverage"])
    _gate(
        checks,
        "arr_delay/plan:rolling:interval80",
        float(np.mean((qb.y >= lower) & (qb.y <= upper))),
        stored_rolling[fe.INTERVAL_KEY]["coverage"],
    )
    stored_offsets = qs["conformal"]["model"]["offsets"][fe.PRIMARY_SCHEME]
    for key in (k80, k95, fe.INTERVAL_KEY):
        for month, record in rolling[key].items():
            _gate(
                checks, f"arr_delay/plan:offset:{key}:{month}", record["offset"], stored_offsets[key][month]["offset"]
            )
    failed = [c for c in checks if not c["ok"]]
    if failed:
        raise ie.ExportError(f"reproduction of the final test failed ({len(failed)} checks): {failed[:10]}")
    clock.lap("reproduction_checks")

    # --- aggregates for the site ---
    model_table = ie.cell_model_table(
        cells.n_cells,
        codes15=cells.codes[mask15],
        y15=t2.y,
        p15=p15,
        codes_q=cells.codes[mask_q],
        y_q=qb.y,
        q50=qb.raw[0.50],
        q80=qb.raw[0.80],
        q95=qb.raw[0.95],
        c80=c80,
        c95=c95,
        lower=lower,
        upper=upper,
    )
    routes = ie.route_table(labels, model_table, plan.or_table)
    observed_or = routes["gozlenen_arrdel15_tamponsuz"].to_numpy(dtype="float64")
    observed_now = routes["gozlenen_arrdel15_orani"].to_numpy(dtype="float64")
    both = np.isfinite(observed_or) & np.isfinite(observed_now)
    tables = ModelTables(
        routes=routes,
        origin_coverage=ie.origin_coverage(qb.origin, qb.y, c80, c95),
        reliability=reliability,
        interval_monthly=ie.monthly_interval_coverage(qb.month, qb.y, lower, upper),
        checks={"final_test": checks, "or_cells": or_check, "development": reproduction},
        info={
            "single_carrier_share_over_090_origins": single_carrier_origins,
            "observed_arrdel15_vs_or_max_abs_diff": float(np.max(np.abs(observed_now[both] - observed_or[both])))
            if both.any()
            else None,
            "observed_arrdel15_note": "BTS ArrDel15 label (this export) vs ArrDelay >= 15 (OR table); information only",
        },
    )
    clock.lap("aggregates")
    tables.info["timings_seconds"] = clock.timings
    tables.info["peak_rss_gb"] = rm._peak_rss_gb()
    return tables


# ----------------------------------------------------------------------------
# payloads
# ----------------------------------------------------------------------------


def build_payloads(
    plan: Preflight, *, created: dt.datetime, tables: ModelTables | None
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Site path -> payload, plus counts of hidden route cells (empty in summary-only mode)."""
    results = plan.results
    version = ie.model_version(results)
    notes = [] if tables is not None else ["Özet kipinde üretildi: rota dosyaları ve güvenilirlik kutuları yok."]
    # M10 at airport level needs the test-period carrier shares (layer data): unknown in summary mode
    hidden_origins: list[str] = [] if tables is None else list(tables.info["single_carrier_share_over_090_origins"])
    payloads: dict[str, dict[str, Any]] = {
        ie.FILE_PATHS["ozet"]: ie.build_ozet(
            results, n_airports=len(plan.targets), created=created, version=version, extra_notes=notes
        ),
        ie.FILE_PATHS["havalimanlari"]: ie.build_havalimanlari(
            results,
            plan.airports,
            created=created,
            version=version,
            coverage=None if tables is None else tables.origin_coverage,
            hidden_origins=hidden_origins,
        ),
        ie.FILE_PATHS["kalibrasyon"]: ie.build_kalibrasyon(
            results,
            created=created,
            version=version,
            reliability=() if tables is None else tables.reliability,
            interval_monthly=() if tables is None else tables.interval_monthly,
        ),
        ie.FILE_PATHS["hava_deneyi"]: ie.build_hava_deneyi(results, created=created, version=version),
        ie.FILE_PATHS["hata_analizi"]: ie.build_hata_analizi(
            results, created=created, version=version, hidden_origins=hidden_origins
        ),
    }
    hidden: dict[str, Any] = {}
    if tables is not None:
        by_origin, route_hidden = ie.route_cells(tables.routes)
        hidden.update(route_hidden)
        unknown = sorted(set(by_origin) - set(plan.targets))
        if unknown:
            raise ie.ExportError(f"route cells for origins outside the target list: {unknown}")
        for code in plan.targets:
            payloads[ie.route_path(code)] = ie.build_rotalar(
                code, by_origin.get(code, []), created=created, version=version
            )
        hidden["per_origin_published"] = {code: len(by_origin.get(code, [])) for code in plan.targets}
    return payloads, hidden


def _write_record(log_dir: Path, stamp: str, record: Mapping[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"arayuz-{stamp}.json"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(_jsonable(dict(record)), ensure_ascii=False, indent=2, allow_nan=False))
    return path


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the static-site JSON files (interface contract 0.1.x).")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="site data folder (must not exist)")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--lock-file", type=Path, default=FINAL_TEST_LOCK_FILE)
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    parser.add_argument("--or-folder", type=Path, default=DEFAULT_OR_FOLDER)
    parser.add_argument("--or-cells", type=Path, default=DEFAULT_OR_CELLS)
    parser.add_argument("--schema", type=Path, default=ie.DEFAULT_SCHEMA_FILE)
    parser.add_argument("--airports", type=Path, default=DEFAULT_AIRPORTS)
    parser.add_argument("--tz-overrides", type=Path, default=DEFAULT_TZ_OVERRIDES)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_FILE)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument(
        "--strict-size",
        action="store_true",
        help="per-file size recommendations (x-azami-boyut-kb) become errors; default: recorded warnings",
    )
    parser.add_argument("--summary-only", action="store_true", help="no layer data; no rotalar/*.json")
    parser.add_argument("--dry-run", action="store_true", help="checks + summary files in memory; nothing written")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    created = dt.datetime.now(dt.UTC)
    stamp = f"{created:%Y%m%dT%H%M%SZ}"
    full = not (args.summary_only or args.dry_run)
    plan = preflight(
        results_path=args.results,
        manifest_path=args.manifest,
        lock_file=args.lock_file,
        schema_path=args.schema,
        airports_csv=args.airports,
        tz_overrides=args.tz_overrides,
        targets_file=args.targets,
        out_dir=args.out,
        or_folder=args.or_folder if not args.summary_only else None,
        or_cells=args.or_cells if not args.summary_only else None,
    )
    tables = compute_model_tables(plan, layer_root=args.layer_dir, lock_file=args.lock_file) if full else None
    payloads, hidden = build_payloads(plan, created=created, tables=tables)
    size_warnings: list[str] = []
    files = ie.prepare_site_files(
        payloads,
        plan.validator,
        created=created,
        version=ie.model_version(plan.results),
        strict_sizes=args.strict_size,
        warnings=size_warnings,
    )
    for warning in size_warnings:
        LOG.warning("size recommendation exceeded: %s", warning)
    listing = [{"path": p, "bytes": len(d)} for p, d in sorted(files.items())]
    record: dict[str, Any] = {
        "created_utc": created.isoformat(),
        "command": f"{COMMAND} {' '.join(argv) if argv is not None else ''}".strip(),
        "mode": "dry_run" if args.dry_run else ("summary_only" if args.summary_only else "full"),
        "out": str(args.out),
        "inputs": plan.record,
        "files": listing,
        "total_bytes": sum(len(d) for d in files.values()),
        "size_warnings": size_warnings,
        "hidden_route_cells": hidden,
    }
    if tables is not None:
        record["checks"] = tables.checks
        record["info"] = tables.info
    if args.dry_run:
        print(json.dumps(_jsonable(record), ensure_ascii=False, indent=2))
        return 0
    if tables is None:
        raise ie.ExportError(
            "--summary-only cannot apply the airport-level M10 rule (carrier shares need layer data); "
            "nothing is written. Use the full run, or --dry-run to inspect."
        )
    written = ie.write_site(files, args.out, stamp=stamp)
    record["written"] = str(written)
    path = _write_record(args.log_dir, stamp, record)
    print(f"Site data: {written}\nRun record: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
