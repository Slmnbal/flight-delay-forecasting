"""GitHub Pages sitesi (deliverables/src/web) için statik denetimler.

Burada tarayıcı çalıştırılmaz ve sunucu başlatılmaz. Testler sitenin dosyalarını metin olarak okur
ve yayımlamadan önce geçerli olması gereken kuralları denetler: dış kaynak yok, güvensiz DOM API'si
yok, sıkı CSP, yalnızca göreli yollar, betiklerin okuduğu her veri dosyası manifestte listeli ve
sunum kuralları (havayolu adı yok, "worst"/"en kötü" yok, Türkçe sorumluluk reddi, tampon uyarısı,
sözlük sekmesi, "null" metninin ekrana sızmaması).
Veri klasörü (veri/) ve harita klasörü (harita/) okunur, asla yazılmaz.
"""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

DELIVERABLES = Path(__file__).resolve().parents[3]
WEB = DELIVERABLES / "src" / "web"
VERI = WEB / "veri"
HARITA = WEB / "harita"
SCHEMA = DELIVERABLES.parent / "experiments" / "arayuz-sozlesmesi.json"

DISCLAIMER = "Kamu verisine dayalı; havayollarıyla bağlantısız."
BUFFER_WARNING = "varsayılmış maliyet oranı; operasyonel öneri değildir"
OR_NOTE_PREFIX = "Tampon optimizasyonu (OR):"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
GLOSSARY_GROUPS = ["Veri ve hedef", "Model ve tahmin", "Ölçütler", "İstatistik", "Optimizasyon (OR)"]

SOURCE_SUFFIXES = {".html", ".css", ".js", ".svg"}


def source_files() -> list[Path]:
    """Sitenin HTML, CSS, JS ve SVG dosyaları (veri ve harita klasörleri hariç)."""
    return sorted(
        p
        for p in WEB.rglob("*")
        if p.is_file() and p.suffix in SOURCE_SUFFIXES and VERI not in p.parents and HARITA not in p.parents
    )


def js_files() -> list[Path]:
    return [p for p in source_files() if p.suffix == ".js"]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def view(name: str) -> str:
    """Bir görünümün betiği ile tüm arayüz metinlerini (metin.js) birlikte döndürür."""
    return read(WEB / "js" / "views" / f"{name}.js") + "\n" + read(WEB / "js" / "metin.js")


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):  # noqa: D401
        self.tags.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


@pytest.fixture(scope="module")
def html() -> str:
    return read(WEB / "index.html")


@pytest.fixture(scope="module")
def tags(html):
    collector = _Collector()
    collector.feed(html)
    return collector.tags


def walk_tokens(node, out: set[str]) -> None:
    """Her anahtarı ve her metin değerini toplar (JS'teki alan adlarıyla karşılaştırmak için)."""
    if isinstance(node, dict):
        for key, value in node.items():
            out.add(key)
            walk_tokens(value, out)
    elif isinstance(node, list):
        for item in node:
            walk_tokens(item, out)
    elif isinstance(node, str):
        out.add(node)


def collect_keys(node, keys: set[str]) -> None:
    """Bir JSON ağacındaki tüm anahtarları `keys` kümesine ekler (döngü değişkenine bağlı değil)."""
    if isinstance(node, dict):
        keys.update(node.keys())
        for value in node.values():
            collect_keys(value, keys)
    elif isinstance(node, list):
        for value in node:
            collect_keys(value, keys)


# --------------------------------------------------------------------------- yapı


def test_expected_files_exist():
    for rel in [
        "index.html",
        "css/style.css",
        "js/main.js",
        "js/data.js",
        "js/metin.js",
        "js/sozluk-terimleri.js",
        "js/views/sozluk.js",
        "js/theme-init.js",
        "veri/manifest.json",
        "harita/abd-eyaletler.json",
    ]:
        assert (WEB / rel).is_file(), rel


