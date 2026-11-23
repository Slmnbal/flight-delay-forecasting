// Sözlük: gruplu terim listesi, istemci tarafı arama ve her terime bağlantı (#sozluk/terim).

import { el, fill } from '../dom.js';
import { T } from '../metin.js';
import { GRUPLAR, grupAdi, terimMetni } from '../sozluk-terimleri.js';

const t = T.sozluk;

/** Aramayı Türkçe harflere duyarsız yapar: "ısı" ve "isi", "şans" ve "sans" eşleşir (İngilizce metinde de zararsız). */
function normalize(text) {
  return String(text)
    .toLocaleLowerCase('tr')
    .replace(/ı/g, 'i')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}

let entries = [];
let ui = null;

function visibleCount() {
  return entries.filter((e) => !e.node.hidden).length;
}

function applyFilter(query) {
  const q = normalize(query).trim();
  for (const e of entries) e.node.hidden = q !== '' && !e.haystack.includes(q);
  for (const g of ui.groups) g.section.hidden = !g.entries.some((e) => !e.node.hidden);
  const shown = visibleCount();
  ui.status.textContent = T.sozluk.durum(shown, entries.length);
  ui.empty.hidden = shown !== 0;
}

function focusTerm(id) {
  const entry = entries.find((e) => e.id === id);
  if (!entry) return;
  if (entry.node.hidden) {
    ui.input.value = '';
    applyFilter('');
  }
  for (const e of entries) e.node.classList.toggle('is-target', e === entry);
  entry.node.scrollIntoView({ block: 'start' });
  entry.node.focus({ preventScroll: true });
}

export function onParams(params) {
  if (ui && params && params[0]) focusTerm(params[0]);
}

export async function mount(root, params) {
  entries = [];
  const groups = [];
  const groupEls = [];

  GRUPLAR.forEach((group, gi) => {
    const list = el('dl', { class: 'gloss-list' });
    const groupEntries = [];
    for (const raw of group.terimler) {
      const term = { id: raw.id, ...terimMetni(raw) };
      const node = el(
        'div',
        { class: 'term', id: `terim-${term.id}`, tabindex: '-1' },
        el('dt', null, el('a', { href: `#sozluk/${term.id}` }, term.terim)),
        el('dd', null, term.tanim),
        term.nerede ? el('dd', { class: 'where' }, el('strong', null, t.nerede), term.nerede) : null,
      );
      const entry = { id: term.id, node, haystack: normalize(`${term.terim} ${term.tanim} ${term.nerede || ''}`) };
      entries.push(entry);
      groupEntries.push(entry);
      list.append(node);
    }
    const headingId = `sz-g-${gi}`;
    const section = el('section', { class: 'stack gloss-group', 'aria-labelledby': headingId }, el('h3', { id: headingId }, grupAdi(group)), list);
    groups.push({ section, entries: groupEntries });
    groupEls.push(section);
  });

  const input = el('input', { type: 'search', id: 'sozluk-ara', class: 'gloss-input', autocomplete: 'off', 'aria-describedby': 'sozluk-durum', placeholder: t.araIpucu });
  input.addEventListener('input', () => applyFilter(input.value));
  const clear = el('button', {
    type: 'button',
    class: 'btn',
    onclick: () => {
      input.value = '';
      applyFilter('');
      input.focus();
    },
  }, t.temizle);
  const status = el('p', { id: 'sozluk-durum', class: 'note', role: 'status', 'aria-live': 'polite' });
  const empty = el('p', { class: 'notice', role: 'note', hidden: true }, t.bos);

  ui = { input, status, empty, groups };

  fill(
    root,
    el('p', null, t.giris),
    el('div', { class: 'controls' }, el('label', { class: 'field gloss-field', for: 'sozluk-ara' }, el('span', null, t.ara), input), clear),
    status,
    empty,
    groupEls,
  );
  applyFilter('');
  if (params && params[0]) focusTerm(params[0]);
}
