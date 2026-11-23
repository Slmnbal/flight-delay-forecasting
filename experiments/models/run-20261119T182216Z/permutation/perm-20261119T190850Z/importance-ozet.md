> Sızıntı incelemesi (2 aşama) tamamlandı: **sızıntı bulunmadı** (durum `dominant_past_only`). Kazanç şüphesi permütasyon ve zaman yolculuğu testiyle değerlendirildi; ayrıntı aşağıda ve JSON `leakage_review`'da.
> Not: en az bir modelde tek bir geçmiş-only özellik becerinin büyük kısmını taşıyor (sızıntı değil, güçlü bağımlılık); segment kırılımıyla birlikte okunmalı.

# Sızıntı incelemesi (sonradan, yeniden eğitim yok) – `run-20261119T182216Z`

- Oluşturma (UTC): 2026-11-19T19:08:50.652942+00:00 · koşu: `experiments/models/run-20261119T182216Z` · modeller: `deliverables/models/run-20261119T182216Z`
- Okunan: fit penceresi (geçmiş istatistikleri için) + Val-B; **Val-A ve son test okunmadı**; model yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı (57 dosya).
- Süre: 5802.0 sn · tepe bellek (RSS): 6.614 GB · adımlar: {'load': 3.0, 'history': 4.6, 'time_travel': 72.5, 'matrix': 1.8, 'permutation_arr_del15-lgbm': 1627.9, 'permutation_arr_del15-logreg': 60.6, 'permutation_cancelled-lgbm': 15.6, 'permutation_cancelled-logreg': 64.2, 'permutation_arr_delay_q050-lgbm': 2475.1, 'permutation_arr_delay_q080-lgbm': 1076.3, 'permutation_arr_delay_q095-lgbm': 400.4}

## Koşunun Val-B metriğini yeniden üretme (tüm hedef evreni)

| Model | Metrik | Koşu | Şimdi | Aynı mı |
|---|---|---|---|---|
| arr_del15-lgbm | roc_auc | 0.666551 | 0.666551 | evet |
| arr_del15-logreg | roc_auc | 0.653228 | 0.653228 | evet |
| cancelled-lgbm | roc_auc | 0.687920 | 0.687920 | evet |
| cancelled-logreg | roc_auc | 0.739340 | 0.739340 | evet |
| arr_delay_q050-lgbm | pinball_q050 | 11.730741 | 11.730741 | evet |
| arr_delay_q080-lgbm | pinball_q080 | 12.402431 | 12.402431 | evet |
| arr_delay_q095-lgbm | pinball_q095 | 7.785567 | 7.785567 | evet |

Yeniden üretilemeyen model permüte edilmez (başka matris / model olurdu).

## Sızıntı incelemesi (2 aşama: kazanç = şüphe; permütasyon + zaman yolculuğu = karar)

- Koşu düzeyi karar: **güçlü bağımlılık, geçmiş-only (sızıntı değil; notla raporlanır)** · raporlanabilir: evet
- Eşikler (kural, uydurulmuş sayı değil): çökme = B0 üstü becerinin en fazla %25'i kalırsa; zararlı = permütasyon metriği 2 sd'den fazla iyileştirirse; zaman yolculuğu toleransı 1e-05.
- sd yalnızca permütasyon tekrarlarının gürültüsüdür; Val-B örneklem belirsizliği değildir.

- Zaman yolculuğu: tümü geçti: evet · fit gelecek satırı reddediyor: evet · bilgi aralığı (dk, ≥ 0 olmalı): 174210.0 · OOF kendi blok kontrolü: evet

### `arr_del15-lgbm` – şüphe yok

- Val-B örneklemi: 290812 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban roc_auc 0.6563 · B0 roc_auc 0.5000 · 1611.6 sn

