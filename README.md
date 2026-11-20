# 트렌드 레이더 (trend-radar)

SNS 콘텐츠 기획용 트렌드 대시보드. 네이버 데이터랩(쇼핑인사이트)·한국관광공사·구글 트렌드의 공개 데이터를
GitHub Actions 가 **하루 2회** 수집해 `data/*.json` 으로 저장하고, 순수 HTML/CSS/JS 정적 사이트(GitHub Pages)가 보여줍니다.
조회 시 AI/LLM 호출은 없으며 모든 계산·문구는 규칙 기반입니다.

- **사이트:** https://bomnoon6.github.io/trend-radar/
- **갱신 시각:** 매일 06:17 KST, 18:17 KST (GitHub 사정에 따라 수 분~수십 분 늦을 수 있음). 화면 상단에 마지막 갱신 시각이 표시됩니다.
- **수동 갱신:** 저장소 Actions 탭 → *Collect trends* → *Run workflow* (`skip` 에 `google_youtube` 처럼 건너뛸 수집기를 적을 수 있음)

## 구조

```
config/categories.json   카테고리·소스 매핑·시드 키워드 (코드 수정 없이 편집)
config/templates.json    글 기획 메모 규칙·배지 기준·해시태그·검색 링크
collectors/              소스별 수집기. 공통 인터페이스 collect(period, category) -> list[Item]
scripts/build_data.py    수집 → 병합 → data/*.json 생성 (운영/Actions 에서 실행)
scripts/run_collector.py 수집기 단독 실행·테스트
data/                    latest.json · lastyear.json · status.json · archive/ · _cache/
docs/samples/            실제 API 응답 샘플(키 제거)
index.html, assets/      프론트엔드 (빌드 도구 없음, ES 모듈)
.github/workflows/       collect.yml(수집 cron) · pages.yml(배포)
```

데이터 항목 공통 형식(모든 JSON 에 `schema_version`):
`{rank, keyword, category, source, sub_source, score, change_wow, yoy, rank_change, cross_count, period, extra:{}}`

## 조회 기준 (토글 2개)

| 토글 | 주간 데이터(네이버·구글) | 월간 데이터(관광공사) |
|---|---|---|
| 조회일 기준 | 마지막으로 완료된 주(월~일) | 직전 월 (없으면 더 이전 월로 대체, "직전 월" 태그 표시) |
| 작년 기준 20일 후 | (오늘−345일)이 속한 주 | 그 날짜가 속한 월 |

실제 기준 기간은 화면 상단에 항상 표시됩니다. 구글 트렌드는 과거 조회가 불가능하므로 `data/archive/` 에 쌓은 자체 스냅샷 중
해당 날짜에 가장 가까운 것(±7일)을 씁니다. 없으면 "아카이브 축적 중 — YYYY-MM-DD부터 제공" 으로 표시되며,
수집을 시작한 날 + 345일부터 제공됩니다.

## 소스별 제약과 실패 시 동작

모든 소스는 서로 격리되어 있습니다. 하나가 실패해도 나머지는 정상 발행되고, 실패 내역은 `data/status.json` 과 화면 하단 "소스별 수집 상태"에 표시됩니다.

| 소스 | 주기 | 호출량(1회 실행) | 제약 | 실패 시 |
|---|---|---|---|---|
| 네이버 쇼핑인사이트 (NAVER API HUB) | 주간 | 약 115회 (두 기준 × 약 57회) | 일일 한도 수치는 공식 문서에 없음(429 시 중단). 키워드 5개(앵커 1 + 신규 4)씩 호출, 기본 상한 `NAVER_MAX_CALLS`=1000 | 해당 묶음만 건너뜀. 전체 실패 시 박스에 "수집 실패" 표시 |
| 한국관광공사 (공공데이터포털) | **월간** | 약 30회 × 2 | 개발계정 일 1,000건. 최신 월이 비면 직전 월로 대체. 행정구역 개편 반영: 2026-07부터 광주+전남=`전남광주`(코드 12) | 실패 시 "수집 실패" 표시 |
| 구글 트렌드 – 검색 | 최근 7일 | 페이지 약 7회 | 공식 API 없음. Playwright 로 CSV 내보내기 → 실패 시 화면 표 → 실패 시 공식 RSS(24시간·약 10개) | 모두 실패하면 박스에 실패 표시 |
| 구글 트렌드 – 유튜브 | 최근 7일 | 요청 약 24회(20초 간격, 약 8분) | pytrends 비공식, **429 가 잦음** | 직전 성공 데이터(`data/_cache/youtube.json`)를 쓰고 "갱신 지연" 배지 표시. 성공 이력이 없으면 비어 있음 |

