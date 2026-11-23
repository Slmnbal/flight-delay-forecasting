**Etiket: keşifsel (post hoc), son test sonucu değildir.**

# Blok süre tamponu – çözücü uzantısı (Pyomo + HiGHS)

> Son test dönemi bu politikalar için ilk OR koşusunda (`tampon-20261122T173803Z`) görüldü; buradaki test sayıları keşifseldir ve son test sonucu yerine geçmez. Maliyetler varsayımdır; A1: 1 dk tampon = 1 dk daha az varış rötarı (model yeniden tahmin ettirilmez). Hücre dağılımı seçimi yalnızca geliştirme döneminde yapıldı ve test okunmadan önce donduruldu.

- Oluşturma (UTC): 2026-11-22T18:17:20.022695+00:00 · dondurma: `experiments/or/cozucu-20261122T181720Z/cozucu-dondurma.json` · toplayıcı: mean · hücre dağılımı (geliştirmede seçildi): **mixture**
- Çözücü sürümleri: {'pyomo': '6.11.0', 'highspy': '1.16.0', 'matplotlib': '3.11.2', 'scipy': '1.18.1'} · son test okundu mu: True · süre 2498.4 sn · tepe bellek 3.864 GB

## Geliştirme seçimi: hücre dağılımı (yalnızca 2025-11..2026-02)

- Kural: development only; (1) lower mean realised ArrDel15 over budgets if |difference| > 0.0001; (2) lower mean |realised - expected|; (3) vincentize
- Seçilen: **mixture** (realised ArrDel15)

| Dağılım | Ortalama gerçekleşen ArrDel15 | Ortalama |gerçekleşen − beklenen| |
|---|---|---|
| vincentize | 0.1943 | 0.0138 |
| mixture | 0.1926 | 0.0073 |

- İlk koşuyla yeniden üretim (dogrulama): kontrol True, karşılaştırılan 303, en büyük fark 0.000000000
- İlk koşuyla yeniden üretim (test): kontrol True, karşılaştırılan 303, en büyük fark 0.000000000

## Dönem: Geliştirme (2025-11..2026-02)

- Hücre: 24162 · günler: 120 (2025-11-01 .. 2026-02-28)
- Sırt çantası adayları: {"vincentize": {"candidates_per_cell": 6, "cells_censored_at_zero_buffer": 236}, "mixture": {"cells": 24162, "candidates_per_cell": 19, "candidate_levels": [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95], "cells_with_censored_flights_at_zero_buffer": 741, "censored_share_at_zero_buffer_mean": 0.012979758532741324, "seconds": 33.2}}
- LP boyutu: {'cells': 24162, 'pieces': 947585, 'variables': 971747, 'constraints': 24163} · kurulum 5.2 sn · kiriş hata sınırı 8204.6 uçuş·dk

### Dakika bütçesi: Pyomo LP (HiGHS) ve kapalı biçim

| Bütçe dk/uçuş | Kapalı biçim τ (durum) | LP τ (dual) | LP durumu | Maks. |Δb| dk | Tolerans içi pay | Göreli amaç farkı | Sertifika (alt/üst) | Kısıt ihlali | Uyum | LP sn |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.5286 (binding) | 0.5284 | binding | 1.012 | 1.0000 | 0.000031 | True/True | 0 | True | 232.4 |
| 2 | 0.5589 (binding) | 0.5587 | binding | 1.032 | 1.0000 | 0.000050 | True/True | 0 | True | 1.9 |
| 3 | 0.5825 (binding) | 0.5825 | binding | 1.002 | 1.0000 | 0.000071 | True/True | 0 | True | 2.3 |
| 5 | 0.6211 (binding) | 0.6214 | binding | 1.042 | 1.0000 | 0.000104 | True/True | 0 | True | 2.1 |
| 7.5 | 0.6622 (binding) | 0.6624 | binding | 1.026 | 1.0000 | 0.000144 | True/True | 0 | True | 12.3 |
| 10 | 0.6993 (binding) | 0.6991 | binding | 1.012 | 1.0000 | 0.000184 | True/True | 0 | True | 2.7 |
| 15 | 0.7675 (binding) | 0.7666 | binding | 1.125 | 1.0000 | 0.000211 | True/True | 0 | True | 23.0 |

### ArrDel15 sırt çantası: açgözlü, LP alt sınırı ve Pyomo MILP (HiGHS)

