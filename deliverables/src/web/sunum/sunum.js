// Sunum sitesinin giriş noktası: slayt kabuğu. Her slayt tam ekran bir <section>; aynı anda yalnızca biri görünür
// (diğerleri inert). Gezinme: ◀ ▶ düğmeleri, klavye (← → PageUp PageDown Home End), dokunmatik kaydırma,
// ilerleme noktaları ve sayaç; her slaytın kendi adresi vardır (#0 kapak, #1 ... #11; yalnızca düz #sayı).
// Dil (EN | TR) ve tema detay sitesiyle aynı mekanizmayı kullanır (kabuk.js: localStorage "lang"/"theme", ?lang=).
// Slayt içerikleri ./slaytlar-liste.js içindedir; veri ../veri/ ve ../harita/ klasörlerinden okunur.

import { el, fill, loadingNode } from '../js/dom.js';
import { T, setLang, getLang } from '../js/metin.js';
import { txt } from '../js/fmt.js';
import { readLangParam, readStoredLang, storeLang, syncUrlLang, currentMode, applyMode, nextMode } from '../js/kabuk.js';
import { loadContext, buildSlides } from './slaytlar-liste.js';

const byId = (id) => document.getElementById(id);
const SWIPE_MIN = 60; // piksel
const NO_SWIPE = 'input, select, textarea, svg.map, .chart-box, .table-wrap';

let slides = []; // [{node}], 0 = kapak
let index = 0;
let generation = 0;
let ctx = null;

const last = () => Math.max(0, slides.length - 1);
const clamp = (i) => Math.min(Math.max(0, i), last());

/** Yalnızca düz "#sayı" adresleri slayt adresidir; başka her şey kapak sayılır. */
function parseHash() {
  const match = /^#(\d{1,2})$/.exec(window.location.hash);
  return match ? Number(match[1]) : 0;
}

// ---------------------------------------------------------------------- sabit metinler
function lookup(path) {
  return path.split('.').reduce((node, key) => (node === undefined || node === null ? undefined : node[key]), T);
}

function refreshThemeButton() {
  const button = byId('theme-toggle');
  const name = { auto: T.tema.otomatik, light: T.tema.acik, dark: T.tema.koyu }[currentMode()];
  button.textContent = T.temaDugmesi(name);
  button.setAttribute('aria-label', T.temaEtiketi(name));
}

function refreshFullscreenButton() {
  const on = Boolean(document.fullscreenElement);
  const button = byId('full-btn');
  fill(button, on ? T.sunum.tamEkranKapat : T.sunum.tamEkran);
  button.setAttribute('aria-pressed', on ? 'true' : 'false');
}

function refreshCounter() {
  fill(byId('counter'), index === 0 ? T.sunum.kapak : T.sunum.sayac(index, last()));
}

function applyStatic() {
  const lang = getLang();
  document.documentElement.setAttribute('lang', lang);
  for (const node of document.querySelectorAll('[data-t]')) node.textContent = txt(lookup(node.dataset.t));
  for (const node of document.querySelectorAll('[data-t-aria]')) node.setAttribute('aria-label', txt(lookup(node.dataset.tAria)));
  const description = document.querySelector('meta[name="description"]');
  if (description) description.setAttribute('content', T.meta.aciklama);
  for (const button of document.querySelectorAll('[data-lang]')) button.setAttribute('aria-pressed', button.dataset.lang === lang ? 'true' : 'false');
  document.title = `${T.siteBasligi} – ${T.sunum.sunum}`;
  refreshThemeButton();
  refreshFullscreenButton();
  if (slides.length) {
    refreshCounter();
    labelDots();
  }
}

// ---------------------------------------------------------------------- noktalar
function labelDots() {
  byId('dots')
    .querySelectorAll('button')
    .forEach((button, i) => button.setAttribute('aria-label', i === 0 ? T.sunum.gitKapak : T.sunum.git(i)));
}

function buildDots() {
  fill(
    byId('dots'),
    slides.map((_, i) => el('li', null, el('button', { type: 'button', class: 'dot-btn', onclick: () => go(i) }))),
  );
  labelDots();
}

// ---------------------------------------------------------------------- gezinme
function titleOf(i) {
  const heading = byId(`sl-${i}`);
  return heading ? heading.textContent : '';
}

