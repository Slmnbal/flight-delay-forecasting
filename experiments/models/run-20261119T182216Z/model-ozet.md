# Ana modeller – T2 sözleşmesi (Val-A / Val-B, B1'e göre)

- Çalıştırma: `run-20261119T182216Z` · UTC: 2026-11-19T18:22:16.620679+00:00 · git: `a8e41ddd77d547e64abf58256e5adb6d93d070f6` (kirli: True)
- Okunan aylar: 2023-09 .. 2026-02 (30 ay); **son test (2026-03..08) okunmadı**.
- Fit penceresi: 2023-09-01 .. 2025-08-31 · özellik sayısı: 65 · sözleşme özeti: `c86a71f835d8`
- Erken durdurma: **val_a** (plan §4.3; LightGBM'in Val-A sonuçları bu yüzden hafif iyimser) · F1 eşiği: **val_b** (Val-B'de örneklem içi) · Val-B başka hiçbir seçimde kullanılmadı.
- Arama: 8 deneme / 8 aday, bütçe 45.0 dk, bütçeyle durdu: False, süre 638.4 sn
- Süreler (sn): {'load': 4.0, 'search': 638.4, 'b1_reference': 4.7, 'history': 30.5, 'matrices': 22.9, 'classification': 610.8, 'quantiles': 1453.9} · tepe bellek (RSS): 6.536 GB
- Model dosyaları: `deliverables/models/run-20261119T182216Z` · git'te yok sayılıyor mu: True
- MLflow: kapalı (--mlflow off)

Notlar: Farklar nokta tahminidir; GA ve anlamlılık (gün blok bootstrap, plan §5.2) son test içindir. Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). Kantiller satır başına sıralandı (plan §3.3); B1 kantilleri tanımlandığı gibi (sıralamasız).

- Seçilen parametreler (arr_del15, fold search): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`
- Seçilen parametreler (arr_delay_q080, fold search): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`

## ArrDel15 (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 0.2228 | 0.6320 | - | 0.3086 | - | 0.1670 | 0.0000 | 0.5121 | - | 0.0100 | -0.0027 | 0.861 | 0.4016 |
| val_a | LightGBM | 1483504 | 0.2228 | 0.7057 | +0.0736 | 0.4285 | +0.1199 | 0.1586 | 0.0503 | 0.4912 | -0.0209 | 0.0538 | -0.0538 | 1.047 | 0.4464 |
| val_a | L | 1483504 | 0.2228 | 0.6885 | +0.0564 | 0.4008 | +0.0922 | 0.1612 | 0.0349 | 0.4986 | -0.0136 | 0.0505 | -0.0505 | 0.980 | 0.4331 |
| val_b | B1 | 662410 | 0.2131 | 0.6000 | - | 0.2750 | - | 0.1653 | 0.0000 | 0.5104 | - | 0.0274 | 0.0082 | 0.651 | 0.3719 |
| val_b | LightGBM | 662410 | 0.2131 | 0.6666 | +0.0666 | 0.3894 | +0.1144 | 0.1553 | 0.0605 | 0.4868 | -0.0236 | 0.0251 | -0.0160 | 0.782 | 0.4074 |
| val_b | L | 662410 | 0.2131 | 0.6532 | +0.0533 | 0.3669 | +0.0919 | 0.1576 | 0.0469 | 0.4930 | -0.0174 | 0.0201 | -0.0200 | 0.790 | 0.3987 |

## İptal (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1506008 | 0.0128 | 0.6166 | - | 0.0225 | - | 0.0126 | 0.0000 | 0.0686 | - | 0.0033 | -0.0001 | 0.479 | 0.0431 |
| val_a | LightGBM | 1506008 | 0.0128 | 0.6248 | +0.0082 | 0.0389 | +0.0165 | 0.0126 | 0.0042 | 0.0671 | -0.0015 | 0.0066 | -0.0026 | 1.676 | 0.0735 |
| val_a | L | 1506008 | 0.0128 | 0.6541 | +0.0375 | 0.0354 | +0.0130 | 0.0127 | -0.0013 | 0.0756 | +0.0070 | 0.0095 | -0.0095 | 0.579 | 0.0244 |
| val_b | B1 | 689119 | 0.0367 | 0.6192 | - | 0.0568 | - | 0.0357 | 0.0000 | 0.1719 | - | 0.0239 | -0.0239 | 0.497 | 0.1041 |
| val_b | LightGBM | 689119 | 0.0367 | 0.6879 | +0.0687 | 0.0917 | +0.0348 | 0.0354 | 0.0072 | 0.1621 | -0.0098 | 0.0239 | -0.0225 | 1.363 | 0.1679 |
| val_b | L | 689119 | 0.0367 | 0.7393 | +0.1202 | 0.2282 | +0.1713 | 0.0334 | 0.0655 | 0.1499 | -0.0221 | 0.0218 | -0.0218 | 0.967 | 0.2812 |

