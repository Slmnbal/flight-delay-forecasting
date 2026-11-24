// Rotalar (Keşfet sekmesinin alt yarısı): bir kalkış havalimanı seçilir, sonra varış x kalkış bloğu x
// mevsim hücrelerine bakılır. Sütunlar sıralanabilir; bu bir tablo özelliğidir, hiçbir kuruluşun sıralaması değildir.

import { el, svg, fill, selectField, fillSelect, loadingNode, sozlukLink } from '../dom.js';
import { loadHavalimanlari, loadManifest, loadRoutes, routeOrigins } from '../data.js';
import { fmtPct, fmtMin, fmtInt, NA, seasonLabel, SEASON_ORDER, blockLabel, BLOCK_ORDER, txt } from '../fmt.js';
import { T } from '../metin.js';
import { gizlemeNedeni } from '../yerel.js';
import { createTable } from '../table.js';
import { icon } from '../simgeler.js';
import { riskClass, riskLevel, RISK_LOW, RISK_HIGH } from '../kesfet-hesap.js';

const BAR_W = 56; // hücre içi küçük çubukların genişliği (piksel)
const BAR_H = 8;
const RATE_BAR_MAX = 0.5; // oran çubuğu bu orana kadar dolar
const LEVEL_ICON = { low: 'shield', medium: 'info', high: 'alert' };

let names = new Map();
let airportByCode = new Map();
let state;

export async function mount(root, params) {
  const t = T.rota;
  const [airportsFile, manifest] = await Promise.all([loadHavalimanlari(), loadManifest()]);
  const available = routeOrigins(manifest);
  const airports = airportsFile.havalimanlari.filter((a) => available.has(a.iata)).sort((a, b) => a.iata.localeCompare(b.iata));
  names = new Map(airportsFile.havalimanlari.map((a) => [a.iata, a.ad]));
  airportByCode = new Map(airportsFile.havalimanlari.map((a) => [a.iata, a]));
  if (!airports.length) throw new Error(T.hata.rotaDosyasiYok);

  const first = params && params[0] && available.has(params[0]) ? params[0] : airports.some((a) => a.iata === 'ORD') ? 'ORD' : airports[0].iata;

  state = { origin: first, dest: '', block: '', season: '', rows: [], request: 0 };

  const originField = selectField(t.kalkis, airports.map((a) => ({ value: a.iata, label: `${a.iata} ${a.ad}` })), first, (v) => setOrigin(v, true));
  const destField = selectField(t.varis, [{ value: '', label: t.tumVarislar }], '', (v) => { state.dest = v; applyFilters(); });
  const blockField = selectField(t.blok, [{ value: '', label: t.tumBloklar }], '', (v) => { state.block = v; applyFilters(); });
  const seasonField = selectField(t.mevsim, [{ value: '', label: t.tumMevsimler }], '', (v) => { state.season = v; applyFilters(); });

  const summary = el('p', { role: 'status', 'aria-live': 'polite' });
  const airportNote = el('div');
  const tableHolder = el('div');

  const heading = el('h3', { id: 'ex-routes', tabindex: '-1' }, txt(t.baslik(first)));
  state.ui = { originField, destField, blockField, seasonField, summary, airportNote, tableHolder, heading, table: null };

  fill(
    root,
    heading,
    el('form', { class: 'controls', onsubmit: (e) => e.preventDefault(), 'aria-label': t.filtreler }, originField.wrap, destField.wrap, blockField.wrap, seasonField.wrap),
    scaleLegend(),
    el('p', { class: 'note note-ico', role: 'note' }, icon('buffer', { size: 16 }), el('span', null, el('strong', null, t.uyariBaslik), T.tamponUyari, ' ', sozlukLink('blok-sure-tamponu'), ', ', sozlukLink('kantil'), '.')),
    el('p', { class: 'note' }, t.gizlemeNotu),
    airportNote,
    summary,
    tableHolder,
  );
  await setOrigin(first, false);
}

