"""Fixtures for the data-layer tests: a tiny FAKE BTS On-Time dataset (not real data; no network).

This file holds fixtures only. The package is imported normally (``pip install -e deliverables[dev]``);
no sys.path manipulation is needed.

Fake flights (2025-07; summer time: ORD/CDT=-5, ATL/EDT=-4, LAX/PDT=-7):
  r1 ORD->ATL 07-01 CRS 0900 -> 1210 (UTC 14:00 -> 16:10, 130 min), actual 0915/1230
  r2 ATL->ORD 07-01 CRS 2300 -> 0035 next day (UTC 07-02 03:00 -> 05:35, 155 min), actual 2350/0125
  r3 ORD->LAX 07-02 CANCELLED, CRS 1500 -> 1745 (UTC 20:00 -> 00:45 next day, 285 min)
  r4 LAX->ATL 07-02 (only Dest is a target)
  r5 LAX->XYZ 07-02 (neither is a target)
  r6 ORD->ZZZ 07-03 (ZZZ time zone unknown)
Which airports are targets is given per test (default ["ORD", "ATL"]).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from flight_delay.data import layer

MANUAL_TZ = {
    "ORD": "America/Chicago",
    "ATL": "America/New_York",
    "LAX": "America/Los_Angeles",
    "XYZ": "America/Chicago",
}  # ZZZ is deliberately missing

TARGETS = ["ORD", "ATL"]


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "Year": 2025,
        "Quarter": 3,
        "Month": 7,
        "DayofMonth": 1,
        "DayOfWeek": 2,
        "FlightDate": "2025-07-01",
        "Reporting_Airline": "AA",
        "OriginCityName": "Some City",
        "Flight_Number_Reporting_Airline": 100,
        "Tail_Number": "N100AA",
        "OriginAirportID": 1,
        "Origin": "ORD",
        "DestAirportID": 2,
        "Dest": "ATL",
        "CRSDepTime": 900,
        "DepTime": 915,
        "DepDelay": 15.0,
        "DepDelayMinutes": 15.0,
        "DepDel15": 1.0,
        "TaxiOut": 12.0,
        "WheelsOff": 927.0,
        "WheelsOn": 1220.0,
        "TaxiIn": 10.0,
        "CRSArrTime": 1210,
        "ArrTime": 1230.0,
        "ArrDelay": 20.0,
        "ArrDelayMinutes": 20.0,
        "ArrDel15": 1.0,
        "Cancelled": 0.0,
        "CancellationCode": np.nan,
        "Diverted": 0.0,
        "CRSElapsedTime": 130.0,
        "ActualElapsedTime": 135.0,
        "AirTime": 113.0,
        "Distance": 606.0,
        "DistanceGroup": 3,
        "CarrierDelay": 20.0,
        "WeatherDelay": 0.0,
        "NASDelay": 0.0,
        "SecurityDelay": 0.0,
        "LateAircraftDelay": 0.0,
    }
    base.update(overrides)
    return base


_NO_CAUSES = {
    "CarrierDelay": np.nan,
    "WeatherDelay": np.nan,
    "NASDelay": np.nan,
    "SecurityDelay": np.nan,
    "LateAircraftDelay": np.nan,
}


def build_fake_frame() -> pd.DataFrame:
    r1 = _row()
    r2 = _row(
        Origin="ATL",
        Dest="ORD",
        Reporting_Airline="UA",
        Flight_Number_Reporting_Airline=200,
        Tail_Number="N200UA",
        CRSDepTime=2300,
        DepTime=2350.0,
        DepDelay=50.0,
        DepDelayMinutes=50.0,
        CRSArrTime=35,
        ArrTime=125.0,
        ArrDelay=50.0,
        ArrDelayMinutes=50.0,
        CRSElapsedTime=155.0,
        ActualElapsedTime=155.0,
        CarrierDelay=50.0,
    )
    r3 = _row(
        FlightDate="2025-07-02",
        DayofMonth=2,
        DayOfWeek=3,
        Origin="ORD",
        Dest="LAX",
        Reporting_Airline="DL",
        Flight_Number_Reporting_Airline=300,
        Tail_Number="N300DL",
        CRSDepTime=1500,
        DepTime=np.nan,
        DepDelay=np.nan,
        DepDelayMinutes=np.nan,
        DepDel15=np.nan,
        TaxiOut=np.nan,
        WheelsOff=np.nan,
        WheelsOn=np.nan,
        TaxiIn=np.nan,
        CRSArrTime=1745,
        ArrTime=np.nan,
        ArrDelay=np.nan,
        ArrDelayMinutes=np.nan,
        ArrDel15=np.nan,
        Cancelled=1.0,
        CancellationCode="B",
        CRSElapsedTime=285.0,
        ActualElapsedTime=np.nan,
        AirTime=np.nan,
        Distance=1744.0,
        DistanceGroup=7,
        **_NO_CAUSES,
    )
    r4 = _row(
        FlightDate="2025-07-02",
        DayofMonth=2,
        DayOfWeek=3,
        Origin="LAX",
        Dest="ATL",
        Reporting_Airline="WN",
        Flight_Number_Reporting_Airline=400,
        Tail_Number="N400WN",
        CRSDepTime=600,
        DepTime=600.0,
        DepDelay=0.0,
        DepDelayMinutes=0.0,
        DepDel15=0.0,
        CRSArrTime=1400,
        ArrTime=1355.0,
        ArrDelay=-5.0,
        ArrDelayMinutes=0.0,
        ArrDel15=0.0,
        CRSElapsedTime=300.0,
        ActualElapsedTime=295.0,
        Distance=1947.0,
        DistanceGroup=8,
        **_NO_CAUSES,
    )
    r5 = _row(
        FlightDate="2025-07-02",
        DayofMonth=2,
        DayOfWeek=3,
        Origin="LAX",
        Dest="XYZ",
        Reporting_Airline="WN",
        Flight_Number_Reporting_Airline=500,
        Tail_Number="N500WN",
        CRSDepTime=700,
        DepTime=700.0,
        DepDelay=0.0,
        DepDelayMinutes=0.0,
        DepDel15=0.0,
        CRSArrTime=1100,
        ArrTime=1100.0,
        ArrDelay=0.0,
        ArrDelayMinutes=0.0,
        ArrDel15=0.0,
        CRSElapsedTime=120.0,
        ActualElapsedTime=120.0,
        **_NO_CAUSES,
    )
    r6 = _row(
        FlightDate="2025-07-03",
        DayofMonth=3,
        DayOfWeek=4,
        Origin="ORD",
        Dest="ZZZ",
        Flight_Number_Reporting_Airline=600,
        Tail_Number="N600AA",
        CRSDepTime=1000,
        DepTime=1000.0,
        DepDelay=0.0,
        DepDelayMinutes=0.0,
        DepDel15=0.0,
        CRSArrTime=1200,
        ArrTime=1200.0,
        ArrDelay=0.0,
        ArrDelayMinutes=0.0,
        ArrDel15=0.0,
        CRSElapsedTime=120.0,
        ActualElapsedTime=120.0,
        **_NO_CAUSES,
    )
    return pd.DataFrame([r1, r2, r3, r4, r5, r6])


@pytest.fixture
def manual_tz() -> dict[str, str]:
    """Manual time-zone overrides for the fake airports."""
    return dict(MANUAL_TZ)


@pytest.fixture
def empty_airports() -> pd.DataFrame:
    """An empty airport table: time zones come only from the manual overrides."""
    return pd.DataFrame(
        {
            "iata": pd.Series(dtype=str),
            "lat": pd.Series(dtype=float),
            "lon": pd.Series(dtype=float),
            "tz_field": pd.Series(dtype=object),
        }
    )


@pytest.fixture
def fake_ontime() -> pd.DataFrame:
    """A fresh fake On-Time DataFrame (6 flights) for each test."""
    return build_fake_frame()


@pytest.fixture
def write_ontime_csv() -> Callable[..., Path]:
    """Factory: write the fake data (or a given frame) as CSV; optionally upper-case the column names."""

    def write(path: Path, df: pd.DataFrame | None = None, upper_case_columns: bool = False) -> Path:
        frame = build_fake_frame() if df is None else df
        if upper_case_columns:
            frame = frame.rename(columns=lambda c: c.upper())
        frame.to_csv(path, index=False)
        return path

    return write


@pytest.fixture
def process_fake_month(
    write_ontime_csv: Callable[..., Path], empty_airports: pd.DataFrame, manual_tz: dict[str, str]
) -> Callable[..., tuple[Path, dict[str, Any]]]:
    """Factory: write the fake CSV and run layer.process_month; returns (layer_root, summary)."""

    def process(
        tmp_path: Path,
        scope: str = "origin",
        df: pd.DataFrame | None = None,
        name: str = "raw.csv",
        year: int = 2025,
        month: int = 7,
        **csv_options: Any,
    ) -> tuple[Path, dict[str, Any]]:
        csv = write_ontime_csv(tmp_path / name, df, **csv_options)
        root = tmp_path / "layer"
        summary = layer.process_month(csv, year, month, root, TARGETS, empty_airports, manual_tz, scope)
        return root, summary

    return process
