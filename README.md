# trend-radar

SNS 콘텐츠 기획용 트렌드 대시보드. 네이버 데이터랩(쇼핑인사이트)·한국관광공사·구글 트렌드의 공개 데이터를
GitHub Actions 로 하루 2회 수집해 `data/*.json` 으로 저장하고, 순수 HTML/CSS/JS 정적 사이트(GitHub Pages)로 보여줍니다.

> 작성 중 — 단계별로 채워집니다. (현재: 1단계 뼈대)

## 구조

```
config/categories.json   카테고리·소스 매핑·시드 키워드 (코드 수정 없이 편집)
config/templates.json    글 기획 메모 규칙·배지 기준·해시태그·검색 링크
collectors/              소스별 수집기 (공통 인터페이스 collect(period, category))
scripts/                 수집 실행·병합·아카이브 스크립트
data/                    latest.json / lastyear.json / status.json / archive/
docs/samples/            실제 API 응답 샘플(키 제거)
assets/, index.html      프론트엔드 (빌드 도구 없음)
.github/workflows/       수집(cron) · Pages 배포
```

## 로컬 설정

1. `.env.example` 을 `.env` 로 복사하고 키를 채웁니다. (`.env` 는 커밋되지 않습니다)
2. `pip install -r requirements.txt`

## TODO (이후 단계에서 작성)

- 사이트 URL / 갱신 시각
- 소스별 제약(주간/월간, 한도, 실패 시 동작)
- 시드 키워드 수정 방법
- A-2 옵션(`USE_DATALAB_WEB_RANK`) 켜는 법
- 장애 시 체크리스트
