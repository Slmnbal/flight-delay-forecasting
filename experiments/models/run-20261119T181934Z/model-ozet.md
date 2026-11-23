> **SIZINTI ALARMI:** en az bir modelde tek bir özellik toplam kazancın %50'sinden fazlasını taşıyor. Sonuçlar inceleme bitene kadar raporlanmamalı (data-leakage-prevention). Ayrıntı: JSON `leakage_alarm`.

# Ana modeller – T2 sözleşmesi (Val-A / Val-B, B1'e göre)

- Çalıştırma: `run-20261119T181934Z` · UTC: 2026-11-19T18:19:34.963471+00:00 · git: `8f2488982bcb014572047a731918f6cf31d9a767` (kirli: True)
- Okunan aylar: 2024-12 .. 2026-02 (15 ay); **son test (2026-03..08) okunmadı**.
- Fit penceresi: 2025-06-01 .. 2025-08-31 · özellik sayısı: 65 · sözleşme özeti: `c86a71f835d8`
- Erken durdurma: **val_a** (plan §4.3; LightGBM'in Val-A sonuçları bu yüzden hafif iyimser) · F1 eşiği: **val_b** (Val-B'de örneklem içi) · Val-B başka hiçbir seçimde kullanılmadı.
- Arama: 2 deneme / 2 aday, bütçe 5.0 dk, bütçeyle durdu: False, süre 45.3 sn
- Süreler (sn): {'load': 1.9, 'search': 45.3, 'b1_reference': 1.1, 'history': 3.7, 'matrices': 6.1, 'classification': 36.1, 'quantiles': 30.0} · tepe bellek (RSS): 4.447 GB
- Model dosyaları: `deliverables/models/run-20261119T181934Z` · git'te yok sayılıyor mu: True
- MLflow: kapalı (--mlflow off)

Notlar: Farklar nokta tahminidir; GA ve anlamlılık (gün blok bootstrap, plan §5.2) son test içindir. Segment tabloları JSON'da (Origin, saat bloğu, ay); taşıyıcı kırılımı üretilmez (plan §7). Kantiller satır başına sıralandı (plan §3.3); B1 kantilleri tanımlandığı gibi (sıralamasız).

- Seçilen parametreler (arr_del15, fold search): `{"bagging_fraction": 0.6, "cat_smooth": 10, "feature_fraction": 0.8, "lambda_l2": 10.0, "learning_rate": 0.1, "max_bin": 255, "min_child_samples": 1000, "num_leaves": 31}`
- Seçilen parametreler (arr_delay_q080, fold search): `{"bagging_fraction": 0.8, "cat_smooth": 50, "feature_fraction": 0.6, "lambda_l2": 0.0, "learning_rate": 0.1, "max_bin": 63, "min_child_samples": 200, "num_leaves": 127}`

## ArrDel15 (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 0.2228 | 0.6263 | - | 0.3036 | - | 0.1762 | 0.0000 | 0.5323 | - | 0.0690 | 0.0624 | 0.580 | 0.3966 |
| val_a | LightGBM | 1483504 | 0.2228 | 0.6453 | +0.0190 | 0.3282 | +0.0246 | 0.1658 | 0.0588 | 0.5088 | -0.0235 | 0.0194 | -0.0125 | 1.054 | 0.4072 |
| val_a | L | 1483504 | 0.2228 | 0.6027 | -0.0236 | 0.3082 | +0.0046 | 0.1790 | -0.0159 | 0.5902 | +0.0579 | 0.0951 | -0.0867 | 0.329 | 0.3307 |
| val_b | B1 | 662410 | 0.2131 | 0.5897 | - | 0.2652 | - | 0.1792 | 0.0000 | 0.5412 | - | 0.0904 | 0.0744 | 0.407 | 0.3680 |
| val_b | LightGBM | 662410 | 0.2131 | 0.6077 | +0.0180 | 0.2850 | +0.0198 | 0.1652 | 0.0783 | 0.5094 | -0.0317 | 0.0306 | 0.0300 | 0.774 | 0.3737 |
| val_b | L | 662410 | 0.2131 | 0.5838 | -0.0059 | 0.2769 | +0.0117 | 0.2032 | -0.1341 | 0.5996 | +0.0584 | 0.1526 | 0.1225 | 0.272 | 0.3604 |

## İptal (sınıflandırma)

