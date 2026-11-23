# M3 – Son test öncesi kararlar (Red Team incelemesinden sonra), 2026-11-21

Kaynak: `reports/red-team-modelleme-incelemesi.md`. Kullanıcı dört öneriyi de kabul etti ("önerilerin hepsi uygun").

1. **Plan sözleşmeli modeller eğitilir (C1).** K4, K6 ve OR planda yazıldığı gibi `plan` modeline bağlı kalır; yeniden tanımlanmaz. Gerekçe: tampon aylar önce, T−2 havası bilinmeden belirlenir. B1 → plan farkı ML katkısını, plan → T2 farkı hava katkısını ayırır. Parametreler `run-20261119T182216Z`'den, erken durdurma kuralı aynı (Val-A).
2. **Takvim özellikleri ArrDel15 ve kantil modellerinde de denenir (D adımı, M3).** Karar kuralı sonuçtan ÖNCE `experiments/` altında yazılır; karar yalnızca Val-A'ya (aylık kırılım dahil) göre verilir, Val-B kullanılmaz (hipotez Val-B'den doğdu).
3. **Olasılık kalibratörü Platt (M6).** Plandaki isotonic'ten sapma. Gerekçe veriye bakmadan: 2 parametre, kış → yaz kaymasında daha düşük varyans, sıralamayı bozmaz. Şubat 2026 sonucu gerekçe değildir. Isotonic ikincil raporlanır. Sıralama metrikleri (AUC, PR-AUC) ham skorla hesaplanır.
4. **Son test kodu ve prova (C2, M4).** Son test betiği (aylık kayan conformal, gün blok bootstrap B = 1000 tohum 42, Holm α = 0,05, kabul ölçütleri K1–K7) kilit öncesi yazılır ve test edilir. Eğitim penceresindeki K3/K4 katlarıyla (2025-03..08) uçtan uca prova yapılır. K3/K5 toleransları prova sonucuna göre test öncesinde kesinleşir. Kilit ancak prova geçince yazılır.

Ek (Red Team, kabul edilen eylemler): iptal sapması ve aylık Val-A tablosu model kartına; D2'nin Val-B sayıları başlık metriği değildir; özet şablonundaki "Val-B başka hiçbir seçimde kullanılmadı" cümlesi düzeltilir; kilit dosyası hedef başına koşu/model/best_iteration/sözleşme özeti/çıkarılan özellik/kalibratör anahtarını listeler ve temiz commit'te yeniden üretim doğrulanır; tek taşıyıcılı hücre kuralı arayüz aşamasında.

## Prova sonrası kararlar (kullanıcı onayı, 2026-11-22)

Prova: `experiments/son-test-prova/prova-20261121T193353Z` (2025-03..08; kod yolu geçti). Provada K1, K2 geçti; K3, K4 (P95), K5 (yaz segmentleri), K6, K7 geçmedi.

1. **K7 (usul):** kilide sızıntı incelemeleri eklenir: D2 (`perm-20261120T192352Z`) ve yeni D gecikme modeli incelemesi.
2. **K3 – birincil olasılık = aylık kayan Platt** ([m − 57, m − 2] gün; conformal ile aynı pencere). Ön kayıttan (madde 3: sabit Platt birincil) sapma. Gerekçe: provada sabit Platt mevsim geçişinde kayıyor (birleşik CITL −0,015), kayan Platt kaymayı düzeltiyor (−0,004, eğim 1,003). Kanıt geliştirme verisinden (prova), son testten değil; red-team M4 bu kararın test öncesinde verilmesini istemişti. Sabit Platt (Val-B'de bir kez fit, `calibrators.json`) ve isotonic ikincil raporlanır. Varsayım: etiketler 1 gün gecikmeyle bilinir (kamu BTS ~2 ay gecikmeli; sınırlılık olarak yazılır). Kod: `final_eval.PRIMARY_PROBABILITY = "platt_rolling"`, `STATIC_PROBABILITY = "platt"`. Prova bu kodla yeniden çalıştırılır (K3 tolerans önerisi birincil yöntemden hesaplanmalı).
3. **K4 (P95), K5 (segment), K6 değişmez.** Kurallar ve modeller olduğu gibi kalır; son testte geçmezlerse "geçmedi" yazılır (plan §5.3: "model süslenmez").
