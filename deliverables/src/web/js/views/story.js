// Hikâye (açılış sayfası): yönetici sunumu. Her slayt = bulguyu söyleyen bir başlık + tek görsel + en fazla
// iki sade cümle + ilgili teknik sekmeye "Ayrıntılar" bağlantısı. Sayıların hepsi veri dosyalarından okunur
// (ozet, hata-analizi, kalibrasyon, hava-deneyi, optimizasyon, rotalar/<IATA>); metinler parametreli
// işlevlerdir (metin.js / metin-en.js). Seçimler dil değişince (görünüm yeniden çizilir) korunur.
// Elle yazılan tek değerler: "geç" tanımındaki eşik, birim grafikteki daire sayısı ve tampon şemasındaki
// örnek dakikalar (şema "örnek" diye işaretlidir).

import { el, fill, selectField, fillSelect, loadingNode } from '../dom.js';
import { loadOzet, loadHava, loadOptimizasyon, loadHata, loadKalibrasyon, loadHavalimanlari, loadManifest, loadRoutes, routeOrigins, findResult, findMetric, metricOf } from '../data.js';
import { fmtPct, fmtMin, fmtInt, fmtNum, fmtPlain, fmtRatio, blockLabel, BLOCK_ORDER, seasonLabel, SEASON_ORDER, monthLabel, safeHttpsUrl, txt } from '../fmt.js';
import { T, REPO_URL } from '../metin.js';
import { gizlemeNedeni } from '../yerel.js';
import { barChart, xyChart, legend, niceDomain, mountChart, pictograph } from '../charts.js';
import { columnChart, stackedBar, keyList, bufferDiagram } from '../story-gorseller.js';
import { rowOf, excludesZero, sortedGrid, nearestIndex, equalBudget, tauSlider } from '../or-ortak.js';
import { icon } from '../simgeler.js';

// Dil değişince görünüm yeniden kurulur; seçimler burada saklanır.
const memory = { origin: null, dest: null, block: null, season: null, tau: null };

const LATE_AFTER = 15; // "geç varış" tanımı (dakika)
const PICTO_TOTAL = 100; // birim grafikteki daire sayısı
const EXAMPLE = { flight: 100, buffer: 20, small: 12, large: 40 }; // tampon şeması: örnek dakikalar
const COIN_FLIP = 0.5;
const NEAR_ENOUGH = 0.03; // "tahmin gerçeğe yakın" demek için en büyük fark
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const count100 = (rate) => Math.round(rate * PICTO_TOTAL);

// ---------------------------------------------------------------------- yardımcılar
// Slayt başlığındaki simge (ortak simge seti; yalnızca süs, başlık metni değişmez).
const STEP_ICON = ['plane', 'clock', 'chart', 'shield', 'cloud', 'buffer', 'target', 'route', 'target', 'pin'];
const ACTION_ICON = ['shield', 'buffer', 'route'];

function step(n, id, title, ...children) {
  return el(
    'section',
    { class: 'story-step stack', 'aria-labelledby': id },
    el('h3', { id }, el('span', { class: 'step-no', 'aria-hidden': 'true' }, String(n)), icon(STEP_ICON[n - 1] || 'info', { size: 24, class: 'step-ico' }), el('span', { class: 'visually-hidden' }, `${T.hikaye.adim(n)}: `), title),
    children,
  );
}

const unavailable = (n) => step(n, `st-${n}`, T.bolumler.story, el('p', { class: 'muted' }, T.hikaye.yok));
const figure = (content, caption) => el('figure', { class: 'slide-fig' }, content, caption ? el('figcaption', null, caption) : null);
const sentence = (text) => el('p', { class: 'slide-text' }, text);
const details = (href) => el('p', { class: 'details-link' }, el('a', { href }, T.hikaye.ayrinti));

function chartBox(build, wide = true) {
  const box = el('div', { class: wide ? 'chart-box wide' : 'chart-box' });
  const handle = mountChart(box, build);
  return { box, handle };
}

/** Etiketi, dar sütunlara sığsın diye satırlara böler. */
function wrapLabel(text, max) {
  const lines = [];
  let cur = '';
  for (const word of String(text).split(' ')) {
    if (cur && `${cur} ${word}`.length > max) {
      lines.push(cur);
      cur = word;
    } else {
      cur = cur ? `${cur} ${word}` : word;
    }
  }
  if (cur) lines.push(cur);
  return lines;
}

