"""End-to-end model run on a tiny SYNTHETIC layer: final test never opened, oracle off by default, fixed categories."""

from __future__ import annotations

import datetime as dt
import inspect
import json

import pytest
from modeling_synth import random_frame, write_layer
from models_synth import ALL_TABLES, SMALL_PARAMS, WEATHER_T_TABLE, corrupt, write_side_tables

from flight_delay.data.feature_contract import LeakageError
from flight_delay.data.weather_join import ORACLE_TABLE
from flight_delay.modeling import run_models as rm
from flight_delay.modeling import splits as sp

NOW = dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.UTC)


def _tiny_config(**changes):
    options = {
        "max_train_months": 3,
        "tuning_trials": 1,
        "tuning_num_boost_round": 8,
        "tuning_early_stopping_rounds": 3,
        "num_boost_round": 12,
        "early_stopping_rounds": 3,
        "num_threads": 1,
        "segment_min_n": 10,
        "logistic_day_fraction": 1.0,
        "logistic_max_iter": 200,
        "param_overrides": SMALL_PARAMS,
    }
    options.update(changes)
    return rm.RunConfig(**options)


def _layer(root, *, weather: bool = True):
    # 4 flights a day; months needed with --max-train-months 3: 2024-12 .. 2026-02
    frame = random_frame("2024-12-01", "2026-02-28", per_day=4)
    write_layer(root, frame)
    write_side_tables(root, frame, weather=weather)
    for table in ALL_TABLES:  # CORRUPT final-test partitions: any attempt to read them fails loudly
        corrupt(root, table, 2026, 3)
    for period in frame["FlightDate"].dt.to_period("M").unique():  # oracle weather must never be opened by default
        corrupt(root, ORACLE_TABLE, period.year, period.month)
    if not weather:
        for period in frame["FlightDate"].dt.to_period("M").unique():
            corrupt(root, WEATHER_T_TABLE, period.year, period.month)
    return root


@pytest.fixture
def tiny_layer(tmp_path):
    return _layer(tmp_path / "layer")


def test_t2_run_end_to_end_never_reads_final_test_or_oracle(tiny_layer, tmp_path):
    folder = rm.run(
        layer_root=tiny_layer,
        output_dir=tmp_path / "out",
        model_dir=tmp_path / "models",
        config=_tiny_config(),
        mlflow_mode="off",
        hash_files=False,
        now=NOW,
    )
    results = json.loads((folder / rm.RESULTS_NAME).read_text(encoding="utf-8"))
    meta = results["metadata"]
    assert meta["final_test_read"] is False and meta["contract"] == "T2" and meta["oracle"] is False
    assert meta["months_read"][-1] == "2026-02"
    paths = [f["path"] for f in results["data_fingerprint"]["files"]]
    assert not any("year=2026/month=03" in p for p in paths)
    assert not any(ORACLE_TABLE in p for p in paths)
    assert any(WEATHER_T_TABLE in p for p in paths)
    assert results["periods"]["fit"] == {"name": "train_last3m", "start": "2025-06-01", "end": "2025-08-31"}

    names = results["features"]["names"]
    assert "origin_tmpf" in names and not any(n.startswith("oracle_") for n in names)
    assert results["categories"]["encoder"]["fit_end"] <= "2025-08-31"

    assert results["tuning"]["trials_done"] == 1
    assert {f["name"] for f in results["tuning"]["folds"]} == {"K3", "K4"}
    for target in ("arr_del15", "cancelled"):
        block = results["classification"][target]
        assert set(block) == {"B1", "LightGBM", "L"}
        assert block["LightGBM"]["threshold"]["chosen_on"] == "val_b"
        assert set(block["LightGBM"]["sets"]) == {"val_a", "val_b"}
        assert "delta_vs_B1" in block["LightGBM"]["sets"]["val_b"]
        assert "carrier" not in json.dumps(block["LightGBM"]["sets"]["val_a"]["segments"]).lower()
        assert set(block["LightGBM"]["sets"]["val_a"]["segments"]) == {"Origin", "hour_block", "month"}
    quantiles = results["quantile"]["arr_delay"]["LightGBM"]["sets"]
    for entry in quantiles.values():
        assert entry["total"]["crossing_rate"] == 0.0
        assert entry["total"]["crossing_rate_raw"] is not None
        assert "total_before_sorting" in entry

    records = results["models"]
    assert {"arr_del15-lgbm", "cancelled-lgbm", "arr_del15-logreg", "cancelled-logreg"} <= set(records)
    assert {"arr_delay_q050-lgbm", "arr_delay_q080-lgbm", "arr_delay_q095-lgbm"} <= set(records)
    for record in records.values():
        assert (tmp_path / "models" / "run-20261119T120000Z").joinpath(record["file"].split("/")[-1]).is_file()
        if record["kind"] == "lightgbm":
            assert record["early_stopping_set"] == "val_a"
            assert record["gain_importance"]
    spec = json.loads((tmp_path / "models" / "run-20261119T120000Z" / "model-spec.json").read_text("utf-8"))
    assert spec["categories"]["categories"]["Origin"] == sorted(spec["categories"]["categories"]["Origin"])

    summary = (folder / rm.SUMMARY_NAME).read_text(encoding="utf-8")
    assert "son test (2026-03..08) okunmadı" in summary and "ORACLE" not in summary
    with pytest.raises(FileExistsError):
        rm.run(layer_root=tiny_layer, output_dir=tmp_path / "out", config=_tiny_config(), mlflow_mode="off", now=NOW)


