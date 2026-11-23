// Rotalar: bir kalkış havalimanı seçilir, sonra varış x kalkış bloğu x mevsim hücrelerine bakılır.
// Sütunlar sıralanabilir; bu bir tablo özelliğidir, hiçbir kuruluşun sıralaması değildir.

import { el, fill, selectField, fillSelect, loadingNode, sozlukLink, anlamKutusu } from '../dom.js';
import { loadHavalimanlari, loadManifest, loadRoutes, routeOrigins } from '../data.js';
import { fmtPct, fmtMin, fmtInt, NA, seasonLabel, SEASON_ORDER, blockLabel, BLOCK_ORDER, txt } from '../fmt.js';
import { T } from '../metin.js';
import { gizlemeNedeni } from '../yerel.js';
import { createTable } from '../table.js';

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

  state.ui = { originField, destField, blockField, seasonField, summary, airportNote, tableHolder, table: null };

  fill(
    root,
    anlamKutusu('rotalar', ['blok-sure-tamponu']),
    el('p', null, t.giris, ' ', T.ortak.sozluk, sozlukLink('hucre'), ', ', sozlukLink('kantil'), ', ', sozlukLink('conformal'), '.'),
    el('form', { class: 'controls', onsubmit: (e) => e.preventDefault(), 'aria-label': t.filtreler }, originField.wrap, destField.wrap, blockField.wrap, seasonField.wrap),
    el(
      'div',
      { class: 'notice warn', role: 'note' },
      el('strong', null, t.uyariBaslik),
      t.uyari,
      ' ',
      sozlukLink('maliyet-orani'),
      '. ',
      el('a', { href: '#optimization' }, T.bolumler.optimization),
    ),
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

async function setOrigin(iata, updateHash) {
  const ui = state.ui;
  const t = T.rota;
  state.origin = iata;
  const ticket = ++state.request;
  if (updateHash) history.replaceState(null, '', `#routes/${iata}`);
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

function buildTable(rows) {
  const tb = T.rota.tablo;
  const pct = (key) => (r) => fmtPct(r[key]);
  const mins = (key) => (r) => fmtMin(r[key]);
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
      { key: 'obs', label: tb.gozlenen, numeric: true, render: pct('obs') },
      { key: 'pred', label: tb.tahmin, numeric: true, render: pct('pred') },
      { key: 'p50', label: 'P50', numeric: true, render: mins('p50') },
      { key: 'p80', label: 'P80', numeric: true, render: mins('p80') },
      { key: 'p95', label: 'P95', numeric: true, render: mins('p95') },
      { key: 'c80', label: tb.p80Sinir, title: tb.p80SinirIpucu, numeric: true, render: mins('c80') },
      { key: 'c95', label: tb.p95Sinir, title: tb.p95SinirIpucu, numeric: true, render: mins('c95') },
      { key: 'cov80', label: tb.p80Kapsama, title: tb.p80KapsamaIpucu, numeric: true, render: pct('cov80') },
      { key: 'cov95', label: tb.p95Kapsama, title: tb.p95KapsamaIpucu, numeric: true, render: pct('cov95') },
      { key: 'canc', label: tb.iptal, numeric: true, render: pct('canc') },
      { key: 'blk', label: tb.blok, title: tb.blokIpucu, numeric: true, render: mins('blk') },
      { key: 'buf', label: tb.tampon, title: tb.tamponIpucu(T.tamponUyari), numeric: true, render: (r) => (r.buf === null ? NA : fmtMin(r.buf)) },
    ],
  });
}