function show(i, userNavigation) {
  index = clamp(i);
  slides.forEach((s, k) => {
    const active = k === index;
    s.node.classList.toggle('is-active', active);
    if (active) {
      s.node.removeAttribute('inert');
      s.node.scrollTop = 0;
    } else {
      s.node.setAttribute('inert', '');
    }
  });
  byId('dots')
    .querySelectorAll('button')
    .forEach((button, k) => {
      if (k === index) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    });
  byId('prev').setAttribute('aria-disabled', index === 0 ? 'true' : 'false');
  byId('next').setAttribute('aria-disabled', index === last() ? 'true' : 'false');
  refreshCounter();
  if (userNavigation) {
    fill(byId('live'), index === 0 ? T.sunum.duyuruKapak(titleOf(0)) : T.sunum.duyuru(index, last(), titleOf(index)));
    const heading = byId(`sl-${index}`);
    if (heading) heading.focus({ preventScroll: true });
  }
}

/** Slayta git: adres değişir, hashchange slaytı gösterir (geri düğmesi slaytlar arasında çalışır). */
function go(i) {
  const target = clamp(i);
  if (target === index) return;
  window.location.hash = `#${target}`;
}

function onKey(e) {
  if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
  const tag = e.target && e.target.tagName;
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
  const moves = { ArrowRight: index + 1, PageDown: index + 1, ArrowLeft: index - 1, PageUp: index - 1, Home: 0, End: last() };
  if (!Object.prototype.hasOwnProperty.call(moves, e.key)) return;
  e.preventDefault();
  go(moves[e.key]);
}

function initSwipe() {
  const host = byId('slides');
  let start = null;
  host.addEventListener(
    'touchstart',
    (e) => {
      const target = e.target;
      if (e.touches.length !== 1 || (target && target.closest && target.closest(NO_SWIPE))) {
        start = null;
        return;
      }
      start = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    },
    { passive: true },
  );
  host.addEventListener(
    'touchend',
    (e) => {
      if (!start || !e.changedTouches.length) return;
      const dx = e.changedTouches[0].clientX - start.x;
      const dy = e.changedTouches[0].clientY - start.y;
      start = null;
      if (Math.abs(dx) >= SWIPE_MIN && Math.abs(dx) > 1.5 * Math.abs(dy)) go(index + (dx < 0 ? 1 : -1));
    },
    { passive: true },
  );
}

function initNav() {
  byId('prev').addEventListener('click', () => go(index - 1));
  byId('next').addEventListener('click', () => go(index + 1));
  document.addEventListener('keydown', onKey);
  window.addEventListener('hashchange', () => show(parseHash(), true));
  initSwipe();
}

// ---------------------------------------------------------------------- tam ekran
function initFullscreen() {
  const button = byId('full-btn');
  if (!document.fullscreenEnabled) {
    button.hidden = true; // Tam ekran desteklenmiyorsa (ör. iPhone) düğme gösterilmez.
    return;
  }
  button.addEventListener('click', () => {
    try {
      const request = document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
      if (request && typeof request.catch === 'function') request.catch(() => {});
    } catch (err) {
      // Tam ekran reddedilirse sessizce yok sayılır.
    }
  });
  document.addEventListener('fullscreenchange', refreshFullscreenButton);
}

// ---------------------------------------------------------------------- dil ve tema
function changeLang(lang) {
  if (lang === getLang()) return;
  setLang(lang);
  storeLang(lang);
  syncUrlLang(lang);
  applyStatic();
  mount();
}

function initLang() {
  const fromUrl = readLangParam();
  if (fromUrl) storeLang(fromUrl);
  setLang(fromUrl || readStoredLang() || 'en');
  for (const button of document.querySelectorAll('[data-lang]')) button.addEventListener('click', () => changeLang(button.dataset.lang));
  applyStatic();
}

function initTheme() {
  byId('theme-toggle').addEventListener('click', () => {
    applyMode(nextMode());
    refreshThemeButton();
  });
}

// ---------------------------------------------------------------------- slaytları kur
function errorNode(err) {
  const message = err && err.message ? err.message : T.ortak.bilinmeyenHata;
  return el(
    'div',
    { class: 'error', role: 'alert' },
    el('p', null, el('strong', null, T.hata.baslik)),
    el('p', null, message),
    el('p', null, T.hata.diskUyarisi),
    el('button', { type: 'button', class: 'btn', onclick: mount }, T.hata.yenidenYukle),
  );
}

async function mount() {
  generation += 1;
  const mine = generation;
  const host = byId('slides');
  slides = [];
  fill(host, loadingNode());
  try {
    if (!ctx) ctx = await loadContext();
    const built = await buildSlides(ctx, () => go(1));
    if (mine !== generation) return;
    slides = built;
    fill(host, built.map((s) => s.node));
    buildDots();
    show(parseHash(), false);
  } catch (err) {
    if (mine !== generation) return;
    fill(host, errorNode(err));
  }
}

initLang();
initTheme();
initFullscreen();
initNav();
byId('skip-link').addEventListener('click', (event) => {
  event.preventDefault();
  byId('slides').focus();
});
mount();
