"""Permutation importance, time travel test and the two-stage leakage review on SYNTHETIC data."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from modeling_synth import random_frame

from flight_delay.modeling import features as ft
from flight_delay.modeling import importance as imp

FIT_END = dt.date(2025, 8, 31)


def _factory() -> ft.HistoryFeatures:
    return ft.HistoryFeatures(m=20.0, min_support=1, min_tail=20)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    train = random_frame("2025-06-01", "2025-08-31", per_day=12, seed=1)
    evaluation = random_frame("2026-01-01", "2026-01-31", per_day=12, seed=2)
    return train, evaluation


# ----------------------------------------------------------------------------
# permutation
# ----------------------------------------------------------------------------


def test_permutations_keep_values_and_within_day_keeps_days():
    rng = np.random.default_rng(0)
    values = np.arange(12, dtype="float64")
    days = np.repeat([0, 1, 2], 4)
    rows = imp.permute_values(values, days, rng, "rows")
    assert sorted(rows) == sorted(values) and not np.array_equal(rows, values)
    within = imp.permute_values(values, days, np.random.default_rng(1), "within_day")
    for day in range(3):
        assert sorted(within[days == day]) == sorted(values[days == day])
    again = imp.permute_values(values, days, np.random.default_rng(1), "within_day")
    np.testing.assert_array_equal(within, again)  # seeded: reproducible
    with pytest.raises(ValueError):
        imp.permute_values(values, days, rng, "random_k_fold")


def test_day_sample_takes_whole_days():
    dates = np.repeat(pd.date_range("2026-01-01", periods=30).to_numpy(), 10)
    mask = imp.sample_rows_by_days(dates, 100, seed=3)
    picked = pd.Series(dates[mask]).value_counts()
    assert mask.sum() == 100 and (picked == 10).all()  # 10 complete days
    assert imp.sample_rows_by_days(dates, 1000).all()


def _classification_data(n: int = 6000, seed: int = 5):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 2)).astype("float32")
    y = (rng.random(n) < 1 / (1 + np.exp(-3.0 * x[:, 0]))).astype("float64")
    days = np.repeat(pd.date_range("2026-01-01", periods=n // 100).to_numpy(), 100)
    return x, y, days


def _model(x: np.ndarray) -> np.ndarray:
    """The 'fitted model': uses feature 0 only."""
    return 1 / (1 + np.exp(-3.0 * x[:, 0].astype("float64")))


def test_permutation_importance_finds_the_used_feature_and_ignores_the_unused_one():
    x, y, days = _classification_data()
    config = imp.PermutationConfig(repeats=3, seed=7)
    out = imp.permutation_importance(
        _model,
        x,
        y,
        feature_names=["signal", "noise"],
        kind=imp.CLASSIFICATION,
        days=days,
        config=config,
        reference=0.5,
    )
    by_name = {r["feature"]: r for r in out["features"]}
    assert out["features"][0]["feature"] == "signal"
    assert by_name["signal"]["roc_auc"]["mean_drop"] > 0.2 and by_name["signal"]["log_loss"]["mean_drop"] > 0
    assert by_name["signal"]["remaining_skill_share"] < imp.COLLAPSE_REMAINING_SKILL  # permuted -> about B0
    assert by_name["noise"]["roc_auc"]["mean_drop"] == 0.0  # the model never reads it
    assert len(by_name["signal"]["roc_auc"]["drops"]) == 3 and by_name["signal"]["roc_auc"]["sd_drop"] >= 0
    assert out["reference_B0"]["roc_auc"] == 0.5 and out["n_days"] == 60
    np.testing.assert_array_equal(x, _classification_data()[0])  # input matrix untouched
    again = imp.permutation_importance(
        _model, x, y, feature_names=["signal", "noise"], kind=imp.CLASSIFICATION, days=days, config=config
    )
    assert again["features"][0]["roc_auc"]["drops"] == by_name["signal"]["roc_auc"]["drops"]  # seeded


def test_permutation_importance_for_a_quantile_model_uses_pinball_and_b0():
    rng = np.random.default_rng(9)
    x = rng.normal(size=(3000, 2)).astype("float32")
    y = 10.0 * x[:, 0] + rng.normal(size=3000)
    days = np.repeat(pd.date_range("2026-02-01", periods=30).to_numpy(), 100)

    def model(m: np.ndarray) -> np.ndarray:
        return 10.0 * m[:, 0].astype("float64") + 0.84

    out = imp.permutation_importance(
        model,
        x,
        y,
        feature_names=["a", "b"],
        kind=imp.QUANTILE,
        alpha=0.8,
        days=days,
        config=imp.PermutationConfig(repeats=2, scheme="within_day"),
        reference=float(np.quantile(y, 0.8)),
    )
    assert out["primary_metric"] == "pinball_q080"
    first = out["features"][0]
    assert first["feature"] == "a" and first["pinball_q080"]["mean_drop"] > 0
    assert first["remaining_skill_share"] is not None and first["remaining_skill_share"] < 0.25


def test_permutation_input_checks():
    x, y, days = _classification_data(600)
    config = imp.PermutationConfig()
    with pytest.raises(ValueError):
        imp.permutation_importance(_model, x, y[:-1], feature_names=["a", "b"], kind="binary", days=days, config=config)
    y_nan = y.copy()
    y_nan[0] = np.nan
    with pytest.raises(ValueError):
        imp.permutation_importance(_model, x, y_nan, feature_names=["a", "b"], kind="binary", days=days, config=config)
    with pytest.raises(KeyError):
        imp.permutation_importance(
            _model,
            x,
            y,
            feature_names=["a", "b"],
            kind="binary",
            days=days,
            config=imp.PermutationConfig(features=("c",)),
        )
    with pytest.raises(ValueError):
        imp.PermutationConfig(scheme="shuffle_everything")


def test_b0_reference_comes_from_the_fit_window_tables():
    train, _ = _frames()
    description = _factory().fit(train, fit_end=FIT_END).describe()
    assert imp.b0_reference(description, "arr_del15") == pytest.approx(
        description["tables"]["route_hour_arrdel15"]["global_mean"]
    )
    assert imp.b0_reference(description, "arr_delay", 0.8) == pytest.approx(
        description["tables"]["route_hour_delay"]["global_quantiles"]["q080"]
    )
    assert imp.b0_reference(description, "arr_delay") is None


# ----------------------------------------------------------------------------
# time travel
# ----------------------------------------------------------------------------


def test_naive_recomputation_matches_the_history_tables():
    train, evaluation = _frames()
    fitted = _factory().fit(train, fit_end=FIT_END).transform(evaluation)
    for feature, (levels, target) in imp.RATE_FEATURES.items():
        recomputed = imp.naive_rate(train, evaluation, levels[1:], target, m=20.0, min_support=1)
        np.testing.assert_allclose(fitted[feature].to_numpy(dtype="float64"), recomputed, atol=1e-6)


def test_time_travel_passes_for_the_real_history_features():
    train, evaluation = _frames()
    result = imp.time_travel_check(train, evaluation, fit_end=FIT_END, history_factory=_factory, n_blocks=5)
    assert result["passed_all"] is True
    assert result["fit_refuses_future_rows"] is True
    assert result["information_gap_minutes"] > 0
    route = result["features"]["te_route_hour_arrdel15"]
    assert (
        route["future_labels_max_diff"] == 0.0 and route["recomputed_from_past_max_diff"] <= imp.TIME_TRAVEL_TOLERANCE
    )
    assert route["past_labels_change_values"] is True  # control: the check can see a change
    assert route["own_block_max_diff"] == 0.0 and result["oof"]["other_blocks_changed"] is True


class _OwnLabelHistory(ft.HistoryFeatures):
    """A broken implementation: mixes the evaluated row's own ArrDel15 into te_route_hour_arrdel15 (leak)."""

    def transform(self, frame: pd.DataFrame, *, require_after_fit_end: bool = True) -> pd.DataFrame:
        out = super().transform(frame, require_after_fit_end=require_after_fit_end)
        if "ArrDel15" in frame.columns:
            own = pd.to_numeric(frame["ArrDel15"], errors="coerce").fillna(0.0).to_numpy()
            out["te_route_hour_arrdel15"] = (0.5 * out["te_route_hour_arrdel15"] + 0.5 * own).astype("float32")
        return out


