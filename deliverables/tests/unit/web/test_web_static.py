"""GitHub Pages sitesi (deliverables/src/web) için statik denetimler.

Burada tarayıcı çalıştırılmaz ve sunucu başlatılmaz. Testler sitenin dosyalarını metin olarak okur
ve yayımlamadan önce geçerli olması gereken kuralları denetler: dış kaynak yok, güvensiz DOM API'si
yok, sıkı CSP, yalnızca göreli yollar, betiklerin okuduğu her veri dosyası manifestte listeli ve
sunum kuralları (havayolu adı yok, "worst"/"en kötü" yok, iki dilde sorumluluk reddi, tampon uyarısı,
sözlük sekmesi, "null" metninin ekrana sızmaması). İki dilli arayüz (varsayılan EN, TR düğmeyle) için:
her metin anahtarının iki dilde değeri vardır, sözlük terimlerinin İngilizce alanı vardır, kaydırıcıda
aria-valuetext vardır. Sade yapı için: 6 sekme, eski adreslerin yönlendirilmesi, Story'de on slayt (başlık +
tek görsel + sade metin), soru-cevap kalıbı yasağı, meta cümle yasağı, LinkedIn adresi boşsa bağlantı çizilmez.
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
BUFFER_WARNING = "Maliyet oranı bir varsayımdır; operasyon için öneri değildir."
BUFFER_WARNING_EN = "Assumed cost ratio — not an operational recommendation."
OR_NOTE_PREFIX = "Tampon optimizasyonu (OR):"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
# Dış bağlantılar yalnızca <a href> olarak, yalnızca metin.js içinde (gezinme; veri çekmez).
ALLOWED_LINKS = {
    "metin.js": {
        "https://github.com/Slmnbal",
        "https://github.com/Slmnbal/flight-delay-forecasting",
    },
}
LINKEDIN_RE = re.compile(r"^https://www\.linkedin\.com/in/[A-Za-z0-9-]+/?$")
GLOSSARY_GROUPS = ["Veri ve hedef", "Model ve tahmin", "Ölçütler", "İstatistik", "Optimizasyon (OR)"]
VIEWS = ["story", "results", "explore", "buffers", "method", "sozluk"]
# Eski adres (ilk parça) -> yeni sekme; paylaşılmış bağlantılar kırılmasın.
OLD_HASHES = {
    "overview": "results",
    "airports": "explore",
    "routes": "explore",
    "optimization": "buffers",
    "calibration": "method",
    "weather": "method",
    "errors": "method",
    "about": "method",
}
# Geliştiriciye / veri dosyasına atıf yapan meta cümleler (hiçbir dosyada olmamalı).
META_PHRASES = [
    "Kaydırıcı yalnızca veri dosyasındaki",
    "Veri dosyasında kaydedilen notlar",
    "Bu sayfa, konuyu hiç bilmeyen biri için",
    "Aralık sıfırı dışlamıyorsa",
    "The slider snaps only to the cost ratios computed in the data file",
    "Notes recorded in the data file",
    "This page is for someone who knows nothing",
    "If the interval does not exclude zero",
]
# Kullanıcıya görünen metin dosyalarında geçmemesi gereken geliştirici ifadeleri.
DEV_WORDS = ["veri dosyasında", "veri dosyası", "şemada", "betik", "data file", "the schema", "the script"]

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


def linkedin_url() -> str:
    match = re.search(r"export const LINKEDIN_URL = '([^']*)';", read(WEB / "js" / "metin.js"))
    assert match, "metin.js içinde tek bir LINKEDIN_URL sabiti olmalı"
    return match.group(1)


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
        "js/yazar.js",
        "js/views/sozluk.js",
        "js/views/story.js",
        "js/story-gorseller.js",
        "js/views/results.js",
        "js/views/explore.js",
        "js/views/buffers.js",
        "js/views/method.js",
        "js/views/optimization.js",
        "js/theme-init.js",
        "js/simgeler.js",
        "js/kesfet-hesap.js",
        "js/views/rota-ozeti.js",
        "js/kabuk.js",
        "js/kendin-dene.js",
        "js/hikaye-ortak.js",
        "js/harita-lejant.js",
        "css/harita.css",
        "sunum/index.html",
        "sunum/sunum.css",
        "sunum/sunum.js",
        "sunum/slayt.js",
        "sunum/slaytlar.js",
        "sunum/slaytlar-tampon.js",
        "sunum/slaytlar-liste.js",
        "sunum/harita-slayti.js",
        "sunum/deneme-slayti.js",
        "veri/manifest.json",
        "harita/abd-eyaletler.json",
    ]:
        assert (WEB / rel).is_file(), rel


def test_html_basics(html, tags):
    assert re.search(r"<html[^>]*\blang=\"en\"", html), "varsayılan dil İngilizce"
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
    assert nav_order == VIEWS, "sekme sırası: Hikâye ilk, Sözlük son"
    assert len(nav_order) == 6
    main_js = read(WEB / "js" / "main.js")
    for name in ids:
        assert (WEB / "js" / "views" / f"{name}.js").is_file(), name
        assert f"./views/{name}.js" in main_js, name


def test_story_and_buffers_sections_are_in_the_page(html, tags):
    for name in ("story", "buffers"):
        assert f'id="view-{name}"' in html
        assert f'id="h-{name}"' in html
        assert f'href="#{name}"' in html
    # Sekme başlıkları ve sabit metinler data-t anahtarıyla iki dile çevrilir.
    assert 'data-t="bolumler.story"' in html and 'data-t="bolumler.buffers"' in html


def test_old_hashes_are_redirected():
    """Eski adresler (#airports, #routes/ORD, #calibration ...) yeni sekmelere yönlendirilir."""
    main_js = read(WEB / "js" / "main.js")
    for old, new in OLD_HASHES.items():
        assert re.search(rf"\b{old}: \['{new}'", main_js), (old, new)
    assert "canonicalize(" in main_js and "history.replaceState" in main_js
    # #routes/XXX parametresi (havalimanı kodu) Keşfet sayfasına taşınır; Yöntem adresleri bölümü açar.
    assert "params: fixed.length ? fixed : parts.slice(1)" in main_js
    for section in ("calibration", "weather", "errors", "limits"):
        assert f"['method', '{section}']" in main_js, section
    explore = read(WEB / "js" / "views" / "explore.js")
    assert "`#explore/${iata}`" in explore
    assert "#routes/" not in read(WEB / "js" / "views" / "routes.js")
    method = read(WEB / "js" / "views" / "method.js")
    for section in ("calibration", "weather", "errors", "limits", "sources", "notes"):
        assert f"id: '{section}'" in method, section
    assert "<details" not in read(WEB / "index.html")


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
            if url == SVG_NAMESPACE:
                continue
            allowed = ALLOWED_LINKS.get(path.name, set())
            linkedin_ok = path.name == "metin.js" and url.startswith("https://") and bool(LINKEDIN_RE.match(url))
            assert url in allowed or linkedin_ok, f"{path.name}: external URL {url}"
        assert not re.search(r"""(?:src|href)\s*=\s*["']//""", text), path.name
        assert not re.search(r"""["'`]//[A-Za-z]""", text) or path.suffix == ".css", path.name
        assert "@import" not in text, path.name
        # CSS may only reference the bundled font files (../fonts/*.woff2), never another site or file.
        urls = re.findall(r"url\(\s*[\"']?([^\"')]+)", text) if path.suffix == ".css" else []
        assert all(re.fullmatch(r"\.\./fonts/[a-z0-9-]+\.woff2", u) for u in urls), (path.name, urls)


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
    # Veri yolları sayfaya değil modüle göre çözülür: hem / hem /sunum/ altında doğru dosyaya gider.
    data_js = read(WEB / "js" / "data.js")
    assert "const BASE = new URL('../veri/', import.meta.url).href;" in data_js
    assert "const HARITA = new URL('../harita/', import.meta.url).href;" in data_js
    assert "./veri/" not in data_js.replace("../veri/", "")
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
    assert "loadOptimizasyon" in read(WEB / "sunum" / "slaytlar-liste.js")
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
    assert DISCLAIMER_EN in html, "İngilizce sorumluluk reddi sayfada (üst bilgi ve noscript)"
    assert f"sorumluluk: '{DISCLAIMER}'" in read(WEB / "js" / "metin.js")
    assert f"sorumluluk: '{DISCLAIMER_EN}'" in read(WEB / "js" / "metin-en.js")
    ozet = json.loads(read(VERI / "ozet.json"))
    assert "havayol" in ozet["proje"]["sorumluluk_reddi"].lower()
    assert "sorumluluk_reddi" in read(WEB / "js" / "yerel.js")
    main_js = read(WEB / "js" / "main.js")
    assert "sorumlulukReddi" in main_js and "footer-disclaimer" in main_js
    # Üst bilgide kısa satır (dil anahtarına bağlı), alt bilgide tam metin bir kez; sekmelerde tekrar yok.
    assert html.count('data-t="sorumluluk"') == 1
    assert 'id="footer-disclaimer"' in html
    for path in (WEB / "js" / "views").glob("*.js"):
        text = read(path)
        assert "sorumlulukReddi" not in text and "T.sorumluluk" not in text, path.name


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
    # İstisna yok: P95 sütununun adı artık "Very bad day" / "Çok kötü gün" (sütun adında da "worst" geçmez).
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
    assert "tamponUyari: BUFFER_WARNING," in metin
    en = read(WEB / "js" / "metin-en.js")
    assert f"BUFFER_WARNING_EN = '{BUFFER_WARNING_EN}'" in en
    assert "tamponUyari: BUFFER_WARNING_EN," in en
    routes_js = read(WEB / "js" / "views" / "routes.js")
    assert "tampon_onerisi_dk" in routes_js
    # Uyarı tek cümle: sütun başlığının ipucunda (title) ve tamponun gösterildiği her yerde görünür.
    assert "tamponIpucu(T.tamponUyari)" in routes_js
    assert "T.tamponUyari" in routes_js
    # Sunumda tamponun gösterildiği slaytlarda (tampon bedeli, eşit bütçe, öneriler) uyarı vardır.
    tampon_slides = read(WEB / "sunum" / "slaytlar-tampon.js")
    assert tampon_slides.count("warning()") >= 3 and "T.tamponUyari" in tampon_slides
    assert "T.tamponUyari" in read(WEB / "js" / "views" / "optimization.js")
    # Başka sayfalarda yinelenmez (Sonuçlar, Yöntem).
    assert "tamponUyari" not in read(WEB / "js" / "views" / "overview.js")
    assert "tamponUyari" not in read(WEB / "js" / "views" / "method.js")


def test_failed_criteria_and_buffer_finding_are_visible():
    overview = read(WEB / "js" / "views" / "overview.js")
    metin = read(WEB / "js" / "metin.js")
    yerel = read(WEB / "js" / "yerel.js")
    assert "'kaldi'" in overview
    assert "kaldi: 'Geçmedi'" in metin
    assert "kaldi: 'Not passed'" in read(WEB / "js" / "metin-en.js")
    assert "kaldiBaslik: 'Neler işe yaramadı'" in metin
    assert "kaldiBaslik: 'What did not work'" in read(WEB / "js" / "metin-en.js")
    # OR bulgusu sayfaya elle yazılmaz; veri notundan, önekle bulunur (TR notun başı, EN aynı sıradaki nottan).
    assert f"OR_NOTE_PREFIX = '{OR_NOTE_PREFIX}'" in yerel
    assert "startsWith(onek)" in yerel
    assert "orBulgusu(ozet)" in read(WEB / "js" / "views" / "optimization.js")
    assert "eşit bütçe" not in overview.lower()
    # Sunum: the "model only matches a simple rule" message is shown only when no budget comparison is significant
    # (data-driven, from the 95% intervals through equalBudget).
    story = read(WEB / "sunum" / "slaytlar-tampon.js")
    assert "eb.significant === 0" in story and "equalBudget(opt)" in story
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
    assert "baslik: 'Sonuçlarla kaydedilen notlar'" in metin
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
        "politikaEtiketi(",
    ]:
        assert token in opt_js or token in read(WEB / "js" / "or-ortak.js"), token
    # Politika/karşılaştırma tabloları ve keşifsel bölüm açılır (<details>) bölümlerdedir.
    assert opt_js.count("'details'") >= 4
    assert "class: 'fold explore'" in opt_js
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
    assert "tauSlider(" in read(WEB / "js" / "views" / "optimization.js")
    assert "tauSlider(" in read(WEB / "sunum" / "slaytlar-tampon.js")
    # Ara değer uydurulmaz: kaydırıcı dizin üzerinden ızgara satırını okur.
    assert "grid[i]" in shared


