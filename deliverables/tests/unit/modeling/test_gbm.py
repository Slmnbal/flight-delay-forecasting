"""LightGBM wrappers, quantile ordering and the gain alarm on SYNTHETIC numpy data (fast)."""

from __future__ import annotations

import numpy as np
import pytest
from models_synth import SMALL_PARAMS

from flight_delay.modeling import gbm
from flight_delay.modeling import metrics as mt

NAMES = ["origin_code", "num_a", "num_b"]


def _data(n: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    origin = rng.integers(0, 3, n).astype("float32")
    num_a = rng.normal(size=n).astype("float32")
    num_b = rng.normal(size=n).astype("float32")
    num_b[rng.random(n) < 0.1] = np.nan  # missing values are allowed
    logit = -1.0 + 1.5 * num_a + 0.8 * (origin == 2)
    y_class = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype("float64")
    y_delay = 10.0 * num_a + 5.0 * (origin == 2) + rng.gamma(1.5, 10.0, n)
    return np.column_stack([origin, num_a, num_b]), y_class, y_delay


def _train(task: gbm.GBMTask, y_index: int, rounds: int = 40) -> tuple[gbm.TrainedModel, np.ndarray, np.ndarray]:
    x, *ys = _data(1500, 1)
    x_valid, *ys_valid = _data(600, 2)
    params = gbm.make_params(task, gbm.DEFAULT_TUNABLE, num_threads=1, overrides=SMALL_PARAMS)
    model = gbm.train_model(
        task,
        x,
        ys[y_index],
        x_valid=x_valid,
        y_valid=ys_valid[y_index],
        params=params,
        feature_names=NAMES,
        categorical_indices=[0],
        num_boost_round=rounds,
        early_stopping_rounds=10,
    )
    return model, x_valid, ys_valid[y_index]


def test_binary_model_trains_predicts_probabilities_and_beats_chance():
    model, x_valid, y_valid = _train(gbm.BINARY_TASKS["arr_del15"], 0)
    p = gbm.predict(model, x_valid)
    assert p.shape == y_valid.shape and np.all((p >= 0) & (p <= 1))
    assert mt.roc_auc(y_valid, p) > 0.6
    assert 1 <= model.best_iteration <= 40
    assert model.summary()["params"]["deterministic"] is True


def test_training_is_deterministic():
    first, x_valid, _ = _train(gbm.BINARY_TASKS["arr_del15"], 0)
    second, _, _ = _train(gbm.BINARY_TASKS["arr_del15"], 0)
    np.testing.assert_array_equal(gbm.predict(first, x_valid), gbm.predict(second, x_valid))


def test_unknown_category_code_nan_is_predicted():
    model, x_valid, _ = _train(gbm.BINARY_TASKS["arr_del15"], 0)
    row = x_valid[:2].copy()
    row[:, 0] = np.nan  # category not in the fit-window list
    assert np.all(np.isfinite(gbm.predict(model, row)))


def test_quantile_models_and_ordering():
    predictions = {}
    for alpha, task in gbm.QUANTILE_TASKS.items():
        model, x_valid, y_valid = _train(task, 1)
        assert model.params["objective"] == "quantile" and model.params["alpha"] == alpha
        predictions[alpha] = gbm.predict(model, x_valid)
    ordered, raw_rate = gbm.order_quantiles(predictions)
    assert 0.0 <= raw_rate <= 1.0
    assert mt.quantile_crossing_rate(ordered) == 0.0
    assert np.all(ordered[0.5] <= ordered[0.8]) and np.all(ordered[0.8] <= ordered[0.95])


def test_order_quantiles_reports_the_raw_crossing_rate():
    crossing = {0.5: np.array([1.0, 5.0, 2.0]), 0.8: np.array([2.0, 4.0, 3.0]), 0.95: np.array([3.0, 6.0, 1.0])}
    ordered, raw_rate = gbm.order_quantiles(crossing)
    assert raw_rate == pytest.approx(2 / 3)  # rows 2 and 3 cross
    assert ordered[0.5].tolist() == [1.0, 4.0, 1.0]
    assert ordered[0.8].tolist() == [2.0, 5.0, 2.0]
    assert ordered[0.95].tolist() == [3.0, 6.0, 3.0]
    untouched, rate = gbm.order_quantiles({0.5: np.array([1.0]), 0.8: np.array([2.0])})
    assert rate == 0.0 and untouched[0.8].tolist() == [2.0]


def test_candidates_are_reproducible_and_inside_the_plan_space():
    first = gbm.candidate_parameters(5, seed=42)
    assert first == gbm.candidate_parameters(5, seed=42)
    assert len(first) == 5 and gbm.candidate_parameters(0) == []
    for candidate in first:
        assert set(candidate) == set(gbm.SEARCH_SPACE)
        for key, value in candidate.items():
            assert value in gbm.SEARCH_SPACE[key]
    params = gbm.make_params(gbm.QUANTILE_TASKS[0.95], first[0], num_threads=2)
    assert params["alpha"] == 0.95 and params["seed"] == 42 and params["num_threads"] == 2
    assert "is_unbalance" not in params  # plan 4.2: no class weights


def test_gain_importance_and_leakage_alarm():
    rng = np.random.default_rng(0)
    leak = rng.normal(size=1000).astype("float32")
    noise = rng.normal(size=(1000, 2)).astype("float32")
    x = np.column_stack([leak, noise])
    y = (leak > 0).astype("float64")  # the label is a function of one column: a "leak"
    task = gbm.BINARY_TASKS["arr_del15"]
    model = gbm.train_model(
        task,
        x,
        y,
        x_valid=x[:200],
        y_valid=y[:200],
        params=gbm.make_params(task, gbm.DEFAULT_TUNABLE, num_threads=1, overrides=SMALL_PARAMS),
        feature_names=["leak", "noise_1", "noise_2"],
        categorical_indices=[],
        num_boost_round=20,
        early_stopping_rounds=5,
    )
    importance = gbm.gain_importance(model)
    assert importance[0]["feature"] == "leak"
    assert sum(r["gain_share"] for r in importance) == pytest.approx(1.0)
    alarm = gbm.leakage_alarm(importance)
    assert alarm["raised"] is True and alarm["top_feature"] == "leak"
    assert gbm.leakage_alarm([{"feature": "a", "gain_share": 0.4}])["raised"] is False


def test_saved_model_is_never_overwritten(tmp_path):
    model, _, _ = _train(gbm.BINARY_TASKS["arr_del15"], 0, rounds=5)
    path = model.save(tmp_path / "m.txt")
    assert path.is_file()
    with pytest.raises(FileExistsError):
        model.save(path)


def _fit(task, *, rounds, patience, y_index=0, valid_seed=2, **kwargs):
    x, *ys = _data(1500, 1)
    x_valid, *ys_valid = _data(600, valid_seed)
    params = gbm.make_params(task, gbm.DEFAULT_TUNABLE, num_threads=1, overrides=SMALL_PARAMS)
    return gbm.train_model(
        task,
        x,
        ys[y_index],
        x_valid=x_valid,
        y_valid=ys_valid[y_index],
        params=params,
        feature_names=NAMES,
        categorical_indices=[0],
        num_boost_round=rounds,
        early_stopping_rounds=patience,
        **kwargs,
    )


def test_round_cap_is_reported_from_the_rounds_actually_trained():
    # patience larger than the cap: early stopping cannot trigger, every round is trained -> the cap was hit,
    # whatever the best iteration is (the old check compared the re-loaded booster's size with the cap)
    capped = _fit(gbm.QUANTILE_TASKS[0.5], rounds=6, patience=50, y_index=1)
    assert capped.rounds_trained == 6
    assert capped.hit_round_cap is True
    assert 1 <= capped.best_iteration <= 6
    assert capped.summary()["rounds_trained"] == 6 and capped.summary()["early_stopping_rounds"] == 50


def test_early_stop_before_the_cap_is_not_a_cap_hit():
    rng = np.random.default_rng(5)
    x = rng.normal(size=(800, 3)).astype("float32")
    y = rng.integers(0, 2, 800).astype("float64")  # pure noise: the validation loss stops improving quickly
    task = gbm.BINARY_TASKS["arr_del15"]
    params = gbm.make_params(task, gbm.DEFAULT_TUNABLE, num_threads=1, overrides=SMALL_PARAMS)
    model = gbm.train_model(
        task,
        x[:600],
        y[:600],
        x_valid=x[600:],
        y_valid=y[600:],
        params=params,
        feature_names=NAMES,
        categorical_indices=[],
        num_boost_round=300,
        early_stopping_rounds=3,
    )
    assert model.rounds_trained < 300
    assert model.rounds_trained - model.best_iteration == 3  # stopped by the patience
    assert model.hit_round_cap is False


def test_record_curves_keeps_every_round_and_stops_on_the_first_metric():
    model = _fit(gbm.BINARY_TASKS["cancelled"], rounds=40, patience=5, record_curves=True, keep_full_booster=True)
    curves = model.curves
    assert set(curves) == set(gbm.BINARY_CURVE_METRICS)
    assert all(len(values) == model.rounds_trained for values in curves.values())
    logloss = np.asarray(curves["binary_logloss"])
    assert model.best_iteration == int(np.argmin(logloss)) + 1  # log-loss (the task metric) chose the round
    summary = model.summary()["valid_curves"]
    assert summary["binary_logloss"]["best_round"] == model.best_iteration
    x_valid, *_ = _data(600, 2)
    last = gbm.predict_at(model, x_valid, model.rounds_trained)  # trees after the best one are still there
    assert last.shape == (600,)
    np.testing.assert_allclose(gbm.predict_at(model, x_valid, model.best_iteration), gbm.predict(model, x_valid))
    with pytest.raises(ValueError):
        gbm.predict_at(model, x_valid, model.rounds_trained + 1)


def test_average_precision_can_drive_early_stopping_of_a_binary_task():
    task = gbm.with_early_stopping_metric(gbm.BINARY_TASKS["cancelled"], "average_precision")
    assert task.metric == "average_precision" and gbm.BINARY_TASKS["cancelled"].metric == "binary_logloss"
    model = _fit(task, rounds=40, patience=5, record_curves=True)
    ap = np.asarray(model.curves["average_precision"])
    assert model.best_iteration == int(np.argmax(ap)) + 1  # higher is better for AP
    assert model.summary()["early_stopping_metric"] == "average_precision"
    assert model.best_score == pytest.approx(float(ap.max()))
    with pytest.raises(ValueError):
        gbm.with_early_stopping_metric(gbm.QUANTILE_TASKS[0.8], "auc")
    with pytest.raises(ValueError):
        gbm.with_early_stopping_metric(task, "accuracy")


def test_interval_tasks_and_thin_curve():
    assert sorted(gbm.INTERVAL_TASKS) == [0.1, 0.9]
    assert gbm.INTERVAL_TASKS[0.1].name == "arr_delay_q010" and gbm.INTERVAL_TASKS[0.9].alpha == 0.9
    points = gbm.thin_curve([float(i) for i in range(1, 126)])
    rounds = [int(r) for r, _ in points]
    assert rounds[:50] == list(range(1, 51)) and rounds[50:] == [60, 70, 80, 90, 100, 110, 120, 125]
    assert gbm.thin_curve([]) == []


def test_labels_outside_the_universe_are_refused():
    x, y, _ = _data(50, 3)
    y[0] = np.nan
    task = gbm.BINARY_TASKS["arr_del15"]
    with pytest.raises(ValueError):
        gbm.train_model(
            task,
            x,
            y,
            x_valid=x,
            y_valid=np.nan_to_num(y),
            params=gbm.make_params(task, gbm.DEFAULT_TUNABLE, num_threads=1),
            feature_names=NAMES,
            categorical_indices=[0],
            num_boost_round=2,
            early_stopping_rounds=1,
        )
