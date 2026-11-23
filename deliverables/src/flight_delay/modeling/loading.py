"""Month-by-month, column-pruned reading of the layer for modeling (memory: never all 36 months, never all columns).

- Reads ``<layer>/<table>/year=YYYY/month=MM/part-0.parquet`` with pyarrow column selection, converts string keys to
  ``category`` per month and concatenates with ``union_categoricals`` (no object-string blow-up).
- Split guard: ``load_months_for`` takes split / fold names and refuses the final test unless the explicit flag is set
  (``splits.get_period``). The final-test partitions are therefore never opened in development (plan section 1.5).
  After reading, rows are filtered to the requested periods by ``FlightDate`` and ``assert_no_final_test`` runs.
- Labels (``flight_labels``) are joined only when ``label_columns`` is given; this is label / evaluation code.
  Feature code receives frames without labels (``features.check_no_forbidden_inputs``).
- File fingerprint: sha256 of exactly the files read (for MLflow / the result JSON), so the final-test files are not
  even hashed.

Known limit: a row whose ``FlightDate`` lies outside its partition month (``summary.json`` ``rows_outside_month``)
is dropped by the period filter if its month is not read.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

from flight_delay.data.layer import DEFAULT_LAYER_DIR, PARQUET_NAME, table_dir
from flight_delay.data.tables import FLIGHTS, LABELS
from flight_delay.modeling.splits import (
    FINAL_TEST,
    SPLIT_DATE_COLUMN,
    FinalTestAccessError,
    Period,
    assert_no_final_test,
    get_fold,
    get_period,
)

__all__ = [
    "BASELINE_FLIGHT_COLUMNS",
    "BASELINE_LABEL_COLUMNS",
    "CATEGORY_COLUMNS",
    "LoadedData",
    "fingerprint",
    "load_periods",
    "partition_file",
    "periods_for",
    "read_months",
]

BASELINE_FLIGHT_COLUMNS = ("flight_uid", "FlightDate", "Origin", "Dest", "Reporting_Airline", "crs_dep_local_min")
BASELINE_LABEL_COLUMNS = ("flight_uid", "ArrDelay", "ArrDel15", "Cancelled", "Diverted")
CATEGORY_COLUMNS = ("Origin", "Dest", "Reporting_Airline")


@dataclass
class LoadedData:
    frame: pd.DataFrame
    files: list[dict[str, Any]] = field(default_factory=list)
    months: list[tuple[int, int]] = field(default_factory=list)


def partition_file(root: Path, table: str, year: int, month: int) -> Path:
    return table_dir(Path(root), table, year, month) / PARQUET_NAME


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _read_table(path: Path, columns: Sequence[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Layer partition missing: {path}")
    frame = pd.read_parquet(path, columns=list(columns), engine="pyarrow")
    for column in CATEGORY_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].astype("string").astype("category")
    return frame


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        raise ValueError("No month was read")
    categorical = [c for c in CATEGORY_COLUMNS if c in frames[0].columns]
    unified = {c: union_categoricals([f[c] for f in frames], sort_categories=True) for c in categorical}
    plain = pd.concat([f.drop(columns=categorical) for f in frames], ignore_index=True)
    for column, values in unified.items():
        plain[column] = pd.Categorical(values)
    return plain[list(frames[0].columns)]


def read_months(
    layer_root: Path,
    months: Iterable[tuple[int, int]],
    *,
    flight_columns: Sequence[str] = BASELINE_FLIGHT_COLUMNS,
    label_columns: Sequence[str] = (),
    hash_files: bool = True,
) -> LoadedData:
    """Read the given partitions (flights + optionally labels). Does NOT check splits: use ``load_periods``."""
    month_list = list(months)
    if "flight_uid" not in flight_columns:
        raise ValueError("flight_columns must include flight_uid")
    frames: list[pd.DataFrame] = []
    files: list[dict[str, Any]] = []
    for year, month in month_list:
        flights_path = partition_file(layer_root, FLIGHTS, year, month)
        frame = _read_table(flights_path, flight_columns)
        used = [flights_path]
        if label_columns:
            labels_path = partition_file(layer_root, LABELS, year, month)
            labels = _read_table(labels_path, ["flight_uid", *[c for c in label_columns if c != "flight_uid"]])
            merged = frame.merge(labels, on="flight_uid", how="inner", validate="one_to_one")
            if len(merged) != len(frame) or len(merged) != len(labels):
                raise ValueError(f"flights and flight_labels row sets differ in {year}-{month:02d}")
            frame = merged
            used.append(labels_path)
        frames.append(frame)
        for path in used:
            record: dict[str, Any] = {
                "path": path.relative_to(Path(layer_root)).as_posix(),
                "bytes": path.stat().st_size,
            }
            if hash_files:
                record["sha256"] = _sha256(path)
            files.append(record)
    return LoadedData(frame=_concat(frames), files=files, months=month_list)


def periods_for(names: Iterable[str], *, allow_final_test: bool = False, lock_file: Path | None = None) -> list[Period]:
    """Split names ('train', 'val_a', 'val_b', 'final_test') or fold names ('K1'..'K4' -> fit + evaluation)."""
    periods: list[Period] = []
    for name in names:
        if name.startswith("K"):
            fold = get_fold(name)
            periods.extend([fold.fit, fold.evaluation])
        else:
            periods.append(get_period(name, allow_final_test=allow_final_test, lock_file=lock_file))
    return periods


def load_periods(
    layer_root: Path | None,
    periods: Sequence[Period],
    *,
    flight_columns: Sequence[str] = BASELINE_FLIGHT_COLUMNS,
    label_columns: Sequence[str] = (),
    hash_files: bool = True,
    allow_final_test: bool = False,
) -> LoadedData:
    """Read the union of the periods' months and keep rows inside any of the periods (order kept, no shuffling).

    ``periods`` must come from ``periods_for`` / ``splits``; a period that overlaps the final test is refused unless
    ``allow_final_test`` (which ``periods_for`` already demanded) is passed again here.
    """
    root = Path(layer_root) if layer_root is not None else DEFAULT_LAYER_DIR
    for period in periods:
        if period.end >= FINAL_TEST.start and not allow_final_test:
            raise FinalTestAccessError(f"Period {period.name} reaches into the final test; refused in development")
    months = sorted({m for period in periods for m in period.months()})
    loaded = read_months(
        root, months, flight_columns=flight_columns, label_columns=label_columns, hash_files=hash_files
    )
    inside = np.zeros(len(loaded.frame), dtype=bool)
    for period in periods:
        inside |= period.contains(loaded.frame[SPLIT_DATE_COLUMN])
    loaded.frame = loaded.frame.loc[inside].reset_index(drop=True)
    if not allow_final_test:
        assert_no_final_test(loaded.frame[SPLIT_DATE_COLUMN])
    return loaded


def fingerprint(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic digest of the files read (same shape as mlops.reproducibility.data_fingerprint)."""
    records = sorted(files, key=lambda r: str(r["path"]))
    lines = [f"{r['path']}\t{r['bytes']}\t{r.get('sha256', '')}" for r in records]
    return {
        "pattern": "files read by flight_delay.modeling.loading",
        "content_hash": all("sha256" in r for r in records),
        "file_count": len(records),
        "total_bytes": sum(int(r["bytes"]) for r in records),
        "digest": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
        "files": records,
    }