def story_text_sections() -> dict[str, str]:
    """Hikâye sekmesinin görünür metinleri: metin.js (TR) ve metin-en.js (EN) içindeki hero + hikaye bölümleri."""
    tr = read(WEB / "js" / "metin.js")
    en = read(WEB / "js" / "metin-en.js")
    tr_part = tr[
        tr.index("  hero: {") : tr.index(
            "  // ------------------------------------------------------------------ sonuçlar"
        )
    ]
    en_part = en[
        en.index("  hero: {") : en.index(
            "  // ------------------------------------------------------------------ results"
        )
    ]
    return {"tr": tr_part, "en": en_part}


SUNUM_SLIDE_FILES = [
    "slaytlar.js",
    "slaytlar-tampon.js",
    "harita-slayti.js",
    "deneme-slayti.js",
]


def story_sources() -> dict[str, str]:
    """Hikâye ve sunum görselleri/slaytları: sayı biçimleme, soru-cevap kalıbı ve grafik başlıkları bunlarda denetlenir."""
    out = {
        "story.js": read(WEB / "js" / "views" / "story.js"),
        "story-gorseller.js": read(WEB / "js" / "story-gorseller.js"),
        "hikaye-ortak.js": read(WEB / "js" / "hikaye-ortak.js"),
        "kendin-dene.js": read(WEB / "js" / "kendin-dene.js"),
    }
    for name in SUNUM_SLIDE_FILES:
        out[name] = read(WEB / "sunum" / name)
    return out


