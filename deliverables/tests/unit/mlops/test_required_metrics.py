"""Per-topic required metrics: settings schema, expansion, unknown-topic policy, start_run check. Offline."""

import json
import math
from contextlib import contextmanager
from pathlib import Path

import pytest

from flight_delay.mlops import settings as st
from flight_delay.mlops import tracking as tr
from flight_delay.paths import PROJECT_ROOT

DATA = tr.DataVersion(start_month="2023-01", end_month="2025-12")
FINGERPRINT = {"digest": "abc123"}
BASELINE_JSON = PROJECT_ROOT / "experiments" / "baselines" / "run-20261119T174701Z" / "baseline-results.json"
# same mapping as run_baselines._MLFLOW_TOPICS (JSON key -> MLflow topic); kept literal so no heavy imports
TOPICS = {"arr_del15": "arrdel15", "cancelled": "cancelled", "arr_delay": "arr-delay-quantile"}

YAML = """
version: 1
seed: 7
paths:
  raw_data: a/raw
  processed_data: a/proc
  target_airports_file: a/h.txt
  experiment_outputs: experiments
  result_json: web/data
mlflow:
  tracking_dir: mlruns
  experiment_prefix: havayolu-ds
  evaluation_sets: [val_a, val_b]
  required_metrics:
    t1: ["{set}_auc", "n_rows"]
    free: []
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(st.TRACKING_URI_ENV, raising=False)


@pytest.fixture
def small_settings(tmp_path: Path) -> st.Settings:
    path = tmp_path / "project.yaml"
    path.write_text(YAML, encoding="utf-8")
    return st.load_settings(path, project_root=tmp_path)


def test_expansion_of_set_placeholder(small_settings):
    assert small_settings.mlflow.required_metrics_for("t1") == ["val_a_auc", "val_b_auc", "n_rows"]


def test_explicit_empty_list_requires_nothing(small_settings):
    assert small_settings.mlflow.required_metrics_for("free") == []


def test_unknown_topic_is_an_explicit_error(small_settings):
    with pytest.raises(st.UnknownTopicError, match="known topics"):
        small_settings.mlflow.required_metrics_for("new-model")


def test_empty_mapping_enforces_nothing(tmp_path):
    path = tmp_path / "project.yaml"
    path.write_text(YAML.split("  evaluation_sets")[0], encoding="utf-8")
    s = st.load_settings(path, project_root=tmp_path)
    assert s.mlflow.required_metrics == {}
    assert s.mlflow.required_metrics_for("anything") == []


def test_bad_topic_key_and_old_list_form_are_rejected(tmp_path):
    for bad in ('  required_metrics:\n    Bad_Topic: ["x"]\n', '  required_metrics: ["x"]\n'):
        path = tmp_path / "project.yaml"
        path.write_text(YAML.split("  evaluation_sets")[0] + bad, encoding="utf-8")
        with pytest.raises(st.SettingsError):
            st.load_settings(path, project_root=tmp_path)


def test_real_project_yaml_topics_and_no_unstable_metrics(project_settings):
    m = project_settings.mlflow
    assert set(m.required_metrics) == {"arrdel15", "cancelled", "arr-delay-quantile"}
    every = {n for topic in m.required_metrics for n in m.required_metrics_for(topic)}
    assert "val_a_roc_auc" in every and "val_b_pinball_q050" in every
    assert not [n for n in every if "calibration_slope" in n or "calibration_intercept" in n]


class _RunFake:
    """Just enough of the MLflow fluent API for start_run (calls are not checked here)."""

    def __init__(self) -> None:
        self.experiments: dict[str, object] = {}

    def set_tracking_uri(self, uri):
        pass

    def get_experiment_by_name(self, name):
        return self.experiments.get(name)

    def create_experiment(self, name, artifact_location=None, tags=None):
        self.experiments[name] = type("E", (), {"experiment_id": "1", "artifact_location": artifact_location})()
        return "1"

    def set_experiment(self, experiment_name=None, experiment_id=None):
        pass

    @contextmanager
    def start_run(self, run_name=None):
        yield

    def log_params(self, params):
        pass

    def set_tags(self, tags):
        pass

    def log_artifact(self, path, artifact_path=None):
        pass

    def log_param(self, name, value):
        pass

    def log_metric(self, name, value, step=None):
        pass


@pytest.fixture
def fake_module(monkeypatch):
    fake = _RunFake()
    monkeypatch.setattr(tr, "load_mlflow", lambda name="mlflow": fake)
    return fake


def _run(settings, topic, metrics):
    with tr.start_run(settings, "baseline", topic, "b0", DATA, FINGERPRINT) as run:
        for name, value in metrics.items():
            run.metric(name, value)


def test_start_run_passes_when_topic_metrics_present(small_settings, fake_module):
    _run(small_settings, "t1", {"val_a_auc": 0.7, "val_b_auc": 0.6, "n_rows": 10})


def test_start_run_fails_on_missing_metric(small_settings, fake_module):
    with pytest.raises(tr.ContractError, match="val_b_auc"):
        _run(small_settings, "t1", {"val_a_auc": 0.7, "n_rows": 10})


def test_non_finite_metric_counts_as_missing(small_settings, fake_module):
    with pytest.raises(tr.ContractError, match="val_a_auc"):
        _run(small_settings, "t1", {"val_a_auc": math.nan, "val_b_auc": 0.6, "n_rows": 10})


def test_start_run_unknown_topic_fails_before_mlflow(small_settings, monkeypatch):
    def boom(name="mlflow"):
        raise AssertionError("MLflow must not be touched")

    monkeypatch.setattr(tr, "load_mlflow", boom)
    with (
        pytest.raises(tr.ContractError, match="No required_metrics entry"),
        tr.start_run(small_settings, "baseline", "new-model", "b0", DATA, FINGERPRINT),
    ):
        pass


def test_start_run_free_topic_needs_no_metric(small_settings, fake_module):
    _run(small_settings, "free", {})


def _emitted_metrics(results: dict) -> list[tuple[str, dict[str, float]]]:
    """(topic, metrics) per (job, target, baseline), built exactly like run_baselines._log_mlflow."""
    out = []
    for job in results["jobs"]:
        groups = [(t, job["classification"][t]) for t in ("arr_del15", "cancelled")]
        groups.append(("arr_delay", job["quantile"]["arr_delay"]))
        for target, per_set in groups:
            for baseline in job["parameters"]["baselines"]:
                metrics = {}
                for set_name, per_baseline in per_set.items():
                    for metric, value in per_baseline[baseline]["total"].items():
                        if isinstance(value, int | float) and math.isfinite(float(value)):
                            metrics[f"{set_name}_{metric}"] = float(value)
                out.append((TOPICS[target], metrics))
    return out


@pytest.mark.skipif(not BASELINE_JSON.is_file(), reason="baseline result file not present")
def test_existing_baseline_results_satisfy_required_metrics(project_settings):
    results = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    emitted = _emitted_metrics(results)
    assert len(emitted) == 9
    for topic, metrics in emitted:
        required = project_settings.mlflow.required_metrics_for(topic)
        tr.check_contract(dict.fromkeys(tr.REQUIRED_PARAMS, "x"), metrics, required)
