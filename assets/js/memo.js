// 규칙 기반 글 기획 메모 — 규칙·문구는 config/templates.json 에서 수정한다. (AI/LLM 호출 없음)
import { fmt, pctText } from './util.js';

function longestCommonSubstring(a, b) {
  let best = 0;
  const dp = Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    let prev = 0;
    for (let j = 1; j <= b.length; j++) {
      const tmp = dp[j];
      dp[j] = a[i - 1] === b[j - 1] ? prev + 1 : 0;
      if (dp[j] > best) best = dp[j];
      prev = tmp;
    }
  }
  return best;
}

/** 같은 카테고리·같은 소스에서 키워드를 일부 공유하는 다른 항목 수 */
export function similarCount(item, siblings, tpl) {
  const min = tpl.similar_keywords?.min_shared_chars ?? 3;
  const a = item.keyword.replace(/\s+/g, '');
  return siblings.filter((o) => o !== item && o.category === item.category &&
    longestCommonSubstring(a, o.keyword.replace(/\s+/g, '')) >= min).length;
}

function matches(when, item, ctx) {
  const e = item.extra || {};
  if (when.change_wow_gte != null && !(item.change_wow != null && item.change_wow >= when.change_wow_gte)) return false;
  if (when.yoy_top_prior && !e.yoy_top10) return false;
  if (when.is_season != null && (item.category === 'season') !== when.is_season) return false;
  if (when.similar_count_gte != null && !(ctx.similar >= when.similar_count_gte)) return false;
  if (when.cross_count_gte != null && !(item.cross_count >= when.cross_count_gte)) return false;
  return true;
}

export function wowLabel(item, tpl) {
  const m = tpl.memo;
  const v = item.change_wow;
  if (v == null) return m.wow_label_none;
  if (Math.abs(v) < 0.5) return m.wow_label_flat;
  return fmt(v > 0 ? m.wow_label_up : m.wow_label_down, { pct: Math.abs(v).toFixed(0) });
}

export function yoyLabel(item, tpl) {
  const y = tpl.yoy;
  if (item.yoy != null) return fmt(item.yoy >= 0 ? y.label_up : y.label_down, { pct: Math.abs(item.yoy).toFixed(0) });
  if (item.extra?.yoy_top10) return fmt(y.label_top, { n: y.top_n_for_same_period });
  return y.label_none;
}

export function hashtags(item, catLabel, tpl) {
  const t = tpl.hashtags;
  const kw = item.keyword.split('/')[0].replace(/\s+/g, '');
  const vars = { keyword: kw, category: catLabel, category_suffix: t.category_suffix[catLabel] || '', category_tag: t.category_tag[catLabel] || catLabel };
  const out = [];
  for (const p of t.patterns) {
    const tag = fmt(p, vars).replace(/\s+/g, '').replace(/^#/, '');
    if (tag.length > 1 && !out.includes(tag)) out.push(tag);
    if (out.length >= t.count) break;
  }
  return out;
}

export function buildMemo(item, ctx, tpl, catLabel) {
  const rule = tpl.rules.find((r) => matches(r.when || {}, item, ctx)) || tpl.rules[tpl.rules.length - 1];
  const hint = fmt(rule.hint, { list_top_n: tpl.memo.list_top_n });
  const headline = fmt(tpl.memo.headline, { keyword: item.keyword, wow_label: wowLabel(item, tpl), type: rule.type });
  const priority = item.cross_count >= 2 ? tpl.memo.priority_tag : '';
  const tags = hashtags(item, catLabel, tpl);
  const lines = [headline + (priority ? ` · ${priority}` : ''), `구성 힌트: ${hint}`];
  const y = yoyLabel(item, tpl);
  if (y !== tpl.yoy.label_none) lines.push(y);
  const full = [`키워드: ${item.keyword}`, `카테고리: ${catLabel || '-'}`, `전주 대비: ${wowLabel(item, tpl)}`, `작년 동기: ${y}`,
    `추천 유형: ${rule.type} (${hint})`, priority ? `태그: ${priority}` : null, `해시태그: ${tags.map((t) => '#' + t).join(' ')}`]
    .filter(Boolean).join('\n');
  return { type: rule.type, hint, headline, priority, tags, short: lines.join('\n'), full };
}

export { pctText };