def sunum_text_sections() -> dict[str, str]:
    """Sunum metinleri (metin.js ve metin-en.js içindeki `sunum` grubu)."""
    tr = read(WEB / "js" / "metin.js")
    en = read(WEB / "js" / "metin-en.js")
    return {
        "tr": tr[tr.index("  sunum: {") : tr.index("// Dil ve metin nesnesi")],
        "en": en[en.index("  sunum: {") :],
    }


def test_story_hero_is_plain_and_has_no_hand_written_numbers():
    story = read(WEB / "js" / "views" / "story.js")
    for token in ["REPO_URL", "rel: 'noopener'", "t.kapsam(", "t.soru(", "href: './sunum/'", "buildTry("]:
        assert token in story, token
    # Story sekmesi kısa girişe indi: slayt anlatımı sunumda, burada "Sunumu aç" çağrısı ve "Kendin dene" var.
    assert "slideProblem" not in story and "story-steps" not in story
    en = read(WEB / "js" / "metin-en.js")
    assert "How well can public data predict whether a US flight will be late" in en
    assert "kod: 'Code on GitHub'" in en and not re.search(r"\byuru:", en)
    assert "ac: '▶ Open presentation'" in en and "ac: '▶ Sunumu aç'" in read(WEB / "js" / "metin.js")
    # Her sayı veriden: görünür metinlerde rakam yok (metinler işlevdir ve değerleri parametre olarak alır).
    for lang, text in story_text_sections().items():
        visible = re.sub(r"\$\{[^}]*\}", "", text)
        visible = re.sub(r"//[^\n]*", "", visible)
        visible = re.sub(r"\b[A-Za-z_]+\d+\w*", "", visible)  # identifiers such as p50, t2, b1 are not numbers
        assert not re.search(r"\d", visible), (lang, re.search(r".{30}\d.{10}", visible))
    for name, text in story_sources().items():
        assert not re.search(r"toFixed\(|toLocaleString\(", text), name


def test_story_has_no_question_answer_pattern_and_no_precision_recall():
    """Terimler ilk geçtikleri cümlede ara açıklamayla anlatılır; "X nedir?" kalıbı ve tanım kutusu yoktur."""
    qa = re.compile(r"nedir\?|ne demek|\bPeki\b|What is\b|What(?:'|’)s an?\b|\bWhat are\b", re.IGNORECASE)
    for lang, text in story_text_sections().items():
        assert not qa.search(text), (lang, qa.search(text).group(0) if qa.search(text) else "")
    for name, text in story_sources().items():
        assert not qa.search(text), name
    # Kesinlik/duyarlılık ve modeller arası "kaçını yakaladı" karşılaştırması hikâyede yok (eşikler farklı).
    banned = re.compile(r"precision|recall|kesinlik|duyarl[ıi]l[ıi]k|f1", re.IGNORECASE)
    for lang, text in story_text_sections().items():
        assert not banned.search(text), (lang, banned.search(text).group(0) if banned.search(text) else "")
    story = read(WEB / "js" / "views" / "story.js")
    assert not re.search(r"'(?:precision|recall|f1)'", story)


def test_presentation_has_cover_and_eleven_slides_each_with_title_figure_and_details_link():
    """Kapak (0) + 11 içerik slaydı; her içerik slaydı slide({...}) ile kurulur: başlık, ana görsel, yan panel, ayrıntı."""
    sources = {name: read(WEB / "sunum" / name) for name in SUNUM_SLIDE_FILES}
    joined = "\n".join(sources.values())
    for n in range(1, 12):
        assert re.search(rf"\bn: {n},", joined), f"slayt {n} yok"
    assert "'slayt-0'" in joined, "kapak slaydı"
    lst = read(WEB / "sunum" / "slaytlar-liste.js")
    for fn in (
        "cover(",
        "slideProblem(",
        "slideTime(",
        "slideRisk(",
        "slideTrust(",
        "slideWeather(",
        "slideBufferIdea(",
        "slideTradeoff(",
        "slideRule(",
        "slideActions(",
        "slideMap(",
        "slideTry(",
    ):
        assert fn in lst, fn
    shell = read(WEB / "sunum" / "slayt.js")
    # Her slayt: section + aria-labelledby + h2 başlık, ana görsel, yan panel (rakamlar, nasıl okunur, anlam), ayrıntı bağlantısı.
    for token in [
        "'section'",
        "'aria-labelledby'",
        "'h2'",
        "slide-main",
        "slide-panel",
        "rakamlar",
        "t.nasil",
        "t.anlam",
        "t.ayrinti",
        "details-link",
    ]:
        assert token in shell, token
    # Her slaytın ayrıntı bağlantısı detay sitesine (../) gider.
    hrefs = [
        h for h in re.findall(r"href: [`']([^`']*)[`']", joined) if h != "../"
    ]  # "../": kapaktaki "Detaylı siteye geç"
    assert len(hrefs) >= 11 and all(h.startswith("../#") for h in hrefs), hrefs
    assert "href: '../'" in sources["slaytlar.js"], "kapakta detay sitesine geçiş"
    for target in (
        "../#results",
        "../#method/errors",
        "../#method/calibration",
        "../#method/weather",
        "../#buffers",
        "../#explore",
    ):
        assert target in hrefs or any(h.startswith(target) for h in hrefs), target
    # Her grafik çağrısının yakınında başlık ve açıklama (title/desc) verilir.
    for name, text in story_sources().items():
        for call in ("barChart(", "columnChart(", "xyChart(", "stackedBar(", "pictograph(", "bufferDiagram("):
            for match in re.finditer(re.escape(call), text):
                if text[max(0, match.start() - 16) : match.start()].endswith("function "):
                    continue
                window = text[match.start() : match.start() + 1600]
                assert "title" in window and "desc" in window, (name, call)
    gorseller = read(WEB / "js" / "story-gorseller.js")
    assert gorseller.count("o.title, o.desc") == 2 and "o.text.title, o.text.desc" in gorseller
    # Dar ekranda daha az eksen etiketi.
    assert "tickCount: width < 480" in joined and "tickCount: narrow" in joined
    # Tampon şeması örnek diye işaretlidir.
    assert "ornek:" in read(WEB / "js" / "metin.js") and "Illustration" in read(WEB / "js" / "metin-en.js")
    # Harita slaydında havalimanı sıralaması yoktur: yalnızca en düşük-en yüksek aralığı ve seçili havalimanı.
    harita = sources["harita-slayti.js"]
    assert "Math.min(...rates)" in harita and "Math.max(...rates)" in harita and ".sort(" not in harita
    assert "gizleme_nedeni" in harita and "yayimlanmayanlar" in harita, "DAL/MDW yayımlanmadı notu"


