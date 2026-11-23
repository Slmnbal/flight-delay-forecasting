"""LightGBM main models (plan sections 4.2 - 4.3): binary (ArrDel15, cancellation) and quantile (P50 / P80 / P95).

- ``lgb.train`` on float32 numpy matrices; categorical columns are the FIXED codes of ``CategoryEncoder`` (indices
  passed as ``categorical_feature``). No class weights (plan 4.2: ``is_unbalance`` off, probabilities stay calibrated).
- Reproducibility (plan 4.2): ``seed`` = 42, ``deterministic`` = True, ``force_row_wise`` = True (LightGBM recommends
  fixing the row/col-wise choice together with ``deterministic``), fixed ``num_threads`` (recorded in the results).
- Early stopping on ONE named validation set (``valid``) with the plan's objective metric: ``binary_logloss`` for the
  binary tasks, ``quantile`` (= pinball loss at alpha) for the quantile tasks. Which period plays the validation role is
  the caller's decision (run_models: fold evaluation window during the search, Val-A for the final fit; never Val-B).
- Hyperparameter search space = plan section 4.3, with ``feature_fraction`` / ``bagging_fraction`` discretised to
  {0.6, 0.7, 0.8, 0.9, 1.0} (assumption: the plan gives a continuous range [0.6, 1.0]); sampled with scikit-learn
  ``ParameterSampler`` (random_state 42), so the candidate list is reproducible.
- Quantile crossing (plan 3.3): three separate models can cross; ``order_quantiles`` reports the raw crossing rate and
  sorts each row (``np.sort``), which makes P50 <= P80 <= P95 hold by construction.
- Feature importance: total gain per feature and its share. Plan section 7 prefers permutation importance (gain favours
  high-cardinality / often-split features); gain is what this step reports, with that caveat. ``leakage_alarm`` flags a
  single feature with > 50 % of the total gain (plan 2.6 "suspicious score" rule, applied here to gain as a proxy).
- Round cap (fix after run-20261119T182216Z): ``lgb.train`` returns a booster re-loaded from its own text model, which
  keeps only the trees up to the best iteration, so ``current_iteration()`` is the best iteration, not the number of
  rounds trained. The old ``hit_round_cap = current_iteration() >= cap`` was therefore False for q050 (best 1999 of
  2000 with patience 100: early stopping could not have triggered before round 2099, so the cap WAS hit). Now a
  callback counts the rounds actually trained: ``hit_round_cap`` = all ``cap`` rounds trained and the patience did not
  run out (``rounds_trained - best_iteration < early_stopping_rounds``).
- Interval tasks (plan 4.2): alpha 0.10 / 0.90 for the two-sided 80 % interval (``INTERVAL_TASKS``, opt-in in the run).
- Early stopping metric of a binary task can be switched to ``auc`` / ``average_precision``
  (``with_early_stopping_metric``); ``record_curves`` keeps the per-round validation curves (+ ``auc`` and
  ``average_precision`` for binary tasks, recorded only, the first metric stops) for the diagnosis of early stops.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
from sklearn.model_selection import ParameterSampler

from flight_delay.modeling import metrics as mt

__all__ = [
    "BINARY_CURVE_METRICS",
    "BINARY_EARLY_STOPPING_METRICS",
    "BINARY_TASKS",
    "DEFAULT_TUNABLE",
    "FIXED_PARAMS",
    "INTERVAL_TASKS",
    "LEAKAGE_GAIN_SHARE",
    "QUANTILE_TASKS",
    "SEARCH_SPACE",
    "GBMTask",
    "TrainedModel",
    "candidate_parameters",
    "gain_importance",
    "leakage_alarm",
    "make_params",
    "order_quantiles",
    "predict",
    "predict_at",
    "thin_curve",
    "train_model",
    "with_early_stopping_metric",
]


@dataclass(frozen=True)
class GBMTask:
    """One LightGBM model: objective, metric used for early stopping, and the alpha of a quantile task."""

    name: str
    objective: str
    metric: str
    alpha: float | None = None

    @property
    def is_quantile(self) -> bool:
        return self.objective == "quantile"


BINARY_TASKS: dict[str, GBMTask] = {
    "arr_del15": GBMTask("arr_del15", "binary", "binary_logloss"),
    "cancelled": GBMTask("cancelled", "binary", "binary_logloss"),
}
QUANTILE_TASKS: dict[float, GBMTask] = {
    a: GBMTask(f"arr_delay_{mt.quantile_key(a)}", "quantile", "quantile", alpha=a) for a in (0.50, 0.80, 0.95)
}
# plan 4.2: alpha 0.10 / 0.90 models for the two-sided 80 % interval (CQR); same naming as the main quantiles
INTERVAL_TASKS: dict[float, GBMTask] = {
    a: GBMTask(f"arr_delay_{mt.quantile_key(a)}", "quantile", "quantile", alpha=a) for a in (0.10, 0.90)
}
# LightGBM metric names; the first is the plan's objective metric (plan 4.3), the others rank-based alternatives
BINARY_EARLY_STOPPING_METRICS: tuple[str, ...] = ("binary_logloss", "auc", "average_precision")
BINARY_CURVE_METRICS: tuple[str, ...] = BINARY_EARLY_STOPPING_METRICS


def with_early_stopping_metric(task: GBMTask, metric: str) -> GBMTask:
    """Copy of a binary task that early-stops on ``metric`` (one of ``BINARY_EARLY_STOPPING_METRICS``)."""
    if task.objective != "binary":
        raise ValueError(f"Only binary tasks can change the early stopping metric: {task.name}")
    if metric not in BINARY_EARLY_STOPPING_METRICS:
        raise ValueError(f"metric must be one of {BINARY_EARLY_STOPPING_METRICS}: {metric!r}")
    return dataclasses.replace(task, metric=metric)


FIXED_PARAMS: dict[str, Any] = {
    "seed": 42,
    "deterministic": True,
    "force_row_wise": True,
    "bagging_freq": 1,
    "verbosity": -1,
}
# used when the search is off (assumption: mid-range values of the plan 4.3 space)
DEFAULT_TUNABLE: dict[str, Any] = {
    "num_leaves": 63,
    "learning_rate": 0.05,
    "min_child_samples": 200,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "lambda_l2": 1.0,
    "max_bin": 255,
    "cat_smooth": 10,
}
_FRACTIONS = [0.6, 0.7, 0.8, 0.9, 1.0]
SEARCH_SPACE: dict[str, list[Any]] = {
    "num_leaves": [31, 63, 127, 255],
    "learning_rate": [0.03, 0.05, 0.1],
    "min_child_samples": [50, 200, 500, 1000],
    "feature_fraction": _FRACTIONS,
    "bagging_fraction": _FRACTIONS,
    "lambda_l2": [0.0, 1.0, 10.0],
    "max_bin": [63, 255],
    "cat_smooth": [10, 50],
}
LEAKAGE_GAIN_SHARE = 0.5


def candidate_parameters(n_trials: int, *, seed: int = 42) -> list[dict[str, Any]]:
    """``n_trials`` configurations from SEARCH_SPACE (sorted keys, plain Python values; reproducible)."""
    if n_trials < 1:
        return []
    sampled = ParameterSampler(SEARCH_SPACE, n_iter=n_trials, random_state=seed)
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in sorted(dict(c).items())} for c in sampled]


def make_params(
    task: GBMTask, tunable: Mapping[str, Any], *, num_threads: int, overrides: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Full LightGBM parameter dict: objective / metric of the task + tunable values + fixed values (+ overrides)."""
    params: dict[str, Any] = {"objective": task.objective, "metric": task.metric}
    if task.alpha is not None:
        params["alpha"] = task.alpha
    params.update(dict(tunable))
    params.update(FIXED_PARAMS)
    params["num_threads"] = int(num_threads)
    if overrides:
        params.update(dict(overrides))
    return params