def test_html_basics(html, tags):
    assert re.search(r"<html[^>]*\blang=\"tr\"", html)
    names = [t for t, _ in tags]
    assert names.count("h1") == 1
    assert names.count("main") == 1
    assert "nav" in names
    assert any(t == "meta" and a.get("name") == "viewport" for t, a in tags)
    assert any(t == "a" and a.get("class") == "skip" for t, a in tags)


def test_sections_are_labelled_and_routed(tags):
    sections = [a for t, a in tags if t == "section" and (a.get("id") or "").startswith("view-")]
    assert len(sections) == 8
    for attrs in sections:
        assert attrs.get("aria-labelledby"), attrs
    ids = {a["id"].removeprefix("view-") for a in sections}
    nav_order = [a["data-nav"] for t, a in tags if t == "a" and a.get("data-nav")]
    assert set(nav_order) == ids
    assert nav_order[-1] == "sozluk", "Sözlük sekmesi navigasyonun sonunda olmalı"
    main_js = read(WEB / "js" / "main.js")
    for name in ids:
        assert (WEB / "js" / "views" / f"{name}.js").is_file(), name
        assert f"./views/{name}.js" in main_js, name


def test_no_positive_tabindex(tags):
    for _, attrs in tags:
        value = attrs.get("tabindex")
        if value is not None:
            assert int(value) <= 0, attrs


def test_css_has_accessibility_hooks():
    css = read(WEB / "css" / "style.css")
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "prefers-color-scheme" in css
    assert '[data-theme="dark"]' in css


# --------------------------------------------------------------------------- güvenlik


def test_csp_is_strict(tags):
    metas = [a for t, a in tags if t == "meta" and (a.get("http-equiv") or "").lower() == "content-security-policy"]
    assert len(metas) == 1
    csp = metas[0]["content"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert not re.search(r"https?:|\*", csp)
    assert "object-src 'none'" in csp


def test_html_has_no_inline_code_or_styles(html, tags):
    for tag, attrs in tags:
        assert tag != "style"
        assert "style" not in attrs, (tag, attrs)
        for name in attrs:
            assert not name.startswith("on"), (tag, name)
        if tag == "script":
            assert attrs.get("src"), "inline <script> is not allowed by the CSP"
    assert "javascript:" not in html.lower()


def test_no_external_resources():
    for path in source_files():
        text = read(path)
        for url in re.findall(r"https?://[^\s\"'<>)\\]+", text):
            assert url == SVG_NAMESPACE, f"{path.name}: external URL {url}"
        assert not re.search(r"""(?:src|href)\s*=\s*["']//""", text), path.name
        assert not re.search(r"""["'`]//[A-Za-z]""", text) or path.suffix == ".css", path.name
        assert "@import" not in text, path.name
        assert not re.search(r"url\(\s*[\"']?(?!#)", text) or path.suffix != ".css", path.name


def test_no_unsafe_dom_apis():
    forbidden = [
        r"\.innerHTML",
        r"\.outerHTML",
        r"insertAdjacentHTML",
        r"document\.write",
        r"\beval\s*\(",
        r"new\s+Function",
        r"createContextualFragment",
        r"setAttribute\(\s*['\"]on",
        r"\.srcdoc",
        r"importScripts",
        r"\bXMLHttpRequest\b",
        r"\bWebSocket\b",
        r"sendBeacon",
    ]
    for path in js_files():
        text = read(path)
        for pattern in forbidden:
            assert not re.search(pattern, text), f"{path.name}: {pattern}"


def test_fetch_only_through_the_data_module():
    for path in js_files():
        text = read(path)
        calls = re.findall(r"\bfetch\s*\(([^)]*)\)", text)
        if path.name == "data.js":
            assert calls and all(c.strip().startswith(("BASE", "HARITA")) for c in calls), calls
            assert any(c.strip().startswith("HARITA") for c in calls), "eyalet dosyası fetch'i yok"
        else:
            assert not calls, path.name


def test_only_relative_paths():
    html = read(WEB / "index.html")
    for value in re.findall(r"""(?:src|href)\s*=\s*["']([^"']*)["']""", html):
        assert value.startswith(("./", "#")), value
    data_js = read(WEB / "js" / "data.js")
    assert "const BASE = './veri/';" in data_js
    assert "const HARITA = './harita/';" in data_js
    for path in js_files():
        text = read(path)
        assert not re.search(r"""['"`]/(?:veri|harita|css|js)/""", text), path.name
        for spec in re.findall(r"""(?:from\s+|import\s*\(\s*)['"]([^'"]+)['"]""", text):
            assert spec.startswith(("./", "../")), (path.name, spec)
            assert (path.parent / spec).resolve().is_file(), (path.name, spec)


def test_links_from_data_are_https_only():
    fmt = read(WEB / "js" / "fmt.js")
    assert "protocol === 'https:'" in fmt


# --------------------------------------------------------------------------- veri sözleşmesi


def test_manifest_matches_disk():
    manifest = json.loads(read(VERI / "manifest.json"))
    assert manifest["dosya_turu"] == "manifest"
    total = 0
    for entry in manifest["dosyalar"]:
        path = WEB / entry["yol"]
        assert path.is_file(), entry["yol"]
        raw = path.read_bytes()
        assert len(raw) == entry["bayt"], entry["yol"]
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], entry["yol"]
        total += len(raw)
    assert total <= manifest["toplam_bayt"]


