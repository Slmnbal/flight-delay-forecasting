// Yöntem: kalibrasyon ve kapsama, hava deneyi, hata analizi, sınırlılıklar, kaynaklar ve notlar açılır
// bölümlerdir (başlıkta bir cümlelik özet); her bölüm ilk açıldığında yüklenir. Sayfanın sonunda
// "Bu proje hakkında" kutusu vardır. #method/weather gibi adresler ilgili bölümü açar.

import { el, fill, loadingNode } from '../dom.js';
import { T, AUTHOR } from '../metin.js';
import { authorLinkNodes } from '../yazar.js';

const SECTIONS = [
  { id: 'calibration', key: 'kalibrasyon', run: async (body) => (await import('./calibration.js')).mount(body) },
  { id: 'weather', key: 'hava', run: async (body) => (await import('./weather.js')).mount(body) },
  { id: 'errors', key: 'hatalar', run: async (body) => (await import('./errors.js')).mount(body) },
  { id: 'limits', key: 'sinirlar', run: async (body) => (await import('./about.js')).limits(body) },
  { id: 'sources', key: 'kaynaklar', run: async (body) => (await import('./about.js')).sources(body) },
  { id: 'notes', key: 'notlar', run: async (body) => (await import('./about.js')).notes(body) },
];

let built = [];

function errorNode(err, retry) {
  return el(
    'div',
    { class: 'error', role: 'alert' },
    el('p', null, el('strong', null, T.hata.baslik), err && err.message ? err.message : T.ortak.bilinmeyenHata),
    el('button', { type: 'button', class: 'btn', onclick: retry }, T.hata.yenidenDene),
  );
}

function ensure(entry) {
  if (entry.started) return;
  entry.started = true;
  fill(entry.body, loadingNode());
  entry.sec.run(entry.body).catch((err) => {
    entry.started = false;
    fill(entry.body, errorNode(err, () => ensure(entry)));
  });
}

function open(id, scroll) {
  const entry = built.find((e) => e.sec.id === id);
  if (!entry) return;
  entry.details.open = true;
  ensure(entry);
  if (scroll) {
    entry.details.scrollIntoView();
    entry.summary.focus({ preventScroll: true });
  }
}

export function onParams(params) {
  if (params && params[0]) open(params[0], true);
}

function aboutBox() {
  const t = T.hakkimda;
  return el(
    'section',
    { class: 'about-box stack', 'aria-labelledby': 'about-h' },
    el('h3', { id: 'about-h' }, t.baslik),
    el('p', null, t.metin),
    el('p', null, el('strong', null, t.yazar), AUTHOR),
    el('p', { class: 'about-links' }, authorLinkNodes()),
  );
}

export async function mount(root, params) {
  built = SECTIONS.map((sec) => {
    const t = T.yontem[sec.key];
    const summary = el('summary', null, el('span', { class: 'fold-title' }, t.baslik), el('span', { class: 'fold-sub' }, t.ozet));
    const body = el('div', { class: 'fold-body stack' });
    const details = el('details', { class: 'fold', id: `m-${sec.id}` }, summary, body);
    const entry = { sec, details, summary, body, started: false };
    details.addEventListener('toggle', () => {
      if (details.open) ensure(entry);
    });
    return entry;
  });
  fill(root, el('p', { class: 'lede' }, T.yontem.giris), el('div', { class: 'folds stack' }, built.map((e) => e.details)), aboutBox());
  if (params && params[0]) open(params[0], false);
}
