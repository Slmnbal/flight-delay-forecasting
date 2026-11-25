// Sunum slaytları: kapak ve bulgu slaytları (sorun, saat, risk grupları, güvenilirlik, hava). Her slayt
// mesajı söyleyen bir başlık + büyük ana görsel + yan panel (önemli rakamlar, nasıl okunur, ne anlama
// geliyor) + detay sitesine bağlantı taşır. Sayıların hepsi veri dosyalarından okunur (ozet, hata-analizi,
// kalibrasyon, hava-deneyi); metinler metin.js / metin-en.js içindedir. Elle yazılan tek değerler: "geç"
// tanımındaki eşik, birim grafikteki daire sayısı ve güven aralığı düzeyi (tanım gereği %95).

import { el } from '../js/dom.js';
import { findResult, findMetric, metricOf } from '../js/data.js';
import { fmtPct, fmtInt, fmtNum, fmtPlain, blockLabel, BLOCK_ORDER, monthLabel, safeHttpsUrl, txt } from '../js/fmt.js';
import { T, AUTHOR, REPO_URL } from '../js/metin.js';
import { authorLinkNodes } from '../js/yazar.js';
import { barChart, pictograph } from '../js/charts.js';
import { columnChart } from '../js/story-gorseller.js';
import { excludesZero } from '../js/or-ortak.js';
import { LATE_AFTER, COIN_FLIP, NEAR_ENOUGH, isNum, count100, PICTO_TOTAL, chartBox, wrapLabel, riskGroups, riskiest, figure } from '../js/hikaye-ortak.js';
import { slide, unavailable } from './slayt.js';

const CONFIDENCE = 0.95; // güven aralığı düzeyi (tanım gereği)

/** Geç varış oranı (tüm test uçuşları): modeller aynı uçuşlara baktığı için ilk geçerli değer. */
export function prevalenceOf(ozet) {
  for (const model of ['lgbm_T2', 'lgbm_plan', 'B1', 'B0']) {
    const m = findMetric(findResult(ozet, 'arrdel15', model), 'yayginlik');
    if (m && isNum(m.deger) && m.deger > 0) return m.deger;
  }
  return null;
}

const rateOf = (segment) => {
  const m = segment.metrikler.find((x) => x.ad === 'yayginlik');
  return m ? m.deger : null;
};

// ---------------------------------------------------------------------- kapak
export function cover(ctx, onStart) {
  const { ozet, kal } = ctx;
  const h = T.hero;
  const p = T.sunum;
  const rate = prevalenceOf(ozet);
  const k = ozet.kapsam;
  const saat = fmtPlain(ozet.bilgi_zamani_saat);
  const period = T.donem(monthLabel(String(ozet.bolme.test.baslangic).slice(0, 7)), monthLabel(String(ozet.bolme.test.bitis).slice(0, 7)));
  const bins = riskGroups(kal);
  const brief = [];
  if (rate) brief.push(T.hikaye.s1.baslik(fmtInt(Math.round(1 / rate))));
  if (bins) brief.push(T.hikaye.s3.baslik(riskiest(bins), { n: fmtInt(bins.length), deger: fmtInt(Math.max(1, Math.round(bins[0].gozlenen_oran * bins.length))) }));
  brief.push(T.hikaye.s7.baslik);
  const repo = safeHttpsUrl(REPO_URL);
  const x = rate ? fmtInt(count100(rate)) : null;
  const picto = rate
    ? el(
        'figure',
        { class: 'cover-fig' },
        pictograph({ count: count100(rate), title: T.hikaye.s1.ikon(x, fmtInt(PICTO_TOTAL)), desc: T.hikaye.s1.ikonAciklama(fmtInt(LATE_AFTER)), cls: 'picto-big' }),
        el('figcaption', null, T.hikaye.s1.ikon(x, fmtInt(PICTO_TOTAL))),
      )
    : null;
  const node = el(
    'section',
    { class: 'slide slide-cover', id: 'slayt-0', 'aria-labelledby': 'sl-0' },
    el(
      'div',
      { class: 'cover-grid' },
      el(
        'div',
        { class: 'cover-text stack' },
        el('h2', { id: 'sl-0', class: 'cover-title', tabindex: '-1' }, T.siteBasligi),
        el('p', { class: 'cover-q' }, h.soru(saat)),
        el('p', { class: 'scope' }, h.kapsam(fmtInt(k.test_ucus_sayisi), fmtInt(k.havalimani_sayisi), period)),
        el('div', { class: 'cover-brief' }, el('h3', null, p.kapakSayfa.kisaca), el('ul', null, brief.map((b) => el('li', null, b)))),
        el(
          'p',
          { class: 'cover-actions' },
          el('button', { type: 'button', class: 'btn btn-primary btn-start', onclick: onStart }, p.baslat),
          el('a', { class: 'btn', href: '../' }, p.detaySite),
          repo ? el('a', { class: 'btn', href: repo, rel: 'noopener' }, h.kod) : null,
        ),
        el('p', { class: 'cover-author' }, el('strong', null, T.altBilgi.yazar), AUTHOR, authorLinkNodes().length ? ' | ' : null, authorLinkNodes()),
        el('p', { class: 'note' }, T.sorumluluk),
      ),
      picto,
    ),
  );
  return { node };
}

