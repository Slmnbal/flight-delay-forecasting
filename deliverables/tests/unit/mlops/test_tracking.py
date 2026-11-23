import pytest

from flight_delay.mlops import tracking as tr

DATA = tr.DataVersion(start_month="2023-01", end_month="2025-12")
FINGERPRINT = {"digest": "abc123"}
GIT = {"commit": "deadbeef", "dirty": False}


def test_experiment_name_rule():
    assert tr.experiment_name("baseline", "delay-regression") == "havayolu-ds/baseline/delay-regression"


@pytest.mark.parametrize(
    "stage,topic", [("unknown", "x"), ("data", "Capital Letters"), ("data", "under_score"), ("data", "")]
)
def test_experiment_name_invalid(stage, topic):
    with pytest.raises(tr.ContractError):
        tr.experiment_name(stage, topic)


def test_run_name():
    assert tr.run_name("lgbm", DATA, 42) == "lgbm__2023-01_2025-12__s42"
    with pytest.raises(tr.ContractError):
        tr.run_name("LGBM v2", DATA, 42)


def test_data_version_validation():
    with pytest.raises(ValueError):
        tr.DataVersion(start_month="2023-13", end_month="2025-01")
    with pytest.raises(ValueError):
        tr.DataVersion(start_month="2025-06", end_month="2025-01")
    with pytest.raises(ValueError):
        tr.DataVersion(start_month="2023-01", end_month="2025-01", extra_field=1)


def test_context_satisfies_the_contract():
    params, tags = tr.build_context("baseline", "lgbm", DATA, 42, FINGERPRINT, git=GIT, versions={"pandas": "9.9"})
    tr.check_contract(params)
    assert params["data_fingerprint"] == "abc123" and params["seed"] == "42"
    assert params["git_commit"] == "deadbeef"
    assert tags["library.pandas"] == "9.9"


def test_contract_missing_parameter():
    params, _ = tr.build_context("baseline", "lgbm", DATA, 42, FINGERPRINT, git=GIT, versions={})
    del params["seed"]
    with pytest.raises(tr.ContractError):
        tr.check_contract(params)


def test_contract_required_metric():
    params, _ = tr.build_context("baseline", "lgbm", DATA, 42, FINGERPRINT, git=GIT, versions={})
    tr.check_contract(params, {"mae": 1.0}, ["mae"])
    with pytest.raises(tr.ContractError):
        tr.check_contract(params, {}, ["mae"])


def test_missing_mlflow_gives_a_clear_error():
    with pytest.raises(tr.MLflowMissingError):
        tr.load_mlflow("definitely_not_a_module_xyz")


def test_start_run_without_mlflow_gives_a_clear_error(project_settings):
    with (
        pytest.raises(tr.MLflowMissingError),
        tr.start_run(
            project_settings, "baseline", "arrdel15", "lgbm", DATA, FINGERPRINT, mlflow_module_name="missing_module_xyz"
        ),
    ):
        pass


def test_start_run_checks_names_first(project_settings):
    with (
        pytest.raises(tr.ContractError),  # rejected without ever reaching MLflow
        tr.start_run(
            project_settings, "wrong", "x", "lgbm", DATA, FINGERPRINT, mlflow_module_name="missing_module_xyz"
        ),
    ):
        pass
