"""Static-site interface export: pure helpers (no model, no layer data; the only I/O is ``write_site``).

Contract: ``experiments/arayuz-sozlesmesi.json`` (JSON Schema draft 2020-12, ``sema_surumu`` 0.1.x) and
``experiments/modelleme-plani.md`` section 9. The CLI and the data pipeline live in ``run_interface_export``; the field
-> source map is ``experiments/arayuz-ciktisi-notlari.md``.

What is here:
- ``SchemaValidator``: a small, dependency-free validator for the JSON Schema subset the contract uses (``jsonschema``
  is not installed). The schema is scanned first: any keyword outside the supported set raises ``SchemaError``, so a
  later schema edit can never be silently ignored. ``format`` is ASSERTED for ``date``, ``date-time`` and ``uri``
  (stricter than the 2020-12 default, where ``format`` is only an annotation).
- builders that turn the frozen final-test results (``son-test-sonuclari.json``) and pre-aggregated tables into the
  site payloads. Builders only select, rename and round; they never fit, tune or re-weight anything.
- presentation rules (decision M2, plan section 9, red team M10): no carrier / tail-number / flight-number field
  (``assert_no_forbidden_keys``), no flight-level rows, cells and segments with n < 50 are not published, route cells
  flagged by the OR table (single carrier > 90 % or n < 50) are not published.
- rounding (plan section 9): minutes 1 decimal, rates 3 decimals; scores (AUC, Brier, log-loss, slopes) 4 decimals
  (decision of this module: the plan names no rule for scores).
- ``prepare_site_files``: forbidden-key check, schema validation (own definition AND the root ``oneOf``), compact
  UTF-8 serialisation, per-file size limits (``x-azami-boyut-kb``, 1 KB = 1024 bytes; hard or recorded warnings, see
  the function), the hard 10 MB total and the manifest (bytes + sha256 of every file). Note: with 30 route files the
  manifest alone is about 5.2 KB (36 entries x ~145 bytes of fixed path + sha256), above its 5 KB recommendation.
- ``write_site``: never overwrites: refuses an existing output folder, writes into a fresh staging folder next to it
  and renames it into place at the end.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import os
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

from flight_delay.modeling import final_eval as fe
from flight_delay.modeling.features import DEFAULT_HORIZON_HOURS
from flight_delay.modeling.splits import FINAL_TEST, TRAIN, VAL_A, VAL_B, Period
from flight_delay.optimization import newsvendor as nv
from flight_delay.optimization import policies as pol
from flight_delay.paths import PROJECT_ROOT

__all__ = [
    "DEFAULT_SCHEMA_FILE",
    "DIGITS",
    "DISCLAIMER",
    "FILE_PATHS",
    "FORBIDDEN_KEY_PARTS",
    "MIN_PUBLISH_N",
    "OR_REQUIRED_COLUMNS",
    "ROUTE_COLUMNS",
    "SCHEMA_VERSION",
    "ExportError",
    "SchemaError",
    "SchemaValidator",
    "assert_no_forbidden_keys",
    "build_hata_analizi",
    "build_hava_deneyi",
    "build_havalimanlari",
    "build_kalibrasyon",
    "build_manifest",
    "build_ozet",
    "build_rotalar",
    "cell_key_labels",
    "cell_model_table",
    "check_close",
    "check_or_table",
    "compare_with_or",
    "ece_from_bins",
    "header",
    "metric",
    "model_version",
    "monthly_interval_coverage",
    "origin_coverage",
    "prepare_site_files",
    "reliability_bins",
    "reliability_entry",
    "round_value",
    "route_cells",
    "route_path",
    "route_table",
    "scan_schema",
    "serialize",
    "write_site",
]

SCHEMA_VERSION = "0.1.0"
DEFAULT_SCHEMA_FILE = PROJECT_ROOT / "experiments" / "arayuz-sozlesmesi.json"
SITE_PREFIX = "veri/"
MIN_PUBLISH_N = pol.PUBLISH_MIN_N  # 50: plan section 9 "n < 50 olan hücreler yayımlanmaz"
DIGITS: dict[str, int] = {"oran": 3, "dakika": 1, "skor": 4}
COORDINATE_DIGITS = 4
RELIABILITY_BINS = 10  # plan section 9: "model başına 10 kutu"; same equal-frequency bins as metrics.reliability_table
KB = 1024
KUME = "test"
FILE_PATHS: dict[str, str] = {
    "manifest": "veri/manifest.json",
    "ozet": "veri/ozet.json",
    "havalimanlari": "veri/havalimanlari.json",
    "kalibrasyon": "veri/kalibrasyon.json",
    "hava_deneyi": "veri/hava-deneyi.json",
    "hata_analizi": "veri/hata-analizi.json",
    "optimizasyon": "veri/optimizasyon.json",
    "varis_noktalari": "veri/varis-noktalari.json",
}
_ROUTE_PATH = re.compile(r"^veri/rotalar/([A-Z0-9]{3})\.json$")
FORBIDDEN_KEY_PARTS: tuple[str, ...] = (
    "airline",
    "carrier",
    "tail",
    "flight_number",
    "flightnumber",
    "tasiyici",
    "taşıyıcı",
    "havayolu",
    "kuyruk",
    "ucus_no",
    "ucus_numara",
    "logo",
)
DISCLAIMER_EN = (
    "Based on public data; not affiliated with any airline. An independent analysis of US DOT/BTS flight data and "
    "Iowa Environmental Mesonet (IEM) ASOS/METAR observations. No per-carrier results or rankings are published; "
    "BTS delay-cause fields are the carrier's own declaration and are not used here. Not an operational decision "
    "tool; buffer suggestions rest on assumed cost ratios."
)

CARRIER_DOMINATED_NOTE_EN = (
    "Not published: more than 90% of this airport's test-period flights belong to one carrier, so airport-level "
    "figures would show that carrier's performance (presentation rule)."
)

CARRIER_DOMINATED_NOTE = (
    "Yayımlanmadı: Bu havalimanından kalkan uçuşların %90'ından fazlası tek bir havayoluna ait. Havalimanının "
    "sayıları fiilen o havayolunun performansını göstereceği için paylaşılmıyor."
)

DISCLAIMER = (
    "Kamu verisine dayalı; havayollarıyla bağlantısız. ABD Ulaştırma Bakanlığı'nın (DOT/BTS) uçuş verisi ve Iowa "
    "Environmental Mesonet'in (IEM) hava gözlemleriyle yapılmış bağımsız bir çalışmadır. Havayolu bazında sonuç ya "
    "da sıralama paylaşılmaz. BTS'deki rötar nedeni alanları havayollarının kendi beyanıdır ve burada kullanılmadı. "
    "Bu bir operasyon aracı değildir; tampon önerileri varsayılan maliyet oranlarına dayanır."
)

# --- role -> (gorev, model kimliği) of the interface enums ---
CLASSIFIER_ROLE_IDS: dict[str, tuple[str, str]] = {
    fe.ROLE_ARR_DEL15_T2: ("arrdel15", "lgbm_T2"),
    fe.ROLE_ARR_DEL15_PLAN: ("arrdel15", "lgbm_plan"),
    fe.ROLE_CANCELLED_PLAN: ("iptal", "lgbm_plan"),
    fe.ROLE_CANCELLED_T2: ("iptal", "lgbm_T2"),
}
B1_CLASSIFIER_SOURCE: dict[str, str] = {"arrdel15": fe.ROLE_ARR_DEL15_T2, "iptal": fe.ROLE_CANCELLED_PLAN}
QUANTILE_ROLE_IDS: dict[str, str] = {fe.ROLE_QUANTILES_PLAN: "lgbm_plan", fe.ROLE_QUANTILES_T2: "lgbm_T2"}
UNPUBLISHED_ROLES: tuple[str, ...] = (fe.ROLE_CANCELLED_T2_CALENDAR,)  # no model id in the schema enum
_SEGMENT_DIMENSIONS: tuple[tuple[str, str], ...] = (("Origin", "origin"), ("hour_block", "saat_blogu"), ("month", "ay"))

OR_REQUIRED_COLUMNS: tuple[str, ...] = (
    "origin",
    "dest",
    "saat_blogu",
    "mevsim",
    "n_ucus",
    "n_tamamlanan",
    "n_iptal",
    "crs_elapsed_medyan_dk",
    "gozlenen_arrdel15_tamponsuz",
    *(f"plan_q{round(level * 100):03d}_dk" for level in nv.KNOT_LEVELS),
    "tek_tasiyici_yogun",
    "yayimlanabilir",
    "tampon_onerisi_dk",
)
_MODEL_CELL_COLUMNS: tuple[str, ...] = (
    "n_arrdel15",
    "gozlenen_arrdel15_orani",
    "tahmin_arrdel15_orani",
    "n_kantil",
    "kantil_p50",
    "kantil_p80",
    "kantil_p95",
    "kantil_conf_p80",
    "kantil_conf_p95",
    "aralik80_alt",
    "aralik80_ust",
    "kapsama_p80",
    "kapsama_p95",
)
_KEYS: tuple[str, ...] = ("origin", "dest", "saat_blogu", "mevsim")
ROUTE_COLUMNS: tuple[str, ...] = (*OR_REQUIRED_COLUMNS, *_MODEL_CELL_COLUMNS)
_MISSING_KEY = "\x00"  # merge sentinel for cells without an hour block (missing local departure minute)


class SchemaError(ValueError):
    """The schema uses a keyword this validator does not implement (or is malformed)."""


class ExportError(ValueError):
    """An export rule is broken (schema validation, size limit, forbidden field, reproduction check, ...)."""


# ----------------------------------------------------------------------------
# JSON Schema subset validator
# ----------------------------------------------------------------------------

_SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "unevaluatedProperties",
        "items",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "$ref",
        "$defs",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "if",
        "then",
        "else",
    }
)
_ANNOTATION_KEYWORDS = frozenset({"$schema", "$id", "$comment", "title", "description", "default", "examples"})
_SUPPORTED_FORMATS = frozenset({"date", "date-time", "uri"})
_TYPE_NAMES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})
_SINGLE_SUBSCHEMA = frozenset({"items", "not", "if", "then", "else", "additionalProperties", "unevaluatedProperties"})
_SUBSCHEMA_MAPS = frozenset({"properties", "$defs"})
_SUBSCHEMA_LISTS = frozenset({"allOf", "anyOf", "oneOf"})


def scan_schema(schema: Any, path: str = "#") -> list[str]:
    """Every problem of a schema for this validator: unsupported keyword, unknown type / format, bad pattern, ...

    Keys starting with ``x-`` are project annotations and are skipped (not descended into)."""
    if isinstance(schema, bool):
        return []
    if not isinstance(schema, dict):
        return [f"{path}: a schema must be an object or a boolean"]
    problems: list[str] = []
    for key, value in schema.items():
        where = f"{path}/{key}"
        if key.startswith("x-") or key in _ANNOTATION_KEYWORDS:
            continue
        if key not in _SUPPORTED_KEYWORDS:
            problems.append(f"{path}: unsupported keyword {key!r}")
            continue
        if key in _SINGLE_SUBSCHEMA:
            problems += scan_schema(value, where)
        elif key in _SUBSCHEMA_MAPS:
            if not isinstance(value, dict):
                problems.append(f"{where}: must be an object of schemas")
            else:
                for name, sub in value.items():
                    problems += scan_schema(sub, f"{where}/{name}")
        elif key in _SUBSCHEMA_LISTS:
            if not isinstance(value, list) or not value:
                problems.append(f"{where}: must be a non-empty list of schemas")
            else:
                for i, sub in enumerate(value):
                    problems += scan_schema(sub, f"{where}/{i}")
        elif key == "type":
            names = value if isinstance(value, list) else [value]
            bad = [n for n in names if n not in _TYPE_NAMES]
            if bad or not names:
                problems.append(f"{where}: unknown type(s) {bad}")
        elif key == "format" and value not in _SUPPORTED_FORMATS:
            problems.append(f"{where}: unsupported format {value!r}")
        elif key == "$ref" and (not isinstance(value, str) or not value.startswith("#")):
            problems.append(f"{where}: only local '#/...' references are supported: {value!r}")
        elif key == "pattern":
            try:
                re.compile(value)
            except (re.error, TypeError) as error:
                problems.append(f"{where}: invalid pattern {value!r} ({error})")
        elif key == "required" and (not isinstance(value, list) or not all(isinstance(v, str) for v in value)):
            problems.append(f"{where}: must be a list of property names")
        elif key == "enum" and not isinstance(value, list):
            problems.append(f"{where}: must be a list")
    return problems


def _refs(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key.startswith("x-"):
                continue
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _type_matches(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "number":
        return _is_number(value) and math.isfinite(value)
    if name == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        return isinstance(value, float) and math.isfinite(value) and value.is_integer()
    return False


def _json_equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_number(a) and _is_number(b):
        return float(a) == float(b)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _format_ok(value: str, fmt: str) -> bool:
    if fmt == "date":
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return False
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            return False
        return True
    if fmt == "date-time":
        if "T" not in value:
            return False
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return parsed.tzinfo is not None
    if fmt == "uri":
        parts = urlsplit(value)
        return bool(parts.scheme) and bool(parts.netloc or parts.path) and not any(c.isspace() for c in value)
    return False


def _describe(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if _is_number(value):
        return "number" if math.isfinite(value) else f"non-finite number {value!r}"
    return type(value).__name__


class SchemaValidator:
    """Validator for the JSON Schema subset of the interface contract (see the module docstring)."""

    def __init__(self, schema: Mapping[str, Any]) -> None:
        if not isinstance(schema, dict):
            raise SchemaError("The schema root must be an object")
        self.schema: dict[str, Any] = schema
        problems = scan_schema(schema)
        for ref in sorted(set(_refs(schema))):
            try:
                self.resolve(ref)
            except SchemaError as error:
                problems.append(str(error))
        if problems:
            raise SchemaError("Schema not supported: " + "; ".join(problems))
        self._patterns: dict[str, re.Pattern[str]] = {}

    @classmethod
    def from_file(cls, path: Path) -> SchemaValidator:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def resolve(self, ref: str) -> Any:
        if not ref.startswith("#"):
            raise SchemaError(f"only local references are supported: {ref!r}")
        node: Any = self.schema
        pointer = ref[1:]
        if pointer == "":
            return node
        for raw in pointer.lstrip("/").split("/"):
            part = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                raise SchemaError(f"unresolvable $ref {ref!r}")
        return node

    def definitions(self) -> list[str]:
        return sorted(self.schema.get("$defs", {}))

    def max_bytes(self, definition: str) -> int | None:
        """``x-azami-boyut-kb`` of a definition in bytes (1 KB = 1024 bytes); None if the schema sets none."""
        kb = self.schema.get("$defs", {}).get(definition, {}).get("x-azami-boyut-kb")
        return None if kb is None else int(round(float(kb) * KB))

    def errors(self, instance: Any, definition: str | None = None) -> list[str]:
        """All validation errors (empty = valid) against the root schema or ``#/$defs/<definition>``."""
        schema = self.schema if definition is None else self.resolve(f"#/$defs/{definition}")
        found, _ = self._check(instance, schema, "$")
        return found

    def validate(self, instance: Any, definition: str | None = None, *, label: str = "") -> None:
        found = self.errors(instance, definition)
        if found:
            what = definition or "root"
            shown = "; ".join(found[:20]) + (f"; ... ({len(found)} errors)" if len(found) > 20 else "")
            raise ExportError(f"{label or 'payload'} does not match the schema ({what}): {shown}")

    def _pattern(self, pattern: str) -> re.Pattern[str]:
        compiled = self._patterns.get(pattern)
        if compiled is None:
            compiled = self._patterns[pattern] = re.compile(pattern)
        return compiled

    def _check(self, value: Any, schema: Any, path: str) -> tuple[list[str], set[str]]:
        if schema is True:
            return [], set()
        if schema is False:
            return [f"{path}: not allowed"], set()
        errors: list[str] = []
        evaluated: set[str] = set()
        if "$ref" in schema:
            found, seen = self._check(value, self.resolve(schema["$ref"]), path)
            errors += found
            evaluated |= seen
        if "type" in schema:
            names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_type_matches(value, n) for n in names):
                errors.append(f"{path}: expected {'/'.join(names)}, got {_describe(value)}")
        if "enum" in schema and not any(_json_equal(value, c) for c in schema["enum"]):
            errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
        if "const" in schema and not _json_equal(value, schema["const"]):
            errors.append(f"{path}: {value!r} must be {schema['const']!r}")
        if _is_number(value) and math.isfinite(value):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{path}: {value} < minimum {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{path}: {value} > maximum {schema['maximum']}")
            if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
                errors.append(f"{path}: {value} <= exclusiveMinimum {schema['exclusiveMinimum']}")
            if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
                errors.append(f"{path}: {value} >= exclusiveMaximum {schema['exclusiveMaximum']}")
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(f"{path}: shorter than {schema['minLength']} characters")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append(f"{path}: longer than {schema['maxLength']} characters")
            if "pattern" in schema and not self._pattern(schema["pattern"]).search(value):
                errors.append(f"{path}: {value!r} does not match {schema['pattern']!r}")
            if "format" in schema and not _format_ok(value, schema["format"]):
                errors.append(f"{path}: {value!r} is not a valid {schema['format']}")
        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path}: fewer than {schema['minItems']} items")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append(f"{path}: more than {schema['maxItems']} items ({len(value)})")
            if "items" in schema:
                for i, item in enumerate(value):
                    found, _ = self._check(item, schema["items"], f"{path}[{i}]")
                    errors += found
        if isinstance(value, dict):
            missing = [k for k in schema.get("required", []) if k not in value]
            errors += [f"{path}: required property {k!r} missing" for k in missing]
            properties = schema.get("properties", {})
            for key, sub in properties.items():
                if key in value:
                    found, _ = self._check(value[key], sub, f"{path}.{key}")
                    errors += found
                    evaluated.add(key)
            if "additionalProperties" in schema:
                extra = [k for k in value if k not in properties]
                rule = schema["additionalProperties"]
                for key in extra:
                    if rule is False:
                        errors.append(f"{path}.{key}: additional property not allowed")
                    else:
                        found, _ = self._check(value[key], rule, f"{path}.{key}")
                        errors += found
                evaluated |= set(extra)
        for sub in schema.get("allOf", []):
            found, seen = self._check(value, sub, path)
            errors += found
            evaluated |= seen
        if "anyOf" in schema:
            passed = [seen for found, seen in (self._check(value, s, path) for s in schema["anyOf"]) if not found]
            if not passed:
                errors.append(f"{path}: matches none of the anyOf schemas")
            for seen in passed:
                evaluated |= seen
        if "oneOf" in schema:
            results = [self._check(value, s, path) for s in schema["oneOf"]]
            passed = [seen for found, seen in results if not found]
            if len(passed) == 1:
                evaluated |= passed[0]
            elif not passed:
                closest = min((found for found, _ in results), key=len)
                errors.append(f"{path}: matches none of the oneOf schemas (closest: {'; '.join(closest[:3])})")
            else:
                errors.append(f"{path}: matches {len(passed)} oneOf schemas (exactly one required)")
        if "not" in schema:
            found, _ = self._check(value, schema["not"], path)
            if not found:
                errors.append(f"{path}: must not match the 'not' schema")
        if "if" in schema:
            found, seen = self._check(value, schema["if"], path)
            branch = "then" if not found else "else"
            if not found:
                evaluated |= seen
            if branch in schema:
                found_branch, seen_branch = self._check(value, schema[branch], path)
                errors += found_branch
                evaluated |= seen_branch
        if isinstance(value, dict) and "unevaluatedProperties" in schema:
            rule = schema["unevaluatedProperties"]
            extra = [k for k in value if k not in evaluated]
            for key in extra:
                if rule is False:
                    errors.append(f"{path}.{key}: unevaluated property not allowed")
                else:
                    found, _ = self._check(value[key], rule, f"{path}.{key}")
                    errors += found
            evaluated |= set(extra)
        return errors, evaluated


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------