/** Kalibrasyon dosyasından on risk grubu (en düşükten en yükseğe); yoksa null. */
function riskGroups(kal) {
  const entry = kal && Array.isArray(kal.siniflandirma) ? kal.siniflandirma.find((e) => e.gorev === 'arrdel15' && e.model === 'lgbm_T2') : null;
  if (!entry || !Array.isArray(entry.kutular)) return null;
  const bins = entry.kutular.filter((b) => isNum(b.gozlenen_oran) && isNum(b.ortalama_tahmin)).sort((a, b) => a.ortalama_tahmin - b.ortalama_tahmin);
  return bins.length >= 2 ? bins : null;
}

/** En riskli grup için "her N uçuştan K" (metin parametresi). */
function riskiest(bins) {
  const per = bins.length;
  return { n: fmtInt(per), deger: fmtInt(Math.max(1, Math.round(bins[per - 1].gozlenen_oran * per))) };
}

function pictoPanel(name, rate) {
  const t = T.hikaye;
  const x = fmtInt(count100(rate));
  const total = fmtInt(PICTO_TOTAL);
  return el(
    'figure',
    { class: 'picto-panel' },
    pictograph({ count: count100(rate), title: t.s10.ikonEtiket(name, x, total), desc: t.s1.ikonAciklama(fmtInt(LATE_AFTER)) }),
    el('figcaption', null, el('strong', null, name), el('span', { class: 'picto-count' }, t.s1.ikon(x, total)), el('span', { class: 'note' }, fmtPct(rate))),
  );
}

// ---------------------------------------------------------------------- açılış
function buildHero(ozet) {
  const t = T.hero;
  const saat = fmtPlain(ozet.bilgi_zamani_saat);
  const k = ozet.kapsam;
  const period = T.donem(monthLabel(String(ozet.bolme.test.baslangic).slice(0, 7)), monthLabel(String(ozet.bolme.test.bitis).slice(0, 7)));
  const repo = safeHttpsUrl(REPO_URL);
  const walk = () => {
    const target = document.getElementById('story-steps');
    if (!target) return;
    target.scrollIntoView();
    target.focus({ preventScroll: true });
  };
  return el(
    'section',
    { class: 'hero', 'aria-labelledby': 'hero-q' },
    el('p', { class: 'hero-q', id: 'hero-q' }, t.soru(saat)),
    el('p', { class: 'hero-ozet' }, t.ozet),
    el('p', { class: 'scope' }, t.kapsam(fmtInt(k.test_ucus_sayisi), fmtInt(k.havalimani_sayisi), period)),
    el(
      'p',
      { class: 'hero-actions' },
      el('button', { type: 'button', class: 'btn btn-primary', onclick: walk }, t.yuru),
      repo ? el('a', { class: 'btn', href: repo, rel: 'noopener' }, t.kod) : null,
    ),
  );
}

export async function mount(root) {
  const [ozet, airportsFile, manifest] = await Promise.all([loadOzet(), loadHavalimanlari(), loadManifest()]);
  // Diğer dosyalar yüklenemezse yalnızca ilgili slayt uyarı gösterir; diğerleri çalışır.
  const [hava, opt, hata, kal] = await Promise.all([loadHava().catch(() => null), loadOptimizasyon().catch(() => null), loadHata().catch(() => null), loadKalibrasyon().catch(() => null)]);

  const tenth = await buildTry(airportsFile, manifest);
  const steps = el(
    'div',
    { class: 'story-steps stack', id: 'story-steps', tabindex: '-1' },
    slideProblem(ozet),
    slideTime(hata),
    slideRisk(kal),
    slideTrust(kal),
    slideWeather(ozet, hava),
    slideBufferIdea(),
    slideTradeoff(opt),
    slideRule(opt),
    slideActions(kal, opt),
    tenth,
  );
  fill(root, buildHero(ozet), steps);
}

