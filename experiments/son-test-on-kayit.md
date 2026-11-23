# Son test – önceden kayıt (pre-registration)

- **Tarih:** 2026-11-21 · **Hazırlayan:** Data Scientist (builder) · **Durum:** önceden kayıt; kullanıcı onayına sunulur.
- **Dayanak (bağlayıcı):** `decisions/M3-son-test-oncesi-kararlari.md` (4 karar), `reports/red-team-modelleme-incelemesi.md`, `experiments/modelleme-plani.md` §1.5, §5.1–5.4, §6, §7, §8, `experiments/kalibrasyon-conformal-kararlari.md`.
- **Kod:** `flight_delay.modeling.calendar_rule` (kural a/b), `final_lock` (kilit girdisi + kilit kaydı), `final_eval` (değerlendirme çekirdeği), `run_final_test` (son test ve prova), `bootstrap` (gün blok bootstrap, Holm). Bu belgedeki her kural kodda karşılığıyla yazıldı; ikisi çelişirse bu belge geçerlidir ve kod düzeltilir (testten ÖNCE).
- **Bu belge yazılırken bilinenler (açıklık için):** C (`run-20261120T175822Z`), D1, D2 ve `run-20261119T182216Z` koşularının Val-A / Val-B toplamları ve red-team raporundaki aylık değerler biliniyor. **Bilinmeyenler:** D adımı koşusu (T2 + `--drop-date-features`), plan sözleşmeli iki koşu, prova ve son test; hiçbiri çalışmadı. Son test verisi (2026-03..08) hiçbir kodda okunmadı; `allow_final_test` yalnızca `run_final_test --final` içinde, kilit kaydından sonra kullanılır.
- **Sayı yok:** Bu belgede performans sayısı ya da beklentisi yoktur. Tolerans sayıları provadan sonra, aşağıdaki kuralla, kod tarafından hesaplanır.

---

## (a) D adımı: T2 ArrDel15 ve kantil modellerinde takvim özellikleri

**Takvim özellikleri:** `matrix.DATE_FEATURES` = `month, day_of_year, day_of_month, days_to_holiday, holiday_week` (`day_of_week` grupta değil).
**Karşılaştırılan koşular:** takvimli = C (`run-20261120T175822Z`); takvimsiz = D (yeni koşu, aşağıda c). Tek fark `--drop-date-features`; parametreler, tur tavanları, erken durdurma kuralı aynı. Araç: `python -m flight_delay.modeling.calendar_rule --with-calendar <C> --without-calendar <D>` (kuralı mekanik uygular; koşuların yalnızca `val_a` bloğunu okur).

**Kural (yalnızca Val-A; Val-B okunmaz):**
1. **ArrDel15:** takvim özellikleri **çıkarılır** ancak ve ancak takvimsiz modelin Val-A **Brier** skoru hem **toplamda** hem de **4 aydan (Eylül–Aralık 2025) en az 3'ünde** takvimli modelinkinden **küçükse**. Aksi halde takvim özellikleri kalır.
2. **Kantiller (P50/P80/P95 ve %80 aralığın 0,10/0,90 uçları tek karar):** çıkarılır ancak ve ancak aynı iki koşul (toplamda küçük ve ≥ 3/4 ayda küçük) **hem P80 pinball'unda hem P95 pinball'unda** sağlanıyorsa. Aksi halde kalır.
3. Eşitlik iyileşme sayılmaz (kesin "<"). Karşılaştırma geçersizse (araç `valid: false` yazar: farklı satırlar, farklı parametreler, farklı çıkarılan özellikler) takvim özellikleri kalır ve durum raporlanır; kural esnetilmez.

