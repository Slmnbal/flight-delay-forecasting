# Arayüz verisi dışa aktarımı – notlar

Kod: `deliverables/src/flight_delay/modeling/interface_export.py` (saf yardımcılar, doğrulayıcı) ve
`run_interface_export.py` (CLI, veri hattı). Testler: `deliverables/tests/unit/modeling/test_interface_export.py`.
Sözleşme: `experiments/arayuz-sozlesmesi.json` (sema_surumu 0.1.0), plan §9. **Hiçbir şey çalıştırılmadı; süre, bellek
ve dosya boyutları ölçülmedi.**

## Çalıştırma (proje kökü `projects/havayolu-ds/`, düzenlenebilir kurulum)

```
python -m pytest deliverables/tests/unit/modeling/test_interface_export.py -q   # yeni testler (22 durum)
python -m pytest deliverables/tests/unit -q                                      # tümü: 613 + 22 bekleniyor
python -m flight_delay.modeling.run_interface_export --dry-run                   # denetim + özet dosyaları bellekte; yazmaz
python -m flight_delay.modeling.run_interface_export --summary-only --out deliverables/src/web/veri-ozet
python -m flight_delay.modeling.run_interface_export                             # tam çıktı (seçenek a), --out varsayılanı deliverables/src/web/veri
```

- **Kipler.** `--dry-run`: katman verisi okunmaz, hiçbir şey yazılmaz; ön denetim (dondurma manifestosundaki her dosyanın
  sha256'sı, kilit kaydının ve son test / OR çıktılarının aynı manifestoyu adlandırması, şema taraması, OR tablosu,
  havalimanı bilgisi, çıkış klasörünün olmaması) + JSON-yalnız dosyaların doğrulanmış boyutları stdout'a.
  `--summary-only`: katman okunmaz; `rotalar/` yok, `kalibrasyon.siniflandirma` boş, havalimanı kapsaması null.
  Varsayılan (tam): kilitli modellerle test dönemi yeniden tahmin edilir (seçenek a).
- **Üzerine yazmama (karar).** `--out` klasörü varsa (boş bile olsa) çalışma reddedilir. Dosyalar yanındaki
  `.<ad>.yaziliyor-<UTC>` klasörüne tek tek "x" kipiyle yazılır, geri okunup sha256 karşılaştırılır, sonunda klasör
  `--out` adına taşınır. Zaman damgalı klasör seçilmedi: site sabit `veri/` yolunu okur. Hata olursa ara klasör
  incelemeye bırakılır, yayın klasörü oluşmaz. Eski çıktıyı taşımak/silmek kullanıcının işi.
- **Çalıştırma kaydı.** `experiments/arayuz-ciktisi/arayuz-<UTC>.json` (yalnızca yeni dosya): girdilerin sha256'sı,
  yeniden üretim kontrolleri, gizlenen hücre sayıları, dosya listesi, boyut uyarıları, süreler. Uçuş düzeyi veri yok.
- **Tahmini maliyet (ölçülmedi).** Tam kip: son test 7 rolü bağlam + test satırlarında 1331 sn'de tahmin etti, tepe
  bellek 6,0 GB idi. Burada 3 rol (bir T2, bir plan matrisi) + Val-B yeniden üretimi: tahminen 15-40 dk, 5-8 GB.
  `--dry-run` / `--summary-only`: saniyeler.

## Seçenek (a): yeniden üretim kapıları

Tam kipte `run_final_test` yapı taşları çağrılır (kopyalanmaz): `_load_entries`, `_check_boosters`, `_settings`,
`_b1_tables`, `_predict_saved`, `_b1_predict`, `_development_checks`, `_assemble` → `final_eval.assemble_inputs`.
Roller: `arr_del15/T2`, `arr_delay/plan`, `cancelled/plan`. Önce geliştirme verisinde Val-B yeniden üretimi yapılır,
sonra `require_lock_written` ve `allow_final_test=True` ile test okunur. Testte hiçbir şey seçilmez ya da ayarlanmaz;
aylık kayan Platt ve kayan conformal, son testin önceden kayıtlı yordamıdır.

Dışa aktarma ancak şu kontrollerin hepsi geçerse yapılır (biri bile tutmazsa durur, hiçbir şey yazılmaz):

- son test dosya özeti (`metadata.final_test_files.digest`) aynı;
- T2 ArrDel15 ve iptal (plan): n, yaygınlık, kayan Platt ortalama tahmin, Brier, ECE (model ve B1) son test JSON'uyla
  |fark| ≤ 1e-9; kutulardan hesaplanan ECE de aynı;
- plan kantilleri: n, ham P80 kapsaması, kayan conformal P80/P95 kapsaması, %80 CQR kapsaması ve her ayın ofsetleri
  (q080, q095, interval80) ≤ 1e-9;
- OR hücre tablosu: aynı hücre kümesi, aynı tarifeli uçuş sayıları ve OR toplayıcısıyla (`politika-dondurma.json`,
  "mean") hesaplanan plan hücre düğümleri ≤ 1e-6 dk.

