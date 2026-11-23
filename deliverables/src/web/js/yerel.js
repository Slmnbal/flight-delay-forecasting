// Veri dosyalarından gelen metinlerin dile göre seçimi. Türkçe alanlar esas metindir; İngilizce
// karşılıklar ozet.json içindeki ceviri_en bölümünde ve *_en alanlarındadır. İngilizce karşılığı
// yoksa Türkçe metne düşülür.

import { getLang } from './metin.js';

/** İngilizce seçiliyse ve karşılığı doluysa en, değilse tr. */
export function loc(tr, en) {
  return getLang() === 'en' && typeof en === 'string' && en !== '' ? en : tr;
}

const ceviri = (ozet) => (ozet && ozet.ceviri_en ? ozet.ceviri_en : null);

export function projeBaslik(ozet) {
  const c = ceviri(ozet);
  return loc(ozet.proje.baslik, c && c.proje ? c.proje.baslik : null);
}

export function projeAciklama(ozet) {
  const c = ceviri(ozet);
  return loc(ozet.proje.aciklama, c && c.proje ? c.proje.aciklama : null);
}

export function sorumlulukReddi(ozet) {
  const c = ceviri(ozet);
  return loc(ozet.proje.sorumluluk_reddi, c && c.proje ? c.proje.sorumluluk_reddi : null);
}

/** kaynaklar[i].lisans_notu; İngilizce notlar kaynaklarla aynı sıradadır. */
export function kaynakLisansNotu(ozet, index) {
  const c = ceviri(ozet);
  const list = c && Array.isArray(c.kaynak_lisans_notlari) ? c.kaynak_lisans_notlari : [];
  return loc(ozet.proje.kaynaklar[index].lisans_notu, list[index]);
}

export function modelAciklamasi(ozet, model) {
  const c = ceviri(ozet);
  const list = c && Array.isArray(c.modeller) ? c.modeller : [];
  const hit = list.find((m) => m.kimlik === model.kimlik);
  return loc(model.aciklama, hit ? hit.aciklama : null);
}

export function kabulAciklamasi(ozet, kabul) {
  const c = ceviri(ozet);
  const list = c && Array.isArray(c.kabul) ? c.kabul : [];
  const hit = list.find((k) => k.olcut === kabul.olcut);
  return loc(kabul.aciklama, hit ? hit.aciklama : null);
}

/** Notların seçili dildeki listesi; İngilizce notlar Türkçe notlarla aynı sıradadır. */
export function notlar(ozet) {
  const tr = Array.isArray(ozet.notlar) ? ozet.notlar : [];
  const c = ceviri(ozet);
  const en = c && Array.isArray(c.notlar) ? c.notlar : [];
  return tr.map((n, i) => loc(n, en[i]));
}

// Optimizasyon bulgusu, veri dosyasındaki notlar arasından bu önekle bulunur (sayfaya elle yazılmaz).
// Önek Türkçe notun başıdır; İngilizce metin aynı sıradaki İngilizce nottan gelir.
export const OR_NOTE_PREFIX = 'Tampon optimizasyonu (OR):';

export function notBul(ozet, onek) {
  const tr = Array.isArray(ozet.notlar) ? ozet.notlar : [];
  const index = tr.findIndex((n) => typeof n === 'string' && n.startsWith(onek));
  return index < 0 ? null : notlar(ozet)[index];
}

export function gizlemeNedeni(havalimani) {
  return havalimani.gizleme_nedeni ? loc(havalimani.gizleme_nedeni, havalimani.gizleme_nedeni_en) : null;
}

export const varyantEtiketi = (v) => loc(v.etiket, v.etiket_en);

/** optimizasyon.json içindeki politika etiketi (kimlik bulunamazsa kimliğin kendisi). */
export function politikaEtiketi(opt, kimlik) {
  const list = opt && Array.isArray(opt.politikalar) ? opt.politikalar : [];
  const hit = list.find((p) => p.kimlik === kimlik);
  return hit ? loc(hit.etiket, hit.etiket_en) : kimlik;
}

export function optimizasyonNotlari(opt) {
  const tr = Array.isArray(opt.notlar) ? opt.notlar : [];
  const en = Array.isArray(opt.notlar_en) ? opt.notlar_en : [];
  return tr.map((n, i) => loc(n, en[i]));
}

export const kesifselEtiketi = (k) => loc(k.etiket, k.etiket_en);
