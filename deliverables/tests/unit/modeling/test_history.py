"""Past statistics: fit window only, transform without labels, back-off, out-of-fold (plan 2.4, 2.6, 4.1)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from flight_delay.data.feature_contract import LeakageError
from flight_delay.modeling.history import (
    BackoffQuantileTable,
    SmoothedRateTable,
    day_blocks,
    out_of_fold,
    required_count,
)

LEVELS = ((), ("Origin",), ("Origin", "Dest"))
FIT_END = dt.date(2025, 8, 31)


def _fit_frame() -> tuple[pd.DataFrame, np.ndarray]:
    frame = pd.DataFrame(
        {
            "FlightDate": pd.to_datetime(["2025-08-01"] * 6),
            "Origin": ["ORD", "ORD", "ORD", "ORD", "ATL", "ATL"],
            "Dest": ["LAX", "LAX", "JFK", "JFK", "LAX", "LAX"],
        }
    )
    y = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 1.0])
    return frame, y


def test_rate_table_m_estimate_known_values():
    frame, y = _fit_frame()
    table = SmoothedRateTable(LEVELS, m=2.0).fit(frame, y, fit_end=FIT_END)
    out = table.transform(pd.DataFrame({"Origin": ["ORD"], "Dest": ["LAX"]}))
    global_mean = 0.5
    origin = (2.0 + 2.0 * global_mean) / (4 + 2.0)  # ORD: 2 of 4
    route = (2.0 + 2.0 * origin) / (2 + 2.0)  # ORD-LAX: 2 of 2
    assert out["value"].iloc[0] == pytest.approx(route)
    assert out["support"].iloc[0] == 2 and out["level"].iloc[0] == 2


def test_unseen_keys_back_off_to_the_parent_level():
    frame, y = _fit_frame()
    table = SmoothedRateTable(LEVELS, m=2.0).fit(frame, y, fit_end=FIT_END)
    out = table.transform(pd.DataFrame({"Origin": ["ORD", "DEN"], "Dest": ["DEN", "LAX"]}))
    origin_only = table.transform(pd.DataFrame({"Origin": ["ORD"], "Dest": ["LAX"]}))
    assert out["level"].tolist() == [1, 0]  # unseen route -> origin; unseen origin -> global
    assert out["value"].iloc[1] == pytest.approx(0.5)
    assert out["value"].iloc[0] == pytest.approx((2.0 + 1.0) / 6.0)
    assert origin_only["level"].iloc[0] == 2


def test_min_support_forces_back_off():
    frame, y = _fit_frame()
    table = SmoothedRateTable(LEVELS, m=0.0, min_support=3).fit(frame, y, fit_end=FIT_END)
    out = table.transform(pd.DataFrame({"Origin": ["ORD"], "Dest": ["LAX"]}))
    assert out["level"].iloc[0] == 1 and out["value"].iloc[0] == pytest.approx(0.5)


def test_statistics_only_from_the_fit_window():
    """plan 2.6 test_istatistik_donemi: a row after fit_end cannot enter a statistic."""
    frame, y = _fit_frame()
    frame.loc[5, "FlightDate"] = pd.Timestamp("2025-09-01")
    with pytest.raises(LeakageError):
        SmoothedRateTable(LEVELS).fit(frame, y, fit_end=FIT_END)
    with pytest.raises(LeakageError):
        BackoffQuantileTable(LEVELS, (0.5,)).fit(frame, y, fit_end=FIT_END)
    frame.loc[5, "FlightDate"] = pd.Timestamp("2025-08-31")
    table = SmoothedRateTable(LEVELS).fit(frame, y, fit_end=FIT_END)
    assert table.describe()["fit_last_date"] == "2025-08-31"


def test_transform_reads_no_labels():
    """plan 2.6 test_transform_etiketsiz: transform works without label columns and ignores them if present."""
    frame, y = _fit_frame()
    table = SmoothedRateTable(LEVELS).fit(frame, y, fit_end=FIT_END)
    keys_only = pd.DataFrame({"Origin": ["ORD", "ATL"], "Dest": ["LAX", "LAX"]})
    with_labels = keys_only.assign(ArrDel15=[1.0, 1.0], ArrDelay=[300.0, 300.0])
    flipped = keys_only.assign(ArrDel15=[0.0, 0.0], ArrDelay=[-30.0, -30.0])
    expected = table.transform(keys_only)["value"].tolist()
    assert table.transform(with_labels)["value"].tolist() == expected
    assert table.transform(flipped)["value"].tolist() == expected


def test_transform_can_require_rows_after_the_fit_window():
    frame, y = _fit_frame()
    table = SmoothedRateTable(LEVELS).fit(frame, y, fit_end=FIT_END)
    later = pd.DataFrame({"FlightDate": pd.to_datetime(["2025-09-01"]), "Origin": ["ORD"], "Dest": ["LAX"]})
    table.transform(later, require_after_fit_end=True)
    with pytest.raises(LeakageError):
        table.transform(later.assign(FlightDate=pd.Timestamp("2025-08-31")), require_after_fit_end=True)


def test_quantile_support_rule_matches_the_plan():
    assert required_count(0.5) == 40
    assert required_count(0.8) == 100
    assert required_count(0.95) == 400
    assert required_count(0.1) == 200  # lower tail: min(alpha, 1 - alpha) (assumption)


def test_quantile_table_backs_off_when_support_is_too_small():
    big = pd.DataFrame({"FlightDate": pd.to_datetime(["2025-08-01"] * 140), "Origin": ["ORD"] * 140})
    big["Dest"] = ["LAX"] * 100 + ["JFK"] * 40
    y = np.r_[np.arange(100, dtype=float), np.full(40, 500.0)]
    table = BackoffQuantileTable(LEVELS, (0.5, 0.8), min_tail=20).fit(big, y, fit_end=FIT_END)
    out = table.transform(pd.DataFrame({"Origin": ["ORD", "ORD"], "Dest": ["LAX", "JFK"]}))
    # LAX has n = 100: P50 and P80 from the route; JFK has n = 40: P50 from the route, P80 backs off to origin
    assert out["level_q050"].tolist() == [2, 2]
    assert out["level_q080"].tolist() == [2, 1]
    assert out["q050"].iloc[0] == pytest.approx(np.quantile(np.arange(100), 0.5))
    assert out["q050"].iloc[1] == pytest.approx(500.0)
    assert out["q080"].iloc[1] == pytest.approx(np.quantile(y, 0.8))


def test_day_blocks_are_contiguous_whole_days():
    dates = pd.Series(pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]))
    blocks = day_blocks(dates, 2)
    assert blocks.tolist() == [0, 0, 0, 1, 1]
    assert (np.diff(blocks[np.argsort(dates.to_numpy(), kind="mergesort")]) >= 0).all()


def _encode(fit_rows: pd.DataFrame, apply_rows: pd.DataFrame, part_end: dt.date) -> pd.DataFrame:
    table = SmoothedRateTable(((), ("Origin",)), m=0.0).fit(fit_rows, fit_rows["y"].to_numpy(), fit_end=part_end)
    return table.transform(apply_rows)


def _blocked_frame() -> pd.DataFrame:
    days = pd.date_range("2025-01-01", periods=10, freq="D")
    return pd.DataFrame({"FlightDate": np.repeat(days, 2), "Origin": ["ORD", "ATL"] * 10, "y": [0.0, 1.0] * 10})


def test_out_of_fold_own_label_does_not_change_own_encoding():
    frame = _blocked_frame()
    base = out_of_fold(frame, _encode, fit_end=dt.date(2025, 1, 10), n_blocks=5)
    changed = frame.copy()
    changed.loc[0, "y"] = 1.0  # row 0 is in block 0
    after = out_of_fold(changed, _encode, fit_end=dt.date(2025, 1, 10), n_blocks=5)
    blocks = day_blocks(frame["FlightDate"], 5)
    assert after.loc[blocks == 0, "value"].tolist() == base.loc[blocks == 0, "value"].tolist()
    assert after.loc[blocks != 0, "value"].tolist() != base.loc[blocks != 0, "value"].tolist()


def test_expanding_encoding_uses_only_the_past():
    frame = _blocked_frame()
    base = out_of_fold(frame, _encode, fit_end=dt.date(2025, 1, 10), n_blocks=5, mode="expanding")
    blocks = day_blocks(frame["FlightDate"], 5)
    assert base.loc[blocks == 0, "value"].isna().all()  # nothing before the first block
    changed = frame.copy()
    changed.loc[frame.index[blocks == 4], "y"] = 0.5  # change the LAST block only
    after = out_of_fold(changed, _encode, fit_end=dt.date(2025, 1, 10), n_blocks=5, mode="expanding")
    assert after.loc[blocks < 4, "value"].fillna(-1).tolist() == base.loc[blocks < 4, "value"].fillna(-1).tolist()


def test_levels_must_refine():
    with pytest.raises(ValueError):
        SmoothedRateTable((("Origin",),))
    with pytest.raises(ValueError):
        SmoothedRateTable(((), ("Origin",), ("Dest",)))