## Alan → kaynak (a = kilitli modellerle yeniden üretim, b = boş bırakıldı / yazılmadı)

Kısaltmalar: **ST** = `son-test-20261122T105048Z/son-test-sonuclari.json` → `blocks.final_test`; **OR** =
`deliverables/data/or/tampon-20261122T173803Z/hucre-tamponlari.parquet`. Olasılıklar her yerde aylık kayan Platt
(`platt_rolling`, birincil; ST özetinin başlığındaki "Platt (Val-B'de fit)" eski metin, kullanılmadı).

| Dosya / alan | Kaynak |
|---|---|
| ozet.proje | Kodda sabit Türkçe metin; sorumluluk reddi "Kamu verisine dayalı; havayollarıyla bağlantısız." ile başlar. Lisans notları `research/veri-kaynaklari.md`'deki doğrulama düzeyleriyle. |
| ozet.kapsam | havalimanı sayısı `target-airports.txt`; veri dönemi `metadata.periods` fit başı .. test sonu; test uçuşu ST `rows.classifiers["cancelled/plan"].n` (iptal hedefi tanımlı tarifeli uçuş); gün ST `days.n` |
| ozet.bolme | `metadata.periods` (fit, static_calibration, final_test; `splits` ile tutarlılık denetlenir) + `splits.VAL_A` |
| ozet.bilgi_zamani_saat | `features.DEFAULT_HORIZON_HOURS` (2,0) |
| ozet.sonuclar | ST rol eşlemesi: arrdel15 ← `arr_del15/T2` (lgbm_T2), `arr_del15/plan_matched` (lgbm_plan), B1; iptal ← `cancelled/plan` (lgbm_plan), `cancelled/T2` (lgbm_T2), B1; kantil ← `arr_delay/plan` (lgbm_plan), `arr_delay/T2_matched` (lgbm_T2), B1. Sıralama metrikleri ve F1/eşik ham skorla; Brier/log-loss/ECE/CITL/eğim/kesişim kayan Platt; GA yalnızca ST'de bootstrap kaydı olanlarda (brier_skill, CITL, T2 eğimi, kayan conformal kapsama) |
| ozet.kabul | ST `criteria` K1-K7 (K5, K6 "kaldi") |
| havalimanlari.ad/enlem/boylam | OurAirports `airports.csv` (`load_ourairports` tekilleştirme kuralı; ad = `name`) |
| havalimanlari.saat_dilimi | `airports.build_tz_map` (elle JSON > dosya sütunu > timezonefinder), katmanla aynı fonksiyon |
| havalimanlari.n_test_ucus, gozlenen, tahmin | ST `classification["arr_del15/T2"].segments_platt.Origin` (n, prevalence, mean_pred) |
| havalimanlari.iptal_orani | ST `classification["cancelled/plan"].segments_platt.Origin.prevalence` (gözlenen) |
| havalimanlari.kapsama_p80/p95 | **a** (origin başına kayan conformal kapsama); özet kipinde null |
| havalimanlari.hava_eksik_orani | **b** (kaynakta yok; alan yazılmaz) |
| rotalar hücre anahtarı, n_ucus | OR (Origin × Dest × saat bloğu × mevsim; tarifeli uçuş, iptal dahil) |
| rotalar.gozlenen_arrdel15_orani | **a** BTS ArrDel15 etiketi, ArrDel15 evreni (OR'daki `gozlenen_arrdel15_tamponsuz` ArrDelay ≥ 15'ten; aradaki en büyük fark kayda bilgi olarak yazılır) |
| rotalar.tahmin_arrdel15_orani | **a** T2 kayan Platt ortalaması |
| rotalar.kantil_dk | **a** plan P50/P80/P95 (final_eval sıralaması), hücredeki tamamlanan uçuşların **medyanı** |
| rotalar.kantil_conf_dk | **a** Q + ayın kayan conformal ofseti, medyan |
| rotalar.aralik80_dk | **a** CQR alt/üst, medyan (isteğe bağlı alan, dolduruldu) |
| rotalar.kapsama | **a** y ≤ conformal üst sınır payı |
| rotalar.planli_blok_sure_medyan_dk | OR `crs_elapsed_medyan_dk` |
| rotalar.iptal_orani | OR `n_iptal / n_ucus` |
| rotalar.tampon_onerisi_dk | OR `tampon_onerisi_dk` (plan @ τ = 0,80; yayımlanamazsa null) |
| rotalar.tarife_fazlasi_dk | **b** (yazılmaz) |
| kalibrasyon.siniflandirma | **a** 10 eşit frekanslı kutu (`metrics.reliability_table` ile aynı kutular): arrdel15 lgbm_T2 ve B1, iptal lgbm_plan ve B1; özet kipinde boş |
| kalibrasyon.kapsama_aylik | ST `quantile[plan / T2_matched].monthly` (ham, kayan, statik; tek yönlü), B1 ham; iki yönlü %80 kayan aylık **a** |
| hava_deneyi | ST: plan = `arr_del15/plan_matched` + `arr_delay/plan` P80 pinball; T2 = `arr_del15/T2` + `arr_delay/T2_matched`; farklar `comparisons.weather_contribution` (GA'lı). Oracle **b**: kilitli oracle yok, varyant yazılmaz (şema izin veriyor); yakalanan_pay ve hava_segmentleri **b** |
| hata_analizi | ST segmentleri: origin / saat_blogu / ay (T2 ArrDel15 ve plan kantilleri; ay için kayan conformal kapsama), olay_gunu (T2 ve B1). en_kotu: origin'ler arasında en düşük brier_skill (5) ve ham P80 kapsaması 0,80'den en uzak (5) |

## Gizleme ve sunum kuralları

- Rota hücresi yalnızca OR `yayimlanabilir` (n_ucus ≥ 50 ve tek taşıyıcı payı ≤ %90, M10) ise ve ArrDel15 ile ArrDelay
  evrenlerinde en az 50 tamamlanan uçuş varsa yayımlanır; saat bloğu eksik ya da zorunlu değeri eksik hücre de
  yayımlanmaz (gizlenen sayılar nedenleriyle kayda yazılır). Segment, kutu ve ay satırlarında n < 50 gizlenir.
- Taşıyıcı / kuyruk / uçuş numarası / logo içeren anahtar her yükte aranır, bulunursa hata. OR tablosu ve segment
  boyutlarında taşıyıcı sütunu/boyutu da hata. Taşıyıcı boyutu, sıralaması, uçuş düzeyi satır yok; rötar nedeni
  yayımlanmaz.
- Yuvarlama: dakika 1, oran 3 ondalık (plan §9); skor (AUC, Brier, log-loss, eğim) 4 ondalık (bu modülün kararı).
- Doğrulama: her dosya kendi tanımına ve kök `oneOf`'a göre. `format` (date, date-time, uri) burada denetlenir.
- Boyut: dosya başına `x-azami-boyut-kb` (1 KB = 1024 bayt) varsayılan olarak **uyarı + kayıt** (§9 "öneri" diyor),
  `--strict-size` ile hata; 10 MB toplam her zaman hata.
- Metin alanları Türkçe (şemada dil alanı yok; sitenin dili kullanıcı kararı bekliyor).

## Bilinen boşluklar ve şema çelişkileri (öneri; şema değiştirilmedi)

1. **Manifest boyutu.** 30 rota dosyasıyla 36 girdi × ~145 bayt (sabit yol + sha256) + başlık ≈ 5,2 KB > 5 KB.
   Öneri: `manifest.x-azami-boyut-kb` 8.
2. **`hata_analizi.boyutlar`'da `gorev` yok.** lgbm_T2 hem ArrDel15 hem iptal olabilir; bu yüzden yalnızca ArrDel15
   (T2) ve kantil (plan) segmentleri yazıldı. Öneri: isteğe bağlı `gorev` alanı.
3. **`cancelled/T2_calendar` için model kimliği yok**; yayımlanmadı. Öneri: gerekirse ayrı kimlik.
4. **`kalibrasyon.yontem`'de kamu senaryosu (2 ay gecikmeli) yok**; yayımlanmadı. Öneri: `"kamu"`.
5. **Kantil hücre özeti.** Şema "uçuş kantillerinin medyanı" diyor, yazıldı. OR tamponu ise hücre düğümlerinin
   ortalamasından (Vincentisation) gelir; iki sayı farklı istatistiktir, sitede yan yana gösterilirse not gerekir.
6. **`n_test_ucus` / `n_ucus` tanımı.** Havalimanında tamamlanan uçuş (ArrDel15 evreni), rotada tarifeli uçuş.
   Öneri: şema açıklamasına yazılsın.
7. **Dil alanı yok.** Öneri: `baslik`'a isteğe bağlı `dil` ("tr" / "en").
8. **Origin düzeyinde M10.** Kural hücre için tanımlı; havalimanı ve origin segmentleri yayımlanır. Tek taşıyıcının
   payı > %90 olan origin'ler tam kipte kayda yazılır (`info.single_carrier_share_over_090_origins`); hangileri
   olduğu çalıştırılmadan bilinmiyor.
9. `hava_eksik_orani`, `tarife_fazlasi_dk`, `yakalanan_pay`, `hava_segmentleri`, `fdr_bayrak` üretilmedi (kaynak yok).

## jsonschema önerisi

Varsayılan saf doğrulayıcıdır. Şemadaki tüm anahtar kelimeleri destekler: type, enum, const, properties, required,
additionalProperties, unevaluatedProperties, items, min/maxItems, minimum, maximum, exclusiveMinimum, min/maxLength,
pattern, format, $ref, $defs, allOf, anyOf, oneOf, not, if/then/else. Desteklemediği bir anahtar kelime görürse hata
verir. Şema 4. haftada dondurulduğunda bir kez `jsonschema` (Draft202012Validator) ile çapraz kontrol öneririm. Bu
yeni bir bağımlılık, kurulumu kullanıcı onayı ister. Gerekirse yalnızca geliştirme bağımlılığı olarak eklenir.
