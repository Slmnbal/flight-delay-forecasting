// Tüm arayüz metinleri tek yerde. Türkçe metinler bu dosyadadır (TR); İngilizce karşılıkları aynı
// yapıda metin-en.js içindedir (EN). Varsayılan dil İngilizcedir. Başka modüllerde kullanıcıya görünen
// sabit metin bulunmaz.
//
// T, sayfa boyunca aynı nesnedir: dil değişince setLang() içeriğini yerinde günceller; böylece
// "const t = T.kal" gibi modül düzeyindeki başvurular geçerli kalır. Parametre alan metinler küçük
// işlevlerdir; i18n çatısı yoktur.

import { EN } from './metin-en.js';

export const BUFFER_WARNING = 'Varsayılmış maliyet oranı; operasyonel öneri değildir.';

// Yazar bağlantıları. LINKEDIN_URL boşsa LinkedIn bağlantısı hiç çizilmez.
export const GITHUB_URL = 'https://github.com/Slmnbal';
export const REPO_URL = 'https://github.com/Slmnbal/flight-delay-forecasting';
export const LINKEDIN_URL = 'https://www.linkedin.com/in/selman-bal-069598222/';
export const AUTHOR = 'Slmnbal';

const TR = {
  // ------------------------------------------------------------------ site
  siteBasligi: 'Uçuş rötarı riski ve tarife tamponları',
  sorumluluk: 'Kamu verisine dayalı; havayollarıyla bağlantısız.',
  tamponUyari: BUFFER_WARNING,
  atla: 'İçeriğe geç',
  nav: 'Bölümler',
  ornekBanner: 'Bu dosyalar örnek veri olarak işaretli. Sayılar gerçek sonuç değildir.',
  meta: {
    aciklama: 'Kamu verisi ABD iç hat uçuşlarının rötarını ne kadar iyi tahmin eder ve bu, daha iyi tarifeler yapmaya yardım eder mi? Havayollarıyla bağlantısız.',
  },
  dil: {
    grup: 'Dil',
    tr: 'Türkçe',
    en: 'English',
  },
  birim: { dk: 'dk' },
  harita: { kuzey: '°K', bati: '°B' },

  bolumler: {
    story: 'Hikâye',
    results: 'Sonuçlar',
    explore: 'Keşfet',
    buffers: 'Tampon (OR)',
    method: 'Yöntem',
    sozluk: 'Sözlük',
  },

  ortak: {
    yukleniyor: 'Veriler yükleniyor…',
    bilinmeyenHata: 'Bilinmeyen hata.',
    yok: 'yok',
    yayimlanmadi: 'Yayımlanmadı',
    yayimlanmadiKucuk: 'yayımlanmadı',
    evet: 'Evet',
    hayir: 'Hayır',
    puan: 'puan',
    sozluk: 'Sözlük: ',
  },

  tema: {
    otomatik: 'otomatik',
    acik: 'açık',
    koyu: 'koyu',
  },
  temaDugmesi: (mod) => `Tema: ${mod}`,
  temaEtiketi: (mod) => `Renk teması: ${mod}. Değiştirmek için etkinleştirin.`,

  hata: {
    baslik: 'Bu bölüm yüklenemedi. ',
    diskUyarisi: 'Sayfayı doğrudan diskten açtıysanız tarayıcı sonuçların yüklenmesini engeller; yerel bir web sunucusu kullanın.',
    yenidenYukle: 'Bu bölümü yeniden yükle',
    yenidenDene: 'Yeniden dene',
    dosya: (yol, neden) => `${yol} yüklenemedi (${neden}).`,
    http: (kod) => `HTTP ${kod}`,
    gecersizJson: 'geçerli JSON değil',
    ag: 'ağ ya da dosya erişim hatası',
    gecersizKod: 'geçersiz havalimanı kodu',
    rotaDosyasiYok: 'Hiç rota dosyası listelenmemiş.',
  },

  altBilgi: {
    uretim: (zaman) => `Sonuçlar ${zaman} tarihinde üretildi.`,
    yazar: 'Yazar: ',
  },

  // ------------------------------------------------------------------ biçimler
  metrik: {
    roc_auc: 'ROC-AUC',
    pr_auc: 'PR-AUC',
    yayginlik: 'Gözlenen geç varış oranı',
    brier: 'Brier skoru',
    brier_skill: 'Brier skor kazancı (B1’e göre)',
    log_loss: 'Log kaybı',
    ece: 'ECE (kalibrasyon hatası)',
    kalibrasyon_egimi: 'Kalibrasyon eğimi',
    kalibrasyon_kesisimi: 'Kalibrasyon kesişimi',
    calibration_in_the_large: 'CITL (genel sapma)',
    f1: 'F1',
    precision: 'Kesinlik',
    recall: 'Duyarlılık',
    esik: 'Karar eşiği',
    pinball_p50: 'Pinball kaybı P50',
    pinball_p80: 'Pinball kaybı P80',
    pinball_p95: 'Pinball kaybı P95',
    mae_p50: 'P50 ortalama mutlak hata',
    kapsama_p80_ham: 'P80 kapsaması, ham',
    kapsama_p95_ham: 'P95 kapsaması, ham',
    kapsama_p80_conf: 'P80 kapsaması, conformal ayarlı',
    kapsama_p95_conf: 'P95 kapsaması, conformal ayarlı',
    kapsama_aralik80: '%80 aralık kapsaması',
    aralik80_genislik_dk: '%80 aralık genişliği',
    kantil_kesisme_orani: 'Kantil kesişme oranı',
    roc_auc_farki_b1: 'ROC-AUC farkı (B1’e göre)',
    pr_auc_farki_b1: 'PR-AUC farkı (B1’e göre)',
  },

  daha: { higher: 'Yüksek değer', lower: 'Düşük değer' },

  model: {
    B0: 'B0 (referans)',
    B1: 'B1 (referans)',
    B2: 'B2 (referans)',
    L: 'Lojistik referans',
    lgbm_plan: 'Plan modeli',
    lgbm_T2: 'T2 modeli',
    lgbm_oracle: 'Oracle modeli (üst sınır)',
    xgb_T2: 'XGBoost T2 modeli',
  },

  mevsim: { tum: 'Tüm yıl', kis: 'Kış', ilkbahar: 'İlkbahar', yaz: 'Yaz', sonbahar: 'Sonbahar' },
  aylar: ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'],
  donem: (bas, bit) => `${bas} – ${bit}`,

  // ------------------------------------------------------------------ tablo
  tablo: {
    varsayilanEtiket: 'Veri tablosu',
    bos: 'Seçili filtrelere uyan satır yok.',
    dahaFazla: 'Daha fazla satır göster',
    durum: (gosterilen, toplam) => `${toplam} satırın ${gosterilen} tanesi gösteriliyor.`,
  },

  // ------------------------------------------------------------------ hikâye: açılış
  hero: {
    soru: (saat) => `Kamu verisi, bir ABD iç hat uçuşunun geç varıp varmayacağını kalkıştan ${saat} saat önce ne kadar iyi tahmin edebilir; bu, daha iyi tarifeler yapmaya yardım eder mi?`,
    ozet: 'Kaydırarak izleyin: sorun, bulgular ve sonraki adımlar.',
    kapsam: (n, havalimani, donem) => `${havalimani} havalimanında ${n} test uçuşu; tek seferlik test (${donem}).`,
    yuru: 'Adım adım gez',
    kod: 'Kod GitHub’da',
  },

  // ------------------------------------------------------------------ hikâye: adımlar
  hikaye: {
    veriYok: 'Bu adımın verisi yüklenemedi.',
    adim: (n) => `Slayt ${n}`,
    ayrinti: 'Ayrıntılar →',
    yok: 'Bu slaytın verisi yüklenemedi.',
    // 1. sorun
    s1: {
      baslik: (n) => `Her ${n} uçuştan yaklaşık biri geç varıyor`,
      p1: (esik, oran, n) => `Tarifeden ${esik} dakika ya da daha geç inen uçuş geç sayılır. Test döneminde ${n} uçuşun ${oran} kadarı geç vardı.`,
      ikon: (x, toplam) => `${toplam} uçuştan ${x} tanesi geç vardı`,
      ikonAciklama: (esik) => `Dolu daire: ${esik} dakika ya da daha geç varan uçuş. Boş daire: zamanında varan uçuş.`,
    },
    // 2. ne zaman daha kötü
    s2: {
      baslik: (yuksek, dusuk, kat) => `${yuksek} arasında kalkan uçuşların geç varma olasılığı, ${dusuk} arasında kalkanlara göre yaklaşık ${kat} kat fazla`,
      baslikDuz: 'Geç varma riski günün saatine göre değişiyor',
      p1: (esik) => `Kalkış saatine göre, tarifeden ${esik} dakika ya da daha geç inen uçuşların payı.`,
      olay: (a, b) => `Fırtına gibi olağandışı günlerde uçuşların ${a} kadarı geç varıyor; diğer günlerde ${b}.`,
      eksen: 'Geç varan uçuşların payı',
      grafikBaslik: 'Kalkış saatine göre geç varış oranı',
      grafikAciklama: (yuksek, dusuk) => `Yatay çubuklar: en yüksek oran ${yuksek}, en düşük oran ${dusuk}.`,
    },
    // 3. model önceden görebiliyor mu
    s3: {
      baslik: (yuksek, dusuk) => `Modelin en riskli bulduğu uçuşlarda her ${yuksek.n} uçuştan yaklaşık ${yuksek.deger} tanesi geç varıyor; en güvenli grupta ${dusuk.n} uçuştan ${dusuk.deger} tanesi`,
      baslikAz: (yuksek, dusuk) => `Modelin en riskli bulduğu uçuşlarda her ${yuksek.n} uçuştan yaklaşık ${yuksek.deger} tanesi geç varıyor; en güvenli grupta ${dusuk.n} uçuşun birinden azı geç varıyor`,
      p1: 'Uçuşlar, modelin risk tahminine göre on eşit gruba ayrıldı. Her çubuk, o gruptaki uçuşların gerçekte ne kadarının geç vardığını gösteriyor.',
      eksen: (ilk, son) => `Risk grubu (${ilk} = en düşük risk, ${son} = en yüksek)`,
      grafikBaslik: 'Risk grubuna göre gerçekleşen geç varış oranı',
      grafikAciklama: (dusuk, yuksek) => `Çubuklar soldan sağa yükselir: en güvenli grup ${dusuk}, en riskli grup ${yuksek}.`,
    },
    // 4. sayılara güvenilir mi
    s4: {
      baslik: (tahmin, gercek) => `Model “${tahmin}” dediğinde, bu uçuşların yaklaşık ${gercek} kadarı gerçekten geç varıyor`,
      baslikGenel: (puan) => `Modelin risk yüzdeleri, gerçekleşenden en fazla ${puan} puan sapıyor`,
      p1: (puan) => `On grubun hepsinde, modelin tahmini gerçekleşenden en fazla ${puan} puan farklı.`,
      model: 'Modelin söylediği',
      gercek: 'Gerçekleşen',
      eksen: (ilk, son) => `Risk grubu (${ilk} = en düşük risk, ${son} = en yüksek)`,
      grafikBaslik: 'Her risk grubunda modelin söylediği ve gerçekleşen geç varış oranı',
      grafikAciklama: (puan) => `Her grup için iki çubuk; fark en fazla ${puan} puan.`,
    },
    // 5. hava bilgisi
    s5: {
      baslik: 'Hava bilgisi, modelin geç kalacak uçuşları önceden fark etmesine yardım ediyor',
      baslikNotr: 'Hava bilgisi, modelin geç kalacak uçuşları fark etmesine belirgin bir katkı yapmıyor',
      p1: (saat, a, b) => `Kalkıştan ${saat} saat önceki hava bilgisi, modelin ROC-AUC değerini, yani geç kalacak bir uçuşu zamanında gelecek olandan ne sıklıkla daha riskli bulduğunu, ${a} değerinden ${b} değerine çıkarıyor.`,
      p1Notr: (saat, a, b) => `Kalkıştan ${saat} saat önceki hava bilgisi, modelin ROC-AUC değerini, yani geç kalacak bir uçuşu zamanında gelecek olandan ne sıklıkla daha riskli bulduğunu, ${a} değerinden ${b} değerine getiriyor; bu fark günlük dalgalanmadan ayırt edilemiyor.`,
      gecmis: 'Yalnızca geçmiş kayıt',
      tarife: 'Tarife modeli',
      hava: (saat) => `Tarife + ${saat} saat önceki hava`,
      eksen: (taban) => ['Geç ve zamanında uçuşları ayırma gücü', `(${taban} = yazı tura)`],
      grafikBaslik: 'Geç ve zamanında uçuşları ayırma gücü, üç yaklaşım',
      grafikAciklama: (a, b, c) => `Çubuklar: yalnızca geçmiş kayıt ${a}, tarife modeli ${b}, tarife ve hava ${c}.`,
    },
    // 6. tampon şeması
    s6: {
      baslik: 'Havayolları tarifeye fazladan süre ekler; böylece küçük gecikmeler uçuşu geç yapmaz',
      p1: 'Tampon, havayolunun tarifedeki uçuş süresine eklediği fazladan dakikalar; küçük gecikmeleri karşılar, büyük gecikmelerde yetmez.',
      planlanan: 'Tarifedeki varış',
      satir1: 'Tarife: uçuş süresi + tampon',
      satir2: 'Küçük gecikme tamponla karşılanır: zamanında varır',
      satir3: 'Büyük gecikme tamponu aşar: geç varır',
      ucus: 'Uçuş süresi',
      tampon: 'Tampon',
      gecikme: 'Gecikme',
      asan: 'Tamponu aşan gecikme',
      anahtar: (ad, dk) => `${ad} (${dk})`,
      ornek: 'Örnek şema: dakikalar anlatım içindir, gerçek veri değildir.',
      grafikBaslik: 'Tarife tamponunun nasıl çalıştığını gösteren örnek şema',
      grafikAciklama: 'Üç satır: tarifedeki süre uçuş ve tampondan oluşur; küçük gecikme tamponun içinde kalır ve uçuş zamanında varır; büyük gecikme tamponu aşar ve uçuş geç varır.',
    },
    // 7. tampon ne kazandırır, ne kaybettirir
    s7: {
      baslik: 'Daha fazla tampon geç varışları azaltır, ama boşta bekleyen dakikaları artırır',
      p1: 'Geç bir dakikanın boşta bir dakikadan ne kadar kötü sayıldığı arttıkça, daha fazla tampon eklenir.',
      eksenX: 'Geç dakika, boş dakikadan kaç kat kötü',
      gecPanel: 'Geç varan uçuşlar',
      bosPanel: 'Uçuş başına boşta kalan dakika',
      tamponYok: 'Tampon yok',
      secili: 'Seçilen',
      gecBaslik: 'Geç varış oranı, tampon ağırlığına göre',
      bosBaslik: 'Uçuş başına boşta kalan dakika, tampon ağırlığına göre',
      grafikAciklama: (ad, dusuk, yuksek) => `${ad}: soldan sağa ${dusuk} değerinden ${yuksek} değerine.`,
      ozet: (ek, a, b, bos) => `Uçuş başına yaklaşık ${ek} tampon, geç varışları ${a} düzeyinden ${b} düzeyine indiriyor; bunun bedeli uçuş başına yaklaşık ${bos} boşta bekleme.`,
      yiginBaslik: 'Uçuşların nasıl sonuçlandığı',
      yiginAciklama: (a, b, c) => `Yığılmış çubuk: zaten zamanında ${a}, tampon sayesinde zamanında ${b}, yine geç ${c}.`,
      zaten: 'Zaten zamanında',
      sayesinde: 'Tampon sayesinde zamanında',
      yineGec: 'Tamponla bile geç',
    },
    // 8. basit kural ve model
    s8: {
      baslikEsit: 'Tarifeyi belirlerken model, geçmişe dayalı basit bir kuralın yalnızca ayarında',
      baslikFark: (k, n) => `Tarifeyi belirlerken model ile geçmişe dayalı basit kural, ${n} bütçeden ${k} tanesinde belirgin biçimde ayrışıyor`,
      p1Esit: 'Aynı toplam tampon verildiğinde ikisi de uçuşların hemen hemen aynı payını geç bırakıyor. Modelin asıl değeri uçuş gününde ortaya çıkıyor.',
      p1Fark: 'Aynı toplam tampon verildiğinde iki yaklaşım arasındaki fark bazı bütçelerde belirgin; ayrıntı için tabloya bakın.',
      model: 'Modele dayalı tarife',
      kural: 'Geçmişe dayalı basit kural',
      eksenX: 'Toplam tampon bütçesi (dk/uçuş)',
      eksenY: 'Geç varış oranı',
      grafikBaslik: 'Aynı tampon bütçesinde geç varış oranı: model ve basit kural',
      grafikAciklama: (adlar) => `Tampon bütçesine karşı geç varış oranı; çizgiler: ${adlar}.`,
    },
    // 9. ne yapmalı
    s9: {
      baslik: 'Üç öneri',
      kartlar: 'Öneriler',
      gun: {
        baslik: 'Uçuş gününde risk skorunu operasyonda kullanın',
        metin: (yuksek) => `Modelin en riskli bulduğu grupta her ${yuksek.n} uçuştan yaklaşık ${yuksek.deger} tanesi geç varıyor.`,
      },
      tampon: {
        baslikEsit: 'Tampon belirlemek için geçmişe dayalı kural, model kadar iyi',
        baslikFark: 'Tampon belirlerken modeli geçmişe dayalı kuralla karşılaştırın',
        metin: (ek, a, b, bos) => `Yaklaşık ${ek} eklemek geç varışları ${a} düzeyinden ${b} düzeyine indiriyor; bedeli uçuş başına yaklaşık ${bos} boşta bekleme.`,
      },
      sonraki: {
        baslik: 'Sonraki adım: uçak rotasyonu verisi',
        metin: 'Her uçağın o gün yaptığı önceki uçuşların verisi burada kullanılan kamu verisinde yok; sıradaki en umut verici girdi bu.',
      },
      sinirlar: 'Neler işe yaramadı →',
    },
    // 10. kendiniz deneyin
    s10: {
      baslik: 'Bir uçuş türü seçin ve ne sıklıkla, ne kadar geç kaldığını görün',
      p1: 'Havalimanı, varış yeri, saat ve mevsim seçin; modelin beklentisi gerçekleşenin yanında görünür.',
      secim: 'Uçuş türü',
      gerceklesen: 'Gerçekleşen',
      modelTahmini: 'Modelin beklentisi',
      ikonEtiket: (ad, x, toplam) => `${ad}: ${toplam} uçuştan ${x} tanesi geç vardı.`,
      ikonAnahtar: (esik) => `Dolu daire: ${esik} dakika ya da daha geç varan uçuş.`,
      cumle: (x, y, toplam, n) => `Bu türden ${toplam} uçuştan yaklaşık ${x} tanesi geç vardı; model ${y} bekliyordu (${n} test uçuşu).`,
      rotarBaslik: 'Ne kadar geç varıyorlar?',
      rotarCumle: (p50, p80, p95, erken) => erken
        ? `Bu uçuşların yarısı tarifeden en az ${p50} erken varır; beşte dördü en fazla ${p80}, yirmide on dokuzu en fazla ${p95} geç varır.`
        : `Bu uçuşların yarısı tarifeden en fazla ${p50} geç varır; beşte dördü en fazla ${p80}, yirmide on dokuzu en fazla ${p95} geç varır.`,
      yarisi: 'Yarısı',
      dortBes: 'Beşte dördü',
      ondokuz: 'Yirmide on dokuzu',
      grafikBaslik: 'Geç varış süresi: uçuşların yarısı, beşte dördü ve yirmide on dokuzu',
      grafikAciklama: (p50, p80, p95) => `Yatay çubuklar: yarısı ${p50}, beşte dördü ${p80}, yirmide on dokuzu ${p95}.`,
      hucreYok: 'Bu seçim için yayımlanmış bir hücre yok.',
      yukleniyor: (iata) => `${iata} çıkışlı rotalar yükleniyor…`,
    },
  },

  // ------------------------------------------------------------------ sonuçlar
  genel: {
    giris: 'Nihai test: kilitlenmiş modeller, tek değerlendirme, modelin hiç görmediği aylar.',
    pano: {
      baslik: 'Öne çıkan sonuçlar',
      aciklamaBaslik: 'Nihai test, %95 aralıklarla',
      olcut: 'Ölçüt',
      sonuc: 'Sonuç',
      aralik: '%95 aralık',
      referans: 'Referans',
      rocSatiri: 'Geç varış sıralaması: ROC-AUC, T2',
      prSatiri: 'Geç varış sıralaması: PR-AUC, T2',
      brierSatiri: 'Brier skor kazancı, T2',
      egimSatiri: 'Kalibrasyon eğimi, T2',
      citlSatiri: 'CITL (genel sapma), T2',
      p80Satiri: 'P80 üst sınır kapsaması, plan',
      p95Satiri: 'P95 üst sınır kapsaması, plan',
      havaSatiri: 'Havanın ROC-AUC kazancı (T2 eksi plan)',
      b1Referans: (deger, fark) => `B1: ${deger}; kazanç: ${fark}`,
      sifirUstu: 'Sıfırın üstü, B1’den iyi demektir',
      ideal: (v) => `İdeal: ${v}`,
      hedef: (v) => `Hedef: ${v}`,
      ayniUcuslar: 'Aynı uçuşlar, kalkıştan önceki hava',
      not: 'ROC-AUC ve PR-AUC aralıkları, B1’e göre kazanca aittir. B1, aynı rota ve saat bloğunun geçmiş kaydıdır.',
    },
    kabul: {
      baslik: 'Kabul ölçütleri K1–K7',
      ozet: (gecen, toplam, kalanlar) => `${toplam} ölçütten ${gecen} tanesi geçti. ${kalanlar.length ? `Geçmeyen: ${kalanlar.join(', ')}.` : 'Geçmeyen yok.'}`,
      gecti: 'Geçti',
      kaldi: 'Geçmedi',
      degerlendirilmedi: 'Değerlendirilmedi',
      kaldiBaslik: 'Neler işe yaramadı',
      k5: 'K5, kapsama. ',
      k5Metin: (p80, p95) => `Üst sınırların kapsaması P80 için ${p80}, P95 için ${p95}.`,
      k6: 'K6, iptal. ',
      k6Metin: (plan, b1) => `Yalnızca tarifeyle iptal tahmininin PR-AUC değeri ${plan}; B1 için ${b1}.`,
    },
    guven: {
      baslik: 'Bu sayılara ne kadar güvenmeli',
      noktalar: [
        ['Zaman sıralı bölme. ', 'Modeller geçmişten öğrendi, sonraki aylarda sınandı.'],
        ['Tek değerlendirme. ', 'Kurallar test dönemi okunmadan yazıldı; test üzerinde ayar yapılmadı.'],
        ['Güçlü bir referans. ', 'Her model, aynı rota ve saat bloğunun geçmiş kaydı olan B1 ile karşılaştırıldı.'],
        ['Belirsizlik gösterilir. ', 'Aralıklar günleri bütün olarak yeniden örnekler; aynı gündeki uçuşlar birbirinden bağımsız değildir.'],
        ['Sızıntı yok. ', 'Yalnızca belirtilen zamanda bilinen bilgi kullanıldı; iki ayrı inceleme sızıntı bulmadı.'],
      ],
      bolmeBaslik: 'Zaman sıralı bölme',
      kume: 'Küme',
      baslangic: 'Başlangıç',
      bitis: 'Bitiş',
      egitim: 'Eğitim',
      dogrulamaA: 'Doğrulama A (erken durdurma)',
      dogrulamaB: 'Doğrulama B (kalibrasyon)',
      test: 'Nihai test',
      modeller: 'Karşılaştırılan modeller',
    },
  },

  // ------------------------------------------------------------------ keşfet
  kesfet: {
    giris: 'Haritada bir havalimanı seç: oradan çıkan rotalar, uçuşların ne sıklıkla 15 dakika ya da daha geç vardığına göre renklenen yaylarla çizilir. Aşağıdaki tabloda her rotada uçuşların tipik, kötü gün ve en kötü durumda kaç dakika geç vardığı yazar.',
    rotalarBaslik: 'Rotalar',
    rotalarGit: 'Rotalara git',
    kart: {
      baslik: (iata) => `${iata} bir bakışta`,
      liste: 'Özet kartları',
      yok: 'Bu kart için yeterli yayımlanmış uçuş yok.',
      esik: (n) => `En az ${n} test uçuşu olan kalkış blokları ve varışlar değerlendirilir.`,
      yalnizca: 'Yalnızca yayımlanmış rota hücrelerine dayanır; havalimanı düzeyindeki oranlar gösterilmez.',
      blok: {
        baslik: 'En riskli kalkış bloğu',
        detay: (oran, n) => `Bu bloktaki uçuşların ${oran} kadarı 15 dakika ya da daha geç vardı (${n} test uçuşu).`,
        detaySiz: 'Geç varış payının en yüksek olduğu kalkış bloğu.',
      },
      varis: {
        baslik: 'En güvenilir ve en riskli varış',
        guvenilir: 'En güvenilir:',
        riskli: 'En riskli:',
        satir: (ad, oran) => `${ad}, geç varış ${oran}`,
        satirSiz: (ad) => ad,
      },
      mevsim: {
        baslik: 'Yaz ve ilkbahar karşılaştırması',
        ileri: 'Yazın daha geç',
        geri: 'Yazın daha erken',
        ayni: 'Yaz ve ilkbahar aynı',
        detay: (yaz, ilk) => `Geç varış oranı: yaz ${yaz}, ilkbahar ${ilk}.`,
      },
      tipik: {
        baslik: 'Tipik rötar',
        detay: 'Uçuşların yarısı tarifeden en fazla bu kadar geç varır (eksi değer erken varış demektir).',
      },
    },
  },

  havalimani: {
    olcutler: {
      gozlenen_arrdel15_orani: 'Gözlenen geç varış oranı (15+ dk)',
      tahmin_arrdel15_orani: 'Tahmin edilen geç varış oranı (T2)',
      iptal_orani: 'İptal oranı',
      kapsama_p80: 'P80 üst sınır kapsaması',
      kapsama_p95: 'P95 üst sınır kapsaması',
    },
    aria: (iata, ad, olcut, deger, n) => `${iata}, ${ad}. ${olcut}: ${deger}. ${n} test uçuşu. Ayrıntı için seçin.`,
    lejantBaslik: (olcut) => `${olcut}: düşük → yüksek`,
    lejantBoyut: (az, cok) => `Nokta alanı test uçuşu sayısıyla büyür (${az} ile ${cok} arası)`,
    lejantYok: 'Kesik çizgili boş daire: yayımlanmadı',
    lejantYay: (az, cok) => `Yay kalınlığı, rotadaki uçuş sayısını gösterir (${az} ile ${cok} arası)`,
    lejantYayRenk: 'Yay rengi, noktalarla aynı geç varış skalasını kullanır.',
    yayGrup: (iata) => `${iata} çıkışlı rotalar. Rotalar arasında gezinmek için ok tuşlarını kullan.`,
    yayEtiket: (iata, ad, n, oran) => `${iata}, ${ad}. ${n} test uçuşu, geç varış oranı ${oran}.`,
    yayEksik: (n) => `${n} varış noktasının koordinatı yok; haritada çizilmedi.`,
    yayDisari: (n) => `${n} varış noktası haritanın gösterdiği alanın dışında; çizilmedi.`,
    yayYok: 'Rota yayları yüklenemedi; aşağıdaki rota tablosu etkilenmedi.',
    yayIpucuUcus: (n) => `${n} test uçuşu`,
    yayIpucuGec: (oran) => `Geç varış: ${oran}`,
    ayrintiBaslik: 'Havalimanı ayrıntıları',
    ayrintiBos: 'Haritada bir nokta ya da tabloda bir kod seç; o havalimanından çıkan rotalar yay olarak çizilir.',
    satirlar: {
      testUcus: 'Test uçuşu',
      gozlenen: 'Gözlenen geç varış',
      tahmin: 'Tahmin edilen geç varış',
      iptal: 'İptal oranı',
      p80: 'P80 kapsaması',
      p95: 'P95 kapsaması',
    },
    rotalariGoster: (iata) => `${iata} çıkışlı rotalara git`,
    renklendir: 'Noktaları şuna göre renklendir',
    haritaNotu: 'Harita: Natural Earth (kamu malı) eyalet sınırları.',
    haritaNotuEyaletsiz: 'Eyalet sınırları yüklenemedi; noktalar ve tablo etkilenmedi.',
    tabloBaslik: 'Havalimanı tablosu',
    tablo: {
      baslik: 'Havalimanı değerleri, nihai test dönemi',
      etiket: 'Havalimanı değerleri tablosu, kaydırılabilir',
      havalimani: 'Havalimanı',
      testUcus: 'Test uçuşu',
      gozlenen: 'Gözlenen geç',
      gozlenenIpucu: 'Tarifeden 15 dakika ya da daha geç varan uçuşların payı',
      tahmin: 'Tahmin edilen geç',
      tahminIpucu: 'T2 modelinin ortalama tahmin olasılığı',
      fark: 'Tahmin − gözlenen',
      farkIpucu: 'Yüzde puan',
      iptal: 'İptal',
      p80: 'P80 kapsaması',
      p80Ipucu: 'Hedef %80',
      p95: 'P95 kapsaması',
      p95Ipucu: 'Hedef %95',
    },
    yayimlanmayanlar: 'Yayımlanmayanlar: ',
    yayimlanmayanSonu: '. Uçuşların %90’ından fazlası tek havayoluna ait olduğu için oranları gizlenir; havalimanları haritada kalır.',
    haritaBaslik: (n) => `${n} havalimanının haritası`,
    haritaAciklama: 'Eyalet sınırları üzerinde havalimanı noktaları. Her nokta seçilebilir; seçilen havalimanından çıkan rotalar yay olarak çizilir. Tablo aynı değerleri listeler.',
  },

  rota: {
    baslik: (kalkis) => `${kalkis} çıkışlı rotalar`,
    filtreler: 'Rota filtreleri',
    kalkis: 'Kalkış havalimanı',
    varis: 'Varış',
    tumVarislar: 'Tüm varışlar',
    blok: 'Kalkış bloğu (yerel saat)',
    tumBloklar: 'Tüm bloklar',
    mevsim: 'Mevsim',
    tumMevsimler: 'Tüm mevsimler',
    uyariBaslik: 'Önerilen tampon (†): ',
    gizlemeNotu: 'n < 50 uçuşlu ya da uçuşların %90’ından fazlası tek havayoluna ait hücreler gösterilmez. Kantiller varış rötarıdır (dk; eksi değer erken varış).',
    yukleniyor: (iata) => `${iata} çıkışlı rotalar yükleniyor…`,
    havalimaniNotu: (nedeni) => `havalimanı düzeyindeki oranlar yayımlanmıyor. ${nedeni}`,
    ozet: (gosterilen, toplam, kalkis) => `${kalkis} çıkışlı ${toplam} hücreden ${gosterilen} tanesi gösteriliyor.`,
    risk: {
      low: 'Düşük',
      medium: 'Orta',
      high: 'Yüksek',
      aciklama: (alt, ust) => `Geç varış oranı için risk düzeyi: ${alt} altı düşük, ${alt} ile ${ust} arası orta, ${ust} ve üstü yüksek.`,
    },
    olcek: {
      baslik: 'Gecikme sütunlarını okuma',
      p50: 'uçuşların yarısı bu süre içinde varır',
      p80: 'uçuşların 10’da 8’i bu süre içinde varır',
      p95: 'uçuşların 20’de 19’u bu süre içinde varır',
      erken: 'Eksi değer erken varış demektir.',
    },
    tablo: {
      baslik: (kalkis) => `${kalkis} çıkışlı rota hücreleri, nihai test dönemi`,
      etiket: 'Rota hücreleri tablosu, kaydırılabilir',
      gruplar: ['Rota hücresi', 'Geç varış (15+ dk)', 'Varış rötarı', 'Ayarlı sınırlar', 'Sınır içinde kalan pay', 'Diğer'],
      varis: 'Varış',
      kalkis: 'Kalkış',
      kalkisIpucu: 'Tarifeli kalkış bloğu, yerel saat',
      mevsim: 'Mevsim',
      ucus: 'Uçuş (n)',
      gozlenen: 'Geç varış oranı',
      gozlenenIpucu: 'Tarifeden 15 dakika ya da daha geç varan uçuşların payı',
      tahmin: 'Tahmin edilen oran',
      p50: 'Tipik rötar',
      p50Ipucu: 'Tipik rötar (P50): uçuşların yarısı bu süre içinde varır',
      p80: 'Kötü gün',
      p80Ipucu: 'Kötü gün (P80): uçuşların 10’da 8’i bu süre içinde varır',
      p95: 'En kötü durum',
      p95Ipucu: 'En kötü durum (P95): uçuşların 20’de 19’u bu süre içinde varır',
      p80Sinir: 'Kötü gün sınırı (ayarlı)',
      p80SinirIpucu: 'Tek yönlü conformal ayarlı P80 üst sınırı, hedef kapsama %80',
      p95Sinir: 'En kötü durum sınırı (ayarlı)',
      p95SinirIpucu: 'Tek yönlü conformal ayarlı P95 üst sınırı, hedef kapsama %95',
      p80Kapsama: 'Kötü gün sınırı içinde',
      p80KapsamaIpucu: 'Uçuşların ayarlı kötü gün sınırı içinde kalan gözlenen payı (hedef %80)',
      p95Kapsama: 'En kötü durum sınırı içinde',
      p95KapsamaIpucu: 'Uçuşların ayarlı en kötü durum sınırı içinde kalan gözlenen payı (hedef %95)',
      iptal: 'İptal',
      blok: 'Tarifeli blok süresi',
      blokIpucu: 'Tarifeli blok süresinin medyanı',
      tampon: 'Önerilen tampon †',
      tamponIpucu: (uyari) => `Plan modeli, τ = 0,80. ${uyari}`,
    },
  },

  // ------------------------------------------------------------------ kalibrasyon
  kal: {
    gorevler: { arrdel15: 'Geç varış (15+ dk)', iptal: 'İptal' },
    gorev: 'Görev',
    model: 'Model',
    modelPlan: 'Plan modeli (yalnızca tarife)',
    modelT2: 'T2 modeli (hava bilgisiyle)',
    yontem: {
      ham: 'Ham model kantili',
      statik: 'Statik conformal ayar',
      kayan: 'Kayan conformal ayar (aylık)',
    },
    b1Ham: 'B1 referansı, ham kantil',
    ikiYonlu: 'İki yönlü %80 aralık, kayan',
    guvenBaslik: 'Güvenilirlik: tahmin edilen olasılıklar gerçekleşenle örtüşüyor mu?',
    nokta: (k, tahmin, gozlenen, n) => `dilim ${k}: tahmin ${tahmin}, gözlenen ${gozlenen}, n ${n}`,
    aciklama: (n) => `Her nokta bir ondalık dilimdir (dilim başına yaklaşık ${n} uçuş). Köşegene yakın nokta, tahminle gerçekleşenin örtüştüğü anlamına gelir.`,
    aciklamaYok: 'Bu görev için güvenilirlik verisi yok.',
    xEtiket: 'Ortalama tahmin olasılığı',
    yEtiket: 'Gözlenen sıklık',
    grafikBaslik: (gorev) => `Güvenilirlik diyagramı: ${gorev}`,
    grafikAciklama: (adlar) => `Ondalık dilimlerde ortalama tahmin olasılığına karşı gözlenen sıklık: ${adlar}.`,
    tabloGoster: 'Değerleri tablo olarak göster',
    dilim: 'Dilim',
    tahmin: (ad) => `${ad}: tahmin`,
    gozlenen: (ad) => `${ad}: gözlenen`,
    tabloBaslik: (gorev) => `Güvenilirlik dilimleri: ${gorev}`,
    kapsamaBaslik: 'Rötar üst sınırlarının aylık kapsaması',
    kapsamaGiris: 'P80 sınırının yaklaşık %20, P95 sınırının yaklaşık %5 uçuş tarafından aşılması beklenir.',
    ay: (yil) => `Ay (${yil})`,
    ayYok: 'Ay',
    kapsamaY: 'Gözlenen kapsama',
    hedef: (yuzde) => `Hedef ${yuzde}`,
    nokta2: (ay, kapsama, n) => `${ay}: ${kapsama} (n ${n})`,
    ustSinir: (p) => `P${p} üst sınır: sınırın altında kalan uçuşların payı`,
    kapsamaGrafikBaslik: (p, model) => `P${p} sınırının aylık kapsaması, ${model}`,
    kapsamaGrafikAciklama: (adlar) => `Üst sınırın altında kalan uçuşların aylık payı: ${adlar}.`,
    ay2: 'Ay',
    cumle: (alt, altAy, ust, ustAy, hedef) => `Kayan ayarlı kapsama aylara göre ${alt} (${altAy}) ile ${ust} (${ustAy}) arasında değişir; hedef ${hedef}.`,
  },

  // ------------------------------------------------------------------ hava deneyi
  hava: {
    varyant: { plan: 'Plan', T2: 'T2', T6: 'T6', T12: 'T12', oracle: 'Oracle (üst sınır)' },
    karsilastirma: {
      'T2-plan': 'T2 eksi plan',
      'oracle-T2': 'Oracle eksi T2',
      'oracle-plan': 'Oracle eksi plan',
      'T6-plan': 'T6 eksi plan',
      'T12-plan': 'T12 eksi plan',
    },
    degerAriaEtiket: 'Varyanta göre ölçüt değerleri',
    degerBaslik: 'Varyanta göre sonuçlar',
    degerCaption: 'Varyanta göre ölçüt değerleri, nihai test dönemi',
    olcut: 'Ölçüt',
    dahaIyi: 'Daha iyi olan',
    farkBaslik: 'Havanın kattığı',
    farkAriaEtiket: 'Varyantlar arasındaki farklar',
    farkCaption: 'Aynı uçuşlarda farklar, %95 aralıklarla',
    karsilastirmaBaslik: 'Karşılaştırma',
    fark: 'Fark',
    aralik: '%95 aralık',
    aralikGrafik: 'Aralık',
    sifiriDislar: 'Sıfırı dışlıyor mu?',
    oracleVar: 'Oracle varyantı (tarifeli anda gözlenmiş hava) yalnızca üst sınırdır; pratikte elde edilemez.',
    oracleYok: 'Oracle sonucu (tarifeli anda gözlenmiş havayla üst sınır) yok.',
    miniEtiket: (deger, aralik) => `Fark ${deger}, %95 aralık ${aralik}`,
  },

  // ------------------------------------------------------------------ hata analizi
  hataAnalizi: {
    boyut: {
      origin: 'Kalkış havalimanı',
      dest: 'Varış havalimanı',
      saat_blogu: 'Tarifeli kalkış bloğu',
      ay: 'Ay',
      haftanin_gunu: 'Haftanın günü',
      mesafe_grubu: 'Mesafe grubu',
      rota: 'Rota',
      hava_T2: 'Hava kategorisi (T2)',
      olay_gunu: 'Olay günleri ve diğer günler',
    },
    olay: 'Olay günleri',
    diger: 'Diğer günler',
    gorevKantil: 'varış rötarı kantilleri',
    gorevGecVaris: 'geç varış (15+ dk)',
    secenek: (boyut, model, gorev) => `${boyut}: ${model}, ${gorev}`,
    listeBaslik: {
      brier_skill: 'B1’e göre en küçük Brier skor kazancına sahip kalkış havalimanları (T2 modeli)',
      kapsama_p80_ham: 'En büyük kalibrasyon sapmaları: ham plan P80 kapsaması %80’den en uzak olan kalkış havalimanları',
    },
    listeGenel: (olcut) => `${olcut} ölçütü için listelenen segmentler`,
    kirilim: 'Kırılım',
    cubukOlcut: 'Çubuk grafik için ölçüt',
    giris: 'Betimleyici kırılımlar: farklar model kalitesi kadar trafik karışımını, havayı ve hacmi de yansıtır; hiçbir havalimanı hakkında hüküm değildir.',
    tabloBaslik: (boyut, model) => `${boyut}, ${model}, nihai test dönemi`,
    tabloEtiket: 'Segment tablosu, kaydırılabilir',
    segment: 'Segment',
    ucus: 'Uçuş (n)',
    eksikler: (liste) => `Bu kırılımda yer almayanlar: ${liste} (havalimanı düzeyindeki değerleri yayımlanmıyor).`,
    cubukNotu: 'Çubuklar segmentlerin sırasını izler, değerlerini değil.',
    cubukNotuHedef: (yuzde) => `Çubuklar segmentlerin sırasını izler. Kesik çizgi %${yuzde} hedefini gösterir.`,
    cubukBaslik: (olcut) => `Segmentlere göre ${olcut}`,
    cubukAciklama: (olcut, boyut, model) => `${boyut} segmentlerinin her biri için ${olcut} değerlerini gösteren yatay çubuklar, ${model}.`,
    iki: 'İki ölçüte göre listelenen kalkış havalimanları',
    ikiNot: 'Yalnızca kalkış havalimanları; hiçbir havalimanının operasyonu hakkında hüküm değildir.',
  },

  // ------------------------------------------------------------------ yöntem
  yontem: {
    giris: 'Her başlığı aç; ayrıntılar açıldığında yüklenir.',
    kalibrasyon: {
      baslik: 'Kalibrasyon ve kapsama',
      ozet: 'Olasılıklar gerçekleşenle uyumlu; rötar üst sınırları bazı aylarda hedefin altında kalıyor.',
    },
    hava: {
      baslik: 'Hava deneyi',
      ozet: 'Aynı uçuşlar, hava gözlemiyle ve gözlemsiz: hava, sıralama başarısını artırıyor.',
    },
    hatalar: {
      baslik: 'Hata analizi',
      ozet: 'Model nerede daha güçlü, nerede daha zayıf: havalimanı, saat ve aya göre betimleyici kırılımlar.',
    },
    sinirlar: {
      baslik: 'Sınırlılıklar',
      ozet: 'Bu analiz neyi söyleyemez.',
      maddeler: (n) => [
        `Yalnızca ${n} kalkış havalimanındaki, bildirim yapan havayollarının tarifeli iç hat uçuşları; uçak rotasyonu, ekip ve ağ etkileri yok.`,
        'Kamuya açık rötar kayıtları yaklaşık iki ay gecikmeyle yayımlanır. Aylık yeniden kalibrasyon, sonuçların uçuştan bir gün sonra bilindiğini varsayar; bu yalnızca kendi verisine sahip bir işletmeci için geçerlidir.',
        'Modeller bir kez, test döneminden önce biten veriyle eğitildi; rötar düzeyi kaydı ve modeller güncellenmedi.',
        'Rötar kantilleri yalnızca gerçekleşen uçuşları anlatır; iptal edilen ve yönü değişen uçuşlar dışındadır.',
        'Tampon sonuçları, bir dakika tamponun bir dakika rötarı ortadan kaldırdığını varsayar ve varsayılmış bir maliyet oranı kullanır; gerçek tarife değişiklikleriyle doğrulanmadı.',
        'Havalimanı ve segment farkları trafiği, havayı ve hacmi de yansıtır; hiçbir havalimanı hakkında hüküm değildir.',
        'Gösterilmeyenler: havayolu adı, sıralama, uçuş numarası, rötar nedeni; n < 50 uçuşlu ya da tek havayolunun %90’dan fazla payı olan hücreler.',
      ],
      gizlenen: (liste) => `${liste} için havalimanı düzeyindeki oranlar gizlendi.`,
    },
    kaynaklar: {
      baslik: 'Veri kaynakları ve lisanslar',
      ozet: 'Uçuş, hava ve havalimanı verileri kamuya açık kaynaklardan gelir.',
      not: 'Lisans notları, doğrulamanın kısmi kaldığı yerleri belirtir. Ham veri burada yeniden dağıtılmaz.',
      harita: 'Harita: Natural Earth (kamu malı)',
      haritaAyrinti: 'Natural Earth 1:110m eyalet sınırları.',
    },
    notlar: {
      baslik: 'Sonuçlarla kaydedilen notlar',
      ozet: 'Değerlendirmeyle birlikte tutulan ayrıntılar.',
      yok: 'Kaydedilmiş not yok.',
    },
  },

  // ------------------------------------------------------------------ hakkında
  hakkimda: {
    baslik: 'Bu proje hakkında',
    metin: 'Bu projeyi veri analizinden veri bilimine geçerken yaptım. Tahmini, dürüst değerlendirmeyi ve bir karar modelini birleştiren uçtan uca bir çalışma istedim; konu da ilgi duyduğum havacılık. Verilerin hepsi kamuya açık.',
    yazar: 'Yazar: ',
    github: 'GitHub profili',
    depo: 'Proje deposu',
    linkedin: 'LinkedIn',
  },

  // ------------------------------------------------------------------ sözlük
  sozluk: {
    giris: 'Sitede geçen terimlerin sade açıklamaları.',
    ara: 'Terim ara',
    araIpucu: 'Terim ya da açıklamada geçen sözcük',
    durum: (n, toplam) => `${toplam} terimden ${n} tanesi gösteriliyor.`,
    bos: 'Aramayla eşleşen terim yok. Aramayı temizleyin ya da daha kısa bir sözcük deneyin.',
    temizle: 'Aramayı temizle',
    nerede: 'Bu sitede: ',
    grupEtiket: (ad) => `${ad} terimleri`,
  },

  // ------------------------------------------------------------------ tampon (OR)
  or: {
    giris: 'Tarifeye kaç dakika tampon eklenmeli? Çok tampon zaman harcar, az tampon rötar bırakır. Politikalar test döneminden önce donduruldu.',
    bulgu: 'Ana bulgu: ',
    bulguYok: 'Tampon bulgusu bulunamadı.',
    notlarBaslik: 'Varsayımlar ve notlar',
    tauBaslik: 'Maliyet oranı',
    ozetCumle: (kat, a, b, ek) => `Rötar dakikası ${kat} kat kötüyse: geç varış ${a} düzeyinden ${b} düzeyine iniyor (uçuş başına ${ek} tampon).`,
    slider: {
      soru: 'Bir dakika rötar, bir dakika boş beklemeden kaç kat daha kötü?',
      kat: (x) => `${x} kat`,
      deger: (x) => `Bir dakika rötar, bir dakika boş beklemeden ${x} kat daha kötü`,
      tau: (t) => `τ = ${t}`,
      ipucu: 'Ok tuşlarıyla değiştirebilirsin.',
    },
    politikalarBaslik: 'Politikalar ve karşılaştırmalar',
    politikaBaslik: (kat) => `Politikalar, maliyet oranı ${kat}`,
    politikaCaption: (kat) => `Politikaların test dönemi değerlendirmesi, maliyet oranı ${kat}`,
    politikaEtiket: 'Politikalar tablosu, kaydırılabilir',
    kolon: {
      politika: 'Politika',
      ek: 'Ek tampon (dk/uçuş)',
      kalan: 'Kalan rötar (dk/uçuş)',
      bosa: 'Boşa giden (dk/uçuş)',
      arr: 'Geç varış oranı (15+ dk)',
      emilen: 'Zamanında ya da erken varan',
      maliyet: 'Maliyet',
      butce: 'Bütçe (dk/uçuş)',
    },
    karsilastirmaBaslik: 'Karşılaştırmalar: fark ve %95 aralık',
    karsilastirmaCaption: (kat) => `Politika farkları, maliyet oranı ${kat}`,
    karsilastirmaEtiket: 'Karşılaştırmalar tablosu, kaydırılabilir',
    karsilastirma: 'Karşılaştırma',
    olcut: {
      maliyet: 'Maliyet',
      kalan_rotar_dk: 'Kalan rötar (dk)',
      arrdel15_orani: 'Geç varış oranı',
      kullanilmayan_dk: 'Boşa giden (dk)',
    },
    farkNotu: 'Fark, ilk politika eksi ikincidir; düşük değer daha iyidir, eksi fark ilk politikanın daha iyi olduğunu gösterir.',
    diger: 'Diğer karşılaştırmalar',
    yokKarsilastirma: 'Bu maliyet oranı için karşılaştırma yok.',
    butceBaslik: 'Bütçe eğrisi: aynı toplam tampon, farklı dağıtım',
    olcutSec: 'Grafikte gösterilen ölçüt',
    olcutArr: 'Geç varış oranı (15+ dk)',
    olcutKalan: 'Kalan rötar (dk/uçuş)',
    xEtiket: 'Tampon bütçesi (dk/uçuş)',
    grafikBaslik: (olcut) => `Bütçe eğrisi: ${olcut}`,
    grafikAciklama: (adlar) => `Tampon bütçesine karşı ölçüt değeri; seriler: ${adlar}.`,
    nokta: (butce, deger) => `bütçe ${butce}: ${deger}`,
    tabloGoster: 'Değerleri tablo olarak göster',
    butceCaption: (olcut) => `Bütçe eğrisi değerleri: ${olcut}`,
    esitBaslik: 'Aynı bütçede: plan modeli ile B1 arasındaki fark',
    esit: {
      anlamsiz: (n) => `${n} bütçe noktasının hiçbirinde, plan modeli B1’den belirgin biçimde iyi değil.`,
      anlamli: (k, n) => `${n} bütçe noktasının ${k} tanesinde fark belirgin; ayrıntı için tabloya bak.`,
      yok: 'Bu karşılaştırma için veri yok.',
    },
    esitCaption: (olcut) => `Plan modeli eksi B1, aynı bütçede: ${olcut}`,
    kesifsel: {
      rozet: 'Keşifsel',
      baslik: 'Keşifsel bölüm',
      uyari: 'Sonuç görüldükten sonra yapılan inceleme; nihai test sonucu sayılmaz.',
      beklenen: 'beklenen',
      gerceklesen: 'gerçekleşen',
      seri: (ad, tur) => `${ad}, ${tur}`,
      grafikBaslik: 'Keşifsel bütçe eğrisi: geç varış oranı, beklenen ve gerçekleşen',
      tabloCaption: 'Keşifsel bütçe eğrisi değerleri, geç varış oranı',
    },
    veriYok: 'Tampon verisi bulunamadı.',
  },
};

// Dil ve metin nesnesi. T yerinde güncellenir; başvurular geçerli kalır.
export const T = {};

let current = 'en';

function isPlain(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function merge(target, source) {
  for (const [key, value] of Object.entries(source)) {
    if (isPlain(value)) {
      if (!isPlain(target[key])) target[key] = {};
      merge(target[key], value);
    } else {
      target[key] = value;
    }
  }
}

export function setLang(lang) {
  current = lang === 'tr' ? 'tr' : 'en';
  merge(T, TR);
  if (current === 'en') merge(T, EN);
  return current;
}

export const getLang = () => current;

setLang('en');
