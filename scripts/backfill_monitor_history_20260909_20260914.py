"""일회성 백필 스크립트 — 2026-09-16 세션, `/monitor`(monitor_log.py) 도입 이전 기간의
tweet/notice/preview 실이력을 이미 존재하는 저장소 데이터(*_archive.json, 활성 tweets.json/
notices.json/preview.json)에서 재구성해 `monitoring/events-YYYY-MM-DD.jsonl`에 채운다.

**옛 push_monitor_history.json(파일별 커밋 집계, devpapers 브랜치)은 이관 대상이 아니다** —
그건 "몇 번 커밋됐는지"만 있고 개별 이벤트의 시각·성공여부·detail이 없어서 이벤트 로그로
재현할 근거가 없다(추측하면 가짜 이벤트가 된다). 반면 *_archive.json류는 각 항목이 실제
타임스탬프(received_at/first_seen/actual_start/state_since)와 실제 결과(text_ko/title_ko
유무)를 갖고 있어 "그때 그 tweet/notice/preview 항목이 실제로 있었다"는 사실 자체는
재구성 가능 — 단, 옛 push_monitor 가 세던 "파일 커밋 횟수"와는 다른 걸 세는 것이므로
숫자가 정확히 일치하지는 않는다(정상 — 한 항목이 여러 번 커밋돼도 여기선 1개 사건으로 침).

재구성 규칙(전부 실제 기록된 필드에서만 가져옴 — 중간 상태 추측 없음):
  - tweet: ts=received_at, result=ok(text_ko 있음)/degraded(없음), via="ingest"(추정 — 옛
    데이터엔 via 구분이 없었음, 압도적 다수가 자동 인입이라 근사)
  - notice: ts=first_seen(없으면 archived_at), result=ok(title_ko 있음)/degraded(없음)
  - preview: 항목당 최대 2개 지점만 — actual_start(실제 방송 시작, 있으면) / preview_archive
    항목의 state_since(최종 관측 상태). 중간 전이는 근거가 없어 만들지 않는다.
  - 오늘(today bucket) 이후는 제외 — 이미 monitor_log.py 가 실시간으로 기록 중이라 중복 방지.
  - 모든 백필 이벤트는 `backfill: true` + `src_id`(원본 항목 id)를 달아 원본 로그와 구분·감사
    가능하게 한다.

실행:
  GH_TOKEN=<data 저장소 쓰기 가능한 GITHUB_TOKEN> python scripts/backfill_monitor_history_20260909_20260914.py [--apply]
  (--apply 없으면 dry-run — 날짜별 집계만 출력, 아무것도 쓰지 않음)

멱등성: 이미 같은 src_id의 backfill 이벤트가 있는 날짜 파일은 건너뛴다(재실행 안전).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

from src.backend.gh_store import GitHubStore
from src.backend.monitor_log import RESULT_DEGRADED, RESULT_OK, bucket_date_kst

DATA_REPO = "sbb2002/mewtype-scheduler-data"


def build_events(gh: GitHubStore, today_bucket: str) -> dict[str, list[dict]]:
    tweet_archive, _ = gh.read_json("tweet_archive.json")
    tweets, _ = gh.read_json("tweets.json")
    notice_archive, _ = gh.read_json("notice_archive.json")
    notices, _ = gh.read_json("notices.json")
    preview_archive, _ = gh.read_json("preview_archive.json")
    preview, _ = gh.read_json("preview.json")

    events_by_date: dict[str, list[dict]] = {}

    def add(ts: str | None, flow: str, **fields):
        if not ts:
            return
        b = bucket_date_kst(ts)
        if b >= today_bucket:
            return
        row = {"ts": ts, "flow": flow, "backfill": True, **fields}
        events_by_date.setdefault(b, []).append(row)

    for t in (tweet_archive or {}).get("tweets", []):
        add(t.get("received_at"), "tweet", who=t.get("channel_key", ""),
            result=RESULT_OK if t.get("text_ko") else RESULT_DEGRADED,
            detail="[백필] mode: backfill(tweet_archive)", via="ingest", src_id=t.get("id"))
    for ch, items in (tweets or {}).get("tweets", {}).items():
        for t in items:
            add(t.get("received_at"), "tweet", who=t.get("channel_key", ch),
                result=RESULT_OK if t.get("text_ko") else RESULT_DEGRADED,
                detail="[백필] mode: backfill(tweets.json)", via="ingest", src_id=t.get("id"))

    for n in (notice_archive or {}).get("notices", []):
        add(n.get("first_seen") or n.get("archived_at"), "notice", who="",
            result=RESULT_OK if n.get("title_ko") else RESULT_DEGRADED,
            detail="[백필] " + (n.get("title") or n.get("category") or ""), src_id=n.get("id"))
    for n in (notices or {}).get("notices", []):
        add(n.get("first_seen") or n.get("archived_at"), "notice", who="",
            result=RESULT_OK if n.get("title_ko") else RESULT_DEGRADED,
            detail="[백필] " + (n.get("title") or n.get("category") or ""), src_id=n.get("id"))

    for src_key, doc in (("preview_archive", preview_archive), ("preview", preview)):
        for p in (doc or {}).get("items", []):
            ck, title, pid = p.get("channel_key", ""), p.get("title"), p.get("id")
            if p.get("actual_start"):
                add(p["actual_start"], "preview", who=ck, result=RESULT_OK, to_state="live",
                    title=title, detail="[백필] 실제 방송 시작(actual_start)", src_id=pid)
            if src_key == "preview_archive" and p.get("state_since"):
                add(p["state_since"], "preview", who=ck, result=RESULT_OK, to_state=p.get("state"),
                    title=title, detail="[백필] preview_archive 최종 상태", src_id=pid)

    for evs in events_by_date.values():
        evs.sort(key=lambda e: e["ts"])
    return events_by_date


def main() -> None:
    apply = "--apply" in sys.argv
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        print("GH_TOKEN 환경변수 필요 (data 저장소 쓰기 가능한 GITHUB_TOKEN)", file=sys.stderr)
        sys.exit(1)

    gh = GitHubStore(token, DATA_REPO, "data")
    today_bucket = bucket_date_kst(datetime.now(timezone.utc))
    events_by_date = build_events(gh, today_bucket)

    for date_kst in sorted(events_by_date):
        new_events = events_by_date[date_kst]
        path = f"monitoring/events-{date_kst}.jsonl"
        text, sha = gh.read_text(path)
        existing_src_ids = set()
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("backfill") and row.get("src_id"):
                existing_src_ids.add(row["src_id"])

        to_add = [e for e in new_events if e.get("src_id") not in existing_src_ids]
        by_flow: dict[str, int] = {}
        for e in to_add:
            by_flow[e["flow"]] = by_flow.get(e["flow"], 0) + 1
        skipped = len(new_events) - len(to_add)
        print(f"{date_kst}: {by_flow} (총 {len(to_add)}건 추가"
              + (f", {skipped}건은 이미 있어 건너뜀" if skipped else "") + ")")

        if not apply or not to_add:
            continue

        lines = [json.dumps(e, ensure_ascii=False, sort_keys=True) for e in to_add]
        new_text = (text or "") + "\n".join(lines) + "\n"
        gh.write_text(
            path, new_text, prev_sha=sha,
            message=f"data: monitor 백필 {date_kst} (push_monitor 폐지 이전 tweet/notice/preview 실이력 재구성)",
        )
        print(f"  → 커밋 완료: {path}")

    if not apply:
        print("\n(dry-run — 실제로 쓰려면 --apply 추가)")


if __name__ == "__main__":
    main()
