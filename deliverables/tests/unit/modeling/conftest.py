"""Fixtures for the modeling tests. Synthetic data builders live in ``modeling_synth.py`` (not real data)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def missing_lock(tmp_path: Path) -> Path:
    """A final-test lock path that does not exist (the final test was never looked at)."""
    return tmp_path / "son-test-kilidi.json"