// ---------------------------------------------------------------------- 1. sorun
export function slideProblem(ctx) {
  const { ozet, hata } = ctx;
  const t = T.hikaye.s1;
  const p = T.sunum.s1;
  const rate = prevalenceOf(ozet);
  if (rate === null) return unavailable(1);
  const x = fmtInt(count100(rate));
  const total = fmtInt(PICTO_TOTAL);
  const months = hata && Array.isArray(hata.boyutlar) ? hata.boyutlar.find((b) => b.boyut === 'ay' && b.model === 'lgbm_T2') : null;
  const monthRows = months ? months.segmentler.map((s) => ({ seg: s.segment, v: rateOf(s) })).filter((r) => isNum(r.v)) : [];
  const keys = [
    { label: p.testUcus, value: fmtInt(ozet.kapsam.test_ucus_sayisi) },
    { label: p.tanim, value: p.tanimDeger(fmtInt(LATE_AFTER)) },
  ];
  if (monthRows.length >= 2) {
    const hi = monthRows.reduce((a, b) => (b.v > a.v ? b : a));
    const lo = monthRows.reduce((a, b) => (b.v < a.v ? b : a));
    keys.push({ label: p.enYuksekAy, value: p.ayDeger(monthLabel(hi.seg), fmtPct(hi.v, 0)) }, { label: p.enDusukAy, value: p.ayDeger(monthLabel(lo.seg), fmtPct(lo.v, 0)) });
  }
  return slide({
    n: 1,
    ico: 'plane',
    title: t.baslik(fmtInt(Math.round(1 / rate))),
    figure: figure(pictograph({ count: count100(rate), title: t.ikon(x, total), desc: t.ikonAciklama(fmtInt(LATE_AFTER)), cls: 'picto-big' }), t.ikon(x, total)),
    keys,
    how: p.nasil,
    means: p.anlam(fmtPct(rate, 0)),
    href: '../#results',
  });
}

// ---------------------------------------------------------------------- 2. kalkış saati
export function slideTime(ctx) {
  const { hata } = ctx;
  const t = T.hikaye.s2;
  const p = T.sunum.s2;
  const block = hata && Array.isArray(hata.boyutlar) ? hata.boyutlar.find((b) => b.boyut === 'saat_blogu' && b.model === 'lgbm_T2') : null;
  const rows = block
    ? block.segmentler
        .map((s) => ({ seg: s.segment, v: rateOf(s) }))
        .filter((r) => isNum(r.v))
        .sort((a, b) => BLOCK_ORDER.indexOf(a.seg) - BLOCK_ORDER.indexOf(b.seg))
    : [];
  if (rows.length < 2) return unavailable(2);
  const hi = rows.reduce((a, b) => (b.v > a.v ? b : a));
  const lo = rows.reduce((a, b) => (b.v < a.v ? b : a));
  const ratio = lo.v > 0 ? hi.v / lo.v : 0;
  const title = ratio >= 1.5 ? t.baslik(blockLabel(hi.seg), blockLabel(lo.seg), fmtInt(Math.round(ratio))) : t.baslikDuz;
  const event = hata.boyutlar.find((b) => b.boyut === 'olay_gunu' && b.model === 'lgbm_T2');
  const pick = (name) => {
    const s = event ? event.segmentler.find((y) => y.segment === name) : null;
    return s ? rateOf(s) : null;
  };
  const eventRate = pick('olay');
  const otherRate = pick('diger');
  const keys = [
    { label: p.enYuksek, value: p.blokDeger(blockLabel(hi.seg), fmtPct(hi.v, 0)) },
    { label: p.enDusuk, value: p.blokDeger(blockLabel(lo.seg), fmtPct(lo.v, 0)) },
  ];
  if (isNum(eventRate) && isNum(otherRate)) keys.push({ label: p.olayGunu, value: fmtPct(eventRate, 0) }, { label: p.digerGunler, value: fmtPct(otherRate, 0) });
  const items = rows.map((r) => ({ label: blockLabel(r.seg), value: r.v, text: fmtPct(r.v, 0), emph: r === hi }));
  const { box } = chartBox((width) =>
    barChart({
      width,
      rowH: 34,
      labelWidth: 96,
      tickCount: width < 480 ? 2 : 4,
      items,
      tickFormat: (v) => fmtPct(v, 0),
      xLabel: t.eksen,
      title: t.grafikBaslik,
      desc: t.grafikAciklama(fmtPct(hi.v, 0), fmtPct(lo.v, 0)),
    }),
  );
  return slide({ n: 2, ico: 'clock', title, figure: figure(box), keys, how: p.nasil, means: p.anlam, href: '../#method/errors' });
}

