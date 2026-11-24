// Simge seti: küçük, tutarlı, elle çizilmiş satır içi SVG simgeleri (dış kütüphane ya da yazı tipi yok).
// Hepsi 24x24 görünüm kutusunda, 1,75 çizgi kalınlığında ve currentColor ile çizilir; yani yazının
// rengini alır, iki temada da çalışır. Simgeler süstür: aria-hidden="true" olur ve yanında her zaman
// metinli bir etiket bulunur (simge tek başına anlam taşımaz).

import { svg } from './dom.js';

// Her simge: [öğe, öznitelikler] listesi. Yollar sade tutuldu.
const P = (d) => ['path', { d }];
const C = (cx, cy, r) => ['circle', { cx, cy, r }];

export const ICONS = Object.freeze({
  // Kâğıt uçak: kalkış, uçuş
  plane: [P('M21 3 3 10l7.5 3.5L14 21z'), P('M21 3 10.5 13.5')],
  // Saat: saat bloğu, tipik rötar
  clock: [C(12, 12, 9), P('M12 7v5l3 2')],
  // Bulut: hava
  cloud: [P('M7 18h10.5a3.75 3.75 0 0 0 .4-7.48A6 6 0 0 0 6.4 9.2 4.5 4.5 0 0 0 7 18z')],
  // Kum saati: tampon
  buffer: [P('M6 3h12M6 21h12M7 3v3.5a5 5 0 0 0 2 4l1.5 1.5L9 13.5a5 5 0 0 0-2 4V21M17 3v3.5a5 5 0 0 1-2 4L13.5 12l1.5 1.5a5 5 0 0 1 2 4V21')],
  // Konum işareti: havalimanı, harita
  pin: [P('M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z'), C(12, 9.5, 2.5)],
  // Rota yayı: iki nokta ve aralarında yay
  route: [C(5, 18, 2), C(19, 18, 2), P('M5 16C5 6 19 6 19 16')],
  // Sütun grafiği
  chart: [P('M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6')],
  // Kalkan ve onay: geçti, güvenilir
  shield: [P('M12 3 4.5 6v5.5c0 4.5 3.2 8 7.5 9.5 4.3-1.5 7.5-5 7.5-9.5V6z'), P('M8.5 12l2.5 2.5 4.5-5')],
  // Uyarı üçgeni: geçmedi, riskli
  alert: [P('M12 3.5 2.5 20h19z'), P('M12 10v4.5M12 17.5h.01')],
  // Bilgi
  info: [C(12, 12, 9), P('M12 11v5M12 8h.01')],
  // Takvim: mevsim
  calendar: [['rect', { x: 4, y: 5, width: 16, height: 15, rx: 2 }], P('M4 10h16M8 3v4M16 3v4')],
  // Hedef
  target: [C(12, 12, 9), C(12, 12, 5), C(12, 12, 1)],
  // Çizgili daire: değerlendirilmedi, yok
  dash: [C(12, 12, 9), P('M8 12h8')],
});

export const ICON_NAMES = Object.freeze(Object.keys(ICONS));

/**
 * Bir simge düğümü döndürür. Her zaman aria-hidden="true"; erişilebilir ad, yanındaki metindir.
 * opts: {size (piksel, varsayılan 20), class}
 */
export function icon(name, opts = {}) {
  const parts = ICONS[name];
  const size = opts.size || 20;
  const root = svg('svg', {
    class: opts.class ? `ico ${opts.class}` : 'ico',
    viewBox: '0 0 24 24',
    width: size,
    height: size,
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': 1.75,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'aria-hidden': 'true',
    focusable: 'false',
  });
  for (const [tag, attrs] of parts || []) root.append(svg(tag, attrs));
  return root;
}
