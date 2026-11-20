"""공통 유틸: 환경변수, 기간 계산, HTTP(재시도·호출수 집계·키 마스킹), 항목 형식, 샘플 저장."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import unquote

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
SECRET_ENVS = ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "DATA_GO_KR_KEY", "TOUR_RLTE_KEY"]
log = logging.getLogger("trend")


# ---------------------------------------------------------------- env / config
def load_env() -> None:
    """.env 가 있으면 읽는다(로컬 테스트용). Actions 에서는 Secrets 가 환경변수로 이미 들어온다."""
    path = ROOT / ".env"
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(path)
    except ImportError:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_json(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def secret_values() -> list[str]:
    return [v for k in SECRET_ENVS if (v := os.environ.get(k, "")) and len(v) >= 4]


def redact(text: str) -> str:
    for s in secret_values():
        for variant in {s, unquote(s)}:
            text = text.replace(variant, "***")
    return text


def data_go_kr_key(primary: str = "DATA_GO_KR_KEY", override: str | None = "TOUR_RLTE_KEY") -> str:
    """requests 가 params 를 한 번 인코딩하므로, Encoding 키(%포함)가 들어오면 디코딩해서 넘긴다(이중 인코딩 방지)."""
    key = (os.environ.get(override or "", "") or os.environ.get(primary, "")).strip()
    if not key:
        raise RuntimeError("DATA_GO_KR_KEY(또는 TOUR_RLTE_KEY) 환경변수가 없습니다")
    return unquote(key) if "%" in key else key


# ---------------------------------------------------------------- periods
@dataclass
class Period:
    mode: str  # latest | lastyear
    start: dt.date  # 주 시작(월)
    end: dt.date  # 주 끝(일)
    ref_date: dt.date  # 기준 날짜(lastyear 는 오늘-345일)
    tour_ym: str  # 관광 데이터 기준 월 YYYYMM
    season_date: dt.date  # 시즌 키워드 창 판정 기준일

    @property
    def label(self) -> str:
        return f"{self.start.isoformat()} ~ {self.end.isoformat()}"

    def to_dict(self) -> dict:
        return {
            "mode": self.mode, "start": self.start.isoformat(), "end": self.end.isoformat(),
            "ref_date": self.ref_date.isoformat(), "tour_ym": self.tour_ym,
            "season_date": self.season_date.isoformat(),
        }


def _prev_month(d: dt.date) -> dt.date:
    return (d.replace(day=1) - dt.timedelta(days=1)).replace(day=1)


def build_period(mode: str, today: dt.date | None = None) -> Period:
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    if mode == "latest":
        monday = today - dt.timedelta(days=today.weekday())
        start = monday - dt.timedelta(days=7)
        return Period("latest", start, start + dt.timedelta(days=6), today,
                      _prev_month(today).strftime("%Y%m"), today)
    if mode == "lastyear":
        ref = today - dt.timedelta(days=345)
        start = ref - dt.timedelta(days=ref.weekday())
        return Period("lastyear", start, start + dt.timedelta(days=6), ref,
                      ref.strftime("%Y%m"), today + dt.timedelta(days=20))
    raise ValueError(mode)


def shift_month(ym: str, delta: int) -> str:
    y, m = int(ym[:4]), int(ym[4:])
    t = y * 12 + (m - 1) + delta
    return f"{t // 12:04d}{t % 12 + 1:02d}"


# ---------------------------------------------------------------- items
def make_item(keyword: str, category: str | None, source: str, sub_source: str, score: float | None,
              period: str, *, rank: int | None = None, change_wow=None, yoy=None, extra: dict | None = None) -> dict:
    return {
        "rank": rank, "keyword": keyword, "category": category, "source": source, "sub_source": sub_source,
        "score": None if score is None else round(float(score), 2),
        "change_wow": None if change_wow is None else round(float(change_wow), 1),
        "yoy": None if yoy is None else round(float(yoy), 1),
        "rank_change": None, "cross_count": 1, "period": period, "extra": extra or {},
    }


def assign_ranks(items: list[dict]) -> list[dict]:
    items.sort(key=lambda i: (i["score"] is None, -(i["score"] or 0)))
    for n, it in enumerate(items, 1):
        it["rank"] = n
    return items


def match_category(keyword: str, cfg: dict, only: list[str] | None = None) -> str | None:
    """시드 키워드 부분일치로 카테고리 추정(구글 RSS/트렌딩 분류용)."""
    kw = re.sub(r"\s+", "", keyword).lower()
    for cat in cfg["categories"]:
        if only and cat["id"] not in only:
            continue
        pool = list(cat.get("youtube_seeds", []))
        for g in cat["naver"].get("groups", []) if cat.get("naver") else []:
            pool += g["seeds"]
        for w in (cat.get("naver") or {}).get("season_windows", []):
            pool += [k if isinstance(k, str) else k["name"] for k in w["keywords"]]
        for s in pool:
            s = re.sub(r"\s+", "", s).lower()
            if len(s) >= 2 and (s in kw or (len(kw) >= 2 and kw in s)):
                return cat["id"]
    return None


# ---------------------------------------------------------------- HTTP
class QuotaExceeded(RuntimeError):
    pass


class Http:
    """재시도(지수 백오프)·호출 간 지연·호출수 집계·로그 마스킹을 담당하는 얇은 래퍼."""

    def __init__(self, name: str, *, delay: float = 0.3, max_calls: int = 1000, retries: int = 4, sample_dir=None):
        self.name, self.delay, self.max_calls, self.retries = name, delay, max_calls, retries
        self.calls = 0
        self.sample_dir = pathlib.Path(sample_dir) if sample_dir else None
        self._sampled: set[str] = set()
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "trend-radar/1.0"

    def request(self, method: str, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", 30)
        last = None
        for attempt in range(self.retries + 1):
            if self.calls >= self.max_calls:
                raise QuotaExceeded(f"{self.name}: 호출 상한 {self.max_calls} 도달")
            time.sleep(self.delay)
            self.calls += 1
            try:
                r = self.s.request(method, url, **kw)
            except requests.RequestException as e:
                last = redact(str(e))
                log.warning("%s 네트워크 오류(%d/%d): %s", self.name, attempt + 1, self.retries + 1, last)
            else:
                log.info("%s #%d %s %s -> %s", self.name, self.calls, method, url.split("?")[0], r.status_code)
                if r.status_code == 429 and attempt >= 1:
                    raise QuotaExceeded(f"{self.name}: 429 호출 한도 초과")
                if r.status_code < 500 and r.status_code != 429:
                    return r
                last = f"HTTP {r.status_code}"
            time.sleep(min(60, (2 ** attempt) * 2 + random.random()))
        raise RuntimeError(f"{self.name}: 재시도 소진 ({last})")

    def save_sample(self, tag: str, request_info, response_obj) -> None:
        """실제 응답 샘플을 docs/samples 에 저장(키 값은 제거). 태그당 1회."""
        if not self.sample_dir or tag in self._sampled:
            return
        self._sampled.add(tag)
        self.sample_dir.mkdir(parents=True, exist_ok=True)
        text = redact(json.dumps({"request": request_info, "response": response_obj}, ensure_ascii=False, indent=2))
        (self.sample_dir / f"{self.name}_{tag}.json").write_text(text, encoding="utf-8")
