"""수집기 실행 → 병합 → data/latest.json, lastyear.json, status.json, archive 스냅샷 생성.

  python scripts/build_data.py                 # 전체 수집(운영/Actions)
  python scripts/build_data.py --from-samples  # docs/samples/out_*.json 으로 합성(프론트 로컬 미리보기용, 아카이브 미기록)
  python scripts/build_data.py --skip google_youtube   # 느린 소스 제외

한 소스가 실패해도 나머지는 정상 발행하고, 실패 내역은 status.json 에 남긴다.
"""
import argparse
import datetime as dt
import gzip
import json
import logging
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from collectors import REGISTRY, base  # noqa: E402

DATA = base.ROOT / "data"
SAMPLES = base.ROOT / "docs" / "samples"
KEEP_PER_LIST = 50
KST = dt.timezone(dt.timedelta(hours=9))
SOURCE_ORDER = ["naver", "tour", "google_trending", "google_youtube"]
MODE_SOURCES = {"latest": SOURCE_ORDER, "lastyear": ["naver", "tour"]}  # 구글은 아카이브에서 가져온다
SOURCE_LABEL = {"naver": "네이버 데이터랩", "tour": "한국관광공사", "google_trending": "구글 트렌드(검색)", "google_youtube": "구글 트렌드(유튜브)"}


def now_kst() -> dt.datetime:
    return dt.datetime.now(KST)


# ------------------------------------------------------------ 보조
def norm(kw: str, cfg: dict) -> str:
    s = re.sub(r"\s+", "", kw.split("/")[0]).lower()
    if len(s) > 2 and s[-1] in cfg["cross_trend"]["normalize"]["strip_particles"]:
        s = s[:-1]
    return s


def write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def read_json(path: pathlib.Path):
    if path.suffix == ".gz":
        return json.loads(gzip.open(path, "rt", encoding="utf-8").read())
    return json.loads(path.read_text(encoding="utf-8"))


def trim(items: list[dict]) -> list[dict]:
    out, seen = [], {}
    for it in sorted(items, key=lambda i: i["rank"] or 9999):
        k = (it["source"], it["sub_source"], it["category"])
        seen[k] = seen.get(k, 0) + 1
        if seen[k] <= KEEP_PER_LIST:
            out.append(it)
    return out


def compute_cross(items: list[dict], cfg: dict) -> list[dict]:
    groups: dict[str, dict] = {}
    for it in items:
        if it["sub_source"] == "area_demand":  # 지역명은 교차 대상에서 제외
            continue
        g = groups.setdefault(norm(it["keyword"], cfg), {"sources": set(), "names": [], "cats": set()})
        g["sources"].add(it["source"])
        g["names"].append(it["keyword"])
        if it["category"]:
            g["cats"].add(it["category"])
    need = cfg["cross_trend"]["min_sources"]
    cross = []
    for key, g in groups.items():
        if len(g["sources"]) >= need:
            cross.append({"key": key, "keyword": g["names"][0], "sources": sorted(g["sources"]), "categories": sorted(g["cats"])})
    keys = {c["key"]: c for c in cross}
    for it in items:
        c = keys.get(norm(it["keyword"], cfg)) if it["sub_source"] != "area_demand" else None
        it["cross_count"] = len(c["sources"]) if c else 1
    cross.sort(key=lambda c: (-len(c["sources"]), c["keyword"]))
    return cross


def apply_rank_change(items: list[dict], prev_path: pathlib.Path, cfg: dict) -> None:
    if not prev_path.exists():
        return
    prev = {}
    for p in read_json(prev_path).get("items", []):
        prev[(p["source"], p["sub_source"], p["category"], norm(p["keyword"], cfg))] = p["rank"]
    for it in items:
        r = prev.get((it["source"], it["sub_source"], it["category"], norm(it["keyword"], cfg)))
        it["rank_change"] = "NEW" if r is None else r - it["rank"]


def archive_files() -> list[tuple[dt.datetime, pathlib.Path]]:
    out = []
    for p in (DATA / "archive").glob("*/*.json*"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})", p.name)
        if m:
            out.append((dt.datetime.fromisoformat(m.group(1)), p))
    return sorted(out)


