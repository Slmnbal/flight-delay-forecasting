// Kalibrasyon ve kapsama: güvenilirlik diyagramları ve kantil üst sınırlarının aylık kapsaması.

import { el, fill, selectField, sozlukLink } from '../dom.js';
import { loadKalibrasyon } from '../data.js';
import { fmtPct, fmtInt, monthLabel, modelLabel, NA } from '../fmt.js';
import { T } from '../metin.js';
import { xyChart, legend, niceDomain, mountChart } from '../charts.js';

const t = T.kal;

const SERIES_STYLE = [
  { cls: 'ser-a', marker: 'circle', hollow: false, dash: false },
  { cls: 'ser-b', marker: 'diamond', hollow: true, dash: true },
];

// Etiketler seçili dilde okunur; mount() her çağrıldığında (dil değişince de) yeniden kurulur.
let TASKS = [];
let METHOD = {};

function initLabels() {
  TASKS = [
    { value: 'arrdel15', label: t.gorevler.arrdel15 },
    { value: 'iptal', label: t.gorevler.iptal },
  ];
  METHOD = {
    ham: { name: t.yontem.ham, cls: 'ser-c', marker: 'triangle', dash: true },
    statik: { name: t.yontem.statik, cls: 'ser-d', marker: 'square', dash: true },
    kayan: { name: t.yontem.kayan, cls: 'ser-a', marker: 'circle', dash: false },
  };
}

function explainText(series) {
  return series.length && series[0].bins.length ? t.aciklama(fmtInt(series[0].bins[0].n)) : t.aciklamaYok;
}

