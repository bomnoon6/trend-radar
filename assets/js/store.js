// localStorage 래퍼 — 어떤 경우에도 예외를 던지지 않는다(사생활 보호 모드 등). 즐겨찾기·메모 확장 지점.
const P = 'trendradar:';

export function load(key, fallback = null) {
  try {
    const raw = localStorage.getItem(P + key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch { return fallback; }
}

export function save(key, value) {
  try { localStorage.setItem(P + key, JSON.stringify(value)); return true; } catch { return false; }
}

export const favorites = {
  all: () => load('fav', []),
  has: (kw) => favorites.all().includes(kw),
  toggle(kw) {
    const cur = favorites.all();
    const next = cur.includes(kw) ? cur.filter((k) => k !== kw) : [...cur, kw];
    save('fav', next);
    return next.includes(kw);
  },
};

export const notes = {
  get: (kw) => (load('notes', {}))[kw] || '',
  set(kw, text) {
    const all = load('notes', {});
    if (text) all[kw] = text; else delete all[kw];
    save('notes', all);
  },
};