| Bütçe dk/uçuş | Dağılım | Açgözlü (beklenen geç uçuş) | LP alt sınırı | MILP | MILP − açgözlü | MIP gap | Sonlanma | Farklı hücre | Model hücre / ikili | MILP sn |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | vincentize | 314082.66 | 314082.65 | 314082.66 | -0.000 | 0.00000000 | optimal | 12 | 23926 / 81980 | 61.4 |
| 1 | mixture | 315173.36 | 315173.36 | 315173.42 | 0.061 | 0.00000019 | optimal | 21 | 24004 / 124364 | 2.9 |
| 2 | vincentize | 299495.87 | 299495.87 | 299495.87 | -0.001 | 0.00000001 | optimal | 15 | 23926 / 81980 | 23.2 |
| 2 | mixture | 303175.89 | 303175.89 | 303175.89 | 0.000 | 0.00000000 | optimal | 19 | 24004 / 124364 | 80.7 |
| 3 | vincentize | 286387.30 | 286387.29 | 286397.41 | 10.113 | 0.00003533 | maxTimeLimit | 21 | 23926 / 81980 | 142.4 |
| 3 | mixture | 292142.09 | 292142.09 | 292142.09 | 0.000 | 0.00000000 | optimal | 12 | 24004 / 124364 | 63.3 |
| 5 | vincentize | 263524.24 | 263524.24 | 263524.24 | -0.000 | 0.00000000 | optimal | 11 | 23926 / 81980 | 55.7 |
| 5 | mixture | 272247.93 | 272247.93 | 272247.93 | 0.000 | 0.00000000 | optimal | 14 | 24004 / 124364 | 106.8 |
| 7.5 | vincentize | 240153.89 | 240153.89 | 240153.89 | -0.001 | 0.00000000 | optimal | 4 | 23926 / 81980 | 31.5 |
| 7.5 | mixture | 250694.87 | 250694.87 | 250694.87 | 0.000 | 0.00000000 | optimal | 10 | 24004 / 124364 | 62.9 |
| 10 | vincentize | 221907.90 | 221907.90 | 221907.90 | -0.003 | 0.00000000 | optimal | 11 | 23926 / 81980 | 13.8 |
| 10 | mixture | 232148.86 | 232148.86 | 232148.86 | 0.000 | 0.00000000 | optimal | 9 | 24004 / 124364 | 88.8 |
| 15 | vincentize | 193095.99 | 193095.98 | 193097.86 | 1.879 | 0.00000977 | maxTimeLimit | 16 | 23926 / 81980 | 134.3 |
| 15 | mixture | 201555.04 | 201555.04 | 201555.14 | 0.094 | 0.00000047 | optimal | 5 | 24004 / 124364 | 4.0 |

### Eşit bütçe: gerçekleşen sonuçlar [%95 GA] ve sırt çantası beklenen vs gerçekleşen