export function onParams(params) {
  if (!state || !params || !params[0]) return;
  if (params[0] !== state.origin && state.ui.originField.select.querySelector(`option[value="${params[0]}"]`)) {
    state.ui.originField.select.value = params[0];
    setOrigin(params[0], false);
  }
}

/** Başlığa odaklanır (haritadan "rotalara git" için). */
export function focusHeading() {
  if (!state) return;
  state.ui.heading.scrollIntoView();
  state.ui.heading.focus({ preventScroll: true });
}

async function setOrigin(iata, updateHash) {
  const ui = state.ui;
  const t = T.rota;
  state.origin = iata;
  const ticket = ++state.request;
  ui.heading.textContent = txt(t.baslik(iata));
  if (updateHash) history.replaceState(null, '', `#explore/${iata}`);
  fill(ui.tableHolder, loadingNode(t.yukleniyor(iata)));
  ui.summary.textContent = '';

  // Not: boş not alanı null olabilir; fill() null değerleri atlar ("null" metni görünmez).
  const a = airportByCode.get(iata);
  fill(
    ui.airportNote,
    a && a.gizleme_nedeni ? el('div', { class: 'notice warn', role: 'note' }, el('strong', null, `${iata}: `), t.havalimaniNotu(gizlemeNedeni(a))) : null,
  );

  let file;
  try {
    file = await loadRoutes(iata);
  } catch (err) {
    if (ticket !== state.request) return;
    fill(
      ui.tableHolder,
      el('div', { class: 'error', role: 'alert' }, el('p', null, err.message), el('button', { type: 'button', class: 'btn', onclick: () => setOrigin(iata, false) }, T.hata.yenidenDene)),
    );
    return;
  }
  if (ticket !== state.request) return;

  const seasonIndex = (s) => SEASON_ORDER.indexOf(s);
  state.rows = file.hucreler
    .map((h) => ({
      dest: h.dest,
      block: h.saat_blogu,
      season: h.mevsim,
      seasonIdx: seasonIndex(h.mevsim),
      n: h.n_ucus,
      obs: h.gozlenen_arrdel15_orani,
      pred: h.tahmin_arrdel15_orani,
      p50: h.kantil_dk.p50,
      p80: h.kantil_dk.p80,
      p95: h.kantil_dk.p95,
      c80: h.kantil_conf_dk.p80,
      c95: h.kantil_conf_dk.p95,
      cov80: h.kapsama.p80,
      cov95: h.kapsama.p95,
      canc: h.iptal_orani,
      blk: h.planli_blok_sure_medyan_dk,
      buf: h.tampon_onerisi_dk === undefined ? null : h.tampon_onerisi_dk,
    }))
    .sort((x, y) => x.dest.localeCompare(y.dest) || BLOCK_ORDER.indexOf(x.block) - BLOCK_ORDER.indexOf(y.block) || x.seasonIdx - y.seasonIdx);

  // Filtre seçeneklerini gerçekte bulunan veriden yeniden kur.
  const dests = [...new Set(state.rows.map((r) => r.dest))].sort();
  const blocks = BLOCK_ORDER.filter((b) => state.rows.some((r) => r.block === b));
  const seasons = SEASON_ORDER.filter((s) => state.rows.some((r) => r.season === s));
  state.dest = '';
  state.block = '';
  state.season = '';
  fillSelect(ui.destField.select, [{ value: '', label: t.tumVarislar }, ...dests.map((d) => ({ value: d, label: names.has(d) ? `${d} ${names.get(d)}` : d }))], '');
  fillSelect(ui.blockField.select, [{ value: '', label: t.tumBloklar }, ...blocks.map((b) => ({ value: b, label: blockLabel(b) }))], '');
  fillSelect(ui.seasonField.select, [{ value: '', label: t.tumMevsimler }, ...seasons.map((s) => ({ value: s, label: seasonLabel(s) }))], '');

  ui.table = buildTable(state.rows);
  fill(ui.tableHolder, ui.table.element);
  applyFilters();
}

