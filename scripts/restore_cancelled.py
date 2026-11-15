"""(v4.11.14) 이미 내려간 취소 예고를 「취소됨」으로 되살리는 일회성 스크립트 — 소급 적용용.

LLM 판단 기록(ops `llm_actions.json`)의 방송 취소 항목(undo.restore_items 스냅샷)을 data `preview.json` 에
`cancelled` 를 붙여 다시 넣는다. 취소 글 = 그 판단의 인입 태그(`…#1tweet-<id>`), 주소는 data `tweets.json` 에서.
그날 끝(KST 04:00)이 이미 지났으면 넣지 않는다(수집이 바로 아카이브할 항목이라).

반드시 v4.11.14 프론트 · 백엔드 배포 **뒤에** 돌린다 — 옛 프론트는 `cancelled` 를 몰라 일반 예고로 보여 주고,
옛 백엔드는 자리표시 TTL(expires_at)로 지운다.

사용: python scripts/restore_cancelled.py <llm 판단 id> [--apply]
  (기본 = 미리보기만, --apply 면 data 브랜치에 커밋). gh CLI 로그인(데이터 저장소 쓰기 권한) 필요.
예:   python scripts/restore_cancelled.py llm_b1fff50dcb --apply     # 2026-11-15 아라레 22:00 휴방
"""
import base64
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])
from src.backend import preview  # noqa: E402

REPO = "sbb2002/mewtype-scheduler-data"


def _get(path: str, ref: str) -> tuple[dict, str]:
    out = subprocess.run(["gh", "api", f"repos/{REPO}/contents/{path}?ref={ref}"], capture_output=True, text=True, encoding="utf-8", check=True)
    meta = json.loads(out.stdout)
    return json.loads(base64.b64decode(meta["content"]).decode("utf-8")), meta["sha"]


def _ser(obj: dict) -> str:   # gh_store._serialize 와 같은 규칙
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    aid, apply = sys.argv[1], "--apply" in sys.argv
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    acts, _ = _get("llm_actions.json", "ops")
    act = next((a for a in acts.get("items", []) if a.get("id") == aid), None)
    if not act or act.get("kind") != "broadcast_change" or (act.get("undo") or {}).get("type") != "restore_items":
        sys.exit(f"방송 취소 판단 기록이 아닙니다: {aid}")
    if act.get("undone"):
        sys.exit("이미 반려된 판단입니다 — 되살리지 않습니다")
    m = re.search(r"tweet-(\d{5,25})", ((act.get("input") or {}).get("tag")) or "")
    tid = m.group(1) if m else None
    ck = act.get("who")
    turl = None
    if tid:
        tw, _ = _get("tweets.json", "data")
        hit = next((t for t in (tw.get("tweets") or {}).get(ck, []) if str(t.get("id")) == tid), None)
        turl = (hit or {}).get("url") or f"https://x.com/i/status/{tid}"
    pv, sha = _get("preview.json", "data")
    items = pv.get("items", [])
    out = []
    for snap in act["undo"].get("items") or []:
        if any(i.get("id") == snap.get("id") for i in items):
            print(f"건너뜀 {snap.get('id')} — 이미 예고에 있음")
            continue
        it = dict(snap, cancelled={"at": act.get("ts") or now, "by": "tweet", "tweet_id": tid, "tweet_url": turl},
                  last_updated=now)
        if preview.cancel_expired(it, now):
            print(f"건너뜀 {snap.get('id')} — 그날 끝({preview.cancel_until(it)})이 지남")
            continue
        out.append(it)
        print(f"되살림 {it['id']} {ck} {it.get('scheduled_start')} · 취소 글 {tid} · 남김 ~{preview.cancel_until(it)}")
    if not out:
        return
    if not apply:
        print("(미리보기 — 커밋하려면 --apply)")
        return
    new = dict(pv, items=preview.sort_items(items + out), generated_at=now)
    body = base64.b64encode(_ser(new).encode("utf-8")).decode("ascii")
    req = json.dumps({"message": f"data: 취소 예고 소급 표시 {aid} {now}", "content": body, "sha": sha, "branch": "data"})
    subprocess.run(["gh", "api", "-X", "PUT", f"repos/{REPO}/contents/preview.json", "--input", "-"],
                   input=req, text=True, encoding="utf-8", check=True, capture_output=True)
    print("커밋 완료")


if __name__ == "__main__":
    main()
