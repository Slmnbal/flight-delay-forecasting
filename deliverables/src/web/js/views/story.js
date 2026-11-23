// Hikâye: konuyu hiç bilmeyen biri için altı kısa adım. Sorun, model (100 ikonlu birim grafiği ve
// rötar dakikaları), hava bilgisi, tampon kaydırıcısı, dürüstlük ve teknik sekmelere bağlantılar.
// Hiçbir sayı elle yazılmaz: hepsi rotalar/<IATA>.json, hava-deneyi.json, optimizasyon.json ve
// ozet.json dosyalarından okunur. Seçimler dil değişince (görünüm yeniden çizilir) korunur.

import { el, fill, selectField, fillSelect, sozlukLink, loadingNode } from '../dom.js';
import { loadOzet, loadHava, loadOptimizasyon, loadHavalimanlari, loadManifest, loadRoutes, routeOrigins, findResult, findMetric, metricOf } from '../data.js';
import { fmtPct, fmtMin, fmtInt, fmtPlain, fmtRatio, fmtMetricValue, fmtInterval, blockLabel, BLOCK_ORDER, seasonLabel, SEASON_ORDER, NA, txt } from '../fmt.js';
import { T } from '../metin.js';
import { kabulAciklamasi, gizlemeNedeni } from '../yerel.js';
import { barChart, mountChart, pictograph } from '../charts.js';
import { rowOf, excludesZero, sortedGrid, nearestIndex, equalBudget, equalBudgetSentence, tauSlider } from '../or-ortak.js';

// Dil değişince görünüm yeniden kurulur; seçimler burada saklanır.
const memory = { origin: null, dest: null, block: null, season: null, tau: null };

const MORE = ['overview', 'airports', 'routes', 'optimization', 'calibration', 'weather', 'errors', 'about', 'sozluk'];

function step(n, id, title, ...children) {
  return el(
    'section',
    { class: 'story-step stack', 'aria-labelledby': id },
    el('h3', { id }, el('span', { class: 'step-no', 'aria-hidden': 'true' }, String(n)), el('span', { class: 'visually-hidden' }, `${T.hikaye.adim(n)}: `), title),
    children,
  );
}

const count100 = (rate) => Math.round(rate * 100);

function pictoPanel(name, rate, text) {
  const x = fmtInt(count100(rate));
  return el(
    'figure',
    { class: 'picto-panel' },
    pictograph({ count: count100(rate), title: text(name, x) }),
    el('figcaption', null, el('strong', null, name), el('span', { class: 'picto-count' }, T.hikaye.s2.ikonBaslik(x)), el('span', { class: 'note' }, fmtPct(rate))),
  );
}

export async function mount(root) {
  const s = T.hikaye;
  const [ozet, airportsFile, manifest] = await Promise.all([loadOzet(), loadHavalimanlari(), loadManifest()]);
  // Hava ve OR verisi yüklenemezse yalnızca o adım uyarı gösterir; diğer adımlar çalışır.
  const [hava, opt] = await Promise.all([loadHava().catch(() => null), loadOptimizasyon().catch(() => null)]);

  const stepTwo = await buildStepTwo(airportsFile, manifest);

  fill(
    root,
    el('p', { class: 'lede' }, s.giris),
    buildStepOne(ozet),
    stepTwo,
    buildStepThree(ozet, hava),
    buildStepFour(opt),
    buildStepFive(ozet, opt),
    buildStepSix(),
  );
}

// ---------------------------------------------------------------------- 1. sorun
function buildStepOne(ozet) {
  const t = T.hikaye.s1;
  let prevalence = null;
  for (const model of ['lgbm_T2', 'lgbm_plan', 'B1', 'B0']) {
    const m = findMetric(findResult(ozet, 'arrdel15', model), 'yayginlik');
    if (m && typeof m.deger === 'number') {
      prevalence = m;
      break;
    }
  }
  return step(
    1,
    'st-1',
    t.baslik,
    el('p', null, t.p1),
    el('p', null, t.p2, ' ', T.ortak.sozluk, sozlukLink('arrdel15'), '.'),
    el('p', null, t.p3),
    prevalence ? el('p', { class: 'fact' }, t.olgu(fmtInt(ozet.kapsam.test_ucus_sayisi), fmtMetricValue(prevalence))) : null,
  );
}