def test_presentation_slides_are_data_driven_and_linked():
    story = "\n".join(
        [
            read(WEB / "sunum" / "slaytlar-liste.js"),
            read(WEB / "js" / "kendin-dene.js"),
            read(WEB / "js" / "hikaye-ortak.js"),
            *(read(WEB / "sunum" / name) for name in SUNUM_SLIDE_FILES),
        ]
    )
    for token in [
        # 1. sorun
        "'yayginlik'",
        "ozet.kapsam.test_ucus_sayisi",
        # 2. saat bloğu ve olay günü
        "b.boyut === 'saat_blogu' && b.model === 'lgbm_T2'",
        "'olay_gunu'",
        # 3-4. risk grupları
        "e.gorev === 'arrdel15' && e.model === 'lgbm_T2'",
        "gozlenen_oran",
        "ortalama_tahmin",
        "maxGap",
        # 5. hava
        "metricOf(ozet, 'arrdel15', model, 'roc_auc')",
        "'T2-plan'",
        "base: COIN_FLIP",
        # 7. ödünleşim
        "'arrdel15_orani'",
        "'kullanilmayan_dk'",
        "nearestIndex(grid, 0.8)",
        "tauSlider(",
        "T.tamponUyari",
        "stackedBar(",
        # 8. eşit bütçe
        "equalBudget(opt)",
        "'plan_budget'",
        "'b1_budget'",
        # 10. uçuş seç
        "pictograph(",
        "loadRoutes(",
        "kantil_conf_dk",
        "kantil_dk",
        "gozlenen_arrdel15_orani",
        "tahmin_arrdel15_orani",
        "`${base}#explore/${sel.origin}`",
        "loadHata(",
        "loadKalibrasyon(",
        "loadHava(",
        "loadOptimizasyon(",
    ]:
        assert token in story, token
    # Sunumdan kendin-dene bağlantıları detay sitesine gider ('../' öneki); Story sekmesinde önek boştur.
    assert "base: '../'" in read(WEB / "sunum" / "deneme-slayti.js")
    assert "base: ''" in read(WEB / "js" / "views" / "story.js")
    # Neler işe yaramadı (K5, K6) sunumun son öneri slaydındadır ve sayıları veriden gelir.
    assert "failed.has('K5')" in story and "failed.has('K6')" in story
    # Hikâyede elle yazılmış havayolu/sıralama yok; metin dosyalarındaki Story bölümleri iki dilli.
    charts = read(WEB / "js" / "charts.js")
    assert "export function pictograph" in charts
    assert "i < 100" in charts, "100 ikonlu birim grafiği"
    assert "'dot late'" in charts and "'dot ok'" in charts, "geç olanlar ayrı sınıfta"
    css = read(WEB / "css" / "style.css")
    assert ".picto .dot.late" in css and ".picto .dot.ok" in css


def test_no_what_does_this_mean_boxes_and_method_uses_folds():
    """ "Ne anlama geliyor?" kutuları kalktı; Yöntem'deki bölümler açılır (<details>) ve başlıkta özet taşır."""
    tr = text_paths("metin.js", "TR")
    assert not [p for p in tr if p == "anlam" or p.startswith("anlam.")]
    for path in js_files():
        assert "anlamKutusu" not in read(path), path.name
    method = read(WEB / "js" / "views" / "method.js")
    assert "el('details'" in method and "toggle" in method, "bölümler ilk açıldığında yüklenir"
    for section in ("kalibrasyon", "hava", "hatalar", "sinirlar", "kaynaklar", "notlar"):
        assert f"yontem.{section}.baslik" in tr and f"yontem.{section}.ozet" in tr, section
    # Hakkında kutusu Yöntem sayfasının sonunda; yazar yalnızca "Slmnbal".
    assert "aboutBox()" in method and "AUTHOR" in method
    assert "export const AUTHOR = 'Slmnbal';" in read(WEB / "js" / "metin.js")
    metin = read(WEB / "js" / "metin.js")
    assert "Bu projeyi veri analizinden veri bilimine geçerken yaptım." in metin
    assert "I built this project while moving from data analysis into data science." in read(WEB / "js" / "metin-en.js")


def test_linkedin_link_is_only_drawn_when_the_url_is_set():
    yazar = read(WEB / "js" / "yazar.js")
    assert "[LINKEDIN_URL, t.linkedin]" in yazar
    assert "url ? safeHttpsUrl(url) : null" in yazar and ".filter((l) => l.href)" in yazar, "boş adres çizilmez"
    assert "rel: 'noopener'" in yazar
    url = linkedin_url()
    assert url == "" or LINKEDIN_RE.match(url), url
    assert "linkedin: 'LinkedIn'" in read(WEB / "js" / "metin.js"), "bağlantı metni yalnızca LinkedIn"
    assert "export const GITHUB_URL = 'https://github.com/Slmnbal';" in read(WEB / "js" / "metin.js")
    assert "export const REPO_URL = 'https://github.com/Slmnbal/flight-delay-forecasting';" in read(
        WEB / "js" / "metin.js"
    )
    # E-posta yok.
    for path in source_files():
        assert "mailto:" not in read(path), path.name


def test_no_developer_facing_meta_sentences():
    for path in source_files():
        text = read(path)
        for phrase in META_PHRASES:
            assert phrase not in text, (path.name, phrase)
    # Kullanıcıya görünen metin dosyalarında geliştirici/veri dosyası atıfları yok.
    for name in ("metin.js", "metin-en.js", "sozluk-terimleri.js"):
        text = read(WEB / "js" / name).lower()
        for word in DEV_WORDS:
            assert word not in text, (name, word)
    assert "data file" not in read(WEB / "index.html").lower()


# --------------------------------------------------------------------------- dil ve metin


