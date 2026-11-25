// Sonuçlar (Results sekmesi; results.js bu modülü kullanır): başlık tablosu, kabul ölçütleri K1-K7,
// "neler işe yaramadı" kutusu ve açılır "bu sayılara ne kadar güvenmeli" bölümü.

import { el, fill, sozlukLink } from '../dom.js';
import { loadOzet, loadHava, metricOf } from '../data.js';
import { fmtMetricValue, fmtInterval, fmtPct, fmtInt, NA } from '../fmt.js';
import { T } from '../metin.js';
import { modelAciklamasi, kabulAciklamasi } from '../yerel.js';
import { icon } from '../simgeler.js';

// Etiketler dile göre okunur (dil değişince görünüm yeniden kurulur).
const verdictOf = (sonuc) => {
  const k = T.genel.kabul;
  if (sonuc === 'gecti') return { label: k.gecti, cls: 'pass', symbol: 'shield' };
  if (sonuc === 'kaldi') return { label: k.kaldi, cls: 'fail', symbol: 'alert' };
  return { label: k.degerlendirilmedi, cls: 'na', symbol: 'dash' };
};

export async function mount(root) {
  const [ozet, hava] = await Promise.all([loadOzet(), loadHava()]);
  fill(root, el('p', { class: 'lede' }, T.genel.giris), headline(ozet, hava), acceptance(ozet), trust(ozet));
}

function boardRow(label, value, interval, reference) {
  return el(
    'tr',
    null,
    el('th', { scope: 'row' }, label),
    el('td', { class: 'num' }, value),
    el('td', { class: 'ci' }, interval),
    el('td', { class: 'ref' }, reference),
  );
}

function headline(ozet, hava) {
  const p = T.genel.pano;
  const m = (task, model, name) => metricOf(ozet, task, model, name);
  const weatherGap = hava.farklar.find((f) => f.karsilastirma === 'T2-plan' && f.metrik.ad === 'roc_auc');
  const rocT2 = m('arrdel15', 'lgbm_T2', 'roc_auc');
  const rocB1 = m('arrdel15', 'B1', 'roc_auc');
  const prT2 = m('arrdel15', 'lgbm_T2', 'pr_auc');
  const prB1 = m('arrdel15', 'B1', 'pr_auc');
  // ROC-AUC ve PR-AUC satırlarındaki aralık, T2 modelinin B1'e göre farkının aralığıdır.
  const rocDiff = m('arrdel15', 'lgbm_T2', 'roc_auc_farki_b1');
  const prDiff = m('arrdel15', 'lgbm_T2', 'pr_auc_farki_b1');
  const vsB1 = (base, diff) => p.b1Referans(fmtMetricValue(base), diff ? `${fmtMetricValue(diff, true)}` : NA);
  const rows = [
    boardRow(p.rocSatiri, fmtMetricValue(rocT2), fmtInterval(rocDiff, true), vsB1(rocB1, rocDiff)),
    boardRow(p.prSatiri, fmtMetricValue(prT2), fmtInterval(prDiff, true), vsB1(prB1, prDiff)),
    boardRow(p.brierSatiri, fmtMetricValue(m('arrdel15', 'lgbm_T2', 'brier_skill')), fmtInterval(m('arrdel15', 'lgbm_T2', 'brier_skill')), p.sifirUstu),
    boardRow(p.egimSatiri, fmtMetricValue(m('arrdel15', 'lgbm_T2', 'kalibrasyon_egimi')), fmtInterval(m('arrdel15', 'lgbm_T2', 'kalibrasyon_egimi')), p.ideal('1')),
    boardRow(p.citlSatiri, fmtMetricValue(m('arrdel15', 'lgbm_T2', 'calibration_in_the_large')), fmtInterval(m('arrdel15', 'lgbm_T2', 'calibration_in_the_large')), p.ideal('0')),
    boardRow(p.p80Satiri, fmtMetricValue(m('kantil', 'lgbm_plan', 'kapsama_p80_conf')), fmtInterval(m('kantil', 'lgbm_plan', 'kapsama_p80_conf')), p.hedef(fmtPct(0.8))),
    boardRow(p.p95Satiri, fmtMetricValue(m('kantil', 'lgbm_plan', 'kapsama_p95_conf')), fmtInterval(m('kantil', 'lgbm_plan', 'kapsama_p95_conf')), p.hedef(fmtPct(0.95))),
  ];
  if (weatherGap) {
    rows.push(boardRow(p.havaSatiri, fmtMetricValue(weatherGap.metrik, true), fmtInterval(weatherGap.metrik, true), p.ayniUcuslar));
  }
  return el(
    'section',
    { 'aria-labelledby': 'ov-board' },
    el('h3', { id: 'ov-board' }, p.baslik),
    el(
      'div',
      { class: 'board-wrap' },
      el(
        'table',
        { class: 'board' },
        el('caption', null, p.aciklamaBaslik),
        el('thead', null, el('tr', null, el('th', { scope: 'col' }, p.olcut), el('th', { scope: 'col', class: 'num' }, p.sonuc), el('th', { scope: 'col' }, p.aralik), el('th', { scope: 'col' }, p.referans))),
        el('tbody', null, rows),
      ),
    ),
    el('p', { class: 'note' }, p.not, ' ', T.ortak.sozluk, sozlukLink('roc-auc'), ', ', sozlukLink('b1'), ', ', sozlukLink('citl'), '.'),
  );
}

