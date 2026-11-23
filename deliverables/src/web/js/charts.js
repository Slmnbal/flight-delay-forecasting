// Minimal SVG grafikleri (kütüphanesiz). Renkler CSS sınıflarından gelir; iki tema da çalışır.
// Her grafiğin <title>/<desc> değeri vardır ve görünümde bir veri tablosu eşlik eder.

import { el, svg, fill, uniqueId } from './dom.js';
import { T } from './metin.js';

export function niceStep(range, count = 5) {
  if (!(range > 0)) return 1;
  const raw = range / count;
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / magnitude;
  const factor = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
  return factor * magnitude;
}

/** Round [min, max] outwards to "nice" bounds; returns {lo, hi, step, ticks}. */
export function niceDomain(min, max, count = 5) {
  let lo = min;
  let hi = max;
  if (!(hi > lo)) hi = lo + 1;
  const step = niceStep(hi - lo, count);
  lo = Math.floor(lo / step + 1e-9) * step;
  hi = Math.ceil(hi / step - 1e-9) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step * 1e-6; v += step) ticks.push(Number(v.toFixed(10)));
  return { lo: Number(lo.toFixed(10)), hi: Number(hi.toFixed(10)), step, ticks };
}

/** Draw `build(width)` into `container` and redraw when the container width changes. */
export function mountChart(container, build) {
  let lastWidth = 0;
  function draw(force) {
    const width = Math.max(300, Math.round(container.clientWidth));
    if (!force && width === lastWidth) return;
    lastWidth = width;
    fill(container, build(width));
  }
  draw(true);
  if ('ResizeObserver' in window) new ResizeObserver(() => draw(false)).observe(container);
  return { redraw: () => draw(true) };
}

function marker(kind, cx, cy, cls) {
  const r = 4.5;
  const f = (n) => Number(n.toFixed(1));
  if (kind === 'square') return svg('rect', { x: f(cx - r), y: f(cy - r), width: 2 * r, height: 2 * r, class: cls });
  if (kind === 'diamond') {
    return svg('path', { d: `M${f(cx)} ${f(cy - r - 1)}L${f(cx + r + 1)} ${f(cy)}L${f(cx)} ${f(cy + r + 1)}L${f(cx - r - 1)} ${f(cy)}Z`, class: cls });
  }
  if (kind === 'triangle') {
    return svg('path', { d: `M${f(cx)} ${f(cy - r - 1)}L${f(cx + r + 1)} ${f(cy + r)}L${f(cx - r - 1)} ${f(cy + r)}Z`, class: cls });
  }
  return svg('circle', { cx: f(cx), cy: f(cy), r, class: cls });
}

function seriesClass(s) {
  return `ser ${s.cls || 'ser-a'}${s.hollow ? ' hollow' : ''}${s.dash ? ' dashed' : ''}`;
}

/**
 * Line/marker chart on numeric axes.
 * o: {width, height, xDomain, yDomain, xTicks, yTicks, xFormat, yFormat, xLabel, yLabel,
 *     series: [{name, cls, marker, hollow, dash, points: [{x, y, label}]}],
 *     hlines: [{y, label}], diagonal, title, desc}
 */