def test_permutation_flag_adds_the_stage_two_review(tiny_layer, tmp_path):
    folder = rm.run(
        layer_root=tiny_layer,
        output_dir=tmp_path / "out",
        model_dir=tmp_path / "models",
        config=_tiny_config(tuning=False, permutation=True, permutation_repeats=2),
        mlflow_mode="off",
        hash_files=False,
        now=NOW,
    )
    results = json.loads((folder / rm.RESULTS_NAME).read_text(encoding="utf-8"))
    permuted = results["permutation_importance"]["models"]
    assert set(permuted) == {k for k, r in results["models"].items() if "skipped" not in r}
    for block in permuted.values():
        assert block["set"] == "val_b" and block["repeats"] == 2
        assert len(block["features"]) == results["features"]["count"]
    assert results["time_travel"]["passed_all"] is True
    assert results["leakage_review"]["status"] in {"leak", "undecided", "dominant_past_only", "cleared", "no_suspicion"}
    assert results["leakage_alarm"]["stage"].startswith("1")
    logreg = results["models"]["cancelled-logreg"]
    assert logreg["params"]["clip_quantile"] == 0.0 and set(logreg["extrapolation_top10"]) == {"val_a", "val_b"}
    summary = (folder / rm.SUMMARY_NAME).read_text(encoding="utf-8")
    assert "Sızıntı incelemesi (2 aşama" in summary


def test_posthoc_permutation_reproduces_the_saved_run_without_retraining(tiny_layer, tmp_path):
    from flight_delay.modeling import run_permutation as rp

    folder = rm.run(
        layer_root=tiny_layer,
        output_dir=tmp_path / "out",
        model_dir=tmp_path / "models",
        config=_tiny_config(tuning=False),
        mlflow_mode="off",
        hash_files=False,
        now=NOW,
    )
    models = tmp_path / "models" / "run-20261119T120000Z"
    summary_before = (folder / rm.SUMMARY_NAME).read_bytes()
    results = json.loads((folder / rm.RESULTS_NAME).read_text(encoding="utf-8"))
    assert "leakage_review" not in results  # default run: unchanged output shape
    argv = ["--run-dir", str(folder), "--model-dir", str(models), "--layer-dir", str(tiny_layer), "--no-hash"]
    assert rp.main([*argv, "--repeats", "2", "--models", "arr_del15-lgbm", "cancelled-logreg"]) == 0
    out_dirs = list((folder / "permutation").iterdir())
    assert len(out_dirs) == 1
    output = json.loads((out_dirs[0] / rp.RESULTS_FILE).read_text(encoding="utf-8"))
    assert output["metadata"]["retrained"] is False and output["metadata"]["final_test_read"] is False
    assert set(output["reproduction"]) == {"arr_del15-lgbm", "cancelled-logreg"}
    assert all(entry["reproduces_run"] for entry in output["reproduction"].values())
    assert set(output["permutation_importance"]["models"]) == {"arr_del15-lgbm", "cancelled-logreg"}
    assert output["time_travel"]["passed_all"] is True
    assert (folder / rm.SUMMARY_NAME).read_bytes() == summary_before  # the run's own files are not touched
    assert "Sızıntı incelemesi (sonradan" in (out_dirs[0] / rp.SUMMARY_FILE).read_text(encoding="utf-8")

    spec_path = models / rp.SPEC_FILE
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["history"]["tables"]["route_cancel"]["n_fit"] += 1  # pretend the data changed since the run
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(RuntimeError, match="history differs"):
        rp.run_posthoc(folder, models, layer_root=tiny_layer, hash_files=False, now=NOW)


