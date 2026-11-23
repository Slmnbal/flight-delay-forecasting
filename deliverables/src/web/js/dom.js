// Küçük DOM yardımcıları. Her şey DOM API'leriyle kurulur (createElement, textContent,
// setAttribute); veri değerleri asla işaretleme olarak çözümlenmez.

import { T } from './metin.js';
import { terimAdi } from './sozluk-terimleri.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

function applyAttrs(node, attrs) {
  if (!attrs) return;
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') {
      node.setAttribute('class', value);
    } else if (key.startsWith('on')) {
      if (typeof value !== 'function') throw new TypeError('Olay işleyicileri işlev olmalı');
      node.addEventListener(key.slice(2), value);
    } else {
      node.setAttribute(key, value === true ? '' : String(value));
    }
  }
}

/** null, undefined ve false çocukları atlanır; "null" metni asla yazılmaz. */
function toNodes(children) {
  const out = [];
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    out.push(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return out;
}

function appendAll(node, children) {
  node.append(...toNodes(children));
}

export function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  applyAttrs(node, attrs);
  appendAll(node, children);
  return node;
}

export function svg(tag, attrs, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  applyAttrs(node, attrs);
  appendAll(node, children);
  return node;
}

/**
 * Bir düğümün içeriğini değiştirir. replaceChildren(null) "null" metni yazar; bu yüzden
 * argümanlı replaceChildren çağrısı yalnızca bu dosyada yapılır, diğer her yer fill() kullanır.
 */
export function fill(node, ...children) {
  node.replaceChildren(...toNodes(children));
}

/** Sözlükte bir terime bağlantı; metin verilmezse terimin seçili dildeki adı kullanılır. */
export function sozlukLink(id, text) {
  return el('a', { href: `#sozluk/${id}`, class: 'term-link' }, text === undefined ? terimAdi(id) : text);
}

/**
 * Teknik sekmelerin başındaki kısa "Ne anlama geliyor?" kutusu.
 * key: T.anlam içindeki metin anahtarı; terimler: sözlük kimlikleri (isteğe bağlı).
 */
export function anlamKutusu(key, terimler = []) {
  const links = [];
  terimler.forEach((id, i) => {
    if (i > 0) links.push(', ');
    links.push(sozlukLink(id));
  });
  return el(
    'aside',
    { class: 'meaning', 'aria-label': T.anlam.baslik },
    el('h3', { class: 'meaning-title' }, T.anlam.baslik),
    el('p', null, T.anlam[key]),
    links.length ? el('p', { class: 'note' }, T.ortak.sozluk, links, '.') : null,
  );
}

let counter = 0;
export function uniqueId(prefix = 'id') {
  counter += 1;
  return `${prefix}-${counter}`;
}

/** <select> öğesini [{value, label}] seçenekleriyle doldurur; `value` varsa onu seçer. */
export function fillSelect(selectEl, options, value) {
  selectEl.replaceChildren(...options.map((o) => el('option', { value: o.value }, o.label)));
  if (options.some((o) => o.value === value)) selectEl.value = value;
  else if (options.length) selectEl.value = options[0].value;
}

/** Etiketli bir <select>. {wrap, select} döndürür. */
export function selectField(label, options, value, onChange) {
  const select = el('select');
  fillSelect(select, options, value);
  select.addEventListener('change', () => onChange(select.value));
  const wrap = el('label', { class: 'field' }, el('span', null, label), select);
  return { wrap, select };
}

export function loadingNode(text = T.ortak.yukleniyor) {
  return el('p', { class: 'status', role: 'status' }, text);
}

export function note(text, cls = 'note') {
  return el('p', { class: cls }, text);
}
