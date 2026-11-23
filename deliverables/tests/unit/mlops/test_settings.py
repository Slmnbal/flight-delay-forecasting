from pathlib import Path

import pytest

from flight_delay.mlops import settings as st

VALID = """
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


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "project.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_real_project_yaml_is_valid():
    s = st.load_settings(st.DEFAULT_SETTINGS_PATH)
    assert s.seed == 42
    assert s.mlflow.experiment_prefix == "havayolu-ds"
    assert s.tracking_uri({}).startswith("sqlite:///")


def test_valid_settings_and_absolute_path(tmp_path):
    s = st.load_settings(_write(tmp_path, VALID), project_root=tmp_path)
    assert s.absolute(s.paths.raw_data) == (tmp_path / "a" / "raw").resolve()


def test_unknown_top_level_field_is_rejected(tmp_path):
    with pytest.raises(st.SettingsError):
        st.load_settings(_write(tmp_path, VALID + "extra_field: 1\n"))


def test_unknown_inner_field_is_rejected(tmp_path):
    with pytest.raises(st.SettingsError):
        st.load_settings(_write(tmp_path, VALID.replace("result_json: web/data", "result_json: web/data\n  other: x")))


def test_negative_seed_is_rejected(tmp_path):
    with pytest.raises(st.SettingsError):
        st.load_settings(_write(tmp_path, VALID.replace("seed: 7", "seed: -1")))


def test_path_leaving_the_root_is_rejected(tmp_path):
    with pytest.raises(st.SettingsError):
        st.load_settings(_write(tmp_path, VALID.replace("a/raw", "../outside")))


def test_absolute_path_is_rejected(tmp_path):
    with pytest.raises(st.SettingsError):
        st.load_settings(_write(tmp_path, VALID.replace("a/raw", "/etc/raw")))


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(st.SettingsError):
        st.load_settings(tmp_path / "missing.yaml")


def test_project_root_cannot_be_given_in_the_file(tmp_path):
    with pytest.raises(st.SettingsError):
        st.load_settings(_write(tmp_path, VALID + "project_root: /tmp\n"))
