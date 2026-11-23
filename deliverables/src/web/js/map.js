// Havalimanı haritası: Albers eşit alanlı konik projeksiyon (standart paraleller 29,5 ve 45,5 derece).
// Altta sade eyalet sınırları (Natural Earth 1:110m, kamu malı; ./harita/abd-eyaletler.json) ve
// enlem-boylam ızgarası, üstte havalimanı noktaları vardır. Eyalet dosyası yüklenemezse (o.states
// null) harita yalnızca ızgarayla çalışır.
// Etiketler deterministik bir yerleşimle konur: her etiket için sağ, sol, üst, alt ve çaprazlar
// denenir; başka etikete, noktaya ya da eksen etiketine çarpmayan ilk yer seçilir. Yakın
// noktalarda (ör. JFK-LGA-EWR) etiket noktadan uzaklaşır ve kısa bir bağlantı çizgisi çizilir.

import { svg, uniqueId } from './dom.js';
import { T } from './metin.js';

const RAD = Math.PI / 180;

export function albers(lon, lat) {
  const lat1 = 29.5 * RAD;
  const lat2 = 45.5 * RAD;
  const lat0 = 37.5 * RAD;
  const lon0 = -96;
  const n = (Math.sin(lat1) + Math.sin(lat2)) / 2;
  const c = Math.cos(lat1) ** 2 + 2 * n * Math.sin(lat1);
  const rho0 = Math.sqrt(c - 2 * n * Math.sin(lat0)) / n;
  const rho = Math.sqrt(c - 2 * n * Math.sin(lat * RAD)) / n;
  const theta = n * (lon - lon0) * RAD;
  return [rho * Math.sin(theta), rho * Math.cos(theta) - rho0]; // ekran y'si aşağı doğru artar
}

const STOPS = ['#EAF3FB', '#A9CCE9', '#4F8FC6', '#1B5C99', '#0B2E57'];

function hexToRgb(hex) {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
}

export function rampColor(t) {
  const clamped = Math.min(1, Math.max(0, t));
  const pos = clamped * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(pos));
  const f = pos - i;
  const a = hexToRgb(STOPS[i]);
  const b = hexToRgb(STOPS[i + 1]);
  return '#' + a.map((v, k) => Math.round(v + (b[k] - v) * f).toString(16).padStart(2, '0')).join('');
}

/** Gösterge için küçük renk skalası (SVG gradyanı). */
export function rampBar(width = 160, height = 12) {
  const id = uniqueId('ramp');
  const stops = STOPS.map((c, i) => svg('stop', { offset: `${(i / (STOPS.length - 1)) * 100}%`, 'stop-color': c }));
  return svg(
    'svg',
    { width, height, viewBox: `0 0 ${width} ${height}`, 'aria-hidden': 'true', focusable: 'false' },
    svg('defs', null, svg('linearGradient', { id }, ...stops)),
    svg('rect', { x: 0.5, y: 0.5, width: width - 1, height: height - 1, fill: `url(#${id})`, stroke: '#7B8794' }),
  );
}

const LAT_LINES = [25, 30, 35, 40, 45, 50];
const LON_LINES = [-125, -115, -105, -95, -85, -75, -65];
const LAT_RANGE = [22, 52];
const LON_RANGE = [-128, -64];

function line(points) {
  return points.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join('');
}

// ---------------------------------------------------------------- etiket yerleşimi
const LABEL_W = 24; // "ATL" gibi 3 harf, 11 px kalın
const LABEL_H = 12;
const DIRS = [[1, 0], [-1, 0], [0, -1], [0, 1], [1, -1], [1, 1], [-1, -1], [-1, 1]];
const GAPS = [3, 12, 24, 38]; // ilki bitişik; sonrakiler bağlantı çizgisiyle

function rectOf(x, y, w, h) {
  return { x0: x - w / 2, y0: y - h / 2, x1: x + w / 2, y1: y + h / 2, cx: x, cy: y };
}

function overlapArea(a, b) {
  const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0);
  const h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
  return w > 0 && h > 0 ? w * h : 0;
}

