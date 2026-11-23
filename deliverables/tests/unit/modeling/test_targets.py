"""Target universes (plan section 3) and the ArrDel15 consistency check (plan 2.6 test_hedef_tutarliligi)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from flight_delay.modeling import targets as tg


def _labels() -> pd.DataFrame:
    # completed on time, completed late, cancelled, diverted, completed with inconsistent ArrDel15
    return pd.DataFrame(
        {
            "flight_uid": [1, 2, 3, 4, 5],
            "ArrDelay": pd.array([-5.0, 40.0, np.nan, np.nan, 20.0], dtype="float32"),
            "ArrDel15": pd.array([0, 1, pd.NA, pd.NA, 0], dtype="Int8"),
            "Cancelled": pd.array([0, 0, 1, 0, 0], dtype="Int8"),
            "Diverted": pd.array([0, 0, 0, 1, 0], dtype="Int8"),
        }
    )


def test_arr_del15_universe_excludes_cancelled_and_diverted():
    values = tg.target_values(_labels(), tg.ARR_DEL15)
    assert np.isnan(values[2]) and np.isnan(values[3])
    assert values[[0, 1, 4]].tolist() == [0.0, 1.0, 0.0]


def test_cancellation_universe_is_every_scheduled_flight():
    values = tg.target_values(_labels(), tg.CANCELLED)
    assert values.tolist() == [0.0, 0.0, 1.0, 0.0, 0.0]  # a diversion is not a cancellation


def test_arrival_delay_target_is_conditional_on_completion_and_not_clipped():
    values = tg.target_values(_labels(), tg.ARR_DELAY)
    assert values[0] == -5.0 and values[1] == 40.0
    assert np.isnan(values[2]) and np.isnan(values[3])


def test_disruption_target_counts_late_cancelled_or_diverted():
    assert tg.target_values(_labels(), tg.DISRUPTION).tolist() == [0.0, 1.0, 1.0, 1.0, 0.0]


def test_build_targets_and_summary():
    targets = tg.build_targets(_labels())
    assert list(targets.columns) == ["flight_uid", *tg.TARGETS]
    summary = tg.universe_summary(_labels())
    assert summary["universe_arr_del15"] == 3 and summary["universe_cancelled"] == 5
    assert summary["cancelled"] == 1 and summary["diverted"] == 1


def test_arr_del15_consistency_counts_mismatches():
    check = tg.arr_del15_consistency(_labels())
    assert check["compared_rows"] == 3
    assert check["mismatch_rows"] == 1  # row 5: ArrDelay 20 but ArrDel15 0
    assert check["completed_arr_del15_missing"] == 0


def test_unknown_target_is_rejected():
    with pytest.raises(KeyError):
        tg.target_values(_labels(), "DepDel15")


def test_conditional_level_and_unconditional_exceedance():
    level = tg.conditional_level(0.8, np.array([0.0, 0.1, 0.25]))
    assert level[0] == pytest.approx(0.8)
    assert level[1] == pytest.approx(0.8 / 0.9)
    assert np.isnan(level[2])  # alpha >= 1 - p: the unconditional quantile is "infinite"
    assert tg.unconditional_exceedance(0.1, 0.2) == pytest.approx(0.1 + 0.9 * 0.2)
