# Ana modeller – T2 sözleşmesi (Val-A / Val-B, B1'e göre)

- Çalıştırma: `run-20261120T173554Z` · UTC: 2026-11-20T17:35:54.039814+00:00 · git: `c3ad8cf6d106ccd2519b73ec0e4aa049309ce8b3` (kirli: True)
- Okunan aylar: 2023-09 .. 2026-02 (30 ay); **son test (2026-03..08) okunmadı**.
- Fit penceresi: 2023-09-01 .. 2025-08-31 · özellik sayısı: 65 · sözleşme özeti: `c86a71f835d8`
- Erken durdurma: **val_a** (plan §4.3; LightGBM'in Val-A sonuçları bu yüzden hafif iyimser) · F1 eşiği: **val_b** (Val-B'de örneklem içi) · Val-B başka hiçbir seçimde kullanılmadı.
- Arama: 0 deneme (arama yok; parametreler `run-20261119T182216Z` koşusundan)
- Çıkarılan özellikler: yok · iptal erken durdurma metriği: `binary_logloss` · kantil tur tavanı: 1000 · aralık modelleri (α 0,10/0,90): hayır
- Süreler (sn): {'load': 4.0, 'search': 0.0, 'b1_reference': 4.3, 'history': 28.8, 'matrices': 19.9, 'classification': 490.3, 'quantiles': 0.0} · tepe bellek (RSS): 4.466 GB
- Model dosyaları: `deliverables/models/run-20261120T173554Z` · git'te yok sayılıyor mu: True
- MLflow: kapalı (--mlflow off)

Notlar: Farklar nokta tahminidir; GA ve anlamlılık (gün blok bootstrap, plan §5.2) son test içindir. Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). Kantiller satır başına sıralandı (plan §3.3); B1 kantilleri tanımlandığı gibi (sıralamasız).

- Seçilen parametreler (arr_del15, from run-20261119T182216Z): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`

## İptal (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1506008 | 0.0128 | 0.6166 | - | 0.0225 | - | 0.0126 | 0.0000 | 0.0686 | - | 0.0033 | -0.0001 | 0.479 | 0.0431 |
| val_a | LightGBM | 1506008 | 0.0128 | 0.6248 | +0.0082 | 0.0389 | +0.0165 | 0.0126 | 0.0042 | 0.0671 | -0.0015 | 0.0066 | -0.0026 | 1.676 | 0.0735 |
| val_b | B1 | 689119 | 0.0367 | 0.6192 | - | 0.0568 | - | 0.0357 | 0.0000 | 0.1719 | - | 0.0239 | -0.0239 | 0.497 | 0.1041 |
| val_b | LightGBM | 689119 | 0.0367 | 0.6879 | +0.0687 | 0.0917 | +0.0348 | 0.0354 | 0.0072 | 0.1621 | -0.0098 | 0.0239 | -0.0225 | 1.363 | 0.1679 |

## Modeller ve özellik önemi (kazanç; ilk 8)

- `cancelled-lgbm`: en iyi iterasyon 15 / eğitilen tur 1000 (tavan 1000, tavana ulaştı: True, durdurma metriği binary_logloss), 399.61 sn · day_of_year 13.2%, origin_p01i 12.9%, Origin 11.9%, origin_dwpf 9.2%, day_of_month 7.2%, Reporting_Airline 6.4%, days_to_holiday 5.4%, origin_wx_ts 4.8%
  - Val-A eğrisi `binary_logloss`: en iyi tur 15, değer 0.0671
  - Val-A eğrisi `auc`: en iyi tur 181, değer 0.6311
  - Val-A eğrisi `average_precision`: en iyi tur 8, değer 0.0419

Kazanç önemi sık bölünen/yüksek kardinaliteli özellikleri kayırır; permütasyon önemi (plan §7) bu koşuda hesaplanmadı: `python -m flight_delay.modeling.run_permutation --run-id run-20261120T173554Z`.

## Bilinmeyen kategoriler (eğitim penceresinde olmayan değerler → eksik)

- train: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_a: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_b: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
