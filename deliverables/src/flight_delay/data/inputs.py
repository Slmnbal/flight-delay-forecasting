"""Input-file guards (NO NETWORK).

Rule (code review M5): a missing input file must never be ignored silently. A caller either gets the
file or a clear error that names the option to fix (or to switch off on purpose).
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["require_file"]


def require_file(path: Path, description: str, option: str) -> Path:
    """Return ``path`` if it is an existing file, else raise ``FileNotFoundError`` with a helpful message.

    ``description`` says what the file is ("time zone overrides"); ``option`` names the CLI option
    (and, if there is one, the explicit opt-out flag) so the message tells the user what to do.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Required input file not found: {description}: {resolved}. Fix {option}.")
    return resolved