def test_new_options_interval_models_dropped_dates_curves_and_posthoc_calibration(tiny_layer, tmp_path):
    from flight_delay.modeling import run_calibration as rc
    from flight_delay.modeling import run_permutation as rp
    from flight_delay.modeling.matrix import DATE_FEATURES

    config = _tiny_config(
        tuning=False,
        interval_models=True,
        drop_features=DATE_FEATURES,
        record_curves=True,
        cancel_early_stopping_metric="average_precision",
        quantile_num_boost_round=7,
    )
    folder = rm.run(
        layer_root=tiny_layer,
        output_dir=tmp_path / "out",
        model_dir=tmp_path / "models",
        config=config,
        mlflow_mode="off",
        hash_files=False,
        now=NOW,
    )
    models = tmp_path / "models" / "run-20261119T120000Z"
    results = json.loads((folder / rm.RESULTS_NAME).read_text(encoding="utf-8"))
    assert not set(DATE_FEATURES) & set(results["features"]["names"])
    assert results["features"]["dropped"] == list(DATE_FEATURES)
    records = results["models"]
    for key in ("q010", "q050", "q080", "q090", "q095"):
        record = records[f"arr_delay_{key}-lgbm"]
        assert record["num_boost_round_cap"] == 7 and 1 <= record["rounds_trained"] <= 7
    assert records["arr_del15-lgbm"]["num_boost_round_cap"] == 12  # the quantile cap does not touch the classifiers
    assert records["cancelled-lgbm"]["early_stopping_metric"] == "average_precision"
    assert records["arr_del15-lgbm"]["early_stopping_metric"] == "binary_logloss"
    assert set(records["cancelled-lgbm"]["valid_curves"]) == {"binary_logloss", "auc", "average_precision"}
    checkpoints = records["cancelled-lgbm"]["val_a_checkpoints"]
    assert checkpoints and set(checkpoints[0]["by_month"]) == {"9", "10", "11", "12"}
    assert records["arr_delay_q080-lgbm"]["valid_curves"]["quantile"]["points"]
    block = results["quantile"]["arr_delay"]
    for set_name in ("val_a", "val_b"):
        for model_name in ("LightGBM", "B1"):
            total = block[model_name]["sets"][set_name]["total"]
            assert 0.0 <= total["interval80_coverage"] <= 1.0
            assert total["interval80_mean_width_min"] is not None and "pinball_q090" in total
        assert block["LightGBM"]["sets"][set_name]["total"]["interval80_crossing_rate"] == 0.0  # pair sorted
        assert "pinball_q010" in block["LightGBM"]["sets"][set_name]["total_before_sorting"]
        assert "interval80_coverage" in block["LightGBM"]["sets"][set_name]["delta_vs_B1"]
    summary_before = (folder / rm.SUMMARY_NAME).read_text(encoding="utf-8")
    assert "İki yönlü %80 aralık" in summary_before and "day_of_year" in summary_before

    # the post-hoc permutation rebuilds the matrix WITH the same dropped features
    argv = ["--run-dir", str(folder), "--model-dir", str(models), "--layer-dir", str(tiny_layer), "--no-hash"]
    assert rp.main([*argv, "--repeats", "1", "--no-time-travel", "--models", "cancelled-lgbm"]) == 0
    perm = json.loads(next((folder / "permutation").iterdir()).joinpath(rp.RESULTS_FILE).read_text("utf-8"))
    assert perm["reproduction"]["cancelled-lgbm"]["reproduces_run"] is True

    # calibration + conformal on the saved run (Val-B only, time-ordered split)
    assert rc.main([*argv, "--segment-min-n", "10"]) == 0
    out_dir = next((folder / "calibration").iterdir())
    output = json.loads((out_dir / rc.RESULTS_FILE).read_text(encoding="utf-8"))
    assert output["metadata"]["final_test_read"] is False and output["metadata"]["val_a_read"] is False
    assert output["split"]["fit"] == {"start": "2026-01-01", "end": "2026-01-30"}
    assert output["split"]["evaluation"] == {"start": "2026-02-01", "end": "2026-02-28"}
    assert output["split"]["embargo_days_left_out"] == 1
    assert all(entry["reproduces_run"] for entry in output["reproduction"].values())
    for target in ("arr_del15", "cancelled"):
        per_model = output["classification"][target]
        assert set(per_model) == {"B1", "LightGBM", "L"}
        iso = per_model["LightGBM"]["methods"]["isotonic"]
        assert iso["before"]["n"] == iso["after"]["n"] == per_model["LightGBM"]["n_eval"]
        assert "platt" in per_model["LightGBM"]["methods"]
    for model_name in ("LightGBM", "B1"):
        quantile = output["quantile"][model_name]
        assert set(quantile["one_sided"]) == {"q080", "q095"}
        assert quantile["one_sided"]["q080"]["coverage_after"] is not None
        assert quantile["interval80"]["method"].startswith("CQR")
    static = json.loads((out_dir / rc.CALIBRATORS_FILE).read_text(encoding="utf-8"))
    assert static["fitted_on"] == {"start": "2026-01-01", "end": "2026-02-28"}
    assert "isotonic" in static["arr_del15/LightGBM"] and "interval80" in static["arr_delay/LightGBM"]
    assert "Kalibrasyon ve conformal ayar" in (out_dir / rc.SUMMARY_FILE).read_text(encoding="utf-8")
    assert (folder / rm.SUMMARY_NAME).read_text(encoding="utf-8") == summary_before  # run files untouched

    # --tuning-from-run: no search, the earlier run's parameters
    second = rm.run(
        layer_root=tiny_layer,
        output_dir=tmp_path / "out",
        model_dir=tmp_path / "models",
        config=_tiny_config(models=("cancelled",), tuning_from_run="run-20261119T120000Z"),
        mlflow_mode="off",
        hash_files=False,
        now=NOW + dt.timedelta(hours=1),
    )
    tuning = json.loads((second / rm.RESULTS_NAME).read_text(encoding="utf-8"))["tuning"]
    assert tuning["trials_done"] == 0 and tuning["from_run"] == "run-20261119T120000Z"
    assert tuning["selected"]["arr_del15"]["selected_by"] == "from run-20261119T120000Z"
    assert tuning["selected"]["arr_del15"]["params"] == results["tuning"]["selected"]["arr_del15"]["params"]


