# Ana modeller – T2 sözleşmesi (Val-A / Val-B, B1'e göre)

- Çalıştırma: `run-20261121T082853Z` · UTC: 2026-11-21T08:28:53.120781+00:00 · git: `20a81c7b52d7bf9da26da7ba50730b071f081ad2` (kirli: True)
- Okunan aylar: 2023-09 .. 2026-02 (30 ay); **son test (2026-03..08) okunmadı**.
- Fit penceresi: 2023-09-01 .. 2025-08-31 · özellik sayısı: 60 · sözleşme özeti: `b3ea6b364a0e`
- Erken durdurma: **val_a** (plan §4.3; LightGBM'in Val-A sonuçları bu yüzden hafif iyimser) · F1 eşiği: **val_b** (Val-B'de örneklem içi).
- Val-B'nin kullanımları (red-team M1): bu koşuda F1 eşiği; koşudan sonra kalibratör ve conformal ofset fit'i (`run_calibration`), permütasyon önemi (`run_permutation`) ve takvim özelliği hipotezinin kaynağı. Bu yüzden Val-B sayıları da seçimlerden tamamen bağımsız değildir (F1 örneklem içidir; takvim hipotezi Val-B'den doğduğu için takvimsiz modellerin Val-B sayıları iyimserdir); bağımsız ölçüm yalnızca son testtir.
- Arama: 0 deneme (arama yok; parametreler `run-20261119T182216Z` koşusundan)
- Çıkarılan özellikler: month, day_of_year, day_of_month, days_to_holiday, holiday_week · iptal erken durdurma metriği: `binary_logloss` · kantil tur tavanı: 5000 · aralık modelleri (α 0,10/0,90): evet
- Süreler (sn): {'load': 3.7, 'search': 0.0, 'b1_reference': 4.1, 'history': 27.9, 'matrices': 18.5, 'classification': 454.6, 'quantiles': 4366.5} · tepe bellek (RSS): 7.512 GB
- Model dosyaları: `deliverables/models/run-20261121T082853Z` · git'te yok sayılıyor mu: True
- MLflow: 6 koşu kaydedildi (deney öneki havayolu-ds/modeling/...)

Notlar: Farklar nokta tahminidir; GA ve anlamlılık (gün blok bootstrap, plan §5.2) son test içindir. Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). Kantiller satır başına sıralandı (plan §3.3); B1 kantilleri tanımlandığı gibi (sıralamasız).

- Seçilen parametreler (arr_del15, from run-20261119T182216Z): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`
- Seçilen parametreler (arr_delay_q080, from run-20261119T182216Z): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`

## ArrDel15 (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 0.2228 | 0.6320 | - | 0.3086 | - | 0.1670 | 0.0000 | 0.5121 | - | 0.0100 | -0.0027 | 0.861 | 0.4016 |
| val_a | LightGBM | 1483504 | 0.2228 | 0.7041 | +0.0720 | 0.4290 | +0.1204 | 0.1558 | 0.0670 | 0.4831 | -0.0290 | 0.0249 | -0.0249 | 0.982 | 0.4491 |
| val_b | B1 | 662410 | 0.2131 | 0.6000 | - | 0.2750 | - | 0.1653 | 0.0000 | 0.5104 | - | 0.0274 | 0.0082 | 0.651 | 0.3719 |
| val_b | LightGBM | 662410 | 0.2131 | 0.6998 | +0.0999 | 0.4192 | +0.1442 | 0.1508 | 0.0878 | 0.4718 | -0.0386 | 0.0148 | -0.0148 | 0.925 | 0.4356 |

## Varış rötarı kantilleri (tamamlanan uçuşlar, dk)

| Küme | Model | n | Pinball P50 | Δ | Pinball P80 | Δ | Pinball P95 | Δ | MAE P50 | Kapsama P80 | Kapsama P95 | Kesişme (ham) | Kesişme (sonra) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 11.931 | - | 12.822 | - | 7.964 | - | 23.863 | 0.8001 | 0.9488 | 0.0001 | 0.0001 |
| val_a | LightGBM | 1483504 | 11.349 | -0.583 | 12.037 | -0.785 | 7.432 | -0.532 | 22.697 | 0.7697 | 0.9350 | 0.0001 | 0.0000 |
| val_b | B1 | 662410 | 12.193 | - | 13.067 | - | 8.231 | - | 24.387 | 0.8063 | 0.9498 | 0.0002 | 0.0002 |
| val_b | LightGBM | 662410 | 11.503 | -0.690 | 12.076 | -0.992 | 7.529 | -0.702 | 23.006 | 0.7783 | 0.9389 | 0.0000 | 0.0000 |

