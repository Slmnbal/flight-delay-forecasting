# M3 – Modelleme ve değerlendirme planı (`rotar-kantil-tampon`)

- **Tarih:** 2026-11-17 · **Durum:** taslak, kullanıcı onayı bekliyor
- **Dayanak:** proje kapsam kararları (3 yıl × 30 havalimanı; sunum kuralları), `research/veri-kaynaklari.md` §6.3, `deliverables/src/data/ozellik_sozlesmesi.py`, `deliverables/src/data/zaman.py`, `deliverables/data/olcum-sonucu.json`, `deliverables/data/utc-kontrol-sonucu.json`, `deliverables/data/hedef-havalimanlari.txt`.
- **Uygulanan Skill'ler:** time-based-validation, data-leakage-prevention, baseline-modeling, time-series-forecasting, statistical-analysis, scikit-learn.
- **Önemli:** Bu belgede **hiçbir performans tahmini yok**. Kabul ölçütleri baseline'a ve kapsama hedefine göre tanımlıdır. "Kaba hesap" diye işaretli sayılar yalnızca boyut planlaması içindir (Temmuz 2025 ölçümünden çarpım), ölçüm değildir. "Varsayım" diye işaretli her şey doğrulanmadı.
- **Arayüz sözleşmesi (JSON Schema):** `experiments/arayuz-sozlesmesi.json`.

---

## 0. Bir bakışta

| Konu | Karar (öneri) |
|---|---|
| Veri dönemi | 2023-09-01 – 2026-08-31 (36 ay; COVID dönemi tamamen dışarıda) |
| Bölme | Eğitim 24 ay · Doğrulama-A (ayar) 4 ay · Doğrulama-B (kalibrasyon) 2 ay · Son test 6 ay |
| Bilgi zamanı T | **Kalkıştan 2 saat önce** (operasyonel model); ayrıca **"plan" modeli** (yalnızca tarife + geçmiş istatistik, hava yok) OR tamponu için |
| Hedefler | ArrDel15 (sınıflandırma), iptal (ayrı sınıflandırma), varış rötarı P50/P80/P95 (tamamlanan uçuşlar koşullu) |
| Baseline | B0 genel oran/kantil; **B1 rota × saat bloğu geçmiş oranı/kantili (hiyerarşik geri çekilmeli)** — kabul ölçütleri B1'e göre |
| Ana modeller | LightGBM binary (ArrDel15, iptal) + LightGBM quantile (α = 0,50/0,80/0,95); lojistik regresyon (sklearn Pipeline) ara baseline; XGBoost isteğe bağlı |
| Belirsizlik | Tek yönlü split-conformal (P80, P95 üst sınırları; aylık kayan kalibrasyon birincil) + MAPIE CQR iki yönlü %80 aralık |
| İstatistik | Gün blok bootstrap'lı eşleştirilmiş fark, %95 GA, birincil aile için Holm düzeltmesi |
| Son test | Tek sefer; kilit dosyasıyla zorlanır |

---

## 1. Tarih aralığı ve zamana göre bölme

### 1.1 Aralık
- BTS'de en son veri **Ağustos 2026** [araştırma raporu, D]. 3 yıl = **2023-09-01 – 2026-08-31**, 36 tam ay. Bölme anahtarı **FlightDate** (tarifeli kalkışın yerel tarihi).
- **COVID:** 2020–2021 (ve 2022 başı toparlanması) aralığın tamamen dışında; ayrı bir dışlama kuralı gerekmez.
- **Kontrol (DE):** Ağustos 2026 dosyası tam mı (gün sayısı ve satır sayısı önceki ayların düzeyinde mi)? Değilse **tüm tarihler bir ay geri kayar** (aynı uzunluklar korunur). Bu kontrol veri katmanı görevinin parçasıdır.

### 1.2 Bölmeler

| Küme | Tarih (FlightDate) | Süre | Kullanım |
|---|---|---|---|
| **Eğitim** | 2023-09-01 – 2025-08-31 | 24 ay (731 gün) | Model fit; geçmiş istatistikler ve hedef kodlama **yalnızca buradan** |
| **Doğrulama-A (ayar)** | 2025-09-01 – 2025-12-31 | 4 ay (122 gün) | Erken durdurma, model/özellik seçimi, B1 geri çekilme eşiklerinin seçimi |
| **Doğrulama-B (kalibrasyon)** | 2026-01-01 – 2026-02-28 | 2 ay (59 gün) | Olasılık kalibrasyonu (gerekirse isotonic), F1 eşiği seçimi, conformal kalibrasyonun ilk penceresi |
| **Son test** | 2026-03-01 – 2026-08-31 | 6 ay (184 gün) | Tek seferlik nihai değerlendirme |

