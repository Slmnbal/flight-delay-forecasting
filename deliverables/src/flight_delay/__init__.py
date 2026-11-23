"""Flight delay forecasting project: data layer (BTS On-Time + weather) and MLOps helpers.

Subpackages:
    flight_delay.data   -- download, parse, UTC conversion, partitioned Parquet layer, quality checks, queries.
    flight_delay.mlops  -- settings, reproducibility helpers, local MLflow wrapper.

Subpackages are not imported here on purpose: heavy optional dependencies (duckdb, mlflow) load only when needed.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("flight-delay")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
