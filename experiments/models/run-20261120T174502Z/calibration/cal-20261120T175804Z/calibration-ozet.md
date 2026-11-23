# Kalibrasyon ve conformal ayar (sonradan, yeniden eğitim yok) – `run-20261120T174502Z`

- Oluşturma (UTC): 2026-11-20T17:58:04.552758+00:00 · koşu: `experiments/models/run-20261120T174502Z` · modeller: `deliverables/models/run-20261120T174502Z`
- Okunan: fit penceresi (geçmiş istatistikleri ve B1 için) + Val-B; **Val-A ve son test okunmadı**; model yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı (57 dosya).
- Zaman sıralı ayrım (Val-B içinde): fit 2026-01-01 .. 2026-01-30, değerlendirme 2026-02-01 .. 2026-02-28, aradaki 1 gün embargo (plan §1.4). Önce/sonra sayıları yalnızca değerlendirme kısmındandır (koşunun Val-B toplamı Ocak+Şubat'tı).
- Birincil kalibratör: **isotonic** (plan §4.2); Platt karşılaştırma. B1 aynı kuralla kalibre edildi; BSS her aşamada aynı aşamadaki B1'e göre.
- Süre: 16.3 sn · tepe bellek (RSS): 3.65 GB · adımlar: {'load': 3.0, 'history_and_b1': 8.0, 'matrix': 1.8, 'classification': 3.5, 'quantiles': 0.0}

## Koşunun Val-B metriğini yeniden üretme

| Model | Metrik | Koşu | Şimdi | Aynı mı |
|---|---|---|---|---|
| cancelled-B1 | roc_auc | 0.619179 | 0.619179 | evet |
| cancelled-lgbm | roc_auc | 0.838494 | 0.838494 | evet |

## İptal: olasılık kalibrasyonu (değerlendirme ayı, önce → sonra)

| Model | Yöntem | n | Yaygınlık | Brier | ECE | Ort. tahmin − gözlenen | Kal. eğimi | Log-loss | ROC-AUC |
|---|---|---|---|---|---|---|---|---|---|
| B1 | isotonic | 334815 | 0.0244 | 0.0238 → 0.0242 | 0.0116 → 0.0219 | -0.0116 → 0.0219 | 0.5900 → 1.1626 | 0.1172 → 0.1184 | 0.6346 → 0.6349 |
| B1 | platt | 334815 | 0.0244 | 0.0238 → 0.0241 | 0.0116 → 0.0219 | -0.0116 → 0.0219 | 0.5900 → 1.2444 | 0.1172 → 0.1185 | 0.6346 → 0.6346 |
| LightGBM | isotonic | 334815 | 0.0244 | 0.0210 → 0.0193 | 0.0121 → 0.0077 | -0.0121 → 0.0071 | 1.3403 → 0.9863 | 0.0933 → 0.0881 | 0.8152 → 0.8148 |
| LightGBM | platt | 334815 | 0.0244 | 0.0210 → 0.0192 | 0.0121 → 0.0068 | -0.0121 → 0.0068 | 1.3403 → 0.9967 | 0.0933 → 0.0875 | 0.8152 → 0.8152 |

- B1 (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) DFW 0.0515 (önce 0.0081, n 22019)
- LightGBM (isotonic): Origin segmenti 30; en büyük |ort. tahmin − gözlenen| (sonra) DCA 0.0415 (önce -0.0129, n 10996)

