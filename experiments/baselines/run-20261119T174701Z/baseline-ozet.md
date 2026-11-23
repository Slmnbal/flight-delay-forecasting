# Baseline değerlendirmesi (B0, B1, B2)

- Çalıştırma: `run-20261119T174701Z` · oluşturma (UTC): 2026-11-19T17:47:01.230912+00:00 · git: `21b6dc145dcaa673cbc464d6ab58b25f0b9ff122` (kirli: True)
- Okunan aylar: 2023-09 .. 2026-02 (30 ay); **son test (2026-03..08) okunmadı**.
- Veri parmak izi (okunan dosyalar): `caeb5fabc8e9533b5f4ea343bd57987c256138b097193e77a4fd5b658de1cb37`
- Parametreler: m = 20.0, min_support = 1, min_tail = 20, embargo = 0 gün, segment n eşiği = 500
- MLflow: 9 koşu kaydedildi (deney öneki havayolu-ds/baseline/...)
- Plan: `experiments/modelleme-plani.md` §1 (bölme), §3 (hedefler), §4.1 (baseline), §5.1 (metrikler).

Notlar: F1 eşiği her baseline için Val-B'de seçildi; Val-B'deki F1 örneklem içidir. Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). GA/bootstrap bu çalıştırmada yok (plan §5.2 son test içindir).

## Fit penceresi 2023-09-01 .. 2025-08-31

### ArrDel15 (sınıflandırma)

| Küme | Baseline | n | Yaygınlık | ROC-AUC | PR-AUC | Brier | BSS (B1'e göre) | Log-loss | ECE | Ort. tahmin − gözlenen | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B0 | 1483504 | 0.2228 | 0.5000 | 0.2228 | 0.1732 | -0.0368 | 0.5305 | 0.0442 | -0.0031 | 0.3644 |
| val_a | B1 | 1483504 | 0.2228 | 0.6320 | 0.3086 | 0.1670 | 0.0000 | 0.5121 | 0.0100 | -0.0027 | 0.4016 |
| val_a | B2 | 1483504 | 0.2228 | 0.6299 | 0.3063 | 0.1694 | -0.0140 | 0.5204 | 0.0457 | -0.0457 | 0.4005 |
| val_b | B0 | 662410 | 0.2131 | 0.5000 | 0.2131 | 0.1677 | -0.0145 | 0.5181 | 0.0479 | 0.0066 | 0.3513 |
| val_b | B1 | 662410 | 0.2131 | 0.6000 | 0.2750 | 0.1653 | 0.0000 | 0.5104 | 0.0274 | 0.0082 | 0.3719 |
| val_b | B2 | 662410 | 0.2131 | 0.6016 | 0.2791 | 0.1645 | 0.0051 | 0.5087 | 0.0170 | -0.0091 | 0.3726 |

### İptal (sınıflandırma)

| Küme | Baseline | n | Yaygınlık | ROC-AUC | PR-AUC | Brier | BSS (B1'e göre) | Log-loss | ECE | Ort. tahmin − gözlenen | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B0 | 1506008 | 0.0128 | 0.5000 | 0.0128 | 0.0127 | -0.0013 | 0.0686 | 0.0076 | 0.0001 | 0.0253 |
| val_a | B1 | 1506008 | 0.0128 | 0.6166 | 0.0225 | 0.0126 | 0.0000 | 0.0686 | 0.0033 | -0.0001 | 0.0431 |
| val_a | B2 | 1506008 | 0.0128 | 0.5861 | 0.0176 | 0.0127 | -0.0061 | 0.0754 | 0.0072 | -0.0039 | 0.0351 |
| val_b | B0 | 689119 | 0.0367 | 0.5000 | 0.0367 | 0.0359 | -0.0055 | 0.1721 | 0.0298 | -0.0238 | 0.0708 |
| val_b | B1 | 689119 | 0.0367 | 0.6192 | 0.0568 | 0.0357 | 0.0000 | 0.1719 | 0.0239 | -0.0239 | 0.1041 |
| val_b | B2 | 689119 | 0.0367 | 0.5772 | 0.0474 | 0.0357 | -0.0011 | 0.1783 | 0.0216 | -0.0216 | 0.0853 |

### Varış rötarı kantilleri (tamamlanan uçuşlar, dk)

| Küme | Baseline | n | Pinball P50 | Pinball P80 | Pinball P95 | MAE P50 | Kapsama P80 | Kapsama P95 | %80 aralık kapsama | %80 aralık genişlik | Kesişme oranı |
|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B0 | 1483504 | 12.081 | 13.268 | 8.320 | 24.162 | 0.7973 | 0.9504 | 0.8110 | 69.0 | 0.0000 |
| val_a | B1 | 1483504 | 11.931 | 12.822 | 7.964 | 23.863 | 0.8001 | 0.9488 | 0.7953 | 67.4 | 0.0028 |
| val_a | B2 | 1483504 | 12.044 | 13.031 | 8.066 | 24.089 | 0.7519 | 0.9414 | 0.7740 | 59.2 | 0.0030 |
| val_b | B0 | 662410 | 12.245 | 13.233 | 8.410 | 24.490 | 0.8066 | 0.9535 | 0.7800 | 69.0 | 0.0000 |
| val_b | B1 | 662410 | 12.193 | 13.067 | 8.231 | 24.387 | 0.8063 | 0.9498 | 0.7569 | 67.9 | 0.0034 |
| val_b | B2 | 662410 | 12.198 | 13.006 | 8.226 | 24.396 | 0.7887 | 0.9478 | 0.7632 | 64.6 | 0.0040 |

ArrDel15 tutarlılığı (BTS ArrDel15 ile ArrDelay >= 15 karşılaştırması):

- train: karşılaştırılan 8985342, uyumsuz 0, tamamlanmış ama ArrDel15 boş 0
- val_a: karşılaştırılan 1483504, uyumsuz 0, tamamlanmış ama ArrDel15 boş 1
- val_b: karşılaştırılan 662410, uyumsuz 0, tamamlanmış ama ArrDel15 boş 0

