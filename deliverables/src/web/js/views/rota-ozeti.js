// Keşfet: seçili havalimanının özet kartları (harita ile rota tablosunun arasında). Sayıların hepsi
// havalimanının rota hücrelerinden hesaplanır (kesfet-hesap.js, saf işlevler); metinler T.kesfet.kart içindedir.
// Yayımlanmayan havalimanlarında (tek havayolu payı yüksek) yalnızca yayımlanmış rota hücreleri kullanılır ve
// havalimanı düzeyine yaklaşan toplam oranlar gösterilmez; kartlarda ad ve yön kalır.

import { el } from '../dom.js';
import { T } from '../metin.js';
import { fmtPct, fmtMin, fmtInt, fmtNum, blockLabel } from '../fmt.js';
import { icon } from '../simgeler.js';
import { summarize, MIN_FLIGHTS } from '../kesfet-hesap.js';

function card(tone, iconName, title, ...body) {
  return el(
    'li',
    { class: `stat-card tone-${tone}` },
    el('span', { class: 'stat-ico' }, icon(iconName, { size: 22 })),
    el('h4', null, title),
    body,
  );
}

const empty = () => el('p', { class: 'stat-note muted' }, T.kesfet.kart.yok);

/**
 * iata: seçili havalimanı, airport: havalimanı kaydı (gizleme_nedeni için), cells: rota dosyasındaki hücreler,
 * nameOf(iata) -> ad ya da null. Döner: bölüm düğümü.
 */
export function buildCards(iata, airport, cells, nameOf) {
  const k = T.kesfet.kart;
  const hidden = Boolean(airport && airport.gizleme_nedeni);
  const s = summarize(cells, MIN_FLIGHTS);
  const label = (code) => {
    const name = nameOf ? nameOf(code) : null;
    return name ? `${code} ${name}` : code;
  };

  // 1. En riskli kalkış bloğu
  const blockCard = s.block
    ? card('warn', 'plane', k.blok.baslik, el('p', { class: 'stat-big' }, blockLabel(s.block.block)), el('p', { class: 'stat-note' }, hidden ? k.blok.detaySiz : k.blok.detay(fmtPct(s.block.rate), fmtInt(s.block.n))))
    : card('warn', 'plane', k.blok.baslik, empty());

  // 2. En güvenilir ve en riskli varış
  const row = (iconName, tone, head, d) =>
    el('p', { class: `stat-row tone-${tone}` }, icon(iconName, { size: 18 }), el('span', null, el('strong', null, head), ' ', hidden ? k.varis.satirSiz(label(d.dest)) : k.varis.satir(label(d.dest), fmtPct(d.rate))));
  const destCard =
    s.reliable && s.risky
      ? card('neutral', 'pin', k.varis.baslik, row('shield', 'good', k.varis.guvenilir, s.reliable), row('alert', 'bad', k.varis.riskli, s.risky))
      : card('neutral', 'pin', k.varis.baslik, empty());

  // 3. Yaz ve ilkbahar farkı
  let seasonCard;
  if (s.season) {
    const d = s.season.diffPoints;
    const big = hidden ? (d > 0 ? k.mevsim.ileri : d < 0 ? k.mevsim.geri : k.mevsim.ayni) : `${fmtNum(d, 1, true)} ${T.ortak.puan}`;
    seasonCard = card('neutral', 'calendar', k.mevsim.baslik, el('p', { class: 'stat-big' }, big), hidden ? null : el('p', { class: 'stat-note' }, k.mevsim.detay(fmtPct(s.season.summer), fmtPct(s.season.spring))));
  } else {
    seasonCard = card('neutral', 'calendar', k.mevsim.baslik, empty());
  }

  // 4. Tipik rötar
  const typicalCard =
    s.typical === null
      ? card('neutral', 'clock', k.tipik.baslik, empty())
      : card('neutral', 'clock', k.tipik.baslik, el('p', { class: 'stat-big' }, fmtMin(s.typical)), el('p', { class: 'stat-note' }, k.tipik.detay));

  return el(
    'section',
    { class: 'stack', 'aria-labelledby': 'ex-cards-h' },
    el('h3', { id: 'ex-cards-h', class: 'with-ico' }, icon('target'), el('span', null, k.baslik(iata))),
    el('ul', { class: 'stat-grid', 'aria-label': k.liste }, blockCard, destCard, seasonCard, typicalCard),
    el('p', { class: 'note' }, k.esik(fmtInt(MIN_FLIGHTS)), hidden ? ` ${k.yalnizca}` : ''),
  );
}
