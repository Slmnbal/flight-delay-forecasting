# M3 kararı – Plan ve altyapı soruları

- **Tarih:** 2026-11-18 · **Karar veren:** kullanıcı ("Öneriler uygun")
- **Data Scientist planı (`experiments/modelleme-plani.md`):** bilgi zamanı T = 2 saat; varış (Dest) havası yalnızca hedef 30 havalimanı için; kabul toleransları (P80 ±2 puan, P95 ±1 puan, segment ölçütü, K3 kalibrasyon eşikleri) şimdilik plandaki gibi, ilk sonuçlardan sonra gözden geçirilir; birincil conformal yöntemi aylık kayan pencere; 7 saat bloğu ve OR hücresi rota × saat bloğu × mevsim; arayüzde taşıyıcı boyutu yok.
- **MLOps:** bağımlılıklar requirements dosyaları + `pip freeze` kilit dosyası; GitHub deposunun kökü `projects/havayolu-ds/`; Docker kapsam dışı.
- **Data Engineer:** kapsam filtresi `origin` (kalkış havalimanı hedef 30'da); rotasyon özelliği çekirdekte yok.
