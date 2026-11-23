"""Freeze manifest ("kilit girdisi") and one-time lock record ("kilit kaydı") of the final test (plan section 1.5).

Two different files:
- **Freeze manifest** (input, e.g. ``experiments/son-test-dondurma.json``): what is frozen BEFORE the test, per role
  (``final_eval`` role names): run id, results / model-spec / model files with sha256 and best_iteration, contract and
  its full sha256 digest, dropped features, data fingerprint digest of the run, Platt calibrator (file + key), the F1
  thresholds; plus the git commit of the code, the pre-registration file, the K3 / K5 tolerances, the bootstrap
  settings, the rehearsal output and the leakage evidence for K7. ``draft_manifest`` / the CLI fill it from the runs,
  so nothing is typed by hand.
- **Lock record** (``splits.FINAL_TEST_LOCK_FILE`` = ``experiments/son-test-kilidi.json``): written by
  ``run_final_test`` exactly once, with exclusive create, AFTER every check on development data passed and BEFORE any
  final-test partition is opened. ``splits.require_final_test_access`` refuses any later attempt (the existing
  mechanism; this module does not keep a second copy of it).

Every check here fails closed: a problem list that is not empty stops the final test before the lock is written.
CLI (drafting only, never reads layer data):
    python -m flight_delay.modeling.final_lock --out experiments/son-test-dondurma.json \\
        --role arr_del15/T2=run-20261120T175822Z@cal-20261120T190336Z --role arr_delay/plan=run-... ...
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flight_delay.modeling import bootstrap as bs
from flight_delay.modeling import final_eval as fe
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import targets as tg
from flight_delay.modeling.matrix import DATE_FEATURES
from flight_delay.modeling.splits import FinalTestAccessError
from flight_delay.paths import PROJECT_ROOT

__all__ = [
    "CODE_PATHS",
    "LOCK_SCHEMA",
    "MANIFEST_SCHEMA",
    "QUANTILE_MODEL_KEYS",
    "ROLES",
    "Entry",
    "FileRef",
    "GitProbe",
    "LockVerificationError",
    "Manifest",
    "RoleSpec",
    "check_entries_against_runs",
    "check_git",
    "check_rehearsal",
    "check_role_rules",
    "draft_manifest",
    "entries_fingerprint",
    "leakage_evidence",
    "load_manifest",
    "lock_record",
    "main",
    "run_settings",
    "sha256_file",
    "verify_files",
    "write_lock_record",
]

MANIFEST_SCHEMA = "flight_delay/final-test-manifest/v1"
LOCK_SCHEMA = "flight_delay/final-test-lock/v1"
QUANTILE_MODEL_KEYS = tuple(f"arr_delay_{mt.quantile_key(a)}-lgbm" for a in (0.10, 0.50, 0.80, 0.90, 0.95))
CODE_PATHS = ("deliverables/src", "deliverables/pyproject.toml")  # code identity: no change since the manifest commit


class LockVerificationError(RuntimeError):
    """The freeze manifest does not match the files, the runs, the rules or the code; the final test is refused."""


@dataclass(frozen=True)
class RoleSpec:
    target: str
    contract: str
    kind: str  # 'classifier' | 'quantiles'
    primary: bool
    match: str | None = None  # must have the same dropped features as this role
    required_dropped: tuple[str, ...] | None = None  # exact calendar features dropped (None = no rule)
    description: str = ""


ROLES: dict[str, RoleSpec] = {
    fe.ROLE_ARR_DEL15_T2: RoleSpec(tg.ARR_DEL15, "T2", "classifier", True, description="K1, K2, K3"),
    fe.ROLE_ARR_DEL15_PLAN: RoleSpec(
        tg.ARR_DEL15, "plan", "classifier", False, match=fe.ROLE_ARR_DEL15_T2, description="plan 6 (weather)"
    ),
    fe.ROLE_QUANTILES_PLAN: RoleSpec(tg.ARR_DELAY, "plan", "quantiles", True, description="K4, K5, OR"),
    fe.ROLE_QUANTILES_T2: RoleSpec(
        tg.ARR_DELAY, "T2", "quantiles", False, match=fe.ROLE_QUANTILES_PLAN, description="plan 6 (weather)"
    ),
    fe.ROLE_CANCELLED_PLAN: RoleSpec(
        tg.CANCELLED, "plan", "classifier", True, required_dropped=DATE_FEATURES, description="K6"
    ),
    fe.ROLE_CANCELLED_T2: RoleSpec(
        tg.CANCELLED, "T2", "classifier", False, required_dropped=DATE_FEATURES, description="D2 (secondary)"
    ),
    fe.ROLE_CANCELLED_T2_CALENDAR: RoleSpec(
        tg.CANCELLED, "T2", "classifier", False, required_dropped=(), description="D1 (secondary)"
    ),
}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class FileRef:
    path: str  # relative to the project root (or absolute)
    sha256: str

    def resolve(self, base: Path) -> Path:
        candidate = Path(self.path)
        return candidate if candidate.is_absolute() else base / candidate

    def problems(self, base: Path, what: str) -> list[str]:
        path = self.resolve(base)
        if not path.is_file():
            return [f"{what}: file missing: {self.path}"]
        actual = sha256_file(path)
        return [] if actual == self.sha256 else [f"{what}: sha256 differs for {self.path}"]

    @classmethod
    def of(cls, path: Path, base: Path) -> FileRef:
        return cls(path=_relative(path, base), sha256=sha256_file(path))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FileRef:
        return cls(path=str(data["path"]), sha256=str(data["sha256"]))

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class Entry:
    role: str
    run_id: str
    target: str
    contract: str
    results: FileRef
    spec: FileRef
    models: dict[str, tuple[FileRef, int]]  # model key -> (file, best_iteration)
    contract_sha256: str
    dropped_features: tuple[str, ...]
    data_fingerprint_digest: str
    calibrator: dict[str, Any] | None  # {"file": FileRef, "key", "b1_key", "method"}
    f1_threshold: float | None
    b1_f1_threshold: float | None

    @classmethod
    def from_dict(cls, role: str, data: Mapping[str, Any]) -> Entry:
        calibrator = data.get("calibrator")
        return cls(
            role=role,
            run_id=str(data["run_id"]),
            target=str(data["target"]),
            contract=str(data["contract"]),
            results=FileRef.from_dict(data["results"]),
            spec=FileRef.from_dict(data["spec"]),
            models={str(k): (FileRef.from_dict(v), int(v["best_iteration"])) for k, v in dict(data["models"]).items()},
            contract_sha256=str(data["contract_sha256"]),
            dropped_features=tuple(str(x) for x in data.get("dropped_features", [])),
            data_fingerprint_digest=str(data["data_fingerprint_digest"]),
            calibrator=None
            if calibrator is None
            else {
                "file": FileRef.from_dict(calibrator["file"]),
                "key": str(calibrator["key"]),
                "b1_key": str(calibrator["b1_key"]),
                "method": str(calibrator["method"]),
            },
            f1_threshold=None if data.get("f1_threshold") is None else float(data["f1_threshold"]),
            b1_f1_threshold=None if data.get("b1_f1_threshold") is None else float(data["b1_f1_threshold"]),
        )


@dataclass(frozen=True)
class Manifest:
    path: Path
    sha256: str
    git_commit: str
    pre_registration: FileRef
    entries: dict[str, Entry]
    acceptance: fe.Acceptance | None
    bootstrap: dict[str, Any]
    holm_alpha: float
    leakage: dict[str, Any]
    rehearsal: FileRef | None
    raw: dict[str, Any] = field(repr=False)


def load_manifest(path: Path) -> Manifest:
    """Parse and structurally validate a freeze manifest (ValueError lists every problem)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    problems: list[str] = []
    if data.get("schema") != MANIFEST_SCHEMA:
        problems.append(f"schema must be {MANIFEST_SCHEMA!r}")
    for key in ("git_commit", "pre_registration", "entries", "bootstrap", "holm_alpha"):
        if key not in data:
            problems.append(f"missing key {key!r}")
    unknown = sorted(set(data.get("entries", {})) - set(ROLES))
    if unknown:
        problems.append(f"unknown roles {unknown}; known: {sorted(ROLES)}")
    if problems:
        raise ValueError("Invalid freeze manifest: " + "; ".join(problems))
    entries: dict[str, Entry] = {}
    for role, raw in data["entries"].items():
        try:
            entries[role] = Entry.from_dict(role, raw)
        except (KeyError, TypeError, ValueError) as error:
            problems.append(f"{role}: {error!r}")
    if problems:
        raise ValueError("Invalid freeze manifest: " + "; ".join(problems))
    return Manifest(
        path=Path(path),
        sha256=sha256_file(Path(path)),
        git_commit=str(data["git_commit"]),
        pre_registration=FileRef.from_dict(data["pre_registration"]),
        entries=entries,
        acceptance=fe.Acceptance.from_dict(data["acceptance"]) if data.get("acceptance") else None,
        bootstrap=dict(data["bootstrap"]),
        holm_alpha=float(data["holm_alpha"]),
        leakage=dict(data.get("leakage") or {}),
        rehearsal=FileRef.from_dict(data["rehearsal"]) if data.get("rehearsal") else None,
        raw=data,
    )


