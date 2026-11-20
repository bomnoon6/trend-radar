"""한국관광공사(공공데이터포털): (a) 지역별 관광 자원 수요 → 뜨는 지역, (b) 관광지별 연관 관광지 → 여행/맛집 순위.

(a) 베이스 URL·파라미터는 data.go.kr 상세 페이지(15152138)로 확인했으나, 오퍼레이션 경로명과 응답 필드명은 문서에 없어
(b) 는 서비스/오퍼레이션 이름 자체가 미확인이라, config/categories.json 의 *_candidates 를 순서대로 시도한다.
응답 필드는 후보 키 + 숫자 필드 자동 탐지로 읽으며, 실제 응답은 docs/samples 에 저장되어 3단계 전에 확정한다.
"""
from __future__ import annotations

import re

from . import base
from .base import Period, log, make_item

SOURCE_ID = "tourapi"
HOST = "https://apis.data.go.kr/B551011"
_SKIP_NUM = re.compile(r"(Cd|Nm|Ym|No|Rank|Seq|Num|Rows|Page|Count)$", re.I)


def _rows(data) -> list[dict]:
    try:
        items = data["response"]["body"]["items"]
    except (KeyError, TypeError):
        return []
    if not items:
        return []
    item = items.get("item") if isinstance(items, dict) else items
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def _call(http: base.Http, service: str, op: str, params: dict, key: str) -> dict | None:
    """성공 시 JSON, 오퍼레이션 없음(400/404 등)이면 None, 인증/쿼터 문제는 예외."""
    p = {"serviceKey": key, "MobileOS": "ETC", "MobileApp": "trend-radar", "_type": "json", **params}
    r = http.request("GET", f"{HOST}/{service}/{op}", params=p)
    text = r.text.strip()
    if r.status_code in (400, 404) or text.startswith("<"):
        if "SERVICE_KEY" in text or "SERVICE KEY" in text.upper() or "LIMITED" in text:
            raise RuntimeError(f"관광공사 인증/한도 오류: {base.redact(text[:200])}")
        log.info("tour: %s/%s -> HTTP %s (후보 불일치 가능): %s", service, op, r.status_code, base.redact(text[:120]))
        return None
    if r.status_code != 200:
        raise RuntimeError(f"관광공사 HTTP {r.status_code}: {base.redact(text[:200])}")
    data = r.json()
    code = (data.get("response", {}).get("header", {}) or {}).get("resultCode") or data.get("resultCode")
    if code in ("11", "10") and "mandatory" in str(data).lower():
        raise RuntimeError(f"관광공사 필수 파라미터 누락: {data.get('resultMsg')}")
    if code not in (None, "0000", "00"):
        raise RuntimeError(f"관광공사 resultCode={code}: {base.redact(str(data)[:200])}")
    return data


def _try_candidates(http, services, ops, params, key, tag):
    for s in services:
        for o in ops:
            data = _call(http, s, o, params, key)
            if data is not None:
                log.info("tour: 사용 가능한 조합 확인 %s/%s", s, o)
                http.save_sample(tag, {"path": f"/{s}/{o}", "params": {k: v for k, v in params.items()}}, data)
                return s, o, data
    return None


def _row_value(row: dict, keys: list[str]) -> float | None:
    for k in keys:
        if k in row:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                pass
    vals = []
    for k, v in row.items():
        if _SKIP_NUM.search(k):
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            pass
    return sum(vals) / len(vals) if vals else None