// ---------------------------------------------------------------------- 1. sorun
function slideProblem(ozet) {
  const t = T.hikaye.s1;
  let prevalence = null;
  for (const model of ['lgbm_T2', 'lgbm_plan', 'B1', 'B0']) {
    const m = findMetric(findResult(ozet, 'arrdel15', model), 'yayginlik');
    if (m && isNum(m.deger) && m.deger > 0) {
      prevalence = m;
      break;
    }
  }
  if (!prevalence) return unavailable(1);
  const rate = prevalence.deger;
  const x = fmtInt(count100(rate));
  const total = fmtInt(PICTO_TOTAL);
  return step(
    1,
    'st-1',
    t.baslik(fmtInt(Math.round(1 / rate))),
    figure(pictograph({ count: count100(rate), title: t.ikon(x, total), desc: t.ikonAciklama(fmtInt(LATE_AFTER)), cls: 'picto-big' }), t.ikon(x, total)),
    sentence(t.p1(fmtInt(LATE_AFTER), fmtPct(rate, 0), fmtInt(ozet.kapsam.test_ucus_sayisi))),
    details('#results'),
  );
}

// ---------------------------------------------------------------------- 2. ne zaman daha kötü
function slideTime(hata) {
  const t = T.hikaye.s2;
  const block = hata && Array.isArray(hata.boyutlar) ? hata.boyutlar.find((b) => b.boyut === 'saat_blogu' && b.model === 'lgbm_T2') : null;
  const rateOf = (s) => {
    const m = s.metrikler.find((x) => x.ad === 'yayginlik');
    return m ? m.deger : null;
  };
  const rows = block
    ? block.segmentler
        .map((s) => ({ seg: s.segment, v: rateOf(s) }))
        .filter((r) => isNum(r.v))
        .sort((a, b) => BLOCK_ORDER.indexOf(a.seg) - BLOCK_ORDER.indexOf(b.seg))
    : [];
  if (rows.length < 2) return unavailable(2);
  const hi = rows.reduce((a, b) => (b.v > a.v ? b : a));
  const lo = rows.reduce((a, b) => (b.v < a.v ? b : a));
  const ratio = lo.v > 0 ? hi.v / lo.v : 0;
  const title = ratio >= 1.5 ? t.baslik(blockLabel(hi.seg), blockLabel(lo.seg), fmtInt(Math.round(ratio))) : t.baslikDuz;

  const event = hata.boyutlar.find((b) => b.boyut === 'olay_gunu' && b.model === 'lgbm_T2');
  const pick = (name) => {
    const s = event ? event.segmentler.find((x) => x.segment === name) : null;
    return s ? rateOf(s) : null;
  };
  const eventRate = pick('olay');
  const otherRate = pick('diger');

  const items = rows.map((r) => ({ label: blockLabel(r.seg), value: r.v, text: fmtPct(r.v, 0), emph: r === hi }));
  const { box } = chartBox((width) =>
    barChart({
      width,
      labelWidth: 86,
      tickCount: width < 480 ? 2 : 4,
      items,
      tickFormat: (v) => fmtPct(v, 0),
      xLabel: t.eksen,
      title: t.grafikBaslik,
      desc: t.grafikAciklama(fmtPct(hi.v, 0), fmtPct(lo.v, 0)),
    }),
  );
  return step(
    2,
    'st-2',
    title,
    figure(box),
    sentence(t.p1(fmtInt(LATE_AFTER))),
    isNum(eventRate) && isNum(otherRate) ? el('p', { class: 'note' }, t.olay(fmtPct(eventRate, 0), fmtPct(otherRate, 0))) : null,
    details('#method/errors'),
  );
}

// ---------------------------------------------------------------------- 3. model önceden görebiliyor mu
function slideRisk(kal) {
  const t = T.hikaye.s3;
  const bins = riskGroups(kal);
  if (!bins) return unavailable(3);
  const per = bins.length;
  const low = bins[0].gozlenen_oran;
  const lowFew = low < 1 / per;
  const lowText = { n: fmtInt(per), deger: fmtInt(Math.max(1, Math.round(low * per))) };
  const title = lowFew ? t.baslikAz(riskiest(bins), lowText) : t.baslik(riskiest(bins), lowText);
  const items = bins.map((b, i) => ({ label: fmtInt(i + 1), values: [{ value: b.gozlenen_oran, text: fmtPct(b.gozlenen_oran, 0) }] }));
  const { box } = chartBox((width) =>
    columnChart({
      width,
      items,
      showValues: true,
      yFormat: (v) => fmtPct(v, 0),
      tickCount: width < 480 ? 3 : 4,
      xLabel: t.eksen(fmtInt(1), fmtInt(per)),
      title: t.grafikBaslik,
      desc: t.grafikAciklama(fmtPct(low, 0), fmtPct(bins[per - 1].gozlenen_oran, 0)),
    }),
  );
  return step(3, 'st-3', title, figure(box), sentence(t.p1), details('#method/calibration'));
}

