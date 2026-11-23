"""Fixtures for the MLOps tests. Tests are OFFLINE; MLflow is not needed.

Fixtures only; the package is imported normally (``pip install -e deliverables[dev]``).
"""

import pytest

from flight_delay.mlops import settings as settings_module
from flight_delay.mlops.settings import Settings, load_settings


@pytest.fixture
def project_settings() -> Settings:
    """The real project settings that ship with the package."""
    return load_settings(settings_module.DEFAULT_SETTINGS_PATH)
