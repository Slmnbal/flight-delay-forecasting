"""PNG figures of the solver run (formulation section 17.6). matplotlib is imported inside the functions (Agg backend).

Rules: no carrier, no logo; Turkish axis labels; colour-blind safe Okabe-Ito palette plus distinct line styles and
markers; a figure is never written over an existing file (FileExistsError). Inputs are plain dictionaries of
numbers taken from the results JSON (``run_solver``), so the functions can be tested without data.

Series format (every list has one value per x):
    {"x": [...], "series": {name: {"y": [...], "low": [...] | None, "high": [...] | None, "label": str,
                                   "style": "solid" | "dashed"}}}
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = ["OKABE_ITO", "line_panels", "plot_budget_curve", "plot_expected_vs_realized", "plot_level_sensitivity"]

OKABE_ITO: tuple[str, ...] = ("#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#000000", "#F0E442")
_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")


def _pyplot() -> Any:
    matplotlib = importlib.import_module("matplotlib")
    matplotlib.use("Agg")
    return importlib.import_module("matplotlib.pyplot")


def line_panels(
    path: Path,
    panels: Sequence[Mapping[str, Any]],
    *,
    title: str,
    x_label: str,
    note: str | None = None,
    dpi: int = 150,
) -> Path:
    """One row of line panels; each panel: {"x", "series", "y_label"} (module docstring). Returns ``path``."""
    target = Path(path)
    if target.exists():
        raise FileExistsError(f"will not overwrite: {target}")
    if not panels:
        raise ValueError("at least one panel is required")
    plt = _pyplot()
    figure, axes = plt.subplots(1, len(panels), figsize=(5.2 * len(panels), 4.2), squeeze=False)
    for axis, panel in zip(axes[0], panels, strict=True):
        x = [float(v) for v in panel["x"]]
        for i, (name, series) in enumerate(panel["series"].items()):
            colour = OKABE_ITO[i % len(OKABE_ITO)]
            y = [float("nan") if v is None else float(v) for v in series["y"]]
            if len(y) != len(x):
                raise ValueError(f"{name}: one value per x is required")
            axis.plot(
                x,
                y,
                color=colour,
                linestyle="--" if series.get("style") == "dashed" else "-",
                marker=_MARKERS[i % len(_MARKERS)],
                markersize=4,
                linewidth=1.6,
                label=str(series.get("label", name)),
            )
            low, high = series.get("low"), series.get("high")
            if low is not None and high is not None:
                lows = [float("nan") if v is None else float(v) for v in low]
                highs = [float("nan") if v is None else float(v) for v in high]
                axis.fill_between(x, lows, highs, color=colour, alpha=0.18, linewidth=0)
        axis.set_xlabel(x_label)
        axis.set_ylabel(str(panel["y_label"]))
        axis.grid(True, alpha=0.3)
        axis.legend(fontsize=8, frameon=False)
    figure.suptitle(title, fontsize=11)
    if note:
        figure.text(0.01, 0.01, note, fontsize=7, ha="left", va="bottom")
    figure.tight_layout(rect=(0, 0.04 if note else 0, 1, 0.95))
    target.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(target, dpi=dpi)
    plt.close(figure)
    return target


def plot_budget_curve(
    path: Path, arr_del15: Mapping[str, Any], residual: Mapping[str, Any], *, title: str, note: str | None = None
) -> Path:
    """(a) budget curve: ArrDel15 and remaining delay per flight vs planned minutes per flight (95 % CI bands)."""
    return line_panels(
        path,
        [
            {**arr_del15, "y_label": "ArrDel15 oranı (tampon sonrası)"},
            {**residual, "y_label": "Kalan varış rötarı (dk/uçuş)"},
        ],
        title=title,
        x_label="Bütçe: ek tampon (dk / tarifeli uçuş)",
        note=note,
    )


def plot_level_sensitivity(
    path: Path,
    cost: Mapping[str, Any],
    added: Mapping[str, Any],
    arr_del15: Mapping[str, Any],
    *,
    title: str,
    note: str | None = None,
) -> Path:
    """(b) tau sensitivity: cost per flight, added buffer per flight and ArrDel15 vs the critical ratio."""
    return line_panels(
        path,
        [
            {**cost, "y_label": "Maliyet (ağırlıklı dk/uçuş, varsayım)"},
            {**added, "y_label": "Eklenen tampon (dk/uçuş)"},
            {**arr_del15, "y_label": "ArrDel15 oranı (tampon sonrası)"},
        ],
        title=title,
        x_label="Kritik oran τ = c_u / (c_u + c_o)",
        note=note,
    )


def plot_expected_vs_realized(path: Path, arr_del15: Mapping[str, Any], *, title: str, note: str | None = None) -> Path:
    """(c) knapsack: expected (model) vs realised ArrDel15 per budget and cell distribution."""
    return line_panels(
        path,
        [{**arr_del15, "y_label": "ArrDel15 oranı"}],
        title=title,
        x_label="Bütçe: ek tampon (dk / tarifeli uçuş)",
        note=note,
    )
