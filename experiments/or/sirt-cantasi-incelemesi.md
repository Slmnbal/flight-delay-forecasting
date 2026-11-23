# OR – ArrDel15 sırt çantası incelemesi (2026-11-22)

Koşu: `experiments/or/tampon-20261122T173803Z`. Gözlem: eşit bütçede ArrDel15'i en aza indiren sırt çantası (`plan_arrdel15_budget`), B1'in ortak düzey politikasından (`b1_budget`) biraz daha **kötü** (test: +0,0001 … +0,0033 ArrDel15). İnceleme yalnızca kod okuma ve var olan sonuç JSON'u ile yapıldı; yeni koşu yok, hiçbir sonuç değiştirilmedi.

## Kod hatası var mı?
Bulunmadı. `allocation.mckp_greedy` dışbükey zarf (convex hull) açgözlü çözümü doğru: bütçe aşılmıyor (kullanılan = bütçe), LP alt sınırı ile tamsayı çözüm arasındaki açık 0. Aday tamponlar düğümlerde (b = q_j − 15), orada ara değerleme kesindir. Sansürlü hücre sayısı (b = 0'da düğüm dışı) 236; küçük.

## Neden kötü? Optimizasyoncunun laneti + hücre dağılımı yaklaşımı
Sırt çantasının **beklediği** ArrDel15 ile gerçekleşen arasındaki fark bütçe büyüdükçe açılıyor. Geliştirme dönemi (2025-11..2026-02; testten önce, yaz etkisi yok), tamamlanan uçuşa ölçeklenmiş (× 1 436 759 / 1 393 174):

| Bütçe dk/uçuş | Beklenen | Gerçekleşen | Fark |
|---|---|---|---|
| 1 | 0,2254 | 0,2239 | −0,0015 |
| 5 | 0,1891 | 0,1986 | +0,0095 |
| 15 | 0,1386 | 0,1522 | +0,0136 |

Yorum: Hücre dağılımı uçuş kantillerinin düzey düzey ortalaması (Vincentizasyon, varsayım A6). Bu, hücrenin gerçek karışım dağılımından **daha dar**dır. ArrDel15 hedefi eşiğe (15 dk) yakın olasılık yoğunluğuna çok duyarlıdır; dar dağılım "birkaç dakikayla çok uçuş eşiğin altına iner" der. Sırt çantası tam da bu iyimser hücreleri seçer (optimizasyoncunun laneti: hatanın en lehte olduğu yerler seçilir). Dakika hedefli ortak düzey politikası (newsvendor) bu yoğunluğa daha az duyarlıdır, bu yüzden etkilenmez. Etki geliştirme döneminde de var; yalnızca yaz (K5) kaynaklı değil.

## Karar
- Sonuç olduğu gibi raporlanır (politika testten önce dondurulmuştu).
- README/model kartı: "ArrDel15 hedefli sırt çantası, hücre dağılımı yaklaşımı nedeniyle basit kuraldan iyi değil; dakika hedefli politika tercih edilir."
- Gelecek iş (keşifsel, ayrı etiketle): hücre CDF'sini uçuş CDF'lerinin ortalaması olarak (gerçek karışım) hesaplamak; yalnızca geliştirme döneminde seçilir. Test dönemi bu politika için zaten görüldüğünden testteki sonucu "son test sonucu" sayılmaz.
