import { h } from '../util.js';

const SRC = { naver: '네이버', tourapi: '관광공사', google: '구글' };

/** 3개 소스 중 2곳 이상에서 등장한 키워드 띠 */
export function CrossBand({ data, state, onOpen }) {
  const list = data.cross.filter((c) => state.category === 'all' || c.categories.includes(state.category) || c.categories.length === 0);
  const box = h('section', { class: 'cross', 'aria-label': '교차 트렌드' },
    h('h2', {}, '★ 교차 트렌드', h('small', {}, '2곳 이상 소스에서 동시에 등장')));
  if (!list.length) {
    box.append(h('p', { class: 'none' }, '지금은 겹치는 키워드가 없어요.'));
    return box;
  }
  box.append(h('div', { class: 'chips' }, list.slice(0, 20).map((c) => h('button', {
    class: 'chip', type: 'button', onclick: () => onOpen(c),
  }, h('span', { class: 'star' }, '★ '), c.keyword, h('small', {}, c.sources.map((s) => SRC[s] || s).join('·'))))));
  return box;
}
