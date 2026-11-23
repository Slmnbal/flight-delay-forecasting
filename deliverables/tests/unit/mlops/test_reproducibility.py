import random

import pytest

from flight_delay.mlops import reproducibility as rp


def _make_data(folder):
    (folder / "year=2024").mkdir(parents=True)
    (folder / "year=2024" / "b.parquet").write_bytes(b"BBBB")
    (folder / "a.parquet").write_bytes(b"AAA")
    (folder / "not.txt").write_bytes(b"ignored")
    return folder


def test_fingerprint_is_deterministic(tmp_path):
    folder = _make_data(tmp_path / "v")
    assert rp.data_fingerprint(folder) == rp.data_fingerprint(folder)


def test_fingerprint_changes_when_content_changes(tmp_path):
    folder = _make_data(tmp_path / "v")
    before = rp.data_fingerprint(folder)["digest"]
    (folder / "a.parquet").write_bytes(b"AAB")  # same size, different content
    assert rp.data_fingerprint(folder)["digest"] != before


def test_size_only_mode_misses_a_same_size_change(tmp_path):
    # Known (documented) limit: content_hash=False looks only at path + bytes
    folder = _make_data(tmp_path / "v")
    before = rp.data_fingerprint(folder, content_hash=False)["digest"]
    (folder / "a.parquet").write_bytes(b"AAB")
    assert rp.data_fingerprint(folder, content_hash=False)["digest"] == before


def test_fingerprint_fields_and_order(tmp_path):
    fingerprint = rp.data_fingerprint(_make_data(tmp_path / "v"))
    assert fingerprint["file_count"] == 2
    assert fingerprint["total_bytes"] == 7
    assert [f["path"] for f in fingerprint["files"]] == ["a.parquet", "year=2024/b.parquet"]


def test_fingerprint_independent_of_creation_order(tmp_path):
    first, second = tmp_path / "x", tmp_path / "y"
    for folder, order in ((first, ("a", "b")), (second, ("b", "a"))):
        folder.mkdir()
        for name in order:
            (folder / f"{name}.parquet").write_bytes(name.encode())
    assert rp.data_fingerprint(first)["digest"] == rp.data_fingerprint(second)["digest"]


def test_fingerprint_missing_and_empty_folder(tmp_path):
    with pytest.raises(FileNotFoundError):
        rp.data_fingerprint(tmp_path / "missing")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError):
        rp.data_fingerprint(tmp_path / "empty")


def test_seed_gives_the_same_sequence():
    rp.set_seed(123)
    first = [random.random() for _ in range(3)]
    rp.set_seed(123)
    assert first == [random.random() for _ in range(3)]


@pytest.mark.parametrize("bad", [-1, 1.5, "7", True])
def test_invalid_seed(bad):
    with pytest.raises(ValueError):
        rp.set_seed(bad)


def test_environment_and_versions():
    env = rp.environment_summary()
    assert env["python"] and env["pip_freeze"]["package_count"] >= 1
    versions = rp.library_versions(("pytest", "definitely-not-a-package-xyz"))
    assert versions["definitely-not-a-package-xyz"] == "not installed"
    assert versions["pytest"] != "not installed"


def test_git_info_does_not_fail_outside_a_repo(tmp_path):
    info = rp.git_info(tmp_path)  # tmp may or may not be a git repo; the keys exist either way
    assert set(info) == {"commit", "dirty"}


def test_write_json_does_not_overwrite(tmp_path):
    path = rp.write_json({"b": 1, "a": 2}, tmp_path / "x" / "o.json")
    text = path.read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')
    with pytest.raises(FileExistsError):
        rp.write_json({}, path)
