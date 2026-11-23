"""Evaluation core of the final test (SYNTHETIC arrays): conformal windows, k > n, stratified AUC, criteria, pooling."""

from __future__ import annotations

import datetime as dt
import itertools
import math

import numpy as np
import pandas as pd
import pytest

from flight_delay.data.feature_contract import LeakageError
from flight_delay.modeling import calibration as cal
from flight_delay.modeling import conformal as cf
from flight_delay.modeling import final_eval as fe
from flight_delay.modeling import metrics as mt
from flight_delay.modeling import targets as tg
from flight_delay.modeling.splits import conformal_calibration_window

Z = {0.10: -1.2816, 0.50: 0.0, 0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def synthetic(start="2025-11-05", end="2026-08-31", per_day=40, seed=0):
    """Rows (context + evaluation) with an informative model and a flat B1, for every role of the final test."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    dates = np.repeat(days.to_numpy(), per_day)
    n = dates.size
    origin = rng.choice(["ORD", "ATL", "DEN"], size=n)
    minutes = rng.choice([420, 600, 900, 1140], size=n).astype("float64")
    signal = rng.normal(size=n)
    p_true = _sigmoid(-1.3 + 1.2 * signal)
    y15 = (rng.random(n) < p_true).astype("float64")
    cancel_true = _sigmoid(-3.0 + 1.0 * signal)
    cancelled = (rng.random(n) < cancel_true).astype("float64")
    mu = 5.0 + 8.0 * signal
    delay = mu + 10.0 * rng.normal(size=n)
    y15 = np.where(cancelled == 1, np.nan, y15)
    delay = np.where(cancelled == 1, np.nan, delay)
    targets = {tg.ARR_DEL15: y15, tg.CANCELLED: cancelled, tg.ARR_DELAY: delay}
    day_values = pd.to_datetime(dates)
    eval_mask = np.asarray(day_values >= pd.Timestamp("2026-03-01"))
    static_mask = np.asarray((day_values >= pd.Timestamp("2026-01-01")) & (day_values <= pd.Timestamp("2026-02-28")))
    p_model = np.clip(p_true + rng.normal(scale=0.02, size=n), 0.001, 0.999)
    p_plan = np.clip(_sigmoid(-1.3 + 1.2 * signal + rng.normal(scale=1.5, size=n)), 0.001, 0.999)  # noisier ranking
    b1 = np.full(n, float(np.nanmean(y15)))
    b1 = np.clip(b1 + rng.normal(scale=0.01, size=n), 0.001, 0.999)
    c_model = np.clip(cancel_true, 0.0005, 0.999)
    c_b1 = np.clip(np.full(n, float(cancelled.mean())) + rng.normal(scale=0.001, size=n), 0.0005, 0.999)
    model_q = {a: mu + z * 10.0 for a, z in Z.items()}
    plan_q = {a: 0.7 * mu + z * 11.0 for a, z in Z.items()}
    b1_q = {a: np.full(n, 5.0 + z * 13.0) for a, z in Z.items()}

    def calibrators(y, p, rows):
        keep = rows & np.isfinite(y)
        return {"platt": cal.fit_platt(y[keep], p[keep]), "isotonic": cal.fit_isotonic(y[keep], p[keep])}

    def role(name, target, p, ref):
        return fe.ClassifierRole(
            role=name,
            target=target,
            p=p,
            calibrators=calibrators(targets[target], p, static_mask),
            b1_calibrators=calibrators(targets[target], ref, static_mask),
            threshold=0.3,
            b1_threshold=0.25,
        )

    classifiers = {
        fe.ROLE_ARR_DEL15_T2: role(fe.ROLE_ARR_DEL15_T2, tg.ARR_DEL15, p_model, b1),
        fe.ROLE_ARR_DEL15_PLAN: role(fe.ROLE_ARR_DEL15_PLAN, tg.ARR_DEL15, p_plan, b1),
        fe.ROLE_CANCELLED_PLAN: role(fe.ROLE_CANCELLED_PLAN, tg.CANCELLED, c_model, c_b1),
    }
    quantiles = {
        fe.ROLE_QUANTILES_PLAN: fe.QuantileRole(fe.ROLE_QUANTILES_PLAN, model_q),
        fe.ROLE_QUANTILES_T2: fe.QuantileRole(fe.ROLE_QUANTILES_T2, plan_q),
    }
    return {
        "dates": dates,
        "origin": origin,
        "local_minutes": minutes,
        "targets": targets,
        "eval_mask": eval_mask,
        "static_mask": static_mask,
        "classifiers": classifiers,
        "quantiles": quantiles,
        "b1_rates": {tg.ARR_DEL15: b1, tg.CANCELLED: c_b1},
        "b1_quantiles": b1_q,
    }


def _inputs(data, **changes):
    options = {
        "label": "synthetic",
        "mode": "final_test",
        "event_threshold": 0.3,
        **{k: data[k] for k in data},
    }
    options.update(changes)
    return fe.assemble_inputs(**options)


@pytest.fixture(scope="module")
def data():
    return synthetic()


@pytest.fixture(scope="module")
def evaluation(data):
    acceptance = fe.Acceptance(k5_segment_min_n=100)
    return fe.evaluate(_inputs(data), acceptance=acceptance, replicates=200, segment_min_n=100)


def test_conformal_offsets_use_the_split_windows_and_report_k_greater_than_n():
    days = pd.date_range("2025-11-01", "2026-04-30", freq="D")
    dates = np.repeat(days.to_numpy(), 3)
    rng = np.random.default_rng(1)
    scores = rng.normal(size=dates.size)
    static = np.asarray((pd.to_datetime(dates) >= "2026-01-01") & (pd.to_datetime(dates) <= "2026-02-28"))
    months = [dt.date(2026, 3, 1), dt.date(2026, 4, 1)]
    out = fe.conformal_offsets(scores, dates, static, months, 0.80)
    window = conformal_calibration_window(dt.date(2026, 3, 1))
    assert out["rolling"]["2026-03"]["window_start"] == "2026-01-03" == str(window.start)
    assert out["rolling"]["2026-03"]["window_end"] == "2026-02-27" == str(window.end)
    inside = np.asarray((pd.to_datetime(dates) >= "2026-01-03") & (pd.to_datetime(dates) <= "2026-02-27"))
    assert out["rolling"]["2026-03"]["offset"] == cf.one_sided_offset(scores[inside], np.zeros(inside.sum()), 0.80)
    assert out["rolling"]["2026-03"]["n"] == int(inside.sum())
    public = conformal_calibration_window(dt.date(2026, 1, 1))  # month m - 2
    assert out["public"]["2026-03"]["window_start"] == str(public.start)
    assert out["static"]["2026-03"] == out["static"]["2026-04"] and out["static"]["2026-03"]["n"] == int(static.sum())
    # k > n: five rows in the window, level 0.95 -> k = ceil(6 * 0.95) = 6 > 5 -> +inf, flagged
    few = np.repeat(pd.date_range("2026-01-10", periods=5, freq="D").to_numpy(), 1)
    tiny = fe.conformal_offsets(np.zeros(5), few, np.zeros(5, dtype=bool), [dt.date(2026, 3, 1)], 0.95)
    record = tiny["rolling"]["2026-03"]
    assert record["n"] == 5 and record["rank"] == 6 and record["insufficient"] and math.isinf(record["offset"])
    assert tiny["public"]["2026-03"]["n"] == 0 and tiny["public"]["2026-03"]["insufficient"]
    assert tiny["static"]["2026-03"]["n"] == 0 and math.isinf(tiny["static"]["2026-03"]["offset"])


def test_static_window_inside_the_evaluation_is_refused():
    dates = pd.date_range("2026-01-01", "2026-03-31", freq="D").to_numpy()
    static = np.asarray(pd.to_datetime(dates) >= "2026-03-15")
    with pytest.raises(LeakageError):
        fe.conformal_offsets(np.zeros(dates.size), dates, static, [dt.date(2026, 3, 1)], 0.8)


def test_stratified_auc_counts_only_pairs_inside_a_stratum():
    rng = np.random.default_rng(2)
    n = 300
    strata = rng.integers(0, 12, size=n)
    score = np.round(rng.random(n), 1)
    y = (rng.random(n) < score).astype(float)
    wins = pairs = 0.0
    for i, j in itertools.product(range(n), range(n)):
        if strata[i] == strata[j] and y[i] == 1 and y[j] == 0:
            pairs += 1
            wins += 1.0 if score[i] > score[j] else 0.5 if score[i] == score[j] else 0.0
    out = fe.stratified_auc(y, score, strata)
    assert out["auc"] == pytest.approx(wins / pairs) and out["pairs"] == pairs
    assert fe.stratified_auc(np.zeros(4), np.ones(4), [1, 1, 2, 2])["auc"] is None


def test_assemble_refuses_overlap_and_too_short_context(data):
    with pytest.raises(LeakageError):
        _inputs(data, static_mask=data["eval_mask"] | data["static_mask"])
    late = np.asarray(pd.to_datetime(data["dates"]) >= "2026-01-01")
    short = dict(data)
    for key in ("dates", "origin", "local_minutes", "eval_mask", "static_mask"):
        short[key] = data[key][late]
    short["targets"] = {k: v[late] for k, v in data["targets"].items()}
    short["b1_rates"] = {k: v[late] for k, v in data["b1_rates"].items()}
    short["b1_quantiles"] = {k: v[late] for k, v in data["b1_quantiles"].items()}
    short["classifiers"] = {}
    short["quantiles"] = {
        r: fe.QuantileRole(r, {a: v[late] for a, v in q.q.items()}) for r, q in data["quantiles"].items()
    }
    with pytest.raises(ValueError, match="conformal windows need"):
        _inputs(short)


def test_evaluation_structure_criteria_and_paired_estimates(evaluation):
    assert set(evaluation["criteria"]) == {"K1", "K2", "K3", "K4", "K5", "K6", "K7"}
    assert evaluation["criteria"]["K7"]["passed"] is None  # no leakage evidence given
    assert evaluation["all_passed"] is False
    assert evaluation["days"]["n"] == 184 and evaluation["bootstrap"]["replicates"] == 200
    family = evaluation["holm"]["family"]
    assert len(family) == 7 and all(row["available"] for row in family.values())
    assert all(row["p_holm"] >= row["p_value"] for row in family.values())
    primary = evaluation["classification"][fe.ROLE_ARR_DEL15_T2]
    raw = primary["raw"]
    d_auc = evaluation["comparisons"][fe.ROLE_ARR_DEL15_T2]["vs_B1"]["d_roc_auc"]
    assert d_auc["estimate"] == pytest.approx(raw["model"]["roc_auc"] - raw["B1"]["roc_auc"], abs=1e-9)
    assert "roc_auc" not in primary["probability"]["platt"]["model"]  # ranking metrics from raw scores only
    assert set(primary["probability"]) == {"platt", "isotonic", "platt_rolling"}
    assert primary["stratified_auc_origin_day"]["model"]["auc"] is not None
    assert {"citl_platt", "slope_platt"} <= set(primary["bootstrap"])
    assert "slope_platt" not in evaluation["classification"][fe.ROLE_CANCELLED_PLAN]["bootstrap"]
    assert [row["month"] for row in primary["monthly"]] == [f"2026-0{m}" for m in range(3, 9)]
    assert set(primary["segments_platt"]) == {"Origin", "hour_block", "month"}
    # an informative model beats a flat B1: these criteria are computable and pass on this synthetic data
    assert evaluation["criteria"]["K1"]["passed"] is True
    assert evaluation["criteria"]["K4"]["passed"] is True
    weather = evaluation["comparisons"]["weather_contribution"]
    assert weather["arr_del15"]["d_roc_auc"]["estimate"] > 0 and "arr_delay" in weather


def test_conformal_section_and_k5(evaluation):
    plan = evaluation["quantile"][fe.ROLE_QUANTILES_PLAN]
    rolling = plan["conformal"]["model"]["rolling"]
    assert rolling["q080"]["months_insufficient"] == [] and rolling["q095"]["months_insufficient"] == []
    assert 0.7 < rolling["q080"]["coverage"] < 0.9  # exchangeable synthetic rows: near the target
    assert set(plan["conformal"]["model"]) == {"rolling", "static", "public", "offsets"}
    assert plan["conformal"]["model"]["offsets"]["rolling"]["q080"]["2026-03"]["window_end"] == "2026-02-27"
    assert rolling["q080"]["segments_origin_month"] == 18  # 3 origins x 6 months, n >= 100
    k5 = evaluation["criteria"]["K5"]
    assert k5["passed"] is not None and set(k5["details"]) >= {"coverage_q080", "segment_share_q095"}
    assert plan["bootstrap"]["coverage_rolling_q080"]["ci_low"] <= plan["bootstrap"]["coverage_rolling_q080"]["ci_high"]
    assert plan["monthly"][0]["coverage_public_q080"] is not None


def test_evaluation_is_deterministic(data):
    acceptance = fe.Acceptance(k5_segment_min_n=100)
    first = fe.evaluate(_inputs(data), acceptance=acceptance, replicates=50, segment_min_n=100)
    second = fe.evaluate(_inputs(data), acceptance=acceptance, replicates=50, segment_min_n=100)
    assert first["comparisons"] == second["comparisons"] and first["holm"] == second["holm"]


def test_pool_keeps_rows_and_refuses_overlapping_months(data):
    march = np.asarray(pd.to_datetime(data["dates"]) < "2026-06-01")
    first = _inputs(data, eval_mask=data["eval_mask"] & march, label="a")
    second = _inputs(data, eval_mask=data["eval_mask"] & ~march, label="b")
    pooled = fe.pool([first, second], label="a+b")
    whole = _inputs(data)
    for role in whole.classifiers:
        assert pooled.classifiers[role].y.size == whole.classifiers[role].y.size
        assert np.array_equal(np.sort(pooled.classifiers[role].raw), np.sort(whole.classifiers[role].raw))
    assert set(pooled.quantiles[fe.ROLE_QUANTILES_PLAN].offsets["rolling"]["q080"]) == {
        f"2026-0{m}" for m in range(3, 9)
    }
    with pytest.raises(ValueError, match="overlap"):
        fe.pool([first, first], label="twice")


def test_leakage_evidence_drives_k7(data):
    acceptance = fe.Acceptance(k5_segment_min_n=100)
    inputs = _inputs(data)
    passed = fe.evaluate(inputs, acceptance=acceptance, leakage={"passed": True}, replicates=20, segment_min_n=100)
    failed = fe.evaluate(inputs, acceptance=acceptance, leakage={"passed": False}, replicates=20, segment_min_n=100)
    assert passed["criteria"]["K7"]["passed"] is True and failed["criteria"]["K7"]["passed"] is False


def test_tolerance_rule_uses_only_the_interval_width():
    def entry(estimate, low, high):
        return {"estimate": estimate, "ci_low": low, "ci_high": high}

    pooled = {
        "classification": {
            fe.ROLE_ARR_DEL15_T2: {
                "bootstrap": {"citl_platt": entry(0.0, -0.004, 0.013), "slope_platt": entry(1.0, 0.97, 1.03)}
            }
        },
        "quantile": {
            fe.ROLE_QUANTILES_PLAN: {
                "bootstrap": {
                    "coverage_rolling_q080": entry(0.70, 0.669, 0.72),  # far from 0.80: the miss is NOT used
                    "coverage_rolling_q095": entry(0.95, 0.946, 0.954),
                }
            }
        },
    }
    proposal = fe.tolerance_proposal(pooled)["acceptance"]
    assert proposal["K3"]["citl_abs_max"] == pytest.approx(0.015)  # 0.013 rounded up to 0.015 > 0.01
    assert proposal["K3"]["slope_min"] == pytest.approx(0.90) and proposal["K3"]["slope_max"] == pytest.approx(1.10)
    assert proposal["K5"]["q080"] == pytest.approx([0.765, 0.835])  # half-width 0.031 -> 0.035
    assert proposal["K5"]["q095"] == pytest.approx([0.94, 0.96])  # 0.004 < plan 0.01
    assert proposal["K5"]["segment_tolerance"] == 0.05 and proposal["K5"]["segment_min_n"] == 500
    shifted = dict(pooled)
    shifted["quantile"] = {
        fe.ROLE_QUANTILES_PLAN: {
            "bootstrap": {
                "coverage_rolling_q080": entry(0.80, 0.769, 0.82),
                "coverage_rolling_q095": entry(0.95, 0.946, 0.954),
            }
        }
    }
    assert fe.tolerance_proposal(shifted)["acceptance"]["K5"]["q080"] == proposal["K5"]["q080"]
    assert fe.tolerance_proposal({})["acceptance"] is None
    round_trip = fe.Acceptance.from_dict(proposal)
    assert round_trip.same_values(fe.Acceptance.from_dict(round_trip.to_dict()))
    assert not round_trip.same_values(fe.Acceptance())


def test_rehearsal_checks_pass_on_a_complete_evaluation_and_fail_otherwise(evaluation):
    checks = fe.rehearsal_checks({"block": evaluation})
    assert checks["passed"] is True
    broken = {**evaluation, "criteria": {**evaluation["criteria"], "K5": {"passed": None}}}
    assert fe.rehearsal_checks({"block": broken})["passed"] is False
    assert fe.rehearsal_checks({})["passed"] is False


def test_rolling_platt_and_event_days(data):
    inputs = _inputs(data, event_threshold=0.0)  # every day with a delayed flight is an "event day"
    block = inputs.classifiers[fe.ROLE_ARR_DEL15_T2]
    assert block.event_day.all()
    assert np.all(np.isfinite(block.calibrated["platt_rolling"]))
    fit_rows = np.isfinite(data["targets"][tg.ARR_DEL15])
    days = pd.to_datetime(data["dates"])
    window = np.asarray((days >= "2026-01-03") & (days <= "2026-02-27")) & fit_rows
    march = np.asarray((days >= "2026-03-01") & (days <= "2026-03-31"))[fit_rows & data["eval_mask"]]
    refit = cal.fit_platt(data["targets"][tg.ARR_DEL15][window], data["classifiers"][fe.ROLE_ARR_DEL15_T2].p[window])
    expected = refit.predict(block.raw[march])
    assert np.allclose(block.calibrated["platt_rolling"][march], expected)
    threshold = fe.event_rate_threshold(pd.date_range("2025-01-01", periods=20).repeat(2), np.tile([0.0, 1.0], 20))
    assert threshold == pytest.approx(0.5)
    assert mt.brier_score([0, 1], [0.0, 1.0]) == 0.0
