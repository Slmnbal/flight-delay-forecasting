// Keşfet sayfasının hesapları: saf işlevler (DOM yok, ağ yok); kolay denetlenir ve sınanır.
// Girdiler, rota dosyasındaki ham hücrelerdir: {dest, saat_blogu, mevsim, n_ucus, gozlenen_arrdel15_orani,
// kantil_dk: {p50, p80, p95}, ...}. Hiçbir sayı elle yazılmaz; yalnızca eşikler ve sınıf sınırları sabittir.
//
// Risk skalası: geç varış oranı (15+ dk) için 5 sıralı sınıf. Sınırlar sabittir ve harita noktalarında, rota
// yaylarında ve tablo rozetlerinde aynı kullanılır. Rozet düzeyleri bu sınıflardan türer:
//   düşük  : oran < RISK_LOW  (sınıf 1-2)
//   orta   : RISK_LOW <= oran < RISK_HIGH (sınıf 3-4)
//   yüksek : oran >= RISK_HIGH (sınıf 5)
// Sınırlar, sonuç dosyalarının dağılımına bakılmadan konmuştur (veri yeniden üretilirken); gerekirse
// yalnızca bu sabitler değişir.

export const RISK_EDGES = Object.freeze([0.15, 0.2, 0.25, 0.3]);
export const RISK_LOW = 0.2;
export const RISK_HIGH = 0.3;
export const RISK_CLASSES = 5;

// Özet kartlarında bir varış ya da kalkış bloğunun değerlendirilmesi için en az test uçuşu sayısı.
export const MIN_FLIGHTS = 200;

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** Bir oranın risk sınıfı (1 en düşük, 5 en yüksek); sayı değilse null. */
export function riskClass(value, edges = RISK_EDGES) {
  if (!isNum(value)) return null;
  let cls = 1;
  for (const edge of edges) if (value >= edge) cls += 1;
  return cls;
}

/** Rozet düzeyi: 'low' | 'medium' | 'high'; sayı değilse null. */
export function riskLevel(value) {
  if (!isNum(value)) return null;
  if (value < RISK_LOW) return 'low';
  if (value < RISK_HIGH) return 'medium';
  return 'high';
}

/** [lo, hi] aralığını eşit 5 sınıfa bölen 4 iç sınır (oran dışı ölçütler için). */
export function equalEdges(lo, hi) {
  if (!(hi > lo)) return [lo - 2, lo - 1, lo + 1, lo + 2]; // tek değer: ortadaki sınıf
  return [1, 2, 3, 4].map((k) => lo + ((hi - lo) * k) / RISK_CLASSES);
}

// ---------------------------------------------------------------------- ağırlıklı özetler
/** Ağırlıklı ortalama; geçersiz değer ya da ağırlıklar atlanır, ağırlık yoksa null. */
export function weightedMean(items, valueOf, weightOf) {
  let sum = 0;
  let total = 0;
  for (const item of items) {
    const v = valueOf(item);
    const w = weightOf(item);
    if (!isNum(v) || !isNum(w) || w <= 0) continue;
    sum += v * w;
    total += w;
  }
  return total > 0 ? sum / total : null;
}

/** Ağırlıklı medyan: değerler sıralanır, toplam ağırlığın yarısına ilk ulaşılan değer döner. */
export function weightedMedian(items, valueOf, weightOf) {
  const rows = items
    .map((item) => ({ v: valueOf(item), w: weightOf(item) }))
    .filter((r) => isNum(r.v) && isNum(r.w) && r.w > 0)
    .sort((a, b) => a.v - b.v);
  const total = rows.reduce((s, r) => s + r.w, 0);
  if (!(total > 0)) return null;
  let run = 0;
  for (const r of rows) {
    run += r.w;
    if (run * 2 >= total) return r.v;
  }
  return rows[rows.length - 1].v;
}

/**
 * Aynı (varış, saat bloğu) için hem "tüm yıl" hem mevsim hücreleri varsa yalnızca "tüm yıl" hücresi alınır;
 * böylece uçuşlar iki kez sayılmaz. Yalnızca mevsim hücreleri varsa hepsi alınır.
 */
