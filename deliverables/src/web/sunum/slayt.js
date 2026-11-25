// Slayt iskeleti: her slayt bir <section>; içinde mesajı söyleyen başlık (h2), büyük ana görsel ve yan panel.
// Yan panel: "Önemli rakamlar" (2-4 madde), "Nasıl okunur", "Ne anlama geliyor" ve ayrıntı bağlantısı.
// Hiçbir sayı burada üretilmez; çağıran biçimlenmiş değerleri verir (hepsi veri dosyalarından gelir).

import { el, fill } from '../js/dom.js';
import { T } from '../js/metin.js';
import { icon } from '../js/simgeler.js';

/** keys: [{label, value}] ya da null; dl listesini kurar. */
function keyList(keys) {
  return el(
    'dl',
    { class: 'key-nums' },
    keys.map((k) => el('div', null, el('dt', null, k.label), el('dd', null, k.value))),
  );
}

/**
 * o: {n (slayt sırası), ico (simge adı), title, figure (düğüm ya da liste), keys, how, means, href (detay sitesi
 * bağlantısı; '../#results' gibi), extra (panel sonuna eklenen düğümler), cls}
 * Döner: {node, setKeys(keys)}.
 */
export function slide(o) {
  const t = T.sunum.ortak;
  const hid = `sl-${o.n}`;
  const keysBox = el('section', { class: 'pn-keys', 'aria-labelledby': `${hid}-k` });
  const setKeys = (keys) => {
    fill(keysBox, keys && keys.length ? [el('h3', { id: `${hid}-k` }, t.rakamlar), keyList(keys)] : null);
    keysBox.hidden = !(keys && keys.length);
  };
  setKeys(o.keys);

  const panel = el(
    'aside',
    { class: 'slide-panel', 'aria-label': `${t.rakamlar}, ${t.nasil}` },
    keysBox,
    o.how ? el('section', { class: 'pn-how', 'aria-labelledby': `${hid}-h` }, el('h3', { id: `${hid}-h` }, t.nasil), el('p', null, o.how)) : null,
    o.means ? el('section', { class: 'pn-means', 'aria-labelledby': `${hid}-m` }, el('h3', { id: `${hid}-m` }, t.anlam), el('p', { class: 'means-text' }, o.means)) : null,
    o.extra || null,
    o.href ? el('p', { class: 'details-link' }, el('a', { href: o.href }, t.ayrinti)) : null,
  );

  const node = el(
    'section',
    { class: `slide${o.cls ? ` ${o.cls}` : ''}`, id: `slayt-${o.n}`, 'aria-labelledby': hid },
    el('h2', { id: hid, class: 'slide-title', tabindex: '-1' }, o.ico ? icon(o.ico, { size: 28, class: 'step-ico' }) : null, el('span', null, o.title)),
    el('div', { class: 'slide-body' }, el('div', { class: 'slide-main' }, o.figure), panel),
  );
  return { node, setKeys };
}

/** Verisi yüklenemeyen slayt: başlık yerine kısa uyarı. */
export function unavailable(n) {
  return slide({ n, ico: 'info', title: T.bolumler.story, figure: el('p', { class: 'muted' }, T.hikaye.yok) });
}
