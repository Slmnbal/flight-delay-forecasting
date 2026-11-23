# M1 – Havayolu alanı veri kaynakları araştırması

- **Tarih:** 2026-11-17
- **Kapsam:** Gerçek, açık havayolu verisiyle 4–6 haftalık, tek kişilik, CV'ye konacak bir data scientist projesi için veri kaynakları. AI engineer ve OR ikincil.
- **Yöntem:** Yalnızca resmi belge ve sayfalar okundu, hiçbir veri indirilmedi. Örneklem incelemesi (data-source-discovery 4. adım) bu yüzden yapılmadı; proje seçildikten sonra kullanıcı yapmalı (bkz. §7).
- **Etiketler:**
  - **[D]** Doğrulandı: kaynağın kendi sayfasında okundu.
  - **[K]** Kısmen doğrulandı: ikincil kaynakta ya da katalog kaydında görüldü, resmi metin okunmadı.
  - **[V]** Varsayım ya da tahmin: doğrulanmadı.

---

## 1. Özet (Portföy Danışmanı için)

1. **En güçlü çekirdek, ABD BTS verisi.** On-Time Performance (uçuş düzeyi, 1987'den bugüne, aylık), T-100 (rota-ay düzeyinde koltuk, yolcu ve sefer) ve DB1B (%10 bilet örneklemi, ücret, çeyreklik) aynı havalimanı ve taşıyıcı kodlarını kullanır. Üçü de ücretsiz ve hesap gerektirmez. Data.gov kayıtlarında ABD kamu malı (public domain) etiketi var [K]; BTS'nin kendi sayfasında lisans metni okunamadı.
2. **Hava durumu birleştirmesi kolay ve lisans açısından temiz.** Iowa Environmental Mesonet (IEM) ASOS/METAR arşivi, havalimanı istasyon koduyla saatlik gözlem verir. Kendi beyanı "public domain" [D]. NOAA NCEI LCD de ücretsiz; tek koşul atıf [D].
3. **Ağ ve meta veri:** OurAirports kamu malıdır [K]: havalimanı koordinatları ve türü. OpenFlights ODbL lisanslıdır ve rota verisi 2014'te donmuştur [D]. Bu yüzden rota ağı için güncel kaynak T-100'dür.
4. **Avrupa:** Eurostat havayolu yolcu istatistikleri (avia_par) atıfla ticari ya da ticari olmayan yeniden kullanıma açık; ABD gibi AB dışı ülke verisinde istisnalar var [D]. EUROCONTROL ansperformance.eu günlük havalimanı trafiği ve ATFM rötarı CSV olarak ücretsiz sunuluyor, ancak lisans metni sayfada yok [D: içerik / doğrulanmadı: lisans]. EUROCONTROL ADRR uçuş düzeyinde veri veriyor ama kayıt, inceleme ve yalnızca Ar-Ge kullanımı gerektiriyor; yeniden dağıtım yasak [K]. Bu yüzden portföy için ikincil.
5. **Önerilmeyen ya da dikkat isteyenler:** OpenSky (ticari olmayan araştırma lisansı, büyük veri), Meteostat (CC BY ile CC BY-NC arasında çelişkili beyan), kazınmış Expedia fiyat verisi (Kaggle, lisans doğrulanmadı) ve OpenFlights rotaları (2014, güncel değil).

---

## 2. Veri kaynakları tablosu

| # | Kaynak | Erişim | Lisans | Ücretsiz ve hesapsız mı? | Zaman / sıklık | Yaklaşık boyut | Durum |
|---|---|---|---|---|---|---|---|
| 1 | **BTS Reporting Carrier On-Time Performance** (uçuş düzeyi) | TranStats "Download" sayfası (alan seçerek CSV veya hazır aylık zip) | ABD federal hükümet eseri. Data.gov kayıtlarında `usa.gov/publicdomain/label/1.0` [K]; BTS sayfasında lisans metni yok | Evet / evet [D] | 1987'den bugüne; en son veri Ağustos 2026 [D]; aylık | 111 alan [D]. Yıllık satır sayısı: 2015 için ikincil kaynakta yaklaşık 5,8 milyon uçuş [K]. Aylık yaklaşık 0,5–0,7 milyon satır [V] | Önerilir (çekirdek) |
| 2 | **BTS Marketing Carrier On-Time Performance** | TranStats | 1 ile aynı [K] | Evet [K] | Ocak 2018'den bugüne [K] | Bilinmiyor | Opsiyonel (codeshare ayrımı) |
| 3 | **BTS T-100 (Air Carrier Statistics, Form 41 Traffic)** Segment ve Market, Domestic ve International | TranStats | 1 ile aynı mantık [V]; T-100 için data.gov lisans etiketi okunmadı | Evet [D: ücretsiz indirme] | 1990–2026, aylık [D]; uluslararası veri yurt içinden 3 ay geç yayınlanır [D]; uluslararası segmentte en az 6 ay gizlilik [K] | Rota-taşıyıcı-uçak tipi-ay düzeyinde, onbinlerden yüzbinlere satır/yıl [V] | Önerilir (talep / kapasite) |
| 4 | **BTS DB1B (Airline Origin & Destination Survey)** Coupon, Market, Ticket | TranStats | 1 ile aynı mantık [V] | Evet [K] | 1993–2025, çeyreklik [D] | %10 bilet örneklemi [D]. Çeyreklik dosyalar büyük; Coupon tablosu en büyüğü [V] | Önerilir (ücret), dikkatli |
| 5 | **DOT Domestic Airline Consumer Airfare Report** (Tablo 1, 1A, 6) | DOT / data.transportation.gov | ABD hükümet eseri [V] | Evet [K] | 1996 Q3'ten itibaren çeyreklik [K] | En büyük 1000 şehir çifti; Tablo 6'da günde en az 10 yolculu tüm pazarlar (2021 Q4'te 5.958 pazar) [K] | Önerilir (DB1B'nin hafif, özet alternatifi) |
| 6 | **Iowa Environmental Mesonet (IEM) ASOS/METAR arşivi** | `mesonet.agron.iastate.edu/request/download.phtml` ve betik API'si `/cgi-bin/request/asos.py` | "Public domain ... may be used freely by anyone for any lawful purpose"; atıf rica edilir [D] | Evet / evet [D] | Dünya geneli istasyonlar, 10 dakikada bir güncellenir; istasyon başlangıç yılları değişken [D] | İstek sınırı 1.000 istasyon-yıl [D] | Önerilir (hava durumu) |
| 7 | **NOAA NCEI Local Climatological Data (LCD)** | NCEI erişim servisi, bulut | Lisans metni yok; kullanım koşulu "Cite this dataset" ve garanti yok [D]; "çoğu durumda ücretsiz" [D] | Evet [D] | Yaklaşık 1000 ABD istasyonu, 2005'ten beri; aylık güncelleme [D] | Bilinmiyor | Yedek (hava durumu) |
| 8 | **NOAA GHCNh (saatlik)** | NCEI | Bir katalog kaydında CC0 [K] | Evet [K] | Bilinmiyor | Bilinmiyor | Yedek |
| 9 | **OurAirports** (airports.csv, runways.csv…) | ourairports.com/data, GitHub aynası | "All data is released to the Public Domain", garanti yok [K: sayfa alıntısı arama sonucundan; sayfa sertifika hatası nedeniyle doğrudan okunamadı] | Evet / evet | Sürekli güncellenen topluluk verisi [V] | Küçük (onbinlerce havalimanı) [V] | Önerilir (meta veri) |
| 10 | **OpenFlights** (airports, airlines, routes, planes) | openflights.org/data.php, GitHub | **ODbL 1.0**, içerik DbCL; atıf ve türev verinin açık lisansla paylaşılması gerekir [D] | Evet / evet [D] | Rotalar **Haziran 2014'te dondu**, "yalnızca tarihsel değer" [D] | 67.663 rota, 3.321 havalimanı, 548 havayolu [D] | Yalnızca meta veri; rota için önerilmez |
| 11 | **FAA Releasable Aircraft Registry** (MASTER, ACFTREF) | faa.gov indirme sayfası | ABD hükümet verisi [V]; lisans metni okunmadı | Evet [K] | Her iş günü güncellenir [K] | Yaklaşık 60 MB arşiv [K] | Opsiyonel (kuyruk no → uçak tipi ve yaşı) |
| 12 | **Eurostat havayolu istatistikleri** (avia_par_*, avia_pa*) | Eurostat veri tarayıcısı / API | Atıfla ticari ya da ticari olmayan yeniden kullanım serbest. İstisnalar: üçüncü taraf materyali, AB/EFTA/aday dışı ülke verisi (ör. ABD) ticari kullanılamaz; değişiklik belirtilmeli [D] | Evet / evet [K] | Aylık, çeyreklik, yıllık serilerin yılları bilinmiyor [V] | Küçük–orta [V] | Önerilir (Avrupa talep zaman serisi) |
| 13 | **EUROCONTROL ansperformance.eu açık veri** | `ansperformance.eu/data/` (CSV/Excel) | **Doğrulanmadı.** Sayfada lisans yok; bir dashboard'da "copyright notice ve disclaimer ile kopyalanabilir" notu var [K] | Evet / evet [D] | Havalimanı trafiği günlük, Ocak 2016–Eylül 2026; havalimanı varış ATFM rötarı günlük, 2020–2026; ATC kalkış öncesi rötarı günlük, 2016–2026 [D] | Küçük [V] | Kullanılabilir, lisans teyidi şart |
| 14 | **EUROCONTROL ADRR** (uçuş düzeyi, 4D yörünge) | OneSky Online kaydı, başvuru, inceleme, kullanım koşullarını kabul | Ücretsiz, yalnızca Ar-Ge; **paylaşma ve dağıtma yok**, atıf şart [K] | Ücretsiz ama **hesap ve onay gerekli** [D] | 2015'ten bugüne; Ocak 2027'ye kadar 2015–2025'in tüm ayları hedefleniyor; yayın gecikmesi 24 aydan 12 aya iniyor [D] | 100 milyondan fazla uçuş kaydı hedefi [D] | İkincil (erişim belirsiz, dağıtım yasak) |
| 15 | **OPDI** (OpenSky ADS-B tabanlı uçuş listesi ve olayları) | opdi.aero (ansperformance.eu bağlantısı) | Doğrulanmadı | Bilinmiyor | Ocak 2022–Eylül 2026 [D] | Bilinmiyor | Araştırılmalı |
| 16 | **OpenSky Network** tarihsel veri | Hesap ve başvuru | Ticari olmayan araştırma, eğitim ve kamu amaçlı sınırlı lisans [K]. 2019–2022 Zenodo uçuş listesi anlık görüntüsü CC BY [K] | Hesap gerekli [K] | Zenodo görüntüsü Aralık 2022'de durdu [K] | Çok büyük [V] | Önerilmez (portföy için gereksiz karmaşık) |
| 17 | **Kaggle "2015 Flight Delays and Cancellations"** (usdot) | Kaggle hesabı | **Doğrulanmadı** (CC0 olduğu söyleniyor, sayfada okunamadı) | Kaggle hesabı gerekir [V] | 2015 [K] | Yaklaşık 5,8 milyon uçuş, 14 havayolu [K] | Önerilmez; ham BTS daha temiz ve günceldir |
| 18 | **Meteostat** | data.meteostat.net (Parquet, beta) | **Çelişkili:** CC BY-NC 4.0 ile CC BY 4.0 arasında iki beyan [K] | Anahtarsız toplu erişim [K] | Eski bulk servisi Ocak 2026'dan itibaren güncellenmiyor [K] | Bilinmiyor | Önerilmez (IEM daha temiz) |
| 19 | **Kazınmış Expedia fiyatları** (Kaggle dilwong/flightprices) | Kaggle | **Doğrulanmadı**; kazıma kaynaklı, kullanım koşulu riski [V] | Kaggle hesabı | 2022-04-16 ile 2022-10-05 arası [K] | Bilinmiyor | Önerilmez |

---

## 3. Kaynak ayrıntıları

### 3.1 BTS Reporting Carrier On-Time Performance (çekirdek)
- **Kapsam [D]:** Yurt içi gelirin en az %0,5'ini taşıyan ABD taşıyıcılarının tarifeli, aktarmasız yurt içi uçuşları. Eşik 1 Ocak 2018'den itibaren %1'den %0,5'e indi. Rapor veren taşıyıcı sayısı yıla göre değişir: 2018'de 18, 2021'de 17 [K: BTS sayfası, arama özeti].
- **Önemli alanlar [D]:**
  - Tarih: FlightDate, Year, Month, DayOfWeek.
  - Kimlik: Reporting_Airline, Tail_Number, Flight_Number.
  - Havalimanı: Origin/Dest, OriginAirportID, CityMarketID.
  - Tarife saatleri: CRSDepTime, CRSArrTime, CRSElapsedTime.
  - Gerçekleşen saatler: DepTime, ArrTime, TaxiOut, TaxiIn, WheelsOff/On, AirTime, ActualElapsedTime.
  - Rötar: DepDelay, ArrDelay, ArrDel15.
  - Rötar nedeni (dakika, 06/2003'ten): CarrierDelay, WeatherDelay, NASDelay, SecurityDelay, LateAircraftDelay.
  - İptal ve sapma: Cancelled, CancellationCode, Diverted, Div* alanları (alan listesinin ilk 100 alanında Div1–Div4 görüldü).
  - Mesafe: Distance.
- **Saat dilimi [D]:** Saatler yerel saattir (hhmm). Hava durumuyla UTC'de birleştirmek için havalimanı saat dilimi gerekir. Bunu OurAirports koordinatları ve bir saat dilimi kütüphanesiyle üretmek gerekir [V].
- **Bilinen kalite sorunları:**
  - Rötar nedeni dakikaları taşıyıcının kendi beyanıdır ve yalnızca 15 dakika ve üzeri rötarlarda doldurulur [V: yaygın bilgi, bu oturumda resmi belgede okunmadı].
  - İptal edilen uçuşlarda gerçekleşen saat alanları boştur [V].
  - Gece yarısını geçen uçuşlarda "2400" saat değeri ve gün devri sorunu vardır [V].
  - Havalimanı kodları zamanla değişebilir; kararlı anahtar olarak `OriginAirportID` kullanılmalı [V].
  - Rapor veren taşıyıcı listesi yıllara göre değişir. Bölgesel taşıyıcılar marketing ve operating ayrımında farklı görünür [K].
- **DS problemleri:**
  - Sınıflandırma: ArrDel15, iptal.
  - Regresyon / kantil regresyon: ArrDelay (LightGBM quantile, MAPIE).
  - Zaman serisi: havalimanı-gün rötar oranı ya da iptal sayısı (ETS/ARIMA, rolling-origin backtest, MASE).
  - Kümeleme: havalimanı veya rota rötar profilleri.
  - Nedensel ya da yarı-nedensel analiz: hava durumu şokunun etkisi, rötar yayılımı (LateAircraftDelay ve kuyruk numarası zinciri).
  - Drift: COVID dönemi ve 2018 eşik değişikliği doğal drift örnekleridir.

### 3.2 BTS T-100 (talep ve kapasite)
- **Tablolar [D]:** Domestic/International × Segment/Market ve Combined. Segment tablosunda uçak tipi, koltuk (satışa sunulan kurulu koltuk), taşınan yolcu, planlanan ve gerçekleşen sefer, uçak saatleri, yük ve posta ile doluluk oranı var. Market tablosunda kalkış-varış arası binen yolcu var.
- **Kapsam [D]:** Yıllık işletme geliri 20 milyon $ ve üzeri sertifikalı taşıyıcılar. ABD'ye dokunan uluslararası trafikte yabancı taşıyıcılar da var; iki ucu yabancı olan uçuşlar hariç.
- **Gecikmeler:** Uluslararası veri yurt içinden 3 ay geç gelir. Combined tablolar bu yüzden yurt içinin son 3 ayını dışarıda bırakır [D]. Uluslararası segment için en az 6 ay gizlilik kuralı vardır [K: 1997 DOT kuralı, DataLumos/NTL etiketi].
- **DS problemleri:**
  - Rota-ay yolcu talebi tahmini: hiyerarşik zaman serisi (rota → havalimanı → ulusal); statsforecast, Darts, LightGBM global model.
  - Doluluk oranı regresyonu.
  - Rota kümeleme: mevsimsellik profili.
  - COVID şoku ve toparlanma analizi.
- **Kalite [V]:** Küçük taşıyıcıların ya da charter'ların kayıtları dağınık olabilir. Aynı rota farklı uçak tiplerine bölünür, bu yüzden toplulaştırma gerekir.

### 3.3 BTS DB1B (ücret)
- **[D]** %10 bilet örneklemi, 1993–2025, çeyreklik.
  - Coupon tablosu: kupon düzeyi, ücret sınıfı.
  - Market tablosu: yönlü pazar, prorate edilmiş pazar ücreti.
  - Ticket tablosu: güzergâh ücreti, gidiş-dönüş bayrağı.
- **Kalite [V]:** Sıfır ya da çok düşük ücretli kayıtlar (mil puanı, personel bileti) ve aşırı yüksek değerler literatürde filtrelenir; eşik değerleri bu oturumda doğrulanmadı. Ücretin vergi ve harç içerip içermediği belgede teyit edilmeli. Yalnızca yurt içi.
- **Boyut [V]:** Coupon tablosu çeyrek başına onlarca milyon satır olabilir; tek dizüstünde yalnızca Market ya da Ticket tablosu ve sütun seçimiyle (Parquet + DuckDB/Polars) çalışılmalı.
- **DS problemleri:**
  - Pazar ücreti regresyonu: mesafe, rekabet (taşıyıcı sayısı, HHI), hub etkisi.
  - Düşük maliyetli taşıyıcı girişinin ücrete etkisi: fark-içinde-fark, nedensel analiz.
  - Gelir yönetimine giriş.
- **Hafif alternatif:** DOT Consumer Airfare Report (Tablo 1/1A/6) çeyreklik şehir çifti ortalama ücreti ve pazar payı sunar [K]. Hızlı prototip için idealdir.

### 3.4 Hava durumu
- **IEM ASOS [D]:** İstasyon kodu (ör. ORD, JFK; ABD'de genelde IATA koduyla aynı, dünya genelinde ICAO kodu) ile sorgulanır. Gelen alanlar: sıcaklık, çiğ noktası, rüzgâr ve hamle, görüş, bulut tavanı, mevcut hava kodları, buzlanma, ham METAR. Yağış yalnızca ABD istasyonlarında var. Kalite kontrolü çok az ("very little quality control"). Saat UTC ya da ABD yerel saat dilimi olarak seçilebilir. Betikle erişim belgelenmiş.
- **NOAA LCD [D]:** Yaklaşık 1000 ABD havalimanı ve önemli istasyon, aylık güncelleme, atıf şartı.
- **Birleştirme anahtarı:** (havalimanı istasyonu, UTC saat). On-Time'daki yerel saatin UTC'ye çevrilmesi gerekir [V].

### 3.5 Ağ ve meta veri
- **OurAirports [K]:** Koordinat, havalimanı türü, ICAO/IATA kodları, ülke ve bölge. Mesafe, saat dilimi ve harita için kullanılır.
- **OpenFlights [D]:** ODbL. Bu lisansla türetilmiş bir veri tabanını kamuya açarsan aynı lisansla paylaşman gerekir; kod deposuna veri koyarken dikkat. DST verisi 2009 yaklaşıklamasıdır; airlines tablosundaki "Active" alanı güvenilmez; rotalar 2014'te kaldı.
- **FAA Registry [K]:** Tail_Number → üretici, model, üretim yılı. Uçak yaşı ve tipi özelliği için kullanılır. ABD tescilleri "N" ile başlar; On-Time'daki Tail_Number ile eşleşme oranı doğrulanmadı [V].

### 3.6 Avrupa
- **Eurostat [D: lisans / K: veri seti]:** "Detailed air passenger transport by reporting country and routes" (avia_par_xx) rapor eden ülke ve havalimanı çifti düzeyinde yolcu, sefer ve koltuk verir [V: alanlar tam doğrulanmadı]. Avrupa rota talep zaman serisi için uygundur. ABD kaynaklı veriler ticari olmayan kullanımla sınırlıdır; portföy projesi ticari olmadığından sorun beklenmez [V].
- **EUROCONTROL ansperformance.eu [D: içerik]:** Günlük havalimanı IFR trafiği ve varış ATFM rötarı (2020–2026, post-ops düzeltmesiz), ATC ve toplam kalkış öncesi rötarı, taxi-out ek süresi (aylık). Bunlar havalimanı-gün zaman serisi tahmini için iyi, küçük ve temiz veriler. **Lisans sayfada belirtilmemiş**; kullanmadan önce sitenin "Disclaimer" ve kullanım koşulları sayfası okunmalı.
- **ADRR [K]:** Uçuş düzeyi ve yörünge verisi. Erişim kurumsal ya da akademik e-posta ve inceleme gerektirir; ham veri GitHub'a konamaz. Tek kişilik portföy için riskli.

---

## 4. Birleştirilebilirlik (anahtarlar)

| Birleştirme | Anahtar | Not |
|---|---|---|
| On-Time ↔ T-100 | (Origin/Dest AirportID ya da IATA, taşıyıcı kodu, yıl-ay) | T-100 aylık ve rota düzeyinde; On-Time'ı aya toplulaştırarak birleştirilir [V]. Taşıyıcı kodu tanımları (unique carrier, operating/marketing) uyumlu hâle getirilmeli |
| On-Time ↔ DB1B | (Origin/Dest, yıl-çeyrek), gerekirse CityMarketID | DB1B çeyreklik; rota-çeyrek düzeyi [V] |
| On-Time ↔ IEM/NOAA | (havalimanı istasyon kodu, UTC saat) | Yerel saat → UTC dönüşümü; en yakın önceki gözlem (`merge_asof`) [V] |
| On-Time ↔ FAA Registry | Tail_Number ↔ N-number | Eşleşme oranı doğrulanmadı [V] |
| Hepsi ↔ OurAirports | IATA / ICAO kodu | Koordinat, saat dilimi, mesafe |
| Eurostat ↔ EUROCONTROL | ICAO havalimanı kodu, ay | Avrupa havalimanı-ay paneli [V] |
| On-Time içinde rötar yayılımı | Tail_Number + FlightDate + CRSDepTime sırası | Aynı uçağın önceki bacağı; uçak rotasyonu yeniden kurulur [V] |

---

## 5. Tahmin → optimizasyon (OR) uzantısı (kısa)

| Tahmin | Optimizasyon | Veri yeterliliği |
|---|---|---|
| T-100 rota-ay yolcu talebi (kantil tahmin) | Sabit filoyla rotalara kapasite (sefer × uçak tipi) atama, talebi karşılamama cezası; Pyomo/PuLP + HiGHS; stokastik ya da robust varyant | Talep ve koltuk verisi var [D]. **İşletme maliyeti ve gelir yok.** Maliyet parametreleri varsayım olarak belgelenmeli (ör. blok saat başına maliyet ve ortalama ücret DB1B'den) [V] |
| On-Time rötar kantil tahmini (ör. P80 varış rötarı) | Tarife tampon (block time padding) optimizasyonu: tampon maliyeti ile beklenen rötar maliyeti arasındaki takas; ya da kuyruk zincirinde dönüş süresi tamponu | CRSElapsedTime ve gerçekleşen süreler var [D]. Rötar maliyeti varsayım [V] |
| Günlük havalimanı iptal / rötar tahmini | Basitleştirilmiş aksaklık (disruption) yönetimi, CP-SAT ile yeniden atama | Kuyruk numarasıyla rotasyon kurulabilir [V]; ekip verisi **yok**, ekip çizelgeleme gerçek veriyle yapılamaz |
| DB1B ücret ve talep | Gelir yönetimine giriş (EMSR-b koruma seviyeleri) | Rezervasyon eğrisi ya da ücret sınıfı bazlı talep yok. Yalnızca kaba, varsayımlı demonstrasyon yapılabilir [V] |

Sonuç: OR uzantısı için en dürüst iki seçenek (a) T-100 talep tahmini → kapasite atama ve (b) rötar kantil tahmini → tampon optimizasyonu. İkisinde de maliyet parametreleri gerçek veriden değil varsayımdan gelir ve bu açıkça yazılmalı.

---

## 6. Riskler

### 6.1 Lisans
- BTS için data.gov kayıtlarında kamu malı etiketi var, ama BTS'nin kendi sayfasında lisans okunamadı (web-policies sayfası 403 verdi) [K]. Risk düşük; README'de "U.S. DOT/BTS, public domain (U.S. Government work)" ve kaynak URL'si yazılmalı.
- OpenFlights ODbL lisanslı: türev veri tabanı paylaşılırsa share-alike yükümlülüğü doğar. Yalnızca havalimanı meta verisi gerekiyorsa OurAirports tercih edilmeli.
- EUROCONTROL açık verisinin lisansı doğrulanmadı. ADRR yeniden dağıtımı yasaklıyor [K].
- OpenSky ticari olmayan bir lisans [K]. Meteostat'ın lisans beyanı çelişkili [K]. Kaggle aynaları ve kazınmış fiyat verisi doğrulanmadı.
- **Kural:** Ham veri kod deposuna konmamalı; indirme betiği ve kaynak bağlantısı paylaşılmalı.

### 6.2 Veri boyutu (tek dizüstü)
- On-Time 111 alanlı ve yılda milyonlarca satırlı [D/K]. 1–3 yıl, sütun seçimiyle ve Parquet + DuckDB/Polars kullanılarak 16 GB RAM'li bir dizüstünde işlenebilir olmalı [V]. Tüm 1987–2026 dönemi gereksiz ve zor.
- DB1B Coupon büyük [V]; Market ya da Ticket tablosu ya da Consumer Airfare Report tercih edilmeli.
- T-100, Eurostat, ansperformance ve OurAirports küçük [V].
- IEM için istek sınırı 1.000 istasyon-yıl [D]. 30 havalimanı × 3 yıl gibi bir kapsam rahat sığar.

### 6.3 Sızıntı tuzakları (tahmin anında bilinmeyen alanlar)
- **On-Time, kalkış öncesi varış rötarı tahmininde yasak alanlar:**
  - Gerçekleşen saat ve süreler: DepTime, DepDelay, DepDel15, TaxiOut, WheelsOff, WheelsOn, TaxiIn, ArrTime, ActualElapsedTime, AirTime.
  - Rötar nedeni dakikaları: Carrier/Weather/NAS/Security/LateAircraftDelay.
  - İptal ve sapma: CancellationCode, Diverted ve Div* alanları.
  - Hedefin türevleri: ArrDelayMinutes, ArrivalDelayGroups.
- **Hava durumu:** Gerçekleşmiş (gözlenen) hava, tahmin anında bilinmez. Ya tahmin ufku kadar önceki gözlem kullanılmalı (ör. kalkıştan 2 saat önceki METAR) ya da bunun bir "oracle / üst sınır" deneyi olduğu açıkça yazılmalı. Arşivlenmiş hava tahmini (TAF/NWP) kaynağı bu oturumda doğrulanmadı.
- **Rotasyon özellikleri:** Önceki bacağın rötarı yalnızca o bacak gerçekleştiyse ve tahmin ufkundan önceyse kullanılabilir.
- **Hedef kodlama ve istatistikler:** Havalimanı veya rota rötar ortalamaları yalnızca eğitim döneminden hesaplanmalı.
- **Doğrulama:** Rastgele değil zamana göre bölme ya da rolling-origin backtest kullanılmalı.
- **Seçim yanlılığı:** İptal edilen uçuşlarda ArrDelay yok. İptaller modelden düşürülürse seçim yanlılığı oluşur; iptal ayrı hedef olmalı ya da açıkça hariç tutulmalı.
- **T-100 ve DB1B:** Yayın gecikmesi var (uluslararası T-100 +3 ay, DB1B çeyreklik). Gerçekçi tahmin senaryosunda "veri ne zaman elde olurdu" kuralı uygulanmalı.
- **Drift ve kırılmalar:** 2018 eşik değişikliği rapor eden taşıyıcı kümesini değiştirdi [D]; COVID dönemi bir yapı kırılmasıdır [V].

### 6.4 Gerçek şirket adlarıyla sunum
- BTS verisi taşıyıcıları adıyla verir. Rötar nedeni kodları taşıyıcının kendi beyanıdır [V]. "X havayolu kötü" gibi itibar zedeleyici, nedensel olmayan iddialardan kaçınılmalı.
- Sonuçlar "ABD DOT/BTS kamu verisine dayalı analiz; hiçbir havayoluyla bağlantılı değildir" notuyla sunulmalı. Taşıyıcı logoları kullanılmamalı; Eurostat da logo ve ticari markaları hariç tutar [D].
- Taşıyıcı karşılaştırması gerekiyorsa operasyonel bağlam (hub yapısı, rota karışımı) ile normalize edilmeli; ya da taşıyıcı kodları anonim tutulup ana mesaj havalimanı ve rota düzeyine taşınmalı.
- Kuyruk numarası kişisel veri değildir ama uçak sahibi bireysel olabilir. Analizde kuyruk numarası yalnızca birleştirme anahtarı olarak kullanılmalı, yayımlanmamalı [V].

---

## 7. Varsayım envanteri (assumption-audit)

| # | Varsayım | Durum | Etki (yanlışsa) | Doğrulama yolu |
|---|---|---|---|---|
| A1 | BTS On-Time, T-100 ve DB1B ABD kamu malıdır, atıfla serbest kullanılır | Kısmen doğrulandı (data.gov etiketi) | Yüksek: proje paylaşımı | BTS "Web Policies and Notices" sayfası ve ilgili data.gov kayıtları tarayıcıda okunmalı |
| A2 | 1–3 yıllık On-Time verisi tek dizüstünde işlenebilir | Doğrulanmadı | Orta: kapsam daralır | Bir aylık dosya indirilip satır sayısı ve bellek ölçülmeli (kullanıcı çalıştırır) |
| A3 | Yerel saat → UTC dönüşümü güvenilir yapılabilir | Doğrulanmadı | Orta: hava birleştirmesi bozulur | OurAirports koordinatı + timezonefinder; örnek uçuşlarla kontrol |
| A4 | IEM istasyon kodları büyük ABD havalimanlarında IATA koduyla eşleşir | Doğrulanmadı | Düşük–orta | IEM istasyon listesinden hedef havalimanları kontrol edilmeli |
| A5 | Tail_Number ile FAA Registry yüksek oranda eşleşir | Doğrulanmadı | Düşük (opsiyonel özellik) | Örneklem eşleşme oranı ölçülmeli |
| A6 | EUROCONTROL ansperformance verisi atıfla yeniden kullanılabilir | Doğrulanmadı | Orta (yalnızca Avrupa seçilirse) | Disclaimer ve kullanım koşulları okunmalı; gerekirse EUROCONTROL'e sorulmalı |
| A7 | OR uzantısındaki maliyet parametreleri varsayım olarak kabul edilebilir | Varsayım | Orta: OR sonucunun yorumu | Parametreler literatürden ya da açık kaynaktan kaynakçalı seçilmeli ve duyarlılık analizi yapılmalı |
| A8 | Rötar nedeni alanları yalnızca 15 dakika ve üzeri rötarlarda dolar | Doğrulanmadı | Düşük (bunlar zaten sızıntı alanı) | BTS teknik direktifi ya da alan açıklaması okunmalı |
| A9 | DB1B ücretleri filtreleme gerektirir (düşük ve yüksek uç değerler) | Doğrulanmadı | Orta (ücret projesi seçilirse) | BTS DB1B belgeleri ve literatür okunmalı |

---

## 8. Kaynakça (bu oturumda okunan ya da arama özetinde görülen)

1. BTS TranStats – Reporting Carrier On-Time Performance alan listesi: https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ [D]
2. BTS – Airline On-Time Performance and Causes of Flight Delays: https://www.bts.gov/topics/airlines-and-airports/airline-time-performance-and-causes-flight-delays ve https://www.transtats.bts.gov/ONTIME/ [K]
3. BTS Technical Directive No. 27 (2018 eşik değişikliği): https://www.bts.gov/sites/bts.dot.gov/files/docs/explore-topics-and-geography/topics/airlines-and-airports/207741/technical-directive-no-27-time-2018.pdf [K]
4. BTS TranStats – Air Carrier Statistics (T-100) veritabanı bilgisi: https://www.transtats.bts.gov/DatabaseInfo.asp?QO_VQ=EEE [D]
5. BTS – International Traffic Data T-100 (gizlilik kuralı): https://www.bts.gov/topics/airlines-and-airports/number-213-international-traffic-data-t-100-traffic-system [K]
6. BTS TranStats – DB1B veritabanı bilgisi: https://www.transtats.bts.gov/DatabaseInfo.asp?QO_VQ=EFI [D]
7. DOT Domestic Airline Fares Consumer Report arşivi (ör.): https://rosap.ntl.bts.gov/view/dot/75809/dot_75809_DS1.pdf [K]
8. data.gov – Airline On-Time Performance kaydı (public domain etiketi): https://catalog.data.gov/dataset/airline-on-time-performance-and-causes-of-flight-delays-june-2014 ve https://catalog.data.gov/dataset/bts-flight-data [K]
9. OpenFlights Data: https://openflights.org/data.php [D]
10. OurAirports Data: https://ourairports.com/data/ [K: sertifika hatası, arama özeti]
11. Iowa Environmental Mesonet ASOS indirme: https://mesonet.agron.iastate.edu/request/download.phtml [D]; Disclaimer: https://mesonet.agron.iastate.edu/disclaimer.php [D]
12. NOAA NCEI LCD meta verisi: https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc:C00684/html [D]
13. NOAA GHCNh katalog kaydı: https://catalog.data.gov/dataset/global-historical-climatology-network-hourly-ghcnh-version-1 [K]
14. FAA Releasable Aircraft Database: https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download/ [K]
15. Eurostat Copyright notice: https://ec.europa.eu/eurostat/help/copyright-notice [D]; avia_pa meta verisi: https://ec.europa.eu/eurostat/cache/metadata/en/avia_pa_esms.htm [K]
16. EUROCONTROL ansperformance.eu açık veri: https://ansperformance.eu/data/ [D]
17. EUROCONTROL ADRR: https://www.eurocontrol.int/dashboard/aviation-data-research [D]; Kullanım koşulları PDF: https://www.eurocontrol.int/sites/default/files/2025-04/eurocontol-aviation-data-repository-research-terms-of-use.pdf [K: arama özeti]
18. OpenSky veri anlaşması (Zenodo kopyası): https://zenodo.org/records/6325961/files/LICENSE.txt?download=1 [K]; Zenodo 2020 CC BY: https://zenodo.org/record/3931948 [K]
19. Meteostat lisans sayfaları: https://dev.meteostat.net/license ve https://meteostat.net/en/legal [K]
20. Kaggle 2015 Flight Delays: https://www.kaggle.com/datasets/usdot/flight-delays [doğrulanmadı]
21. dilwong/FlightPrices: https://github.com/dilwong/FlightPrices [K]
