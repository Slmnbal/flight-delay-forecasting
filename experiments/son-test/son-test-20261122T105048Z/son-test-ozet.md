# SON TEST SONUÇLARI (tek seferlik, 2026-03..08)

- Oluşturma (UTC): 2026-11-22T10:50:48.968766+00:00 · kilit kaydı: `experiments/son-test-kilidi.json` (sha256 `fee816c25ddf`) · kilit girdisi: `experiments/son-test-dondurma.json`
- git: `25ebfb622117a37c7a56ed22317eaa1f73725971` (kirli: False) · süre 2593.9 sn
- Kurallar: `experiments/son-test-on-kayit.md` (önceden kayıt). Olasılıklar Platt (Val-B'de fit), isotonic ikincil; sıralama metrikleri ham skorla. Sonuçlar olduğu gibi yazılır; testte ayar yapılmaz.
- Val-B sayıları (ör. iptal D2'nin Val-B AUC'si) başlık metriği değildir; başlık yalnızca bu tablodur.

## final_test: final test 2026-03..08

- Günler: 184 (2026-03-01 .. 2026-08-31) · gün blok bootstrap B = 1000, tohum 42, yüzdelik GA %95
- Tüm kabul ölçütleri geçti mi: **hayır**

### Kabul ölçütleri (plan §5.3)

| Ölçüt | Sonuç | Tanım |
|---|---|---|
| K1 | geçti | ArrDel15 T2 vs B1: ΔROC-AUC > 0 ve ΔPR-AUC > 0; ikisinde de GA alt sınırı > 0 ve Holm sonrası anlamlı |
| K2 | geçti | ArrDel15 BSS (aylık kayan Platt: model vs B1) > 0 ve GA alt sınırı > 0 |
| K3 | geçti | ArrDel15 aylık kayan Platt: |CITL| ≤ 0.01 ve eğim [0.9; 1.1] (rehearsal rule (pre-registration d): max(plan, rounded-up bootstrap half-width)) |
| K4 | geçti | Plan kantilleri vs B1 (ham): α 0,50/0,80/0,95 için Δpinball < 0, GA üst sınırı < 0 ve Holm sonrası anlamlı |
| K5 | GEÇMEDİ | Plan kantilleri, aylık kayan conformal: P80 kapsama [0.78, 0.82], P95 [0.94, 0.96]; Origin × ay (n ≥ 500) segmentlerinin ≥ 80%'i hedefin ±0.05 içinde (rehearsal rule (pre-registration d): max(plan, rounded-up bootstrap half-width)) |
| K6 | GEÇMEDİ | İptal plan vs B1: ΔPR-AUC > 0 ve GA alt sınırı > 0 (ham skor) |
| K7 | geçti | Sızıntı: §2.6 testleri geçti (beyan) ve kilitli modellerde çözülmemiş şüphe yok |

### Birincil aile (plan §5.2, Holm α = 0.05)

| # | Rol | Karşılaştırma | Δ [%95 GA] | p | p (Holm) | Anlamlı |
|---|---|---|---|---|---|---|
| 1_arr_del15_roc_auc | arr_del15/T2 | d_roc_auc | +0.0556 [+0.0499; +0.0612] | < 0.001 | < 0.001 | evet |
| 2_arr_del15_pr_auc | arr_del15/T2 | d_pr_auc | +0.1013 [+0.0915; +0.1105] | < 0.001 | < 0.001 | evet |
| 3_arr_del15_bss | arr_del15/T2 | bss_platt | +0.0625 [+0.0541; +0.0712] | < 0.001 | < 0.001 | evet |
| 4_pinball_q050 | arr_delay/plan | d_pinball_q050 | -0.2315 [-0.2586; -0.2016] | < 0.001 | < 0.001 | evet |
| 5_pinball_q080 | arr_delay/plan | d_pinball_q080 | -0.2168 [-0.2704; -0.1637] | < 0.001 | < 0.001 | evet |
| 6_pinball_q095 | arr_delay/plan | d_pinball_q095 | -0.1066 [-0.1422; -0.0713] | < 0.001 | < 0.001 | evet |
| 7_cancelled_pr_auc | cancelled/plan | d_pr_auc | -0.0005 [-0.0048; +0.0039] | 0.850 | 0.850 | hayır |

### Hava katkısı (plan §6; T2 − plan, aynı uçuşlar; ikincil)

- arr_del15: d_roc_auc +0.0363 [+0.0315; +0.0410] · d_pr_auc +0.0711 [+0.0618; +0.0800] · d_brier_platt -0.0083 [-0.0098; -0.0069]
- arr_delay: d_pinball_q080 -0.7560 [-0.9017; -0.6163]
- oracle: not part of the final test (no oracle model is locked); the captured share is not reported

### ArrDel15 T2: olasılık kalitesi (aylık kayan Platt birincil, sabit Platt ikincil; sıralama metrikleri ham skorla)

| Yöntem | Brier | BSS (aynı yöntemle B1) | Log-loss | ECE | CITL | Eğim |
|---|---|---|---|---|---|---|
| ham | 0.1723 | 0.0671 | 0.5215 | 0.0302 | -0.0302 | 0.940 |
| platt | 0.1716 | 0.0834 | 0.5192 | 0.0165 | -0.0163 | 1.016 |
| isotonic | 0.1716 | 0.0839 | 0.5193 | 0.0161 | -0.0161 | 1.013 |
| platt_rolling | 0.1716 | 0.0625 | 0.5193 | 0.0052 | -0.0025 | 1.002 |

- ROC-AUC (ham) 0.7120, PR-AUC (ham) 0.4767, yaygınlık 0.2626; Origin × gün tabakalı AUC (keşifsel, M5): model 0.6930, B1 0.6634

| Ay | n | Yaygınlık | CITL ham | CITL Platt | CITL kayan Platt | ROC-AUC ham |
|---|---|---|---|---|---|---|
| 2026-03 | 383592 | 0.2564 | -0.0539 | -0.0391 | -0.0401 | 0.6994 |
| 2026-04 | 384249 | 0.2139 | -0.0160 | -0.0010 | 0.0202 | 0.6949 |
| 2026-05 | 390398 | 0.2298 | -0.0228 | -0.0081 | 0.0168 | 0.6940 |
| 2026-06 | 382021 | 0.2750 | -0.0291 | -0.0157 | -0.0104 | 0.7171 |
| 2026-07 | 392034 | 0.3089 | -0.0296 | -0.0174 | -0.0043 | 0.7104 |
| 2026-08 | 383324 | 0.2914 | -0.0297 | -0.0169 | 0.0027 | 0.7284 |

### Plan kantilleri: conformal kapsama (birincil: aylık kayan)

| Şema | P80 kapsama | P95 kapsama | Segment payı P80 | Segment payı P95 | Yetersiz ay (k > n) | %80 aralık (CQR) kapsama |
|---|---|---|---|---|---|---|
| rolling | 0.7877 | 0.9447 | 0.6889 | 0.9778 | - | 0.7956 |
| static | 0.7792 | 0.9415 | 0.6389 | 0.9667 | - | 0.7923 |
| public | 0.7866 | 0.9448 | 0.5778 | 0.9556 | - | 0.7949 |
- Ham kapsama: P80 0.7698, P95 0.9373 (statik = tek ofset; public = 2 ay gecikmeli 'kamu senaryosu', ikincil)

| Ay | n | P80 ham | P80 kayan | P80 statik | P80 public | P95 ham | P95 kayan | P95 statik | P95 public |
|---|---|---|---|---|---|---|---|---|---|
| 2026-03 | 383592 | 0.7681 | 0.7758 | 0.7769 | 0.8050 | 0.9317 | 0.9357 | 0.9360 | 0.9494 |
| 2026-04 | 384249 | 0.8167 | 0.8314 | 0.8255 | 0.8528 | 0.9579 | 0.9652 | 0.9612 | 0.9702 |
| 2026-05 | 390398 | 0.7972 | 0.8090 | 0.8065 | 0.8054 | 0.9511 | 0.9574 | 0.9546 | 0.9543 |
| 2026-06 | 382021 | 0.7630 | 0.7547 | 0.7727 | 0.7790 | 0.9360 | 0.9294 | 0.9403 | 0.9456 |
| 2026-07 | 392034 | 0.7331 | 0.7560 | 0.7431 | 0.7455 | 0.9217 | 0.9306 | 0.9266 | 0.9306 |
| 2026-08 | 383324 | 0.7407 | 0.7994 | 0.7506 | 0.7326 | 0.9257 | 0.9499 | 0.9303 | 0.9188 |

### İkincil karşılaştırmalar (B1'e göre; keşifsel, Holm dışı)

- `arr_del15/plan_matched`: d_roc_auc +0.0193 [+0.0152; +0.0234] · d_pr_auc +0.0302 [+0.0234; +0.0365] · bss_platt +0.0172 [+0.0130; +0.0213]
- `cancelled/T2`: d_roc_auc +0.1043 [+0.0843; +0.1211] · d_pr_auc +0.0898 [+0.0619; +0.1182] · bss_platt +0.0376 [+0.0085; +0.0626]
- `cancelled/T2_calendar`: d_roc_auc +0.0826 [+0.0627; +0.0998] · d_pr_auc +0.0713 [+0.0471; +0.0959] · bss_platt +0.0263 [+0.0043; +0.0469]
- `arr_delay/T2_matched`: d_pinball_q050 -0.6386 [-0.7202; -0.5635] · d_pinball_q080 -0.9728 [-1.1476; -0.8170] · d_pinball_q095 -0.6279 [-0.7522; -0.5145]

