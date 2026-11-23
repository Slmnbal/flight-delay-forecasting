"""Model matrices, the side-table reader and day sampling on a tiny SYNTHETIC layer."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from modeling_synth import random_frame
from models_synth import WEATHER_T_TABLE, corrupt, write_side_tables

from flight_delay.data.tables import DENSITY
from flight_delay.data.weather_join import ORACLE_TABLE
from flight_delay.modeling import features as ft
from flight_delay.modeling.categories import CategoryEncoder
from flight_delay.modeling.matrix import (
    HISTORY_INPUT_COLUMNS,
    LayerTableReader,
    build_model_matrix,
    sample_days,
)
from flight_delay.modeling.splits import FinalTestAccessError


@pytest.fixture
def layer(tmp_path):
    root = tmp_path / "layer"
    frame = random_frame("2025-07-01", "2025-10-31", per_day=4)
    write_side_tables(root, frame)
    return root, frame


def test_reader_refuses_final_test_months_even_if_the_file_exists(tmp_path):
    root = tmp_path / "layer"
    corrupt(root, DENSITY, 2026, 3)
    reader = LayerTableReader(root)
    with pytest.raises(FinalTestAccessError):
        reader.read(DENSITY, 2026, 3)
    with pytest.raises(FinalTestAccessError):
        reader.weather(2026, 8, oracle=False, horizon_hours=2.0)


def test_density_of_february_2026_never_opens_march(tmp_path):
    root = tmp_path / "layer"
    frame = random_frame("2026-01-01", "2026-02-28", per_day=2)
    write_side_tables(root, frame, weather=False)
    corrupt(root, DENSITY, 2026, 3)  # would fail if read
    reader = LayerTableReader(root)
    density = reader.density_for_month(2026, 2)
    assert len(density) > 0
    assert any("2026-03" in note for note in reader.density_neighbours_skipped)
    assert not any("month=03" in f["path"] and "year=2026" in f["path"] for f in reader.files)


def test_build_model_matrix_plan_and_t2_with_fixed_codes(layer):
    root, frame = layer
    fit_end = dt.date(2025, 8, 31)
    train = frame.loc[frame["FlightDate"] <= pd.Timestamp(fit_end)].reset_index(drop=True)
    evaluation = frame.loc[frame["FlightDate"] > pd.Timestamp(fit_end)].reset_index(drop=True)
    encoder = CategoryEncoder().fit(train, fit_end=fit_end)
    history = ft.HistoryFeatures()
    encoded = history.fit_transform_out_of_fold(train[list(HISTORY_INPUT_COLUMNS)], fit_end=fit_end)
    reader = LayerTableReader(root, hash_files=False)

    plan_train = build_model_matrix(train, kind="plan", reader=reader, encoder=encoder, history_frame=encoded)
    assert plan_train.x.shape == (len(train), len(plan_train.feature_names))
    assert plan_train.x.dtype == np.float32
    assert not any(n.startswith(("origin_", "dest_", "oracle_")) for n in plan_train.feature_names)
    assert plan_train.months == ["2025-07", "2025-08"]
    origin_index = plan_train.feature_names.index("Origin")
    assert plan_train.categorical_indices == [origin_index, plan_train.feature_names.index("Reporting_Airline")]
    expected = encoder.codes(train["Origin"], "Origin")
    np.testing.assert_array_equal(plan_train.x[:, origin_index], expected)

    t2_eval = build_model_matrix(evaluation, kind="T2", reader=reader, encoder=encoder, history=history)
    assert "origin_tmpf" in t2_eval.feature_names and "oracle_origin_tmpf" not in t2_eval.feature_names
    assert t2_eval.contract.oracle_experiment is False
    assert not any(ORACLE_TABLE in f["path"] for f in reader.files)
    assert any(WEATHER_T_TABLE in f["path"] for f in reader.files)


def test_build_model_matrix_selected_rows_keep_frame_order(layer):
    root, frame = layer
    fit_end = dt.date(2025, 8, 31)
    train = frame.loc[frame["FlightDate"] <= pd.Timestamp(fit_end)].reset_index(drop=True)
    encoder = CategoryEncoder().fit(train, fit_end=fit_end)
    history = ft.HistoryFeatures()
    encoded = history.fit_transform_out_of_fold(train[list(HISTORY_INPUT_COLUMNS)], fit_end=fit_end)
    rows = sample_days(train["FlightDate"], 0.25, seed=42)
    matrix = build_model_matrix(
        train, kind="plan", reader=LayerTableReader(root), encoder=encoder, history_frame=encoded, rows=rows
    )
    assert matrix.row_positions.tolist() == np.flatnonzero(rows).tolist()
    day_index = matrix.feature_names.index("day_of_month")
    np.testing.assert_array_equal(matrix.x[:, day_index], train.loc[rows, "FlightDate"].dt.day.to_numpy())


def test_drop_leaves_the_named_features_out_and_keeps_the_rest_identical(layer):
    from flight_delay.modeling.matrix import DATE_FEATURES

    root, frame = layer
    fit_end = dt.date(2025, 8, 31)
    train = frame.loc[frame["FlightDate"] <= pd.Timestamp(fit_end)].reset_index(drop=True)
    encoder = CategoryEncoder().fit(train, fit_end=fit_end)
    history = ft.HistoryFeatures()
    encoded = history.fit_transform_out_of_fold(train[list(HISTORY_INPUT_COLUMNS)], fit_end=fit_end)
    reader = LayerTableReader(root, hash_files=False)
    full = build_model_matrix(train, kind="plan", reader=reader, encoder=encoder, history_frame=encoded)
    assert set(DATE_FEATURES) <= set(full.feature_names) and set(DATE_FEATURES) <= set(ft.SCHEDULE_FEATURES)
    assert full.dropped == []
    reduced = build_model_matrix(
        train, kind="plan", reader=reader, encoder=encoder, history_frame=encoded, drop=DATE_FEATURES
    )
    assert reduced.dropped == list(DATE_FEATURES)
    assert reduced.feature_names == [n for n in full.feature_names if n not in DATE_FEATURES]
    assert "day_of_week" in reduced.feature_names  # not part of the group
    kept = [full.feature_names.index(n) for n in reduced.feature_names]
    np.testing.assert_array_equal(reduced.x, full.x[:, kept])
    assert reduced.categorical_indices == [
        reduced.feature_names.index("Origin"),
        reduced.feature_names.index("Reporting_Airline"),
    ]
    with pytest.raises(ValueError, match="Cannot drop"):
        build_model_matrix(train, kind="plan", reader=reader, encoder=encoder, history_frame=encoded, drop=["nope"])


def test_history_features_are_required(layer):
    root, frame = layer
    with pytest.raises(ValueError):
        build_model_matrix(frame, kind="plan", reader=LayerTableReader(root), encoder=CategoryEncoder().fit(frame))


def test_sample_days_selects_whole_days_reproducibly():
    dates = pd.Series(pd.to_datetime(["2025-01-01"] * 3 + ["2025-01-02"] * 2 + ["2025-01-03"] * 4 + ["2025-01-04"]))
    mask = sample_days(dates, 0.5, seed=7)
    assert mask.tolist() == sample_days(dates, 0.5, seed=7).tolist()
    chosen = set(dates[mask].dt.day)
    assert len(chosen) == 2
    for day in chosen:  # every row of a chosen day is in
        assert mask[(dates.dt.day == day).to_numpy()].all()
    assert sample_days(dates, 1.0).all()
    with pytest.raises(ValueError):
        sample_days(dates, 0.0)
