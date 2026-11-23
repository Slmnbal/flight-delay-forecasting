# OR – Blok süre tamponu optimizasyonu: formülasyon

- **Tarih:** 2026-11-22 · **Durum:** taslak, kod yazıldı, **hiçbir şey çalıştırılmadı** (bu belgede sonuç sayısı yok)
- **Dayanak:** `experiments/modelleme-plani.md` §1, §3.3, §5.4, §8, §9 · proje kararı: maliyetler varsayım + duyarlılık analizi · `decisions/M3-son-test-oncesi-kararlari.md` (C1: OR `plan` modeline bağlı; tek taşıyıcılı hücre kuralı) · `reports/red-team-modelleme-incelemesi.md` (M8, M10) · `experiments/son-test-dondurma.json` · `experiments/son-test/son-test-20261122T105048Z/son-test-ozet.md` · `experiments/arayuz-sozlesmesi.json`
- **Kod:** `deliverables/src/flight_delay/optimization/` (`newsvendor.py`, `allocation.py`, `policies.py`, `evaluation.py`, `run_buffer.py`) · **Testler:** `deliverables/tests/unit/optimization/`

---

## 0. Veri dönemi kuralı (önce bu)

1. Politikanın **serbest parametreleri yalnızca eğitim / Val-A / Val-B (2023-09 .. 2026-02) ile seçilir.** Bu çalışmada tek serbest seçim hücre toplayıcısıdır (§6); `policies.select_aggregator` son test tarihli (≥ 2026-03-01) tek bir satır görse durur (`FinalTestAccessError`, testle denetlenir).
2. **Son test dönemi (2026-03 .. 2026-08) bir kez açıldı ve sonuçları donduruldu** (`experiments/son-test-kilidi.json`). OR bu dönemi yalnızca **önceden sabitlenmiş politikaları değerlendirmek** için okur: önce `politika-dondurma.json` (ızgara, bütçeler, toplayıcı, yayım kuralı) özel oluşturma kipinde yazılır, sonra `splits.require_lock_written` + `LayerTableReader(allow_final_test=True)` ile test okunur. **Testte hiçbir şey ayarlanmaz.**
3. ML sonuçlarına, kilit ve dondurma dosyalarına dokunulmaz; yalnızca okunur (sha256 doğrulanır). Kilit kaydı bu dondurma dosyasını adlandırmıyorsa koşu reddedilir.

---

## 1. Karar (tek cümle)

Tarife planlayıcısı, aylar önce (o günün havası bilinmeden), her **rota × saat bloğu × mevsim** hücresi için tarifedeki blok süreye eklenecek **b ≥ 0 dakikalık ek tamponu** seçer.

---

## 2. Karar değişkenleri, parametreler, birimler

| Sembol | Anlam | Birim | Kaynak |
|---|---|---|---|
| b_c | c hücresinin ek blok süre tamponu (karar değişkeni) | dk, ≥ 0 | karar |
| D | Tamamlanan bir uçuşun varış rötarı (ArrDelay; erken = negatif) | dk | **tahmin** (dağılım) / gerçekleşen (değerlendirme) |
| q_α(x) | Kilitli `arr_delay/plan` modelinin α kantili, α ∈ {0,10; 0,50; 0,80; 0,90; 0,95} | dk | **tahmin** (run-20261121T080035Z) |
| c_m(τ) | Ay m için kayan tek yönlü conformal ofseti (τ düzeyinde) | dk | **tahmin** (kalibrasyon penceresi [m − 57 g, m − 2 g]) |
| n_c | Hücredeki tarifeli uçuş sayısı (iptaller dahil) | uçuş | tarife |
| c_u | Kalan varış rötarının dakika maliyeti | göreli | **VARSAYIM** |
| c_o | Kullanılmayan tampon dakikasının maliyeti (uçak / ekip verimliliği) | göreli | **VARSAYIM** |
| τ = c_u / (c_u + c_o) | Kritik oran | 0–1 | varsayımdan türetilir; ızgara ile taranır |
| B | Ağ geneli ek tampon bütçesi (kapasiteli sürüm) | uçuş·dk | **VARSAYIM** (ızgara) |

Maliyetler için kaynaklı bir sayı yok; **tek bir "doğru" değer verilmez.** Yalnızca oran önemlidir; raporlanan maliyetler c_u = τ, c_o = 1 − τ normalizasyonuyla "ağırlıklı dakika"dır, fiyat değildir.

---

## 3. Amaç: hücre başına newsvendor

Varsayım A1 ile tampon sonrası varış rötarı D − b'dir. Tamamlanan bir uçuşun maliyeti:

    maliyet(b, D) = c_u · (D − b)⁺  +  c_o · U(b, D),     U(b, D) = b − min(D⁺, b)

U, **planlanıp kullanılmayan tampon dakikasıdır** (rötar b'den küçükse artan kısım; erken varışın tampondan bağımsız kısmı sayılmaz). b ≥ 0 için U = b − D⁺ + (D − b)⁺ olduğundan

    maliyet = c_o · b + (c_u + c_o) · (D − b)⁺ − c_o · D⁺

ve son terim b'ye bağlı değildir. Türev: c_o − (c_u + c_o)(1 − F(b)) = 0 ⇒ **F(b\*) = c_u / (c_u + c_o) = τ**, kısıtla birlikte **b\* = max(0, Q(τ))**.

**Öneriden sapma (gerekçeli):** Görevdeki taslak maliyet "c_o · b + c_u · E[(D − b)⁺]" idi; bu ifadenin optimumu F(b) = 1 − c_o/c_u olur ve verilen b\* = F⁻¹(c_u/(c_u + c_o)) formülüyle tutarsızdır. "Planlanan ama kullanılmayan dakika" tanımını harfiyen U(b, D) olarak yazınca hem tanım hem formül tutar. Klasik newsvendor c_o·E[(b − D)⁺] + c_u·E[(D − b)⁺] ile aynı b\*'yi verir; iki tanımın farkı c_o·D⁻ (b'den bağımsız) olduğu için **politikalar arası maliyet farkları iki tanımda da aynıdır.**