// ---------------------------------------------------------------------- 4. sayılara güvenilir mi
function slideTrust(kal) {
  const t = T.hikaye.s4;
  const bins = riskGroups(kal);
  if (!bins) return unavailable(4);
  const per = bins.length;
  const maxGap = Math.max(...bins.map((b) => Math.abs(b.ortalama_tahmin - b.gozlenen_oran)));
  const points = fmtInt(Math.ceil(maxGap * 100 - 1e-9));
  // Başlıktaki örnek: tahmini yüzde 30'a en yakın grup.
  const sample = bins.reduce((a, b) => (Math.abs(b.ortalama_tahmin - 0.3) < Math.abs(a.ortalama_tahmin - 0.3) ? b : a));
  const title = maxGap <= NEAR_ENOUGH ? t.baslik(fmtPct(sample.ortalama_tahmin, 0), fmtPct(sample.gozlenen_oran, 0)) : t.baslikGenel(points);
  const items = bins.map((b, i) => ({
    label: fmtInt(i + 1),
    values: [
      { value: b.ortalama_tahmin, variant: 'hollow', text: `${t.model}: ${fmtPct(b.ortalama_tahmin, 0)}` },
      { value: b.gozlenen_oran, text: `${t.gercek}: ${fmtPct(b.gozlenen_oran, 0)}` },
    ],
  }));
  const { box } = chartBox((width) =>
    columnChart({
      width,
      items,
      yFormat: (v) => fmtPct(v, 0),
      tickCount: width < 480 ? 3 : 4,
      xLabel: t.eksen(fmtInt(1), fmtInt(per)),
      title: t.grafikBaslik,
      desc: t.grafikAciklama(points),
    }),
  );
  return step(
    4,
    'st-4',
    title,
    figure(box, null),
    keyList([
      { cls: 'pred', label: t.model },
      { cls: 'col', label: t.gercek },
    ]),
    sentence(t.p1(points)),
    details('#method/calibration'),
  );
}

// ---------------------------------------------------------------------- 5. hava bilgisi
function slideWeather(ozet, hava) {
  const t = T.hikaye.s5;
  const score = (model) => {
    const m = metricOf(ozet, 'arrdel15', model, 'roc_auc');
    return m && isNum(m.deger) ? m.deger : null;
  };
  const b1 = score('B1');
  const plan = score('lgbm_plan');
  const t2 = score('lgbm_T2');
  if (plan === null || t2 === null) return unavailable(5);
  const gap = hava && Array.isArray(hava.farklar) ? hava.farklar.find((f) => f.karsilastirma === 'T2-plan' && f.metrik.ad === 'roc_auc') : null;
  const better = gap ? excludesZero(gap.metrik) && gap.metrik.ga95_alt > 0 : t2 > plan;
  const saat = fmtPlain(ozet.bilgi_zamani_saat);
  const shown = (v) => (v === null ? txt(null) : fmtNum(v, 2));
  const labels = [t.gecmis, t.tarife, t.hava(saat)];
  const values = [b1, plan, t2];
  const { box } = chartBox((width) => {
    const narrow = width < 480;
    return barChart({
      width,
      rowH: 38,
      labelWidth: narrow ? 112 : 150,
      tickCount: narrow ? 2 : 4,
      base: COIN_FLIP,
      items: labels.map((label, i) => ({ label: wrapLabel(label, narrow ? 17 : 23), value: values[i], text: shown(values[i]), emph: i === 2 })),
      tickFormat: (v) => fmtNum(v, 2),
      xLabel: t.eksen(fmtNum(COIN_FLIP, 1)),
      title: t.grafikBaslik,
      desc: t.grafikAciklama(shown(b1), shown(plan), shown(t2)),
    });
  });
  const text = better ? t.p1(saat, fmtNum(plan, 3), fmtNum(t2, 3)) : t.p1Notr(saat, fmtNum(plan, 3), fmtNum(t2, 3));
  return step(5, 'st-5', better ? t.baslik : t.baslikNotr, figure(box), sentence(text), details('#method/weather'));
}