비공식 수집(구글)은 요청 간격을 넉넉히 두고 하루 2회 이내로 유지합니다. 구글 화면 구조가 바뀌면 `collectors/google.py` 의 선택자를 고쳐야 합니다.

### 네이버 점수 읽는 법
분야별 앵커 키워드 1개의 기간 평균을 100 으로 두고 나머지 키워드를 환산한 **상대 관심지수**입니다(분야 안에서만 비교 가능).
"작년 대비"는 같은 분야 앵커 대비 상대값이라 시장 전체의 증감은 제외되며, 원래 값은 `extra.yoy_abs` 에 있습니다.
점수 3 미만 키워드는 클릭량이 너무 작아 변동률을 계산하지 않습니다(`config/categories.json` 의 `naver.min_score_for_change`).
분야가 둘인 카테고리(리빙·자기개발)는 앵커가 달라 순위가 완전히 공정하지는 않으며, `group_weight` 로 보정할 수 있습니다.

## 시드 키워드 수정 방법

`config/categories.json` 만 고치면 됩니다(코드 수정 불필요). 수정 후 `main` 에 push 하면 다음 수집부터 반영됩니다.

- **키워드 추가/삭제:** `categories[].naver.groups[].seeds` 배열을 편집합니다. 한 분야는 4개씩 묶여 호출되므로 많이 늘리면 호출 수가 늘어납니다.
- **앵커 변경:** `groups[].anchor`. 해당 분야에서 클릭량이 크고 꾸준한 키워드를 고르세요(너무 작으면 점수가 비정상적으로 커집니다).
- **시즌상품:** `season.naver.season_windows` 의 시기 창(`start`~`end`, MM-DD)과 `keywords` 를 편집합니다. 조회 기준일부터 `lookahead_days`(기본 30일) 안에 걸리는 창만 사용됩니다. 키워드는 문자열 또는 `{"name":..., "cid":...}`.
- **구글 카테고리 매핑:** `categories[].google.trending_categories`(구글 Trending Now 의 영어 카테고리명). 유튜브용 시드는 `youtube_seeds`.
- **관광공사:** `tour.areas`(지역 코드·기간별 `from`/`until`), `tour.related.food_keywords`(맛집으로 분류할 분류명 키워드).
- **글 기획 메모·배지·해시태그:** `config/templates.json`.

로컬 검증:
```bash
python scripts/run_collector.py naver --category beauty
python scripts/run_collector.py naver --verify-cids     # 분야 코드 검증
```

## 로컬 개발

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env            # 값을 채움. .env 는 커밋되지 않음
python scripts/build_data.py --from-samples   # 샘플로 data/*.json 합성
python -m http.server 8000      # http://localhost:8000
```

환경변수(GitHub Actions 에서는 Secrets 로 등록): `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `DATA_GO_KR_KEY`,
`TOUR_RLTE_KEY`(없으면 `DATA_GO_KR_KEY` 사용). API 키는 코드·커밋·로그에 남지 않으며(로그와 샘플에서 마스킹), `.env.example` 에도 실제 값을 적지 마세요.

## A-2 옵션 (데이터랩 웹 '분야별 인기검색어')

기본 수집(A-1)은 시드 키워드 기반이라 목록에 없는 신규 키워드는 잡히지 않습니다. A-2 를 켜면 데이터랩 웹 화면이 쓰는 내부 요청
(`getCategoryKeywordRank.naver`, 비공식)으로 분야별 인기검색어 1~20위를 가져와 보완합니다.

- **동작:** 인기검색어 중 시드에 없는 키워드는 **"신규 발견"** 배지를 달고, A-1 과 같은 방식(앵커 정규화)으로 다시 호출해
  점수·전주 대비·작년 대비를 계산한 뒤 같은 순위표에 합쳐집니다(분야당 최대 `naver.web_rank.max_new_per_category` 개, 기본 12).
  시드에 있는 키워드는 "데이터랩 인기 n위" 표시만 더해집니다.
