"""Tracking URI resolution (SQLite default, env override) and experiment selection. Offline; no real MLflow."""

from pathlib import Path

import pytest

from flight_delay.mlops import settings as st
from flight_delay.mlops import tracking as tr
from flight_delay.paths import PROJECT_ROOT

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
"""


@pytest.fixture
def local_settings(tmp_path: Path) -> st.Settings:
    path = tmp_path / "project.yaml"
    path.write_text(YAML, encoding="utf-8")
    return st.load_settings(path, project_root=tmp_path)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(st.TRACKING_URI_ENV, raising=False)


def test_default_uri_is_sqlite_inside_the_project(local_settings, tmp_path):
    expected = f"sqlite:///{(tmp_path.resolve() / 'mlruns' / 'mlflow.db').as_posix()}"
    assert local_settings.tracking_uri() == expected
    assert not local_settings.tracking_uri().startswith("file:")


def test_artifact_root_is_inside_tracking_dir(local_settings, tmp_path):
    assert local_settings.artifact_root() == tmp_path.resolve() / "mlruns" / "artifacts"


def test_real_settings_default_points_to_project_root():
    s = st.load_settings(st.DEFAULT_SETTINGS_PATH)
    assert s.tracking_db_path() == (PROJECT_ROOT / "mlruns" / "mlflow.db").resolve()
    assert s.tracking_uri({}).endswith("/mlruns/mlflow.db")


def test_env_variable_overrides_default(local_settings, monkeypatch):
    monkeypatch.setenv(st.TRACKING_URI_ENV, "sqlite:////tmp/other.db")
    assert local_settings.tracking_uri() == "sqlite:////tmp/other.db"
    assert not local_settings.uses_default_tracking_uri()


def test_explicit_environ_mapping_is_used(local_settings):
    assert local_settings.tracking_uri({st.TRACKING_URI_ENV: "http://example.invalid:5000"}) == (
        "http://example.invalid:5000"
    )


def test_empty_env_variable_falls_back_to_default(local_settings, monkeypatch):
    monkeypatch.setenv(st.TRACKING_URI_ENV, "  ")
    assert local_settings.tracking_uri().startswith("sqlite:///")
    assert local_settings.uses_default_tracking_uri()


def test_uri_does_not_depend_on_working_directory(local_settings, tmp_path, monkeypatch):
    before = local_settings.tracking_uri()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert local_settings.tracking_uri() == before
    s = st.load_settings(st.DEFAULT_SETTINGS_PATH)
    assert s.tracking_db_path().is_absolute()
    assert s.tracking_db_path() == (PROJECT_ROOT / "mlruns" / "mlflow.db").resolve()


def test_no_file_store_opt_out_in_source():
    src = (Path(st.__file__).parent / "tracking.py").read_text(encoding="utf-8")
    src += Path(st.__file__).read_text(encoding="utf-8")
    assert "MLFLOW_ALLOW_FILE_STORE" not in src


class _Exp:
    def __init__(self, experiment_id: str, name: str, artifact_location: str) -> None:
        self.experiment_id, self.name, self.artifact_location = experiment_id, name, artifact_location


class _FakeMlflow:
    """Mirrors the real fluent API contract (MLflow 3):

    * ``get_experiment_by_name(name)`` -> Experiment | None (has ``experiment_id``, ``artifact_location``)
    * ``create_experiment(name, artifact_location=None, tags=None)`` -> experiment id (str); duplicate name raises;
      without ``artifact_location`` the location is ``<default root>/<id>``
    * ``set_experiment(experiment_name=None, experiment_id=None)``: an unknown NAME is created implicitly with the
      DEFAULT location (this is how the legacy ``mlruns/1`` experiments came about); an unknown id raises.
    """

    DEFAULT_ROOT = "file:///somewhere-else/mlruns"

    def __init__(self, existing: dict[str, str] | None = None) -> None:
        self.experiments: dict[str, _Exp] = {}
        self.calls: list[tuple] = []
        self.active: _Exp | None = None
        for name, location in (existing or {}).items():
            self._add(name, location)

    def _add(self, name: str, location: str | None) -> _Exp:
        experiment_id = str(len(self.experiments) + 1)
        exp = _Exp(experiment_id, name, location or f"{self.DEFAULT_ROOT}/{experiment_id}")
        self.experiments[name] = exp
        return exp

    def get_experiment_by_name(self, name):
        self.calls.append(("get", name))
        return self.experiments.get(name)

    def create_experiment(self, name, artifact_location=None, tags=None):
        self.calls.append(("create", name, artifact_location))
        if name in self.experiments:
            raise RuntimeError(f"Experiment {name!r} already exists")
        return self._add(name, artifact_location).experiment_id

    def set_experiment(self, experiment_name=None, experiment_id=None):
        self.calls.append(("set", experiment_name, experiment_id))
        if experiment_id is not None:
            matches = [e for e in self.experiments.values() if e.experiment_id == experiment_id]
            if not matches:
                raise RuntimeError(f"No experiment with id {experiment_id}")
            self.active = matches[0]
        else:
            self.active = self.experiments.get(experiment_name) or self._add(experiment_name, None)
        return self.active


def test_select_experiment_pins_artifact_location_for_new_experiment(local_settings):
    fake = _FakeMlflow()
    location = tr.select_experiment(fake, local_settings, "havayolu-ds/baseline/x")
    root = local_settings.artifact_root()
    assert root.is_dir()  # also creates the folder that will hold mlflow.db
    assert fake.active is not None and fake.active.name == "havayolu-ds/baseline/x"
    assert fake.active.artifact_location == root.as_uri() == location
    assert [c[0] for c in fake.calls] == ["get", "create", "set"]


def test_select_experiment_activates_by_id_so_set_experiment_never_creates(local_settings):
    fake = _FakeMlflow()
    tr.select_experiment(fake, local_settings, "e")
    set_call = fake.calls[-1]
    assert set_call[1] is None and set_call[2] == fake.active.experiment_id
    assert len(fake.experiments) == 1


def test_select_experiment_does_not_recreate_existing_inside_root(local_settings, recwarn):
    root_uri = local_settings.artifact_root().as_uri()
    fake = _FakeMlflow({"e": root_uri})
    tr.select_experiment(fake, local_settings, "e")
    assert [c[0] for c in fake.calls] == ["get", "set"]
    assert not [w for w in recwarn if "artifact_location" in str(w.message)]


def test_select_experiment_warns_for_legacy_experiment_outside_root(local_settings):
    fake = _FakeMlflow({"e": None})  # created the old way: default location, outside the artifact root
    with pytest.warns(UserWarning, match="outside"):
        location = tr.select_experiment(fake, local_settings, "e")
    assert location == f"{_FakeMlflow.DEFAULT_ROOT}/1"
    assert fake.active.name == "e"  # the run still goes ahead


def test_select_experiment_with_env_uri_leaves_defaults_to_mlflow(local_settings, monkeypatch, tmp_path):
    monkeypatch.setenv(st.TRACKING_URI_ENV, "sqlite:////tmp/other.db")
    fake = _FakeMlflow()
    assert tr.select_experiment(fake, local_settings, "e") is None
    assert fake.calls == [("set", "e", None)]
    assert not (tmp_path / "mlruns").exists()


def test_inside_helper():
    root = Path("/p/mlruns/artifacts")
    assert tr._inside(root.as_uri() + "/3", root)
    assert tr._inside("/p/mlruns/artifacts", root)
    assert not tr._inside("file:///p/mlruns/1", root)
    assert not tr._inside("/p/mlruns/artifactsX", root)
    assert not tr._inside(None, root)


def test_real_mlflow_pins_artifact_location_in_sqlite(local_settings, tmp_path):
    """Real MLflow against a temp SQLite DB (skipped when MLflow is not installed)."""
    mlflow = pytest.importorskip("mlflow")
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(local_settings.tracking_uri())
    try:
        name = "havayolu-ds/baseline/real-check"
        location = tr.select_experiment(mlflow, local_settings, name)
        exp = mlflow.get_experiment_by_name(name)
        root = local_settings.artifact_root()
        assert exp is not None
        assert tr._inside(exp.artifact_location, root), exp.artifact_location
        assert location == root.as_uri()
        assert mlflow.get_experiment_by_name(name).experiment_id == exp.experiment_id
        with mlflow.start_run(run_name="r") as active:
            artifact_uri = active.info.artifact_uri
        assert tr._inside(artifact_uri, root), artifact_uri
        assert not (tmp_path / "mlruns" / "1").exists()
    finally:
        mlflow.set_tracking_uri(previous)


def test_missing_mlflow_behaviour_unchanged_and_no_folders_created(local_settings, tmp_path):
    data = tr.DataVersion(start_month="2023-01", end_month="2023-12")
    with (
        pytest.raises(tr.MLflowMissingError),
        tr.start_run(
            local_settings, "baseline", "x", "m", data, {"digest": "d"}, mlflow_module_name="mlflow_does_not_exist_xyz"
        ),
    ):
        pass
    assert not (tmp_path / "mlruns").exists()
