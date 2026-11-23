"""run_solver without layer data: configuration, refusals, development-only choice, exploratory label, synthetic period."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from flight_delay.modeling import final_lock as fl
from flight_delay.modeling.run_baselines import _jsonable
from flight_delay.modeling.splits import FinalTestAccessError
from flight_delay.optimization import run_solver as rs


def test_config_validation() -> None:
    assert rs.SolverConfig().validate() == []
    assert rs.SolverConfig(lp_formulation="dense").validate()
    assert rs.SolverConfig(solver="cbc").validate()
    assert rs.SolverConfig(mixture_candidate_levels=(0.5, 0.97)).validate()
    assert rs.SolverConfig(milp_time_limit_s=0).validate()
    assert rs.SolverConfig(levels=(0.5, 0.97)).validate()


def _manifest(tmp_path: Path) -> Path:
    pre = tmp_path / "pre.md"
    pre.write_text("pre-registration\n", encoding="utf-8")
    manifest = {
        "schema": fl.MANIFEST_SCHEMA,
        "git_commit": "0" * 40,
        "pre_registration": {"path": str(pre), "sha256": fl.sha256_file(pre)},
        "entries": {},
        "bootstrap": {"replicates": 1000, "seed": 42, "level": 0.95},
        "holm_alpha": 0.05,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_preflight_refuses_and_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(fl.LockVerificationError) as error:
        rs.preflight(
            _manifest(tmp_path),
            config=rs.SolverConfig(plots=False, lp=False, milp=False),
            lock_file=tmp_path / "lock.json",
            base=tmp_path,
            output_dir=tmp_path / "out",
            first_run_dir=tmp_path / "first",
            stamp="20990101T000000Z",
        )
    message = str(error.value)
    assert "roles missing" in message and "first-run file missing" in message
    assert not (tmp_path / "out").exists()


def test_dry_run_refused_writes_nothing(tmp_path: Path) -> None:
    argv = [
        "--dry-run",
        "--manifest", str(_manifest(tmp_path)),
        "--lock-file", str(tmp_path / "lock.json"),
        "--output-dir", str(tmp_path / "out"),
        "--first-run-dir", str(tmp_path / "first"),
        "--no-plots", "--no-lp", "--no-milp",
    ]  # fmt: skip
    with pytest.raises(fl.LockVerificationError):
        rs.main(argv)
    assert not (tmp_path / "out").exists()


def _period(curve_rates: dict[str, list[float]], gaps: dict[str, list[float]], last_day: str) -> dict[str, Any]:
    curve = {}
    for i, beta in enumerate((1.0, 5.0)):
        curve[f"b{beta:g}"] = {
            "expected_vs_realized": {
                rs.KNAPSACK_POLICY[d]: {"realized_rate": curve_rates[d][i], "gap_realized_minus_expected": gaps[d][i]}
                for d in curve_rates
            }
        }
    return {"design": {"first_day": "2025-11-01", "last_day": last_day}, "solver": {"curve": curve}}


def test_distribution_choice_rule() -> None:
    rates = {"vincentize": [0.22, 0.19], "mixture": [0.21, 0.18]}
    gaps = {"vincentize": [0.0, 0.01], "mixture": [0.0, 0.0]}
    chosen, record = rs.select_cell_distribution(_period(rates, gaps, "2026-02-28"))
    assert chosen == "mixture" and record["reason"] == "realised ArrDel15"
    tied = {"vincentize": [0.20, 0.18], "mixture": [0.20, 0.18 + 5e-5]}
    chosen, record = rs.select_cell_distribution(_period(tied, gaps, "2026-02-28"))
    assert chosen == "mixture" and "gap" in record["reason"]
    chosen, _ = rs.select_cell_distribution(_period(tied, {"vincentize": [0, 0], "mixture": [0, 0]}, "2026-02-28"))
    assert chosen == "vincentize"


def test_distribution_choice_refuses_final_test_days() -> None:
    rates = {"vincentize": [0.22, 0.19], "mixture": [0.21, 0.18]}
    with pytest.raises(FinalTestAccessError):
        rs.select_cell_distribution(_period(rates, rates, "2026-03-05"))


def test_reproduction_vs_first_run() -> None:
    new = {"levels": {"t080": {"policies": {"plan": {"arr_del15_rate": 0.2, "cost_mean": 1.0}}}}, "budget_curve": {}}
    old = {"levels": {"t080": {"policies": {"plan": {"arr_del15_rate": 0.2, "cost_mean": 1.5}}}}}
    check = rs.reproduction_vs_first_run(new, old)
    assert check["checked"] and check["compared"] == 2 and check["max_abs_diff"] == pytest.approx(0.5)
    assert rs.reproduction_vs_first_run(new, None)["checked"] is False


def _synthetic_rows() -> dict[str, Any]:
    rng = np.random.default_rng(11)
    days = pd.date_range("2025-01-01", "2025-04-30", freq="D").to_numpy(dtype="datetime64[D]")
    per_day = 24
    dates = np.repeat(days, per_day)
    n = dates.size
    origin = np.tile(np.array(["AAA", "BBB"] * (per_day // 2)), days.size)
    dest = np.tile(np.array(["XXX"] * (per_day // 2) + ["YYY"] * (per_day // 2)), days.size)
    minutes = np.tile(np.array([420.0, 780.0] * (per_day // 2)), days.size)
    shift = np.where(origin == "AAA", 8.0, 0.0)
    base = np.array([-15.0, 0.0, 12.0, 25.0, 40.0])
    plan = base[None, :] + shift[:, None] + rng.normal(0, 6, size=(n, 1)) * np.array([0.5, 1.0, 1.0, 1.5, 2.0])
    delay = rng.normal(5.0, 20.0, size=n) + shift
    cancelled = (rng.random(n) < 0.02).astype(float)
    delay[cancelled == 1] = np.nan
    return {
        "flight_uid": np.arange(n),
        "dates": dates,
        "month": dates.astype("datetime64[M]").astype(str),
        "origin": origin,
        "dest": dest,
        "minutes": minutes,
        "crs_elapsed": np.full(n, 90.0),
        "carrier": np.where(rng.random(n) < 0.5, "C1", "C2"),
        "delay": delay,
        "cancelled": cancelled,
        "diverted": np.zeros(n),
        "plan_knots": np.sort(plan, axis=1),
        "b1_knots": np.tile(base + 4.0, (n, 1)),
        "p_cancel": np.full(n, 0.02),
        "crossing": {"plan": 0.0, "b1": 0.0},
    }


def _evaluate(config: rs.SolverConfig) -> dict[str, Any]:
    import flight_delay.optimization.run_buffer as rb

    rows = _synthetic_rows()
    offsets = rb._offsets(rows, [dt.date(2025, 3, 1), dt.date(2025, 4, 1)], config.levels)
    evaluation = np.asarray(rows["dates"] >= np.datetime64("2025-03-01"))
    return rs._period("dogrulama", rb._take(rows, evaluation), offsets, "mean", config)


def _output(period: dict[str, Any]) -> dict[str, Any]:
    chosen, record = rs.select_cell_distribution(period)
    return _jsonable(
        {
            "etiket": rs.EXPLORATORY_LABEL,
            "exploratory_post_hoc": True,
            "metadata": {
                "created_utc": "2099-01-01T00:00:00+00:00",
                "freeze_file": "experiments/or/cozucu-x/cozucu-dondurma.json",
                "aggregator": "mean",
                "cell_distribution": chosen,
                "solver_versions": {},
                "final_test_read": True,
            },
            "verification": {"first_run_reproduction": {}},
            "selection": {"cell_distribution": record},
            "periods": {"dogrulama": period, "test": period},
        }
    )


SMALL = {"levels": (0.5, 0.8, 0.95), "budgets_per_flight": (1.0, 5.0), "replicates": 25}


def test_synthetic_period_without_solvers_label_and_budget(tmp_path: Path) -> None:
    period = _evaluate(rs.SolverConfig(**SMALL, lp=False, milp=False, plots=False))  # type: ignore[arg-type]
    curve = period["solver"]["curve"]
    assert set(curve) == {"b1", "b5"}
    for entry in curve.values():
        assert {"plan_budget", "b1_budget", "plan_arrdel15_budget", "plan_arrdel15_mixture"} <= set(entry["policies"])
        for row in entry["policies"].values():
            assert row["buffer_planned_total_min"] <= entry["budget_total_min"] + 1e-6
        ci = entry["absolute_ci"]["plan_arrdel15_mixture"]["arr_del15_rate"]
        assert ci["ci_low"] <= ci["ci_high"] and ci["replicates"] == 25
    # the Vincentised knapsack is the first run's policy: same numbers as run_buffer's budget curve
    for key, entry in curve.items():
        first = period["budget_curve"][key]["policies"]["plan_arrdel15_budget"]["arr_del15_rate"]
        assert entry["policies"]["plan_arrdel15_budget"]["arr_del15_rate"] == pytest.approx(first)
    output = _output(period)
    text = rs.render(output)
    assert text.splitlines()[0] == f"**Etiket: {rs.EXPLORATORY_LABEL}.**"
    assert next(iter(output)) == "etiket"
    assert "C1" not in text and "C2" not in text
    pytest.importorskip("matplotlib")
    written = rs.make_plots(output, tmp_path / "grafikler")
    assert len(written) == 6 and all(p.is_file() for p in written)


def test_synthetic_period_with_pyomo_solvers() -> None:
    pytest.importorskip("pyomo")
    pytest.importorskip("highspy")
    period = _evaluate(rs.SolverConfig(**SMALL, plots=False, lp_max_segment_min=1.0))  # type: ignore[arg-type]
    for entry in period["solver"]["curve"].values():
        check = entry["allocations"]["plan_budget"]["lp_cross_check"]
        if check["closed_form_status"] == "binding":
            assert check["agrees"], check
        for policy in rs.KNAPSACK_POLICY.values():
            alloc = entry["allocations"][policy]
            milp = alloc["milp"]
            assert milp["valid"]
            assert alloc["lp_value"] - 1e-6 <= milp["value"] <= alloc["value"] + 1e-6
