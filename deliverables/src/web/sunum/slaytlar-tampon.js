// Sunum slaytları: tampon (şema, kazanç ve maliyet, eşit bütçe) ve öneriler. Sayılar optimizasyon.json,
// ozet.json ve kalibrasyon.json dosyalarından okunur; tampon şemasındaki dakikalar "örnek" diye işaretlidir.
// Tamponun gösterildiği her yerde varsayım uyarısı (T.tamponUyari) vardır.

import { el, fill } from '../js/dom.js';
import { fmtPct, fmtMin, fmtInt, fmtPlain, fmtRatio, txt } from '../js/fmt.js';
import { T } from '../js/metin.js';
import { icon } from '../js/simgeler.js';
import { xyChart, legend, niceDomain, mountChart } from '../js/charts.js';
import { stackedBar, keyList, bufferDiagram } from '../js/story-gorseller.js';
import { rowOf, sortedGrid, nearestIndex, equalBudget, tauSlider } from '../js/or-ortak.js';
import { metricOf } from '../js/data.js';
import { isNum, chartBox, riskGroups, riskiest, figure } from '../js/hikaye-ortak.js';
import { slide, unavailable } from './slayt.js';

const EXAMPLE = { flight: 100, buffer: 20, small: 12, large: 40 }; // tampon şeması: örnek dakikalar
const TARGET = { p80: 0.8, p95: 0.95 }; // kapsama hedefleri (P80, P95 tanımı gereği)
const memory = { tau: null };

const warning = () => el('p', { class: 'note', role: 'note' }, T.tamponUyari);

// ---------------------------------------------------------------------- 7. tampon nedir
export function slideBufferIdea() {
  const t = T.hikaye.s6;
  const p = T.sunum.s7;
  const { box } = chartBox((width) =>
    bufferDiagram({
      width,
      minutes: EXAMPLE,
      text: { scheduled: t.planlanan, row1: t.satir1, row2: t.satir2, row3: t.satir3, title: t.grafikBaslik, desc: t.grafikAciklama },
    }),
  );
  const m = (v) => fmtMin(v, 0);
  const keys = [
    { label: `${p.ucus} (${p.ornek})`, value: m(EXAMPLE.flight) },
    { label: p.tampon, value: m(EXAMPLE.buffer) },
    { label: p.kucuk, value: m(EXAMPLE.small) },
    { label: p.buyuk, value: m(EXAMPLE.large) },
  ];
  return slide({
    n: 7,
    ico: 'buffer',
    title: t.baslik,
    figure: [
      figure(box, t.ornek),
      keyList([
        { cls: 'flight', label: t.anahtar(t.ucus, m(EXAMPLE.flight)) },
        { cls: 'buffer', pattern: true, hatch: 'hatch-a', label: t.anahtar(t.tampon, m(EXAMPLE.buffer)) },
        { cls: 'delay', label: t.gecikme },
        { cls: 'over', label: t.asan },
      ]),
    ],
    keys,
    how: p.nasil,
    means: t.p1,
    extra: warning(),
    href: '../#buffers',
  });
}

