# Ana modeller – T2 sözleşmesi (Val-A / Val-B, B1'e göre)

- Çalıştırma: `run-20261120T174502Z` · UTC: 2026-11-20T17:45:02.917664+00:00 · git: `c3ad8cf6d106ccd2519b73ec0e4aa049309ce8b3` (kirli: True)
- Okunan aylar: 2023-09 .. 2026-02 (30 ay); **son test (2026-03..08) okunmadı**.
- Fit penceresi: 2023-09-01 .. 2025-08-31 · özellik sayısı: 60 · sözleşme özeti: `b3ea6b364a0e`
- Erken durdurma: **val_a** (plan §4.3; LightGBM'in Val-A sonuçları bu yüzden hafif iyimser) · F1 eşiği: **val_b** (Val-B'de örneklem içi) · Val-B başka hiçbir seçimde kullanılmadı.
- Arama: 0 deneme (arama yok; parametreler `run-20261119T182216Z` koşusundan)
- Çıkarılan özellikler: month, day_of_year, day_of_month, days_to_holiday, holiday_week · iptal erken durdurma metriği: `binary_logloss` · kantil tur tavanı: 1000 · aralık modelleri (α 0,10/0,90): hayır
- Süreler (sn): {'load': 3.8, 'search': 0.0, 'b1_reference': 3.8, 'history': 30.3, 'matrices': 24.5, 'classification': 582.8, 'quantiles': 0.0} · tepe bellek (RSS): 6.475 GB
- Model dosyaları: `deliverables/models/run-20261120T174502Z` · git'te yok sayılıyor mu: True
- MLflow: kapalı (--mlflow off)

Notlar: Farklar nokta tahminidir; GA ve anlamlılık (gün blok bootstrap, plan §5.2) son test içindir. Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). Kantiller satır başına sıralandı (plan §3.3); B1 kantilleri tanımlandığı gibi (sıralamasız).

- Seçilen parametreler (arr_del15, from run-20261119T182216Z): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`

## İptal (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1506008 | 0.0128 | 0.6166 | - | 0.0225 | - | 0.0126 | 0.0000 | 0.0686 | - | 0.0033 | -0.0001 | 0.479 | 0.0431 |
| val_a | LightGBM | 1506008 | 0.0128 | 0.6962 | +0.0796 | 0.0712 | +0.0487 | 0.0123 | 0.0249 | 0.0636 | -0.0050 | 0.0031 | -0.0031 | 1.047 | 0.1385 |
| val_b | B1 | 689119 | 0.0367 | 0.6192 | - | 0.0568 | - | 0.0357 | 0.0000 | 0.1719 | - | 0.0239 | -0.0239 | 0.497 | 0.1041 |
| val_b | LightGBM | 689119 | 0.0367 | 0.8385 | +0.2193 | 0.4147 | +0.3579 | 0.0306 | 0.1425 | 0.1271 | -0.0448 | 0.0214 | -0.0214 | 1.352 | 0.4415 |

## Modeller ve özellik önemi (kazanç; ilk 8)

- `cancelled-lgbm`: en iyi iterasyon 73 / eğitilen tur 1000 (tavan 1000, tavana ulaştı: True, durdurma metriği binary_logloss), 455.42 sn · Origin 14.7%, origin_dwpf 14.4%, origin_p01i 10.8%, origin_tmpf 7.3%, Reporting_Airline 6.7%, crs_dep_minute_of_day 4.6%, origin_ceiling_ft 4.4%, dest_dwpf 4.1%
  - Val-A eğrisi `binary_logloss`: en iyi tur 73, değer 0.0636
  - Val-A eğrisi `auc`: en iyi tur 86, değer 0.6966
  - Val-A eğrisi `average_precision`: en iyi tur 115, değer 0.0720

Kazanç önemi sık bölünen/yüksek kardinaliteli özellikleri kayırır; permütasyon önemi (plan §7) bu koşuda hesaplanmadı: `python -m flight_delay.modeling.run_permutation --run-id run-20261120T174502Z`.

## Bilinmeyen kategoriler (eğitim penceresinde olmayan değerler → eksik)

- train: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_a: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_b: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
