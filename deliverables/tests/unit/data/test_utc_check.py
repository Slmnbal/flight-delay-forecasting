"""utc_check tests (offline, tiny data)."""

import pandas as pd

from flight_delay.data import utc_check

NY, LA = "America/New_York", "America/Los_Angeles"


def test_utc_check_summary():
    df = pd.DataFrame(
        {
            "FlightDate": ["2024-07-15", "2024-07-15"],
            "Origin": ["JFK", "LAX"],
            "Dest": ["LAX", "JFK"],
            "CRSDepTime": [1000, 2300],
            "CRSArrTime": [1300, 700],
            "CRSElapsedTime": [360, 300],
        }
    )
    report = utc_check.utc_check(df, {"JFK": NY, "LAX": LA})
    assert report["rows"] == 2 and report["tz_missing_origin_rows"] == 0
    assert report["crs_duration_abs_diff_min"]["max"] == 0.0  # 14:00Z->20:00Z = 360 min; 06:00Z->11:00Z = 300 min
    assert report["arr_day_offset_distribution"] == {"0": 1, "1": 1}