function candidateRect(cx, cy, r, dir, gap) {
  const [ux, uy] = dir;
  const k = ux !== 0 && uy !== 0 ? 0.71 : 1;
  const x = ux === 0 ? cx : cx + ux * (k * (r + gap) + LABEL_W / 2);
  const y = uy === 0 ? cy : cy + uy * (k * (r + gap) + LABEL_H / 2);
  return rectOf(x, y, LABEL_W, LABEL_H);
}

/**
 * dots: [{x, y, r, id}] (en büyükten küçüğe), obstacles: sabit dikdörtgenler (eksen etiketleri),
 * bounds: {w, h}. Her nokta için {rect, leader} döndürür (Map, id -> yerleşim).
 */
export function placeLabels(dots, obstacles, bounds) {
  const placed = [];
  const result = new Map();
  const frame = { x0: 0, y0: 0, x1: bounds.w, y1: bounds.h };
  for (const dot of dots) {
    let best = null;
    search: for (let gi = 0; gi < GAPS.length; gi += 1) {
      for (const dir of DIRS) {
        const rect = candidateRect(dot.x, dot.y, dot.r, dir, GAPS[gi]);
        let score = 0;
        for (const p of placed) score += overlapArea(rect, p);
        for (const ob of obstacles) score += overlapArea(rect, ob);
        for (const other of dots) {
          if (other === dot) continue;
          const sq = { x0: other.x - other.r - 1, y0: other.y - other.r - 1, x1: other.x + other.r + 1, y1: other.y + other.r + 1 };
          score += overlapArea(rect, sq);
        }
        const inside = overlapArea(rect, frame);
        score += (LABEL_W * LABEL_H - inside) * 10;
        score += gi * 0.01; // eşitlikte yakın olan kazanır
        if (best === null || score < best.score) best = { rect, gi, score };
        if (score < 0.5) break search;
      }
    }
    placed.push(best.rect);
    let leader = null;
    if (best.gi > 0) {
      const px = Math.min(Math.max(dot.x, best.rect.x0), best.rect.x1);
      const py = Math.min(Math.max(dot.y, best.rect.y0), best.rect.y1);
      leader = [dot.x, dot.y, px, py];
    }
    result.set(dot.id, { rect: best.rect, leader });
  }
  return result;
}

/**
 * o: {width, airports, states: [{eyalet, halkalar}] | null, valueOf(a) -> number|null,
 *     domain: [lo, hi], selected, onSelect(iata), labelOf(a) -> aria metni}
 */
