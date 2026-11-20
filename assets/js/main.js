import { h, normKey, computeCross } from './util.js';
import { load, save } from './store.js';
import { BOXES } from './boxes.js';
import { Header, CategoryTabs } from './components/header.js';
import { CrossBand } from './components/cross.js';
import { Box } from './components/box.js';
import { Footer } from './components/footer.js';
import { openDetail } from './components/detail.js';

const app = document.getElementById('app');
const state = { mode: load('mode', 'latest'), category: load('category', 'all'), a2: load('a2', true), tabs: {}, expanded: {} };
const cache = {};
let tpl, status, theme;

const getJSON = async (url) => {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url} ${r.status}`);
  return r.json();
};

function applyTheme(t) {
  theme = t;
  if (t) document.documentElement.setAttribute('data-theme', t); else document.documentElement.removeAttribute('data-theme');
}
const systemDark = () => matchMedia('(prefers-color-scheme: dark)').matches;

async function getData(mode) {
  if (!cache[mode]) cache[mode] = await getJSON(`data/${mode === 'latest' ? 'latest' : 'lastyear'}.json`);
  return cache[mode];
}

function openFromCross(c, data) {
  const k = c.key;
  const hit = data.items.filter((i) => i.sub_source !== 'area_demand' && normKey(i.keyword) === k)
    .sort((a, b) => (a.source === 'naver' ? -1 : 1) - (b.source === 'naver' ? -1 : 1))[0];
  if (hit) openDetail({ item: hit, siblings: data.items.filter((i) => i.source === hit.source), tpl, data });
}

const hasA2 = (data) => data.items.some((i) => i.extra?.discovered || i.extra?.web_rank);

/** A-2(데이터랩 웹 인기검색어)를 끄면 '신규 발견' 항목과 인기 순위 표시를 숨기고 교차 트렌드를 다시 계산한다. */
function view(data) {
  if (state.a2 || !hasA2(data)) return data;
  const kept = data.items.filter((i) => !i.extra?.discovered)
    .map((i) => (i.extra?.web_rank ? { ...i, extra: { ...i.extra, web_rank: null } } : i));
  const cross = computeCross(kept);
  const cnt = new Map(cross.map((c) => [c.key, c.sources.length]));
  const items = kept.map((i) => {
    const n = i.sub_source === 'area_demand' ? 1 : (cnt.get(normKey(i.keyword)) || 1);
    // 순위 변동은 '신규 발견 포함' 순위 기준으로 계산돼 있으므로, 네이버 박스는 숨김 상태에서 변동 표시를 비운다
    const rc = i.source === 'naver' ? null : i.rank_change;
    return n === i.cross_count && rc === i.rank_change ? i : { ...i, cross_count: n, rank_change: rc };
  });
  return { ...data, items, cross };
}

async function render() {
  let data;
  try { data = view(await getData(state.mode)); } catch (e) {
    app.replaceChildren(h('p', { class: 'error-box' }, '데이터를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.'));
    return;
  }
  const rerender = () => render();
  const onOpen = (item, pool) => openDetail({ item, siblings: pool, tpl, data });
  app.replaceChildren(
    Header({ data, state, theme: theme || (systemDark() ? 'dark' : 'light'), hasA2: hasA2(cache[state.mode]),
      onA2: (on) => { state.a2 = on; save('a2', on); render(); },
      onMode: (m) => { state.mode = m; save('mode', m); render(); },
      onTheme: () => { const next = (theme || (systemDark() ? 'dark' : 'light')) === 'dark' ? 'light' : 'dark'; applyTheme(next); save('theme', next); render(); } }),
    CategoryTabs({ data, state, onSelect: (c) => { state.category = c; save('category', c); render(); } }),
    CrossBand({ data, state, onOpen: (c) => openFromCross(c, data) }),
    h('main', { class: 'boxes' }, BOXES.map((def) => Box({ def, state, data, status, tpl, onOpen, rerender }))),
    Footer({ status, state }));
}

(async function init() {
  applyTheme(load('theme', null));
  try {
    [tpl, status] = await Promise.all([getJSON('config/templates.json'), getJSON('data/status.json').catch(() => null)]);
  } catch (e) {
    app.replaceChildren(h('p', { class: 'error-box' }, '설정을 불러오지 못했어요.'));
    return;
  }
  render();
})();
