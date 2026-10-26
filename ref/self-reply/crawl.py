"""멤버 5명 프로필 글 목록을 fxtwitter v2 로 커서 따라 가능한 만큼 받아 저장."""
import json, sys, time, urllib.request, urllib.parse
from pathlib import Path

HANDLES = sys.argv[3].split(",") if len(sys.argv) > 3 else ["arale_yumemita", "yuno_yumemita", "nonoka_yumemita", "ritsu_yumemita", "miyako_yumemita"]
OUT = Path(sys.argv[1])
MAX_PAGES = int(sys.argv[2]) if len(sys.argv) > 2 else 60


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


res = {}
for h in HANDLES:
    seen, rows, cur = set(), [], None
    for p in range(MAX_PAGES):
        url = f"https://api.fxtwitter.com/2/profile/{h}/statuses"
        if cur:
            url += "?cursor=" + urllib.parse.quote(cur)
        try:
            j = get(url)
        except Exception as e:
            print(h, "page", p, "error", e, file=sys.stderr)
            break
        new = 0
        for r in j.get("results") or []:
            if r["id"] in seen:
                continue
            seen.add(r["id"]); new += 1
            rt = r.get("replying_to")
            rows.append({"id": r["id"], "ts": r.get("created_timestamp"), "text": r.get("text"),
                         "author": (r.get("author") or {}).get("screen_name"),
                         "repost": bool(r.get("reposted_by")),
                         "reply_to": rt.get("screen_name") if isinstance(rt, dict) else rt,
                         "reply_to_status": rt.get("status") if isinstance(rt, dict) else None})
        nxt = (j.get("cursor") or {}).get("bottom")
        oldest = min((x["ts"] for x in rows if not x["repost"] and x["ts"]), default=None)
        print(h, "page", p, "new", new, "total", len(rows), "oldest", time.strftime("%Y-%m-%d", time.gmtime(oldest)) if oldest else None, file=sys.stderr)
        if not new or not nxt or nxt == cur:
            break
        cur = nxt
        time.sleep(0.5)
    res[h] = rows
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
