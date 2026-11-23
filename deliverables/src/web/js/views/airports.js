// Havalimanları: harita ve sıralanabilir tablo (gözlenen ve tahmin edilen geç varış oranı, iptal, kapsama).

import { el, fill, selectField } from '../dom.js';
import { loadHavalimanlari, loadEyaletler } from '../data.js';
import { fmtPct, fmtInt, fmtNum, NA } from '../fmt.js';
import { T } from '../metin.js';
import { buildMap, rampBar } from '../map.js';
import { mountChart } from '../charts.js';
import { createTable } from '../table.js';

const METRIC_KEYS = ['gozlenen_arrdel15_orani', 'tahmin_arrdel15_orani', 'iptal_orani', 'kapsama_p80', 'kapsama_p95'];
const METRICS = METRIC_KEYS.map((key) => ({ key, label: T.havalimani.olcutler[key] }));

export async function mount(root) {
  // Eyalet sınırları isteğe bağlıdır: yüklenemezse (null) harita ızgarayla çalışır.
  const [file, states] = await Promise.all([loadHavalimanlari(), loadEyaletler()]);
  const airports = file.havalimanlari;
  const byCode = new Map(airports.map((a) => [a.iata, a]));
  const t = T.havalimani;
  let metric = METRICS[0];
  let selected = null;

  const detail = el('div', { class: 'detail', 'aria-live': 'polite' });
  const rampHolder = el('div', { class: 'ramp' });
  const mapHolder = el('div', { class: 'map-box' });

  function domainFor(key) {
    const values = airports.map((a) => a[key]).filter((v) => v !== null && v !== undefined);
    return values.length ? [Math.min(...values), Math.max(...values)] : [0, 1];
  }

  function labelOf(a) {
    const v = a[metric.key];
    const text = v === null || v === undefined ? T.ortak.yayimlanmadiKucuk : fmtPct(v);
    return t.aria(a.iata, a.ad, metric.label, text, fmtInt(a.n_test_ucus));
  }

  const chart = mountChart(mapHolder, (width) =>
    buildMap({
      width,
      airports,
      states,
      valueOf: (a) => a[metric.key],
      domain: domainFor(metric.key),
      selected,
      labelOf,
      onSelect: select,
    }),
  );

  function renderRamp() {
    const [lo, hi] = domainFor(metric.key);
    fill(rampHolder, el('span', { class: 'key' }, fmtPct(lo)), rampBar(), el('span', { class: 'key' }, fmtPct(hi)), el('span', null, t.rampaNotu));
  }

  function renderDetail() {
    const a = selected ? byCode.get(selected) : null;
    if (!a) {
      fill(detail, el('h3', null, t.ayrintiBaslik), el('p', { class: 'muted' }, t.ayrintiBos));
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
      el('h3', null, a.iata),
      el('p', null, a.ad),
      el('p', { class: 'muted' }, a.saat_dilimi),
      a.gizleme_nedeni ? el('p', { class: 'notice warn' }, a.gizleme_nedeni) : null,
      el('dl', null, rows.flatMap(([term, v]) => [el('dt', null, term), el('dd', null, v)])),
      el('p', null, el('a', { href: `#routes/${a.iata}` }, t.rotalariGoster(a.iata))),
    );
  }

  function select(iata) {
    selected = iata;
    renderDetail();
    chart.redraw();
  }

  const metricField = selectField(
    t.renklendir,
    METRICS.map((m) => ({ value: m.key, label: m.label })),
    metric.key,
    (value) => {
      metric = METRICS.find((m) => m.key === value) || METRICS[0];
      renderRamp();
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
    ? el(
        'div',
        { class: 'notice warn stack', role: 'note' },
        el('p', null, el('strong', null, t.yayimlanmayanlar), hidden.map((a) => a.iata).join(', ') + t.yayimlanmayanSonu),
        hidden.map((a) => el('p', null, el('strong', null, `${a.iata}: `), a.gizleme_nedeni)),
      )
    : null;

  renderRamp();
  renderDetail();

  fill(
    root,
    el('p', null, t.giris),
    el('div', { class: 'controls' }, metricField.wrap),
    el('div', { class: 'map-layout' }, el('div', null, mapHolder, rampHolder), detail),
    el('p', { class: 'note' }, states ? t.haritaNotu : t.haritaNotuEyaletsiz),
    el('h3', null, t.tabloBaslik),
    table.element,
    hiddenNotes,
  );
}
