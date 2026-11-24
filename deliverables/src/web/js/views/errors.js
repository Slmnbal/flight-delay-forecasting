// Hata analizi: model başarımının segment kırılımları ve veri dosyasından alınan iki kısa liste,
// tarafsız başlıklar altında. Segmentler betimleyicidir; kalite sıralaması değildir.

import { el, fill, selectField, fillSelect, sozlukLink } from '../dom.js';
import { loadHata, loadHavalimanlari } from '../data.js';
import { fmtValue, fmtMetricValue, fmtInt, metricLabel, blockLabel, monthLabel, modelLabel, NA, txt } from '../fmt.js';
import { T } from '../metin.js';
import { barChart, mountChart } from '../charts.js';
import { createTable } from '../table.js';

const t = T.hataAnalizi;
const DIMENSION = t.boyut;

const dimensionLabel = (d) => DIMENSION[d] || txt(d);

function segmentLabel(dimension, segment) {
  if (dimension === 'saat_blogu') return blockLabel(segment);
  if (dimension === 'ay') return monthLabel(segment);
  if (dimension === 'olay_gunu') return segment === 'olay' ? t.olay : segment === 'diger' ? t.diger : txt(segment);
  return txt(segment);
}

function taskOf(block) {
  const names = new Set(block.segmentler.flatMap((s) => s.metrikler.map((m) => m.ad)));
  if (names.has('pinball_p80') || names.has('kapsama_p80_ham')) return t.gorevKantil;
  return t.gorevGecVaris;
}

function noteText(target) {
  return target !== null ? t.cubukNotuHedef(Math.round(target * 100)) : t.cubukNotu;
}

