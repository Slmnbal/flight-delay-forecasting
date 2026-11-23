# Takvim özelliği kararı (önceden kayıtlı kural, yalnızca Val-A) – T2

- Takvimli: `run-20261120T175822Z` · takvimsiz: `run-20261121T082853Z` · Val-B okunmadı.
- Geçerli karşılaştırma: **evet**

## arr_del15: takvim özellikleri ÇIKARILIR

Kural: Val-A Brier lower in total AND in >= 3 of 4 months

| Metrik | Toplam takvimli | Toplam takvimsiz | Eylül | Ekim | Kasım | Aralık | Koşul |
|---|---|---|---|---|---|---|---|
| brier | 0.1586 | 0.1558 | 0.1330 → 0.1333 | 0.1587 → 0.1543 | 0.1571 → 0.1524 | 0.1851 → 0.1828 | evet |

Bilgi (karar dışı): `{"log_loss_total": [0.4912429713692518, 0.4831297682072132], "roc_auc_total": [0.705697584876181, 0.7040751715765227], "citl_months": [{"9": -0.010680059489435428, "10": -0.06330011682905404, "11": -0.06443473489913942, "12": -0.0757956034916542}, {"9": 0.023896208442005934, "10": -0.0250691418907511, "11": -0.032390084987602596, "12": -0.0650879701044959}]}`

## arr_delay: takvim özellikleri ÇIKARILIR

Kural: Val-A pinball P80 AND P95 each lower in total AND in >= 3 of 4 months

| Metrik | Toplam takvimli | Toplam takvimsiz | Eylül | Ekim | Kasım | Aralık | Koşul |
|---|---|---|---|---|---|---|---|
| pinball_q080 | 12.2572 | 12.0368 | 10.3208 → 10.3326 | 11.3194 → 10.9830 | 12.7564 → 12.4048 | 14.6534 → 14.4557 | evet |
| pinball_q095 | 7.7458 | 7.4324 | 6.5145 → 6.4990 | 7.0492 → 6.7331 | 8.2036 → 7.6492 | 9.2385 → 8.8710 | evet |

Bilgi (karar dışı): `{"pinball_q050_total": [11.417541728684668, 11.348685994843006]}`

