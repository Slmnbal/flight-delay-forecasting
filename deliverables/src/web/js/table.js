// Sıralanabilir tablo; isteğe bağlı sütun grupları ve "daha fazla göster" sayfalaması.
// Sıralama sütuna göredir (sade bir tablo özelliği); hiçbir kuruluşun sıralaması değildir.

import { el } from './dom.js';
import { T } from './metin.js';
import { fmtInt } from './fmt.js';

/**
 * columns: [{key, label, title?, numeric?, sortable?, sortValue?(row), render?(row)}]
 * groups:  [{label, span}] (isteğe bağlı, sütun başlıklarının üstünde ek satır)
 */
export function createTable({ columns, groups, caption, label, rows = [], sort = null, pageSize = 0, sticky = false, emptyText = T.tablo.bos }) {
  let data = rows;
  let sortState = sort ? { ...sort } : null;
  let shown = pageSize > 0 ? pageSize : Infinity;
  const headerRefs = new Map();

  const thead = el('thead');
  const tbody = el('tbody');
  const table = el('table', { class: sticky ? 'data sticky-first' : 'data' }, caption ? el('caption', null, caption) : null, thead, tbody);
  const wrap = el('div', { class: 'table-wrap', role: 'region', tabindex: '0', 'aria-label': label || caption || T.tablo.varsayilanEtiket }, table);
  const status = el('p', { class: 'table-status', role: 'status', 'aria-live': 'polite' });
  const more = el('button', {
    type: 'button',
    class: 'btn table-more',
    onclick: () => {
      shown += pageSize;
      renderBody();
    },
  }, T.tablo.dahaFazla);
  const element = el('div', null, wrap, status, more);

  function sortAttr(col) {
    if (!sortState || sortState.key !== col.key) return 'none';
    return sortState.dir === 'desc' ? 'descending' : 'ascending';
  }

  function arrowFor(col) {
    if (!sortState || sortState.key !== col.key) return '';
    return sortState.dir === 'desc' ? '▼' : '▲';
  }

  function statusText(shownCount, total) {
    return total ? T.tablo.durum(fmtInt(Math.min(shownCount, total)), fmtInt(total)) : '';
  }

  function updateHeader() {
    for (const col of columns) {
      const ref = headerRefs.get(col.key);
      if (!ref || col.sortable === false) continue;
      ref.th.setAttribute('aria-sort', sortAttr(col));
      ref.arrow.textContent = arrowFor(col);
    }
  }

  function buildHeader() {
    thead.replaceChildren();
    if (groups) {
      thead.append(el('tr', { class: 'group-row' }, groups.map((g) => el('th', { scope: 'colgroup', colspan: g.span }, g.label))));
    }
    const tr = el('tr');
    for (const col of columns) {
      const th = el('th', { scope: 'col', class: col.numeric ? 'num' : null });
      if (col.sortable === false) {
        th.append(col.label);
      } else {
        const arrow = el('span', { class: 'arrow', 'aria-hidden': 'true' });
        const button = el('button', {
          type: 'button',
          class: 'sort',
          title: col.title || null,
          onclick: () => toggleSort(col),
        }, col.label, ' ', arrow);
        th.append(button);
        headerRefs.set(col.key, { th, arrow });
      }
      tr.append(th);
    }
    thead.append(tr);
    updateHeader();
  }

  function toggleSort(col) {
    if (sortState && sortState.key === col.key) {
      sortState = { key: col.key, dir: sortState.dir === 'asc' ? 'desc' : 'asc' };
    } else {
      sortState = { key: col.key, dir: 'asc' };
    }
    shown = pageSize > 0 ? pageSize : Infinity;
    updateHeader();
    renderBody();
  }

  function sortedRows() {
    if (!sortState) return data;
    const col = columns.find((c) => c.key === sortState.key);
    if (!col) return data;
    const dir = sortState.dir === 'desc' ? -1 : 1;
    const valueOf = (row) => (col.sortValue ? col.sortValue(row) : row[col.key]);
    return [...data].sort((a, b) => {
      const x = valueOf(a);
      const y = valueOf(b);
      const xNull = x === null || x === undefined;
      const yNull = y === null || y === undefined;
      if (xNull || yNull) return xNull && yNull ? 0 : xNull ? 1 : -1; // boş değerler hep sonda
      if (typeof x === 'string' || typeof y === 'string') {
        return String(x).localeCompare(String(y), 'tr', { numeric: true }) * dir;
      }
      return (x - y) * dir;
    });
  }

  function renderBody() {
    const all = sortedRows();
    const slice = all.slice(0, shown);
    tbody.replaceChildren();
    if (!all.length) {
      tbody.append(el('tr', null, el('td', { colspan: columns.length }, emptyText)));
    }
    for (const row of slice) {
      const tr = el('tr');
      columns.forEach((col, index) => {
        const content = col.render ? col.render(row) : row[col.key];
        const attrs = { class: col.numeric ? 'num' : null };
        tr.append(index === 0 && col.rowHeader ? el('th', { scope: 'row', ...attrs }, content) : el('td', attrs, content));
      });
      tbody.append(tr);
    }
    const total = all.length;
    status.textContent = statusText(slice.length, total);
    more.hidden = !(slice.length < total);
  }

  buildHeader();
  renderBody();

  return {
    element,
    setRows(newRows) {
      data = newRows;
      shown = pageSize > 0 ? pageSize : Infinity;
      renderBody();
    },
  };
}
