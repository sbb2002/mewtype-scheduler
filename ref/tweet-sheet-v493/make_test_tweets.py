# 로컬 사본 tweets.json 에 시험 글을 덧붙인다(운영 데이터는 건드리지 않음).
# 실제 X 글을 fxtwitter 로 받아 계약 I 모양으로 만든다 — 여러 미디어 경우 · 인용 · 자기 답글을 실제 X 카드와 맞대 보려고.
import json, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

DATA = sys.argv[1]
CK = "yuno"
IDS = [
    ("2115087399558726136", "[시험] 영상 1개"),
    ("2115111482816082307", "[시험] 영상 3개 + 사진 1장"),
    ("2115093368921641205", "[시험] 사진 4장"),
    ("2113196648180637922", "[시험] 인용 글 사진 3장"),
    ("2114348675963232311", "[시험] 사진 1장 + 인용 글 사진 2장"),
    ("2115087886269948174", "[시험] 세로 사진 1장"),
]

def fx(i):
    req = urllib.request.Request(f"https://api.fxtwitter.com/status/{i}", headers={"User-Agent": "mewtype-local-check"})
    return json.load(urllib.request.urlopen(req, timeout=15))["tweet"]

def media(t):
    out = []
    for x in ((t or {}).get("media") or {}).get("all") or []:
        u = x.get("thumbnail_url") if x.get("type") in ("video", "gif") else x.get("url")
        if u: out.append(u)
    return out

p = f"{DATA}/tweets.json"
d = json.load(open(p, encoding="utf-8"))
now = datetime.now(timezone.utc)
rows = []
for k, (i, label) in enumerate(IDS):
    t = fx(i)
    q = t.get("quote")
    posted = now - timedelta(minutes=50 - k * 7)
    iso = posted.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows.append({
        "channel_key": CK, "id": i, "handle": "yuno_yumemita",
        "text": t.get("text") or "", "text_ko": label + " — 번역 시험 글입니다. 실제 X 카드와 칸 위치를 맞대 봅니다.",
        "media": media(t),
        "quote": ({"text": q.get("text") or "", "text_ko": "[시험] 인용한 글 번역", "media": media(q)} if q else None),
        "posted_at": iso, "received_at": iso,
        "expires_at": (now + timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": t.get("url") or f"https://x.com/i/status/{i}",
    })
    time.sleep(0.3)
# 자기 답글 하나(실제 X 의 자기 답글 글 — 「님에게 보내는 답글」 줄 확인)
t = fx("2115032626037948855")
base = rows[-1]
iso = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
rows.append({"channel_key": CK, "id": "2115032626037948855", "handle": "yuno_yumemita", "text": t.get("text") or "",
             "text_ko": "[시험] 자기 답글 — 「이어서」 줄", "media": media(t), "quote": None, "posted_at": iso, "received_at": iso,
             "expires_at": (now + timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%SZ"), "url": t.get("url"), "reply_to_id": base["id"]})
lst = d["tweets"].setdefault(CK, [])
known = {str(m.get("id")) for m in lst}
lst.extend(r for r in rows if r["id"] not in known)
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
for r in rows: print(r["id"], len(r["media"]), "quote" if r["quote"] else "", (r["quote"] or {}).get("media") and len(r["quote"]["media"]))
