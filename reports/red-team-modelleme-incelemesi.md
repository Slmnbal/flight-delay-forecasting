# Red Team incelemesi – modelleme (son test açılmadan önce), 2026-11-21

Bağımsız eleştirel inceleme (red team). İnceleme sırasında kod çalıştırılmadı; sayılar dosyalardan, "(türetilmiş)" olanlar inceleyenin hesabı. C1 ayrıca doğrulandı (`experiments/modelleme-plani.md:254,256,303`; beş koşunun hepsi `"contract": "T2"`).

**Genel hüküm:** Son test şimdi açılamaz: (1) K4/K6/OR'un dayandığı `plan` sözleşmeli modeller yok; (2) son testin birincil yöntemleri (aylık kayan conformal, gün blok bootstrap + Holm, son test betiği) kodda yok. İptal sapması Val-A aylık kırılımıyla savunulabilir; D2'nin Val-B sayıları (AUC 0,838) başlık metriği olmamalı.

## Critical
- **C1 – plan modeli yok.** K4 "plan vs B1", K6 "plan vs B1", OR kaynağı `plan` kantilleri; tüm koşular T2. Eylem: `--contract plan` koşuları (aynı parametre ve erken durdurma kuralı; takvim kararı önceden yazılı) ya da K4/K6/OR'u T2 olarak yeniden tanımla (plan değişikliği, kullanıcı kararı). OR'a `p_k` verecek model dondurulsun; D2 (T2) tarife planlamasında kullanılamaz.
- **C2 – son test kodu yok.** `run_calibration.py:28-30` kayan conformal'ı "son test betiği"ne bırakıyor; betik, bootstrap ve Holm yok. Eylem: kilit öncesi yazılsın, birim testten geçsin, provada uçtan uca çalışsın.