def _file_refs(manifest: Manifest) -> list[tuple[str, FileRef]]:
    refs: list[tuple[str, FileRef]] = [("pre_registration", manifest.pre_registration)]
    if manifest.rehearsal is not None:
        refs.append(("rehearsal", manifest.rehearsal))
    for role, entry in manifest.entries.items():
        refs += [(f"{role} results", entry.results), (f"{role} spec", entry.spec)]
        refs += [(f"{role} {key}", ref) for key, (ref, _) in entry.models.items()]
        if entry.calibrator is not None:
            refs.append((f"{role} calibrators", entry.calibrator["file"]))
    for index, review in enumerate(manifest.leakage.get("reviews", [])):
        refs.append((f"leakage review {index}", FileRef.from_dict(review)))
    return refs


def verify_files(manifest: Manifest, base: Path = PROJECT_ROOT) -> list[str]:
    """sha256 of every referenced file must match (fail closed on a missing or changed file)."""
    problems: list[str] = []
    for what, ref in _file_refs(manifest):
        problems += ref.problems(base, what)
    return problems


def _json(ref: FileRef, base: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(ref.resolve(base).read_text(encoding="utf-8"))
    return loaded


def check_entries_against_runs(manifest: Manifest, base: Path = PROJECT_ROOT) -> list[str]:
    """Every frozen value must equal what the run itself recorded."""
    problems: list[str] = []
    for role, entry in manifest.entries.items():
        results, spec = _json(entry.results, base), _json(entry.spec, base)
        meta, features = results["metadata"], results["features"]
        rule = ROLES[role]

        def same(what: str, frozen: Any, recorded: Any, role: str = role) -> None:
            if frozen != recorded:
                problems.append(f"{role}: {what} frozen {frozen!r} != run {recorded!r}")

        same("run_id", entry.run_id, meta["run_id"])
        same("spec run_id", entry.run_id, spec["run_id"])
        same("contract", entry.contract, meta["contract"])
        same("role contract", rule.contract, entry.contract)
        same("target", rule.target, entry.target)
        same("contract_sha256", entry.contract_sha256, features["contract_sha256"])
        same("dropped_features", list(entry.dropped_features), list(features.get("dropped", [])))
        same("data_fingerprint_digest", entry.data_fingerprint_digest, meta["data_fingerprint_digest"])
        if meta.get("oracle"):
            problems.append(f"{role}: oracle runs can never be locked (plan 6)")
        wanted = set(QUANTILE_MODEL_KEYS) if rule.kind == "quantiles" else {f"{rule.target}-lgbm"}
        same("model keys", sorted(wanted), sorted(entry.models))
        for key, (ref, best) in entry.models.items():
            record = results["models"].get(key)
            if record is None or key not in spec["models"]:
                problems.append(f"{role}: model {key} not in the run")
                continue
            same(f"{key} best_iteration", best, record.get("best_iteration"))
            same(f"{key} target", rule.target, record.get("target"))
            if Path(ref.path).name != Path(spec["models"][key]["file"]).name:
                problems.append(f"{role}: {key} file {ref.path} is not the run's {spec['models'][key]['file']}")
        if rule.kind == "classifier":
            block = results["classification"].get(rule.target, {})
            model_threshold = (block.get("LightGBM") or {}).get("threshold", {}).get("value")
            b1_threshold = (block.get("B1") or {}).get("threshold", {}).get("value")
            same("f1_threshold", entry.f1_threshold, model_threshold)
            same("b1_f1_threshold", entry.b1_f1_threshold, b1_threshold)
            if entry.calibrator is None:
                problems.append(f"{role}: a Platt calibrator is required (decision M3 item 3)")
            else:
                if entry.calibrator["method"] != fe.STATIC_PROBABILITY:
                    problems.append(f"{role}: calibrator method must be {fe.STATIC_PROBABILITY!r}")
                stored = _json(entry.calibrator["file"], base)
                same("calibrators run_id", entry.run_id, stored.get("run_id"))
                for key in (entry.calibrator["key"], entry.calibrator["b1_key"]):
                    platt = (stored.get(key) or {}).get(fe.STATIC_PROBABILITY)
                    if not platt or "failed" in platt:
                        problems.append(f"{role}: calibrator {key!r}/{fe.STATIC_PROBABILITY} missing or failed")
    return problems


def run_settings(results: Mapping[str, Any]) -> dict[str, Any]:
    """Fit window and history settings of a run (must be the same for every locked run)."""
    config = results.get("metadata", {}).get("config", {})
    return {
        "fit": results.get("periods", {}).get("fit"),
        **{k: config.get(k) for k in ("m", "min_support", "min_tail", "n_blocks")},
    }


def check_role_rules(manifest: Manifest, *, final: bool, base: Path = PROJECT_ROOT) -> list[str]:
    """Pre-registered role rules (``experiments/son-test-on-kayit.md`` c) and the frozen test settings."""
    problems: list[str] = []
    if final:
        missing = sorted(set(ROLES) - set(manifest.entries))
        if missing:
            problems.append(f"the final test needs every pre-registered role; missing {missing}")
    for role, entry in manifest.entries.items():
        rule = ROLES[role]
        calendar_dropped = set(entry.dropped_features) & set(DATE_FEATURES)
        if rule.required_dropped is not None and calendar_dropped != set(rule.required_dropped):
            problems.append(
                f"{role}: calendar features dropped {sorted(calendar_dropped)}, required {list(rule.required_dropped)}"
            )
        if rule.match is not None and rule.match in manifest.entries:
            other = manifest.entries[rule.match]
            if set(entry.dropped_features) != set(other.dropped_features):
                problems.append(
                    f"{role}: dropped features must equal those of {rule.match} (plan 6: only the weather differs)"
                )
    settings: set[str] = set()
    for entry in manifest.entries.values():
        path = entry.results.resolve(base)
        if path.is_file():
            settings.add(json.dumps(run_settings(_json(entry.results, base)), sort_keys=True))
    if len(settings) > 1:
        problems.append("runs differ in fit window or history settings (m, min_support, min_tail, n_blocks)")
    if final:
        expected = {"replicates": bs.DEFAULT_REPLICATES, "seed": bs.DEFAULT_SEED, "level": bs.CI_LEVEL}
        if {k: manifest.bootstrap.get(k) for k in expected} != expected:
            problems.append(f"bootstrap settings must be {expected} (plan 5.2)")
        if manifest.holm_alpha != bs.HOLM_ALPHA:
            problems.append(f"holm_alpha must be {bs.HOLM_ALPHA}")
        if manifest.acceptance is None:
            problems.append("acceptance (K3 / K5 tolerances) missing: they are fixed from the rehearsal")
        if manifest.rehearsal is None:
            problems.append("rehearsal output missing: the lock is written only after a passed rehearsal")
    return problems


def check_rehearsal(manifest: Manifest, base: Path = PROJECT_ROOT) -> list[str]:
    """The referenced rehearsal must have passed, used the same frozen models, and its tolerance proposal must be the
    manifest's acceptance (pre-registration d: the numbers are not chosen by hand)."""
    if manifest.rehearsal is None:
        return ["rehearsal output missing"]
    output = _json(manifest.rehearsal, base)
    problems: list[str] = []
    if output.get("metadata", {}).get("mode") != "rehearsal":
        problems.append("the referenced file is not a rehearsal output")
    if output.get("metadata", {}).get("smoke", True):
        problems.append("the rehearsal was a smoke run (shortened fit window, day sample or one fold): not valid")
    if set(output.get("blocks", {})) != {"K3", "K4", "pooled"}:
        problems.append("the rehearsal must cover K3, K4 and their pooled block")
    if not output.get("rehearsal_checks", {}).get("passed"):
        problems.append("the rehearsal did not pass its code-path checks")
    frozen = entries_fingerprint(manifest)
    rehearsed = output.get("metadata", {}).get("entries_fingerprint", {})
    for role in frozen:
        if rehearsed.get(role) != frozen[role]:
            problems.append(f"{role}: the rehearsal used other frozen models / settings")
    proposal = (output.get("tolerance_proposal") or {}).get("acceptance")
    if proposal is None:
        problems.append("the rehearsal has no tolerance proposal")
    elif manifest.acceptance is None or not manifest.acceptance.same_values(fe.Acceptance.from_dict(proposal)):
        problems.append("acceptance differs from the rehearsal's tolerance proposal")
    return problems


def entries_fingerprint(manifest: Manifest) -> dict[str, dict[str, Any]]:
    """Role -> run id, model sha256s, dropped features (what the rehearsal must have used)."""
    return {
        role: {
            "run_id": e.run_id,
            "contract": e.contract,
            "dropped_features": list(e.dropped_features),
            "models": {k: ref.sha256 for k, (ref, _) in sorted(e.models.items())},
        }
        for role, e in sorted(manifest.entries.items())
    }


class GitProbe:
    """git queries (injectable for tests): HEAD commit, dirty flag, code files changed since a commit."""

    def __init__(self, cwd: Path = PROJECT_ROOT, runner: Callable[..., Any] | None = None) -> None:
        self.cwd = cwd
        self._run: Callable[..., Any] = runner or subprocess.run

    def _git(self, *args: str) -> str | None:
        try:
            done = self._run(["git", *args], cwd=self.cwd, capture_output=True, text=True, timeout=30, check=True)
        except (OSError, subprocess.SubprocessError):
            return None
        return str(done.stdout).strip()

    def head(self) -> str | None:
        return self._git("rev-parse", "HEAD")

    def dirty(self) -> bool | None:
        status = self._git("status", "--porcelain")
        return None if status is None else bool(status)

    def code_changes_since(self, commit: str) -> list[str] | None:
        out = self._git("diff", "--name-only", "--relative", commit, "HEAD", "--", *CODE_PATHS)
        return None if out is None else [line for line in out.splitlines() if line.strip()]


def check_git(manifest: Manifest, git: GitProbe) -> tuple[list[str], dict[str, Any]]:
    """Clean working tree, and no code change between the manifest's commit and HEAD."""
    head, dirty = git.head(), git.dirty()
    info: dict[str, Any] = {"head": head, "dirty": dirty, "manifest_commit": manifest.git_commit}
    problems: list[str] = []
    if head is None or dirty is None:
        problems.append("git is not available: the code version cannot be proven")
        return problems, info
    if dirty:
        problems.append("the working tree is dirty: commit everything (manifest included) before the final test")
    changes = git.code_changes_since(manifest.git_commit)
    info["code_changes_since_manifest_commit"] = changes
    if changes is None:
        problems.append(f"commit {manifest.git_commit} is unknown to git")
    elif changes:
        problems.append(f"code changed since {manifest.git_commit}: {changes[:10]}")
    return problems, info


def leakage_evidence(manifest: Manifest, base: Path = PROJECT_ROOT) -> dict[str, Any]:
    """K7 (pre-registration b/e): declared pytest result at the manifest commit + no unresolved stage-1 alarm of a
    locked model + at least one review with a passed time travel test + no review status 'leak' for a locked model."""
    pytest_record = manifest.leakage.get("pytest") or {}
    declared_ok = (
        pytest_record.get("commit") == manifest.git_commit
        and int(pytest_record.get("failed", 1)) == 0
        and int(pytest_record.get("passed", 0)) > 0
    )
    reviews = [_json(FileRef.from_dict(r), base) for r in manifest.leakage.get("reviews", [])]
    by_run: dict[str, list[dict[str, Any]]] = {}
    for review in reviews:
        by_run.setdefault(str(review.get("metadata", {}).get("run_id")), []).append(review)
    time_travel_ok = any((r.get("time_travel") or {}).get("passed_all") is True for r in reviews)
    unresolved: list[str] = []
    leaks: list[str] = []
    for role, entry in manifest.entries.items():
        results = _json(entry.results, base)
        for key in entry.models:
            alarm = (results["models"].get(key) or {}).get("leakage_alarm") or {}
            verdicts = [
                (r.get("leakage_review") or {}).get("models", {}).get(key) for r in by_run.get(entry.run_id, [])
            ]
            verdicts = [v for v in verdicts if v is not None]
            if any(v.get("status") == "leak" for v in verdicts):
                leaks.append(f"{role}:{key}")
            if alarm.get("raised") and not any(v.get("reportable") for v in verdicts):
                unresolved.append(f"{role}:{key}")
    passed = bool(declared_ok and time_travel_ok and not unresolved and not leaks)
    return {
        "passed": passed,
        "pytest_declared": pytest_record or None,
        "pytest_declared_ok": declared_ok,
        "pytest_note": "declared by the person who ran the tests; the script cannot run pytest",
        "time_travel_passed": time_travel_ok,
        "unresolved_stage1_alarms": unresolved,
        "leak_verdicts": leaks,
        "reviews": len(reviews),
    }


def lock_record(manifest: Manifest, git_info: Mapping[str, Any], created: dt.datetime, command: str) -> dict[str, Any]:
    return {
        "schema": LOCK_SCHEMA,
        "created_utc": created.isoformat(),
        "status": "started: development checks passed; final-test data is read after this file is written",
        "command": command,
        "manifest": {"path": str(manifest.path), "sha256": manifest.sha256},
        "git": dict(git_info),
        "pre_registration": manifest.pre_registration.to_dict(),
        "entries": entries_fingerprint(manifest),
        "note": "Written once (plan 1.5). If the run fails after this point, do not delete this file: the decision "
        "goes to the user.",
    }


def write_lock_record(lock_file: Path, record: Mapping[str, Any]) -> Path:
    """Exclusive create: a second writer gets FinalTestAccessError, never a silent overwrite."""
    lock = Path(lock_file)
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=2))
    except FileExistsError as error:
        raise FinalTestAccessError(f"The final test has already been started (lock record exists: {lock})") from error
    return lock


