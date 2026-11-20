"""수집기 단독 실행/테스트.

  python scripts/run_collector.py naver --verify-cids      # 분야 코드 검증
  python scripts/run_collector.py naver --mode latest --category beauty
  python scripts/run_collector.py tour
  python scripts/run_collector.py google_trending
  python scripts/run_collector.py google_youtube --category travel

결과 요약은 콘솔에, 실제 응답 샘플(키 제거)은 docs/samples/ 에, 수집 결과는 docs/samples/out_<소스>_<모드>.json 에 저장한다.
"""
import argparse
import json
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from collectors import REGISTRY, base, naver  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(REGISTRY))
    ap.add_argument("--mode", choices=["latest", "lastyear"], default="latest")
    ap.add_argument("--category")
    ap.add_argument("--verify-cids", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    base.load_env()
    samples = base.ROOT / "docs" / "samples"
    cfg = base.load_json("config/categories.json")

    if a.verify_cids:
        http = base.Http("naver", sample_dir=samples)
        for r in naver.verify_cids(cfg, http):
            print(("OK  " if r["ok"] else "FAIL"), r["cid"], r["name"], r["status"], r["detail"])
        return 0

    period = base.build_period(a.mode)
    print(f"기준 기간: {period.label} (관광 기준월 {period.tour_ym}, 모드 {a.mode})")
    http = base.Http(a.source, sample_dir=samples)
    items = REGISTRY[a.source](period, a.category, config=cfg, http=http)
    out = samples / f"out_{a.source}_{a.mode}.json"
    out.write_text(base.redact(json.dumps({"schema_version": base.SCHEMA_VERSION, "period": period.to_dict(), "items": items},
                                          ensure_ascii=False, indent=1)), encoding="utf-8")
    print(f"항목 {len(items)}개 / API 호출 {http.calls}회 → {out.relative_to(base.ROOT)}")
    cats = sorted({i["category"] or "etc" for i in items})
    for c in cats:
        print(f"\n[{c}]")
        for i in [x for x in items if (x["category"] or "etc") == c][: a.top]:
            print(f"  {i['rank']:>2}. {i['keyword']}  score={i['score']} wow={i['change_wow']} yoy={i['yoy']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
