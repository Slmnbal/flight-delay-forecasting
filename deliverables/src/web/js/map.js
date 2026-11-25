// Havalimanı haritası: Albers eşit alanlı konik projeksiyon (standart paraleller 29,5 ve 45,5 derece).
// En altta deniz, üstünde kara (eyalet sınırları: Natural Earth 1:110m, kamu malı; ./harita/abd-eyaletler.json),
// denizin üzerinde çok soluk bir enlem-boylam ızgarası, üstte seçili havalimanından çıkan rota yayları ve
// havalimanı noktaları vardır. Eyalet dosyası yüklenemezse (o.states null) harita yalnızca ızgarayla çalışır.
//
// Renkler risk skalasının 5 sınıfıdır (CSS: .r1 ... .r5 dolgu, .rs1 ... .rs5 çizgi); sınıf numarasını
// çağıran verir, renkleri tema belirler. Böylece açık ve koyu tema ayrı renk listesiyle çalışır.
//
// Noktalar: alan = test uçuşu sayısı. Yaylar: kalınlık = rotanın toplam uçuşu, renk = geç varış oranı.
// Bilgi kartı (üzerine gelince, dokununca ya da klavye odağında) SVG içinde çizilir; ekran okuyucu için
// her nokta ve yayda aria-label vardır. Yaylar klavyede tek durak olarak girilir; ok tuşlarıyla gezilir.
//
// Etiketler deterministik bir yerleşimle konur: her etiket için sağ, sol, üst, alt ve çaprazlar
// denenir; başka etikete, noktaya ya da eksen etiketine çarpmayan ilk yer seçilir. Yakın
// noktalarda (ör. JFK-LGA-EWR) etiket noktadan uzaklaşır ve kısa bir bağlantı çizgisi çizilir.

import { svg, uniqueId } from './dom.js';
import { T } from './metin.js';
import { arcGeometry, arcWidth, riskClass, RISK_EDGES } from './kesfet-hesap.js';

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

const LAT_LINES = [25, 30, 35, 40, 45, 50];
const LON_LINES = [-125, -115, -105, -95, -85, -75, -65];
const LAT_RANGE = [22, 52];
const LON_RANGE = [-128, -64];

/** Koordinat haritanın gösterdiği alanda mı (dışındakiler yayla çizilmez). */
export function onMap(lat, lon) {
  return lat >= LAT_RANGE[0] && lat <= LAT_RANGE[1] && lon >= LON_RANGE[0] && lon <= LON_RANGE[1];
}

export const isCompact = (width) => width < 560;

/** Yay kalınlık aralığı (az uçuşlu rota, çok uçuşlu rota); telefonda daha ince ama yine çizilir. */
export const arcRange = (compact) => (compact ? [1.6, 6] : [2.6, 12]);

const PAD = 24;
let heightRatio = null;

/** Haritanın yükseklik/genişlik oranı (projeksiyon kutusundan); sabit yükseklikli bantta genişliği bulmak için. */
function projectionRatio() {
  if (heightRatio === null) {
    const pts = [];
    for (const lat of LAT_LINES) for (let lon = LON_RANGE[0]; lon <= LON_RANGE[1]; lon += 1) pts.push(albers(lon, lat));
    for (const lon of LON_LINES) for (let lat = LAT_RANGE[0]; lat <= LAT_RANGE[1]; lat += 1) pts.push(albers(lon, lat));
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    heightRatio = (Math.max(...ys) - Math.min(...ys)) / (Math.max(...xs) - Math.min(...xs));
  }
  return heightRatio;
}

/** Verilen yükseklikte (piksel) haritanın sığacağı genişlik; harita bu yüksekliği aşmaz. */
export const widthForHeight = (height) => Math.round((height - 2 * PAD) / projectionRatio() + 2 * PAD);

