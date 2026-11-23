# Model card: flight delay risk models (T-2h and schedule-only)

> Based on public data; not affiliated with any airline.

Structure follows Mitchell et al., "Model Cards for Model Reporting" (2019). Status 2026-11-22. All numbers come from the
one-shot final test (2026-03..08) unless labelled otherwise: [`son-test-ozet.md`](../../experiments/son-test/son-test-20261122T105048Z/son-test-ozet.md)
(Turkish) and `son-test-sonuclari.json` in the same folder. Abbreviations: ArrDel15 = arrival delay of 15 minutes or more;
ROC-AUC / PR-AUC = areas under the ROC / precision-recall curves; BSS = Brier skill score; CITL = calibration-in-the-large
(mean predicted probability minus observed rate); CQR = conformalized quantile regression; B1 = baseline (below).

## Model details

- **Developed by:** Slmnbal. **Version:** final models locked 2026-11-22 (freeze manifest `experiments/son-test-dondurma.json`).
  **License:** code under the MIT License (repository `LICENSE`).
- **Model family:** gradient-boosted trees (LightGBM 4.7.0).
  - ArrDel15: binary classifier. Cancellation: binary classifier.
  - Arrival delay (minutes): quantile models at levels 0.10, 0.50, 0.80, 0.90, 0.95 (the 0.10 / 0.90 pair is for the two-sided 80% interval).
  - Post-processing: Platt (logistic) recalibration of probabilities; split-conformal upper bounds for P80 / P95; CQR for the 80% interval.
- **Information contracts (when the prediction is made):**
  - `plan`: schedule and history statistics from the training window, no weather. Models the situation of a planner months ahead. Used for the delay quantiles in the OR part and for the cancellation model.
  - `T2` (operational): `plan` inputs plus METAR observations of origin and destination airports with cut-off = scheduled departure - 2 h - 10 min (look-back at most 3 h).
  - An "oracle" weather experiment (observed weather at departure/arrival) is a diagnostic upper bound only and is **not** part of the results.
- **Baselines.** B0: overall training rate / quantile. **B1 (reference for all acceptance criteria):** historical rate or quantile per
  route x departure-hour block from the training window, with hierarchical back-off (route-hour -> origin-hour -> origin -> overall;
  for quantiles at least 20 observations in the tail). B1 represents "what a planner would do by looking at history".
- **Inputs (high level):** scheduled times, scheduled block time, distance, origin, reporting carrier, day of week, scheduled traffic
  density at origin/destination, historical statistics (out-of-fold target encodings of route x hour etc.), METAR variables for `T2`.
  Calendar features (month, day of year, day of month, days to holiday, holiday week) were **removed** from the final models by a
  pre-registered rule on the validation period; the final-test roles used calendar-free models (a calendar-including cancellation model is reported as a secondary sensitivity).
  Not used: tail number, flight number, any post-departure field, BTS delay-cause minutes.
- **Citation / contact:** none yet.

## Intended use

- Demonstration of an honest, leakage-controlled delay-risk forecasting and schedule-buffer analysis on public data (portfolio / research).
- Exploring how much information is in the schedule, in history, and in weather 2 hours before departure.
- Intended users: data scientists, OR practitioners, reviewers of this work.

## Out-of-scope use

- Operational decisions (crew, gates, rebooking, dispatch) or any safety-related use. No validation against airline operations.
- Ranking, scoring or comparing airlines. No carrier-level results are produced or published; do not derive them.
- Early-warning of cancellations: BTS does not give the time a cancellation was decided, so a flight may already have been known as cancelled at T-2h.
- Airports outside the 30 origins, non-US flights, periods outside 2023-09..2026-08 (COVID years are not covered), non-reporting carriers.
- Reading OR costs as money, or the large buffers at high critical ratios as achievable improvements (they rest on assumption A1).

## Data

