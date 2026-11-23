"""Local MLflow wrapper: experiment naming rule, run contract, data fingerprint.

No server; by default a local SQLite database under settings.mlflow.tracking_dir (see Settings.tracking_uri;
MLFLOW_TRACKING_URI overrides it). The legacy file store is not used. MLflow is needed ONLY when a
run is started; if it is not installed MLflowMissingError is raised (no silent fallback). Contract / name
checks work without MLflow and are tested that way.

Usage (data scientist):
    settings = load_settings()
    fingerprint = data_fingerprint(settings.absolute(settings.paths.processed_data))
    data = DataVersion(start_month="2023-01", end_month="2025-12")
    with start_run(settings, "modeling", "arr-delay-quantile", "lgbm", data, fingerprint) as run:
        run.parameter("n_estimators", 300)
        run.metric("val_a_pinball_q050", 11.2)  # + the topic's other required metrics (project.yaml)
        run.artifact_file(Path("experiments/feature_importance.csv"))
"""

from __future__ import annotations

import importlib
import math
import re
import tempfile
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from flight_delay.mlops import reproducibility as repro
from flight_delay.mlops.settings import Settings, UnknownTopicError

__all__ = [
    "REQUIRED_PARAMS",
    "STAGES",
    "ContractError",
    "DataVersion",
    "MLflowMissingError",
    "RunRecorder",
    "build_context",
    "check_contract",
    "experiment_name",
    "load_mlflow",
    "run_name",
    "select_experiment",
    "start_run",
]

STAGES = ("data", "baseline", "modeling", "evaluation", "or")
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# Parameter keys that are REQUIRED in every run (contract)
REQUIRED_PARAMS = (
    "data_start_month",
    "data_end_month",
    "data_fingerprint",
    "seed",
    "git_commit",
    "git_dirty",
    "stage",
    "model",
)


class MLflowMissingError(ImportError):
    """MLflow is not installed."""


class ContractError(ValueError):
    """The experiment record does not satisfy the contract."""


class DataVersion(BaseModel):
    """Data version = covered month range (+ optional label). Content identity lives in the fingerprint."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    start_month: str
    end_month: str
    label: str | None = None

    @field_validator("start_month", "end_month")
    @classmethod
    def _month(cls, v: str) -> str:
        if not _MONTH.match(v):
            raise ValueError(f"month must be in 'YYYY-MM' form: {v!r}")
        return v

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.end_month < self.start_month:  # YYYY-MM lexicographic order = time order
            raise ValueError("end_month cannot be before start_month")
        return self


def experiment_name(stage: str, topic: str, prefix: str = "havayolu-ds") -> str:
    """Rule: '<prefix>/<stage>/<topic>'. stage from the fixed list, topic lowercase-digits-hyphen."""
    if stage not in STAGES:
        raise ContractError(f"stage must be one of {STAGES}: {stage!r}")
    for label, value in (("prefix", prefix), ("topic", topic)):
        if not _SLUG.match(value):
            raise ContractError(
                f"{label} must be lowercase letters/digits/hyphens (e.g. 'delay-regression'): {value!r}"
            )
    return f"{prefix}/{stage}/{topic}"


def run_name(model: str, data: DataVersion, seed: int) -> str:
    """Rule: '<model>__<startMonth>_<endMonth>__s<seed>' (e.g. lgbm__2023-01_2025-12__s42)."""
    if not _SLUG.match(model):
        raise ContractError(f"model name must be lowercase letters/digits/hyphens: {model!r}")
    return f"{model}__{data.start_month}_{data.end_month}__s{seed}"


def build_context(
    stage: str,
    model: str,
    data: DataVersion,
    seed: int,
    fingerprint: dict[str, Any],
    git: dict[str, Any] | None = None,
    versions: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (parameters, tags). Every required contract key is filled."""
    git = git if git is not None else repro.git_info()
    versions = versions if versions is not None else repro.library_versions()
    params = {
        "stage": stage,
        "model": model,
        "data_start_month": data.start_month,
        "data_end_month": data.end_month,
        "data_fingerprint": str(fingerprint["digest"]),
        "seed": str(seed),
        "git_commit": str(git.get("commit", "unknown")),
        "git_dirty": str(git.get("dirty")),
    }
    tags = {f"library.{name}": version for name, version in versions.items()}
    if data.label:
        tags["data_label"] = data.label
    return params, tags


def check_contract(
    params: dict[str, Any],
    metrics: dict[str, float] | None = None,
    required_metrics: tuple[str, ...] | list[str] = (),
) -> None:
    """Raise ContractError if a required parameter / metric is missing."""
    missing = [k for k in REQUIRED_PARAMS if k not in params or params[k] in (None, "")]
    if missing:
        raise ContractError(f"Required parameters are missing: {missing}")
    if metrics is not None:
        missing_metrics = [m for m in required_metrics if m not in metrics or not math.isfinite(metrics[m])]
        if missing_metrics:
            raise ContractError(f"Required metrics were not recorded: {missing_metrics}")