## Major
- **M1 – Val-B çok amaçlı kullanıldı.** F1 eşiği, kalibrasyon, conformal, permütasyon (plan Val-A diyordu), takvim hipotezi. Özetlerdeki "Val-B başka hiçbir seçimde kullanılmadı" cümlesi artık yanlış (`run_models.py:1226`). ArrDel15/kantil Val-B sıralama/kayıp metrikleri görece temiz; Val-B F1 ve D2'nin Val-B sayıları iyimser. "Zararlı" etiketi yalnızca permütasyon gürültüsüne dayanıyor (26 gün).
- **M2 – iptal kuralından sapma.** Lehine: D2, Val-A'nın 4 ayının 4'ünde daha iyi (log-loss ve AUC; Eylül 0,743→0,790, Ekim 0,668→0,786, Kasım 0,620→0,676, Aralık 0,662→0,694); D1'de ortalama tahmin turlarla 0,0102→0,0037 düşüyor (yaygınlık 0,0128). Aleyhine: R1 eşiği sonuçtan sonra esnetildi (çatallanan yollar); hipotez Val-B'den doğdu; iptal için ayrı ayar yapılmadı. Val-A/Val-B AUC farkı daha çok iptal nedenlerinin farkından: Kasım Val-A pozitiflerinin ~%49'u, D2 Kasım'da ciddi düşük tahmin (0,0083 vs 0,0255; hava dışı/önceden planlı iptaller olabilir, doğrulanmadı); Val-B hava kaynaklı. L ve B1 aynı örüntüyü gösteriyor → D2'ye özgü aşırı uyum değil. Yaz için 0,838 beklenti değildir. Eylem: aylık tablo karar notuna, sapma model kartına; D1'in testte ikincil raporlanıp raporlanmayacağı önceden yazılsın.
- **M3 – takvim özellikleri ArrDel15/kantillerde hâlâ var.** Val-B permütasyonunda hepsinde "zararlı"; ArrDel15 LightGBM aylık calibration-in-the-large Val-A'da −0,011/−0,063/−0,064/−0,076 (B1 toplamda −0,003). Eylem: D adımı (C + `--drop-date-features`), karar kuralı önceden ve yalnızca Val-A aylık; yapılmazsa takvimli sürüm birincil dondurulsun, sınırlılık yazılsın.
- **M4 – kalibrasyon/conformal tek kış ayında sınandı.** Kayan pencere ~57 gün geriden gelir; K5 toleransı gün içi bağımlılık nedeniyle iyimser (etkin n ≈ 184 gün); kamu BTS ~2 ay gecikmeli (varsayım). Olasılıklar için kayan düzeltme yok; K3 test aylarının şansına bağlı. Eylem: K3/K4 katlarıyla (Mart–Ağustos 2025) uçtan uca **prova**; 2 ay gecikmeli "kamu senaryosu" ikincil önceden kayıt; olasılık için kayan kesişim düzeltmesi kararı.
- **M5 – iptal etiketinin bilinme zamanı belirsiz.** T−2'de zaten iptal edilmiş uçuşlar hedef tanımı sorunu. Eylem: Origin × gün içinde tabakalı AUC; "erken uyarı" iddiası yok.
- **M6 – isotonic (plan) vs Platt (veri).** Fark tek ayda ve küçük; ikisi de savunulabilir, testten önce donmalı. Sıralama metrikleri ham skorla.
- **M7 – +0,07 AUC'nin anlamı.** Δ, hem ML'nin hem T−2 havasının katkısı; ayırmak için plan modeli gerekir (C1). Çerçeve: "kamu verisiyle, uçak rotasyonu olmadan ulaşılabilen düzey".
- **M8 – `schedule_excess_min`.** Sızıntı değil ama q050 becerisinin ~%95'i; OR karar değişkeni (`CRSElapsedTime`) modelin girdisinde. Eylem: OR model duyarlılığını nedensel kullanmasın; plan varsayımı (1 dk tampon = 1 dk daha az rötar) açıkça uygulansın; keşifsel "B1 + tarife fazlası" baseline.
- **M9 – iki koşu, farklı ve kirli commit'ler.** D2 `c3ad8cf` (60 özellik, özet `b3ea6b364a0e`), C `61ddb4f` (65 özellik, `c86a71f835d8`), ikisi `dirty: true`; C'nin `calibrators.json`'unda reddedilen iptal kalibratörü de var. Eylem: kilit dosyasında hedef başına koşu/model/best_iteration/özet/çıkarılan özellik/kalibratör anahtarı; temiz commit'te Val-B yeniden üretimi.
- **M10 – `Reporting_Airline` ve dolaylı sıralama.** q095 permütasyonunda 1. sırada. Tek taşıyıcılı rota × saat hücreleri fiilen taşıyıcı performansıdır. Eylem: tek taşıyıcı payı > %90 olan hücre kuralı; taşıyıcı SHAP/bağımlılık grafiği yok; önem tek sayı.

## Minor
m1 embargo 0 (etkisi Val-A'nın ilk günü); m2 yoğunluk tablosu sınır günleri (2026-09 yok); m3 OOF temsil farkı, "expanding" kontrolü yapılmadı; m4 F1 eşiği taşınamayabilir; m5 METAR `valid` zamanı ≠ alınma zamanı, +30 dk duyarlılık önerisi; m6 permütasyon Val-B'de yapıldı (sapma kaydı).

## Son test açılmadan önce dondurulacaklar
1. Hedef başına koşu, model, best_iteration, sözleşme, çıkarılan özellik; temiz commit, veri parmak izi `5a964e…`, sürümler.
2. Takvim kararı (ArrDel15/kantil).
3. Kalibratör yöntemi, fit kümesi, anahtar; olasılık için kayan düzeltme var mı.
4. Conformal: kayan pencere [m−57, m−2] ve kodu, statik karşılaştırma, kamu senaryosu, k > n davranışı.
5. F1 eşikleri (ör. ArrDel15 LightGBM 0,1879; B1 0,1724).
6. Holm ailesi (§5.2) ve sözleşmeleri.
7. K1–K7 (K3 ham mı kalibre mi; K3/K5 toleransları; K4/K6 sözleşmesi).
8. Bootstrap: gün blok, B = 1000, tohum 42, yüzdelik GA, p-değeri formülü.
9. Raporlama kuralları (D1 ikincil mi, D2 Val-B başlık değil, taşıyıcı hücre kuralı, olay günleri, aylık kapsama grafiği).
10. K3/K4 provası; kilit ancak prova geçince.