function applyFilters() {
  const ui = state.ui;
  const rows = state.rows.filter((r) => (!state.dest || r.dest === state.dest) && (!state.block || r.block === state.block) && (!state.season || r.season === state.season));
  if (ui.table) ui.table.setRows(rows);
  ui.summary.textContent = T.rota.ozet(fmtInt(rows.length), fmtInt(state.rows.length), txt(state.origin));
}

// ---------------------------------------------------------------------- hücre içi görseller
function barSvg(...children) {
  return svg('svg', { class: 'cbar', width: BAR_W, height: BAR_H, viewBox: `0 0 ${BAR_W} ${BAR_H}`, 'aria-hidden': 'true', focusable: 'false' }, ...children);
}

/** Geç varış oranı hücresi: yüzde, risk rozeti (simge + metin + renk) ve küçük yatay çubuk. */
function riskCell(rate) {
  const level = riskLevel(rate);
  const cls = riskClass(rate);
  if (level === null) return NA;
  const filled = Math.max(1, Math.min(1, rate / RATE_BAR_MAX) * BAR_W);
  return el(
    'span',
    { class: 'risk-cell' },
    fmtPct(rate),
    el('span', { class: `risk-badge rb${cls}` }, icon(LEVEL_ICON[level], { size: 14 }), T.rota.risk[level]),
    barSvg(svg('rect', { class: 'cbar-bg', x: 0, y: 0, width: BAR_W, height: BAR_H, rx: 2 }), svg('rect', { class: `cbar-fill r${cls}`, x: 0, y: 0, width: filled.toFixed(1), height: BAR_H, rx: 2 })),
  );
}

/** Kantil hücresi: dakika ve sıfır çizgisinden başlayan küçük çubuk (eksi = erken, ayrı renk). */
function quantileCell(value, scale) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return NA;
  const span = scale.neg + scale.pos;
  const perMin = span > 0 ? BAR_W / span : 0;
  const zero = scale.neg * perMin;
  const w = Math.max(Math.abs(value) * perMin, value === 0 ? 0 : 1);
  const x = value >= 0 ? zero : zero - w;
  return el(
    'span',
    { class: 'q-cell' },
    fmtMin(value),
    barSvg(svg('rect', { class: 'cbar-bg', x: 0, y: 0, width: BAR_W, height: BAR_H, rx: 2 }), svg('rect', { class: value < 0 ? 'qbar-fill early' : 'qbar-fill late', x: x.toFixed(1), y: 0, width: w.toFixed(1), height: BAR_H }), svg('line', { class: 'qbar-zero', x1: zero.toFixed(1), x2: zero.toFixed(1), y1: 0, y2: BAR_H })),
  );
}

/** Sade sütun başlığı: ana ad ve altında küçük teknik etiket (ör. P50). */
function head(main, tag) {
  return el('span', { class: 'th-stack' }, el('span', { class: 'th-main' }, main), tag ? el('span', { class: 'th-tag' }, tag) : null);
}

/** Gecikme sütunlarının ne anlama geldiği, risk rozetinin eşikleri ve sözlük bağlantıları. */
function scaleLegend() {
  const o = T.rota.olcek;
  const tb = T.rota.tablo;
  const items = [
    [tb.p50, 'P50', o.p50],
    [tb.p80, 'P80', o.p80],
    [tb.p95, 'P95', o.p95],
  ];
  return el(
    'div',
    { class: 'p-legend', role: 'note' },
    el('p', { class: 'p-legend-title' }, icon('clock', { size: 16 }), el('strong', null, o.baslik)),
    el('dl', { class: 'p-list' }, items.map(([name, tag, text]) => el('div', null, el('dt', null, name, ' ', el('span', { class: 'th-tag' }, tag)), el('dd', null, text)))),
    el('p', { class: 'note' }, o.erken, ' ', T.rota.risk.aciklama(fmtPct(RISK_LOW, 0), fmtPct(RISK_HIGH, 0)), ' ', T.ortak.sozluk, sozlukLink('kantil'), ', ', sozlukLink('conformal'), ', ', sozlukLink('kapsama'), '.'),
  );
}

