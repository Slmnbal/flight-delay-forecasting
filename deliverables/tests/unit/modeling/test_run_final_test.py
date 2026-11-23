"""End to end on a tiny SYNTHETIC layer: frozen runs -> manifest -> rehearsal (K3/K4) -> final test (once) -> refusals.

Nothing here touches the project's real lock file: every call passes its own lock path / output folder.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from modeling_synth import build_frame, write_layer
from models_synth import SMALL_PARAMS, write_side_tables

from flight_delay.modeling import final_eval as fe
from flight_delay.modeling import final_lock as fl
from flight_delay.modeling import run_calibration as rc
from flight_delay.modeling import run_final_test as rft
from flight_delay.modeling import run_models as rm
from flight_delay.modeling import splits as sp
from flight_delay.modeling.matrix import DATE_FEATURES

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)


class FakeGit(fl.GitProbe):
    def __init__(self, dirty=False, changes=()):
        super().__init__()
        self._dirty, self._changes = dirty, changes

    def head(self):
        return "abc123"

    def dirty(self):
        return self._dirty

    def code_changes_since(self, commit):
        return list(self._changes)


def signal_frame(start: str, end: str, *, per_day: int = 8, seed: int = 7) -> pd.DataFrame:
    """Flights whose delay and cancellation depend on Origin and the hour (so every model has something to learn)."""
    rng = np.random.default_rng(seed)
    origins, dests = ["ORD", "ATL", "DEN"], ["LAX", "JFK"]
    hours = [600, 800, 1100, 1400, 1700, 2000, 2300]
    records = []
    for day in pd.date_range(start, end, freq="D"):
        for _ in range(per_day):
            o, h = int(rng.integers(len(origins))), int(rng.integers(len(hours)))
            delay = float(np.round(-12.0 + 6.0 * h + 8.0 * o + rng.gamma(1.5, 10.0) - 10.0))
            cancelled = int(rng.random() < 0.02 + 0.05 * (o == 2) + 0.01 * h)
            records.append(
                {
                    "FlightDate": day.strftime("%Y-%m-%d"),
                    "Origin": origins[o],
                    "Dest": dests[int(rng.integers(len(dests)))],
                    "Reporting_Airline": ["AA", "UA"][int(rng.integers(2))],
                    "CRSDepTime": hours[h],
                    "ArrDelay": np.nan if cancelled else delay,
                    "ArrDel15": np.nan if cancelled else float(delay >= 15),
                    "Cancelled": cancelled,
                    "Diverted": 0,
                    "ActualElapsedTime": np.nan if cancelled else 130.0 + delay / 4,
                    "TaxiOut": np.nan if cancelled else 15.0,
                }
            )
    return build_frame(records)


def _config(**changes):
    options = {
        "max_train_months": 3,
        "tuning": False,
        "num_boost_round": 12,
        "early_stopping_rounds": 3,
        "quantile_num_boost_round": 12,
        "interval_models": True,
        "num_threads": 1,
        "segment_min_n": 10,
        "param_overrides": SMALL_PARAMS,
    }
    options.update(changes)
    return rm.RunConfig(**options)


@contextlib.contextmanager
def hidden_final_months(layer: Path, backup: Path):
    """Move every final-test partition away: any attempt to open one fails (the rehearsal must not need them)."""
    moved = []
    for month_dir in sorted(layer.glob("*/year=2026/month=0[3-8]")):
        target = backup / month_dir.relative_to(layer)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(month_dir), str(target))
        moved.append((target, month_dir))
    try:
        yield len(moved)
    finally:
        for target, month_dir in moved:
            shutil.move(str(target), str(month_dir))


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    root = tmp_path_factory.mktemp("final")
    layer = root / "layer"
    frame = signal_frame("2023-09-01", "2026-08-31")  # the rehearsal needs the full fold fit windows
    write_layer(layer, frame)
    write_side_tables(layer, frame)
    out, models = root / "experiments" / "models", root / "deliverables" / "models"
    specs = {
        "C": ("T2", ("arr_del15", "cancelled", "quantiles"), ()),
        "D": ("T2", ("arr_del15", "cancelled", "quantiles"), DATE_FEATURES),
        "P": ("plan", ("arr_del15", "quantiles"), ()),
        "PD": ("plan", ("arr_del15", "cancelled", "quantiles"), DATE_FEATURES),
    }
    runs = {}
    for i, (name, (contract, chosen, drop)) in enumerate(specs.items()):
        folder = rm.run(
            layer_root=layer,
            output_dir=out,
            model_dir=models,
            config=_config(contract=contract, models=chosen, drop_features=drop),
            mlflow_mode="off",
            hash_files=False,
            now=NOW + dt.timedelta(minutes=i),
        )
        calibration = rc.run_posthoc(
            folder,
            models / folder.name,
            layer_root=layer,
            segment_min_n=10,
            hash_files=False,
            now=NOW + dt.timedelta(minutes=10 + i),
        )
        runs[name] = (folder.name, calibration.name)
    pre = root / "experiments" / "son-test-on-kayit.md"
    pre.write_text("önceden kayıt (test)", encoding="utf-8")
    roles = {
        fe.ROLE_ARR_DEL15_T2: runs["C"],
        fe.ROLE_ARR_DEL15_PLAN: runs["P"],
        fe.ROLE_QUANTILES_PLAN: (runs["P"][0], None),
        fe.ROLE_QUANTILES_T2: (runs["C"][0], None),
        fe.ROLE_CANCELLED_PLAN: runs["PD"],
        fe.ROLE_CANCELLED_T2: runs["D"],
        fe.ROLE_CANCELLED_T2_CALENDAR: runs["C"],
    }
    common = {"base": root, "results_dir": out, "model_dir": models, "git_commit": "abc123", "pre_registration": pre}
    draft = fl.draft_manifest(roles, acceptance=fe.Acceptance(k5_segment_min_n=10).to_dict(), **common)
    draft_path = root / "experiments" / "son-test-dondurma-taslak.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    return SimpleNamespace(root=root, layer=layer, runs=runs, roles=roles, draft=draft_path, common=common, out=out)


@pytest.fixture(scope="module")
def rehearsal(frozen, tmp_path_factory):
    backup = tmp_path_factory.mktemp("hidden")
    original = fl.write_lock_record

    def refuse(*args, **kwargs):
        raise AssertionError("the rehearsal must never write the lock record")

    fl.write_lock_record = refuse
    try:
        with hidden_final_months(frozen.layer, backup) as moved:
            assert moved > 0
            folder = rft.run_rehearsal(
                frozen.draft,
                layer_root=frozen.layer,
                base=frozen.root,
                output_dir=frozen.root / "experiments" / "son-test-prova",
                num_threads=1,
                hash_files=False,
                now=NOW,
            )
    finally:
        fl.write_lock_record = original
    return folder


def _final_manifest(frozen, rehearsal_folder, name="son-test-dondurma.json", **overrides):
    results = rehearsal_folder / rft.RESULTS_FILE["rehearsal"]
    proposal = json.loads(results.read_text(encoding="utf-8"))["tolerance_proposal"]["acceptance"]
    leakage = {"pytest": {"commit": "abc123", "passed": 1, "failed": 0}, "reviews": []}
    options = {"acceptance": proposal, "rehearsal": results, "leakage": leakage}
    options.update(overrides)
    manifest = fl.draft_manifest(frozen.roles, **frozen.common, **options)
    path = frozen.root / "experiments" / name
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_manifest_draft_copies_every_frozen_value(frozen):
    manifest = fl.load_manifest(frozen.draft)
    assert set(manifest.entries) == set(fl.ROLES)
    assert fl.verify_files(manifest, frozen.root) == []
    assert fl.check_entries_against_runs(manifest, frozen.root) == []
    assert fl.check_role_rules(manifest, final=False, base=frozen.root) == []
    entry = manifest.entries[fe.ROLE_QUANTILES_PLAN]
    assert sorted(entry.models) == sorted(fl.QUANTILE_MODEL_KEYS) and entry.contract == "plan"
    assert manifest.entries[fe.ROLE_CANCELLED_PLAN].dropped_features == DATE_FEATURES
    assert manifest.entries[fe.ROLE_ARR_DEL15_T2].calibrator["method"] == "platt"


def test_rehearsal_retrains_per_fold_and_never_touches_the_final_test(frozen, rehearsal):
    output = json.loads((rehearsal / rft.RESULTS_FILE["rehearsal"]).read_text(encoding="utf-8"))
    meta = output["metadata"]
    assert meta["mode"] == "rehearsal" and meta["final_test_read"] is False and meta["lock_written"] is False
    assert set(output["blocks"]) == {"K3", "K4", "pooled"}
    k3 = output["folds"]["K3"]["periods"]
    assert k3["evaluation"] == {"start": "2025-03-01", "end": "2025-05-31"}
    assert k3["calibration"] == {"start": "2025-01-01", "end": "2025-02-28"}
    assert k3["early_stopping"] == {"start": "2024-09-01", "end": "2024-12-31"}
    assert k3["fit"] == {"start": "2023-09-01", "end": "2024-08-31"}
    assert meta["smoke"] is False
    assert len(output["folds"]["K4"]["models"]) == 15  # 1 + 1 + 5 + 5 + 3 models, retrained in the fold
    for fold in ("K3", "K4"):
        paths = [f["path"] for f in output["folds"][fold]["files"]["files"]]
        assert paths and not any("year=2026" in p for p in paths)
    checks = output["rehearsal_checks"]
    assert checks["passed"] is True, checks
    assert output["tolerance_proposal"]["acceptance"] is not None
    assert output["tolerance_proposal"]["from_block"] == "pooled"
    assert set(meta["entries_fingerprint"]) == set(fl.ROLES)
    summary = (rehearsal / rft.SUMMARY_FILE["rehearsal"]).read_text(encoding="utf-8")
    assert "PROVA – SON TEST DEĞİL" in summary and "K3 / K5 tolerans önerisi" in summary


def test_final_test_runs_once_after_the_lock_and_refuses_a_second_look(frozen, rehearsal, tmp_path):
    manifest = _final_manifest(frozen, rehearsal)
    lock = tmp_path / "son-test-kilidi.json"
    folder = rft.run_final(
        manifest,
        layer_root=frozen.layer,
        base=frozen.root,
        output_dir=tmp_path / "son-test",
        lock_file=lock,
        git=FakeGit(),
        now=NOW,
    )
    record = json.loads(lock.read_text(encoding="utf-8"))
    assert record["schema"] == fl.LOCK_SCHEMA and set(record["entries"]) == set(fl.ROLES)
    output = json.loads((folder / rft.RESULTS_FILE["final_test"]).read_text(encoding="utf-8"))
    assert output["metadata"]["mode"] == "final_test"
    assert output["metadata"]["periods"]["context"] == {"start": "2025-11-05", "end": "2026-02-28"}
    test_paths = [f["path"] for f in output["metadata"]["final_test_files"]["files"]]
    assert any("year=2026/month=03" in p for p in test_paths) and any("year=2026/month=08" in p for p in test_paths)
    assert all(entry["reproduces_run"] for entry in output["verification"]["reproduction"].values())
    block = output["blocks"]["final_test"]
    assert set(block["criteria"]) == {"K1", "K2", "K3", "K4", "K5", "K6", "K7"}
    assert block["criteria"]["K7"]["passed"] is False  # no permutation review given: time travel not shown
    assert block["days"]["n"] == 184 and block["bootstrap"]["replicates"] == 1000
    assert len(block["holm"]["family"]) == 7
    assert "arr_del15" in block["comparisons"]["weather_contribution"]
    summary = (folder / rft.SUMMARY_FILE["final_test"]).read_text(encoding="utf-8")
    assert "SON TEST SONUÇLARI" in summary and "### Kabul ölçütleri" in summary
    with pytest.raises(sp.FinalTestAccessError):
        rft.run_final(manifest, layer_root=frozen.layer, base=frozen.root, lock_file=lock, git=FakeGit(), now=NOW)


def test_final_test_fails_closed_before_any_lock(frozen, rehearsal, tmp_path):
    good = _final_manifest(frozen, rehearsal, name="good.json")
    counter = iter(range(100))

    def refused(manifest, git=None, match=""):
        lock = tmp_path / f"lock-{next(counter)}.json"
        with pytest.raises(fl.LockVerificationError, match=match):
            rft.run_final(
                manifest,
                layer_root=frozen.layer,
                base=frozen.root,
                output_dir=tmp_path / "never",
                lock_file=lock,
                git=git or FakeGit(),
                now=NOW,
            )
        assert not lock.exists() and not (tmp_path / "never").exists()

    refused(good, git=FakeGit(dirty=True), match="dirty")
    refused(good, git=FakeGit(changes=["deliverables/src/flight_delay/modeling/gbm.py"]), match="code changed")
    tampered = json.loads(good.read_text(encoding="utf-8"))
    role = fe.ROLE_ARR_DEL15_T2
    tampered["entries"][role]["models"]["arr_del15-lgbm"]["sha256"] = "0" * 64
    bad_sha = frozen.root / "experiments" / "tampered.json"
    bad_sha.write_text(json.dumps(tampered), encoding="utf-8")
    refused(bad_sha, match="sha256 differs")
    no_rehearsal = _final_manifest(frozen, rehearsal, name="no-rehearsal.json", rehearsal=None)
    refused(no_rehearsal, match="rehearsal")
    widened = _final_manifest(
        frozen, rehearsal, name="widened.json", acceptance=fe.Acceptance(k3_citl_abs_max=0.5).to_dict()
    )
    refused(widened, match="tolerance proposal")
    missing_role = json.loads(good.read_text(encoding="utf-8"))
    del missing_role["entries"][fe.ROLE_CANCELLED_T2_CALENDAR]
    partial = frozen.root / "experiments" / "partial.json"
    partial.write_text(json.dumps(missing_role), encoding="utf-8")
    refused(partial, match="every pre-registered role")
    # a smoke rehearsal (one fold, shortened fit window) can never open the lock
    smoke = rft.run_rehearsal(
        frozen.draft,
        layer_root=frozen.layer,
        base=frozen.root,
        output_dir=frozen.root / "experiments" / "son-test-prova-smoke",
        folds=("K4",),
        max_fit_months=3,
        num_threads=1,
        hash_files=False,
        replicates=50,
        now=NOW,
    )
    smoke_output = json.loads((smoke / rft.RESULTS_FILE["rehearsal"]).read_text(encoding="utf-8"))
    assert smoke_output["metadata"]["smoke"] is True and smoke_output["rehearsal_checks"]["passed"] is False
    assert set(smoke_output["blocks"]) == {"K4"}
    from_smoke = _final_manifest(frozen, smoke, name="from-smoke.json")
    refused(from_smoke, match="smoke run")


def test_cli_separates_the_final_test_from_rehearsal_options(frozen):
    with pytest.raises(SystemExit):
        rft.main(["--manifest", str(frozen.draft)])  # a mode is required
    with pytest.raises(SystemExit):
        rft.main(["--final", "--manifest", str(frozen.draft), "--folds", "K3"])
    with pytest.raises(SystemExit):
        rft.main(["--final", "--rehearsal", "--manifest", str(frozen.draft)])


def test_rehearsal_periods_and_context():
    k4 = rft.rehearsal_periods("K4")
    assert (str(k4.fit.end), str(k4.early_stopping.start), str(k4.early_stopping.end)) == (
        "2024-11-30",
        "2024-12-01",
        "2025-03-31",
    )
    assert (str(k4.calibration.start), str(k4.calibration.end)) == ("2025-04-01", "2025-05-31")
    assert k4.evaluation == sp.get_fold("K4").evaluation and k4.fit.start == sp.TRAIN.start
    context = rft.context_period(sp.FINAL_TEST, sp.VAL_B.end)
    assert (str(context.start), str(context.end)) == ("2025-11-05", "2026-02-28")
    with pytest.raises(KeyError):
        rft.rehearsal_periods("K9")


def test_plan_runs_can_reuse_the_t2_parameters_only_on_purpose(frozen, tmp_path):
    source = frozen.runs["C"][0]
    plan = {"contract": "plan", "models": ("arr_del15",)}
    with pytest.raises(ValueError, match="tuning-from-other-contract"):
        rm.run(layer_root=frozen.layer, output_dir=frozen.out, config=_config(**plan, tuning_from_run=source))
    with pytest.raises(ValueError, match="needs tuning_from_run"):
        rm.run(layer_root=frozen.layer, config=_config(**plan, tuning_from_other_contract=True), mlflow_mode="off")
    folder = rm.run(
        layer_root=frozen.layer,
        output_dir=frozen.out,
        model_dir=tmp_path / "models",
        config=_config(**plan, tuning_from_run=source, tuning_from_other_contract=True),
        mlflow_mode="off",
        hash_files=False,
        now=NOW + dt.timedelta(hours=5),
    )
    results = json.loads((folder / rm.RESULTS_NAME).read_text(encoding="utf-8"))
    assert results["tuning"]["from_run_contract"] == "T2"
    assert results["tuning"]["selected"]["arr_del15"]["selected_by"] == f"from {source} (contract T2)"
    assert results["metadata"]["config"]["tuning_from_other_contract"] is True
    summary = (folder / rm.SUMMARY_NAME).read_text(encoding="utf-8")
    assert "kaynak sözleşme T2" in summary
    assert "Val-B'nin kullanımları" in summary and "başka hiçbir seçimde" not in summary
