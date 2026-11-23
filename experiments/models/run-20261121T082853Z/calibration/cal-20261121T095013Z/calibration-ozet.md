# Kalibrasyon ve conformal ayar (sonradan, yeniden eğitim yok) – `run-20261121T082853Z`

- Oluşturma (UTC): 2026-11-21T09:50:13.499800+00:00 · koşu: `experiments/models/run-20261121T082853Z` · modeller: `deliverables/models/run-20261121T082853Z`
- Okunan: fit penceresi (geçmiş istatistikleri ve B1 için) + Val-B; **Val-A ve son test okunmadı**; model yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı (57 dosya).
- Zaman sıralı ayrım (Val-B içinde): fit 2026-01-01 .. 2026-01-30, değerlendirme 2026-02-01 .. 2026-02-28, aradaki 1 gün embargo (plan §1.4). Önce/sonra sayıları yalnızca değerlendirme kısmındandır (koşunun Val-B toplamı Ocak+Şubat'tı).
- Birincil kalibratör: **isotonic** (plan §4.2); Platt karşılaştırma. B1 aynı kuralla kalibre edildi; BSS her aşamada aynı aşamadaki B1'e göre.
- Süre: 283.6 sn · tepe bellek (RSS): 4.244 GB · adımlar: {'load': 3.9, 'history_and_b1': 10.2, 'matrix': 2.3, 'classification': 29.2, 'quantiles': 238.0}

## Koşunun Val-B metriğini yeniden üretme

| Model | Metrik | Koşu | Şimdi | Aynı mı |
|---|---|---|---|---|
| arr_del15-B1 | roc_auc | 0.599962 | 0.599962 | evet |
| arr_del15-lgbm | roc_auc | 0.699819 | 0.699819 | evet |
| arr_delay_q010-lgbm | pinball_q010 | 3.482948 | 3.482948 | evet |
| arr_delay_q050-lgbm | pinball_q050 | 11.503156 | 11.503156 | evet |
| arr_delay_q080-lgbm | pinball_q080 | 12.075530 | 12.075530 | evet |
| arr_delay_q090-lgbm | pinball_q090 | 9.944792 | 9.944792 | evet |
| arr_delay_q095-lgbm | pinball_q095 | 7.529320 | 7.529320 | evet |

## ArrDel15: olasılık kalibrasyonu (değerlendirme ayı, önce → sonra)

| Model | Yöntem | n | Yaygınlık | Brier | ECE | Ort. tahmin − gözlenen | Kal. eğimi | Log-loss | ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| B1 | isotonic | 325967 | 0.2079 | 0.1616 → 0.1608 | 0.0245 → 0.0143 | 0.0139 → 0.0106 | 0.7131 → 1.1645 | 0.5011 → 0.4993 | 0.6101 → 0.6100 |
| B1 | platt | 325967 | 0.2079 | 0.1616 → 0.1608 | 0.0245 → 0.0124 | 0.0139 → 0.0106 | 0.7131 → 1.1937 | 0.5011 → 0.4993 | 0.6101 → 0.6101 |
| LightGBM | isotonic | 325967 | 0.2079 | 0.1499 → 0.1497 | 0.0152 → 0.0047 | -0.0152 → 0.0003 | 0.9101 → 0.9560 | 0.4703 → 0.4694 | 0.6907 → 0.6906 |
| LightGBM | platt | 325967 | 0.2079 | 0.1499 → 0.1496 | 0.0152 → 0.0033 | -0.0152 → 0.0002 | 0.9101 → 0.9642 | 0.4703 → 0.4692 | 0.6907 → 0.6907 |

- B1 (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) FLL -0.0882 (önce -0.0691, n 7912)
- LightGBM (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) IAH 0.0674 (önce 0.0505, n 8871)

## Varış rötarı: conformal ayar (değerlendirme ayı)

| Model | Düzey | Ofset (dk) | Kapsama önce | Kapsama sonra | Pinball/genişlik önce | sonra | Havalimanı ±5 puan içinde (önce → sonra) |
|---|---|---|---|---|---|---|---|
| LightGBM | q080 (tek yönlü) | 2.39 | 0.7776 | 0.8010 | 11.552 | 11.527 | 0.73 → 0.93 |
| LightGBM | q095 (tek yönlü) | 10.64 | 0.9403 | 0.9539 | 7.183 | 7.158 | 1.00 → 1.00 |
| LightGBM | interval80 (CQR) | 1.82 | 0.7607 | 0.7993 | 56.8 dk | 60.4 dk | 0.70 → 0.97 |
| LightGBM | q080+c > q095+c | 0.0000 | | | | | |
| B1 | q080 (tek yönlü) | 0.80 | 0.8136 | 0.8143 | 12.359 | 12.370 | 0.73 → 0.73 |
| B1 | q095 (tek yönlü) | 5.40 | 0.9546 | 0.9589 | 7.746 | 7.783 | 1.00 → 1.00 |
| B1 | interval80 (CQR) | 3.00 | 0.7607 | 0.8175 | 67.9 dk | 73.9 dk | 0.63 → 0.87 |
| B1 | q080+c > q095+c | 0.0001 | | | | | |

Hedefler: P80 0,80 · P95 0,95 · %80 aralık 0,80. Kabul ölçütü K5 son testte ve **aylık kayan** pencereyle değerlendirilir; buradaki tek ay yalnızca yöntemin dürüst bir ön kontrolüdür. Statik (tüm Val-B) kalibratörler ve ofsetler `calibrators.json` dosyasında; burada değerlendirilmedi.

