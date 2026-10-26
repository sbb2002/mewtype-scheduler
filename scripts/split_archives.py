"""보관함 첫 이전(1회) — 데이터 저장소 체크아웃 폴더에서 캐시 보관함을 캐시 + 일자 보관함으로 나눈다 (핫픽스 archive-split, 2026-10-26).

보관함 정리(`archive_rotate`)는 한 번에 일자 파일 3개까지만 쓰므로, 이미 쌓인 분량(트윗 약 47일 · 소식 약 45일 · LLM 판단 약 22일)은
이 스크립트로 한 번에 나눈다 — Contents API 로 파일 120여 개를 하나씩 쓰면 GitHub 콘텐츠 생성 속도 제한에 걸리고 운영 쓰기와 다툰다.
나눈 결과를 git 으로 브랜치마다 커밋 1개로 민다(커밋 · push 는 이 스크립트가 하지 않는다).

나누는 기준은 `archive_rotate.plan` 과 같다(파일 수 상한만 없음). 이미 있는 일자 파일은 id 로 합친다(두 번 돌려도 같음).
끝에 전후 id 집합을 비교해 잃은 항목 · 중복이 없는지 확인하고, 하나라도 어긋나면 아무것도 쓰지 않고 멈춘다.

사용:
  python -m scripts.split_archives --data <data 브랜치 체크아웃> --ops <ops 브랜치 체크아웃> [--now 2026-10-27T00:00:00Z] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.backend import archive_rotate as ar
from src.backend.gh_store import _serialize


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def split(root: Path, target: ar.Target, now: datetime) -> dict:
    """한 대상을 메모리에서 나눠 {경로: 새 내용} 과 점검 결과를 돌려준다(쓰지 않음)."""
    cache = _load(root / target.cache)
    if cache is None:
        return {"name": target.name, "skipped": "no-cache", "writes": {}}
    items = list(cache.get(target.list_key) or [])
    keep, moves, over = ar.plan(items, target, now, max_files=10 ** 6)
    writes: dict[str, dict] = {}
    for day, its in sorted(moves.items()):
        path = ar.day_path(target.directory, day)
        cur = _load(root / path) or {}
        writes[path] = {target.list_key: ar.merge_day(list(cur.get(target.list_key) or []), its)}
    if target.index and moves:
        idx = _load(root / target.index)
        for day, its in sorted(moves.items()):
            idx = ar.merge_index(idx, its, day)
        writes[target.index] = idx
    new_cache = dict(cache)
    new_cache[target.list_key] = keep
    writes[target.cache] = new_cache

    # 점검 — 전: 캐시 + 기존 일자 파일 / 후: 새 캐시 + 새 일자 파일(+ 손대지 않은 기존 일자 파일)
    def ids_in(lst):
        return [ar._key(x) for x in lst]
    before = ids_in(items)
    after_cache = ids_in(keep)
    after_days = [k for p, d in writes.items() if p.startswith(target.directory + "/") and p != target.index
                  for k in ids_in(d.get(target.list_key) or [])]
    lost = set(before) - set(after_cache) - set(after_days)
    dup_cache_day = set(after_cache) & set(after_days)
    dup_in_days = len(after_days) - len(set(after_days))
    return {"name": target.name, "writes": writes, "before": len(before), "keep": len(keep),
            "moved": sum(len(v) for v in moves.values()), "days": len(moves), "over_limit": over,
            "cache_bytes": len(_serialize(new_cache).encode("utf-8")),
            "max_day_bytes": max((len(_serialize(d).encode("utf-8")) for p, d in writes.items()
                                  if p.startswith(target.directory + "/") and p != target.index), default=0),
            "lost": sorted(lost), "dup_cache_day": sorted(dup_cache_day), "dup_in_days": dup_in_days}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--ops", required=True, type=Path)
    ap.add_argument("--now", default=None, help="기준 시각(UTC ISO) — 생략하면 지금")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    now = ar._parse_iso(a.now) if a.now else datetime.now(timezone.utc)
    plans = [(a.data, split(a.data, ar.TWEETS, now)), (a.data, split(a.data, ar.NOTICES, now)), (a.ops, split(a.ops, ar.LLM, now))]
    ok = True
    for root, r in plans:
        if r.get("skipped"):
            print(f"[{r['name']}] 건너뜀 — {r['skipped']}")
            continue
        print(f"[{r['name']}] {r['before']}건 → 캐시 {r['keep']}건({r['cache_bytes']:,}B) + 일자 파일 {r['days']}개로 {r['moved']}건 "
              f"(가장 큰 일자 파일 {r['max_day_bytes']:,}B){' · 크기 상한 초과 남음' if r['over_limit'] else ''}")
        if r["lost"] or r["dup_cache_day"] or r["dup_in_days"]:
            ok = False
            print(f"  ✗ 잃은 항목 {len(r['lost'])} · 캐시와 일자 파일 양쪽 {len(r['dup_cache_day'])} · 일자 파일 안 중복 {r['dup_in_days']}")
        else:
            print("  ✓ 잃은 항목 0 · 중복 0")
    if not ok:
        print("점검 실패 — 아무것도 쓰지 않음")
        return 1
    if a.dry_run:
        print("dry-run — 쓰지 않음")
        return 0
    n = 0
    for root, r in plans:
        for path, data in (r.get("writes") or {}).items():
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_serialize(data), encoding="utf-8", newline="\n")
            n += 1
    print(f"파일 {n}개 씀 — 각 체크아웃에서 git add · commit · push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
