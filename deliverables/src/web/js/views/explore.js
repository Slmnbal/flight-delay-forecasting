// Keşfet: üstte havalimanı haritası ve tablosu, ortada seçilen havalimanının özet kartları, altta o havalimanından
// çıkan rotaların tablosu; hepsi tek sayfada. Haritada bir havalimanı seçilince rota yayları çizilir, kartlar ve
// rota tablosu o havalimanına göre güncellenir; adres #explore/ORD olur.
// Eski #routes/ORD bağlantıları main.js içinde bu sayfaya yönlendirilir.

import { el, fill } from '../dom.js';
import { loadHavalimanlari, loadManifest, loadRoutes, loadVarisNoktalari, routeOrigins } from '../data.js';
import { T } from '../metin.js';
import { arcItems } from '../kesfet-hesap.js';
import { mount as mountAirports } from './airports.js';
import { mount as mountRoutes, onParams as routesOnParams, focusHeading } from './routes.js';
import { buildCards } from './rota-ozeti.js';

export async function mount(root, params) {
  const mapBox = el('div', { class: 'stack' });
  const cardsBox = el('div', { class: 'explore-cards' });
  const routesBox = el('div', { class: 'stack explore-routes' });

  // Adreste havalimanı yoksa rota tablosunun açıldığı havalimanı (ORD, yoksa ilk rota dosyası) seçili başlar.
  const [airportsFile, manifest] = await Promise.all([loadHavalimanlari(), loadManifest()]);
  const available = routeOrigins(manifest);
  const known = airportsFile.havalimanlari.filter((a) => available.has(a.iata)).map((a) => a.iata).sort();
  const wanted = params && params[0] ? String(params[0]) : null;
  const initial = wanted && available.has(wanted) ? wanted : known.includes('ORD') ? 'ORD' : known[0] || null;
  const byCode = new Map(airportsFile.havalimanlari.map((a) => [a.iata, a]));

  fill(root, el('p', { class: 'lede' }, T.kesfet.giris), mapBox, cardsBox, routesBox);

  let controller = null;
  let ticket = 0;

  // Seçili havalimanının rota hücrelerinden yaylar ve özet kartları.
  async function showOrigin(iata) {
    const mine = ++ticket;
    fill(cardsBox);
    if (controller) controller.setArcs(null);
    let file;
    let coords = null;
    try {
      [file, coords] = await Promise.all([loadRoutes(iata), loadVarisNoktalari()]);
    } catch (err) {
      return; // rota tablosu kendi hata iletisini gösterir
    }
    if (mine !== ticket) return;
    const cells = Array.isArray(file.hucreler) ? file.hucreler : [];
    const nameOf = (code) => (coords && coords.get(code) ? coords.get(code).ad : byCode.has(code) ? byCode.get(code).ad : null);
    fill(cardsBox, buildCards(iata, byCode.get(iata), cells, nameOf));
    if (controller) {
      const { items, missing } = arcItems(cells, coords, iata);
      controller.setArcs({ origin: iata, items, missing: missing.length, failed: coords === null });
    }
  }

  const onSelect = (iata, goToRoutes) => {
    routesOnParams([iata]);
    try {
      window.history.replaceState(null, '', `#explore/${iata}`);
    } catch (err) {
      // Adres güncellenemezse seçim yine çalışır.
    }
    showOrigin(iata);
    if (goToRoutes) focusHeading();
  };
  const [airportsCtl] = await Promise.all([mountAirports(mapBox, [], { initial, onSelect }), mountRoutes(routesBox, initial ? [initial] : [])]);
  controller = airportsCtl;
  if (initial) showOrigin(initial);
}

export function onParams(params) {
  routesOnParams(params);
}
