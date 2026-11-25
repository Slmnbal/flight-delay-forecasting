// Harita slaydı: büyük ABD haritası, havalimanları geç varış oranının risk rengiyle; seçili havalimanından çıkan
// rota yayları (varsayılan: test uçuşu en çok olan havalimanı). Havalimanları SIRALANMAZ: yan panelde yalnızca
// oranların aralığı (en düşükten en yükseğe, adsız) ve seçili havalimanının sayıları vardır. Yayımlanmayan
// havalimanları (tek havayolu payı yüksek) "yayımlanmadı" olarak işaretlenir. Harita, yaylar ve açıklama
// detay sitesiyle aynı modüllerdir (map.js, kesfet-hesap.js, harita-lejant.js).

import { el, fill } from '../js/dom.js';
import { loadEyaletler, loadRoutes, loadVarisNoktalari, routeOrigins } from '../js/data.js';
import { fmtPct, fmtInt, NA } from '../js/fmt.js';
import { T } from '../js/metin.js';
import { icon } from '../js/simgeler.js';
import { buildMap, isCompact, onMap, widthForHeight } from '../js/map.js';
import { mountChart } from '../js/charts.js';
import { RISK_EDGES, riskClass, arcItems } from '../js/kesfet-hesap.js';
import { riskStrip, sizeKey, hiddenKey, arcKey } from '../js/harita-lejant.js';
import { isNum } from '../js/hikaye-ortak.js';
import { slide, unavailable } from './slayt.js';

const clip = (text, max = 44) => (String(text).length > max ? `${String(text).slice(0, max - 1)}…` : String(text));
const wideLayout = () => typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 62rem)').matches;

export async function slideMap(ctx) {
  const { airportsFile, manifest } = ctx;
  const t = T.havalimani;
  const p = T.sunum.harita;
  const airports = airportsFile.havalimanlari;
  const byCode = new Map(airports.map((a) => [a.iata, a]));
  const published = airports.filter((a) => !a.gizleme_nedeni && isNum(a.gozlenen_arrdel15_orani));
  if (published.length < 2) return unavailable(3);
  const rates = published.map((a) => a.gozlenen_arrdel15_orani);
  const lo = Math.min(...rates);
  const hi = Math.max(...rates);
  const available = routeOrigins(manifest);
  const withRoutes = published.filter((a) => available.has(a.iata));
  const firstPick = (withRoutes.length ? withRoutes : published).reduce((best, a) => (a.n_test_ucus > best.n_test_ucus ? a : best));

  const [states, coords] = await Promise.all([loadEyaletler(), loadVarisNoktalari()]);
  let selected = firstPick.iata;
  let arcState = null; // {origin, items}
  let ticket = 0;
  let sl = null;

  const mapBox = el('div', { class: 'map-box' });
  const legendBox = el('div', { class: 'map-legend map-legend-row' });

  const labelOf = (a) => t.aria(a.iata, a.ad, t.olcutler.gozlenen_arrdel15_orani, isNum(a.gozlenen_arrdel15_orani) ? fmtPct(a.gozlenen_arrdel15_orani) : T.ortak.yayimlanmadiKucuk, fmtInt(a.n_test_ucus));
  const pointTip = (a) => [
    clip(`${a.iata} ${a.ad}`),
    clip(`${t.olcutler.gozlenen_arrdel15_orani}: ${isNum(a.gozlenen_arrdel15_orani) ? fmtPct(a.gozlenen_arrdel15_orani) : T.ortak.yayimlanmadi}`),
    clip(`${t.satirlar.testUcus}: ${fmtInt(a.n_test_ucus)}`),
  ];
  const arcLabel = (item) => t.yayEtiket(item.iata, item.ad, fmtInt(item.n), item.rate === null ? NA : fmtPct(item.rate));
  const arcTip = (item) => [clip(`${item.iata} ${item.ad}`), t.yayIpucuUcus(fmtInt(item.n)), item.rate === null ? NA : t.yayIpucuGec(fmtPct(item.rate))];

  const chart = mountChart(mapBox, (width) => {
    const fixed = wideLayout() && mapBox.clientHeight > 0;
    return buildMap({
      width: fixed ? Math.max(300, Math.min(width, widthForHeight(mapBox.clientHeight))) : width,
      airports,
      states,
      valueOf: (a) => a.gozlenen_arrdel15_orani,
      classOf: (a) => riskClass(a.gozlenen_arrdel15_orani, RISK_EDGES),
      selected,
      labelOf,
      pointTip,
      onSelect: select,
      arcs: arcState && arcState.origin === selected ? { origin: arcState.origin, items: arcState.items, edges: RISK_EDGES, groupLabel: t.yayGrup(arcState.origin) } : null,
      arcLabel,
      arcTip,
    });
  });

  function renderLegend() {
    const compact = isCompact(mapBox.clientWidth || 600);
    fill(
      legendBox,
      el('div', { class: 'legend-row legend-col' }, el('span', { class: 'legend-title' }, t.lejantBaslik(t.olcutler.gozlenen_arrdel15_orani)), riskStrip()),
      sizeKey(airports, compact),
      hiddenKey(airports),
      arcState ? arcKey(arcState.items, compact, true, '') : null,
    );
  }

  function keysFor() {
    const a = byCode.get(selected);
    const shown = a && isNum(a.gozlenen_arrdel15_orani) ? fmtPct(a.gozlenen_arrdel15_orani, 1) : T.ortak.yayimlanmadi;
    return [
      { label: p.aralik, value: p.aralikDeger(fmtPct(lo, 1), fmtPct(hi, 1)) },
      { label: p.secili, value: p.seciliDeger(selected, shown) },
      { label: p.testUcus, value: a ? fmtInt(a.n_test_ucus) : NA },
    ];
  }

  async function loadArcs(iata) {
    const mine = (ticket += 1);
    let items = [];
    if (available.has(iata)) {
      try {
        const file = await loadRoutes(iata);
        const found = arcItems(Array.isArray(file.hucreler) ? file.hucreler : [], coords, iata);
        items = found.items.filter((i) => onMap(i.enlem, i.boylam));
      } catch (err) {
        items = [];
      }
    }
    if (mine !== ticket) return false;
    arcState = items.length ? { origin: iata, items } : null;
    return true;
  }

  async function select(iata) {
    selected = iata;
    arcState = null;
    if (sl) {
      sl.setKeys(keysFor());
      const link = sl.node.querySelector('.details-link a');
      if (link) link.setAttribute('href', `../#explore/${iata}`);
    }
    renderLegend();
    chart.redraw();
    if (await loadArcs(iata)) {
      renderLegend();
      chart.redraw();
    }
  }

  await loadArcs(selected);
  renderLegend();

  const hidden = airports.filter((a) => a.gizleme_nedeni);
  const hiddenNote = hidden.length
    ? el('p', { class: 'notice warn', role: 'note' }, icon('alert'), el('span', null, el('strong', null, t.yayimlanmayanlar), hidden.map((a) => a.iata).join(', ') + t.yayimlanmayanSonu))
    : null;

  sl = slide({
    n: 3,
    ico: 'pin',
    title: p.baslik(fmtPct(lo, 1), fmtPct(hi, 1)),
    cls: 'slide-map',
    figure: [mapBox, legendBox, el('p', { class: 'note' }, p.secimEtiketi)],
    keys: keysFor(),
    how: p.nasil,
    means: p.anlam,
    extra: hiddenNote,
    href: `../#explore/${selected}`,
  });
  return sl;
}