def test_every_data_file_read_by_scripts_is_in_the_manifest():
    manifest = json.loads(read(VERI / "manifest.json"))
    listed = {e["yol"].removeprefix("veri/") for e in manifest["dosyalar"]}
    referenced: set[str] = set()
    uses_route_template = False
    for path in js_files():
        text = read(path)
        referenced.update(re.findall(r"""['"]([a-z0-9-]+\.json)['"]""", text))
        if "`rotalar/${" in text:
            uses_route_template = True
    assert referenced, "no data file names found in scripts"
    for name in referenced:
        # Harita dosyası manifestte değil, harita/ klasöründedir.
        assert name in listed or name == "manifest.json" or (HARITA / name).is_file(), name
    assert uses_route_template
    # Haritadaki her havalimanının rota dosyası vardır ve her rota dosyası bilinen bir havalimanına aittir.
    airports = json.loads(read(VERI / "havalimanlari.json"))["havalimanlari"]
    codes = {a["iata"] for a in airports}
    route_files = {n.removeprefix("rotalar/").removesuffix(".json") for n in listed if n.startswith("rotalar/")}
    assert codes == route_files


def test_data_files_are_real_results_and_have_no_carrier_dimension():
    banned_key_parts = ("tasiyici", "carrier", "airline", "kuyruk", "tail", "ucus_no", "flight_num", "neden_kodu")
    for path in sorted(VERI.rglob("*.json")):
        doc = json.loads(read(path))
        assert doc.get("ornek") is False, f"{path.name} is marked as sample data"
        keys: set[str] = set()
        collect_keys(doc, keys)
        for key in keys:
            assert not any(part in key.lower() for part in banned_key_parts), (path.name, key)


def test_field_names_used_in_scripts_exist_in_data_or_schema():
    known: set[str] = set()
    for path in sorted(VERI.rglob("*.json")):
        walk_tokens(json.loads(read(path)), known)
    if SCHEMA.is_file():
        walk_tokens(json.loads(read(SCHEMA)), known)
    pattern = re.compile(r"\.([a-z][a-z0-9]*(?:_[A-Za-z0-9]+)+)\b|['\"]([a-z][a-z0-9]*(?:_[A-Za-z0-9]+)+)['\"]")
    for path in js_files():
        for dotted, quoted in pattern.findall(read(path)):
            token = dotted or quoted
            assert token in known, f"{path.name}: unknown field or value {token!r}"