function acceptance(ozet) {
  const k = T.genel.kabul;
  const kabul = ozet.kabul;
  const failed = kabul.filter((x) => x.sonuc === 'kaldi');
  const passed = kabul.filter((x) => x.sonuc === 'gecti');
  const summary = k.ozet(passed.length, kabul.length, failed.map((x) => x.olcut));

  const list = el('ul', { class: 'criteria' });
  for (const item of kabul) {
    const verdict = verdictOf(item.sonuc);
    list.append(
      el(
        'li',
        { class: item.sonuc === 'kaldi' ? 'is-fail' : null },
        el('span', { class: 'cid' }, item.olcut),
        el('span', { class: 'ctitle' }, kabulAciklamasi(ozet, item)),
        el('span', { class: `badge ${verdict.cls}` }, icon(verdict.symbol, { size: 16 }), verdict.label),
      ),
    );
  }

  const notes = [];
  if (failed.some((x) => x.olcut === 'K5')) {
    const p80 = metricOf(ozet, 'kantil', 'lgbm_plan', 'kapsama_p80_conf');
    const p95 = metricOf(ozet, 'kantil', 'lgbm_plan', 'kapsama_p95_conf');
    notes.push(el('p', null, el('strong', null, k.k5), k.k5Metin(fmtMetricValue(p80), fmtMetricValue(p95))));
  }
  if (failed.some((x) => x.olcut === 'K6')) {
    const plan = metricOf(ozet, 'iptal', 'lgbm_plan', 'pr_auc');
    const b1 = metricOf(ozet, 'iptal', 'B1', 'pr_auc');
    notes.push(el('p', null, el('strong', null, k.k6), k.k6Metin(fmtMetricValue(plan), fmtMetricValue(b1))));
  }
  return el(
    'section',
    { 'aria-labelledby': 'ov-accept', class: 'stack' },
    el('h3', { id: 'ov-accept' }, k.baslik),
    el('p', null, summary),
    notes.length ? el('div', { class: 'notice warn stack', role: 'note' }, el('h4', { class: 'with-ico' }, icon('alert'), el('span', null, k.kaldiBaslik)), notes) : null,
    list,
  );
}

function trust(ozet) {
  const g = T.genel.guven;
  const b = ozet.bolme;
  const k = ozet.kapsam;
  const splits = [
    [g.egitim, b.egitim, k.egitim_ucus_sayisi],
    [g.dogrulamaA, b.dogrulama_a, k.dogrulama_a_ucus_sayisi],
    [g.dogrulamaB, b.dogrulama_b, k.dogrulama_b_ucus_sayisi],
    [g.test, b.test, k.test_ucus_sayisi],
  ];
  const nf = k.ozellik_sayisi || {};
  const split = el(
    'div',
    { class: 'table-wrap' },
    el(
      'table',
      { class: 'data' },
      el('caption', null, g.bolmeBaslik),
      el('thead', null, el('tr', null, el('th', { scope: 'col' }, g.kume), el('th', { scope: 'col' }, g.baslangic), el('th', { scope: 'col' }, g.bitis), el('th', { scope: 'col', class: 'num' }, g.ucus))),
      el('tbody', null, splits.map(([name, d, n]) => el('tr', null, el('th', { scope: 'row' }, name), el('td', null, d.baslangic), el('td', null, d.bitis), el('td', { class: 'num' }, typeof n === 'number' ? fmtInt(n) : NA)))),
    ),
    typeof k.toplam_ucus_sayisi === 'number' && nf.plan && nf.T2
      ? el('p', { class: 'note' }, g.veriNotu(fmtInt(k.toplam_ucus_sayisi), fmtInt(nf.plan), fmtInt(nf.T2)))
      : null,
  );
  const modelList = el('dl', { class: 'stack' }, ozet.modeller.flatMap((md) => [el('dt', null, el('strong', null, md.kimlik)), el('dd', null, modelAciklamasi(ozet, md))]));
  return el(
    'details',
    { class: 'fold' },
    el('summary', null, g.baslik),
    el(
      'div',
      { class: 'two-col fold-body' },
      el('div', { class: 'stack' }, el('ul', { class: 'points' }, g.noktalar.map(([head, text]) => el('li', null, el('strong', null, head), text)))),
      el('div', { class: 'stack' }, split, el('h4', null, g.modeller), modelList),
    ),
  );
}
