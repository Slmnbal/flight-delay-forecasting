"""Cells, policy buffers, the development-only guard and the presentation rules (synthetic rows, not data)."""

from __future__ import annotations

import datetime as dt
import inspect

import numpy as np
import pandas as pd
import pytest

from flight_delay.modeling import conformal as cf
from flight_delay.modeling.splits import FinalTestAccessError, conformal_calibration_window
from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization import policies as pol

KNOTS_A = [0.0, 10.0, 20.0, 30.0, 40.0]
KNOTS_B = [-20.0, -10.0, -5.0, 0.0, 5.0]


def _cells() -> pol.Cells:
    # rows 0-2: JFK-BOS 07:00 (block 06-09) in June; row 3: JFK-BOS 13:00; row 4: LGA-ORD 07:00
    return pol.make_cells(
        ["JFK", "JFK", "JFK", "JFK", "LGA"],
        ["BOS", "BOS", "BOS", "BOS", "ORD"],
        [420, 430, 440, 780, 420],
        pd.to_datetime(["2025-06-01", "2025-06-02", "2025-07-01", "2025-06-01", "2025-06-01"]),
    )


def test_make_cells_route_hour_block_season() -> None:
    cells = _cells()
    assert cells.n_cells == 3
    assert cells.codes[0] == cells.codes[1] == cells.codes[2]
    assert len({int(cells.codes[0]), int(cells.codes[3]), int(cells.codes[4])}) == 3
    np.testing.assert_allclose(sorted(cells.counts()), [1.0, 1.0, 3.0])


def test_aggregate_knots_mean_and_median() -> None:
    knots = np.array([[0, 10, 20, 30, 40], [0, 20, 40, 60, 80], [0, 0, 0, 0, 0]], dtype=float)
    codes = np.zeros(3, dtype=int)
    np.testing.assert_allclose(pol.aggregate_knots(knots, codes, 1, "mean")[0], [0, 10, 20, 30, 40])
    np.testing.assert_allclose(pol.aggregate_knots(knots, codes, 1, "median")[0], [0, 10, 20, 30, 40])
    with pytest.raises(ValueError):
        pol.aggregate_knots(knots, codes, 1, "max")


def _inputs(with_offsets: bool = True) -> pol.PolicyInputs:
    cells = pol.make_cells(["A", "A", "B"], ["X", "X", "Y"], [420, 420, 420], pd.to_datetime(["2025-06-01"] * 3))
    plan = np.array([KNOTS_A, KNOTS_A, KNOTS_B])
    b1 = np.array([[5.0, 15.0, 25.0, 35.0, 45.0]] * 3)
    offsets = {0.80: {"2025-06": {"offset": 3.0}}} if with_offsets else None
    return pol.PolicyInputs(
        cells=cells,
        month=np.array(["2025-06"] * 3),
        plan_knots=plan,
        b1_knots=b1,
        plan_offsets=offsets,
        b1_offsets=offsets,
    )


def test_policy_buffers_by_hand() -> None:
    out = pol.policy_buffers(_inputs(), 0.80)
    np.testing.assert_allclose(out[pol.POLICY_NONE], [0.0, 0.0, 0.0])
    np.testing.assert_allclose(out[pol.POLICY_PLAN], [20.0, 20.0, 0.0])  # cell B: Q(0.8) = -5 -> 0
    np.testing.assert_allclose(out[pol.POLICY_PLAN_CONFORMAL], [23.0, 23.0, 0.0])  # -5 + 3 < 0 -> 0
    np.testing.assert_allclose(out[pol.POLICY_B1], [25.0, 25.0, 25.0])
    np.testing.assert_allclose(out[pol.POLICY_B1_CONFORMAL], [28.0, 28.0, 28.0])
    np.testing.assert_allclose(out[pol.POLICY_PLAN_FLIGHT], [20.0, 20.0, 0.0])
    assert all(np.all(v >= 0) for v in out.values())


def test_policy_buffers_refuse_infinite_offsets_and_out_of_grid_levels() -> None:
    inputs = _inputs()
    bad = pol.PolicyInputs(
        cells=inputs.cells,
        month=inputs.month,
        plan_knots=inputs.plan_knots,
        b1_knots=inputs.b1_knots,
        plan_offsets={0.80: {"2025-06": {"offset": float("inf")}}},
    )
    with pytest.raises(ValueError, match="inf"):
        pol.policy_buffers(bad, 0.80)
    with pytest.raises(nv.GridError):
        pol.policy_buffers(inputs, 0.99)


def test_buffer_construction_takes_no_outcomes() -> None:
    """Policies are built from quantiles and keys only: no realised delay can enter a buffer."""
    outcome_names = {"y", "delay", "arr_delay", "outcome", "label", "labels", "target"}
    assert not outcome_names & set(inspect.signature(pol.policy_buffers).parameters)
    assert not outcome_names & {f.name for f in pol.PolicyInputs.__dataclass_fields__.values()}


