// Giriş noktası: hash yönlendirici (#story, #results, #explore/ORD, #method/weather, #sozluk/b1 ...), dil
// düğmesi (EN | TR), tema düğmesi, alt bilgi. Tek sayfa, altı bölüm; her bölüm verisini ilk açıldığında yükler.
// Eski adresler (#overview, #airports, #routes/ORD, #optimization, #calibration, #weather, #errors, #about)
// yeni bölümlere yönlendirilir; paylaşılmış bağlantılar kırılmaz.
//
// Dil: varsayılan İngilizce. Seçim sırası: adres satırındaki ?lang=tr (ya da ?lang=en), sonra localStorage
// ("lang"; kullanılamıyorsa try/catch ile atlanır), sonra İngilizce. Düğmeye basınca <html lang>, sabit
// metinler ve açık bölüm yeniden çizilir (sayfa yenilenmez); seçim localStorage'a yazılır. Adreste
// ?lang= varsa o da güncellenir, böylece paylaşılan adres seçili dille açılır. #hash yalnızca bölümü
// belirler ve dilden bağımsızdır.

import { el, fill, loadingNode } from './dom.js';
import { loadOzet, loadManifest } from './data.js';
import { T, setLang, getLang, AUTHOR } from './metin.js';
import { txt } from './fmt.js';
import { sorumlulukReddi } from './yerel.js';
import { authorLinkNodes } from './yazar.js';
import { icon } from './simgeler.js';
import { readLangParam, readStoredLang, storeLang, syncUrlLang, currentMode, applyMode, nextMode } from './kabuk.js';

const VIEWS = ['story', 'results', 'explore', 'buffers', 'method', 'sozluk'];
const DEFAULT_VIEW = 'story';
const TITLES = T.bolumler;

// Eski adres -> [yeni bölüm, sabit parametreler...]; sabit parametre yoksa eski adresin kalanı taşınır.
const ALIASES = {
  overview: ['results'],
  airports: ['explore'],
  routes: ['explore'],
  optimization: ['buffers'],
  calibration: ['method', 'calibration'],
  weather: ['method', 'weather'],
  errors: ['method', 'errors'],
  about: ['method', 'limits'],
};

const loaders = {
  story: () => import('./views/story.js'),
  results: () => import('./views/results.js'),
  explore: () => import('./views/explore.js'),
  buffers: () => import('./views/buffers.js'),
  method: () => import('./views/method.js'),
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
  if (VIEWS.includes(parts[0])) return { name: parts[0], params: parts.slice(1), alias: false };
  if (Object.prototype.hasOwnProperty.call(ALIASES, parts[0])) {
    const [name, ...fixed] = ALIASES[parts[0]];
    return { name, params: fixed.length ? fixed : parts.slice(1), alias: true };
  }
  return { name: DEFAULT_VIEW, params: [], alias: false };
}

/** Eski adresi yeni bölümün adresiyle değiştirir (geçmişe yeni kayıt eklemez). */
function canonicalize(name, params) {
  try {
    const tail = params.length ? `/${params.map((p) => encodeURIComponent(p)).join('/')}` : '';
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${name}${tail}`);
  } catch (err) {
    // Adres güncellenemezse sayfa yine doğru bölümü gösterir.
  }
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
  const { name, params, alias } = parseHash();
  if (alias) canonicalize(name, params);
  for (const view of VIEWS) {
    document.getElementById(`view-${view}`).hidden = view !== name;
  }
  for (const link of document.querySelectorAll('[data-nav]')) {
    if (link.dataset.nav === name) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  document.title = `${TITLES[name]} – ${T.siteBasligi}`;
  mountView(name, params);
  // Sözlükte belirli bir terime, Yöntem'de belirli bir bölüme gidilirken sayfa başına dönülmez; bölüm kendisi gider.
  const toTerm = (name === 'sozluk' || name === 'method') && params.length > 0;
  if (userNavigation && !toTerm) {
    window.scrollTo(0, 0);
    const heading = document.getElementById(`h-${name}`);
    if (heading) heading.focus();
  }
}

// ---------------------------------------------------------------------- dil
// Dil ve tema okuma/yazma işlevleri kabuk.js içindedir (sunum sitesiyle ortak).
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
  setLang(fromUrl || readStoredLang() || 'en');
  for (const button of document.querySelectorAll('[data-lang]')) {
    button.addEventListener('click', () => changeLang(button.dataset.lang));
  }
  applyStatic();
}

// ---------------------------------------------------------------------- tema: otomatik (sistem) -> açık -> koyu
const modeName = (mode) => ({ auto: T.tema.otomatik, light: T.tema.acik, dark: T.tema.koyu })[mode];

function refreshThemeButton() {
  const button = document.getElementById('theme-toggle');
  const name = modeName(currentMode());
  button.textContent = T.temaDugmesi(name);
  button.setAttribute('aria-label', T.temaEtiketi(name));
}

function initTheme() {
  refreshThemeButton();
  document.getElementById('theme-toggle').addEventListener('click', () => {
    applyMode(nextMode());
    refreshThemeButton();
  });
}

async function initFooter() {
  const gen = generation;
  fill(document.getElementById('footer-author'), el('strong', null, T.altBilgi.yazar), AUTHOR, authorLinkNodes().length ? ' | ' : null, authorLinkNodes());
  try {
    const [ozet, manifest] = await Promise.all([loadOzet(), loadManifest()]);
    if (gen !== generation) return;
    document.getElementById('footer-disclaimer').textContent = txt(sorumlulukReddi(ozet));
    document.getElementById('footer-build').textContent = T.altBilgi.uretim(txt(manifest.olusturma_zamani).slice(0, 10));
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

/** Sekme başlıklarındaki simge yerleri (data-ico) satır içi SVG simgeyle doldurulur; metin yanındadır. */
function initIcons() {
  for (const slot of document.querySelectorAll('[data-ico]')) slot.append(icon(slot.dataset.ico, { size: 18 }));
}

initIcons();
initLang();
initTheme();
initSkipLink();
window.addEventListener('hashchange', () => show(true));
show(false);
initFooter();
