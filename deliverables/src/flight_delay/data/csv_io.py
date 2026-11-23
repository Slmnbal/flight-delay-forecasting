"""Reading the BTS On-Time CSV (plain or inside a single-CSV zip).

Shared by the layer builder, the size measurement and the UTC check.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path

import pandas as pd

__all__ = ["column_selector", "read_csv"]


def column_selector(names: Iterable[str]) -> Callable[[str], bool]:
    """Case-insensitive ``usecols`` selector (BTS column spelling was not verified against the data dictionary)."""
    wanted = {name.lower() for name in names}
    return lambda column: column.strip().lower() in wanted


def read_csv(
    path: Path,
    usecols: Callable[[str], bool] | list[str] | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    """Read a CSV, or a zip that contains exactly one CSV.

    ``index_col=False`` guards against the trailing comma at the end of BTS lines. The empty unnamed
    column that comma produces is dropped (rule: name starts with ``Unnamed:`` AND the column is
    entirely empty). No rows are dropped.
    """
    path = Path(path)
    kwargs = {"usecols": usecols, "nrows": nrows, "index_col": False, "low_memory": False}
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"Expected exactly 1 csv inside the zip, found: {csv_names}")
            with archive.open(csv_names[0]) as handle:
                frame = pd.read_csv(handle, **kwargs)
    else:
        frame = pd.read_csv(path, **kwargs)
    empty_unnamed = [c for c in frame.columns if str(c).startswith("Unnamed:") and frame[c].isna().all()]
    return frame.drop(columns=empty_unnamed)