// ---------------------------------------------------------------------- 4. model riskli uçuşları önceden görüyor
export function slideRisk(ctx) {
  const { kal, ozet } = ctx;
  const t = T.hikaye.s3;
  const p = T.sunum.s4;
  const bins = riskGroups(kal);
  if (!bins) return unavailable(4);
  const per = bins.length;
  const low = bins[0].gozlenen_oran;
  const high = bins[per - 1].gozlenen_oran;
  const lowText = { n: fmtInt(per), deger: fmtInt(Math.max(1, Math.round(low * per))) };
  const title = low < 1 / per ? t.baslikAz(riskiest(bins), lowText) : t.baslik(riskiest(bins), lowText);
  const items = bins.map((b, i) => ({ label: fmtInt(i + 1), values: [{ value: b.gozlenen_oran, text: fmtPct(b.gozlenen_oran, 0) }] }));
  const { box } = chartBox((width) =>
    columnChart({
      width,
      height: 300,
      items,
      showValues: true,
      yFormat: (v) => fmtPct(v, 0),
      tickCount: width < 480 ? 3 : 4,
      xLabel: t.eksen(fmtInt(1), fmtInt(per)),
      title: t.grafikBaslik,
      desc: t.grafikAciklama(fmtPct(low, 0), fmtPct(high, 0)),
    }),
  );
  const avg = prevalenceOf(ozet);
  const keys = [
    { label: p.riskli, value: fmtPct(high, 0) },
    { label: p.guvenli, value: fmtPct(low, 0) },
  ];
  if (avg !== null) keys.push({ label: p.ortalama, value: fmtPct(avg, 0) });
  return slide({ n: 4, ico: 'chart', title, figure: figure(box), keys, how: p.nasil, means: p.anlam, href: '../#method/calibration' });
}