def google_from_archive(ref: dt.date, today: dt.date) -> tuple[list[dict], dict]:
    files = archive_files()
    cand = [(abs((d.date() - ref).days), d, p) for d, p in files if abs((d.date() - ref).days) <= 7]
    if cand:
        _, d, p = min(cand, key=lambda x: x[0])
        items = [i for i in read_json(p)["items"] if i["source"] == "google"]
        for i in items:
            i["period"] = f"스냅샷 {d.date()}"
            i["extra"]["archived"] = True
        return items, {"ok": True, "snapshot": d.date().isoformat()}
    first = files[0][0].date() if files else today
    avail = first + dt.timedelta(days=345)
    return [], {"ok": False, "message": f"아카이브 축적 중 — {avail.isoformat()}부터 제공", "available_from": avail.isoformat()}


def compress_old_archives() -> None:
    cur = now_kst().strftime("%Y-%m")
    for p in (DATA / "archive").glob("*/*.json"):
        if p.parent.name != cur:
            with open(p, "rb") as f, gzip.open(str(p) + ".gz", "wb") as g:
                g.write(f.read())
            p.unlink()


# ------------------------------------------------------------ 수집
def collect_mode(mode: str, cfg: dict, skip: set, from_samples: bool, status: dict) -> list[dict]:
    period = base.build_period(mode)
    items: list[dict] = []
    for src in MODE_SOURCES[mode]:
        if src in skip:
            continue
        st = status.setdefault(src, {"label": SOURCE_LABEL[src]})
        t0 = time.time()
        try:
            if from_samples:
                got = json.loads((SAMPLES / f"out_{src}_{mode}.json").read_text(encoding="utf-8"))["items"]
                calls = None
            else:
                http = base.Http(src)
                got = REGISTRY[src](period, None, config=cfg, http=http)
                calls = http.calls
            stale = any(i["extra"].get("stale") for i in got)
            ok = bool(got)
            st[mode] = {"ok": ok, "count": len(got), "calls": calls, "stale": stale,
                        "seconds": round(time.time() - t0, 1), "error": None if ok else "수집 결과 없음"}
            items += got
        except Exception as e:  # 소스 격리
            logging.exception("%s(%s) 실패", src, mode)
            st[mode] = {"ok": False, "count": 0, "stale": False, "error": base.redact(str(e))[:300]}
    return items


def finalize(items: list[dict], cfg: dict, period: base.Period, prev_path: pathlib.Path | None) -> dict:
    items = trim(items)
    if prev_path:
        apply_rank_change(items, prev_path, cfg)
    cross = compute_cross(items, cfg)
    cats = [{"id": c["id"], "label": c["label"]} for c in sorted(cfg["categories"], key=lambda c: c["order"])]
    return {"schema_version": base.SCHEMA_VERSION, "generated_at": now_kst().isoformat(timespec="seconds"),
            "mode": period.mode, "period": period.to_dict(), "categories": cats, "cross": cross, "notices": {}, "items": items}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-samples", action="store_true")
    ap.add_argument("--skip", nargs="*", default=[])
    ap.add_argument("--archive", action="store_true", help="샘플 모드에서도 아카이브 기록")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    base.load_env()
    cfg = base.load_json("config/categories.json")
    skip = set(a.skip)
    status: dict = {}
    today = now_kst().date()

    # 최신
    p_latest = base.build_period("latest")
    items = collect_mode("latest", cfg, skip, a.from_samples, status)
    latest = finalize(items, cfg, p_latest, DATA / "latest.json")
    # 작년 기준
    p_ly = base.build_period("lastyear")
    ly_items = collect_mode("lastyear", cfg, skip, a.from_samples, status)
    g_items, g_note = google_from_archive(p_ly.ref_date, today)
    lastyear = finalize(ly_items + g_items, cfg, p_ly, None)
    lastyear["notices"]["google"] = g_note
    status["google_archive"] = {"label": "구글 작년 비교(아카이브)", **g_note}

    write_json(DATA / "latest.json", latest)
    write_json(DATA / "lastyear.json", lastyear)
    write_json(DATA / "status.json", {"schema_version": base.SCHEMA_VERSION, "generated_at": latest["generated_at"], "sources": status})
    if not a.from_samples or a.archive:
        ts = now_kst()
        write_json(DATA / "archive" / ts.strftime("%Y-%m") / ts.strftime("%Y-%m-%d_%H.json"), latest)
        compress_old_archives()
    sizes = {n: (DATA / n).stat().st_size // 1024 for n in ("latest.json", "lastyear.json", "status.json")}
    print("완료:", sizes, "KB / 교차 트렌드", len(latest["cross"]), "개")
    for s, v in status.items():
        print(" ", s, {k: x for k, x in v.items() if k in ("latest", "lastyear", "ok", "message")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
