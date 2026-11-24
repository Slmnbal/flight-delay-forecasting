// Hikâye sekmesine özgü basit görseller (kütüphanesiz SVG): sütun grafiği, yüzde 100 yığılmış çubuk,
// tarife tamponu şeması ve renge bağımlı olmayan anahtar listesi. Hiçbir sayı burada üretilmez;
// değerleri ve metinleri çağıran verir. Her grafikte <title> ve <desc> vardır.

import { el, svg, uniqueId } from './dom.js';
import { niceDomain } from './charts.js';

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

function rootSvg(W, H, title, desc, tid, did) {
  return svg(
    'svg',
    { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-labelledby': `${tid} ${did}`, focusable: 'false' },
    svg('title', { id: tid }, title),
    svg('desc', { id: did }, desc),
  );
}

/** Taralı desen: dolgu rengi yerine biçimle ayrışan bölgeler için. */
function hatch(id, cls) {
  return svg(
    'pattern',
    { id, width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)', class: `hatch ${cls}` },
    svg('rect', { width: 6, height: 6, class: 'hatch-bg' }),
    svg('line', { x1: 0, y1: 0, x2: 0, y2: 6, class: 'hatch-ln' }),
  );
}

/**
 * Dikey sütun grafiği. o: {width, height, items: [{label, values: [{value, text, variant}]}],
 * yFormat, xLabel, tickCount, showValues, title, desc}. variant 'hollow' = içi boş (çizgili) sütun.
 */
export function columnChart(o) {
  const W = o.width;
  const H = o.height || 240;
  const m = { t: 18, r: 10, b: 28 + (o.xLabel ? 20 : 0), l: 42 };
  const iw = W - m.l - m.r;
  const ih = H - m.t - m.b;
  const all = o.items.flatMap((i) => i.values.map((v) => v.value)).filter(isNum);
  const dom = niceDomain(0, Math.max(...all, 0.01), o.tickCount || 4);
  const sy = (v) => m.t + ih - ((v - dom.lo) / (dom.hi - dom.lo)) * ih;
  const root = rootSvg(W, H, o.title, o.desc, uniqueId('ct'), uniqueId('cd'));

  for (const t of dom.ticks) {
    root.append(svg('line', { class: 'grid', x1: m.l, x2: W - m.r, y1: sy(t), y2: sy(t) }), svg('text', { x: m.l - 6, y: sy(t) + 4, 'text-anchor': 'end' }, o.yFormat(t)));
  }
  root.append(svg('line', { class: 'axis', x1: m.l, x2: W - m.r, y1: sy(dom.lo), y2: sy(dom.lo) }));

  const gw = iw / o.items.length;
  o.items.forEach((item, i) => {
    const k = item.values.length;
    const barW = Math.min((gw * 0.8) / k, 30);
    const start = m.l + gw * i + (gw - barW * k) / 2;
    item.values.forEach((v, j) => {
      if (!isNum(v.value)) return;
      const y = sy(v.value);
      const x = start + j * barW;
      const rect = svg('rect', { class: v.variant === 'hollow' ? 'col pred' : 'col', x, y, width: Math.max(barW - 1, 1), height: Math.max(sy(dom.lo) - y, 1) }, svg('title', null, `${item.label}: ${v.text}`));
      root.append(rect);
      if (o.showValues && k === 1) root.append(svg('text', { class: 'bar-val', x: x + barW / 2, y: y - 4, 'text-anchor': 'middle' }, v.text));
    });
    root.append(svg('text', { x: m.l + gw * i + gw / 2, y: H - m.b + 16, 'text-anchor': 'middle' }, item.label));
  });
  if (o.xLabel) root.append(svg('text', { class: 'axis-title', x: W / 2, y: H - 6 }, o.xLabel));
  return root;
}

/**
 * Tek yatay çubuk, parçalara bölünmüş (toplam 1). o: {width, segments: [{value, text, cls, pattern}], title, desc}.
 * Değerler çubuğun altında yazılır; "pattern" parçaları taralı çizilir.
 */
export function stackedBar(o) {
  const W = o.width;
  const H = 70;
  const m = { l: 6, r: 6 };
  const iw = W - m.l - m.r;
  const root = rootSvg(W, H, o.title, o.desc, uniqueId('sb'), uniqueId('sd'));
  const pid = uniqueId('hs');
  root.append(svg('defs', null, hatch(pid, 'hatch-d')));
  const total = o.segments.reduce((s, x) => s + (isNum(x.value) ? Math.max(0, x.value) : 0), 0) || 1;
  let at = m.l;
  for (const seg of o.segments) {
    const w = (Math.max(0, isNum(seg.value) ? seg.value : 0) / total) * iw;
    const attrs = { class: `seg ${seg.cls}`, x: at, y: 10, width: Math.max(w, 0), height: 32 };
    if (seg.pattern) attrs.fill = `url(#${pid})`;
    root.append(svg('rect', attrs, svg('title', null, seg.text)), svg('text', { class: 'bar-val', x: at + w / 2, y: 60, 'text-anchor': 'middle' }, seg.text));
    at += w;
  }
  return root;
}

/** Anahtar listesi: küçük örnek şekil + metin. items: [{cls, label, pattern}]. */
export function keyList(items) {
  const ul = el('ul', { class: 'legend key-list' });
  for (const it of items) {
    const sw = svg('svg', { class: 'swatch', width: 22, height: 14, viewBox: '0 0 22 14', 'aria-hidden': 'true', focusable: 'false' });
    const attrs = { class: `seg ${it.cls}`, x: 1, y: 1, width: 20, height: 12 };
    if (it.pattern) {
      const pid = uniqueId('hk');
      sw.append(svg('defs', null, hatch(pid, it.hatch || 'hatch-d')));
      attrs.fill = `url(#${pid})`;
    }
    sw.append(svg('rect', attrs));
    ul.append(el('li', null, sw, el('span', null, it.label)));
  }
  return ul;
}

/**
 * Tarife tamponu şeması (veri değil, örnekleme). o: {width, minutes: {flight, buffer, small, large},
 * text: {scheduled, row1, row2, row3, title, desc}}.
 */
export function bufferDiagram(o) {
  const W = o.width;
  const { flight, buffer, small, large } = o.minutes;
  const m = { l: 10, r: 10, t: 26 };
  const rowH = 52;
  const H = m.t + 3 * rowH + 4;
  const end = flight + Math.max(buffer, large);
  const sx = (v) => m.l + (v / end) * (W - m.l - m.r);
  const pid = uniqueId('hb');
  const root = rootSvg(W, H, o.text.title, o.text.desc, uniqueId('bt'), uniqueId('bd'));
  root.append(svg('defs', null, hatch(pid, 'hatch-a')));

  const part = (from, to, cls, y, pattern) => {
    const attrs = { class: `seg ${cls}`, x: sx(from), y, width: Math.max(sx(to) - sx(from), 1), height: 20 };
    if (pattern) attrs.fill = `url(#${pid})`;
    return svg('rect', attrs);
  };
  const rows = [
    { caption: o.text.row1, parts: [[0, flight, 'flight'], [flight, flight + buffer, 'buffer', true]] },
    { caption: o.text.row2, parts: [[0, flight, 'flight'], [flight, flight + buffer, 'buffer', true], [flight, flight + small, 'delay']] },
    { caption: o.text.row3, parts: [[0, flight, 'flight'], [flight, flight + buffer, 'buffer', true], [flight, flight + buffer, 'delay'], [flight + buffer, flight + large, 'over']] },
  ];
  rows.forEach((row, i) => {
    const top = m.t + i * rowH;
    root.append(svg('text', { class: 'diag-caption', x: m.l, y: top + 12 }, row.caption));
    for (const [from, to, cls, pattern] of row.parts) root.append(part(from, to, cls, top + 18, pattern));
  });
  const mx = sx(flight + buffer);
  root.append(svg('line', { class: 'ref', x1: mx, x2: mx, y1: m.t - 6, y2: H - 2 }), svg('text', { class: 'ref-label', x: mx - 4, y: 14 }, o.text.scheduled));
  return root;
}
