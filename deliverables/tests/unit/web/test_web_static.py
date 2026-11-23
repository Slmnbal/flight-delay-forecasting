"""GitHub Pages sitesi (deliverables/src/web) için statik denetimler.

Burada tarayıcı çalıştırılmaz ve sunucu başlatılmaz. Testler sitenin dosyalarını metin olarak okur
ve yayımlamadan önce geçerli olması gereken kuralları denetler: dış kaynak yok, güvensiz DOM API'si
yok, sıkı CSP, yalnızca göreli yollar, betiklerin okuduğu her veri dosyası manifestte listeli ve
sunum kuralları (havayolu adı yok, "worst"/"en kötü" yok, iki dilde sorumluluk reddi, tampon uyarısı,
sözlük sekmesi, "null" metninin ekrana sızmaması). İki dilli arayüz (TR / EN) için: her metin
anahtarının iki dilde değeri vardır, sözlük terimlerinin İngilizce alanı vardır, hikâye ve OR sekmeleri
sayfada ve kaydırıcıda aria-valuetext vardır.
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
DISCLAIMER_EN = "Based on public data; not affiliated with any airline."
BUFFER_WARNING = "varsayılmış maliyet oranı; operasyonel öneri değildir"
BUFFER_WARNING_EN = "assumed cost ratio; not an operational recommendation"
OR_NOTE_PREFIX = "Tampon optimizasyonu (OR):"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
GLOSSARY_GROUPS = ["Veri ve hedef", "Model ve tahmin", "Ölçütler", "İstatistik", "Optimizasyon (OR)"]
VIEWS = [
    "story",
    "overview",
    "airports",
    "routes",
    "optimization",
    "calibration",
    "weather",
    "errors",
    "about",
    "sozluk",
]

SOURCE_SUFFIXES = {".html", ".css", ".js", ".svg"}
TEXT_MODULES = {"metin.js", "metin-en.js"}  # iki dilli metin dosyaları; diğer dosyalar 60 KB altında kalır


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
    """Bir görünümün betiği ile Türkçe arayüz metinlerini (metin.js) birlikte döndürür."""
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


# --------------------------------------------------------------------------- metin nesnesi okuyucu
# metin.js (TR) ve metin-en.js (EN) içindeki nesne değişmezlerinden anahtar yollarını çıkarır.
# JavaScript çalıştırılmaz; dizgeler, şablon dizgeleri ve parantezler elle gezilir.

_KEY = re.compile(r"""([A-Za-z_$][\w$]*|'[^']*'|"[^"]*")\s*:""")


def _skip_string(src: str, i: int) -> int:
    quote = src[i]
    i += 1
    while src[i] != quote:
        i += 2 if src[i] == "\\" else 1
    return i + 1


def _skip_template(src: str, i: int) -> int:
    i += 1
    while src[i] != "`":
        if src[i] == "\\":
            i += 2
        elif src.startswith("${", i):
            i = _skip_braces(src, i + 1)
        else:
            i += 1
    return i + 1


def _skip_braces(src: str, i: int) -> int:
    """src[i] == '{'; eşleşen '}' karakterinden sonraki dizini döndürür."""
    depth = 0
    while True:
        ch = src[i]
        if ch in "'\"":
            i = _skip_string(src, i)
        elif ch == "`":
            i = _skip_template(src, i)
        else:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1


def _skip_space(src: str, i: int) -> int:
    while True:
        while src[i].isspace():
            i += 1
        if src.startswith("//", i):
            i = src.index("\n", i)
        else:
            return i


def _parse_value(src: str, i: int) -> tuple[int, str, str]:
    start = i
    depth = 0
    while True:
        ch = src[i]
        if ch in "'\"":
            i = _skip_string(src, i)
            continue
        if ch == "`":
            i = _skip_template(src, i)
            continue
        if src.startswith("//", i):
            i = src.index("\n", i)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            break
        i += 1
    text = src[start:i].strip()
    kind = "arr" if text.startswith("[") else "fn" if "=>" in text else "str"
    return i, kind, text