**Gerekçeler (veriye bakmadan):**
- *Yalnızca Val-A:* hipotez Val-B permütasyonundan doğdu (red-team M1/M3); aynı veriyle doğrulamak döngüsel olur. Val-A erken durdurmayı seçtiği için hafif iyimserdir, ama iki koşu için aynı ölçüde (aynı kural).
- *Brier:* uygun (proper) bir skor ve koşular onu ay kırılımıyla kaydediyor (`segments.month`); log-loss yalnızca toplamda kayıtlı. Log-loss toplamı ve aylık CITL bilgi olarak yazılır, kararı değiştirmez.
- *3/4:* dört aylık bir pencerede en küçük kesin çoğunluk; keyfi bir fark eşiği (ör. "0,002 daha iyi") yerine yön ve çoğunluk. Toplam koşulu, tek bir büyük ayın baskın olmasını değil genel yönü ister; ay koşulu tek bir ayın (ör. Ekim–Kasım 2025 aksaklıkları, doğrulanmadı) toplamı sürüklemesine karşıdır.
- *Kantilde P80 + P95:* P80 aramanın amaç fonksiyonu (plan §4.3), P95 OR'un kuyruğu (§8). İkisini birden istemek "değiştirme" yükünü artırır. P50 aylık kayıtlı değil; toplamı bilgi olarak yazılır.
- *Varsayılan = takvimli:* planın özellik listesi budur; değişiklik kanıt ister (iptal modelinde kural dışı karar zaten verildi, M2; burada ikinci bir esneme yapılmaz).

## (b) Plan sözleşmesi için aynı takvim kuralı

- **Koşular:** P = `plan` (takvimli), PD = `plan` + `--drop-date-features` (aşağıda c). Araç: `calendar_rule --with-calendar <P> --without-calendar <PD>`.
- **Plan kantilleri (K4, K5, OR kaynağı):** (a)'daki kantil kuralı aynen uygulanır; sonuç `arr_delay/plan` rolünün koşusunu belirler.
- **Plan ArrDel15:** (a)'daki ArrDel15 kuralı uygulanır ve raporlanır; ancak plan ArrDel15'in son testteki tek rolü plan → T2 hava katkısıdır (§6). Hava katkısı "tek fark hava" olsun diye bu rolde **T2 birincil ArrDel15 ile aynı takvim ayarına sahip** plan modeli kullanılır (`arr_del15/plan_matched`). Plan ArrDel15 kuralının sonucu bu yüzden yalnızca bilgi olarak kalır.
- **Plan iptal (K6):** takvimsiz, oylamasız (D2 kararıyla tutarlı: iptal modeli takvim özellikleri olmadan). Kaynak: PD'nin `cancelled-lgbm` modeli. Erken durdurma planın standart kuralıyla (Val-A, sabır 100); D2'deki 1000/1000 ayarı tanı amaçlıydı.

## (c) Koşular ve her hedef için birincil model

**Yeni koşular** (hepsi `--tuning-from-run run-20261119T182216Z`, `--interval-models --quantile-num-boost-round 5000`, C ile aynı tavan ve sabır; lojistik L eğitilmez – kabul ölçütlerinde rolü yok):

| Ad | Sözleşme | Takvim | `--models` | Neden |
|---|---|---|---|---|
| P | plan | var | `arr_del15 quantiles` | C1 (K4/OR plan modeli), §6 |
| PD | plan | yok | `arr_del15 cancelled quantiles` | (b) kuralı, K6 (plan iptal, takvimsiz) |
| D | T2 | yok | `arr_del15 quantiles` | (a) kuralı (D adımı) |

Plan koşuları parametreleri T2 koşusundan alır (karar M3 madde 1); bunun için `run_models`'a `--tuning-from-other-contract` bayrağı eklendi (kaynak sözleşme sonuçlara `tuning.from_run_contract` olarak yazılır). Her yeni koşudan sonra `run_calibration` (Platt + isotonic, statik Val-B kalibratörleri) çalıştırılır; kilit girdisi bu `calibrators.json` dosyalarını referans verir.

**Roller ve kaynakları** (kilit girdisi bu tabloyla doldurulur; `final_lock` kuralları kodla denetler):

