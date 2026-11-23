# M3 – Kalibrasyon, conformal, interval80, iptal erken durması, tur tavanı, tarih özellikleri (karar notu)

- **Tarih:** 2026-11-20 · **Durum:** kod yazıldı, **hiçbiri çalıştırılmadı**; sonuçlar çalıştırmadan sonra eklenecek.
- **Dayanak:** `experiments/modelleme-plani.md` (§1.2, §1.4, §3.3, §4.2, §4.3, §5.1, §5.3, §5.4), `experiments/models/run-20261119T182216Z/` (sonuç JSON + özet), aynı koşunun permütasyon incelemesi `permutation/perm-20261119T190850Z/`, `deliverables/src/flight_delay/mlops/project.yaml`.
- **Kural:** Bu belgedeki sayıların hepsi yukarıdaki koşu çıktılarından alındı ya da onlardan aritmetikle türetildi (türetilenler "türetilmiş" diye işaretli). Yeni sonuç yok. Son test (2026-03..08) hiçbir kodda okunmuyor; `allow_final_test` kullanılmadı.
- **Varsayılanlar değişmedi:** yeni seçeneklerin hepsi kapalı başlar; varsayılan `run_models` koşusu öncekiyle aynı çıktıyı üretir. Tek istisna: `--mlflow on/auto` ile kantil modeli `--interval-models` olmadan artık **en başta** reddediliyor (önceden saatler sonra MLflow sözleşme kontrolünde düşerdi; bkz. §3).

## Ad eşlemesi (yeni kod)

| Plan / görev | Kod |
|---|---|
| Kalibratör (isotonic birincil, Platt karşılaştırma) | `modeling/calibration.py` (`fit_isotonic`, `fit_platt`, `evaluate`, `Calibrator`) |
| Tek yönlü split-conformal, CQR | `modeling/conformal.py` (`one_sided_offset`, `cqr_offset`, `conformal_rank`) |
| Kalibrasyon + conformal (kaydedilmiş koşuda, yeniden eğitim yok) | `modeling/run_calibration.py` → `<koşu>/calibration/cal-<UTC>/` |
| %80 aralık metrikleri | `metrics.interval_metrics`, `metrics.interval_key` (`interval80_coverage`, `interval80_mean_width_min`) |
| α 0,10 / 0,90 modelleri | `gbm.INTERVAL_TASKS`, `run_models --interval-models` |
| Tur tavanı / gerçek tur sayısı | `gbm.TrainedModel.rounds_trained`, `hit_round_cap` (düzeltildi), `--quantile-num-boost-round` |
| İptal erken durdurma metriği, eğriler | `--cancel-early-stopping-metric`, `--record-curves`, `gbm.with_early_stopping_metric`, `gbm.predict_at` |
| Tarih özelliklerini çıkarma | `matrix.DATE_FEATURES`, `build_model_matrix(drop=...)`, `--drop-date-features` |
| Önceki koşunun parametreleri | `--tuning-from-run RUN_ID` |

## 1. Olasılık kalibrasyonu (ArrDel15, iptal; LightGBM + L + B1)

**Durum (koşu çıktısı):** ArrDel15 LightGBM Val-A ort. tahmin − gözlenen −0,0538 (yaygınlık 0,2228), Val-B −0,0160; L Val-A −0,0505, Val-B −0,0200; B1 Val-A −0,0027, Val-B +0,0082. İptal LightGBM Val-B −0,0225, L −0,0218.

