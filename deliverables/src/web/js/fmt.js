// Sayı ve etiket biçimleri. Dile göre:
//   Türkçe:    ondalık virgül, binlik ayırıcı nokta, yüzde "%24,2" (0,712 · 2.369.002)
//   İngilizce: ondalık nokta, binlik ayırıcı virgül, yüzde "24.2%" (0.712 · 2,369,002)
// Eksi işareti "−". Sitenin tek yuvarlama ilkesi: oranlar ve kapsama yüzde olarak 1 ondalık, skorlar
// 4 ondalık, dakikalar 1 ondalık. Eksik değer her yerde "–" olur; ekrana "null" ya da "undefined" yazılmaz.

import { T, getLang } from './metin.js';

export const NA = '–';
export const MINUS = '−';

const missing = (x) => x === null || x === undefined || typeof x !== 'number' || !Number.isFinite(x);

/** Metin olarak yazılacak herhangi bir değer için güvenli biçimleyici. */
export const txt = (v) => (v === null || v === undefined ? NA : String(v));

function parts(x, digits, plus) {
  const s = Math.abs(x).toFixed(digits);
  const isZero = Number(s) === 0;
  const [whole, dec] = s.split('.');
  const en = getLang() === 'en';
  const group = en ? ',' : '.';
  const body = whole.replace(/\B(?=(\d{3})+(?!\d))/g, group) + (dec ? (en ? `.${dec}` : `,${dec}`) : '');
  let sign = '';
  if (x < 0 && !isZero) sign = MINUS;
  else if (plus && x > 0 && !isZero) sign = '+';
  return { sign, body };
}

function signed(x, digits, plus) {
  const p = parts(x, digits, plus);
  return p.sign + p.body;
}

export const fmtNum = (x, d = 4, plus = false) => (missing(x) ? NA : signed(x, d, plus));
export const fmtPct = (x, d = 1, plus = false) => {
  if (missing(x)) return NA;
  const p = parts(x * 100, d, plus);
  return getLang() === 'en' ? `${p.sign}${p.body}%` : `${p.sign}%${p.body}`;
};
export const fmtMin = (x, d = 1, plus = false) => (missing(x) ? NA : `${signed(x, d, plus)} ${T.birim.dk}`);
export const fmtInt = (x) => (missing(x) ? NA : signed(Math.round(x), 0, false));

/** Maliyet oranı gibi: tam sayıysa ondalıksız, değilse 2 ondalık ("4", "1,22"). */
export const fmtRatio = (x) => (missing(x) ? NA : signed(x, Number.isInteger(x) ? 0 : 2, false));

/** Bir metrik nesnesinin {ad, birim} birimiyle değer biçimi. */
export function fmtValue(value, name, unit, plus = false) {
  if (missing(value)) return NA;
  if (name === 'esik') return signed(value, 3, plus);
  if (unit === 'oran') return fmtPct(value, 1, plus);
  if (unit === 'dakika') return fmtMin(value, 1, plus);
  return signed(value, 4, plus);
}

export function fmtMetricValue(m, plus = false) {
  return m ? fmtValue(m.deger, m.ad, m.birim, plus) : NA;
}

/** Bir metriğin %95 aralığı "[alt; üst]" olarak; veri dosyasında yoksa "–". */
export function fmtInterval(m, plus = false) {
  if (!m || missing(m.ga95_alt) || missing(m.ga95_ust)) return NA;
  return `[${fmtValue(m.ga95_alt, m.ad, m.birim, plus)}; ${fmtValue(m.ga95_ust, m.ad, m.birim, plus)}]`;
}

/** Saat gibi küçük, çoğunlukla tam sayılar: 2 -> "2", 2.5 -> "2,5". */
export const fmtPlain = (x) => (missing(x) ? NA : signed(x, Number.isInteger(x) ? 0 : 1, false));

export const METRIC_LABEL = T.metrik;
export const metricLabel = (name) => METRIC_LABEL[name] || txt(name);

/** Belirsizlik bırakmayan ölçütlerde hangi yönün daha iyi olduğu. */
export const BETTER = {
  roc_auc: 'higher', pr_auc: 'higher', brier_skill: 'higher',
  brier: 'lower', log_loss: 'lower', ece: 'lower',
  pinball_p50: 'lower', pinball_p80: 'lower', pinball_p95: 'lower', mae_p50: 'lower',
};
export const betterLabel = (name) => (BETTER[name] ? T.daha[BETTER[name]] : NA);

export const MODEL_SHORT = T.model;
export const modelLabel = (id) => MODEL_SHORT[id] || txt(id);

export const SEASON_LABEL = T.mevsim;
export const SEASON_ORDER = ['tum', 'kis', 'ilkbahar', 'yaz', 'sonbahar'];
export const seasonLabel = (s) => SEASON_LABEL[s] || txt(s);

export const BLOCK_ORDER = ['00-06', '06-09', '09-12', '12-15', '15-18', '18-21', '21-24'];
export function blockLabel(b) {
  const m = /^(\d\d)-(\d\d)$/.exec(b);
  return m ? `${m[1]}:00–${m[2]}:00` : txt(b);
}

/** "2026-03" -> "Mar 2026". */
export function monthLabel(ay) {
  const m = /^(\d{4})-(\d{2})$/.exec(ay);
  if (!m) return txt(ay);
  return `${T.aylar[Number(m[2]) - 1] || m[2]} ${m[1]}`;
}

export const fmtPeriod = (p) => T.donem(txt(p.baslangic), txt(p.bitis));

/** Yalnızca düz https bağlantıları <a href> olur. */
export function safeHttpsUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' ? u.href : null;
  } catch (err) {
    return null;
  }
}