def test_selection_refuses_final_test_rows() -> None:
    """The only free policy choice is made on development rows; one final-test date stops it."""
    inputs = _inputs(with_offsets=False)
    delay = np.array([12.0, 30.0, -4.0])
    dev_dates = pd.to_datetime(["2026-02-27"] * 3).to_numpy()
    chosen, record = pol.select_aggregator(dev_dates, delay, inputs, (0.5, 0.8))
    assert chosen in pol.AGGREGATORS
    assert record["chosen"] == chosen
    test_dates = pd.to_datetime(["2026-02-27", "2026-03-01", "2026-02-27"]).to_numpy()
    with pytest.raises(FinalTestAccessError):
        pol.select_aggregator(test_dates, delay, inputs, (0.5, 0.8))


def test_selection_tie_goes_to_the_default() -> None:
    inputs = _inputs(with_offsets=False)  # identical knots inside each cell: mean == median
    chosen, _ = pol.select_aggregator(pd.to_datetime(["2025-12-01"] * 3).to_numpy(), np.zeros(3), inputs, (0.8,))
    assert chosen == pol.DEFAULT_AGGREGATOR


def test_rolling_offsets_equal_the_conformal_quantile_of_the_window() -> None:
    days = pd.date_range("2025-01-01", "2025-03-31", freq="D")
    rng = np.random.default_rng(3)
    dates = np.repeat(days.to_numpy(dtype="datetime64[D]"), 20)
    knots = np.tile(np.array(KNOTS_A), (dates.size, 1))
    y = rng.normal(15.0, 12.0, size=dates.size)
    y[::7] = np.nan  # cancelled rows are outside the universe
    month = dt.date(2025, 3, 1)
    out = pol.rolling_offsets(y, knots, dates, [month], (0.80,))
    window = conformal_calibration_window(month)
    inside = (dates >= np.datetime64(window.start, "D")) & (dates <= np.datetime64(window.end, "D")) & np.isfinite(y)
    expected = cf.one_sided_offset(y[inside], np.full(int(inside.sum()), 20.0), 0.80)
    assert out[0.80]["2025-03"]["offset"] == pytest.approx(expected)
    assert out[0.80]["2025-03"]["window_end"] == str(window.end)


def _cell_frame(carriers: list[str], n_rows: int) -> pd.DataFrame:
    cells = pol.make_cells(["A"] * n_rows, ["X"] * n_rows, [420] * n_rows, pd.to_datetime(["2026-06-01"] * n_rows))
    knots = pol.aggregate_knots(np.tile(KNOTS_A, (n_rows, 1)), cells.codes, cells.n_cells)
    return pol.cell_table(
        cells=cells,
        carrier=carriers,
        delay=np.linspace(-5, 40, n_rows),
        cancelled=np.zeros(n_rows),
        diverted=np.zeros(n_rows),
        crs_elapsed=np.full(n_rows, 75.0),
        cell_knots={"plan": knots},
        buffer_columns={"tampon_plan_t080_dk": np.array([20.0])},
        recommendation=np.array([20.04]),
        recommendation_source="plan@t080",
    )


def test_cell_table_has_no_carrier_column_and_flags_single_carrier_cells() -> None:
    mixed = _cell_frame(["AA", "DL"] * 30, 60)
    assert not any("airline" in c.lower() or "carrier" in c.lower() for c in mixed.columns)
    assert "Reporting_Airline" not in mixed.columns
    assert not bool(mixed["tek_tasiyici_yogun"].iloc[0])
    assert bool(mixed["yayimlanabilir"].iloc[0])
    assert mixed["tampon_onerisi_dk"].iloc[0] == pytest.approx(20.0)
    assert mixed["saat_blogu"].iloc[0] == "06-09"
    assert mixed["mevsim"].iloc[0] == "yaz"
    single = _cell_frame(["AA"] * 58 + ["DL"] * 2, 60)  # 96.7 % one carrier
    assert bool(single["tek_tasiyici_yogun"].iloc[0])
    assert np.isnan(single["tampon_onerisi_dk"].iloc[0])
    assert not any(str(v) in ("AA", "DL") for v in single.astype(str).to_numpy().ravel())


def test_small_cells_are_not_published() -> None:
    small = _cell_frame(["AA", "DL"] * 20, 40)  # n = 40 < 50
    assert not bool(small["yayimlanabilir"].iloc[0])
    assert np.isnan(small["tampon_onerisi_dk"].iloc[0])


def test_flight_table_refuses_carrier_and_identity_columns() -> None:
    assert list(pol.flight_table({"ucus_id": [1, 2], "origin": ["A", "B"]}).columns) == ["ucus_id", "origin"]
    for bad in ("Reporting_Airline", "Tail_Number", "Flight_Number_Reporting_Airline", "carrier"):
        with pytest.raises(ValueError, match="forbidden"):
            pol.flight_table({"ucus_id": [1], bad: ["X"]})
    with pytest.raises(ValueError, match="length"):
        pol.flight_table({"a": [1, 2], "b": [1]})