**Kararlar ve gerekçeler**
1. **Yöntem: isotonic birincil, Platt karşılaştırma.** Plan §4.2 isotonic diyor; bu seçim sonuç görülmeden yapıldı (`calibration.PRIMARY_METHOD`). Platt = `metrics.calibration_slope_intercept` ile aynı lojistik yeniden kalibrasyon; raporlanan eğim ile uygulanan düzeltme tek koddan gelir.
2. **Yalnızca Val-B'de fit; Val-A hiç okunmaz.** Val-A ağaç sayısını seçti (erken durdurma); kalibratör orada fit edilseydi Val-A iki kez kullanılmış olurdu.
3. **Val-B içinde dürüst değerlendirme: zaman sıralı tek ayrım.** Fit = Val-B ∩ planın Şubat 2026 kayan conformal penceresi (`conformal_calibration_window(2026-02-01)` = 2025-12-06..2026-01-30) → **2026-01-01..01-30**; değerlendirme = **2026-02-01..02-28**; 2026-01-31 bir günlük embargo olarak iki kısma da girmez (plan §1.4 ile aynı kural). Ters katlama (Şubat'ta fit, Ocak'ta değerlendirme) geleceği geçmişe uydurur, kullanılmadı. İki ay ancak bir fit / bir değerlendirme ayrımına izin verir; bu bir sınırlılıktır (iki ay da kış, test ilkbahar–yaz).
4. **B1 de aynı kuralla kalibre edilir** (plan §4.2: "hem model hem B1 için aynı kural"). BSS her aşamada aynı aşamadaki B1'e göre (önce: ham B1, sonra: kendi kalibratöründen geçmiş B1).
5. **Raporlanan:** değerlendirme ayında önce → sonra Brier, BSS, log-loss, ECE (10 eşit frekanslı kutu), calibration-in-the-large, lojistik eğim/kesişim, ROC-AUC, PR-AUC (isotonic eşitlikleri sıralama metriklerini biraz oynatabilir); fit ayında örneklem içi değerler ayrıca ve etiketli; Origin segmentleri (n ≥ `segment_min_n`).
6. **Son test için:** tüm Val-B'de fit edilmiş "statik" kalibratörler `calibrators.json`'a yazılır (plan §1.5: kalibrasyon yöntemi kilitten önce dondurulur); burada değerlendirilmez.

## 2. Conformal aralıklar (kantil modelleri)

**Durum (koşu çıktısı):** LightGBM ham kapsama P80 0,7389 (Val-A) / 0,7734 (Val-B), P95 0,9178 / 0,9332; B1 P80 0,8001 / 0,8063, P95 0,9488 / 0,9498.

**Kararlar ve gerekçeler**
1. **P80 / P95 üst sınırları: planın tek yönlü split-conformal yöntemi** (§5.4): s = y − q̂_α, ĉ = ⌈(n+1)α⌉. küçük skor, ayarlı sınır q̂_α + ĉ. Bu, CQR'nin tek yönlü biçimidir (kantil regresyonun conformal ayarı). İki yönlü **CQR** yalnızca %80 aralık için (α 0,10/0,90 modelleri, §5.4); mevcut koşuda bu modeller yok, o yüzden CQR o koşuda "yok" diye raporlanır.
2. **Kalibrasyon kümesi Val-B, aynı zaman sıralı ayrım** (Ocak 1–30 fit, Şubat değerlendirme). Model kantilleri koşudaki gibi satır başına sıralandıktan sonra ayarlanır; B1 kantilleri tanımlandığı gibi. Hem model hem B1 aynı adımdan geçer (§5.4).
3. **numpy, MAPIE değil:** kurulu `mapie` paketinin kaynağı bu ortamdan okunamadı (`.venv` erişimi engelli), yani API doğrulanamadı; tahmin edilmedi. Yöntem tek formül; kendi fonksiyonumuz sentetik kapsama testiyle (`test_conformal.py`: değiş-tokuş edilebilir veride ortalama kapsama α ile α + 1/(n+1) arasında) ve bilinen değer testleriyle doğrulanıyor. MAPIE ile çapraz kontrol açık iş (Kullanıcıya soru 4).
4. **Raporlanan:** ofset (dk), sıra numarası k, değerlendirme ayında kapsama ve pinball önce/sonra, %80 aralıkta ortalama genişlik önce/sonra, ayar sonrası q080+c > q095+c kesişme oranı, Origin segmentlerinde hedefin ±5 puan içindeki havalimanı payı (K5 kuralı, burada tek ay üzerinde). k > n ise ofset +∞ (yetersiz kalibrasyon) diye raporlanır, sessizce kırpılmaz.
5. **Kabul (K5) yine son testte ve planın birincil aylık kayan penceresiyle** verilir; buradaki tek ay yöntemin ön kontrolüdür.

## 3. `interval80` metrikleri

