# Kalibrasyon ve conformal ayar (sonradan, yeniden eğitim yok) – `run-20261121T080035Z`

- Oluşturma (UTC): 2026-11-21T08:28:02.637500+00:00 · koşu: `experiments/models/run-20261121T080035Z` · modeller: `deliverables/models/run-20261121T080035Z`
- Okunan: fit penceresi (geçmiş istatistikleri ve B1 için) + Val-B; **Val-A ve son test okunmadı**; model yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı (55 dosya).
- Zaman sıralı ayrım (Val-B içinde): fit 2026-01-01 .. 2026-01-30, değerlendirme 2026-02-01 .. 2026-02-28, aradaki 1 gün embargo (plan §1.4). Önce/sonra sayıları yalnızca değerlendirme kısmındandır (koşunun Val-B toplamı Ocak+Şubat'tı).
- Birincil kalibratör: **isotonic** (plan §4.2); Platt karşılaştırma. B1 aynı kuralla kalibre edildi; BSS her aşamada aynı aşamadaki B1'e göre.
- Süre: 49.3 sn · tepe bellek (RSS): 4.233 GB · adımlar: {'load': 3.0, 'history_and_b1': 7.9, 'matrix': 1.4, 'classification': 8.7, 'quantiles': 28.3}

## Koşunun Val-B metriğini yeniden üretme

| Model | Metrik | Koşu | Şimdi | Aynı mı |
|---|---|---|---|---|
| arr_del15-B1 | roc_auc | 0.599962 | 0.599962 | evet |
| arr_del15-lgbm | roc_auc | 0.624967 | 0.624967 | evet |
| cancelled-B1 | roc_auc | 0.619179 | 0.619179 | evet |
| cancelled-lgbm | roc_auc | 0.632264 | 0.632264 | evet |
| arr_delay_q010-lgbm | pinball_q010 | 3.555199 | 3.555199 | evet |
| arr_delay_q050-lgbm | pinball_q050 | 11.992814 | 11.992814 | evet |
| arr_delay_q080-lgbm | pinball_q080 | 12.883267 | 12.883267 | evet |
| arr_delay_q090-lgbm | pinball_q090 | 10.662654 | 10.662654 | evet |
| arr_delay_q095-lgbm | pinball_q095 | 8.063403 | 8.063403 | evet |

## ArrDel15: olasılık kalibrasyonu (değerlendirme ayı, önce → sonra)

| Model | Yöntem | n | Yaygınlık | Brier | ECE | Ort. tahmin − gözlenen | Kal. eğimi | Log-loss | ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| B1 | isotonic | 325967 | 0.2079 | 0.1616 → 0.1608 | 0.0245 → 0.0143 | 0.0139 → 0.0106 | 0.7131 → 1.1645 | 0.5011 → 0.4993 | 0.6101 → 0.6100 |
| B1 | platt | 325967 | 0.2079 | 0.1616 → 0.1608 | 0.0245 → 0.0124 | 0.0139 → 0.0106 | 0.7131 → 1.1937 | 0.5011 → 0.4993 | 0.6101 → 0.6101 |
| LightGBM | isotonic | 325967 | 0.2079 | 0.1589 → 0.1593 | 0.0153 → 0.0201 | 0.0024 → 0.0201 | 0.8153 → 0.8252 | 0.4933 → 0.5042 | 0.6322 → 0.6322 |
| LightGBM | platt | 325967 | 0.2079 | 0.1589 → 0.1589 | 0.0153 → 0.0191 | 0.0024 → 0.0191 | 0.8153 → 1.0118 | 0.4933 → 0.4935 | 0.6322 → 0.6322 |

- B1 (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) FLL -0.0882 (önce -0.0691, n 7912)
- LightGBM (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) IAH 0.1049 (önce 0.0941, n 8871)

## İptal: olasılık kalibrasyonu (değerlendirme ayı, önce → sonra)

| Model | Yöntem | n | Yaygınlık | Brier | ECE | Ort. tahmin − gözlenen | Kal. eğimi | Log-loss | ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| B1 | isotonic | 334815 | 0.0244 | 0.0238 → 0.0242 | 0.0116 → 0.0219 | -0.0116 → 0.0219 | 0.5900 → 1.1626 | 0.1172 → 0.1184 | 0.6346 → 0.6349 |
| B1 | platt | 334815 | 0.0244 | 0.0238 → 0.0241 | 0.0116 → 0.0219 | -0.0116 → 0.0219 | 0.5900 → 1.2444 | 0.1172 → 0.1185 | 0.6346 → 0.6346 |
| LightGBM | isotonic | 334815 | 0.0244 | 0.0238 → 0.0241 | 0.0118 → 0.0218 | -0.0118 → 0.0218 | 1.2746 → 1.1116 | 0.1159 → 0.1177 | 0.6517 → 0.6511 |
| LightGBM | platt | 334815 | 0.0244 | 0.0238 → 0.0242 | 0.0118 → 0.0220 | -0.0118 → 0.0220 | 1.2746 → 1.1529 | 0.1159 → 0.1180 | 0.6517 → 0.6517 |

- B1 (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) DFW 0.0515 (önce 0.0081, n 22019)
- LightGBM (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) DFW 0.0602 (önce 0.0057, n 22019)

## Varış rötarı: conformal ayar (değerlendirme ayı)

| Model | Düzey | Ofset (dk) | Kapsama önce | Kapsama sonra | Pinball/genişlik önce | sonra | Havalimanı ±5 puan içinde (önce → sonra) |
|---|---|---|---|---|---|---|---|
| LightGBM | q080 (tek yönlü) | 2.66 | 0.8021 | 0.8223 | 12.199 | 12.232 | 0.80 → 0.83 |
| LightGBM | q095 (tek yönlü) | 9.02 | 0.9520 | 0.9599 | 7.598 | 7.653 | 1.00 → 1.00 |
| LightGBM | interval80 (CQR) | 1.12 | 0.7844 | 0.8068 | 66.5 dk | 68.7 dk | 0.83 → 0.90 |
| LightGBM | q080+c > q095+c | 0.0000 | | | | | |
| B1 | q080 (tek yönlü) | 0.80 | 0.8136 | 0.8143 | 12.359 | 12.370 | 0.73 → 0.73 |
| B1 | q095 (tek yönlü) | 5.40 | 0.9546 | 0.9589 | 7.746 | 7.783 | 1.00 → 1.00 |
| B1 | interval80 (CQR) | 3.00 | 0.7607 | 0.8175 | 67.9 dk | 73.9 dk | 0.63 → 0.87 |
| B1 | q080+c > q095+c | 0.0001 | | | | | |

Hedefler: P80 0,80 · P95 0,95 · %80 aralık 0,80. Kabul ölçütü K5 son testte ve **aylık kayan** pencereyle değerlendirilir; buradaki tek ay yalnızca yöntemin dürüst bir ön kontrolüdür. Statik (tüm Val-B) kalibratörler ve ofsetler `calibrators.json` dosyasında; burada değerlendirilmedi.