| Bütçe dk/uçuş | Politika | Ek tampon dk/uçuş | ArrDel15 [GA] | Kalan rötar dk/uçuş [GA] | Beklenen ArrDel15 | Gerçekleşen − beklenen |
|---|---|---|---|---|---|---|
| 1 | Plan, ortak düzey (dakika hedefi) | 1.00 | 0.2232 [0.2078; 0.2398] | 16.77 [15.12; 18.52] | - | - |
| 1 | B1, ortak düzey (dakika hedefi) | 1.00 | 0.2228 [0.2072; 0.2394] | 16.79 [15.13; 18.53] | - | - |
| 1 | Sırt çantası, Vincentize hücre | 1.00 | 0.2239 [0.2084; 0.2406] | 16.85 [15.19; 18.60] | 0.2182 | 0.0058 |
| 1 | plan_arrdel15_budget_milp | 1.00 | 0.2239 [0.2084; 0.2406] | 16.85 [15.19; 18.60] | - | - |
| 1 | Sırt çantası, karışım hücre | 1.00 | 0.2232 [0.2077; 0.2397] | 16.82 [15.16; 18.57] | 0.2190 | 0.0042 |
| 1 | plan_arrdel15_mixture_milp | 1.00 | 0.2232 [0.2077; 0.2397] | 16.82 [15.16; 18.57] | - | - |
| 2 | Plan, ortak düzey (dakika hedefi) | 2.00 | 0.2158 [0.2005; 0.2322] | 16.36 [14.73; 18.07] | - | - |
| 2 | B1, ortak düzey (dakika hedefi) | 2.00 | 0.2153 [0.1999; 0.2317] | 16.37 [14.74; 18.09] | - | - |
| 2 | Sırt çantası, Vincentize hücre | 2.00 | 0.2171 [0.2019; 0.2335] | 16.48 [14.84; 18.21] | 0.2080 | 0.0091 |
| 2 | plan_arrdel15_budget_milp | 2.00 | 0.2171 [0.2019; 0.2335] | 16.48 [14.84; 18.21] | - | - |
| 2 | Sırt çantası, karışım hücre | 2.00 | 0.2156 [0.2005; 0.2320] | 16.41 [14.78; 18.14] | 0.2106 | 0.0050 |
| 2 | plan_arrdel15_mixture_milp | 2.00 | 0.2156 [0.2005; 0.2320] | 16.41 [14.78; 18.14] | - | - |
| 3 | Plan, ortak düzey (dakika hedefi) | 3.00 | 0.2089 [0.1939; 0.2251] | 15.97 [14.37; 17.67] | - | - |
| 3 | B1, ortak düzey (dakika hedefi) | 3.00 | 0.2086 [0.1935; 0.2248] | 15.99 [14.38; 17.68] | - | - |
| 3 | Sırt çantası, Vincentize hücre | 3.00 | 0.2107 [0.1957; 0.2270] | 16.11 [14.49; 17.81] | 0.1989 | 0.0118 |
| 3 | plan_arrdel15_budget_milp | 3.00 | 0.2107 [0.1957; 0.2270] | 16.11 [14.49; 17.82] | - | - |
| 3 | Sırt çantası, karışım hücre | 3.00 | 0.2087 [0.1939; 0.2249] | 16.03 [14.41; 17.72] | 0.2030 | 0.0058 |
| 3 | plan_arrdel15_mixture_milp | 3.00 | 0.2087 [0.1939; 0.2249] | 16.03 [14.41; 17.72] | - | - |
| 5 | Plan, ortak düzey (dakika hedefi) | 5.00 | 0.1966 [0.1819; 0.2125] | 15.26 [13.70; 16.91] | - | - |
| 5 | B1, ortak düzey (dakika hedefi) | 5.00 | 0.1967 [0.1820; 0.2126] | 15.28 [13.72; 16.95] | - | - |
| 5 | Sırt çantası, Vincentize hücre | 5.00 | 0.1986 [0.1842; 0.2144] | 15.37 [13.81; 17.03] | 0.1831 | 0.0155 |
| 5 | plan_arrdel15_budget_milp | 5.00 | 0.1986 [0.1842; 0.2144] | 15.37 [13.81; 17.03] | - | - |
| 5 | Sırt çantası, karışım hücre | 5.00 | 0.1965 [0.1820; 0.2124] | 15.31 [13.74; 16.98] | 0.1892 | 0.0074 |
| 5 | plan_arrdel15_mixture_milp | 5.00 | 0.1965 [0.1820; 0.2124] | 15.31 [13.74; 16.98] | - | - |
| 7.5 | Plan, ortak düzey (dakika hedefi) | 7.50 | 0.1832 [0.1690; 0.1986] | 14.46 [12.95; 16.06] | - | - |
| 7.5 | B1, ortak düzey (dakika hedefi) | 7.50 | 0.1832 [0.1689; 0.1985] | 14.49 [12.97; 16.10] | - | - |
| 7.5 | Sırt çantası, Vincentize hücre | 7.50 | 0.1851 [0.1710; 0.2005] | 14.56 [13.05; 16.16] | 0.1670 | 0.0181 |
| 7.5 | plan_arrdel15_budget_milp | 7.50 | 0.1851 [0.1710; 0.2005] | 14.56 [13.05; 16.16] | - | - |
| 7.5 | Sırt çantası, karışım hücre | 7.50 | 0.1832 [0.1692; 0.1986] | 14.51 [13.00; 16.11] | 0.1742 | 0.0089 |
| 7.5 | plan_arrdel15_mixture_milp | 7.50 | 0.1832 [0.1692; 0.1986] | 14.51 [13.00; 16.11] | - | - |
| 10 | Plan, ortak düzey (dakika hedefi) | 10.00 | 0.1710 [0.1573; 0.1860] | 13.74 [12.28; 15.28] | - | - |
| 10 | B1, ortak düzey (dakika hedefi) | 10.00 | 0.1716 [0.1578; 0.1865] | 13.77 [12.29; 15.32] | - | - |
| 10 | Sırt çantası, Vincentize hücre | 10.00 | 0.1727 [0.1590; 0.1875] | 13.90 [12.43; 15.46] | 0.1543 | 0.0184 |
| 10 | plan_arrdel15_budget_milp | 10.00 | 0.1727 [0.1590; 0.1875] | 13.90 [12.43; 15.46] | - | - |
| 10 | Sırt çantası, karışım hücre | 10.00 | 0.1711 [0.1574; 0.1860] | 13.80 [12.33; 15.35] | 0.1613 | 0.0098 |
| 10 | plan_arrdel15_mixture_milp | 10.00 | 0.1711 [0.1574; 0.1860] | 13.80 [12.33; 15.35] | - | - |
| 15 | Plan, ortak düzey (dakika hedefi) | 15.00 | 0.1503 [0.1375; 0.1640] | 12.46 [11.10; 13.92] | - | - |
| 15 | B1, ortak düzey (dakika hedefi) | 15.00 | 0.1509 [0.1382; 0.1649] | 12.51 [11.13; 13.97] | - | - |
| 15 | Sırt çantası, Vincentize hücre | 15.00 | 0.1522 [0.1395; 0.1658] | 12.70 [11.31; 14.16] | 0.1341 | 0.0181 |
| 15 | plan_arrdel15_budget_milp | 15.00 | 0.1522 [0.1395; 0.1658] | 12.70 [11.31; 14.16] | - | - |
| 15 | Sırt çantası, karışım hücre | 15.00 | 0.1502 [0.1374; 0.1639] | 12.54 [11.16; 14.00] | 0.1401 | 0.0101 |
| 15 | plan_arrdel15_mixture_milp | 15.00 | 0.1502 [0.1374; 0.1639] | 12.54 [11.16; 14.00] | - | - |

