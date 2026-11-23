# Ana modeller – T2 sözleşmesi (Val-A / Val-B, B1'e göre)

- Çalıştırma: `run-20261120T175822Z` · UTC: 2026-11-20T17:58:22.113147+00:00 · git: `61ddb4f236b98e6873b5ffa594c85778eaf5547a` (kirli: True)
- Okunan aylar: 2023-09 .. 2026-02 (30 ay); **son test (2026-03..08) okunmadı**.
- Fit penceresi: 2023-09-01 .. 2025-08-31 · özellik sayısı: 65 · sözleşme özeti: `c86a71f835d8`
- Erken durdurma: **val_a** (plan §4.3; LightGBM'in Val-A sonuçları bu yüzden hafif iyimser) · F1 eşiği: **val_b** (Val-B'de örneklem içi) · Val-B başka hiçbir seçimde kullanılmadı.
- Arama: 0 deneme (arama yok; parametreler `run-20261119T182216Z` koşusundan)
- Çıkarılan özellikler: yok · iptal erken durdurma metriği: `binary_logloss` · kantil tur tavanı: 5000 · aralık modelleri (α 0,10/0,90): evet
- Süreler (sn): {'load': 3.7, 'search': 0.0, 'b1_reference': 4.1, 'history': 28.7, 'matrices': 20.1, 'classification': 710.2, 'quantiles': 2886.6} · tepe bellek (RSS): 7.255 GB
- Model dosyaları: `deliverables/models/run-20261120T175822Z` · git'te yok sayılıyor mu: True
- MLflow: 9 koşu kaydedildi (deney öneki havayolu-ds/modeling/...)

Notlar: Farklar nokta tahminidir; GA ve anlamlılık (gün blok bootstrap, plan §5.2) son test içindir. Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). Kantiller satır başına sıralandı (plan §3.3); B1 kantilleri tanımlandığı gibi (sıralamasız).

- Seçilen parametreler (arr_del15, from run-20261119T182216Z): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`
- Seçilen parametreler (arr_delay_q080, from run-20261119T182216Z): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`

## ArrDel15 (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 0.2228 | 0.6320 | - | 0.3086 | - | 0.1670 | 0.0000 | 0.5121 | - | 0.0100 | -0.0027 | 0.861 | 0.4016 |
| val_a | LightGBM | 1483504 | 0.2228 | 0.7057 | +0.0736 | 0.4285 | +0.1199 | 0.1586 | 0.0503 | 0.4912 | -0.0209 | 0.0538 | -0.0538 | 1.047 | 0.4464 |
| val_a | L | 1483504 | 0.2228 | 0.6885 | +0.0565 | 0.4008 | +0.0922 | 0.1613 | 0.0346 | 0.4987 | -0.0135 | 0.0508 | -0.0508 | 0.981 | 0.4344 |
| val_b | B1 | 662410 | 0.2131 | 0.6000 | - | 0.2750 | - | 0.1653 | 0.0000 | 0.5104 | - | 0.0274 | 0.0082 | 0.651 | 0.3719 |
| val_b | LightGBM | 662410 | 0.2131 | 0.6666 | +0.0666 | 0.3894 | +0.1144 | 0.1553 | 0.0605 | 0.4868 | -0.0236 | 0.0251 | -0.0160 | 0.782 | 0.4074 |
| val_b | L | 662410 | 0.2131 | 0.6533 | +0.0533 | 0.3670 | +0.0920 | 0.1576 | 0.0468 | 0.4931 | -0.0174 | 0.0204 | -0.0203 | 0.790 | 0.3987 |