export function buildMap(o) {
  const grid = [];
  for (const lat of LAT_LINES) {
    const pts = [];
    for (let lon = LON_RANGE[0]; lon <= LON_RANGE[1]; lon += 1) pts.push(albers(lon, lat));
    grid.push({ kind: 'lat', value: lat, pts });
  }
  for (const lon of LON_LINES) {
    const pts = [];
    for (let lat = LAT_RANGE[0]; lat <= LAT_RANGE[1]; lat += 1) pts.push(albers(lon, lat));
    grid.push({ kind: 'lon', value: lon, pts });
  }
  const all = grid.flatMap((g) => g.pts);
  const minX = Math.min(...all.map((p) => p[0]));
  const maxX = Math.max(...all.map((p) => p[0]));
  const minY = Math.min(...all.map((p) => p[1]));
  const maxY = Math.max(...all.map((p) => p[1]));
  const pad = 24;
  const scale = (o.width - 2 * pad) / (maxX - minX);
  const height = Math.round((maxY - minY) * scale + 2 * pad);
  const tx = (p) => [pad + (p[0] - minX) * scale, pad + (p[1] - minY) * scale];

  const compact = o.width < 560;
  const tid = uniqueId('mt');
  const did = uniqueId('md');
  const hasStates = Array.isArray(o.states) && o.states.length > 0;
  const root = svg(
    'svg',
    { viewBox: `0 0 ${o.width} ${height}`, class: hasStates ? 'map has-states' : 'map', role: 'group', 'aria-labelledby': `${tid} ${did}`, focusable: 'false' },
    svg('title', { id: tid }, T.havalimani.haritaBaslik(o.airports.length)),
    svg('desc', { id: did }, T.havalimani.haritaAciklama),
    svg('rect', { class: 'map-bg', x: 0, y: 0, width: o.width, height }),
  );

  // Eyalet sınırları (aynı projeksiyon): ince çizgi, düşük kontrastlı dolgu.
  if (hasStates) {
    const states = svg('g', { class: 'states', 'aria-hidden': 'true' });
    for (const st of o.states) {
      const rings = Array.isArray(st.halkalar) ? st.halkalar : [];
      const d = rings
        .map((ring) => `${line(ring.map((pt) => tx(albers(pt[0], pt[1]))))}Z`)
        .join('');
      if (d) states.append(svg('path', { class: 'state', d }));
    }
    root.append(states);
  }

  // Eksen etiketleri: enlemler batı ucunda (çizginin üstünde), boylamlar güney ucunda (altında);
  // iki grup ayrı köşelerde olduğu için birbirine çarpmaz.
  const obstacles = [];
  for (const g of grid) {
    const pts = g.pts.map(tx);
    root.append(svg('path', { class: 'grid', d: line(pts) }));
    if (g.kind === 'lat') {
      const [x, y] = pts[0];
      const text = `${g.value}${T.harita.kuzey}`;
      root.append(svg('text', { class: 'grid-label', x: x + 4, y: y - 4 }, text));
      obstacles.push({ x0: x + 3, y0: y - 14, x1: x + 3 + text.length * 6.4, y1: y - 1 });
    } else {
      const [x, y] = pts[0];
      const text = `${Math.abs(g.value)}${T.harita.bati}`;
      const w = text.length * 6.4;
      root.append(svg('text', { class: 'grid-label', x: x - w / 2, y: y + 14 }, text));
      obstacles.push({ x0: x - w / 2 - 1, y0: y + 4, x1: x + w / 2 + 1, y1: y + 17 });
    }
  }

  const maxN = Math.max(...o.airports.map((a) => a.n_test_ucus), 1);
  const [lo, hi] = o.domain;
  const rMin = compact ? 4 : 5;
  const rSpan = compact ? 6 : 9;
  const placed = o.airports
    .map((a) => {
      const xy = tx(albers(a.boylam, a.enlem));
      return { a, xy, r: rMin + rSpan * Math.sqrt(a.n_test_ucus / maxN) };
    })
    .sort((p, q) => q.a.n_test_ucus - p.a.n_test_ucus || p.a.iata.localeCompare(q.a.iata)); // büyükler önce, küçükler üstte kalır

  const labels = compact
    ? new Map()
    : placeLabels(placed.map((p) => ({ x: p.xy[0], y: p.xy[1], r: p.r, id: p.a.iata })), obstacles, { w: o.width, h: height });

  for (const { leader } of labels.values()) {
    if (leader) root.append(svg('line', { class: 'leader', x1: leader[0].toFixed(1), y1: leader[1].toFixed(1), x2: leader[2].toFixed(1), y2: leader[3].toFixed(1) }));
  }

  for (const { a, xy, r } of placed) {
    const value = o.valueOf(a);
    const hidden = value === null || value === undefined;
    const isSel = a.iata === o.selected;
    const g = svg('g', {
      class: `pt${hidden ? ' hidden-pt' : ''}${isSel ? ' sel' : ''}`,
      tabindex: '0',
      role: 'button',
      'aria-pressed': isSel ? 'true' : 'false',
      'aria-label': o.labelOf(a),
    });
    g.append(
      svg('circle', { class: 'ring', cx: xy[0].toFixed(1), cy: xy[1].toFixed(1), r: (r + 4).toFixed(1) }),
      svg('circle', {
        class: 'dot',
        cx: xy[0].toFixed(1),
        cy: xy[1].toFixed(1),
        r: r.toFixed(1),
        fill: hidden ? null : rampColor(hi > lo ? (value - lo) / (hi - lo) : 0.5),
      }),
    );
    g.addEventListener('click', () => o.onSelect(a.iata));
    g.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        o.onSelect(a.iata);
      }
    });
    root.append(g);
  }

  for (const { a } of placed) {
    const spot = labels.get(a.iata);
    if (!spot) continue;
    root.append(svg('text', { class: 'pt-label', 'aria-hidden': 'true', 'text-anchor': 'middle', x: spot.rect.cx.toFixed(1), y: (spot.rect.cy + 4).toFixed(1) }, a.iata));
  }
  return root;
}
