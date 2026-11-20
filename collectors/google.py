"""구글 트렌드 — 공식 API 없음. 실패는 정상 상황으로 취급한다.

(a) Trending Now(검색): Playwright 로 CSV 내보내기 → 실패 시 DOM 표 → 실패 시 공식 RSS.
(b) YouTube 검색(보조): pytrends 의 gprop=youtube 급상승 검색어. 실패 시 직전 성공 캐시 + stale 표시.
화면 문구/셀렉터는 구글이 바꿀 수 있어, 각 단계가 독립적으로 try/except 되어 있다.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
import xml.etree.ElementTree as ET

from . import base
from .base import Period, log, make_item

SOURCE_ID = "google"
CACHE = base.ROOT / "data" / "_cache" / "youtube.json"


def parse_volume(text: str) -> float:
    """'2만+', '20K+', '1.5M+', '200+' → 숫자."""
    t = (text or "").replace(",", "").replace("+", "").strip()
    m = re.match(r"([\d.]+)\s*([KkMm만천]?)", t)
    if not m:
        return 0.0
    mult = {"": 1, "K": 1e3, "k": 1e3, "M": 1e6, "m": 1e6, "만": 1e4, "천": 1e3}[m.group(2)]
    return float(m.group(1)) * mult


def _cats_for_google(cfg: dict) -> dict[str, list[str]]:
    rev: dict[str, list[str]] = {}
    for c in cfg["categories"]:
        for g in c["google"]["trending_categories"]:
            rev.setdefault(g, []).append(c["id"])
    return rev


# ------------------------------------------------------------ (a) Trending Now
def _parse_csv(text: str) -> list[tuple[str, float, str]]:
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]
    ki = next((i for i, h in enumerate(head) if h in ("trends", "트렌드", "title", "검색어")), 0)
    vi = next((i for i, h in enumerate(head) if "volume" in h or "검색량" in h), None)
    si = next((i for i, h in enumerate(head) if "started" in h or "시작" in h), None)
    out = []
    for r in rows[1:]:
        if len(r) > ki and r[ki].strip():
            out.append((r[ki].strip(), parse_volume(r[vi]) if vi is not None and len(r) > vi else 0.0,
                        r[si] if si is not None and len(r) > si else ""))
    return out


def _export_csv(page) -> list[tuple[str, float, str]]:
    page.get_by_text("Export", exact=True).first.click(timeout=8000)
    with page.expect_download(timeout=20000) as dl:
        page.get_by_role("menuitem", name=re.compile(r"Download CSV", re.I)).first.click(timeout=8000)
    path = dl.value.path()
    return _parse_csv(open(path, encoding="utf-8-sig").read())


def _scrape_dom(page) -> list[tuple[str, float, str]]:
    out = []
    for row in page.locator("table tbody tr").all()[:50]:
        lines = [x.strip() for x in row.inner_text().split("\n") if x.strip()]
        if lines:
            vol = next((parse_volume(x) for x in lines[1:4] if re.match(r"^[\d.,]+\s*[KkMm만천]?\+?$", x)), 0.0)
            out.append((lines[0], vol, ""))
    return out


def fetch_trending_playwright(cfg: dict, wanted_categories: list[str], http: base.Http) -> dict[str | None, list]:
    """반환: {구글카테고리명 또는 None(전체): [(keyword, volume, started)]}"""
    from playwright.sync_api import sync_playwright

    t = cfg["google"]["trending"]
    url = f"https://trends.google.com/trending?geo={t['geo']}&hours={t['hours']}&sort={t['sort']}&hl=en"
    result: dict[str | None, list] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(locale="en-US", timezone_id="Asia/Seoul", accept_downloads=True)
            page = ctx.new_page()
            for cat in [None] + wanted_categories:
                http.calls += 1
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    if cat:
                        page.locator("[aria-label$='select category']").first.click(timeout=8000)
                        page.get_by_role("menuitemradio", name=re.compile(rf"^{re.escape(cat)}\b")).first.click(timeout=8000)
                        page.wait_for_timeout(2500)
                    try:
                        rows = _export_csv(page)
                    except Exception as e:
                        log.info("google: CSV 내보내기 실패(%s) → DOM 수집 시도: %s", cat, str(e)[:80])
                        rows = _scrape_dom(page)
                    if rows:
                        result[cat] = rows
                    else:
                        log.warning("google: '%s' 수집 결과 없음", cat)
                except Exception as e:
                    log.warning("google: '%s' 페이지 수집 실패: %s", cat, str(e)[:120])
                time.sleep(6)  # 요청 간격
        finally:
            browser.close()
    return result


def fetch_trending_rss(cfg: dict, http: base.Http) -> list[tuple[str, float, str]]:
    r = http.request("GET", cfg["google"]["trending"]["rss_fallback"])
    if r.status_code != 200:
        raise RuntimeError(f"RSS HTTP {r.status_code}")
    root = ET.fromstring(r.content)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        traffic = it.find("ht:approx_traffic", ns)
        if title:
            out.append((title, parse_volume(traffic.text if traffic is not None else ""), it.findtext("pubDate") or ""))
    return out


def collect_trending(period: Period, category: str | None = None, *, config: dict | None = None,
                     http: base.Http | None = None) -> list[dict]:
    cfg = config or base.load_json("config/categories.json")
    http = http or base.Http("google_trending", delay=1, max_calls=50)
    rev = _cats_for_google(cfg)
    wanted = sorted(rev)
    mode = "playwright"
    try:
        data = fetch_trending_playwright(cfg, wanted, http)
        if not data:
            raise RuntimeError("Playwright 결과 없음")
    except Exception as e:
        log.warning("google trending: Playwright 실패 → RSS 대체 (%s)", str(e)[:120])
        data, mode = {None: fetch_trending_rss(cfg, http)}, "rss"
    http.save_sample("trending_" + mode, {"mode": mode}, {str(k): v[:15] for k, v in data.items()})

    items: dict[tuple[str, str], dict] = {}

    def add(kw, cat_id, vol, started, via):
        key = (cat_id or "etc", re.sub(r"\s+", "", kw).lower())
        if key not in items or vol > (items[key]["score"] or 0):
            items[key] = make_item(kw, cat_id, SOURCE_ID, "trending_now", vol, "최근 7일" if mode == "playwright" else "최근 24시간",
                                   extra={"started": started, "via": via, "mode": mode})

    for gcat, rows in data.items():
        for kw, vol, started in rows:
            if gcat:  # 카테고리 필터에서 온 값
                ids = rev[gcat]
                cid = ids[0] if len(ids) == 1 else (base.match_category(kw, cfg, ids) or ids[0])
                add(kw, cid, vol, started, "filter")
            else:  # 전체 목록은 시드 키워드 매칭으로 분류
                add(kw, base.match_category(kw, cfg), vol, started, "seed")
    out = []
    for cid in {i["category"] for i in items.values()}:
        out += base.assign_ranks([i for i in items.values() if i["category"] == cid])
    log.info("google trending(%s): 항목 %d개", mode, len(out))
    return [i for i in out if not category or i["category"] == category]


# ------------------------------------------------------------ (b) YouTube
def collect_youtube(period: Period, category: str | None = None, *, config: dict | None = None,
                    http: base.Http | None = None) -> list[dict]:
    cfg = config or base.load_json("config/categories.json")
    y = cfg["google"]["youtube"]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    items: list[dict] = []
    try:
        from pytrends.request import TrendReq

        py = TrendReq(hl="ko-KR", tz=-540, timeout=(10, 30))
        fresh: dict[str, list] = {}
        for cat in cfg["categories"]:
            if category and cat["id"] != category:
                continue
            rising_all: dict[str, float] = {}
            for seed in cat["youtube_seeds"]:
                try:
                    py.build_payload([seed], geo=y["geo"], timeframe=y["timeframe"], gprop=y["gprop"])
                    rq = py.related_queries().get(seed, {}).get("rising")
                    if rq is not None:
                        for q, v in zip(rq["query"], rq["value"]):
                            rising_all[str(q)] = max(rising_all.get(str(q), 0), float(v))
                except Exception as e:
                    log.warning("youtube '%s' 실패: %s", seed, str(e)[:100])
                    if "429" in str(e):
                        raise
                time.sleep(y["request_interval_sec"])
            fresh[cat["id"]] = sorted(rising_all.items(), key=lambda kv: -kv[1])[:30]
        if not any(fresh.values()):
            raise RuntimeError("급상승 검색어를 하나도 얻지 못함")
        cache = {**cache, **{k: {"rows": v, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")} for k, v in fresh.items() if v}}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        stale = False
    except Exception as e:
        log.warning("youtube 수집 실패 → 직전 성공 데이터 사용: %s", str(e)[:150])
        stale = True
    for cid, v in cache.items():
        if category and cid != category:
            continue
        sub = [make_item(q, cid, SOURCE_ID, "youtube", s, "최근 7일", extra={"stale": stale, "fetched_at": v["fetched_at"]})
               for q, s in v["rows"]]
        items += base.assign_ranks(sub)
    return items