| Özellik | Δ roc_auc (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| origin_tmpf | 0.0245 | 0.0006 | 0.844 |
| Reporting_Airline | 0.0213 | 0.0004 | 0.863 |
| Origin | 0.0193 | 0.0006 | 0.877 |
| crs_dep_minute_of_day | 0.0142 | 0.0003 | 0.909 |
| te_route_hour_arrdel15 | 0.0097 | 0.0003 | 0.938 |
| schedule_excess_min | 0.0093 | 0.0001 | 0.940 |
| day_of_week | 0.0087 | 0.0002 | 0.944 |
| planned_departures_origin_day | 0.0055 | 0.0002 | 0.965 |
| origin_ceiling_ft | 0.0050 | 0.0001 | 0.968 |
| origin_p01i | 0.0032 | 0.0001 | 0.979 |

- Val-B'de zararlı (permütasyon metriği iyileştiriyor): day_of_month, day_of_year, days_to_holiday, month, holiday_week, dest_vsby, dest_ifr_flag, CRSElapsedTime, hist_route_hour_p50, DistanceGroup

### `arr_del15-logreg` – şüphe yok

- Val-B örneklemi: 290812 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban roc_auc 0.6407 · B0 roc_auc 0.5000 · 59.5 sn

| Özellik | Δ roc_auc (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| crs_dep_minute_of_day | 0.0798 | 0.0013 | 0.433 |
| te_route_hour_arrdel15 | 0.0502 | 0.0006 | 0.644 |
| Origin | 0.0458 | 0.0010 | 0.675 |
| planned_departures_origin_day | 0.0428 | 0.0004 | 0.696 |
| origin_tmpf | 0.0136 | 0.0003 | 0.903 |
| origin_wx_sn | 0.0127 | 0.0000 | 0.910 |
| crs_dep_hour | 0.0117 | 0.0001 | 0.917 |
| Reporting_Airline | 0.0087 | 0.0002 | 0.938 |
| hour_block | 0.0050 | 0.0002 | 0.964 |
| origin_gust | 0.0047 | 0.0001 | 0.966 |

- Val-B'de zararlı (permütasyon metriği iyileştiriyor): month, day_of_week, te_route_cancel, dest_vsby, dest_ifr_flag, dest_weather_available

### `cancelled-lgbm` – şüphe yok

- Val-B örneklemi: 303504 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban roc_auc 0.7200 · B0 roc_auc 0.5000 · 15.4 sn

| Özellik | Δ roc_auc (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| origin_p01i | 0.1128 | 0.0014 | 0.487 |
| dest_p01i | 0.0240 | 0.0002 | 0.891 |
| Origin | 0.0146 | 0.0002 | 0.933 |
| dest_wx_sn | 0.0087 | 0.0001 | 0.960 |
| te_route_cancel | 0.0081 | 0.0004 | 0.963 |
| origin_tmpf | 0.0052 | 0.0002 | 0.976 |
| origin_ceiling_ft | 0.0047 | 0.0002 | 0.979 |
| origin_dwpf | 0.0034 | 0.0003 | 0.984 |
| dest_tmpf | 0.0028 | 0.0002 | 0.987 |
| day_of_year | 0.0028 | 0.0012 | 0.987 |

- Val-B'de zararlı (permütasyon metriği iyileştiriyor): day_of_month, days_to_holiday, holiday_week, month, CRSElapsedTime, day_of_week, dest_ceiling_ft, crs_dep_hour, support_n_dest_hour_arrdel15

### `cancelled-logreg` – şüphe yok

- Val-B örneklemi: 303504 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban roc_auc 0.7457 · B0 roc_auc 0.5000 · 63.4 sn

| Özellik | Δ roc_auc (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| dest_wx_sn | 0.0394 | 0.0002 | 0.840 |
| month | 0.0388 | 0.0008 | 0.842 |
| origin_wx_sn | 0.0348 | 0.0005 | 0.858 |
| origin_tmpf | 0.0297 | 0.0006 | 0.879 |
| Origin | 0.0208 | 0.0006 | 0.915 |
| dest_gust | 0.0126 | 0.0001 | 0.949 |
| day_of_month | 0.0123 | 0.0001 | 0.950 |
| origin_ceiling_ft | 0.0117 | 0.0004 | 0.952 |
| origin_sknt | 0.0114 | 0.0003 | 0.954 |
| Reporting_Airline | 0.0109 | 0.0011 | 0.955 |

- Val-B'de zararlı (permütasyon metriği iyileştiriyor): day_of_week, dest_dwpf, origin_dwpf, holiday_week, dest_tmpf, day_of_year, DistanceGroup, planned_departures_origin_day, support_n_dest_hour_arrdel15, Distance

### `arr_delay_q050-lgbm` – güçlü bağımlılık, geçmiş-only (sızıntı değil; notla raporlanır)

- Val-B örneklemi: 290812 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban pinball_q050 11.5115 · B0 pinball_q050 11.9077 · 2445.0 sn

| Özellik | Δ pinball_q050 (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| schedule_excess_min | 0.3753 | 0.0025 | 0.053 |
| origin_tmpf | 0.2498 | 0.0012 | 0.370 |
| Origin | 0.2453 | 0.0041 | 0.381 |
| Reporting_Airline | 0.1198 | 0.0034 | 0.698 |
| crs_dep_minute_of_day | 0.1161 | 0.0016 | 0.707 |
| planned_arrivals_dest_hour | 0.0771 | 0.0007 | 0.805 |
| origin_p01i | 0.0476 | 0.0029 | 0.880 |
| planned_departures_origin_day | 0.0476 | 0.0007 | 0.880 |
| origin_ceiling_ft | 0.0441 | 0.0007 | 0.889 |
| origin_dwpf | 0.0427 | 0.0013 | 0.892 |

- Şüpheli `schedule_excess_min` (permutation leaves <= 25% of the skill over B0): kazanç payı 0.069, kalan beceri payı 0.053, geçmiş-only: evet (history feature: time travel test passed) → **güçlü bağımlılık, geçmiş-only (sızıntı değil; notla raporlanır)**
- Val-B'de zararlı (permütasyon metriği iyileştiriyor): day_of_month, day_of_year, month, days_to_holiday, holiday_week, DistanceGroup, te_route_cancel, dest_ifr_flag, origin_ifr_flag, dest_obs_age_min

### `arr_delay_q080-lgbm` – şüphe yok

- Val-B örneklemi: 290812 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban pinball_q080 12.1893 · B0 pinball_q080 12.8746 · 1064.0 sn

| Özellik | Δ pinball_q080 (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| origin_tmpf | 0.3350 | 0.0044 | 0.511 |
| Origin | 0.2199 | 0.0034 | 0.679 |
| Reporting_Airline | 0.1701 | 0.0016 | 0.752 |
| schedule_excess_min | 0.1502 | 0.0039 | 0.781 |
| crs_dep_minute_of_day | 0.1046 | 0.0018 | 0.847 |
| te_route_hour_arrdel15 | 0.0924 | 0.0017 | 0.865 |
| day_of_week | 0.0696 | 0.0030 | 0.898 |
| origin_p01i | 0.0681 | 0.0042 | 0.901 |
| origin_dwpf | 0.0642 | 0.0030 | 0.906 |
| origin_ceiling_ft | 0.0542 | 0.0020 | 0.921 |

- Val-B'de zararlı (permütasyon metriği iyileştiriyor): day_of_month, day_of_year, days_to_holiday, month, holiday_week, dest_wx_ts, origin_obs_age_min, support_n_carrier_origin_arrdel15, dest_ifr_flag, dest_obs_age_min

### `arr_delay_q095-lgbm` – şüphe yok

- Val-B örneklemi: 290812 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban pinball_q095 7.7109 · B0 pinball_q095 8.3272 · 396.0 sn

| Özellik | Δ pinball_q095 (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| Reporting_Airline | 0.2761 | 0.0042 | 0.552 |
| origin_tmpf | 0.2040 | 0.0011 | 0.669 |
| hist_route_hour_p95 | 0.0910 | 0.0028 | 0.852 |
| day_of_week | 0.0781 | 0.0009 | 0.873 |
| Origin | 0.0683 | 0.0031 | 0.889 |
| origin_dwpf | 0.0502 | 0.0017 | 0.919 |
| origin_p01i | 0.0501 | 0.0039 | 0.919 |
| crs_dep_minute_of_day | 0.0357 | 0.0018 | 0.942 |
| origin_ceiling_ft | 0.0257 | 0.0034 | 0.958 |
| schedule_excess_min | 0.0235 | 0.0024 | 0.962 |

- Val-B'de zararlı (permütasyon metriği iyileştiriyor): day_of_month, day_of_year, days_to_holiday, month, te_carrier_origin_arrdel15, dest_vsby, holiday_week, dest_wx_ts, support_n_origin_hour_taxiout, dest_ifr_flag

Δ: pozitif = özelliği karıştırmak modeli kötüleştirdi (özellik önemli); log-loss / pinball artışı, ROC-AUC düşüşü. Kalan beceri payı: ROC-AUC için (AUC_perm − 0.5) / (AUC − 0.5); kantil için (pinball_B0 − pinball_perm) / (pinball_B0 − pinball).

