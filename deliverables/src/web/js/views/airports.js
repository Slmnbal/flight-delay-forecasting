// Havalimanları (Keşfet sekmesinin üst yarısı): sayfa genişliğinin tamamını kaplayan harita bandı ve açılır,
// sıralanabilir tablo (gözlenen ve tahmin edilen geç varış oranı, iptal, kapsama). Renk açıklaması, seçili
// havalimanının bilgi kartı ve notlar geniş ekranda haritanın köşelerinde yarı saydam panel olarak durur;
// dar ekranda haritanın altına iner (CSS: .map-band). Seçili havalimanından çıkan rota yayları haritada
// çizilir; üzerine gelinen yay öne çıkar, diğerleri solar (map.js).
// opts.onSelect(iata, goToRoutes) seçimi rota tablosuna iletir. mount() bir denetleyici döndürür:
// setArcs(veri) seçili havalimanının rota yaylarını çizdirir (veriyi Keşfet sayfası hazırlar).

import { el, fill, selectField } from '../dom.js';
import { loadHavalimanlari, loadEyaletler } from '../data.js';
import { fmtPct, fmtInt, fmtNum, NA } from '../fmt.js';
import { T } from '../metin.js';
import { gizlemeNedeni } from '../yerel.js';
import { buildMap, isCompact, onMap, widthForHeight } from '../map.js';
import { mountChart } from '../charts.js';
import { createTable } from '../table.js';
import { icon } from '../simgeler.js';
import { RISK_EDGES, riskClass, equalEdges } from '../kesfet-hesap.js';
import { strip, edgeLabels, sizeKey, hiddenKey, arcKey } from '../harita-lejant.js';

const METRIC_KEYS = ['gozlenen_arrdel15_orani', 'tahmin_arrdel15_orani', 'iptal_orani', 'kapsama_p80', 'kapsama_p95'];
// Geç varış oranları sabit risk sınırlarıyla boyanır; diğer ölçütler kendi aralığını 5 eşit sınıfa böler.
const RATE_KEYS = new Set(['gozlenen_arrdel15_orani', 'tahmin_arrdel15_orani']);

// Geniş ekranda harita sabit yükseklikli bantta durur (CSS ile aynı eşik).
const wideBand = () => typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 75rem)').matches;

const clip = (text, max = 34) => (String(text).length > max ? `${String(text).slice(0, max - 1)}…` : String(text));

