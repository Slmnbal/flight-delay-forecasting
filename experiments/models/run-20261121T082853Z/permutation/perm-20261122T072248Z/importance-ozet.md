> Sızıntı incelemesi (2 aşama) tamamlandı: **sızıntı bulunmadı** (durum `no_suspicion`). Kazanç şüphesi permütasyon ve zaman yolculuğu testiyle değerlendirildi; ayrıntı aşağıda ve JSON `leakage_review`'da.

# Sızıntı incelemesi (sonradan, yeniden eğitim yok) – `run-20261121T082853Z`

- Oluşturma (UTC): 2026-11-22T07:22:48.621877+00:00 · koşu: `experiments/models/run-20261121T082853Z` · modeller: `deliverables/models/run-20261121T082853Z`
- Okunan: fit penceresi (geçmiş istatistikleri için) + Val-B; **Val-A ve son test okunmadı**; model yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı (57 dosya).
- Süre: 1768.1 sn · tepe bellek (RSS): 4.477 GB · adımlar: {'load': 3.0, 'history': 4.7, 'time_travel': 71.6, 'matrix': 1.8, 'permutation_arr_del15-lgbm': 1687.1}

## Koşunun Val-B metriğini yeniden üretme (tüm hedef evreni)

| Model | Metrik | Koşu | Şimdi | Aynı mı |
|---|---|---|---|---|
| arr_del15-lgbm | roc_auc | 0.699819 | 0.699819 | evet |

Yeniden üretilemeyen model permüte edilmez (başka matris / model olurdu).

## Sızıntı incelemesi (2 aşama: kazanç = şüphe; permütasyon + zaman yolculuğu = karar)

- Koşu düzeyi karar: **şüphe yok** · raporlanabilir: evet
- Eşikler (kural, uydurulmuş sayı değil): çökme = B0 üstü becerinin en fazla %25'i kalırsa; zararlı = permütasyon metriği 2 sd'den fazla iyileştirirse; zaman yolculuğu toleransı 1e-05.
- sd yalnızca permütasyon tekrarlarının gürültüsüdür; Val-B örneklem belirsizliği değildir.

- Zaman yolculuğu: tümü geçti: evet · fit gelecek satırı reddediyor: evet · bilgi aralığı (dk, ≥ 0 olmalı): 174210.0 · OOF kendi blok kontrolü: evet

### `arr_del15-lgbm` – şüphe yok

- Val-B örneklemi: 290812 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban roc_auc 0.6890 · B0 roc_auc 0.5000 · 1670.9 sn

| Özellik | Δ roc_auc (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| origin_tmpf | 0.0450 | 0.0005 | 0.762 |
| Origin | 0.0440 | 0.0010 | 0.767 |
| planned_departures_origin_day | 0.0376 | 0.0008 | 0.801 |
| Reporting_Airline | 0.0289 | 0.0003 | 0.847 |
| crs_dep_minute_of_day | 0.0185 | 0.0003 | 0.902 |
| schedule_excess_min | 0.0140 | 0.0003 | 0.926 |
| origin_dwpf | 0.0091 | 0.0002 | 0.952 |
| te_route_hour_arrdel15 | 0.0070 | 0.0004 | 0.963 |
| day_of_week | 0.0065 | 0.0001 | 0.965 |
| origin_ceiling_ft | 0.0053 | 0.0002 | 0.972 |

- Val-B'de zararlı (permütasyon metriği iyileştiriyor): support_n_carrier_origin_arrdel15, dest_ifr_flag, hist_taxiout_origin_hour_median, hour_block

### `arr_delay_q010-lgbm` – şüphe yok


### `arr_delay_q050-lgbm` – şüphe yok


### `arr_delay_q080-lgbm` – şüphe yok


### `arr_delay_q090-lgbm` – şüphe yok


### `arr_delay_q095-lgbm` – şüphe yok


Δ: pozitif = özelliği karıştırmak modeli kötüleştirdi (özellik önemli); log-loss / pinball artışı, ROC-AUC düşüşü. Kalan beceri payı: ROC-AUC için (AUC_perm − 0.5) / (AUC − 0.5); kantil için (pinball_B0 − pinball_perm) / (pinball_B0 − pinball).

