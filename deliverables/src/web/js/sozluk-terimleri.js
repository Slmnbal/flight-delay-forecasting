// Sözlük terimleri, Türkçe ve İngilizce. Her terimin kısa bir kimliği (#sozluk/kimlik bağlantısı için),
// 1-3 cümlelik sade bir tanımı ve gerekiyorsa "bu sitede nerede görülür" notu vardır.
// İngilizce karşılık `en` alanındadır (terim, tanim, nerede); grup adının karşılığı `adEn` alanındadır.

import { getLang } from './metin.js';

export const GRUPLAR = [
  {
    ad: 'Veri ve hedef',
    adEn: 'Data and target',
    terimler: [
      { id: 'arrdel15', terim: 'ArrDel15', tanim: 'Uçuşun tarifedeki varış saatinden 15 dakika ya da daha fazla geç varması. ABD Ulaştırma İstatistikleri Bürosu’nun (BTS) resmi “rötarlı” tanımıdır.', nerede: 'Sitedeki “rötar oranı” ve “geç varış oranı” budur.',
        en: { terim: 'ArrDel15', tanim: 'A flight arriving 15 minutes or more after its scheduled arrival time. This is the official “delayed” definition of the US Bureau of Transportation Statistics (BTS).', nerede: 'This is the “delay rate” and “late-arrival rate” on this site.' } },
      { id: 'varis-rotari', terim: 'Varış rötarı (dk)', tanim: 'Gerçek varış ile tarifedeki varış arasındaki fark. Eksi değer erken varış demektir.', nerede: 'Keşfet sayfasındaki rota tablosunda P50, P80 ve P95 sütunları bu farkın kantilleridir.',
        en: { terim: 'Arrival delay (min)', tanim: 'The difference between the actual arrival and the scheduled arrival. A negative value means early arrival.', nerede: 'In the Explore route table, the P50, P80 and P95 columns are quantiles of this difference.' } },
      { id: 'iptal', terim: 'İptal', tanim: 'Tarifeli bir uçuşun gerçekleşmemesi. Rötar kantilleri yalnızca gerçekleşen uçuşlar için hesaplanır.',
        en: { terim: 'Cancellation', tanim: 'A scheduled flight that does not operate. Delay quantiles are computed only for flights that were operated.' } },
      { id: 'bts', terim: 'BTS', tanim: 'ABD Ulaştırma Bakanlığı’nın Ulaştırma İstatistikleri Bürosu. Uçuş verisinin kaynağıdır (kamu verisi).', nerede: 'Yöntem sayfasında, veri kaynakları listesinde.',
        en: { terim: 'BTS', tanim: 'The Bureau of Transportation Statistics of the US Department of Transportation. It is the source of the flight data (public data).', nerede: 'On the Method page, in the list of data sources.' } },
      { id: 'metar', terim: 'METAR', tanim: 'Havalimanlarının düzenli yayımladığı hava gözlem raporu: rüzgâr, görüş, yağış, bulut ve benzeri.', nerede: 'T2 modelinin kullandığı hava bilgisi budur; Yöntem sayfasındaki hava deneyinde.',
        en: { terim: 'METAR', tanim: 'The weather observation report that airports publish regularly: wind, visibility, precipitation, cloud and so on.', nerede: 'This is the weather information the T2 model uses; in the weather experiment on the Method page.' } },
      { id: 'test-donemi', terim: 'Test dönemi', tanim: 'Modelin hiç görmediği, sonuçların ölçüldüğü dönem (2026-03 ile 2026-08 arası). Bir kez açıldı.', nerede: 'Sonuçlar sayfasında “Nihai test”.',
        en: { terim: 'Test period', tanim: 'The period the model never saw, in which the results are measured (2026-03 to 2026-08). It was opened once.', nerede: 'On the Results page as “Final test”.' } },
      { id: 'egitim-dogrulama', terim: 'Eğitim ve doğrulama dönemleri', tanim: 'Eğitim, modelin öğrendiği dönemdir (2023-09 ile 2025-08). Doğrulama, ayar ve kalibrasyon için ayrılan dönemlerdir (2025-09 ile 2026-02). Zaman sırası korunur: geleceğin verisi geçmişin modeline girmez.', nerede: 'Sonuçlar sayfasında “Zaman sıralı bölme” tablosu.',
        en: { terim: 'Training and validation periods', tanim: 'Training is the period the model learns from (2023-09 to 2025-08). Validation periods are set aside for tuning and calibration (2025-09 to 2026-02). Time order is kept: data from the future never enters a model of the past.', nerede: 'On the Results page, the “Time-ordered split” table.' } },
      { id: 'hucre', terim: 'Hücre', tanim: 'Rota (kalkış–varış) × kalkış saat bloğu × mevsim grubu. Rota tablosundaki her satır bir hücredir.', nerede: 'Keşfet sayfasındaki rota tablosu.',
        en: { terim: 'Cell', tanim: 'Route (origin–destination) × departure time block × season group. Each row of the route table is one cell.', nerede: 'The route table on the Explore page.' } },
      { id: 'segment', terim: 'Segment', tanim: 'Sonuçların bir boyuta göre kırılımındaki bir parça: örneğin bir havalimanı, bir saat bloğu ya da bir ay.', nerede: 'Yöntem sayfasındaki hata analizi.',
        en: { terim: 'Segment', tanim: 'One part of a breakdown of the results along one dimension: for example an airport, a time block or a month.', nerede: 'The error analysis on the Method page.' } },
      { id: 'olay-gunu', terim: 'Olay günü', tanim: 'Rötar oranının, eğitim dönemindeki günlük oranların %95’lik dilimini aştığı olağandışı gün (fırtına gibi).', nerede: 'Yöntem sayfasındaki hata analizinde “Olay günleri ve diğer günler” kırılımı.',
        en: { terim: 'Event day', tanim: 'An unusual day (such as a storm) on which the delay rate exceeded the 95th percentile of the daily rates in the training period.', nerede: 'In the error analysis on the Method page, the “Event days and other days” breakdown.' } },
    ],
  },
  {
    ad: 'Model ve tahmin',
    adEn: 'Model and prediction',
    terimler: [
      { id: 'b1', terim: 'B1 (referans)', tanim: 'Basit bir kural: “geçmişte bu rotada, bu saat bloğunda ne olduysa”. Modelin gerçekten bir şey öğrenip öğrenmediğini görmek için karşılaştırma noktasıdır.', nerede: 'Sonuçlar panosunda ve Hikâye’nin ilk grafiğinde.',
        en: { terim: 'B1 (reference)', tanim: 'A simple rule: “whatever happened in the past on this route in this time block”. It is the point of comparison for seeing whether the model has really learned anything.', nerede: 'On the Results board and in the first chart of the Story.' } },
      { id: 'plan-modeli', terim: 'Plan modeli', tanim: 'Yalnızca tarife yapılırken bilinen bilgiyle tahmin yapar; hava bilgisi yoktur. Tampon önerileri bundan gelir.', nerede: 'Keşfet sayfasındaki rota tablosunda kantiller ve üst sınırlar.',
        en: { terim: 'Plan model', tanim: 'Predicts using only what is known when the schedule is made; there is no weather information. The buffer suggestions come from it.', nerede: 'The quantiles and upper limits in the Explore route table.' } },
      { id: 't2-modeli', terim: 'T2 modeli', tanim: 'Kalkıştan 2 saat önceki hava gözlemlerini de kullanır; operasyon ekibi içindir.', nerede: 'Keşfet sayfasındaki havalimanı haritasında tahmin oranları.',
        en: { terim: 'T2 model', tanim: 'Also uses the weather observations from 2 hours before departure; it is meant for an operations team.', nerede: 'The predicted rates on the Explore airport map.' } },
      { id: 'lightgbm', terim: 'LightGBM', tanim: 'Karar ağaçlarını art arda ekleyerek öğrenen, tablo verisinde güçlü bir makine öğrenmesi yöntemidir.',
        en: { terim: 'LightGBM', tanim: 'A machine learning method that learns by adding decision trees one after another; it is strong on tabular data.' } },
      { id: 'olasilik-kalibrasyon', terim: 'Olasılık ve kalibrasyon', tanim: 'Model “%30” dediğinde, bu tür uçuşların gerçekten yaklaşık %30’unun gecikmesi beklenir. Kalibrasyon, bu uyumu sağlayan düzeltmedir.', nerede: 'Yöntem sayfasındaki kalibrasyon bölümünde güvenilirlik diyagramı.',
        en: { terim: 'Probability and calibration', tanim: 'When the model says “30%”, about 30% of such flights should really be late. Calibration is the correction that makes this match.', nerede: 'The reliability diagram in the calibration section of the Method page.' } },
      { id: 'platt', terim: 'Platt (aylık kayan)', tanim: 'Ham skorları olasılığa çeviren basit bir kalibrasyon. Her ay son yaklaşık 2 ayın verisiyle yeniden ayarlanır; böylece mevsim değişimine uyum sağlar.',
        en: { terim: 'Platt (monthly rolling)', tanim: 'A simple calibration that turns raw scores into probabilities. Every month it is refitted on roughly the last 2 months of data, so it adapts to seasonal change.' } },
      { id: 'kantil', terim: 'Kantil (P50, P80, P95)', tanim: 'Rötar süresi için sınırlar. P80 = 40 dk demek, “bu tür uçuşların %80’i en fazla 40 dakika gecikir” demektir.', nerede: 'Keşfet sayfasındaki rota tablosu.',
        en: { terim: 'Quantile (P50, P80, P95)', tanim: 'Limits for the delay time. P80 = 40 min means “80% of such flights are at most 40 minutes late”.', nerede: 'The route table on the Explore page.' } },
      { id: 'conformal', terim: 'Conformal ayar', tanim: 'Kantil sınırlarını, geçmişteki gerçek hatalara bakarak hedef kapsamayı tutturacak biçimde genişleten ya da daraltan yöntemdir. Kayan: her ay yeniden yapılır. Statik: bir kez yapılır. Ham: ayar yoktur.', nerede: 'Yöntem sayfasındaki kalibrasyon bölümünde aylık kapsama grafikleri.',
        en: { terim: 'Conformal adjustment', tanim: 'A method that widens or narrows the quantile limits, by looking at real past errors, so that they hit the target coverage. Rolling: redone every month. Static: done once. Raw: no adjustment.', nerede: 'The monthly coverage charts in the calibration section of the Method page.' } },
      { id: 'kapsama', terim: 'Kapsama', tanim: 'Gerçek değerin sınırın altında kalma oranı. P80 sınırı için hedef %80’dir.', nerede: 'Keşfet ve Yöntem sayfaları.',
        en: { terim: 'Coverage', tanim: 'The share of cases in which the real value stays below the limit. For the P80 limit the target is 80%.', nerede: 'The Explore and Method pages.' } },
      { id: 'sizinti', terim: 'Sızıntı (leakage)', tanim: 'Modelin, tahmin anında bilemeyeceği bir bilgiyi (örneğin gerçekleşen kalkış saatini) görmesi. Sonuçları sahte biçimde iyi gösterir. İki ayrı inceleme sızıntı bulmadı.',
        en: { terim: 'Leakage', tanim: 'The model seeing information it could not know at prediction time (for example the actual departure time). It makes results look falsely good. Two separate reviews found no leakage.' } },
    ],
  },
  {
    ad: 'Ölçütler',
    adEn: 'Measures',
    terimler: [
      { id: 'roc-auc', terim: 'ROC-AUC', tanim: 'Modelin geç kalacak bir uçuşa, zamanında gelecek bir uçuştan daha yüksek risk verme olasılığı. 0,5 yazı tura, 1 kusursuz demektir.', nerede: 'Hikâye’nin ilk grafiği, Sonuçlar panosu ve hava deneyi.',
        en: { terim: 'ROC-AUC', tanim: 'The chance that the model gives a higher risk to a flight that will be late than to one that will arrive on time. 0.5 is a coin flip, 1 is perfect.', nerede: 'The first chart of the Story, the Results board and the weather experiment.' } },
      { id: 'pr-auc', terim: 'PR-AUC', tanim: 'Geç uçuşları yakalama başarısını (kesinlik ve duyarlılık birlikte) özetler. Olay seyrekken ROC-AUC’tan daha zorlayıcıdır.',
        en: { terim: 'PR-AUC', tanim: 'Summarises how well late flights are caught (precision and recall together). It is more demanding than ROC-AUC when the event is rare.' } },
      { id: 'brier', terim: 'Brier skoru', tanim: 'Olasılık tahminlerinin ortalama kare hatası. Düşük olan daha iyidir.',
        en: { terim: 'Brier score', tanim: 'The mean squared error of probability predictions. Lower is better.' } },
      { id: 'bss', terim: 'Brier skor kazancı (BSS)', tanim: 'Modelin Brier skorunun B1’e göre iyileşme payı. 0’ın üstü, B1’den iyi demektir.', nerede: 'Sonuçlar panosu.',
        en: { terim: 'Brier skill score (BSS)', tanim: 'The share by which the model’s Brier score improves on B1. Above 0 means better than B1.', nerede: 'The Results board.' } },
      { id: 'ece', terim: 'ECE', tanim: 'Tahmin edilen olasılıklar ile gerçekleşen oranlar arasındaki ortalama fark (kalibrasyon hatası).',
        en: { terim: 'ECE', tanim: 'The average gap between predicted probabilities and observed rates (calibration error).' } },
      { id: 'citl', terim: 'CITL (genel sapma)', tanim: 'Ortalama tahmin ile gerçek oran arasındaki fark; 0 idealdir. Eksi değer, modelin riski genel olarak düşük tahmin ettiğini gösterir.', nerede: 'Hikâye’deki kalibrasyon kartı ve Sonuçlar panosu.',
        en: { terim: 'CITL (overall bias)', tanim: 'The difference between the average prediction and the real rate; 0 is ideal. A negative value shows that the model underestimates risk overall.', nerede: 'The calibration card in the Story and the Results board.' } },
      { id: 'kalibrasyon-egimi', terim: 'Kalibrasyon eğimi', tanim: '1 idealdir. 1’den küçük değer tahminlerin fazla uçta olduğunu, büyük değer fazla temkinli olduğunu gösterir.', nerede: 'Sonuçlar panosu.',
        en: { terim: 'Calibration slope', tanim: '1 is ideal. A value below 1 shows that predictions are too extreme; a value above 1 shows that they are too cautious.', nerede: 'The Results board.' } },
      { id: 'pinball', terim: 'Pinball kaybı', tanim: 'Kantil tahminlerinin hatası. Düşük olan daha iyidir.',
        en: { terim: 'Pinball loss', tanim: 'The error of quantile predictions. Lower is better.' } },
      { id: 'kabul-olcutleri', terim: 'Kabul ölçütleri (K1–K7)', tanim: 'Test öncesinde yazılan geçme ya da kalma kuralları. 5’i geçti, K5 ve K6 geçmedi; sonuçlar olduğu gibi yayımlandı.', nerede: 'Sonuçlar sayfasında.',
        en: { terim: 'Acceptance criteria (K1–K7)', tanim: 'Pass or fail rules written before the test. 5 passed, K5 and K6 did not; the results were published as they are.', nerede: 'On the Results page.' } },
    ],
  },
  {
    ad: 'İstatistik',
    adEn: 'Statistics',
    terimler: [
      { id: 'guven-araligi', terim: 'Güven aralığı (%95 GA)', tanim: 'Bir sonucun belirsizlik aralığı. Aralık 0’ı içermiyorsa fark anlamlı kabul edilir.', nerede: 'Sonuçlar panosu ve hava deneyi.',
        en: { terim: 'Confidence interval (95% CI)', tanim: 'The range of uncertainty of a result. If the interval does not contain 0, the difference is considered significant.', nerede: 'The Results board and the weather experiment.' } },
      { id: 'gun-blok-bootstrap', terim: 'Gün blok bootstrap', tanim: 'Aynı günün uçuşları birbirine bağlı olduğu için (ortak hava gibi), günleri bütün olarak yeniden örnekleyerek güven aralığı hesaplama yöntemi. 1000 tekrar kullanıldı.',
        en: { terim: 'Day-block bootstrap', tanim: 'A way to compute a confidence interval by resampling whole days, because flights on the same day are linked to each other (for example by shared weather). 1000 repetitions were used.' } },
      { id: 'holm', terim: 'Holm düzeltmesi', tanim: 'Birden fazla karşılaştırma yapınca şans eseri “anlamlı” bulma riskini kontrol eden düzeltme.',
        en: { terim: 'Holm correction', tanim: 'A correction that controls the risk of finding something “significant” by chance when several comparisons are made.' } },
      { id: 'onceden-kayit', terim: 'Önceden kayıt', tanim: 'Kuralların ve ölçütlerin sonuç görülmeden yazılması. Sonuca göre kural değiştirmeyi engeller.',
        en: { terim: 'Pre-registration', tanim: 'Writing down the rules and criteria before seeing the results. It prevents changing the rules to fit the result.' } },
      { id: 'kesifsel', terim: 'Keşifsel (post hoc)', tanim: 'Sonuç görüldükten sonra yapılan inceleme. İpucu verir ama kesin kanıt değildir.', nerede: 'Yöntem sayfasındaki hata analizi ve Tampon sayfasındaki keşifsel bölüm.',
        en: { terim: 'Exploratory (post hoc)', tanim: 'An analysis made after seeing the results. It gives hints but is not firm proof.', nerede: 'The error analysis on the Method page and the exploratory section of the Buffers page.' } },
    ],
  },
  {
    ad: 'Optimizasyon (OR)',
    adEn: 'Optimization (OR)',
    terimler: [
      { id: 'blok-sure-tamponu', terim: 'Blok süre tamponu', tanim: 'Tarifedeki uçuş süresine eklenen fazladan dakika. Rötarı emer ama uçak ve ekip zamanına mal olur.', nerede: 'Keşfet sayfasındaki rota tablosunda “Önerilen tampon” sütunu.',
        en: { terim: 'Block-time buffer', tanim: 'Extra minutes added to the scheduled flight time. It absorbs delay but costs aircraft and crew time.', nerede: 'The “Suggested buffer” column in the Explore route table.' } },
      { id: 'maliyet-orani', terim: 'Maliyet oranı (τ)', tanim: 'Bir dakika rötarın, bir dakika boşta beklemeye göre ne kadar pahalı sayıldığı. τ = 0,80 olduğunda rötar dakikası 4 kat pahalıdır (varsayım, ölçülmedi). Önerilen tampon, plan modelinin τ kantilidir.', nerede: 'Hikâye’deki ve Tampon sayfasındaki kaydırıcı.',
        en: { terim: 'Cost ratio (τ)', tanim: 'How much more expensive one minute of delay is counted than one minute of idle waiting. When τ = 0.80, a minute of delay is 4 times as expensive (an assumption, not measured). The suggested buffer is the τ quantile of the plan model.', nerede: 'The slider in the Story and on the Buffers page.' } },
      { id: 'newsvendor', terim: 'Newsvendor', tanim: 'Az ve fazla stokun (burada az ve fazla tamponun) maliyetini dengeleyen klasik karar modeli. En iyi tampon, dağılımın τ kantilidir.',
        en: { terim: 'Newsvendor', tanim: 'The classic decision model that balances the cost of too little and too much stock (here, too little and too much buffer). The best buffer is the τ quantile of the distribution.' } },
      { id: 'tampon-butcesi', terim: 'Tampon bütçesi', tanim: 'Uçuş başına ortalama eklenebilecek en fazla dakika. Dakikalar, hücrelere en verimli biçimde dağıtılır.', nerede: 'Tampon sayfasındaki bütçe eğrisi.',
        en: { terim: 'Buffer budget', tanim: 'The most minutes that can be added per flight on average. The minutes are spread over the cells in the most efficient way.', nerede: 'The budget curve on the Buffers page.' } },
      { id: 'lp-milp', terim: 'LP / MILP', tanim: 'Doğrusal programlama ve karma tamsayılı programlama: kısıtlar altında en iyi kararı bulan matematiksel modeller. Pyomo ile yazıldı, HiGHS çözücüsüyle çözüldü.',
        en: { terim: 'LP / MILP', tanim: 'Linear programming and mixed-integer programming: mathematical models that find the best decision under constraints. They were written with Pyomo and solved with the HiGHS solver.' } },
      { id: 'tek-havayolu-kurali', terim: 'Tek havayolu kuralı', tanim: 'Bir hücrede ya da havalimanında uçuşların %90’ından fazlası tek havayoluna aitse sayılar yayımlanmaz; böylece sayılar bir havayolunun performansı gibi okunmaz.', nerede: 'Keşfet sayfasında “Yayımlanmadı”.',
        en: { terim: 'Single-airline rule', tanim: 'If more than 90% of the flights in a cell or at an airport belong to one airline, the numbers are not published, so that they are not read as the performance of an airline.', nerede: '“Not published” on the Explore page.' } },
    ],
  },
];

const alan = (term, key) => {
  if (getLang() === 'en' && term.en && typeof term.en[key] === 'string') return term.en[key];
  return term[key];
};

/** Bir grubun seçili dildeki adı. */
export const grupAdi = (group) => (getLang() === 'en' && group.adEn ? group.adEn : group.ad);

/** Bir terimin seçili dildeki {terim, tanim, nerede} değerleri (nerede yoksa null). */
export function terimMetni(term) {
  const nerede = alan(term, 'nerede');
  return { terim: alan(term, 'terim'), tanim: alan(term, 'tanim'), nerede: nerede || null };
}

/** Kimliğe göre terimin seçili dildeki adı (bulunamazsa kimliğin kendisi). */
export function terimAdi(id) {
  for (const group of GRUPLAR) {
    const hit = group.terimler.find((t) => t.id === id);
    if (hit) return alan(hit, 'terim');
  }
  return id;
}
