// Tampon optimizasyonu (OR): politikalar test döneminde değerlendirilir. Maliyet oranı seçici (τ ızgarası),
// politika ve karşılaştırma tabloları, bütçe eğrisi, "aynı bütçede plan modeli ile B1" farkı ve ana
// sonuçlardan ayrı tutulan keşifsel bölüm. Anlamlılık kararları veri dosyasındaki %95 aralıktan okunur.

import { el, fill, selectField, sozlukLink, anlamKutusu } from '../dom.js';
import { loadOptimizasyon, loadOzet } from '../data.js';
import { fmtNum, fmtPct, fmtMin, fmtInt, fmtPlain, fmtRatio, NA, txt } from '../fmt.js';
import { T } from '../metin.js';
import { OR_NOTE_PREFIX, notBul, optimizasyonNotlari, politikaEtiketi, kesifselEtiketi } from '../yerel.js';
import { xyChart, legend, niceDomain, mountChart } from '../charts.js';
import { rowOf, excludesZero, hasInterval, sortedGrid, nearestIndex, equalBudget, equalBudgetSentence, tauSlider } from '../or-ortak.js';

// Dil değişince görünüm yeniden kurulur; seçimler burada saklanır.
const memory = { tau: null, olcut: 'arrdel15_orani' };

const FEATURED = ['plan-none', 'plan-b1', 'plan_conformal-b1'];
const METRIC_ORDER = ['arrdel15_orani', 'kalan_rotar_dk', 'kullanilmayan_dk', 'maliyet'];

const BUDGET_SERIES = [
  { id: 'plan_budget', cls: 'ser-a', marker: 'circle', hollow: false, dash: false },
  { id: 'b1_budget', cls: 'ser-b', marker: 'diamond', hollow: true, dash: true },
  { id: 'plan_arrdel15_budget', cls: 'ser-d', marker: 'square', hollow: false, dash: false },
];
const EXPLORE_STYLES = [
  { cls: 'ser-e', marker: 'square' },
  { cls: 'ser-c', marker: 'triangle' },
  { cls: 'ser-d', marker: 'circle' },
];

/** Ölçütün türüne göre değer biçimi (oran: yüzde, dakika, maliyet: sayı). */
function fmtBy(ad, v, plus = false) {
  if (ad === 'arrdel15_orani' || ad === 'emilen_orani') {
    // A difference of two rates is in percentage points, not percent.
    if (plus) return v === null || v === undefined ? NA : `${fmtNum(v * 100, 1, true)} ${T.ortak.puan}`;
    return fmtPct(v, 1);
  }
  if (ad === 'maliyet') return fmtNum(v, 2, plus);
  return fmtMin(v, 1, plus);
}

