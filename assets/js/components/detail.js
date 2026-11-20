import { h, copyText, toast, pctText } from '../util.js';
import { buildMemo, similarCount, yoyLabel, wowLabel } from '../memo.js';
import { favorites, notes } from '../store.js';

function Sparkline(series) {
  if (!series || series.length < 2) return null;
  const W = 300, H = 56, pad = 4;
  const min = Math.min(...series), max = Math.max(...series), span = max - min || 1;
  const pts = series.map((v, i) => [pad + (i * (W - pad * 2)) / (series.length - 1), H - pad - ((v - min) / span) * (H - pad * 2)]);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'spark');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `최근 ${series.length}주 관심지수 추이`);
  const line = document.createElementNS(ns, 'polyline');
  line.setAttribute('points', pts.map((p) => p.join(',')).join(' '));
  const dot = document.createElementNS(ns, 'circle');
  dot.setAttribute('cx', pts[pts.length - 1][0]);
  dot.setAttribute('cy', pts[pts.length - 1][1]);
  dot.setAttribute('r', 3.5);
  svg.append(line, dot);
  return svg;
}

export function openDetail({ item, siblings, tpl, data }) {
  const root = document.getElementById('detail-root');
  const catLabel = data.categories.find((c) => c.id === item.category)?.label || '';
  const memo = buildMemo(item, { similar: similarCount(item, siblings, tpl) }, tpl, catLabel);
  const kw = item.keyword.split('/')[0];
  const q = encodeURIComponent(kw);
  const tag = encodeURIComponent(kw.replace(/\s+/g, ''));
  const L = tpl.search_links;
  const close = () => { root.replaceChildren(); document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', onKey);

  const fav = h('button', { class: 'btn ghost', type: 'button' }, favorites.has(item.keyword) ? '★ 즐겨찾기 해제' : '☆ 즐겨찾기');
  fav.addEventListener('click', () => {
    const on = favorites.toggle(item.keyword);
    fav.textContent = on ? '★ 즐겨찾기 해제' : '☆ 즐겨찾기';
    toast(on ? '즐겨찾기에 추가했어요' : '즐겨찾기를 해제했어요');
  });
  const note = h('textarea', { class: 'note', placeholder: '이 키워드에 대한 내 메모 (이 브라우저에만 저장돼요)' });
  note.value = notes.get(item.keyword);
  note.addEventListener('input', () => notes.set(item.keyword, note.value));

  const spark = Sparkline(item.extra?.series);
  const sheet = h('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': `${item.keyword} 상세` },
    h('button', { class: 'close', type: 'button', 'aria-label': '닫기', onclick: close }, '×'),
    h('h3', {}, item.cross_count >= 2 ? h('span', { class: 'star', style: 'color:var(--star)' }, '★') : null, item.keyword,
      catLabel ? h('span', { class: 'tag' }, catLabel) : null),
    h('section', {}, h('div', { class: 'stats' },
      h('div', { class: 'stat' }, h('small', {}, '전주 대비'), h('b', {}, wowLabel(item, tpl))),
      h('div', { class: 'stat' }, h('small', {}, '작년 동기'), h('b', {}, yoyLabel(item, tpl))),
      h('div', { class: 'stat' }, h('small', {}, '순위'), h('b', {}, item.rank != null ? `${item.rank}위` : '-')))),
    spark ? h('section', {}, h('h4', {}, '최근 8주 추이 (네이버)'), spark) : null,
    h('section', {}, h('h4', {}, '글 기획 메모'), h('div', { class: 'memo-box' }, memo.short),
      h('div', { class: 'row-actions' },
        h('button', { class: 'btn', type: 'button', onclick: async () => toast((await copyText(memo.full)) ? '메모를 모두 복사했어요' : '복사에 실패했어요') }, '메모 전체 복사'),
        h('button', { class: 'btn ghost', type: 'button', onclick: async () => toast((await copyText(item.keyword)) ? '키워드를 복사했어요' : '복사에 실패했어요') }, '키워드 복사'),
        fav),
      h('p', { class: 'meta' }, memo.tags.map((t) => `#${t}`).join(' '))),
    h('section', {}, h('h4', {}, '바로 검색'), h('div', { class: 'links' },
      h('a', { href: L.naver.replace('{q}', q), target: '_blank', rel: 'noopener' }, '네이버'),
      h('a', { href: L.google.replace('{q}', q), target: '_blank', rel: 'noopener' }, '구글'),
      h('a', { href: L.youtube.replace('{q}', q), target: '_blank', rel: 'noopener' }, '유튜브'),
      h('a', { href: L.instagram.replace('{tag}', tag), target: '_blank', rel: 'noopener' }, '인스타그램'))),
    h('section', {}, h('h4', {}, '내 메모'), note));
  const overlay = h('div', { class: 'overlay', onclick: (e) => { if (e.target === overlay) close(); } }, sheet);
  root.replaceChildren(overlay);
  sheet.querySelector('.close').focus();
}