// ---------------------------------------------------------------------- 6. tampon nedir (şema)
function slideBufferIdea() {
  const t = T.hikaye.s6;
  const { box } = chartBox((width) =>
    bufferDiagram({
      width,
      minutes: EXAMPLE,
      text: { scheduled: t.planlanan, row1: t.satir1, row2: t.satir2, row3: t.satir3, title: t.grafikBaslik, desc: t.grafikAciklama },
    }),
  );
  const m = (v) => fmtMin(v, 0);
  return step(
    6,
    'st-6',
    t.baslik,
    figure(box, t.ornek),
    keyList([
      { cls: 'flight', label: t.anahtar(t.ucus, m(EXAMPLE.flight)) },
      { cls: 'buffer', pattern: true, hatch: 'hatch-a', label: t.anahtar(t.tampon, m(EXAMPLE.buffer)) },
      { cls: 'delay', label: t.gecikme },
      { cls: 'over', label: t.asan },
    ]),
    sentence(t.p1),
    details('#buffers'),
  );
}

// ---------------------------------------------------------------------- 7. tampon ne kazandırır, ne kaybettirir
function slideTradeoff(opt) {
  const t = T.hikaye.s7;
  if (!opt || !Array.isArray(opt.tau_izgarasi) || !opt.tau_izgarasi.length) return unavailable(7);
  const grid = sortedGrid(opt);
  const rows = grid.map((g) => ({ ratio: g.maliyet_orani, none: rowOf(g.politikalar, 'none'), plan: rowOf(g.politikalar, 'plan') }));
  if (!rows.every((r) => r.plan && isNum(r.plan.arrdel15_orani) && isNum(r.plan.kullanilmayan_dk))) return unavailable(7);
  let index = memory.tau !== null && memory.tau < grid.length ? memory.tau : nearestIndex(grid, 0.8);
  const n = rows.length;

  function panel(width, key, name, yFormat, reference) {
    const pts = rows.map((r, i) => ({ x: i, y: r.plan[key], label: yFormat(r.plan[key]) }));
    const ys = pts.map((p) => p.y).concat(isNum(reference) ? [reference] : []);
    const yd = niceDomain(0, Math.max(...ys), 4);
    const every = Math.max(1, Math.ceil(n / (width < 480 ? 4 : 8)));
    const ticks = [];
    rows.forEach((r, i) => {
      if (i % every === 0 || (i === n - 1 && (n - 1) % every > every / 2)) ticks.push({ v: i, label: fmtRatio(r.ratio) });
    });
    return xyChart({
      width,
      height: 230,
      xDomain: [0, Math.max(1, n - 1)],
      yDomain: [yd.lo, yd.hi],
      xTicks: ticks,
      yTicks: yd.ticks,
      xFormat: (v) => fmtRatio(v),
      yFormat,
      xLabel: t.eksenX,
      yLabel: name,
      hlines: isNum(reference) ? [{ y: reference, label: t.tamponYok }] : [],
      series: [
        { name, cls: 'ser-a', marker: 'circle', points: pts },
        { name: t.secili, cls: 'ser-b', marker: 'diamond', points: [pts[index]] },
      ],
      title: key === 'arrdel15_orani' ? t.gecBaslik : t.bosBaslik,
      desc: t.grafikAciklama(name, yFormat(pts[0].y), yFormat(pts[n - 1].y)),
    });
  }

  const noneRate = rows.find((r) => r.none && isNum(r.none.arrdel15_orani));
  const reference = noneRate ? noneRate.none.arrdel15_orani : null;
  const lateChart = chartBox((w) => panel(w, 'arrdel15_orani', t.gecPanel, (v) => fmtPct(v, 0), reference), false);
  const idleChart = chartBox((w) => panel(w, 'kullanilmayan_dk', t.bosPanel, (v) => fmtMin(v, 0), null), false);

  const summary = el('p', { class: 'fact', role: 'status', 'aria-live': 'polite' });
  const stackBox = el('div', { class: 'chart-box wide' });
  let stack = null;

  function share() {
    const r = rows[index];
    const late = r.plan.arrdel15_orani;
    const base = r.none && isNum(r.none.arrdel15_orani) ? r.none.arrdel15_orani : null;
    if (base === null) return null;
    return { ok: Math.max(0, 1 - base), saved: Math.max(0, base - late), late };
  }

  function render() {
    memory.tau = index;
    const r = rows[index];
    const s = share();
    if (s) {
      summary.textContent = txt(t.ozet(fmtMin(r.plan.ek_tampon_dk, 0), fmtPct(r.none.arrdel15_orani, 0), fmtPct(r.plan.arrdel15_orani, 0), fmtMin(r.plan.kullanilmayan_dk, 0)));
      if (stack) stack.redraw();
      else stack = mountChart(stackBox, (width) => {
        const cur = share();
        return stackedBar({
          width,
          segments: [
            { value: cur.ok, text: fmtPct(cur.ok, 0), cls: 'ok' },
            { value: cur.saved, text: fmtPct(cur.saved, 0), cls: 'saved', pattern: true },
            { value: cur.late, text: fmtPct(cur.late, 0), cls: 'late' },
          ],
          title: t.yiginBaslik,
          desc: t.yiginAciklama(fmtPct(cur.ok, 0), fmtPct(cur.saved, 0), fmtPct(cur.late, 0)),
        });
      });
    } else {
      summary.textContent = txt('');
    }
    lateChart.handle.redraw();
    idleChart.handle.redraw();
  }

  const slider = tauSlider({
    id: 'st-tau',
    grid,
    index,
    showTau: false,
    onChange: (i) => {
      index = i;
      render();
    },
  });
  render();
  return step(
    7,
    'st-7',
    t.baslik,
    sentence(t.p1),
    el('div', { class: 'panel-pair' }, figure(lateChart.box, t.gecPanel), figure(idleChart.box, t.bosPanel)),
    legend([{ name: t.secili, cls: 'ser-b', marker: 'diamond' }]),
    slider.element,
    summary,
    figure(stackBox),
    keyList([
      { cls: 'ok', label: t.zaten },
      { cls: 'saved', pattern: true, hatch: 'hatch-d', label: t.sayesinde },
      { cls: 'late', label: t.yineGec },
    ]),
    el('p', { class: 'note', role: 'note' }, T.tamponUyari),
    details('#buffers'),
  );
}

