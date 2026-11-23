"""download_ontime tests: URL building and zip extraction safety (NO network call)."""

import zipfile

import pytest

from flight_delay.data import download_ontime as dl


def test_build_url_and_validation():
    assert dl.build_url(2025, 7).endswith("_2025_7.zip")
    with pytest.raises(ValueError):
        dl.build_url(2025, 13)
    with pytest.raises(ValueError):
        dl.build_url(1900, 1)


# ---- new tests: the extraction code is a security control (zip-slip) that had no test in the legacy suite
def test_extract_csv_rejects_a_non_zip(tmp_path):
    fake = tmp_path / "page.zip"
    fake.write_text("<html>error page</html>")
    with pytest.raises(RuntimeError, match="not a valid zip"):
        dl._extract_csv(fake, tmp_path)


def test_extract_csv_requires_exactly_one_csv(tmp_path):
    archive = tmp_path / "two.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.csv", "x\n")
        zf.writestr("b.csv", "x\n")
    with pytest.raises(RuntimeError, match="exactly 1 csv"):
        dl._extract_csv(archive, tmp_path)


def test_extract_csv_drops_folder_components(tmp_path):
    archive = tmp_path / "slip.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../evil.csv", "x\n")  # path traversal attempt
    target_dir = tmp_path / "raw"
    target_dir.mkdir()
    extracted = dl._extract_csv(archive, target_dir)
    assert extracted == target_dir / "evil.csv"
    assert not (tmp_path.parent / "evil.csv").exists()
