"""Block-time buffer optimisation (OR extension; formulation: ``experiments/or-tampon-formulasyonu.md``).

Modules:
- ``newsvendor``: quantile-grid interpolation, critical ratio, single-cell buffer, realised outcomes (pure, no I/O).
- ``allocation``: network budget versions (common-level KKT solution for delay minutes, multiple-choice knapsack for
  ArrDel15 counts) (pure, no I/O).
- ``policies``: cell keys (route x hour block x season), cell aggregation, rolling conformal offsets per level,
  policy buffers, development-only selection guard, output tables without any carrier column (pure, no I/O).
- ``evaluation``: out-of-sample realised metrics and the calendar-day block bootstrap (reuses
  ``flight_delay.modeling.bootstrap``) (pure, no I/O).
- ``run_buffer``: CLI; loads the locked plan models, predicts, evaluates, writes outputs (never overwrites).
"""
