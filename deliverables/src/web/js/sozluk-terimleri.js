// Sözlük terimleri (Türkçe). Her terimin kısa bir kimliği (#sozluk/kimlik bağlantısı için),
// 1-3 cümlelik sade bir tanımı ve gerekiyorsa "bu sitede nerede görülür" notu vardır.

export const GRUPLAR = [
  {
    ad: 'Veri ve hedef',
    terimler: [
      { id: 'arrdel15', terim: 'ArrDel15', tanim: 'Uçuşun tarifedeki varış saatinden 15 dakika ya da daha fazla geç varması. ABD Ulaştırma İstatistikleri Bürosu’nun (BTS) resmi “rötarlı” tanımıdır.', nerede: 'Sitedeki “rötar oranı” ve “geç varış oranı” budur.' },
      { id: 'varis-rotari', terim: 'Varış rötarı (dk)', tanim: 'Gerçek varış ile tarifedeki varış arasındaki fark. Eksi değer erken varış demektir.', nerede: 'Rotalar sayfasındaki P50, P80 ve P95 sütunları bu farkın kantilleridir.' },
      { id: 'iptal', terim: 'İptal', tanim: 'Tarifeli bir uçuşun gerçekleşmemesi. Rötar kantilleri yalnızca gerçekleşen uçuşlar için hesaplanır.' },
      { id: 'bts', terim: 'BTS', tanim: 'ABD Ulaştırma Bakanlığı’nın Ulaştırma İstatistikleri Bürosu. Uçuş verisinin kaynağıdır (kamu verisi).', nerede: 'Hakkında bölümünde, veri kaynakları listesinde.' },
      { id: 'metar', terim: 'METAR', tanim: 'Havalimanlarının düzenli yayımladığı hava gözlem raporu: rüzgâr, görüş, yağış, bulut ve benzeri.', nerede: 'T2 modelinin kullandığı hava bilgisi budur; Hava deneyi bölümünde.' },
      { id: 'test-donemi', terim: 'Test dönemi', tanim: 'Modelin hiç görmediği, sonuçların ölçüldüğü dönem (2026-03 ile 2026-08 arası). Bir kez açıldı.', nerede: 'Genel bakışta “Nihai test dönemi”.' },
      { id: 'egitim-dogrulama', terim: 'Eğitim ve doğrulama dönemleri', tanim: 'Eğitim, modelin öğrendiği dönemdir (2023-09 ile 2025-08). Doğrulama, ayar ve kalibrasyon için ayrılan dönemlerdir (2025-09 ile 2026-02). Zaman sırası korunur: geleceğin verisi geçmişin modeline girmez.', nerede: 'Genel bakışta “Zaman sıralı bölme” tablosu.' },
      { id: 'hucre', terim: 'Hücre', tanim: 'Rota (kalkış–varış) × kalkış saat bloğu × mevsim grubu. Rota tablosundaki her satır bir hücredir.', nerede: 'Rotalar sayfası.' },
      { id: 'segment', terim: 'Segment', tanim: 'Sonuçların bir boyuta göre kırılımındaki bir parça: örneğin bir havalimanı, bir saat bloğu ya da bir ay.', nerede: 'Hata analizi sayfası.' },
      { id: 'olay-gunu', terim: 'Olay günü', tanim: 'Rötar oranının, eğitim dönemindeki günlük oranların %95’lik dilimini aştığı olağandışı gün (fırtına gibi).', nerede: 'Hata analizinde “Olay günleri ve diğer günler” kırılımı.' },
    ],
  },
  {
    ad: 'Model ve tahmin',
    terimler: [
      { id: 'b1', terim: 'B1 (referans)', tanim: 'Basit bir kural: “geçmişte bu rotada, bu saat bloğunda ne olduysa”. Modelin gerçekten bir şey öğrenip öğrenmediğini görmek için karşılaştırma noktasıdır.', nerede: 'Genel bakış panosunda ve hava deneyinde.' },
      { id: 'plan-modeli', terim: 'Plan modeli', tanim: 'Yalnızca tarife yapılırken bilinen bilgiyle tahmin yapar; hava bilgisi yoktur. Tampon önerileri bundan gelir.', nerede: 'Rotalar sayfasındaki kantiller ve üst sınırlar.' },
      { id: 't2-modeli', terim: 'T2 modeli', tanim: 'Kalkıştan 2 saat önceki hava gözlemlerini de kullanır; operasyon ekibi içindir.', nerede: 'Havalimanları sayfasındaki tahmin oranları.' },
      { id: 'lightgbm', terim: 'LightGBM', tanim: 'Karar ağaçlarını art arda ekleyerek öğrenen, tablo verisinde güçlü bir makine öğrenmesi yöntemidir.' },
      { id: 'olasilik-kalibrasyon', terim: 'Olasılık ve kalibrasyon', tanim: 'Model “%30” dediğinde, bu tür uçuşların gerçekten yaklaşık %30’unun gecikmesi beklenir. Kalibrasyon, bu uyumu sağlayan düzeltmedir.', nerede: 'Kalibrasyon ve kapsama sayfasındaki güvenilirlik diyagramı.' },
      { id: 'platt', terim: 'Platt (aylık kayan)', tanim: 'Ham skorları olasılığa çeviren basit bir kalibrasyon. Her ay son yaklaşık 2 ayın verisiyle yeniden ayarlanır; böylece mevsim değişimine uyum sağlar.' },
      { id: 'kantil', terim: 'Kantil (P50, P80, P95)', tanim: 'Rötar süresi için sınırlar. P80 = 40 dk demek, “bu tür uçuşların %80’i en fazla 40 dakika gecikir” demektir.', nerede: 'Rotalar sayfası.' },
      { id: 'conformal', terim: 'Conformal ayar', tanim: 'Kantil sınırlarını, geçmişteki gerçek hatalara bakarak hedef kapsamayı tutturacak biçimde genişleten ya da daraltan yöntemdir. Kayan: her ay yeniden yapılır. Statik: bir kez yapılır. Ham: ayar yoktur.', nerede: 'Kalibrasyon ve kapsama sayfasındaki aylık kapsama grafikleri.' },
      { id: 'kapsama', terim: 'Kapsama', tanim: 'Gerçek değerin sınırın altında kalma oranı. P80 sınırı için hedef %80’dir.', nerede: 'Havalimanları, Rotalar ve Kalibrasyon sayfaları.' },
      { id: 'sizinti', terim: 'Sızıntı (leakage)', tanim: 'Modelin, tahmin anında bilemeyeceği bir bilgiyi (örneğin gerçekleşen kalkış saatini) görmesi. Sonuçları sahte biçimde iyi gösterir. İki ayrı inceleme sızıntı bulmadı.' },
    ],
  },
  {
    ad: 'Ölçütler',
    terimler: [
      { id: 'roc-auc', terim: 'ROC-AUC', tanim: 'Modelin geç kalacak bir uçuşa, zamanında gelecek bir uçuştan daha yüksek risk verme olasılığı. 0,5 yazı tura, 1 kusursuz demektir.', nerede: 'Genel bakış panosu ve hava deneyi.' },
      { id: 'pr-auc', terim: 'PR-AUC', tanim: 'Geç uçuşları yakalama başarısını (kesinlik ve duyarlılık birlikte) özetler. Olay seyrekken ROC-AUC’tan daha zorlayıcıdır.' },
      { id: 'brier', terim: 'Brier skoru', tanim: 'Olasılık tahminlerinin ortalama kare hatası. Düşük olan daha iyidir.' },
      { id: 'bss', terim: 'Brier skor kazancı (BSS)', tanim: 'Modelin Brier skorunun B1’e göre iyileşme payı. 0’ın üstü, B1’den iyi demektir.', nerede: 'Genel bakış panosu.' },
      { id: 'ece', terim: 'ECE', tanim: 'Tahmin edilen olasılıklar ile gerçekleşen oranlar arasındaki ortalama fark (kalibrasyon hatası).' },
      { id: 'citl', terim: 'CITL (genel sapma)', tanim: 'Ortalama tahmin ile gerçek oran arasındaki fark; 0 idealdir. Eksi değer, modelin riski genel olarak düşük tahmin ettiğini gösterir.', nerede: 'Genel bakış panosu.' },
      { id: 'kalibrasyon-egimi', terim: 'Kalibrasyon eğimi', tanim: '1 idealdir. 1’den küçük değer tahminlerin fazla uçta olduğunu, büyük değer fazla temkinli olduğunu gösterir.', nerede: 'Genel bakış panosu.' },
      { id: 'pinball', terim: 'Pinball kaybı', tanim: 'Kantil tahminlerinin hatası. Düşük olan daha iyidir.' },
      { id: 'kabul-olcutleri', terim: 'Kabul ölçütleri (K1–K7)', tanim: 'Test öncesinde yazılan geçme ya da kalma kuralları. 5’i geçti, K5 ve K6 geçmedi; sonuçlar olduğu gibi yayımlandı.', nerede: 'Genel bakış sayfasında.' },
    ],
  },
  {
    ad: 'İstatistik',
    terimler: [
      { id: 'guven-araligi', terim: 'Güven aralığı (%95 GA)', tanim: 'Bir sonucun belirsizlik aralığı. Aralık 0’ı içermiyorsa fark anlamlı kabul edilir.', nerede: 'Genel bakış panosu ve hava deneyi.' },
      { id: 'gun-blok-bootstrap', terim: 'Gün blok bootstrap', tanim: 'Aynı günün uçuşları birbirine bağlı olduğu için (ortak hava gibi), günleri bütün olarak yeniden örnekleyerek güven aralığı hesaplama yöntemi. 1000 tekrar kullanıldı.' },
      { id: 'holm', terim: 'Holm düzeltmesi', tanim: 'Birden fazla karşılaştırma yapınca şans eseri “anlamlı” bulma riskini kontrol eden düzeltme.' },
      { id: 'onceden-kayit', terim: 'Önceden kayıt', tanim: 'Kuralların ve ölçütlerin sonuç görülmeden yazılması. Sonuca göre kural değiştirmeyi engeller.' },
      { id: 'kesifsel', terim: 'Keşifsel (post hoc)', tanim: 'Sonuç görüldükten sonra yapılan inceleme. İpucu verir ama kesin kanıt değildir.', nerede: 'Hata analizi sayfası.' },
    ],
  },
  {
    ad: 'Optimizasyon (OR)',
    terimler: [
      { id: 'blok-sure-tamponu', terim: 'Blok süre tamponu', tanim: 'Tarifedeki uçuş süresine eklenen fazladan dakika. Rötarı emer ama uçak ve ekip zamanına mal olur.', nerede: 'Rotalar sayfasındaki “Önerilen tampon” sütunu.' },
      { id: 'maliyet-orani', terim: 'Maliyet oranı (τ)', tanim: 'Bir dakika rötarın, bir dakika boşta beklemeye göre ne kadar pahalı sayıldığı. τ = 0,80 olduğunda rötar dakikası 4 kat pahalıdır (varsayım, ölçülmedi). Önerilen tampon, plan modelinin τ kantilidir.' },
      { id: 'newsvendor', terim: 'Newsvendor', tanim: 'Az ve fazla stokun (burada az ve fazla tamponun) maliyetini dengeleyen klasik karar modeli. En iyi tampon, dağılımın τ kantilidir.' },
      { id: 'tampon-butcesi', terim: 'Tampon bütçesi', tanim: 'Uçuş başına ortalama eklenebilecek en fazla dakika. Dakikalar, hücrelere en verimli biçimde dağıtılır.' },
      { id: 'lp-milp', terim: 'LP / MILP', tanim: 'Doğrusal programlama ve karma tamsayılı programlama: kısıtlar altında en iyi kararı bulan matematiksel modeller. Pyomo ile yazıldı, HiGHS çözücüsüyle çözüldü.' },
      { id: 'tek-havayolu-kurali', terim: 'Tek havayolu kuralı', tanim: 'Bir hücrede ya da havalimanında uçuşların %90’ından fazlası tek havayoluna aitse sayılar yayımlanmaz; böylece sayılar bir havayolunun performansı gibi okunmaz.', nerede: 'Rotalar sayfasında ve Havalimanları tablosunda “Yayımlanmadı”.' },
    ],
  },
];
