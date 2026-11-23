"""Tests of the static-site interface export helpers (``interface_export``). Synthetic inputs only, no real data.

The real contract ``experiments/arayuz-sozlesmesi.json`` is read (it is part of the repository); every file type built
from small fake final-test results must pass it.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from flight_delay.modeling import final_eval as fe
from flight_delay.modeling import interface_export as ie
from flight_delay.modeling import metrics as mt

CREATED = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.UTC)
VERSION = "son-test-20261122T105048Z@25ebfb622117"


@pytest.fixture(scope="module")
def validator() -> ie.SchemaValidator:
    return ie.SchemaValidator.from_file(ie.DEFAULT_SCHEMA_FILE)


# ----------------------------------------------------------------------------
# fake inputs
# ----------------------------------------------------------------------------


def _boot(estimate: float, low: float, high: float) -> dict:
    return {"estimate": estimate, "ci_low": low, "ci_high": high, "p_value": 0.0, "level": 0.95}


def _cls_segment(code: str, n: int) -> dict:
    return {
        "segment": code,
        "n": n,
        "prevalence": 0.2512345,
        "mean_pred": 0.2634567,
        "calibration_in_the_large": 0.0122222,
        "brier": 0.1712345,
        "brier_skill_score": 0.05 if code != "ORD" else 0.02,
        "roc_auc": 0.7012345,
        "pr_auc": 0.4512345,
    }


def _classifier_section(prevalence: float, *, slope: bool = False) -> dict:
    prob = {
        "n": 1000.0,
        "prevalence": prevalence,
        "mean_pred": prevalence + 0.0011,
        "brier": 0.17157214,
        "log_loss": 0.5192752,
        "ece": 0.0052034,
        "calibration_in_the_large": -0.0024589,
        "calibration_intercept": 0.0163371,
        "calibration_slope": 1.0020632,
    }
    f1 = {
        "precision": 0.3887786,
        "recall": 0.6942009,
        "f1": 0.4984221,
        "threshold_min": 0.2036809,
        "threshold_max": 0.2036809,
    }
    section = {
        "n": 1000,
        "prevalence": prevalence,
        "raw": {
            "model": {"roc_auc": 0.71200714, "pr_auc": 0.47670421},
            "B1": {"roc_auc": 0.65641366, "pr_auc": 0.37543346},
        },
        "f1_at_frozen_threshold": {"model": f1, "B1": dict(f1, f1=0.4637314)},
        "probability": {fe.PRIMARY_PROBABILITY: {"model": prob, "B1": dict(prob, brier=0.18300375)}},
        "bootstrap": {"citl_platt": _boot(-0.0024589, -0.0104591, 0.0055499)},
        "segments_platt": {
            "Origin": [_cls_segment("ATL", 1200), _cls_segment("ORD", 900), _cls_segment("XXX", 40)],
            "hour_block": [_cls_segment("0", 400), _cls_segment("1", 600), _cls_segment("-1", 100)],
            "month": [_cls_segment("2026-03", 500), _cls_segment("2026-04", 500)],
        },
        "event_days": {
            "event_days": {
                "n": 300,
                "days": 3,
                "prevalence": 0.4070761,
                "mean_pred_platt": 0.3,
                "brier_platt": 0.2178580,
                "brier_platt_B1": 0.2515397,
                "roc_auc_raw": 0.7217356,
                "roc_auc_raw_B1": 0.6847177,
            },
            "other_days": {
                "n": 700,
                "days": 7,
                "prevalence": 0.2483001,
                "mean_pred_platt": 0.25,
                "brier_platt": 0.1669818,
                "brier_platt_B1": 0.1762068,
                "roc_auc_raw": 0.7070688,
                "roc_auc_raw_B1": 0.6548251,
            },
        },
    }
    if slope:
        section["bootstrap"]["slope_platt"] = _boot(1.0020632, 0.9665600, 1.0367293)
    return section


def _q_segment(code: str, n: int) -> dict:
    return {
        "segment": code,
        "n": n,
        "pinball_q050": 12.0666105,
        "pinball_q080": 13.3965339,
        "pinball_q095": 8.2000990,
        "coverage_raw_q080": 0.7565918 if code != "ORD" else 0.7012,
        "coverage_raw_q095": 0.9225955,
    }


def _month_row(month: str, n: int) -> dict:
    return {
        "month": month,
        "n": n,
        "coverage_raw_q080": 0.7680504,
        "coverage_raw_q080_B1": 0.7677923,
        "coverage_rolling_q080": 0.7757539,
        "coverage_static_q080": 0.7768932,
        "coverage_raw_q095": 0.9316852,
        "coverage_raw_q095_B1": 0.9322770,
        "coverage_rolling_q095": 0.9356686,
        "coverage_static_q095": 0.9360336,
    }


def _quantile_section() -> dict:
    raw = {
        "pinball_q050": 13.4758731,
        "pinball_q080": 14.4679031,
        "pinball_q095": 8.7515381,
        "mae_q050": 26.9517462,
        "coverage_q080": 0.7697612,
        "coverage_q095": 0.9373308,
        "crossing_rate": 0.0,
    }
    rolling = {
        "q080": {"coverage": 0.7876904, "monthly_coverage": {"2026-03": 0.7757539, "2026-04": 0.8314244}},
        "q095": {"coverage": 0.9446800, "monthly_coverage": {"2026-03": 0.9356686, "2026-04": 0.9651996}},
        "interval80": {"coverage": 0.7956118, "mean_width_min": 70.6073900},
    }
    return {
        "n": 1000,
        "raw": {"model": raw, "B1": dict(raw, pinball_q080=14.6847400)},
        "conformal": {"model": {"rolling": rolling}, "B1": {"rolling": copy.deepcopy(rolling)}},
        "bootstrap": {
            "coverage_rolling_q080": _boot(0.7876904, 0.7773259, 0.7978371),
            "coverage_rolling_q095": _boot(0.9446800, 0.9398416, 0.9490928),
        },
        "monthly": [_month_row("2026-03", 500), _month_row("2026-04", 500), _month_row("2026-05", 30)],
        "segments": {
            "Origin": [_q_segment("ATL", 1200), _q_segment("ORD", 900), _q_segment("XXX", 40)],
            "hour_block": [_q_segment("0", 400), _q_segment("1", 600)],
            "month": [_q_segment("2026-03", 500), _q_segment("2026-04", 500)],
        },
    }


def _fake_results() -> dict:
    criteria = {f"K{i}": {"passed": i not in (5, 6), "description": f"Ölçüt {i} tanımı"} for i in range(1, 8)}
    return {
        "metadata": {
            "mode": "final_test",
            "created_utc": "2026-11-22T10:50:48.968766+00:00",
            "git": {"head": "25ebfb622117a37c7a56ed22317eaa1f73725971"},
            "periods": {
                "fit": {"start": "2023-09-01", "end": "2025-08-31"},
                "static_calibration": {"start": "2026-01-01", "end": "2026-02-28"},
                "final_test": {"start": "2026-03-01", "end": "2026-08-31"},
            },
        },
        "blocks": {
            "final_test": {
                "days": {"n": 184},
                "rows": {"classifiers": {fe.ROLE_CANCELLED_PLAN: {"n": 1100}}},
                "classification": {
                    fe.ROLE_ARR_DEL15_T2: _classifier_section(0.2626258, slope=True),
                    fe.ROLE_ARR_DEL15_PLAN: _classifier_section(0.2626258),
                    fe.ROLE_CANCELLED_PLAN: _classifier_section(0.0188252),
                },
                "quantile": {fe.ROLE_QUANTILES_PLAN: _quantile_section(), fe.ROLE_QUANTILES_T2: _quantile_section()},
                "comparisons": {
                    fe.ROLE_ARR_DEL15_T2: {
                        "vs_B1": {
                            "d_roc_auc": _boot(0.0555935, 0.0498793, 0.0612178),
                            "d_pr_auc": _boot(0.1012708, 0.0915387, 0.1105309),
                            "bss_platt": _boot(0.0624665, 0.0541025, 0.0712064),
                        }
                    },
                    "weather_contribution": {
                        "arr_del15": {
                            "d_roc_auc": _boot(0.0362689, 0.0314522, 0.0410202),
                            "d_pr_auc": _boot(0.0710666, 0.0617562, 0.0800331),
                            "d_brier_platt": _boot(-0.0082927, -0.0097853, -0.0068654),
                        },
                        "arr_delay": {"d_pinball_q080": _boot(-0.7559961, -0.9016609, -0.6163101)},
                        "oracle": "not part of the final test (no oracle model is locked)",
                    },
                },
                "criteria": criteria,
            }
        },
    }


AIRPORTS = [
    {
        "iata": "ATL",
        "ad": "Hartsfield Jackson Atlanta International Airport",
        "enlem": 33.6367,
        "boylam": -84.428101,
        "saat_dilimi": "America/New_York",
    },
    {
        "iata": "ORD",
        "ad": "Chicago O'Hare International Airport",
        "enlem": 41.9786,
        "boylam": -87.9048,
        "saat_dilimi": "America/Chicago",
    },
]


def _route_row(**overrides: object) -> dict:
    row = {
        "origin": "ATL",
        "dest": "LGA",
        "saat_blogu": "06-09",
        "mevsim": "yaz",
        "n_ucus": 120,
        "n_tamamlanan": 118,
        "n_iptal": 2,
        "crs_elapsed_medyan_dk": 135.0,
        "gozlenen_arrdel15_tamponsuz": 0.25,
        "plan_q010_dk": -20.0,
        "plan_q050_dk": -5.0,
        "plan_q080_dk": 12.0,
        "plan_q090_dk": 30.0,
        "plan_q095_dk": 50.0,
        "tek_tasiyici_yogun": False,
        "yayimlanabilir": True,
        "tampon_onerisi_dk": 10.26,
        "n_arrdel15": 118,
        "gozlenen_arrdel15_orani": 0.2542373,
        "tahmin_arrdel15_orani": 0.2612345,
        "n_kantil": 118,
        "kantil_p50": -5.04,
        "kantil_p80": 12.06,
        "kantil_p95": 49.96,
        "kantil_conf_p80": 13.1,
        "kantil_conf_p95": 55.55,
        "aralik80_alt": -21.0,
        "aralik80_ust": 31.0,
        "kapsama_p80": 0.8135593,
        "kapsama_p95": 0.9576271,
    }
    row.update(overrides)
    return row


def _payloads(results: dict | None = None) -> dict[str, dict]:
    results = results or _fake_results()
    y = np.r_[np.zeros(600), np.ones(400)]
    p = np.linspace(0.05, 0.9, 1000)
    reliability = [ie.reliability_entry("arrdel15", "lgbm_T2", y, p)]
    by_origin, _ = ie.route_cells(pd.DataFrame([_route_row(), _route_row(dest="BOS", tampon_onerisi_dk=np.nan)]))
    return {
        ie.FILE_PATHS["ozet"]: ie.build_ozet(results, n_airports=2, created=CREATED, version=VERSION),
        ie.FILE_PATHS["havalimanlari"]: ie.build_havalimanlari(
            results, AIRPORTS, created=CREATED, version=VERSION, coverage={"ATL": {"p80": 0.79, "p95": 0.95, "n": 500}}
        ),
        ie.FILE_PATHS["kalibrasyon"]: ie.build_kalibrasyon(
            results,
            created=CREATED,
            version=VERSION,
            reliability=reliability,
            interval_monthly=[{"ay": "2026-03", "kapsama": 0.7956, "n": 500}],
        ),
        ie.FILE_PATHS["hava_deneyi"]: ie.build_hava_deneyi(results, created=CREATED, version=VERSION),
        ie.FILE_PATHS["hata_analizi"]: ie.build_hata_analizi(results, created=CREATED, version=VERSION),
        ie.route_path("ATL"): ie.build_rotalar("ATL", by_origin["ATL"], created=CREATED, version=VERSION),
        ie.route_path("ORD"): ie.build_rotalar("ORD", [], created=CREATED, version=VERSION),
    }


def _metric(payload: dict, task: str, model: str, name: str) -> dict:
    entry = next(e for e in payload["sonuclar"] if e["gorev"] == task and e["model"] == model)
    return next(m for m in entry["metrikler"] if m["ad"] == name)


# ----------------------------------------------------------------------------
# validator
# ----------------------------------------------------------------------------


def test_contract_schema_is_fully_supported(validator: ie.SchemaValidator) -> None:
    assert ie.scan_schema(validator.schema) == []
    assert {"manifest", "ozet", "havalimanlari", "rotalar", "kalibrasyon", "hava_deneyi", "hata_analizi"} <= set(
        validator.definitions()
    )
    assert validator.max_bytes("rotalar") == 300 * 1024


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "patternProperties": {"^a": {}}},
        {"$defs": {"x": {"type": "array", "prefixItems": [{"type": "string"}]}}},
        {"type": "string", "format": "email"},
        {"$ref": "https://example.org/other.json"},
        {"$ref": "#/$defs/missing"},
        {"type": "decimal"},
    ],
)
def test_unsupported_schema_constructs_raise(schema: dict) -> None:
    with pytest.raises(ie.SchemaError):
        ie.SchemaValidator(schema)


def test_every_file_type_passes_the_schema(validator: ie.SchemaValidator) -> None:
    payloads = _payloads()
    files = ie.prepare_site_files(payloads, validator, created=CREATED, version=VERSION)
    assert set(files) == {*payloads, ie.FILE_PATHS["manifest"]}
    for path, payload in payloads.items():
        assert validator.errors(payload, payload["dosya_turu"]) == [], path
        assert validator.errors(payload) == [], path  # root oneOf: exactly one file type matches
        assert json.loads(files[path].decode("utf-8")) == payload
    manifest = json.loads(files[ie.FILE_PATHS["manifest"]])
    assert validator.errors(manifest, "manifest") == []


def test_validator_catches_additional_and_unevaluated_properties(validator: ie.SchemaValidator) -> None:
    payload = _payloads()[ie.FILE_PATHS["havalimanlari"]]
    item_extra = copy.deepcopy(payload)
    item_extra["havalimanlari"][0]["ekstra_alan"] = 1
    assert any("additional property not allowed" in e for e in validator.errors(item_extra, "havalimanlari"))
    top_extra = copy.deepcopy(payload)
    top_extra["ekstra_alan"] = 1
    assert any("unevaluated property not allowed" in e for e in validator.errors(top_extra, "havalimanlari"))
    with pytest.raises(ie.ExportError, match="additional property"):
        ie.prepare_site_files({ie.FILE_PATHS["havalimanlari"]: item_extra}, validator, created=CREATED, version=VERSION)


def test_validator_types_ranges_enums_and_conditionals(validator: ie.SchemaValidator) -> None:
    route = _payloads()[ie.route_path("ATL")]
    bad = copy.deepcopy(route)
    bad["hucreler"][0]["n_ucus"] = 49
    bad["hucreler"][0]["saat_blogu"] = "05-07"
    errors = validator.errors(bad, "rotalar")
    assert any("minimum 50" in e for e in errors)
    assert any("is not one of" in e for e in errors)
    as_float = copy.deepcopy(route)
    as_float["hucreler"][0]["n_ucus"] = 120.0  # JSON integer
    assert validator.errors(as_float, "rotalar") == []
    as_bool = copy.deepcopy(route)
    as_bool["hucreler"][0]["n_ucus"] = True
    assert validator.errors(as_bool, "rotalar")
    weather = _payloads()[ie.FILE_PATHS["hava_deneyi"]]
    oracle = {"varyant": "oracle", "oracle": True, "etiket": "Gözlenmiş hava", "metrikler": []}
    with_oracle = copy.deepcopy(weather)
    with_oracle["varyantlar"].append(oracle)
    assert any("does not match" in e for e in validator.errors(with_oracle, "hava_deneyi"))  # 'Üst sınır' required
    with_oracle["varyantlar"][-1]["etiket"] = "Oracle: üst sınır (gerçekte elde edilemez)"
    assert validator.errors(with_oracle, "hava_deneyi") == []
    summary = _payloads()[ie.FILE_PATHS["ozet"]]
    summary["sonuclar"][0]["model"] = "lgbm_oracle"
    assert any("'not'" in e for e in validator.errors(summary, "ozet"))
    broken_date = _payloads()[ie.FILE_PATHS["ozet"]]
    broken_date["bolme"]["test"]["bitis"] = "2026-02-30"
    assert any("valid date" in e for e in validator.errors(broken_date, "ozet"))


# ----------------------------------------------------------------------------
# presentation rules
# ----------------------------------------------------------------------------


def test_cells_and_segments_with_n_below_50_are_hidden() -> None:
    rows = [
        _route_row(),
        _route_row(dest="BOS", n_ucus=49),
        _route_row(dest="BWI", yayimlanabilir=False, tek_tasiyici_yogun=True),
        _route_row(dest="CLT", n_arrdel15=30),
        _route_row(dest="DCA", saat_blogu=None),
        _route_row(dest="DEN", kantil_p80=np.nan),
    ]
    by_origin, hidden = ie.route_cells(pd.DataFrame(rows))
    assert [c["dest"] for c in by_origin["ATL"]] == ["LGA"]
    assert hidden == {
        "yayimlanamaz": 1,
        "n_ucus_az": 1,
        "tamamlanan_az": 1,
        "anahtar_eksik": 1,
        "eksik_deger": 1,
        "yayimlanan": 1,
    }
    errors = _payloads()[ie.FILE_PATHS["hata_analizi"]]
    origin_segments = next(b for b in errors["boyutlar"] if b["boyut"] == "origin" and b["model"] == "lgbm_T2")
    assert [s["segment"] for s in origin_segments["segmentler"]] == ["ATL", "ORD"]  # XXX (n = 40) hidden
    hours = next(b for b in errors["boyutlar"] if b["boyut"] == "saat_blogu" and b["model"] == "lgbm_T2")
    assert [s["segment"] for s in hours["segmentler"]] == ["00-06", "06-09"]  # code -1 (no hour) hidden
    calibration = _payloads()[ie.FILE_PATHS["kalibrasyon"]]
    assert "2026-05" not in {r["ay"] for r in calibration["kapsama_aylik"]}  # n = 30
    results = _fake_results()
    results["blocks"]["final_test"]["classification"][fe.ROLE_ARR_DEL15_T2]["segments_platt"]["Origin"][0]["n"] = 49
    with pytest.raises(ie.ExportError, match="< 50"):
        ie.build_havalimanlari(results, AIRPORTS, created=CREATED, version=VERSION)


def test_carrier_fields_are_refused(validator: ie.SchemaValidator) -> None:
    with pytest.raises(ie.ExportError, match="forbidden"):
        ie.assert_no_forbidden_keys({"a": [{"tasiyici_payi": 0.5}]})
    payload = _payloads()[ie.FILE_PATHS["havalimanlari"]]
    payload["havalimanlari"][0]["carrier"] = "XX"
    with pytest.raises(ie.ExportError, match="forbidden"):
        ie.prepare_site_files({ie.FILE_PATHS["havalimanlari"]: payload}, validator, created=CREATED, version=VERSION)
    with pytest.raises(ValueError, match="forbidden"):
        ie.route_cells(pd.DataFrame([_route_row(Reporting_Airline="XX")]))
    results = _fake_results()
    t2 = results["blocks"]["final_test"]["classification"][fe.ROLE_ARR_DEL15_T2]
    t2["segments_platt"]["Reporting_Airline"] = [_cls_segment("XX", 500)]
    with pytest.raises(ie.ExportError, match="forbidden"):
        ie.build_hata_analizi(results, created=CREATED, version=VERSION)
    or_table = pd.DataFrame([{c: _route_row()[c] for c in ie.OR_REQUIRED_COLUMNS} | {"carrier_top": "XX"}])
    with pytest.raises(ValueError, match="forbidden"):
        ie.check_or_table(or_table)


def test_rounding_rules() -> None:
    assert ie.round_value(12.345678, "dakika") == 12.3
    assert ie.round_value(0.1234567, "oran") == 0.123
    assert ie.round_value(0.71200714, "skor") == 0.712
    negative_zero = ie.round_value(-0.00001, "oran")
    assert negative_zero == 0.0 and json.dumps(negative_zero) == "0.0"
    assert ie.round_value(float("nan"), "oran") is None
    assert ie.round_value(None, "dakika") is None
    with pytest.raises(ValueError):
        ie.round_value(1.0, "saat")
    entry = ie.metric("pinball_p80", 14.4679, "dakika", ci={"ci_low": 14.01, "ci_high": 14.96})
    assert entry == {"ad": "pinball_p80", "deger": 14.5, "ga95_alt": 14.0, "ga95_ust": 15.0, "birim": "dakika"}
    cell = ie.route_cells(pd.DataFrame([_route_row()]))[0]["ATL"][0]
    assert cell["kantil_dk"] == {"p50": -5.0, "p80": 12.1, "p95": 50.0}
    assert cell["kapsama"] == {"p80": 0.814, "p95": 0.958}
    assert cell["iptal_orani"] == round(2 / 120, 3)
    assert cell["tampon_onerisi_dk"] == 10.3


def test_manifest_lists_bytes_and_sha256(validator: ie.SchemaValidator) -> None:
    files = ie.prepare_site_files(_payloads(), validator, created=CREATED, version=VERSION)
    manifest = json.loads(files[ie.FILE_PATHS["manifest"]])
    listed = {e["yol"]: e for e in manifest["dosyalar"]}
    assert set(listed) == set(files) - {ie.FILE_PATHS["manifest"]}
    for path, entry in listed.items():
        assert entry["sha256"] == hashlib.sha256(files[path]).hexdigest()
        assert entry["bayt"] == len(files[path])
    assert manifest["toplam_bayt"] == sum(len(files[p]) for p in listed)
    assert manifest["olusturma_zamani"] == "2026-11-22T12:00:00+00:00"


def test_size_limit_is_enforced(validator: ie.SchemaValidator) -> None:
    schema = copy.deepcopy(validator.schema)
    schema["$defs"]["ozet"]["x-azami-boyut-kb"] = 0.5
    small = ie.SchemaValidator(schema)
    payload = _payloads()[ie.FILE_PATHS["ozet"]]
    with pytest.raises(ie.ExportError, match="limit"):
        ie.prepare_site_files({ie.FILE_PATHS["ozet"]: payload}, small, created=CREATED, version=VERSION)
    warnings: list[str] = []
    files = ie.prepare_site_files(
        {ie.FILE_PATHS["ozet"]: payload}, small, created=CREATED, version=VERSION, strict_sizes=False, warnings=warnings
    )
    assert len(warnings) == 1 and "veri/ozet.json" in warnings[0] and ie.FILE_PATHS["ozet"] in files
    schema["$defs"]["manifest"]["properties"]["toplam_bayt"]["maximum"] = 100
    with pytest.raises(ie.ExportError, match="toplam_bayt|total"):  # the 10 MB total is always a hard limit
        ie.prepare_site_files(
            {ie.FILE_PATHS["ozet"]: payload},
            ie.SchemaValidator(schema),
            created=CREATED,
            version=VERSION,
            strict_sizes=False,
            warnings=[],
        )


def test_write_site_never_overwrites(tmp_path, validator: ie.SchemaValidator) -> None:
    files = ie.prepare_site_files(_payloads(), validator, created=CREATED, version=VERSION)
    out = tmp_path / "web" / "veri"
    ie.write_site(files, out, stamp="20261122T120000Z")
    for path, data in files.items():
        assert (out / path[len("veri/") :]).read_bytes() == data
    assert not list(out.parent.glob(".veri.yaziliyor-*"))
    with pytest.raises(ie.ExportError, match="will not overwrite"):
        ie.write_site(files, out, stamp="20261122T120001Z")
    empty = tmp_path / "bos"
    empty.mkdir()
    with pytest.raises(ie.ExportError, match="will not overwrite"):
        ie.write_site(files, empty, stamp="20261122T120002Z")


# ----------------------------------------------------------------------------
# no tuning: source numbers pass through (rounded only)
# ----------------------------------------------------------------------------


def test_source_numbers_pass_through_unchanged() -> None:
    results = _fake_results()
    before = copy.deepcopy(results)
    payloads = _payloads(results)
    assert results == before  # builders never modify their input
    summary = payloads[ie.FILE_PATHS["ozet"]]
    block = results["blocks"]["final_test"]
    t2 = block["classification"][fe.ROLE_ARR_DEL15_T2]
    assert _metric(summary, "arrdel15", "lgbm_T2", "roc_auc")["deger"] == round(t2["raw"]["model"]["roc_auc"], 4)
    bss = block["comparisons"][fe.ROLE_ARR_DEL15_T2]["vs_B1"]["bss_platt"]
    assert _metric(summary, "arrdel15", "lgbm_T2", "brier_skill") == ie.metric(
        "brier_skill", bss["estimate"], "skor", ci=bss
    )
    slope = t2["bootstrap"]["slope_platt"]
    assert _metric(summary, "arrdel15", "lgbm_T2", "kalibrasyon_egimi")["ga95_alt"] == round(slope["ci_low"], 4)
    plan = block["quantile"][fe.ROLE_QUANTILES_PLAN]
    conf = _metric(summary, "kantil", "lgbm_plan", "kapsama_p80_conf")
    assert conf["deger"] == round(plan["bootstrap"]["coverage_rolling_q080"]["estimate"], 3)
    assert _metric(summary, "kantil", "B1", "pinball_p80")["deger"] == round(plan["raw"]["B1"]["pinball_q080"], 1)
    assert [k["sonuc"] for k in summary["kabul"]] == ["gecti"] * 4 + ["kaldi", "kaldi", "gecti"]
    airports = payloads[ie.FILE_PATHS["havalimanlari"]]["havalimanlari"]
    atl = t2["segments_platt"]["Origin"][0]
    assert airports[0]["tahmin_arrdel15_orani"] == round(atl["mean_pred"], 3)
    assert airports[0]["kapsama_p80"] == 0.79 and airports[1]["kapsama_p80"] is None  # given / not computed
    weather = payloads[ie.FILE_PATHS["hava_deneyi"]]
    assert [v["varyant"] for v in weather["varyantlar"]] == ["plan", "T2"]  # no oracle is made up
    brier = next(f["metrik"] for f in weather["farklar"] if f["metrik"]["ad"] == "brier")
    source = block["comparisons"]["weather_contribution"]["arr_del15"]["d_brier_platt"]
    assert brier == ie.metric("brier", source["estimate"], "skor", ci=source)


def test_model_version_and_periods() -> None:
    results = _fake_results()
    assert ie.model_version(results) == VERSION
    summary = ie.build_ozet(results, n_airports=2, created=CREATED, version=VERSION)
    assert summary["bolme"]["dogrulama_a"] == {"baslangic": "2025-09-01", "bitis": "2025-12-31"}
    assert summary["kapsam"]["test_ucus_sayisi"] == 1100
    assert summary["proje"]["sorumluluk_reddi"].startswith("Kamu verisine dayalı; havayollarıyla bağlantısız.")
    results["metadata"]["periods"]["final_test"]["end"] = "2026-09-30"
    with pytest.raises(ie.ExportError, match="period"):
        ie.build_ozet(results, n_airports=2, created=CREATED, version=VERSION)
    results = _fake_results()
    results["metadata"]["mode"] = "rehearsal"
    with pytest.raises(ie.ExportError, match="final test"):
        ie.build_hava_deneyi(results, created=CREATED, version=VERSION)
    with pytest.raises(ie.ExportError, match="timezone"):
        ie.header("ozet", dt.datetime(2026, 11, 22), VERSION)


# ----------------------------------------------------------------------------
# aggregation helpers
# ----------------------------------------------------------------------------


def test_reliability_bins_match_metrics() -> None:
    rng = np.random.default_rng(42)
    p = rng.uniform(0.01, 0.9, 5000)
    y = (rng.uniform(size=5000) < p).astype("float64")
    bins = ie.reliability_bins(y, p)
    assert len(bins) == 10 and sum(b["n"] for b in bins) == 5000
    assert all(b["alt"] <= b["ortalama_tahmin"] <= b["ust"] for b in bins)
    assert ie.ece_from_bins(bins) == pytest.approx(mt.expected_calibration_error(y, p), abs=1e-12)
    table = mt.reliability_table(y, p)
    assert [b["n"] for b in bins] == table["n"].tolist()
    entry = ie.reliability_entry("arrdel15", "lgbm_T2", y, p)
    assert entry["kutular"][0]["ortalama_tahmin"] == round(bins[0]["ortalama_tahmin"], 3)
    with pytest.raises(ValueError):
        ie.reliability_bins(y, np.r_[p[:-1], np.nan])


def test_cell_model_table_means_medians_and_coverage() -> None:
    codes = np.array([0, 0, 0, 1, 1])
    y = np.array([10.0, 20.0, 30.0, -5.0, 100.0])
    table = ie.cell_model_table(
        3,
        codes15=codes,
        y15=np.array([0.0, 1.0, 1.0, 0.0, 1.0]),
        p15=np.array([0.2, 0.4, 0.6, 0.1, 0.3]),
        codes_q=codes,
        y_q=y,
        q50=np.array([1.0, 2.0, 9.0, 0.0, 4.0]),
        q80=y,
        q95=y,
        c80=np.array([15.0, 15.0, 15.0, 0.0, 0.0]),
        c95=np.array([25.0, 25.0, 25.0, 200.0, 200.0]),
        lower=np.zeros(5),
        upper=np.ones(5),
    )
    assert table["n_arrdel15"].tolist() == [3, 2, 0]
    assert table.loc[0, "gozlenen_arrdel15_orani"] == pytest.approx(2 / 3)
    assert table.loc[0, "tahmin_arrdel15_orani"] == pytest.approx(0.4)
    assert table.loc[0, "kantil_p50"] == 2.0 and table.loc[1, "kantil_p50"] == 2.0
    assert table.loc[0, "kapsama_p80"] == pytest.approx(1 / 3) and table.loc[1, "kapsama_p80"] == pytest.approx(0.5)
    assert table.loc[0, "kapsama_p95"] == pytest.approx(2 / 3)
    assert np.isnan(table.loc[2, "kantil_p50"])
    with pytest.raises(ValueError):
        ie.cell_model_table(
            1, codes15=codes, y15=y, p15=y, codes_q=codes, y_q=y, q50=y, q80=y, q95=y, c80=y, c95=y, lower=y, upper=y
        )


def _or_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {c: _route_row()[c] for c in ie.OR_REQUIRED_COLUMNS},
            {
                c: _route_row(dest="BOS", saat_blogu=None, n_ucus=3, yayimlanabilir=False)[c]
                for c in ie.OR_REQUIRED_COLUMNS
            },
        ]
    )


def test_or_reproduction_check_and_join() -> None:
    or_table = _or_rows()
    keys = pd.DataFrame({"Origin": ["ATL", "ATL"], "Dest": ["BOS", "LGA"], "hour_block": [-1, 1], "season": [2, 2]})
    labels = ie.cell_key_labels(keys)
    assert labels["saat_blogu"].tolist() == [None, "06-09"] and labels["mevsim"].tolist() == ["yaz", "yaz"]
    knots = np.array([[-20.0, -5.0, 12.0, 30.0, 50.0], [-20.0, -5.0, 12.0, 30.0, 50.0]])
    record = ie.compare_with_or(labels, [3, 120], knots, or_table)
    assert record["cells"] == 2 and record["max_abs_knot_diff_min"] == 0.0
    with pytest.raises(ie.ExportError, match="n_ucus"):
        ie.compare_with_or(labels, [4, 120], knots, or_table)
    with pytest.raises(ie.ExportError, match="knots"):
        ie.compare_with_or(labels, [3, 120], knots + np.array([[0.0, 0.0, 0.01, 0.0, 0.0], [0.0] * 5]), or_table)
    model = pd.DataFrame([{c: _route_row()[c] for c in ie._MODEL_CELL_COLUMNS}] * 2)
    routes = ie.route_table(labels, model, or_table)
    assert len(routes) == 2 and routes.loc[routes["dest"] == "BOS", "saat_blogu"].isna().all()
    by_origin, hidden = ie.route_cells(routes)
    assert [c["dest"] for c in by_origin["ATL"]] == ["LGA"] and hidden["yayimlanamaz"] == 1
    with pytest.raises(ie.ExportError, match="not in both"):
        ie.route_table(labels.iloc[[1]], model.iloc[[1]], or_table)


def test_origin_and_monthly_interval_coverage() -> None:
    origin = np.array(["ATL", "ATL", "ORD"])
    y = np.array([1.0, 5.0, 3.0])
    coverage = ie.origin_coverage(origin, y, np.array([2.0, 2.0, 4.0]), np.array([9.0, 9.0, 9.0]))
    assert coverage == {"ATL": {"p80": 0.5, "p95": 1.0, "n": 2}, "ORD": {"p80": 1.0, "p95": 1.0, "n": 1}}
    monthly = ie.monthly_interval_coverage(np.array(["2026-03", "2026-03", "2026-04"]), y, np.zeros(3), np.full(3, 4.0))
    assert monthly == [{"ay": "2026-03", "kapsama": 0.5, "n": 2}, {"ay": "2026-04", "kapsama": 1.0, "n": 1}]
    record = ie.check_close("x", 0.5, 0.5 + 1e-12, 1e-9)
    assert record["ok"] and not ie.check_close("x", 0.5, None, 1e-9)["ok"]


def test_carrier_dominated_airport_rates_are_hidden(validator: ie.SchemaValidator) -> None:
    """User decision 2026-11-23: M10 at airport level -> airport listed, rates null, a reason; no Origin segment."""
    results = _fake_results()
    airports = ie.build_havalimanlari(results, AIRPORTS, created=CREATED, version=VERSION, hidden_origins={"ATL"})
    validator.validate(airports, "havalimanlari")
    atl = next(a for a in airports["havalimanlari"] if a["iata"] == "ATL")
    assert atl["gozlenen_arrdel15_orani"] is None and atl["tahmin_arrdel15_orani"] is None
    assert atl["iptal_orani"] is None and atl["kapsama_p80"] is None and atl["kapsama_p95"] is None
    assert atl["gizleme_nedeni"] == ie.CARRIER_DOMINATED_NOTE
    others = [a for a in airports["havalimanlari"] if a["iata"] != "ATL"]
    assert all(a["gozlenen_arrdel15_orani"] is not None and "gizleme_nedeni" not in a for a in others)
    errors = ie.build_hata_analizi(results, created=CREATED, version=VERSION, hidden_origins={"ATL"})
    validator.validate(errors, "hata_analizi")
    text = json.dumps(errors)
    assert '"ATL"' not in text
