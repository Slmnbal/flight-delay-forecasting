"""UTC quality check on real On-Time data (A3) -- CLI (NO NETWORK).

Usage:
  python -m flight_delay.data.utc_check --ontime deliverables/data/raw/ontime_2025_07.zip \\
      --ourairports deliverables/data/raw/airports.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from flight_delay.data.airports import build_tz_map, load_ourairports
from flight_delay.data.csv_io import column_selector, read_csv
from flight_delay.data.time_conversion import arrival_utc_series, local_to_utc_series
from flight_delay.paths import DATA_DIR

__all__ = ["main", "utc_check"]

DEFAULT_OUTPUT = DATA_DIR / "utc-check-result.json"


def utc_check(df: pd.DataFrame, tz_map: dict[str, str]) -> dict[str, Any]:
    """Produce CRS departure/arrival UTC and return consistency statistics.

    Check: how close is (UTC arrival - UTC departure) to BTS's CRSElapsedTime? Large deviations are a
    sign of a time zone / day rollover error (BTS itself can rarely be inconsistent; this is a
    measurement report, not a test threshold).
    """
    data = df.reset_index(drop=True).copy()
    data["_date"] = pd.to_datetime(data["FlightDate"])
    data["_tz_origin"] = data["Origin"].map(tz_map)
    data["_tz_dest"] = data["Dest"].map(tz_map)
    dep = local_to_utc_series(data["_date"], data["CRSDepTime"], data["_tz_origin"])
    arr = arrival_utc_series(data["_date"], data["CRSArrTime"], data["_tz_dest"], dep["utc"])
    duration_min = (arr["utc"] - dep["utc"]).dt.total_seconds() / 60
    report: dict[str, Any] = {
        "rows": int(len(data)),
        "tz_missing_origin_rows": int(data["_tz_origin"].isna().sum()),
        "tz_missing_dest_rows": int(data["_tz_dest"].isna().sum()),
        "tz_missing_airports": sorted(
            set(data.loc[data["_tz_origin"].isna(), "Origin"].dropna().astype(str))
            | set(data.loc[data["_tz_dest"].isna(), "Dest"].dropna().astype(str))
        ),
        "crs_dep_invalid": int(dep["invalid"].sum()),
        "crs_arr_invalid": int(arr["invalid"].sum()),
        "dep_ambiguous_dst_fall_back": int(dep["ambiguous"].sum()),
        "dep_gap_dst_spring_forward": int(dep["gap"].sum()),
        "arr_ambiguous_dst_fall_back": int(arr["ambiguous"].sum()),
        "arr_gap_dst_spring_forward": int(arr["gap"].sum()),
        "arr_inconsistent_window": int(arr["inconsistent"].sum()),
        "crs_arr_2400_rows": int((pd.to_numeric(data["CRSArrTime"], errors="coerce") == 2400).sum()),
        "crs_dep_2400_rows": int((pd.to_numeric(data["CRSDepTime"], errors="coerce") == 2400).sum()),
        "arr_day_offset_distribution": {
            str(int(k)): int(v) for k, v in arr["day_offset"].dropna().value_counts().sort_index().items()
        },
    }
    if "CRSElapsedTime" in data.columns:
        diff = (duration_min - pd.to_numeric(data["CRSElapsedTime"], errors="coerce")).abs().dropna()
        if len(diff):
            report["crs_duration_abs_diff_min"] = {
                "n": int(len(diff)),
                "median": round(float(diff.median()), 2),
                "p95": round(float(diff.quantile(0.95)), 2),
                "p99": round(float(diff.quantile(0.99)), 2),
                "max": round(float(diff.max()), 2),
                "share_diff_0": round(float((diff == 0).mean()), 4),
                "share_diff_gt_60min": round(float((diff > 60).mean()), 4),
            }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local -> UTC conversion quality check for CRS times (no network).")
    parser.add_argument("--ontime", type=Path, required=True, help="On-Time csv/zip.")
    parser.add_argument(
        "--ourairports", type=Path, required=True, help="OurAirports airports.csv (downloaded by hand)."
    )
    parser.add_argument("--tz-overrides", type=Path, default=None, help='JSON {"IATA": "IANA/Name"} corrections.')
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--nrows", type=int, default=None)
    args = parser.parse_args(argv)

    df = read_csv(
        args.ontime,
        usecols=column_selector(["FlightDate", "Origin", "Dest", "CRSDepTime", "CRSArrTime", "CRSElapsedTime"]),
        nrows=args.nrows,
    )
    airports = load_ourairports(args.ourairports)
    overrides = json.loads(args.tz_overrides.read_text(encoding="utf-8")) if args.tz_overrides else None
    used = sorted(set(df["Origin"].dropna().astype(str)) | set(df["Dest"].dropna().astype(str)))
    tz_map, missing = build_tz_map(airports, used, overrides)
    report = utc_check(df, tz_map)
    report["tz_map_missing"] = missing
    report["tz_map_size"] = len(tz_map)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
