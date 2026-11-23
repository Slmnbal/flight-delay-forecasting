# Ana modeller – plan sözleşmesi (Val-A / Val-B, B1'e göre)

- Çalıştırma: `run-20261121T080035Z` · UTC: 2026-11-21T08:00:35.059124+00:00 · git: `20a81c7b52d7bf9da26da7ba50730b071f081ad2` (kirli: True)
- Okunan aylar: 2023-09 .. 2026-02 (30 ay); **son test (2026-03..08) okunmadı**.
- Fit penceresi: 2023-09-01 .. 2025-08-31 · özellik sayısı: 29 · sözleşme özeti: `73927af93df3`
- Erken durdurma: **val_a** (plan §4.3; LightGBM'in Val-A sonuçları bu yüzden hafif iyimser) · F1 eşiği: **val_b** (Val-B'de örneklem içi).
- Val-B'nin kullanımları (red-team M1): bu koşuda F1 eşiği; koşudan sonra kalibratör ve conformal ofset fit'i (`run_calibration`), permütasyon önemi (`run_permutation`) ve takvim özelliği hipotezinin kaynağı. Bu yüzden Val-B sayıları da seçimlerden tamamen bağımsız değildir (F1 örneklem içidir; takvim hipotezi Val-B'den doğduğu için takvimsiz modellerin Val-B sayıları iyimserdir); bağımsız ölçüm yalnızca son testtir.
- Arama: 0 deneme (arama yok; parametreler `run-20261119T182216Z` koşusundan, kaynak sözleşme T2)
- Çıkarılan özellikler: month, day_of_year, day_of_month, days_to_holiday, holiday_week · iptal erken durdurma metriği: `binary_logloss` · kantil tur tavanı: 5000 · aralık modelleri (α 0,10/0,90): evet
- Süreler (sn): {'load': 4.3, 'search': 0.0, 'b1_reference': 4.5, 'history': 33.7, 'matrices': 14.2, 'classification': 201.5, 'quantiles': 1028.6} · tepe bellek (RSS): 5.636 GB
- Model dosyaları: `deliverables/models/run-20261121T080035Z` · git'te yok sayılıyor mu: True
- MLflow: 7 koşu kaydedildi (deney öneki havayolu-ds/modeling/...)

Notlar: Farklar nokta tahminidir; GA ve anlamlılık (gün blok bootstrap, plan §5.2) son test içindir. Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). Kantiller satır başına sıralandı (plan §3.3); B1 kantilleri tanımlandığı gibi (sıralamasız).

