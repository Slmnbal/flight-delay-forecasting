// Hikâye ve sunum için ortak küçük yardımcılar: grafik kutusu, etiket bölme, risk grupları, daire paneli.
// Hiçbir sonuç burada elle yazılmaz; yalnızca "geç" tanımındaki eşik ve birim grafikteki daire sayısı sabittir.

import { el } from './dom.js';
import { T } from './metin.js';
import { fmtPct, fmtInt } from './fmt.js';
import { mountChart, pictograph } from './charts.js';

export const LATE_AFTER = 15; // "geç varış" tanımı (dakika)
export const PICTO_TOTAL = 100; // birim grafikteki daire sayısı
export const COIN_FLIP = 0.5;
export const NEAR_ENOUGH = 0.03; // "tahmin gerçeğe yakın" demek için en büyük fark
export const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
export const count100 = (rate) => Math.round(rate * PICTO_TOTAL);

export function chartBox(build, wide = true) {
  const box = el('div', { class: wide ? 'chart-box wide' : 'chart-box' });
  const handle = mountChart(box, build);
  return { box, handle };
}

/** Etiketi, dar sütunlara sığsın diye satırlara böler. */
export function wrapLabel(text, max) {
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
export function riskGroups(kal) {
  const entry = kal && Array.isArray(kal.siniflandirma) ? kal.siniflandirma.find((e) => e.gorev === 'arrdel15' && e.model === 'lgbm_T2') : null;
  if (!entry || !Array.isArray(entry.kutular)) return null;
  const bins = entry.kutular.filter((b) => isNum(b.gozlenen_oran) && isNum(b.ortalama_tahmin)).sort((a, b) => a.ortalama_tahmin - b.ortalama_tahmin);
  return bins.length >= 2 ? bins : null;
}

/** En riskli grup için "her N uçuştan K" (metin parametresi). */
export function riskiest(bins) {
  const per = bins.length;
  return { n: fmtInt(per), deger: fmtInt(Math.max(1, Math.round(bins[per - 1].gozlenen_oran * per))) };
}

export function pictoPanel(name, rate) {
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

export const figure = (content, caption) => el('figure', { class: 'slide-fig' }, content, caption ? el('figcaption', null, caption) : null);
