// Detay sitesi (index.html) ile sunum sitesinin (sunum/index.html) ortak kabuğu: dil seçimi ve tema.
// İki site aynı localStorage anahtarlarını ("lang", "theme") ve aynı ?lang= parametresini kullanır;
// bu yüzden birinde seçilen dil ve tema ötekinde de geçerlidir. Depolama kullanılamıyorsa her yerde
// try/catch ile atlanır ve seçim yalnızca o ziyaret boyunca geçerli olur.

export function readLangParam() {
  try {
    const value = new URLSearchParams(window.location.search).get('lang');
    return value === 'en' || value === 'tr' ? value : null;
  } catch (err) {
    return null;
  }
}

export function readStoredLang() {
  try {
    const value = window.localStorage.getItem('lang');
    return value === 'en' || value === 'tr' ? value : null;
  } catch (err) {
    return null;
  }
}

export function storeLang(lang) {
  try {
    window.localStorage.setItem('lang', lang);
  } catch (err) {
    // Depolama kullanılamayabilir; seçim yalnızca bu ziyaret boyunca geçerli olur.
  }
}

/** Adreste ?lang= varsa seçili dille günceller; böylece paylaşılan adres seçili dille açılır. */
export function syncUrlLang(lang) {
  if (readLangParam() === null) return;
  try {
    const params = new URLSearchParams(window.location.search);
    params.set('lang', lang);
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}${window.location.hash}`);
  } catch (err) {
    // Adres güncellenemezse seçim yine localStorage'da kalır.
  }
}

// Tema: açık (varsayılan) -> koyu -> otomatik (sistem)
export const MODES = ['light', 'dark', 'auto'];

export function currentMode() {
  const attr = document.documentElement.getAttribute('data-theme');
  return attr === 'light' || attr === 'dark' ? attr : 'auto';
}

export function applyMode(mode) {
  const root = document.documentElement;
  if (mode === 'auto') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', mode);
  try {
    window.localStorage.setItem('theme', mode); // 'auto' is stored too: no stored value means the light default
  } catch (err) {
    // Depolama kullanılamayabilir; seçim yalnızca bu ziyaret boyunca geçerli olur.
  }
}

export const nextMode = () => MODES[(MODES.indexOf(currentMode()) + 1) % MODES.length];