export async function mount(root) {
  const [hata, airportsFile] = await Promise.all([loadHata(), loadHavalimanlari()]);
  const blocks = hata.boyutlar;
  let current = 0;
  let metricName = null;

  const optionList = blocks.map((b, i) => ({ value: String(i), label: t.secenek(dimensionLabel(b.boyut), modelLabel(b.model), taskOf(b)) }));
  const dimField = selectField(t.kirilim, optionList, '0', (v) => {
    current = Number(v);
    metricName = null;
    render();
  });
  const metricSelect = selectField(t.cubukOlcut, [{ value: 'x', label: 'x' }], 'x', (v) => {
    metricName = v;
    renderChart();
  });

  const chartBox = el('div', { class: 'chart-box wide' });
  const chartNote = el('p', { class: 'note' });
  const tableHolder = el('div');
  const dimNote = el('div');
  let chartHandle = null;
  let chartBuild = null;

  function currentBlock() {
    return blocks[current];
  }

  function metricNames() {
    const seen = [];
    for (const s of currentBlock().segmentler) for (const m of s.metrikler) if (!seen.includes(m.ad)) seen.push(m.ad);
    return seen;
  }

  function unitOf(name) {
    for (const s of currentBlock().segmentler) {
      const m = s.metrikler.find((x) => x.ad === name);
      if (m) return m.birim;
    }
    return 'skor';
  }

  function render() {
    const block = currentBlock();
    const names = metricNames();
    if (!metricName || !names.includes(metricName)) metricName = names.includes('brier_skill') ? 'brier_skill' : names[0];
    fillSelect(metricSelect.select, names.map((n) => ({ value: n, label: metricLabel(n) })), metricName);

    const rows = block.segmentler.map((s) => ({
      segment: s.segment,
      label: segmentLabel(block.boyut, s.segment),
      n: s.n,
      metrics: Object.fromEntries(s.metrikler.map((m) => [m.ad, m])),
    }));
    const table = createTable({
      caption: t.tabloBaslik(dimensionLabel(block.boyut), modelLabel(block.model)),
      label: t.tabloEtiket,
      sticky: true,
      rows,
      columns: [
        { key: 'label', label: t.segment, rowHeader: true, sortValue: (r) => (block.boyut === 'saat_blogu' || block.boyut === 'ay' ? r.segment : r.label), render: (r) => r.label },
        { key: 'n', label: t.ucus, numeric: true, render: (r) => fmtInt(r.n) },
        ...names.map((n) => ({
          key: n,
          label: metricLabel(n),
          numeric: true,
          sortValue: (r) => (r.metrics[n] ? r.metrics[n].deger : null),
          render: (r) => (r.metrics[n] ? fmtMetricValue(r.metrics[n]) : NA),
        })),
      ],
    });
    fill(tableHolder, table.element);

    // "Olay günü" tanımı sayfada elle yazılmaz: Hakkında bölümündeki Notlar kutusu ve Sözlük kullanılır.
    const notes = [];
    if (block.boyut === 'olay_gunu') {
      notes.push(el('p', { class: 'note' }, T.ortak.sozluk, sozlukLink('olay-gunu'), '.'));
    }
    if (block.boyut === 'origin') {
      const shown = new Set(block.segmentler.map((s) => s.segment));
      const missing = airportsFile.havalimanlari.filter((a) => !shown.has(a.iata)).map((a) => a.iata);
      if (missing.length) notes.push(el('p', { class: 'note' }, t.eksikler(missing.join(', '))));
    }
    fill(dimNote, notes);
    renderChart();
  }

  function renderChart() {
    const block = currentBlock();
    const unit = unitOf(metricName);
    const isCoverage = /^kapsama_p(80|95)/.test(metricName);
    const target = isCoverage ? (metricName.includes('p80') ? 0.8 : 0.95) : null;
    const items = block.segmentler.map((s) => {
      const m = s.metrikler.find((x) => x.ad === metricName);
      return { label: segmentLabel(block.boyut, s.segment), value: m ? m.deger : null, text: m ? fmtValue(m.deger, m.ad, m.birim) : T.ortak.yok };
    });
    chartNote.textContent = noteText(target);
    chartBuild = (width) =>
      barChart({
        width,
        items,
        refs: target !== null ? [{ value: target }] : [],
        tickFormat: (tick) => fmtValue(tick, metricName, unit),
        title: t.cubukBaslik(metricLabel(metricName)),
        desc: t.cubukAciklama(metricLabel(metricName), dimensionLabel(block.boyut), modelLabel(block.model)),
      });
    if (chartHandle) chartHandle.redraw();
    else chartHandle = mountChart(chartBox, (width) => chartBuild(width));
  }

  // Veri dosyasındaki listeler, tarafsız başlıklarla.
  const lists = [];
  const grouped = new Map();
  for (const item of hata.en_kotu || []) {
    const key = item.metrik.ad;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(item);
  }
  for (const [name, items] of grouped) {
    const heading = t.listeBaslik[name] || t.listeGenel(metricLabel(name));
    lists.push(
      el(
        'div',
        { class: 'stack' },
        el('h4', null, heading),
        el(
          'div',
          { class: 'table-wrap' },
          el(
            'table',
            { class: 'data' },
            el('caption', null, heading),
            el('thead', null, el('tr', null, el('th', { scope: 'col' }, t.segment), el('th', { scope: 'col', class: 'num' }, t.ucus), el('th', { scope: 'col', class: 'num' }, metricLabel(name)))),
            el('tbody', null, items.map((it) => el('tr', null, el('th', { scope: 'row' }, `${dimensionLabel(it.boyut)}: ${segmentLabel(it.boyut, it.segment)}`), el('td', { class: 'num' }, fmtInt(it.n)), el('td', { class: 'num' }, fmtMetricValue(it.metrik))))),
          ),
        ),
      ),
    );
  }

  fill(
    root,
    el('p', null, t.giris, ' ', T.ortak.sozluk, sozlukLink('segment'), ', ', sozlukLink('kesifsel'), '.'),
    el('div', { class: 'controls' }, dimField.wrap, metricSelect.wrap),
    chartBox,
    chartNote,
    dimNote,
    tableHolder,
    lists.length
      ? el('section', { class: 'stack', 'aria-labelledby': 'err-lists' }, el('h4', { id: 'err-lists' }, t.iki), el('p', { class: 'note' }, t.ikiNot), el('div', { class: 'two-col' }, lists))
      : null,
  );
  render();
}