def test_state_boundary_file_is_well_formed():
    doc = json.loads(read(HARITA / "abd-eyaletler.json"))
    assert doc["dosya_turu"] == "harita_eyaletler"
    assert "Natural Earth" in doc["kaynak"]
    states = doc["eyaletler"]
    assert len(states) >= 49, "48 eyalet + DC beklenir"
    for state in states:
        assert re.fullmatch(r"[A-Z]{2}", state["eyalet"]), state["eyalet"]
        assert state["halkalar"], state["eyalet"]
        for ring in state["halkalar"]:
            assert len(ring) >= 4 and ring[0] == ring[-1], state["eyalet"]
            for lon, lat in ring:
                assert -130 < lon < -60 and 20 < lat < 55, (state["eyalet"], lon, lat)


def test_disclaimer_present_in_page_and_data(html):
    assert DISCLAIMER in html
    assert f"sorumluluk: '{DISCLAIMER}'" in read(WEB / "js" / "metin.js")
    ozet = json.loads(read(VERI / "ozet.json"))
    assert "havayol" in ozet["proje"]["sorumluluk_reddi"].lower()
    assert "sorumluluk_reddi" in read(WEB / "js" / "main.js")


# --------------------------------------------------------------------------- sunum kuralları


def test_no_worst_and_no_airline_names_or_codes():
    names = [
        "American Airlines",
        "Delta Air",
        "Delta Airlines",
        "United Airlines",
        "JetBlue",
        "Alaska Airlines",
        "Spirit Airlines",
        "Frontier Airlines",
        "Allegiant",
        "Hawaiian Airlines",
        "SkyWest",
        "Envoy Air",
        "Republic Airways",
        "Endeavor Air",
        "Mesa Airlines",
        "PSA Airlines",
        "Horizon Air",
        "Air Wisconsin",
        "Sun Country",
        "Breeze Airways",
        "GoJet",
        "CommuteAir",
        "Piedmont Airlines",
        "ExpressJet",
        "Virgin America",
        "Compass Airlines",
        "Trans States",
    ]
    standalone = re.compile(r"\b(Southwest|Delta|Frontier|Spirit|Alaska|Hawaiian)\b")
    codes = re.compile(r"""['"](?:AA|DL|UA|WN|B6|AS|NK|F9|G4|HA|OO|YX|9E|MQ|OH|QX|YV|EV|MX|XE|ZW|CP|C5|G7)['"]""")
    worst = re.compile(r"worst|\ben\s+k[öo]t[üu]\b", re.IGNORECASE)
    for path in source_files():
        text = read(path)
        assert not worst.search(text), (path.name, worst.search(text).group(0) if worst.search(text) else "")
        for name in names:
            assert name.lower() not in text.lower(), (path.name, name)
        match = standalone.search(text)
        assert not match, (path.name, match.group(0) if match else "")
        assert not codes.search(text), path.name


def test_no_delay_cause_fields_and_no_flight_identifiers():
    causes = [
        "carrier_delay",
        "weather_delay",
        "nas_delay",
        "security_delay",
        "late_aircraft",
        "tail_num",
        "flight_num",
    ]
    for path in source_files():
        text = read(path).lower()
        for term in causes:
            assert term not in text, (path.name, term)


def test_error_analysis_uses_neutral_headings():
    errors = view("errors")
    assert "En büyük kalibrasyon sapmaları" in errors
    assert "en küçük Brier skor kazancına" in errors


def test_hidden_airports_and_route_notes_are_shown():
    airports = view("airports")
    assert "Yayımlanmadı" in airports
    assert "gizleme_nedeni" in read(WEB / "js" / "views" / "airports.js")
    routes = view("routes")
    assert "n < 50" in routes and "%90" in routes


def test_buffer_suggestion_carries_the_warning():
    metin = read(WEB / "js" / "metin.js")
    assert f"BUFFER_WARNING = '{BUFFER_WARNING}'" in metin
    assert "${BUFFER_WARNING}" in metin, "uyarı görünür bildirimde kullanılmalı"
    routes_js = read(WEB / "js" / "views" / "routes.js")
    assert "tampon_onerisi_dk" in routes_js
    # Uyarı, sütun başlığının ipucunda (title) ve görünür bildirimde yer alır.
    assert "tamponIpucu(BUFFER_WARNING)" in routes_js
    assert "t.uyari" in routes_js