function dataTable({ caption, label, head, rows }) {
  return el(
    'div',
    { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': label },
    el(
      'table',
      { class: 'data' },
      el('caption', null, caption),
      el('thead', null, el('tr', null, head.map((h, i) => el('th', { scope: 'col', class: i > 0 ? 'num' : null }, h)))),
      el('tbody', null, rows.map((r) => el('tr', null, r.map((c, i) => (i === 0 ? el('th', { scope: 'row' }, c) : el('td', { class: 'num' }, c)))))),
    ),
  );
}

const byBudget = (a, b) => a.butce_dk - b.butce_dk;

export async function mount(root) {
  const t = T.or;
  const [opt, ozet] = await Promise.all([loadOptimizasyon(), loadOzet()]);
  if (!Array.isArray(opt.tau_izgarasi) || !opt.tau_izgarasi.length) throw new Error(t.veriYok);

  fill(
    root,
    anlamKutusu('tampon', ['blok-sure-tamponu', 'maliyet-orani', 'tampon-butcesi']),
    problemSection(opt, ozet),
    tauSection(opt),
    budgetSection(opt),
    exploratorySection(opt),
  );
}

// ---------------------------------------------------------------------- sorun ve varsayımlar
function problemSection(opt, ozet) {
  const t = T.or;
  const finding = notBul(ozet, OR_NOTE_PREFIX);
  const notes = optimizasyonNotlari(opt);
  const counts = opt.sayilar ? Object.keys(t.sayilar).map((key) => [t.sayilar[key], fmtInt(opt.sayilar[key])]) : [];
  return el(
    'section',
    { class: 'stack', 'aria-labelledby': 'or-problem' },
    el('h3', { id: 'or-problem' }, t.problemBaslik),
    el('p', null, t.problem),
    counts.length ? el('dl', { class: 'facts' }, counts.map(([term, v]) => el('div', null, el('dt', null, term), el('dd', null, v)))) : null,
    finding ? el('p', { class: 'notice' }, el('strong', null, t.bulgu), finding) : el('p', { class: 'muted' }, t.bulguYok),
    notes.length
      ? el('div', { class: 'notice stack' }, el('p', null, el('strong', null, t.notlarBaslik), ' ', t.notlarGiris), el('ul', { class: 'points' }, notes.map((n) => el('li', null, n))))
      : null,
    el('div', { class: 'notice warn', role: 'note' }, el('strong', null, T.rota.uyariBaslik), T.genel.tampon.varsayim),
    el('p', null, el('a', { href: '#routes' }, t.rotalarLink), ' ', T.ortak.sozluk, sozlukLink('newsvendor'), ', ', sozlukLink('lp-milp'), '.'),
  );
}

// ---------------------------------------------------------------------- τ seçici, politikalar, karşılaştırmalar
function tauSection(opt) {
  const t = T.or;
  const grid = sortedGrid(opt);
  const index = memory.tau !== null && memory.tau < grid.length ? memory.tau : nearestIndex(grid, 0.8);
  const out = el('div', { class: 'stack' });

  function cmpLabel(id) {
    const [a, b] = id.split('-');
    return b ? `${politikaEtiketi(opt, a)} − ${politikaEtiketi(opt, b)}` : id;
  }

  function cmpRows(list) {
    return list.map((c) => [
      cmpLabel(c.karsilastirma),
      t.olcut[c.ad] || txt(c.ad),
      fmtBy(c.ad, c.deger, true),
      hasInterval(c) ? `[${fmtBy(c.ad, c.ga95_alt, true)}; ${fmtBy(c.ad, c.ga95_ust, true)}]` : NA,
      hasInterval(c) ? (excludesZero(c) ? T.ortak.evet : T.ortak.hayir) : NA,
    ]);
  }

  function cmpTable(list, caption) {
    const head = [t.karsilastirma, T.hava.olcut, T.hava.fark, T.hava.aralik, T.hava.sifiriDislar];
    return el(
      'div',
      { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': t.karsilastirmaEtiket },
      el(
        'table',
        { class: 'data' },
        el('caption', null, caption),
        el('thead', null, el('tr', null, head.map((h, i) => el('th', { scope: 'col', class: i === 2 || i === 3 ? 'num' : null }, h)))),
        el(
          'tbody',
          null,
          cmpRows(list).map((r) => el('tr', null, el('th', { scope: 'row' }, r[0]), el('td', null, r[1]), el('td', { class: 'num' }, r[2]), el('td', { class: 'num' }, r[3]), el('td', null, r[4]))),
        ),
      ),
    );
  }

  function render(i) {
    memory.tau = i;
    const g = grid[i];
    const kat = fmtRatio(g.maliyet_orani);
    const k = t.slider.kat(kat);
    const policies = g.politikalar.map((r) => [
      politikaEtiketi(opt, r.kimlik),
      fmtMin(r.ek_tampon_dk),
      fmtMin(r.kalan_rotar_dk),
      fmtMin(r.kullanilmayan_dk),
      fmtPct(r.arrdel15_orani),
      fmtPct(r.emilen_orani),
      fmtNum(r.maliyet, 2),
    ]);
    const all = Array.isArray(g.karsilastirmalar) ? g.karsilastirmalar : [];
    const metricRank = (c) => METRIC_ORDER.indexOf(c.ad);
    const featured = FEATURED.flatMap((id) => all.filter((c) => c.karsilastirma === id).sort((a, b) => metricRank(a) - metricRank(b)));
    const others = all.filter((c) => !FEATURED.includes(c.karsilastirma));
    const kol = t.kolon;
    fill(
      out,
      el('h4', null, t.politikaBaslik(k)),
      dataTable({ caption: t.politikaCaption(k), label: t.politikaEtiket, head: [kol.politika, kol.ek, kol.kalan, kol.bosa, kol.arr, kol.emilen, kol.maliyet], rows: policies }),
      el('h4', null, t.karsilastirmaBaslik),
      featured.length ? cmpTable(featured, t.karsilastirmaCaption(k)) : el('p', { class: 'muted' }, t.yokKarsilastirma),
      others.length ? el('details', { class: 'data-table' }, el('summary', null, t.diger), cmpTable(others, t.karsilastirmaCaption(k))) : null,
      el('p', { class: 'note' }, t.farkNotu),
    );
  }

  const slider = tauSlider({ id: 'or-tau', grid, index, showTau: true, onChange: render });
  render(index);
  return el(
    'section',
    { class: 'stack', 'aria-labelledby': 'or-tau-h' },
    el('h3', { id: 'or-tau-h' }, t.tauBaslik),
    slider.element,
    out,
  );
}

// ---------------------------------------------------------------------- bütçe eğrisi
function budgetSection(opt) {
  const t = T.or;
  const curve = (Array.isArray(opt.butce_egrisi) ? [...opt.butce_egrisi] : []).sort(byBudget);
  if (!curve.length) return null;

  let metric = memory.olcut;
  const box = el('div', { class: 'chart-box wide' });
  const legendBox = el('div');
  const tableBox = el('div');
  const verdictBox = el('div', { class: 'stack' });

  const series = () =>
    BUDGET_SERIES.map((def) => ({
      ...def,
      name: politikaEtiketi(opt, def.id),
      points: curve
        .map((b) => ({ x: b.butce_dk, row: rowOf(b.politikalar, def.id) }))
        .filter((p) => p.row && typeof p.row[metric] === 'number')
        .map((p) => ({ x: p.x, y: p.row[metric], label: t.nokta(fmtPlain(p.x), fmtBy(metric, p.row[metric])) })),
    })).filter((s) => s.points.length);

  const metricName = () => (metric === 'arrdel15_orani' ? t.olcutArr : t.olcutKalan);

  function build(width) {
    const list = series();
    const xs = curve.map((b) => b.butce_dk);
    const ys = list.flatMap((s) => s.points.map((p) => p.y));
    if (!ys.length) return el('p', { class: 'muted' }, t.yokKarsilastirma);
    const xd = niceDomain(Math.min(...xs), Math.max(...xs), 5);
    const yd = niceDomain(Math.min(...ys), Math.max(...ys), 5);
    return xyChart({
      width,
      height: Math.round(Math.min(Math.max(width * 0.6, 280), 400)),
      xDomain: [xd.lo, xd.hi],
      yDomain: [yd.lo, yd.hi],
      xTicks: xd.ticks,
      yTicks: yd.ticks,
      xFormat: (v) => fmtPlain(v),
      yFormat: (v) => (metric === 'arrdel15_orani' ? fmtPct(v, 1) : fmtMin(v, 1)),
      xLabel: t.xEtiket,
      yLabel: metricName(),
      series: list.map((s) => ({ name: s.name, cls: s.cls, marker: s.marker, hollow: s.hollow, dash: s.dash, points: s.points })),
      title: t.grafikBaslik(metricName()),
      desc: t.grafikAciklama(list.map((s) => s.name).join(', ')),
    });
  }

  function renderTables() {
    const list = series();
    const head = [t.kolon.butce, ...list.map((s) => s.name)];
    const rows = curve.map((b) => [fmtPlain(b.butce_dk), ...list.map((s) => {
      const p = s.points.find((q) => q.x === b.butce_dk);
      return p ? fmtBy(metric, p.y) : NA;
    })]);
    fill(legendBox, legend(list));
    fill(
      tableBox,
      el('details', { class: 'data-table' }, el('summary', null, t.tabloGoster), dataTable({ caption: t.butceCaption(metricName()), label: t.butceCaption(metricName()), head, rows })),
    );

    const eb = equalBudget(opt, metric);
    const diffRows = eb.points.map((p) => [
      fmtPlain(p.butce),
      fmtBy(metric, p.c.deger, true),
      hasInterval(p.c) ? `[${fmtBy(metric, p.c.ga95_alt, true)}; ${fmtBy(metric, p.c.ga95_ust, true)}]` : NA,
      hasInterval(p.c) ? (excludesZero(p.c) ? T.ortak.evet : T.ortak.hayir) : NA,
    ]);
    fill(
      verdictBox,
      el('h4', null, t.esitBaslik),
      el('p', null, t.esitGiris),
      el('p', { class: 'notice', role: 'status' }, equalBudgetSentence(eb)),
      eb.total ? dataTable({ caption: t.esitCaption(metricName()), label: t.esitCaption(metricName()), head: [t.kolon.butce, T.hava.fark, T.hava.aralik, T.hava.sifiriDislar], rows: diffRows }) : null,
    );
  }

  const chart = mountChart(box, build);
  renderTables();

  const metricField = selectField(
    t.olcutSec,
    [
      { value: 'arrdel15_orani', label: t.olcutArr },
      { value: 'kalan_rotar_dk', label: t.olcutKalan },
    ],
    metric,
    (v) => {
      metric = v;
      memory.olcut = v;
      chart.redraw();
      renderTables();
    },
  );

  return el(
    'section',
    { class: 'stack', 'aria-labelledby': 'or-budget' },
    el('h3', { id: 'or-budget' }, t.butceBaslik),
    el('p', null, t.butceGiris),
    el('div', { class: 'controls' }, metricField.wrap),
    box,
    legendBox,
    tableBox,
    verdictBox,
  );
}

// ---------------------------------------------------------------------- keşifsel bölüm
function exploratorySection(opt) {
  const t = T.or.kesifsel;
  const k = opt.kesifsel;
  if (!k || !Array.isArray(k.butce_egrisi) || !k.butce_egrisi.length) return null;
  const curve = [...k.butce_egrisi].sort(byBudget);
  const ids = [];
  for (const b of curve) for (const r of b.politikalar) if (!ids.includes(r.kimlik)) ids.push(r.kimlik);

  const list = [];
  ids.forEach((id, n) => {
    const style = EXPLORE_STYLES[n % EXPLORE_STYLES.length];
    const label = politikaEtiketi(opt, id);
    const pointsOf = (key) =>
      curve
        .map((b) => ({ x: b.butce_dk, row: rowOf(b.politikalar, id) }))
        .filter((p) => p.row && typeof p.row[key] === 'number')
        .map((p) => ({ x: p.x, y: p.row[key] }));
    const observed = pointsOf('arrdel15_orani');
    const expected = pointsOf('beklenen_arrdel15_orani');
    const two = expected.length > 0;
    const named = (pts) => pts.map((p) => ({ x: p.x, y: p.y, label: T.or.nokta(fmtPlain(p.x), fmtPct(p.y)) }));
    if (observed.length) list.push({ ...style, hollow: false, dash: false, name: two ? t.seri(label, t.gerceklesen) : label, points: named(observed) });
    if (two) list.push({ ...style, hollow: true, dash: true, name: t.seri(label, t.beklenen), points: named(expected) });
  });
  if (!list.length) return null;

  const box = el('div', { class: 'chart-box wide' });
  const xs = curve.map((b) => b.butce_dk);
  const ys = list.flatMap((s) => s.points.map((p) => p.y));
  mountChart(box, (width) => {
    const xd = niceDomain(Math.min(...xs), Math.max(...xs), 5);
    const yd = niceDomain(Math.min(...ys), Math.max(...ys), 5);
    return xyChart({
      width,
      height: Math.round(Math.min(Math.max(width * 0.6, 280), 400)),
      xDomain: [xd.lo, xd.hi],
      yDomain: [yd.lo, yd.hi],
      xTicks: xd.ticks,
      yTicks: yd.ticks,
      xFormat: (v) => fmtPlain(v),
      yFormat: (v) => fmtPct(v, 1),
      xLabel: T.or.xEtiket,
      yLabel: T.or.olcutArr,
      series: list.map((s) => ({ name: s.name, cls: s.cls, marker: s.marker, hollow: s.hollow, dash: s.dash, points: s.points })),
      title: t.grafikBaslik,
      desc: T.or.grafikAciklama(list.map((s) => s.name).join(', ')),
    });
  });

  const head = [T.or.kolon.butce, ...list.map((s) => s.name)];
  const rows = curve.map((b) => [fmtPlain(b.butce_dk), ...list.map((s) => {
    const p = s.points.find((q) => q.x === b.butce_dk);
    return p ? fmtPct(p.y) : NA;
  })]);

  return el(
    'section',
    { class: 'explore stack', 'aria-labelledby': 'or-explore' },
    el('h3', { id: 'or-explore' }, el('span', { class: 'badge explore-badge' }, t.rozet), ' ', t.baslik),
    el('p', { class: 'notice warn' }, el('strong', null, kesifselEtiketi(k))),
    el('p', null, t.uyari),
    box,
    legend(list),
    el('details', { class: 'data-table' }, el('summary', null, T.or.tabloGoster), dataTable({ caption: t.tabloCaption, label: t.tabloCaption, head, rows })),
  );
}
