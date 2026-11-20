// DOM 헬퍼·복사·정규화 등 공통 유틸 (프레임워크 없음)
export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function fmt(str, vars) {
  return String(str).replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ''));
}

/** 교차 트렌드 비교용 정규화: '/' 뒤 지점명·공백·대소문자·끝 조사 제거 (build_data.py 의 norm 과 동일 규칙) */
const PARTICLES = ['은', '는', '이', '가', '을', '를', '의', '에', '과', '와', '도'];
export function normKey(kw) {
  let s = String(kw).split('/')[0].replace(/\s+/g, '').toLowerCase();
  if (s.length > 2 && PARTICLES.includes(s[s.length - 1])) s = s.slice(0, -1);
  return s;
}

/** 교차 트렌드를 화면에서 다시 계산(A-2 를 숨길 때 사용). build_data.py 의 compute_cross 와 같은 규칙 */
export function computeCross(items) {
  const g = new Map();
  for (const it of items) {
    if (it.sub_source === 'area_demand') continue;
    const k = normKey(it.keyword);
    if (!g.has(k)) g.set(k, { key: k, keyword: it.keyword, sources: new Set(), cats: new Set() });
    const e = g.get(k);
    e.sources.add(it.source);
    if (it.category) e.cats.add(it.category);
  }
  return [...g.values()].filter((e) => e.sources.size >= 2)
    .map((e) => ({ key: e.key, keyword: e.keyword, sources: [...e.sources].sort(), categories: [...e.cats].sort() }))
    .sort((a, b) => b.sources.length - a.sources.length || a.keyword.localeCompare(b.keyword));
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = h('textarea', { style: 'position:fixed;opacity:0' });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { /* ignore */ }
    ta.remove();
    return ok;
  }
}

let toastTimer;
export function toast(msg) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 1600);
}

export function pctText(v, digits = 0) {
  if (v == null || Number.isNaN(v)) return null;
  return `${v > 0 ? '▲' : v < 0 ? '▼' : ''}${Math.abs(v).toFixed(digits)}%`;
}

export function volumeText(v) {
  if (v == null) return '';
  if (v >= 1e6) return `${(v / 1e6).toFixed(1).replace(/\.0$/, '')}M+`;
  if (v >= 1e4) return `${Math.round(v / 1e4)}만+`;
  if (v >= 1e3) return `${Math.round(v / 1e3)}천+`;
  return `${Math.round(v)}+`;
}