def test_failed_criteria_and_buffer_finding_are_visible():
    overview = read(WEB / "js" / "views" / "overview.js")
    metin = read(WEB / "js" / "metin.js")
    assert "'kaldi'" in overview
    assert "kaldi: 'Geçmedi'" in metin
    # OR bulgusu sayfaya elle yazılmaz; veri notundan, önekle bulunur.
    assert OR_NOTE_PREFIX in overview
    assert "startsWith(OR_NOTE_PREFIX)" in overview
    assert "eşit bütçe" not in metin.lower() and "eşit bütçe" not in overview.lower()
    ozet = json.loads(read(VERI / "ozet.json"))
    failed = {k["olcut"] for k in ozet["kabul"] if k["sonuc"] == "kaldi"}
    assert {"K5", "K6"} <= failed


def test_roc_and_pr_rows_use_difference_intervals_from_data():
    overview = read(WEB / "js" / "views" / "overview.js")
    assert "roc_auc_farki_b1" in overview and "pr_auc_farki_b1" in overview


def test_notes_box_and_no_hand_written_data_notes():
    about = read(WEB / "js" / "views" / "about.js")
    assert "ozet.notlar" in about
    metin = read(WEB / "js" / "metin.js")
    assert "notlarBaslik: 'Notlar'" in metin
    errors = read(WEB / "js" / "views" / "errors.js")
    # "Olay günü" tanımı elle yazılmaz; Sözlük'e bağlantı verilir.
    assert "sozlukLink('olay-gunu'" in errors
    # Harita kaynak atfı Hakkında bölümünde.
    assert "Harita: Natural Earth (kamu malı)" in metin


# --------------------------------------------------------------------------- dil ve metin


def test_site_language_is_turkish(html):
    assert re.search(r"[çğışöüÇĞİŞÖÜ]", html), "statik HTML Türkçe karakterler içermeli"
    for english in ["Skip to content", "Overview", "Airports", "Loading", "Weather experiment", "Error analysis"]:
        assert english not in html, english
    for path in js_files():
        text = read(path)
        assert not re.search(
            r"Loading data|Not published|Show more rows|Select a point|Try again|Reload this section|Colour points",
            text,
        ), path.name


def test_all_ui_text_lives_in_metin_module():
    # Görünümlerde İngilizce kalıp cümle bırakılmadı; metinler T nesnesinden gelir.
    metin = read(WEB / "js" / "metin.js")
    assert "export const T = {" in metin
    for key in ["bolumler", "genel", "havalimani", "rota", "kal", "hava", "hataAnalizi", "hakkinda", "sozluk"]:
        assert re.search(rf"^  {key}: ", metin, re.MULTILINE), key
    fmt = read(WEB / "js" / "fmt.js")
    assert "`,${dec}`" in fmt, "ondalık virgül"
    assert "'.'" in fmt, "binlik ayırıcı nokta"
    assert "`${p.sign}%${p.body}`" in fmt, "yüzde işareti başta"


def test_text_content_assignments_use_a_formatter():
    """Her textContent atamasının sağ tarafı bir metin ya da biçimleyiciden gelir ("null" sızmaz)."""
    allowed = re.compile(r"^(?:['\"`]|txt\(|T\.|arrowFor\(|\w*Text\()")
    seen = 0
    for path in js_files():
        for match in re.finditer(r"\.textContent\s*=(?!=)\s*([^;]+);", read(path)):
            seen += 1
            rhs = match.group(1).strip()
            assert allowed.match(rhs), (path.name, rhs)
            if rhs.startswith("`"):
                for expr in re.findall(r"\$\{([^}]*)\}", rhs):
                    assert expr.strip().startswith(("txt(", "fmt", "T.")), (path.name, expr)
    assert seen > 0


