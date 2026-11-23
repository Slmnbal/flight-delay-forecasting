"""Logistic baseline L (scikit-learn Pipeline) on SYNTHETIC data."""

from __future__ import annotations

import pickle

import numpy as np
import pandas as pd

from flight_delay.modeling import metrics as mt
from flight_delay.modeling.categories import CategoryEncoder
from flight_delay.modeling.logistic import RangeClipper, fit_logistic

NAMES = ["Origin", "hour_block", "num"]


def _encoder() -> CategoryEncoder:
    frame = pd.DataFrame({"Origin": ["ATL", "DEN", "ORD"], "Reporting_Airline": ["AA", "AA", "UA"]})
    return CategoryEncoder().fit(frame)


def _data(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    origin = rng.choice([0.0, 2.0], n)  # DEN (code 1) never appears in the fit sample
    hour = rng.integers(0, 4, n).astype("float64")  # blocks 4..6 never appear
    num = rng.normal(size=n)
    num[rng.random(n) < 0.1] = np.nan
    logit = -0.5 + 1.2 * np.nan_to_num(num) + 0.7 * (origin == 2)
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype("float64")
    return np.column_stack([origin, hour, num]).astype("float32"), y


def test_logistic_pipeline_uses_fixed_one_hot_lists_and_predicts_probabilities():
    x, y = _data(800, 1)
    model = fit_logistic(x, y, NAMES, _encoder(), c=1.0, max_iter=200)
    summary = model.summary()
    # one-hot: 3 Origin codes (fixed list) + 7 hour blocks (fixed) ; numeric: num + its missing indicator
    assert summary["n_model_columns"] == 3 + 7 + 2
    x_new, _ = _data(50, 2)
    x_new[0, 0] = np.nan  # unknown Origin (not in the fit-window list) -> all-zero one-hot row
    x_new[1, 1] = 6.0  # a block never seen in the fit sample, but inside the fixed list
    p = model.predict(x_new, chunk_rows=7)
    assert p.shape == (50,) and np.all((p > 0) & (p < 1))
    assert summary["params"]["solver"] == "lbfgs"
    assert isinstance(summary["convergence_warnings"], list)


# ----------------------------------------------------------------------------
# root cause of the smoke-run cancellation L (ROC-AUC 0.41 / 0.23): extrapolation of summer slopes into winter
# ----------------------------------------------------------------------------

SEASON_NAMES = ["Origin", "te_route_cancel", "origin_tmpf"]


def _season(n: int, seed: int, *, winter: bool) -> tuple[np.ndarray, np.ndarray]:
    """Cancellation risk is U-shaped in temperature: hot (thunderstorms) AND cold (snow) raise it.

    Summer fit window: tmpf in [60, 100], only the hot arm is visible (positive slope). Winter evaluation: tmpf in
    [-10, 40], entirely below the fit range, where the cold arm applies (negative slope). ``te_route_cancel`` carries a
    stable signal in both seasons.
    """
    rng = np.random.default_rng(seed)
    origin = rng.integers(0, 3, n).astype("float64")
    te = rng.uniform(0.0, 0.1, n)
    if winter:
        tmpf = rng.uniform(-10.0, 40.0, n)
        logit = -4.0 + 25.0 * te + 0.10 * (20.0 - tmpf)
    else:
        tmpf = rng.uniform(60.0, 100.0, n)
        logit = -4.0 + 25.0 * te + 0.08 * (tmpf - 80.0)
    y = (rng.random(n) < 1.0 / (1.0 + np.exp(-logit))).astype("float64")
    return np.column_stack([origin, te, tmpf]).astype("float32"), y


def test_unclipped_logistic_inverts_the_ranking_out_of_season():
    """Reproduces the smoke symptom with the step-2 pipeline (no clipping): ROC-AUC far below 0.5 out of season,
    although the labels, the class order (predict_proba[:, 1] = P(y = 1)) and the rows are all correct."""
    x, y = _season(20_000, 11, winter=False)
    model = fit_logistic(x, y, SEASON_NAMES, _encoder(), clip_quantile=None)
    assert list(model.pipeline.named_steps["model"].classes_) == [0, 1]
    x_summer, y_summer = _season(20_000, 12, winter=False)
    assert mt.roc_auc(y_summer, model.predict(x_summer)) > 0.6  # in season the model is fine
    x_winter, y_winter = _season(20_000, 13, winter=True)
    assert mt.roc_auc(y_winter, model.predict(x_winter)) < 0.45  # out of season: inverted (symptom)


def test_default_logistic_ranks_out_of_season_rows_above_chance():
    """Fails on the step-2 pipeline (see the test above), passes with the fit-range clipping (default)."""
    x, y = _season(20_000, 11, winter=False)
    model = fit_logistic(x, y, SEASON_NAMES, _encoder())
    x_winter, y_winter = _season(20_000, 13, winter=True)
    assert mt.roc_auc(y_winter, model.predict(x_winter)) > 0.53
    report = model.extrapolation(x_winter)
    assert report[0]["feature"] == "origin_tmpf" and report[0]["share_outside_fit_range"] == 1.0
    assert model.summary()["params"]["clip_quantile"] == 0.0


def test_range_clipper_keeps_nan_and_training_values():
    train = np.array([[1.0, 0.0], [3.0, np.nan], [2.0, 1.0]])
    clipper = RangeClipper().fit(train)
    np.testing.assert_array_equal(clipper.transform(train), train)  # training values never move
    out = clipper.transform(np.array([[-5.0, np.nan], [9.0, 0.5]]))
    assert out[0, 0] == 1.0 and np.isnan(out[0, 1]) and out[1, 0] == 3.0 and out[1, 1] == 0.5
    np.testing.assert_allclose(clipper.share_outside(np.array([[-5.0, np.nan], [9.0, 0.5]])), [1.0, 0.0])
    assert RangeClipper().fit(np.array([[np.nan], [np.nan]])).transform(np.array([[7.0]]))[0, 0] == 7.0
    assert pickle.loads(pickle.dumps(clipper)).lower_.tolist() == [1.0, 0.0]