Kısıt: **b ≥ 0** — kaynak: görev tanımı "ek tampon"; tarifeyi kısaltmak (negatif tampon) kapsam dışı. Q(τ) < 0 olan hücrelerde b\* = 0.

---

## 4. Dağılım: kantil ızgarası

- Kaynak: yalnızca kilitli **`plan`** modelleri (C1). T2 kantilleri yalnızca ikincil karşılaştırma (`--with-t2`), çünkü T − 2 saat havası tarife anında bilinmez.
- Beş kantil satır içinde **birlikte sıralanır** (yeniden düzenleme; kesişme oranı sıralama öncesi raporlanır). Not: `final_eval` 0,50/0,80/0,95'i ve 0,10/0,90'ı ayrı sıralıyordu; kesişme olmayan satırlarda sonuç aynıdır, conformal ofsetleri son test kaydıyla karşılaştırılır (bilgi amaçlı, kapı değil).
- **Ara düzeyler (A5):** Q, iki komşu düğüm arasında **düzeyde doğrusal** ara değerlenir (ör. τ = 0,85 → q080 ile q090'ın ortası). Bu bir yaklaşımdır; gerçek dağılım düğümler arasında doğrusal olmak zorunda değildir.
- **Izgara dışı:** τ < 0,10 ya da τ > 0,95 **reddedilir** (`GridError`). Kuyruk uydurulmaz. F'nin düğümler dışındaki değeri gerektiğinde **sansürlü sınır** olarak bayraklanır (alt: F ≤ 0,10; üst: F ≥ 0,95) ve sayısı raporlanır.
- **İptal / sapma (§3.3):** Koşulsuz kantil F⁻¹(α/(1 − p_k)) **kullanılmaz.** Gerekçe: iptal edilen ya da sapan uçuşa tampon fayda sağlamaz ve maliyet tanımında yer almaz; koşulsuz kantil iptali "sonsuz rötar" sayarak tamponu, tamponun etkileyemediği bir olay için şişirir. Bu yüzden amaç tamamlanan uçuşlara koşulludur. `cancelled/plan` modelinin (Val-B'de dondurulmuş Platt ile) ortalama iptal olasılığı hücre dosyasına **bilgi olarak** yazılır (K6 geçmedi; politikaya girmez). İptal/sapma sayıları her dönemde raporlanır.

---

## 5. Kapasiteli sürüm (ağ bütçesi)

Bütçe uçuş·dakika cinsindendir: Σ_c n_c · b_c ≤ B (her uçuşun blok süresi uçak/ekip dakikası tüketir). Bütçe ızgarası **uçuş başı ortalama ek dakika** β ile verilir: B = β · (dönemdeki tarifeli uçuş sayısı); varsayılan β ∈ {1; 2; 3; 5; 7,5; 10; 15} (VARSAYIM).

**5.1 Beklenen rötar dakikası** (`allocation.common_level_allocation`)

    min Σ_c n_c · E[(D_c − b_c)⁺]   s.t.   Σ_c n_c · b_c ≤ B,   b_c ≥ 0

Amaç ayrılabilir ve dışbükeydir (d/db E[(D − b)⁺] = −(1 − F(b))). KKT: b_c > 0 olan her hücrede 1 − F_c(b_c) = λ ⇒ **b_c = max(0, Q_c(1 − λ))**: optimumda bütün hücreler **aynı kantil düzeyini** τ = 1 − λ kullanır; τ, bütçe tam kullanılacak şekilde ikiye bölmeyle bulunur (bütçe τ'nun monoton ve sürekli fonksiyonudur). Sonuç: **B dakika bütçe ⇔ c_u/c_o = τ/(1 − τ) varsayımı** (bütçenin gölge fiyatı). Çözüm kuyruk gerektirmez. Durumlar: `binding`; `grid_top` (bütçe τ = 0,95'in gerektirdiğinden büyük: ızgara içinde bağlayıcı değil, ötesi uydurulmaz); `below_grid` (optimum τ < 0,10: hesaplanmaz).

Öneriden sapma: LP yerine kapalı biçim. Ara değerlenmiş F parça parça doğrusal olduğundan E[(D − b)⁺] parça parça ikinci derecedendir; LP gerekmez ve KKT çözümü kesindir. scipy'ye ihtiyaç yok.

**5.2 Beklenen ArrDel15 sayısı** (`allocation.arrdel15_allocation`)

    min Σ_c n_c · P(D_c − b_c ≥ 15)   s.t.   aynı bütçe

1 − F(15 + b), b'de parça parça doğrusaldır ama dışbükey değildir → **çok seçimli sırt çantası** (MCKP). Adaylar: b = 0 ve düğümlerde b = max(0, q_k − 15) (kırılma noktaları). `mckp_greedy`: her hücrenin alt dışbükey zarfı üzerinde LP gevşetmesini kesin çözer ve uygulanabilir bir tamsayı çözüm verir (kesirli artış atılır, o hücre dondurulur, diğer hücrelerin sığan artışları alınmaya devam eder); **LP alt sınırı ile açık raporlanır** (açık, tamsayı optimumuna uzaklığın üst sınırıdır). `mckp_milp` (scipy `milp`/HiGHS; scipy 1.18.1 kilit dosyasında var, `pyproject.toml`'da doğrudan beyanlı değil, scikit-learn bağımlılığıyla geliyor) yalnızca küçük örneklerde kesin çapraz kontrol (testler). b = 0'da F(15) düğüm dışındaysa sansürlü sayılır ve sayısı raporlanır.

**Kısıt ihlali:** her bütçe çözümünde planlanan toplam dakika ≤ B testle ve çıktıda denetlenir.

---

## 6. Hücre tanımı ve hücre dağılımı

- Hücre = (Origin, Dest) × `saat_blogu` (CRS kalkış yerel saati, 7 blok) × mevsim (Ara–Şub kış, Mar–May ilkbahar, Haz–Ağu yaz, Eyl–Kas sonbahar) — plan §8; sabit.
- Hücre tamponu, hücredeki **tarifeli** uçuşların (iptaller dahil; tarife önceden bilinir) model kantillerinden hesaplanır; gerçekleşen rötar kullanılmaz (`policy_buffers` imzası sonuç almaz, testle denetlenir).
- **Toplayıcı (A6):** uçuş düğümleri düzey düzey toplanır: `mean` (kantil ortalaması / Vincentizasyon, varsayılan) ya da `median`. İkisi de artan düğüm verir. Bu, hücrenin karışım dağılımının kantili **değildir** (karışım için 0,95 ötesi kuyruk gerekir). **Seçim yalnızca geliştirme döneminde** (2025-11 .. 2026-02, plan politikasının τ ızgarası ortalaması gerçekleşen maliyeti en düşük olan; eşitlikte `mean`).
- Geliştirme değerlendirme ayları 2025-11 .. 2026-02'dir: Eylül–Ekim 2025'in kayan conformal pencereleri eğitim penceresine (modelin gördüğü veriye) düşer, bu yüzden dışarıda.

---

## 7. Politikalar (karşılaştırmalar)

| # | Politika | Tampon |
|---|---|---|
| (i) | `none` – mevcut tarife | b = 0 |
| (ii) | `b1` – B1 baseline ampirik hücre kantili (rota × saat bloğu, eğitim penceresi, n·(1 − α) ≥ 20 geri çekilmesi) | max(0, Q^B1(τ)) |
| (iii) | `plan` – kilitli plan modeli (ham) | max(0, Q_c(τ)) |
| (iv) | `plan_conformal` – plan + aylık kayan conformal | max(0, Q_c(τ) + c_m(τ)); hücre × ay |
| (v) | `b1_conformal` – adillik kontrolü: B1'e aynı conformal adımı | max(0, Q^B1(τ) + c^B1_m(τ)) |
| (vi) | `plan_flight` – uçuş düzeyi (ikincil) | max(0, Q_i(τ)) |
| (vii) | `t2` – T2 kantilleri (ikincil, `--with-t2`; bilgi zamanı tarifeye uymaz) | max(0, Q^T2_c(τ)) |

- Conformal: `final_eval` ile aynı pencere ve aynı fonksiyon (`final_eval.conformal_offsets`, `splits.conformal_calibration_window`); her τ için skor y − Q_i(τ) ile yeniden hesaplanır. Bilgi zamanı notu: kayan pencere m − 2. güne kadar etiket ister; aylar önce tarife yapan biri için bu bilgi yoktur. (iv) bu yüzden "operatör senaryosu"dur.
- Eşit bütçe karşılaştırması (adil baseline): her β için B1 ve plan aynı planlanan dakikayla (§5.1) ve plan ArrDel15 sırt çantasıyla (§5.2) karşılaştırılır.

---

## 8. Değerlendirme (örneklem dışı, gerçekleşen rötarla)

- Dönemler: geliştirme (2025-11 .. 2026-02) ve son test (2026-03 .. 2026-08). Ek tampon dakikası tüm tarifeli uçuşlar üzerinden toplanır; gerçekleşen nicelikler yalnızca tamamlanan uçuşlarda (ArrDelay var). İptal/sapma uçuşları maliyette yok (NaN); sayıları raporlanır.
- Metrikler (politika × τ): uçuş başı ve toplam maliyet, kalan rötar dk (uçuş başı / toplam), kullanılmayan tampon dk, tampon sonrası ArrDel15 oranı (D − b ≥ 15), tam emilen pay P(D ≤ b) (τ ile karşılaştırılır: kalibrasyon göstergesi), eklenen toplam tampon dk; aylık kırılım.
- Belirsizlik: **takvim günü blok bootstrap** (`modeling/bootstrap.py`: `day_multiplicities`, `DayMeans`, `summarize_draws`), B = 1000, tohum 42, %95 yüzdelik GA; eşleştirilmiş farklar (politika − referans) aynı yeniden örneklemlerde. Karşılaştırma çiftleri: (ii),(iii),(iv) − (i); (iii),(iv) − (ii); (iv) − (v); (iv) − (iii); (vi) − (iii); (vii) − (iii).
- Bunlar keşifsel karşılaştırmalardır; çoklu karşılaştırma düzeltmesi yapılmaz (önceden kayıtlı kabul ölçütü yok). Yorum GA'lı Δ ile yapılır.
- Kazanç küçük ve τ'ya duyarlıysa bu açıkça yazılır (Yükseltme kuralı).

---

## 9. Duyarlılık ızgarası

- **Kritik oran τ:** 0,50; 0,55; …; 0,95 (10 düzey) ⇔ c_u/c_o = 1; 1,22; 1,5; 1,86; 2,33; 3; 4; 5,67; 9; 19. τ > 0,95 ızgara dışıdır (§4).
- **Bütçe:** β ∈ {1; 2; 3; 5; 7,5; 10; 15} dk/uçuş.
- **Toplayıcı:** mean / median (yalnızca geliştirmede).
- **Conformal:** ham vs kayan (iv) ve B1 için aynı adım (v).
- Mevsim: aylık kırılım (ilkbahar / yaz farkı K5 nedeniyle önemli).

---

## 10. Varsayımlar (numaralı)

- **A1 (plan §8 b):** 1 dk ek tampon = 1 dk daha az varış rötarı; uçuşun kendisi (kalkış, uçuş, taksi) değişmez.
- **A2 (M8):** Model duyarlılığı nedensel kullanılmaz. `schedule_excess_min` / `CRSElapsedTime` modelin girdisidir; tampon ekleyip modeli yeniden tahmin ettirmek **yasak**. Tahminler sabit, tampon yalnızca dağılımı kaydırır.
- **A3:** Maliyet oranı c_u/c_o bilinmiyor; ızgarayla taranır. Mutlak ölçek yok.
- **A4:** Bütçe uçuş·dakika cinsinden doğrusal (her dakikanın maliyeti aynı); uçak rotasyonu, ekip görev süresi, kapı/slot kısıtları **modellenmedi** (kaynağı olmayan kısıt eklenmez; bkz. §11).
- **A5:** Düğümler arası doğrusal kantil ara değerlemesi; ızgara dışı yok.
- **A6:** Hücre dağılımı = uçuş kantillerinin düzey düzey ortalaması (ya da medyanı); karışım kantili değil.
- **A7:** Kantiller tamamlanan uçuşa koşulludur; iptal/sapma maliyet dışı.
- **A8:** Tarifeli uçuşlar ve plan modeli girdileri tampon planlama anında biliniyor (plan sözleşmesi: tarife + takvim + eğitim penceresi istatistikleri).
- **A9:** Tampon, aynı uçağın sonraki bacaklarına yayılan (zincirleme) rötarı ayrıca azaltmaz/artırmaz kabul edilir (etki yok sayılır; büyük olasılıkla kazancı eksik gösterir, doğrulanmadı).
- **A10:** b ≥ 0 (tarife kısaltılmaz).
- **A11:** ArrDel15 = (ArrDelay − b ≥ 15), BTS tanımıyla.
- **A12:** Kayan conformal ofseti ay içinde sabittir (hücre × ay tamponu).

---

## 11. Kısıtlar ve operasyonel kaynakları

| Kısıt | Kaynak |
|---|---|
| b_c ≥ 0 | Görev tanımı ("ek tampon") |
| Σ n_c b_c ≤ B | Kullanıcı/CEO parametresi (bütçe ızgarası; varsayım) |
| Hücre başına tek b (mevsim boyunca; (iv)'de ay başına) | Plan §8 hücre tanımı |
| τ ∈ [0,10; 0,95] | Kilitli kantil ızgarası (son-test-dondurma) |

Rotasyon, ekip, slot ve kapı kısıtları için Araştırmacı kaynağı yok; modele **eklenmedi** (sınırlılık).

---

## 12. Sunum kuralları ve çıktılar

- Taşıyıcı boyutu yok (çıktı, tablo, sıralama); kuyruk ve uçuş numarası yok. Çıktı tablolarında taşıyıcı / kuyruk / uçuş no sütunu bulunursa kod durur (`assert_no_forbidden_columns`, testli). Taşıyıcı yalnızca `cell_table` içinde **M10 bayrağı** için kullanılır: bir taşıyıcının payı > %90 olan hücre `tek_tasiyici_yogun = true`; kimlik dışarı çıkmaz.
- `tampon_onerisi_dk` (arayüz sözleşmesi, rotalar dosyası): **n ≥ 50 tarifeli uçuş ve M10 bayrağı yok** ise yayım politikasının yayım τ'sundaki hücre tamponu (1 ondalık), değilse **null**. Varsayılan yayım: `plan` (iii) @ τ = 0,80 (bkz. Kullanıcıya sorular).
- Çıktı yolları (yeni klasör, üzerine yazma yok):
  - `experiments/or/tampon-<UTC>/politika-dondurma.json` (test okunmadan önce), `tampon-sonuclari.json`, `tampon-ozet.md` (Türkçe).
  - `deliverables/data/or/tampon-<UTC>/hucre-tamponlari.parquet` (hücre; arayüz kaynağı) ve `ucus-tamponlari.parquet` (uçuş düzeyi; **yalnızca git bu klasörü yok sayıyorsa** yazılır, `git check-ignore` ile denetlenir; yazılmazsa sonuçta not edilir).

---

## 13. Sınırlılıklar

1. **Yaz conformal kapsaması (K5 geçmedi):** son testte P80 kayan conformal kapsama Haziran 0,755, Temmuz 0,756 (hedef 0,80); yaz aylarında (iv)'nin tamponları hedeflenen düzeyin altında koruma sağlayabilir. "Tam emilen pay"ın τ ile aylık karşılaştırması bunu görünür kılar; düzeltme testte yapılmaz.
2. **Kantil ara değerlemesi (A5)** ve **ızgara dışı reddi:** c_u/c_o > 19 (τ > 0,95) incelenemez; kuyruk riski (P95 ötesi) bu modelin dışında.
3. **Nedensellik (A1, A2):** blok süre artışının uçuş davranışını değiştirmediği (ör. ekiplerin yavaşlamaması, slotların değişmemesi) varsayılır; doğrulanmadı.
4. **Toplayıcı (A6):** hücre içi heterojenlik büyükse Vincentize edilmiş dağılım karışım dağılımından sapar; (vi) uçuş düzeyi politikası bu farkın ölçüsünü verir.
5. **Koşulluluk (A7):** kötü günlerde iptaller yoğunlaşır; koşullu dağılım kötü günlerin kuyruğunu eksik temsil eder.
6. **Bilgi zamanı:** (iv) yakın tarihli etiket ister (operatör senaryosu); (iii) tarife anı bilgisine uygundur.
7. **Zincirleme rötar (A9) ve kaynak kısıtları (A4)** yok.
8. **İstatistik:** bootstrap gün içi bağımlılığı ele alır, ama 184 günle ay ve mevsim kırılımları geniş GA'lı olabilir; aylık tablolar keşifseldir.

---

## 14. Elle doğrulama örnekleri (testlerde)

- Düğümler (0, 10, 20, 30, 40) dk @ (0,10; 0,50; 0,80; 0,90; 0,95): τ = 0,85 → b\* = 25; τ = 0,60 → 13,33; τ = 0,96 → reddedilir.
- D ~ U[0, 100] (düğümler kesin): gerçekleşen maliyetin kaba kuvvet argmin'i τ·100'e eşit (τ = 0,6/0,8/0,9).
- İki hücre U[0,100] ve U[0,50], n = (1, 1), B = 120 → ortak düzey τ = 0,80, b = (80, 40); kaba kuvvet aynı optimumu verir; ima edilen c_u/c_o = 4.
- MCKP: maliyetler (0, 10, 20) / (0, 5, 30), değerler (1; 0,5; 0,4) / (1; 0,6; 0,1); B = 35 → tamsayı 1,0 (b = 20 ve 5), LP sınırı 0,7; küçük rastgele örneklerde scipy MILP ile çapraz kontrol.
- D = (−5, 10, 30, 40), b = 20: kalan (0, 0, 10, 20), kullanılmayan (20, 10, 0, 0), ArrDel15 (0, 0, 0, 1); τ = 0,8 maliyet (4, 2, 8, 16).

---

## 15. Çalıştırma (depo kökünden)

1. Testler: `python -m pytest deliverables/tests/unit/optimization -q` (ardından tüm paket: `python -m pytest deliverables/tests/unit`), `ruff check deliverables/src/flight_delay/optimization deliverables/tests/unit/optimization`, `ruff format --check …`, `mypy` (`deliverables/` içinde).
2. Ön kontrol (veri okumaz, dosya yazmaz): `python -m flight_delay.optimization.run_buffer --dry-run`
3. Tam koşu: `python -m flight_delay.optimization.run_buffer` (isteğe bağlı: `--with-t2`, `--publish-level 0.80`, `--publish-policy plan|plan_conformal`, `--levels …`, `--budgets …`). Yalnızca geliştirme: `--development-only`.

**Tahmini süre / bellek (ölçülmedi, kaba):** son test koşusu 7 rolü (T2 hava matrisleri dahil) 2,3 M test satırında 1331 sn'de tahmin etti, tepe 6,0 GB. Bu koşu yalnızca plan sözleşmeli 6 model ile ~2,4 M geliştirme + ~2,3 M test satırını tahmin eder; Val-B yeniden üretim kontrolleri, ~10 τ × 7 politika değerlendirmesi, 2 × 7 bütçe çözümü ve B = 1000 bootstrap (gün düzeyinde, ucuz) eklenir. Beklenti **20–45 dk, 6–9 GB tepe bellek**; `--with-t2` ile daha uzun. İlerleme stderr'e loglanır (adım süreleri, tepe RSS).

---

## 16. Öneriden sapmalar (özet)

1. Maliyet tanımı U(b, D) = b − min(D⁺, b) (§3): verilen b\* formülüyle tutarlı olsun diye.
2. Kapasiteli sürüm LP yerine KKT kapalı biçim (ortak kantil düzeyi) + ArrDel15 için MCKP (§5).
3. Bütçe uçuş·dakika (n_c ağırlıklı) (§5).
4. Hücre dağılımı Vincentizasyon (karışım kantili değil) (§6).
5. Geliştirme değerlendirmesi 2025-11 .. 2026-02 (Eylül–Ekim conformal pencereleri eğitime düşüyor) (§6).
6. Adillik için (v) B1 + conformal ve eşit bütçe karşılaştırması eklendi (§7).
7. Koşulsuz kantil kullanılmadı (§4).
8. Yayım varsayılanı (iii) ham plan @ τ = 0,80 (tarife anı bilgisine uygun) — kullanıcı onayladı (2026-11-22).

---

## 17. Çözücü uzantısı (Pyomo + HiGHS; 2026-11-22 eki)

- **Durum:** kod ve testler yazıldı, **hiçbir şey çalıştırılmadı**; bu bölümde sonuç sayısı yok. Dayanak: `experiments/or/sirt-cantasi-incelemesi.md` (sırt çantası B1'den kötü; neden Vincentize hücre dağılımının karışımdan dar olması + optimizasyoncunun laneti).
- **Kod:** `piecewise.py` (parçalı doğrusal girdiler, numpy), `pyomo_models.py` (LP ve MILP; Pyomo/highspy fonksiyon içinde içe aktarılır, isteğe bağlı), `mixture.py` (karışım hücre dağılımı), `plots.py` (matplotlib, PNG), `run_solver.py` (ayrı CLI). `run_buffer.py`'de yalnızca uçuş düzeyi dosyası için git-ignore denetimi düzeltildi (§17.7). Testler: `test_piecewise.py`, `test_pyomo_models.py`, `test_mixture.py`, `test_plots.py`, `test_run_solver.py`, `test_flight_file_ignore.py`.
- **Bağımlılık:** pyomo==6.11.0 ve highspy==1.16.0 kurulu; `pyproject.toml`'da `optimization = ["pyomo", "highspy", "matplotlib"]` ekstrası. scipy (`allocation.mckp_milp`) yalnızca küçük örneklerde çapraz kontrol olarak kalır.

### 17.1 Dakika bütçesi: LP (Pyomo `MinutesLP`)

Problem (§5.1 ile aynı): min Σ_c n_c E[(D_c − b_c)⁺] s.t. Σ_c n_c b_c ≤ B, L_c ≤ b_c ≤ U_c.

- **Alan:** L_c = max(0, q_c,10), U_c = max(0, q_c,95) — kapalı biçimin τ ∈ [0,10; 0,95] alanıyla aynı. Izgara dışı yok.
- **Amaç, ızgara içinde kesin:** E[(D − b)⁺] = T_c + S_c(b), S_c(b) = ∫_b^{q_95} (1 − F_c(x)) dx (`piecewise.grid_shortfall`). T_c = E[(D − q_95)⁺] tanımlanmamış kuyruk sabitidir, b'ye bağlı değildir; bütün karşılaştırmalar Σ n_c S_c(b_c) ile yapılır.
- **Not (görev metnine düzeltme):** A5 altında F düğümler arasında doğrusal olduğundan E[(D − b)⁺] düğümler arasında **ikinci derecedendir**, parçalı doğrusal değil. LP bu yüzden S_c'nin **kiriş ara değerlemesini** çözer: [L_c, U_c] düğümlerde ve her düğüm aralığı içinde en çok `max_segment_min` (varsayılan 2 dk) uzunluğunda eşit parçalara bölünür. Bir parçada kiriş eğimi tam olarak −(1 − F(orta nokta))'dır; kirişin S'nin üstünde kalma payı en çok ℓ·ΔF/8'dir (ℓ parça uzunluğu, ΔF parçadaki F artışı).
- **Pyomo bileşenleri (adlar sembollerle aynı):** kümeler `C` (hücre), `K` = {(c, k)} (parça); parametreler `n[c]`, `L[c]`, `U[c]`, `S0[c]` = S_c(L_c), `ell[c,k]`, `a[c,k]` (kiriş eğimi, < 0, k'da artan), `B` (değiştirilebilir); değişkenler `b[c]` ∈ [L, U], `y[c,k]` ∈ [0, ell]; kısıtlar `link[c]`: b = L + Σ_k y, `budget`: Σ n b ≤ B; amaç `expected_delay` = Σ n (S0 + Σ_k a·y). S_c dışbükey olduğundan eğimler artar ve LP parçaları sırayla doldurur (tamsayı değişken gerekmez).
- **Epigraf biçimi** (`--lp-formulation epigraph`, aynı optimum): `t[c]` ≥ S_c(U_c), `epi[c,k]`: t ≥ S_c(p) + a·(b − p); amaç Σ n t. Testlerde iki biçimin amacı eşit (rel 1e-6).
- **Boyut:** değişken = C + P (parça sayısı P ≈ Σ_c ⌈(U_c − L_c)/2⌉ + ≤ 4C), kısıt = C + 1 (segment biçimi); epigraf: 2C değişken, P + 1 kısıt. Hücre ~24–25 bin. Ortalama U_c bilinmiyor (ölçülmedi); **varsayım** ortalama U − L ≈ 80 dk ise P ≈ 1,1 M. Model dönem başına bir kez kurulur, her bütçede yalnızca `B` değiştirilip yeniden çözülür (appsi kalıcı arayüzü).
- **Zaman sınırı:** `--lp-time-limit` (varsayılan 600 sn / çözüm).

**Çapraz doğrulama (`pyomo_models.compare_minutes`), her bütçe için, kapalı biçim `common_level_allocation` ile:**
1. **Amaç sertifikası:** S\*(CF) − (B − kullanılan_CF) ≤ LP amacı ≤ S\*(CF) + Σ_c n_c · maks_k(ℓ·ΔF/8). (Alt sınır: LP amacı, LP çözümündeki kesin S'nin üstünde, o da kesin optimumun üstündedir; ikiye bölmenin kullanmadığı küçük bütçe payı düşülür. Üst sınır: CF noktası LP'de olurludur ve kiriş hatası sınırlıdır.)
2. **Tamponlar:** |b_LP − b_CF| ≤ 2 × hücrenin en uzun parçası (raporda en büyük, ortalama, %99 fark ve tolerans içi pay).
3. **Kısıt ihlali:** bütçe, alt/üst sınır ve negatif tampon sayısı 0 olmalı.
4. **Gölge fiyat:** bütçe satırının duali −(1 − τ); LP'nin ima ettiği τ kapalı biçim τ'suyla raporlanır (bilgi).
5. Durumlar aynı olmalı: `below_grid` (Σ n L > B: çözülmez), `grid_top`, `binding`, `zero`.
`agrees = false` olursa koşu durmaz, uyarı loglanır ve özet tablosunda görünür; politikalar her durumda kapalı biçimle değerlendirilir (LP yalnızca doğrulamadır).

### 17.2 ArrDel15 sırt çantası: MILP (Pyomo `solve_arrdel15_milp`)

- **Kümeler:** `C` (modeldeki hücreler), `J` = {(c, j)} (baskın olmayan adaylar). **Parametreler:** `n[c]`, `beta[c,j]` (aday tampon, dk), `pi[c,j]` = P(D_c − beta ≥ 15), `B`, `used_fixed` / `late_fixed` (model dışında sabitlenen hücrelerin dakikası ve beklenen geç uçuşu). **Değişken:** `x[c,j]` ∈ {0, 1}. **Kısıtlar:** `one_choice[c]`: Σ_j x = 1; `budget`: used_fixed + Σ n·beta·x ≤ B. **Amaç:** `expected_late` = late_fixed + Σ n·pi·x.
- **Ön indirgeme (optimumu değiştirmez):** aynı hücrede daha ucuz-ya-da-eşit ve daha az-ya-da-eşit geç seçeneği olan aday atılır (`piecewise.undominated_options`); tek adayı kalan hücre sabitlenir.
- **Boyut:** Vincentize: ≤ 6 aday/hücre → ≤ ~150 bin ikili; karışım: ≤ 19 aday/hücre → ≤ ~470 bin ikili (indirgemeden önce; indirgeme sonrası sayı raporlanır). Kısıt: model hücresi + 1.
- **Boyut sınırlama seçeneği:** `--milp-min-n N` (varsayılan 0 = bütün hücreler): n < N olan hücreler açgözlü çözümün seçiminde sabitlenir, bütçeden düşülür; sabitlenen hücre sayısı sonuçta yazılır. Bu durumda MILP yalnızca kısıtlı problemin optimumudur.
- **Çözücü ayarları:** `--milp-time-limit` (varsayılan 120 sn / çözüm), `--milp-gap` (HiGHS `mip_rel_gap`, varsayılan 1e-6). Rapor: sonlanma durumu, en iyi olurlu amaç, en iyi sınır, MIP gap, açgözlü değer, açgözlünün LP alt sınırı, MILP − açgözlü, farklı tampon seçilen hücre sayısı, kısıt ihlalleri (tek seçim, bütçe).
- **Değerlendirme:** politikalar açgözlü çözümle değerlendirilir (ilk koşuyla aynı; zaman sınırına bağlı değil). MILP farklı ve geçerli bir çözüm bulursa `<politika>_milp` olarak ayrıca gerçekleşen sonuçlarla puanlanır.
- **Testler:** elle örnek (§14'teki MCKP: B = 35 → 1,0), rastgele küçük örneklerde scipy `mckp_milp` ile aynı değer ve LP alt sınırı ≤ MILP ≤ açgözlü; uçuş ağırlıkları ve sabitleme.

### 17.3 Karışım hücre dağılımı (keşifsel)

- F_c^mix(x) = (1/n_c) Σ_{i∈c} F_i(x); her F_i aynı A5 ara değerlemesiyle. **Kuyruk uydurulmaz:** x bir uçuşun ilk düğümünün altındaysa F_i ≤ 0,10, son düğümünün üstündeyse F_i ≥ 0,95 bilinir; sınır değer kullanılır ve **sansürlü uçuş payı** her değerle birlikte döner (`mixture.mixture_cdf`).
- Kantil: F_c^mix üzerinde ikiye bölme (50 adım), aralık [min q_i,10, maks q_i,95].
- **Sırt çantası adayları:** b = 0 ve b = max(0, Q_c^mix(α) − 15), α ∈ {0,10; 0,15; …; 0,95} (18 düzey). Karışımın gerçek kırılma noktaları hücredeki bütün uçuşların bütün düğümleridir (çok fazla); aday kümesi bu ızgarayla **sınırlandı** (yaklaşım; ızgara dondurma dosyasına yazılır). Vincentize adayları ilk koşuyla aynıdır (düğümler; F orada kesin).
- Beklenen ArrDel15 = seçilen adayın model geç payının **tamamlanan uçuşlar** üzerindeki ortalaması (gerçekleşen oranla aynı satırlar). Not: incelemedeki tablo (× tarifeli / tamamlanan ölçeklemesi) farklı bir ölçeklemedir; ikisi birebir karşılaştırılmamalı.

### 17.4 Seçim kuralı ve keşifsel etiket

- **Hücre dağılımı yalnızca geliştirme döneminde (2025-11 .. 2026-02) seçilir** (`run_solver.select_cell_distribution`; son test tarihli bir gün görürse `FinalTestAccessError`). Sözlük sırası kural: (1) bütçe ızgarası üzerinden ortalama gerçekleşen ArrDel15 farkı > 0,0001 ise düşük olan; (2) değilse ortalama |gerçekleşen − beklenen| düşük olan; (3) değilse Vincentize (mevcut). Seçim ve kural `cozucu-dondurma.json`'a test okunmadan **önce**, özel oluşturma kipinde yazılır.
- Toplayıcı yeniden seçilir ve ilk koşunun dondurulmuş toplayıcısıyla (`mean`) aynı olmazsa koşu durur.
- **Etiket kuralı:** son test dönemi bu politikalar için ilk koşuda zaten görüldü. Bu koşunun bütün çıktıları **"keşifsel (post hoc), son test sonucu değildir"** etiketini taşır: özetin **ilk satırı**, JSON'un ilk anahtarı (`etiket`, ayrıca `exploratory_post_hoc: true`), dondurma dosyası ve test dönemi grafiklerinin dipnotu. Bu koşunun test sayıları ilk koşunun son test sonuçlarının yerine geçmez ve README/model kartında "son test" olarak yazılmaz.
- **Yeniden üretim kontrolü:** her dönemde ilk koşuyla ortak politika metrikleri (τ ızgarası ve ilk koşunun bütçe eğrisi) karşılaştırılır, en büyük mutlak fark raporlanır (bilgi; kapı değil). İlk koşunun dosyaları yalnızca okunur, sha256'ları kaydedilir.

### 17.5 Tahmini süre ve bellek (ölçülmedi, kaba)

| Adım | Tahmin | Dayanak |
|---|---|---|
| Model/tahmin/değerlendirme (ilk koşuyla aynı yol) | ~4–6 dk, tepe ~5,2 GB | ilk koşu 236,7 sn, 5,199 GB |
| Karışım adayları (18 düzey × 50 ikiye bölme, ~1,4 M satır) | dönem başına 1–3 dk | varsayım |
| LP kurulumu (P ≈ 1 M parça, Pyomo) | dönem başına 1–3 dk, +1,5–3 GB | varsayım (Pyomo ~1–2 KB/değişken) |
| LP çözümü (tek bağlayan satır) | bütçe başına saniyeler–birkaç dk | varsayım; sınır 600 sn |
| MILP (7 bütçe × 2 dağılım × 2 dönem = 28 çözüm) | tipik birkaç dk; en kötü 28 × 120 sn ≈ 56 dk | zaman sınırı |

Toplam beklenti **15–40 dk, en kötü ~80 dk; tepe bellek 7–9 GB**. Bellek dar ise: `--lp-max-segment 4` (P yarıya iner, kiriş hata sınırı büyür), `--no-lp`, `--milp-min-n 50`. İlerleme logu stderr'e (adım süreleri, tepe RSS; LP kurulum sonrası RSS JSON'da).

### 17.6 Grafikler (`experiments/or/cozucu-<UTC>/grafikler/`)

(a) `butce-egrisi-<dönem>.png`: dk/uçuş bütçesine karşı ArrDel15 ve kalan rötar (plan ortak düzey, B1 ortak düzey, sırt çantası Vincentize ve karışım; %95 gün blok bootstrap GA bantları). (b) `tau-duyarliligi-<dönem>.png`: τ'ya karşı maliyet, eklenen tampon, ArrDel15. (c) `sirt-cantasi-beklenen-gerceklesen-<dönem>.png`: beklenen (kesikli) ve gerçekleşen (düz, GA bandı). Taşıyıcı ve logo yok; eksenler Türkçe; Okabe-Ito renk körü dostu palet + farklı işaretçiler; dosya varsa üzerine yazılmaz.

### 17.7 Uçuş düzeyi dosyası düzeltmesi

İlk koşu logu: "flight-level file not written (git ignored: False…)". Neden: `git check-ignore` klasör yolu ile çağrıldı; kural `*.parquet` bir dosya kalıbıdır, klasör eşleşmez. Düzeltme: `run_buffer.flight_file_git_ignored(data_folder)` denetimi **dosya yolunun kendisiyle** yapar (`…/ucus-tamponlari.parquet`). Sonuç JSON'unda `flight_file_git_ignored` eklendi; `data_folder_git_ignored` bilgi olarak kalır. Bu, `run_buffer`'ın bir sonraki tam koşusunda uçuş düzeyi Parquet'in (yalnızca yerel, git dışı) yazılmasını sağlar; diğer davranış aynıdır. `run_solver` Parquet yazmaz.

### 17.8 Komutlar (depo kökünden)

1. `python -m pytest deliverables/tests/unit/optimization -q`, sonra `python -m pytest deliverables/tests/unit`; `ruff check` / `ruff format --check` (optimization kaynak ve testleri); `mypy` (`deliverables/` içinde).
2. `python -m flight_delay.optimization.run_solver --dry-run` (veri okumaz, yazmaz).
3. İsteğe bağlı duman: `python -m flight_delay.optimization.run_solver --development-only --budgets 1 5 --replicates 50` (yeni klasör yazar; test okunmaz).
4. Tam koşu: `python -m flight_delay.optimization.run_solver` (seçenekler: `--solver highs`, `--lp-formulation segments|epigraph`, `--lp-max-segment`, `--lp-time-limit`, `--milp-time-limit`, `--milp-gap`, `--milp-min-n`, `--no-lp`, `--no-milp`, `--no-mixture-cells`, `--no-plots`).

### 17.9 Sınırlılıklar ve riskler

1. Pyomo `appsi_highs` eski arayüzünün `solve(timelimit=…, options=…, load_solutions=True)` imzası ve sonuç alanları (`results.problem.upper_bound/lower_bound`, dual soneki) kod okunarak değil bilgiyle kullanıldı; testlerle doğrulanacak (`test_pyomo_models.py`). Uyuşmazlıkta hata `_solve` içinde tek yerde düzeltilir.
2. LP büyük boyutta Pyomo kurulumu belleği artırır; tahmin ölçülmedi.
3. Karışımda kuyruk uydurulmadığı için sansürlü uçuş payı yüksek hücrelerde F_mix bir sınırdır; pay raporlanır.
4. Karışım adayları 18 düzeyle sınırlı (kırılma noktalarının tamamı değil).
5. Test dönemi sonuçları keşifseldir; dağılım seçimi geliştirmede yapılsa da test bu politika ailesi için daha önce görüldü.