def area_demand(http: base.Http, cfg: dict, period: Period, key: str) -> tuple[list[dict], str]:
    t = cfg["tour"]
    ad = t["area_demand"]
    ym0 = period.tour_ym
    for back in range(0, 3):  # 최신 월 데이터가 없으면 직전 월로 대체
        ym = base.shift_month(ym0, -back)
        agg: dict[str, list[float]] = {}
        sigungu: dict[str, list[dict]] = {}
        op_used = None
        for area in t["areas"]:
            # 행정구역 개편(예: 2026-07 광주+전남 → 전남광주 코드 12)을 기준월로 구분
            if ym < area.get("from", "000000") or ym > area.get("until", "999999"):
                continue
            params = {"baseYm": ym, "areaCd": area["code"], "numOfRows": 100, "pageNo": 1,
                      ad["indicator_param"]: ad["indicator_value"]}
            if op_used:
                data = _call(http, ad["service"], op_used, params, key)
            else:
                found = _try_candidates(http, [ad["service"]], ad["operation_candidates"], params, key, "area_demand")
                data = found[2] if found else None
                op_used = found[1] if found else None
            rows = _rows(data) if data else []
            vals, sg = [], []
            for r in rows:
                v = _row_value(r, ad["value_key_candidates"])
                if v is not None:
                    vals.append(v)
                    sg.append({"code": r.get("signguCd"), "name": r.get("signguNm"), "value": v})
            if vals:
                agg[area["name"]] = vals
                sigungu[area["name"]] = sorted(sg, key=lambda x: -x["value"])
            else:
                log.warning("tour: %s(%s) %s 데이터 없음", area["name"], area["code"], ym)
            if not op_used:
                raise RuntimeError("지역별 관광 자원 수요: 오퍼레이션 후보가 모두 실패 — 활용가이드로 operation_candidates 확인 필요")
        if agg:
            items = [make_item(n, "travel", SOURCE_ID, "area_demand", sum(v) / len(v), f"{ym[:4]}-{ym[4:]} (월간)",
                               extra={"ym": ym, "fallback_month": back > 0, "rows": len(v), "sigungu": sigungu[n][:10], "area_code": next(a["code"] for a in t["areas"] if a["name"] == n)})
                     for n, v in agg.items()]
            return base.assign_ranks(items), ym
    return [], ym0


def related(http: base.Http, cfg: dict, period: Period, key: str, areas: list[dict], ym: str) -> list[dict]:
    rl = cfg["tour"]["related"]
    class_keys = rl["class_keys"]
    scores: dict[tuple[str, str], dict] = {}
    found = None
    per_area = cfg["tour"].get("related_sigungu_per_area", 3)
    targets = [(a, s) for a in areas for s in a["extra"].get("sigungu", [])[:per_area] if s.get("code")]
    for area, sg in targets:  # 연관 관광지 API 는 signguCd 가 필수 → 수요 상위 시군구 단위로 호출
        params = {"baseYm": ym, "areaCd": area["extra"]["area_code"], "signguCd": sg["code"],
                  "numOfRows": cfg["tour"]["related_per_area"], "pageNo": 1}
        if found is None:
            res = _try_candidates(http, rl["service_candidates"], rl["operation_candidates"], params, key, "related")
            if not res:
                raise RuntimeError("연관 관광지: 서비스/오퍼레이션 후보가 모두 실패 — 활용가이드 확인 필요")
            found, data = (res[0], res[1]), res[2]
        else:
            data = _call(http, found[0], found[1], params, key)
        for idx, row in enumerate(_rows(data) if data else [], 1):
            name = (row.get(rl["name_key"]) or "").strip()
            if not name:
                continue
            klass = " ".join(str(row.get(k, "")) for k in class_keys)
            if any(x in klass for x in rl["exclude_keywords"]):
                continue
            role = "food" if any(x in klass for x in rl["food_keywords"]) else "travel"
            try:
                rank = int(row.get(rl["rank_key"]) or idx)
            except ValueError:
                rank = idx
            e = scores.setdefault((role, name), {"score": 0.0, "n": 0, "area": area["keyword"], "class": klass.strip()})
            e["score"] += max(1, 101 - rank)  # 순위가 높을수록, 여러 번 등장할수록 가산
            e["n"] += 1
    items = []
    role_to_cat = cfg["tour"]["role_to_category"]
    for (role, name), e in scores.items():
        items.append(make_item(name, role_to_cat[role], SOURCE_ID, "related_places", e["score"], f"{ym[:4]}-{ym[4:]} (월간)",
                               extra={"appearances": e["n"], "area": e["area"], "class": e["class"], "ym": ym}))
    out = []
    for cat in set(i["category"] for i in items):
        out += base.assign_ranks([i for i in items if i["category"] == cat])
    return out


def collect(period: Period, category: str | None = None, *, config: dict | None = None,
            http: base.Http | None = None) -> list[dict]:
    cfg = config or base.load_json("config/categories.json")
    http = http or base.Http("tour", delay=0.5, max_calls=3000)
    key = base.data_go_kr_key()
    demand, ym = area_demand(http, cfg, period, key)
    top = demand[: cfg["tour"]["area_demand_top_n"]]
    rel = related(http, cfg, period, key, top, ym) if top else []
    items = demand + rel
    log.info("tour: 지역 %d, 연관 %d, API 호출 %d회 (기준월 %s)", len(demand), len(rel), http.calls, ym)
    return [i for i in items if not category or i["category"] == category]
