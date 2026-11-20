// 박스 정의 레지스트리 — 새 박스(4번째 자리)는 여기에 항목 하나를 추가하면 된다.
// select(items) 는 해당 박스에 속한 항목을 고르고, meta(item) 는 행 아래 보조 문구를 만든다.
import { volumeText } from './util.js';

const SUB = (name) => (i) => i.sub_source === name;

export const BOXES = [
  {
    id: 'naver', title: '네이버 데이터랩', sub: '쇼핑인사이트 · 주간 · 여성 20~40대', statusKeys: ['naver'],
    tabs: [{ id: 'main', label: null, filter: (i) => i.source === 'naver',
      meta: (i) => [`관심지수 ${i.score}`] }],
  },
  {
    id: 'tour', title: '한국관광공사', sub: '월간 · 여행·맛집 전용', statusKeys: ['tour'], monthly: true,
    areaTop: (i) => i.source === 'tourapi' && i.sub_source === 'area_demand',
    onlyCategories: ['travel', 'food'],
    tabs: [{ id: 'main', label: null, filter: (i) => i.source === 'tourapi' && i.sub_source === 'related_places',
      meta: (i) => [`${i.extra.area || ''} · 연관 ${i.extra.appearances ?? 1}회`, i.extra.class] }],
  },
  {
    id: 'google', title: '구글 트렌드', sub: '한국', statusKeys: ['google_trending', 'google_youtube'],
    tabs: [
      { id: 'search', label: '검색', statusKey: 'google_trending', filter: (i) => i.source === 'google' && SUB('trending_now')(i),
        meta: (i) => [i.score ? `검색량 ${volumeText(i.score)}` : ''] },
      { id: 'youtube', label: '유튜브', statusKey: 'google_youtube', filter: (i) => i.source === 'google' && SUB('youtube')(i),
        meta: (i) => [i.score ? `급상승 지수 ${i.score >= 5000 ? '급증' : '+' + i.score + '%'}` : ''] },
    ],
  },
];