| Bütçe dk/uçuş | Karşılaştırma | Δ ArrDel15 [GA] | Δ kalan rötar dk [GA] |
|---|---|---|---|
| 1 | plan_budget-b1_budget | 0.0004 [0.0000; 0.0008] | -0.01 [-0.03; 0.01] |
| 1 | plan_arrdel15_budget-b1_budget | 0.0011 [0.0008; 0.0014] | 0.07 [0.05; 0.08] |
| 1 | plan_arrdel15_budget_milp-b1_budget | 0.0011 [0.0008; 0.0014] | 0.07 [0.05; 0.08] |
| 1 | plan_arrdel15_mixture-b1_budget | 0.0004 [0.0000; 0.0006] | 0.03 [0.02; 0.05] |
| 1 | plan_arrdel15_mixture_milp-b1_budget | 0.0004 [0.0000; 0.0007] | 0.03 [0.02; 0.05] |
| 1 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0008 [-0.0010; -0.0005] | -0.03 [-0.04; -0.02] |
| 2 | plan_budget-b1_budget | 0.0004 [-0.0001; 0.0009] | -0.01 [-0.04; 0.01] |
| 2 | plan_arrdel15_budget-b1_budget | 0.0018 [0.0014; 0.0021] | 0.11 [0.09; 0.13] |
| 2 | plan_arrdel15_budget_milp-b1_budget | 0.0018 [0.0014; 0.0021] | 0.11 [0.09; 0.13] |
| 2 | plan_arrdel15_mixture-b1_budget | 0.0003 [-0.0002; 0.0007] | 0.04 [0.02; 0.06] |
| 2 | plan_arrdel15_mixture_milp-b1_budget | 0.0003 [-0.0002; 0.0007] | 0.04 [0.02; 0.06] |
| 2 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0015 [-0.0018; -0.0011] | -0.07 [-0.08; -0.05] |
| 3 | plan_budget-b1_budget | 0.0003 [-0.0003; 0.0008] | -0.02 [-0.05; 0.02] |
| 3 | plan_arrdel15_budget-b1_budget | 0.0021 [0.0016; 0.0024] | 0.12 [0.10; 0.14] |
| 3 | plan_arrdel15_budget_milp-b1_budget | 0.0021 [0.0017; 0.0025] | 0.12 [0.10; 0.14] |
| 3 | plan_arrdel15_mixture-b1_budget | 0.0001 [-0.0004; 0.0006] | 0.04 [0.01; 0.06] |
| 3 | plan_arrdel15_mixture_milp-b1_budget | 0.0001 [-0.0004; 0.0006] | 0.04 [0.01; 0.06] |
| 3 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0020 [-0.0023; -0.0016] | -0.08 [-0.10; -0.06] |
| 5 | plan_budget-b1_budget | -0.0001 [-0.0008; 0.0005] | -0.02 [-0.06; 0.02] |
| 5 | plan_arrdel15_budget-b1_budget | 0.0019 [0.0015; 0.0024] | 0.09 [0.07; 0.11] |
| 5 | plan_arrdel15_budget_milp-b1_budget | 0.0019 [0.0015; 0.0024] | 0.09 [0.07; 0.11] |
| 5 | plan_arrdel15_mixture-b1_budget | -0.0001 [-0.0008; 0.0005] | 0.03 [-0.01; 0.06] |
| 5 | plan_arrdel15_mixture_milp-b1_budget | -0.0001 [-0.0008; 0.0005] | 0.03 [-0.01; 0.06] |
| 5 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0021 [-0.0024; -0.0018] | -0.06 [-0.08; -0.05] |
| 7.5 | plan_budget-b1_budget | -0.0000 [-0.0007; 0.0006] | -0.02 [-0.07; 0.01] |
| 7.5 | plan_arrdel15_budget-b1_budget | 0.0019 [0.0012; 0.0025] | 0.07 [0.03; 0.11] |
| 7.5 | plan_arrdel15_budget_milp-b1_budget | 0.0019 [0.0012; 0.0025] | 0.07 [0.03; 0.11] |
| 7.5 | plan_arrdel15_mixture-b1_budget | -0.0000 [-0.0007; 0.0006] | 0.02 [-0.01; 0.06] |
| 7.5 | plan_arrdel15_mixture_milp-b1_budget | -0.0000 [-0.0007; 0.0006] | 0.02 [-0.01; 0.06] |
| 7.5 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0019 [-0.0022; -0.0016] | -0.05 [-0.06; -0.03] |
| 10 | plan_budget-b1_budget | -0.0005 [-0.0011; 0.0000] | -0.03 [-0.07; 0.01] |
| 10 | plan_arrdel15_budget-b1_budget | 0.0011 [0.0004; 0.0018] | 0.13 [0.09; 0.17] |
| 10 | plan_arrdel15_budget_milp-b1_budget | 0.0011 [0.0004; 0.0018] | 0.13 [0.09; 0.17] |
| 10 | plan_arrdel15_mixture-b1_budget | -0.0005 [-0.0011; 0.0001] | 0.03 [-0.01; 0.07] |
| 10 | plan_arrdel15_mixture_milp-b1_budget | -0.0005 [-0.0011; 0.0001] | 0.03 [-0.01; 0.07] |
| 10 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0016 [-0.0020; -0.0013] | -0.10 [-0.11; -0.09] |
| 15 | plan_budget-b1_budget | -0.0006 [-0.0012; 0.0001] | -0.05 [-0.09; -0.01] |
| 15 | plan_arrdel15_budget-b1_budget | 0.0013 [0.0006; 0.0019] | 0.19 [0.15; 0.23] |
| 15 | plan_arrdel15_budget_milp-b1_budget | 0.0013 [0.0006; 0.0019] | 0.19 [0.15; 0.23] |
| 15 | plan_arrdel15_mixture-b1_budget | -0.0007 [-0.0013; -0.0002] | 0.03 [-0.01; 0.06] |
| 15 | plan_arrdel15_mixture_milp-b1_budget | -0.0007 [-0.0013; -0.0002] | 0.03 [-0.01; 0.06] |
| 15 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0020 [-0.0024; -0.0016] | -0.16 [-0.18; -0.15] |

