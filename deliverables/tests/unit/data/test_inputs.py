"""M5 tests: a missing input file is a clear error, never silently ignored (offline)."""

import json

import pytest

from flight_delay.data import inputs, layer, quality


def test_require_file_names_the_option(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"--my-option"):
        inputs.require_file(tmp_path / "nope.json", "some file", "--my-option")
    existing = tmp_path / "yes.json"
    existing.write_text("{}", encoding="utf-8")
    assert inputs.require_file(existing, "some file", "--my-option") == existing


def test_tz_overrides_missing_file_is_an_error_but_none_is_an_explicit_opt_out(tmp_path):
    with pytest.raises(FileNotFoundError, match="time zone overrides"):
        layer.load_tz_overrides(tmp_path / "missing.json")
    assert layer.load_tz_overrides(None) == {}
    path = tmp_path / "tz.json"
    path.write_text(json.dumps({"ORD": "America/Chicago"}), encoding="utf-8")
    assert layer.load_tz_overrides(path) == {"ORD": "America/Chicago"}


def test_missing_target_list_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="target airport list"):
        layer.read_targets(tmp_path / "missing.txt")


def test_missing_airports_file_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="airports"):
        layer.load_airports(tmp_path / "missing.csv")


def _airports_csv(path):
    path.write_text(
        "ident,type,latitude_deg,longitude_deg,iata_code,scheduled_service\nKORD,large_airport,41.97,-87.9,ORD,yes\n",
        encoding="utf-8",
    )
    return path


def test_layer_cli_fails_on_missing_tz_overrides_unless_opted_out(tmp_path, write_ontime_csv):
    csv = write_ontime_csv(tmp_path / "raw.csv")
    targets = tmp_path / "targets.txt"
    targets.write_text("ORD\nATL\n", encoding="utf-8")
    common = [
        "--input",
        str(csv),
        "--year",
        "2025",
        "--month",
        "7",
        "--layer-dir",
        str(tmp_path / "layer"),
        "--targets-file",
        str(targets),
        "--ourairports",
        str(_airports_csv(tmp_path / "airports.csv")),
    ]
    with pytest.raises(FileNotFoundError, match="tz-overrides"):
        layer.main([*common, "--tz-overrides", str(tmp_path / "missing.json")])
    assert not (tmp_path / "layer").exists()  # nothing was written before the error
    assert layer.main([*common, "--no-tz-overrides"]) == 0  # explicit opt-out works


def test_quality_cli_fails_on_missing_targets_and_previous_report(tmp_path, fake_ontime, process_fake_month):
    root, _ = process_fake_month(tmp_path, df=fake_ontime.query("Dest != 'ZZZ'"))
    out = ["--output-json", str(tmp_path / "r.json"), "--output-md", str(tmp_path / "r.md")]
    with pytest.raises(FileNotFoundError, match="target airport list"):
        quality.main(["--layer-dir", str(root), "--targets-file", str(tmp_path / "missing.txt"), *out])
    targets = tmp_path / "targets.txt"
    targets.write_text("ORD\nATL\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="previous quality report"):
        quality.main(
            ["--layer-dir", str(root), "--targets-file", str(targets), "--previous", str(tmp_path / "gone.json"), *out]
        )
    # explicit opt-out of the scope check: runs without a target file
    assert (
        quality.main(["--layer-dir", str(root), "--targets-file", str(tmp_path / "missing.txt"), "--no-targets", *out])
        == 0
    )
