import { h, copyText, toast, pctText } from '../util.js';
import { yoyLabel } from '../memo.js';

export function rankChange(item) {
  const rc = item.rank_change;
  if (rc === 'NEW') return h('small', { class: 'rc-new' }, 'NEW');
  if (typeof rc === 'number' && rc > 0) return h('small', { class: 'rc-up' }, `▲${rc}`);
  if (typeof rc === 'number' && rc < 0) return h('small', { class: 'rc-down' }, `▼${-rc}`);
  if (rc === 0) return h('small', { class: 'rc-same' }, '–');
  return null;
}

export function surgeBadge(item, tpl) {
  const w = item.change_wow;
  const b = tpl.badges;
  if (w == null) return null;
  if (w >= b.surge_hot.min_wow) return h('span', { class: 'pill hot' }, `${b.surge_hot.label} ${pctText(w)}`);
  if (w >= b.surge_warm.min_wow) return h('span', { class: 'pill warm' }, `${b.surge_warm.label} ${pctText(w)}`);
  return null;
}

/** 한 행: 순위·변동 / 키워드·배지·작년 대비 / 복사 버튼 */
export function Row({ item, displayRank, tpl, metaParts, catLabel, showCategory, onOpen }) {
  const y = yoyLabel(item, tpl);
  const meta = [...(metaParts || []).filter(Boolean)];
  if (item.sub_source === 'shopping_insight' || item.source === 'naver') {
    meta.push(y === tpl.yoy.label_none ? `작년 동기 ${y}` : y);
  } else if (y !== tpl.yoy.label_none) meta.push(y);
  return h('li', { class: 'row' },
    h('div', { class: 'rank' }, displayRank, rankChange(item)),
    h('button', { class: 'main', type: 'button', onclick: () => onOpen(item), 'aria-label': `${item.keyword} 상세 보기` },
      h('div', { class: 'kw' },
        item.cross_count >= 2 ? h('span', { class: 'star', title: '교차 트렌드' }, '★') : null,
        item.keyword,
        surgeBadge(item, tpl),
        item.extra?.discovered ? h('span', { class: 'pill new', title: '데이터랩 인기검색어에서 새로 발견' }, tpl.badges.new_discovery_label) : null,
        showCategory && catLabel ? h('span', { class: 'tag' }, catLabel) : null,
        item.extra?.stale ? h('span', { class: 'badge-stale' }, tpl.badges.stale_label) : null,
        item.extra?.fallback_month ? h('span', { class: 'tag gray' }, '직전 월') : null),
      h('div', { class: 'meta' }, meta.map((m) => h('span', {}, m)))),
    h('button', { class: 'copy', type: 'button', 'aria-label': `${item.keyword} 복사`, onclick: async (e) => {
      e.stopPropagation();
      toast((await copyText(item.keyword)) ? `“${item.keyword}” 복사했어요` : '복사에 실패했어요');
    } }, '복사'));
}
