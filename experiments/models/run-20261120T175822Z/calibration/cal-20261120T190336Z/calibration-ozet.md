# Kalibrasyon ve conformal ayar (sonradan, yeniden eğitim yok) – `run-20261120T175822Z`

- Oluşturma (UTC): 2026-11-20T19:03:36.927333+00:00 · koşu: `experiments/models/run-20261120T175822Z` · modeller: `deliverables/models/run-20261120T175822Z`
- Okunan: fit penceresi (geçmiş istatistikleri ve B1 için) + Val-B; **Val-A ve son test okunmadı**; model yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı (57 dosya).
- Zaman sıralı ayrım (Val-B içinde): fit 2026-01-01 .. 2026-01-30, değerlendirme 2026-02-01 .. 2026-02-28, aradaki 1 gün embargo (plan §1.4). Önce/sonra sayıları yalnızca değerlendirme kısmındandır (koşunun Val-B toplamı Ocak+Şubat'tı).
- Birincil kalibratör: **isotonic** (plan §4.2); Platt karşılaştırma. B1 aynı kuralla kalibre edildi; BSS her aşamada aynı aşamadaki B1'e göre.
- Süre: 209.8 sn · tepe bellek (RSS): 4.341 GB · adımlar: {'load': 5.2, 'history_and_b1': 12.7, 'matrix': 2.9, 'classification': 41.1, 'quantiles': 148.0}

## Koşunun Val-B metriğini yeniden üretme

| Model | Metrik | Koşu | Şimdi | Aynı mı |
|---|---|---|---|---|
| arr_del15-B1 | roc_auc | 0.599962 | 0.599962 | evet |
| arr_del15-lgbm | roc_auc | 0.666551 | 0.666551 | evet |
| arr_del15-logreg | roc_auc | 0.653303 | 0.653303 | evet |
| cancelled-B1 | roc_auc | 0.619179 | 0.619179 | evet |
| cancelled-lgbm | roc_auc | 0.687920 | 0.687920 | evet |
| cancelled-logreg | roc_auc | 0.739417 | 0.739417 | evet |
| arr_delay_q010-lgbm | pinball_q010 | 3.533789 | 3.533789 | evet |
| arr_delay_q050-lgbm | pinball_q050 | 11.732924 | 11.732924 | evet |
| arr_delay_q080-lgbm | pinball_q080 | 12.402431 | 12.402431 | evet |
| arr_delay_q090-lgbm | pinball_q090 | 10.277670 | 10.277670 | evet |
| arr_delay_q095-lgbm | pinball_q095 | 7.785567 | 7.785567 | evet |

## ArrDel15: olasılık kalibrasyonu (değerlendirme ayı, önce → sonra)

| Model | Yöntem | n | Yaygınlık | Brier | ECE | Ort. tahmin − gözlenen | Kal. eğimi | Log-loss | ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| B1 | isotonic | 325967 | 0.2079 | 0.1616 → 0.1608 | 0.0245 → 0.0143 | 0.0139 → 0.0106 | 0.7131 → 1.1645 | 0.5011 → 0.4993 | 0.6101 → 0.6100 |
| B1 | platt | 325967 | 0.2079 | 0.1616 → 0.1608 | 0.0245 → 0.0124 | 0.0139 → 0.0106 | 0.7131 → 1.1937 | 0.5011 → 0.4993 | 0.6101 → 0.6101 |
| LightGBM | isotonic | 325967 | 0.2079 | 0.1522 → 0.1521 | 0.0234 → 0.0178 | -0.0183 → -0.0017 | 0.8182 → 1.0545 | 0.4774 → 0.4769 | 0.6781 → 0.6780 |
| LightGBM | platt | 325967 | 0.2079 | 0.1522 → 0.1517 | 0.0234 → 0.0061 | -0.0183 → -0.0034 | 0.8182 → 1.0883 | 0.4774 → 0.4748 | 0.6781 → 0.6781 |
| L | isotonic | 325967 | 0.2079 | 0.1540 → 0.1545 | 0.0122 → 0.0261 | -0.0055 → 0.0261 | 0.8505 → 1.0584 | 0.4820 → 0.4831 | 0.6626 → 0.6625 |
| L | platt | 325967 | 0.2079 | 0.1540 → 0.1547 | 0.0122 → 0.0279 | -0.0055 → 0.0274 | 0.8505 → 1.1147 | 0.4820 → 0.4836 | 0.6626 → 0.6626 |

- B1 (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) FLL -0.0882 (önce -0.0691, n 7912)
- LightGBM (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) FLL -0.0608 (önce -0.0655, n 7912)
- L (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) IAH 0.1081 (önce 0.0808, n 8871)

## İptal: olasılık kalibrasyonu (değerlendirme ayı, önce → sonra)

| Model | Yöntem | n | Yaygınlık | Brier | ECE | Ort. tahmin − gözlenen | Kal. eğimi | Log-loss | ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| B1 | isotonic | 334815 | 0.0244 | 0.0238 → 0.0242 | 0.0116 → 0.0219 | -0.0116 → 0.0219 | 0.5900 → 1.1626 | 0.1172 → 0.1184 | 0.6346 → 0.6349 |
| B1 | platt | 334815 | 0.0244 | 0.0238 → 0.0241 | 0.0116 → 0.0219 | -0.0116 → 0.0219 | 0.5900 → 1.2444 | 0.1172 → 0.1185 | 0.6346 → 0.6346 |
| LightGBM | isotonic | 334815 | 0.0244 | 0.0235 → 0.0227 | 0.0159 → 0.0179 | -0.0131 → -0.0015 | 2.4778 → 1.3581 | 0.1109 → 0.1024 | 0.7660 → 0.7537 |
| LightGBM | platt | 334815 | 0.0244 | 0.0235 → 0.0231 | 0.0159 → 0.0213 | -0.0131 → 0.0101 | 2.4778 → 3.1876 | 0.1109 → 0.1088 | 0.7660 → 0.7660 |
| L | isotonic | 334815 | 0.0244 | 0.0226 → 0.0215 | 0.0158 → 0.0129 | -0.0158 → 0.0042 | 1.1461 → 1.8834 | 0.1088 → 0.1008 | 0.7465 → 0.7454 |
| L | platt | 334815 | 0.0244 | 0.0226 → 0.0218 | 0.0158 → 0.0054 | -0.0158 → -0.0027 | 1.1461 → 1.2867 | 0.1088 → 0.0990 | 0.7465 → 0.7465 |

- B1 (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) DFW 0.0515 (önce 0.0081, n 22019)
- LightGBM (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) JFK -0.0546 (önce -0.0742, n 7458)
- L (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) JFK -0.0524 (önce -0.0753, n 7458)

## Varış rötarı: conformal ayar (değerlendirme ayı)

| Model | Düzey | Ofset (dk) | Kapsama önce | Kapsama sonra | Pinball/genişlik önce | sonra | Havalimanı ±5 puan içinde (önce → sonra) |
|---|---|---|---|---|---|---|---|
| LightGBM | q080 (tek yönlü) | 2.31 | 0.7675 | 0.7914 | 11.720 | 11.673 | 0.67 → 0.97 |
| LightGBM | q095 (tek yönlü) | 15.13 | 0.9353 | 0.9554 | 7.226 | 7.172 | 1.00 → 1.00 |
| LightGBM | interval80 (CQR) | 2.67 | 0.7536 | 0.8083 | 55.9 dk | 61.2 dk | 0.63 → 0.93 |
| LightGBM | q080+c > q095+c | 0.0000 | | | | | |
| B1 | q080 (tek yönlü) | 0.80 | 0.8136 | 0.8143 | 12.359 | 12.370 | 0.73 → 0.73 |
| B1 | q095 (tek yönlü) | 5.40 | 0.9546 | 0.9589 | 7.746 | 7.783 | 1.00 → 1.00 |
| B1 | interval80 (CQR) | 3.00 | 0.7607 | 0.8175 | 67.9 dk | 73.9 dk | 0.63 → 0.87 |
| B1 | q080+c > q095+c | 0.0001 | | | | | |

Hedefler: P80 0,80 · P95 0,95 · %80 aralık 0,80. Kabul ölçütü K5 son testte ve **aylık kayan** pencereyle değerlendirilir; buradaki tek ay yalnızca yöntemin dürüst bir ön kontrolüdür. Statik (tüm Val-B) kalibratörler ve ofsetler `calibrators.json` dosyasında; burada değerlendirilmedi.

