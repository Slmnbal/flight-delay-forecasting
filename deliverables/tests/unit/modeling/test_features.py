"""Feature leakage tests (plan section 2.6) and schedule / weather feature derivations."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from modeling_synth import build_frame, flights_only, random_frame, weather_frame

from flight_delay.data.feature_contract import LeakageError, validate_columns
from flight_delay.modeling import features as ft


def _flights() -> pd.DataFrame:
    return flights_only(
        build_frame(
            [
                {"flight_uid": 1, "FlightDate": "2025-09-02", "CRSDepTime": 545, "CRSArrTime": 830},
                {"flight_uid": 2, "FlightDate": "2025-09-02", "CRSDepTime": 600, "Origin": "ATL", "Dest": "ORD"},
                {"flight_uid": 3, "FlightDate": "2025-09-03", "CRSDepTime": 2400, "CRSArrTime": 2400},
            ]
        )
    )


# ---------------------------------------------------------------- schedule


def test_hour_block_edges():
    minutes = [0, 359, 360, 539, 540, 720, 900, 1080, 1260, 1439, 1440]
    assert ft.hour_block(minutes).tolist() == [0, 0, 1, 1, 2, 3, 4, 5, 6, 6, 6]
    assert ft.hour_block(pd.array([pd.NA], dtype="Int16")).tolist() == [-1]


def test_season_mapping():
    assert ft.season([12, 1, 2, 3, 6, 9, 11]).tolist() == [0, 0, 0, 1, 2, 3, 3]


def test_us_federal_holidays_known_dates():
    days = set(ft.us_federal_holidays([2025, 2026]))
    assert dt.date(2025, 11, 27) in days  # Thanksgiving 2025
    assert dt.date(2026, 1, 19) in days  # Martin Luther King Jr. Day 2026
    assert dt.date(2026, 7, 4) in days and dt.date(2026, 7, 3) in days  # Saturday -> observed Friday
    assert dt.date(2025, 9, 1) in days  # Labor Day 2025
    distance = ft.days_to_nearest_holiday(pd.Series(pd.to_datetime(["2025-11-27", "2025-11-30", "2025-09-03"])))
    assert distance.tolist() == [0.0, 3.0, 2.0]


def test_schedule_features_do_not_use_year_and_derive_calendar_from_flightdate():
    features = ft.build_schedule_features(_flights())
    assert "Year" not in features.columns and "Quarter" not in features.columns
    assert features["hour_block"].tolist() == [0, 1, 6]
    assert features["crs_arr_hour"].tolist() == [8.0, 12.0, 0.0]
    assert features["day_of_week"].tolist() == [2, 2, 3]  # 2025-09-02 is a Tuesday
    assert str(features["Origin"].dtype) == "category"


def test_density_features_sum_over_month_files():
    flights = _flights().iloc[[0]]
    density = pd.DataFrame(
        {
            "airport": ["ORD", "ORD", "ORD", "ATL"],
            "local_date": pd.to_datetime(["2025-09-02", "2025-09-02", "2025-09-02", "2025-09-02"]),
            "local_hour": [5, 5, 9, 8],  # two rows for ORD 05h: e.g. from two month files
            "planned_departures": [3, 2, 7, 0],
            "planned_arrivals": [0, 0, 0, 4],
        }
    )
    out = ft.build_density_features(flights, ft.aggregate_density(density))
    assert out["planned_departures_origin_hour"].iloc[0] == 5
    assert out["planned_departures_origin_day"].iloc[0] == 12
    assert out["planned_arrivals_dest_hour"].iloc[0] == 4  # ATL 08h (arrival 08:30)


# ---------------------------------------------------------------- leakage (plan 2.6)


def test_feature_code_rejects_frames_with_outcome_columns():
    """Future information cannot enter a feature: frames carrying labels are refused outright."""
    flights = _flights().assign(ArrDelay=[1.0, 2.0, 3.0])
    with pytest.raises(LeakageError, match="ArrDelay"):
        ft.build_feature_matrix(flights)
    with pytest.raises(LeakageError):
        ft.build_schedule_features(_flights().assign(DepTimeBlk=["0600-0659"] * 3))


def test_feature_matrix_has_no_forbidden_columns_and_contract_covers_all():
    matrix = ft.build_feature_matrix(_flights())
    validate_columns(matrix.frame.columns)
    assert matrix.contract.feature_names() == list(matrix.frame.columns)
    assert matrix.kind == "plan"


def test_undeclared_column_is_rejected_by_the_contract():
    with pytest.raises(LeakageError, match="not a declared feature"):
        ft.build_contract("plan", ["crs_dep_hour", "mystery_feature"])


def test_weather_row_level_information_time_is_enforced():
    flights = _flights()
    ok = ft.build_weather_features(weather_frame(flights, minutes_before_cutoff=30.0), flights)
    assert ok["origin_ceiling_ft"].tolist() == [800.0, 800.0, 800.0]
    assert ok["origin_ifr_flag"].tolist() == [1.0, 1.0, 1.0]  # ceiling 800 ft < 1000 ft
    assert ok["origin_wx_ts"].tolist() == [1.0, 1.0, 1.0] and ok["origin_wx_sn"].tolist() == [0.0, 0.0, 0.0]
    with pytest.raises(LeakageError, match="information-time"):
        ft.build_weather_features(weather_frame(flights, minutes_before_cutoff=-1.0), flights)


def test_weather_exactly_at_the_cutoff_is_allowed():
    flights = _flights()
    ft.build_weather_features(weather_frame(flights, minutes_before_cutoff=0.0), flights)


def test_oracle_weather_is_off_by_default():
    flights = _flights()
    oracle_table = weather_frame(flights, oracle=True)
    with pytest.raises(LeakageError, match="oracle"):
        ft.build_feature_matrix(flights, weather_oracle=oracle_table)
    with pytest.raises(LeakageError, match="[Oo]racle"):
        ft.build_feature_matrix(flights, weather_t=oracle_table)  # oracle rows passed as T-2 h weather
    with pytest.raises(LeakageError):
        ft.build_contract("T2", ["oracle_origin_tmpf"])


def test_oracle_features_only_with_the_flag_and_labelled():
    flights = _flights()
    matrix = ft.build_feature_matrix(
        flights, weather_t=weather_frame(flights), weather_oracle=weather_frame(flights, oracle=True), oracle=True
    )
    oracle_columns = [c for c in matrix.frame.columns if c.startswith("oracle_")]
    assert oracle_columns and matrix.kind == "oracle" and matrix.contract.oracle_experiment
    assert not [
        c
        for c in matrix.frame.columns
        if c.startswith("origin_") and c.replace("origin_", "oracle_origin_") not in matrix.frame.columns
    ]
    with pytest.raises(LeakageError, match="not the oracle table"):
        ft.build_weather_features(weather_frame(flights), flights, oracle=True)  # T table passed as oracle
    with pytest.raises(ValueError):
        ft.build_feature_matrix(flights, oracle=True)  # the flag alone does not invent an oracle table


def test_t2_contract_has_weather_but_plan_contract_refuses_it():
    flights = _flights()
    matrix = ft.build_feature_matrix(flights, weather_t=weather_frame(flights))
    assert matrix.kind == "T2" and "origin_tmpf" in matrix.frame.columns
    with pytest.raises(LeakageError):
        ft.build_contract("plan", ["origin_tmpf"])


# ---------------------------------------------------------------- history features


def test_history_features_fit_window_and_label_free_transform():
    train = random_frame("2025-07-01", "2025-08-31", per_day=8)
    later = random_frame("2025-09-01", "2025-09-10", per_day=8, seed=7)
    history = ft.HistoryFeatures().fit(train, fit_end=dt.date(2025, 8, 31))
    features = history.transform(flights_only(later))
    assert list(features.columns) == list(ft.HISTORY_FEATURES)
    flipped = later.assign(ArrDel15=1.0, ArrDelay=999.0, Cancelled=1, ActualElapsedTime=1.0, TaxiOut=99.0)
    assert features.equals(history.transform(later))  # evaluation labels present but unread ...
    assert features.equals(history.transform(flipped))  # ... and changing them changes nothing
    with pytest.raises(LeakageError):
        ft.HistoryFeatures().fit(later, fit_end=dt.date(2025, 8, 31))
    with pytest.raises(LeakageError):
        history.transform(flights_only(train))  # rows inside the fit window need out_of_fold


def test_history_features_in_the_matrix_validate_against_the_contract():
    train = random_frame("2025-07-01", "2025-08-31", per_day=8)
    later = flights_only(random_frame("2025-09-01", "2025-09-05", per_day=8, seed=3))
    history = ft.HistoryFeatures().fit(train, fit_end=dt.date(2025, 8, 31))
    matrix = ft.build_feature_matrix(later, history=history)
    assert set(ft.HISTORY_FEATURES) <= set(matrix.frame.columns)
    validate_columns(matrix.frame.columns)
    spec = {s.name: s for s in matrix.contract.features}["te_route_hour_arrdel15"]
    assert spec.knowledge_time == "past_realized" and spec.ready_minutes_before >= 120


def test_history_out_of_fold_for_training_rows():
    train = random_frame("2025-07-01", "2025-08-31", per_day=8)
    encoded = ft.HistoryFeatures().fit_transform_out_of_fold(train, fit_end=dt.date(2025, 8, 31), n_blocks=5)
    assert encoded.index.equals(train.index)
    assert np.isfinite(encoded["te_route_hour_arrdel15"].to_numpy()).all()
