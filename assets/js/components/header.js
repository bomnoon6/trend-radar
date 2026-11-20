import { h } from '../util.js';

const d = (iso) => iso.slice(0, 10).replaceAll('-', '.');
const ym = (s) => `${s.slice(0, 4)}년 ${Number(s.slice(4))}월`;

export function Header({ data, state, theme, onMode, onTheme }) {
  const p = data.period;
  const g = data.generated_at; // 'YYYY-MM-DDTHH:MM:SS+09:00' (KST 그대로 표시)
  const upd = `${Number(g.slice(5, 7))}월 ${Number(g.slice(8, 10))}일 ${g.slice(11, 16)} 갱신`;
  const modes = [['latest', '조회일 기준'], ['lastyear', '작년 기준 20일 후']];
  return h('header', { class: 'top' },
    h('div', { class: 'brand' }, h('h1', {}, '트렌드 레이더'), h('span', { class: 'updated' }, `마지막 ${upd}`)),
    h('div', { class: 'top-right' },
      h('div', { class: 'seg', role: 'group', 'aria-label': '조회 기준' },
        modes.map(([id, label]) => h('button', { type: 'button', 'aria-pressed': String(state.mode === id), onclick: () => onMode(id) }, label))),
      h('button', { class: 'icon-btn', type: 'button', onclick: onTheme, 'aria-label': '화면 모드 전환' }, theme === 'dark' ? '☀ 라이트' : '☾ 다크')),
    h('div', { class: 'period' },
      state.mode === 'latest' ? '실제 기준: ' : '작년 기준(오늘−345일): ',
      h('strong', {}, `${d(p.start)} ~ ${d(p.end)}`), ' (주간) · 관광 ', h('strong', {}, ym(p.tour_ym)), ' (월간)'));
}

export function CategoryTabs({ data, state, onSelect }) {
  const cats = [{ id: 'all', label: '모두보기' }, ...data.categories];
  return h('nav', { class: 'cats', 'aria-label': '카테고리' },
    cats.map((c) => h('button', { class: 'cat-btn', type: 'button', 'aria-pressed': String(state.category === c.id), onclick: () => onSelect(c.id) }, c.label)));
}