## İptal (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1506008 | 0.0128 | 0.6166 | - | 0.0225 | - | 0.0126 | 0.0000 | 0.0686 | - | 0.0033 | -0.0001 | 0.479 | 0.0431 |
| val_a | LightGBM | 1506008 | 0.0128 | 0.6248 | +0.0082 | 0.0389 | +0.0165 | 0.0126 | 0.0042 | 0.0671 | -0.0015 | 0.0066 | -0.0026 | 1.676 | 0.0735 |
| val_a | L | 1506008 | 0.0128 | 0.6540 | +0.0375 | 0.0354 | +0.0129 | 0.0127 | -0.0014 | 0.0756 | +0.0070 | 0.0095 | -0.0095 | 0.578 | 0.0244 |
| val_b | B1 | 689119 | 0.0367 | 0.6192 | - | 0.0568 | - | 0.0357 | 0.0000 | 0.1719 | - | 0.0239 | -0.0239 | 0.497 | 0.1041 |
| val_b | LightGBM | 689119 | 0.0367 | 0.6879 | +0.0687 | 0.0917 | +0.0348 | 0.0354 | 0.0072 | 0.1621 | -0.0098 | 0.0239 | -0.0225 | 1.363 | 0.1679 |
| val_b | L | 689119 | 0.0367 | 0.7394 | +0.1202 | 0.2283 | +0.1715 | 0.0334 | 0.0655 | 0.1498 | -0.0222 | 0.0218 | -0.0218 | 0.968 | 0.2813 |

## Varış rötarı kantilleri (tamamlanan uçuşlar, dk)

| Küme | Model | n | Pinball P50 | Δ | Pinball P80 | Δ | Pinball P95 | Δ | MAE P50 | Kapsama P80 | Kapsama P95 | Kesişme (ham) | Kesişme (sonra) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 11.931 | - | 12.822 | - | 7.964 | - | 23.863 | 0.8001 | 0.9488 | 0.0001 | 0.0001 |
| val_a | LightGBM | 1483504 | 11.418 | -0.514 | 12.257 | -0.564 | 7.746 | -0.218 | 22.835 | 0.7389 | 0.9178 | 0.0000 | 0.0000 |
| val_b | B1 | 662410 | 12.193 | - | 13.067 | - | 8.231 | - | 24.387 | 0.8063 | 0.9498 | 0.0002 | 0.0002 |
| val_b | LightGBM | 662410 | 11.733 | -0.460 | 12.402 | -0.665 | 7.786 | -0.446 | 23.466 | 0.7734 | 0.9332 | 0.0000 | 0.0000 |

Δ = model − B1; kayıplarda (log-loss, pinball, Brier) negatif daha iyidir.

### İki yönlü %80 aralık (α 0,10 / 0,90; ham, conformal öncesi)

| Küme | Model | Kapsama | Ort. genişlik (dk) | Pinball P10 | Pinball P90 | Kesişme (ham) |
|---|---|---|---|---|---|---|
| val_a | B1 | 0.7953 | 67.4 | 3.565 | 10.580 | 0.0000 |
| val_a | LightGBM | 0.7552 | 49.8 | 3.350 | 10.192 | 0.0000 |
| val_b | B1 | 0.7569 | 67.9 | 3.771 | 10.847 | 0.0000 |
| val_b | LightGBM | 0.7483 | 57.2 | 3.534 | 10.278 | 0.0000 |

Hedef kapsama 0,80 (plan §5.3 ikincil: [0,78; 0,82]); conformal ayar `run_calibration`'da.

## Modeller ve özellik önemi (kazanç; ilk 8)

- `arr_del15-lgbm`: en iyi iterasyon 1154 / eğitilen tur 1254 (tavan 2000, tavana ulaştı: False, durdurma metriği binary_logloss), 516.96 sn · te_route_hour_arrdel15 16.8%, day_of_year 9.3%, Origin 9.3%, origin_dwpf 6.4%, Reporting_Airline 5.6%, day_of_month 4.3%, days_to_holiday 4.1%, crs_dep_minute_of_day 3.5%
- `arr_del15-logreg`: lojistik, 1348189 satır (whole-day sample 15% of the fit window), 21.28 sn, yakınsama uyarısı: 0, fit aralığına kırpma: min/maks
  - val_a: fit aralığı dışında (kırpıldı): support_n_origin_hour_taxiout 8.6%, day_of_year 1.6%, planned_departures_origin_day 0.7%, support_n_route_hour_elapsed 0.2%, support_n_route_hour_p80 0.1%
  - val_b: fit aralığı dışında (kırpıldı): support_n_origin_hour_taxiout 8.5%, day_of_year 3.6%, support_n_route_hour_elapsed 0.3%, support_n_route_hour_p80 0.1%, planned_departures_origin_hour 0.1%
