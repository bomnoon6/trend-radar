"""네이버 데이터랩 쇼핑인사이트(NAVER API HUB) — 분야 내 키워드 트렌드 기반 순위(A-1).

공식 문서(api.ncloud-docs.com naver-api-hub-shopping-insight-keywords) 기준:
  POST https://naverapihub.apigw.ntruss.com/shopping/v1/category/keywords
  헤더 X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY
  body: startDate, endDate, timeUnit, category(분야코드 문자열), keyword[{name,param:[kw]}] (최대 5개), device, gender, ages
"""
from __future__ import annotations

import datetime as dt
import os

from . import base
from .base import Period, log, make_item

SOURCE_ID = "naver"
BASE_URL = "https://naverapihub.apigw.ntruss.com"
KEYWORDS_PATH = "/shopping/v1/category/keywords"
CATEGORIES_PATH = "/shopping/v1/categories"


def _headers() -> dict:
    cid, sec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not sec:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 없습니다")
    return {"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": sec, "Content-Type": "application/json"}


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


# ------------------------------------------------------------ 그룹 구성
def _season_groups(cat: dict, period: Period) -> list[dict]:
    """조회 기준일~기준일+lookahead 와 겹치는 시즌 창의 키워드를 분야(cid)별로 묶는다."""
    nv = cat["naver"]
    lo, hi = period.season_date, period.season_date + dt.timedelta(days=nv.get("lookahead_days", 30))
    by_cid: dict[str, list[str]] = {}
    for w in nv["season_windows"]:
        for year in (lo.year - 1, lo.year, hi.year):
            try:
                ws = dt.date(year, *map(int, w["start"].split("-")))
                we = dt.date(year, *map(int, w["end"].split("-")))
            except ValueError:
                continue
            if ws <= hi and we >= lo:
                for k in w["keywords"]:
                    name, cid = (k, w["cid"]) if isinstance(k, str) else (k["name"], k.get("cid", w["cid"]))
                    lst = by_cid.setdefault(cid, [])
                    if name not in lst:
                        lst.append(name)
                break
    return [{"name": f"시즌/{cid}", "cid": cid, "anchor": nv["anchor_by_cid"][cid], "group_weight": 1.0, "include_anchor": False, "seeds": kws}
            for cid, kws in by_cid.items()]


def groups_for(cat: dict, period: Period) -> list[dict]:
    nv = cat.get("naver")
    if not nv:
        return []
    return _season_groups(cat, period) if "season_windows" in nv else nv["groups"]


# ------------------------------------------------------------ 호출
def _fetch_chunk(http: base.Http, filters: dict, cid: str, names: list[str], start: dt.date, end: dt.date) -> dict:
    body = {
        "startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": filters["time_unit"],
        "category": cid,
        "keyword": [{"name": n, "param": [n]} for n in names],
        "gender": filters["gender"], "ages": filters["ages"],
    }
    if filters.get("device"):
        body["device"] = filters["device"]
    r = http.request("POST", BASE_URL + KEYWORDS_PATH, headers=_headers(), json=body)
    if r.status_code != 200:
        raise RuntimeError(f"네이버 키워드 트렌드 실패 HTTP {r.status_code}: {base.redact(r.text[:300])}")
    data = r.json()
    http.save_sample("keywords", {"path": KEYWORDS_PATH, "body": body}, data)
    return data


def _score_series(data: dict, anchor: str, weight: float):
    """앵커의 기간 평균을 100 으로 두고 모든 키워드의 주간 ratio 를 환산한다.
    반환: ({키워드: [(날짜, 점수)]}, 앵커 점수 시계열) — 앵커 시계열은 전체 시장 변동을 걷어낸 '상대 작년 대비' 계산에 쓴다."""
    series = {r["title"]: [(_d(p["period"]), float(p["ratio"])) for p in r["data"]] for r in data.get("results", [])}
    anc = [v for _, v in series.get(anchor, []) if v > 0]
    if not anc:
        return {}, []
    scale = sum(anc) / len(anc)
    scored = {k: [(d, v / scale * 100 * weight) for d, v in pts] for k, pts in series.items()}
    return scored, sorted(scored.get(anchor, []))


def _anchor_level(anchor_pts: list[tuple[dt.date, float]], day: dt.date) -> float | None:
    """해당 주 ±2주 앵커 평균(주간 잡음 완화)."""
    vals = [v for d, v in anchor_pts if abs((d - day).days) <= 14]
    return sum(vals) / len(vals) if vals else None


def _metrics(pts: list[tuple[dt.date, float]], period: Period, anchor_pts=None, min_score: float = 3.0) -> dict | None:
    pts = sorted(pts)
    idx = max((i for i, (d, _) in enumerate(pts) if d <= period.start + dt.timedelta(days=2)), default=None)
    if idx is None:
        return None
    d_now, now = pts[idx]
    prev = pts[idx - 1][1] if idx > 0 else None
    ly_pt = next(((d, v) for d, v in pts if abs((d - (d_now - dt.timedelta(days=364))).days) <= 3), None)
    ly = ly_pt[1] if ly_pt else None
    yoy = (now - ly) / ly * 100 if ly and ly >= min_score and now >= min_score else None
    yoy_abs = yoy
    if yoy is not None and anchor_pts:  # 같은 분야 앵커 대비 상대값으로 비교(시장 전체의 증감 제외)
        a_now, a_ly = _anchor_level(anchor_pts, d_now), _anchor_level(anchor_pts, ly_pt[0])
        if a_now and a_ly:
            yoy = ((now / a_now) / (ly / a_ly) - 1) * 100
    return {
        "score": now,
        "wow": (now - prev) / prev * 100 if prev and prev >= min_score and now >= min_score else None,
        "yoy": yoy, "yoy_abs": yoy_abs,
        "ly_score": ly,
        "series": [round(v, 1) for _, v in pts[max(0, idx - 7): idx + 1]],
        "week": d_now.isoformat(),
    }


