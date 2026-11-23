> Sızıntı incelemesi (2 aşama) tamamlandı: **sızıntı bulunmadı** (durum `no_suspicion`). Kazanç şüphesi permütasyon ve zaman yolculuğu testiyle değerlendirildi; ayrıntı aşağıda ve JSON `leakage_review`'da.

# Sızıntı incelemesi (sonradan, yeniden eğitim yok) – `run-20261120T174502Z`

- Oluşturma (UTC): 2026-11-20T19:23:52.851682+00:00 · koşu: `experiments/models/run-20261120T174502Z` · modeller: `deliverables/models/run-20261120T174502Z`
- Okunan: fit penceresi (geçmiş istatistikleri için) + Val-B; **Val-A ve son test okunmadı**; model yeniden eğitilmedi; dosyalar koşunun parmak iziyle karşılaştırıldı (57 dosya).
- Süre: 215.5 sn · tepe bellek (RSS): 6.534 GB · adımlar: {'load': 3.6, 'history': 7.5, 'time_travel': 111.9, 'matrix': 2.8, 'permutation_cancelled-lgbm': 89.6}

## Koşunun Val-B metriğini yeniden üretme (tüm hedef evreni)

| Model | Metrik | Koşu | Şimdi | Aynı mı |
|---|---|---|---|---|
| cancelled-lgbm | roc_auc | 0.838494 | 0.838494 | evet |

Yeniden üretilemeyen model permüte edilmez (başka matris / model olurdu).

## Sızıntı incelemesi (2 aşama: kazanç = şüphe; permütasyon + zaman yolculuğu = karar)

- Koşu düzeyi karar: **şüphe yok** · raporlanabilir: evet
- Eşikler (kural, uydurulmuş sayı değil): çökme = B0 üstü becerinin en fazla %25'i kalırsa; zararlı = permütasyon metriği 2 sd'den fazla iyileştirirse; zaman yolculuğu toleransı 1e-05.
- sd yalnızca permütasyon tekrarlarının gürültüsüdür; Val-B örneklem belirsizliği değildir.

- Zaman yolculuğu: tümü geçti: evet · fit gelecek satırı reddediyor: evet · bilgi aralığı (dk, ≥ 0 olmalı): 174210.0 · OOF kendi blok kontrolü: evet

### `cancelled-lgbm` – şüphe yok

- Val-B örneklemi: 303504 satır / 26 gün · şema rows · 3 tekrar · tohum 42 · taban roc_auc 0.8607 · B0 roc_auc 0.5000 · 88.6 sn

| Özellik | Δ roc_auc (ort.) | sd | Kalan beceri payı |
|---|---|---|---|
| origin_tmpf | 0.0590 | 0.0002 | 0.837 |
| Origin | 0.0307 | 0.0007 | 0.915 |
| dest_p01i | 0.0260 | 0.0002 | 0.928 |
| dest_tmpf | 0.0181 | 0.0009 | 0.950 |
| origin_p01i | 0.0166 | 0.0006 | 0.954 |
| dest_ceiling_ft | 0.0139 | 0.0005 | 0.962 |
| origin_dwpf | 0.0121 | 0.0006 | 0.967 |
| day_of_week | 0.0065 | 0.0001 | 0.982 |
| origin_ceiling_ft | 0.0060 | 0.0003 | 0.983 |
| Reporting_Airline | 0.0033 | 0.0009 | 0.991 |

- Val-B'de zararlı (permütasyon metriği iyileştiriyor): Distance, support_n_origin_hour_taxiout, support_n_carrier_origin_arrdel15, dest_wx_ts, support_n_route_cancel, origin_wx_fg, origin_obs_age_min, support_n_route_hour_elapsed

Δ: pozitif = özelliği karıştırmak modeli kötüleştirdi (özellik önemli); log-loss / pinball artışı, ROC-AUC düşüşü. Kalan beceri payı: ROC-AUC için (AUC_perm − 0.5) / (AUC − 0.5); kantil için (pinball_B0 − pinball_perm) / (pinball_B0 − pinball).

