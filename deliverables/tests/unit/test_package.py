"""Package-level tests (new): the package installs and resolves its own locations."""

import flight_delay
from flight_delay import paths


def test_package_imports_and_has_a_version():
    assert isinstance(flight_delay.__version__, str) and flight_delay.__version__


def test_paths_point_into_the_source_tree():
    assert (paths.DELIVERABLES_DIR / "pyproject.toml").is_file()
    assert (paths.DELIVERABLES_DIR / "src" / "flight_delay" / "__init__.py").is_file()
    assert paths.DELIVERABLES_DIR.parent == paths.PROJECT_ROOT
    assert paths.DATA_DIR == paths.DELIVERABLES_DIR / "data"
