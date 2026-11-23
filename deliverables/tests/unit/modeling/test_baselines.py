"""Baselines B0 / B1 / B2 (plan 4.1) on synthetic frames: fit window only, same metric code, no carrier segments."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest
from modeling_synth import random_frame

from flight_delay.data.feature_contract import LeakageError
from flight_delay.modeling import baselines as bl
from flight_delay.modeling import targets as tg
from flight_delay.modeling.features import add_key_columns

FIT_END = dt.date(2025, 8, 31)


@pytest.fixture(scope="module")
def frames():
    train = random_frame("2025-03-01", "2025-08-31", per_day=10)
    val_a = random_frame("2025-09-01", "2025-10-31", per_day=10, seed=1)
    val_b = random_frame("2026-01-01", "2026-01-31", per_day=10, seed=2)
    return train, {"val_a": val_a, "val_b": val_b}


def test_b0_is_the_training_rate(frames):
    train, evaluations = frames
    keys = add_key_columns(train)
    model = bl.make_rate_baseline("B0").fit(keys, tg.target_values(train, tg.ARR_DEL15), fit_end=FIT_END)
    predicted = model.transform(add_key_columns(evaluations["val_a"]))["value"].to_numpy()
    assert np.allclose(predicted, np.nanmean(tg.target_values(train, tg.ARR_DEL15)))


def test_b1_ignores_evaluation_labels(frames):
    train, evaluations = frames
    keys = add_key_columns(train)
    model = bl.make_rate_baseline("B1").fit(keys, tg.target_values(train, tg.ARR_DEL15), fit_end=FIT_END)
    val = add_key_columns(evaluations["val_a"])
    flipped = val.assign(ArrDel15=1.0 - val["ArrDel15"], ArrDelay=-val["ArrDelay"])
    assert np.array_equal(model.transform(val)["value"].to_numpy(), model.transform(flipped)["value"].to_numpy())


def test_b1_back_off_chain_and_b2_extends_b1():
    assert bl.BASELINES["B1"].levels == ((), ("Origin",), ("Origin", "hour_block"), ("Origin", "Dest", "hour_block"))
    assert bl.BASELINES["B2"].levels[:-1] == bl.BASELINES["B1"].levels
    assert "season" in bl.BASELINES["B2"].levels[-1]


def test_evaluate_baselines_structure_and_no_carrier_segments(frames):
    train, evaluations = frames
    result = bl.evaluate_baselines(train, evaluations, fit_end=FIT_END, segment_min_n=50)
    for target in tg.CLASSIFICATION_TARGETS:
        for set_name in ("val_a", "val_b"):
            block = result["classification"][target][set_name]
            assert set(block) == {"B0", "B1", "B2"}
            total = block["B1"]["total"]
            assert total["brier_skill_score"] == pytest.approx(0.0)  # B1 against itself
            assert set(block["B1"]["segments"]) == set(bl.SEGMENT_DIMENSIONS)
            assert "Reporting_Airline" not in block["B1"]["segments"]
    quantile = result["quantile"][tg.ARR_DELAY]["val_a"]["B1"]["total"]
    for key in ("pinball_q050", "pinball_q080", "pinball_q095", "coverage_q080", "interval80_coverage"):
        assert key in quantile
    assert result["thresholds"][tg.ARR_DEL15]["chosen_on"] == "val_b"
    assert result["classification"][tg.ARR_DEL15]["val_b"]["B1"]["total"]["threshold_in_sample"] == 1.0


def test_evaluate_baselines_refuses_overlapping_windows(frames):
    train, evaluations = frames
    with pytest.raises(LeakageError):
        bl.evaluate_baselines(train, {"bad": train.iloc[-20:]}, fit_end=FIT_END)
    with pytest.raises(ValueError):
        bl.evaluate_baselines(train, evaluations, fit_end=FIT_END, baselines=("B0",))  # B1 is the reference
