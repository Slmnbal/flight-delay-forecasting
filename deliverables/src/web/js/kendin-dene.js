// "Kendin dene": bir uçuş türü (kalkış havalimanı, varış, saat bloğu, mevsim) seçilir; gerçekleşen geç varış
// payı ve modelin beklentisi 100 daireyle, gecikme süresi de üç çubukla ("yarısı", "beşte dördü", "yirmide on
// dokuzu") gösterilir. Detay sitesinin Hikâye sekmesi ve sunumun son slaydı bu modülü kullanır. Seçimler dil
// değişince (görünüm yeniden kurulur) korunur. Sayıların hepsi rotalar/<IATA> dosyalarından okunur.
//
// opts: {base: ayrıntı bağlantılarının önü ('' ya da '../'), onCell(hücre | null): seçim değişince çağrılır}.

import { el, fill, selectField, fillSelect, loadingNode } from './dom.js';
import { loadRoutes, routeOrigins } from './data.js';
import { fmtMin, fmtInt, blockLabel, BLOCK_ORDER, seasonLabel, SEASON_ORDER } from './fmt.js';
import { T } from './metin.js';
import { gizlemeNedeni } from './yerel.js';
import { barChart, mountChart } from './charts.js';
import { LATE_AFTER, PICTO_TOTAL, count100, pictoPanel, wrapLabel } from './hikaye-ortak.js';

const memory = { origin: null, dest: null, block: null, season: null };

