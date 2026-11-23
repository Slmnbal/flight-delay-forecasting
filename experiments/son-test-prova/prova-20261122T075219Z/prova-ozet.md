> **PROVA – SON TEST DEĞİL.** Değerlendirme pencereleri eğitim penceresinin içinde (K3: 2025-03..05, K4: 2025-06..08); modeller katın öncesinde yeniden eğitildi. Parametreler bu kat pencerelerinde arandığı için performans sayıları iyimserdir ve sonuç değildir.

# Son test provası

- Oluşturma (UTC): 2026-11-22T07:52:19.127547+00:00 · kilit girdisi: `experiments/son-test-dondurma-taslak.json` · roller: arr_del15/T2, arr_del15/plan_matched, arr_delay/plan, arr_delay/T2_matched, cancelled/plan, cancelled/T2, cancelled/T2_calendar · B = 1000 · süre 7350.6 sn
- Son test okundu mu: False · kilit yazıldı mı: False

## Prova kontrolleri (kod yolu; performans kapı değildir)

- Genel: **geçti**
- K3: geçti (hesaplanamayan ölçüt: yok; Holm tam: True; GA'lar sonlu: True; yetersiz conformal ayı: yok)
- K4: geçti (hesaplanamayan ölçüt: yok; Holm tam: True; GA'lar sonlu: True; yetersiz conformal ayı: yok)
- pooled: geçti (hesaplanamayan ölçüt: yok; Holm tam: True; GA'lar sonlu: True; yetersiz conformal ayı: yok)

## K3 / K5 tolerans önerisi (önceden kayıt d: max(plan, bootstrap yarı genişliği ↑0,005))

- Kaynak blok: pooled · yarı genişlikler: citl_platt 0.0080, slope_platt 0.0361, coverage_rolling_q080 0.0106, coverage_rolling_q095 0.0041
- K3: |CITL| ≤ 0.01, eğim [0.9; 1.1]
- K5: P80 [0.78, 0.82], P95 [0.94, 0.96] (segment kuralı değişmez)

- K3: fit 2023-09-01..2024-08-31, erken durdurma 2024-09-01..2024-12-31, kalibrasyon 2025-01-01..2025-02-28, değerlendirme 2025-03-01..2025-05-31 · 15 model
- K4: fit 2023-09-01..2024-11-30, erken durdurma 2024-12-01..2025-03-31, kalibrasyon 2025-04-01..2025-05-31, değerlendirme 2025-06-01..2025-08-31 · 15 model

## K3: rehearsal K3

- Günler: 92 (2025-03-01 .. 2025-05-31) · gün blok bootstrap B = 1000, tohum 42, yüzdelik GA %95
- Tüm kabul ölçütleri geçti mi: **hayır**

### Kabul ölçütleri (plan §5.3)

| Ölçüt | Sonuç | Tanım |
|---|---|---|
| K1 | geçti | ArrDel15 T2 vs B1: ΔROC-AUC > 0 ve ΔPR-AUC > 0; ikisinde de GA alt sınırı > 0 ve Holm sonrası anlamlı |
| K2 | geçti | ArrDel15 BSS (aylık kayan Platt: model vs B1) > 0 ve GA alt sınırı > 0 |
| K3 | GEÇMEDİ | ArrDel15 aylık kayan Platt: |CITL| ≤ 0.01 ve eğim [0.9; 1.1] (plan 5.3 proposal) |
| K4 | GEÇMEDİ | Plan kantilleri vs B1 (ham): α 0,50/0,80/0,95 için Δpinball < 0, GA üst sınırı < 0 ve Holm sonrası anlamlı |
| K5 | geçti | Plan kantilleri, aylık kayan conformal: P80 kapsama [0.78, 0.82], P95 [0.94, 0.96]; Origin × ay (n ≥ 500) segmentlerinin ≥ 80%'i hedefin ±0.05 içinde (plan 5.3 proposal) |
| K6 | GEÇMEDİ | İptal plan vs B1: ΔPR-AUC > 0 ve GA alt sınırı > 0 (ham skor) |
| K7 | GEÇMEDİ | Sızıntı: §2.6 testleri geçti (beyan) ve kilitli modellerde çözülmemiş şüphe yok |

### Birincil aile (plan §5.2, Holm α = 0.05)

| # | Rol | Karşılaştırma | Δ [%95 GA] | p | p (Holm) | Anlamlı |
|---|---|---|---|---|---|---|
| 1_arr_del15_roc_auc | arr_del15/T2 | d_roc_auc | +0.0626 [+0.0556; +0.0699] | < 0.001 | < 0.001 | evet |
| 2_arr_del15_pr_auc | arr_del15/T2 | d_pr_auc | +0.1074 [+0.0935; +0.1203] | < 0.001 | < 0.001 | evet |
| 3_arr_del15_bss | arr_del15/T2 | bss_platt | +0.0597 [+0.0495; +0.0693] | < 0.001 | < 0.001 | evet |
| 4_pinball_q050 | arr_delay/plan | d_pinball_q050 | -0.1877 [-0.2096; -0.1653] | < 0.001 | < 0.001 | evet |
| 5_pinball_q080 | arr_delay/plan | d_pinball_q080 | -0.0899 [-0.1348; -0.0395] | < 0.001 | < 0.001 | evet |
| 6_pinball_q095 | arr_delay/plan | d_pinball_q095 | +0.0132 [-0.0577; +0.0988] | 0.770 | 1.000 | hayır |
| 7_cancelled_pr_auc | cancelled/plan | d_pr_auc | -0.0006 [-0.0028; +0.0015] | 0.598 | 1.000 | hayır |

### Hava katkısı (plan §6; T2 − plan, aynı uçuşlar; ikincil)

- arr_del15: d_roc_auc +0.0486 [+0.0421; +0.0552] · d_pr_auc +0.0828 [+0.0709; +0.0936] · d_brier_platt -0.0083 [-0.0099; -0.0067]
- arr_delay: d_pinball_q080 -0.6219 [-0.7669; -0.4894]
- oracle: not part of the final test (no oracle model is locked); the captured share is not reported

### ArrDel15 T2: olasılık kalitesi (aylık kayan Platt birincil, sabit Platt ikincil; sıralama metrikleri ham skorla)

| Yöntem | Brier | BSS (aynı yöntemle B1) | Log-loss | ECE | CITL | Eğim |
|---|---|---|---|---|---|---|
| ham | 0.1577 | 0.0596 | 0.4884 | 0.0161 | -0.0095 | 0.864 |
| platt | 0.1582 | 0.0606 | 0.4892 | 0.0242 | -0.0242 | 1.049 |
| isotonic | 0.1583 | 0.0602 | 0.4895 | 0.0248 | -0.0248 | 1.067 |
| platt_rolling | 0.1576 | 0.0597 | 0.4875 | 0.0129 | -0.0129 | 1.019 |

- ROC-AUC (ham) 0.6909, PR-AUC (ham) 0.4089, yaygınlık 0.2225; Origin × gün tabakalı AUC (keşifsel, M5): model 0.6631, B1 0.6353

| Ay | n | Yaygınlık | CITL ham | CITL Platt | CITL kayan Platt | ROC-AUC ham |
|---|---|---|---|---|---|---|
| 2025-03 | 383842 | 0.2069 | -0.0038 | -0.0167 | -0.0155 | 0.6928 |
| 2025-04 | 374989 | 0.2069 | -0.0035 | -0.0162 | -0.0054 | 0.6781 |
| 2025-05 | 386950 | 0.2531 | -0.0210 | -0.0393 | -0.0175 | 0.6942 |

### Plan kantilleri: conformal kapsama (birincil: aylık kayan)

| Şema | P80 kapsama | P95 kapsama | Segment payı P80 | Segment payı P95 | Yetersiz ay (k > n) | %80 aralık (CQR) kapsama |
|---|---|---|---|---|---|---|
| rolling | 0.7925 | 0.9482 | 0.8444 | 0.9778 | - | 0.8088 |
| static | 0.7925 | 0.9496 | 0.8333 | 0.9889 | - | 0.8165 |
| public | 0.7873 | 0.9464 | 0.8111 | 0.9778 | - | 0.8040 |
- Ham kapsama: P80 0.7984, P95 0.9423 (statik = tek ofset; public = 2 ay gecikmeli 'kamu senaryosu', ikincil)

| Ay | n | P80 ham | P80 kayan | P80 statik | P80 public | P95 ham | P95 kayan | P95 statik | P95 public |
|---|---|---|---|---|---|---|---|---|---|
| 2025-03 | 383842 | 0.8119 | 0.8100 | 0.8064 | 0.7860 | 0.9464 | 0.9543 | 0.9534 | 0.9434 |
| 2025-04 | 374989 | 0.8118 | 0.8056 | 0.8062 | 0.8065 | 0.9477 | 0.9533 | 0.9544 | 0.9533 |
| 2025-05 | 386950 | 0.7719 | 0.7623 | 0.7654 | 0.7699 | 0.9331 | 0.9370 | 0.9413 | 0.9428 |

### İkincil karşılaştırmalar (B1'e göre; keşifsel, Holm dışı)

- `arr_del15/plan_matched`: d_roc_auc +0.0140 [+0.0087; +0.0190] · d_pr_auc +0.0246 [+0.0173; +0.0322] · bss_platt +0.0104 [+0.0069; +0.0139]
- `cancelled/T2`: d_roc_auc +0.1185 [+0.0841; +0.1500] · d_pr_auc +0.0342 [+0.0191; +0.0553] · bss_platt +0.0225 [+0.0155; +0.0313]
- `cancelled/T2_calendar`: d_roc_auc +0.0860 [+0.0496; +0.1209] · d_pr_auc +0.0270 [+0.0132; +0.0444] · bss_platt +0.0165 [+0.0044; +0.0300]
- `arr_delay/T2_matched`: d_pinball_q050 -0.5191 [-0.5865; -0.4546] · d_pinball_q080 -0.7118 [-0.8500; -0.5807] · d_pinball_q095 -0.3581 [-0.4605; -0.2515]

## K4: rehearsal K4

- Günler: 92 (2025-06-01 .. 2025-08-31) · gün blok bootstrap B = 1000, tohum 42, yüzdelik GA %95
- Tüm kabul ölçütleri geçti mi: **hayır**

### Kabul ölçütleri (plan §5.3)

| Ölçüt | Sonuç | Tanım |
|---|---|---|
| K1 | geçti | ArrDel15 T2 vs B1: ΔROC-AUC > 0 ve ΔPR-AUC > 0; ikisinde de GA alt sınırı > 0 ve Holm sonrası anlamlı |
| K2 | geçti | ArrDel15 BSS (aylık kayan Platt: model vs B1) > 0 ve GA alt sınırı > 0 |
| K3 | geçti | ArrDel15 aylık kayan Platt: |CITL| ≤ 0.01 ve eğim [0.9; 1.1] (plan 5.3 proposal) |
| K4 | GEÇMEDİ | Plan kantilleri vs B1 (ham): α 0,50/0,80/0,95 için Δpinball < 0, GA üst sınırı < 0 ve Holm sonrası anlamlı |
| K5 | GEÇMEDİ | Plan kantilleri, aylık kayan conformal: P80 kapsama [0.78, 0.82], P95 [0.94, 0.96]; Origin × ay (n ≥ 500) segmentlerinin ≥ 80%'i hedefin ±0.05 içinde (plan 5.3 proposal) |
| K6 | GEÇMEDİ | İptal plan vs B1: ΔPR-AUC > 0 ve GA alt sınırı > 0 (ham skor) |
| K7 | GEÇMEDİ | Sızıntı: §2.6 testleri geçti (beyan) ve kilitli modellerde çözülmemiş şüphe yok |

### Birincil aile (plan §5.2, Holm α = 0.05)

| # | Rol | Karşılaştırma | Δ [%95 GA] | p | p (Holm) | Anlamlı |
|---|---|---|---|---|---|---|
| 1_arr_del15_roc_auc | arr_del15/T2 | d_roc_auc | +0.0521 [+0.0459; +0.0578] | < 0.001 | < 0.001 | evet |
| 2_arr_del15_pr_auc | arr_del15/T2 | d_pr_auc | +0.0957 [+0.0857; +0.1053] | < 0.001 | < 0.001 | evet |
| 3_arr_del15_bss | arr_del15/T2 | bss_platt | +0.0808 [+0.0700; +0.0909] | < 0.001 | < 0.001 | evet |
| 4_pinball_q050 | arr_delay/plan | d_pinball_q050 | -0.2646 [-0.3007; -0.2265] | < 0.001 | < 0.001 | evet |
| 5_pinball_q080 | arr_delay/plan | d_pinball_q080 | -0.2211 [-0.2858; -0.1511] | < 0.001 | < 0.001 | evet |
| 6_pinball_q095 | arr_delay/plan | d_pinball_q095 | +0.0617 [-0.0007; +0.1316] | 0.054 | 0.054 | hayır |
| 7_cancelled_pr_auc | cancelled/plan | d_pr_auc | -0.0093 [-0.0150; -0.0051] | < 0.001 | < 0.001 | evet |

### Hava katkısı (plan §6; T2 − plan, aynı uçuşlar; ikincil)

- arr_del15: d_roc_auc +0.0377 [+0.0329; +0.0421] · d_pr_auc +0.0671 [+0.0581; +0.0761] · d_brier_platt -0.0119 [-0.0138; -0.0099]
- arr_delay: d_pinball_q080 -1.2313 [-1.4641; -1.0000]
- oracle: not part of the final test (no oracle model is locked); the captured share is not reported

### ArrDel15 T2: olasılık kalitesi (aylık kayan Platt birincil, sabit Platt ikincil; sıralama metrikleri ham skorla)

| Yöntem | Brier | BSS (aynı yöntemle B1) | Log-loss | ECE | CITL | Eğim |
|---|---|---|---|---|---|---|
| ham | 0.1783 | 0.0919 | 0.5342 | 0.0313 | -0.0313 | 1.026 |
| platt | 0.1774 | 0.0853 | 0.5320 | 0.0145 | -0.0056 | 1.114 |
| isotonic | 0.1775 | 0.0837 | 0.5322 | 0.0148 | -0.0056 | 1.099 |
| platt_rolling | 0.1776 | 0.0808 | 0.5325 | 0.0068 | 0.0044 | 1.028 |

- ROC-AUC (ham) 0.7232, PR-AUC (ham) 0.5117, yaygınlık 0.2849; Origin × gün tabakalı AUC (keşifsel, M5): model 0.7017, B1 0.6736

| Ay | n | Yaygınlık | CITL ham | CITL Platt | CITL kayan Platt | ROC-AUC ham |
|---|---|---|---|---|---|---|
| 2025-06 | 384688 | 0.3023 | -0.0464 | -0.0206 | -0.0240 | 0.7227 |
| 2025-07 | 392673 | 0.3111 | -0.0421 | -0.0168 | -0.0006 | 0.7281 |
| 2025-08 | 382682 | 0.2406 | -0.0051 | 0.0209 | 0.0380 | 0.7111 |

### Plan kantilleri: conformal kapsama (birincil: aylık kayan)

| Şema | P80 kapsama | P95 kapsama | Segment payı P80 | Segment payı P95 | Yetersiz ay (k > n) | %80 aralık (CQR) kapsama |
|---|---|---|---|---|---|---|
| rolling | 0.7880 | 0.9438 | 0.4889 | 0.9444 | - | 0.7978 |
| static | 0.7589 | 0.9339 | 0.6000 | 0.8889 | - | 0.7834 |
| public | 0.7469 | 0.9285 | 0.4556 | 0.8778 | - | 0.7836 |
- Ham kapsama: P80 0.7361, P95 0.9170 (statik = tek ofset; public = 2 ay gecikmeli 'kamu senaryosu', ikincil)

| Ay | n | P80 ham | P80 kayan | P80 statik | P80 public | P95 ham | P95 kayan | P95 statik | P95 public |
|---|---|---|---|---|---|---|---|---|---|
| 2025-06 | 384688 | 0.7233 | 0.7409 | 0.7465 | 0.7341 | 0.9123 | 0.9287 | 0.9304 | 0.9240 |
| 2025-07 | 392673 | 0.7099 | 0.7697 | 0.7331 | 0.7147 | 0.9034 | 0.9362 | 0.9221 | 0.9139 |
| 2025-08 | 382682 | 0.7760 | 0.8542 | 0.7979 | 0.7927 | 0.9357 | 0.9669 | 0.9494 | 0.9481 |

### İkincil karşılaştırmalar (B1'e göre; keşifsel, Holm dışı)

- `arr_del15/plan_matched`: d_roc_auc +0.0144 [+0.0093; +0.0194] · d_pr_auc +0.0286 [+0.0207; +0.0358] · bss_platt +0.0193 [+0.0134; +0.0250]
- `cancelled/T2`: d_roc_auc +0.1097 [+0.0921; +0.1263] · d_pr_auc +0.0841 [+0.0512; +0.1237] · bss_platt +0.0547 [+0.0309; +0.0777]
- `cancelled/T2_calendar`: d_roc_auc +0.0735 [+0.0492; +0.0946] · d_pr_auc +0.0122 [+0.0006; +0.0372] · bss_platt -0.0042 [-0.0497; +0.0273]
- `arr_delay/T2_matched`: d_pinball_q050 -0.7767 [-0.8740; -0.6694] · d_pinball_q080 -1.4524 [-1.6860; -1.2003] · d_pinball_q095 -0.8996 [-1.0725; -0.7258]

## pooled: rehearsal pooled K3+K4

- Günler: 184 (2025-03-01 .. 2025-08-31) · gün blok bootstrap B = 1000, tohum 42, yüzdelik GA %95
- Tüm kabul ölçütleri geçti mi: **hayır**

### Kabul ölçütleri (plan §5.3)

| Ölçüt | Sonuç | Tanım |
|---|---|---|
| K1 | geçti | ArrDel15 T2 vs B1: ΔROC-AUC > 0 ve ΔPR-AUC > 0; ikisinde de GA alt sınırı > 0 ve Holm sonrası anlamlı |
| K2 | geçti | ArrDel15 BSS (aylık kayan Platt: model vs B1) > 0 ve GA alt sınırı > 0 |
| K3 | geçti | ArrDel15 aylık kayan Platt: |CITL| ≤ 0.01 ve eğim [0.9; 1.1] (plan 5.3 proposal) |
| K4 | GEÇMEDİ | Plan kantilleri vs B1 (ham): α 0,50/0,80/0,95 için Δpinball < 0, GA üst sınırı < 0 ve Holm sonrası anlamlı |
| K5 | GEÇMEDİ | Plan kantilleri, aylık kayan conformal: P80 kapsama [0.78, 0.82], P95 [0.94, 0.96]; Origin × ay (n ≥ 500) segmentlerinin ≥ 80%'i hedefin ±0.05 içinde (plan 5.3 proposal) |
| K6 | GEÇMEDİ | İptal plan vs B1: ΔPR-AUC > 0 ve GA alt sınırı > 0 (ham skor) |
| K7 | GEÇMEDİ | Sızıntı: §2.6 testleri geçti (beyan) ve kilitli modellerde çözülmemiş şüphe yok |

### Birincil aile (plan §5.2, Holm α = 0.05)

| # | Rol | Karşılaştırma | Δ [%95 GA] | p | p (Holm) | Anlamlı |
|---|---|---|---|---|---|---|
| 1_arr_del15_roc_auc | arr_del15/T2 | d_roc_auc | +0.0657 [+0.0599; +0.0709] | < 0.001 | < 0.001 | evet |
| 2_arr_del15_pr_auc | arr_del15/T2 | d_pr_auc | +0.1177 [+0.1081; +0.1267] | < 0.001 | < 0.001 | evet |
| 3_arr_del15_bss | arr_del15/T2 | bss_platt | +0.0710 [+0.0631; +0.0783] | < 0.001 | < 0.001 | evet |
| 4_pinball_q050 | arr_delay/plan | d_pinball_q050 | -0.2264 [-0.2502; -0.2038] | < 0.001 | < 0.001 | evet |
| 5_pinball_q080 | arr_delay/plan | d_pinball_q080 | -0.1559 [-0.1990; -0.1119] | < 0.001 | < 0.001 | evet |
| 6_pinball_q095 | arr_delay/plan | d_pinball_q095 | +0.0376 [-0.0127; +0.0899] | 0.152 | 0.152 | hayır |
| 7_cancelled_pr_auc | cancelled/plan | d_pr_auc | -0.0062 [-0.0097; -0.0034] | < 0.001 | < 0.001 | evet |

### Hava katkısı (plan §6; T2 − plan, aynı uçuşlar; ikincil)

- arr_del15: d_roc_auc +0.0492 [+0.0446; +0.0537] · d_pr_auc +0.0903 [+0.0820; +0.0987] · d_brier_platt -0.0101 [-0.0113; -0.0088]
- arr_delay: d_pinball_q080 -0.9285 [-1.0731; -0.7925]
- oracle: not part of the final test (no oracle model is locked); the captured share is not reported

### ArrDel15 T2: olasılık kalitesi (aylık kayan Platt birincil, sabit Platt ikincil; sıralama metrikleri ham skorla)

| Yöntem | Brier | BSS (aynı yöntemle B1) | Log-loss | ECE | CITL | Eğim |
|---|---|---|---|---|---|---|
| ham | 0.1681 | 0.0771 | 0.5114 | 0.0205 | -0.0205 | 0.959 |
| platt | 0.1678 | 0.0739 | 0.5107 | 0.0148 | -0.0148 | 1.052 |
| isotonic | 0.1679 | 0.0728 | 0.5110 | 0.0152 | -0.0152 | 1.049 |
| platt_rolling | 0.1677 | 0.0710 | 0.5102 | 0.0043 | -0.0042 | 1.003 |

- ROC-AUC (ham) 0.7119, PR-AUC (ham) 0.4686, yaygınlık 0.2539; Origin × gün tabakalı AUC (keşifsel, M5): model 0.6848, B1 0.6568

| Ay | n | Yaygınlık | CITL ham | CITL Platt | CITL kayan Platt | ROC-AUC ham |
|---|---|---|---|---|---|---|
| 2025-03 | 383842 | 0.2069 | -0.0038 | -0.0167 | -0.0155 | 0.6928 |
| 2025-04 | 374989 | 0.2069 | -0.0035 | -0.0162 | -0.0054 | 0.6781 |
| 2025-05 | 386950 | 0.2531 | -0.0210 | -0.0393 | -0.0175 | 0.6942 |
| 2025-06 | 384688 | 0.3023 | -0.0464 | -0.0206 | -0.0240 | 0.7227 |
| 2025-07 | 392673 | 0.3111 | -0.0421 | -0.0168 | -0.0006 | 0.7281 |
| 2025-08 | 382682 | 0.2406 | -0.0051 | 0.0209 | 0.0380 | 0.7111 |

### Plan kantilleri: conformal kapsama (birincil: aylık kayan)

| Şema | P80 kapsama | P95 kapsama | Segment payı P80 | Segment payı P95 | Yetersiz ay (k > n) | %80 aralık (CQR) kapsama |
|---|---|---|---|---|---|---|
| rolling | 0.7902 | 0.9460 | 0.6667 | 0.9611 | - | 0.8033 |
| static | 0.7756 | 0.9417 | 0.7167 | 0.9389 | - | 0.7999 |
| public | 0.7669 | 0.9374 | 0.6333 | 0.9278 | - | 0.7937 |
- Ham kapsama: P80 0.7671, P95 0.9296 (statik = tek ofset; public = 2 ay gecikmeli 'kamu senaryosu', ikincil)

| Ay | n | P80 ham | P80 kayan | P80 statik | P80 public | P95 ham | P95 kayan | P95 statik | P95 public |
|---|---|---|---|---|---|---|---|---|---|
| 2025-03 | 383842 | 0.8119 | 0.8100 | 0.8064 | 0.7860 | 0.9464 | 0.9543 | 0.9534 | 0.9434 |
| 2025-04 | 374989 | 0.8118 | 0.8056 | 0.8062 | 0.8065 | 0.9477 | 0.9533 | 0.9544 | 0.9533 |
| 2025-05 | 386950 | 0.7719 | 0.7623 | 0.7654 | 0.7699 | 0.9331 | 0.9370 | 0.9413 | 0.9428 |
| 2025-06 | 384688 | 0.7233 | 0.7409 | 0.7465 | 0.7341 | 0.9123 | 0.9287 | 0.9304 | 0.9240 |
| 2025-07 | 392673 | 0.7099 | 0.7697 | 0.7331 | 0.7147 | 0.9034 | 0.9362 | 0.9221 | 0.9139 |
| 2025-08 | 382682 | 0.7760 | 0.8542 | 0.7979 | 0.7927 | 0.9357 | 0.9669 | 0.9494 | 0.9481 |

### İkincil karşılaştırmalar (B1'e göre; keşifsel, Holm dışı)

- `arr_del15/plan_matched`: d_roc_auc +0.0165 [+0.0124; +0.0204] · d_pr_auc +0.0273 [+0.0216; +0.0333] · bss_platt +0.0152 [+0.0117; +0.0189]
- `cancelled/T2`: d_roc_auc +0.1188 [+0.0939; +0.1403] · d_pr_auc +0.0682 [+0.0435; +0.0960] · bss_platt +0.0435 [+0.0264; +0.0593]
- `cancelled/T2_calendar`: d_roc_auc +0.0926 [+0.0635; +0.1175] · d_pr_auc +0.0222 [+0.0104; +0.0407] · bss_platt +0.0031 [-0.0268; +0.0243]
- `arr_delay/T2_matched`: d_pinball_q050 -0.6487 [-0.7108; -0.5886] · d_pinball_q080 -1.0844 [-1.2311; -0.9390] · d_pinball_q095 -0.6305 [-0.7441; -0.5210]