export async function mount(root, params, opts = {}) {
  // Eyalet sınırları isteğe bağlıdır: yüklenemezse (null) harita ızgarayla çalışır.
  const [file, states] = await Promise.all([loadHavalimanlari(), loadEyaletler()]);
  const airports = file.havalimanlari;
  const byCode = new Map(airports.map((a) => [a.iata, a]));
  const t = T.havalimani;
  // Etiketler seçili dilde okunur (dil değişince görünüm yeniden kurulur).
  const METRICS = METRIC_KEYS.map((key) => ({ key, label: t.olcutler[key] }));
  let metric = METRICS[0];
  let selected = opts.initial && airports.some((a) => a.iata === opts.initial) ? opts.initial : null;
  let arcState = null; // {origin, items (çizilebilenler), missing, outside, failed}

  const detail = el('div', { class: 'detail', 'aria-live': 'polite' });
  const legendHolder = el('div', { class: 'map-legend' });
  const arcNote = el('div', { class: 'stack' });
  const mapHolder = el('div', { class: 'map-box' });

  function domainFor(key) {
    const values = airports.map((a) => a[key]).filter((v) => v !== null && v !== undefined);
    return values.length ? [Math.min(...values), Math.max(...values)] : [0, 1];
  }

  /** Seçili ölçütün renk sınıfı sınırları ve açıklama etiketleri. */
  function scaleOf() {
    if (RATE_KEYS.has(metric.key)) return { edges: RISK_EDGES, labels: edgeLabels(RISK_EDGES) };
    const [lo, hi] = domainFor(metric.key);
    return { edges: equalEdges(lo, hi), labels: [fmtPct(lo), '', '', '', fmtPct(hi)] };
  }

  function labelOf(a) {
    const v = a[metric.key];
    const text = v === null || v === undefined ? T.ortak.yayimlanmadiKucuk : fmtPct(v);
    return t.aria(a.iata, a.ad, metric.label, text, fmtInt(a.n_test_ucus));
  }

  function pointTip(a) {
    const v = a[metric.key];
    const text = v === null || v === undefined ? T.ortak.yayimlanmadi : fmtPct(v);
    return [`${a.iata} ${a.ad}`, `${metric.label}: ${text}`, `${t.satirlar.testUcus}: ${fmtInt(a.n_test_ucus)}`].map((l) => clip(l, 44));
  }

  const arcLabel = (item) => t.yayEtiket(item.iata, item.ad, fmtInt(item.n), item.rate === null ? NA : fmtPct(item.rate));
  const arcTip = (item) => [clip(`${item.iata} ${item.ad}`, 44), t.yayIpucuUcus(fmtInt(item.n)), item.rate === null ? NA : t.yayIpucuGec(fmtPct(item.rate))];

  const chart = mountChart(mapHolder, (width) => {
    const scale = scaleOf();
    // Sabit yükseklikli bantta harita yüksekliğe sığacak genişlikte çizilir (yanlarda deniz kalır).
    const fixed = wideBand() && mapHolder.clientHeight > 0;
    return buildMap({
      width: fixed ? Math.max(300, Math.min(width, widthForHeight(mapHolder.clientHeight))) : width,
      airports,
      states,
      valueOf: (a) => a[metric.key],
      classOf: (a) => riskClass(a[metric.key], scale.edges),
      selected,
      labelOf,
      pointTip,
      onSelect: select,
      arcs: arcState && selected === arcState.origin ? { origin: arcState.origin, items: arcState.items, edges: RISK_EDGES, groupLabel: t.yayGrup(arcState.origin) } : null,
      arcLabel,
      arcTip,
    });
  });

  // ---------------------------------------------------------------- açıklama (lejant)
  function renderLegend() {
    const sc = scaleOf();
    const compact = isCompact(mapHolder.clientWidth || 600);
    fill(
      legendHolder,
      el('div', { class: 'legend-row legend-col' }, el('span', { class: 'legend-title' }, t.lejantBaslik(metric.label)), strip(sc.labels)),
      sizeKey(airports, compact),
      hiddenKey(airports),
      arcState ? arcKey(arcState.items, compact, RATE_KEYS.has(metric.key), t.olcutler.gozlenen_arrdel15_orani) : null,
    );
  }

  function renderArcNote() {
    if (!arcState) {
      fill(arcNote);
      return;
    }
    fill(
      arcNote,
      arcState.failed ? el('p', { class: 'notice', role: 'note' }, icon('info'), el('span', null, t.yayYok)) : null,
      arcState.missing > 0 ? el('p', { class: 'note', role: 'note' }, t.yayEksik(fmtInt(arcState.missing), arcState.missing === 1)) : null,
      arcState.outside > 0 ? el('p', { class: 'note', role: 'note' }, t.yayDisari(fmtInt(arcState.outside), arcState.outside === 1)) : null,
    );
  }

  function renderDetail() {
    const a = selected ? byCode.get(selected) : null;
    if (!a) {
      fill(detail, el('h3', { class: 'with-ico' }, icon('pin'), el('span', null, t.ayrintiBaslik)), el('p', { class: 'muted' }, t.ayrintiBos));
      return;
    }
    const s = t.satirlar;
    const pub = (v) => (a.gizleme_nedeni ? T.ortak.yayimlanmadi : fmtPct(v));
    const rows = [
      [s.testUcus, fmtInt(a.n_test_ucus)],
      [s.gozlenen, pub(a.gozlenen_arrdel15_orani)],
      [s.tahmin, pub(a.tahmin_arrdel15_orani)],
      [s.iptal, pub(a.iptal_orani)],
      [s.p80, pub(a.kapsama_p80)],
      [s.p95, pub(a.kapsama_p95)],
    ];
    fill(
      detail,
      el('h3', { class: 'with-ico' }, icon('plane'), el('span', null, a.iata)),
      el('p', null, a.ad),
      el('p', { class: 'muted' }, a.saat_dilimi),
      a.gizleme_nedeni ? el('p', { class: 'notice warn' }, icon('alert'), el('span', null, gizlemeNedeni(a))) : null,
      el('dl', null, rows.flatMap(([term, v]) => [el('dt', null, term), el('dd', null, v)])),
      opts.onSelect ? el('p', null, el('button', { type: 'button', class: 'link-btn', onclick: () => opts.onSelect(a.iata, true) }, t.rotalariGoster(a.iata))) : null,
    );
  }

  function select(iata) {
    selected = iata;
    renderDetail();
    // Yaylar yeni havalimanı için gelene kadar eskileri gösterilmez.
    if (arcState && arcState.origin !== iata) {
      arcState = null;
      renderArcNote();
    }
    renderLegend();
    chart.redraw();
    if (opts.onSelect) opts.onSelect(iata, false);
  }

  const metricField = selectField(
    t.renklendir,
    METRICS.map((m) => ({ value: m.key, label: m.label })),
    metric.key,
    (value) => {
      metric = METRICS.find((m) => m.key === value) || METRICS[0];
      renderLegend();
      chart.redraw();
    },
  );

  // Tablo
  const pp = (a) => (a.gizleme_nedeni || a.tahmin_arrdel15_orani === null ? null : (a.tahmin_arrdel15_orani - a.gozlenen_arrdel15_orani) * 100);
  const cell = (a, key) => (a.gizleme_nedeni ? el('span', { class: 'np' }, T.ortak.yayimlanmadi) : fmtPct(a[key]));
  const tb = t.tablo;
  const table = createTable({
    caption: tb.baslik,
    label: tb.etiket,
    sort: { key: 'iata', dir: 'asc' },
    sticky: true,
    columns: [
      { key: 'iata', label: tb.havalimani, rowHeader: true, render: (a) => el('button', { type: 'button', class: 'link-btn', title: a.ad, onclick: () => select(a.iata) }, a.iata) },
      { key: 'n_test_ucus', label: tb.testUcus, numeric: true, render: (a) => fmtInt(a.n_test_ucus) },
      { key: 'gozlenen_arrdel15_orani', label: tb.gozlenen, title: tb.gozlenenIpucu, numeric: true, render: (a) => cell(a, 'gozlenen_arrdel15_orani') },
      { key: 'tahmin_arrdel15_orani', label: tb.tahmin, title: tb.tahminIpucu, numeric: true, render: (a) => cell(a, 'tahmin_arrdel15_orani') },
      {
        key: 'gap',
        label: tb.fark,
        title: tb.farkIpucu,
        numeric: true,
        sortValue: pp,
        render: (a) => {
          const v = pp(a);
          if (v === null) return a.gizleme_nedeni ? el('span', { class: 'np' }, T.ortak.yayimlanmadi) : NA;
          return `${fmtNum(v, 1, true)} ${T.ortak.puan}`;
        },
      },
      { key: 'iptal_orani', label: tb.iptal, numeric: true, render: (a) => cell(a, 'iptal_orani') },
      { key: 'kapsama_p80', label: tb.p80, title: tb.p80Ipucu, numeric: true, render: (a) => cell(a, 'kapsama_p80') },
      { key: 'kapsama_p95', label: tb.p95, title: tb.p95Ipucu, numeric: true, render: (a) => cell(a, 'kapsama_p95') },
    ],
    rows: airports,
  });

  const hidden = airports.filter((a) => a.gizleme_nedeni);
  const hiddenNotes = hidden.length
    ? el('p', { class: 'notice warn', role: 'note' }, icon('alert'), el('span', null, el('strong', null, t.yayimlanmayanlar), hidden.map((a) => a.iata).join(', ') + t.yayimlanmayanSonu))
    : null;

  renderLegend();
  renderDetail();

  // Tam genişlik bant: harita + köşelerde yarı saydam paneller (dar ekranda haritanın altında).
  const band = el(
    'div',
    { class: 'map-band' },
    mapHolder,
    el(
      'div',
      { class: 'map-overlays' },
      el('div', { class: 'map-panel ov-left' }, el('div', { class: 'controls' }, metricField.wrap), legendHolder),
      el('div', { class: 'map-panel ov-right' }, detail),
      el('div', { class: 'map-panel ov-bottom' }, arcNote, el('p', { class: 'note' }, states ? t.haritaNotu : t.haritaNotuEyaletsiz), hiddenNotes),
    ),
  );

  fill(root, band, el('details', { class: 'fold' }, el('summary', null, t.tabloBaslik), el('div', { class: 'fold-body' }, table.element)));

  return {
    /** data: {origin, items: [{iata, ad, enlem, boylam, n, rate}], missing: sayı, failed: boolean} ya da null */
    setArcs(data) {
      if (!data) {
        arcState = null;
      } else {
        const drawable = data.items.filter((i) => onMap(i.enlem, i.boylam));
        arcState = { origin: data.origin, items: drawable, missing: data.missing, outside: data.items.length - drawable.length, failed: Boolean(data.failed) };
        if (arcState.failed) arcState.missing = 0; // dosya yüklenemediyse tek ileti: yaylar yüklenemedi
      }
      renderArcNote();
      renderLegend();
      chart.redraw();
    },
  };
}
