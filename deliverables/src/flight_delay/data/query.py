"""DuckDB helper that reads the layer Parquet files (NO NETWORK).

Views (each reads <layer>/<table>/year=*/month=*/*.parquet; data is not loaded into memory):
  ``flights``            schedule + UTC + flags (the feature side)
  ``flight_labels``      outcomes (ArrDelay, Cancelled, actual UTC, ...); join with flights on ``flight_uid``
  ``scheduled_density``  scheduled traffic per airport x local date x local hour (all BTS flights)
A view whose table has no files yet is simply not created. ``flight_keys`` (Tail_Number) is local-only and
is deliberately NOT exposed as a view.

Partition columns: the views expose ``partition_year`` and ``partition_month`` (parsed from the folder
names ``year=YYYY/month=MM``). DuckDB's hive auto-detection is switched OFF on purpose: identifiers are
case-insensitive in DuckDB, so a hive column named ``year`` / ``month`` would collide with the BTS file
columns ``Year`` / ``Month``. ``partition_year`` / ``partition_month`` are SEPARATE from those file columns.

Usage (Python):
    from flight_delay.data.query import run_query
    df = run_query("SELECT Origin, count(*) n FROM flights GROUP BY ALL ORDER BY n DESC")

CLI:
    python -m flight_delay.data.query --summary
    python -m flight_delay.data.query --sql "SELECT count(*) FROM flights WHERE Cancelled = 1"

Note: ``*_utc`` columns are UTC and tz-less (naive) timestamps (see the layer module docstring).
The ``--sql`` option runs ANY SQL the caller gives (including DuckDB file-reading/writing functions);
it is a local analysis tool and must not be exposed to untrusted input.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from flight_delay.data.layer import DEFAULT_LAYER_DIR
from flight_delay.data.tables import DENSITY, FLIGHTS, LABELS

__all__ = ["SUMMARY_SQL", "connect", "main", "parquet_glob", "run_query"]

SUMMARY_SQL = """
SELECT f.partition_year, f.partition_month,
       count(*)                                AS row_count,
       count(*) FILTER (WHERE l.Cancelled = 1) AS cancelled_count,
       count(*) FILTER (WHERE l.Diverted = 1)  AS diverted_count,
       round(avg(l.ArrDelay), 2)               AS mean_arr_delay_min,
       count(DISTINCT f.Origin)                AS origin_count
FROM flights f
JOIN flight_labels l USING (flight_uid)
GROUP BY f.partition_year, f.partition_month
ORDER BY f.partition_year, f.partition_month
"""


def parquet_glob(layer_root: Path | None = None, table: str = FLIGHTS) -> str:
    root = Path(layer_root) if layer_root else DEFAULT_LAYER_DIR
    return str(root / table / "year=*" / "month=*" / "*.parquet")


def _create_view(connection: Any, view_name: str, root: Path, table: str) -> None:
    pattern = parquet_glob(root, table).replace("'", "''")
    connection.execute(
        f"""
        CREATE VIEW {view_name} AS
        SELECT * EXCLUDE (filename),
               CAST(regexp_extract(filename, 'year=([0-9]{{4}}).month=([0-9]{{2}})', 1) AS INTEGER) AS partition_year,
               CAST(regexp_extract(filename, 'year=([0-9]{{4}}).month=([0-9]{{2}})', 2) AS INTEGER) AS partition_month
        FROM read_parquet('{pattern}', filename = true, hive_partitioning = false, union_by_name = true)
        """
    )


def connect(layer_root: Path | None = None, view_name: str = "flights") -> Any:
    """In-memory DuckDB connection; defines the flights view under ``view_name`` (+ labels / density views)."""
    import duckdb  # local import: only this function fails if duckdb is not installed

    root = Path(layer_root) if layer_root else DEFAULT_LAYER_DIR
    if not list(root.glob(f"{FLIGHTS}/year=*/month=*/*.parquet")):
        raise FileNotFoundError(
            f"Layer Parquet not found: {root} (run flight_delay.data.layer / download_range --process first)."
        )
    if not view_name.isidentifier():
        raise ValueError(f"Invalid view name: {view_name!r}")
    connection = duckdb.connect(database=":memory:")
    _create_view(connection, view_name, root, FLIGHTS)
    for table in (LABELS, DENSITY):
        if list(root.glob(f"{table}/year=*/month=*/*.parquet")):
            _create_view(connection, table, root, table)
    return connection


def run_query(sql: str, layer_root: Path | None = None) -> pd.DataFrame:
    """Run the SQL and return a pandas DataFrame (keep the result small: aggregate / filter)."""
    connection = connect(layer_root)
    try:
        return connection.execute(sql).df()
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DuckDB query over the layer Parquet files (no network).")
    parser.add_argument("--layer-dir", type=Path, default=DEFAULT_LAYER_DIR)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--summary", action="store_true", help="Per-month rows / cancelled / diverted summary.")
    group.add_argument("--sql", help="SQL that uses the `flights` view.")
    args = parser.parse_args(argv)
    df = run_query(SUMMARY_SQL if args.summary else args.sql, args.layer_dir)
    with pd.option_context("display.max_rows", 200, "display.width", 200, "display.max_columns", 50):
        print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