def _extra_groups(cat: dict, period: Period, extras: list[tuple[str, str]]) -> list[dict]:
    """A-2 로 발견한 신규 키워드를 같은 분야의 앵커로 묶어 A-1 과 같은 방식으로 점수화한다."""
    base_groups = {g["cid"]: g for g in groups_for(cat, period)}
    by: dict[str, list[str]] = {}
    for kw, cid in extras:
        by.setdefault(cid, []).append(kw)
    return [{"name": f"신규발견/{cid}", "cid": cid, "anchor": base_groups[cid]["anchor"],
             "group_weight": base_groups[cid].get("group_weight", 1.0), "include_anchor": False,
             "discovered": True, "seeds": kws} for cid, kws in by.items() if cid in base_groups]


def collect(period: Period, category: str | None = None, *, config: dict | None = None,
            http: base.Http | None = None, extra_seeds: dict[str, list[tuple[str, str]]] | None = None) -> list[dict]:
    cfg = config or base.load_json("config/categories.json")
    nv = cfg["naver"]
    http = http or base.Http("naver", max_calls=int(os.environ.get("NAVER_MAX_CALLS", "1000")))
    per_call = nv["batch"]["new_per_call"]
    # 전년 동주 값까지 한 번의 호출로 얻기 위해 [시작-364일, 끝] 범위를 조회한다.
    start, end = period.start - dt.timedelta(days=364 + 7), period.end
    out: list[dict] = []
    for cat in cfg["categories"]:
        if category and cat["id"] != category:
            continue
        items: dict[str, dict] = {}
        for g in groups_for(cat, period) + _extra_groups(cat, period, (extra_seeds or {}).get(cat["id"], [])):
            seeds = [s for s in dict.fromkeys(g["seeds"]) if s != g["anchor"]]
            for i in range(0, len(seeds), per_call):
                chunk = seeds[i:i + per_call]
                names = [g["anchor"]] + chunk
                try:
                    data = _fetch_chunk(http, nv["common_filters"], g["cid"], names, start, end)
                except Exception as e:  # 한 묶음 실패가 전체를 멈추지 않게
                    log.warning("naver %s/%s %s 건너뜀: %s", cat["id"], g["name"], chunk, base.redact(str(e)))
                    continue
                scored, anchor_pts = _score_series(data, g["anchor"], g.get("group_weight", 1.0))
                first = names if (i == 0 and g.get("include_anchor", True)) else chunk
                for kw in first:
                    m = (_metrics(scored[kw], period, anchor_pts, nv.get("min_score_for_change", 3.0))
                         if kw in scored else None)
                    if m and kw not in items:
                        items[kw] = make_item(
                            kw, cat["id"], SOURCE_ID, "shopping_insight", m["score"], period.label,
                            change_wow=m["wow"], yoy=m["yoy"],
                            extra={"discovered": bool(g.get("discovered")), "series": m["series"], "cid": g["cid"], "group": g["name"], "week": m["week"],
                                   "ly_score": m["ly_score"], "yoy_abs": None if m["yoy_abs"] is None else round(m["yoy_abs"], 1)})
        ranked = base.assign_ranks(list(items.values()))
        ly = sorted((it for it in ranked if it["extra"].get("ly_score")), key=lambda x: -x["extra"]["ly_score"])
        for n, it in enumerate(ly, 1):
            it["extra"]["yoy_rank"] = n
            it["extra"]["yoy_top10"] = n <= 10
        out += ranked
    log.info("naver: 항목 %d개, API 호출 %d회", len(out), http.calls)
    return out


def verify_cids(config: dict | None = None, http: base.Http | None = None) -> list[dict]:
    """설정의 분야 코드가 실제로 응답하는지 확인한다(분야별 트렌드 API, 최근 4주)."""
    cfg = config or base.load_json("config/categories.json")
    http = http or base.Http("naver")
    seen: dict[str, str] = {}
    for cat in cfg["categories"]:
        for g in (cat.get("naver") or {}).get("groups", []):
            seen[g["cid"]] = g["name"]
        for w in (cat.get("naver") or {}).get("season_windows", []):
            seen.setdefault(w["cid"], "시즌 기본")
    today = dt.date.today()
    results = []
    for cid, name in seen.items():
        body = {"startDate": (today - dt.timedelta(days=35)).isoformat(), "endDate": (today - dt.timedelta(days=1)).isoformat(),
                "timeUnit": "week", "category": [{"name": name, "param": [cid]}], "gender": "f", "ages": ["20", "30", "40"]}
        try:
            r = http.request("POST", BASE_URL + CATEGORIES_PATH, headers=_headers(), json=body)
            ok = r.status_code == 200 and any(x.get("data") for x in r.json().get("results", []))
            results.append({"cid": cid, "name": name, "ok": ok, "status": r.status_code,
                            "detail": "" if ok else base.redact(r.text[:200])})
            http.save_sample("categories", {"path": CATEGORIES_PATH, "body": body}, r.json() if r.status_code == 200 else r.text[:300])
        except Exception as e:
            results.append({"cid": cid, "name": name, "ok": False, "status": None, "detail": base.redact(str(e))})
    return results
