# Kalibrasyon ve conformal ayar (sonradan, yeniden eğitim yok) – `run-20261121T073825Z`

- Oluşturma (UTC): 2026-11-21T07:59:19.766155+00:00 · koşu: `experiments/models/run-20261121T073825Z` · modeller: `deliverables/models/run-20261121T073825Z`
- Okunan: fit penceresi (geçmiş istatistikleri ve B1 için) + Val-B; **Val-A ve son test okunmadı**; model yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı (55 dosya).
- Zaman sıralı ayrım (Val-B içinde): fit 2026-01-01 .. 2026-01-30, değerlendirme 2026-02-01 .. 2026-02-28, aradaki 1 gün embargo (plan §1.4). Önce/sonra sayıları yalnızca değerlendirme kısmındandır (koşunun Val-B toplamı Ocak+Şubat'tı).
- Birincil kalibratör: **isotonic** (plan §4.2); Platt karşılaştırma. B1 aynı kuralla kalibre edildi; BSS her aşamada aynı aşamadaki B1'e göre.
- Süre: 73.9 sn · tepe bellek (RSS): 4.247 GB · adımlar: {'load': 3.7, 'history_and_b1': 10.3, 'matrix': 1.8, 'classification': 7.4, 'quantiles': 50.7}

## Koşunun Val-B metriğini yeniden üretme

| Model | Metrik | Koşu | Şimdi | Aynı mı |
|---|---|---|---|---|
| arr_del15-B1 | roc_auc | 0.599962 | 0.599962 | evet |
| arr_del15-lgbm | roc_auc | 0.590984 | 0.590984 | evet |
| arr_delay_q010-lgbm | pinball_q010 | 3.641745 | 3.641745 | evet |
| arr_delay_q050-lgbm | pinball_q050 | 12.307872 | 12.307872 | evet |
| arr_delay_q080-lgbm | pinball_q080 | 13.181531 | 13.181531 | evet |
| arr_delay_q090-lgbm | pinball_q090 | 10.815001 | 10.815001 | evet |
| arr_delay_q095-lgbm | pinball_q095 | 8.182095 | 8.182095 | evet |

## ArrDel15: olasılık kalibrasyonu (değerlendirme ayı, önce → sonra)

| Model | Yöntem | n | Yaygınlık | Brier | ECE | Ort. tahmin − gözlenen | Kal. eğimi | Log-loss | ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| B1 | isotonic | 325967 | 0.2079 | 0.1616 → 0.1608 | 0.0245 → 0.0143 | 0.0139 → 0.0106 | 0.7131 → 1.1645 | 0.5011 → 0.4993 | 0.6101 → 0.6100 |
| B1 | platt | 325967 | 0.2079 | 0.1616 → 0.1608 | 0.0245 → 0.0124 | 0.0139 → 0.0106 | 0.7131 → 1.1937 | 0.5011 → 0.4993 | 0.6101 → 0.6101 |
| LightGBM | isotonic | 325967 | 0.2079 | 0.1650 → 0.1627 | 0.0439 → 0.0283 | 0.0056 → 0.0146 | 0.5237 → 0.7228 | 0.5091 → 0.5036 | 0.6035 → 0.6032 |
| LightGBM | platt | 325967 | 0.2079 | 0.1650 → 0.1612 | 0.0439 → 0.0137 | 0.0056 → 0.0088 | 0.5237 → 0.9754 | 0.5091 → 0.5005 | 0.6035 → 0.6035 |

- B1 (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) FLL -0.0882 (önce -0.0691, n 7912)
- LightGBM (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) DEN 0.0755 (önce 0.0782, n 22797)

## Varış rötarı: conformal ayar (değerlendirme ayı)

| Model | Düzey | Ofset (dk) | Kapsama önce | Kapsama sonra | Pinball/genişlik önce | sonra | Havalimanı ±5 puan içinde (önce → sonra) |
|---|---|---|---|---|---|---|---|
| LightGBM | q080 (tek yönlü) | 1.95 | 0.7865 | 0.8026 | 12.543 | 12.532 | 0.80 → 0.93 |
| LightGBM | q095 (tek yönlü) | 5.63 | 0.9550 | 0.9592 | 7.633 | 7.673 | 1.00 → 1.00 |
| LightGBM | interval80 (CQR) | 2.12 | 0.7685 | 0.8093 | 65.3 dk | 69.6 dk | 0.67 → 0.73 |
| LightGBM | q080+c > q095+c | 0.0000 | | | | | |
| B1 | q080 (tek yönlü) | 0.80 | 0.8136 | 0.8143 | 12.359 | 12.370 | 0.73 → 0.73 |
| B1 | q095 (tek yönlü) | 5.40 | 0.9546 | 0.9589 | 7.746 | 7.783 | 1.00 → 1.00 |
| B1 | interval80 (CQR) | 3.00 | 0.7607 | 0.8175 | 67.9 dk | 73.9 dk | 0.63 → 0.87 |
| B1 | q080+c > q095+c | 0.0001 | | | | | |

Hedefler: P80 0,80 · P95 0,95 · %80 aralık 0,80. Kabul ölçütü K5 son testte ve **aylık kayan** pencereyle değerlendirilir; buradaki tek ay yalnızca yöntemin dürüst bir ön kontrolüdür. Statik (tüm Val-B) kalibratörler ve ofsetler `calibrators.json` dosyasında; burada değerlendirilmedi.