- **켜는 법(기본 꺼짐):**
  - 한 번만: Actions → *Collect trends* → *Run workflow* 의 **datalab_web** 체크
  - 계속: 저장소 Settings → Secrets and variables → Actions → **Variables** 에 `USE_DATALAB_WEB_RANK` = `true`
  - 로컬: `.env` 에 `USE_DATALAB_WEB_RANK=true` 또는 `python scripts/build_data.py --datalab-web`
- **비용/제약:** 한 번 실행에 웹 요청 약 12회(두 기준 × 분야 6개, 3초 간격)와 신규 키워드 재조회로 네이버 API 호출이 약 30회 늘어납니다.
  비공식 경로라 언제든 바뀌거나 막힐 수 있으며, 실패하면 하단 상태에 "A-2 실패"로 표시되고 A-1 결과만 정상 발행됩니다.
- **제외 대상:** 시즌상품(분야가 따로 없음)과, 분야 코드를 공유하는 여행/자기개발의 여가·생활편의(여행이 소유, 시드와 맞으면 자기개발로 배정).
  그룹별 `web_rank: false` 로 끄고 켤 수 있습니다.
- 수집기는 [collectors/datalab_web.py](collectors/datalab_web.py), 신규 판정·병합은 `scripts/build_data.py` 의 `find_discovered`/`annotate_web_rank`.

## 새 소스/박스 추가하기

1. `collectors/새소스.py` 에 `collect(period, category=None, *, config=None, http=None)` 구현 (항목은 `base.make_item` 으로 생성)
2. `collectors/__init__.py` 의 `REGISTRY` 에 등록, `scripts/build_data.py` 의 `SOURCE_ORDER` 에 추가
3. 화면: `assets/js/boxes.js` 의 `BOXES` 배열에 박스 정의 한 개 추가 (4번째 박스 자리)

## 장애 시 체크리스트

1. **화면이 비었거나 오래됨:** Actions 탭에서 *Collect trends* 최근 실행의 성공 여부와 시각을 확인. 실패했다면 로그의 "수집·병합" 단계를 봅니다.
2. **하단 상태가 "실패":** 사이트 하단 소스별 상태의 사유를 확인합니다.
   - *네이버* 401/403 → Secrets 의 `NAVER_CLIENT_ID/SECRET` 확인, API HUB 앱에 쇼핑인사이트 이용 신청이 되어 있는지 확인. 429 → 호출 한도 초과(다음 실행까지 대기, 시드 수 축소).
   - *관광공사* `SERVICE_KEY` 오류 → 키 활성화 지연(발급 후 수 시간)·잘못된 키. 두 API 모두 활용신청이 필요합니다. 특정 지역 "데이터 없음" 경고 → 행정구역 코드 개편 여부 확인(`tour.areas`).
   - *구글 검색* 실패 → 구글 화면 구조 변경 가능성. `collectors/google.py` 선택자(Export/Download CSV/카테고리 메뉴) 점검. RSS 대체는 자동으로 동작합니다.
   - *유튜브* "갱신 지연" → 429 로 직전 성공 데이터 사용 중. 정상 동작이며 잠시 후 자동 복구됩니다.
3. **사이트는 열리는데 최신 데이터가 아님:** Pages 배포 단계 실패 여부 확인. Settings → Pages → Source 가 *GitHub Actions* 인지 확인.
4. **cron 이 안 돌아감:** 저장소에 60일간 활동이 없으면 GitHub 이 예약 실행을 멈춥니다. Actions 탭에서 워크플로를 다시 활성화하거나 수동 실행하세요.
5. **키가 유출된 것 같을 때:** 즉시 각 서비스에서 키를 재발급하고 Secrets 를 교체한 뒤, 커밋 이력에 값이 남았는지 확인합니다.
6. **로컬에서 재현:** `python scripts/run_collector.py <naver|tour|google_trending|google_youtube>` 로 소스 단독 실행. 실제 응답 샘플은 `docs/samples/` 에 저장됩니다.

## 데이터 출처

- 네이버 데이터랩 쇼핑인사이트 (NAVER API HUB) — 여성 20·30·40대, 주간
- 한국관광공사 「지역별 관광 자원 수요」·「관광지별 연관 관광지 정보」 (공공데이터포털) — 월간
- 구글 트렌드 (공식 API 없음, 비공식 수집)