- Seçilen parametreler (arr_del15, from run-20261119T182216Z (contract T2)): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`
- Seçilen parametreler (arr_delay_q080, from run-20261119T182216Z (contract T2)): `{"bagging_fraction": 0.7, "cat_smooth": 50, "feature_fraction": 0.9, "lambda_l2": 10.0, "learning_rate": 0.03, "max_bin": 63, "min_child_samples": 1000, "num_leaves": 127}`

## ArrDel15 (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 0.2228 | 0.6320 | - | 0.3086 | - | 0.1670 | 0.0000 | 0.5121 | - | 0.0100 | -0.0027 | 0.861 | 0.4016 |
| val_a | LightGBM | 1483504 | 0.2228 | 0.6543 | +0.0223 | 0.3350 | +0.0264 | 0.1646 | 0.0146 | 0.5051 | -0.0070 | 0.0106 | -0.0056 | 0.908 | 0.4088 |
| val_b | B1 | 662410 | 0.2131 | 0.6000 | - | 0.2750 | - | 0.1653 | 0.0000 | 0.5104 | - | 0.0274 | 0.0082 | 0.651 | 0.3719 |
| val_b | LightGBM | 662410 | 0.2131 | 0.6250 | +0.0250 | 0.3043 | +0.0294 | 0.1624 | 0.0179 | 0.5021 | -0.0083 | 0.0179 | -0.0084 | 0.802 | 0.3828 |

## İptal (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1506008 | 0.0128 | 0.6166 | - | 0.0225 | - | 0.0126 | 0.0000 | 0.0686 | - | 0.0033 | -0.0001 | 0.479 | 0.0431 |
| val_a | LightGBM | 1506008 | 0.0128 | 0.6159 | -0.0006 | 0.0219 | -0.0006 | 0.0126 | 0.0012 | 0.0675 | -0.0011 | 0.0009 | -0.0003 | 0.989 | 0.0440 |
| val_b | B1 | 689119 | 0.0367 | 0.6192 | - | 0.0568 | - | 0.0357 | 0.0000 | 0.1719 | - | 0.0239 | -0.0239 | 0.497 | 0.1041 |
| val_b | LightGBM | 689119 | 0.0367 | 0.6323 | +0.0131 | 0.0585 | +0.0016 | 0.0358 | -0.0020 | 0.1693 | -0.0027 | 0.0241 | -0.0241 | 1.127 | 0.1077 |

## Varış rötarı kantilleri (tamamlanan uçuşlar, dk)

| Küme | Model | n | Pinball P50 | Δ | Pinball P80 | Δ | Pinball P95 | Δ | MAE P50 | Kapsama P80 | Kapsama P95 | Kesişme (ham) | Kesişme (sonra) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 11.931 | - | 12.822 | - | 7.964 | - | 23.863 | 0.8001 | 0.9488 | 0.0001 | 0.0001 |
| val_a | LightGBM | 1483504 | 11.743 | -0.188 | 12.675 | -0.146 | 7.830 | -0.134 | 23.487 | 0.7953 | 0.9468 | 0.0000 | 0.0000 |
| val_b | B1 | 662410 | 12.193 | - | 13.067 | - | 8.231 | - | 24.387 | 0.8063 | 0.9498 | 0.0002 | 0.0002 |
| val_b | LightGBM | 662410 | 11.993 | -0.200 | 12.883 | -0.184 | 8.063 | -0.168 | 23.986 | 0.7904 | 0.9463 | 0.0000 | 0.0000 |

Δ = model − B1; kayıplarda (log-loss, pinball, Brier) negatif daha iyidir.

### İki yönlü %80 aralık (α 0,10 / 0,90; ham, conformal öncesi)

| Küme | Model | Kapsama | Ort. genişlik (dk) | Pinball P10 | Pinball P90 | Kesişme (ham) |
|---|---|---|---|---|---|---|
| val_a | B1 | 0.7953 | 67.4 | 3.565 | 10.580 | 0.0000 |
| val_a | LightGBM | 0.7887 | 65.2 | 3.408 | 10.437 | 0.0000 |
| val_b | B1 | 0.7569 | 67.9 | 3.771 | 10.847 | 0.0000 |
| val_b | LightGBM | 0.7809 | 65.4 | 3.555 | 10.663 | 0.0000 |

Hedef kapsama 0,80 (plan §5.3 ikincil: [0,78; 0,82]); conformal ayar `run_calibration`'da.

## Modeller ve özellik önemi (kazanç; ilk 8)

- `arr_del15-lgbm`: en iyi iterasyon 332 / eğitilen tur 432 (tavan 2000, tavana ulaştı: False, durdurma metriği binary_logloss), 129.85 sn · te_route_hour_arrdel15 39.7%, planned_departures_origin_day 9.8%, Origin 9.5%, Reporting_Airline 7.5%, te_carrier_origin_arrdel15 6.1%, crs_dep_minute_of_day 3.8%, day_of_week 3.6%, support_n_carrier_origin_arrdel15 3.3%
- `cancelled-lgbm`: en iyi iterasyon 36 / eğitilen tur 136 (tavan 2000, tavana ulaştı: False, durdurma metriği binary_logloss), 39.68 sn · Origin 21.4%, planned_departures_origin_day 14.7%, te_carrier_origin_arrdel15 11.8%, Reporting_Airline 11.5%, day_of_week 8.4%, crs_dep_minute_of_day 7.6%, support_n_carrier_origin_arrdel15 6.9%, hist_route_hour_p95 4.2%
- `arr_delay_q010-lgbm`: en iyi iterasyon 1430 / eğitilen tur 1530 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 385.15 sn · schedule_excess_min 35.6%, Origin 15.9%, CRSElapsedTime 9.8%, Reporting_Airline 6.2%, hist_route_hour_p50 4.6%, planned_departures_origin_day 4.5%, te_carrier_origin_arrdel15 2.8%, support_n_carrier_origin_arrdel15 2.4%
- `arr_delay_q050-lgbm`: en iyi iterasyon 719 / eğitilen tur 819 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 227.87 sn · hist_route_hour_p50 24.8%, schedule_excess_min 12.4%, Origin 11.2%, Reporting_Airline 8.2%, planned_departures_origin_day 8.1%, te_carrier_origin_arrdel15 5.2%, crs_dep_minute_of_day 3.8%, day_of_week 3.2%
- `arr_delay_q080-lgbm`: en iyi iterasyon 319 / eğitilen tur 419 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 133.72 sn · te_route_hour_arrdel15 38.1%, planned_departures_origin_day 9.7%, Origin 9.3%, Reporting_Airline 7.3%, te_carrier_origin_arrdel15 5.9%, hist_route_hour_p80 5.9%, crs_dep_minute_of_day 3.6%, day_of_week 3.4%
- `arr_delay_q090-lgbm`: en iyi iterasyon 289 / eğitilen tur 389 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 81.45 sn · te_route_hour_arrdel15 15.1%, hist_route_hour_p80 14.9%, hist_route_hour_p95 10.9%, planned_departures_origin_day 10.9%, Origin 9.5%, Reporting_Airline 8.3%, te_carrier_origin_arrdel15 6.3%, support_n_carrier_origin_arrdel15 4.1%
- `arr_delay_q095-lgbm`: en iyi iterasyon 217 / eğitilen tur 317 (tavan 5000, tavana ulaştı: False, durdurma metriği quantile), 67.48 sn · hist_route_hour_p95 30.0%, planned_departures_origin_day 12.1%, Origin 10.4%, Reporting_Airline 10.0%, te_carrier_origin_arrdel15 6.9%, support_n_carrier_origin_arrdel15 4.7%, crs_dep_minute_of_day 3.7%, day_of_week 3.5%

Kazanç önemi sık bölünen/yüksek kardinaliteli özellikleri kayırır; permütasyon önemi (plan §7) bu koşuda hesaplanmadı: `python -m flight_delay.modeling.run_permutation --run-id run-20261121T080035Z`.

## Bilinmeyen kategoriler (eğitim penceresinde olmayan değerler → eksik)

- train: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_a: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_b: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