// ---------------------------------------------------------------------- 8. basit kural ve model
function slideRule(opt) {
  const t = T.hikaye.s8;
  if (!opt || !Array.isArray(opt.butce_egrisi) || !opt.butce_egrisi.length) return unavailable(8);
  const eb = equalBudget(opt);
  const same = eb.total > 0 && eb.significant === 0;
  const title = !eb.total ? T.bolumler.buffers : same ? t.baslikEsit : t.baslikFark(fmtInt(eb.significant), fmtInt(eb.total));
  const text = same ? t.p1Esit : t.p1Fark;
  const curve = [...opt.butce_egrisi].sort((a, b) => a.butce_dk - b.butce_dk);
  const defs = [
    { id: 'plan_budget', name: t.model, cls: 'ser-a', marker: 'circle', hollow: false, dash: false },
    { id: 'b1_budget', name: t.kural, cls: 'ser-b', marker: 'diamond', hollow: true, dash: true },
  ];
  const list = defs
    .map((d) => ({
      ...d,
      points: curve
        .map((b) => ({ x: b.butce_dk, row: rowOf(b.politikalar, d.id) }))
        .filter((p) => p.row && isNum(p.row.arrdel15_orani))
        .map((p) => ({ x: p.x, y: p.row.arrdel15_orani, label: fmtPct(p.row.arrdel15_orani, 1) })),
    }))
    .filter((s) => s.points.length);
  if (!list.length) return step(8, 'st-8', title, sentence(text), details('#buffers'));
  const xs = curve.map((b) => b.butce_dk);
  const ys = list.flatMap((s) => s.points.map((p) => p.y));
  const names = list.map((s) => s.name).join(', ');
  const { box } = chartBox((width) => {
    const xd = niceDomain(Math.min(...xs), Math.max(...xs), width < 480 ? 3 : 5);
    const yd = niceDomain(0, Math.max(...ys), 4);
    return xyChart({
      width,
      height: 250,
      xDomain: [xd.lo, xd.hi],
      yDomain: [yd.lo, yd.hi],
      xTicks: xd.ticks,
      yTicks: yd.ticks,
      xFormat: (v) => fmtPlain(v),
      yFormat: (v) => fmtPct(v, 0),
      xLabel: t.eksenX,
      yLabel: t.eksenY,
      series: list.map((s) => ({ name: s.name, cls: s.cls, marker: s.marker, hollow: s.hollow, dash: s.dash, points: s.points })),
      title: t.grafikBaslik,
      desc: t.grafikAciklama(names),
    });
  });
  return step(8, 'st-8', title, figure(box), legend(list), sentence(text), details('#buffers'));
}