export async function buildTry(airportsFile, manifest, opts = {}) {
  const t = T.hikaye.s10;
  const base = opts.base || '';
  const notify = typeof opts.onCell === 'function' ? opts.onCell : () => {};
  const available = routeOrigins(manifest);
  const airports = airportsFile.havalimanlari.filter((a) => available.has(a.iata)).sort((a, b) => a.iata.localeCompare(b.iata));
  if (!airports.length) throw new Error(T.hata.rotaDosyasiYok);
  const byCode = new Map(airportsFile.havalimanlari.map((a) => [a.iata, a]));
  const first = airports.some((a) => a.iata === memory.origin) ? memory.origin : airports.some((a) => a.iata === 'ORD') ? 'ORD' : airports[0].iata;
  const sel = { origin: first, dest: memory.dest, block: memory.block, season: memory.season };
  let cells = [];
  let ticket = 0;

  const out = el('div', { class: 'stack' });
  const airportNote = el('div');

  const originField = selectField(T.rota.kalkis, airports.map((a) => ({ value: a.iata, label: `${a.iata} ${a.ad}` })), first, (v) => {
    sel.origin = v;
    sel.dest = null;
    sel.block = null;
    sel.season = null;
    loadOrigin();
  });
  const destField = selectField(T.rota.varis, [], '', (v) => {
    sel.dest = v;
    sel.block = null;
    sel.season = null;
    syncCell();
  });
  const blockField = selectField(T.rota.blok, [], '', (v) => {
    sel.block = v;
    sel.season = null;
    syncCell();
  });
  const seasonField = selectField(T.rota.mevsim, [], '', (v) => {
    sel.season = v;
    syncCell();
  });

  function bestCell() {
    const full = cells.filter((c) => c.mevsim === 'tum');
    const pool = full.length ? full : cells;
    return pool.reduce((best, c) => (c.n_ucus > best.n_ucus ? c : best), pool[0]);
  }

  function renderCell(cell) {
    notify(cell);
    if (!cell) {
      fill(out, el('p', { class: 'muted' }, t.hucreYok));
      return;
    }
    const obs = cell.gozlenen_arrdel15_orani;
    const pred = cell.tahmin_arrdel15_orani;
    const p50 = cell.kantil_dk.p50;
    const p80 = cell.kantil_conf_dk.p80;
    const p95 = cell.kantil_conf_dk.p95;
    const delayBox = el('div', { class: 'chart-box' });
    fill(
      out,
      el('div', { class: 'picto-pair' }, pictoPanel(t.gerceklesen, obs), pictoPanel(t.modelTahmini, pred)),
      el('p', { class: 'note' }, t.ikonAnahtar(fmtInt(LATE_AFTER))),
      el('p', { class: 'fact', role: 'status' }, t.cumle(fmtInt(count100(obs)), fmtInt(count100(pred)), fmtInt(PICTO_TOTAL), fmtInt(cell.n_ucus))),
      el('h4', null, t.rotarBaslik),
      el('p', null, p50 < 0 ? t.rotarCumle(fmtMin(-p50), fmtMin(p80), fmtMin(p95), true) : t.rotarCumle(fmtMin(p50), fmtMin(p80), fmtMin(p95), false)),
      delayBox,
      el('p', null, el('a', { href: `${base}#explore/${sel.origin}` }, T.havalimani.rotalariGoster(sel.origin))),
    );
    const items = [
      { label: t.yarisi, value: p50, text: fmtMin(p50) },
      { label: t.dortBes, value: p80, text: fmtMin(p80) },
      { label: t.ondokuz, value: p95, text: fmtMin(p95) },
    ];
    mountChart(delayBox, (width) => {
      const narrow = width < 480;
      return barChart({
        width,
        rowH: 36,
        labelWidth: narrow ? 84 : 130,
        tickCount: narrow ? 2 : 4,
        items: items.map((i) => ({ ...i, label: wrapLabel(i.label, narrow ? 12 : 22) })),
        tickFormat: (v) => fmtMin(v, 0),
        title: t.grafikBaslik,
        desc: t.grafikAciklama(fmtMin(p50), fmtMin(p80), fmtMin(p95)),
      });
    });
  }

  function syncCell() {
    if (!cells.length) {
      fill(out, el('p', { class: 'muted' }, t.hucreYok));
      notify(null);
      return;
    }
    const dests = [...new Set(cells.map((c) => c.dest))].sort();
    if (!dests.includes(sel.dest)) {
      const best = bestCell();
      sel.dest = best.dest;
      sel.block = best.saat_blogu;
      sel.season = best.mevsim;
    }
    const blocks = BLOCK_ORDER.filter((b) => cells.some((c) => c.dest === sel.dest && c.saat_blogu === b));
    if (!blocks.includes(sel.block)) sel.block = blocks[0];
    const seasons = SEASON_ORDER.filter((x) => cells.some((c) => c.dest === sel.dest && c.saat_blogu === sel.block && c.mevsim === x));
    if (!seasons.includes(sel.season)) sel.season = seasons.includes('tum') ? 'tum' : seasons[0];
    fillSelect(destField.select, dests.map((d) => ({ value: d, label: byCode.has(d) ? `${d} ${byCode.get(d).ad}` : d })), sel.dest);
    fillSelect(blockField.select, blocks.map((b) => ({ value: b, label: blockLabel(b) })), sel.block);
    fillSelect(seasonField.select, seasons.map((x) => ({ value: x, label: seasonLabel(x) })), sel.season);
    Object.assign(memory, sel);
    renderCell(cells.find((c) => c.dest === sel.dest && c.saat_blogu === sel.block && c.mevsim === sel.season) || null);
  }

  async function loadOrigin() {
    const iata = sel.origin;
    const mine = (ticket += 1);
    fill(out, loadingNode(t.yukleniyor(iata)));
    let file;
    try {
      file = await loadRoutes(iata);
    } catch (err) {
      if (mine !== ticket) return;
      fill(out, el('div', { class: 'error', role: 'alert' }, el('p', null, err.message), el('button', { type: 'button', class: 'btn', onclick: loadOrigin }, T.hata.yenidenDene)));
      return;
    }
    if (mine !== ticket) return;
    cells = file.hucreler;
    const a = byCode.get(iata);
    const reason = a ? gizlemeNedeni(a) : null;
    fill(airportNote, reason ? el('div', { class: 'notice warn', role: 'note' }, el('strong', null, `${iata}: `), T.rota.havalimaniNotu(reason)) : null);
    syncCell();
  }

  const section = el(
    'div',
    { class: 'stack try-it' },
    opts.intro === false ? null : el('p', { class: 'slide-text' }, t.p1),
    el('form', { class: 'controls', onsubmit: (e) => e.preventDefault(), 'aria-label': t.secim }, originField.wrap, destField.wrap, blockField.wrap, seasonField.wrap),
    airportNote,
    out,
  );
  await loadOrigin();
  return section;
}
