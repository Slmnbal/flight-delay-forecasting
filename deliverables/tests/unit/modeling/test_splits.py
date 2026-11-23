"""Split tests (plan sections 1.2 - 1.5 and 2.6: test_bolme_ortusmez, test_gelistirme_test_gormez)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from flight_delay.data.feature_contract import LeakageError
from flight_delay.modeling import splits as sp


def test_split_dates_match_the_plan():
    assert (sp.TRAIN.start, sp.TRAIN.end) == (dt.date(2023, 9, 1), dt.date(2025, 8, 31))
    assert (sp.VAL_A.start, sp.VAL_A.end) == (dt.date(2025, 9, 1), dt.date(2025, 12, 31))
    assert (sp.VAL_B.start, sp.VAL_B.end) == (dt.date(2026, 1, 1), dt.date(2026, 2, 28))
    assert (sp.FINAL_TEST.start, sp.FINAL_TEST.end) == (dt.date(2026, 3, 1), dt.date(2026, 8, 31))
    assert [sp.TRAIN.days, sp.VAL_A.days, sp.VAL_B.days, sp.FINAL_TEST.days] == [731, 122, 59, 184]
    assert len(sp.TRAIN.months()) == 24 and len(sp.FINAL_TEST.months()) == 6
    assert dt.date(2026, 2, 28) == sp.DEVELOPMENT_END


def test_splits_do_not_overlap_and_are_ordered():
    periods = list(sp.SPLITS.values())
    sp.validate_layout(periods)
    for earlier, later in zip(periods, periods[1:], strict=False):
        assert earlier.end < later.start
    every_day = pd.Series(pd.date_range(sp.DATA_START, sp.DATA_END, freq="D"))
    membership = sum(p.contains(every_day).astype(int) for p in periods)
    assert (membership == 1).all()  # every day in exactly one split, none outside


def test_validate_layout_rejects_overlap_and_gap():
    a = sp.Period("a", dt.date(2025, 1, 1), dt.date(2025, 1, 31))
    overlapping = sp.Period("b", dt.date(2025, 1, 31), dt.date(2025, 2, 28))
    gapped = sp.Period("c", dt.date(2025, 2, 2), dt.date(2025, 2, 28))
    with pytest.raises(ValueError, match="overlap"):
        sp.validate_layout([a, overlapping])
    with pytest.raises(ValueError, match="Gap"):
        sp.validate_layout([a, gapped])


def test_assign_split_boundaries():
    dates = [
        "2023-09-01",
        "2025-08-31",
        "2025-09-01",
        "2025-12-31",
        "2026-01-01",
        "2026-02-28",
        "2026-03-01",
        "2026-08-31",
    ]
    labels = sp.assign_split(pd.Series([*dates, "2026-09-01"]))
    assert labels.tolist()[:8] == ["train", "train", "val_a", "val_a", "val_b", "val_b", "final_test", "final_test"]
    assert pd.isna(labels.iloc[8])


def test_assign_split_before_data_start_is_na():
    assert pd.isna(sp.assign_split(pd.Series(["2023-08-31"])).iloc[0])


def test_final_test_is_refused_without_the_flag(missing_lock):
    frame = pd.DataFrame({"FlightDate": pd.to_datetime(["2026-03-02"])})
    with pytest.raises(sp.FinalTestAccessError):
        sp.get_period("final_test")
    with pytest.raises(sp.FinalTestAccessError):
        sp.split_months("final_test")
    with pytest.raises(sp.FinalTestAccessError):
        sp.select_split(frame, "final_test")
    with pytest.raises(sp.FinalTestAccessError):
        sp.require_final_test_access(False, missing_lock)


def test_final_test_is_refused_once_the_lock_exists(tmp_path):
    lock = tmp_path / "son-test-kilidi.json"
    lock.write_text("{}", encoding="utf-8")
    with pytest.raises(sp.FinalTestAccessError, match="already"):
        sp.get_period("final_test", allow_final_test=True, lock_file=lock)


def test_final_test_opens_only_with_flag_and_no_lock(missing_lock):
    period = sp.get_period("final_test", allow_final_test=True, lock_file=missing_lock)
    assert period == sp.FINAL_TEST


def test_development_loader_never_returns_final_test_dates():
    frame = pd.DataFrame(
        {"FlightDate": pd.to_datetime(["2025-01-01", "2026-02-28", "2026-03-01", "2026-08-31", "2023-08-31"])}
    )
    kept = sp.development_only(frame)
    assert kept["FlightDate"].max() == pd.Timestamp("2026-02-28")
    assert kept["FlightDate"].min() == pd.Timestamp("2025-01-01")
    with pytest.raises(sp.FinalTestAccessError):
        sp.assert_no_final_test(frame["FlightDate"])


def test_select_split_keeps_order_and_rows_inside():
    frame = pd.DataFrame({"FlightDate": pd.to_datetime(["2025-12-31", "2025-09-01", "2025-08-31", "2025-10-15"])})
    selected = sp.select_split(frame, "val_a")
    assert selected.index.tolist() == [0, 1, 3]  # original order, nothing shuffled


def test_embargo_trims_the_tail_of_the_fit_window():
    frame = pd.DataFrame({"FlightDate": pd.to_datetime(["2025-08-29", "2025-08-30", "2025-08-31"])})
    assert len(sp.select_split(frame, "train")) == 3
    trimmed = sp.select_split(frame, "train", embargo_days=2)
    assert trimmed["FlightDate"].tolist() == [pd.Timestamp("2025-08-29")]
    assert sp.trim_end(sp.TRAIN, 1).end == dt.date(2025, 8, 30)
    with pytest.raises(ValueError):
        sp.trim_end(sp.TRAIN, -1)


def test_check_temporal_order_rejects_overlap_and_embargo_violation():
    fit = pd.Series(pd.to_datetime(["2025-08-30", "2025-08-31"]))
    sp.check_temporal_order(fit, pd.Series(pd.to_datetime(["2025-09-01"])))
    with pytest.raises(LeakageError):
        sp.check_temporal_order(fit, pd.Series(pd.to_datetime(["2025-08-31"])))
    with pytest.raises(LeakageError):
        sp.check_temporal_order(fit, pd.Series(pd.to_datetime(["2025-09-01"])), embargo_days=1)
    sp.check_temporal_order(fit, pd.Series(pd.to_datetime(["2025-09-02"])), embargo_days=1)


def test_rolling_folds_fit_before_evaluation_inside_training():
    assert [f.name for f in sp.ROLLING_FOLDS] == ["K1", "K2", "K3", "K4"]
    for fold in sp.ROLLING_FOLDS:
        assert fold.fit.start == sp.TRAIN.start
        assert fold.fit.end + dt.timedelta(days=1) == fold.evaluation.start
        assert fold.evaluation.end <= sp.TRAIN.end
    assert [f.core for f in sp.ROLLING_FOLDS] == [False, False, True, True]


def test_conformal_window_has_a_one_day_embargo():
    window = sp.conformal_calibration_window(dt.date(2026, 3, 1))
    assert window.start == dt.date(2026, 1, 3)
    assert window.end == dt.date(2026, 2, 27)  # 2026-02-28 is the embargo day
    with pytest.raises(ValueError):
        sp.conformal_calibration_window(dt.date(2026, 3, 2))