function buildTable(rows) {
  const tb = T.rota.tablo;
  const pct = (key) => (r) => fmtPct(r[key]);
  const mins = (key) => (r) => fmtMin(r[key]);
  // Kantil çubukları tek ölçeği paylaşır: sıfırın solu (erken) ve sağı (geç) için en büyük değerler.
  const quantiles = rows.flatMap((r) => [r.p50, r.p80, r.p95, r.c80, r.c95]).filter((v) => typeof v === 'number' && Number.isFinite(v));
  const scale = { neg: Math.max(0, ...quantiles.map((v) => -v)), pos: Math.max(0, ...quantiles) };
  const qcol = (key, main, tag, hint) => ({ key, label: head(main, tag), title: hint, numeric: true, render: (r) => quantileCell(r[key], scale) });
  return createTable({
    caption: tb.baslik(state.origin),
    label: tb.etiket,
    sticky: true,
    pageSize: 100,
    rows,
    groups: [
      { label: tb.gruplar[0], span: 4 },
      { label: tb.gruplar[1], span: 2 },
      { label: tb.gruplar[2], span: 3 },
      { label: tb.gruplar[3], span: 2 },
      { label: tb.gruplar[4], span: 2 },
      { label: tb.gruplar[5], span: 3 },
    ],
    columns: [
      { key: 'dest', label: tb.varis, rowHeader: true, render: (r) => el('abbr', { title: names.get(r.dest) || r.dest }, r.dest) },
      { key: 'block', label: tb.kalkis, title: tb.kalkisIpucu, sortValue: (r) => BLOCK_ORDER.indexOf(r.block), render: (r) => blockLabel(r.block) },
      { key: 'seasonIdx', label: tb.mevsim, render: (r) => seasonLabel(r.season) },
      { key: 'n', label: tb.ucus, numeric: true, render: (r) => fmtInt(r.n) },
      { key: 'obs', label: head(tb.gozlenen), title: tb.gozlenenIpucu, numeric: true, render: (r) => riskCell(r.obs) },
      { key: 'pred', label: head(tb.tahmin, 'T2'), numeric: true, render: pct('pred') },
      qcol('p50', tb.p50, 'P50', tb.p50Ipucu),
      qcol('p80', tb.p80, 'P80', tb.p80Ipucu),
      qcol('p95', tb.p95, 'P95', tb.p95Ipucu),
      qcol('c80', tb.p80Sinir, 'P80', tb.p80SinirIpucu),
      qcol('c95', tb.p95Sinir, 'P95', tb.p95SinirIpucu),
      { key: 'cov80', label: head(tb.p80Kapsama, 'P80'), title: tb.p80KapsamaIpucu, numeric: true, render: pct('cov80') },
      { key: 'cov95', label: head(tb.p95Kapsama, 'P95'), title: tb.p95KapsamaIpucu, numeric: true, render: pct('cov95') },
      { key: 'canc', label: tb.iptal, numeric: true, render: pct('canc') },
      { key: 'blk', label: tb.blok, title: tb.blokIpucu, numeric: true, render: mins('blk') },
      {
        key: 'buf',
        label: el('span', { class: 'th-stack' }, el('span', { class: 'th-main th-ico' }, icon('buffer', { size: 14 }), tb.tampon)),
        title: tb.tamponIpucu(T.tamponUyari),
        numeric: true,
        render: (r) => (r.buf === null ? NA : el('span', { class: 'buf-cell' }, icon('buffer', { size: 14 }), fmtMin(r.buf))),
      },
    ],
  });
}