def test_new_options_are_checked_before_any_file_is_read(tmp_path):
    missing = tmp_path / "no-layer-here"
    with pytest.raises(ValueError, match="interval-models"):  # MLflow topic needs interval80 (project.yaml)
        rm.run(layer_root=missing, output_dir=tmp_path / "out", config=_tiny_config(), mlflow_mode="on")
    with pytest.raises(ValueError, match="cancel_early_stopping_metric"):
        rm.run(layer_root=missing, config=_tiny_config(cancel_early_stopping_metric="accuracy"), mlflow_mode="off")
    with pytest.raises(ValueError, match="quantile_num_boost_round"):
        rm.run(layer_root=missing, config=_tiny_config(quantile_num_boost_round=0), mlflow_mode="off")
    with pytest.raises(FileNotFoundError, match="tuning-from-run"):
        rm.run(
            layer_root=missing,
            output_dir=tmp_path / "out",
            config=_tiny_config(tuning_from_run="run-19990101T000000Z"),
            mlflow_mode="off",
        )
    assert rm.quantile_levels(rm.RunConfig()) == (0.5, 0.8, 0.95)
    assert rm.quantile_levels(rm.RunConfig(interval_models=True)) == (0.1, 0.5, 0.8, 0.9, 0.95)
    defaults = rm.RunConfig()
    assert defaults.drop_features == () and defaults.cancel_early_stopping_metric == "binary_logloss"
    assert defaults.interval_models is False and defaults.quantile_num_boost_round is None


