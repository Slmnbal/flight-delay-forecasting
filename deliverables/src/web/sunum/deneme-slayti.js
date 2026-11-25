// 11. slayt: "Kendin dene". Uçuş seçici, 100 daire ve gecikme çubukları kendin-dene.js modülündedir (detay
// sitesinin Hikâye sekmesiyle ortak); burada yan panel ("gerçekte ne oldu, model ne bekliyordu") eklenir.

import { fmtInt } from '../js/fmt.js';
import { T } from '../js/metin.js';
import { buildTry } from '../js/kendin-dene.js';
import { PICTO_TOTAL, count100 } from '../js/hikaye-ortak.js';
import { slide } from './slayt.js';

export async function slideTry(ctx) {
  const { airportsFile, manifest } = ctx;
  const p = T.sunum.s11;
  let sl = null;
  let last = null;

  function apply(cell) {
    if (!sl) return;
    if (!cell) {
      sl.setKeys(null);
      return;
    }
    const total = fmtInt(PICTO_TOTAL);
    sl.setKeys([
      { label: p.gercek, value: p.gercekDeger(fmtInt(count100(cell.gozlenen_arrdel15_orani)), total) },
      { label: p.model, value: p.gercekDeger(fmtInt(count100(cell.tahmin_arrdel15_orani)), total) },
      { label: p.ucus, value: fmtInt(cell.n_ucus) },
    ]);
  }

  const tryIt = await buildTry(airportsFile, manifest, {
    base: '../',
    intro: false,
    onCell: (cell) => {
      last = cell;
      apply(cell);
    },
  });
  sl = slide({
    n: 11,
    ico: 'plane',
    title: T.hikaye.s10.baslik,
    cls: 'slide-dense',
    figure: tryIt,
    keys: null,
    how: p.nasil,
    means: p.anlam,
    href: '../#explore',
  });
  apply(last);
  return sl;
}
