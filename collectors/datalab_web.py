"""(A-2, 옵션) 네이버 데이터랩 웹 '쇼핑인사이트 > 분야별 인기검색어' 순위 — 비공식 경로.

  POST https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver  (웹 화면이 쓰는 내부 요청)

공식 API 가 아니므로 언제든 바뀔 수 있다. 켜는 방법: 환경변수 USE_DATALAB_WEB_RANK=true.
build_data.py 가 이 수집기를 격리해서 호출하며, 실패해도 파이프라인은 멈추지 않는다.
여기서는 순위 목록만 가져오고, '신규 발견' 판정과 점수 계산은 build_data/naver 가 맡는다.
"""
from __future__ import annotations

from . import base
from .base import Period, log, make_item

SOURCE_ID = "naver"
URL = "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://datalab.naver.com/shoppingInsight/sCategory.naver",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}


def web_groups(cat: dict) -> list[dict]:
    """이 카테고리에서 인기검색어를 가져올 (cid, 그룹) 목록. 시즌처럼 web_rank=false 인 곳은 제외."""
    nv = cat.get("naver") or {}
    if nv.get("web_rank") is False:
        return []
    return [g for g in nv.get("groups", []) if g.get("web_rank", True)]


def fetch_rank(http: base.Http, cid: str, period: Period, filters: dict, top_n: int) -> list[tuple[int, str]]:
    form = {"cid": cid, "timeUnit": filters["time_unit"], "startDate": period.start.isoformat(), "endDate": period.end.isoformat(),
            "age": ",".join(filters["ages"]), "gender": filters["gender"], "device": filters.get("device", ""),
            "page": "1", "count": str(top_n)}
    r = http.request("POST", URL, data=form, headers=HEADERS)
    if r.status_code != 200:
        raise RuntimeError(f"데이터랩 웹 HTTP {r.status_code}")
    data = r.json()  # content-type 이 text/html 로 오므로 본문을 직접 파싱
    if data.get("returnCode") not in (0, "0", None) or "ranks" not in data:
        raise RuntimeError(f"데이터랩 웹 응답 이상: {str(data)[:150]}")
    http.save_sample(f"rank_{cid}", {"url": URL, "form": form}, data)
    return [(int(x["rank"]), str(x["keyword"]).strip()) for x in data["ranks"] if x.get("keyword")]


def collect(period: Period, category: str | None = None, *, config: dict | None = None,
            http: base.Http | None = None) -> list[dict]:
    cfg = config or base.load_json("config/categories.json")
    nv = cfg["naver"]
    wr = nv.get("web_rank", {})
    http = http or base.Http("naver_web", delay=wr.get("request_interval_sec", 3), max_calls=60, retries=2)
    top_n = wr.get("top_n", 20)
    by_cid: dict[str, list[dict]] = {}
    sharing: dict[str, list[str]] = {}  # 같은 분야 코드를 쓰는 모든 카테고리(배정 후보)
    for cat in cfg["categories"]:
        for g in (cat.get("naver") or {}).get("groups", []):
            sharing.setdefault(g["cid"], []).append(cat["id"])
        if category and cat["id"] != category:
            continue
        for g in web_groups(cat):
            by_cid.setdefault(g["cid"], []).append({"cat": cat, "group": g})
    items: list[dict] = []
    for cid, owners in by_cid.items():
        try:
            ranks = fetch_rank(http, cid, period, nv["common_filters"], top_n)
        except Exception as e:  # 분야 하나가 실패해도 계속
            log.warning("naver_web cid=%s 실패: %s", cid, str(e)[:150])
            continue
        for rank, kw in ranks:
            cat_id = owners[0]["cat"]["id"]
            if len(sharing[cid]) > 1:  # 같은 분야 코드를 공유하는 카테고리는 시드 일치로 배정, 없으면 소유 카테고리
                cat_id = base.match_category(kw, cfg, sharing[cid]) or cat_id
            items.append(make_item(kw, cat_id, SOURCE_ID, "datalab_web_rank", top_n + 1 - rank, period.label, rank=rank,
                                   extra={"cid": cid, "group": owners[0]["group"]["name"], "web_rank": rank}))
    log.info("naver_web: 인기검색어 %d개, 요청 %d회", len(items), http.calls)
    return items