## Dönem: Son test dönemi (2026-03..2026-08), keşifsel (post hoc)

> Bu dönemin bütün sayıları **keşifsel (post hoc), son test sonucu değildir**.

- Hücre: 24765 · günler: 184 (2026-03-01 .. 2026-08-31)
- Sırt çantası adayları: {"vincentize": {"candidates_per_cell": 6, "cells_censored_at_zero_buffer": 226}, "mixture": {"cells": 24765, "candidates_per_cell": 19, "candidate_levels": [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95], "cells_with_censored_flights_at_zero_buffer": 707, "censored_share_at_zero_buffer_mean": 0.011869190241242732, "seconds": 60.6}}
- LP boyutu: {'cells': 24765, 'pieces': 1015081, 'variables': 1039846, 'constraints': 24766} · kurulum 5.8 sn · kiriş hata sınırı 13827.7 uçuş·dk

### Dakika bütçesi: Pyomo LP (HiGHS) ve kapalı biçim

| Bütçe dk/uçuş | Kapalı biçim τ (durum) | LP τ (dual) | LP durumu | Maks. |Δb| dk | Tolerans içi pay | Göreli amaç farkı | Sertifika (alt/üst) | Kısıt ihlali | Uyum | LP sn |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.4992 (binding) | 0.4934 | binding | 0.986 | 1.0000 | 0.000003 | True/True | 0 | True | 304.3 |
| 2 | 0.5299 (binding) | 0.5300 | binding | 1.013 | 1.0000 | 0.000040 | True/True | 0 | True | 2.2 |
| 3 | 0.5524 (binding) | 0.5525 | binding | 1.015 | 1.0000 | 0.000052 | True/True | 0 | True | 1.8 |
| 5 | 0.5894 (binding) | 0.5896 | binding | 1.017 | 1.0000 | 0.000078 | True/True | 0 | True | 2.1 |
| 7.5 | 0.6286 (binding) | 0.6289 | binding | 1.029 | 1.0000 | 0.000113 | True/True | 0 | True | 12.1 |
| 10 | 0.6639 (binding) | 0.6641 | binding | 1.033 | 1.0000 | 0.000145 | True/True | 0 | True | 2.2 |
| 15 | 0.7286 (binding) | 0.7287 | binding | 1.012 | 1.0000 | 0.000212 | True/True | 0 | True | 9.0 |

### ArrDel15 sırt çantası: açgözlü, LP alt sınırı ve Pyomo MILP (HiGHS)

| Bütçe dk/uçuş | Dağılım | Açgözlü (beklenen geç uçuş) | LP alt sınırı | MILP | MILP − açgözlü | MIP gap | Sonlanma | Farklı hücre | Model hücre / ikili | MILP sn |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | vincentize | 568344.41 | 568344.40 | 568344.84 | 0.436 | 0.00000078 | optimal | 24 | 24539 / 85504 | 1.4 |
| 1 | mixture | 569525.74 | 569525.74 | 569525.90 | 0.161 | 0.00000028 | optimal | 14 | 24619 / 135027 | 2.7 |
| 2 | vincentize | 543811.89 | 543811.87 | 543812.06 | 0.171 | 0.00000034 | optimal | 12 | 24539 / 85504 | 2.1 |
| 2 | mixture | 548702.26 | 548702.26 | 548702.26 | -0.001 | 0.00000000 | optimal | 19 | 24619 / 135027 | 58.6 |
| 3 | vincentize | 521848.07 | 521848.06 | 521848.44 | 0.370 | 0.00000072 | optimal | 17 | 24539 / 85504 | 1.7 |
| 3 | mixture | 529540.87 | 529540.87 | 529541.11 | 0.239 | 0.00000045 | optimal | 15 | 24619 / 135027 | 5.1 |
| 5 | vincentize | 482963.49 | 482963.48 | 482975.44 | 11.959 | 0.00002477 | maxTimeLimit | 10 | 24539 / 85504 | 169.3 |
| 5 | mixture | 494736.17 | 494736.17 | 494736.17 | -0.000 | 0.00000000 | optimal | 15 | 24619 / 135027 | 77.1 |
| 7.5 | vincentize | 441548.26 | 441548.25 | 441548.25 | -0.002 | 0.00000000 | optimal | 10 | 24539 / 85504 | 16.9 |
| 7.5 | mixture | 456237.34 | 456237.34 | 456237.36 | 0.015 | 0.00000003 | optimal | 11 | 24619 / 135027 | 3.8 |
| 10 | vincentize | 405884.81 | 405884.80 | 405884.81 | -0.001 | 0.00000001 | optimal | 11 | 24539 / 85504 | 98.2 |
| 10 | mixture | 422232.93 | 422232.93 | 422232.93 | 0.000 | 0.00000000 | optimal | 12 | 24619 / 135027 | 79.3 |
| 15 | vincentize | 349882.79 | 349882.79 | 349882.79 | -0.005 | 0.00000000 | optimal | 10 | 24539 / 85504 | 18.3 |
| 15 | mixture | 365248.10 | 365248.10 | 365248.10 | 0.000 | 0.00000000 | optimal | 11 | 24619 / 135027 | 81.0 |