Δ = model − B1; kayıplarda (log-loss, pinball, Brier) negatif daha iyidir.

### İki yönlü %80 aralık (α 0,10 / 0,90; ham, conformal öncesi)

| Küme | Model | Kapsama | Ort. genişlik (dk) | Pinball P10 | Pinball P90 | Kesişme (ham) |
|---|---|---|---|---|---|---|
| val_a | B1 | 0.7953 | 67.4 | 3.565 | 10.580 | 0.0000 |
| val_a | LightGBM | 0.7696 | 56.5 | 3.345 | 9.893 | 0.0000 |
| val_b | B1 | 0.7569 | 67.9 | 3.771 | 10.847 | 0.0000 |
| val_b | LightGBM | 0.7608 | 57.9 | 3.483 | 9.945 | 0.0000 |

Hedef kapsama 0,80 (plan §5.3 ikincil: [0,78; 0,82]); conformal ayar `run_calibration`'da.

## Modeller ve özellik önemi (kazanç; ilk 8)

- `arr_del15-lgbm`: en iyi iterasyon 1409 / eğitilen tur 1509 (tavan 2000, tavana ulaştı: False, durdurma metriği binary_logloss), 389.82 sn · te_route_hour_arrdel15 18.2%, Origin 9.8%, origin_dwpf 9.1%, Reporting_Airline 5.9%, planned_departures_origin_day 5.2%, origin_tmpf 5.2%, crs_dep_minute_of_day 4.6%, origin_p01i 3.8%
- `arr_delay_q010-lgbm`: en iyi iterasyon 5000 / eğitilen tur 5000 (tavan 5000, tavana ulaştı: True, durdurma metriği quantile), 1143.0 sn · schedule_excess_min 24.4%, Origin 13.9%, CRSElapsedTime 6.7%, Reporting_Airline 5.7%, hist_route_hour_p50 3.6%, planned_departures_origin_day 3.4%, origin_tmpf 3.3%, origin_dwpf 2.8%
- `arr_delay_q050-lgbm`: en iyi iterasyon 4486 / eğitilen tur 4586 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 1224.89 sn · hist_route_hour_p50 12.5%, Origin 11.4%, schedule_excess_min 6.8%, Reporting_Airline 6.3%, origin_dwpf 5.4%, planned_departures_origin_day 5.2%, origin_tmpf 4.8%, crs_dep_minute_of_day 3.7%
- `arr_delay_q080-lgbm`: en iyi iterasyon 2320 / eğitilen tur 2420 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 668.76 sn · te_route_hour_arrdel15 16.1%, Origin 10.7%, origin_dwpf 8.6%, Reporting_Airline 6.0%, planned_departures_origin_day 5.1%, origin_tmpf 5.0%, crs_dep_minute_of_day 4.3%, origin_ceiling_ft 3.3%
- `arr_delay_q090-lgbm`: en iyi iterasyon 1181 / eğitilen tur 1281 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 381.72 sn · Origin 11.1%, origin_dwpf 10.9%, te_route_hour_arrdel15 7.1%, Reporting_Airline 6.1%, hist_route_hour_p80 5.9%, hist_route_hour_p95 4.9%, planned_departures_origin_day 4.8%, crs_dep_minute_of_day 4.8%
- `arr_delay_q095-lgbm`: en iyi iterasyon 732 / eğitilen tur 832 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 304.74 sn · origin_dwpf 11.8%, Origin 11.7%, hist_route_hour_p95 11.0%, Reporting_Airline 6.7%, origin_wx_ts 5.5%, origin_tmpf 5.0%, planned_departures_origin_day 4.7%, crs_dep_minute_of_day 3.8%

Kazanç önemi sık bölünen/yüksek kardinaliteli özellikleri kayırır; permütasyon önemi (plan §7) bu koşuda hesaplanmadı: `python -m flight_delay.modeling.run_permutation --run-id run-20261121T082853Z`.

## Bilinmeyen kategoriler (eğitim penceresinde olmayan değerler → eksik)

- train: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_a: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_b: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
