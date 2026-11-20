import { h } from '../util.js';

export function Footer({ status, state }) {
  const rows = Object.entries(status?.sources || {}).map(([id, s]) => {
    const st = id === 'google_archive' ? s : s[state.mode];
    if (!st) return null;
    const ok = st.ok !== false;
    const warn = ok && st.stale;
    const text = id === 'google_archive'
      ? (ok ? `스냅샷 ${st.snapshot}` : st.message)
      : (ok ? `성공 · ${st.count}건${st.discovered != null ? ` · 신규 발견 ${st.discovered}개` : ''}${st.stale ? ' · 갱신 지연' : ''}` : `실패 · ${st.error || ''}`);
    return h('li', {}, h('span', { class: `dot${!ok ? ' fail' : warn ? ' warn' : ''}` }), `${s.label}: ${text}`);
  }).filter(Boolean);
  return h('footer', { class: 'foot' },
    h('div', {}, '소스별 수집 상태'), h('ul', {}, rows),
    h('div', {}, '데이터 출처: 네이버 데이터랩 쇼핑인사이트(여성 20~40대, 주간) · 한국관광공사 공공데이터포털(월간) · 구글 트렌드(비공식 수집). ',
      '조회 시 AI를 호출하지 않으며 모든 문구는 규칙 기반입니다. 하루 2회 자동 갱신됩니다.'));
}