def test_site_language_is_english_by_default(html):
    """Varsayılan dil İngilizce: <html lang>, statik metinler ve metin.js başlangıcı; TR düğmeyle seçilir."""
    assert not re.search(r"[çğışöüÇĞİŞÖÜ]", re.sub(r"<!--.*?-->", "", html, flags=re.S).replace("Türkçe", "")), (
        "statik HTML'de Türkçe metin yok (düğme etiketi hariç)"
    )
    for english in ["Skip to content", "Story", "Results", "Explore", "Buffers (OR)", "Method", "Glossary"]:
        assert english in html, english
    metin = read(WEB / "js" / "metin.js")
    assert "let current = 'en';" in metin and "setLang('en');" in metin
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
    by_lang = {b["data-lang"]: b for b in buttons}
    assert by_lang["en"].get("aria-pressed") == "true" and by_lang["tr"].get("aria-pressed") == "false", (
        "varsayılan dil İngilizce"
    )
    assert by_lang["tr"].get("aria-label") == "Türkçe" and by_lang["en"].get("aria-label") == "English"
    assert "TR" in html and "EN" in html
    main_js = read(WEB / "js" / "main.js")
    kabuk = read(WEB / "js" / "kabuk.js")  # dil ve tema okuma/yazma: detay ve sunum siteleri ortak kullanır
    # Seçim sırası: ?lang=, localStorage('lang'), İngilizce; localStorage her yerde try/catch içinde.
    assert "URLSearchParams(window.location.search).get('lang')" in kabuk
    assert "window.localStorage.getItem('lang')" in kabuk
    assert "window.localStorage.setItem('lang', lang)" in kabuk
    assert "setLang(fromUrl || readStoredLang() || 'en')" in main_js
    assert "setAttribute('lang', lang)" in main_js, "<html lang> güncellenir"
    for func in ("readLangParam", "readStoredLang", "storeLang"):
        body = kabuk[kabuk.index(f"function {func}") :]
        assert "try {" in body.split("\n\n")[0], func
    # İki site de aynı mekanizmayı kullanır (kabuk.js), aynı localStorage anahtarını paylaşır.
    sunum_js = read(WEB / "sunum" / "sunum.js")
    for token in [
        "from '../js/kabuk.js'",
        "setLang(fromUrl || readStoredLang() || 'en')",
        "setAttribute('lang', lang)",
        "storeLang(lang)",
    ]:
        assert token in sunum_js, token
    assert "from './kabuk.js'" in main_js
    # Sayfa yenilenmeden: görünümler yeniden çizilir.
    assert "records.clear()" in main_js and "generation += 1" in main_js
    assert "location.reload" not in main_js
    # Seçimler dil değişince korunur.
    assert "const memory = " in read(WEB / "js" / "kendin-dene.js")
    assert "const memory = " in read(WEB / "sunum" / "slaytlar-tampon.js")
    assert "const memory = " in read(WEB / "js" / "views" / "optimization.js")
    # TR düğmesi ?lang=tr ile de seçilir.
    assert "value === 'en' || value === 'tr' ? value : null" in main_js + read(WEB / "js" / "kabuk.js")


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
        "hero",
        "genel",
        "kesfet",
        "havalimani",
        "rota",
        "kal",
        "hava",
        "hataAnalizi",
        "yontem",
        "hakkimda",
        "sozluk",
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


# --------------------------------------------------------------------------- simgeler, palet, Keşfet yenilikleri

REQUIRED_ICONS = [
    "plane",  # kalkış
    "clock",  # saat bloğu, tipik rötar
    "cloud",  # hava
    "buffer",  # tampon (kum saati)
    "pin",  # havalimanı
    "route",  # rota yayı
    "chart",
    "shield",  # geçti, güvenilir
    "alert",  # geçmedi, riskli
    "info",
    "calendar",  # mevsim
    "target",
]
THEME_TOKENS = [
    "--text", "--muted", "--link", "--surface", "--surface-2", "--bg", "--accent",
    "--good", "--warn", "--bad", "--neutral",
    "--risk-1", "--risk-2", "--risk-3", "--risk-4", "--risk-5",
    "--c-a", "--c-b", "--c-c", "--c-d", "--c-e", "--c-f",
    "--sea", "--land", "--land-line",
    "--pass-bg", "--pass-fg", "--fail-bg", "--fail-fg", "--na-bg", "--na-fg",
]  # fmt: skip


def css_blocks() -> dict[str, dict[str, str]]:
    """Açık tema (:root), koyu tema (medya sorgusu) ve koyu tema (data-theme) değişken tanımları."""
    css = read(WEB / "css" / "style.css")
    heads = {
        "light": ":root {",
        "dark-media": ':root:not([data-theme="light"]) {',
        "dark-attr": ':root[data-theme="dark"] {',
    }
    out: dict[str, dict[str, str]] = {}
    for name, head in heads.items():
        start = css.index(head) + len(head)
        body = css[start : css.index("}", start)]
        out[name] = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", body))
    return out


def resolve(tokens: dict[str, str], name: str, base: dict[str, str]) -> str:
    value = tokens.get(name) or base[name]
    while value.startswith("var("):
        ref = value[4:-1].strip()
        value = tokens.get(ref) or base[ref]
    return value


def luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def hue(hex_color: str) -> float:
    import colorsys

    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def test_icon_set_is_complete_and_decorative():
    src = read(WEB / "js" / "simgeler.js")
    for name in REQUIRED_ICONS:
        assert re.search(rf"^  {name}: \[", src, re.MULTILINE), name
    assert "viewBox: '0 0 24 24'" in src
    assert "'stroke-width': 1.75" in src
    assert "stroke: 'currentColor'" in src
    assert "'aria-hidden': 'true'" in src, "simgeler süstür; metinli etiketin yanında durur"
    assert not re.search(r"#[0-9A-Fa-f]{3,6}\b", src), "simgelerde renk kodu yok; currentColor kullanılır"
    # Simgeler gerçekten kullanılıyor: sekmeler, hikâye başlıkları, kabul ölçütü rozetleri, Keşfet kartları.
    assert "data-ico" in read(WEB / "index.html") and "[data-ico]" in read(WEB / "js" / "main.js")
    assert "icon(o.ico" in read(WEB / "sunum" / "slayt.js")
    overview = read(WEB / "js" / "views" / "overview.js")
    assert "icon(verdict.symbol" in overview and "'✓'" not in overview and "'✕'" not in overview
    assert "icon(" in read(WEB / "js" / "views" / "rota-ozeti.js")


def test_palette_tokens_exist_in_light_and_dark_themes():
    blocks = css_blocks()
    for name, tokens in blocks.items():
        if name == "light":
            for token in THEME_TOKENS:
                assert token in tokens, (name, token)
        else:
            # Koyu tema, açık temadan farklı olması gereken her değeri yeniden tanımlar.
            for token in THEME_TOKENS:
                assert token in tokens, (name, token)
    assert blocks["dark-media"] == blocks["dark-attr"] or {k: v.strip() for k, v in blocks["dark-media"].items()} == {
        k: v.strip() for k, v in blocks["dark-attr"].items()
    }, "iki koyu tema tanımı aynı değerleri taşımalı"