// ---------------------------------------------------------------------- 2. model: bir uçuş türü seç
async function buildStepTwo(airportsFile, manifest) {
  const t = T.hikaye.s2;
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
      el(
        'div',
        { class: 'picto-pair' },
        pictoPanel(t.gerceklesen, obs, t.ikonEtiket),
        pictoPanel(t.modelTahmini, pred, t.ikonEtiket),
      ),
      el('p', { class: 'note' }, t.ikonAnahtar),
      el('p', { class: 'fact', role: 'status' }, t.cumle(fmtInt(count100(obs)), fmtInt(count100(pred)), fmtInt(cell.n_ucus))),
      el('h4', null, t.rotarBaslik),
      el('p', null, p50 < 0 ? t.rotarCumle(fmtMin(-p50), fmtMin(p80), fmtMin(p95), true) : t.rotarCumle(fmtMin(p50), fmtMin(p80), fmtMin(p95), false)),
      delayBox,
      el('p', { class: 'note' }, t.eksi, ' ', t.kantilNotu),
      el('p', null, el('a', { href: `#routes/${sel.origin}` }, T.havalimani.rotalariGoster(sel.origin)), ' · ', el('a', { href: '#routes' }, T.bolumler.routes)),
    );
    const items = [
      { label: t.yarisi, value: p50, text: fmtMin(p50) },
      { label: t.seksen, value: p80, text: fmtMin(p80) },
      { label: t.doksanbes, value: p95, text: fmtMin(p95) },
    ];
    mountChart(delayBox, (width) =>
      barChart({
        width,
        labelWidth: 62,
        items,
        tickFormat: (v) => fmtMin(v, 0),
        title: t.grafikBaslik,
        desc: t.grafikAciklama(fmtMin(p50), fmtMin(p80), fmtMin(p95)),
      }),
    );
  }

  function syncCell() {
    if (!cells.length) {
      fill(out, el('p', { class: 'muted' }, t.hucreYok));
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

  const section = step(
    2,
    'st-2',
    t.baslik,
    el('p', null, t.p1),
    el('form', { class: 'controls', onsubmit: (e) => e.preventDefault(), 'aria-label': t.secim }, originField.wrap, destField.wrap, blockField.wrap, seasonField.wrap),
    airportNote,
    out,
  );
  await loadOrigin();
  return section;
}

// ---------------------------------------------------------------------- 3. hava bilgisi
function buildStepThree(ozet, hava) {
  const t = T.hikaye.s3;
  const title = T.hikaye.s3.baslik;
  if (!hava) return step(3, 'st-3', title, el('p', { class: 'muted' }, t.yok));
  const roc = (id) => {
    const v = hava.varyantlar.find((x) => x.varyant === id);
    return v ? v.metrikler.find((m) => m.ad === 'roc_auc') || null : null;
  };
  const plan = roc('plan');
  const t2 = roc('T2');
  const gap = hava.farklar.find((f) => f.karsilastirma === 'T2-plan' && f.metrik.ad === 'roc_auc');
  const d = gap ? gap.metrik : null;
  const meter = (label, m) => {
    if (!m || typeof m.deger !== 'number') return null;
    const shown = fmtMetricValue(m);
    return el(
      'div',
      { class: 'meter-row' },
      el('span', { class: 'meter-label' }, label),
      el('meter', { min: 0.5, max: 1, value: Math.min(1, Math.max(0.5, m.deger)), 'aria-label': `${label}: ${t.olcek(shown)}` }, shown),
      el('strong', { class: 'meter-val' }, shown),
    );
  };
  let verdict = null;
  if (d && typeof d.ga95_alt === 'number' && typeof d.ga95_ust === 'number') {
    verdict = excludesZero(d) ? (d.ga95_alt > 0 ? t.anlamli : t.ters) : t.anlamsiz;
  }
  return step(
    3,
    'st-3',
    title,
    el('p', null, t.p1(fmtPlain(ozet.bilgi_zamani_saat))),
    el('p', null, t.puan, ' ', T.ortak.sozluk, sozlukLink('roc-auc'), ', ', sozlukLink('t2-modeli'), '.'),
    el('div', { class: 'meters' }, meter(t.plan, plan), meter(t.t2, t2)),
    d ? el('p', { class: 'fact' }, t.fark(fmtMetricValue(d, true), fmtInterval(d, true)), ' ', verdict) : null,
    el('p', null, el('a', { href: '#weather' }, T.bolumler.weather)),
  );
}

// ---------------------------------------------------------------------- 4. tampon kaydırıcısı
function buildStepFour(opt) {
  const t = T.hikaye.s4;
  if (!opt || !Array.isArray(opt.tau_izgarasi) || !opt.tau_izgarasi.length) {
    return step(4, 'st-4', t.baslik, el('p', { class: 'muted' }, t.yok));
  }
  const grid = sortedGrid(opt);
  const index = memory.tau !== null && memory.tau < grid.length ? memory.tau : nearestIndex(grid, 0.8);
  const summary = el('p', { class: 'fact', role: 'status', 'aria-live': 'polite' });
  const result = el('div', { class: 'stack' });
  const base = grid.find((g) => Math.abs(g.tau - 0.8) < 1e-6);

  function render(i) {
    memory.tau = i;
    const g = grid[i];
    const kat = fmtRatio(g.maliyet_orani);
    const none = rowOf(g.politikalar, 'none');
    const plan = rowOf(g.politikalar, 'plan');
    if (!plan) {
      summary.textContent = txt(t.yok);
      fill(result);
      return;
    }
    const noneRate = none ? none.arrdel15_orani : null;
    const planRate = plan.arrdel15_orani;
    summary.textContent = txt(`${t.baslikSonuc(kat)}: ${t.oranlar(fmtPct(noneRate), fmtPct(planRate))}`);
    const panels = [];
    if (typeof noneRate === 'number') panels.push(pictoPanel(t.tamponYok, noneRate, T.hikaye.s2.ikonEtiket));
    if (typeof planRate === 'number') panels.push(pictoPanel(t.planModeli, planRate, T.hikaye.s2.ikonEtiket));
    fill(
      result,
      el('div', { class: 'picto-pair' }, panels),
      el(
        'dl',
        { class: 'stat-cards' },
        [
          [t.ek, fmtMin(plan.ek_tampon_dk)],
          [t.bosa, fmtMin(plan.kullanilmayan_dk)],
          [t.kalan, fmtMin(plan.kalan_rotar_dk)],
        ].map(([term, v]) => el('div', null, el('dt', null, term), el('dd', null, v))),
      ),
    );
  }

  const slider = tauSlider({ id: 'st-tau', grid, index, showTau: false, onChange: render });
  render(index);
  return step(
    4,
    'st-4',
    t.baslik,
    el('p', null, t.p1),
    slider.element,
    summary,
    result,
    base ? el('p', { class: 'note' }, t.rotalarNotu(fmtRatio(base.maliyet_orani))) : null,
    el('div', { class: 'notice warn', role: 'note' }, el('strong', null, T.rota.uyariBaslik), T.genel.tampon.varsayim),
    el('p', null, T.ortak.sozluk, sozlukLink('maliyet-orani'), ', ', sozlukLink('blok-sure-tamponu'), '. ', el('a', { href: '#optimization' }, T.bolumler.optimization)),
  );
}

// ---------------------------------------------------------------------- 5. dürüstlük
function buildStepFive(ozet, opt) {
  const t = T.hikaye.s5;
  const k = T.genel.kabul;
  const failed = ozet.kabul.filter((x) => x.sonuc === 'kaldi');
  const items = failed.map((x) => el('li', null, t.kabulSatiri(x.olcut, kabulAciklamasi(ozet, x))));
  const details = [];
  if (failed.some((x) => x.olcut === 'K5')) {
    const p80 = metricOf(ozet, 'kantil', 'lgbm_plan', 'kapsama_p80_conf');
    const p95 = metricOf(ozet, 'kantil', 'lgbm_plan', 'kapsama_p95_conf');
    details.push(el('p', null, el('strong', null, k.k5), k.k5Metin(fmtMetricValue(p80), fmtMetricValue(p95))));
  }
  if (failed.some((x) => x.olcut === 'K6')) {
    const plan = metricOf(ozet, 'iptal', 'lgbm_plan', 'pr_auc');
    const b1 = metricOf(ozet, 'iptal', 'B1', 'pr_auc');
    details.push(el('p', null, el('strong', null, k.k6), k.k6Metin(fmtMetricValue(plan), fmtMetricValue(b1))));
  }
  const orLine = opt && Array.isArray(opt.butce_egrisi) ? equalBudgetSentence(equalBudget(opt)) : null;
  return step(
    5,
    'st-5',
    t.baslik,
    el('p', null, t.p1),
    items.length ? el('ul', { class: 'points' }, items) : el('p', null, k.ozet(ozet.kabul.length - failed.length, ozet.kabul.length, [])),
    details.length ? el('div', { class: 'notice warn stack', role: 'note' }, details) : null,
    orLine ? el('p', { class: 'notice' }, orLine, ' ', el('a', { href: '#optimization' }, T.bolumler.optimization)) : null,
    el('p', null, t.kapanis),
  );
}

// ---------------------------------------------------------------------- 6. daha fazlası
function buildStepSix() {
  const t = T.hikaye.s6;
  return step(
    6,
    'st-6',
    t.baslik,
    el('p', null, t.p1),
    el('ul', { class: 'more-links' }, MORE.map((name) => el('li', null, el('a', { href: `#${name}` }, T.bolumler[name]), el('span', { class: 'note' }, ` ${NA} ${t.acik[name]}`)))),
  );
}
