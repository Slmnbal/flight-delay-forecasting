# Methodology

> Based on public data; not affiliated with any airline.

Details behind the [README](../../README.md) and the [model card](model-card.md). Sources: the modelling plan
[`experiments/modelleme-plani.md`](../../experiments/modelleme-plani.md), the pre-registration
[`experiments/son-test-on-kayit.md`](../../experiments/son-test-on-kayit.md), calibration/conformal notes
[`experiments/kalibrasyon-conformal-kararlari.md`](../../experiments/kalibrasyon-conformal-kararlari.md) (all Turkish).

## 1. Question and information time

Prediction time T is **2 hours before scheduled departure** (operational model, contract `T2`). A second contract, `plan`, uses only
the schedule and history (no weather) because a block-time buffer is decided months before the day. Plan versus baseline measures what
machine learning adds from schedule and history; T2 versus plan measures what weather 2 hours ahead adds. Weather cut-off:
scheduled departure - 2 h - 10 min (10 min is an assumed METAR publication tolerance), last observation not older than 3 h, same cut-off
for origin and destination.

## 2. Data layer

- BTS On-Time files month by month into Parquet, one file per table and month. Tables: `flights` (schedule, UTC, flags; no outcome),
  `flight_labels` (outcomes, physically separate, never given to feature code), `scheduled_density` (scheduled movements per airport and hour,
  computed from all BTS flights before the 30-airport filter), `metar`, weather joins (`weather_t120m`, and a separate `weather_oracle`
  used only by the diagnostic experiment). Schema: [`data/LAYER_SCHEMA.md`](../data/LAYER_SCHEMA.md).
- Local scheduled times converted to UTC (arrival = candidate day within 24 h after departure); daylight-saving ambiguities and gaps are flagged, not guessed.
  Actual UTC times are built as scheduled UTC + delay minutes.
- No row is dropped except by the scope filter (origin in the 30 airports) and a missing-key drop (rows missing a key field; 1 row in the quality report, 2024-08).
- Quality report: [`data/quality-report.md`](../data/quality-report.md): overall WARNING, no critical finding.

## 3. Split and information discipline

