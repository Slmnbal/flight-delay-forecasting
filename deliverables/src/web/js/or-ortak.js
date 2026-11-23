// Tampon optimizasyonu (OR) için ortak yardımcılar: hikâye adımı ve OR sekmesi aynı hesapları kullanır.
// Hiçbir sonuç elle yazılmaz; "anlamlı mı" kararı her zaman veri dosyasındaki %95 aralıktan okunur.

import { el } from './dom.js';
import { T } from './metin.js';
import { fmtRatio, fmtNum, txt } from './fmt.js';

/** Bir politika satırı listesinde kimliğe göre satır (yoksa null). */
export function rowOf(rows, id) {
  return Array.isArray(rows) ? rows.find((r) => r.kimlik === id) || null : null;
}

/** Bir karşılaştırmanın %95 aralığı sıfırı dışlıyor mu? Aralık yoksa false. */
export function excludesZero(c) {
  return !!c && typeof c.ga95_alt === 'number' && typeof c.ga95_ust === 'number' && (c.ga95_alt > 0 || c.ga95_ust < 0);
}

export const hasInterval = (c) => !!c && typeof c.ga95_alt === 'number' && typeof c.ga95_ust === 'number';

/** Maliyet oranına göre artan sırada τ ızgarası. Yalnızca dosyadaki noktalar kullanılır. */
export function sortedGrid(opt) {
  return [...opt.tau_izgarasi].sort((a, b) => a.maliyet_orani - b.maliyet_orani);
}

/** Verilen τ değerine en yakın ızgara noktasının sırası. */
export function nearestIndex(grid, tau) {
  let best = 0;
  grid.forEach((g, i) => {
    if (Math.abs(g.tau - tau) < Math.abs(grid[best].tau - tau)) best = i;
  });
  return best;
}

/** Bütçe eğrisindeki "plan_budget-b1_budget" karşılaştırmaları ve sonucu (aynı bütçede fark). */
export function equalBudget(opt, ad = 'arrdel15_orani') {
  const curve = Array.isArray(opt.butce_egrisi) ? opt.butce_egrisi : [];
  const points = curve
    .map((b) => ({ butce: b.butce_dk, c: (b.karsilastirmalar || []).find((x) => x.karsilastirma === 'plan_budget-b1_budget' && x.ad === ad) || null }))
    .filter((p) => p.c)
    .sort((a, b) => a.butce - b.butce);
  const significant = points.filter((p) => excludesZero(p.c)).length;
  return { points, total: points.length, significant };
}

/** "Eşit bütçede fark anlamlı mı?" cümlesi; karşılaştırma yoksa null yerine "yok" metni. */
export function equalBudgetSentence(eb) {
  const s = T.or.esit;
  if (!eb.total) return s.yok;
  return eb.significant === 0 ? s.anlamsiz(txt(eb.total)) : s.anlamli(txt(eb.significant), txt(eb.total));
}

/**
 * Maliyet oranı kaydırıcısı (<input type="range">): yalnızca ızgara noktalarına oturur.
 * o: {id, grid, index, showTau, onChange(index)}; {element, setIndex(i)} döndürür.
 */
export function tauSlider(o) {
  const s = T.or.slider;
  const { grid } = o;
  const input = el('input', {
    type: 'range',
    id: o.id,
    class: 'slider',
    min: 0,
    max: grid.length - 1,
    step: 1,
    value: o.index,
    'aria-describedby': `${o.id}-help`,
  });
  const out = el('output', { class: 'slider-out', for: o.id });

  function sync(i) {
    const g = grid[i];
    const kat = fmtRatio(g.maliyet_orani);
    out.textContent = txt(o.showTau ? `${s.kat(kat)} (${s.tau(fmtNum(g.tau, 2))})` : s.kat(kat));
    input.setAttribute('aria-valuetext', s.deger(kat));
  }

  input.addEventListener('input', () => {
    const i = Number(input.value);
    sync(i);
    o.onChange(i);
  });
  sync(o.index);

  const element = el(
    'div',
    { class: 'slider-box' },
    el('label', { class: 'slider-label', for: o.id }, s.soru),
    el('div', { class: 'slider-row' }, input, out),
    el('div', { class: 'slider-ends', 'aria-hidden': 'true' }, el('span', null, s.kat(fmtRatio(grid[0].maliyet_orani))), el('span', null, s.kat(fmtRatio(grid[grid.length - 1].maliyet_orani)))),
    el('p', { class: 'note', id: `${o.id}-help` }, s.ipucu),
  );
  return {
    element,
    setIndex(i) {
      input.value = String(i);
      sync(i);
    },
  };
}
