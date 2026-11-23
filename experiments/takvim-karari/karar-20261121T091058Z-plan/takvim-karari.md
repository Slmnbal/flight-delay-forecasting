# Takvim özelliği kararı (önceden kayıtlı kural, yalnızca Val-A) – plan

- Takvimli: `run-20261121T073825Z` · takvimsiz: `run-20261121T080035Z` · Val-B okunmadı.
- Geçerli karşılaştırma: **evet**

## arr_del15: takvim özellikleri ÇIKARILIR

Kural: Val-A Brier lower in total AND in >= 3 of 4 months

| Metrik | Toplam takvimli | Toplam takvimsiz | Eylül | Ekim | Kasım | Aralık | Koşul |
|---|---|---|---|---|---|---|---|
| brier | 0.1672 | 0.1646 | 0.1371 → 0.1393 | 0.1653 → 0.1599 | 0.1661 → 0.1614 | 0.1999 → 0.1973 | evet |

Bilgi (karar dışı): `{"log_loss_total": [0.5146602535055599, 0.5051067229559446], "roc_auc_total": [0.6560082768322388, 0.6543315519655396], "citl_months": [{"9": -0.003422350450545869, "10": -0.06566951062573817, "11": -0.0643050765971499, "12": -0.08882049420433816}, {"9": 0.03934730653852225, "10": 0.010353321710600688, "11": -7.171101898101329e-05, "12": -0.07185491641247604}]}`

## arr_delay: takvim özellikleri ÇIKARILIR

Kural: Val-A pinball P80 AND P95 each lower in total AND in >= 3 of 4 months

| Metrik | Toplam takvimli | Toplam takvimsiz | Eylül | Ekim | Kasım | Aralık | Koşul |
|---|---|---|---|---|---|---|---|
| pinball_q080 | 12.8747 | 12.6754 | 10.6269 → 10.8232 | 11.8100 → 11.4680 | 13.4263 → 13.0321 | 15.6584 → 15.4117 | evet |
| pinball_q095 | 8.1372 | 7.8302 | 6.9385 → 6.8938 | 7.3237 → 7.1125 | 8.5019 → 7.8962 | 9.8118 → 9.4374 | evet |

Bilgi (karar dışı): `{"pinball_q050_total": [11.742560294146669, 11.74341193380851]}`

