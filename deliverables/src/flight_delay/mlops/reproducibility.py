"""Reproducibility helpers: seed, environment record, git info, data fingerprint.

No network calls. Independent of MLflow. Randomness libraries (numpy, torch) are seeded if present,
skipped otherwise, and the returned dict says which.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata as metadata
import json
import os
import platform
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "TRACKED_LIBRARIES",
    "data_fingerprint",
    "environment_summary",
    "git_info",
    "library_versions",
    "pip_freeze_summary",
    "set_seed",
    "write_json",
]

# Libraries whose versions go into the experiment record (installed ones only)
TRACKED_LIBRARIES = (
    "pandas",
    "numpy",
    "pyarrow",
    "scikit-learn",
    "lightgbm",
    "xgboost",
    "statsmodels",
    "scipy",
    "pydantic",
    "mlflow",
    "ortools",
    "pulp",
)


def set_seed(seed: int) -> dict[str, bool]:
    """Seed random and (if installed) numpy/torch. Returns which ones were seeded.

    Note: PYTHONHASHSEED has no effect inside this process (the interpreter reads it at start-up); it
    is written to the environment only for child processes. Model libraries' own ``random_state``
    parameters must still be passed explicitly.
    """
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError(f"seed must be a non-negative integer: {seed!r}")
    seeded = {"random": True, "numpy": False, "torch": False}
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        numpy = importlib.import_module("numpy")
        numpy.random.seed(seed % (2**32))
        seeded["numpy"] = True
    except ImportError:
        pass
    try:
        torch = importlib.import_module("torch")
        torch.manual_seed(seed)
        seeded["torch"] = True
    except ImportError:
        pass
    return seeded


def library_versions(names: tuple[str, ...] = TRACKED_LIBRARIES) -> dict[str, str]:
    """Installed library versions; 'not installed' for missing ones."""
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def pip_freeze_summary() -> dict[str, Any]:
    """'name==version' list of all installed distributions plus a digest (from metadata, without running pip)."""
    lines = sorted(
        {f"{(d.metadata['Name'] or '').lower()}=={d.version}" for d in metadata.distributions() if d.metadata["Name"]}
    )
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return {"package_count": len(lines), "digest": digest, "packages": lines}


def environment_summary() -> dict[str, Any]:
    """Python, operating system and package summary."""
    return {
        "python": platform.python_version(),
        "implementation": sys.implementation.name,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "pip_freeze": pip_freeze_summary(),
    }


def git_info(working_dir: Path | None = None) -> dict[str, Any]:
    """Git commit and whether the working tree is dirty. 'unknown' if git is missing / not a repo (no error)."""
    cwd = str(working_dir) if working_dir else None

    def _run(*args: str) -> str | None:
        try:
            result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15, check=True)
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    commit = _run("rev-parse", "HEAD")
    status = _run("status", "--porcelain")
    return {
        "commit": commit or "unknown",
        "dirty": (bool(status) if status is not None else None),
    }


def _file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def data_fingerprint(folder: Path, pattern: str = "*.parquet", content_hash: bool = True) -> dict[str, Any]:
    """Deterministic fingerprint of the files in a folder (Parquet by default).

    - Order: sorted by relative path. Not affected by changed mtime or by directory listing order.
    - content_hash=True: each file's sha256 goes into the digest (catches content changes; can be slow).
    - content_hash=False: path + bytes only (fast; does NOT catch a same-size content change).
    FileNotFoundError if the folder is missing, ValueError if no file matches (never makes an empty fingerprint silently).
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Data folder not found: {folder}")
    files = sorted(p for p in folder.rglob(pattern) if p.is_file())
    if not files:
        raise ValueError(f"No file matches the pattern '{pattern}': {folder}")
    records = []
    for path in files:
        record: dict[str, Any] = {"path": path.relative_to(folder).as_posix(), "bytes": path.stat().st_size}
        if content_hash:
            record["sha256"] = _file_sha256(path)
        records.append(record)
    lines = [f"{r['path']}\t{r['bytes']}\t{r.get('sha256', '')}" for r in records]
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return {
        "pattern": pattern,
        "content_hash": content_hash,
        "file_count": len(records),
        "total_bytes": sum(int(r["bytes"]) for r in records),
        "digest": digest,
        "files": records,
    }


def write_json(obj: object, path: Path) -> Path:
    """Write JSON in a stable form (sorted keys, UTF-8). Does NOT overwrite an existing file."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Existing file will not be overwritten: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path
