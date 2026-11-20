import { h } from '../util.js';
import { Row } from './row.js';

const PAGE = 10;
const MAX = 20;

function roundRobin(items, catOrder) {
  const by = new Map();
  for (const it of items) {
    const k = it.category || 'etc';
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(it);
  }
  const keys = [...catOrder, 'etc'].filter((k) => by.has(k));
  keys.forEach((k) => by.get(k).sort((a, b) => a.rank - b.rank));
  const out = [];
  for (let i = 0; keys.some((k) => by.get(k)[i]); i++) keys.forEach((k) => { if (by.get(k)[i]) out.push(by.get(k)[i]); });
  return out;
}

/** 박스 하나: 소스 상태·카테고리 가용성에 따라 목록 또는 안내문을 그린다. */
export function Box({ def, state, data, status, tpl, onOpen, rerender }) {
  const tabId = state.tabs[def.id] || def.tabs[0].id;
  const tab = def.tabs.find((t) => t.id === tabId) || def.tabs[0];
  const cat = state.category;
  const catOrder = data.categories.map((c) => c.id);
  const catLabel = (id) => data.categories.find((c) => c.id === id)?.label || '기타';
  const modeKey = state.mode;

  const srcStatus = status?.sources?.[tab.statusKey || def.statusKeys[0]]?.[modeKey];
  const stale = data.items.some((i) => tab.filter(i) && i.extra?.stale);

  const head = h('div', { class: 'box-head' },
    h('h2', {}, def.title, stale ? h('span', { class: 'badge-stale' }, tpl.badges.stale_label) : null),
    h('span', { class: 'sub' }, def.sub));
  const parts = [head];

  if (def.tabs.length > 1) {
    parts.push(h('div', { class: 'subtabs' }, h('div', { class: 'seg', role: 'tablist' },
      def.tabs.map((t) => h('button', { type: 'button', role: 'tab', 'aria-pressed': String(t.id === tab.id),
        onclick: () => { state.tabs[def.id] = t.id; rerender(); } }, t.label)))));
  }

  // 작년 기준의 구글은 아카이브 상황에 따라 제공 여부가 갈린다
  const gNote = def.id === 'google' && modeKey === 'lastyear' ? data.notices?.google : null;
  let pool = data.items.filter(tab.filter);
  const unsupported = def.onlyCategories && cat !== 'all' && !def.onlyCategories.includes(cat);
  if (cat !== 'all') pool = pool.filter((i) => i.category === cat);
  else if (def.onlyCategories) pool = pool.filter((i) => def.onlyCategories.includes(i.category));

  if (unsupported) {
    parts.push(h('div', { class: 'notice' }, '이 카테고리는 제공되지 않음'));
    return h('section', { class: 'box', 'data-box': def.id }, parts);
  }
  if (gNote && !gNote.ok && pool.length === 0) {
    parts.push(h('div', { class: 'notice' }, gNote.message));
    return h('section', { class: 'box', 'data-box': def.id }, parts);
  }

  // 한국관광공사: 여행(또는 모두보기)에서는 '뜨는 지역 TOP'을 상단에 노출
  if (def.areaTop && (cat === 'all' || cat === 'travel')) {
    const areas = data.items.filter(def.areaTop).sort((a, b) => a.rank - b.rank).slice(0, 5);
    if (areas.length) {
      parts.push(h('div', { class: 'area-top' }, h('b', {}, `뜨는 지역 TOP ${areas.length} (월간)`),
        h('ol', {}, areas.map((a) => h('li', {}, `${a.rank}. ${a.keyword} `, h('span', {}, `${a.score}`))))));
    }
  }

  if (pool.length === 0) {
    const failed = srcStatus && srcStatus.ok === false;
    parts.push(h('div', { class: 'notice' },
      failed ? `수집 실패 — ${srcStatus.error || '데이터 없음'}` : (cat === 'all' ? '표시할 데이터가 없어요' : '이 카테고리는 제공되지 않음')));
    return h('section', { class: 'box', 'data-box': def.id }, parts);
  }

  const list = cat === 'all' ? roundRobin(pool, catOrder) : pool.sort((a, b) => a.rank - b.rank);
  const key = `${def.id}:${tab.id}`;
  const expanded = !!state.expanded[key];
  const shown = list.slice(0, expanded ? MAX : PAGE);
  parts.push(h('ol', { class: 'list' }, shown.map((item, i) => Row({
    item, displayRank: i + 1, tpl, metaParts: tab.meta(item),
    catLabel: catLabel(item.category), showCategory: cat === 'all', onOpen: (it) => onOpen(it, pool),
  }))));
  if (list.length > PAGE) {
    parts.push(h('button', { class: 'more', type: 'button',
      onclick: () => { state.expanded[key] = !expanded; rerender(); } }, expanded ? '접기' : `더보기 (${Math.min(MAX, list.length)}위까지)`));
  }
  return h('section', { class: 'box', 'data-box': def.id }, parts);
}