def _parse_object(src: str, i: int, prefix: str, out: dict[str, tuple[str, str]]) -> int:
    i += 1  # '{'
    while True:
        i = _skip_space(src, i)
        if src[i] == "}":
            return i + 1
        match = _KEY.match(src, i)
        assert match, src[i : i + 60]
        key = match.group(1).strip("'\"")
        path = f"{prefix}.{key}" if prefix else key
        i = _skip_space(src, match.end())
        if src[i] == "{":
            out[path] = ("obj", "")
            i = _parse_object(src, i, path, out)
        else:
            i, kind, text = _parse_value(src, i)
            out[path] = (kind, text)
        i = _skip_space(src, i)
        if src[i] == ",":
            i += 1


def text_paths(file_name: str, const_name: str) -> dict[str, tuple[str, str]]:
    src = read(WEB / "js" / file_name)
    start = src.index("{", src.index(f"const {const_name} ="))
    out: dict[str, tuple[str, str]] = {}
    _parse_object(src, start, "", out)
    return out


@pytest.fixture(scope="module")
def tr_paths():
    return text_paths("metin.js", "TR")


@pytest.fixture(scope="module")
def en_paths():
    return text_paths("metin-en.js", "EN")


# --------------------------------------------------------------------------- yapı


def test_expected_files_exist():
    for rel in [
        "index.html",
        "css/style.css",
        "js/main.js",
        "js/data.js",
        "js/metin.js",
        "js/metin-en.js",
        "js/yerel.js",
        "js/or-ortak.js",
        "js/sozluk-terimleri.js",
        "js/views/sozluk.js",
        "js/views/story.js",
        "js/views/optimization.js",
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
    assert len(sections) == len(VIEWS)
    for attrs in sections:
        assert attrs.get("aria-labelledby"), attrs
    ids = {a["id"].removeprefix("view-") for a in sections}
    nav_order = [a["data-nav"] for t, a in tags if t == "a" and a.get("data-nav")]
    assert set(nav_order) == ids == set(VIEWS)
    assert nav_order == VIEWS, "sekme sırası: Hikâye ilk, OR Rotalar'dan sonra, Sözlük son"
    main_js = read(WEB / "js" / "main.js")
    for name in ids:
        assert (WEB / "js" / "views" / f"{name}.js").is_file(), name
        assert f"./views/{name}.js" in main_js, name


def test_story_and_or_sections_are_in_the_page(html, tags):
    for name in ("story", "optimization"):
        assert f'id="view-{name}"' in html
        assert f'id="h-{name}"' in html
        assert f'href="#{name}"' in html
    # Sekme başlıkları ve sabit metinler data-t anahtarıyla iki dile çevrilir.
    assert 'data-t="bolumler.story"' in html and 'data-t="bolumler.optimization"' in html


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
    assert "@media (max-width: 40rem)" in css, "telefon genişliği kuralları"
    assert "animation" not in css.replace("animation: none", ""), "kullanıcıdan bağımsız animasyon yok"


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
        r"setAttribute\(\s*['\"]style",
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


def test_optimization_file_is_read_and_listed_in_the_manifest():
    data_js = read(WEB / "js" / "data.js")
    assert "optimizasyon: 'optimizasyon.json'" in data_js
    assert "loadOptimizasyon" in read(WEB / "js" / "views" / "optimization.js")
    assert "loadOptimizasyon" in read(WEB / "js" / "views" / "story.js")
    manifest = json.loads(read(VERI / "manifest.json"))
    entries = {e["yol"]: e for e in manifest["dosyalar"]}
    assert "veri/optimizasyon.json" in entries
    assert entries["veri/optimizasyon.json"]["dosya_turu"] == "optimizasyon"


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


def test_english_data_fields_are_read_through_the_locale_module():
    yerel = read(WEB / "js" / "yerel.js")
    for field in [
        "ceviri_en",
        "kaynak_lisans_notlari",
        "gizleme_nedeni_en",
        "etiket_en",
        "notlar_en",
    ]:
        assert field in yerel, field
    assert "return loc(" in yerel and "typeof en === 'string'" in yerel, "İngilizce karşılık yoksa Türkçe'ye düşülür"
    # Veriden gelen metinler doğrudan değil, yerel.js üzerinden yazılır.
    for name, banned in {
        "overview": ["ozet.proje.baslik", "ozet.proje.aciklama", ".aciklama)"],
        "about": ["s.lisans_notu", "ozet.proje.sorumluluk_reddi"],
        "weather": ["v.etiket)"],
    }.items():
        text = read(WEB / "js" / "views" / f"{name}.js")
        for token in banned:
            assert token not in text, (name, token)


def test_ceviri_en_in_data_matches_turkish_fields():
    ozet = json.loads(read(VERI / "ozet.json"))
    en = ozet["ceviri_en"]
    assert len(en["kaynak_lisans_notlari"]) == len(ozet["proje"]["kaynaklar"])
    assert len(en["notlar"]) == len(ozet["notlar"])
    assert {m["kimlik"] for m in en["modeller"]} == {m["kimlik"] for m in ozet["modeller"]}
    assert {k["olcut"] for k in en["kabul"]} == {k["olcut"] for k in ozet["kabul"]}
    assert en["proje"]["baslik"] and en["proje"]["aciklama"] and en["proje"]["sorumluluk_reddi"]
    assert any(n.startswith(OR_NOTE_PREFIX) for n in ozet["notlar"])


def test_optimization_data_supports_story_and_or_tab():
    opt = json.loads(read(VERI / "optimizasyon.json"))
    assert opt["dosya_turu"] == "optimizasyon"
    assert len(opt["notlar"]) == len(opt["notlar_en"])
    for p in opt["politikalar"]:
        assert p["etiket"] and p["etiket_en"], p
    grid = opt["tau_izgarasi"]
    assert grid
    for point in grid:
        kimlikler = {r["kimlik"] for r in point["politikalar"]}
        assert {"none", "plan"} <= kimlikler, point["tau"]
    assert any(abs(point["tau"] - 0.8) < 1e-6 for point in grid), (
        "Rotalar sekmesinin varsayımı (τ = 0,80) ızgarada olmalı"
    )
    assert opt["butce_egrisi"]


def test_disclaimer_present_in_page_and_data(html):
    assert DISCLAIMER in html
    assert DISCLAIMER_EN in html, "JavaScript kapalıyken de İngilizce sorumluluk reddi (noscript)"
    assert f"sorumluluk: '{DISCLAIMER}'" in read(WEB / "js" / "metin.js")
    assert f"sorumluluk: '{DISCLAIMER_EN}'" in read(WEB / "js" / "metin-en.js")
    ozet = json.loads(read(VERI / "ozet.json"))
    assert "havayol" in ozet["proje"]["sorumluluk_reddi"].lower()
    assert "sorumluluk_reddi" in read(WEB / "js" / "yerel.js")
    main_js = read(WEB / "js" / "main.js")
    assert "sorumlulukReddi" in main_js and "footer-disclaimer" in main_js
    # Üst ve alt bilgi sorumluluk reddi dil anahtarına bağlıdır.
    assert html.count('data-t="sorumluluk"') == 2


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
    for path in source_files():  # metin-en.js dahil: İngilizce metinlerde de aynı kurallar
        text = read(path)
        assert not worst.search(text), (path.name, worst.search(text).group(0) if worst.search(text) else "")
        for name in names:
            assert name.lower() not in text.lower(), (path.name, name)
        match = standalone.search(text)
        assert not match, (path.name, match.group(0) if match else "")
        assert not codes.search(text), path.name


def test_no_process_words_in_interface_text():
    """Arayüz metinlerinde süreç ifadeleri (yapay zekâ aracı, ajan) geçmez."""
    for path in source_files():
        assert not re.search(r"\bAI\b|\bajan\b|\bagent\b", read(path)), path.name


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
    en = read(WEB / "js" / "metin-en.js")
    assert "Largest calibration deviations" in en
    assert "smallest Brier skill score" in en


def test_hidden_airports_and_route_notes_are_shown():
    airports = view("airports")
    assert "Yayımlanmadı" in airports
    assert "gizleme_nedeni" in read(WEB / "js" / "views" / "airports.js")
    assert "Not published" in read(WEB / "js" / "metin-en.js")
    routes = view("routes")
    assert "n < 50" in routes and "%90" in routes
    en = read(WEB / "js" / "metin-en.js")
    assert "fewer than 50 flights" in en and "90%" in en


def test_buffer_suggestion_carries_the_warning_in_both_languages():
    metin = read(WEB / "js" / "metin.js")
    assert f"BUFFER_WARNING = '{BUFFER_WARNING}'" in metin
    assert "${BUFFER_WARNING}" in metin, "uyarı görünür bildirimde kullanılmalı"
    assert "tamponUyari: BUFFER_WARNING," in metin
    en = read(WEB / "js" / "metin-en.js")
    assert f"BUFFER_WARNING_EN = '{BUFFER_WARNING_EN}'" in en
    assert "${BUFFER_WARNING_EN}" in en
    assert "tamponUyari: BUFFER_WARNING_EN," in en
    routes_js = read(WEB / "js" / "views" / "routes.js")
    assert "tampon_onerisi_dk" in routes_js
    # Uyarı, sütun başlığının ipucunda (title) ve görünür bildirimde yer alır.
    assert "tamponIpucu(T.tamponUyari)" in routes_js
    assert "t.uyari" in routes_js
    # Hikâye ve OR sekmesindeki tampon bölümleri de aynı uyarıyı gösterir.
    assert "T.genel.tampon.varsayim" in read(WEB / "js" / "views" / "story.js")
    assert "T.genel.tampon.varsayim" in read(WEB / "js" / "views" / "optimization.js")


def test_failed_criteria_and_buffer_finding_are_visible():
    overview = read(WEB / "js" / "views" / "overview.js")
    metin = read(WEB / "js" / "metin.js")
    yerel = read(WEB / "js" / "yerel.js")
    assert "'kaldi'" in overview
    assert "kaldi: 'Geçmedi'" in metin
    assert "kaldi: 'Not passed'" in read(WEB / "js" / "metin-en.js")
    # OR bulgusu sayfaya elle yazılmaz; veri notundan, önekle bulunur (TR notun başı, EN aynı sıradaki nottan).
    assert f"OR_NOTE_PREFIX = '{OR_NOTE_PREFIX}'" in yerel
    assert "startsWith(onek)" in yerel
    assert "notBul(ozet, OR_NOTE_PREFIX)" in overview
    assert "notBul(ozet, OR_NOTE_PREFIX)" in read(WEB / "js" / "views" / "optimization.js")
    assert "eşit bütçe" not in metin.lower() and "eşit bütçe" not in overview.lower()
    ozet = json.loads(read(VERI / "ozet.json"))
    failed = {k["olcut"] for k in ozet["kabul"] if k["sonuc"] == "kaldi"}
    assert {"K5", "K6"} <= failed


def test_roc_and_pr_rows_use_difference_intervals_from_data():
    overview = read(WEB / "js" / "views" / "overview.js")
    assert "roc_auc_farki_b1" in overview and "pr_auc_farki_b1" in overview


def test_notes_box_and_no_hand_written_data_notes():
    about = read(WEB / "js" / "views" / "about.js")
    assert "notlar(ozet)" in about
    metin = read(WEB / "js" / "metin.js")
    assert "notlarBaslik: 'Notlar'" in metin
    errors = read(WEB / "js" / "views" / "errors.js")
    # "Olay günü" tanımı elle yazılmaz; Sözlük'e bağlantı verilir.
    assert "sozlukLink('olay-gunu'" in errors
    # Harita kaynak atfı Hakkında bölümünde.
    assert "Harita: Natural Earth (kamu malı)" in metin
    assert "Map: Natural Earth (public domain)" in read(WEB / "js" / "metin-en.js")


# --------------------------------------------------------------------------- hikâye ve OR sekmesi


def test_or_tab_content_is_data_driven():
    opt_js = read(WEB / "js" / "views" / "optimization.js")
    shared = read(WEB / "js" / "or-ortak.js")
    # τ seçici, politika ve karşılaştırma tabloları, bütçe eğrisi, keşifsel bölüm.
    for token in [
        "tauSlider(",
        "tau_izgarasi",
        "butce_egrisi",
        "kesifsel",
        "kesifselEtiketi(",
        "beklenen_arrdel15_orani",
        "'plan-none'",
        "'plan-b1'",
        "'plan_conformal-b1'",
        "'plan_budget'",
        "'b1_budget'",
        "'plan_arrdel15_budget'",
        "xyChart(",
        "anlamKutusu('tampon'",
        "politikaEtiketi(",
    ]:
        assert token in opt_js or token in read(WEB / "js" / "or-ortak.js"), token
    # "Eşit bütçede fark anlamlı değil" sonucu elle yazılmaz: aralık sıfırı dışlıyor mu, veriden hesaplanır.
    assert "plan_budget-b1_budget" in shared
    assert "ga95_alt > 0 || c.ga95_ust < 0" in shared
    assert "equalBudgetSentence" in opt_js
    # Keşifsel bölüm ana sonuçlardan ayrı ve etiketli.
    assert "explore" in opt_js and "explore-badge" in opt_js
    assert "explore" in read(WEB / "css" / "style.css")


def test_range_slider_has_visible_value_and_aria_valuetext():
    shared = read(WEB / "js" / "or-ortak.js")
    assert "type: 'range'" in shared
    assert "aria-valuetext" in shared
    assert "'output'" in shared and "slider-out" in shared, "görünür değer"
    assert "step: 1" in shared, "yalnızca ızgara noktalarına oturur"
    assert "for: o.id" in shared, "etiketli kaydırıcı"
    for name in ("story", "optimization"):
        assert "tauSlider(" in read(WEB / "js" / "views" / f"{name}.js"), name
    # Ara değer uydurulmaz: kaydırıcı dizin üzerinden ızgara satırını okur.
    assert "grid[i]" in shared


def test_story_view_is_stepwise_data_driven_and_linked():
    story = read(WEB / "js" / "views" / "story.js")
    for token in [
        "pictograph(",
        "loadRoutes(",
        "loadHava(",
        "loadOptimizasyon(",
        "kantil_conf_dk",
        "kantil_dk",
        "gozlenen_arrdel15_orani",
        "tahmin_arrdel15_orani",
        "equalBudgetSentence",
        "'kaldi'",
        "`#routes/${sel.origin}`",
        "MORE = ['overview', 'airports', 'routes', 'optimization', 'calibration', 'weather', 'errors', 'about', 'sozluk']",
    ]:
        assert token in story, token
    # Altı adım.
    for n in range(1, 7):
        assert re.search(rf"step\(\s*{n},", story), n
    charts = read(WEB / "js" / "charts.js")
    assert "export function pictograph" in charts
    assert "i < 100" in charts, "100 ikonlu birim grafiği"
    assert "'dot late'" in charts and "'dot ok'" in charts, "geç olanlar ayrı sınıfta"
    css = read(WEB / "css" / "style.css")
    assert ".picto .dot.late" in css and ".picto .dot.ok" in css


def test_technical_tabs_start_with_a_meaning_box():
    boxes = {
        "overview": "genel",
        "airports": "havalimanlari",
        "routes": "rotalar",
        "optimization": "tampon",
        "calibration": "kalibrasyon",
        "weather": "hava",
        "errors": "hata",
    }
    tr = text_paths("metin.js", "TR")
    for name, key in boxes.items():
        text = read(WEB / "js" / "views" / f"{name}.js")
        assert f"anlamKutusu('{key}'" in text, name
        assert f"anlam.{key}" in tr, key
        # Kutu, bölüm gövdesinin ilk öğesidir.
        assert re.search(r"fill\(\s*root,\s*anlamKutusu\(", text), name
    assert tr["anlam.baslik"][1].startswith("'Ne anlama geliyor?'")
    assert "'What does this mean?'" in read(WEB / "js" / "metin-en.js")


# --------------------------------------------------------------------------- dil ve metin


def test_site_language_is_turkish_by_default(html):
    assert re.search(r"[çğışöüÇĞİŞÖÜ]", html), "statik HTML Türkçe karakterler içermeli"
    for english in ["Skip to content", "Overview", "Airports", "Loading", "Weather experiment", "Error analysis"]:
        assert english not in html, english
    for path in js_files():
        if path.name in ("metin-en.js", "sozluk-terimleri.js"):  # bilingual by design
            continue  # İngilizce metinler yalnızca bu dosyadadır
        text = read(path)
        assert not re.search(
            r"Loading data|Not published|Show more rows|Select a point|Try again|Reload this section|Colour points",
            text,
        ), path.name


def test_english_texts_live_only_in_the_english_module():
    en = read(WEB / "js" / "metin-en.js")
    assert "export const EN = {" in en
    assert "import " not in en, "metin-en.js hiçbir şey içe aktarmaz (döngüsel bağımlılık yok)"
    for phrase in ["Loading data", "Not published", "Show more rows", "Try again", "Skip to content"]:
        assert phrase in en, phrase
    metin = read(WEB / "js" / "metin.js")
    assert "import { EN } from './metin-en.js';" in metin
    assert "export function setLang" in metin and "export const getLang" in metin
    assert "merge(T, TR);" in metin and "if (current === 'en') merge(T, EN);" in metin, (
        "EN'de karşılığı yoksa Türkçe kalır"
    )


def test_every_text_key_has_turkish_and_english_values(tr_paths, en_paths):
    assert tr_paths.keys() == en_paths.keys(), (
        sorted(tr_paths.keys() - en_paths.keys()),
        sorted(en_paths.keys() - tr_paths.keys()),
    )
    for path, (kind, text) in tr_paths.items():
        en_kind, en_text = en_paths[path]
        assert kind == en_kind, (path, kind, en_kind)
        if kind in {"str", "fn", "arr"}:
            assert text not in {"", "''", '""', "``"}, f"TR değeri boş: {path}"
            assert en_text not in {"", "''", '""', "``"}, f"EN değeri boş: {path}"
    # İngilizce metin Türkçe'nin kopyası olmamalı (aynı kalabilenler: kısa adlar ve işaretler).
    same = [p for p, (k, t) in tr_paths.items() if k == "str" and len(t) > 40 and t == en_paths[p][1]]
    assert not same, same


def test_text_keys_used_in_scripts_exist(tr_paths):
    """Betiklerdeki doğrudan T.anahtar.yolu başvurularının hepsi metin.js içinde tanımlıdır."""
    ref = re.compile(r"(?<![\w.$])T\.([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")
    checked = 0
    for path in js_files():
        if path.name in TEXT_MODULES:
            continue
        for match in ref.finditer(read(path)):
            checked += 1
            assert match.group(1) in tr_paths, f"{path.name}: T.{match.group(1)}"
    assert checked > 50


def test_site_titles_exist_for_every_view(tr_paths, en_paths):
    for name in VIEWS:
        assert f"bolumler.{name}" in tr_paths and f"bolumler.{name}" in en_paths, name
    main_js = read(WEB / "js" / "main.js")
    for name in VIEWS:
        assert f"'{name}'" in main_js, name
    # sayfa: her data-t anahtarı metin.js içinde tanımlı
    html = read(WEB / "index.html")
    keys = set(re.findall(r'data-t(?:-aria)?="([^"]+)"', html))
    assert keys
    for key in keys:
        assert key in tr_paths, key


def test_language_switch_is_wired(html, tags):
    buttons = [a for t, a in tags if t == "button" and a.get("data-lang")]
    assert {b["data-lang"] for b in buttons} == {"tr", "en"}
    assert [b.get("aria-pressed") for b in buttons] == ["true", "false"], "varsayılan dil Türkçe"
    assert [b.get("aria-label") for b in buttons] == ["Türkçe", "English"]
    assert "TR" in html and "EN" in html
    main_js = read(WEB / "js" / "main.js")
    # Seçim sırası: ?lang=, localStorage('lang'), Türkçe; localStorage her yerde try/catch içinde.
    assert "URLSearchParams(window.location.search).get('lang')" in main_js
    assert "window.localStorage.getItem('lang')" in main_js
    assert "window.localStorage.setItem('lang', lang)" in main_js
    assert "setLang(fromUrl || readStoredLang() || 'tr')" in main_js
    assert "setAttribute('lang', lang)" in main_js, "<html lang> güncellenir"
    for func in ("readLangParam", "readStoredLang", "storeLang"):
        body = main_js[main_js.index(f"function {func}") :]
        assert "try {" in body.split("\n\n")[0], func
    # Sayfa yenilenmeden: görünümler yeniden çizilir.
    assert "records.clear()" in main_js and "generation += 1" in main_js
    assert "location.reload" not in main_js
    # Seçimler dil değişince korunur.
    assert "const memory = " in read(WEB / "js" / "views" / "story.js")
    assert "const memory = " in read(WEB / "js" / "views" / "optimization.js")


def test_numbers_are_formatted_per_language():
    fmt = read(WEB / "js" / "fmt.js")
    assert "getLang() === 'en'" in fmt
    assert "const group = en ? ',' : '.';" in fmt, "binlik ayırıcı: TR nokta, EN virgül"
    assert "`.${dec}`" in fmt and "`,${dec}`" in fmt, "ondalık: EN nokta, TR virgül"
    assert "`${p.sign}${p.body}%`" in fmt and "`${p.sign}%${p.body}`" in fmt, "yüzde: EN sonda, TR başta"
    assert "T.birim.dk" in fmt
    assert "birim: { dk: 'dk' }" in read(WEB / "js" / "metin.js")
    assert "birim: { dk: 'min' }" in read(WEB / "js" / "metin-en.js")
    # Ham sayı biçimleri görünümlerde elle yazılmaz.
    for name in ("story", "optimization"):
        text = read(WEB / "js" / "views" / f"{name}.js")
        assert not re.search(r"toFixed\(|toLocaleString\(", text), name


def test_all_ui_text_lives_in_metin_module(tr_paths):
    metin = read(WEB / "js" / "metin.js")
    assert "const TR = {" in metin and "export const T = {};" in metin
    for key in [
        "bolumler",
        "genel",
        "havalimani",
        "rota",
        "kal",
        "hava",
        "hataAnalizi",
        "hakkinda",
        "sozluk",
        "anlam",
        "hikaye",
        "or",
        "dil",
    ]:
        assert key in tr_paths, key
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


def test_glossary_terms_have_english_fields():
    text = read(WEB / "js" / "sozluk-terimleri.js")
    chunks = text.split("{ id: '")[1:]
    assert len(chunks) >= 40
    for chunk in chunks:
        term_id = chunk.split("'", 1)[0]
        assert "en: { terim: '" in chunk, f"EN terim yok: {term_id}"
        en_part = chunk.split("en: { terim: '", 1)[1].split("} },", 1)[0]
        assert "tanim: '" in en_part, f"EN tanım yok: {term_id}"
        tr_part = chunk.split("en: { terim: '", 1)[0]
        # "nerede" varsa İngilizce karşılığı da vardır (ve tersi).
        assert tr_part.count("nerede: '") == en_part.count("nerede: '"), f"nerede çevirisi eksik: {term_id}"
    # Grup adlarının İngilizce karşılığı.
    assert text.count("adEn: '") == len(GLOSSARY_GROUPS)
    assert "export function terimAdi" in text and "export function terimMetni" in text


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
        text = read(path)
        used.update(re.findall(r"sozlukLink\(\s*'([^']+)'", text))
        # anlamKutusu('anahtar', ['terim', ...]) listeleri
        for group in re.findall(r"anlamKutusu\(\s*'[a-z]+',\s*\[([^\]]*)\]", text):
            used.update(re.findall(r"'([a-z0-9-]+)'", group))
    assert used, "hiçbir yerde sözlük bağlantısı yok"
    assert used <= ids, used - ids
    # Metin parametresi verilmez: bağlantı metni terimin seçili dildeki adıdır.
    for path in js_files():
        assert not re.search(r"sozlukLink\(\s*'[^']+'\s*,", read(path)), path.name


def test_glossary_view_has_search_and_term_anchors():
    sozluk = read(WEB / "js" / "views" / "sozluk.js")
    assert "type: 'search'" in sozluk
    assert "`#sozluk/${term.id}`" in sozluk
    assert "export function onParams" in sozluk
    assert "terimMetni(" in sozluk and "grupAdi(" in sozluk, "sözlük seçili dilde yazılır"
    main_js = read(WEB / "js" / "main.js")
    assert "'sozluk'" in main_js


# --------------------------------------------------------------------------- harita


def test_map_uses_state_layer_and_label_placement():
    map_js = read(WEB / "js" / "map.js")
    assert "placeLabels" in map_js
    assert "o.states" in map_js
    assert "halkalar" in map_js
    assert "albers(" in map_js
    # Eksen etiketleri ayrı köşelerde: enlemler batı ucunda, boylamlar güney ucunda (dile göre °K/°B ya da °N/°W).
    assert "T.harita.kuzey" in map_js and "T.harita.bati" in map_js
    assert "harita: { kuzey: '°K', bati: '°B' }" in read(WEB / "js" / "metin.js")
    assert "harita: { kuzey: '°N', bati: '°W' }" in read(WEB / "js" / "metin-en.js")
    airports = read(WEB / "js" / "views" / "airports.js")
    assert "loadEyaletler" in airports
    data_js = read(WEB / "js" / "data.js")
    assert "() => null" in data_js, "eyalet dosyası yüklenemezse harita ızgarayla çalışmalı"


def test_site_files_stay_small():
    for path in source_files():
        limit = 100_000 if path.name in TEXT_MODULES else 60_000
        assert path.stat().st_size < limit, path.name
