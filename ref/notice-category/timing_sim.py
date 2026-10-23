"""코드 시점 판정 초안 점검 — 실제 소식 129건(정답표 데이터)에 적용해 「지난 일」 로 버려지는 글을 본다. Groq 안 씀.

초안 규칙: 글에 적힌 날짜(월/일 · 本日 · 明日 …) 중 판정 시각(KST) 기준 오늘 이후가 하나라도 있으면 「앞으로」,
모두 오늘이면 「오늘」, 모두 지났으면 「지난 일」. 범위(A〜B)는 끝 날짜, 「まで」 는 그 날짜.
"""
import json, re, sys, os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, sys.argv[1])          # 메인 저장소 루트(src.backend.xnotice 를 그대로 쓴다)
from src.backend import xnotice as xn

JST = timezone(timedelta(hours=9))
REL = {"本日": 0, "今日": 0, "今夜": 0, "今晩": 0, "明日": 1, "あす": 1, "明後日": 2}


def posted_kst(tid):
    return datetime.fromtimestamp(((int(tid) >> 22) + 1288834974657) / 1000, JST)


def mentions(text, now):
    t = xn.normalize(text)
    out = []
    for m in xn._DATE_RE.finditer(t):
        try:
            mo, da = int(m.group("m")), int(m.group("d"))
            y = int(m.group("y")) if m.group("y") else xn._infer_year(mo, da, now)
            out.append((datetime(y, mo, da).date(), m.group(0)))
        except (ValueError, TypeError):
            pass
    for w, k in REL.items():
        if w in t:
            out.append(((now + timedelta(days=k)).date(), w))
    return out


def judge(text, now):
    ms = mentions(text, now)
    if not ms:
        return "날짜 없음", ms
    today = now.date()
    if any(d > today for d, _ in ms):
        return "앞으로", ms
    if any(d == today for d, _ in ms):
        return "오늘", ms
    return "지난 일", ms


data = sys.argv[2]
items = json.load(open(os.path.join(data, "labeler_items.json"), encoding="utf-8"))
labels = {}
for f in ("labels_2026-10-23.json", "holdout_labels_2026-10-23.json"):
    p = os.path.join(data, f)
    if os.path.exists(p):
        for k, v in json.load(open(p, encoding="utf-8")).items():
            labels[k] = v.get("cats") or ([v["cat"]] if v.get("cat") else [])
from collections import Counter
cnt = Counter()
rows = []
for it in items:
    tid = it["id"] if it["id"].isdigit() else None
    if not tid:
        continue
    now = posted_kst(tid)
    v, ms = judge((it.get("title") or "") + "\n" + (it.get("body") or ""), now)
    cnt[v] += 1
    if v in ("지난 일", "날짜 없음"):
        rows.append((it["n"], v, now.strftime("%m-%d %H:%M"), [f"{d.isoformat()}({s})" for d, s in ms][:4], labels.get(it["id"]), (it.get("title_ko") or "")[:34]))
print("판정 분포(게시 시각 기준):", dict(cnt))
for r in rows:
    print(r)