def test_replace_children_is_only_used_through_the_null_safe_helper():
    """replaceChildren(null) ekrana "null" yazar; argümanlı çağrı yalnızca dom.js içinde (fill) yapılır."""
    for path in js_files():
        if path.name == "dom.js":
            continue
        assert not re.search(r"replaceChildren\((?!\))", read(path)), path.name
    dom = read(WEB / "js" / "dom.js")
    assert "child === null || child === undefined || child === false" in dom
    assert "export function fill(" in dom


def test_routes_filters_area_cannot_render_null():
    routes = read(WEB / "js" / "views" / "routes.js")
    assert "fill(\n    ui.airportNote" in routes, "airportNote null değerle doldurulabilir; fill() kullanılmalı"
    assert "airportNote.replaceChildren" not in routes


# --------------------------------------------------------------------------- sözlük


def _glossary_sections() -> dict[str, str]:
    text = read(WEB / "js" / "sozluk-terimleri.js")
    starts = []
    for group in GLOSSARY_GROUPS:
        marker = f"ad: '{group}'"
        assert marker in text, f"sözlük grubu yok: {group}"
        starts.append(text.index(marker))
    assert starts == sorted(starts)
    ends = [*starts[1:], len(text)]
    return {g: text[s:e] for g, s, e in zip(GLOSSARY_GROUPS, starts, ends, strict=True)}


def test_glossary_has_every_group_with_terms():
    sections = _glossary_sections()
    for group, body in sections.items():
        assert len(re.findall(r"\{ id: '[a-z0-9-]+', terim: '", body)) >= 1, group
    ids = re.findall(r"\{ id: '([a-z0-9-]+)'", read(WEB / "js" / "sozluk-terimleri.js"))
    assert len(ids) == len(set(ids)), "yinelenen terim kimliği"
    assert len(ids) >= 40


def test_glossary_covers_required_terms():
    ids = set(re.findall(r"\{ id: '([a-z0-9-]+)'", read(WEB / "js" / "sozluk-terimleri.js")))
    required = [
        "arrdel15",
        "bts",
        "metar",
        "b1",
        "plan-modeli",
        "t2-modeli",
        "conformal",
        "kapsama",
        "sizinti",
        "roc-auc",
        "pr-auc",
        "brier",
        "ece",
        "citl",
        "pinball",
        "guven-araligi",
        "gun-blok-bootstrap",
        "holm",
        "newsvendor",
        "maliyet-orani",
        "lp-milp",
        "tek-havayolu-kurali",
        "olay-gunu",
    ]
    for term_id in required:
        assert term_id in ids, term_id


def test_glossary_links_point_to_existing_terms():
    ids = set(re.findall(r"\{ id: '([a-z0-9-]+)'", read(WEB / "js" / "sozluk-terimleri.js")))
    used = set()
    for path in js_files():
        used.update(re.findall(r"sozlukLink\(\s*'([^']+)'", read(path)))
    assert used, "hiçbir yerde sözlük bağlantısı yok"
    assert used <= ids, used - ids


def test_glossary_view_has_search_and_term_anchors():
    sozluk = read(WEB / "js" / "views" / "sozluk.js")
    assert "type: 'search'" in sozluk
    assert "`#sozluk/${term.id}`" in sozluk
    assert "export function onParams" in sozluk
    main_js = read(WEB / "js" / "main.js")
    assert "'sozluk'" in main_js


# --------------------------------------------------------------------------- harita


def test_map_uses_state_layer_and_label_placement():
    map_js = read(WEB / "js" / "map.js")
    assert "placeLabels" in map_js
    assert "o.states" in map_js
    assert "halkalar" in map_js
    assert "albers(" in map_js
    # Eksen etiketleri ayrı köşelerde: enlemler batı ucunda, boylamlar güney ucunda.
    assert "°K" in map_js and "°B" in map_js
    airports = read(WEB / "js" / "views" / "airports.js")
    assert "loadEyaletler" in airports
    data_js = read(WEB / "js" / "data.js")
    assert "() => null" in data_js, "eyalet dosyası yüklenemezse harita ızgarayla çalışmalı"


def test_site_files_stay_small():
    for path in source_files():
        assert path.stat().st_size < 60_000, path.name
