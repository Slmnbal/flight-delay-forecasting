// Giriş noktası: hash yönlendirici (#story, #overview, #routes/ORD, #sozluk/b1 ...), dil düğmesi (TR | EN),
// tema düğmesi, alt bilgi. Tek sayfa, birkaç bölüm; her bölüm verisini ilk açıldığında yükler.
//
// Dil: varsayılan Türkçe. Seçim sırası: adres satırındaki ?lang=en (ya da ?lang=tr), sonra localStorage
// ("lang"; kullanılamıyorsa try/catch ile atlanır), sonra Türkçe. Düğmeye basınca <html lang>, sabit
// metinler ve açık bölüm yeniden çizilir (sayfa yenilenmez); seçim localStorage'a yazılır. Adreste
// ?lang= varsa o da güncellenir, böylece paylaşılan adres seçili dille açılır. #hash yalnızca bölümü
// belirler ve dilden bağımsızdır.

import { el, fill, loadingNode } from './dom.js';
import { loadOzet, loadManifest } from './data.js';
import { T, setLang, getLang } from './metin.js';
import { txt } from './fmt.js';
import { sorumlulukReddi } from './yerel.js';

const VIEWS = ['story', 'overview', 'airports', 'routes', 'optimization', 'calibration', 'weather', 'errors', 'about', 'sozluk'];
const DEFAULT_VIEW = 'story';
const TITLES = T.bolumler;

const loaders = {
  story: () => import('./views/story.js'),
  overview: () => import('./views/overview.js'),
  airports: () => import('./views/airports.js'),
  routes: () => import('./views/routes.js'),
  optimization: () => import('./views/optimization.js'),
  calibration: () => import('./views/calibration.js'),
  weather: () => import('./views/weather.js'),
  errors: () => import('./views/errors.js'),
  about: () => import('./views/about.js'),
  sozluk: () => import('./views/sozluk.js'),
};

const records = new Map(); // bölüm adı -> {mod, promise}
let generation = 0; // dil değişince artar; eski dildeki yüklemeler görünüme yazmaz

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
  return { name: DEFAULT_VIEW, params: [] };
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
  const gen = generation;
  fill(body, loadingNode());
  rec.promise = (async () => {
    const mod = await loaders[name]();
    if (gen !== generation) return;
    await mod.mount(body, params);
    rec.mod = mod;
  })();
  rec.promise.catch((err) => {
    if (gen !== generation) return;
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
  document.title = `${TITLES[name]} – ${T.siteBasligi}`;
  mountView(name, params);
  // Sözlükte belirli bir terime gidilirken sayfa başına dönülmez; bölüm terime kendisi gider.
  const toTerm = name === 'sozluk' && params.length > 0;
  if (userNavigation && !toTerm) {
    window.scrollTo(0, 0);
    const heading = document.getElementById(`h-${name}`);
    if (heading) heading.focus();
  }
}

// ---------------------------------------------------------------------- dil
function readLangParam() {
  try {
    const value = new URLSearchParams(window.location.search).get('lang');
    return value === 'en' || value === 'tr' ? value : null;
  } catch (err) {
    return null;
  }
}

function readStoredLang() {
  try {
    const value = window.localStorage.getItem('lang');
    return value === 'en' || value === 'tr' ? value : null;
  } catch (err) {
    return null;
  }
}

function storeLang(lang) {
  try {
    window.localStorage.setItem('lang', lang);
  } catch (err) {
    // Depolama kullanılamayabilir; seçim yalnızca bu ziyaret boyunca geçerli olur.
  }
}

function syncUrlLang(lang) {
  if (readLangParam() === null) return;
  try {
    const params = new URLSearchParams(window.location.search);
    params.set('lang', lang);
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}${window.location.hash}`);
  } catch (err) {
    // Adres güncellenemezse seçim yine localStorage'da kalır.
  }
}

function lookup(path) {
  return path.split('.').reduce((node, key) => (node === undefined || node === null ? undefined : node[key]), T);
}

/** index.html'deki sabit metinler: data-t (metin) ve data-t-aria (aria-label) anahtarları T içindedir. */
function applyStatic() {
  const lang = getLang();
  document.documentElement.setAttribute('lang', lang);
  for (const node of document.querySelectorAll('[data-t]')) node.textContent = txt(lookup(node.dataset.t));
  for (const node of document.querySelectorAll('[data-t-aria]')) node.setAttribute('aria-label', txt(lookup(node.dataset.tAria)));
  const description = document.querySelector('meta[name="description"]');
  if (description) description.setAttribute('content', T.meta.aciklama);
  for (const button of document.querySelectorAll('[data-lang]')) {
    button.setAttribute('aria-pressed', button.dataset.lang === lang ? 'true' : 'false');
  }
  refreshThemeButton();
}

function changeLang(lang) {
  if (lang === getLang()) return;
  setLang(lang);
  storeLang(lang);
  syncUrlLang(lang);
  applyStatic();
  // Bütün görünümler seçili dilde yeniden kurulur; açık olan hemen, diğerleri açıldığında.
  generation += 1;
  records.clear();
  for (const view of VIEWS) fill(document.querySelector(`#view-${view} [data-view-body]`));
  show(false);
  initFooter();
}

function initLang() {
  const fromUrl = readLangParam();
  if (fromUrl) storeLang(fromUrl);
  setLang(fromUrl || readStoredLang() || 'tr');
  for (const button of document.querySelectorAll('[data-lang]')) {
    button.addEventListener('click', () => changeLang(button.dataset.lang));
  }
  applyStatic();
}

// ---------------------------------------------------------------------- tema: otomatik (sistem) -> açık -> koyu
const MODES = ['auto', 'light', 'dark'];
const modeName = (mode) => ({ auto: T.tema.otomatik, light: T.tema.acik, dark: T.tema.koyu })[mode];

function currentMode() {
  const attr = document.documentElement.getAttribute('data-theme');
  return attr === 'light' || attr === 'dark' ? attr : 'auto';
}

function refreshThemeButton() {
  const button = document.getElementById('theme-toggle');
  const name = modeName(currentMode());
  button.textContent = T.temaDugmesi(name);
  button.setAttribute('aria-label', T.temaEtiketi(name));
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
  refreshThemeButton();
}

function initTheme() {
  refreshThemeButton();
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const next = MODES[(MODES.indexOf(currentMode()) + 1) % MODES.length];
    applyMode(next);
  });
}

async function initFooter() {
  const gen = generation;
  try {
    const [ozet, manifest] = await Promise.all([loadOzet(), loadManifest()]);
    if (gen !== generation) return;
    document.getElementById('footer-disclaimer').textContent = txt(sorumlulukReddi(ozet));
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

initLang();
initTheme();
initSkipLink();
window.addEventListener('hashchange', () => show(true));
show(false);
initFooter();