// ---------------------------------------------------------------------- 8. tampon ne kazandırır, neye mal olur
export function slideTradeoff(ctx) {
  const { opt } = ctx;
  const t = T.hikaye.s7;
  const p = T.sunum.s8;
  if (!opt || !Array.isArray(opt.tau_izgarasi) || !opt.tau_izgarasi.length) return unavailable(8);
  const grid = sortedGrid(opt);
  const rows = grid.map((g) => ({ ratio: g.maliyet_orani, none: rowOf(g.politikalar, 'none'), plan: rowOf(g.politikalar, 'plan') }));
  if (!rows.every((r) => r.plan && isNum(r.plan.arrdel15_orani) && isNum(r.plan.kullanilmayan_dk))) return unavailable(8);
  let index = memory.tau !== null && memory.tau < grid.length ? memory.tau : nearestIndex(grid, 0.8);
  const n = rows.length;

  function panel(width, key, name, yFormat, reference) {
    const pts = rows.map((r, i) => ({ x: i, y: r.plan[key], label: yFormat(r.plan[key]) }));
    const ys = pts.map((q) => q.y).concat(isNum(reference) ? [reference] : []);
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
  let sl = null;

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
      fill(summary, txt(t.ozet(fmtMin(r.plan.ek_tampon_dk, 0), fmtPct(r.none.arrdel15_orani, 0), fmtPct(r.plan.arrdel15_orani, 0), fmtMin(r.plan.kullanilmayan_dk, 0))));
      if (sl) {
        sl.setKeys([
          { label: p.ek, value: fmtMin(r.plan.ek_tampon_dk, 0) },
          { label: p.gec, value: p.gecDeger(fmtPct(r.none.arrdel15_orani, 0), fmtPct(r.plan.arrdel15_orani, 0)) },
          { label: p.bos, value: fmtMin(r.plan.kullanilmayan_dk, 0) },
        ]);
      }
      if (stack) stack.redraw();
      else {
        stack = mountChart(stackBox, (width) => {
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
      }
    } else {
      fill(summary, txt(''));
    }
    lateChart.handle.redraw();
    idleChart.handle.redraw();
  }

  const slider = tauSlider({
    id: 'sl-tau',
    grid,
    index,
    showTau: false,
    onChange: (i) => {
      index = i;
      render();
    },
  });
  sl = slide({
    n: 8,
    ico: 'chart',
    title: t.baslik,
    cls: 'slide-dense',
    figure: [
      slider.element,
      el('div', { class: 'panel-pair' }, figure(lateChart.box, t.gecPanel), figure(idleChart.box, t.bosPanel)),
      legend([{ name: t.secili, cls: 'ser-b', marker: 'diamond' }]),
      summary,
      figure(stackBox),
      keyList([
        { cls: 'ok', label: t.zaten },
        { cls: 'saved', pattern: true, hatch: 'hatch-d', label: t.sayesinde },
        { cls: 'late', label: t.yineGec },
      ]),
    ],
    keys: null,
    how: p.nasil,
    means: p.anlam,
    extra: warning(),
    href: '../#buffers',
  });
  render();
  return sl;
}

// ---------------------------------------------------------------------- 9. basit kural yeterli
export function slideRule(ctx) {
  const { opt } = ctx;
  const t = T.hikaye.s8;
  const p = T.sunum.s9;
  if (!opt || !Array.isArray(opt.butce_egrisi) || !opt.butce_egrisi.length) return unavailable(9);
  const eb = equalBudget(opt);
  const same = eb.total > 0 && eb.significant === 0;
  const title = !eb.total ? T.bolumler.buffers : same ? t.baslikEsit : t.baslikFark(fmtInt(eb.significant), fmtInt(eb.total));
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
        .filter((q) => q.row && isNum(q.row.arrdel15_orani))
        .map((q) => ({ x: q.x, y: q.row.arrdel15_orani, label: fmtPct(q.row.arrdel15_orani, 1) })),
    }))
    .filter((s) => s.points.length);
  if (!list.length) return slide({ n: 9, ico: 'target', title, figure: el('p', { class: 'muted' }, T.hikaye.yok), means: same ? t.p1Esit : t.p1Fark, href: '../#buffers' });
  const xs = curve.map((b) => b.butce_dk);
  const ys = list.flatMap((s) => s.points.map((q) => q.y));
  const names = list.map((s) => s.name).join(', ');
  const { box } = chartBox((width) => {
    const xd = niceDomain(Math.min(...xs), Math.max(...xs), width < 480 ? 3 : 5);
    const yd = niceDomain(0, Math.max(...ys), 4);
    return xyChart({
      width,
      height: 300,
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
  const keys = [];
  if (eb.total) {
    keys.push({ label: p.butce, value: fmtInt(eb.total) }, { label: p.belirgin, value: fmtInt(eb.significant) });
  }
  const last = (id) => {
    const pts = list.find((s) => s.id === id);
    return pts ? pts.points[pts.points.length - 1] : null;
  };
  const lastModel = last('plan_budget');
  const lastRule = last('b1_budget');
  if (lastModel && lastRule) keys.push({ label: p.enBuyuk, value: p.enBuyukDeger(fmtPct(lastModel.y, 1), fmtPct(lastRule.y, 1)) });
  return slide({ n: 9, ico: 'target', title, figure: [figure(box), legend(list)], keys, how: p.nasil, means: same ? t.p1Esit : t.p1Fark, extra: warning(), href: '../#buffers' });
}

// ---------------------------------------------------------------------- 10. öneriler ve neler işe yaramadı
export function slideActions(ctx) {
  const { kal, opt, ozet } = ctx;
  const t = T.hikaye.s9;
  const p = T.sunum.s10;
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
  const icons = ['shield', 'buffer', 'route'];

  // Neler işe yaramadı: geçmeyen kabul ölçütleri (K5, K6) sade dille; sayılar veriden.
  const failed = new Set((ozet.kabul || []).filter((x) => x.sonuc === 'kaldi').map((x) => x.olcut));
  const lines = [];
  if (failed.has('K5')) {
    const p80 = metricOf(ozet, 'kantil', 'lgbm_plan', 'kapsama_p80_conf');
    const p95 = metricOf(ozet, 'kantil', 'lgbm_plan', 'kapsama_p95_conf');
    if (p80 && p95 && isNum(p80.deger) && isNum(p95.deger)) lines.push(p.k5(fmtPct(TARGET.p80, 0), fmtPct(TARGET.p95, 0), fmtPct(p80.deger, 0), fmtPct(p95.deger, 0)));
  }
  if (failed.has('K6')) {
    const plan = metricOf(ozet, 'iptal', 'lgbm_plan', 'pr_auc');
    const b1 = metricOf(ozet, 'iptal', 'B1', 'pr_auc');
    if (plan && b1 && isNum(plan.deger) && isNum(b1.deger)) lines.push(p.k6(fmtPct(plan.deger, 0), fmtPct(b1.deger, 0)));
  }
  const failedBox = lines.length
    ? el('section', { class: 'pn-failed notice warn', 'aria-labelledby': 'sl-failed' }, el('h3', { id: 'sl-failed', class: 'with-ico' }, icon('alert'), el('span', null, p.kaldi)), el('ul', null, lines.map((l) => el('li', null, l))))
    : null;

  return slide({
    n: 10,
    ico: 'route',
    title: t.baslik,
    figure: el(
      'figure',
      { class: 'slide-fig', role: 'group', 'aria-label': t.kartlar },
      el('ul', { class: 'action-cards' }, cards.map(([head, body], i) => el('li', { class: 'action' }, el('h4', { class: 'with-ico' }, icon(icons[i] || 'info'), el('span', null, head)), el('p', null, body)))),
    ),
    keys: null,
    means: p.anlam,
    extra: [failedBox, warning()],
    href: '../#results',
  });
}
