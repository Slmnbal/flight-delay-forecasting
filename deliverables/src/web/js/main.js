// Giriş noktası: hash yönlendirici (#overview, #routes/ORD, #sozluk/b1 ...), tema düğmesi, alt bilgi.
// Tek sayfa, birkaç bölüm; her bölüm verisini ilk açıldığında yükler.

import { el, fill, loadingNode } from './dom.js';
import { loadOzet, loadManifest } from './data.js';
import { T } from './metin.js';
import { txt } from './fmt.js';

const VIEWS = ['overview', 'airports', 'routes', 'calibration', 'weather', 'errors', 'about', 'sozluk'];
const TITLES = T.bolumler;
const SITE_TITLE = T.siteBasligi;

const loaders = {
  overview: () => import('./views/overview.js'),
  airports: () => import('./views/airports.js'),
  routes: () => import('./views/routes.js'),
  calibration: () => import('./views/calibration.js'),
  weather: () => import('./views/weather.js'),
  errors: () => import('./views/errors.js'),
  about: () => import('./views/about.js'),
  sozluk: () => import('./views/sozluk.js'),
};

const records = new Map(); // bölüm adı -> {mod, promise}

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const parts = raw
    .split('/')
    .filter(Boolean)
    .map((p) => {
      try {
        return decodeURIComponent(p);
      } catch (err) {
        return p;
      }
    });
  if (VIEWS.includes(parts[0])) return { name: parts[0], params: parts.slice(1) };
  return { name: 'overview', params: [] };
}

function errorNode(err, retry) {
  const message = err && err.message ? err.message : T.ortak.bilinmeyenHata;
  return el(
    'div',
    { class: 'error', role: 'alert' },
    el('p', null, el('strong', null, T.hata.baslik)),
    el('p', null, message),
    el('p', null, T.hata.diskUyarisi),
    el('button', { type: 'button', class: 'btn', onclick: retry }, T.hata.yenidenYukle),
  );
}

function mountView(name, params) {
  const body = document.querySelector(`#view-${name} [data-view-body]`);
  let rec = records.get(name);
  if (rec) {
    rec.promise.then(() => {
      if (rec.mod && typeof rec.mod.onParams === 'function') rec.mod.onParams(params);
    }).catch(() => {});
    return;
  }
  rec = { mod: null, promise: null };
  records.set(name, rec);
  fill(body, loadingNode());
  rec.promise = (async () => {
    const mod = await loaders[name]();
    await mod.mount(body, params);
    rec.mod = mod;
  })();
  rec.promise.catch((err) => {
    records.delete(name);
    fill(body, errorNode(err, () => mountView(name, parseHash().params)));
  });
}

function show(userNavigation) {
  const { name, params } = parseHash();
  for (const view of VIEWS) {
    document.getElementById(`view-${view}`).hidden = view !== name;
  }
  for (const link of document.querySelectorAll('[data-nav]')) {
    if (link.dataset.nav === name) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  document.title = `${TITLES[name]} – ${SITE_TITLE}`;
  mountView(name, params);
  // Sözlükte belirli bir terime gidilirken sayfa başına dönülmez; bölüm terime kendisi gider.
  const toTerm = name === 'sozluk' && params.length > 0;
  if (userNavigation && !toTerm) {
    window.scrollTo(0, 0);
    const heading = document.getElementById(`h-${name}`);
    if (heading) heading.focus();
  }
}

// Tema: otomatik (sistem) -> açık -> koyu
const MODES = ['auto', 'light', 'dark'];
const MODE_NAME = { auto: T.tema.otomatik, light: T.tema.acik, dark: T.tema.koyu };

function currentMode() {
  const attr = document.documentElement.getAttribute('data-theme');
  return attr === 'light' || attr === 'dark' ? attr : 'auto';
}

function applyMode(mode) {
  const root = document.documentElement;
  if (mode === 'auto') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', mode);
  try {
    if (mode === 'auto') window.localStorage.removeItem('theme');
    else window.localStorage.setItem('theme', mode);
  } catch (err) {
    // Depolama kullanılamayabilir; seçim yalnızca bu ziyaret boyunca geçerli olur.
  }
  const button = document.getElementById('theme-toggle');
  button.textContent = T.temaDugmesi(MODE_NAME[mode]);
  button.setAttribute('aria-label', T.temaEtiketi(MODE_NAME[mode]));
}

function initTheme() {
  applyMode(currentMode());
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const next = MODES[(MODES.indexOf(currentMode()) + 1) % MODES.length];
    applyMode(next);
  });
}

async function initFooter() {
  try {
    const [ozet, manifest] = await Promise.all([loadOzet(), loadManifest()]);
    document.getElementById('footer-disclaimer').textContent = txt(ozet.proje.sorumluluk_reddi);
    document.getElementById('footer-build').textContent = T.altBilgi.uretim(txt(manifest.olusturma_zamani), txt(manifest.model_surumu));
    if (ozet.ornek === true || manifest.ornek === true) document.getElementById('sample-banner').hidden = false;
  } catch (err) {
    // Bölümler kendi hata iletilerini gösterir; statik alt bilgi notu kalır.
  }
}

function initSkipLink() {
  document.getElementById('skip-link').addEventListener('click', (event) => {
    event.preventDefault();
    document.getElementById('main').focus();
  });
}

initTheme();
initSkipLink();
window.addEventListener('hashchange', () => show(true));
show(false);
initFooter();