def test_time_travel_catches_a_feature_that_reads_the_rows_own_label():
    train, evaluation = _frames()
    result = imp.time_travel_check(
        train, evaluation, fit_end=FIT_END, history_factory=_OwnLabelHistory, oof_check=False
    )
    assert result["passed_all"] is False
    assert result["features"]["te_route_hour_arrdel15"]["passed"] is False
    assert result["features"]["te_dest_hour_arrdel15"]["passed"] is True


def test_time_travel_refuses_inconsistent_inputs():
    train, evaluation = _frames()
    with pytest.raises(ValueError):
        imp.time_travel_check(evaluation, train, fit_end=FIT_END, history_factory=_factory)


# ----------------------------------------------------------------------------
# two-stage review
# ----------------------------------------------------------------------------

KNOWLEDGE = {"te_route_hour_arrdel15": "past_realized", "day_of_year": "schedule", "oracle_origin_tmpf": "oracle"}


def _perm(remaining: float, feature: str = "te_route_hour_arrdel15", auc: float = 0.6) -> dict:
    return {
        "primary_metric": "roc_auc",
        "base": {"roc_auc": auc, "log_loss": 0.5},
        "features": [
            {
                "feature": feature,
                "roc_auc": {"mean_drop": 0.03, "sd_drop": 0.001},
                "remaining_skill_share": remaining,
            },
            {"feature": "day_of_year", "roc_auc": {"mean_drop": -0.01, "sd_drop": 0.001}, "remaining_skill_share": 1.1},
        ],
    }