@dataclass
class TrainedModel:
    task: GBMTask
    booster: lgb.Booster
    params: dict[str, Any]
    best_iteration: int
    best_score: float | None
    num_boost_round: int
    hit_round_cap: bool
    seconds: float
    n_train: int
    n_valid: int
    feature_names: list[str] = field(default_factory=list)
    rounds_trained: int = 0
    early_stopping_rounds: int = 0
    curves: dict[str, list[float]] = field(default_factory=dict)  # validation metric per round (record_curves)
    full_booster: bool = False  # True: trees after the best iteration are still in the booster (predict_at)

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "task": self.task.name,
            "objective": self.task.objective,
            "alpha": self.task.alpha,
            "early_stopping_metric": self.task.metric,
            "best_iteration": self.best_iteration,
            "best_valid_score": self.best_score,
            "num_boost_round_cap": self.num_boost_round,
            "rounds_trained": self.rounds_trained,
            "early_stopping_rounds": self.early_stopping_rounds,
            "hit_round_cap": self.hit_round_cap,
            "seconds": round(self.seconds, 2),
            "n_train": self.n_train,
            "n_valid": self.n_valid,
            "params": dict(self.params),
        }
        if self.curves:
            out["valid_curves"] = {
                name: {
                    "best_round": _best_round(values, name),
                    "best_value": values[_best_round(values, name) - 1],
                    "points": thin_curve(values),
                }
                for name, values in self.curves.items()
            }
        return out

    def save(self, path: Path) -> Path:
        """LightGBM text model with the best iteration only."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"Model file exists, will not overwrite: {path}")
        self.booster.save_model(str(path), num_iteration=self.best_iteration)
        return path


def _check_xy(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    values = np.asarray(y, dtype="float64").ravel()
    if x.ndim != 2 or x.shape[0] != values.size:
        raise ValueError(f"x {x.shape} and y {values.shape} do not match")
    if not np.all(np.isfinite(values)):
        raise ValueError("Non-finite labels: filter the target universe first")
    return values


_HIGHER_IS_BETTER = frozenset({"auc", "average_precision"})


def _best_round(values: Sequence[float], metric: str) -> int:
    """1-based round with the best value (first one on ties)."""
    array = np.asarray(values, dtype="float64")
    index = int(np.argmax(array)) if metric in _HIGHER_IS_BETTER else int(np.argmin(array))
    return index + 1


def thin_curve(values: Sequence[float], *, dense_rounds: int = 50, step: int = 10) -> list[list[float]]:
    """[[round, value], ...]: every round up to ``dense_rounds``, then every ``step``-th round, plus the last round."""
    n = len(values)
    rounds = sorted({r for r in range(1, n + 1) if r <= dense_rounds or r % step == 0} | ({n} if n else set()))
    return [[float(r), float(values[r - 1])] for r in rounds]


class _RoundCounter:
    """LightGBM callback (after each round, before early stopping) counting the rounds actually trained."""

    order = 5  # lower than early_stopping (30) so the round that raises the stop is counted too
    before_iteration = False

    def __init__(self) -> None:
        self.rounds = 0

    def __call__(self, env: Any) -> None:
        self.rounds = int(env.iteration - env.begin_iteration + 1)


def train_model(
    task: GBMTask,
    x: np.ndarray,
    y: np.ndarray,
    *,
    x_valid: np.ndarray,
    y_valid: np.ndarray,
    params: Mapping[str, Any],
    feature_names: Sequence[str],
    categorical_indices: Sequence[int],
    num_boost_round: int,
    early_stopping_rounds: int,
    record_curves: bool = False,
    keep_full_booster: bool = False,
) -> TrainedModel:
    """Fit with early stopping on (x_valid, y_valid) and ``task.metric``. The datasets are freed after construction.

    ``record_curves``: keep the validation value of every round (binary tasks: also ``auc`` and ``average_precision``;
    they are recorded only - ``first_metric_only`` makes the task metric the one that stops).
    ``keep_full_booster``: keep the trees after the best iteration (``predict_at`` for diagnostics); predictions,
    importance and the saved file still use the best iteration.
    """
    labels = _check_xy(x, y)
    labels_valid = _check_xy(x_valid, y_valid)
    if task.objective == "binary" and not np.all((labels == 0) | (labels == 1)):
        raise ValueError("Binary task needs 0/1 labels")
    if num_boost_round < 1 or early_stopping_rounds < 1:
        raise ValueError("num_boost_round and early_stopping_rounds must be >= 1")
    train_params = dict(params)
    train_params["metric"] = task.metric
    if record_curves and task.objective == "binary":
        train_params["metric"] = [task.metric, *(m for m in BINARY_CURVE_METRICS if m != task.metric)]
    started = time.perf_counter()
    train_set = lgb.Dataset(
        x,
        label=labels,
        feature_name=list(feature_names),
        categorical_feature=list(categorical_indices),
        free_raw_data=True,
    )  # binning parameters (max_bin, ...) come from ``params`` when lgb.train constructs the dataset
    valid_set = lgb.Dataset(x_valid, label=labels_valid, reference=train_set, free_raw_data=True)
    counter = _RoundCounter()
    history: dict[str, Any] = {}
    callbacks: list[Any] = [
        counter,
        lgb.early_stopping(stopping_rounds=early_stopping_rounds, first_metric_only=True, verbose=False),
        lgb.log_evaluation(period=0),
    ]
    if record_curves:
        callbacks.append(lgb.record_evaluation(history))
    booster = lgb.train(
        train_params,
        train_set,
        num_boost_round=num_boost_round,
        valid_sets=[valid_set],
        valid_names=["valid"],
        callbacks=callbacks,
        keep_training_booster=keep_full_booster,
    )
    if keep_full_booster:
        booster.free_dataset()
    rounds_done = counter.rounds if counter.rounds > 0 else int(booster.current_iteration())
    best = int(booster.best_iteration) if int(booster.best_iteration) > 0 else rounds_done
    scores = dict(booster.best_score).get("valid", {})
    score = scores.get(task.metric)
    curves = {str(k): [float(v) for v in values] for k, values in dict(history.get("valid", {})).items()}
    return TrainedModel(
        task=task,
        booster=booster,
        params=dict(params),
        best_iteration=best,
        best_score=float(score) if score is not None else None,
        num_boost_round=num_boost_round,
        # every allowed round was trained and the patience had not run out: more rounds could still have helped
        hit_round_cap=rounds_done >= num_boost_round and rounds_done - best < early_stopping_rounds,
        seconds=time.perf_counter() - started,
        n_train=int(labels.size),
        n_valid=int(labels_valid.size),
        feature_names=list(feature_names),
        rounds_trained=rounds_done,
        early_stopping_rounds=early_stopping_rounds,
        curves=curves,
        full_booster=keep_full_booster,
    )


def _predict_booster(model: TrainedModel, x: np.ndarray, iteration: int, chunk_rows: int) -> np.ndarray:
    parts = [
        np.asarray(model.booster.predict(x[start : start + chunk_rows], num_iteration=iteration))
        for start in range(0, x.shape[0], chunk_rows)
    ]
    out = np.concatenate(parts).astype("float64") if parts else np.empty(0, dtype="float64")
    if model.task.objective == "binary":
        out = np.clip(out, 0.0, 1.0)
    return out


def predict(model: TrainedModel, x: np.ndarray, *, chunk_rows: int = 500_000) -> np.ndarray:
    """Predictions at the best iteration (probabilities for binary tasks), float64, in chunks."""
    return _predict_booster(model, x, model.best_iteration, chunk_rows)


def predict_at(model: TrainedModel, x: np.ndarray, iteration: int, *, chunk_rows: int = 500_000) -> np.ndarray:
    """Predictions after ``iteration`` rounds (diagnostics). Rounds after the best one need ``keep_full_booster``."""
    available = model.rounds_trained if model.full_booster else model.best_iteration
    if not 1 <= iteration <= available:
        raise ValueError(f"iteration must be in [1, {available}] for this booster: {iteration}")
    return _predict_booster(model, x, iteration, chunk_rows)


def order_quantiles(predictions: Mapping[float, np.ndarray]) -> tuple[dict[float, np.ndarray], float]:
    """(row-wise sorted quantiles, raw crossing rate). After sorting, a lower alpha never exceeds a higher one."""
    alphas = sorted(predictions)
    raw_rate = mt.quantile_crossing_rate(predictions)
    matrix = np.sort(np.column_stack([np.asarray(predictions[a], dtype="float64") for a in alphas]), axis=1)
    return {a: matrix[:, i].copy() for i, a in enumerate(alphas)}, raw_rate


def gain_importance(model: TrainedModel) -> list[dict[str, Any]]:
    """Total gain per feature at the best iteration, with share of the total; sorted descending."""
    gains = np.asarray(
        model.booster.feature_importance(importance_type="gain", iteration=model.best_iteration), dtype="float64"
    )
    splits = np.asarray(
        model.booster.feature_importance(importance_type="split", iteration=model.best_iteration), dtype="float64"
    )
    total = float(gains.sum())
    rows = [
        {
            "feature": name,
            "gain": float(gain),
            "gain_share": float(gain / total) if total > 0 else 0.0,
            "splits": int(split),
        }
        for name, gain, split in zip(model.feature_names, gains, splits, strict=True)
    ]
    return sorted(rows, key=lambda r: (-r["gain"], r["feature"]))


def leakage_alarm(importance: Sequence[Mapping[str, Any]], threshold: float = LEAKAGE_GAIN_SHARE) -> dict[str, Any]:
    """Flag a single feature carrying more than ``threshold`` of the total gain (plan 2.6; gain used as a proxy)."""
    top = importance[0] if importance else None
    share = float(top["gain_share"]) if top else 0.0
    return {
        "raised": bool(share > threshold),
        "threshold": threshold,
        "top_feature": top["feature"] if top else None,
        "top_gain_share": share,
        "rule": "stage 1 (suspicion): single feature gain share > threshold; the decision is stage 2 "
        "(importance: Val-B permutation + time travel test)",
    }
