"""Model matrices (float32 numpy) built month by month from the layer, with fixed category codes.

Pieces:
- ``LayerTableReader``: reads ``scheduled_density`` / ``weather_t120m`` / ``weather_oracle`` partitions for the months
  of an already split-checked frame. It REFUSES any month on or after the final-test start (2026-03), records every
  file it read (path, bytes, sha256) for the data fingerprint, and reads ``weather_oracle`` only when it is asked to
  (only the ``oracle`` contract does that; default off). Exception: the one-time final-test script passes
  ``allow_final_test=True``, which also requires that its lock record already exists (``splits.require_lock_written``).
- ``build_model_matrix``: per calendar month of ``FlightDate`` it calls ``features.build_feature_matrix`` (contract
  validation, weather information-time check, history features) and writes the result into ONE preallocated float32
  array (no concatenation copy). Categorical columns become fixed codes (``CategoryEncoder``); every month must give
  exactly the same column list (otherwise ValueError).
- ``sample_days``: whole-day sample of a fit window (plan section 4.3: 25 % of days for the search; rows of one day
  stay together, nothing is shuffled).

Feature code receives the schedule columns only (``MODEL_FLIGHT_COLUMNS``); labels are used only through a fitted
``HistoryFeatures`` (or its out-of-fold output for training rows).

Dropping features (``drop``, default none): the feature code still builds and validates the full contract; the named
columns are then left out of X (``ModelMatrix.dropped`` records them). ``DATE_FEATURES`` is the calendar group that the
Val-B permutation of run-20261119T182216Z flagged as harmful in most models (option only; the default keeps them).

Density: the layer partitions ``scheduled_density`` by the month of the SOURCE file, so the rows of the local dates of
month m can sit in the files of m - 1, m and m + 1 (late-evening flights arriving after midnight). The reader sums the
three files (``features.aggregate_density`` does the sum) but never opens a final-test month: for February 2026 the
March file is skipped, so arrivals on 2026-03-01 00:00-05:59 from March-file flights are not counted (the only effect
is on ``planned_arrivals_dest_hour`` of a few red-eye arrivals; recorded as ``density_neighbours_skipped``).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flight_delay.data.feature_contract import FeatureContract
from flight_delay.data.layer import DEFAULT_LAYER_DIR, PARQUET_NAME, table_dir
from flight_delay.data.tables import DENSITY
from flight_delay.data.weather_join import ORACLE_TABLE, horizon_table_name
from flight_delay.modeling import features as ft
from flight_delay.modeling.categories import CategoryEncoder
from flight_delay.modeling.splits import FINAL_TEST, FinalTestAccessError, require_lock_written

__all__ = [
    "DATE_FEATURES",
    "HISTORY_INPUT_COLUMNS",
    "MODEL_FLIGHT_COLUMNS",
    "MODEL_LABEL_COLUMNS",
    "WEATHER_INPUT_COLUMNS",
    "LayerTableReader",
    "ModelMatrix",
    "build_model_matrix",
    "frame_to_array",
    "month_keys",
    "sample_days",
    "segment_keys",
]

# schedule side given to feature code (= features._FLIGHT_INPUTS)
MODEL_FLIGHT_COLUMNS = (
    "flight_uid",
    "FlightDate",
    "Origin",
    "Dest",
    "Reporting_Airline",
    "CRSDepTime",
    "CRSArrTime",
    "CRSElapsedTime",
    "Distance",
    "DistanceGroup",
    "crs_dep_utc",
    "crs_arr_utc",
    "crs_dep_local_min",
    "crs_arr_day_offset",
)
# label side: targets + the label columns HistoryFeatures.fit needs
MODEL_LABEL_COLUMNS = ("flight_uid", "ArrDelay", "ArrDel15", "Cancelled", "Diverted", "ActualElapsedTime", "TaxiOut")
HISTORY_INPUT_COLUMNS = (
    "FlightDate",
    "Origin",
    "Dest",
    "Reporting_Airline",
    "crs_dep_local_min",
    "CRSElapsedTime",
    "ArrDel15",
    "ArrDelay",
    "Cancelled",
    "Diverted",
    "ActualElapsedTime",
    "TaxiOut",
)
_SIDE_COLUMNS = (
    "obs_utc",
    "obs_age_min",
    *ft.WEATHER_NUMERIC,
    *(f"skyc{i}" for i in range(1, 5)),
    *(f"skyl{i}" for i in range(1, 5)),
    "wxcodes",
)
WEATHER_INPUT_COLUMNS = ("flight_uid", "is_oracle", *(f"{s}_{c}" for s in ("origin", "dest") for c in _SIDE_COLUMNS))
# calendar features (plan 2.3 "Takvim" + holidays) without day_of_week; see the module docstring
DATE_FEATURES: tuple[str, ...] = ("month", "day_of_year", "day_of_month", "days_to_holiday", "holiday_week")


def _final_test_month(year: int, month: int) -> bool:
    return dt.date(year, month, 1) >= FINAL_TEST.start.replace(day=1)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


class LayerTableReader:
    """Reads side tables of development months only (final-test months: see the module docstring)."""

    def __init__(
        self,
        layer_root: Path | None = None,
        *,
        hash_files: bool = True,
        allow_final_test: bool = False,
        lock_file: Path | None = None,
    ) -> None:
        self.root = Path(layer_root) if layer_root is not None else DEFAULT_LAYER_DIR
        self.hash_files = hash_files
        self.allow_final_test = bool(allow_final_test)
        if self.allow_final_test:
            require_lock_written(lock_file)
        self.files: list[dict[str, Any]] = []
        self.missing: list[str] = []
        self.density_neighbours_skipped: list[str] = []
        self._density_cache: dict[tuple[int, int], pd.DataFrame | None] = {}
        self._seen: set[str] = set()

    def read(
        self, table: str, year: int, month: int, columns: Sequence[str] | None = None, *, optional: bool = False
    ) -> pd.DataFrame | None:
        if _final_test_month(year, month) and not self.allow_final_test:
            raise FinalTestAccessError(f"{table} {year}-{month:02d} belongs to the final test; refused in development")
        path = table_dir(self.root, table, year, month) / PARQUET_NAME
        relative = path.relative_to(self.root).as_posix()
        if not path.is_file():
            if optional:
                self.missing.append(relative)
                return None
            raise FileNotFoundError(f"Layer partition missing: {path}")
        frame = pd.read_parquet(path, columns=list(columns) if columns is not None else None, engine="pyarrow")
        if relative not in self._seen:
            self._seen.add(relative)
            record: dict[str, Any] = {"path": relative, "bytes": path.stat().st_size}
            if self.hash_files:
                record["sha256"] = _sha256(path)
            self.files.append(record)
        return frame

    def _density_file(self, year: int, month: int, *, optional: bool) -> pd.DataFrame | None:
        key = (year, month)
        if key not in self._density_cache:
            self._density_cache[key] = self.read(DENSITY, year, month, optional=optional)
        return self._density_cache[key]

    def density_for_month(self, year: int, month: int) -> pd.DataFrame:
        """Raw density rows (files m - 1, m, m + 1; never a final-test month) for the local dates of month m."""
        parts: list[pd.DataFrame] = []
        for delta in (-1, 0, 1):
            y, m = _shift_month(year, month, delta)
            if _final_test_month(y, m) and not self.allow_final_test:
                self.density_neighbours_skipped.append(f"{DENSITY} {y}-{m:02d} (final test) for {year}-{month:02d}")
                continue
            part = self._density_file(y, m, optional=delta != 0)
            if part is not None:
                parts.append(part)
        density = pd.concat(parts, ignore_index=True)
        dates = pd.to_datetime(density["local_date"]).dt.normalize()
        first = pd.Timestamp(year, month, 1)
        last = first + pd.offsets.MonthEnd(0) + pd.Timedelta(days=2)
        return density.loc[(dates >= first) & (dates <= last)].reset_index(drop=True)

    def weather(self, year: int, month: int, *, oracle: bool, horizon_hours: float) -> pd.DataFrame:
        table = ORACLE_TABLE if oracle else horizon_table_name(horizon_hours)
        frame = self.read(table, year, month, WEATHER_INPUT_COLUMNS)
        assert frame is not None  # optional=False
        return frame


@dataclass
class ModelMatrix:
    """float32 design matrix; ``row_positions`` = positions of the rows in the source frame (frame order)."""

    x: np.ndarray
    feature_names: list[str]
    categorical_indices: list[int]
    row_positions: np.ndarray
    contract: FeatureContract
    kind: str
    months: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)  # contract features left out of X (``drop``)


def month_keys(dates: pd.Series) -> np.ndarray:
    """year * 100 + month of each date (int64)."""
    values = pd.to_datetime(dates)
    return np.asarray(values.dt.year * 100 + values.dt.month, dtype="int64")


def frame_to_array(frame: pd.DataFrame, names: Sequence[str], encoder: CategoryEncoder) -> np.ndarray:
    """Columns in ``names`` order as float32; encoder columns -> fixed codes (unknown / missing -> NaN)."""
    out = np.empty((len(frame), len(names)), dtype="float32")
    for j, name in enumerate(names):
        if name in encoder.columns:
            out[:, j] = encoder.codes(frame[name], name)
        else:
            out[:, j] = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype="float32", na_value=np.nan)
    return out


def build_model_matrix(
    frame: pd.DataFrame,
    *,
    kind: str,
    reader: LayerTableReader,
    encoder: CategoryEncoder,
    history: ft.HistoryFeatures | None = None,
    history_frame: pd.DataFrame | None = None,
    rows: np.ndarray | None = None,
    require_after_fit_end: bool = True,
    horizon_hours: float = ft.DEFAULT_HORIZON_HOURS,
    margin_minutes: float = ft.DEFAULT_MARGIN_MINUTES,
    history_ready_minutes: int = ft.DEFAULT_HISTORY_READY_MINUTES,
    drop: Sequence[str] = (),
) -> ModelMatrix:
    """X for the selected rows of ``frame`` (loader output: flights + labels columns), month by month.

    ``kind``: 'plan' (no weather), 'T2' (weather before T) or 'oracle' (T2 + oracle weather; upper-bound experiment).
    ``history_frame`` (out-of-fold encoding of the training rows, same index as ``frame``) or ``history`` (fitted;
    applied to evaluation rows strictly after its fit end) gives the past statistics.
    ``drop``: contract features to leave out of X (a name that is not a feature of this contract is an error).
    """
    if kind not in ft.CONTRACT_KINDS:
        raise ValueError(f"kind must be one of {ft.CONTRACT_KINDS}: {kind!r}")
    dropped = list(dict.fromkeys(str(d) for d in drop))
    if history is None and history_frame is None:
        raise ValueError("History features are part of every contract: pass history or history_frame")
    selected = np.ones(len(frame), dtype=bool) if rows is None else np.asarray(rows, dtype=bool)
    if selected.shape != (len(frame),):
        raise ValueError("rows must be a boolean mask over frame")
    positions = np.flatnonzero(selected)
    if positions.size == 0:
        raise ValueError("No rows selected")
    flights_all = frame[list(MODEL_FLIGHT_COLUMNS)]
    keys = month_keys(frame["FlightDate"])
    x: np.ndarray | None = None
    all_names: list[str] = []
    names: list[str] = []
    contract: FeatureContract | None = None
    months: list[str] = []
    for key in sorted(set(keys[selected].tolist())):
        year, month = divmod(int(key), 100)
        in_month = selected & (keys == key)
        flights = flights_all.loc[in_month]
        weather_t = reader.weather(year, month, oracle=False, horizon_hours=horizon_hours) if kind != "plan" else None
        weather_oracle = (
            reader.weather(year, month, oracle=True, horizon_hours=horizon_hours) if kind == "oracle" else None
        )
        built = ft.build_feature_matrix(
            flights,
            density=reader.density_for_month(year, month),
            weather_t=weather_t,
            history=None if history_frame is not None else history,
            history_frame=history_frame,
            weather_oracle=weather_oracle,
            oracle=kind == "oracle",
            horizon_hours=horizon_hours,
            margin_minutes=margin_minutes,
            history_ready_minutes=history_ready_minutes,
            require_after_fit_end=require_after_fit_end,
        )
        if built.kind != kind:
            raise ValueError(f"Expected a {kind!r} matrix, got {built.kind!r} for {year}-{month:02d}")
        if x is None:
            all_names = list(built.frame.columns)
            unknown = [d for d in dropped if d not in all_names]
            if unknown:
                raise ValueError(f"Cannot drop {unknown}: not features of the {kind!r} contract")
            names = [n for n in all_names if n not in dropped]
            if not names:
                raise ValueError("Every feature would be dropped")
            contract = built.contract
            x = np.empty((positions.size, len(names)), dtype="float32")
        elif list(built.frame.columns) != all_names:
            raise ValueError(f"Feature columns of {year}-{month:02d} differ from the first month")
        target = np.searchsorted(positions, np.flatnonzero(in_month))
        x[target] = frame_to_array(built.frame, names, encoder)
        months.append(f"{year:04d}-{month:02d}")
    assert x is not None and contract is not None
    categorical = [names.index(c) for c in encoder.columns if c in names]
    return ModelMatrix(
        x=x,
        feature_names=names,
        categorical_indices=categorical,
        row_positions=positions,
        contract=contract,
        kind=kind,
        months=months,
        dropped=dropped,
    )


def sample_days(dates: pd.Series, fraction: float, *, seed: int = 42) -> np.ndarray:
    """Boolean mask selecting all rows of round(fraction * n_days) randomly chosen whole days (at least one)."""
    if not 0.0 < fraction <= 1.0:
        raise ValueError(f"fraction must be in (0, 1]: {fraction}")
    days = pd.to_datetime(dates).dt.normalize()
    unique_days = np.sort(days.unique())
    if fraction == 1.0:
        return np.ones(len(days), dtype=bool)
    n_pick = max(1, round(fraction * len(unique_days)))
    rng = np.random.default_rng(seed)
    picked = np.sort(rng.choice(unique_days, size=n_pick, replace=False))
    return np.asarray(days.isin(picked).to_numpy(), dtype=bool)


def segment_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """Segment columns of plan section 7 used here: Origin, hour_block, month (NO carrier dimension)."""
    keyed = ft.add_key_columns(frame[["FlightDate", "crs_dep_local_min", "Origin"]])
    return keyed[["Origin", "hour_block", "month"]].reset_index(drop=True)
