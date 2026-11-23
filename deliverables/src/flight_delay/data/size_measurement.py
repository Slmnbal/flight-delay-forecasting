"""Size measurement of a downloaded single-month On-Time file (NO NETWORK).

Measures (to verify assumption A2):
  - row / column counts
  - memory use: pandas memory_usage(deep=True)
  - on-disk size when written to Parquet (zstd, pyarrow)
  - column types and missing-value ratios
  - the busiest departure airports and their share of all rows (for the scope decision)
Two views are measured:
  "all_columns": every column in the file (raw, read as-is)
  "subset"     : model subset (feature_contract.MEASUREMENT_SUBSET) with object columns converted to
                 'category' and FlightDate converted to a date (optimised view)

Result: deliverables/data/size-measurement.json. No number is written in this file; all are measured at
run time. Measurements depend on hardware / pandas version (versions are under "meta" in the JSON).

Usage:
  python -m flight_delay.data.size_measurement --input deliverables/data/raw/<file>.csv
  (a zip works too; it must contain a single csv)
"""

from __future__ import annotations

import argparse
import json
import platform
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd

from flight_delay.data.csv_io import read_csv
from flight_delay.data.feature_contract import MEASUREMENT_SUBSET
from flight_delay.paths import DATA_DIR

__all__ = ["DEFAULT_OUTPUT", "main", "measure", "memory_mb"]

DEFAULT_OUTPUT = DATA_DIR / "size-measurement.json"
MB = 1024**2


def _optimized_view(df: pd.DataFrame) -> pd.DataFrame:
    """Optimised view: low-cardinality object -> category; FlightDate -> datetime."""
    view = df.copy()
    for column in view.columns:
        if column.lower() == "flightdate":
            view[column] = pd.to_datetime(view[column], errors="coerce")
        elif view[column].dtype == object and len(view) > 0 and view[column].nunique(dropna=True) / len(view) < 0.5:
            view[column] = view[column].astype("category")
    return view


def memory_mb(df: pd.DataFrame) -> float:
    """Deep memory use in MB."""
    return int(df.memory_usage(deep=True, index=True).sum()) / MB


def _measure_frame(df: pd.DataFrame, parquet_path: Path) -> dict[str, Any]:
    memory = int(df.memory_usage(deep=True, index=True).sum())
    df.to_parquet(parquet_path, engine="pyarrow", compression="zstd", index=False)
    disk = parquet_path.stat().st_size
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "memory_deep_bytes": memory,
        "memory_deep_mb": round(memory / MB, 2),
        "parquet_bytes": int(disk),
        "parquet_mb": round(disk / MB, 2),
        "column_dtypes": {c: str(t) for c, t in df.dtypes.items()},
    }


def _coverage_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Busiest departure airports and their shares (scope decision: 10/15/20/30 airports)."""
    column = next((c for c in df.columns if c.lower() == "origin"), None)
    if column is None or len(df) == 0:
        return {"origin_column_missing": True}
    counts = df[column].astype(str).value_counts().reset_index()
    counts.columns = ["code", "rows"]
    # deterministic order on ties: count (descending), then code (ascending)
    counts = counts.sort_values(["rows", "code"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
    total = len(df)
    shares = {
        str(n): round(float(counts["rows"].head(n).sum()) / total, 4) for n in (10, 15, 20, 30) if n <= len(counts)
    }
    return {
        "unique_origins": int(len(counts)),
        "top_n_row_share": shares,
        "top_30_origins": [{"code": r.code, "rows": int(r.rows)} for r in counts.head(30).itertuples()],
    }


def _missing_ratios(df: pd.DataFrame) -> dict[str, float]:
    n = len(df)
    if n == 0:
        return {}
    return {c: round(float(df[c].isna().sum()) / n, 4) for c in df.columns}


def measure(
    input_path: Path, parquet_dir: Path, keep_parquet: bool = False, nrows: int | None = None
) -> dict[str, Any]:
    """Run the measurement and return the result dict (the testable core)."""
    input_path = Path(input_path)
    parquet_dir = Path(parquet_dir)
    parquet_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    everything = read_csv(input_path, nrows=nrows)
    read_seconds = time.perf_counter() - started

    subset_lower = {c.lower() for c in MEASUREMENT_SUBSET}
    present = [c for c in everything.columns if c.strip().lower() in subset_lower]
    missing_subset = sorted(
        c for c in MEASUREMENT_SUBSET if c.lower() not in {x.strip().lower() for x in everything.columns}
    )
    subset = _optimized_view(everything[present])

    path_all = parquet_dir / "measure_all.parquet"
    path_subset = parquet_dir / "measure_subset.parquet"
    result = {
        "input_file": input_path.name,
        "input_bytes": int(input_path.stat().st_size),
        "csv_read_seconds": round(read_seconds, 2),
        "all_columns": _measure_frame(everything, path_all),
        "subset": _measure_frame(subset, path_subset),
        "subset_missing_columns": missing_subset,  # expected but absent from the file (name mismatch check)
        "missing_ratios_subset": _missing_ratios(subset),
        "coverage_summary": _coverage_summary(everything),
        "simple_estimate": {
            "description": (
                "Linear extrapolation of ONE MONTH (x12 = 1 year); NOT a measurement. May mislead because of "
                "seasonality. See the rule in the measurement report template before deciding."
            ),
            "subset_memory_mb_yearly": round(memory_mb(subset) * 12, 1),
            "subset_parquet_mb_yearly": round(path_subset.stat().st_size / MB * 12, 1),
        },
        "meta": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "platform": platform.platform(),
            "nrows_limit": nrows,
        },
    }
    if not keep_parquet:
        for path in (path_all, path_subset):
            path.unlink(missing_ok=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Size measurement of a one-month On-Time file (no network).")
    parser.add_argument("--input", type=Path, required=True, help="CSV or single-csv zip.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        default=None,
        help="Default: a temporary folder (deleted after measuring; use --keep-parquet to keep).",
    )
    parser.add_argument("--keep-parquet", action="store_true")
    parser.add_argument("--nrows", type=int, default=None, help="Row limit, for trials only.")
    args = parser.parse_args(argv)

    if args.parquet_dir is None:
        with tempfile.TemporaryDirectory(prefix="measure_parquet_") as temp:
            result = measure(args.input, Path(temp), keep_parquet=False, nrows=args.nrows)
    else:
        result = measure(args.input, args.parquet_dir, keep_parquet=args.keep_parquet, nrows=args.nrows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    full, subset = result["all_columns"], result["subset"]
    print(
        f"all_columns: {full['rows']} rows x {full['columns']} columns, "
        f"memory {full['memory_deep_mb']} MB, parquet {full['parquet_mb']} MB"
    )
    print(
        f"subset     : {subset['rows']} rows x {subset['columns']} columns, "
        f"memory {subset['memory_deep_mb']} MB, parquet {subset['parquet_mb']} MB"
    )
    print(f"Missing expected columns: {result['subset_missing_columns']}")
    print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
