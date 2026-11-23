"""Modeling: time splits, T-2 h features, targets, baselines and metrics (plan ``experiments/modelleme-plani.md``).

Modules:
    splits         -- split dates (single source), embargo, rolling folds, final-test guard (plan section 1)
    features       -- feature matrix at T = 2 h + feature contract; oracle weather only with ``oracle=True`` (2.1-2.6)
    history        -- past statistics / target encoding with back-off, fit-window only, out-of-fold (2.4, 4.1)
    targets        -- ArrDel15, cancellation, arrival-delay quantile target and their universes (3)
    metrics        -- classification and quantile metrics (5.1), numpy only
    baselines      -- B0 / B1 / B2 (4.1) evaluated with the same metric code
    loading        -- month-by-month, column-pruned layer reading that never opens the final test
    run_baselines  -- CLI: baselines on Val-A / Val-B -> experiments/baselines/
    categories     -- fixed category lists from the fit window (unknown -> missing)
    matrix         -- float32 model matrices month by month; side-table reader that refuses final-test months
    gbm            -- LightGBM binary / quantile models, search space (4.3), quantile ordering, gain importance
    logistic       -- logistic-regression baseline L as a scikit-learn Pipeline (4.1)
    run_models     -- CLI: search on K3/K4 + main models on Val-A / Val-B vs B1 -> experiments/models/

(categories / matrix / gbm / logistic / run_models are not imported here, so ``import flight_delay.modeling`` does
not need scikit-learn or LightGBM.)

Plan names (Turkish) -> code names: ``experiments/modelleme-ad-eslemesi.md``.
"""

from flight_delay.modeling.baselines import BASELINES, evaluate_baselines
from flight_delay.modeling.features import FeatureMatrix, HistoryFeatures, build_contract, build_feature_matrix
from flight_delay.modeling.history import BackoffQuantileTable, SmoothedRateTable, out_of_fold
from flight_delay.modeling.splits import (
    FINAL_TEST,
    ROLLING_FOLDS,
    SPLITS,
    TRAIN,
    VAL_A,
    VAL_B,
    FinalTestAccessError,
    Period,
    get_period,
    select_split,
)

__all__ = [
    "BASELINES",
    "FINAL_TEST",
    "ROLLING_FOLDS",
    "SPLITS",
    "TRAIN",
    "VAL_A",
    "VAL_B",
    "BackoffQuantileTable",
    "FeatureMatrix",
    "FinalTestAccessError",
    "HistoryFeatures",
    "Period",
    "SmoothedRateTable",
    "build_contract",
    "build_feature_matrix",
    "evaluate_baselines",
    "get_period",
    "out_of_fold",
    "select_split",
]
