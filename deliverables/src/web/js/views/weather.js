// Hava deneyi: plan (yalnızca tarife) ile T2 (kalkıştan önce gözlenen hava eklenir) karşılaştırması.

import { el, svg, fill, sozlukLink } from '../dom.js';
import { loadHava } from '../data.js';
import { fmtMetricValue, fmtInterval, metricLabel, betterLabel, NA, txt } from '../fmt.js';
import { T } from '../metin.js';

const t = T.hava;

/** Kendi ölçeğinde, sıfır merkezli küçük aralık grafiği. */
function intervalPlot(m) {
  const w = 150;
  const h = 22;
  if (m.ga95_alt === null || m.ga95_alt === undefined || m.ga95_ust === null || m.ga95_ust === undefined) return NA;
  const bound = Math.max(Math.abs(m.ga95_alt), Math.abs(m.ga95_ust), Math.abs(m.deger)) * 1.15 || 1;
  const x = (v) => w / 2 + (v / bound) * (w / 2 - 6);
  return svg(
    'svg',
    { class: 'chart mini', width: w, height: h, viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': t.miniEtiket(fmtMetricValue(m, true), fmtInterval(m, true)), focusable: 'false' },
    svg('line', { class: 'ref', x1: x(0), x2: x(0), y1: 2, y2: h - 2 }),
    svg('line', { class: 'axis', x1: x(m.ga95_alt), x2: x(m.ga95_ust), y1: h / 2, y2: h / 2 }),
    svg('circle', { class: 'bar', cx: x(m.deger), cy: h / 2, r: 4 }),
  );
}

export async function mount(root) {
  const hava = await loadHava();

  const variants = hava.varyantlar;
  const metricNames = [...new Set(variants.flatMap((v) => v.metrikler.map((m) => m.ad)))];

  const variantTable = el(
    'div',
    { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': t.degerAriaEtiket },
    el(
      'table',
      { class: 'data' },
      el('caption', null, t.degerCaption),
      el('thead', null, el('tr', null, el('th', { scope: 'col' }, t.olcut), el('th', { scope: 'col' }, t.dahaIyi), variants.map((v) => el('th', { scope: 'col', class: 'num' }, t.varyant[v.varyant] || txt(v.varyant))))),
      el(
        'tbody',
        null,
        metricNames.map((name) =>
          el(
            'tr',
            null,
            el('th', { scope: 'row' }, metricLabel(name)),
            el('td', null, betterLabel(name)),
            variants.map((v) => el('td', { class: 'num' }, fmtMetricValue(v.metrikler.find((m) => m.ad === name) || null))),
          ),
        ),
      ),
    ),
  );

  const diffTable = el(
    'div',
    { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': t.farkAriaEtiket },
    el(
      'table',
      { class: 'data' },
      el('caption', null, t.farkCaption),
      el(
        'thead',
        null,
        el(
          'tr',
          null,
          [t.karsilastirmaBaslik, t.olcut, t.dahaIyi].map((h) => el('th', { scope: 'col' }, h)),
          [t.fark, t.aralik].map((h) => el('th', { scope: 'col', class: 'num' }, h)),
          el('th', { scope: 'col' }, t.aralikGrafik),
          el('th', { scope: 'col' }, t.sifiriDislar),
        ),
      ),
      el(
        'tbody',
        null,
        hava.farklar.map((f) => {
          const m = f.metrik;
          const hasCi = m.ga95_alt !== null && m.ga95_alt !== undefined && m.ga95_ust !== null && m.ga95_ust !== undefined;
          const excludes = hasCi ? (m.ga95_alt > 0 || m.ga95_ust < 0 ? T.ortak.evet : T.ortak.hayir) : NA;
          return el(
            'tr',
            null,
            el('th', { scope: 'row' }, t.karsilastirma[f.karsilastirma] || txt(f.karsilastirma)),
            el('td', null, metricLabel(m.ad)),
            el('td', null, betterLabel(m.ad)),
            el('td', { class: 'num' }, fmtMetricValue(m, true)),
            el('td', { class: 'num' }, fmtInterval(m, true)),
            el('td', null, intervalPlot(m)),
            el('td', null, excludes),
          );
        }),
      ),
    ),
  );

  const hasOracle = variants.some((v) => v.varyant === 'oracle');

  fill(
    root,
    el('p', null, t.giris, ' ', T.ortak.sozluk, sozlukLink('plan-modeli', 'Plan modeli'), ', ', sozlukLink('t2-modeli', 'T2 modeli'), ', ', sozlukLink('metar', 'METAR'), '.'),
    el('ul', { class: 'points' }, variants.map((v) => el('li', null, el('strong', null, `${t.varyant[v.varyant] || txt(v.varyant)}: `), v.etiket))),
    el('section', { class: 'stack', 'aria-labelledby': 'wx-values' }, el('h3', { id: 'wx-values' }, t.degerBaslik), variantTable),
    el('section', { class: 'stack', 'aria-labelledby': 'wx-diff' }, el('h3', { id: 'wx-diff' }, t.farkBaslik), diffTable, el('p', { class: 'note' }, t.farkNotu)),
    el('div', { class: 'notice' }, el('p', null, hasOracle ? t.oracleVar : t.oracleYok), el('p', { class: 'note' }, t.notlarYonlendirme)),
  );
}