def load_mlflow(module_name: str = "mlflow") -> ModuleType:
    """Import MLflow; explicit error if it is missing. (module_name exists for tests only.)"""
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        raise MLflowMissingError(
            f"'{module_name}' is not installed. Install: pip install -e 'deliverables[mlflow]'"
        ) from e


def _inside(location: str | None, root: Path) -> bool:
    """Is an experiment ``artifact_location`` (file URI or plain path) under ``root``?"""
    if not location:
        return False
    uri = root.as_uri().rstrip("/")
    plain = root.as_posix().rstrip("/")
    return any(location == p or location.startswith(p + "/") for p in (uri, plain))


def select_experiment(mlflow_module: Any, settings: Settings, experiment: str) -> str | None:
    """Make ``experiment`` the active experiment; return its artifact location (None if unknown).

    With the default (project-local SQLite) tracking URI the artifact folder is pinned to
    ``<project>/<tracking_dir>/artifacts`` when the experiment is first created; otherwise MLflow would
    default to ``./mlruns`` relative to the working directory. If ``MLFLOW_TRACKING_URI`` is set, MLflow's
    own defaults apply. The file store is never used.

    The experiment is activated by id (``set_experiment(experiment_id=...)``) so ``set_experiment`` can never
    create it implicitly with the default location. The location is read back; if an already existing
    experiment points outside the artifact root (location is immutable in MLflow) a warning is emitted,
    the run still proceeds.
    """
    if not settings.uses_default_tracking_uri():
        mlflow_module.set_experiment(experiment)
        return None
    root = settings.artifact_root()
    root.mkdir(parents=True, exist_ok=True)  # also creates the folder that holds mlflow.db
    found = mlflow_module.get_experiment_by_name(experiment)
    if found is None:
        experiment_id = mlflow_module.create_experiment(experiment, artifact_location=root.as_uri())
        location = root.as_uri()
    else:
        experiment_id = found.experiment_id
        location = found.artifact_location
    mlflow_module.set_experiment(experiment_id=experiment_id)
    if not _inside(location, root):
        warnings.warn(
            f"Experiment {experiment!r} (id {experiment_id}) has artifact_location {location!r}, outside "
            f"{root.as_uri()}. MLflow cannot change it; use a new experiment name for new runs.",
            stacklevel=2,
        )
    return location


class RunRecorder:
    """Thin layer that records into an open MLflow run and keeps track of what was recorded."""

    def __init__(self, mlflow_module: Any, params: dict[str, str]) -> None:
        self._mlflow = mlflow_module
        self.parameters: dict[str, Any] = dict(params)
        self.metrics: dict[str, float] = {}

    def parameter(self, name: str, value: object) -> None:
        if name in self.parameters and str(self.parameters[name]) != str(value):
            raise ContractError(f"A parameter cannot be silently changed: {name}")
        self.parameters[name] = value
        self._mlflow.log_param(name, value)

    def metric(self, name: str, value: float, step: int | None = None) -> None:
        self.metrics[name] = float(value)
        self._mlflow.log_metric(name, float(value), step=step)

    def artifact_file(self, path: Path, subfolder: str | None = None) -> None:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Artifact file not found: {path}")
        self._mlflow.log_artifact(str(path), artifact_path=subfolder)


@contextmanager
def start_run(
    settings: Settings,
    stage: str,
    topic: str,
    model: str,
    data: DataVersion,
    fingerprint: dict[str, Any],
    mlflow_module_name: str = "mlflow",
) -> Iterator[RunRecorder]:
    """Open a contract-compliant MLflow run. Fixes the seed from the settings and records it.

    Recorded: required parameters, library-version tags, 'environment/environment.json' and
    'data/data_fingerprint.json' artifacts. On exit the required metrics of the topic
    (``settings.mlflow.required_metrics_for(topic)``) are checked (error if missing or non-finite).
    A topic without a settings entry raises ContractError before MLflow is touched.
    """
    experiment = experiment_name(stage, topic, settings.mlflow.experiment_prefix)  # name check first (no MLflow needed)
    name = run_name(model, data, settings.seed)
    try:
        required_metrics = settings.mlflow.required_metrics_for(topic)  # per topic; unknown topic fails early
    except UnknownTopicError as e:
        raise ContractError(str(e)) from e
    mlflow = load_mlflow(mlflow_module_name)

    repro.set_seed(settings.seed)
    params, tags = build_context(
        stage, model, data, settings.seed, fingerprint, git=repro.git_info(settings.project_root)
    )
    check_contract(params)

    mlflow.set_tracking_uri(settings.tracking_uri())
    select_experiment(mlflow, settings, experiment)
    with mlflow.start_run(run_name=name):
        mlflow.log_params(params)
        mlflow.set_tags(tags)
        with tempfile.TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            repro.write_json(fingerprint, temp_dir / "data_fingerprint.json")
            repro.write_json(repro.environment_summary(), temp_dir / "environment.json")
            mlflow.log_artifact(str(temp_dir / "data_fingerprint.json"), artifact_path="data")
            mlflow.log_artifact(str(temp_dir / "environment.json"), artifact_path="environment")
        recorder = RunRecorder(mlflow, params)
        yield recorder
        check_contract(recorder.parameters, recorder.metrics, required_metrics)