def round_value(value: Any, unit: str) -> float | None:
    """Round by unit ('oran' 3, 'dakika' 1, 'skor' 4 decimals); None for missing / non-finite; no negative zero."""
    if unit not in DIGITS:
        raise ValueError(f"unknown unit {unit!r} (one of {sorted(DIGITS)})")
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    rounded = round(number, DIGITS[unit])
    return 0.0 if rounded == 0 else rounded


def _rate(value: Any) -> float | None:
    return round_value(value, "oran")


def _minutes(value: Any) -> float | None:
    return round_value(value, "dakika")


def metric(name: str, value: Any, unit: str, ci: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One ``metrik`` object; ``ci`` = a bootstrap record ({'ci_low', 'ci_high'}) -> ga95_alt / ga95_ust."""
    out: dict[str, Any] = {"ad": name, "deger": round_value(value, unit)}
    if ci is not None:
        out["ga95_alt"] = round_value(ci.get("ci_low"), unit)
        out["ga95_ust"] = round_value(ci.get("ci_high"), unit)
    out["birim"] = unit
    return out


def _metric_from(name: str, entry: Mapping[str, Any] | None, unit: str) -> dict[str, Any]:
    """Metric from a bootstrap record {'estimate', 'ci_low', 'ci_high'} (None -> deger null)."""
    if not entry:
        return metric(name, None, unit)
    return metric(name, entry.get("estimate"), unit, ci=entry)


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _get(mapping: Any, *path: str) -> Any:
    node = mapping
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            raise ExportError(f"missing in the source results: {'/'.join(path)}")
        node = node[key]
    return node


def assert_no_forbidden_keys(payload: Any, where: str = "payload") -> None:
    """Refuse any object key that names a carrier, tail number, flight number or logo (presentation rules)."""
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                lowered = str(key).lower()
                if any(part in lowered for part in FORBIDDEN_KEY_PARTS):
                    found.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list | tuple):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(payload, where)
    if found:
        raise ExportError(f"forbidden field(s) (carrier / tail / flight number / logo): {found[:10]}")


def model_version(results: Mapping[str, Any]) -> str:
    """'son-test-<UTC stamp>@<git 12>' of the final-test run (the models behind every number; max 64 chars)."""
    meta = _get(results, "metadata")
    created = dt.datetime.fromisoformat(str(_get(meta, "created_utc")))
    head = str(_get(meta, "git", "head"))[:12]
    return f"son-test-{created.astimezone(dt.UTC):%Y%m%dT%H%M%SZ}@{head}"[:64]


def header(kind: str, created: dt.datetime, version: str, sample: bool = False) -> dict[str, Any]:
    if created.tzinfo is None:
        raise ExportError("olusturma_zamani must be timezone-aware (UTC)")
    return {
        "dosya_turu": kind,
        "sema_surumu": SCHEMA_VERSION,
        "olusturma_zamani": created.astimezone(dt.UTC).isoformat(timespec="seconds"),
        "model_surumu": version[:64],
        "ornek": bool(sample),
    }


def _final_block(results: Mapping[str, Any]) -> Mapping[str, Any]:
    if _get(results, "metadata", "mode") != "final_test":
        raise ExportError("the source results are not the one-time final test (metadata.mode != 'final_test')")
    block: Mapping[str, Any] = _get(results, "blocks", "final_test")
    return block


def _period(start: Any, end: Any) -> dict[str, str]:
    return {"baslangic": str(start), "bitis": str(end)}


def _check_period(name: str, stored: Mapping[str, Any], expected: Period) -> None:
    if str(stored.get("start")) != str(expected.start) or str(stored.get("end")) != str(expected.end):
        raise ExportError(f"period {name} in the results ({stored}) differs from splits.{expected.name}")


def _hour_label(segment: Any) -> str | None:
    try:
        code = int(segment)
    except (TypeError, ValueError):
        return None
    return pol.HOUR_BLOCK_LABELS[code] if 0 <= code < len(pol.HOUR_BLOCK_LABELS) else None


def _segment_label(dimension: str, segment: Any) -> str | None:
    return _hour_label(segment) if dimension == "hour_block" else str(segment)


# ----------------------------------------------------------------------------
# ozet.json
# ----------------------------------------------------------------------------

_SOURCES: tuple[dict[str, str], ...] = (
    {
        "ad": "ABD DOT/BTS Reporting Carrier On-Time Performance",
        "url": "https://www.transtats.bts.gov/",
        "lisans_notu": "ABD federal hükümetinin yayımladığı veri; data.gov'da kamu malı olarak geçiyor. BTS sayfasındaki "
        "lisans metnine ulaşılamadı (kısmen doğrulandı).",
    },
    {
        "ad": "Iowa Environmental Mesonet (IEM) ASOS/METAR arşivi",
        "url": "https://mesonet.agron.iastate.edu/request/download.phtml",
        "lisans_notu": "IEM'e göre kamu malı; kaynak gösterilmesi rica ediliyor (doğrulandı).",
    },
    {
        "ad": "OurAirports airports.csv (havalimanı adları ve koordinatları)",
        "url": "https://ourairports.com/data/",
        "lisans_notu": "Sitenin açıklamasına göre kamu malı; sayfaya doğrudan ulaşılamadı (kısmen doğrulandı).",
    },
)

_MODELS: tuple[dict[str, str], ...] = (
    {
        "kimlik": "B1",
        "aciklama": "Basit kural (B1): Bir rotanın belirli saatteki uçuşlarının geçmişte ne sıklıkla ve ne kadar geciktiğine "
        "bakar. Veri azsa daha geniş bir gruba (ör. yalnızca kalkış havalimanı) bakar.",
        "sozlesme": "yok",
    },
    {
        "kimlik": "lgbm_plan",
        "aciklama": "Plan modeli (LightGBM): Yalnızca tarife yapılırken bilinen bilgileri kullanır, hava durumunu bilmez. "
        "Rötar süresi aralıkları ve tampon önerileri bu modelden gelir.",
        "sozlesme": "plan",
    },
    {
        "kimlik": "lgbm_T2",
        "aciklama": "T2 modeli (LightGBM): Plan modelinin bildiklerine ek olarak kalkıştan 2 saat önceki hava raporunu (METAR) kullanır.",
        "sozlesme": "T2",
    },
)


def _classifier_metrics(
    section: Mapping[str, Any], comparison: Mapping[str, Any] | None, who: str
) -> list[dict[str, Any]]:
    raw = _get(section, "raw", who)
    prob = _get(section, "probability", fe.PRIMARY_PROBABILITY, who)
    boot = (section.get("bootstrap") or {}) if who == "model" else {}
    f1 = (section.get("f1_at_frozen_threshold") or {}).get(who) or {}
    out = [
        metric("roc_auc", raw.get("roc_auc"), "skor"),
        metric("pr_auc", raw.get("pr_auc"), "skor"),
        metric("yayginlik", section.get("prevalence"), "oran"),
        metric("brier", prob.get("brier"), "skor"),
    ]
    if who == "model" and comparison is not None:
        vs_b1 = comparison.get("vs_B1") or {}
        out.append(_metric_from("brier_skill", vs_b1.get("bss_platt"), "skor"))
        for name, key in (("roc_auc_farki_b1", "d_roc_auc"), ("pr_auc_farki_b1", "d_pr_auc")):
            if vs_b1.get(key):
                out.append(_metric_from(name, vs_b1[key], "skor"))
    out += [metric("log_loss", prob.get("log_loss"), "skor"), metric("ece", prob.get("ece"), "oran")]
    citl = boot.get("citl_platt")
    out.append(
        _metric_from("calibration_in_the_large", citl, "skor")
        if citl
        else metric("calibration_in_the_large", prob.get("calibration_in_the_large"), "skor")
    )
    slope = boot.get("slope_platt")
    out.append(
        _metric_from("kalibrasyon_egimi", slope, "skor")
        if slope
        else metric("kalibrasyon_egimi", prob.get("calibration_slope"), "skor")
    )
    out.append(metric("kalibrasyon_kesisimi", prob.get("calibration_intercept"), "skor"))
    if f1:
        out += [
            metric("f1", f1.get("f1"), "skor"),
            metric("precision", f1.get("precision"), "oran"),
            metric("recall", f1.get("recall"), "oran"),
        ]
        if f1.get("threshold_min") is not None and f1.get("threshold_min") == f1.get("threshold_max"):
            out.append(metric("esik", f1.get("threshold_min"), "oran"))
    return out


def _quantile_metrics(section: Mapping[str, Any], who: str) -> list[dict[str, Any]]:
    raw = _get(section, "raw", who)
    conformal = _get(section, "conformal", who, fe.PRIMARY_SCHEME)
    boot = (section.get("bootstrap") or {}) if who == "model" else {}
    interval = conformal.get(fe.INTERVAL_KEY) or {}
    out = [
        metric("pinball_p50", raw.get("pinball_q050"), "dakika"),
        metric("pinball_p80", raw.get("pinball_q080"), "dakika"),
        metric("pinball_p95", raw.get("pinball_q095"), "dakika"),
        metric("mae_p50", raw.get("mae_q050"), "dakika"),
        metric("kapsama_p80_ham", raw.get("coverage_q080"), "oran"),
        metric("kapsama_p95_ham", raw.get("coverage_q095"), "oran"),
    ]
    for name, key in (("kapsama_p80_conf", "q080"), ("kapsama_p95_conf", "q095")):
        entry = boot.get(f"coverage_{fe.PRIMARY_SCHEME}_{key}")
        out.append(
            _metric_from(name, entry, "oran")
            if entry
            else metric(name, (conformal.get(key) or {}).get("coverage"), "oran")
        )
    out += [
        metric("kapsama_aralik80", interval.get("coverage"), "oran"),
        metric("aralik80_genislik_dk", interval.get("mean_width_min"), "dakika"),
        metric("kantil_kesisme_orani", raw.get("crossing_rate"), "oran"),
    ]
    return out


def _summary_results(block: Mapping[str, Any]) -> list[dict[str, Any]]:
    classification = _get(block, "classification")
    quantile = _get(block, "quantile")
    comparisons = block.get("comparisons") or {}
    for role in (fe.ROLE_ARR_DEL15_T2, fe.ROLE_CANCELLED_PLAN):
        _get(classification, role)
    _get(quantile, fe.ROLE_QUANTILES_PLAN)
    out: list[dict[str, Any]] = []
    for role, (task, model) in CLASSIFIER_ROLE_IDS.items():
        if role in classification:
            metrics = _classifier_metrics(classification[role], comparisons.get(role) or {}, "model")
            out.append({"gorev": task, "model": model, "kume": KUME, "metrikler": metrics})
    for task, role in B1_CLASSIFIER_SOURCE.items():
        out.append(
            {
                "gorev": task,
                "model": "B1",
                "kume": KUME,
                "metrikler": _classifier_metrics(classification[role], None, "B1"),
            }
        )
    for role, model in QUANTILE_ROLE_IDS.items():
        if role in quantile:
            out.append(
                {
                    "gorev": "kantil",
                    "model": model,
                    "kume": KUME,
                    "metrikler": _quantile_metrics(quantile[role], "model"),
                }
            )
    out.append(
        {
            "gorev": "kantil",
            "model": "B1",
            "kume": KUME,
            "metrikler": _quantile_metrics(quantile[fe.ROLE_QUANTILES_PLAN], "B1"),
        }
    )
    return out


_VERDICT = {True: "gecti", False: "kaldi", None: "degerlendirilmedi"}

PROJECT_TITLE_EN = "US domestic flight delays: schedule-time and pre-departure prediction (30 airports)"
PROJECT_TEXT_EN = (
    "The probability that a flight arrives 15+ minutes late (ArrDel15), the cancellation probability and arrival-delay "
    "quantiles (P50/P80/P95) are predicted at two moments: when the schedule is set (plan) and 2 hours before "
    "departure (T2, with METAR weather observations). Models were trained on a time-ordered split; the final test "
    "period (2026-03..08) was evaluated once with locked models and results are published without tuning. "
    "Probabilities are calibrated with monthly rolling Platt scaling; upper quantile bounds use a monthly rolling "
    "one-sided conformal adjustment. Buffer suggestions come from the plan model's cell quantiles with an assumed "
    "cost ratio (tau = 0.80)."
)
_SOURCE_LICENCES_EN = (
    "US federal government work; data.gov lists it as public domain; the licence text on the BTS page could not be "
    "read (partly verified).",
    "Public domain according to IEM; attribution requested (verified).",
    "Public domain according to the site; the page could not be read directly (partly verified).",
)
_MODELS_EN = {
    "B1": "Baseline (B1): historical delay rate / empirical quantile of route x hour block in the training period "
    "(falls back to a coarser group when data are thin).",
    "lgbm_plan": "LightGBM, plan contract: only information known when the schedule is set (no weather). Quantiles "
    "and buffer suggestions come from this model.",
    "lgbm_T2": "LightGBM, T2 contract: schedule information + METAR weather observations 2 hours before scheduled "
    "departure.",
}
ACCEPTANCE_TEXT_EN = {
    "K1": "The T2 model ranks late arrivals better than B1: ROC-AUC and PR-AUC differences are positive, the lower "
    "bound of the confidence interval is above zero and they remain significant after Holm correction.",
    "K2": "The Brier skill gain of the calibrated probabilities over B1 is positive with a lower confidence bound "
    "above zero.",
    "K3": "Probabilities are calibrated: calibration-in-the-large within +/-0.01 and calibration slope between 0.9 "
    "and 1.1.",
    "K4": "The plan model's P50, P80 and P95 quantiles have lower pinball loss than B1; all three significant.",
    "K5": "Conformal upper bounds hit their targets: P80 coverage 0.78-0.82, P95 coverage 0.94-0.96, and at least "
    "80% of airport x month segments within +/-0.05 of target.",
    "K6": "Schedule-only (plan) cancellation prediction beats B1: PR-AUC difference positive with a lower confidence "
    "bound above zero.",
    "K7": "No leakage: leakage tests passed and no unresolved suspicion in the locked models.",
}
NOTES_EN = (
    "The final test was run only once. These are the locked models' results for the test period; nothing was tuned "
    "after the test data were seen.",
    "Probability measures (Brier, log-loss, ECE, calibration) use the adjusted probabilities; separation measures "
    "(ROC-AUC, PR-AUC) and the F1 threshold use the model's raw scores.",
    "95% confidence intervals come from resampling whole test days 1,000 times (day-block bootstrap). Differences and "
    "the Brier gain are always relative to the simple rule (B1).",
    "The 'oracle' model, which knows the weather that actually happened, was not part of the final test, so the "
    "weather experiment has no result for it.",
    "An extra cancellation model that also uses calendar features was only for comparison and is not shown here.",
    "Route groups with fewer than 50 flights, and groups where one airline operates more than 90% of the flights, "
    "are not shown.",
    "Unusual day: a test day whose late-arrival rate is higher than on 95% of the days in the training period (for "
    "example, stormy days). All other days are 'other days'.",
    "How delay limits are adjusted: 'rolling' recomputes the limit each month from flights 2–57 days earlier (main "
    "method); 'static' computes it once in the calibration period (Jan–Feb 2026); 'raw' is the unadjusted model "
    "estimate.",
    "Buffer optimisation (OR): adding buffer to the schedule clearly lowers the share of late flights. With the same "
    "total buffer, however, the model's allocation is not significantly better than the simple historical rule (B1). "
    "The model's main value is on the day of the flight, in the prediction made 2 hours before departure.",
)

# Plain-language criterion texts for the site (pre-registered rules: experiments/son-test-on-kayit.md, plan 5.3).
ACCEPTANCE_TEXT = {
    "K1": "T2 modeli, geç kalacak uçuşları basit kuraldan (B1) daha iyi ayırt ediyor: ROC-AUC ve PR-AUC farkları "
    "pozitif, güven aralıkları sıfırın üstünde ve çoklu karşılaştırma düzeltmesinden (Holm) sonra da anlamlı.",
    "K2": "Modelin olasılık tahminleri basit kuralınkilerden daha isabetli: Brier skorundaki kazanç pozitif ve güven "
    "aralığı sıfırın üstünde.",
    "K3": "Olasılıklar gerçeğe uyuyor: ortalama tahmin ile gerçekleşen oran arasındaki fark (CITL) en fazla ±0,01, "
    "kalibrasyon eğimi 0,9 ile 1,1 arasında.",
    "K4": "Plan modelinin rötar süresi tahminleri (P50, P80, P95) basit kuralınkilerden daha isabetli; üç farkın "
    "üçü de anlamlı.",
    "K5": "Rötar süresi üst sınırları hedefi tutuyor: P80 sınırı uçuşların %78–82'sini, P95 sınırı %94–96'sını "
    "kapsıyor ve havalimanı × ay gruplarının en az %80'inde hedeften sapma 5 puanı geçmiyor.",
    "K6": "Yalnızca tarife bilgisiyle yapılan iptal tahmini basit kuraldan daha iyi: PR-AUC farkı pozitif ve güven "
    "aralığı sıfırın üstünde.",
    "K7": "Sızıntı yok: Model tahmin anında bilemeyeceği bir bilgiyi kullanmıyor; testler geçti, açık bir şüphe kalmadı.",
}


def _acceptance(block: Mapping[str, Any]) -> list[dict[str, Any]]:
    criteria = _get(block, "criteria")
    out = []
    for key in sorted(criteria):
        if not re.fullmatch(r"K[1-7]", key):
            raise ExportError(f"unknown acceptance criterion {key!r} (the schema allows K1 - K7)")
        entry = criteria[key]
        passed = entry.get("passed")
        out.append(
            {
                "olcut": key,
                "aciklama": _truncate(ACCEPTANCE_TEXT.get(key) or entry.get("description", ""), 300),
                "sonuc": _VERDICT.get(passed if isinstance(passed, bool) else None, "degerlendirilmedi"),
            }
        )
    return out


def build_ozet(
    results: Mapping[str, Any],
    *,
    n_airports: int,
    created: dt.datetime,
    version: str,
    extra_notes: Sequence[str] = (),
    extra_notes_en: Sequence[str] = (),
    sample: bool = False,
) -> dict[str, Any]:
    """``ozet.json`` from the final-test results (no number is computed here except rounding)."""
    block = _final_block(results)
    periods = _get(results, "metadata", "periods")
    fit, test, static = _get(periods, "fit"), _get(periods, "final_test"), _get(periods, "static_calibration")
    _check_period("fit", fit, TRAIN)
    _check_period("final_test", test, FINAL_TEST)
    _check_period("static_calibration", static, VAL_B)
    payload = header("ozet", created, version, sample)
    payload["proje"] = {
        "baslik": "ABD iç hat uçuşlarında rötar: tarife yapılırken ve kalkıştan önce tahmin (30 havalimanı)",
        "aciklama": (
            "Bir uçuşun 15 dakika ya da daha geç varma olasılığı (ArrDel15), iptal olasılığı ve ne kadar gecikeceği "
            "(P50/P80/P95) iki ayrı anda tahmin ediliyor: tarife yapılırken (plan modeli) ve kalkıştan 2 saat önce, "
            "hava raporuyla birlikte (T2 modeli). Modeller zaman sırasına göre ayrılmış veriyle eğitildi. Son test "
            "dönemi (Mart–Ağustos 2026) kilitli modellerle yalnızca bir kez değerlendirildi; sonuçlar sonradan "
            "ayar yapılmadan paylaşılıyor. Olasılıklar her ay yeniden ayarlanıyor (kayan Platt); rötar süresi üst "
            "sınırları da her ay geçmiş hatalara göre düzeltiliyor (conformal). Tampon önerileri plan modelinden, "
            "varsayılan bir maliyet oranıyla (τ = 0,80) hesaplandı."
        ),
        "sorumluluk_reddi": DISCLAIMER,
        "kaynaklar": [dict(s) for s in _SOURCES],
    }
    payload["kapsam"] = {
        "havalimani_sayisi": int(n_airports),
        "veri_donemi": _period(fit["start"], test["end"]),
        "test_ucus_sayisi": int(_get(block, "rows", "classifiers", fe.ROLE_CANCELLED_PLAN, "n")),
        "test_gun_sayisi": int(_get(block, "days", "n")),
    }
    payload["bolme"] = {
        "egitim": _period(fit["start"], fit["end"]),
        "dogrulama_a": _period(VAL_A.start, VAL_A.end),
        "dogrulama_b": _period(static["start"], static["end"]),
        "test": _period(test["start"], test["end"]),
    }
    payload["bilgi_zamani_saat"] = float(DEFAULT_HORIZON_HOURS)
    payload["modeller"] = [dict(m) for m in _MODELS]
    payload["sonuclar"] = _summary_results(block)
    payload["kabul"] = _acceptance(block)
    notes = [
        "Son test yalnızca bir kez çalıştırıldı. Buradaki sayılar kilitli modellerin test dönemi sonuçları; "
        "test verisi görüldükten sonra hiçbir ayar yapılmadı.",
        "Olasılıkla ilgili ölçütler (Brier, log-loss, ECE, kalibrasyon) ayarlanmış olasılıklarla; ayırt etme "
        "ölçütleri (ROC-AUC, PR-AUC) ve F1 eşiği ise modelin ham skorlarıyla hesaplandı.",
        "%95 güven aralıkları, test günleri bütün olarak 1000 kez yeniden örneklenerek (gün blok bootstrap) "
        "hesaplandı. Farklar ve Brier kazancı hep basit kurala (B1) göre verilir.",
        "Gerçekleşen havayı bilen 'oracle' modeli son teste dahil edilmediği için hava deneyinde onun sonucu yok.",
        "Takvim bilgisi de kullanan ek iptal modeli yalnızca karşılaştırma amaçlıydı; burada gösterilmiyor.",
        "50'den az uçuşu olan rota gruplarının ve uçuşlarının %90'ından fazlası tek bir havayoluna ait olan "
        "grupların sayıları paylaşılmıyor.",
        "Olağandışı gün: Geç varış oranının, eğitim dönemindeki günlerin %95'inden daha yüksek olduğu test günü "
        "(ör. fırtınalı günler). Geri kalanlar 'diğer günler'.",
        "Rötar süresi sınırlarının düzeltilme biçimleri: 'kayan' sınır her ay, o aydan 2–57 gün önceki uçuşlara "
        "bakılarak yeniden hesaplanır (ana yöntem); 'sabit' sınır kalibrasyon döneminde (Ocak–Şubat 2026) bir kez "
        "hesaplanır; 'ham' sınır ise düzeltilmemiş model tahminidir.",
        "Tampon optimizasyonu (OR): Tarifeye tampon eklemek geç varan uçuşların oranını belirgin şekilde azaltıyor. "
        "Ancak aynı toplam tampon süresiyle, modelin önerdiği dağıtım basit geçmiş kuralından (B1) anlamlı ölçüde "
        "daha iyi değil. Modelin asıl katkısı uçuş günü, kalkıştan 2 saat önce yapılan tahminde.",
    ]
    payload["notlar"] = [_truncate(n, 500) for n in [*notes, *extra_notes]][:20]
    payload["ceviri_en"] = {
        "proje": {"baslik": PROJECT_TITLE_EN, "aciklama": PROJECT_TEXT_EN, "sorumluluk_reddi": DISCLAIMER_EN},
        "kaynak_lisans_notlari": [_truncate(t, 300) for t in _SOURCE_LICENCES_EN],
        "modeller": [{"kimlik": k, "aciklama": _truncate(v, 300)} for k, v in _MODELS_EN.items()],
        "kabul": [{"olcut": k, "aciklama": _truncate(v, 300)} for k, v in sorted(ACCEPTANCE_TEXT_EN.items())],
        "notlar": [_truncate(n, 500) for n in [*NOTES_EN, *extra_notes_en]][:20],
    }
    return payload


# ----------------------------------------------------------------------------
# havalimanlari.json
# ----------------------------------------------------------------------------


def _segments_by_code(section: Mapping[str, Any], key: str, dimension: str) -> dict[str, Mapping[str, Any]]:
    segments = _get(section, key)
    assert_no_forbidden_keys(dict.fromkeys(segments), where=key)  # a carrier dimension upstream is refused
    return {str(s["segment"]): s for s in _get(segments, dimension)}


def build_havalimanlari(
    results: Mapping[str, Any],
    airports: Sequence[Mapping[str, Any]],
    *,
    created: dt.datetime,
    version: str,
    coverage: Mapping[str, Mapping[str, Any]] | None = None,
    hidden_origins: Collection[str] = (),
    sample: bool = False,
) -> dict[str, Any]:
    """``havalimanlari.json``: one item per target airport (``airports`` = iata, ad, enlem, boylam, saat_dilimi).

    Rates come from the final-test Origin segments (T2 ArrDel15, aylık kayan Platt mean = tahmin; cancelled/plan
    observed rate = iptal_orani). ``coverage`` (optional, computed from the locked plan model): iata -> {p80, p95, n}.
    """
    block = _final_block(results)
    classification = _get(block, "classification")
    t2 = _segments_by_code(_get(classification, fe.ROLE_ARR_DEL15_T2), "segments_platt", "Origin")
    cancel = _segments_by_code(_get(classification, fe.ROLE_CANCELLED_PLAN), "segments_platt", "Origin")
    items = []
    for airport in airports:
        code = str(airport["iata"])
        segment = t2.get(code)
        if segment is None or segment.get("prevalence") is None or segment.get("mean_pred") is None:
            raise ExportError(f"{code}: no T2 Origin segment with rates in the final-test results")
        n = int(segment["n"])
        if n < MIN_PUBLISH_N:
            raise ExportError(f"{code}: n = {n} < {MIN_PUBLISH_N}; a target airport cannot be published")
        item: dict[str, Any] = {
            "iata": code,
            "ad": _truncate(str(airport["ad"]), 120),
            "enlem": round(float(airport["enlem"]), COORDINATE_DIGITS),
            "boylam": round(float(airport["boylam"]), COORDINATE_DIGITS),
            "saat_dilimi": str(airport["saat_dilimi"]),
            "n_test_ucus": n,
            "gozlenen_arrdel15_orani": _rate(segment["prevalence"]),
            "tahmin_arrdel15_orani": _rate(segment["mean_pred"]),
        }
        if code in hidden_origins:  # M10 at airport level (user decision 2026-11-23): no rates, a note instead
            item["gozlenen_arrdel15_orani"] = None
            item["tahmin_arrdel15_orani"] = None
            item.update(iptal_orani=None, kapsama_p80=None, kapsama_p95=None, gizleme_nedeni=CARRIER_DOMINATED_NOTE)
            item["gizleme_nedeni_en"] = CARRIER_DOMINATED_NOTE_EN
            items.append(item)
            continue
        cancelled = cancel.get(code)
        usable = cancelled is not None and int(cancelled.get("n", 0)) >= MIN_PUBLISH_N
        item["iptal_orani"] = _rate(cancelled.get("prevalence")) if usable and cancelled else None
        cov = (coverage or {}).get(code)
        usable_cov = cov is not None and int(cov.get("n", 0)) >= MIN_PUBLISH_N
        item["kapsama_p80"] = _rate(cov.get("p80")) if usable_cov and cov else None
        item["kapsama_p95"] = _rate(cov.get("p95")) if usable_cov and cov else None
        items.append(item)
    payload = header("havalimanlari", created, version, sample)
    payload["havalimanlari"] = items
    return payload


# ----------------------------------------------------------------------------
# kalibrasyon.json
# ----------------------------------------------------------------------------


def reliability_bins(y: Any, p: Any, n_bins: int = RELIABILITY_BINS) -> list[dict[str, float]]:
    """Equal-frequency bins by sorted prediction, exactly the bins of ``metrics.reliability_table`` (stable sort);
    plus the lowest / highest prediction of every bin. Raw (unrounded) values."""
    y_arr = np.asarray(y, dtype="float64").ravel()
    p_arr = np.asarray(p, dtype="float64").ravel()
    if y_arr.shape != p_arr.shape or y_arr.size == 0:
        raise ValueError("y and p must be non-empty and of equal length")
    if not (np.all(np.isfinite(y_arr)) and np.all(np.isfinite(p_arr))):
        raise ValueError("y and p must be finite")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    order = np.argsort(p_arr, kind="mergesort")
    bins = np.empty(y_arr.size, dtype="int64")
    bins[order] = (np.arange(y_arr.size) * n_bins) // y_arr.size
    frame = pd.DataFrame({"bin": bins, "y": y_arr, "p": p_arr})
    table = frame.groupby("bin", sort=True).agg(
        n=("y", "size"), alt=("p", "min"), ust=("p", "max"), ortalama_tahmin=("p", "mean"), gozlenen_oran=("y", "mean")
    )
    return [
        {
            "alt": float(row.alt),
            "ust": float(row.ust),
            "ortalama_tahmin": float(row.ortalama_tahmin),
            "gozlenen_oran": float(row.gozlenen_oran),
            "n": int(row.n),
        }
        for row in table.itertuples()
    ]


def ece_from_bins(bins: Sequence[Mapping[str, Any]]) -> float:
    total = float(sum(b["n"] for b in bins))
    return float(sum(b["n"] / total * abs(b["ortalama_tahmin"] - b["gozlenen_oran"]) for b in bins))


def reliability_entry(task: str, model: str, y: Any, p: Any, n_bins: int = RELIABILITY_BINS) -> dict[str, Any]:
    """One ``siniflandirma`` item (rounded rates; bins with n < 50 are hidden)."""
    bins = [b for b in reliability_bins(y, p, n_bins) if b["n"] >= MIN_PUBLISH_N]
    return {
        "gorev": task,
        "model": model,
        "kume": KUME,
        "kutular": [
            {
                "alt": _rate(b["alt"]),
                "ust": _rate(b["ust"]),
                "ortalama_tahmin": _rate(b["ortalama_tahmin"]),
                "gozlenen_oran": _rate(b["gozlenen_oran"]),
                "n": int(b["n"]),
            }
            for b in bins
        ],
    }


def monthly_interval_coverage(month: Any, y: Any, lower: Any, upper: Any) -> list[dict[str, Any]]:
    """Two-sided interval coverage per 'YYYY-MM' (raw values): [{'ay', 'kapsama', 'n'}]."""
    frame = pd.DataFrame(
        {
            "ay": np.asarray(month).astype(str),
            "c": (
                (np.asarray(y, dtype="float64") >= np.asarray(lower, dtype="float64"))
                & (np.asarray(y, dtype="float64") <= np.asarray(upper, dtype="float64"))
            ).astype("float64"),
        }
    )
    grouped = frame.groupby("ay", sort=True)["c"].agg(["size", "mean"])
    return [{"ay": str(ay), "kapsama": float(row["mean"]), "n": int(row["size"])} for ay, row in grouped.iterrows()]


def build_kalibrasyon(
    results: Mapping[str, Any],
    *,
    created: dt.datetime,
    version: str,
    reliability: Sequence[Mapping[str, Any]] = (),
    interval_monthly: Sequence[Mapping[str, Any]] = (),
    sample: bool = False,
) -> dict[str, Any]:
    """``kalibrasyon.json``: reliability bins (given, computed from the locked models) and monthly one-sided coverage
    (raw / rolling / static) of the plan and T2 quantile models from the final-test results; B1 raw coverage;
    ``interval_monthly`` (optional): two-sided 80 % CQR coverage of the plan model, rolling scheme."""
    block = _final_block(results)
    quantile = _get(block, "quantile")
    rows: list[dict[str, Any]] = []
    sources: list[tuple[str, str, Sequence[tuple[str, str]]]] = []
    for role, model in QUANTILE_ROLE_IDS.items():
        if role in quantile:
            sources.append(
                (
                    role,
                    model,
                    (("ham", "coverage_raw_{k}"), ("kayan", "coverage_rolling_{k}"), ("statik", "coverage_static_{k}")),
                )
            )
    sources.append((fe.ROLE_QUANTILES_PLAN, "B1", (("ham", "coverage_raw_{k}_B1"),)))
    for role, model, fields in sources:
        for entry in _get(quantile, role, "monthly"):
            n = int(entry["n"])
            if n < MIN_PUBLISH_N:
                continue
            for key, target in (("q080", 0.8), ("q095", 0.95)):
                for method, template in fields:
                    value = entry.get(template.format(k=key))
                    if value is None:
                        continue
                    rows.append(
                        {
                            "ay": str(entry["month"]),
                            "model": model,
                            "yontem": method,
                            "tur": "tek_yonlu_ust",
                            "hedef": target,
                            "kapsama": _rate(value),
                            "n": n,
                        }
                    )
    for entry in interval_monthly:
        if int(entry["n"]) >= MIN_PUBLISH_N:
            rows.append(
                {
                    "ay": str(entry["ay"]),
                    "model": "lgbm_plan",
                    "yontem": "kayan",
                    "tur": "iki_yonlu",
                    "hedef": 0.8,
                    "kapsama": _rate(entry["kapsama"]),
                    "n": int(entry["n"]),
                }
            )
    payload = header("kalibrasyon", created, version, sample)
    payload["siniflandirma"] = [copy.deepcopy(dict(r)) for r in reliability]
    payload["kapsama_aylik"] = rows
    return payload


# ----------------------------------------------------------------------------
# hava-deneyi.json
# ----------------------------------------------------------------------------


def build_hava_deneyi(
    results: Mapping[str, Any], *, created: dt.datetime, version: str, sample: bool = False
) -> dict[str, Any]:
    """``hava-deneyi.json``: plan vs T2 on the same flights (final-test weather contribution). No oracle variant: no
    oracle model was locked (the final test records only a text note), so none is published and nothing is made up."""
    block = _final_block(results)
    classification = _get(block, "classification")
    quantile = _get(block, "quantile")
    weather = _get(block, "comparisons", "weather_contribution")
    arr_del15 = _get(weather, "arr_del15")

    def variant(classifier_role: str, quantile_role: str) -> list[dict[str, Any]]:
        section = _get(classification, classifier_role)
        raw = _get(section, "raw", "model")
        prob = _get(section, "probability", fe.PRIMARY_PROBABILITY, "model")
        out = [
            metric("roc_auc", raw.get("roc_auc"), "skor"),
            metric("pr_auc", raw.get("pr_auc"), "skor"),
            metric("brier", prob.get("brier"), "skor"),
        ]
        if quantile_role in quantile:
            out.append(
                metric("pinball_p80", _get(quantile, quantile_role, "raw", "model").get("pinball_q080"), "dakika")
            )
        return out

    differences = [
        {"karsilastirma": "T2-plan", "metrik": _metric_from("roc_auc", arr_del15.get("d_roc_auc"), "skor")},
        {"karsilastirma": "T2-plan", "metrik": _metric_from("pr_auc", arr_del15.get("d_pr_auc"), "skor")},
        {"karsilastirma": "T2-plan", "metrik": _metric_from("brier", arr_del15.get("d_brier_platt"), "skor")},
    ]
    arr_delay = weather.get("arr_delay")
    if isinstance(arr_delay, Mapping):
        differences.append(
            {
                "karsilastirma": "T2-plan",
                "metrik": _metric_from("pinball_p80", arr_delay.get("d_pinball_q080"), "dakika"),
            }
        )
    payload = header("hava_deneyi", created, version, sample)
    payload["kume"] = KUME
    payload["varyantlar"] = [
        {
            "varyant": "plan",
            "oracle": False,
            "etiket": "Plan modeli: yalnızca tarife yapılırken bilinenler (hava yok)",
            "etiket_en": "Plan: only information known when the schedule is set (no weather)",
            "metrikler": variant(fe.ROLE_ARR_DEL15_PLAN, fe.ROLE_QUANTILES_PLAN),
        },
        {
            "varyant": "T2",
            "oracle": False,
            "etiket": "T2 modeli: ek olarak kalkıştan 2 saat önceki hava raporu",
            "etiket_en": "T2: adds METAR weather observations 2 hours before scheduled departure",
            "metrikler": variant(fe.ROLE_ARR_DEL15_T2, fe.ROLE_QUANTILES_T2),
        },
    ]
    payload["farklar"] = differences
    return payload


# ----------------------------------------------------------------------------
# hata-analizi.json
# ----------------------------------------------------------------------------


def _classifier_segment_metrics(segment: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        metric("yayginlik", segment.get("prevalence"), "oran"),
        metric("brier", segment.get("brier"), "skor"),
        metric("brier_skill", segment.get("brier_skill_score"), "skor"),
        metric("calibration_in_the_large", segment.get("calibration_in_the_large"), "skor"),
        metric("roc_auc", segment.get("roc_auc"), "skor"),
        metric("pr_auc", segment.get("pr_auc"), "skor"),
    ]


def _quantile_segment_metrics(segment: Mapping[str, Any], conformal: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    out = [
        metric("pinball_p50", segment.get("pinball_q050"), "dakika"),
        metric("pinball_p80", segment.get("pinball_q080"), "dakika"),
        metric("pinball_p95", segment.get("pinball_q095"), "dakika"),
        metric("kapsama_p80_ham", segment.get("coverage_raw_q080"), "oran"),
        metric("kapsama_p95_ham", segment.get("coverage_raw_q095"), "oran"),
    ]
    if conformal:
        out += [
            metric("kapsama_p80_conf", conformal.get("q080"), "oran"),
            metric("kapsama_p95_conf", conformal.get("q095"), "oran"),
        ]
    return out


def _segment_list(
    segments: Iterable[Mapping[str, Any]], dimension: str, required: str, metrics: Any
) -> list[dict[str, Any]]:
    out = []
    for segment in segments:
        label = _segment_label(dimension, segment.get("segment"))
        n = int(segment.get("n", 0))
        if label is None or n < MIN_PUBLISH_N or segment.get(required) is None:
            continue  # hidden: n < 50, no metrics in the source (below its own segment_min_n) or unknown hour block
        out.append({"segment": _truncate(label, 32), "n": n, "metrikler": metrics(segment)})
    return out


def _without_origins(segments: Mapping[str, Any], hidden: Collection[str]) -> dict[str, Any]:
    """Segment tables without the Origin segments of ``hidden`` airports (other dimensions are pooled, kept)."""
    out = dict(segments)
    if hidden and "Origin" in out:
        out["Origin"] = [s for s in out["Origin"] if str(s.get("segment")) not in set(hidden)]
    return out


def build_hata_analizi(
    results: Mapping[str, Any],
    *,
    created: dt.datetime,
    version: str,
    worst: int = 5,
    hidden_origins: Collection[str] = (),
    sample: bool = False,
) -> dict[str, Any]:
    """``hata-analizi.json``: final-test segments (origin / saat_blogu / ay; olay günü). No carrier dimension.

    ``en_kotu``: the ``worst`` origins by lowest brier_skill (T2 ArrDel15) and by largest |raw P80 coverage - 0.80|
    (plan quantiles); ranked on the unrounded source values."""
    block = _final_block(results)
    classification = _get(block, "classification")
    quantile = _get(block, "quantile")
    t2 = _get(classification, fe.ROLE_ARR_DEL15_T2)
    plan = _get(quantile, fe.ROLE_QUANTILES_PLAN)
    t2_segments = _get(t2, "segments_platt")
    plan_segments = _get(plan, "segments")
    assert_no_forbidden_keys(dict.fromkeys(t2_segments), where="segments_platt")
    assert_no_forbidden_keys(dict.fromkeys(plan_segments), where="segments")
    t2_segments = _without_origins(t2_segments, hidden_origins)  # M10 at airport level
    plan_segments = _without_origins(plan_segments, hidden_origins)
    rolling = _get(plan, "conformal", "model", fe.PRIMARY_SCHEME)
    monthly_conf = {
        month: {
            "q080": rolling["q080"]["monthly_coverage"].get(month),
            "q095": rolling["q095"]["monthly_coverage"].get(month),
        }
        for month in rolling.get("q080", {}).get("monthly_coverage", {})
    }
    dimensions: list[dict[str, Any]] = []
    for source, name in _SEGMENT_DIMENSIONS:
        dimensions.append(
            {
                "boyut": name,
                "model": "lgbm_T2",
                "segmentler": _segment_list(
                    t2_segments.get(source, []), source, "prevalence", _classifier_segment_metrics
                ),
            }
        )
    events = t2.get("event_days") or {}
    event_rows = [("olay", events.get("event_days") or {}), ("diger", events.get("other_days") or {})]
    for model, suffix in (("lgbm_T2", ""), ("B1", "_B1")):
        segments = []
        for label, entry in event_rows:
            n = int(entry.get("n", 0))
            if n < MIN_PUBLISH_N or entry.get("prevalence") is None:
                continue
            segments.append(
                {
                    "segment": label,
                    "n": n,
                    "metrikler": [
                        metric("yayginlik", entry.get("prevalence"), "oran"),
                        metric("brier", entry.get(f"brier_platt{suffix}"), "skor"),
                        metric("roc_auc", entry.get(f"roc_auc_raw{suffix}"), "skor"),
                    ],
                }
            )
        if segments:
            dimensions.append({"boyut": "olay_gunu", "model": model, "segmentler": segments})
    for source, name in _SEGMENT_DIMENSIONS:
        dimensions.append(
            {
                "boyut": name,
                "model": "lgbm_plan",
                "segmentler": _segment_list(
                    plan_segments.get(source, []),
                    source,
                    "pinball_q080",
                    lambda s, src=source: _quantile_segment_metrics(
                        s, monthly_conf.get(str(s.get("segment"))) if src == "month" else None
                    ),
                ),
            }
        )
    worst_rows: list[dict[str, Any]] = []
    eligible_t2 = [
        s
        for s in t2_segments.get("Origin", [])
        if int(s.get("n", 0)) >= MIN_PUBLISH_N and s.get("brier_skill_score") is not None
    ]
    for s in sorted(eligible_t2, key=lambda s: (float(s["brier_skill_score"]), str(s["segment"])))[:worst]:
        worst_rows.append(
            {
                "boyut": "origin",
                "segment": str(s["segment"]),
                "n": int(s["n"]),
                "metrik": metric("brier_skill", s["brier_skill_score"], "skor"),
            }
        )
    eligible_plan = [
        s
        for s in plan_segments.get("Origin", [])
        if int(s.get("n", 0)) >= MIN_PUBLISH_N and s.get("coverage_raw_q080") is not None
    ]
    for s in sorted(eligible_plan, key=lambda s: (-abs(float(s["coverage_raw_q080"]) - 0.80), str(s["segment"])))[
        :worst
    ]:
        worst_rows.append(
            {
                "boyut": "origin",
                "segment": str(s["segment"]),
                "n": int(s["n"]),
                "metrik": metric("kapsama_p80_ham", s["coverage_raw_q080"], "oran"),
            }
        )
    payload = header("hata_analizi", created, version, sample)
    payload["kume"] = KUME
    payload["boyutlar"] = dimensions
    payload["en_kotu"] = worst_rows
    return payload


# ----------------------------------------------------------------------------
# rotalar/<IATA>.json: cell tables
# ----------------------------------------------------------------------------


def route_path(origin: str) -> str:
    return f"veri/rotalar/{origin}.json"


def cell_key_labels(keys: pd.DataFrame) -> pd.DataFrame:
    """Interface labels of ``policies.Cells.keys`` (Origin, Dest, hour_block code, season code) in the same order."""
    hours = [int(h) for h in keys["hour_block"]]
    labels = [pol.HOUR_BLOCK_LABELS[h] if 0 <= h < len(pol.HOUR_BLOCK_LABELS) else None for h in hours]
    out = pd.DataFrame(
        {
            "origin": keys["Origin"].astype(str).to_numpy(),
            "dest": keys["Dest"].astype(str).to_numpy(),
            "mevsim": [pol.SEASON_LABELS[int(s)] for s in keys["season"]],
        }
    )
    out.insert(2, "saat_blogu", pd.Series(labels, dtype=object, index=out.index))  # object: None stays None
    return out


def _is_missing(value: Any) -> bool:
    """None / NaN / pd.NA (pandas 3 string columns hold NaN, not None, for missing labels)."""
    if value is None:
        return True
    if isinstance(value, str):
        return value == "" or value == _MISSING_KEY
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _group_mean(codes: np.ndarray, values: np.ndarray, n_cells: int) -> np.ndarray:
    sums = np.bincount(codes, weights=values, minlength=n_cells)
    counts = np.bincount(codes, minlength=n_cells).astype("float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.asarray(np.where(counts > 0, sums / counts, np.nan))


def _group_median(codes: np.ndarray, values: np.ndarray, n_cells: int) -> np.ndarray:
    series = pd.Series(values).groupby(codes, sort=True).median()
    return np.asarray(series.reindex(range(n_cells)).to_numpy(dtype="float64"))


def cell_model_table(
    n_cells: int,
    *,
    codes15: Any,
    y15: Any,
    p15: Any,
    codes_q: Any,
    y_q: Any,
    q50: Any,
    q80: Any,
    q95: Any,
    c80: Any,
    c95: Any,
    lower: Any,
    upper: Any,
) -> pd.DataFrame:
    """One row per cell (row i = cell code i) from flight-level model outputs of the ArrDel15 and ArrDelay universes.

    Rates are means over the cell's completed flights; kantil_* / kantil_conf_* / aralik80_* are MEDIANS of the
    flights' values (schema: "hücredeki uçuş kantillerinin medyanı"); kapsama_* = share of y <= conformal bound."""
    c15 = np.asarray(codes15, dtype="int64").ravel()
    cq = np.asarray(codes_q, dtype="int64").ravel()
    arrays15 = [np.asarray(a, dtype="float64").ravel() for a in (y15, p15)]
    arrays_q = [np.asarray(a, dtype="float64").ravel() for a in (y_q, q50, q80, q95, c80, c95, lower, upper)]
    if any(a.shape != c15.shape for a in arrays15) or any(a.shape != cq.shape for a in arrays_q):
        raise ValueError("codes and values differ in length")
    if (c15.size and (c15.min() < 0 or c15.max() >= n_cells)) or (cq.size and (cq.min() < 0 or cq.max() >= n_cells)):
        raise ValueError("cell codes outside 0 .. n_cells - 1")
    y15_arr, p15_arr = arrays15
    yq, a50, a80, a95, b80, b95, lo, hi = arrays_q
    return pd.DataFrame(
        {
            "n_arrdel15": np.bincount(c15, minlength=n_cells).astype("int64"),
            "gozlenen_arrdel15_orani": _group_mean(c15, y15_arr, n_cells),
            "tahmin_arrdel15_orani": _group_mean(c15, p15_arr, n_cells),
            "n_kantil": np.bincount(cq, minlength=n_cells).astype("int64"),
            "kantil_p50": _group_median(cq, a50, n_cells),
            "kantil_p80": _group_median(cq, a80, n_cells),
            "kantil_p95": _group_median(cq, a95, n_cells),
            "kantil_conf_p80": _group_median(cq, b80, n_cells),
            "kantil_conf_p95": _group_median(cq, b95, n_cells),
            "aralik80_alt": _group_median(cq, lo, n_cells),
            "aralik80_ust": _group_median(cq, hi, n_cells),
            "kapsama_p80": _group_mean(cq, (yq <= b80).astype("float64"), n_cells),
            "kapsama_p95": _group_mean(cq, (yq <= b95).astype("float64"), n_cells),
        }
    )


def check_or_table(or_table: pd.DataFrame) -> None:
    """Required columns of the OR cell table; no carrier / tail / flight-number column."""
    pol.assert_no_forbidden_columns(or_table)
    missing = [c for c in OR_REQUIRED_COLUMNS if c not in or_table.columns]
    if missing:
        raise ExportError(f"OR cell table lacks columns {missing}")


def _keyed(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in _KEYS:
        out[column] = out[column].astype(object).where(out[column].notna(), _MISSING_KEY).astype(str)
    return out


def compare_with_or(
    labels: pd.DataFrame, counts: Any, knots: Any, or_table: pd.DataFrame, *, tolerance: float = 1e-6
) -> dict[str, Any]:
    """Reproduction check against the OR cell table: same cells, same scheduled-flight counts and the same cell knots
    (plan model, OR aggregator) within ``tolerance`` minutes. Raises ExportError on any difference."""
    check_or_table(or_table)
    knot_array = np.asarray(knots, dtype="float64")
    if knot_array.shape != (len(labels), len(nv.KNOT_LEVELS)):
        raise ValueError("knots must have one row per cell and one column per knot level")
    mine = _keyed(labels)
    mine["_n_now"] = np.asarray(counts, dtype="float64")
    names = [f"plan_q{round(level * 100):03d}_dk" for level in nv.KNOT_LEVELS]
    for j, name in enumerate(names):
        mine[f"_{name}_now"] = knot_array[:, j]
    theirs = _keyed(or_table[[*_KEYS, "n_ucus", *names]])
    try:
        merged = mine.merge(theirs, on=list(_KEYS), how="outer", indicator=True, validate="one_to_one")
    except pd.errors.MergeError as error:
        raise ExportError(f"cell keys are not unique: {error}") from error
    only = merged["_merge"] != "both"
    problems: list[str] = []
    if only.any():
        problems.append(f"{int(only.sum())} cells are not in both tables")
    both = merged.loc[~only]
    n_diff = int((both["_n_now"].to_numpy() != both["n_ucus"].to_numpy(dtype="float64")).sum())
    if n_diff:
        problems.append(f"{n_diff} cells differ in n_ucus")
    diffs = [np.abs(both[f"_{n}_now"].to_numpy() - both[n].to_numpy(dtype="float64")) for n in names]
    max_diff = float(np.nanmax(np.concatenate(diffs))) if len(both) else 0.0
    if not math.isfinite(max_diff) or max_diff > tolerance:
        problems.append(f"plan cell knots differ by up to {max_diff} min (tolerance {tolerance})")
    record = {
        "cells": int(len(merged)),
        "cells_only_one_side": int(only.sum()),
        "n_differences": n_diff,
        "max_abs_knot_diff_min": max_diff,
    }
    if problems:
        raise ExportError("OR cell reproduction failed: " + "; ".join(problems) + f" ({record})")
    return record


def route_table(labels: pd.DataFrame, model_table: pd.DataFrame, or_table: pd.DataFrame) -> pd.DataFrame:
    """Cell labels + model statistics (same row order) joined one-to-one with the OR cell table."""
    check_or_table(or_table)
    if len(labels) != len(model_table):
        raise ValueError("labels and model_table differ in length")
    mine = pd.concat([_keyed(labels).reset_index(drop=True), model_table.reset_index(drop=True)], axis=1)
    theirs = _keyed(or_table[list(OR_REQUIRED_COLUMNS)])
    merged = mine.merge(theirs, on=list(_KEYS), how="outer", indicator=True, validate="one_to_one")
    if (merged["_merge"] != "both").any():
        raise ExportError(f"{int((merged['_merge'] != 'both').sum())} cells are not in both tables")
    merged = merged.drop(columns="_merge")
    for column in _KEYS:
        values = merged[column].astype(object).to_numpy()
        # pandas 3 string columns may turn the NUL sentinel into "" -> both mean "missing key"
        merged[column] = pd.Series(
            [None if v in (_MISSING_KEY, "") else v for v in values], dtype=object, index=merged.index
        )
    return merged


def route_cells(table: pd.DataFrame) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Publishable cells per origin and the count of hidden cells per reason.

    Hidden: OR says not publishable (n < 50 scheduled flights or one carrier > 90 %), n_ucus < 50, fewer than 50
    completed flights in the ArrDel15 or ArrDelay universe, no hour block / season, or a required value missing."""
    pol.assert_no_forbidden_columns(table)
    missing = [c for c in ROUTE_COLUMNS if c not in table.columns]
    if missing:
        raise ExportError(f"route table lacks columns {missing}")
    hidden = {"yayimlanamaz": 0, "n_ucus_az": 0, "tamamlanan_az": 0, "anahtar_eksik": 0, "eksik_deger": 0}
    out: dict[str, list[dict[str, Any]]] = {}
    ordered = table.sort_values(["origin", "dest", "saat_blogu", "mevsim"], kind="mergesort", na_position="last")
    for row in ordered.to_dict("records"):
        if not bool(row["yayimlanabilir"]):
            hidden["yayimlanamaz"] += 1
            continue
        if int(row["n_ucus"]) < MIN_PUBLISH_N:
            hidden["n_ucus_az"] += 1
            continue
        if min(int(row["n_arrdel15"]), int(row["n_kantil"])) < MIN_PUBLISH_N:
            hidden["tamamlanan_az"] += 1
            continue
        if _is_missing(row["saat_blogu"]) or _is_missing(row["mevsim"]):
            hidden["anahtar_eksik"] += 1
            continue
        cell: dict[str, Any] = {
            "dest": str(row["dest"]),
            "saat_blogu": str(row["saat_blogu"]),
            "mevsim": str(row["mevsim"]),
            "n_ucus": int(row["n_ucus"]),
            "gozlenen_arrdel15_orani": _rate(row["gozlenen_arrdel15_orani"]),
            "tahmin_arrdel15_orani": _rate(row["tahmin_arrdel15_orani"]),
            "kantil_dk": {
                "p50": _minutes(row["kantil_p50"]),
                "p80": _minutes(row["kantil_p80"]),
                "p95": _minutes(row["kantil_p95"]),
            },
            "kantil_conf_dk": {"p80": _minutes(row["kantil_conf_p80"]), "p95": _minutes(row["kantil_conf_p95"])},
            "aralik80_dk": None,
            "kapsama": {"p80": _rate(row["kapsama_p80"]), "p95": _rate(row["kapsama_p95"])},
            "planli_blok_sure_medyan_dk": _minutes(row["crs_elapsed_medyan_dk"]),
            "iptal_orani": _rate(float(row["n_iptal"]) / float(row["n_ucus"])),
            "tampon_onerisi_dk": _minutes(row["tampon_onerisi_dk"]),
        }
        low, high = _minutes(row["aralik80_alt"]), _minutes(row["aralik80_ust"])
        if low is not None and high is not None:
            cell["aralik80_dk"] = {"alt": low, "ust": high}
        required = [
            cell["gozlenen_arrdel15_orani"],
            cell["tahmin_arrdel15_orani"],
            *cell["kantil_dk"].values(),
            *cell["kantil_conf_dk"].values(),
            *cell["kapsama"].values(),
            cell["planli_blok_sure_medyan_dk"],
            cell["iptal_orani"],
        ]
        if any(v is None for v in required):
            hidden["eksik_deger"] += 1
            continue
        out.setdefault(str(row["origin"]), []).append(cell)
    hidden["yayimlanan"] = sum(len(v) for v in out.values())
    return out, hidden


def build_rotalar(
    origin: str, cells: Sequence[Mapping[str, Any]], *, created: dt.datetime, version: str, sample: bool = False
) -> dict[str, Any]:
    payload = header("rotalar", created, version, sample)
    payload["origin"] = str(origin)
    payload["kume"] = KUME
    payload["hucreler"] = [copy.deepcopy(dict(c)) for c in cells]
    return payload


def build_varis_noktalari(
    points: Sequence[Mapping[str, Any]],
    *,
    missing: Sequence[str] = (),
    created: dt.datetime,
    version: str,
    sample: bool = False,
) -> dict[str, Any]:
    """``varis-noktalari.json``: name and coordinates of every destination in the published route cells (OurAirports),
    so the map can draw route arcs. Destinations without coordinates are listed in ``eksik`` (nothing invented)."""
    payload = header("varis_noktalari", created, version, sample)
    payload["noktalar"] = [
        {
            "iata": str(p["iata"]),
            "ad": _truncate(str(p["ad"]), 120),
            "enlem": round(float(p["enlem"]), COORDINATE_DIGITS),
            "boylam": round(float(p["boylam"]), COORDINATE_DIGITS),
        }
        for p in sorted(points, key=lambda q: str(q["iata"]))
    ]
    payload["eksik"] = sorted(str(m) for m in missing)
    return payload


def origin_coverage(origin: Any, y: Any, upper80: Any, upper95: Any) -> dict[str, dict[str, Any]]:
    """Conformal-adjusted (rolling) one-sided coverage per origin (raw values): iata -> {p80, p95, n}."""
    frame = pd.DataFrame(
        {
            "o": np.asarray(origin).astype(str),
            "c80": (np.asarray(y, dtype="float64") <= np.asarray(upper80, dtype="float64")).astype("float64"),
            "c95": (np.asarray(y, dtype="float64") <= np.asarray(upper95, dtype="float64")).astype("float64"),
        }
    )
    grouped = frame.groupby("o", sort=True).agg(n=("c80", "size"), p80=("c80", "mean"), p95=("c95", "mean"))
    return {str(o): {"p80": float(r["p80"]), "p95": float(r["p95"]), "n": int(r["n"])} for o, r in grouped.iterrows()}


def check_close(name: str, now: Any, stored: Any, tolerance: float) -> dict[str, Any]:
    """One reproduction record; ok = both finite and |now - stored| <= tolerance."""
    a = float(now) if now is not None else float("nan")
    b = float(stored) if stored is not None else float("nan")
    diff = abs(a - b) if math.isfinite(a) and math.isfinite(b) else float("inf")
    return {"name": name, "now": a, "stored": b, "abs_diff": diff, "tolerance": tolerance, "ok": diff <= tolerance}


# ----------------------------------------------------------------------------
# files, manifest, writing
# ----------------------------------------------------------------------------


def serialize(payload: Mapping[str, Any]) -> bytes:
    """Compact UTF-8 JSON (no NaN / Infinity)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _expected_kind(path: str) -> str:
    for kind, known in FILE_PATHS.items():
        if path == known:
            return kind
    if _ROUTE_PATH.match(path):
        return "rotalar"
    raise ExportError(f"unknown site path {path!r}")


def build_manifest(
    files: Sequence[tuple[str, str, bytes]], *, created: dt.datetime, version: str, sample: bool = False
) -> dict[str, Any]:
    """``manifest.json``: path, file type, bytes and sha256 of every listed file; toplam_bayt = their sum (the
    manifest itself is not listed; its size is checked separately)."""
    payload = header("manifest", created, version, sample)
    payload["dosyalar"] = [
        {"yol": path, "dosya_turu": kind, "bayt": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for path, kind, data in files
    ]
    payload["toplam_bayt"] = int(sum(len(data) for _, _, data in files))
    return payload


def _check_size(
    validator: SchemaValidator, kind: str, size: int, path: str, *, strict: bool, warnings: list[str] | None
) -> None:
    limit = validator.max_bytes(kind)
    if limit is not None and size > limit:
        message = f"{path}: {size} bytes > limit {limit} bytes (x-azami-boyut-kb of {kind})"
        if strict or warnings is None:
            raise ExportError(message)
        warnings.append(message)


def prepare_site_files(
    payloads: Mapping[str, Mapping[str, Any]],
    validator: SchemaValidator,
    *,
    created: dt.datetime,
    version: str,
    sample: bool = False,
    strict_sizes: bool = True,
    warnings: list[str] | None = None,
) -> dict[str, bytes]:
    """Site path -> bytes for every payload plus ``veri/manifest.json``. Every file is checked for forbidden keys,
    validated against its own definition and the root ``oneOf`` and size-checked; the total must stay within the
    manifest's ``toplam_bayt`` maximum (10 MB) including the manifest (always a hard limit).

    Per-file limits (``x-azami-boyut-kb``; plan section 9 calls them recommendations): an error when
    ``strict_sizes``; otherwise each overrun is appended to ``warnings`` (which must then be given)."""
    files: dict[str, bytes] = {}
    listed: list[tuple[str, str, bytes]] = []
    for path in sorted(payloads):
        payload = payloads[path]
        kind = _expected_kind(path)
        if kind == "manifest":
            raise ExportError("the manifest is built here, not passed in")
        if payload.get("dosya_turu") != kind:
            raise ExportError(f"{path}: dosya_turu {payload.get('dosya_turu')!r} != {kind!r}")
        if kind == "rotalar" and payload.get("origin") != _ROUTE_PATH.match(path).group(1):  # type: ignore[union-attr]
            raise ExportError(f"{path}: origin {payload.get('origin')!r} does not match the file name")
        assert_no_forbidden_keys(payload, where=path)
        validator.validate(payload, kind, label=path)
        validator.validate(payload, None, label=path)
        data = serialize(payload)
        _check_size(validator, kind, len(data), path, strict=strict_sizes, warnings=warnings)
        files[path] = data
        listed.append((path, kind, data))
    manifest = build_manifest(listed, created=created, version=version, sample=sample)
    validator.validate(manifest, "manifest", label=FILE_PATHS["manifest"])
    validator.validate(manifest, None, label=FILE_PATHS["manifest"])
    data = serialize(manifest)
    _check_size(validator, "manifest", len(data), FILE_PATHS["manifest"], strict=strict_sizes, warnings=warnings)
    total_limit = _get(validator.schema, "$defs", "manifest", "properties", "toplam_bayt").get("maximum")
    total = sum(len(v) for v in files.values()) + len(data)
    if total_limit is not None and total > int(total_limit):
        raise ExportError(f"total {total} bytes > {total_limit} bytes")
    files[FILE_PATHS["manifest"]] = data
    return files


def write_site(files: Mapping[str, bytes], out_dir: Path, *, stamp: str) -> Path:
    """Write ``files`` (site path 'veri/...' -> bytes) to ``out_dir`` without overwriting anything.

    ``out_dir`` must not exist. Files go into a staging folder ``.<name>.yaziliyor-<stamp>`` next to it (exclusive
    create, read back and sha256-checked), which is renamed to ``out_dir`` at the end. On failure the staging folder
    is left in place for inspection (it is never the published folder)."""
    out = Path(out_dir)
    if out.exists():
        raise ExportError(f"output folder exists, will not overwrite: {out}")
    staging = out.parent / f".{out.name}.yaziliyor-{stamp}"
    if staging.exists():
        raise ExportError(f"staging folder exists: {staging}")
    staging.mkdir(parents=True)
    for path, data in sorted(files.items()):
        if not path.startswith(SITE_PREFIX) or ".." in path:
            raise ExportError(f"unexpected site path {path!r}")
        target = staging / path[len(SITE_PREFIX) :]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
        if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(data).digest():
            raise ExportError(f"read-back check failed: {target}")
    if out.exists():
        raise ExportError(f"output folder appeared while writing, will not overwrite: {out} (files are in {staging})")
    os.rename(staging, out)
    return out


# ----------------------------------------------------------------------------
# optimizasyon.json (block-time buffer optimisation; added 2026-11-24)
# ----------------------------------------------------------------------------

OR_RESULTS = "experiments/or/tampon-20261122T173803Z/tampon-sonuclari.json"  # policies frozen before the test
OR_SOLVER_RESULTS = "experiments/or/cozucu-20261122T181720Z/cozucu-sonuclari.json"  # exploratory (post hoc)

OR_POLICY_LABELS: dict[str, tuple[str, str]] = {
    "none": ("Ek tampon yok (bugünkü tarife)", "No extra buffer (current schedule)"),
    "b1": ("Basit kural (B1, geçmişe bakar)", "Simple rule B1 (historical statistics)"),
    "plan": ("Plan modeli", "Plan model"),
    "plan_conformal": ("Plan modeli + conformal", "Plan model + conformal"),
    "b1_conformal": ("B1 + conformal", "B1 + conformal"),
    "plan_flight": ("Plan modeli, uçuş bazında (ikincil)", "Plan model, flight level (secondary)"),
    "plan_budget": ("Plan modeli, dakika hedefli", "Plan model, minutes objective"),
    "b1_budget": ("B1, dakika hedefli", "B1, minutes objective"),
    "plan_arrdel15_budget": (
        "Geç uçuş sayısını azaltma hedefli, ortalama dağılımla",
        "Knapsack (15-min objective), averaged cells",
    ),
    "plan_arrdel15_mixture": (
        "Geç uçuş sayısını azaltma hedefli, karışım dağılımıyla",
        "Knapsack (15-min objective), mixture cells",
    ),
}
_OR_COMPARISON_METRICS = {
    "d_cost": "maliyet",
    "d_residual": "kalan_rotar_dk",
    "d_late15": "arrdel15_orani",
    "d_unused": "kullanilmayan_dk",
}
OR_NOTES: tuple[tuple[str, str], ...] = (
    (
        "Maliyetler varsayımdır: Yalnızca bir dakika rötarın bir dakika boş beklemeye göre ne kadar pahalı "
        "sayıldığı (τ) seçilir. Gösterilen maliyet para değil, ağırlıklandırılmış dakikadır.",
        "Costs are assumptions: only the ratio tau = c_u/(c_u + c_o) is chosen; cost is in normalised 'weighted "
        "minutes' (c_u = tau, c_o = 1 - tau), not money.",
    ),
    (
        "Varsayım: 1 dakika tampon, varış rötarını 1 dakika azaltır. Uçağın gün içindeki diğer seferleri, ekip "
        "planlaması ve ağ etkileri hesaba katılmadı.",
        "Assumption: 1 minute of buffer = 1 minute less arrival delay; no aircraft rotation, crew or network effects.",
    ),
    (
        "Tampon kuralları test döneminden önce sabitlendi; test dönemi (Mart–Ağustos 2026) yalnızca sonucu ölçmek "
        "için kullanıldı.",
        "Policies were frozen before the test period; the test period (2026-03..08) was only used for evaluation.",
    ),
    (
        "Maliyet ve tampon dakikaları yalnızca gerçekleşen uçuşlar için hesaplandı; iptal edilen ve başka "
        "havalimanına inen uçuşlar dahil değil.",
        "Costs and buffer minutes are over completed flights; cancelled and diverted flights carry no delay cost.",
    ),
)


def _or_policy_row(key: str, policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kimlik": key,
        "ek_tampon_dk": _minutes(policy.get("buffer_completed_mean_min")),
        "kalan_rotar_dk": _minutes(policy.get("residual_mean_min")),
        "kullanilmayan_dk": _minutes(policy.get("unused_mean_min")),
        "arrdel15_orani": _rate(policy.get("arr_del15_rate")),
        "emilen_orani": _rate(policy.get("absorbed_rate")),
        "maliyet": None if policy.get("cost_mean") is None else round(float(policy["cost_mean"]), 3),
    }


def _or_comparisons(comparisons: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for name, entry in comparisons.items():
        for source, metric_name in _OR_COMPARISON_METRICS.items():
            ci = (entry or {}).get(source)
            if not ci:
                continue
            row = metric(metric_name, ci.get("estimate"), "skor", ci=ci)
            row.pop("birim", None)
            out.append({"karsilastirma": name, **row})
    return out


def build_optimizasyon(
    or_results: Mapping[str, Any],
    solver_results: Mapping[str, Any] | None,
    *,
    created: dt.datetime,
    version: str,
    sample: bool = False,
) -> dict[str, Any]:
    """``optimizasyon.json``: frozen OR policies evaluated on the final-test period (tau grid, equal-budget curve)
    and, separately labelled, the exploratory solver extension (mixture-cell knapsack). Numbers are copied and
    rounded only."""
    test = _get(or_results, "periods", "test")
    counts = _get(test, "counts")
    payload = header("optimizasyon", created, version, sample)
    payload["kume"] = KUME
    payload["sayilar"] = {
        "tarifeli": int(counts["scheduled"]),
        "tamamlanan": int(counts["completed_with_arr_delay"]),
        "iptal": int(counts["cancelled"]),
        "sapma": int(counts["diverted"]),
    }
    used: set[str] = set()
    grid = []
    for _key, level in sorted(_get(test, "levels").items(), key=lambda kv: float(kv[1]["level"])):
        policies = []
        for key, policy in level["policies"].items():
            if key not in OR_POLICY_LABELS:
                raise ExportError(f"unknown OR policy {key!r}")
            used.add(key)
            policies.append(_or_policy_row(key, policy))
        grid.append(
            {
                "tau": round(float(level["level"]), 3),
                "maliyet_orani": round(float(level["cost_weights"]["c_u_over_c_o"]), 3),
                "politikalar": policies,
                "karsilastirmalar": _or_comparisons(level.get("comparisons") or {}),
            }
        )
    payload["tau_izgarasi"] = grid
    curve = []
    for _key, step in sorted(_get(test, "budget_curve").items(), key=lambda kv: float(kv[1]["budget_per_flight_min"])):
        rows = []
        for key, policy in step["policies"].items():
            used.add(key)
            rows.append(_or_policy_row(key, policy))
        curve.append(
            {
                "butce_dk": float(step["budget_per_flight_min"]),
                "politikalar": rows,
                "karsilastirmalar": _or_comparisons(step.get("comparisons") or {}),
            }
        )
    payload["butce_egrisi"] = curve
    if solver_results is not None:
        if solver_results.get("exploratory_post_hoc") is not True:
            raise ExportError("solver results are not labelled exploratory_post_hoc")
        solver_curve = []
        solver_test = _get(solver_results, "periods", "test", "solver", "curve")
        for _key, step in sorted(solver_test.items(), key=lambda kv: float(kv[1]["budget_per_flight_min"])):
            expected = step.get("expected_vs_realized") or {}
            rows = []
            for key, policy in step["policies"].items():
                if key not in OR_POLICY_LABELS:
                    continue
                used.add(key)
                row = _or_policy_row(key, policy)
                exp = (expected.get(key) or {}).get("expected_rate_completed_rows")
                row["beklenen_arrdel15_orani"] = _rate(exp)
                rows.append(row)
            solver_curve.append({"butce_dk": float(step["budget_per_flight_min"]), "politikalar": rows})
        payload["kesifsel"] = {
            "etiket": "Keşifsel (post hoc): Bu yöntemler test dönemi daha önce görüldükten sonra denendi; bu yüzden son test sonucu sayılmaz.",
            "etiket_en": "Exploratory (post hoc): this test period had already been seen for these policies; "
            "not a final-test result.",
            "butce_egrisi": solver_curve,
        }
    payload["politikalar"] = [
        {"kimlik": key, "etiket": OR_POLICY_LABELS[key][0], "etiket_en": OR_POLICY_LABELS[key][1]}
        for key in OR_POLICY_LABELS
        if key in used
    ]
    payload["notlar"] = [tr for tr, _ in OR_NOTES]
    payload["notlar_en"] = [en for _, en in OR_NOTES]
    assert_no_forbidden_keys(payload, where="optimizasyon")
    return payload