### Eşit bütçe: gerçekleşen sonuçlar [%95 GA] ve sırt çantası beklenen vs gerçekleşen

| Bütçe dk/uçuş | Politika | Ek tampon dk/uçuş | ArrDel15 [GA] | Kalan rötar dk/uçuş [GA] | Beklenen ArrDel15 | Gerçekleşen − beklenen |
|---|---|---|---|---|---|---|
| 1 | Plan, ortak düzey (dakika hedefi) | 1.00 | 0.2532 [0.2418; 0.2641] | 19.30 [18.05; 20.51] | - | - |
| 1 | B1, ortak düzey (dakika hedefi) | 1.00 | 0.2529 [0.2414; 0.2639] | 19.31 [18.06; 20.51] | - | - |
| 1 | Sırt çantası, Vincentize hücre | 1.00 | 0.2531 [0.2416; 0.2639] | 19.38 [18.13; 20.59] | 0.2389 | 0.0142 |
| 1 | plan_arrdel15_budget_milp | 1.00 | 0.2531 [0.2416; 0.2639] | 19.38 [18.13; 20.58] | - | - |
| 1 | Sırt çantası, karışım hücre | 1.00 | 0.2524 [0.2410; 0.2632] | 19.35 [18.09; 20.55] | 0.2395 | 0.0130 |
| 1 | plan_arrdel15_mixture_milp | 1.00 | 0.2524 [0.2410; 0.2632] | 19.35 [18.09; 20.55] | - | - |
| 2 | Plan, ortak düzey (dakika hedefi) | 2.00 | 0.2450 [0.2337; 0.2559] | 18.81 [17.57; 20.00] | - | - |
| 2 | B1, ortak düzey (dakika hedefi) | 2.00 | 0.2448 [0.2333; 0.2558] | 18.82 [17.59; 20.01] | - | - |
| 2 | Sırt çantası, Vincentize hücre | 2.00 | 0.2452 [0.2339; 0.2559] | 18.94 [17.70; 20.12] | 0.2285 | 0.0166 |
| 2 | plan_arrdel15_budget_milp | 2.00 | 0.2452 [0.2339; 0.2559] | 18.94 [17.70; 20.12] | - | - |
| 2 | Sırt çantası, karışım hücre | 2.00 | 0.2440 [0.2327; 0.2546] | 18.87 [17.64; 20.06] | 0.2306 | 0.0133 |
| 2 | plan_arrdel15_mixture_milp | 2.00 | 0.2440 [0.2327; 0.2546] | 18.87 [17.64; 20.06] | - | - |
| 3 | Plan, ortak düzey (dakika hedefi) | 3.00 | 0.2376 [0.2263; 0.2484] | 18.35 [17.13; 19.53] | - | - |
| 3 | B1, ortak düzey (dakika hedefi) | 3.00 | 0.2373 [0.2259; 0.2483] | 18.37 [17.14; 19.53] | - | - |
| 3 | Sırt çantası, Vincentize hücre | 3.00 | 0.2381 [0.2270; 0.2487] | 18.51 [17.29; 19.67] | 0.2193 | 0.0188 |
| 3 | plan_arrdel15_budget_milp | 3.00 | 0.2381 [0.2270; 0.2487] | 18.51 [17.29; 19.67] | - | - |
| 3 | Sırt çantası, karışım hücre | 3.00 | 0.2364 [0.2252; 0.2470] | 18.42 [17.20; 19.59] | 0.2226 | 0.0138 |
| 3 | plan_arrdel15_mixture_milp | 3.00 | 0.2364 [0.2252; 0.2470] | 18.42 [17.20; 19.59] | - | - |
| 5 | Plan, ortak düzey (dakika hedefi) | 5.00 | 0.2240 [0.2128; 0.2347] | 17.51 [16.31; 18.65] | - | - |
| 5 | B1, ortak düzey (dakika hedefi) | 5.00 | 0.2236 [0.2123; 0.2344] | 17.53 [16.33; 18.66] | - | - |
| 5 | Sırt çantası, Vincentize hücre | 5.00 | 0.2252 [0.2140; 0.2356] | 17.70 [16.51; 18.82] | 0.2030 | 0.0222 |
| 5 | plan_arrdel15_budget_milp | 5.00 | 0.2252 [0.2140; 0.2356] | 17.70 [16.51; 18.82] | - | - |
| 5 | Sırt çantası, karışım hücre | 5.00 | 0.2228 [0.2119; 0.2332] | 17.59 [16.40; 18.72] | 0.2080 | 0.0149 |
| 5 | plan_arrdel15_mixture_milp | 5.00 | 0.2228 [0.2119; 0.2332] | 17.59 [16.40; 18.72] | - | - |
| 7.5 | Plan, ortak düzey (dakika hedefi) | 7.50 | 0.2087 [0.1977; 0.2190] | 16.57 [15.40; 17.67] | - | - |
| 7.5 | B1, ortak düzey (dakika hedefi) | 7.50 | 0.2085 [0.1973; 0.2188] | 16.58 [15.43; 17.68] | - | - |
| 7.5 | Sırt çantası, Vincentize hücre | 7.50 | 0.2109 [0.2000; 0.2211] | 16.75 [15.60; 17.85] | 0.1857 | 0.0252 |
| 7.5 | plan_arrdel15_budget_milp | 7.50 | 0.2109 [0.2000; 0.2211] | 16.75 [15.60; 17.85] | - | - |
| 7.5 | Sırt çantası, karışım hücre | 7.50 | 0.2079 [0.1972; 0.2181] | 16.64 [15.49; 17.74] | 0.1919 | 0.0161 |
| 7.5 | plan_arrdel15_mixture_milp | 7.50 | 0.2079 [0.1972; 0.2181] | 16.64 [15.49; 17.74] | - | - |
| 10 | Plan, ortak düzey (dakika hedefi) | 10.00 | 0.1950 [0.1842; 0.2050] | 15.71 [14.59; 16.79] | - | - |
| 10 | B1, ortak düzey (dakika hedefi) | 10.00 | 0.1948 [0.1838; 0.2049] | 15.73 [14.61; 16.80] | - | - |
| 10 | Sırt çantası, Vincentize hücre | 10.00 | 0.1981 [0.1873; 0.2081] | 15.92 [14.80; 16.99] | 0.1709 | 0.0273 |
| 10 | plan_arrdel15_budget_milp | 10.00 | 0.1981 [0.1873; 0.2081] | 15.92 [14.80; 16.99] | - | - |
| 10 | Sırt çantası, karışım hücre | 10.00 | 0.1947 [0.1839; 0.2047] | 15.78 [14.65; 16.85] | 0.1777 | 0.0170 |
| 10 | plan_arrdel15_mixture_milp | 10.00 | 0.1947 [0.1839; 0.2047] | 15.78 [14.65; 16.85] | - | - |
| 15 | Plan, ortak düzey (dakika hedefi) | 15.00 | 0.1715 [0.1614; 0.1811] | 14.21 [13.16; 15.22] | - | - |
| 15 | B1, ortak düzey (dakika hedefi) | 15.00 | 0.1715 [0.1611; 0.1812] | 14.24 [13.19; 15.25] | - | - |
| 15 | Sırt çantası, Vincentize hücre | 15.00 | 0.1740 [0.1640; 0.1834] | 14.50 [13.44; 15.52] | 0.1473 | 0.0268 |
| 15 | plan_arrdel15_budget_milp | 15.00 | 0.1740 [0.1640; 0.1834] | 14.50 [13.44; 15.52] | - | - |
| 15 | Sırt çantası, karışım hücre | 15.00 | 0.1712 [0.1611; 0.1808] | 14.30 [13.24; 15.32] | 0.1538 | 0.0174 |
| 15 | plan_arrdel15_mixture_milp | 15.00 | 0.1712 [0.1611; 0.1808] | 14.30 [13.24; 15.32] | - | - |

