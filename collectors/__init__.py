"""수집기 레지스트리. 새 소스는 모듈 하나를 만들고 아래에 등록하면 된다.
공통 인터페이스: collect(period, category=None, *, config=None, http=None) -> list[Item]
"""
from . import google, naver, tour

REGISTRY = {
    "naver": naver.collect,
    "tour": tour.collect,
    "google_trending": google.collect_trending,
    "google_youtube": google.collect_youtube,
}