export async function mount(root) {
  initLabels();
  const kal = await loadKalibrasyon();

  // Güvenilirlik
  let task = 'arrdel15';
  const relChartBox = el('div', { class: 'chart-box' });
  const relLegend = el('div');
  const relTable = el('div');
  const relText = el('p', { class: 'note' });

  function reliabilitySeries() {
    const found = kal.siniflandirma.filter((s) => s.gorev === task && s.kume === 'test');
    found.sort((a, b) => (a.model === 'B1') - (b.model === 'B1'));
    return found.map((s, i) => ({
      model: s.model,
      name: modelLabel(s.model),
      ...SERIES_STYLE[Math.min(i, SERIES_STYLE.length - 1)],
      bins: s.kutular,
      points: s.kutular.map((b, k) => ({
        x: b.ortalama_tahmin,
        y: b.gozlenen_oran,
        label: t.nokta(k + 1, fmtPct(b.ortalama_tahmin), fmtPct(b.gozlenen_oran), fmtInt(b.n)),
      })),
    }));
  }

  let relChart = null;
  let relBuild = null;
  function renderReliability() {
    const series = reliabilitySeries();
    const max = Math.max(...series.flatMap((s) => s.bins.flatMap((b) => [b.ortalama_tahmin, b.gozlenen_oran])), 0.01);
    const dom = niceDomain(0, max * 1.05, 5);
    const digits = dom.hi < 0.1 ? 1 : 0;
    const taskLabel = TASKS.find((x) => x.value === task).label;
    fill(relLegend, legend(series));
    relText.textContent = explainText(series);
    relBuild = (width) =>
      xyChart({
        width,
        height: Math.round(Math.min(Math.max(width * 0.75, 300), 460)),
        xDomain: [0, dom.hi],
        yDomain: [0, dom.hi],
        xTicks: dom.ticks,
        yTicks: dom.ticks,
        xFormat: (v) => fmtPct(v, digits),
        yFormat: (v) => fmtPct(v, digits),
        xLabel: t.xEtiket,
        yLabel: t.yEtiket,
        diagonal: true,
        series: series.map((s) => ({ name: s.name, cls: s.cls, marker: s.marker, hollow: s.hollow, dash: s.dash, points: s.points })),
        title: t.grafikBaslik(taskLabel),
        desc: t.grafikAciklama(series.map((s) => s.name).join(', ')),
      });
    if (relChart) relChart.redraw();
    else relChart = mountChart(relChartBox, (width) => relBuild(width));

    const header = [t.dilim];
    for (const s of series) header.push(t.tahmin(s.name), t.gozlenen(s.name));
    const bodyRows = [];
    const count = series.length ? series[0].bins.length : 0;
    for (let i = 0; i < count; i += 1) {
      const cells = [el('th', { scope: 'row' }, String(i + 1))];
      for (const s of series) {
        const b = s.bins[i];
        cells.push(el('td', { class: 'num' }, b ? fmtPct(b.ortalama_tahmin) : NA), el('td', { class: 'num' }, b ? fmtPct(b.gozlenen_oran) : NA));
      }
      bodyRows.push(el('tr', null, cells));
    }
    fill(
      relTable,
      el(
        'details',
        { class: 'data-table' },
        el('summary', null, t.tabloGoster),
        el('div', { class: 'table-wrap' }, el('table', { class: 'data' }, el('caption', null, t.tabloBaslik(taskLabel)), el('thead', null, el('tr', null, header.map((h, i) => el('th', { scope: 'col', class: i ? 'num' : null }, h)))), el('tbody', null, bodyRows))),
      ),
    );
  }

  const taskField = selectField(t.gorev, TASKS, task, (v) => {
    task = v;
    renderReliability();
  });

  // Aylık kapsama
  let model = 'lgbm_plan';
  const covBox = el('div');
  const modelField = selectField(
    t.model,
    [
      { value: 'lgbm_plan', label: t.modelPlan },
      { value: 'lgbm_T2', label: t.modelT2 },
    ],
    model,
    (v) => {
      model = v;
      renderCoverage();
    },
  );

  function coverageSeries(target) {
    const rows = kal.kapsama_aylik.filter((r) => r.hedef === target);
    const groups = new Map();
    const add = (key, name, style, subset) => {
      if (!subset.length) return;
      groups.set(key, { name, ...style, rows: subset.sort((a, b) => a.ay.localeCompare(b.ay)) });
    };
    for (const method of ['ham', 'statik', 'kayan']) {
      add(method, METHOD[method].name, METHOD[method], rows.filter((r) => r.model === model && r.yontem === method && r.tur === 'tek_yonlu_ust'));
    }
    add('b1', t.b1Ham, { cls: 'ser-b', marker: 'diamond', hollow: true, dash: true }, rows.filter((r) => r.model === 'B1' && r.tur === 'tek_yonlu_ust'));
    if (target === 0.8) {
      add('iki', t.ikiYonlu, { cls: 'ser-e', marker: 'square', hollow: true, dash: false }, rows.filter((r) => r.model === model && r.tur === 'iki_yonlu'));
    }
    return [...groups.values()];
  }

  function coveragePanel(target) {
    const series = coverageSeries(target);
    const months = [...new Set(series.flatMap((s) => s.rows.map((r) => r.ay)))].sort();
    const values = series.flatMap((s) => s.rows.map((r) => r.kapsama));
    const dom = niceDomain(Math.min(...values, target) - 0.005, Math.max(...values, target) + 0.005, 5);
    const pct = Math.round(target * 100);
    const pctLabel = fmtPct(target, 0);
    const box = el('div', { class: 'chart-box wide' });
    const chartSeries = series.map((s) => ({
      name: s.name,
      cls: s.cls,
      marker: s.marker,
      hollow: s.hollow,
      dash: s.dash,
      points: s.rows.map((r) => ({ x: months.indexOf(r.ay), y: r.kapsama, label: t.nokta2(monthLabel(r.ay), fmtPct(r.kapsama), fmtInt(r.n)) })),
    }));
    mountChart(box, (width) =>
      xyChart({
        width,
        height: Math.round(Math.min(Math.max(width * 0.5, 280), 380)),
        xDomain: [-0.4, months.length - 0.6],
        yDomain: [dom.lo, dom.hi],
        xTicks: months.map((m, i) => ({ v: i, label: width < 520 ? m.slice(5) : monthLabel(m).slice(0, 3) })),
        yTicks: dom.ticks,
        yFormat: (v) => fmtPct(v, 1),
        xLabel: months.length ? t.ay(months[0].slice(0, 4)) : t.ayYok,
        yLabel: t.kapsamaY,
        hlines: [{ y: target, label: t.hedef(pctLabel) }],
        series: chartSeries,
        title: t.kapsamaGrafikBaslik(pct, modelLabel(model)),
        desc: t.kapsamaGrafikAciklama(series.map((s) => s.name).join('; ')),
      }),
    );

    const head = [t.ay2, ...series.map((s) => s.name)];
    const rowsEls = months.map((mo) =>
      el('tr', null, el('th', { scope: 'row' }, monthLabel(mo)), series.map((s) => {
        const r = s.rows.find((x) => x.ay === mo);
        return el('td', { class: 'num' }, r ? fmtPct(r.kapsama) : NA);
      })),
    );
    const rolling = series.find((s) => s.name === METHOD.kayan.name);
    let sentence = null;
    if (rolling) {
      const sorted = [...rolling.rows].sort((a, b) => a.kapsama - b.kapsama);
      const lowest = sorted[0];
      const highest = sorted[sorted.length - 1];
      sentence = el('p', null, t.cumle(fmtPct(lowest.kapsama), monthLabel(lowest.ay), fmtPct(highest.kapsama), monthLabel(highest.ay), pctLabel));
    }
    return el(
      'div',
      { class: 'stack' },
      el('h4', null, t.ustSinir(pct)),
      sentence,
      box,
      legend(series),
      el(
        'details',
        { class: 'data-table' },
        el('summary', null, t.tabloGoster),
        el('div', { class: 'table-wrap' }, el('table', { class: 'data' }, el('caption', null, t.kapsamaGrafikBaslik(pct, modelLabel(model))), el('thead', null, el('tr', null, head.map((h, i) => el('th', { scope: 'col', class: i ? 'num' : null }, h)))), el('tbody', null, rowsEls))),
      ),
    );
  }

  function renderCoverage() {
    fill(covBox, coveragePanel(0.8), coveragePanel(0.95));
  }

  renderReliability();
  renderCoverage();

  fill(
    root,
    el(
      'section',
      { class: 'stack', 'aria-labelledby': 'cal-rel' },
      el('h4', { id: 'cal-rel' }, t.guvenBaslik),
      el('div', { class: 'controls' }, taskField.wrap),
      relChartBox,
      relLegend,
      relText,
      el('p', { class: 'note' }, T.ortak.sozluk, sozlukLink('olasilik-kalibrasyon'), ', ', sozlukLink('platt'), '.'),
      relTable,
    ),
    el(
      'section',
      { class: 'stack', 'aria-labelledby': 'cal-cov' },
      el('h4', { id: 'cal-cov' }, t.kapsamaBaslik),
      el('p', null, t.kapsamaGiris, ' ', sozlukLink('conformal'), ', ', sozlukLink('kapsama'), '.'),
      el('div', { class: 'controls' }, modelField.wrap),
      covBox,
    ),
  );
}