- **Plan tanımı:** iki yönlü %80 aralık = LightGBM α = 0,10 ve 0,90 kantil modelleri (§4.2 tablo satırı, "çekirdek"); metrikler kapsama ve ortalama genişlik (dk) (§5.1); ikincil ölçüt kapsama [0,78; 0,82] (§5.3); conformal ayarı CQR (§5.4). Kodda `targets.INTERVAL_LEVELS = (0.10, 0.90)`; B1 için `baselines.BASELINE_QUANTILE_LEVELS` bu uçları zaten içeriyordu.
- **Uygulama:** `--interval-models` iki modeli ekler (aynı parametreler, aynı Val-A erken durdurma); B1 tablosu da 0,10/0,90 ile fit edilir. Her kantil bloğunda `interval80_coverage`, `interval80_mean_width_min`, `pinball_q010/q090`, `coverage_q010/q090`, ham kesişme oranı; B1'e göre farklar. Aralık uçları **çift olarak** sıralanır (alt = min, üst = maks), P50/P80/P95'ten ayrı: böylece ana kantillerin metrikleri aralık modellerinin eğitilip eğitilmemesine bağlı kalmaz ve önceki koşularla karşılaştırılabilir.
- **MLflow:** metrikler blok toplamından otomatik `{set}_interval80_coverage` / `{set}_interval80_mean_width_min` adlarıyla yazılır (project.yaml'daki adlar). project.yaml'da **değişiklik önermiyorum**: plan bu metrikleri çekirdek sayıyor. Ancak sonuç: MLflow açıkken kantil modelleri `--interval-models` olmadan çalışamaz; bunu koşunun sonunda değil başında hata olarak veriyorum.
- **Mevcut koşu (run-20261119T182216Z):** α 0,10/0,90 modelleri olmadığından interval80 bu koşu için **hesaplanamaz**; yeni koşu gerekir (§7 adım C).

## 4. İptal LightGBM'in 15. turda durması

**Koşu çıktısından kanıtlar**
- E1 – Taban oran kayması **yok** (train → Val-A): eğitim 117 706 / 9 127 110 = 0,01290, Val-A 19 323 / 1 506 008 = 0,01283, Val-B 25 274 / 689 119 = 0,03668 (türetilmiş, `universe` sayılarından). Yani "Val-A'da taban oran farklı" açıklaması geçersiz; Val-B'de oran yaklaşık 2,8 kat.
- E2 – 15 turdaki model az öğrenmiş görünüyor: Val-A kalibrasyon eğimi 1,676, Val-B 1,363 (> 1 = tahminler fazla düz). Öğrenme oranı 0,03; 15 tur bu oranda önsel orana çok yakın bir model demek. Yani yüksek öğrenme oranı açıklaması da zayıf.
- E3 – İlk 15 ağacın kazancının belirgin kısmı takvim özelliklerinde: day_of_year %13,2, day_of_month %7,2, days_to_holiday %5,4 (toplam %25,8, türetilmiş).
- E4 – Val-B permütasyonunda cancelled-lgbm için day_of_month, days_to_holiday, holiday_week, month "zararlı".
- E5 – Yaprak boyutu: min_child_samples = 1000, oysa eğitimde günde ortalama 9 127 110 / 731 ≈ 12 486 uçuş var (türetilmiş). Tek bir takvim günü rahatça bir yaprak olabilir. 24 aylık pencerede her day_of_year değeri yalnızca iki kez görülüyor. İptaller ise fırtına ya da kesinti günlerinde yoğunlaşıyor.
- E6 – L (ağaç değil, ay one-hot, sayısal sütunlar fit aralığına kırpılmış) Val-B'de daha iyi: AUC 0,7393 / 0,6879, PR-AUC 0,2282 / 0,0917. Val-A'da ise AUC 0,6541 / 0,6248.

**Kök neden hipotezleri (henüz doğrulanmadı)**
- **H1 (birincil):** takvim özellikleriyle **tekrar etmeyen olay günlerini ezberleme**. 15. turdan sonraki ağaçlar eğitimdeki belirli tarihlere (fırtına ya da kesinti günleri) bölünüyor, bu da Val-A'da log-loss'u bozuyor. E3, E4, E5 ve E6 bununla tutarlı.
- **H2:** log-loss'un erken platosu kalibrasyon kaymasından kaynaklanıyor olabilir; sıralama (AUC/AP) iyileşmeye devam ediyor olabilir. Bu durumda düzeltme, durdurma metriğini değiştirip kalibrasyonu Val-B'ye bırakmaktır.
- **H3:** Val-A'nın belirli bir ayı (ör. Ekim–Kasım 2025; plan §7 kapanma ve FAA azaltımları notu, doğrulanmadı) log-loss'a baskın geliyor olabilir.
- Elenen ya da zayıf: taban oran kayması (E1), yüksek öğrenme oranı (E2). `scale_pos_weight` / `is_unbalance` plan gereği kullanılmaz (§4.2).

**Teşhis deneyi (yalnızca Val-A ile karar verilir; aşağıdaki kural sonuç görülmeden yazıldı)**
- D1: `--models cancelled --tuning-from-run run-20261119T182216Z --record-curves --num-boost-round 1000 --early-stopping-rounds 1000`. Sabır = tavan olduğundan erken durma tetiklenmez ve tam Val-A eğrileri (log-loss, AUC, AP) alınır. Ayrıca 10/15/25/50/100/200/400/800 turlarda **ay bazında** Val-A log-loss, ortalama tahmin ve yaygınlık kaydedilir.
- D2: D1 + `--drop-date-features`.
- **Karar kuralı** (eşikler 100 ve 30 tur sonuçtan önce konmuş kurallardır, ayarlanmış değerler değil):
  - R1: D2'de Val-A log-loss en iyi turu ≥ 100 **ve** D2'nin en iyi Val-A log-loss'u < D1'inki ise H1 desteklenir. Düzeltme: iptal modelinden takvim özelliklerini çıkarmak (diğer modeller için §6 deneyi karar verir).
  - R2: D1'de AP ya da AUC en iyi turu ≥ 100, log-loss en iyi turu ≤ 30 ve ay checkpoint'lerinde |ort. tahmin − yaygınlık| log-loss'un en iyi turundan sonra büyüyorsa H2 desteklenir. Düzeltme: `--cancel-early-stopping-metric average_precision` ve Val-B'de isotonic kalibrasyon. PR-AUC, iptalin planlanan birincil metriği (§3.2, K6).
  - İkisi birden sağlanırsa R1 önce gelir (ölçütü değil nedeni düzeltir). R1 uygulandıktan sonra log-loss yine 30 turdan önce duruyorsa AP eklenir.
  - Hiçbiri sağlanmazsa bu tasarımda LightGBM iptal modeli L'yi geçmiyor demektir. Bu olduğu gibi raporlanır; Val-B'ye bakarak ayar yapılmaz.
- **Neden "en az N iterasyon" değil:** sabit bir alt sınır, gerekçesi veriden gelmeyen bir sayıdır ve doğru değeri ancak Val-B'ye bakarak bulunabilir. Bu yüzden önerilmedi.
- D1 ve D2 Val-B metriklerini de yazar (`run_models` hep yazar). Bunlar karar için kullanılmaz; bunu raporda belirteceğim.

## 5. Kantil modelleri tur tavanı

- **Hata bulundu ve düzeltildi:** `hit_round_cap` yanlış hesaplanıyordu. `lgb.train` dönüşte booster'ı kendi metin modelinden yeniden yüklüyor ve bu model yalnızca en iyi iterasyona kadar olan ağaçları tutuyor. Bu yüzden `current_iteration()` eğitilen tur sayısını değil en iyi iterasyonu veriyor. q050 için en iyi tur 1999, tavan 2000, sabır 100: erken durma ancak 2099. turda tetiklenebilirdi, yani 2000 turun hepsi eğitildi ve **tavana ulaşıldı**. Koşu özeti ise "False" yazıyor; bu açıklamayla tutarlı. LightGBM kaynağını okuyamadığım için (.venv erişimi yok) davranış kodla değil bu tutarlılıkla gösteriliyor. Yeni hesap bir callback ile eğitilen turları sayıyor: `hit_round_cap` = tavana kadar eğitildi **ve** sabır dolmadı. Testler: sabır tavandan büyükken True, erken durmada False. Eski koşunun JSON'u değiştirilmedi; oradaki `hit_round_cap` değerleri güvenilir değil.
- **Seçenek:** `--quantile-num-boost-round N`, yalnızca kantil modellerine uygulanır. Önerim N = 5000. Bu, sonuç görülmeden konan bir üst sınır; yeni `hit_round_cap` sınırın yetip yetmediğini gösterecek.
- **Süre (türetilmiş, ölçüm değil):** koşuda q050 686,3 sn'de 2000 tur, q080 404,41 sn'de 1125 tur, q095 190,47 sn'de 496 tur eğitti (en iyi + 100 sabır). Bu tur başına yaklaşık 0,34–0,38 sn eder (veri kurulumu dahil). Tur başına sürenin değişmediği varsayımıyla q050 5000 tura kadar giderse üst sınır ≈ 5000 × 0,343 ≈ 1715 sn (≈ 29 dk), yani yaklaşık +17 dk. q010/q090 modelleri her biri en fazla (tavan × ~0,35 sn) ekler; kaç turda duracakları bilinmiyor. Permütasyon süresi ağaç sayısıyla büyür: koşuda q050 permütasyonu 1999 ağaçla 2475 sn sürdü.

## 6. Tarih özellikleri (permütasyon bulgusu)

- `--drop-date-features`: `month, day_of_year, day_of_month, days_to_holiday, holiday_week` her matristen (aramadaki katlar, eğitim, Val-A, Val-B) çıkar. `day_of_week` grupta değil (kullanıcının listesinde yok). Özellik sözleşmesi tam olarak kurulup doğrulanmaya devam eder; yalnızca X'e girmezler. Sözleşme özeti (`contract_sha256`) yalnızca modelin gördüğü özelliklerle hesaplanır (hiçbir şey çıkarılmadığında değişmez). `run_permutation` ve `run_calibration` matrisi koşunun çıkardığı özelliklerle yeniden kurar.
- Varsayılan değişmedi. Deney kullanıcı karar verince yapılacak.
- **Risk:** bu karar Val-B permütasyonuna dayanıyor. Val-B artık eşik seçimi, kalibrasyon, conformal ve özellik teşhisi için kullanılmış oluyor. Bu yüzden Val-B'deki karşılaştırma bu seçim için iyimser olur. Son test etkilenmez. Karşı önlem: kararı Val-A ile birlikte okumak ve Val-B'de tekrar tekrar ayar yapmamak.

## 7. Önerilen çalıştırma sırası

| Adım | Ne | Neden |
|---|---|---|
| 0 | pytest, ruff, mypy | Yeni kod ve mevcut 469 test |
| A | `run_calibration --run-id run-20261119T182216Z` | Ucuz, yeniden eğitim yok: kalibrasyon + tek yönlü conformal (CQR "yok") |
| B | D1, D2 (yalnızca iptal) | §4 karar kuralı |
| C | Tam koşu: `--interval-models --quantile-num-boost-round 5000 --tuning-from-run run-20261119T182216Z` (+ B'de seçilen iptal düzeltmesi), sonra `run_calibration` ve `run_permutation` | interval80 + CQR, tavan, düzeltilmiş `hit_round_cap` |
| D | C + `--drop-date-features` (kullanıcı kararıyla) | §6 deneyi; aynı parametreler, tek değişiklik |

## Karar (kullanıcı, 2026-11-20): iptal LightGBM takvim özellikleri olmadan – önceden yazılan kuraldan bilinçli sapma

- D1 (tüm özellikler) Val-A: log-loss en iyi tur 15, değer 0,0671; AUC en iyi 0,631 (tur 181); AP en iyi 0,042 (tur 8).
- D2 (`--drop-date-features`) Val-A: log-loss en iyi tur 73, değer 0,0636; AUC en iyi 0,697 (tur 86); AP en iyi 0,072 (tur 115).
- Kural sonucu: R1 sağlanmadı (en iyi tur 73 < 100). R2 kâğıt üzerinde sağlandı (AUC en iyi turu 181 ≥ 100, log-loss en iyi turu 15 ≤ 30, ort. tahmin − yaygınlık farkı 10→15 turda büyüyor), ama R2'nin düzeltmesi (AP ile erken durma) D1'de 8. turda durur, sorunu çözmez.
- Karar: kural dışı olarak H1'in düzeltmesi seçildi. Gerekçe: 100 tur eşiği keyfiydi; iyileşme Val-A'nın üç ölçütünde birden ve büyük. Karar Val-A'ya dayanır (Val-B kullanılmadı).
- Uygulama: iptal LightGBM modeli = D2 koşusu `run-20261120T174502Z` (parametreler `run-20261119T182216Z`'den; 1000 tur eğitildi, en iyi tur 73; 100 turluk sabırla da aynı tur seçilirdi). ArrDel15 ve kantil modeller C koşusundan (takvim özellikleri yerinde). Son testte iki koşu kimliği birlikte kullanılacak.
