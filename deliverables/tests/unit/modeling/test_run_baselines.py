"""End-to-end baseline run on a tiny SYNTHETIC layer in tmp_path; the final-test partition must never be opened."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from modeling_synth import random_frame, write_layer

from flight_delay.data.layer import PARQUET_NAME, table_dir
from flight_delay.data.tables import FLIGHTS, LABELS
from flight_delay.modeling import loading
from flight_delay.modeling import run_baselines as rb
from flight_delay.modeling import splits as sp


@pytest.fixture
def tiny_layer(tmp_path):
    root = tmp_path / "layer"
    # 2 flights a day over the 30 development months (about 1 800 rows)
    write_layer(root, random_frame("2023-09-01", "2026-02-28", per_day=2))
    # a CORRUPT final-test partition: any attempt to read it would fail loudly
    for table in (FLIGHTS, LABELS):
        path = table_dir(root, table, 2026, 3) / PARQUET_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not a parquet file - the final test must not be opened")
    return root


def test_run_writes_results_and_never_reads_the_final_test(tiny_layer, tmp_path):
    folder = rb.run(
        layer_root=tiny_layer,
        output_dir=tmp_path / "out",
        set_names=("val_a", "val_b"),
        segment_min_n=10,
        mlflow_mode="off",
        now=dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.UTC),
    )
    results = json.loads((folder / rb.RESULTS_NAME).read_text(encoding="utf-8"))
    meta = results["metadata"]
    assert meta["final_test_read"] is False
    assert meta["months_read"][0] == "2023-09" and meta["months_read"][-1] == "2026-02"
    assert not any("month=03" in f["path"] and "year=2026" in f["path"] for f in results["data_fingerprint"]["files"])
    job = results["jobs"][0]
    assert job["fit_period"]["end"] == "2025-08-31"
    assert set(job["classification"]["arr_del15"]) == {"val_a", "val_b"}
    summary = (folder / rb.SUMMARY_NAME).read_text(encoding="utf-8")
    assert "son test (2026-03..08) okunmadı" in summary
    with pytest.raises(FileExistsError):
        rb.run(
            layer_root=tiny_layer,
            output_dir=tmp_path / "out",
            mlflow_mode="off",
            now=dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.UTC),
        )


def test_run_with_rolling_fold_uses_the_fold_fit_window(tiny_layer, tmp_path):
    folder = rb.run(
        layer_root=tiny_layer, output_dir=tmp_path / "out", set_names=("K4",), mlflow_mode="off", hash_files=False
    )
    job = json.loads((folder / rb.RESULTS_NAME).read_text(encoding="utf-8"))["jobs"][0]
    assert job["fit_period"]["end"] == "2025-05-31"
    assert job["evaluation_periods"]["K4"] == {"start": "2025-06-01", "end": "2025-08-31"}


def test_final_test_is_not_an_evaluation_choice():
    assert "final_test" not in rb.EVALUATION_CHOICES
    with pytest.raises(ValueError):
        rb.plan_jobs(["final_test"])
    with pytest.raises(SystemExit):
        rb.main(["--sets", "final_test", "--mlflow", "off"])


def test_loader_refuses_final_test_periods(tiny_layer):
    with pytest.raises(sp.FinalTestAccessError):
        loading.periods_for(["final_test"])
    with pytest.raises(sp.FinalTestAccessError):
        loading.load_periods(tiny_layer, [sp.FINAL_TEST])


def test_loader_reads_only_requested_columns_and_months(tiny_layer):
    loaded = loading.load_periods(tiny_layer, [sp.VAL_B], label_columns=loading.BASELINE_LABEL_COLUMNS, hash_files=True)
    assert loaded.months == [(2026, 1), (2026, 2)]
    assert set(loaded.frame.columns) == set(loading.BASELINE_FLIGHT_COLUMNS) | set(loading.BASELINE_LABEL_COLUMNS)
    assert str(loaded.frame["Origin"].dtype) == "category"
    assert all("sha256" in f for f in loaded.files)
    assert loading.fingerprint(loaded.files)["digest"] == loading.fingerprint(list(reversed(loaded.files)))["digest"]
