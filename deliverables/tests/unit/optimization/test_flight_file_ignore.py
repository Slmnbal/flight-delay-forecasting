"""Flight-level file guard: ``git check-ignore`` must be asked about the FILE path, not the folder (bug of run 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from flight_delay.optimization import run_buffer as rb


def test_the_file_path_is_checked_not_the_folder(tmp_path: Path) -> None:
    asked: list[Path] = []

    def checker(path: Path) -> bool | None:
        asked.append(path)
        return path.suffix == ".parquet"  # mimics the repository rule '*.parquet'

    folder = tmp_path / "tampon-20990101T000000Z"
    assert rb.flight_file_git_ignored(folder, checker) is True
    assert asked == [folder / rb.FLIGHT_FILE]
    assert checker(folder) is False  # the folder alone does not match a file pattern (the original bug)


def test_unknown_git_state_is_passed_through(tmp_path: Path) -> None:
    assert rb.flight_file_git_ignored(tmp_path, lambda _path: None) is None


def test_repository_ignores_the_flight_file_path() -> None:
    """Real git: the flight Parquet under deliverables/data/or/ is ignored (rule '*.parquet'); skipped without git."""
    ignored = rb.flight_file_git_ignored(rb.DATA_OUTPUT_DIR / "tampon-20990101T000000Z")
    if ignored is None:
        pytest.skip("git is not available")
    assert ignored is True
