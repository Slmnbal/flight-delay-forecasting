// Yöntem sekmesinin üç açılır bölümü: sınırlılıklar, veri kaynakları ve lisanslar, sonuçlarla kaydedilen notlar.
// Bu modül bir sekme değildir; method.js her bölümü ilk açıldığında ilgili işlevle doldurur.

import { el, fill, sozlukLink } from '../dom.js';
import { loadOzet, loadHavalimanlari } from '../data.js';
import { fmtInt, safeHttpsUrl } from '../fmt.js';
import { T } from '../metin.js';
import { notlar, kaynakLisansNotu } from '../yerel.js';

export async function limits(root) {
  const t = T.yontem.sinirlar;
  const [ozet, airports] = await Promise.all([loadOzet(), loadHavalimanlari()]);
  const withheld = airports.havalimanlari.filter((a) => a.gizleme_nedeni).map((a) => a.iata);
  fill(
    root,
    el(
      'ul',
      { class: 'points' },
      t.maddeler(fmtInt(ozet.kapsam.havalimani_sayisi)).map((line) => el('li', null, line)),
      withheld.length ? el('li', null, t.gizlenen(withheld.join(', ')), ' ', sozlukLink('tek-havayolu-kurali')) : null,
    ),
  );
}

export async function sources(root) {
  const t = T.yontem.kaynaklar;
  const ozet = await loadOzet();
  fill(
    root,
    el(
      'ul',
      { class: 'source-list' },
      ozet.proje.kaynaklar.map((s, i) => {
        const href = safeHttpsUrl(s.url);
        return el(
          'li',
          null,
          el('p', null, el('strong', null, s.ad)),
          el('p', { class: 'src-url' }, href ? el('a', { href, rel: 'noopener noreferrer' }, s.url) : s.url),
          el('p', null, kaynakLisansNotu(ozet, i)),
        );
      }),
      // Harita atfı: eyalet sınırları yerel dosyadan okunur (Natural Earth, kamu malı).
      el('li', null, el('p', null, el('strong', null, t.harita)), el('p', null, t.haritaAyrinti)),
    ),
    el('p', { class: 'note' }, t.not),
  );
}

export async function notes(root) {
  const t = T.yontem.notlar;
  const ozet = await loadOzet();
  const list = notlar(ozet);
  fill(root, list.length ? el('ul', { class: 'points' }, list.map((n) => el('li', null, n))) : el('p', { class: 'muted' }, t.yok));
}