| Küme | Model | n | Yaygınlık | ROC-AUC | Δ ROC-AUC | PR-AUC | Δ PR-AUC | Brier | BSS (B1) | Log-loss | Δ log-loss | ECE | Ort. tahmin − gözlenen | Kal. eğimi | F1 (eşik B'den) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1506008 | 0.0128 | 0.6176 | - | 0.0226 | - | 0.0130 | 0.0000 | 0.0724 | - | 0.0099 | 0.0051 | 0.316 | 0.0483 |
| val_a | LightGBM | 1506008 | 0.0128 | 0.6435 | +0.0259 | 0.0390 | +0.0164 | 0.0126 | 0.0287 | 0.0667 | -0.0058 | 0.0028 | -0.0021 | 1.524 | 0.0960 |
| val_a | L | 1506008 | 0.0128 | 0.4094 | -0.2082 | 0.0109 | -0.0117 | 0.0130 | -0.0026 | 0.1220 | +0.0496 | 0.0118 | -0.0107 | - | 0.0251 |
| val_b | B1 | 689119 | 0.0367 | 0.6166 | - | 0.0574 | - | 0.0356 | 0.0000 | 0.1734 | - | 0.0193 | -0.0187 | 0.314 | 0.1041 |
| val_b | LightGBM | 689119 | 0.0367 | 0.6913 | +0.0746 | 0.0938 | +0.0364 | 0.0357 | -0.0033 | 0.1675 | -0.0058 | 0.0248 | -0.0248 | 1.758 | 0.1492 |
| val_b | L | 689119 | 0.0367 | 0.2320 | -0.3846 | 0.0221 | -0.0353 | 0.0416 | -0.1709 | 0.3172 | +0.1438 | 0.0506 | -0.0112 | - | 0.0708 |

## Varış rötarı kantilleri (tamamlanan uçuşlar, dk)

| Küme | Model | n | Pinball P50 | Δ | Pinball P80 | Δ | Pinball P95 | Δ | MAE P50 | Kapsama P80 | Kapsama P95 | Kesişme (ham) | Kesişme (sonra) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_a | B1 | 1483504 | 12.376 | - | 13.589 | - | 8.361 | - | 24.752 | 0.8448 | 0.9623 | 0.0015 | 0.0015 |
| val_a | LightGBM | 1483504 | 11.812 | -0.564 | 12.754 | -0.834 | 7.900 | -0.461 | 23.624 | 0.7774 | 0.9474 | 0.0000 | 0.0000 |
| val_b | B1 | 662410 | 12.903 | - | 14.111 | - | 8.694 | - | 25.806 | 0.8471 | 0.9622 | 0.0015 | 0.0015 |
| val_b | LightGBM | 662410 | 12.174 | -0.729 | 13.022 | -1.088 | 8.143 | -0.552 | 24.347 | 0.8066 | 0.9551 | 0.0000 | 0.0000 |

Δ = model − B1; kayıplarda (log-loss, pinball, Brier) negatif daha iyidir.

## Modeller ve özellik önemi (kazanç; ilk 8)

- `arr_del15-lgbm`: en iyi iterasyon 23 (tavan 200, tavana ulaştı: False), 5.07 sn · te_route_hour_arrdel15 52.9%, day_of_year 9.0%, hist_route_hour_p80 4.9%, Origin 3.2%, Reporting_Airline 2.9%, origin_ceiling_ft 2.7%, origin_wx_ts 2.7%, te_dest_hour_arrdel15 2.6%
- `arr_del15-logreg`: lojistik, 180494 satır (whole-day sample 15% of the fit window), 1.64 sn, yakınsama uyarısı: 0
- `cancelled-lgbm`: en iyi iterasyon 12 (tavan 200, tavana ulaştı: False), 4.65 sn · day_of_year 12.7%, Origin 11.1%, te_route_cancel 9.5%, origin_wx_ts 8.8%, origin_dwpf 8.5%, Reporting_Airline 7.1%, crs_dep_minute_of_day 6.8%, day_of_month 5.9%
- `cancelled-logreg`: lojistik, 183143 satır (whole-day sample 15% of the fit window), 1.27 sn, yakınsama uyarısı: 0
- `arr_delay_q050-lgbm`: en iyi iterasyon 28 (tavan 200, tavana ulaştı: False), 8.85 sn · hist_route_hour_p50 36.7%, day_of_year 8.0%, Origin 6.9%, schedule_excess_min 6.1%, te_route_hour_arrdel15 5.8%, Reporting_Airline 4.4%, te_dest_hour_arrdel15 3.6%, day_of_month 3.3%
- `arr_delay_q080-lgbm`: en iyi iterasyon 25 (tavan 200, tavana ulaştı: False), 8.71 sn · te_route_hour_arrdel15 24.5%, hist_route_hour_p80 12.2%, day_of_year 9.0%, te_dest_hour_arrdel15 8.1%, Origin 6.4%, day_of_month 3.6%, hist_route_hour_p50 3.5%, origin_dwpf 3.4%
- `arr_delay_q095-lgbm`: en iyi iterasyon 17 (tavan 200, tavana ulaştı: False), 7.62 sn · hist_route_hour_p80 13.4%, te_route_hour_arrdel15 10.1%, Origin 9.2%, day_of_year 8.5%, origin_wx_ts 7.4%, origin_dwpf 5.1%, hist_route_hour_p95 5.0%, Reporting_Airline 4.9%

Kazanç önemi sık bölünen/yüksek kardinaliteli özellikleri kayırır; permütasyon önemi (plan §7) sonraki adımda.

## Bilinmeyen kategoriler (eğitim penceresinde olmayan değerler → eksik)

- train: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_a: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
- val_b: Origin: 0 satır (0.0000%); Reporting_Airline: 0 satır (0.0000%)
