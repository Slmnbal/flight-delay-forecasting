// Yazar bağlantıları (GitHub profili, proje deposu, LinkedIn). Yalnızca https bağlantıları <a href> olur;
// LINKEDIN_URL boşsa LinkedIn bağlantısı hiç çizilmez. Dış bağlantılar gezinme içindir, veri çekmez.

import { el } from './dom.js';
import { T, GITHUB_URL, REPO_URL, LINKEDIN_URL } from './metin.js';
import { safeHttpsUrl } from './fmt.js';

/** [{href, label}] listesi; geçersiz ya da boş adresler atlanır. */
export function authorLinks() {
  const t = T.hakkimda;
  return [
    [GITHUB_URL, t.github],
    [REPO_URL, t.depo],
    [LINKEDIN_URL, t.linkedin],
  ]
    .map(([url, label]) => ({ href: url ? safeHttpsUrl(url) : null, label }))
    .filter((l) => l.href);
}

/** Bağlantıları ", " ile ayrılmış <a> düğümleri olarak döndürür. */
export function authorLinkNodes() {
  const nodes = [];
  authorLinks().forEach((l, i) => {
    if (i > 0) nodes.push(' | ');
    nodes.push(el('a', { href: l.href, rel: 'noopener' }, l.label));
  });
  return nodes;
}
