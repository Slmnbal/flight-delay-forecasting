// Harita açıklaması (lejant) parçaları: renk şeridi, nokta boyutu, yay kalınlığı ve yayımlanmayan nokta.
// Keşfet haritası (views/airports.js) ve sunumdaki harita slaydı aynı parçaları kullanır; renk skalası
// (RISK_EDGES) ve boyut işlevleri haritayla aynıdır, böylece açıklama çizimle her zaman tutarlı kalır.

import { el, svg } from './dom.js';
import { T } from './metin.js';
import { fmtPct, fmtInt } from './fmt.js';
import { RISK_EDGES, arcWidth } from './kesfet-hesap.js';
import { dotRadius, arcRange } from './map.js';

export function edgeLabels(e) {
  const p = (v) => fmtPct(v, 0);
  return [`< ${p(e[0])}`, `${p(e[0])}–${p(e[1])}`, `${p(e[1])}–${p(e[2])}`, `${p(e[2])}–${p(e[3])}`, `≥ ${p(e[3])}`];
}

/** Beş basamaklı renk şeridi; her basamağın altında sınır etiketi (renge bağımlı değil). */
export function strip(labels) {
  return el(
    'ol',
    { class: 'risk-strip' },
    labels.map((text, i) => el('li', null, el('span', { class: `sw r${i + 1}`, 'aria-hidden': 'true' }), el('span', { class: 'sw-label' }, text))),
  );
}

export const riskStrip = () => strip(edgeLabels(RISK_EDGES));

export function sizeKey(airports, compact) {
  const t = T.havalimani;
  const counts = airports.map((a) => a.n_test_ucus);
  const maxN = Math.max(...counts, 1);
  const minN = Math.min(...counts);
  const rBig = dotRadius(maxN, maxN, compact);
  const rSmall = dotRadius(minN, maxN, compact);
  const w = Math.round(2 * rBig + 2 * rSmall + 14);
  const h = Math.round(2 * rBig + 4);
  const sample = svg(
    'svg',
    { class: 'legend-svg', width: w, height: h, viewBox: `0 0 ${w} ${h}`, 'aria-hidden': 'true', focusable: 'false' },
    svg('circle', { class: 'dot r3', cx: rSmall + 2, cy: h / 2, r: rSmall }),
    svg('circle', { class: 'dot r3', cx: 2 * rSmall + 10 + rBig, cy: h / 2, r: rBig }),
  );
  return el('div', { class: 'legend-row' }, sample, el('span', null, t.lejantBoyut(fmtInt(minN), fmtInt(maxN))));
}

export function hiddenKey(airports) {
  if (!airports.some((a) => a.gizleme_nedeni)) return null;
  const sample = svg(
    'svg',
    { class: 'legend-svg', width: 20, height: 20, viewBox: '0 0 20 20', 'aria-hidden': 'true', focusable: 'false' },
    svg('g', { class: 'pt hidden-pt' }, svg('circle', { class: 'dot', cx: 10, cy: 10, r: 7 })),
  );
  return el('div', { class: 'legend-row' }, sample, el('span', null, T.havalimani.lejantYok));
}

/**
 * Yay anahtarı: kalınlık = rotadaki uçuş sayısı. sameScale doğruysa renk notu, değilse geç varış renk şeridi.
 * items: [{n}] (çizilen yaylar); boşsa null.
 */
export function arcKey(items, compact, sameScale, scaleTitle) {
  const t = T.havalimani;
  if (!items || !items.length) return null;
  const counts = items.map((i) => i.n);
  const maxN = Math.max(...counts);
  const minN = Math.min(...counts);
  const [lo, hi] = arcRange(compact);
  const wMin = arcWidth(minN, maxN, lo, hi);
  const wMax = arcWidth(maxN, maxN, lo, hi);
  const sample = svg(
    'svg',
    { class: 'legend-svg', width: 64, height: 22, viewBox: '0 0 64 22', 'aria-hidden': 'true', focusable: 'false' },
    svg('path', { class: 'arc-case', d: 'M2 16Q16 3 30 16', 'stroke-width': (wMin + 3).toFixed(1) }),
    svg('path', { class: 'arc-line rs3', d: 'M2 16Q16 3 30 16', 'stroke-width': wMin.toFixed(1) }),
    svg('path', { class: 'arc-case', d: 'M34 16Q48 3 62 16', 'stroke-width': (wMax + 3).toFixed(1) }),
    svg('path', { class: 'arc-line rs3', d: 'M34 16Q48 3 62 16', 'stroke-width': wMax.toFixed(1) }),
  );
  return el(
    'div',
    { class: 'legend-group' },
    el('div', { class: 'legend-row' }, sample, el('span', null, t.lejantYay(fmtInt(minN), fmtInt(maxN)))),
    sameScale ? el('p', { class: 'note' }, t.lejantYayRenk) : el('div', { class: 'legend-row legend-col' }, el('span', { class: 'legend-title' }, t.lejantBaslik(scaleTitle)), riskStrip()),
  );
}