- **Source:** US DOT / BTS Reporting Carrier On-Time Performance (scheduled domestic flights of reporting carriers). Weather: Iowa
  Environmental Mesonet METAR archive. Airport coordinates: OurAirports. Licenses and status: see the [README](../../README.md#data-sources-and-licenses).
- **Scope:** flights whose **origin** is one of 30 airports (ORD, DEN, DFW, ATL, LAX, SEA, CLT, LAS, PHX, MCO, SFO, BOS, DCA, LGA, DTW, MSP,
  EWR, SLC, IAH, BNA, JFK, MIA, PHL, BWI, SAN, AUS, MDW, FLL, TPA, DAL), 2023-09-01 to 2026-08-31 (36 months, 13,691,239 rows; sum of the monthly row counts
  in [`quality-report.md`](../data/quality-report.md)). Cancelled and diverted flights stay in the table.
- **Splits (by scheduled local flight date):**

  | Set | Period | Rows | Use |
  |---|---|---|---|
  | Train | 2023-09..2025-08 | 9,127,110 | fit, history statistics |
  | Val-A | 2025-09..2025-12 | 1,506,008 | early stopping, feature decisions |
  | Val-B | 2026-01..2026-02 | 689,119 | calibration, thresholds, first conformal window |
  | Final test | 2026-03..2026-08 | 2,369,002 scheduled (2,315,618 completed; 44,597 cancelled; 8,787 diverted) | one-shot evaluation |

  (Row counts for train / Val-A / Val-B are sums of the monthly counts in the quality report; test counts are from the OR summary.)
- **Targets:** ArrDel15 and arrival delay (minutes, completed flights only: not cancelled, not diverted); cancellation (all scheduled flights).
  Test ArrDel15 prevalence: 0.2626.
- **Quality:** the data quality report status is WARNING with 0 critical findings; every warning concerns at most 0.023% of the rows of a month
  (e.g. local clock reading of actual times differs from BTS time). Missing-value ratios and checks: [`quality-report.md`](../data/quality-report.md).
  Time conversion to UTC: schema in [`LAYER_SCHEMA.md`](../data/LAYER_SCHEMA.md).
- **Preprocessing:** local scheduled times to UTC (DST cases flagged), METAR matched as last observation not newer than the cut-off.
  Historical statistics are computed only from the fit window (out-of-fold for training rows).

## Metrics

- **Classification:** ROC-AUC and PR-AUC (computed on raw scores, with prevalence reported), Brier score and BSS against B1, log-loss, ECE (expected
  calibration error, 10 equal-frequency bins), CITL and calibration slope. F1 at a frozen threshold is secondary.
- **Quantiles:** pinball loss (minutes) per level; coverage of raw and conformal upper bounds; coverage and width of the 80% interval.
- **Uncertainty:** paired day-block bootstrap (resample the 184 test days; B = 1000, seed 42), 95% percentile intervals; Holm correction (alpha = 0.05)
  over 7 pre-specified primary comparisons.
- **Acceptance criteria K1-K7** were fixed before the test (see below). Presentation of results starts from the interval of the difference, not from p-values.

## Evaluation results

### Acceptance criteria (pre-registered; outcome as obtained)

| Criterion | Result | What it required | Observed |
|---|---|---|---|
| K1 | passed | T-2h model beats B1 in ROC-AUC and PR-AUC, lower CI bound > 0, Holm-significant | +0.0556 / +0.1013 (CIs above 0) |
| K2 | passed | BSS vs B1 > 0, lower CI bound > 0 (monthly-rolling Platt) | +0.0625 [+0.0541; +0.0712] |
| K3 | passed | abs(CITL) <= 0.01 and slope in [0.9; 1.1] (monthly-rolling Platt) | CITL -0.0025, slope 1.002 |
| K4 | passed | plan quantiles beat B1 at 0.50 / 0.80 / 0.95: pinball difference < 0, CI upper bound < 0, Holm-significant | -0.2315 / -0.2168 / -0.1066 |
| K5 | **failed** | rolling-conformal P80 coverage in [0.78; 0.82], P95 in [0.94; 0.96], and >= 80% of Origin x month segments (n >= 500) within +/-0.05 of target | P80 0.7877, P95 0.9447 (inside); segment share P80 **0.6889** (fails), P95 0.9778 |
| K6 | **failed** | cancellation (plan) PR-AUC above B1, CI lower bound > 0 | -0.0005 [-0.0048; +0.0039] |
| K7 | passed | leakage test suite passed (a declaration made at lock time) and no unresolved suspicion in the locked models | see methodology |

K3 tolerances came out of the rehearsal rule (max of plan value and rounded-up bootstrap half-width) and equalled the plan values.
**Honesty note on K3:** the pre-registered primary calibration was a static Platt fit on Val-B; it was replaced by monthly-rolling Platt after the
rehearsal and before the test. The static Platt would have given CITL -0.0163 (slope 1.016), which would **not** have met the 0.01 tolerance.

### Primary family (Holm, alpha = 0.05)

| # | Comparison | Difference vs B1 [95% CI] | Significant |
|---|---|---|---|
| 1 | ArrDel15 ROC-AUC (T-2h) | +0.0556 [+0.0499; +0.0612] | yes |
| 2 | ArrDel15 PR-AUC (T-2h) | +0.1013 [+0.0915; +0.1105] | yes |
| 3 | ArrDel15 BSS (T-2h) | +0.0625 [+0.0541; +0.0712] | yes |
| 4 | pinball P50 (plan) | -0.2315 [-0.2586; -0.2016] | yes |
| 5 | pinball P80 (plan) | -0.2168 [-0.2704; -0.1637] | yes |
| 6 | pinball P95 (plan) | -0.1066 [-0.1422; -0.0713] | yes |
| 7 | cancellation PR-AUC (plan) | -0.0005 [-0.0048; +0.0039] | no |

### ArrDel15, T-2h model: probability quality (test; B1 treated with the same method for BSS)

| Method | Brier | BSS | Log-loss | ECE | CITL | Slope |
|---|---|---|---|---|---|---|
| raw | 0.1723 | 0.0671 | 0.5215 | 0.0302 | -0.0302 | 0.940 |
| static Platt (fit once on Val-B) | 0.1716 | 0.0834 | 0.5192 | 0.0165 | -0.0163 | 1.016 |
| isotonic (fit on Val-B) | 0.1716 | 0.0839 | 0.5193 | 0.0161 | -0.0161 | 1.013 |
| **monthly-rolling Platt (primary)** | 0.1716 | 0.0625 | 0.5193 | 0.0052 | -0.0025 | 1.002 |

ROC-AUC (raw) 0.7120, PR-AUC (raw) 0.4767, prevalence 0.2626. Exploratory: AUC computed within origin-day strata 0.6930 (model) vs 0.6634 (B1).
BSS values differ by method because B1 is recalibrated with the same method each time.

Monthly view (test): prevalence 0.2139 (Apr) to 0.3089 (Jul); CITL of the rolling Platt ranges from -0.0401 (Mar) to +0.0202 (Apr); raw ROC-AUC 0.6940 (May) to 0.7284 (Aug).

### Where the gain comes from (secondary, same flights)

- ArrDel15 ROC-AUC: schedule + history model (weather-free, matched calendar setting) vs B1 **+0.0193** [+0.0152; +0.0234]; PR-AUC +0.0302 [+0.0234; +0.0365]; BSS +0.0172 [+0.0130; +0.0213].
- Weather at T-2h on top of that (T-2h minus plan): ROC-AUC **+0.0363** [+0.0315; +0.0410]; PR-AUC +0.0711 [+0.0618; +0.0800]; Brier (Platt) -0.0083 [-0.0098; -0.0069]; P80 pinball -0.7560 [-0.9017; -0.6163] min.
- No oracle model was locked, so a "share of the upper bound captured" is not reported.

### Conformal coverage of the plan quantiles (test)

| Scheme | P80 coverage | P95 coverage | Segment share P80 | Segment share P95 | 80% interval (CQR) coverage |
|---|---|---|---|---|---|
| raw (no adjustment) | 0.7698 | 0.9373 | - | - | - |
| rolling (primary) | 0.7877 | 0.9447 | 0.6889 | 0.9778 | 0.7956 |
| static (one offset from Val-B) | 0.7792 | 0.9415 | 0.6389 | 0.9667 | 0.7923 |
| "public" (windows lagged 2 months; secondary) | 0.7866 | 0.9448 | 0.5778 | 0.9556 | 0.7949 |

Monthly P80 coverage with the rolling scheme: Mar 0.7758, Apr 0.8314, May 0.8090, Jun 0.7547, Jul 0.7560, Aug 0.7994 (target 0.80). The model under-covers in the early summer months.

### Other secondary results (B1 comparison, exploratory, outside the Holm family)

- Cancellation with T-2h weather: ROC-AUC +0.1043 [+0.0843; +0.1211], PR-AUC +0.0898 [+0.0619; +0.1182]. Caution: cancellation decision times are unknown (some may already be known at T-2h), so this is **not** an early-warning claim.
- Delay quantiles with T-2h weather vs B1: pinball P50 -0.6386, P80 -0.9728, P95 -0.6279 min.
- Locked model checks (Val-B, 26-day sample, permutation + time-travel): no suspicion for the ArrDel15 and quantile models and for the cancellation model.

## Ethical considerations and presentation rules

- **Public data only; no personal data.** Flight-level records are public BTS data; tail numbers and flight numbers are never published; local-only keys stay local.
- **No airline ranking.** Airline names may appear in descriptions, but there are no rankings, no logos, no carrier-level performance tables or charts.
  Delay-cause fields are carrier self-reports; they are not used as features and not presented as causes of any carrier's delays.
- **Carrier as an input.** The reporting carrier is a model input. Its permutation importance is reported only as a single number; no carrier-level breakdown or dependence plot is produced.
- **Single-carrier cells.** A route x hour-block x season cell in which one carrier has more than 90% of scheduled flights effectively describes that carrier. In the test period
  16,882 of 24,765 cells were flagged this way; buffer suggestions are published only for the 7,094 cells with n >= 50 flights that are not flagged. Flagged and small cells are not published.
- **Disclaimer:** "Based on public data; not affiliated with any airline."
- **Risks:** misreading probabilities as certainties; using delay estimates to blame operators; treating assumed OR costs as facts.

## Caveats and limitations

1. **Failed criteria.** Coverage by airport-month (K5) is not reliable enough, especially in June-July; cancellation risk shows no gain over B1 (K6).
2. **Label lag.** Rolling recalibration and conformal windows ([m - 57 d, m - 2 d] for month m) assume labels are known after about 1 day. Public BTS data arrive about 2 months late (assumption, not verified); the 2-month "public" scenario is secondary and its segment coverage is worse.
3. **Season drift.** Calibration and offsets are fitted in winter (Val-B), the test is spring-summer. Raw probabilities under-predict (CITL -0.0302). Models were trained once on data up to 2025-08 (6-12 months stale at test).
4. **Conditioning.** Delay quantiles are conditional on completion; the worst days (cancellation waves) are under-represented. Cancellation timing is unknown.
5. **Coverage of the data.** Only reporting carriers' scheduled domestic flights from 30 origin airports; BTS reporting carrier set changed over time. No aircraft rotation, crew, ground-delay programs or network effects. METAR observations only (no forecasts).
6. **Schedule excess.** The scheduled block time (`schedule_excess_min`, relative to history) is an input; an earlier review found that it accounts for most of the P50 skill (about 95%, derived before the final models). Therefore the model's sensitivity to it must not be read causally (the OR part does not re-predict after adding buffer).
7. **Process caveats.** The validation sets were used for several purposes (early stopping, thresholds, calibration, conformal window, permutation reviews, a calendar-feature hypothesis); calendar features were dropped on Val-A evidence, and the cancellation model deviated from a pre-written rule by a user decision. Details in [`methodology.md`](methodology.md#deviations-and-process-weaknesses). K7 partly rests on a declaration that the leakage tests passed.
8. **Statistics.** 184 test days limit the effective sample size for monthly and segment statements; monthly tables are exploratory. Many comparisons beyond the primary family are exploratory and not multiplicity-corrected.
9. **Not validated** against any airline internal system; no such comparison is claimed.

## Reproducibility

Seed 42; deterministic LightGBM; versions in the README; final test run on git commit `25ebfb622117` with a clean working tree; lock record sha256 `fee816c25ddf...` (prefix as printed in the result summary).
Run IDs: ArrDel15 T-2h `run-20261121T082853Z` (best iteration 1409), plan models `run-20261121T080035Z`, cancellation (T-2h) `run-20261120T174502Z`.
