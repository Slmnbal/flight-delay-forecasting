"""Read the project settings and validate them with Pydantic. No network, no MLflow needed.

Usage:
    from flight_delay.mlops.settings import load_settings
    settings = load_settings()                          # flight_delay/mlops/project.yaml (package data)
    settings.absolute(settings.paths.raw_data)          # absolute path relative to the project root
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from flight_delay.paths import PROJECT_ROOT

__all__ = [
    "ARTIFACTS_DIR_NAME",
    "DEFAULT_SETTINGS_PATH",
    "TRACKING_DB_NAME",
    "TRACKING_URI_ENV",
    "MlflowSettings",
    "PathSettings",
    "Settings",
    "SET_PLACEHOLDER",
    "SettingsError",
    "UnknownTopicError",
    "load_settings",
]

TRACKING_URI_ENV = "MLFLOW_TRACKING_URI"
TRACKING_DB_NAME = "mlflow.db"
ARTIFACTS_DIR_NAME = "artifacts"

# The default settings ship inside the package (package data), next to this module.
DEFAULT_SETTINGS_PATH = Path(__file__).resolve().with_name("project.yaml")


class SettingsError(ValueError):
    """The settings file was not found or is invalid."""


class UnknownTopicError(ValueError):
    """A run topic has no ``required_metrics`` entry in the settings."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PathSettings(_Strict):
    raw_data: Path
    processed_data: Path
    target_airports_file: Path
    experiment_outputs: Path
    result_json: Path

    @field_validator("*")
    @classmethod
    def _relative_and_inside(cls, v: Path) -> Path:
        if v.is_absolute():
            raise ValueError(f"path must be relative to the project root: {v}")
        if ".." in v.parts:
            raise ValueError(f"path cannot leave the project root: {v}")
        return v


_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SET_PLACEHOLDER = "{set}"


class MlflowSettings(_Strict):
    """MLflow settings.

    ``required_metrics`` maps a run topic (the ``topic`` given to ``start_run``) to the metric names that
    must be recorded in every run of that topic. A name containing ``{set}`` is expanded once for each entry
    of ``evaluation_sets`` (e.g. ``{set}_roc_auc`` -> ``val_a_roc_auc``, ``val_b_roc_auc``).

    Policy: an EMPTY mapping means "not configured" (nothing is enforced). Once the mapping has any topic,
    a topic that is not in it is an error (see ``required_metrics_for``); a topic that needs no metric is
    declared explicitly with an empty list.
    """

    tracking_dir: Path
    experiment_prefix: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    evaluation_sets: list[str] = Field(default_factory=lambda: ["val_a", "val_b"])
    required_metrics: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("tracking_dir")
    @classmethod
    def _relative(cls, v: Path) -> Path:
        if v.is_absolute() or ".." in v.parts:
            raise ValueError(f"tracking_dir must be relative to the project root and inside it: {v}")
        return v

    @field_validator("evaluation_sets")
    @classmethod
    def _sets(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if not re.match(r"^[A-Za-z0-9_]+$", s)]
        if bad or len(set(v)) != len(v):
            raise ValueError(f"evaluation_sets must be unique names of letters/digits/underscore: {v}")
        return v

    @field_validator("required_metrics")
    @classmethod
    def _topics(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        for topic, names in v.items():
            if not _SLUG.match(topic):
                raise ValueError(f"required_metrics topic must be lowercase letters/digits/hyphens: {topic!r}")
            if any(not n.strip() for n in names) or len(set(names)) != len(names):
                raise ValueError(f"required_metrics[{topic!r}] has an empty or duplicated name: {names}")
        return v

    def required_metrics_for(self, topic: str) -> list[str]:
        """Expanded required metric names for ``topic``.

        Unknown topic -> ``UnknownTopicError`` (when the mapping is non-empty). Reason: an empty list for an
        unknown topic would silently switch the check off exactly for new work (a new model topic would
        pass with no metric at all). Failing early, before any MLflow run is opened, forces the topic to be
        added to ``project.yaml`` (or declared with ``[]``). An empty mapping (nothing configured) enforces
        nothing.
        """
        if not self.required_metrics:
            return []
        if topic not in self.required_metrics:
            raise UnknownTopicError(
                f"No required_metrics entry for topic {topic!r}; known topics: {sorted(self.required_metrics)}. "
                "Add it to mlflow.required_metrics in project.yaml (use [] for 'none required')."
            )
        names: list[str] = []
        for template in self.required_metrics[topic]:
            if SET_PLACEHOLDER in template:
                names.extend(template.replace(SET_PLACEHOLDER, s) for s in self.evaluation_sets)
            else:
                names.append(template)
        return names


class Settings(_Strict):
    version: int = Field(ge=1)
    seed: int = Field(ge=0, le=2**32 - 1)
    paths: PathSettings
    mlflow: MlflowSettings
    project_root: Path = Field(default=PROJECT_ROOT, exclude=True)

    def absolute(self, relative: Path) -> Path:
        """Turn a project-relative path into an absolute path."""
        return (self.project_root / relative).resolve()

    def tracking_uri(self, environ: Mapping[str, str] | None = None) -> str:
        """MLflow tracking URI.

        ``MLFLOW_TRACKING_URI`` (if set and non-empty) wins. Otherwise a local SQLite database inside the
        project: ``sqlite:///<project>/<tracking_dir>/mlflow.db`` (absolute, independent of the working
        directory). The file store is never used: recent MLflow versions reject it.
        """
        env = os.environ if environ is None else environ
        override = env.get(TRACKING_URI_ENV, "").strip()
        if override:
            return override
        return f"sqlite:///{self.tracking_db_path().as_posix()}"

    def tracking_db_path(self) -> Path:
        """Absolute path of the local SQLite tracking database."""
        return self.absolute(self.mlflow.tracking_dir) / TRACKING_DB_NAME

    def artifact_root(self) -> Path:
        """Absolute local folder for run artifacts (used only with the default tracking URI)."""
        return self.absolute(self.mlflow.tracking_dir) / ARTIFACTS_DIR_NAME

    def uses_default_tracking_uri(self, environ: Mapping[str, str] | None = None) -> bool:
        """True when the project-local SQLite store is in use.

        ``mlflow.set_tracking_uri`` also writes ``MLFLOW_TRACKING_URI`` into ``os.environ`` (MLflow 3), so an
        environment value equal to our own default URI still counts as the default (root cause of the
        2026-11-19 bug: artifacts went to ``./mlruns/<id>`` instead of ``mlruns/artifacts``).
        """
        env = os.environ if environ is None else environ
        override = env.get(TRACKING_URI_ENV, "").strip()
        return not override or override == f"sqlite:///{self.tracking_db_path().as_posix()}"


def load_settings(path: str | Path | None = None, project_root: Path | None = None) -> Settings:
    """Read and validate the YAML. Raises SettingsError if the file is missing or a field is invalid."""
    path = Path(path) if path else DEFAULT_SETTINGS_PATH
    if not path.is_file():
        raise SettingsError(f"Settings file not found: {path}")
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SettingsError(f"Could not read YAML: {path}: {e}") from e
    if not isinstance(raw, dict):
        raise SettingsError(f"The settings file must be a mapping: {path}")
    if "project_root" in raw:
        raise SettingsError("'project_root' cannot be given in the file (unknown field).")
    if project_root is not None:
        raw["project_root"] = project_root
    try:
        return Settings.model_validate(raw)
    except Exception as e:  # includes pydantic.ValidationError
        raise SettingsError(f"Settings could not be validated ({path}): {e}") from e


if __name__ == "__main__":
    print(load_settings().model_dump_json(indent=2))