GAIN = [{"feature": "te_route_hour_arrdel15", "gain_share": 0.529}, {"feature": "day_of_year", "gain_share": 0.09}]
TT_OK = {"features": {"te_route_hour_arrdel15": {"passed": True}}}
TT_FAIL = {"features": {"te_route_hour_arrdel15": {"passed": False}}}


def test_gain_alarm_alone_is_only_a_suspicion():
    review = imp.review_model("m", gain_importance=GAIN, permutation=None, time_travel=None, knowledge=KNOWLEDGE)
    assert review["status"] == "undecided" and review["reportable"] is False
    assert review["suspects"][0]["reasons"] == ["gain share > 50%"]


def test_permutation_plus_time_travel_decide():
    cleared = imp.review_model(
        "m", gain_importance=GAIN, permutation=_perm(0.7), time_travel=TT_OK, knowledge=KNOWLEDGE
    )
    assert cleared["status"] == "cleared" and cleared["reportable"] is True
    assert cleared["harmful_on_evaluation_set"][0]["feature"] == "day_of_year"
    dominant = imp.review_model(
        "m", gain_importance=GAIN, permutation=_perm(0.1), time_travel=TT_OK, knowledge=KNOWLEDGE
    )
    assert dominant["status"] == "dominant_past_only" and dominant["reportable"] is True
    leak = imp.review_model("m", gain_importance=GAIN, permutation=_perm(0.7), time_travel=TT_FAIL, knowledge=KNOWLEDGE)
    assert leak["status"] == "leak" and leak["reportable"] is False
    missing = imp.review_model("m", gain_importance=GAIN, permutation=_perm(0.1), time_travel=None, knowledge=KNOWLEDGE)
    assert missing["status"] == "undecided"


def test_collapse_on_an_oracle_feature_is_a_leak_and_no_skill_is_flagged():
    review = imp.review_model(
        "m",
        gain_importance=None,
        permutation=_perm(0.05, feature="oracle_origin_tmpf", auc=0.45),
        time_travel=None,
        knowledge=KNOWLEDGE,
    )
    assert review["status"] == "leak" and review["model_has_no_skill_over_B0"] is True
    run = imp.review_run({"a": review, "b": {"status": "cleared"}})
    assert run["status"] == "leak" and run["reportable"] is False
    assert imp.review_run({"b": {"status": "cleared"}, "c": {"status": "no_suspicion"}})["reportable"] is True