/** Nokta yarıçapı (alan ~ uçuş sayısı); açıklama (lejant) da aynı işlevi kullanır. */
export function dotRadius(n, maxN, compact) {
  const rMin = compact ? 4 : 5;
  const rSpan = compact ? 6 : 9;
  return rMin + rSpan * Math.sqrt(maxN > 0 ? Math.max(0, n) / maxN : 0);
}

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
 * o: {width, airports, states: [{eyalet, halkalar}] | null, valueOf(a) -> number|null (null: yayımlanmadı),
 *     classOf(a) -> 1..5|null (risk sınıfı), selected, onSelect(iata), labelOf(a) -> aria metni,
 *     pointTip(a) -> bilgi kartı satırları,
 *     arcs: {origin: iata, items: [{iata, ad, enlem, boylam, n, rate}], edges?, groupLabel} | null,
 *     arcLabel(item) -> aria metni, arcTip(item) -> bilgi kartı satırları}
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
  const pad = PAD;
  const scale = (o.width - 2 * pad) / (maxX - minX);
  const height = Math.round((maxY - minY) * scale + 2 * pad);
  const tx = (p) => [pad + (p[0] - minX) * scale, pad + (p[1] - minY) * scale];

  const compact = isCompact(o.width);
  const tid = uniqueId('mt');
  const did = uniqueId('md');
  const hasStates = Array.isArray(o.states) && o.states.length > 0;
  const hasArcs = Boolean(o.arcs && o.arcs.items.length && o.airports.some((a) => a.iata === o.arcs.origin));
  const root = svg(
    'svg',
    { viewBox: `0 0 ${o.width} ${height}`, class: `map${hasStates ? ' has-states' : ''}${hasArcs ? ' has-arcs' : ''}`, role: 'group', 'aria-labelledby': `${tid} ${did}`, focusable: 'false' },
    svg('title', { id: tid }, T.havalimani.haritaBaslik(o.airports.length)),
    svg('desc', { id: did }, T.havalimani.haritaAciklama),
    svg('rect', { class: 'map-bg', x: 0, y: 0, width: o.width, height }),
  );

  // Izgara (yalnızca denizde görünür: kara üstüne çizilir) ve eksen etiketleri: enlemler batı ucunda
  // (çizginin üstünde), boylamlar güney ucunda (altında); iki grup ayrı köşelerde olduğu için çarpmaz.
  const graticule = svg('g', { class: 'graticule', 'aria-hidden': 'true' });
  const axisLabels = svg('g', { 'aria-hidden': 'true' });
  const obstacles = [];
  for (const g of grid) {
    const pts = g.pts.map(tx);
    graticule.append(svg('path', { class: 'grid', d: line(pts) }));
    if (g.kind === 'lat') {
      const [x, y] = pts[0];
      const text = `${g.value}${T.harita.kuzey}`;
      axisLabels.append(svg('text', { class: 'grid-label', x: x + 4, y: y - 4 }, text));
      obstacles.push({ x0: x + 3, y0: y - 14, x1: x + 3 + text.length * 6.4, y1: y - 1 });
    } else {
      const [x, y] = pts[0];
      const text = `${Math.abs(g.value)}${T.harita.bati}`;
      const w = text.length * 6.4;
      axisLabels.append(svg('text', { class: 'grid-label', x: x - w / 2, y: y + 14 }, text));
      obstacles.push({ x0: x - w / 2 - 1, y0: y + 4, x1: x + w / 2 + 1, y1: y + 17 });
    }
  }
  root.append(graticule);

  // Eyalet sınırları (aynı projeksiyon): kara dolgusu ve ince sınır çizgisi.
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
  root.append(axisLabels);

  const maxN = Math.max(...o.airports.map((a) => a.n_test_ucus), 1);
  const placed = o.airports
    .map((a) => {
      const xy = tx(albers(a.boylam, a.enlem));
      return { a, xy, r: dotRadius(a.n_test_ucus, maxN, compact) };
    })
    .sort((p, q) => q.a.n_test_ucus - p.a.n_test_ucus || p.a.iata.localeCompare(q.a.iata)); // büyükler önce, küçükler üstte kalır

  // Bilgi kartı: tek SVG grubu, en üstte; yeri ve satırları çağrıda belirlenir.
  const tip = svg('g', { class: 'tip off', 'aria-hidden': 'true' });
  function showTip(ax, ay, lines) {
    tip.replaceChildren();
    const w = Math.max(...lines.map((l) => String(l).length)) * 6.3 + 16;
    const h = lines.length * 15 + 10;
    let x = ax + 12;
    if (x + w > o.width - 4) x = ax - 12 - w;
    if (x < 4) x = 4;
    let y = ay - h - 10;
    if (y < 4) y = ay + 14;
    if (y + h > height - 4) y = height - h - 4;
    tip.append(svg('rect', { class: 'tip-bg', x: x.toFixed(1), y: y.toFixed(1), width: w.toFixed(1), height: h, rx: 4 }));
    lines.forEach((text, i) => tip.append(svg('text', { class: i === 0 ? 'tip-head' : 'tip-line', x: (x + 8).toFixed(1), y: (y + 17 + i * 15).toFixed(1) }, String(text))));
    tip.setAttribute('class', 'tip');
  }
  let clearArcs = () => {};
  const hideTip = () => {
    tip.setAttribute('class', 'tip off');
    clearArcs();
  };
  root.addEventListener('click', (e) => {
    if (!(e.target.closest && e.target.closest('.arc, .pt'))) hideTip();
  });

  // Rota yayları: seçili havalimanından çıkan rotalar. Kalın olan altta, ince olan üstte çizilir.
  const origin = o.arcs ? o.airports.find((a) => a.iata === o.arcs.origin) : null;
  if (origin && o.arcs.items.length) {
    const [ox, oy] = tx(albers(origin.boylam, origin.enlem));
    const edges = o.arcs.edges || RISK_EDGES;
    const items = [...o.arcs.items].sort((p, q) => q.n - p.n || p.iata.localeCompare(q.iata));
    const arcMax = Math.max(...items.map((i) => i.n), 1);
    const group = svg('g', { class: 'arcs', role: 'group', 'aria-label': o.arcs.groupLabel });
    const els = [];
    // Parlama süzgeci (yalnızca koyu temada görünür): SVG içinde, satır içi; dış kaynak yok.
    const fid = uniqueId('mg');
    root.append(
      svg(
        'defs',
        null,
        svg('filter', { id: fid, filterUnits: 'userSpaceOnUse', x: 0, y: 0, width: o.width, height }, svg('feGaussianBlur', { stdDeviation: compact ? 2 : 3.5 })),
      ),
    );
    const [wMin, wMax] = arcRange(compact);
    // Üzerine gelinen ya da odaktaki yay öne çıkar (active), diğerleri solar (has-active).
    clearArcs = () => {
      group.setAttribute('class', 'arcs');
      for (const other of els) other.setAttribute('class', 'arc');
    };
    for (const item of items) {
      const [x, y] = tx(albers(item.boylam, item.enlem));
      if (x < 0 || x > o.width || y < 0 || y > height) continue;
      const geo = arcGeometry(ox, oy, x, y);
      const w = arcWidth(item.n, arcMax, wMin, wMax);
      const cls = riskClass(item.rate, edges) || 0;
      const g = svg('g', { class: 'arc', tabindex: els.length === 0 ? '0' : '-1', role: 'img', 'aria-label': o.arcLabel(item) });
      g.append(
        svg('path', { class: 'arc-hit', d: geo.d, 'stroke-width': Math.max(w + 12, 18).toFixed(1) }),
        svg('path', { class: `arc-glow rs${cls}`, d: geo.d, 'stroke-width': (w + 6).toFixed(1), filter: `url(#${fid})` }),
        svg('path', { class: 'arc-case', d: geo.d, 'stroke-width': (w + (compact ? 2.4 : 3.4)).toFixed(1) }),
        svg('path', { class: `arc-line rs${cls}`, d: geo.d, 'stroke-width': w.toFixed(1) }),
        svg('circle', { class: `arc-end r${cls}`, cx: x.toFixed(1), cy: y.toFixed(1), r: compact ? 3.2 : 4.2 }),
      );
      const show = () => {
        showTip(x, y, o.arcTip(item));
        clearArcs();
        group.setAttribute('class', 'arcs has-active');
        g.setAttribute('class', 'arc active');
      };
      g.addEventListener('pointerenter', show);
      g.addEventListener('pointerleave', () => {
        if (document.activeElement !== g) hideTip();
      });
      g.addEventListener('click', show);
      g.addEventListener('focus', () => {
        for (const other of els) other.setAttribute('tabindex', other === g ? '0' : '-1');
        show();
      });
      g.addEventListener('blur', hideTip);
      g.addEventListener('keydown', (e) => {
        const at = els.indexOf(g);
        let next = -1;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = Math.min(els.length - 1, at + 1);
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = Math.max(0, at - 1);
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = els.length - 1;
        else if (e.key === 'Escape') hideTip();
        if (next >= 0) {
          e.preventDefault();
          els[next].focus();
        }
      });
      els.push(g);
      group.append(g);
    }
    if (els.length) root.append(group);
  }

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
    const cls = hidden ? null : o.classOf(a);
    const g = svg('g', {
      class: `pt${hidden ? ' hidden-pt' : ''}${isSel ? ' sel' : ''}`,
      tabindex: '0',
      role: 'button',
      'aria-pressed': isSel ? 'true' : 'false',
      'aria-label': o.labelOf(a),
    });
    g.append(
      svg('circle', { class: 'ring', cx: xy[0].toFixed(1), cy: xy[1].toFixed(1), r: (r + 4).toFixed(1) }),
      svg('circle', { class: cls ? `dot r${cls}` : 'dot', cx: xy[0].toFixed(1), cy: xy[1].toFixed(1), r: r.toFixed(1) }),
    );
    const show = () => showTip(xy[0], xy[1] - r, o.pointTip(a));
    g.addEventListener('pointerenter', show);
    g.addEventListener('pointerleave', () => {
      if (document.activeElement !== g) hideTip();
    });
    g.addEventListener('focus', show);
    g.addEventListener('blur', hideTip);
    g.addEventListener('click', () => o.onSelect(a.iata));
    g.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        o.onSelect(a.iata);
      } else if (e.key === 'Escape') {
        hideTip();
      }
    });
    root.append(g);
  }

  for (const { a } of placed) {
    const spot = labels.get(a.iata);
    if (!spot) continue;
    root.append(svg('text', { class: 'pt-label', 'aria-hidden': 'true', 'text-anchor': 'middle', x: spot.rect.cx.toFixed(1), y: (spot.rect.cy + 4).toFixed(1) }, a.iata));
  }
  root.append(tip);
  return root;
}