def test_risk_scale_is_sequential_and_has_no_green_red_pair():
    blocks = css_blocks()
    for name, tokens in blocks.items():
        stops = [resolve(tokens, f"--risk-{i}", blocks["light"]).strip().upper() for i in range(1, 6)]
        assert all(re.fullmatch(r"#[0-9A-F]{6}", s) for s in stops), (name, stops)
        assert len(set(stops)) == 5
        # Yeşil aralığı (tonu 70-170 derece) yok: yeşil-kırmızı ikilisi renk körlüğünde ayırt edilemez.
        for s in stops:
            assert not 70 <= hue(s) <= 170, (name, s, hue(s))
        # Açıklıkları adım adım azalır (en düşük risk en açık): renk körü için de sıralı okunur.
        lums = [luminance(s) for s in stops]
        assert lums == sorted(lums, reverse=True) and len(set(lums)) == 5, (name, lums)
    # Kategorik seriler: en az 4 ayrı renk.
    for name, tokens in blocks.items():
        cats = {resolve(tokens, f"--c-{k}", blocks["light"]).strip().upper() for k in "abcdef"}
        assert len(cats) >= 4, name


def test_text_colours_meet_wcag_aa_in_both_themes():
    blocks = css_blocks()
    base = blocks["light"]
    for name, tokens in blocks.items():
        surfaces = [resolve(tokens, s, base) for s in ("--bg", "--surface", "--surface-2")]
        for token in ("--text", "--muted", "--link", "--good", "--warn", "--bad", "--neutral"):
            fg = resolve(tokens, token, base)
            for bg in surfaces:
                assert contrast(fg, bg) >= 4.5, (name, token, fg, bg, round(contrast(fg, bg), 2))
        for kind in ("pass", "fail", "na"):
            fg = resolve(tokens, f"--{kind}-fg", base)
            bg = resolve(tokens, f"--{kind}-bg", base)
            assert contrast(fg, bg) >= 4.5, (name, kind, round(contrast(fg, bg), 2))


def test_explore_reads_destination_points_and_they_are_in_the_manifest():
    data_js = read(WEB / "js" / "data.js")
    assert "varisNoktalari: 'varis-noktalari.json'" in data_js
    assert "loadVarisNoktalari" in read(WEB / "js" / "views" / "explore.js")
    manifest = json.loads(read(VERI / "manifest.json"))
    entries = {e["yol"]: e for e in manifest["dosyalar"]}
    assert "veri/varis-noktalari.json" in entries
    assert entries["veri/varis-noktalari.json"]["dosya_turu"] == "varis_noktalari"
    doc = json.loads(read(VERI / "varis-noktalari.json"))
    assert doc["dosya_turu"] == "varis_noktalari" and doc.get("ornek") is False
    for point in doc["noktalar"]:
        assert set(point) == {"iata", "ad", "enlem", "boylam"}
    # Koordinatı olanlarla olmayanlar çakışmaz.
    assert not {p["iata"] for p in doc["noktalar"]} & set(doc["eksik"])


def test_explore_calculation_helpers_are_pure_functions():
    src = read(WEB / "js" / "kesfet-hesap.js")
    for name in [
        "riskClass",
        "riskLevel",
        "equalEdges",
        "weightedMean",
        "weightedMedian",
        "baseCells",
        "destTotals",
        "blockRates",
        "seasonRate",
        "typicalDelay",
        "summarize",
        "arcItems",
        "arcWidth",
        "arcGeometry",
    ]:
        assert f"export function {name}(" in src, name
    assert "import " not in src, "saf işlevler: hiçbir şey içe aktarmaz (DOM ve ağ yok)"
    assert "document" not in src and "fetch" not in src
    # Risk sınıfı sınırları ve rozet eşikleri tutarlı: düşük < ikinci sınır, yüksek >= son sınır.
    edges = [float(x) for x in re.search(r"RISK_EDGES = Object\.freeze\(\[([^\]]+)\]\)", src).group(1).split(",")]
    assert edges == sorted(edges) and len(edges) == 4
    low = float(re.search(r"RISK_LOW = ([0-9.]+);", src).group(1))
    high = float(re.search(r"RISK_HIGH = ([0-9.]+);", src).group(1))
    assert low == edges[1] and high == edges[3] and low < high
    assert re.search(r"MIN_FLIGHTS = 200;", src), "en az uçuş eşiği 200 (metinde belirtilir)"
    # Yay kalınlığı uçuş sayısıyla, yay rengi geç varış oranıyla belirlenir; harita ikisini de bu işlevlerle kurar.
    map_js = read(WEB / "js" / "map.js")
    assert "arcWidth(item.n" in map_js and "riskClass(item.rate" in map_js and "arcGeometry(" in map_js
    # Özet kartları ve yaylar aynı rota hücrelerinden gelir.
    explore = read(WEB / "js" / "views" / "explore.js")
    assert "arcItems(" in explore and "buildCards(" in explore and "loadRoutes(" in explore


def test_route_table_uses_plain_delay_names_with_small_tags():
    routes = read(WEB / "js" / "views" / "routes.js")
    for key in ("tb.p50", "tb.p80", "tb.p95", "tb.p80Sinir", "tb.p95Sinir"):
        assert key in routes, key
    for tag in ("'P50'", "'P80'", "'P95'"):
        assert tag in routes, tag
    for src, expected in {
        "metin-en.js": [
            "p50: 'Typical day'",
            "p80: 'Bad day'",
            "p95: 'Very bad day'",
            "Bad-day limit (adjusted)",
            "Very-bad-day limit (adjusted)",
            "8 in 10 flights arrive within this time",
            "19 in 20 flights arrive within this time",
            "half of flights arrive within this time",
        ],
        "metin.js": [
            "p50: 'Tipik gün'",
            "p80: 'Kötü gün'",
            "p95: 'Çok kötü gün'",
            "Kötü gün sınırı (düzeltilmiş)",
            "uçuşların yarısı bu süre içinde varır",
            "uçuşların 10’da 8’i bu süre içinde varır",
            "uçuşların 20’de 19’u bu süre içinde varır",
        ],
    }.items():
        text = read(WEB / "js" / src)
        for phrase in expected:
            assert phrase in text, (src, phrase)
    # Geç varış oranı: renk + metin + simge (rozet) ve küçük çubuk; kantiller küçük çubuk; mobilde ilk sütun yapışkan.
    assert (
        "risk-badge" in routes
        and "icon(LEVEL_ICON[level]" in routes
        and "cbar-fill" in routes
        and "qbar-fill" in routes
    )
    assert "sticky: true" in routes
    css = read(WEB / "css" / "style.css")
    assert "table.sticky-first th:first-child" in css and "overflow-x: auto" in css
    # Önerilen tampon sütunu simgeli; uyarı tek cümle olarak tablonun üstünde.
    assert "icon('buffer'" in routes and "T.tamponUyari" in routes


