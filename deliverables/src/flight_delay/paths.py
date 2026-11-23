"""Well-known project locations, derived from this file's position in the source tree.

Layout: <project>/deliverables/src/flight_delay/paths.py

These paths assume an editable install (``pip install -e deliverables[dev]``) or running from the
source tree. A regular (non-editable) install would point into site-packages; pass explicit paths
(every CLI has options for that) if the package is ever installed that way.
"""

from pathlib import Path

__all__ = ["DATA_DIR", "DELIVERABLES_DIR", "PACKAGE_DIR", "PROJECT_ROOT"]

PACKAGE_DIR = Path(__file__).resolve().parent
DELIVERABLES_DIR = PACKAGE_DIR.parents[1]  # parents[0] = src, parents[1] = deliverables
PROJECT_ROOT = DELIVERABLES_DIR.parent
DATA_DIR = DELIVERABLES_DIR / "data"