export function xyChart(o) {
  const W = o.width;
  const H = o.height;
  const m = { t: 12, r: 16, b: 52, l: 62 };
  const iw = W - m.l - m.r;
  const ih = H - m.t - m.b;
  const [x0, x1] = o.xDomain;
  const [y0, y1] = o.yDomain;
  const sx = (v) => m.l + ((v - x0) / (x1 - x0)) * iw;
  const sy = (v) => m.t + ih - ((v - y0) / (y1 - y0)) * ih;
  const tid = uniqueId('ct');
  const did = uniqueId('cd');

  const root = svg(
    'svg',
    { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-labelledby': `${tid} ${did}`, focusable: 'false' },
    svg('title', { id: tid }, o.title),
    svg('desc', { id: did }, o.desc),
  );

  for (const t of o.yTicks) {
    const y = sy(t);
    root.append(
      svg('line', { class: 'grid', x1: m.l, x2: W - m.r, y1: y, y2: y }),
      svg('text', { x: m.l - 8, y: y + 4, 'text-anchor': 'end' }, o.yFormat(t)),
    );
  }
  for (const t of o.xTicks) {
    const tick = typeof t === 'number' ? { v: t, label: o.xFormat(t) } : t;
    const x = sx(tick.v);
    root.append(
      svg('line', { class: 'grid', x1: x, x2: x, y1: m.t, y2: m.t + ih }),
      svg('text', { x, y: m.t + ih + 18, 'text-anchor': 'middle' }, tick.label),
    );
  }
  root.append(
    svg('line', { class: 'axis', x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih }),
    svg('line', { class: 'axis', x1: m.l, x2: m.l, y1: m.t, y2: m.t + ih }),
  );
  if (o.xLabel) root.append(svg('text', { class: 'axis-title', x: m.l + iw / 2, y: H - 8 }, o.xLabel));
  if (o.yLabel) {
    root.append(svg('text', { class: 'axis-title', x: 14, y: m.t + ih / 2, transform: `rotate(-90 14 ${m.t + ih / 2})` }, o.yLabel));
  }

  if (o.diagonal) {
    const d0 = Math.max(x0, y0);
    const d1 = Math.min(x1, y1);
    root.append(svg('line', { class: 'diag', x1: sx(d0), y1: sy(d0), x2: sx(d1), y2: sy(d1) }));
  }
  for (const h of o.hlines || []) {
    root.append(
      svg('line', { class: 'ref', x1: m.l, x2: W - m.r, y1: sy(h.y), y2: sy(h.y) }),
      svg('text', { class: 'ref-label', x: W - m.r - 4, y: sy(h.y) - 5 }, h.label),
    );
  }

  for (const s of o.series) {
    const g = svg('g', { class: seriesClass(s) });
    if (s.points.length > 1) {
      const d = s.points.map((p, i) => `${i ? 'L' : 'M'}${sx(p.x).toFixed(1)} ${sy(p.y).toFixed(1)}`).join('');
      g.append(svg('path', { class: 'line', d }));
    }
    for (const p of s.points) {
      const mk = marker(s.marker || 'circle', sx(p.x), sy(p.y), 'mk');
      if (p.label) mk.append(svg('title', null, `${s.name}: ${p.label}`));
      g.append(mk);
    }
    root.append(g);
  }
  return root;
}

export function legend(series) {
  const ul = el('ul', { class: 'legend' });
  for (const s of series) {
    const sw = svg(
      'svg',
      { class: `swatch ${seriesClass(s)}`, width: 30, height: 14, viewBox: '0 0 30 14', 'aria-hidden': 'true', focusable: 'false' },
      svg('path', { class: 'line', d: 'M2 7H28' }),
      marker(s.marker || 'circle', 15, 7, 'mk'),
    );
    ul.append(el('li', null, sw, el('span', null, s.name)));
  }
  return ul;
}

/**
 * 100 daireli birim grafiği (10 x 10): `count` daire dolu (geç varan uçuş), kalanı boş.
 * Dolu ve boş daire biçimce de ayrışır (renge bağımlı değil). o: {count, title, cls}
 */
export function pictograph(o) {
  const filled = Math.max(0, Math.min(100, Math.round(o.count)));
  const step = 20;
  const tid = uniqueId('pg');
  const root = svg(
    'svg',
    { viewBox: '0 0 200 200', class: o.cls ? `picto ${o.cls}` : 'picto', role: 'img', 'aria-labelledby': tid, focusable: 'false' },
    svg('title', { id: tid }, o.title),
  );
  for (let i = 0; i < 100; i += 1) {
    root.append(svg('circle', { class: i < filled ? 'dot late' : 'dot ok', cx: (i % 10) * step + 10, cy: Math.floor(i / 10) * step + 10, r: 7 }));
  }
  return root;
}

/**
 * Horizontal bars in the order of `items` (no sorting).
 * o: {width, items: [{label, value, text}], refs: [{value}], title, desc}
 */
export function barChart(o) {
  const W = o.width;
  const rowH = 24;
  const m = { t: 8, r: 84, b: 30, l: o.labelWidth || 78 };
  const H = m.t + m.b + o.items.length * rowH;
  const values = o.items.map((i) => i.value).filter((v) => v !== null && v !== undefined);
  const refVals = (o.refs || []).map((r) => r.value);
  const lo = Math.min(0, ...values, ...refVals);
  const hi = Math.max(0, ...values, ...refVals);
  const dom = niceDomain(lo, hi, 4);
  const sx = (v) => m.l + ((v - dom.lo) / (dom.hi - dom.lo)) * (W - m.l - m.r);
  const tid = uniqueId('bt');
  const did = uniqueId('bd');

  const root = svg(
    'svg',
    { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-labelledby': `${tid} ${did}`, focusable: 'false' },
    svg('title', { id: tid }, o.title),
    svg('desc', { id: did }, o.desc),
  );
  for (const t of dom.ticks) {
    root.append(
      svg('line', { class: 'grid', x1: sx(t), x2: sx(t), y1: m.t, y2: H - m.b }),
      svg('text', { x: sx(t), y: H - m.b + 16, 'text-anchor': 'middle' }, o.tickFormat ? o.tickFormat(t) : String(t)),
    );
  }
  o.items.forEach((item, i) => {
    const y = m.t + i * rowH;
    root.append(svg('text', { x: m.l - 8, y: y + rowH / 2 + 4, 'text-anchor': 'end' }, item.label));
    if (item.value === null || item.value === undefined) {
      root.append(svg('text', { class: 'bar-val', x: sx(0) + 4, y: y + rowH / 2 + 4 }, T.ortak.yok));
      return;
    }
    const x = Math.min(sx(0), sx(item.value));
    const w = Math.abs(sx(item.value) - sx(0));
    const bar = svg('rect', { class: item.value < 0 ? 'bar neg' : 'bar', x, y: y + 4, width: Math.max(w, 1), height: rowH - 8 }, svg('title', null, `${item.label}: ${item.text}`));
    const end = item.value < 0 ? x - 4 : x + w + 4;
    root.append(bar, svg('text', { class: 'bar-val', x: end, y: y + rowH / 2 + 4, 'text-anchor': item.value < 0 ? 'end' : 'start' }, item.text));
  });
  root.append(svg('line', { class: 'axis', x1: sx(0), x2: sx(0), y1: m.t, y2: H - m.b }));
  for (const r of o.refs || []) {
    root.append(svg('line', { class: 'ref', x1: sx(r.value), x2: sx(r.value), y1: m.t, y2: H - m.b }));
  }
  return root;
}