def test_explore_texts_have_no_what_is_pattern_and_arcs_note_is_data_driven():
    qa = re.compile(r"nedir\?|ne demek|\bPeki\b|What is\b|What(?:'|’)s an?\b|\bWhat are\b", re.IGNORECASE)
    for path in ("kesfet", "havalimani", "rota"):
        for lang_file, const in (("metin.js", "TR"), ("metin-en.js", "EN")):
            for key, (_kind, text) in text_paths(lang_file, const).items():
                if key == path or key.startswith(f"{path}."):
                    assert not qa.search(text), (lang_file, key)
    en = read(WEB / "js" / "metin-en.js")
    assert (
        "destinations without coordinates are not drawn" in en and "destination without coordinates is not drawn" in en
    )
    airports = read(WEB / "js" / "views" / "airports.js")
    assert "t.yayEksik(fmtInt(arcState.missing)" in airports, "N, veriden (varis-noktalari eksik listesi) gelir"
    # Yayımlanmayan havalimanlarında (DAL, MDW) kartlar havalimanı düzeyi oran göstermez.
    cards = read(WEB / "js" / "views" / "rota-ozeti.js")
    assert "hidden ? k.blok.detaySiz" in cards and "k.varis.satirSiz" in cards and "k.yalnizca" in cards


def test_map_is_a_single_svg_with_arcs_tooltip_and_keyboard_support():
    map_js = read(WEB / "js" / "map.js")
    for token in [
        "arc-line",
        "arc-case",
        "arc-hit",
        "showTip(",
        "ArrowRight",
        "ArrowLeft",
        "role: 'group'",
        "tabindex",
    ]:
        assert token in map_js, token
    css = read(WEB / "css" / "style.css")
    for token in [".arc-line", ".arc:focus", ".risk-strip", "--sea", "--land", ".stat-card", ".risk-badge"]:
        assert token in css, token
    # Izgara çok soluk ve kara ızgaranın üstünde: önce ızgara, sonra eyaletler çizilir.
    assert map_js.index("root.append(graticule)") < map_js.index("root.append(states)")


# --------------------------------------------------------------------------- sunum sitesi ve tam genişlik harita


@pytest.fixture(scope="module")
def sunum_html() -> str:
    return read(WEB / "sunum" / "index.html")


@pytest.fixture(scope="module")
def sunum_tags(sunum_html):
    collector = _Collector()
    collector.feed(sunum_html)
    return collector.tags


def test_presentation_page_has_same_csp_and_no_external_resources(html, sunum_html, sunum_tags):
    def csp(tags):
        metas = [a for t, a in tags if t == "meta" and (a.get("http-equiv") or "").lower() == "content-security-policy"]
        assert len(metas) == 1
        return metas[0]["content"]

    detail_tags = _Collector()
    detail_tags.feed(html)
    assert csp(sunum_tags) == csp(detail_tags.tags), "iki sitede aynı CSP"
    assert "unsafe-inline" not in csp(sunum_tags)
    names = [t for t, _ in sunum_tags]
    assert names.count("h1") == 1 and names.count("main") == 1 and "nav" in names and "footer" in names
    assert re.search(r"<html[^>]*\blang=\"en\"", sunum_html), "sunum varsayılan dili İngilizce"
    for tag, attrs in sunum_tags:
        assert tag != "style" and "style" not in attrs, (tag, attrs)
        assert not any(name.startswith("on") for name in attrs), (tag, attrs)
        if tag == "script":
            assert attrs.get("src"), "inline <script> yok"
        value = attrs.get("tabindex")
        if value is not None:
            assert int(value) <= 0
    assert "javascript:" not in sunum_html.lower()
    for value in re.findall(r"""(?:src|href)\s*=\s*["']([^"']*)["']""", sunum_html):
        assert value.startswith(("./", "../", "#")), value
        assert not re.match(r"https?:|//", value)
    # Ortak stiller ve kendi küçük dosyası göreli yolla yüklenir; ortak betikler ../js altında.
    assert (
        'href="../css/style.css"' in sunum_html
        and 'href="./sunum.css"' in sunum_html
        and 'src="./sunum.js"' in sunum_html
    )
    assert not re.search(r"[çğışöüÇĞİŞÖÜ]", re.sub(r"<!--.*?-->", "", sunum_html, flags=re.S).replace("Türkçe", ""))
    # Sorumluluk reddi sunum sayfasında (alt bilgi) ve noscript metninde; dil düğmeleri aynı biçimde.
    assert DISCLAIMER_EN in sunum_html and sunum_html.count('data-t="sorumluluk"') == 1
    buttons = {a["data-lang"]: a for t, a in sunum_tags if t == "button" and a.get("data-lang")}
    assert set(buttons) == {"tr", "en"} and buttons["en"]["aria-pressed"] == "true"
    for key in set(re.findall(r'data-t(?:-aria)?="([^"]+)"', sunum_html)):
        assert key in text_paths("metin.js", "TR"), key


def test_presentation_navigation_features_exist():
    js = read(WEB / "sunum" / "sunum.js")
    css = read(WEB / "sunum" / "sunum.css")
    page = read(WEB / "sunum" / "index.html")
    # ◀ ▶ düğmeleri, klavye, dokunmatik kaydırma, sayaç, noktalar, tam ekran, adres (#sayı), duyuru ve odak.
    for token in [
        'id="prev"',
        'id="next"',
        'id="counter"',
        'id="dots"',
        'id="full-btn"',
        'role="status"',
        'aria-live="polite"',
    ]:
        assert token in page, token
    for key in ["ArrowRight", "ArrowLeft", "PageUp", "PageDown", "Home", "End"]:
        assert key in js, key
    for token in [
        "touchstart",
        "touchend",
        "requestFullscreen",
        "exitFullscreen",
        "fullscreenchange",
        "hashchange",
        "/^#(\\d{1,2})$/",
        "'inert'",
        ".focus({ preventScroll: true })",
    ]:
        assert token in js, token
    assert "e.defaultPrevented" in js and "'INPUT'" in js, "kaydırıcı ve harita okları gezinmeyi çalmaz"
    assert "catch(() => {})" in js.replace(" ", "") or ".catch(() => {})" in js, "tam ekran reddi sessizce yok sayılır"
    # Her slayt tam ekran: 100dvh, sayfa kaymaz, içerik sığmazsa slaytın içi kayar; kısa geçiş, azaltılmış harekete saygı.
    for token in [
        "100dvh",
        "overflow-y: auto",
        "opacity 0.25s",
        "prefers-reduced-motion",
        ":focus-visible",
        "@media (max-width: 40rem)",
    ]:
        assert token in css or token in read(WEB / "css" / "style.css"), token
    assert "body.deck-page { margin: 0; overflow: hidden; }" in css
    # Sunum yalnızca düz #sayı adreslerini tanır; başka adresler kapak sayılır.
    assert "return match ? Number(match[1]) : 0;" in js
    assert "animation" not in css


