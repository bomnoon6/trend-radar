import { h, normKey } from './util.js';
import { load, save } from './store.js';
import { BOXES } from './boxes.js';
import { Header, CategoryTabs } from './components/header.js';
import { CrossBand } from './components/cross.js';
import { Box } from './components/box.js';
import { Footer } from './components/footer.js';
import { openDetail } from './components/detail.js';

const app = document.getElementById('app');
const state = { mode: load('mode', 'latest'), category: load('category', 'all'), tabs: {}, expanded: {} };
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

async function render() {
  let data;
  try { data = await getData(state.mode); } catch (e) {
    app.replaceChildren(h('p', { class: 'error-box' }, '데이터를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.'));
    return;
  }
  const rerender = () => render();
  const onOpen = (item, pool) => openDetail({ item, siblings: pool, tpl, data });
  app.replaceChildren(
    Header({ data, state, theme: theme || (systemDark() ? 'dark' : 'light'),
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
