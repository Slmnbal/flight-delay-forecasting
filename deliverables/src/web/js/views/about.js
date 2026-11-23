// Hakkında ve sınırlar: kapsam, gizlenenler, sınırlamalar, veri kaynakları ve lisanslar, notlar, üretim bilgisi.

import { el, fill, sozlukLink } from '../dom.js';
import { loadOzet, loadHavalimanlari, loadManifest } from '../data.js';
import { fmtInt, fmtPlain, safeHttpsUrl, txt } from '../fmt.js';
import { T } from '../metin.js';
import { notlar, kaynakLisansNotu, sorumlulukReddi } from '../yerel.js';

export async function mount(root) {
  const t = T.hakkinda;
  const [ozet, airports, manifest] = await Promise.all([loadOzet(), loadHavalimanlari(), loadManifest()]);
  const k = ozet.kapsam;
  const withheld = airports.havalimanlari.filter((a) => a.gizleme_nedeni).map((a) => a.iata);

  const sources = el(
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
  );

  const kb = (manifest.toplam_bayt / 1024).toFixed(0);
  const notes = notlar(ozet);

  fill(
    root,
    el(
      'section',
      { class: 'stack', 'aria-labelledby': 'ab-scope' },
      el('h3', { id: 'ab-scope' }, t.nedirBaslik),
      el('p', null, t.nedir(fmtInt(k.havalimani_sayisi), txt(k.veri_donemi.baslangic), txt(k.veri_donemi.bitis))),
      el('p', { class: 'notice' }, sorumlulukReddi(ozet)),
    ),
    el(
      'section',
      { class: 'stack', 'aria-labelledby': 'ab-rules' },
      el('h3', { id: 'ab-rules' }, t.gosterilmezBaslik),
      el(
        'ul',
        { class: 'points' },
        t.gosterilmez.map((line) => el('li', null, line)),
        withheld.length ? el('li', null, t.gizlenen(withheld.join(', ')), ' ', sozlukLink('tek-havayolu-kurali')) : null,
        el('li', null, t.tamponGosterilmez),
      ),
    ),
    el(
      'section',
      { class: 'stack', 'aria-labelledby': 'ab-limits' },
      el('h3', { id: 'ab-limits' }, t.sinirBaslik),
      el('ul', { class: 'points' }, t.sinirlar(fmtInt(k.havalimani_sayisi)).map((line) => el('li', null, line))),
    ),
    el('section', { class: 'stack', 'aria-labelledby': 'ab-src' }, el('h3', { id: 'ab-src' }, t.kaynakBaslik), sources, el('p', { class: 'note' }, t.kaynakNotu)),
    el(
      'section',
      { class: 'stack', 'aria-labelledby': 'ab-notes' },
      el('h3', { id: 'ab-notes' }, t.notlarBaslik),
      notes.length
        ? el('div', { class: 'notice stack' }, el('p', null, t.notlarGiris), el('ul', { class: 'points' }, notes.map((n) => el('li', null, n))))
        : el('p', { class: 'muted' }, t.notlarYok),
    ),
    el(
      'section',
      { class: 'stack', 'aria-labelledby': 'ab-build' },
      el('h3', { id: 'ab-build' }, t.dosyalarBaslik),
      el(
        'dl',
        { class: 'facts' },
        [
          [t.uretim, txt(manifest.olusturma_zamani)],
          [t.modelSurumu, txt(manifest.model_surumu)],
          [t.semaSurumu, txt(manifest.sema_surumu)],
          [t.dosyalar, t.dosyaOzeti(fmtInt(manifest.dosyalar.length), fmtPlain(Number(kb)))],
        ].map(([term, v]) => el('div', null, el('dt', null, term), el('dd', null, v))),
      ),
    ),
  );
}
