// Sunumun slayt listesi: kapak (0) ve on bir içerik slaydı (1-11). Veri dosyaları bir kez yüklenir; bir dosya
// yüklenemezse yalnızca onu kullanan slayt uyarı gösterir, diğerleri çalışır.

import { loadOzet, loadHava, loadOptimizasyon, loadHata, loadKalibrasyon, loadHavalimanlari, loadManifest } from '../js/data.js';
import { cover, slideProblem, slideTime, slideRisk, slideTrust, slideWeather } from './slaytlar.js';
import { slideBufferIdea, slideTradeoff, slideRule, slideActions } from './slaytlar-tampon.js';
import { slideMap } from './harita-slayti.js';
import { slideTry } from './deneme-slayti.js';
import { unavailable } from './slayt.js';

/** Sunumun ihtiyaç duyduğu bütün veri dosyaları; zorunlu olanlar (ozet, havalimanları, manifest) yüklenemezse hata fırlatır. */
export async function loadContext() {
  const [ozet, airportsFile, manifest] = await Promise.all([loadOzet(), loadHavalimanlari(), loadManifest()]);
  const [hava, opt, hata, kal] = await Promise.all([loadHava().catch(() => null), loadOptimizasyon().catch(() => null), loadHata().catch(() => null), loadKalibrasyon().catch(() => null)]);
  return { ozet, airportsFile, manifest, hava, opt, hata, kal };
}

/** Slayt düğümleri, sırayla: [{node}], 0 = kapak. onStart: kapaktaki "Başla" düğmesinin işlevi. */
export async function buildSlides(ctx, onStart) {
  const [map, tryIt] = await Promise.all([slideMap(ctx).catch(() => unavailable(3)), slideTry(ctx).catch(() => unavailable(11))]);
  return [
    cover(ctx, onStart),
    slideProblem(ctx),
    slideTime(ctx),
    map,
    slideRisk(ctx),
    slideTrust(ctx),
    slideWeather(ctx),
    slideBufferIdea(),
    slideTradeoff(ctx),
    slideRule(ctx),
    slideActions(ctx),
    tryIt,
  ];
}
