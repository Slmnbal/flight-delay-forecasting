"""run_buffer without layer data: periods, configuration, preflight refusals and one synthetic period end to end."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flight_delay.modeling import final_lock as fl
from flight_delay.modeling.run_baselines import _jsonable
from flight_delay.optimization import policies as pol
from flight_delay.optimization import run_buffer as rb


def test_development_months_have_out_of_sample_conformal_windows() -> None:
    months = rb.development_eval_months(dt.date(2025, 8, 31))
    assert [f"{m:%Y-%m}" for m in months] == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_config_validation() -> None:
    assert rb.BufferConfig().validate() == []
    assert rb.BufferConfig(levels=(0.5, 0.97)).validate()
    assert rb.BufferConfig(publish_level=0.83).validate()
    assert rb.BufferConfig(publish_policy="b1").validate()
    assert rb.BufferConfig(levels=(0.8, 0.5), publish_level=0.8).validate()


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


def _preflight(tmp_path: Path, **overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "config": rb.BufferConfig(),
        "lock_file": tmp_path / "lock.json",
        "base": tmp_path,
        "output_dir": tmp_path / "out",
        "data_output_dir": tmp_path / "data",
        "stamp": "20990101T000000Z",
    }
    kwargs.update(overrides)
    return rb.preflight(_manifest(tmp_path), **kwargs)  # type: ignore[arg-type]


def test_preflight_refuses_without_roles_and_lock(tmp_path: Path) -> None:
    with pytest.raises(fl.LockVerificationError) as error:
        _preflight(tmp_path)
    message = str(error.value)
    assert "roles missing" in message
    assert "lock record missing" in message
    assert not (tmp_path / "out").exists()


def test_preflight_refuses_a_lock_of_another_manifest(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"manifest": {"sha256": "not-this-one"}}), encoding="utf-8")
    with pytest.raises(fl.LockVerificationError, match="different freeze manifest"):
        _preflight(tmp_path, lock_file=lock)


def test_preflight_never_overwrites_an_output_folder(tmp_path: Path) -> None:
    (tmp_path / "out" / "tampon-20990101T000000Z").mkdir(parents=True)
    with pytest.raises(fl.LockVerificationError, match="will not overwrite"):
        _preflight(tmp_path, config=rb.BufferConfig(development_only=True))


def test_dry_run_reads_and_writes_nothing_when_refused(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    argv = [
        "--dry-run",
        "--manifest", str(manifest),
        "--lock-file", str(tmp_path / "lock.json"),
        "--output-dir", str(tmp_path / "out"),
        "--data-output-dir", str(tmp_path / "data"),
    ]  # fmt: skip
    with pytest.raises(fl.LockVerificationError):
        rb.main(argv)
    assert not (tmp_path / "out").exists() and not (tmp_path / "data").exists()


def _synthetic_rows() -> dict[str, object]:
    rng = np.random.default_rng(11)
    days = pd.date_range("2025-01-01", "2025-04-30", freq="D").to_numpy(dtype="datetime64[D]")
    per_day = 24
    dates = np.repeat(days, per_day)
    n = dates.size
    origin = np.tile(np.array(["AAA", "BBB"] * (per_day // 2)), days.size)
    dest = np.tile(np.array(["XXX"] * (per_day // 2) + ["YYY"] * (per_day // 2)), days.size)
    minutes = np.tile(np.array([420.0, 780.0] * (per_day // 2)), days.size)
    level_shift = np.where(origin == "AAA", 8.0, 0.0)
    base = np.array([-15.0, 0.0, 12.0, 25.0, 40.0])
    plan = base[None, :] + level_shift[:, None] + rng.normal(0, 2, size=(n, 1))
    delay = rng.normal(5.0, 20.0, size=n) + level_shift
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


def test_synthetic_period_end_to_end_without_carrier_and_within_budget() -> None:
    rows = _synthetic_rows()
    config = rb.BufferConfig(levels=(0.5, 0.8, 0.95), budgets_per_flight=(1.0, 5.0), replicates=25)
    months = [dt.date(2025, 3, 1), dt.date(2025, 4, 1)]
    offsets = rb._offsets(rows, months, config.levels)  # context rows: January and February
    evaluation = rows["dates"] >= np.datetime64("2025-03-01")  # type: ignore[operator]
    eval_rows = rb._take(rows, np.asarray(evaluation))
    result = rb._evaluate_period("test", eval_rows, offsets, "mean", config, build_tables=True)
    summary = result.summary
    assert set(summary["levels"]) == {"t050", "t080", "t095"}
    policies = summary["levels"]["t080"]["policies"]
    assert {pol.POLICY_NONE, pol.POLICY_B1, pol.POLICY_PLAN, pol.POLICY_PLAN_CONFORMAL} <= set(policies)
    assert summary["counts"]["cancelled"] > 0
    for entry in summary["budget_curve"].values():
        for row in entry["policies"].values():
            assert row["buffer_planned_total_min"] <= entry["budget_total_min"] + 1e-6
    assert result.cell_frame is not None and result.flight_columns is not None
    pol.assert_no_forbidden_columns(result.cell_frame)
    flights = pol.flight_table(result.flight_columns)
    assert "carrier" not in flights.columns and "Reporting_Airline" not in flights.columns
    assert not flights.isin(["C1", "C2"]).any().any()
    assert not result.cell_frame.isin(["C1", "C2"]).any().any()
    output = {
        "metadata": {
            "created_utc": "2099-01-01T00:00:00+00:00",
            "freeze_file": "experiments/or/x/politika-dondurma.json",
            "manifest": {"path": "experiments/son-test-dondurma.json"},
            "roles": ["arr_delay/plan"],
            "aggregator": "mean",
            "config": config.to_dict(),
            "final_test_read": True,
        },
        "selection": {"candidates": {"mean": {"cost_mean_over_levels": 1.0}}},
        "verification": {},
        "periods": {"test": summary},
    }
    text = rb.render(_jsonable(output))
    assert "τ = 0.80" in text and "yayım düzeyi" in text
    assert "C1" not in text and "C2" not in text
