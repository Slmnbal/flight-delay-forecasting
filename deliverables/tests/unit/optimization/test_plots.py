"""Figures: files are produced (tmp_path), never overwritten; series validation."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from flight_delay.optimization import plots as pl  # noqa: E402

X = [1.0, 5.0, 15.0]


def _series(values: list[float], *, band: bool = True, dashed: bool = False) -> dict[str, object]:
    return {
        "y": values,
        "low": [v - 0.01 for v in values] if band else None,
        "high": [v + 0.01 for v in values] if band else None,
        "label": "örnek",
        "style": "dashed" if dashed else "solid",
    }


def test_budget_curve_writes_a_png(tmp_path: Path) -> None:
    late = {"x": X, "series": {"a": _series([0.22, 0.19, 0.14]), "b": _series([0.22, 0.20, 0.15])}}
    residual = {"x": X, "series": {"a": _series([16.0, 14.0, 10.0])}}
    path = pl.plot_budget_curve(tmp_path / "g" / "butce.png", late, residual, title="Bütçe eğrisi", note="not")
    assert path.is_file() and path.stat().st_size > 0
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_level_sensitivity_and_expected_vs_realized(tmp_path: Path) -> None:
    taus = [0.5, 0.8, 0.95]
    panel = {"x": taus, "series": {"plan": _series([8.6, 10.0, 11.0], band=False)}}
    first = pl.plot_level_sensitivity(tmp_path / "tau.png", panel, panel, panel, title="τ duyarlılığı")
    gap = {
        "x": X,
        "series": {"e": _series([0.2, 0.18, 0.13], band=False, dashed=True), "r": _series([0.2, 0.19, 0.15])},
    }
    second = pl.plot_expected_vs_realized(tmp_path / "gap.png", gap, title="Beklenen ve gerçekleşen")
    assert first.is_file() and second.is_file()


def test_figures_are_never_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "var.png"
    target.write_bytes(b"old")
    panel = {"x": X, "series": {"a": _series([1.0, 2.0, 3.0])}}
    with pytest.raises(FileExistsError):
        pl.plot_expected_vs_realized(target, panel, title="x")
    assert target.read_bytes() == b"old"


def test_series_length_is_checked(tmp_path: Path) -> None:
    panel = {"x": X, "series": {"a": _series([1.0, 2.0])}}
    with pytest.raises(ValueError, match="one value per x"):
        pl.plot_expected_vs_realized(tmp_path / "bad.png", panel, title="x")