| Bütçe dk/uçuş | Karşılaştırma | Δ ArrDel15 [GA] | Δ kalan rötar dk [GA] |
|---|---|---|---|
| 1 | plan_budget-b1_budget | 0.0003 [-0.0000; 0.0006] | -0.01 [-0.03; 0.00] |
| 1 | plan_arrdel15_budget-b1_budget | 0.0001 [-0.0002; 0.0005] | 0.07 [0.06; 0.08] |
| 1 | plan_arrdel15_budget_milp-b1_budget | 0.0001 [-0.0002; 0.0005] | 0.07 [0.06; 0.08] |
| 1 | plan_arrdel15_mixture-b1_budget | -0.0005 [-0.0009; -0.0002] | 0.03 [0.02; 0.05] |
| 1 | plan_arrdel15_mixture_milp-b1_budget | -0.0005 [-0.0009; -0.0002] | 0.03 [0.02; 0.05] |
| 1 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0007 [-0.0008; -0.0005] | -0.03 [-0.04; -0.03] |
| 2 | plan_budget-b1_budget | 0.0002 [-0.0002; 0.0006] | -0.01 [-0.03; 0.01] |
| 2 | plan_arrdel15_budget-b1_budget | 0.0004 [0.0000; 0.0008] | 0.11 [0.10; 0.13] |
| 2 | plan_arrdel15_budget_milp-b1_budget | 0.0004 [0.0000; 0.0008] | 0.11 [0.10; 0.13] |
| 2 | plan_arrdel15_mixture-b1_budget | -0.0008 [-0.0012; -0.0004] | 0.05 [0.03; 0.07] |
| 2 | plan_arrdel15_mixture_milp-b1_budget | -0.0008 [-0.0012; -0.0004] | 0.05 [0.03; 0.07] |
| 2 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0012 [-0.0014; -0.0010] | -0.06 [-0.07; -0.05] |
| 3 | plan_budget-b1_budget | 0.0003 [-0.0001; 0.0007] | -0.01 [-0.04; 0.01] |
| 3 | plan_arrdel15_budget-b1_budget | 0.0007 [0.0004; 0.0011] | 0.15 [0.13; 0.16] |
| 3 | plan_arrdel15_budget_milp-b1_budget | 0.0007 [0.0004; 0.0011] | 0.14 [0.13; 0.16] |
| 3 | plan_arrdel15_mixture-b1_budget | -0.0009 [-0.0014; -0.0004] | 0.06 [0.04; 0.08] |
| 3 | plan_arrdel15_mixture_milp-b1_budget | -0.0009 [-0.0014; -0.0004] | 0.06 [0.04; 0.08] |
| 3 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0017 [-0.0019; -0.0014] | -0.09 [-0.10; -0.08] |
| 5 | plan_budget-b1_budget | 0.0004 [-0.0001; 0.0008] | -0.01 [-0.04; 0.01] |
| 5 | plan_arrdel15_budget-b1_budget | 0.0016 [0.0012; 0.0019] | 0.17 [0.15; 0.19] |
| 5 | plan_arrdel15_budget_milp-b1_budget | 0.0016 [0.0013; 0.0019] | 0.17 [0.15; 0.19] |
| 5 | plan_arrdel15_mixture-b1_budget | -0.0008 [-0.0012; -0.0004] | 0.06 [0.05; 0.08] |
| 5 | plan_arrdel15_mixture_milp-b1_budget | -0.0008 [-0.0012; -0.0004] | 0.06 [0.05; 0.08] |
| 5 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0024 [-0.0027; -0.0020] | -0.11 [-0.13; -0.09] |
| 7.5 | plan_budget-b1_budget | 0.0002 [-0.0003; 0.0007] | -0.02 [-0.05; 0.01] |
| 7.5 | plan_arrdel15_budget-b1_budget | 0.0024 [0.0020; 0.0028] | 0.17 [0.15; 0.19] |
| 7.5 | plan_arrdel15_budget_milp-b1_budget | 0.0024 [0.0020; 0.0028] | 0.17 [0.15; 0.19] |
| 7.5 | plan_arrdel15_mixture-b1_budget | -0.0005 [-0.0010; -0.0001] | 0.06 [0.04; 0.07] |
| 7.5 | plan_arrdel15_mixture_milp-b1_budget | -0.0005 [-0.0010; -0.0001] | 0.06 [0.04; 0.07] |
| 7.5 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0030 [-0.0032; -0.0027] | -0.11 [-0.12; -0.10] |
| 10 | plan_budget-b1_budget | 0.0002 [-0.0004; 0.0007] | -0.02 [-0.06; 0.01] |
| 10 | plan_arrdel15_budget-b1_budget | 0.0033 [0.0028; 0.0038] | 0.19 [0.16; 0.22] |
| 10 | plan_arrdel15_budget_milp-b1_budget | 0.0033 [0.0028; 0.0038] | 0.19 [0.16; 0.22] |
| 10 | plan_arrdel15_mixture-b1_budget | -0.0002 [-0.0006; 0.0003] | 0.05 [0.02; 0.07] |
| 10 | plan_arrdel15_mixture_milp-b1_budget | -0.0002 [-0.0006; 0.0003] | 0.05 [0.02; 0.07] |
| 10 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0035 [-0.0037; -0.0032] | -0.14 [-0.16; -0.12] |
| 15 | plan_budget-b1_budget | 0.0000 [-0.0005; 0.0006] | -0.03 [-0.06; 0.01] |
| 15 | plan_arrdel15_budget-b1_budget | 0.0026 [0.0019; 0.0032] | 0.26 [0.22; 0.30] |
| 15 | plan_arrdel15_budget_milp-b1_budget | 0.0026 [0.0019; 0.0032] | 0.26 [0.22; 0.30] |
| 15 | plan_arrdel15_mixture-b1_budget | -0.0003 [-0.0008; 0.0002] | 0.06 [0.02; 0.09] |
| 15 | plan_arrdel15_mixture_milp-b1_budget | -0.0003 [-0.0008; 0.0002] | 0.06 [0.02; 0.09] |
| 15 | plan_arrdel15_mixture-plan_arrdel15_budget | -0.0029 [-0.0031; -0.0026] | -0.20 [-0.21; -0.19] |

## Grafikler

- `experiments/or/cozucu-20261122T181720Z/grafikler/butce-egrisi-dogrulama.png`
- `experiments/or/cozucu-20261122T181720Z/grafikler/tau-duyarliligi-dogrulama.png`
- `experiments/or/cozucu-20261122T181720Z/grafikler/sirt-cantasi-beklenen-gerceklesen-dogrulama.png`
- `experiments/or/cozucu-20261122T181720Z/grafikler/butce-egrisi-test.png`
- `experiments/or/cozucu-20261122T181720Z/grafikler/tau-duyarliligi-test.png`
- `experiments/or/cozucu-20261122T181720Z/grafikler/sirt-cantasi-beklenen-gerceklesen-test.png`