def test_conformal_without_interval_models_and_the_honest_split():
    import numpy as np
    import pandas as pd

    from flight_delay.modeling import run_calibration as rc

    dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-30", "2026-01-31", "2026-02-01", "2026-02-28"]))
    fit, evaluation, description = rc.honest_split(dates)
    assert fit.tolist() == [True, True, False, False, False]
    assert evaluation.tolist() == [False, False, False, True, True]
    assert description["embargo_days_left_out"] == 1
    rng = np.random.default_rng(0)
    y = rng.normal(size=400)
    q = {0.8: np.zeros(400), 0.95: np.ones(400)}
    mask = np.arange(400) < 200
    out = rc.conformalize(y, q, mask, ~mask, np.array(["ORD"] * 400), min_n=10)
    assert "not_available" in out["interval80"]
    assert out["one_sided"]["q080"]["rank"] == 161  # ceil(201 * 0.8)
    assert out["one_sided"]["q095"]["segments"]["rows"][0]["segment"] == "ORD"
    for module in ("run_calibration", "calibration", "conformal"):
        source = inspect.getsource(__import__(f"flight_delay.modeling.{module}", fromlist=["_"]))
        assert "allow_final_test" not in source and "FINAL_TEST" not in source


def test_plan_contract_reads_no_weather_at_all(tmp_path):
    root = _layer(tmp_path / "layer", weather=False)  # every weather partition is corrupt
    folder = rm.run(
        layer_root=root,
        output_dir=tmp_path / "out",
        model_dir=tmp_path / "models",
        config=_tiny_config(contract="plan", models=("arr_del15",), tuning=False),
        mlflow_mode="off",
        hash_files=False,
        now=NOW,
    )
    results = json.loads((folder / rm.RESULTS_NAME).read_text(encoding="utf-8"))
    assert not any(n.startswith(("origin_", "dest_")) for n in results["features"]["names"])
    assert set(results["classification"]) == {"arr_del15"}
    assert results["tuning"]["selected"]["arr_del15"]["selected_by"] == "default (search off)"
    assert results["quantile"] == {}


def test_oracle_is_off_by_default_and_needs_the_explicit_flag(tiny_layer, tmp_path):
    assert rm.RunConfig().contract == "T2" and rm.RunConfig().oracle_experiment is False
    with pytest.raises(LeakageError):
        rm.check_contract_option("oracle", False)
    with pytest.raises(ValueError):
        rm.check_contract_option("T2", True)
    with pytest.raises(LeakageError):  # refused before any file is read
        rm.run(layer_root=tiny_layer, output_dir=tmp_path / "out", config=rm.RunConfig(contract="oracle"))
    with pytest.raises(LeakageError):
        rm.main(["--contract", "oracle", "--mlflow", "off"])


def test_final_test_cannot_be_requested():
    fit, evaluations, folds = rm.plan_periods(rm.RunConfig())
    periods = [fit, *evaluations.values()] + [p for _, f, e in folds for p in (f, e)]
    assert all(p.end < sp.FINAL_TEST.start for p in periods)
    assert set(evaluations) == {"val_a", "val_b"}
    with pytest.raises(SystemExit):
        rm.main(["--sets", "final_test"])  # there is no such option
    source = inspect.getsource(rm)
    assert "allow_final_test" not in source and "FINAL_TEST" not in source
    with pytest.raises(sp.FinalTestAccessError):
        sp.get_period("final_test")


def test_last_months_and_default_folds():
    assert rm.last_months(sp.TRAIN, None) is sp.TRAIN
    trimmed = rm.last_months(sp.TRAIN, 3)
    assert (trimmed.start, trimmed.end) == (dt.date(2025, 6, 1), dt.date(2025, 8, 31))
    assert rm.last_months(sp.TRAIN, 100) is sp.TRAIN
    _, _, folds = rm.plan_periods(rm.RunConfig())
    assert [name for name, _, _ in folds] == ["K3", "K4"]
    with pytest.raises(ValueError):
        rm.last_months(sp.TRAIN, 0)