// ---------------------------------------------------------------------- 5. tahminler güvenilir
export function slideTrust(ctx) {
  const { kal } = ctx;
  const t = T.hikaye.s4;
  const p = T.sunum.s5;
  const bins = riskGroups(kal);
  if (!bins) return unavailable(5);
  const per = bins.length;
  const gaps = bins.map((b) => Math.abs(b.ortalama_tahmin - b.gozlenen_oran));
  const maxGap = Math.max(...gaps);
  const minGap = Math.min(...gaps);
  const points = fmtInt(Math.ceil(maxGap * 100 - 1e-9));
  const sample = bins.reduce((a, b) => (Math.abs(b.ortalama_tahmin - 0.3) < Math.abs(a.ortalama_tahmin - 0.3) ? b : a));
  const close = maxGap <= NEAR_ENOUGH;
  const title = close ? t.baslik(fmtPct(sample.ortalama_tahmin, 0), fmtPct(sample.gozlenen_oran, 0)) : t.baslikGenel(points);
  const items = bins.map((b, i) => ({
    label: fmtInt(i + 1),
    values: [
      { value: b.ortalama_tahmin, variant: 'hollow', text: `${t.model}: ${fmtPct(b.ortalama_tahmin, 0)}` },
      { value: b.gozlenen_oran, text: `${t.gercek}: ${fmtPct(b.gozlenen_oran, 0)}` },
    ],
  }));
  const { box } = chartBox((width) =>
    columnChart({
      width,
      height: 290,
      items,
      yFormat: (v) => fmtPct(v, 0),
      tickCount: width < 480 ? 3 : 4,
      xLabel: t.eksen(fmtInt(1), fmtInt(per)),
      title: t.grafikBaslik,
      desc: t.grafikAciklama(points),
    }),
  );
  const keys = [
    { label: p.enBuyuk, value: p.puanDeger(fmtNum(maxGap * 100, 1)) },
    { label: p.enKucuk, value: p.puanDeger(fmtNum(minGap * 100, 1)) },
    { label: p.gruplar, value: fmtInt(per) },
  ];
  const legendItems = el(
    'ul',
    { class: 'legend key-list' },
    el('li', null, el('span', { class: 'swatch-box pred', 'aria-hidden': 'true' }), el('span', null, t.model)),
    el('li', null, el('span', { class: 'swatch-box col', 'aria-hidden': 'true' }), el('span', null, t.gercek)),
  );
  return slide({
    n: 5,
    ico: 'shield',
    title,
    figure: [figure(box), legendItems],
    keys,
    how: p.nasil,
    means: close ? p.anlam(fmtPct(sample.ortalama_tahmin, 0), fmtPct(sample.gozlenen_oran, 0)) : p.anlamGenel,
    href: '../#method/calibration',
  });
}

// ---------------------------------------------------------------------- 6. hava bilgisi
export function slideWeather(ctx) {
  const { ozet, hava } = ctx;
  const t = T.hikaye.s5;
  const p = T.sunum.s6;
  const score = (model) => {
    const m = metricOf(ozet, 'arrdel15', model, 'roc_auc');
    return m && isNum(m.deger) ? m.deger : null;
  };
  const b1 = score('B1');
  const plan = score('lgbm_plan');
  const t2 = score('lgbm_T2');
  if (plan === null || t2 === null) return unavailable(6);
  const gap = hava && Array.isArray(hava.farklar) ? hava.farklar.find((f) => f.karsilastirma === 'T2-plan' && f.metrik.ad === 'roc_auc') : null;
  const better = gap ? excludesZero(gap.metrik) && gap.metrik.ga95_alt > 0 : t2 > plan;
  const saat = fmtPlain(ozet.bilgi_zamani_saat);
  const shown = (v) => (v === null ? txt(null) : fmtNum(v, 2));
  const labels = [t.gecmis, t.tarife, t.hava(saat)];
  const values = [b1, plan, t2];
  const { box } = chartBox((width) => {
    const narrow = width < 480;
    return barChart({
      width,
      rowH: 46,
      labelWidth: narrow ? 112 : 160,
      tickCount: narrow ? 2 : 4,
      base: COIN_FLIP,
      items: labels.map((label, i) => ({ label: wrapLabel(label, narrow ? 17 : 24), value: values[i], text: shown(values[i]), emph: i === 2 })),
      tickFormat: (v) => fmtNum(v, 2),
      xLabel: t.eksen(fmtNum(COIN_FLIP, 1)),
      title: t.grafikBaslik,
      desc: t.grafikAciklama(shown(b1), shown(plan), shown(t2)),
    });
  });
  const keys = [
    { label: p.gecmis, value: shown(b1) },
    { label: p.tarife, value: shown(plan) },
    { label: p.hava(saat), value: shown(t2) },
  ];
  let how = p.nasil(fmtNum(COIN_FLIP, 2));
  if (gap && isNum(gap.metrik.ga95_alt) && isNum(gap.metrik.ga95_ust)) {
    keys.push({ label: p.katki, value: fmtNum(gap.metrik.deger, 3, true) });
    const confidence = fmtPct(CONFIDENCE, 0);
    const lo = fmtNum(gap.metrik.ga95_alt, 3, true);
    const hi = fmtNum(gap.metrik.ga95_ust, 3, true);
    how = `${how} ${better ? p.guven(lo, hi, confidence) : p.guvenNotr(lo, hi, confidence)}`;
  }
  return slide({
    n: 6,
    ico: 'cloud',
    title: better ? t.baslik : t.baslikNotr,
    figure: figure(box),
    keys,
    how,
    means: better ? p.anlamIyi : p.anlamNotr,
    href: '../#method/weather',
  });
}