export function baseCells(cells) {
  const groups = new Map();
  for (const cell of cells) {
    const key = `${cell.dest}|${cell.saat_blogu}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(cell);
  }
  const out = [];
  for (const group of groups.values()) {
    const whole = group.filter((c) => c.mevsim === 'tum');
    out.push(...(whole.length ? whole : group));
  }
  return out;
}

const rateOf = (c) => c.gozlenen_arrdel15_orani;
const flightsOf = (c) => c.n_ucus;

/** Varış başına toplam uçuş ve uçuş ağırlıklı geç varış oranı; en çok uçuştan en aza. */
export function destTotals(cells) {
  const byDest = new Map();
  for (const cell of baseCells(cells)) {
    if (!byDest.has(cell.dest)) byDest.set(cell.dest, []);
    byDest.get(cell.dest).push(cell);
  }
  return [...byDest.entries()]
    .map(([dest, list]) => ({ dest, n: list.reduce((s, c) => s + (isNum(flightsOf(c)) ? flightsOf(c) : 0), 0), rate: weightedMean(list, rateOf, flightsOf) }))
    .sort((a, b) => b.n - a.n || a.dest.localeCompare(b.dest));
}

/** Kalkış bloğu başına toplam uçuş ve ağırlıklı geç varış oranı. */
export function blockRates(cells) {
  const byBlock = new Map();
  for (const cell of baseCells(cells)) {
    if (!byBlock.has(cell.saat_blogu)) byBlock.set(cell.saat_blogu, []);
    byBlock.get(cell.saat_blogu).push(cell);
  }
  return [...byBlock.entries()].map(([block, list]) => ({
    block,
    n: list.reduce((s, c) => s + (isNum(flightsOf(c)) ? flightsOf(c) : 0), 0),
    rate: weightedMean(list, rateOf, flightsOf),
  }));
}

/** Bir mevsimin hücrelerinden toplam uçuş ve ağırlıklı oran; hücre yoksa null. "Tüm yıl" mevsim sayılmaz. */
export function seasonRate(cells, season) {
  if (season === 'tum') return null;
  const list = cells.filter((c) => c.mevsim === season);
  const rate = weightedMean(list, rateOf, flightsOf);
  if (rate === null) return null;
  return { n: list.reduce((s, c) => s + (isNum(flightsOf(c)) ? flightsOf(c) : 0), 0), rate };
}

/** Tipik rötar: hücrelerin P50 değerlerinin uçuş sayısıyla ağırlıklı medyanı (dakika; eksi değer erken). */
export function typicalDelay(cells) {
  return weightedMedian(baseCells(cells), (c) => (c.kantil_dk ? c.kantil_dk.p50 : null), flightsOf);
}

/**
 * Özet kartlarının değerleri. minFlights: bir blok ya da varışın değerlendirilmesi için en az uçuş.
 * Yeterli veri yoksa ilgili alan null olur. Yaz ve ilkbahar farkı yüzde puandır (yaz eksi ilkbahar).
 */
export function summarize(cells, minFlights = MIN_FLIGHTS) {
  const enough = (r) => r.rate !== null && r.n >= minFlights;
  const blocks = blockRates(cells).filter(enough);
  const dests = destTotals(cells).filter(enough);
  const pick = (list, better) => list.reduce((a, b) => (better(b, a) ? b : a));
  const summer = seasonRate(cells, 'yaz');
  const spring = seasonRate(cells, 'ilkbahar');
  return {
    block: blocks.length ? pick(blocks, (b, a) => b.rate > a.rate) : null,
    reliable: dests.length >= 2 ? pick(dests, (b, a) => b.rate < a.rate) : null,
    risky: dests.length >= 2 ? pick(dests, (b, a) => b.rate > a.rate) : null,
    season: summer && spring ? { summer: summer.rate, spring: spring.rate, diffPoints: (summer.rate - spring.rate) * 100 } : null,
    typical: typicalDelay(cells),
    minFlights,
  };
}

// ---------------------------------------------------------------------- rota yayları
/**
 * Varış başına yay verisi. coords: Map(iata -> {ad, enlem, boylam}) ya da null.
 * Döner: {items: [{iata, ad, enlem, boylam, n, rate}], missing: [iata]} (koordinatı olmayanlar missing'te).
 */
export function arcItems(cells, coords, origin) {
  const items = [];
  const missing = [];
  for (const d of destTotals(cells)) {
    if (d.dest === origin) continue;
    const spot = coords ? coords.get(d.dest) : null;
    if (spot && isNum(spot.enlem) && isNum(spot.boylam)) items.push({ iata: d.dest, ad: spot.ad, enlem: spot.enlem, boylam: spot.boylam, n: d.n, rate: d.rate });
    else missing.push(d.dest);
  }
  return { items, missing };
}

/** Yay kalınlığı: uçuş sayısının karekökü ile orantılı (alan ~ uçuş), minimum ile maksimum arasında. */
export function arcWidth(n, maxN, min = 1.5, max = 8) {
  if (!(maxN > 0) || !isNum(n) || n < 0) return min;
  return min + (max - min) * Math.sqrt(Math.min(1, n / maxN));
}

const round1 = (v) => Math.round(v * 10) / 10;

/**
 * İki ekran noktası arasında ikinci dereceden Bezier yayı; kontrol noktası doğrunun ortasından, dikey
 * yönde (kuzeye doğru) uzunluğun `bulge` katı kadar uzaktadır. Döner: {d, mid: [x, y]} (yayın orta noktası).
 */
export function arcGeometry(x0, y0, x1, y1, bulge = 0.2) {
  const dx = x1 - x0;
  const dy = y1 - y0;
  const dist = Math.hypot(dx, dy) || 1;
  let px = dy / dist;
  let py = -dx / dist;
  if (py > 0 || (py === 0 && px < 0)) {
    px = -px;
    py = -py;
  }
  const cx = (x0 + x1) / 2 + px * bulge * dist;
  const cy = (y0 + y1) / 2 + py * bulge * dist;
  return {
    d: `M${round1(x0)} ${round1(y0)}Q${round1(cx)} ${round1(cy)} ${round1(x1)} ${round1(y1)}`,
    mid: [round1(0.25 * x0 + 0.5 * cx + 0.25 * x1), round1(0.25 * y0 + 0.5 * cy + 0.25 * y1)],
  };
}