**Gerekçe:**
- Eğitim iki tam mevsim döngüsü içerir (iki yaz, iki kış); bu, takvim etkilerinin öğrenilmesi ve rota × saat istatistiklerinin kararlılığı için gereken en az uzunluk.
- Son test, yılın en yoğun ve rötar açısından en zorlu dönemini (ilkbahar–yaz; yaz konvektif hava dönemi) kapsar. Kış dönemi ise A ve B'de görülür; böylece rapor iki mevsimden de sonuç verir.
- Kalibrasyon (B) testten hemen önce gelir: conformal yöntemin değiş-tokuş edilebilirlik (exchangeability) varsayımına en yakın seçenek bu. Yine de **B kış, test yaz**: mevsim kayması kapsamayı bozabilir. Bu yüzden birincil yöntem **aylık kayan kalibrasyondur** (§5.4); statik B kalibrasyonu karşılaştırma olarak raporlanır. İki seçenek de şimdi, sonuçlar görülmeden belirlendi.
- Nihai model **yalnızca eğitimle** fit edilir; A+eğitim ile yeniden fit **yapılmaz** (A'da seçilen eşik ve erken durdurma bozulmasın diye). Bunun bedeli test sonuna kadar 6–12 aylık bayatlıktır; aylık performans eğilimi raporlanır (kayma görünür olsun).

### 1.3 Rolling-origin backtest (eğitim içinde; ayar ve sağlamlık)
Genişleyen pencere, 4 kat, her değerlendirme penceresi 3 ay (dört mevsimi kapsar):

| Kat | Fit | Değerlendirme | Durum |
|---|---|---|---|
| K1 | 2023-09-01 – 2024-08-31 | 2024-09-01 – 2024-11-30 | kesilebilir |
| K2 | 2023-09-01 – 2024-11-30 | 2024-12-01 – 2025-02-28 | kesilebilir |
| K3 | 2023-09-01 – 2025-02-28 | 2025-03-01 – 2025-05-31 | çekirdek |
| K4 | 2023-09-01 – 2025-05-31 | 2025-06-01 – 2025-08-31 | çekirdek |

- Her katta geçmiş istatistikler ve hedef kodlama **o katın fit penceresinden yeniden** hesaplanır.
- Baseline'lar ve nihai yapılandırma bütün katlarda aynı kodla ölçülür; sonuç tablosu kat × segment kırılımlıdır.

### 1.4 Embargo ve sınır kuralları
- A'nın ilk saatlerinde, eğitimin son gününden henüz inmemiş birkaç uçuşun etiketi istatistiklere girmiş olabilir (en fazla birkaç saat). Etkisi A'nın ilk gününde ihmal edilebilir; test eğitimden 6 ay sonra başladığı için testte etkisi yoktur. Not olarak bırakılır.
- **Kayan conformal penceresinde** 1 günlük embargo uygulanır: ay *m* için kalibrasyon penceresi FlightDate ∈ [m − 57 gün, m − 2 gün] (yaklaşık 8 hafta). Böylece pencere içindeki her uçuşun etiketi, ayın ilk uçuşunun tahmin anından önce kesin bilinir.

### 1.5 Son teste bir kez bakma kuralı
1. Test değerlendirmesi ayrı bir betik (`deliverables/src/modeling/son_test.py`, sonra yazılacak) ile yapılır. Betik, `experiments/son-test-kilidi.json` varsa **çalışmayı reddeder**; ilk çalıştırmada bu dosyayı yazar (tarih, git commit, MLflow run kimlikleri, sözleşme özeti).
2. Kilit dosyası yazılmadan önce dondurulanlar: özellik listesi, hiperparametreler, eşikler, kalibrasyon yöntemi, kabul ölçütleri (bu belge, §5).
3. Test sonucu kötü çıkarsa model test üzerinde yeniden ayarlanmaz; teşhis A/B ve rolling-origin katlarıyla yapılır, test sonucu olduğu gibi raporlanır.
4. Geliştirme sırasında hiçbir kod test tarihlerini okumaz: bölme sabitleri tek modülde (`bolme.py`) tutulur; geliştirme yükleyicisi FlightDate > 2026-02-28 satırlarını filtreler ve testle doğrulanır.

---

## 2. Bilgi zamanı T ve özellikler

### 2.1 T önerisi: kalkıştan 2 saat önce (`ufuk_saat = 2`)
- **Gerekçe:** (a) Operasyonel karar anı: yolcu bilgilendirme, kapı/ekip yedeği ve aktarma koruması kararları kalkıştan birkaç saat önce verilir. (b) METAR saatlik (ve SPECI ile daha sık); 2 saat, yakın ama gerçekten bilinebilir hava bilgisi verir. (c) Araştırma raporu §6.3'teki örnekle ve Portföy Danışmanı planıyla tutarlı. (d) Arşivlenmiş hava *tahmini* (TAF/NWP) kaynağımız yok; daha uzun T'de gözlemin değeri muhtemelen azalır (varsayım; ölçülecek).
- **İkinci bilgi düzeyi – "plan" modeli:** Blok süre tamponu bir **tarife planlama** kararıdır ve aylar önce verilir; o anda günün havası bilinmez. Bu yüzden OR'a giden kantiller **yalnızca tarife + takvim + geçmiş istatistik** kullanan modelden gelir (hava yok). Bu, hava deneyinin de ilk basamağıdır (§6).
- **Duyarlılık (kesilebilir):** T ∈ {6, 12} saat ile operasyonel modelin tekrarı; hava katkısının ufukla nasıl azaldığını gösterir.

### 2.2 Bilgi zamanı sınıfları (ozellik_sozlesmesi.py ile uyum)
Üç sözleşme örneği tanımlanır ve her deneyde `OzellikSozlesmesi` ile doğrulanır; eğitimden hemen önce `dogrula_sutunlar(X.columns)` çağrılır:

| Sözleşme | `ufuk_saat` | `oracle_deneyi` | İzinli sınıflar |
|---|---|---|---|
| `plan` | 2 (hava özelliği olmadığı için ufuk yalnızca biçimsel) | False | `tarife`, `gecmis_gerceklesen` |
| `T2` (operasyonel) | 2 | False | `tarife`, `gecmis_gerceklesen`, `gozlem_T_oncesi` |
| `oracle` | 2 | **True** | yukarıdakiler + `oracle` |

- Geçmiş istatistikler yasak ham sütunlardan (ArrDelay, ArrDel15, Cancelled, ActualElapsedTime, TaxiOut) türetilir. Sözleşme bunlara yalnızca `kaynak='turetilmis'`, `bilgi_zamani='gecmis_gerceklesen'` ve `bilgi_hazir_dk_once >= 120` ile izin verir. Değerlendirme kümelerinde bilgi, eğitim sonundan itibaren hazırdır; beyan edilecek `bilgi_hazir_dk_once`, eğitim sonu ile ilgili kümenin ilk kalkışı arasındaki en küçük farktır (en az 1 gün = 1440 dk).
- **Sözleşmenin sınırı (dosyanın kendi notu):** Sözleşme beyanı doğrular, hesabı doğrulamaz. Bu yüzden §2.6'daki **satır düzeyi zaman testleri** zorunludur.

### 2.3 Özellik listesi

**A. Tarife (`bilgi_zamani='tarife'`, `kaynak='bts_ontime'` ya da tarifeden `turetilmis`)**

| Özellik | Türetim | Not |
|---|---|---|
| `crs_kalkis_saat`, `crs_kalkis_dk` | CRSDepTime (yerel; 2400 → 1440) | `zaman.hhmm_ayristir` |
| `crs_varis_saat` | CRSArrTime (yerel) | |
| `saat_blogu` | CRS kalkış yerel saatinden 7 blok: [00–06), [06–09), [09–12), [12–15), [15–18), [18–21), [21–24) | **DepTimeBlk kullanılmaz** (sözleşmede tedbiren yasak); kendimiz türetiyoruz. Blok sınırları öneri. |
| `CRSElapsedTime`, `Distance`, `DistanceGroup` | ham | |
| `Origin`, `Reporting_Airline` | kategorik (LightGBM yerel kategorik; 30 ve ~15 düzey) | Taşıyıcı özellik olabilir; **sunumda taşıyıcı sonucu yok** (§7) |
| `Dest`, `rota` | doğrudan kategorik değil; hedef kodlamalı istatistiklerle (§2.4) | yüksek kardinalite |
| Takvim: `ay`, `haftanin_gunu`, `ayin_gunu`, `yilin_gunu` | FlightDate | **`Year` kullanılmaz**: test yılı eğitimde yok, ağaçlar dışa değerleme yapamaz |
| `tatil_uzakligi_gun`, `tatil_haftasi` | ABD federal tatil listesi (önceden yayımlanır) | kaynak: OPM listesi; yeni bağımlılık yerine sabit tablo önerilir |
| `planli_kalkis_origin_saat`, `planli_varis_dest_saat` | Aynı yerel tarih ve saatte **tarifeli** kalkış/varış sayısı; iptaller dahil, tüm BTS uçuşlarından | Tarife önceden bilinir. Yalnızca rapor veren taşıyıcıları sayar (tutarlı ama eksik). Varış sayısı 30 dışı kalkışlardan da gelen uçuşları içermeli (DE, §10) |
| `planli_kalkis_origin_gun` | Günlük tarifeli kalkış | |

**B. Geçmiş istatistikler (`bilgi_zamani='gecmis_gerceklesen'`, `kaynak='turetilmis'`; YALNIZCA fit penceresinden)**

| Özellik | Kaynak sütun | Geri çekilme |
|---|---|---|
| `te_rota_saat_arrdel15` | ArrDel15 | rota×saat_blogu → origin×saat_blogu → origin → genel |
| `te_dest_saat_arrdel15` | ArrDel15 | dest×saat_blogu → dest → genel |
| `te_tasiyici_origin_arrdel15` | ArrDel15 | taşıyıcı×origin → origin |
| `gecmis_rota_saat_p50/p80/p95` | ArrDelay (tamamlanan uçuşlar) | B1 ile aynı kural (§4.1) |
| `te_rota_iptal` | Cancelled | rota → origin → genel |
| `tarife_fazlasi_dk` | CRSElapsedTime − (rota × saat_blogu medyan ActualElapsedTime) | Tarifedeki "tampon"un geçmişe göre ölçüsü; tampon hikâyesinin anahtar özelliği |
| `gecmis_taxiout_origin_saat_medyan` | TaxiOut | origin×saat_blogu → origin |
| `destek_n_*` | — | Her istatistiğin dayandığı gözlem sayısı (güvenilirlik sinyali) |

**C. Hava – T öncesi (`bilgi_zamani='gozlem_T_oncesi'`, `kaynak='iem_asos'`)** — kesim anı = CRS kalkış UTC − T − 10 dk (§10.2)

- Origin ve (varsa) dest için: `tmpf`, `dwpf`, `sknt`, `gust`, `vsby`, `tavan_ft` (BKN/OVC en alçak katman), `ifr_bayrak` (tavan < 1000 ft ya da görüş < 3 mil; tanım önerisi), yağış/olay bayrakları `wx_ts`, `wx_sn`, `wx_fzra`, `wx_ra`, `wx_fg` (wxcodes'tan), `p01i`, `gozlem_yasi_dk`.
- **Dest havası da kalkış − T kesimiyle alınır, varış − T ile değil.** Tahmin anı kalkıştan T önce olduğu için tüm bilgi aynı anla sınırlıdır.
- Kesilebilir: son 3 saatlik değişimler (`alti`, `vsby`, `sknt` farkı), kesim anından geriye doğru hesaplanır.

**D. Oracle hava (`bilgi_zamani='oracle'`)** — yalnızca `oracle` sözleşmesinde: origin gözlemi ≤ CRS kalkış UTC, dest gözlemi ≤ CRS varış UTC. Gerçekleşen saatler (DepTime/ArrTime) **kullanılmaz**; oracle bile tarifeli anlara göre tanımlanır.

**Modele alınmayanlar ve nedenleri:**
- `Flight_Number_Reporting_Airline`: kimlik niteliğinde, aşırı öğrenmeye açık.
- `Tail_Number` ve rotasyon özellikleri ("günün kaçıncı bacağı", "önceki bacak rötarı"): BTS'deki kuyruk numarası **gerçekleşen** uçağı gösterir; aksaklıkta uçak değişimi olur. T anında atanmış uçağın bu olduğu doğrulanamaz, yani sızıntı riski var. Çekirdekte yok; ayrı bir deney olarak kesilebilir (ve yalnızca önceki bacağın varışı ≤ kalkış − T ise).
- `DepTimeBlk`/`ArrTimeBlk`: sözleşmede yasak; `saat_blogu` kendimiz türetiyoruz.
- `Year`, `Quarter`: zaman eğilimini dışa değerlemeye zorlar (`Quarter` ay ile zaten kodlanır).

### 2.4 Hedef kodlamanın sızıntısız yapılışı
1. **Değerlendirme kümeleri (A, B, test, kat değerlendirmeleri):** istatistikler **yalnızca fit penceresinin tamamından** hesaplanır ve sabit tablo olarak eşlenir. Görülmemiş düzey → üst düzeye geri çekilme.
2. **Fit penceresindeki satırlar:** satırın kendi etiketi kendi özelliğine giremez. **Çapraz uydurma (out-of-fold)** kullanılır: fit penceresi FlightDate'e göre sıralanır, 5 **ardışık zaman bloğuna** bölünür (karıştırma yok); her bloğun kodlaması diğer bloklardan hesaplanır. sklearn `TargetEncoder(cv=5, shuffle=False)` sıralı veride bu davranışı verir (sürüm belgesiyle doğrulanacak). Kantil istatistikleri ve geri çekilmeli oranlar için aynı mantık kendi fonksiyonumuzla uygulanır.
   - Bilinen ödünleşim: eğitim içinde bir satırın kodlaması gelecekteki bloklardan da beslenir. Bu, **değerlendirmenin dürüstlüğünü bozmaz** (değerlendirme kümeleri hiç kullanılmaz), yalnızca eğitim temsilini etkiler. Sağlamlık kontrolü (kesilebilir): yalnızca geçmişe dayalı genişleyen kodlama ile K3/K4'te karşılaştırma.
3. **Yumuşatma:** m-tahmini, ebeveyn düzeyine doğru: `(n·ȳ + m·ȳ_ebeveyn)/(n + m)`. `m` ve en küçük destek A'da seçilir (başlangıç değeri varsayım: m = 20).
4. **Pipeline:** lojistik baseline'da tüm ön işleme (`ColumnTransformer` + `TargetEncoder` + `OneHotEncoder(handle_unknown='ignore')` + `StandardScaler`) sklearn `Pipeline` içinde olur ve yalnızca fit penceresinde öğrenilir. LightGBM'de istatistik tabloları `fit(egitim)` / `transform(herhangi)` arayüzlü tek bir sınıfta tutulur; `transform` hiçbir zaman etiket okumaz (testle doğrulanır).

### 2.5 Eksik veri
- Hava: kesimden önceki 3 saat içinde gözlem yoksa özellik NaN kalır (LightGBM NaN'ı kendi işler) ve `hava_eksik` bayrağı eklenir. Eksiklik oranı havalimanı × ay kırılımında raporlanır. Doldurma yapılmaz.
- Dest 30 dışındaysa dest havası NaN ve `dest_hava_var = 0` (Kullanıcıya soru 2).
- Lojistik baseline'da `SimpleImputer(median)` + eksiklik göstergesi, Pipeline içinde.

### 2.6 Sızıntı kontrol listesi (özellik bazında; testlere dönüşecek)

| Kontrol | Test (planlanan, `deliverables/tests/modeling/`) |
|---|---|
| Yasak ad/önek yok | `dogrula_sutunlar` her eğitimden önce; `test_ozellik_matrisi_yasak_yok` |
| Her özellik sözleşmeye beyanlı | `test_sozlesme_tum_sutunlari_kapsar` (X sütunları == sözleşme adları) |
| T öncesi hava: her satırda `gozlem_utc <= crs_kalkis_utc − T − 10 dk` | `test_hava_bilgi_zamani_satir_duzeyi` |
| Oracle özellik yalnızca oracle deneyinde | `test_oracle_yalnizca_bayrakla` |
| İstatistik tabloları yalnızca fit penceresinden: `max(FlightDate) <= fit_sonu` | `test_istatistik_donemi` |
| `transform` etiket okumaz | `test_transform_etiketsiz` (etiket sütunu silinmiş veriyle çalışmalı) |
| Bölmeler örtüşmez ve sıralı | `test_bolme_ortusmez` |
| Geliştirme yükleyicisi test tarihlerini döndürmez | `test_gelistirme_test_gormez` |
| `ArrDel15 == (ArrDelay >= 15)` tutarlılığı (BTS tanımı doğrulanmadı) | `test_hedef_tutarliligi` |
| Şüpheli skor: tek özelliğin permütasyon öneminin toplamın > %50'si ya da plan→T kazancının oracle'a çok yakın çıkması | Otomatik uyarı; sonuç raporlanmadan önce inceleme (data-leakage-prevention: **şüphe netleşmeden sonuç raporlanmaz**) |

---

## 3. Hedefler

### 3.1 ArrDel15 (birincil sınıflandırma)
- **Evren:** tamamlanan uçuşlar (Cancelled = 0 ve Diverted = 0). Temmuz 2025'te ArrDel15 eksikliği %2,95 [ölçüm, olcum-sonucu.json]; bu, iptal + sapma payına karşılık geliyor gibi görünüyor (doğrulanacak).
- **Modeller:** plan ve T2 (birincil: T2), oracle yalnızca deneyde.

### 3.2 İptal (ayrı sınıflandırma)
- **Evren:** tüm tarifeli uçuşlar (iptaller CRS saatlerini taşır; `zaman.py` iptalleri silmez).
- Çok dengesiz bir hedef; birincil metrik PR-AUC ve yaygınlıkla birlikte verilir.
- **Seçim yanlılığı ve tanım notları:**
  1. Rötar modelleri ve kantiller **"uçuş tamamlandı" koşullu**dur. İptaller en kötü aksaklık günlerinde (fırtına, sistem kesintisi) yoğunlaşır. Bu yüzden koşullu rötar dağılımı, kötü günlerin kuyruğunu eksik temsil eder. Bu **açıkça** raporlanır.
  2. BTS iptalin **ne zaman** yapıldığını vermez. Fırtına öncesi bir gün önceden yapılan iptaller T anında zaten biliniyor olabilir. Yani "T anında henüz iptal edilmemiş uçuşta iptal riski" doğrulanamaz. İptal modeli "tarife ve geçmişe dayalı iptal riski" diye adlandırılır, operasyonel erken uyarı iddiası taşımaz.
  3. Kesilebilir ek hedef **`aksaklik`** = ArrDel15 ∨ Cancelled ∨ Diverted (tüm tarifeli uçuşlarda). Seçim yanlılığından etkilenmez ve duyarlılık kontrolü olarak raporlanır.

### 3.3 Varış rötarı kantilleri P50/P80/P95
- **Hedef:** ArrDelay (dakika; erken varışlar negatif), tamamlanan uçuşlarda. Kırpma yok; aşırı değerler pinball kaybında doğal olarak ele alınır.
- **İptal/sapma:** kantil modelinin dışında. OR ve arayüz için **koşulsuz** risk şöyle birleştirilir (p_k = iptal ∨ sapma olasılığı, F = tamamlanan uçuş koşullu dağılım):
  - P(rötar > q) = p_k + (1 − p_k)·(1 − F(q)), yani iptal/sapma "sonsuz rötar" sayılır.
  - Koşulsuz α-kantili = F⁻¹(α / (1 − p_k)) (α < 1 − p_k için). Bu, OR'un neden yoğun bir kantil ızgarasına ihtiyaç duyduğunu da açıklar (§8).
- Sapan uçuşlar (Diverted) için BTS'deki Div* varış rötarı **etiket** olarak kullanılabilirdi, ama çekirdekte yok (pay küçük; sapma ayrıca raporlanır).
- **Kantil kesişmesi:** üç ayrı LightGBM modeli birbirini kesebilir. Kesişme oranı raporlanır; sonra satır başına sıralanarak (`np.sort`) monotonluk sağlanır.

---

## 4. Baseline'lar ve ana modeller

### 4.1 Baseline'lar (hepsi aynı bölme, aynı metrik kodu)

| Ad | Sınıflandırma (ArrDel15, iptal) | Kantil | Durum |
|---|---|---|---|
| **B0** | Eğitim genel oranı (sabit olasılık; AUC = 0,5 referansı) | Eğitim genel P50/P80/P95 | çekirdek |
| **B1** | rota × saat_blogu geçmiş oranı, m-tahminiyle ebeveyne yumuşatılmış; geri çekilme rota×saat → origin×saat → origin → genel | rota × saat_blogu ampirik kantilleri; geri çekilme kuralı **n·(1 − α) ≥ 20** (kuyrukta en az 20 gözlem: P50 için n ≥ 40, P80 için n ≥ 100, P95 için n ≥ 400) | **çekirdek; kabul ölçütlerinin referansı** |
| B2 | B1 + mevsim (aralık–şubat / mart–mayıs / haziran–ağustos / eylül–kasım) | aynı | kesilebilir |
| **L** | Lojistik regresyon, sklearn Pipeline (one-hot Origin/taşıyıcı/saat_blogu/ay/gün, ölçeklenmiş sayısal + hedef kodlama); büyük veri için `SGDClassifier(loss='log_loss')` ya da gün örneklemli `LogisticRegression` | — (kantil için doğrusal model çekirdekte yok) | çekirdek (ucuz; sklearn becerisi) |

B1 "tarifeyi bilen bir planlamacının geçmişe bakarak yapacağı tahmin"dir. Model bunu geçemiyorsa karmaşıklığı haklı değildir ve bu açıkça raporlanır (baseline-modeling).

### 4.2 Ana modeller

| Model | Hedef | Sözleşme | Durum |
|---|---|---|---|
| LightGBM `binary` | ArrDel15 | plan, T2, oracle | çekirdek |
| LightGBM `binary` | iptal | plan, T2 | çekirdek (T2 varyantı kesilebilir) |
| LightGBM `quantile`, α = 0,50 / 0,80 / 0,95 | ArrDelay | **plan** (OR), T2, oracle (yalnızca α = 0,80) | çekirdek |
| LightGBM `quantile`, α = 0,10 / 0,90 | ArrDelay (MAPIE CQR %80 aralığı için) | plan | çekirdek |
| LightGBM `quantile`, α = 0,60 / 0,70 / 0,85 / 0,90 + 0,025 / 0,975 | OR ızgarası ve %95 iki yönlü aralık | plan | kesilebilir |
| XGBoost `binary:logistic` (`tree_method='hist'`) | ArrDel15 | T2 | isteğe bağlı/kesilebilir |
| `aksaklik` LightGBM | bileşik | T2 | kesilebilir |

- Sınıf ağırlığı **yok** (`is_unbalance` kapalı): olasılıklar kalibre kalsın. Dengesizlik metrik seçimi ve eşikle yönetilir.
- Olasılık kalibrasyonu: A'daki güvenilirlik grafiği sapma gösterirse **isotonic** kalibratör B'de fit edilir. Kalibratör hem model hem B1 için aynı kuralla uygulanır ya da hiçbirine uygulanmaz.
- `random_state`/`seed` = 42 her yerde; LightGBM'de `deterministic=True` ve sabit `num_threads`.
- Bellek: float32 özellikler, kategorikler `category` tipi. Kaba hesap: eğitimde yaklaşık 9,7 milyon satır (aylık yaklaşık 404 bin × 24; Temmuz 2025'ten çarpım, ölçüm değil).

### 4.3 Hiperparametre ayarı
- **Yöntem:** sklearn `ParameterSampler` ile rastgele arama (yeni bağımlılık gerekmez; Optuna mimari karar ister). Başlangıç bütçesi 30 yapılandırma (öneri). Arama, K3 ve K4 katlarında yapılır; hız için fit pencerelerinden **bütün günler** halinde %25 örneklem alınır (satır örneklemi değil; gün içi bağımlılık korunur).
- **Uzay (öneri):** `num_leaves` {31, 63, 127, 255}, `learning_rate` {0,03; 0,05; 0,1}, `min_child_samples` {50, 200, 500, 1000}, `feature_fraction` [0,6–1,0], `bagging_fraction` [0,6–1,0] (`bagging_freq` = 1), `lambda_l2` {0, 1, 10}, `max_bin` {63, 255}, `cat_smooth` {10, 50}.
- **Amaç:** sınıflandırmada katların ortalama log-loss'u; kantilde α = 0,80 pinball kaybı (seçilen yapılandırma diğer α'lara da uygulanır, tek tek ayar yapılmaz: bütçe).
- **Nihai fit:** seçilen yapılandırma tüm eğitimde fit edilir; ağaç sayısı A üzerinde erken durdurmayla belirlenir (sabır 100 tur). A'nın hem erken durdurmada hem seçimde kullanılması hafif iyimserlik getirir; test ayrı olduğu için kabul edilebilir.
- Aynı arama bütçesi ve aynı katlar XGBoost için de kullanılır (kıyas adil olsun).

---

## 5. Metrikler ve kabul ölçütleri

### 5.1 Metrikler

| Görev | Metrikler |
|---|---|
| ArrDel15, iptal | ROC-AUC, PR-AUC (ortalama hassasiyet) + **yaygınlık**, Brier ve Brier skill score (BSS, B1'e göre), log-loss, kalibrasyon (güvenilirlik grafiği 10 eşit frekanslı kutu, ECE, lojistik yeniden kalibrasyon eğimi ve kesişimi, "calibration-in-the-large" = ortalama tahmin − gözlenen oran), eşikte precision/recall/F1 |
| Kantil | α başına ortalama pinball kaybı; P50 için MAE; **ham** kapsama P(y ≤ q̂_α); conformal ayarlı kapsama; iki yönlü %80 aralık kapsaması ve ortalama genişliği (dk) |

**F1 eşiği:** her model (B1 dahil) için B'de F1'i en çok yapan eşik seçilir ve dondurulur; testte o eşik kullanılır. F1 eşiğe bağlı olduğu için **ikincil** metriktir; birincil sınıflandırma karşılaştırması eşikten bağımsız metriklerle yapılır. Arayüzde eşik ve yaygınlık birlikte gösterilir.

### 5.2 İstatistiksel karşılaştırma (statistical-analysis)
- **Soru (veriden önce):** Model, aynı test uçuşlarında B1'den daha iyi mi? Tahmin edilen nicelik: metrik farkı Δ = metrik(model) − metrik(B1). Etki büyüklüğü, metrik biriminde Δ'nın kendisidir.
- **Örnekleme birimi ve bağımlılık:** aynı gündeki uçuşlar ortak hava ve ağ etkileriyle bağımlıdır. Bu yüzden **takvim günü blok bootstrap** kullanılır: test günleri (184) yerine konarak örneklenir, seçilen günün bütün uçuşları alınır; iki model **aynı yeniden örneklemde** ölçülür (eşleştirilmiş). B = 1000 (başlangıç; AUC hesap süresi ölçülüp gerekirse ayarlanır, ama ayar sonuçlara bakılmadan yapılır), yüzdelik GA, tohum 42.
- **Birincil karşılaştırma ailesi (Holm düzeltmesi, α = 0,05):** (1) ArrDel15 ΔROC-AUC, (2) ArrDel15 ΔPR-AUC, (3) ArrDel15 BSS, (4–6) Δpinball P50/P80/P95 (plan modeli), (7) iptal ΔPR-AUC. Bootstrap p-değeri iki yönlü = 2 · min(pay(Δ* ≤ 0), pay(Δ* ≥ 0)).
- Planlanan tüm karşılaştırmalar, anlamsız çıkanlar dahil raporlanır. İkincil metrikler (F1, ECE, segmentler) keşifsel diye etiketlenir.
- Büyük n'de çok küçük farklar bile "anlamlı" çıkabilir. Bu yüzden yorum GA'lı Δ ile başlar, p-değeriyle değil.

### 5.3 Kabul ölçütleri (son test; dondurulmuş)

| # | Ölçüt | Geçme koşulu |
|---|---|---|
| **K1** | ArrDel15 ayrıştırma (T2 vs B1) | ΔROC-AUC > 0 **ve** ΔPR-AUC > 0; ikisinde de %95 GA alt sınırı > 0 ve Holm sonrası anlamlı |
| **K2** | ArrDel15 olasılık kalitesi | BSS (B1'e göre) > 0; GA alt sınırı > 0 |
| **K3** | ArrDel15 kalibrasyon | \|calibration-in-the-large\| ≤ 0,01 ve kalibrasyon eğimi [0,90; 1,10] içinde *(eşikler öneri; kullanıcı onayı)* |
| **K4** | Kantil doğruluğu (plan modeli vs B1) | α = 0,50 / 0,80 / 0,95 için Δpinball < 0; her birinde GA üst sınırı < 0 ve Holm sonrası anlamlı |
| **K5** | Conformal kapsama (birincil: aylık kayan) | Test geneli kapsama: P80 için [0,78; 0,82], P95 için [0,94; 0,96]; ayrıca havalimanı × ay segmentlerinin (n ≥ 500) en az %80'i hedefin ±5 puan içinde *(tolerans öneri; kullanıcı onayı)* |
| **K6** | İptal ayrıştırma (plan vs B1) | ΔPR-AUC > 0, GA alt sınırı > 0 |
| **K7** | Sızıntı | §2.6'daki tüm testler geçti; şüpheli skor incelemesi temiz |
| (ikincil) | F1, iki yönlü %80 aralık kapsaması [0,78; 0,82] ve genişliği, T2'nin plana kazancı (§6) | Raporlanır; kabul koşulu değil |

- **K5 toleransının gerekçesi:** test n'i milyonlar düzeyinde olduğu için örnekleme hatası küçüktür; tolerans esas olarak dağılım kaymasına (mevsim, olağandışı günler) izin verir. P95'te tolerans dar tutuldu, çünkü %5 yerine %7 ıskalama, tampon kararında %40 daha fazla ıskalama demektir.
- Kayan ve statik kalibrasyonun ikisi de raporlanır; kabul **önceden seçilen birincil yönteme** (kayan) bakılarak verilir.
- **Bir ölçüt kalırsa:** sonuç "geçmedi" diye yazılır, model süslenmez. Örneğin K6 kalırsa bu "iptal riski tarifeden öngörülemiyor" bulgusudur. Testte ek ayar yapılmaz.

### 5.4 Conformal yöntemi
- **Tek yönlü üst sınır (OR'un ihtiyacı):** α ∈ {0,80; 0,95} için uygunsuzluk skoru s = y − q̂_α(x). Kalibrasyon kümesinde ⌈(n+1)α⌉/n ampirik kantili ĉ_α; ayarlı üst sınır q̂_α(x) + ĉ_α. Kendi fonksiyonumuz; sentetik veriyle kapsama testi yapılır (`test_conformal_tek_yonlu_kapsama`).
- **İki yönlü %80 aralık (MAPIE):** α = 0,10/0,90 LightGBM modelleriyle conformalized quantile regression (CQR), önceden fit edilmiş tahminci (prefit) + kalibrasyon kümesi. MAPIE sürümü sabitlenir; API (v1'de `ConformalizedQuantileRegressor`, eski sürümlerde `MapieQuantileRegressor`) kurulu sürümün belgesiyle doğrulanacak (**doğrulanmadı**). %95 iki yönlü aralık kesilebilir.
- **Kalibrasyon penceresi:** birincil = **aylık kayan** (§1.4; ay başında güncellenir; Mart 2026 penceresi yaklaşık B'nin kendisi). Karşılaştırma = **statik** (yalnızca B). Gerçek zamanlı kayan pencere etikete erişim ister: operatör için geçerli, ama yayımlanan BTS verisini kullanan biri için yaklaşık 2 aylık yayın gecikmesi var (varsayım). Bu fark raporda yazılır.
- Hem model hem B1 kantilleri aynı conformal adımdan geçirilir. K4'te birincil karşılaştırma **ham** kantiller üzerinden; ayarlı pinball ikincil.
- Aylık kapsama grafiği (kayan / statik / ham) raporun ana grafiklerinden biridir.

---

## 6. Hava deneyi: T öncesi METAR ve oracle

- **Basamaklar** (aynı hiperparametreler, aynı bölmeler, aynı test uçuşları):
  1. `plan`: hava yok,
  2. `T2`: kalkış − 2 saat − 10 dk kesimli METAR,
  3. `oracle`: tarifeli kalkış/varış anındaki gözlenmiş hava.
- **Raporlanan nicelikler:** hava katkısı = metrik(T2) − metrik(plan), GA'lı (eşleştirilmiş gün bootstrap); üst sınır açığı = metrik(oracle) − metrik(T2); yakalanan pay = (T2 − plan) / (oracle − plan). Metrikler ROC-AUC, PR-AUC, Brier (ArrDel15) ve P80 pinball. Payın paydası küçükse pay raporlanmaz, yalnızca farklar verilir.
- **Ayrı raporlama kuralları:**
  - Oracle **hiçbir zaman** başlık sonucu, kabul ölçütü ya da arayüzün ana metriği değildir. Yalnızca `hava-deneyi.json` dosyasında `oracle: true` ve "üst sınır – gerçekte tahmin anında elde edilemez" etiketiyle görünür.
  - MLflow'da oracle koşuları `oracle=true` etiketi ve ayrı deney adıyla tutulur. Sözleşme `oracle_deneyi=True` olmadan oracle özelliğini reddeder (sözleşme bunu zaten yapıyor).
  - Hava etkisi IFR/VFR ve olay (TS, SN) segmentlerinde de verilir; havanın etkisi muhtemelen kötü hava günlerinde yoğunlaşır (varsayım; ölçülecek).
- **Sızıntı akıl sağlığı kontrolü:** T2 sonucu oracle'a şüpheli derecede yakınsa ya da plan → T2 kazancı beklenmedik derecede büyükse, bilgi zamanı testi yeniden incelenir ve sonuç o zamana kadar raporlanmaz.

---

## 7. Hata analizi planı

- **Boyutlar:** origin havalimanı (30), dest havalimanı (30 içindekiler), saat_blogu (7), ay, haftanın günü, mesafe grubu, rota (testte n ≥ 200 olanlar), T anındaki hava durumu (IFR/VFR; TS/SN), **olay günleri** (eğitimde günlük ArrDel15 oranının P95'ini aşan test günleri; veriden tanımlı kural).
- **Segment başına metrikler:** n, gözlenen oran, ortalama tahmin (calibration-in-the-large), PR-AUC (yaygınlıkla), Brier, pinball P80/P95, conformal kapsama P80/P95, modelin B1'e göre Δ'sı.
- **En kötü segmentler:** her boyutta en kötü 5 segment (n eşiğiyle); seyrek segmentler toplamın içinde gizlenmez.
- **Çoklu karşılaştırma:** segment kapsamasının hedeften sapması için segment başına binom testi; boyut başına Benjamini–Hochberg (FDR %5); bayraklı segmentler listelenir (keşifsel).
- **Kalıntı örüntüleri:** saat_blogu × ay ısı haritası (ortalama tahmin − gözlenen), sistematik sapma arama.
- **Özellik önemi:** permütasyon önemi (A'da; safsızlık önemi yüksek kardinaliteli özellikleri kayırdığı için tercih edilmez); isteğe bağlı SHAP özet grafiği. `Reporting_Airline` önemi tek sayı olarak verilebilir; taşıyıcı düzeyi kırılım verilmez.
- **Taşıyıcı sıralaması YOK (M2 sunum kuralları):** taşıyıcı boyutunda segment tablosu, sıralama, "en kötü havayolu" ya da taşıyıcı bazlı performans grafiği **üretilmez ve yayımlanmaz**. Arayüz şemasında taşıyıcı boyutu enum'da bulunmaz (§9). Rötar nedeni alanları zaten sızıntı listesinde; hata analizinde de kullanılmaz (taşıyıcı beyanıdır).
- Olağandışı dönemler test dışında kalmaz; olay günleri ayrıca raporlanır. A dönemi (Eylül–Aralık 2025) için olağandışı aksaklık günleri olup olmadığı veriden kontrol edilir: Ekim–Kasım 2025'te federal hükümet kapanması ve FAA uçuş azaltımları olduğu biliniyor (**doğrulanmadı**). Varsa A'da seçilen eşik ve erken durdurma etkilenebilir; günlük iptal oranı grafiğiyle gösterilir.

---

## 8. OR'a teslim (tampon optimizasyonu)

- **Kaynak model:** `plan` sözleşmeli kantil modelleri (tarife zamanında bilinebilir). T2 kantilleri yalnızca karşılaştırma için.
- **Düzey:** iki dosya.
  1. **Uçuş düzeyi** (yerel, yayımlanmaz): B ve test dönemi. Uçuş başına kantil ızgarası ve gerçekleşen değer; OR bununla politikayı örneklem dışında değerlendirir.
  2. **Hücre düzeyi:** **rota (origin–dest) × saat_blogu × mevsim**; yalnızca test n ≥ 50 olan hücreler (öneri). Hücre kantili olarak uçuş kantillerinin medyanı verilir. Bu, karışım dağılımının kantili değildir (yaklaşık); OR gerekirse uçuş düzeyinden kendisi toplar.
- **Biçim:** Parquet (DuckDB ile okunur), `deliverables/data/or/` altında (yazımı DE/OR klasör kuralına göre; ben yalnızca şemayı tanımlıyorum).

**`or_ucus_kantilleri.parquet`** (yerel; kuyruk no ve uçuş no **yok**)

| Sütun | Tip | Birim/Not |
|---|---|---|
| `ucus_id` | int64 | veri katmanındaki vekil anahtar |
| `donem` | str | `dogrulama_b` / `test` |
| `flight_date`, `origin`, `dest`, `saat_blogu`, `mevsim` | | |
| `crs_elapsed_dk` | float | tarifedeki blok süre |
| `q050 … q095` | float | dk; ham model kantilleri (çekirdek: 0,50/0,80/0,95; kesilebilir: 0,60/0,70/0,85/0,90) |
| `q080_conf`, `q095_conf` | float | dk; conformal ayarlı (kayan) |
| `p_iptal_sapma` | float | 0–1; koşulsuz risk için (§3.3) |
| `gerceklesen_arr_delay` | float | dk; iptal/sapmada NaN |
| `iptal`, `sapma` | int8 | 0/1 |

**`or_hucre_kantilleri.parquet`**: `origin, dest, saat_blogu, mevsim, n_ucus, crs_elapsed_medyan_dk, q050_medyan … q095_medyan, q080_conf_medyan, q095_conf_medyan, p_iptal_sapma_ortalama, gozlenen_kapsama_q080_conf, gozlenen_kapsama_q095_conf, model_surumu`.

- **OR'a notlar:**
  - (a) Newsvendor kritik oranı c_u/(c_u + c_o) duyarlılık analizinde değiştikçe gereken kantil düzeyi de değişir; ızgara bu yüzden var. Izgara kesilirse OR yalnızca 0,50/0,80/0,95'i ve B1 ampirik dağılımını kullanır.
  - (b) "Eklenen tampon varış rötarını dakika dakika azaltır" bir **varsayımdır** (uçuş süresi değişmez kabul edilir); OR formülasyonunda yazılmalı.
  - (c) Koşulsuz kantil formülü §3.3'te.
  - (d) Tarife fazlası özelliği (`tarife_fazlasi_dk`) hücre dosyasına da eklenebilir (kesilebilir).

---

## 9. Arayüz sözleşmesi (frontend; GitHub Pages)

Tam JSON Schema: **`experiments/arayuz-sozlesmesi.json`** (draft 2020-12, `sema_surumu` 0.1.0). Şema 4. haftada dondurulur (M2 ek kararı); o zamana kadar alan eklemek serbest, alan silmek frontend ile konuşularak yapılır.

**Dosyalar** (site kökünde `veri/` altında; her dosyada `dosya_turu` ayırıcısı ve `sema_surumu` var):

| Dosya | İçerik | Boyut sınırı (öneri) |
|---|---|---|
| `manifest.json` | dosya listesi, bayt, sha256, oluşturma zamanı | 8 KB (2026-11-23: 30 rota dosyasıyla ~5,2 KB) |
| `ozet.json` | proje metni, sorumluluk reddi, kaynaklar/lisans, bölme tarihleri, T, model listesi, başlık metrikleri (GA'lı), kabul ölçütleri sonucu | 50 KB |
| `havalimanlari.json` | 30 havalimanı: kod, ad, koordinat, saat dilimi, test n'i, gözlenen ve tahmin oranı, kapsama | 50 KB |
| `rotalar/<IATA>.json` (30 dosya) | rota × saat_blogu hücreleri: n, gözlenen/tahmin ArrDel15 oranı, P50/P80/P95 (dk), kapsama, blok süre medyanı, iptal oranı, tampon önerisi (OR'dan, boş olabilir) | dosya başına 300 KB |
| `kalibrasyon.json` | güvenilirlik kutuları (model başına 10 kutu), aylık kapsama (kayan/statik/ham) | 100 KB |
| `hava-deneyi.json` | plan / T2 / oracle metrikleri ve farklar; oracle etiketli | 30 KB |
| `hata-analizi.json` | boyut × segment metrikleri (taşıyıcı boyutu yok) | 200 KB |

- **Birimler:** süre ve kantiller **dakika** (1 ondalık), oranlar 0–1 (3 ondalık), tarihler ISO `YYYY-MM-DD`, aylar `YYYY-MM`.
- **Toplam boyut sınırı:** 10 MB (öneri; GitHub Pages sınırlarının çok altında; Pages sınırları GitHub belgesinden doğrulanmalı).
- **Yayımlanmayanlar:** ham veri ya da uçuş düzeyi satır, kuyruk numarası, uçuş numarası, taşıyıcı boyutunda metrik ya da sıralama, logo. Şemada her nesnede `additionalProperties: false` var; tanımsız alan doğrulamadan geçemez.
- **Hücre gizleme:** n < 50 olan hücreler yayımlanmaz (kararlılık).
- **Üretim:** JSON dosyalarını yalnızca son test kilidinden sonra çalışan bir betik (`deliverables/src/modeling/arayuz_ciktisi.py`, sonra) üretir ve her dosyayı şemaya göre doğrular (`test_arayuz_sema`). Frontend geliştirme için şemaya uyan **sahte örnek dosyalar** üretilebilir; bunlar `ornek: true` alanıyla işaretlenir ve gerçek sonuç gibi sunulmaz.

---

## 10. Data Engineer'dan beklenenler

### 10.1 Tablolar (Parquet; `yil=/ay=` bölümlü; `crs_kalkis_utc`'ye göre sıralı)
Kapsam filtresi: **Origin ∈ hedef 30** (varsayım: M3 kararındaki %64 kalkış payı bu filtreye karşılık geliyor; DE teyit etsin). İptal ve sapma dahil **hiçbir satır silinmez**.

1. **`ucuslar`** (özellik tarafı; yalnızca tarife bilgisi):
   - `ucus_id` (int64, kararlı vekil anahtar), `FlightDate`, `Month`, `DayofMonth`, `DayOfWeek`
   - `Reporting_Airline`, `Flight_Number_Reporting_Airline` (yerel; model dışı)
   - `OriginAirportID`, `Origin`, `DestAirportID`, `Dest`
   - `CRSDepTime`, `CRSArrTime`, `CRSElapsedTime`, `Distance`, `DistanceGroup`
   - `tz_origin`, `tz_dest`, `crs_kalkis_utc`, `crs_varis_utc`, `crs_kalkis_yerel_dk`, `utc_belirsiz`, `utc_bosluk`, `varis_gun_ofseti` (`zaman.py` çıktıları)
2. **`ucus_etiketleri`** (fiziksel olarak ayrı; özellik koduna doğrudan verilmez):
   - `ucus_id`, `ArrDelay`, `ArrDel15`, `Cancelled`, `Diverted`
   - geçmiş istatistikler için: `ActualElapsedTime`, `TaxiOut`, `DepDelay`
   - yalnızca analiz için: `CancellationCode`
3. **`ucus_anahtar`** (yerel, yayımlanmaz): `ucus_id`, `Tail_Number`. Çekirdekte kullanılmaz.
4. **`planli_yogunluk`**: havalimanı × yerel tarih × yerel saat; `planli_kalkis`, `planli_varis`. **Tüm BTS uçuşlarından** (30 dışı kalkışlar ve iptaller dahil) hesaplanır, filtrelemeden önce.
5. **`metar`**: `istasyon`, `iata`, `gozlem_utc` (IEM `valid`, UTC), `tmpf`, `dwpf`, `relh`, `drct`, `sknt`, `gust`, `vsby`, `alti`, `skyc1–4`, `skyl1–4`, `wxcodes`, `p01i`, `rapor_turu` (METAR/SPECI, varsa). Aynı istasyon ve `gozlem_utc` için tekrarlar tekilleştirilir (kural belgelensin). Fiziksel olarak olanaksız değerler NaN yapılır (IEM "çok az kalite kontrolü" diyor [D]); kural listesi DE'nin belgesinde olsun.
6. **`havalimani`**: `iata`, `airport_id`, `ad`, `lat`, `lon`, `tz`, `iem_istasyon`, `hedef_30` (bool).
7. **`hava_T{T}`** ve **`hava_oracle`** (birleştirilmiş; `ucus_id` anahtarlı; origin_* ve dest_* önekli sütunlar, `gozlem_utc` ve `gozlem_yasi_dk` dahil).

### 10.2 Hava birleştirme kuralı
- **T öncesi:** istasyon başına `merge_asof(direction='backward')`, anahtar `gozlem_utc`, hedef zaman **`crs_kalkis_utc − T − 10 dk`** (10 dk = METAR'ın yayımlanma gecikmesi için tolerans; varsayım, parametre olsun). En fazla 3 saat geriye bakılır; daha eskiyse NaN.
- **Dest:** aynı hedef zaman (kalkış − T − 10 dk), **varış saati değil**. Dest 30 dışındaysa NaN (Kullanıcıya soru 2).
- **Oracle:** origin için `crs_kalkis_utc`, dest için `crs_varis_utc` hedef zamanı, aynı 3 saat toleransı. Gerçekleşen saatler kullanılmaz.
- Tüm zamanlar UTC; `zaman.py` dönüşümü kullanılır. DST bayraklı satırlar korunur.
- **Zorunlu satır düzeyi test (DE):** her satırda `gozlem_utc <= hedef_zaman` (T öncesi tabloda) ve tolerans dışı satırlarda NaN. DS aynı testi modelleme tarafında tekrarlar.

### 10.3 Boyut notu
- Kaba hesap (ölçüm değil): 36 ay × yaklaşık 404 bin = yaklaşık 14,5 milyon uçuş. M3 kararındaki tahmin yaklaşık 180 MB Parquet, yaklaşık 3 GB bellek. Eğitim matrisi float32 ile yaklaşık 50 özellik × 9,7 milyon ≈ 2 GB (kaba).
- METAR küçük: 30 istasyon × 3 yıl. IEM sınırı 1.000 istasyon-yıl [D]; 90 istasyon-yıl. Dest havası tüm varış noktalarına genişletilirse istasyon-yıl sayısı yeniden hesaplanmalı.
- DS, istatistik tablolarını DuckDB ile hesaplar; pandas'a yalnızca model matrisi alınır. Tepe bellek ölçülmeli (Temmuz 2025 tek ayda 2,3 GB tepe görüldü [ölçüm]).
- DE'den ayrıca: Ağustos 2026'nın tamlık kontrolü (§1.1); her ay için satır sayısı ve dosya sha256'sı (veri sürümü notu; MLflow'a girer).

---

## 11. MLflow'da kaydedilecekler (MLOps ile uyum için kısa)

- **Deney adları (öneri):** `havayolu-ds/arrdel15`, `havayolu-ds/iptal`, `havayolu-ds/kantil`, `havayolu-ds/hava-deneyi`, `havayolu-ds/son-test`. Adlandırmayı MLOps'un sözleşmesine uyarlarım.
- **Parametreler:** bölme tarihleri, kat kimliği, T, sözleşme adı ve özet (sha256), özellik listesi, hiperparametreler, tohumlar, m/min_n, conformal penceresi, kalibratör türü, eşik.
- **Veri sürümü:** Parquet dosyalarının sha256'sı ve satır sayıları, DE betik commit'i.
- **Metrikler:** §5.1'deki tümü; bootstrap GA'ları `*_ga_alt` / `*_ga_ust`; kat ve segment bazında metrikler artefakt tablosu olarak.
- **Artefaktlar:** model dosyaları, istatistik tabloları (`fit` penceresi meta verisiyle), özellik sözleşmesi JSON'u, güvenilirlik ve kapsama grafikleri, segment tabloları, permütasyon önemi, OR Parquet'leri, arayüz JSON'ları ve şema doğrulama çıktısı.
- **Etiketler:** `asama` = gelistirme | son_test, `oracle` = true/false, `sozlesme` = plan/T2/oracle, `git_commit`, kütüphane sürümleri (lightgbm, scikit-learn, mapie, pandas, duckdb).
- Son test koşusu tek olmalı; `son-test` deneyinde ikinci koşu varsa denetimde bayrak kalkar.

---

## 12. Haftalık sıra (veri katmanı onayından sonra 6 hafta)

| Hafta | Çekirdek | Kesilebilir |
|---|---|---|
| **H1** | DE veri katmanı (§10) ve testleri · DS: `bolme.py`, sızıntı testleri (§2.6), EDA defteri (yaygınlık, aylık ArrDel15/iptal, eksiklik, ArrDelay dağılımı), metrik fonksiyonları ve testleri (pinball, kapsama, blok bootstrap) | — |
| **H2** | B0, B1 (sınıflandırma + kantil) K3/K4 + A'da; istatistik/hedef kodlama sınıfı; lojistik baseline (Pipeline); LightGBM ArrDel15 `plan`; MLflow düzeni | K1/K2 katları, B2 |
| **H3** | Rastgele arama (K3/K4); LightGBM kantil P50/P80/P95 `plan`; tek yönlü conformal (kayan + statik); MAPIE CQR %80; iptal modeli `plan`; METAR `T2` ArrDel15 | XGBoost, ızgara kantilleri, iptal `T2` |
| **H4** | Hava deneyi (plan/T2/oracle); B'de kalibratör ve eşik; hata analizi (A üzerinde, keşifsel); **arayüz şemasını dondur**; OR uçuş/hücre dosyaları (B dönemi) | `aksaklik` hedefi, T ∈ {6, 12}, genişleyen kodlama kontrolü, SHAP |
| **H5** | Kabul ölçütleri ve yapılandırma dondurulur → **son test (tek sefer)** → test hata analizi, bootstrap GA'ları; OR test dosyaları; model kartı; frontend tasarımı (şemadan sahte veriyle) | %95 iki yönlü MAPIE aralığı |
| **H6** | Arayüz JSON üretimi ve şema doğrulaması; frontend uygulaması; README/vaka çalışması; tampon hafta | rotasyon özellikleri deneyi |

**Kesme sırası (zaman daralırsa, ilk kesilen önce):** XGBoost → T duyarlılığı → `aksaklik` → K1/K2 katları → ızgara kantilleri (OR 3 düzeyle çalışır) → %95 iki yönlü aralık → SHAP. **Kesilmeyecekler:** B1, sızıntı testleri, plan/T2/oracle ayrımı, tek yönlü conformal kapsama, blok bootstrap GA'ları, tek seferlik son test.

---

## 13. Model kartı iskeleti (H5)
Amaç ve kullanım dışı durumlar (operasyonel karar aracı değil; havayollarıyla bağlantısız) · veri ve dönem · bilgi zamanı · özellikler ve sözleşme · bölme · baseline'lar · metrikler (toplam + segment) · kapsama · hava deneyi · sınırlılıklar (iptal zamanı bilinmez, kuyruk değişimi, BTS kapsamı rapor eden taşıyıcılarla sınırlı, koşullu kantiller, mevsim kayması) · tekrar üretim (tohum, sürümler, veri sha256'ları).

---

## 14. Açık noktalar ve riskler (özet)
- **Mevsim kayması:** kalibrasyon kışta, test yazda. Kayan pencere hafifletir, ama ilk test ayı (Mart) kışa yakın bir pencereyle kalibre edilir.
- **Olağandışı dönemler:** A'da (Ekim–Kasım 2025) olası hükümet kapanması ve FAA azaltımları (doğrulanmadı); eğitimde Temmuz 2024'teki yaygın BT kesintisi (doğrulanmadı). Erken durdurmayı ve eşiği etkileyebilir; veriyle kontrol edilecek.
- **İptal hedefinin tanımı:** iptal zamanı bilinmiyor (§3.2).
- **METAR katkısı küçük çıkabilir** (proje kısa listesindeki belirsizlik). Bu da geçerli bir sonuçtur; oracle açığıyla birlikte yorumlanır.
- **Hesap süresi:** 2,4 milyon test satırında (kaba) 1000 blok bootstrap × AUC uzun sürebilir; süre H1'de küçük örnekle ölçülecek.
- **BTS revizyonları ve son ayın tamlığı** (§1.1).
- **Kütüphane API'leri** (MAPIE sürümü, `TargetEncoder` parametreleri) kurulu sürümün belgesiyle doğrulanacak; yeni bağımlılıklar (lightgbm, mapie, mlflow, duckdb, isteğe bağlı xgboost, jsonschema) MLOps/mimari kararıyla sabitlenmeli.