# ----------------------------------------------------------------------------
# drafting a manifest from runs (no layer data is read)
# ----------------------------------------------------------------------------


def draft_manifest(
    roles: Mapping[str, tuple[str, str | None]],
    *,
    base: Path = PROJECT_ROOT,
    results_dir: Path | None = None,
    model_dir: Path | None = None,
    git_commit: str,
    pre_registration: Path,
    acceptance: Mapping[str, Any] | None = None,
    rehearsal: Path | None = None,
    leakage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Manifest dict from {role: (run_id, calibration folder name or None)}; every value copied from the run."""
    results_root = results_dir or base / "experiments" / "models"
    models_root = model_dir or base / "deliverables" / "models"
    entries: dict[str, Any] = {}
    for role, (run_id, calibration) in roles.items():
        if role not in ROLES:
            raise KeyError(f"Unknown role {role!r}; known: {sorted(ROLES)}")
        rule = ROLES[role]
        results_path = results_root / run_id / "model-results.json"
        spec_path = models_root / run_id / "model-spec.json"
        results = json.loads(results_path.read_text(encoding="utf-8"))
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        keys = QUANTILE_MODEL_KEYS if rule.kind == "quantiles" else (f"{rule.target}-lgbm",)
        models = {}
        for key in keys:
            if key not in spec["models"]:
                raise KeyError(f"{run_id} has no model {key}")
            path = models_root / run_id / Path(spec["models"][key]["file"]).name
            best = results["models"][key]["best_iteration"]
            models[key] = {**FileRef.of(path, base).to_dict(), "best_iteration": best}
        entry: dict[str, Any] = {
            "run_id": run_id,
            "target": rule.target,
            "contract": results["metadata"]["contract"],
            "results": FileRef.of(results_path, base).to_dict(),
            "spec": FileRef.of(spec_path, base).to_dict(),
            "models": models,
            "contract_sha256": results["features"]["contract_sha256"],
            "dropped_features": list(results["features"].get("dropped", [])),
            "data_fingerprint_digest": results["metadata"]["data_fingerprint_digest"],
            "calibrator": None,
            "f1_threshold": None,
            "b1_f1_threshold": None,
        }
        if rule.kind == "classifier":
            block = results["classification"][rule.target]
            entry["f1_threshold"] = block["LightGBM"]["threshold"]["value"]
            entry["b1_f1_threshold"] = block["B1"]["threshold"]["value"]
            if calibration is None:
                raise ValueError(f"{role}: give the calibration folder (run-...@cal-...)")
            calibrators = results_root / run_id / "calibration" / calibration / "calibrators.json"
            entry["calibrator"] = {
                "file": FileRef.of(calibrators, base).to_dict(),
                "key": f"{rule.target}/LightGBM",
                "b1_key": f"{rule.target}/B1",
                "method": fe.STATIC_PROBABILITY,
            }
        entries[role] = entry
    return {
        "schema": MANIFEST_SCHEMA,
        "created_utc": dt.datetime.now(dt.UTC).isoformat(),
        "git_commit": git_commit,
        "pre_registration": FileRef.of(pre_registration, base).to_dict(),
        "entries": entries,
        "acceptance": dict(acceptance) if acceptance is not None else None,
        "bootstrap": {"replicates": bs.DEFAULT_REPLICATES, "seed": bs.DEFAULT_SEED, "level": bs.CI_LEVEL},
        "holm_alpha": bs.HOLM_ALPHA,
        "rehearsal": FileRef.of(rehearsal, base).to_dict() if rehearsal is not None else None,
        "leakage": dict(leakage) if leakage is not None else {},
    }


def _parse_role(text: str) -> tuple[str, tuple[str, str | None]]:
    role, _, rest = text.partition("=")
    run_id, _, calibration = rest.partition("@")
    if not role or not run_id:
        raise argparse.ArgumentTypeError(f"--role needs ROLE=run-...[@cal-...]: {text!r}")
    return role, (run_id, calibration or None)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft a final-test freeze manifest from saved runs (no data read).")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--role", action="append", type=_parse_role, required=True, help="ROLE=run-ID[@cal-ID]")
    parser.add_argument("--git-commit", default=None, help="Default: HEAD (the tree must be clean at the final test).")
    parser.add_argument("--pre-registration", type=Path, default=PROJECT_ROOT / "experiments" / "son-test-on-kayit.md")
    parser.add_argument("--acceptance-from-rehearsal", type=Path, default=None, help="rehearsal results JSON")
    parser.add_argument("--pytest-passed", type=int, default=None, help="Declared pytest result at --git-commit.")
    parser.add_argument("--pytest-failed", type=int, default=None)
    parser.add_argument("--review", type=Path, action="append", default=[], help="run_permutation results JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.out.exists():
        parser.error(f"{args.out} exists; it is not overwritten")
    commit = args.git_commit or GitProbe().head()
    if commit is None:
        parser.error("git HEAD unknown; pass --git-commit")
    acceptance = None
    rehearsal = None
    if args.acceptance_from_rehearsal is not None:
        rehearsal = args.acceptance_from_rehearsal
        output = json.loads(rehearsal.read_text(encoding="utf-8"))
        acceptance = (output.get("tolerance_proposal") or {}).get("acceptance")
    leakage: dict[str, Any] = {"reviews": [FileRef.of(p, PROJECT_ROOT).to_dict() for p in args.review]}
    if args.pytest_passed is not None:
        leakage["pytest"] = {
            "commit": commit,
            "passed": args.pytest_passed,
            "failed": args.pytest_failed if args.pytest_failed is not None else 0,
            "command": "python -m pytest (deliverables/tests/unit)",
        }
    manifest = draft_manifest(
        dict(args.role),
        git_commit=str(commit),
        pre_registration=args.pre_registration,
        acceptance=acceptance,
        rehearsal=rehearsal,
        leakage=leakage,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Manifest: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