def test_presentation_and_detail_sites_link_to_each_other():
    index = read(WEB / "index.html")
    assert 'href="./sunum/"' in index and 'data-t="sunum.ac"' in index, "detay sitesi üst bilgisinde Sunumu aç düğmesi"
    story = read(WEB / "js" / "views" / "story.js")
    assert "href: './sunum/'" in story and "T.sunum.ac" in story, "Story sekmesinin başında aynı çağrı"
    page = read(WEB / "sunum" / "index.html")
    assert 'href="../"' in page and 'data-t="sunum.detaySite"' in page, "sunumun sabit köşesinde detaylı siteye geç"
    slides = read(WEB / "sunum" / "slaytlar.js")
    assert "href: '../'" in slides and "p.detaySite" in slides, "kapakta da"
    en, tr = read(WEB / "js" / "metin-en.js"), read(WEB / "js" / "metin.js")
    assert "detaySite: 'Open the detailed site'" in en and "detaySite: 'Detaylı siteye geç'" in tr
    assert "ayrinti: 'Details on this topic →'" in en and "ayrinti: 'Bu konunun ayrıntısı →'" in tr
    # Detay sitesinde bu adresler hâlâ yönlendirilir: #results, #explore/ORD, #buffers, #method/calibration.
    main_js = read(WEB / "js" / "main.js")
    for view in ("results", "explore", "buffers", "method"):
        assert f"'{view}'" in main_js


def test_data_paths_resolve_from_the_module_not_the_page():
    data_js = read(WEB / "js" / "data.js")
    assert "import.meta.url" in data_js
    # Sunum betikleri veriyi yalnızca data.js üzerinden okur (kendi fetch'i yok); aynı modül iki sayfadan da yüklenir.
    for path in (WEB / "sunum").glob("*.js"):
        assert "fetch(" not in read(path), path.name
    assert "from '../js/data.js'" in read(WEB / "sunum" / "slaytlar-liste.js")


def test_presentation_text_rules():
    qa = re.compile(r"nedir\?|ne demek|\bPeki\b|What is\b|What(?:'|’)s an?\b|\bWhat are\b", re.IGNORECASE)
    for lang, text in sunum_text_sections().items():
        assert not qa.search(text), (lang, qa.search(text).group(0) if qa.search(text) else "")
        visible = re.sub(r"\$\{[^}]*\}", "", text)
        visible = re.sub(r"//[^\n]*", "", visible)
        visible = re.sub(r"\b[A-Za-z_]+\d+\w*", "", visible)
        assert not re.search(r"\d", visible), (lang, re.search(r".{30}\d.{10}", visible))
        assert not re.search(r"precision|recall|kesinlik|duyarl[ıi]l[ıi]k|f1|P50|P80|P95", visible, re.IGNORECASE), lang
    # Havalimanı sıralaması yok: "en iyi/en kötü havalimanı", "ranking" gibi ifadeler geçmez.
    for lang, text in sunum_text_sections().items():
        assert not re.search(r"\bbest airport|\bbest-performing|\branking|\bsıralama", text, re.IGNORECASE), lang


def test_presentation_keys_have_both_languages(tr_paths, en_paths):
    keys = [k for k in tr_paths if k == "sunum" or k.startswith("sunum.")]
    assert len(keys) > 60
    assert all(k in en_paths for k in keys)
    for n in ("s1", "s2", "harita", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11"):
        assert f"sunum.{n}.nasil" in tr_paths or f"sunum.{n}.anlam" in tr_paths, n
    for key in ("ortak.rakamlar", "ortak.nasil", "ortak.anlam", "ortak.ayrinti"):
        assert f"sunum.{key}" in tr_paths and f"sunum.{key}" in en_paths


def test_map_is_a_full_width_band_with_prominent_arcs():
    airports = read(WEB / "js" / "views" / "airports.js")
    css = read(WEB / "css" / "harita.css")
    # Tam genişlik bant (ana içerik genişliğinin dışına taşar), ~70vh; paneller köşelerde (dar ekranda altta).
    assert "'map-band'" in airports and "map-overlays" in airports and "ov-left" in airports and "ov-right" in airports
    assert "width: 100vw" in css and "margin-left: calc(50% - 50vw)" in css and "70vh" in css
    assert "position: absolute" in css and "@media (min-width: 75rem)" in css
    assert "color-mix(in srgb, var(--surface)" in css, "yarı saydam panel"
    assert "widthForHeight(" in airports and "export const widthForHeight" in read(WEB / "js" / "map.js")
    # Yaylar: daha kalın, opak, açık temada koyu kontur, koyu temada parlama; telefonda da çizilir (daha ince).
    map_js = read(WEB / "js" / "map.js")
    assert "export const arcRange = (compact) => (compact ? [1.6, 6] : [2.6, 12]);" in map_js
    assert "arcWidth(item.n, arcMax, wMin, wMax)" in map_js and "arc-glow" in map_js and "feGaussianBlur" in map_js
    assert "compact" in map_js[map_js.index("const [wMin, wMax]") :], "dar ekranda yaylar çizilir"
    assert "if (compact) return" not in map_js
    style = read(WEB / "css" / "style.css")
    assert ".arc-glow { display: none;" in style, "parlama yalnızca koyu temada"
    assert "stroke-opacity: 1; }" in style and "export function arcWidth(n, maxN, min = 2.6, max = 12)" in read(
        WEB / "js" / "kesfet-hesap.js"
    )
    assert '[data-theme="dark"] .arc-glow' in css and "prefers-color-scheme: dark" in css
    # Bir yay öne çıkar, diğerleri solar; seçili olmayan noktalar soluk.
    assert "has-active" in map_js and "'arc active'" in map_js
    assert ".arcs.has-active .arc:not(.active)" in css and ".map.has-arcs .pt:not(.sel)" in css
    # Renk skalası aynen kalır: beş basamaklı risk renkleri ve sınırları değişmedi.
    assert "RISK_EDGES = Object.freeze([0.15, 0.2, 0.25, 0.3])" in read(WEB / "js" / "kesfet-hesap.js")
    assert "--risk-1: #FCE08B;" in style and "--risk-5: #8E1B3A;" in style
    # Haritanın bandı ve legendi iki sitede aynı modüllerden gelir.
    assert "harita-lejant.js" in airports and "harita-lejant.js" in read(WEB / "sunum" / "harita-slayti.js")
    assert 'href="./css/harita.css"' in read(WEB / "index.html")


def test_site_files_stay_small():
    for path in source_files():
        limit = 100_000 if path.name in TEXT_MODULES else 60_000
        assert path.stat().st_size < limit, path.name
