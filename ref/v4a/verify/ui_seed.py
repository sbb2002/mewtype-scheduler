"""관리 페이지 UI 시험용 시드 — harness 의 가짜 외부 서비스로 반려 전 판단 기록 몇 건을 만들고 데이터 폴더를 남긴다(수동 실행 전용, git 제외 아님 — 결과는 run/)."""
import sys
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_c as c
h = c.h
BJ = c.BJ
c.BJ["fn"] = lambda: {"action": "none", "banner_ref": None, "event": None, "gacha": None, "image_for": "none", "image_roles": [], "reason": "행사 정보 없음"}
h.ingest_x("新イベント開催決定！", "バンドリ！アワーノーツ", tag=f"p#x#1tweet-{c.TP}701")
ss = h.rnd(c.REAL_NOW + timedelta(hours=6))
h.video("VUI00000001", "miyako", "upcoming", c.z(ss), title="【歌枠】みやこ")
h.RSS.clear(); h.RSS["miyako"] = ["VUI00000001"]
h.reconcile(at=c.REAL_NOW); h.RSS.clear()
c.CHANGE["fn"] = lambda raw, cands: {"action": "del", "target_ids": [x["id"] for x in cands], "when": None, "reason": "취소 공지"}
h.ingest_x("本日の配信はお休みです🙏", "藤都子", tag=f"p#x#1tweet-{c.TP}711")
c.OWN["ret"] = False
dd = (c.REAL_NOW + timedelta(days=2)).astimezone(c.KST)
h.ingest_x(f"{dd.month}/{dd.day} 21:00〜 配信します！", "仲町あられ", tag=f"p#x#1tweet-{c.TP}721")
h.idle()
h.q_apply.stop(); h.q_enrich.stop()
print([ (e["kind"], e["summary"][:30]) for e in c.entries()])