## Varış rötarı kantilleri (tamamlanan uçuşlar, dk)

| Küme | Model | n | Pinball P50 | Δ | Pinball P80 | Δ | Pinball P95 | Δ | MAE P50 | Kapsama P80 | Kapsama P95 | Kesişme (ham) | Kesişme (sonra) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 11.931 | - | 12.822 | - | 7.964 | - | 23.863 | 0.8001 | 0.9488 | 0.0001 | 0.0001 |
| val_a | LightGBM | 1483504 | 11.428 | -0.503 | 12.257 | -0.564 | 7.746 | -0.218 | 22.856 | 0.7389 | 0.9178 | 0.0000 | 0.0000 |
| val_b | B1 | 662410 | 12.193 | - | 13.067 | - | 8.231 | - | 24.387 | 0.8063 | 0.9498 | 0.0002 | 0.0002 |
| val_b | LightGBM | 662410 | 11.731 | -0.463 | 12.402 | -0.665 | 7.786 | -0.446 | 23.461 | 0.7734 | 0.9332 | 0.0000 | 0.0000 |

Δ = model − B1; kayıplarda (log-loss, pinball, Brier) negatif daha iyidir.

## Modeller ve özellik önemi (kazanç; ilk 8)

- `arr_del15-lgbm`: en iyi iterasyon 1154 (tavan 2000, tavana ulaştı: False), 447.65 sn · te_route_hour_arrdel15 16.8%, day_of_year 9.3%, Origin 9.3%, origin_dwpf 6.4%, Reporting_Airline 5.6%, day_of_month 4.3%, days_to_holiday 4.1%, crs_dep_minute_of_day 3.5%
- `arr_del15-logreg`: lojistik, 1348189 satır (whole-day sample 15% of the fit window), 17.06 sn, yakınsama uyarısı: 0
- `cancelled-lgbm`: en iyi iterasyon 15 (tavan 2000, tavana ulaştı: False), 46.72 sn · day_of_year 13.2%, origin_p01i 12.9%, Origin 11.9%, origin_dwpf 9.2%, day_of_month 7.2%, Reporting_Airline 6.4%, days_to_holiday 5.4%, origin_wx_ts 4.8%
- `cancelled-logreg`: lojistik, 1367150 satır (whole-day sample 15% of the fit window), 12.47 sn, yakınsama uyarısı: 0
- `arr_delay_q050-lgbm`: en iyi iterasyon 1999 (tavan 2000, tavana ulaştı: False), 686.3 sn · hist_route_hour_p50 12.4%, Origin 12.0%, day_of_year 8.3%, schedule_excess_min 6.9%, Reporting_Airline 5.9%, days_to_holiday 4.3%, day_of_month 4.1%, origin_dwpf 3.3%
- `arr_delay_q080-lgbm`: en iyi iterasyon 1025 (tavan 2000, tavana ulaştı: False), 404.41 sn · te_route_hour_arrdel15 15.6%, Origin 10.1%, day_of_year 9.4%, origin_dwpf 6.4%, Reporting_Airline 5.7%, day_of_month 4.1%, days_to_holiday 3.9%, hist_route_hour_p80 3.7%
- `arr_delay_q095-lgbm`: en iyi iterasyon 396 (tavan 2000, tavana ulaştı: False), 190.47 sn · Origin 11.1%, hist_route_hour_p95 10.5%, day_of_year 9.0%, origin_dwpf 8.8%, Reporting_Airline 7.1%, origin_wx_ts 5.4%, day_of_month 4.6%, days_to_holiday 3.9%

Kazanç önemi sık bölünen/yüksek kardinaliteli özellikleri kayırır; permütasyon önemi (plan §7) sonraki adımda.

## Bilinmeyen kategoriler (eğitim penceresinde olmayan değerler → eksik)

- train: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_a: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_b: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
