"""행사 배너 시나리오 검증 (2026-10-02) — 실제 판정 LLM(Groq) + 백엔드 `banners` + 프론트 `banners.js`(node)를 시각을 옮겨 가며 돌린다.

두 시나리오(가상 행사 「星降るステージ Rush」, 날짜는 모두 가상 — 실데이터와 무관):
  A. 정상 — 예고 → 당일 재공지 · 개최 글 → 진행 → D-3 노랑 → 행사 종료 뒤 빨강 → 모두 종료(자정까지 회색) → 내림
  B. 보류 → 3일 뒤 시작 — 예고 → 개최 연기 공지(보류) → 새 일정 공지(3일 뒤 시작, 시작 · 종료 갱신) → 개최 글 → 진행 → … → 내림

각 단계에서 확인: 판정(action) · 반영 mode · 저장된 날짜 · 백엔드 derive 상태 == 프론트 상태 · 화면 텍스트(날짜 줄 · 종료 박스 · 말풍선 · 칩).
외부 호출: Groq 텍스트 LLM 만(비전 OCR 은 이미지가 없어 쓰지 않음). `.env.local` 의 GROQ_API_KEY 필요.

    python ref/v4a/verify/banner_scenarios.py        # 저장소 루트에서. 결과: ref/v4a/verify/results_banner.json (git 제외)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.backend import banners  # noqa: E402
from src.backend.llm import LLMClient  # noqa: E402
from src.backend.local_runner import load_env_file  # noqa: E402

load_env_file(ROOT / ".env.local")
KST = timezone(timedelta(hours=9))
RES: list[dict] = []
FRONT: list[dict] = []
FAILS: list[str] = []


def kst(s: str) -> str:
    """'2026-10-25 18:00' (KST) → UTC ISO."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=KST).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(cond: bool, msg: str) -> None:
    RES.append({"ok": bool(cond), "msg": msg})
    print(("  [OK]   " if cond else "  [FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)


# ── 가상 글(일본어) ─────────────────────────────────────────────────────────
NAME = "星降るステージ Rush"
GACHA = "ワタシが主役のスターライトガチャ"
HEAD = "#アワーノーツ\n"


def t_announce(es, ee, ge):
    return (f"{HEAD}【新イベント開催決定】\n{es}よりチャレンジライブイベント「{NAME}」が開催決定🎧\n開催期間：{es}〜{ee}\n"
            f"夢限大みゅーたいぷの宮永ののかがイベント報酬メンバーとして登場✨\n\nイベントガチャ「{GACHA}」も同時開催！\nガチャ開催期間：{es}〜{ge}\n\n#バンドリ #アワーノーツ")


T_REMIND = f"本日18:00より開催✨\nチャレンジライブイベント「{NAME}」\n夢限大みゅーたいぷの新曲もプレイ可能！ぜひ遊んでくださいね🛸\n{HEAD}"
T_OPEN = lambda ee: f"チャレンジライブイベント「{NAME}」開催中🎧\n\n本イベントは{ee}まで✨\n{HEAD}"
T_HOLD = (f"【初のイベント「{NAME}」および関連ガチャの開催延期について】\n不具合対応のため、10月25日(日)18:00開始予定だったイベント「{NAME}」と"
          f"ガチャ「{GACHA}」の開催を延期いたします。開催日程は決定次第あらためてお知らせします。\n{HEAD}")
T_RESCHEDULE = (f"【イベント開催決定のお知らせ】\nチャレンジライブイベント「{NAME}」の開催日程が決定しました。\n開催期間：10月28日(水)18:00〜11月5日(木)20:59\n"
                f"ガチャ「{GACHA}」開催期間：10月28日(水)18:00〜11月6日(金)11:59\n{HEAD}")


class Sim:
    """시각을 옮기며 글을 넣고 판정 · 반영 · 상태를 기록한다."""

    def __init__(self, llm: LLMClient):
        self.llm, self.prev, self.n = llm, banners.default_banners(), 0
        self.points: list[dict] = []

    def post(self, text: str, when_kst: str, expect_action: str | None = None):
        now = kst(when_kst)
        posted_jst = when_kst
        j = self.llm.banner_judge(text, posted_jst, banners.for_llm(self.prev, now))
        print(f"  · 글 {when_kst} → 판정 {None if j is None else j['action']} | {None if j is None else j['reason'][:70]}")
        check(j is not None, f"{when_kst} 글 — 판정 LLM 응답")
        if j is None:
            return None, None
        if expect_action:
            check(j["action"] == expect_action, f"{when_kst} 글 — 판정 action={expect_action} (실제 {j['action']})")
        self.n += 1
        r = banners.apply_judgement(self.prev, j, {"tweet_id": f"sim{self.n}", "media": []}, now)
        print(f"    반영 mode={r['mode']} detail={r['detail'][:60]}")
        if r["mode"] in ("added", "updated", "held", "cancelled"):
            self.prev = r["banners"]
        return j, r

    def at(self, label: str, when_kst: str):
        now = kst(when_kst)
        b = self.prev["banners"][0] if self.prev.get("banners") else None
        self.points.append({"label": label, "now_iso": now, "banner": b})


def front(points):
    inp = HERE / "run" / "banner_in.json"
    out = HERE / "run" / "banner_out.json"
    inp.parent.mkdir(exist_ok=True)
    inp.write_text(json.dumps({"points": [p for p in points if p["banner"]]}, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["node", str(HERE / "banner_front.mjs"), str(inp), str(out)], check=True)
    return json.loads(out.read_text(encoding="utf-8"))


BACK2FRONT = {"announced": {"sched"}, "live": {"live", "warn", "urgent"}, "done": {"done"}, "hold": {"hold"}, "gone": {"gone"}, "pending": {"pending"}}


def verify_points(sim: Sim, expect: dict[str, dict]):
    fr = front(sim.points)
    FRONT.extend(fr)
    by = {f["label"]: f for f in fr}
    for p in sim.points:
        lab = p["label"]
        e = expect.get(lab)
        if p["banner"] is None:
            check(False, f"[{lab}] 배너가 없음")
            continue
        bst, why = banners.derive(p["banner"], p["now_iso"])
        f = by[lab]
        check(f["st"] in BACK2FRONT.get(bst, set()), f"[{lab}] 백엔드 derive={bst} ↔ 프론트={f['st']} 일치")
        print(f"      [{lab}] {bst}/{f['st']} visible={f['visible']} pct={f['pct']} bubble={f['bubble']!r} chip={f['chip']!r}\n"
              f"             날짜줄={f['dates']!r}\n             종료박스={f['ends']}")
        if e:
            if "st" in e:
                check(f["st"] == e["st"], f"[{lab}] 프론트 상태 {e['st']} (실제 {f['st']})")
            if "visible" in e:
                check(f["visible"] == e["visible"], f"[{lab}] 화면 노출 {e['visible']} (실제 {f['visible']})")
            if "bubble" in e:
                check(f["bubble"] == e["bubble"], f"[{lab}] 말풍선 {e['bubble']!r} (실제 {f['bubble']!r})")
            if "chip" in e:
                check(f["chip"] == e["chip"], f"[{lab}] 칩 {e['chip']!r} (실제 {f['chip']!r})")
            for s in e.get("dates_has", []):
                check(s in f["dates"], f"[{lab}] 날짜 줄에 {s!r} 포함 (실제 {f['dates']!r})")
            for s in e.get("ends_has", []):
                check(any(s in x for x in f["ends"]), f"[{lab}] 종료 박스에 {s!r} 포함 (실제 {f['ends']})")
            if e.get("ends_none"):
                check(not f["ends"], f"[{lab}] 보류 중에는 종료 박스를 숨김 (실제 {f['ends']})")
            if "over" in e:                                  # is-over(취소선 · 종료됨) 클래스가 붙은 박스 수
                n = sum(1 for x in f["ends"] if "is-over" in x)
                check(n == e["over"], f"[{lab}] 종료됨 표시 박스 {e['over']}개 (실제 {n}) {f['ends']}")
            if "hot" in e:
                n = sum(1 for x in f["ends"] if "is-hot" in x)
                check(n == e["hot"], f"[{lab}] 강조(is-hot) 박스 {e['hot']}개 (실제 {n})")
    return fr


def scenario_a(llm):
    print("\n══ 시나리오 A — 정상 인입 → 종료 ══")
    s = Sim(llm)
    j, r = s.post(t_announce("10月25日(日)18:00", "11月2日(月)20:59", "11月3日(火)11:59"), "2026-10-20 12:00", "upsert")
    check(r and r["mode"] == "added" and r["shown"], "A1 예고 글 → 새 행사로 올라감(shown)")
    b = s.prev["banners"][0] if s.prev["banners"] else {}
    check(b.get("start_at") == kst("2026-10-25 18:00") and b.get("end_at") == kst("2026-11-02 20:59"), "A1 저장된 행사 기간 = 10.25 18:00 ~ 11.02 20:59")
    check(len(b.get("gachas", [])) == 1 and b["gachas"][0].get("end_at") == kst("2026-11-03 11:59"), "A1 딸린 가챠 1건, 가챠 종료 = 11.03 11:59")
    check(bool(b.get("name_ko")) and b.get("name_ja", "").find("星降る") >= 0, f"A1 이름 ko/ja 저장 (ko={b.get('name_ko')!r})")
    s.at("A 공지 직후 10.20 12:00", "2026-10-20 12:00")
    s.at("A 개최 전날 10.24 12:00", "2026-10-24 12:00")
    j, r = s.post(T_REMIND, "2026-10-25 01:00", None)
    check(r and r["mode"] in ("none", "dup") or (r and r["mode"] == "updated" and s.prev["banners"][0]["start_at"] == kst("2026-10-25 18:00")),
          "A2 당일 재공지 → 새 행사로 안 늘고 일정이 안 바뀜")
    s.at("A 개최 30분 전 10.25 17:30", "2026-10-25 17:30")
    j, r = s.post(T_OPEN("11月2日(月)20:59"), "2026-10-25 18:20", None)
    check(len(s.prev["banners"]) == 1, "A3 개최 글 뒤에도 행사는 1건")
    check(s.prev["banners"][0]["end_at"] == kst("2026-11-02 20:59") and s.prev["banners"][0]["start_at"] == kst("2026-10-25 18:00"), "A3 일정이 그대로(시작 10.25 18:00, 종료 11.02 20:59)")
    s.at("A 진행 10.26 12:00 (D-7)", "2026-10-26 12:00")
    s.at("A D-4 10.29 12:00", "2026-10-29 12:00")
    s.at("A D-3 10.30 00:30", "2026-10-30 00:30")
    s.at("A D-3 10.30 12:00", "2026-10-30 12:00")
    s.at("A D-1 11.01 12:00", "2026-11-01 12:00")
    s.at("A 종료 당일 11.02 14:00", "2026-11-02 14:00")
    s.at("A 행사 종료 뒤 11.02 22:00", "2026-11-02 22:00")
    s.at("A 가챠 종료 29분 전 11.03 11:30", "2026-11-03 11:30")
    s.at("A 전부 종료 11.03 12:30", "2026-11-03 12:30")
    s.at("A 자정 직전 11.03 23:55", "2026-11-03 23:55")
    s.at("A 자정 뒤 11.04 00:05", "2026-11-04 00:05")
    ex = {
        "A 공지 직후 10.20 12:00": {"st": "sched", "visible": True, "chip": "개최까지 D-5"[:0] or None, "dates_has": ["10.25(일) 18:00 개최", "11.02(월) 20:59 종료"], "ends_has": ["행사 종료 11.02(월) 20:59", "가챠 종료 11.03(화) 11:59"]},
        "A 개최 전날 10.24 12:00": {"st": "sched", "bubble": "개최까지 D-1"},
        "A 개최 30분 전 10.25 17:30": {"st": "sched", "bubble": "개최까지 30분"},
        "A 진행 10.26 12:00 (D-7)": {"st": "live", "chip": "이벤트 종료까지 D-7"},
        "A D-4 10.29 12:00": {"st": "live", "chip": "이벤트 종료까지 D-4"},
        "A D-3 10.30 00:30": {"st": "warn", "bubble": "이벤트 종료까지 D-3", "hot": 1, "over": 0},
        "A D-3 10.30 12:00": {"st": "warn", "bubble": "이벤트 종료까지 D-3"},
        "A D-1 11.01 12:00": {"st": "warn", "bubble": "이벤트 종료까지 D-1"},
        "A 종료 당일 11.02 14:00": {"st": "warn", "bubble": "이벤트 종료까지 7시간"},
        "A 행사 종료 뒤 11.02 22:00": {"st": "urgent", "bubble": "가챠 종료까지 14시간", "hot": 1, "over": 1},
        "A 가챠 종료 29분 전 11.03 11:30": {"st": "urgent", "bubble": "가챠 종료까지 29분"},
        "A 전부 종료 11.03 12:30": {"st": "done", "visible": True, "over": 2, "dates_has": ["모두 종료 · 자정까지 표시"]},
        "A 자정 직전 11.03 23:55": {"st": "done", "visible": True},
        "A 자정 뒤 11.04 00:05": {"st": "gone", "visible": False},
    }
    ex["A 공지 직후 10.20 12:00"].pop("chip")
    verify_points(s, ex)
    # 백엔드 sweep — 자정 뒤에는 보관으로, 그 전에는 남는다
    sw, arc, moved = banners.sweep(s.prev, banners.default_archive(), kst("2026-11-03 23:55"))
    check(not moved, "A 자정 직전 sweep — 아직 안 옮김")
    sw, arc, moved = banners.sweep(s.prev, banners.default_archive(), kst("2026-11-04 00:05"))
    check(len(moved) == 1 and moved[0]["archived_reason"] == "ended", "A 자정 뒤 sweep — 보관(ended)")
    return s


def scenario_b(llm):
    print("\n══ 시나리오 B — 시작 전 보류 → 3일 뒤 시작(시작 · 종료 갱신) ══")
    s = Sim(llm)
    j, r = s.post(t_announce("10月25日(日)18:00", "11月2日(月)20:59", "11月3日(火)11:59"), "2026-10-20 12:00", "upsert")
    check(r and r["mode"] == "added" and r["shown"], "B1 예고 글 → 올라감")
    s.at("B 예고 직후 10.20 12:00", "2026-10-20 12:00")
    j, r = s.post(T_HOLD, "2026-10-24 22:00", "hold")
    check(r and r["mode"] == "held", "B2 개최 연기 공지 → 보류(held)")
    b = s.prev["banners"][0]
    check(bool(b.get("hold")) and b["hold"]["anchor"] == kst("2026-10-25 18:00"), "B2 보류 기준일 = 원래 시작 10.25 18:00")
    check(b["hold"]["until"] == kst("2026-11-09 18:00"), "B2 보류 유지 기한 = 기준일 + 15일 (11.09 18:00)")
    s.at("B 보류 중 10.25 18:30", "2026-10-25 18:30")
    s.at("B 보류 중 11.01 12:00", "2026-11-01 12:00")
    j, r = s.post(T_RESCHEDULE, "2026-10-26 12:00", "upsert")
    check(r and r["mode"] == "updated", "B3 새 일정 공지 → 갱신(updated)")
    b = s.prev["banners"][0]
    check(b.get("hold") is None, "B3 보류 해제")
    check(b["start_at"] == kst("2026-10-28 18:00") and b["end_at"] == kst("2026-11-05 20:59"), "B3 시작 · 종료 갱신 = 10.28 18:00 ~ 11.05 20:59 (3일 뒤 시작)")
    check(len(s.prev["banners"]) == 1, "B3 행사는 여전히 1건(새로 안 만듦)")
    check(b["gachas"][0].get("end_at") == kst("2026-11-06 11:59"), "B3 가챠 종료 갱신 = 11.06 11:59")
    s.at("B 새 일정 직후 10.26 12:30", "2026-10-26 12:30")
    s.at("B 개최 D-1 10.27 12:00", "2026-10-27 12:00")
    s.at("B 개최 1시간 전 10.28 17:00", "2026-10-28 17:00")
    j, r = s.post(T_OPEN("11月5日(木)20:59"), "2026-10-28 18:30", None)
    check(len(s.prev["banners"]) == 1 and s.prev["banners"][0]["start_at"] == kst("2026-10-28 18:00") and s.prev["banners"][0]["end_at"] == kst("2026-11-05 20:59"), "B4 개최 글 뒤 일정 그대로")
    s.at("B 진행 10.30 12:00", "2026-10-30 12:00")
    s.at("B D-3 11.02 12:00", "2026-11-02 12:00")
    s.at("B 행사 종료 뒤 11.05 22:00", "2026-11-05 22:00")
    s.at("B 전부 종료 11.06 12:30", "2026-11-06 12:30")
    s.at("B 자정 뒤 11.07 00:05", "2026-11-07 00:05")
    ex = {
        "B 예고 직후 10.20 12:00": {"st": "sched", "visible": True, "dates_has": ["10.25(일) 18:00 개최", "11.02(월) 20:59 종료"]},
        "B 보류 중 10.25 18:30": {"st": "hold", "visible": True, "dates_has": ["10.25(보류)"], "ends_none": True},
        "B 보류 중 11.01 12:00": {"st": "hold", "visible": True},
        "B 새 일정 직후 10.26 12:30": {"st": "sched", "bubble": "개최까지 D-2", "dates_has": ["10.28(수) 18:00 개최", "11.05(목) 20:59 종료"], "ends_has": ["행사 종료 11.05(목) 20:59", "가챠 종료 11.06(금) 11:59"]},
        "B 개최 D-1 10.27 12:00": {"st": "sched", "bubble": "개최까지 D-1"},
        "B 개최 1시간 전 10.28 17:00": {"st": "sched", "bubble": "개최까지 1시간"},
        "B 진행 10.30 12:00": {"st": "live", "chip": "이벤트 종료까지 D-6"},
        "B D-3 11.02 12:00": {"st": "warn", "bubble": "이벤트 종료까지 D-3"},
        "B 행사 종료 뒤 11.05 22:00": {"st": "urgent", "bubble": "가챠 종료까지 14시간"},
        "B 전부 종료 11.06 12:30": {"st": "done", "visible": True},
        "B 자정 뒤 11.07 00:05": {"st": "gone", "visible": False},
    }
    verify_points(s, ex)
    # 보류 만료(보류 기한 + 15일 지나도록 새 일정이 없으면 내림) — 보류만 한 가상 행사로 따로
    h = Sim(llm)
    h.prev = json.loads(json.dumps(s.prev))
    h.prev["banners"][0]["hold"] = {"anchor": kst("2026-10-25 18:00"), "until": kst("2026-11-09 18:00")}
    h.prev["banners"][0]["start_at"], h.prev["banners"][0]["end_at"] = kst("2026-10-25 18:00"), kst("2026-11-02 20:59")
    for when, want in (("2026-11-09 17:59", "hold"), ("2026-11-09 18:00", "gone")):
        st, why = banners.derive(h.prev["banners"][0], kst(when))
        check(st == want, f"B 보류 기한 경계 {when} → {want} (실제 {st}/{why})")
    return s


def main():
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        print("GROQ_API_KEY 없음 — .env.local 필요")
        sys.exit(2)
    llm = LLMClient(key)
    scenario_a(llm)
    scenario_b(llm)
    ok = sum(1 for r in RES if r["ok"])
    print(f"\n결과: {ok}/{len(RES)} 통과" + ("" if not FAILS else f" — 실패 {len(FAILS)}건"))
    for f in FAILS:
        print("  ✗", f)
    (HERE / "results_banner.json").write_text(json.dumps({"ran_at": datetime.now(timezone.utc).isoformat(), "total": len(RES), "ok": ok, "results": RES, "front": FRONT}, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()