- `cancelled-lgbm`: en iyi iterasyon 15 / eğitilen tur 115 (tavan 2000, tavana ulaştı: False, durdurma metriği binary_logloss), 52.55 sn · day_of_year 13.2%, origin_p01i 12.9%, Origin 11.9%, origin_dwpf 9.2%, day_of_month 7.2%, Reporting_Airline 6.4%, days_to_holiday 5.4%, origin_wx_ts 4.8%
- `cancelled-logreg`: lojistik, 1367150 satır (whole-day sample 15% of the fit window), 13.34 sn, yakınsama uyarısı: 0, fit aralığına kırpma: min/maks
  - val_a: fit aralığı dışında (kırpıldı): support_n_origin_hour_taxiout 8.6%, day_of_year 1.6%, planned_departures_origin_day 0.7%, support_n_route_hour_elapsed 0.2%, support_n_route_hour_p80 0.1%
  - val_b: fit aralığı dışında (kırpıldı): support_n_origin_hour_taxiout 8.4%, day_of_year 3.5%, support_n_route_hour_elapsed 0.3%, support_n_route_hour_p80 0.1%, planned_departures_origin_hour 0.1%
- `arr_delay_q010-lgbm`: en iyi iterasyon 2002 / eğitilen tur 2102 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 769.32 sn · schedule_excess_min 26.9%, Origin 15.5%, CRSElapsedTime 7.0%, day_of_year 5.5%, Reporting_Airline 5.1%, hist_route_hour_p50 3.5%, days_to_holiday 2.8%, day_of_month 2.7%
- `arr_delay_q050-lgbm`: en iyi iterasyon 2938 / eğitilen tur 3038 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 966.24 sn · Origin 12.2%, hist_route_hour_p50 11.4%, day_of_year 8.1%, schedule_excess_min 6.4%, Reporting_Airline 5.8%, days_to_holiday 4.4%, day_of_month 4.3%, origin_dwpf 3.3%
- `arr_delay_q080-lgbm`: en iyi iterasyon 1025 / eğitilen tur 1125 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 397.38 sn · te_route_hour_arrdel15 15.6%, Origin 10.1%, day_of_year 9.4%, origin_dwpf 6.4%, Reporting_Airline 5.7%, day_of_month 4.1%, days_to_holiday 3.9%, hist_route_hour_p80 3.7%
- `arr_delay_q090-lgbm`: en iyi iterasyon 622 / eğitilen tur 722 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 247.31 sn · Origin 10.6%, day_of_year 9.4%, origin_dwpf 8.2%, Reporting_Airline 6.2%, hist_route_hour_p80 6.1%, te_route_hour_arrdel15 5.8%, hist_route_hour_p95 5.1%, day_of_month 4.3%
- `arr_delay_q095-lgbm`: en iyi iterasyon 396 / eğitilen tur 496 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 174.11 sn · Origin 11.1%, hist_route_hour_p95 10.5%, day_of_year 9.0%, origin_dwpf 8.8%, Reporting_Airline 7.1%, origin_wx_ts 5.4%, day_of_month 4.6%, days_to_holiday 3.9%

Kazanç önemi sık bölünen/yüksek kardinaliteli özellikleri kayırır; permütasyon önemi (plan §7) bu koşuda hesaplanmadı: `python -m flight_delay.modeling.run_permutation --run-id run-20261120T175822Z`.

## Bilinmeyen kategoriler (eğitim penceresinde olmayan değerler → eksik)

- train: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_a: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_b: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
