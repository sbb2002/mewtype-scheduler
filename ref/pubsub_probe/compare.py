"""PubSub 알림(pubsub_probe.log) vs 배포판 폴링 감지(monitoring 브랜치 이벤트 로그) 비교표를 만든다.

    python -X utf8 compare.py [날짜 ...]      # 날짜 = 이벤트 파일 날짜(KST 06:00 경계), 기본 2026-10-13 ~ 2026-10-16

- PubSub 쪽: 같은 폴더 pubsub_probe.log 의 notify 줄. 본문(Atom)에서 videoId · published · updated 를 뽑는다.
- 폴링 쪽: gh 로 sbb2002/mewtype-scheduler-data 의 monitoring 브랜치 monitoring/events-<날짜>.jsonl 을 받아
  flow=preview 전이(from_state→to_state)를 영상별로 모은다. (gh 로그인 필요, 읽기 전용)
- 출력 시각은 전부 KST. 로컬 러너(_local) 이벤트가 아니라 **배포판** 이벤트다.
"""
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

KST = dt.timezone(dt.timedelta(hours=9))
LOG = Path(__file__).with_name("pubsub_probe.log")
REPO = "sbb2002/mewtype-scheduler-data"


def to_kst(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST)


def fmt(t):
    return t.strftime("%m-%d %H:%M:%S") if t else "-"


def read_notifies():
    out = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("kind") != "notify":
            continue
        b = d.get("body", "")
        g = lambda tag: (re.search(r"<%s>(.*?)</%s>" % (tag, tag), b, re.S) or [None, None])[1]
        vid = g("yt:videoId")
        titles = re.findall(r"<title>(.*?)</title>", b, re.S)
        out.append({
            "recv": dt.datetime.strptime(d["t"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST),  # 시험기 PC 시계 = KST
            "channel": d["channel"], "vid": vid, "title": titles[-1] if titles else "",
            "pub": to_kst(g("published")) if g("published") else None,
            "upd": to_kst(g("updated")) if g("updated") else None,
        })
    return out


def read_polling(dates):
    ev = []
    for day in dates:
        r = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw",
             f"repos/{REPO}/contents/monitoring/events-{day}.jsonl?ref=monitoring"],
            capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            print(f"(건너뜀: events-{day}.jsonl — {r.stderr.strip()[:80]})")
            continue
        for line in r.stdout.splitlines():
            line = line.strip()
            if line:
                try:
                    ev.append(json.loads(line))
                except ValueError:
                    pass
    return ev


def main():
    dates = sys.argv[1:] or ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]
    notes = read_notifies()
    poll = read_polling(dates)
    trans = {}  # video_id -> [(ts, who, from, to)]
    for e in poll:
        if e.get("flow") == "preview" and e.get("video_id"):
            trans.setdefault(e["video_id"], []).append(
                (to_kst(e["ts"]), e.get("who"), e.get("from_state"), e.get("to_state")))

    by_vid = {}
    for n in notes:
        by_vid.setdefault(n["vid"], []).append(n)

    print("## 영상별 신규 감지 (PubSub 첫 알림 vs 배포판 첫 등록)")
    print("채널 | 영상 | 게시 | PubSub 첫 알림 | 알림 지연 | 폴링 첫 등록 | 폴링 지연 | 첫 상태 | 제목")
    for vid, ns in sorted(by_vid.items(), key=lambda kv: kv[1][0]["recv"]):
        first = ns[0]
        tr = sorted(trans.get(vid, []))
        reg = tr[0] if tr else None
        d_push = (first["recv"] - first["pub"]).total_seconds() if first["pub"] else None
        d_poll = (reg[0] - first["pub"]).total_seconds() if reg and first["pub"] else None
        print(f"{first['channel']} | {vid} | {fmt(first['pub'])} | {fmt(first['recv'])} | "
              f"{'%.0f초' % d_push if d_push is not None else '-'} | {fmt(reg[0]) if reg else '(없음)'} | "
              f"{'%.0f초' % d_poll if d_poll is not None else '-'} | {reg[3] if reg else '-'} | {first['title'][:30]}")

    print("\n## 갱신 알림(두 번째 이후)과 배포판 상태 전이 — 시작/종료 신호 여부 확인용")
    print("영상 | 알림 수신 | 피드 updated | 가장 가까운 배포판 전이(시각, from→to, 알림 기준 차이)")
    for vid, ns in sorted(by_vid.items(), key=lambda kv: kv[1][0]["recv"]):
        tr = sorted(trans.get(vid, []))
        for n in ns[1:]:
            near = min(tr, key=lambda t: abs((t[0] - n["recv"]).total_seconds())) if tr else None
            diff = f"{(near[0] - n['recv']).total_seconds():+.0f}초" if near else "-"
            print(f"{n['channel']} {vid} | {fmt(n['recv'])} | {fmt(n['upd'])} | "
                  f"{fmt(near[0]) + ' ' + str(near[2]) + '→' + str(near[3]) + ' (' + diff + ')' if near else '(배포판 전이 없음)'}")

    print("\n## 종료(→end) 전이 중 PubSub 갱신 알림이 앞서 온 것 / 없던 것")
    for vid, tr in sorted(trans.items()):
        if vid not in by_vid:
            continue
        for t in sorted(tr):
            if t[3] == "end":
                before = [n for n in by_vid[vid][1:] if 0 <= (t[0] - n["recv"]).total_seconds() <= 600]
                print(f"{t[1]} {vid} end@{fmt(t[0])} — " +
                      (f"직전 10분 내 알림 {fmt(before[-1]['recv'])}" if before else "알림 없음"))

    print("\n## 푸시 없이 폴링만 잡은 영상(PubSub 누락 후보) — 배포판 등록 영상 중 알림이 없는 것")
    for vid, tr in sorted(trans.items(), key=lambda kv: min(t[0] for t in kv[1])):
        t0 = min(t[0] for t in tr)
        if notes and vid not in by_vid and any(t[2] is None for t in tr) and t0 >= notes[0]["recv"]:
            first = sorted(tr)[0]
            print(f"{first[1]} {vid} 등록@{fmt(first[0])} → {first[3]}")


if __name__ == "__main__":
    main()
