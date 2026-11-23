"""Fixed category lists (step-1 risk: category lists differ between months) on SYNTHETIC frames."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from flight_delay.modeling.categories import CategoryEncoder
from flight_delay.modeling.matrix import frame_to_array


def _frame(origins: list[str], carriers: list[str], *, categories: list[str] | None = None) -> pd.DataFrame:
    dates = pd.to_datetime(["2025-08-01"] * len(origins))
    origin = pd.Categorical(origins, categories=categories) if categories else pd.Categorical(origins)
    return pd.DataFrame({"FlightDate": dates, "Origin": origin, "Reporting_Airline": pd.Categorical(carriers)})


def test_lists_come_from_observed_fit_values_not_from_the_dtype():
    # the dtype knows ZZZ (e.g. from a Val-A month in the union), but no fit row has it
    fit = _frame(["ORD", "ATL", "ORD"], ["UA", "AA", "UA"], categories=["ZZZ", "ORD", "ATL"])
    encoder = CategoryEncoder().fit(fit, fit_end=dt.date(2025, 8, 31))
    assert encoder.categories == {"Origin": ["ATL", "ORD"], "Reporting_Airline": ["AA", "UA"]}


def test_codes_are_identical_across_months_with_different_category_dtypes():
    encoder = CategoryEncoder().fit(_frame(["ORD", "ATL", "DEN"], ["UA", "AA", "UA"]))
    month_1 = _frame(["DEN", "ORD"], ["UA", "UA"], categories=["DEN", "ORD"])
    month_2 = _frame(["ORD", "DEN", "ATL"], ["AA", "UA", "AA"], categories=["ATL", "BOS", "DEN", "ORD"])
    codes_1 = encoder.codes(month_1["Origin"], "Origin")
    codes_2 = encoder.codes(month_2["Origin"], "Origin")
    assert codes_1.tolist() == [1.0, 2.0]  # ATL = 0, DEN = 1, ORD = 2 (sorted fit list)
    assert codes_2.tolist() == [2.0, 1.0, 0.0]
    assert encoder.transform(month_2)["Origin"].cat.categories.tolist() == ["ATL", "DEN", "ORD"]


def test_unknown_and_missing_values_become_nan_and_are_reported():
    encoder = CategoryEncoder().fit(_frame(["ORD", "ATL"], ["UA", "AA"]))
    later = pd.DataFrame(
        {
            "Origin": pd.Categorical(["ORD", "SEA", None, "SEA"]),
            "Reporting_Airline": pd.Categorical(["UA", "UA", "UA", "XX"]),
        }
    )
    codes = encoder.codes(later["Origin"], "Origin")
    assert codes[0] == 1.0 and np.isnan(codes[1:]).all()
    report = encoder.unknown_report(later)
    assert report["Origin"]["unknown"] == 2 and report["Origin"]["missing"] == 1
    assert report["Origin"]["unknown_values"] == ["SEA"]
    assert report["Reporting_Airline"]["unknown"] == 1
    matrix = frame_to_array(later, ["Origin", "Reporting_Airline"], encoder)
    assert matrix.dtype == np.float32 and np.isnan(matrix[3, 1])


def test_fit_refuses_rows_after_fit_end_and_round_trips():
    frame = _frame(["ORD"], ["UA"])
    with pytest.raises(ValueError):
        CategoryEncoder().fit(frame, fit_end=dt.date(2025, 7, 31))
    encoder = CategoryEncoder(min_count=1).fit(frame, fit_end=dt.date(2025, 8, 31))
    restored = CategoryEncoder.from_dict(encoder.to_dict())
    assert restored.categories == encoder.categories
    assert restored.codes(pd.Series(["ORD", "SEA"]), "Origin").tolist()[0] == 0.0


def test_min_count_drops_rare_values_to_unknown():
    encoder = CategoryEncoder(min_count=2).fit(_frame(["ORD", "ORD", "ATL"], ["UA", "UA", "UA"]))
    assert encoder.categories["Origin"] == ["ORD"]
    assert np.isnan(encoder.codes(pd.Series(["ATL"]), "Origin")[0])
