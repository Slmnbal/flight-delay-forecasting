# Özet (Türkçe): ABD iç hat uçuşlarında rötar riski ve tarife tamponu

> Kamu verisine dayalı, havayollarıyla bağlantısız. Ana belgeler İngilizcedir: [`README.md`](../../README.md), [`model-card.md`](model-card.md).

**Problem.** Yalnızca tarife, geçmiş istatistikler ve kalkıştan 2 saat önceki hava gözlemi biliniyorken, bir ABD iç hat uçuşunun 15 dakika veya daha geç varıp varmayacağı
(ArrDel15), varış rötarının büyüklüğü (P50 / P80 / P95) ne kadar iyi tahmin edilebilir ve bu bilgi tarife blok süresi tamponunu seçmeye yarar mı?

**Yaklaşım.** BTS On-Time verisi (30 havalimanından kalkış, 2023-09 ile 2026-08 arası 36 ay, 13,7 milyon satır) ile IEM METAR hava verisi birleştirildi. LightGBM sınıflandırıcı ve
kantil modelleri, Platt olasılık kalibrasyonu ve conformal üst sınırlar kullanıldı. Değerlendirme, son 6 ayda (2026-03..08) tek seferlik ve önceden kayıtlı kurallarla,
B1 baseline'ına (rota × saat bloğu geçmişi) karşı yapıldı. Üzerine kantillerden tarife tamponu politikaları türeten bir OR uzantısı (newsvendor, sırt çantası, Pyomo + HiGHS ile LP / MILP) eklendi.

## Başlıca sonuçlar (son test, B1'e göre fark, %95 güven aralığı)

- ArrDel15 ayrıştırma (T−2 saat modeli): ROC-AUC 0,7120, B1 0,6564 (**+0,0556** [+0,0499; +0,0612]); PR-AUC 0,4767, B1 0,3754 (**+0,1013** [+0,0915; +0,1105]).
- Brier skill score (aylık kayan Platt): **+0,0625** [+0,0541; +0,0712]; kalibrasyon: CITL −0,0025, eğim 1,002.
- Hava bilgisi içermeyen (yalnızca tarife + geçmiş) "plan" modelinin kantilleri B1'den iyi: pinball farkı P50 −0,2315, P80 −0,2168, P95 −0,1066 dk (hepsinde aralık sıfırın altında).
- ROC-AUC kazancının kaynağı: tarife + geçmiş modeli B1'e göre +0,0193; üstüne T−2 saat havası +0,0363.
- Kabul ölçütleri: K1–K4 ve K7 geçti; **K5 ve K6 geçmedi.**

**Geçmeyenler (olduğu gibi):** (K5) conformal P80 / P95 genel kapsaması hedef bandındaydı (0,7877 / 0,9447), ancak havalimanı × ay segmentlerinin yalnızca %68,9'unda P80 kapsaması hedefin ±0,05'i içindeydi
(gereken %80); haziran–temmuzda kapsama düşüktü (0,7547 / 0,7560). (K6) Tarifeye dayalı iptal modeli B1'e göre kazanç göstermedi (PR-AUC farkı −0,0005 [−0,0048; +0,0039]).

**OR ana bulgusu.** Eşit tampon bütçesinde (uçuş başı aynı toplam dakika) plan modeli ≈ B1 (varış rötarı ArrDel15 farkı en çok +0,0004; aralıklar sıfırı içerir ya da ona değer). Değer esas olarak
**T−2 saat operasyonel tahminde**, tarife tamponunda değil. ArrDel15 hedefli sırt çantası, hücre dağılımı yaklaşımı yüzünden basit dakika kuralından kötü çıktı; çözücü uzantısı (LP / MILP) bunun çözücü değil modelleme sorunu olduğunu gösterdi
(keşifsel, post hoc; son test sonucu değildir). Maliyetler varsayımdır (oran ızgarası); A1: 1 dk tampon = 1 dk daha az varış rötarı.

## Neden güvenilir (ve neyle sınırlı)

Zamana göre bölme; sızıntı incelemesi (permütasyon + zaman yolculuğu, şüphe yok); önceden kayıt ve kilitli tek seferlik son test; gün blok bootstrap ve Holm düzeltmesi. Süreçte üç belgelenmiş sapma var
(isotonic yerine Platt; birincil olasılık yöntemi olarak kayan Platt; iptal modelinde takvim özelliklerinin çıkarılması); ayrıntı için [`methodology.md`](methodology.md).

## Sınırlılıklar

- Kamu BTS etiketleri yaklaşık 2 ay gecikmeli yayımlanır; kayan pencere varsayımı 1 gün gecikmedir. 2 ay gecikmeli "kamu" senaryosu ikincildir ve segment kapsaması daha kötüdür.
- Yalnızca rapor veren taşıyıcıların iç hat uçuşları, 30 kalkış havalimanı; uçak rotasyonu, ekip, ağ etkisi yok.
- Kantiller tamamlanan uçuşlara koşulludur; iptal zamanı bilinmez. Model test başında 6–12 ay eskidir; test dönemi rötar oranı (0,2626) erken durdurma dönemine göre (0,2228) yüksektir.
- Havayolu iç sistemleriyle kıyas yapılmadı. Havayolu sıralaması, logo, taşıyıcı bazlı sonuç tablosu ya da kuyruk numarası yayımlanmaz. Tek taşıyıcının payı %90'ı aşan hücreler için tampon önerisi yayımlanmaz
  (test döneminde 24.765 hücrenin 7.094'ü yayımlanabilir).
- Kurulum ve testler her push'ta temiz bir ortamda GitHub Actions ile çalıştırılıyor. Kod lisansı: MIT. Sunum ve etkileşimli site GitHub Pages'te (İngilizce ve Türkçe).

## Bağlantılar

[`README.md`](../../README.md) · [`model-card.md`](model-card.md) · [`methodology.md`](methodology.md) · [`optimization.md`](optimization.md) ·
[son test özeti](../../experiments/son-test/son-test-20261122T105048Z/son-test-ozet.md) · [OR özeti](../../experiments/or/tampon-20261122T173803Z/tampon-ozet.md)
