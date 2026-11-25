// Hikâye sekmesi: kısa bir giriş (soru, kapsam), "Sunumu aç" çağrısı ve "Kendin dene" etkileşimi.
// Slayt anlatımı sunum sitesine (../sunum/) taşındı; burada tekrar edilmez. Sayıların hepsi veri
// dosyalarından okunur (ozet, havalimanlari, rotalar/<IATA>); metinler metin.js / metin-en.js içindedir.

import { el, fill } from '../dom.js';
import { loadOzet, loadHavalimanlari, loadManifest } from '../data.js';
import { fmtInt, fmtPlain, monthLabel, safeHttpsUrl } from '../fmt.js';
import { T, REPO_URL } from '../metin.js';
import { icon } from '../simgeler.js';
import { buildTry } from '../kendin-dene.js';

function buildHero(ozet) {
  const t = T.hero;
  const saat = fmtPlain(ozet.bilgi_zamani_saat);
  const k = ozet.kapsam;
  const period = T.donem(monthLabel(String(ozet.bolme.test.baslangic).slice(0, 7)), monthLabel(String(ozet.bolme.test.bitis).slice(0, 7)));
  const repo = safeHttpsUrl(REPO_URL);
  return el(
    'section',
    { class: 'hero', 'aria-labelledby': 'hero-q' },
    el('p', { class: 'hero-q', id: 'hero-q' }, t.soru(saat)),
    el('p', { class: 'hero-ozet' }, t.ozet),
    el('p', { class: 'scope' }, t.kapsam(fmtInt(k.test_ucus_sayisi), fmtInt(k.havalimani_sayisi), period)),
    el(
      'p',
      { class: 'hero-actions' },
      el('a', { class: 'btn btn-present', href: './sunum/' }, T.sunum.ac),
      repo ? el('a', { class: 'btn', href: repo, rel: 'noopener' }, t.kod) : null,
    ),
  );
}

export async function mount(root) {
  const [ozet, airportsFile, manifest] = await Promise.all([loadOzet(), loadHavalimanlari(), loadManifest()]);
  const t = T.hikaye.s10;
  const tryIt = await buildTry(airportsFile, manifest, { base: '' });
  fill(
    root,
    buildHero(ozet),
    el('section', { class: 'story-step stack', 'aria-labelledby': 'st-try' }, el('h3', { id: 'st-try' }, icon('plane', { size: 24, class: 'step-ico' }), el('span', null, t.baslik)), tryIt),
  );
}