// ---------------------------------------------------------------------- 9. ne yapmalı
function slideActions(kal, opt) {
  const t = T.hikaye.s9;
  const cards = [];
  const bins = riskGroups(kal);
  if (bins) cards.push([t.gun.baslik, t.gun.metin(riskiest(bins))]);
  if (opt && Array.isArray(opt.tau_izgarasi) && opt.tau_izgarasi.length) {
    const grid = sortedGrid(opt);
    const base = grid[nearestIndex(grid, 0.8)];
    const none = rowOf(base.politikalar, 'none');
    const plan = rowOf(base.politikalar, 'plan');
    if (none && plan) {
      const eb = equalBudget(opt);
      const same = eb.total > 0 && eb.significant === 0;
      cards.push([same ? t.tampon.baslikEsit : t.tampon.baslikFark, t.tampon.metin(fmtMin(plan.ek_tampon_dk, 0), fmtPct(none.arrdel15_orani, 0), fmtPct(plan.arrdel15_orani, 0), fmtMin(plan.kullanilmayan_dk, 0))]);
    }
  }
  cards.push([t.sonraki.baslik, t.sonraki.metin]);
  return step(
    9,
    'st-9',
    t.baslik,
    el('figure', { class: 'slide-fig', role: 'group', 'aria-label': t.kartlar }, el('ul', { class: 'action-cards' }, cards.map(([head, body], i) => el('li', { class: 'action' }, el('h4', { class: 'with-ico' }, icon(ACTION_ICON[i] || 'info'), el('span', null, head)), el('p', null, body))))),
    el('p', { class: 'details-link' }, el('a', { href: '#results' }, t.sinirlar)),
  );
}

// ---------------------------------------------------------------------- 10. kendiniz deneyin
async function buildTry(airportsFile, manifest) {
  const t = T.hikaye.s10;
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
      el('div', { class: 'picto-pair' }, pictoPanel(t.gerceklesen, obs), pictoPanel(t.modelTahmini, pred)),
      el('p', { class: 'note' }, t.ikonAnahtar(fmtInt(LATE_AFTER))),
      el('p', { class: 'fact', role: 'status' }, t.cumle(fmtInt(count100(obs)), fmtInt(count100(pred)), fmtInt(PICTO_TOTAL), fmtInt(cell.n_ucus))),
      el('h4', null, t.rotarBaslik),
      el('p', null, p50 < 0 ? t.rotarCumle(fmtMin(-p50), fmtMin(p80), fmtMin(p95), true) : t.rotarCumle(fmtMin(p50), fmtMin(p80), fmtMin(p95), false)),
      delayBox,
      el('p', null, el('a', { href: `#explore/${sel.origin}` }, T.havalimani.rotalariGoster(sel.origin))),
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
    10,
    'st-10',
    t.baslik,
    sentence(t.p1),
    el('form', { class: 'controls', onsubmit: (e) => e.preventDefault(), 'aria-label': t.secim }, originField.wrap, destField.wrap, blockField.wrap, seasonField.wrap),
    airportNote,
    out,
  );
  await loadOrigin();
  return section;
}