| Rol | Hedef / sözleşme | Kaynak | Kullanım |
|---|---|---|---|
| `arr_del15/T2` | ArrDel15, T2 | (a) ArrDel15 kuralı: kalırsa C, çıkarsa D | **birincil**: K1, K2, K3; Holm 1–3 |
| `arr_del15/plan_matched` | ArrDel15, plan | `arr_del15/T2` ile aynı takvim ayarı: C seçildiyse P, D seçildiyse PD | §6 hava katkısı (ikincil) |
| `arr_delay/plan` | kantiller, plan | (b) kantil kuralı: kalırsa P, çıkarsa PD | **birincil**: K4, K5, OR; Holm 4–6 |
| `arr_delay/T2_matched` | kantiller, T2 | `arr_delay/plan` ile aynı takvim ayarı: P seçildiyse C, PD seçildiyse D | §6 (P80 pinball), ikincil kapsama |
| `cancelled/plan` | iptal, plan | PD (takvimsiz, sabit) | **birincil**: K6; Holm 7 |
| `cancelled/T2` | iptal, T2 | D2 `run-20261120T174502Z` | ikincil (operasyonel iptal modeli) |
| `cancelled/T2_calendar` | iptal, T2 | C'nin `cancelled-lgbm`'i (= D1 yapılandırması, en iyi tur 15; C'nin kalibratörleri var) | ikincil duyarlılık (e) |

- Koddaki zorunluluklar: eşleşen rollerin çıkarılan özellikleri birebir aynı; `cancelled/plan` ve `cancelled/T2` takvimsiz, `cancelled/T2_calendar` takvimli; bütün koşular aynı fit penceresi ve geçmiş istatistik ayarı (m, min_support, min_tail, n_blocks); oracle koşusu kilitlenemez. Son testte yedi rolün hepsi zorunlu.
- C'nin `cancelled-lgbm` ile D1 koşusunun (`run-20261120T173554Z`) modelinin aynı olduğu (aynı parametre, deterministik, ikisi de 15 ağaç) muhtemel ama **doğrulanmadı**; D1 rolünde C kullanılır çünkü C'nin kalibratör dosyası var.

## (d) Prova: ne ölçer, kabul mantığı, K3/K5 toleransları

**Ne:** `run_final_test --rehearsal`, son testin değerlendirme kodunu (aynı fonksiyonlar) eğitim penceresi içindeki K3 (2025-03..05) ve K4 (2025-06..08) pencerelerinde çalıştırır. Kilitli modeller 2025-08'e kadar eğitildiği için kullanılamaz; her kat için modeller **yeniden eğitilir**:

| Kat | Fit | Erken durdurma (Val-A rolü, 4 ay) | Kalibrasyon (Val-B rolü, katın hemen öncesindeki 2 ay) | Değerlendirme |
|---|---|---|---|---|
| K3 | 2023-09-01 .. 2024-08-31 | 2024-09-01 .. 2024-12-31 | 2025-01-01 .. 2025-02-28 | 2025-03-01 .. 2025-05-31 |
| K4 | 2023-09-01 .. 2024-11-30 | 2024-12-01 .. 2025-03-31 | 2025-04-01 .. 2025-05-31 | 2025-06-01 .. 2025-08-31 |

- Katın fit penceresinin son 2 ayı kalibratör / F1 eşiği / statik conformal için, ondan önceki 4 ay erken durdurma için ayrılır: modelin eğitildiği satırlarda fit edilen kalibratör örneklem içi olurdu. Kategori listeleri, geçmiş istatistikler (kendi satırları için out-of-fold) ve B1 her katın fit penceresinden yeniden öğrenilir (arama katlarıyla aynı altyapı). Parametreler, tur tavanları ve sabır kilitli koşulardan alınır.
- Kayan conformal pencereleri [m − 57, m − 2] ve 2 ay gecikmeli "kamu" pencereleri katın kalibrasyon / erken durdurma dönemine ve önceki değerlendirme aylarına düşer (son testteki Val-B / Val-A rolünün aynısı).
- **Sınırlılık (her çıktıda yazar):** parametreler bu kat pencerelerinde arandı (`run-20261119T182216Z`); provanın performans sayıları iyimserdir ve sonuç değildir. Prova kod yolunu, kış → yaz kapsama/kalibrasyon davranışını ölçer ve toleransları sabitler.

**Geçerli prova:** iki kat (K3 ve K4) + birleşik blok, tam fit pencereleri (tablodaki gibi), gün örneklemi yok, B = 1000, kilit girdisinin yedi rolünün hepsi. `--max-fit-months`, `--fit-day-fraction < 1`, tek kat ya da rol alt kümesi yalnızca duman testidir: çıktıda `smoke: true` yazar ve kilit girdisi onu kabul etmez (kod reddeder).

**Prova geçti mi (kod yolu; performans kapı değildir):** her blokta (K3, K4, birleşik) K1–K6'nın hepsi hesaplanabildi; Holm ailesinin yedi p-değeri var ve düzeltilmiş p ≥ ham p; her B1 karşılaştırmasının GA'sı sonlu ve alt ≤ üst; birincil kantil rolünde hiçbir ayda kayan conformal penceresi yetersiz değil (k ≤ n); kapsamalar [0, 1] içinde; B = 1000. `fe.rehearsal_checks` bunları hesaplar. **Prova geçmezse kilit yazılmaz**: hata düzeltilir, prova tekrarlanır (prova eğitim içinde olduğu için tekrarı serbesttir; kural değişmez).

**K3 / K5 toleranslarının kesinleşme kuralı (şimdi yazılır, sayı provadan sonra):**
- Kaynak: K3 + K4 birleşik bloğu (Mart–Ağustos, testle aynı takvim ayları, 184 gün; gün blok bootstrap B = 1000, tohum 42).
- Her nicelik için yarı genişlik h = max(tahmin − GA alt, GA üst − tahmin): K3 için Platt sonrası CITL ve kalibrasyon eğimi (`arr_del15/T2`), K5 için kayan conformal P80 ve P95 kapsaması (`arr_delay/plan`).
- Tolerans = **max(plan önerisi, h'nin 0,005'e yukarı yuvarlanmışı)**: |CITL| ≤ max(0,01; ↑h), eğim 1 ± max(0,10; ↑h), P80 0,80 ± max(0,02; ↑h), P95 0,95 ± max(0,01; ↑h). Segment kuralı (Origin × ay, n ≥ 500, hedefin ±5 puanı, segmentlerin ≥ %80'i) değişmez.
- Gerekçe: red-team M4'ün sorunu gün içi bağımlılık (etkin n ≈ gün sayısı); bootstrap yarı genişliği tam bu gürültüyü ölçer. Kural **yalnızca gürültüyü** kullanır, provanın kendi sapmasını (tahmin − hedef) kullanmaz; böylece tolerans "testi geçirecek" yöne ayarlanamaz ve plan önerisinden dar olamaz. 0,005 (yarım puan) raporlama çözünürlüğüdür.
- `run_final_test --rehearsal` öneriyi `tolerance_proposal` olarak yazar; kilit girdisinin `acceptance` alanı bu öneriye **birebir** eşit olmalıdır (kod reddeder); elle sayı girilmez.

## (e) Raporlama kuralları

- **Olasılık:** birincil = **Platt** (Val-B'de fit, `calibrators.json`; son testte Val-B üzerinde yeniden fit edilip eşitliği doğrulanır). İsotonic ve aylık kayan Platt ([m − 57, m − 2]) ikincil. B1 kendi kalibratörüyle aynı adımlardan geçer.
- **Sıralama metrikleri** (ROC-AUC, PR-AUC, tabakalı AUC) **ham skorla**. F1, Val-B'de ham skorla seçilen dondurulmuş eşikle (ikincil).
- **K-ölçütlerinin okunuşu:** K1 = `arr_del15/T2` ΔROC-AUC ve ΔPR-AUC > 0, ikisinde GA alt > 0 ve Holm sonrası anlamlı. K2 = BSS (Platt model / Platt B1) > 0 ve GA alt > 0. K3 = Platt sonrası |CITL| ve eğim (d'deki toleranslar). K4 = `arr_delay/plan` ham (satır başına sıralı) kantillerinde α = 0,50/0,80/0,95 için Δpinball < 0, GA üst < 0, Holm sonrası anlamlı. K5 = `arr_delay/plan`, **aylık kayan** conformal: genel P80/P95 kapsaması toleransta ve Origin × ay segment kuralı. K6 = `cancelled/plan` ΔPR-AUC > 0 ve GA alt > 0. K7 = §2.6 testlerinin kilit commit'inde geçtiği **beyanı** (betik pytest çalıştıramaz; beyan diye yazılır) + kilitli modellerde çözülmemiş 1. aşama sızıntı alarmı yok + en az bir permütasyon incelemesinde zaman yolculuğu testi geçti + hiçbir incelemede "leak" yok. Değerlendirilemeyen ölçüt "geçmedi" sayılır.
- **Bootstrap (plan §5.2):** birim takvim günü; eşleştirilmiş fark (aynı yeniden örneklemde iki model); B = 1000; tohum 42; yüzdelik GA (%2,5 / %97,5); iki yönlü p = 2·min(pay(Δ* ≤ 0), pay(Δ* ≥ 0)), en çok 1; p = 0 "p < 1/B" diye yazılır. Bütün karşılaştırmalar aynı 1000 yeniden örneklemi kullanır.
- **Holm (α = 0,05) birincil aile (plan §5.2):** (1) ArrDel15 ΔROC-AUC, (2) ArrDel15 ΔPR-AUC, (3) ArrDel15 BSS – hepsi `arr_del15/T2`; (4–6) Δpinball P50/P80/P95 – `arr_delay/plan`; (7) iptal ΔPR-AUC – `cancelled/plan`. Anlamsız çıkanlar dahil hepsi raporlanır; yorum GA'lı Δ ile başlar.
- **Conformal:** birincil aylık kayan ([m − 57, m − 2], `splits.conformal_calibration_window`); statik (tek Val-B ofseti) ve **kamu senaryosu** (m − 2 ayının penceresi; BTS yayın gecikmesi ~2 ay, varsayım; Mart ve Nisan 2026'da pencere Val-A'ya/Val-B'ye düşer) ikincil. k > n (ya da boş pencere) ofseti +∞ ve "yetersiz" diye yazılır, kırpılmaz. Model ve B1 aynı adımdan geçer. Aylık kapsama tablosu (ham / kayan / statik / kamu) ana tablolardandır.
- **§6 hava katkısı:** metrik(T2) − metrik(plan), eşleşen takvim ayarıyla, aynı uçuşlar, aynı yeniden örneklemler: ROC-AUC, PR-AUC (ham), Brier (Platt), P80 pinball (ham). İkincil; Holm dışı. Oracle modeli kilitlenmedi: "yakalanan pay" raporlanmaz.
- **D1:** ikincil, rol `cancelled/T2_calendar`; yalnızca iptal kuralından sapmanın (M2) duyarlılığı olarak, hiçbir seçimde kullanılmadan raporlanır.
- **D2'nin Val-B sayıları** (ör. iptal AUC) başlık metriği değildir; başlık yalnızca son test tablosudur. Val-B'nin kullanımları (F1 eşiği, kalibratör/ofset fit'i, permütasyon, takvim hipotezi) her özette yazılır.
- **Keşifsel (etiketli, Holm dışı):** Origin × gün tabakalı AUC (M5; "erken uyarı" iddiası yok), olay günleri (eğitimde günlük ArrDel15 oranının P95'ini aşan test günleri), segmentler (Origin / saat bloğu / ay; taşıyıcı boyutu yok), diğer rollerin B1 karşılaştırmaları.
- **Testte ayar yok.** Sonuç kötüyse olduğu gibi yazılır ("geçmedi"); teşhis yalnızca geliştirme verisiyle yapılır. Kilit kaydı yazıldıktan sonra koşu çökerse kilit silinmez; karar kullanıcıya taşınır.
- **OR notu (M8):** `schedule_excess_min` model girdisi; OR modelin bu özelliğe duyarlılığını nedensel kullanmaz, "1 dk tampon = 1 dk daha az rötar" varsayımı açıkça yazılır.

## Çalıştırma sırası (özet)

1. Testler (pytest, ruff, mypy).
2. P, PD, D koşuları (c) → her birine `run_calibration`.
3. `calendar_rule` (C ↔ D, P ↔ PD) → rollerin kaynakları tablodaki kurala göre seçilir.
4. Kilitli modellerde 1. aşama alarmı varsa `run_permutation` (K7).
5. Kilit girdisi taslağı (`final_lock`, `acceptance` boş) → `run_final_test --rehearsal`.
6. Prova geçtiyse: kilit girdisi (`--acceptance-from-rehearsal`, pytest beyanı, incelemeler) → commit (temiz ağaç) → `run_final_test --final` (bir kez).

## Açık noktalar

- K5'in birincil modeli plan kantilleri olarak okundu (OR'un tükettiği sınırlar, plan §5.4/§8); planın K5 satırı sözleşme yazmıyor. Kullanıcı onayı gerekir.
- K3/K5'te plan önerileri (0,01; [0,90; 1,10]; [0,78; 0,82]; [0,94; 0,96]; segment ±5 puan, %80) taban alındı; bu tabanların kendisi plan §5.3'te "öneri; kullanıcı onayı" diye işaretli.
- Kamu senaryosunun 2 aylık gecikmesi bir varsayımdır (doğrulanmadı).