Time-ordered, by scheduled local flight date (table in the [model card](model-card.md#data)). Final models are fitted on the training window only (no refit on
validation). A rolling-origin backtest inside the training window (folds K3: eval 2025-03..05, K4: eval 2025-06..08) was used for the hyperparameter search
and the rehearsal. Hyperparameters were searched by random search on those folds; the same parameters were reused for the plan-contract models.

## 4. Leakage controls

- **Feature contract:** every model input is declared with its information time (schedule, history from the fit window, weather before cut-off). Banned: actual
  times, delay minutes, delay-cause minutes, cancellation/diversion codes, derived targets, `DepTimeBlk` / `ArrTimeBlk`. The contract validates the declaration, not the computation,
  therefore row-level tests also exist (every weather observation not later than the cut-off; history tables only from the fit window; the transform step never reads labels).
- **Target encodings:** for evaluation sets computed from the whole fit window; for fit rows out-of-fold with 5 consecutive time blocks (no shuffling).
- **No look at the test:** development loaders filter rows after 2026-02-28 (tested); the final-test script refuses to run without a freeze manifest and writes a lock record on its
  first run (git commit, run IDs, contract digests, calibrator keys). A second run is refused.
- **Review of locked models (permutation + time-travel):** `no_suspicion` for the ArrDel15 T-2h model and its quantile models
  ([`importance-ozet.md`](../../experiments/models/run-20261121T082853Z/permutation/perm-20261122T072248Z/importance-ozet.md)) and for the T-2h cancellation model
  ([`importance-ozet.md`](../../experiments/models/run-20261120T174502Z/permutation/perm-20261120T192352Z/importance-ozet.md)). Both use a 26-day Val-B sample; the
  reported standard deviation is permutation noise only, not sampling uncertainty. The largest permutation effects for the ArrDel15 model were origin temperature, origin airport,
  scheduled departures at the origin that day, the reporting carrier and the minute of day.
- **Sanity rule:** the plan required that a T-2h result suspiciously close to the oracle (observed-weather) upper bound, or an unexpectedly large plan-to-T-2h gain, be investigated before reporting. No oracle model was locked and the oracle is not part of any reported result.

## 5. Models

LightGBM binary for ArrDel15 and cancellation; LightGBM quantile for arrival delay at 0.10 / 0.50 / 0.80 / 0.90 / 0.95 (quantiles of one flight are sorted
to avoid crossing; the crossing rate before sorting was recorded). No class weighting, so that probabilities stay calibrated. A logistic regression
and B0 / B1 baselines are fitted with the same code and splits.

## 6. Calibration and conformal bounds

- **Probabilities:** Platt scaling. Primary: monthly-rolling fit on the window [m - 57 d, m - 2 d] for month m (assumes labels known after 1 day). Secondary: static Platt and isotonic, both fitted once on Val-B.
  Ranking metrics (ROC-AUC, PR-AUC) are computed on raw scores.
- **Upper bounds P80 / P95:** one-sided split conformal on the nonconformity score y - q(x), with the same rolling window; static (one Val-B offset) and a "public" variant (windows lagged by 2 months, assumes BTS publication lag)
  are secondary. If a window has too few points the offset is infinite and flagged, never clipped. The 80% interval uses CQR on the 0.10 / 0.90 models.
- B1 passes through the same calibration and conformal steps.

## 7. Statistics

Day-block bootstrap (resample test days with replacement, keep all flights of a day), paired (two models on the same resample), B = 1000, seed 42, 95% percentile intervals,
two-sided p = 2 min(share(D* <= 0), share(D* >= 0)). Holm over 7 primary comparisons. Reading starts from the interval of the difference.

## 8. Acceptance criteria and rehearsal

K1-K7 are defined in [`model-card.md`](model-card.md#evaluation-results). K3 and K5 tolerances were set by a rule written before the numbers: the larger of the plan value and the
bootstrap half-width of the rehearsal, rounded up to 0.005; the outcome equalled the plan values. A rehearsal on the training window (2025-03..08) exercised the whole evaluation code
path and exposed a seasonal calibration shift; its performance numbers are optimistic (parameters were searched on those folds) and are **not results**. In that rehearsal K1 and K2 passed;
K3, K4 (P95), K5 (summer segments), K6 and K7 did not (K7 for procedural reasons, fixed by adding the leakage reviews to the lock).

## Deviations and process weaknesses

1. **Isotonic to Platt (decided before seeing the test).** The plan said isotonic; Platt was chosen for fewer parameters and lower variance under winter-to-summer drift. Isotonic is reported as secondary.
2. **Rolling Platt as primary (decided after the rehearsal, before the test).** The pre-registration had static Platt as primary. In the rehearsal the static fit drifted across the season (pooled CITL -0.015) while the rolling fit corrected it (-0.004).
   Evidence came from development data, not the test. On the test, static Platt would not have met the K3 tolerance (CITL -0.0163).
3. **Cancellation model without calendar features (user decision on Val-A evidence).** The diagnostic rule written before the experiment (a minimum best-round criterion) was not met; the calendar-free model was chosen anyway because validation log-loss, AUC and AP all improved clearly
   on Val-A. The calendar-including cancellation model is reported as a secondary sensitivity. For ArrDel15 and quantiles a pre-written Val-A rule decided; the T-2h ArrDel15 model dropped the calendar features.
4. **Val-B used for several purposes** (F1 threshold, calibrators, first conformal window, permutation review, the calendar hypothesis). Val-B numbers are therefore not headline numbers; the headline is the final-test table only.
5. **K7 is partly a declaration.** The final-test script cannot run the test suite; the pass of the leakage tests is declared in the lock record.
6. **Some earlier training runs were recorded with uncommitted changes** (red-team review of 2026-11-21); the final-test evaluation ran on a clean commit (`25ebfb622117`), and the lock lists run ID, model digest, best iteration, contract digest, dropped features and calibrator key per target.

## Open verification

The label-lag assumption (about 2 months for public BTS data), the timing of cancellation decisions, the operating conditions of October-November 2025 in the early-stopping window (government shutdown and FAA reductions are suspected, **not verified**), and a July-2024 IT outage in the training
window (not verified) are not checked against external sources.
