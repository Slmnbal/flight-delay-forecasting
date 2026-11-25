// Veri erişimi. Sonuç dosyaları veri/ altındadır, harita dosyası harita/ altındadır. Yollar sayfanın
// değil bu modülün konumuna göre çözülür (import.meta.url): hem detay sitesi (/<depo>/) hem sunum
// sitesi (/<depo>/sunum/) aynı dosyaları okur ve GitHub Pages'te depo yolu altında da çalışır.
// Sonuç dosyalarının listesi manifest.json'dan okunur; aşağıdaki adlar sitenin okuduklarıdır.

import { T } from './metin.js';

const BASE = new URL('../veri/', import.meta.url).href;
const HARITA = new URL('../harita/', import.meta.url).href;

export const FILES = Object.freeze({
  manifest: 'manifest.json',
  ozet: 'ozet.json',
  havalimanlari: 'havalimanlari.json',
  kalibrasyon: 'kalibrasyon.json',
  hava: 'hava-deneyi.json',
  hata: 'hata-analizi.json',
  optimizasyon: 'optimizasyon.json',
  varisNoktalari: 'varis-noktalari.json',
});

const EYALETLER = 'abd-eyaletler.json';

export class DataError extends Error {
  constructor(path, reason) {
    super(T.hata.dosya(path, reason));
    this.name = 'DataError';
    this.path = path;
  }
}

const cache = new Map();

/** Bir fetch isteğini JSON'a çevirir; hata durumunda DataError fırlatır. */
function readJson(path, request) {
  return request.then(
    async (response) => {
      if (!response.ok) throw new DataError(path, T.hata.http(response.status));
      try {
        return await response.json();
      } catch (err) {
        throw new DataError(path, T.hata.gecersizJson);
      }
    },
    () => {
      throw new DataError(path, T.hata.ag);
    },
  );
}

function remember(key, make) {
  if (!cache.has(key)) {
    const request = make();
    cache.set(key, request);
    request.catch(() => cache.delete(key));
  }
  return cache.get(key);
}

const getJson = (path) => remember(path, () => readJson(path, fetch(BASE + path)));

export const loadManifest = () => getJson(FILES.manifest);
export const loadOzet = () => getJson(FILES.ozet);
export const loadHavalimanlari = () => getJson(FILES.havalimanlari);
export const loadKalibrasyon = () => getJson(FILES.kalibrasyon);
export const loadHava = () => getJson(FILES.hava);
export const loadHata = () => getJson(FILES.hata);
export const loadOptimizasyon = () => getJson(FILES.optimizasyon);

/**
 * Rota yaylarının varış koordinatları (veri/varis-noktalari.json). Dosya yoksa ya da bozuksa null döner;
 * harita yaysız çalışır. Döner: Map(iata -> {ad, enlem, boylam}) ya da null.
 */
export function loadVarisNoktalari() {
  return getJson(FILES.varisNoktalari).then(
    (doc) => (doc && Array.isArray(doc.noktalar) ? new Map(doc.noktalar.map((p) => [p.iata, p])) : null),
    () => null,
  );
}

/** Eyalet sınırları (Natural Earth, kamu malı). Yüklenemezse null döner; harita ızgarayla çalışır. */
export function loadEyaletler() {
  return remember(HARITA + EYALETLER, () => readJson(EYALETLER, fetch(HARITA + EYALETLER))).then(
    (doc) => (doc && Array.isArray(doc.eyaletler) ? doc.eyaletler : null),
    () => null,
  );
}

export function loadRoutes(iata) {
  if (!/^[A-Z0-9]{3}$/.test(iata)) return Promise.reject(new DataError(`rotalar/${iata}`, T.hata.gecersizKod));
  return getJson(`rotalar/${iata}.json`);
}

/** Manifest'e göre rota dosyası olan IATA kodları. */
export function routeOrigins(manifest) {
  const out = new Set();
  for (const f of manifest.dosyalar) {
    const m = /^veri\/rotalar\/([A-Z0-9]{3})\.json$/.exec(f.yol);
    if (m) out.add(m[1]);
  }
  return out;
}

export function findResult(ozet, gorev, model, kume = 'test') {
  return ozet.sonuclar.find((r) => r.gorev === gorev && r.model === model && r.kume === kume) || null;
}

export function findMetric(result, name) {
  if (!result) return null;
  return result.metrikler.find((m) => m.ad === name) || null;
}

export function metricOf(ozet, gorev, model, name) {
  return findMetric(findResult(ozet, gorev, model), name);
}
