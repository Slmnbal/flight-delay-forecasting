"""Freeze manifest / lock record (plan 1.5), git checks, role rules, K7 evidence, calendar rule (SYNTHETIC files)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from flight_delay.modeling import calendar_rule as cr
from flight_delay.modeling import final_eval as fe
from flight_delay.modeling import final_lock as fl
from flight_delay.modeling import splits as sp
from flight_delay.modeling.matrix import DATE_FEATURES, LayerTableReader


class FakeGit(fl.GitProbe):
    def __init__(self, head="abc123", dirty=False, changes=()):
        super().__init__()
        self._head, self._dirty, self._changes = head, dirty, changes

    def head(self):
        return self._head

    def dirty(self):
        return self._dirty

    def code_changes_since(self, commit):
        return None if self._changes is None else list(self._changes)


def _entry(dropped=(), contract="T2", target="arr_del15", models=None):
    ref = {"path": "x.json", "sha256": "0" * 64}
    return {
        "run_id": "run-1",
        "target": target,
        "contract": contract,
        "results": ref,
        "spec": ref,
        "models": models or {f"{target}-lgbm": {**ref, "best_iteration": 3}},
        "contract_sha256": "c",
        "dropped_features": list(dropped),
        "data_fingerprint_digest": "d",
        "calibrator": None,
    }


def _manifest(tmp_path: Path, entries: dict, **extra) -> fl.Manifest:
    data = {
        "schema": fl.MANIFEST_SCHEMA,
        "git_commit": "abc123",
        "pre_registration": {"path": "pre.md", "sha256": "0" * 64},
        "entries": entries,
        "bootstrap": {"replicates": 1000, "seed": 42, "level": 0.95},
        "holm_alpha": 0.05,
        **extra,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return fl.load_manifest(path)


def test_lock_record_is_written_once_and_the_split_guard_then_refuses(tmp_path):
    lock = tmp_path / "experiments" / "son-test-kilidi.json"
    sp.require_final_test_access(True, lock)  # nothing written yet
    with pytest.raises(sp.FinalTestAccessError):
        sp.require_lock_written(lock)
    with pytest.raises(sp.FinalTestAccessError):
        LayerTableReader(tmp_path, allow_final_test=True, lock_file=lock)  # final-test reader needs the lock first
    fl.write_lock_record(lock, {"schema": fl.LOCK_SCHEMA})
    assert sp.require_lock_written(lock) == lock
    with pytest.raises(sp.FinalTestAccessError):
        fl.write_lock_record(lock, {"schema": "second"})
    assert json.loads(lock.read_text(encoding="utf-8")) == {"schema": fl.LOCK_SCHEMA}
    with pytest.raises(sp.FinalTestAccessError):
        sp.require_final_test_access(True, lock)  # the existing mechanism refuses any second look
    reader = LayerTableReader(tmp_path, allow_final_test=True, lock_file=lock)
    assert reader.allow_final_test is True and LayerTableReader(tmp_path).allow_final_test is False


def test_manifest_parsing_and_file_hashes(tmp_path):
    with pytest.raises(ValueError, match="schema"):
        (tmp_path / "bad.json").write_text(json.dumps({"schema": "x"}), encoding="utf-8")
        fl.load_manifest(tmp_path / "bad.json")
    with pytest.raises(ValueError, match="unknown roles"):
        _manifest(tmp_path, {"arr_del15/T3": _entry()})
    (tmp_path / "pre.md").write_text("rules", encoding="utf-8")
    ref = fl.FileRef.of(tmp_path / "pre.md", tmp_path)
    assert ref.path == "pre.md" and ref.problems(tmp_path, "pre") == []
    (tmp_path / "pre.md").write_text("rules changed", encoding="utf-8")
    assert "sha256 differs" in ref.problems(tmp_path, "pre")[0]
    assert "missing" in fl.FileRef("nope.md", "0").problems(tmp_path, "x")[0]


def test_role_rules_matching_calendar_settings_and_final_requirements(tmp_path):
    entries = {
        fe.ROLE_ARR_DEL15_T2: _entry(dropped=DATE_FEATURES),
        fe.ROLE_ARR_DEL15_PLAN: _entry(dropped=(), contract="plan"),
        fe.ROLE_CANCELLED_PLAN: _entry(dropped=(), contract="plan", target="cancelled"),
    }
    manifest = _manifest(tmp_path, entries)
    problems = fl.check_role_rules(manifest, final=False, base=tmp_path)
    assert any("must equal those of arr_del15/T2" in p for p in problems)
    assert any("cancelled/plan: calendar features dropped" in p for p in problems)
    final = fl.check_role_rules(manifest, final=True, base=tmp_path)
    assert any("needs every pre-registered role" in p for p in final)
    assert any("acceptance" in p for p in final) and any("rehearsal output missing" in p for p in final)
    wrong_bootstrap = _manifest(tmp_path, {}, bootstrap={"replicates": 200, "seed": 42, "level": 0.95})
    assert any("bootstrap settings" in p for p in fl.check_role_rules(wrong_bootstrap, final=True, base=tmp_path))
    assert set(fl.ROLES) == set(fe.CLASSIFIER_ROLES) | set(fe.QUANTILE_ROLES)


def test_git_checks_fail_closed(tmp_path):
    manifest = _manifest(tmp_path, {})
    assert fl.check_git(manifest, FakeGit())[0] == []
    assert any("dirty" in p for p in fl.check_git(manifest, FakeGit(dirty=True))[0])
    changed = fl.check_git(manifest, FakeGit(changes=["deliverables/src/flight_delay/modeling/gbm.py"]))[0]
    assert any("code changed" in p for p in changed)
    assert any("unknown" in p for p in fl.check_git(manifest, FakeGit(changes=None))[0])
    assert any("not available" in p for p in fl.check_git(manifest, FakeGit(head=None))[0])


def test_git_probe_uses_git_diff_on_the_code_paths(tmp_path):
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        if args[1] == "status":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args[1] == "diff":
            return subprocess.CompletedProcess(args, 0, stdout="deliverables/src/x.py\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="abc123\n", stderr="")

    probe = fl.GitProbe(tmp_path, runner=runner)
    assert probe.head() == "abc123" and probe.dirty() is False
    assert probe.code_changes_since("abc123") == ["deliverables/src/x.py"]
    assert calls[-1][:6] == ["git", "diff", "--name-only", "--relative", "abc123", "HEAD"]
    assert calls[-1][-2:] == list(fl.CODE_PATHS)

    def failing(args, **kwargs):
        raise subprocess.CalledProcessError(128, args)

    assert fl.GitProbe(tmp_path, runner=failing).code_changes_since("nope") is None


def test_leakage_evidence_needs_declared_tests_time_travel_and_resolved_alarms(tmp_path):
    results = {"models": {"arr_del15-lgbm": {"leakage_alarm": {"raised": True}}}}
    (tmp_path / "results.json").write_text(json.dumps(results), encoding="utf-8")
    review = {
        "metadata": {"run_id": "run-1"},
        "time_travel": {"passed_all": True},
        "leakage_review": {"models": {"arr_del15-lgbm": {"status": "cleared", "reportable": True}}},
    }
    (tmp_path / "review.json").write_text(json.dumps(review), encoding="utf-8")
    entry = _entry()
    entry["results"] = fl.FileRef.of(tmp_path / "results.json", tmp_path).to_dict()
    pytest_record = {"commit": "abc123", "passed": 10, "failed": 0}
    reviews = [fl.FileRef.of(tmp_path / "review.json", tmp_path).to_dict()]
    manifest = _manifest(tmp_path, {fe.ROLE_ARR_DEL15_T2: entry}, leakage={"pytest": pytest_record, "reviews": reviews})
    assert fl.leakage_evidence(manifest, tmp_path)["passed"] is True
    no_review = _manifest(tmp_path, {fe.ROLE_ARR_DEL15_T2: entry}, leakage={"pytest": pytest_record})
    evidence = fl.leakage_evidence(no_review, tmp_path)
    assert evidence["passed"] is False and evidence["unresolved_stage1_alarms"] == ["arr_del15/T2:arr_del15-lgbm"]
    other = {"pytest": {**pytest_record, "commit": "zzz"}, "reviews": reviews}
    other_commit = _manifest(tmp_path, {fe.ROLE_ARR_DEL15_T2: entry}, leakage=other)
    assert fl.leakage_evidence(other_commit, tmp_path)["pytest_declared_ok"] is False


def _run(run_id, *, dropped=(), months=None, totals=None, contract="T2", params=None):
    months = months or {"9": 0.20, "10": 0.20, "11": 0.20, "12": 0.20}
    totals = totals or {"brier": 0.20, "n": 100, "log_loss": 0.5, "roc_auc": 0.7}
    segment_rows = [{"segment": m, "n": 25, "brier": v, "calibration_in_the_large": 0.0} for m, v in months.items()]
    quantile_rows = [{"segment": m, "n": 25, "pinball_q080": 10 * v, "pinball_q095": 5 * v} for m, v in months.items()]
    quantile_total = {"n": 100, "pinball_q080": 10 * totals["brier"], "pinball_q095": 5 * totals["brier"]}
    return {
        "metadata": {"run_id": run_id, "contract": contract},
        "periods": {"fit": {"start": "2023-09-01", "end": "2025-08-31"}, "val_a": {"start": "2025-09-01"}},
        "features": {"dropped": list(dropped)},
        "tuning": {"selected": {"arr_del15": {"params": params or {"num_leaves": 127}}}},
        "classification": {
            "arr_del15": {"LightGBM": {"sets": {"val_a": {"total": totals, "segments": {"month": segment_rows}}}}}
        },
        "quantile": {
            "arr_delay": {
                "LightGBM": {"sets": {"val_a": {"total": quantile_total, "segments": {"month": quantile_rows}}}}
            }
        },
    }


def test_calendar_rule_needs_the_total_and_three_of_four_months():
    with_calendar = _run("run-C")
    better_3_of_4 = _run(
        "run-D",
        dropped=DATE_FEATURES,
        months={"9": 0.19, "10": 0.19, "11": 0.19, "12": 0.21},
        totals={"brier": 0.195, "n": 100, "log_loss": 0.5, "roc_auc": 0.7},
    )
    decision = cr.decide(with_calendar, better_3_of_4)
    assert decision["valid"] and decision["val_b_read"] is False
    assert decision["families"]["arr_del15"]["drop_calendar_features"] is True
    assert decision["families"]["arr_delay"]["drop_calendar_features"] is True  # P80 and P95 follow the same months
    only_2 = _run(
        "run-D",
        dropped=DATE_FEATURES,
        months={"9": 0.19, "10": 0.19, "11": 0.21, "12": 0.21},
        totals={"brier": 0.195, "n": 100, "log_loss": 0.5, "roc_auc": 0.7},
    )
    assert cr.decide(with_calendar, only_2)["families"]["arr_del15"]["drop_calendar_features"] is False
    total_worse = _run(
        "run-D",
        dropped=DATE_FEATURES,
        months={"9": 0.19, "10": 0.19, "11": 0.19, "12": 0.19},
        totals={"brier": 0.20, "n": 100, "log_loss": 0.5, "roc_auc": 0.7},  # a tie is not an improvement
    )
    assert cr.decide(with_calendar, total_worse)["families"]["arr_del15"]["drop_calendar_features"] is False
    assert "KALIR" in cr.render(cr.decide(with_calendar, only_2))


def test_calendar_rule_refuses_invalid_comparisons():
    assert not cr.decide(_run("a"), _run("b"))["valid"]  # nothing dropped: not the D comparison
    assert not cr.decide(_run("a"), _run("b", dropped=DATE_FEATURES, contract="plan"))["valid"]
    assert not cr.decide(_run("a"), _run("b", dropped=DATE_FEATURES, params={"num_leaves": 31}))["valid"]
