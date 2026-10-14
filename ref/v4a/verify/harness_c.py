"""v4a 검증 3차 (2026-10-02) — LLM 판단 「반려 → LLM 재판단 / 사용자 판단」 7가지 판단 종류 시나리오.

`harness.py` 의 구성(Flask 접수 앱 + q-apply · q-enrich 워커 + LocalStore, 외부 서비스만 가짜)을 그대로 쓴다.
설계 · 판단별 시나리오: ref/v4a/v4a_llm_review_scenarios.md. 결과는 `results_c.json`(git 제외).

    python ref/v4a/verify/harness_c.py
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as h  # noqa: E402

from src.backend import admin_api, llm, telegram_app, vxtwitter  # noqa: E402
from src.collector.youtube import VideoInfo  # noqa: E402

check, scenario, item, pv, idle = h.check, h.scenario, h.item, h.pv, h.idle
REAL_NOW, KST, z, TP = h.REAL_NOW, timezone(timedelta(hours=9)), h.z, h.TP
RES_C: list[dict] = []

# ── 가짜 ──────────────────────────────────────────────────────────────────────
TW: dict[str, dict] = {}
vxtwitter.fetch_tweet = lambda tid, *a, **k: TW.get(str(tid))
vxtwitter.extract = lambda j: {"text": j.get("text", ""), "author": j.get("author", ""), "media": j.get("media", []),
                               "urls": [], "yt_video_id": None, "qrt_url": None, "qrt": None, "reposted_by": ""}
HINTS: list[str] = []          # 판정 호출이 본 「반려됐다」 힌트(재판단일 때만 비어 있지 않다)


def hint() -> str:
    x = llm.REVIEW_HINT.get()
    HINTS.append(x)
    return x


BJ = {"fn": lambda: {"action": "none", "banner_ref": None, "event": None, "gacha": None, "image_for": "none",
                     "image_roles": [], "reason": "행사 무관"}}
h._llm("banner_judge", lambda text, posted, active, images_ocr=None, **k: (hint(), BJ["fn"]())[1])
CHANGE = {"fn": lambda raw, cands: {"action": "none", "target_ids": [], "when": None, "reason": "취소 아님"}}
h._llm("broadcast_change_targets", lambda raw, cands, now_label, **k: (hint(), CHANGE["fn"](raw, cands))[1])
COLLAB = {"all": False}
h._llm("collab_partners", lambda t, **k: (hint(), list(k.get("candidate_names") or []) if COLLAB["all"] else [])[1])
DUP = {"on": False}
h._llm("duplicate_notice", lambda new_text, cands, **k: (hint(), cands[0]["id"] if DUP["on"] and cands else None)[1])
OWN = {"ret": False}
h._llm("announces_own_broadcast", lambda t, **k: (hint(), OWN["ret"])[1])
PART = {"ret": False}
h._llm("participation", lambda t, **k: (hint(), PART["ret"])[1])
OCR: dict[str, list[str]] = {}


class _FakeVision:
    def cast_names(self, image_url=None, **k):
        h.tr("external", svc="groq-vision", call="cast_names")
        return OCR.get(image_url)


telegram_app._make_vision_client = lambda: _FakeVision()


def ext_video(vid, cid, ss, title="外部コラボ"):
    kw = dict(video_id=vid, channel_id=cid, title=title, thumbnail=None, live_state="upcoming", scheduled_start=ss,
              actual_start=None, actual_end=None, concurrent_viewers=None)
    h.WORLD[vid] = VideoInfo(**{k: kw.get(k) for k in h._VI})


# ── 도우미 ────────────────────────────────────────────────────────────────────
def entries() -> list[dict]:
    return admin_api.list_llm_actions()["items"]          # 최신 먼저


def get(eid: str) -> dict:
    return next((e for e in entries() if e["id"] == eid), {})


def newest(kind: str, **match) -> dict:
    return next((e for e in entries() if e["kind"] == kind and all(e.get(k) == v for k, v in match.items())), {})


def own_items() -> list[dict]:
    """텍스트 예고(영상 없음)로 올라온 미야코 개인 예고."""
    return [i for i in pv() if i.get("channel_key") == "miyako" and i.get("source") == "personal" and not i.get("video_id")]


def banners_now() -> list[dict]:
    return (h.GH.read_json("banners.json")[0] or {}).get("banners", [])


def suppressed() -> list[str]:
    st, _ = h.storage.make_store("ops").read_json("admin_state.json")
    return [s.get("url") for s in (st or {}).get("suppress", [])]


def pending_ids() -> set:
    items = (h.storage.make_store("ops").read_json("group_pending.json")[0] or {}).get("items", [])
    return {x.get("video_id") for x in items}


def notices_now() -> list[dict]:
    return (h.GH.read_json("notices.json")[0] or {}).get("notices", [])


def reject(eid: str) -> dict:
    r = admin_api.undo_llm_action(eid)
    idle()
    return r


def rejudge(eid: str) -> dict:
    HINTS.clear()
    r = admin_api.rejudge_llm_action(eid)
    idle()
    return r


def decide(eid: str, dec: dict) -> dict:
    r = admin_api.decide_llm_action(eid, dec)
    idle()
    return r


def kst_local(dt) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%dT%H:%M")


def jst_str(dt) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def run():
    OFF, FOLLOW = "夢限大みゅーたいぷ", None

    # ═════ 1. banner_judge ═════
    scenario("C1 행사 배너 판정 — 반려 → LLM 재판단 → 반려 → 사용자 판단")
    s_, e_ = REAL_NOW + timedelta(days=1), REAL_NOW + timedelta(days=6)
    BJ["fn"] = lambda: {"action": "none", "banner_ref": None, "event": None, "gacha": None, "image_for": "none",
                        "image_roles": [], "reason": "행사 정보 없음"}
    h.ingest_x("新イベント開催決定！", "バンドリ！アワーノーツ", tag=f"p#x#1tweet-{TP}601")
    e1 = newest("banner_judge")
    check("C1", "처음 판정 none → 기록 + 입력 스냅샷(원문 · 태그) 저장", e1 and not banners_now() and (e1.get("input") or {}).get("raw")
          and e1.get("by") == "llm" and not e1.get("undo"), e1)
    r = reject(e1["id"])
    check("C1", "검토용 판단도 반려 가능(롤백 없음, 표시만 반려됨)", r.get("ok") and get(e1["id"]).get("undone") and (r["result"] or {}).get("review_only"), r)
    BJ["fn"] = lambda: {"action": "upsert", "banner_ref": None, "image_for": "none", "image_roles": [], "reason": "행사 개최 글",
                        "event": {"name_ja": "星降るRush", "name_ko": "별 Rush", "start_jst": jst_str(s_), "end_jst": jst_str(e_), "permanent": False},
                        "gacha": None}
    r = rejudge(e1["id"])
    e2 = newest("banner_judge", parent_id=e1["id"])
    check("C1", "LLM 재판단 → 반려 힌트가 판정 호출에 전달됨", r.get("ok") and any("반려" in x for x in HINTS), (r, HINTS))
    check("C1", "재판단 결과로 행사 배너가 올라감 + 새 기록이 parent 로 이어짐 + by=llm_rejudge",
          len(banners_now()) == 1 and e2 and e2.get("by") == "llm_rejudge" and e2.get("undo"), (banners_now(), e2))
    check("C1", "원래 기록에 followup(재판단 · 새 기록 id · 결과) 남음", (get(e1["id"]).get("followup") or {}).get("type") == "rejudge"
          and (get(e1["id"]).get("followup") or {}).get("new_ids") == [e2["id"]], get(e1["id"]).get("followup"))
    r2 = rejudge(e1["id"])
    check("C1", "한 기록에서 후속은 한 번(두 번째 재판단 거절)", not r2.get("ok") and "이미" in (r2.get("error") or ""), r2)
    r2 = reject(e1["id"])
    check("C1", "후속을 한 기록은 다시 반려할 수 없음", not r2.get("ok"), r2)
    r = reject(e2["id"])
    check("C1", "새 판단도 반려 가능 → 그 판단이 만든 배너만 지움", r.get("ok") and not banners_now(), (r, banners_now()))
    r = decide(e2["id"], {"choice": "register", "name_ja": "手動イベント", "name_ko": "수동 이벤트",
                          "start": kst_local(s_), "end": kst_local(e_)})
    e3 = newest("banner_judge", parent_id=e2["id"])
    check("C1", "사용자 판단(직접 입력) → LLM 없이 행사 배너 등록 + by=user", r.get("ok") and len(banners_now()) == 1
          and banners_now()[0]["name_ko"] == "수동 이벤트" and e3 and e3.get("by") == "user", (r, banners_now(), e3))
    r = reject(e3["id"])
    r = decide(e3["id"], {"choice": "skip"})
    check("C1", "사용자 판단 「올리지 않음」 → 변경 없음 + user_review 기록", r.get("ok") and not banners_now()
          and newest("user_review", parent_id=e3["id"]), (r, banners_now()))
    r = decide(e3["id"], {"choice": "skip"})
    check("C1", "이미 후속을 한 기록은 다시 결정할 수 없음", not r.get("ok"), r)
    # 옛 기록(입력 없음) — 재판단 불가, 사용자 판단은 가능
    gh = h.GH
    old = telegram_app._llm_record(gh, "banner_judge", "bang_dream_on", "옛 기록", now_iso=h.CLOCK.iso())
    idle()
    reject(old)
    r = rejudge(old)
    check("C1", "입력 스냅샷이 없는 옛 기록은 LLM 재판단 불가(사용자 판단 안내)", not r.get("ok") and "옛 기록" in (r.get("error") or ""), r)

    # ═════ 2. broadcast_change ═════
    scenario("C2 방송 취소 · 변경 판정 — 반려 → 재판단 → 사용자 판단(취소 · 일정 변경)")
    ss = h.rnd(REAL_NOW + timedelta(hours=6))
    h.video("VCHG0000001", "miyako", "upcoming", z(ss), title="【歌枠】みやこ")
    h.RSS.clear(); h.RSS["miyako"] = ["VCHG0000001"]
    h.reconcile(at=REAL_NOW)
    h.RSS.clear()
    it = item(lambda i: i.get("video_id") == "VCHG0000001")
    check("C2", "준비: 예고 등록", it and it["state"] == "upcoming", it)
    CHANGE["fn"] = lambda raw, cands: {"action": "del", "target_ids": [c["id"] for c in cands], "when": None, "reason": "취소 공지"}
    h.ingest_x("本日の配信はお休みです🙏", "藤都子", tag=f"p#x#1tweet-{TP}611")
    e = newest("broadcast_change")
    check("C2", "취소 판정 → 예고 삭제 + 재등록 차단 + 기록(입력 포함)", not item(lambda i: i.get("video_id") == "VCHG0000001")
          and any("VCHG0000001" in (u or "") for u in suppressed()) and (e.get("input") or {}).get("channel_key") == "miyako", (e, suppressed()))
    r = reject(e["id"])
    check("C2", "반려 → 취소했던 예고 되살림 + 차단 해제", r.get("ok") and item(lambda i: i.get("video_id") == "VCHG0000001")
          and not any("VCHG0000001" in (u or "") for u in suppressed()), (r, suppressed()))
    CHANGE["fn"] = lambda raw, cands: {"action": "none", "target_ids": [], "when": None, "reason": "단순 인사 — 취소 아님"}
    r = rejudge(e["id"])
    e2 = newest("broadcast_change", parent_id=e["id"])
    check("C2", "LLM 재판단(이번엔 취소 아님) → 예고 유지 + 힌트 전달 + 새 기록", r.get("ok") and any("반려" in x for x in HINTS)
          and item(lambda i: i.get("video_id") == "VCHG0000001") and e2 and "아님" in e2["summary"], (r, e2, HINTS))
    reject(e2["id"])
    opt = admin_api.llm_review_options(e2["id"])
    check("C2", "사용자 판단 선택지: 이 멤버의 활성 예고 후보 목록", opt.get("candidates") and opt["candidates"][0]["id"] == it["id"], opt)
    r = decide(e2["id"], {"choice": "cancel", "target_ids": [it["id"]]})
    e3 = newest("broadcast_change", parent_id=e2["id"])
    check("C2", "사용자 판단(취소 적용) → 선택한 예고 삭제 + 차단 + by=user", r.get("ok") and not item(lambda i: i.get("video_id") == "VCHG0000001")
          and e3 and e3.get("by") == "user", (r, e3))
    reject(e3["id"])
    new_t = h.rnd(REAL_NOW + timedelta(hours=9))
    r = decide(e3["id"], {"choice": "edit", "target_ids": [it["id"]], "when": kst_local(new_t)})
    it2 = item(lambda i: i.get("id") == it["id"])
    check("C2", "사용자 판단(일정 변경) → 선택한 예고의 시각이 입력한 KST 로 바뀜", r.get("ok") and it2 and it2["scheduled_start"] == z(new_t), (r, it2 and it2["scheduled_start"], z(new_t)))
    e4 = newest("broadcast_change", parent_id=e3["id"])
    reject(e4["id"])
    check("C2", "일정 변경 반려 → 시각이 원래 값으로", (item(lambda i: i.get("id") == it["id"]) or {}).get("scheduled_start") == z(ss),
          (item(lambda i: i.get("id") == it["id"]) or {}).get("scheduled_start"))
    r = decide(e4["id"], {"choice": "none"})
    check("C2", "사용자 판단(해당 없음) → 변경 없음 + user_review", r.get("ok") and newest("user_review", parent_id=e4["id"]), r)

    # ═════ 3. collab_guest ═════
    scenario("C3 합동 게스트 판정 — 반려 → 재판단 → 사용자 판단")
    ss = h.rnd(REAL_NOW + timedelta(hours=7))
    h.video("VCOL0000001", "miyako", "upcoming", z(ss), title="雑談 with 仲町あられ")
    COLLAB["all"] = False
    h.ingest_x("本日の配信、仲町あられさんと雑談！ https://www.youtube.com/watch?v=VCOL0000001", "藤都子", tag=f"p#x#1tweet-{TP}621")
    e = newest("collab_guest")
    it = item(lambda i: i.get("video_id") == "VCOL0000001")
    check("C3", "게스트 아님 판정 → 합동 없음 + 기록에 후보 · 대상 영상 저장", it and not it.get("collab_with")
          and (e.get("input") or {}).get("guest_keys") == ["arale"] and (e.get("input") or {}).get("target", {}).get("video_id") == "VCOL0000001", (it, e))
    reject(e["id"])
    COLLAB["all"] = True
    r = rejudge(e["id"])
    it = item(lambda i: i.get("video_id") == "VCOL0000001")
    e2 = newest("collab_guest", parent_id=e["id"])
    check("C3", "LLM 재판단 → 게스트로 판정 → 대상 예고의 합동 멤버 갱신 + 힌트", r.get("ok") and it and it.get("collab_with") == ["arale"]
          and any("반려" in x for x in HINTS) and e2 and e2.get("undo"), (r, it, HINTS))
    reject(e2["id"])
    check("C3", "반려 → 합동 멤버가 원래대로(없음)", not (item(lambda i: i.get("video_id") == "VCOL0000001") or {}).get("collab_with"), pv())
    opt = admin_api.llm_review_options(e2["id"])
    r = decide(e2["id"], {"choice": "set", "guests": ["ritsu"]})
    it = item(lambda i: i.get("video_id") == "VCOL0000001")
    check("C3", "사용자 판단 → 고른 멤버로 합동 확정(후보 밖 멤버도 가능) + 멤버 선택지 제공", r.get("ok") and it.get("collab_with") == ["ritsu"]
          and len(opt.get("members") or []) == 5, (r, it and it.get("collab_with"), opt.get("members")))

    # ═════ 4. duplicate_notice ═════
    scenario("C4 소식 같은 행사 판정 — 반려(병합 취소) → 재판단 → 사용자 판단")
    d = (REAL_NOW + timedelta(days=9)).astimezone(KST)
    n0 = len(notices_now())
    DUP["on"] = False
    h.ingest_x(f"💿夢限大みゅーたいぷ 7th Single💿\n{d.month}/{d.day}発売決定！\n予約受付中です✨\n#ゆめみた", OFF, tag=f"p#x#1tweet-{TP}631")
    n1 = len(notices_now())
    DUP["on"] = True
    h.ingest_x(f"🎧夢限大みゅーたいぷ ミニアルバム🎧\n{d.month}/{d.day}同日発売！\nご予約はこちら\n#ゆめみた", OFF, tag=f"p#x#1tweet-{TP}632")
    e = newest("duplicate_notice")
    check("C4", "중복 판정 → 기존 소식에 병합(소식 수 그대로) + 기록(병합 전 스냅샷 · 입력)",
          e and len(notices_now()) == n1 and (e.get("undo") or {}).get("type") == "restore_notice" and (e.get("input") or {}).get("raw"),
          (e, n1, len(notices_now())))
    row = next((n for n in notices_now() if n["id"] == (e.get("undo") or {}).get("id")), {})
    check("C4", "병합된 행에 새 글 id 가 seen_ids 로 들어감", (e.get("undo") or {}).get("parsed_id") in (row.get("seen_ids") or []), row)
    r = reject(e["id"])
    row = next((n for n in notices_now() if n["id"] == (e.get("undo") or {}).get("id")), {})
    check("C4", "반려 → 병합 전 모습으로 복원(새 글 흔적 제거)", r.get("ok") and (e["undo"]["parsed_id"] not in (row.get("seen_ids") or [])), (r, row))
    DUP["on"] = False
    r = rejudge(e["id"])
    check("C4", "LLM 재판단(이번엔 별개 소식) → 소식이 하나 더 생김 + 힌트", r.get("ok") and len(notices_now()) == n1 + 1
          and any("반려" in x for x in HINTS), (r, len(notices_now()), n1, HINTS))
    DUP["on"] = True
    h.ingest_x(f"🎤夢限大みゅーたいぷ ライブ決定🎤\n{d.month}/{d.day}開催！\n詳細はこちら\n#ゆめみた", OFF, tag=f"p#x#1tweet-{TP}633")
    e3 = newest("duplicate_notice", parent_id=None)
    n3 = len(notices_now())
    if e3 and e3["id"] != e["id"]:
        reject(e3["id"])
        r = decide(e3["id"], {"choice": "separate"})
        check("C4", "사용자 판단(별도 소식) → 병합 없이 별도 소식으로", r.get("ok") and len(notices_now()) >= n3, (r, n3, len(notices_now())))
        e4 = newest("duplicate_notice", parent_id=e3["id"])
        opt = admin_api.llm_review_options(e3["id"])
        check("C4", "사용자 판단 선택지: 현재 소식 목록", opt.get("notices"), opt.get("notices"))
    else:
        RES_C.append({"obs": "C4 3번째 소식은 중복 판정 호출이 없었음(소식 key 일치로 갱신)"})

    # ═════ 5. ocr_members ═════
    scenario("C5 그룹 영상 이미지 OCR 판정 — 반려(확인 대기로) → 재판단(재판독) → 사용자 판단")
    t_g = h.rnd(REAL_NOW + timedelta(hours=8))
    h.video("GRPOCR00001", "group", "upcoming", z(t_g), title="コラボ配信")
    url = "https://pbs.twimg.com/media/ocrA.jpg"
    OCR[url] = ["峰月律", "藤都子"]
    TW[f"{TP}641"] = {"author": "arale_yumemita", "media": [url], "text": "今日はコラボ配信！ https://www.youtube.com/watch?v=GRPOCR00001"}
    h.ingest_x("今日はコラボ配信！ https://www.youtube.com/watch?v=GRPOCR00001", "仲町あられ", tag=f"p#x#1tweet-{TP}641")
    e = newest("ocr_members")
    g = item(lambda i: i.get("video_id") == "GRPOCR00001")
    check("C5", "OCR 판정 → 5인 아닌 읽은 멤버로 등록 + 기록(이미지 · 영상 입력)", g and g["channel_key"] == "ritsu"
          and (e.get("input") or {}).get("media") == [url], (g, e))
    reject(e["id"])
    check("C5", "반려 → 예고에서 빠지고 확인 대기로", not item(lambda i: i.get("video_id") == "GRPOCR00001") and "GRPOCR00001" in pending_ids(), pending_ids())
    OCR[url] = ["千石ユノ", "宮永ののか"]
    r = rejudge(e["id"])
    g = item(lambda i: i.get("video_id") == "GRPOCR00001")
    e2 = newest("ocr_members", parent_id=e["id"])
    check("C5", "LLM 재판단(이미지 다시 판독) → 새로 읽은 멤버로 등록 + 대기에서 빠짐 + 새 기록",
          r.get("ok") and g and g["channel_key"] == "yuno" and g.get("collab_with") == ["nonoka"] and "GRPOCR00001" not in pending_ids() and e2, (r, g, pending_ids()))
    reject(e2["id"])
    r = decide(e2["id"], {"choice": "members", "members": ["arale"]})
    g = item(lambda i: i.get("video_id") == "GRPOCR00001")
    check("C5", "사용자 판단(멤버 선택) → 고른 멤버로 등록", r.get("ok") and g and g["channel_key"] == "arale" and not g.get("collab_with"), (r, g))
    e3 = newest("ocr_members", parent_id=e2["id"])
    reject(e3["id"])
    r = decide(e3["id"], {"choice": "skip"})
    check("C5", "사용자 판단(올리지 않음) → 확인 대기에서도 뺌", r.get("ok") and "GRPOCR00001" not in pending_ids()
          and not item(lambda i: i.get("video_id") == "GRPOCR00001"), (r, pending_ids()))

    # ═════ 6. own_broadcast ═════
    scenario("C6 본인 예고 최종 확인 — 반려 → 재판단 → 사용자 판단")
    dd = (REAL_NOW + timedelta(days=2)).astimezone(KST)
    TEXT = f"{dd.month}/{dd.day} 21:00〜 配信します！みんな来てね"
    OWN["ret"] = False
    h.ingest_x(TEXT, "藤都子", tag=f"p#x#1tweet-{TP}651")
    e = newest("own_broadcast")
    n_items = len([i for i in pv() if i.get("channel_key") == "miyako"])
    check("C6", "LLM 최종 확인 불통과 → 예고 안 올림 + 기록(입력)", e and "아님" in e["summary"] and (e.get("input") or {}).get("raw"), e)
    reject(e["id"])
    OWN["ret"] = True
    r = rejudge(e["id"])
    e2 = newest("own_broadcast", parent_id=e["id"])
    mine = own_items()
    check("C6", "LLM 재판단(이번엔 예고로 확인) → 예고 등록 + 힌트 + 새 기록(undo)", r.get("ok") and mine and e2 and e2.get("undo")
          and any("반려" in x for x in HINTS), (r, mine, e2, HINTS))
    reject(e2["id"])
    check("C6", "반려 → 등록했던 예고만 지움", not own_items(), pv())
    OWN["ret"] = False
    r = decide(e2["id"], {"choice": "register"})
    e3 = newest("own_broadcast", parent_id=e2["id"])
    check("C6", "사용자 판단(예고로 등록) → LLM 이 아니라고 해도 등록 + by=user", r.get("ok")
          and own_items() and e3 and e3.get("by") == "user", (r, e3))
    reject(e3["id"])
    r = decide(e3["id"], {"choice": "skip"})
    check("C6", "사용자 판단(등록 안 함) → 변경 없음", r.get("ok") and not own_items(), r)

    # ═════ 7. participation ═════
    scenario("C7 외부 채널 영상 참여 판정 — 반려 → 재판단 → 사용자 판단")
    t_e = h.rnd(REAL_NOW + timedelta(hours=10))
    ext_video("VEXT0000001", "UC_external_channel_xxx", z(t_e), title="外部コラボ配信")
    PART["ret"] = False
    h.ingest_x("明日の配信に出演します https://www.youtube.com/watch?v=VEXT0000001", "藤都子", tag=f"p#x#1tweet-{TP}661")
    e = newest("participation")
    check("C7", "참여 아님 판정 → 예고 안 올림 + 기록(원문 · 영상 id 입력)", e and not item(lambda i: i.get("video_id") == "VEXT0000001")
          and (e.get("input") or {}).get("video_id") == "VEXT0000001", e)
    reject(e["id"])
    PART["ret"] = True
    r = rejudge(e["id"])
    e2 = newest("participation", parent_id=e["id"])
    check("C7", "LLM 재판단(이번엔 참여) → 영상 정보 재조회 후 예고 등록 + 힌트 + 새 기록(undo)", r.get("ok")
          and item(lambda i: i.get("video_id") == "VEXT0000001") and any("반려" in x for x in HINTS) and e2 and e2.get("undo"), (r, e2, HINTS))
    reject(e2["id"])
    check("C7", "반려 → 등록한 예고 지움", not item(lambda i: i.get("video_id") == "VEXT0000001"), pv())
    PART["ret"] = False
    r = decide(e2["id"], {"choice": "register"})
    e3 = newest("participation", parent_id=e2["id"])
    check("C7", "사용자 판단(참여로 등록) → LLM 이 아니라고 해도 등록 + by=user", r.get("ok")
          and item(lambda i: i.get("video_id") == "VEXT0000001") and e3 and e3.get("by") == "user", (r, e3))
    reject(e3["id"])
    r = decide(e3["id"], {"choice": "skip"})
    check("C7", "사용자 판단(참여 아님) → 변경 없음", r.get("ok") and not item(lambda i: i.get("video_id") == "VEXT0000001"), r)

    # ═════ 공통 ═════
    scenario("C0 공통 — 기록 연결 · 안전")
    allk = {x["kind"] for x in entries()}
    check("C0", "7가지 판단 종류가 모두 기록됨", {"banner_judge", "broadcast_change", "collab_guest", "duplicate_notice", "ocr_members",
                                              "own_broadcast", "participation"} <= allk, allk)
    kids = [x for x in entries() if x.get("parent_id")]
    check("C0", "후속 기록은 전부 parent_id 로 이어지고 by 가 llm_rejudge · user 중 하나", kids and all(x["by"] in ("llm_rejudge", "user") for x in kids), len(kids))
    r = admin_api.rejudge_llm_action("llm_nonexistent")
    check("C0", "없는 기록 → 오류", not r.get("ok"), r)
    live = next((x for x in entries() if not x.get("undone")), None)
    if live:
        r = admin_api.rejudge_llm_action(live["id"])
        check("C0", "반려 전 기록은 재판단 불가(먼저 반려)", not r.get("ok") and "먼저 반려" in (r.get("error") or ""), r)
    commits = [json.loads(l) for l in open(h.WORK / "_local/data/.commits.jsonl", encoding="utf-8")]
    bad = [c for c in commits if c["thread"] != "q-apply"]
    check("원칙①", f"data 커밋 {len(commits)}건 전부 q-apply 스레드", not bad, bad[:5])
    ext = [x for x in h.TRACE if x["step"] == "external"]
    w = [x for x in ext if x["svc"] in ("groq", "groq-vision", "vxtwitter", "yt-dlp") and x["actor"] == "writer"]
    check("원칙④", "LLM · 비전 · vxtwitter 호출이 쓰기 스레드에서 0건", not w, [(x["svc"], x["call"]) for x in w][:5])


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
    finally:
        h.q_apply.stop(); h.q_enrich.stop()
        b = [r for r in h.RESULTS]
        (HERE / "results_c.json").write_text(json.dumps({"results": b, "observations": RES_C}, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = sum(r["ok"] for r in b)
        print(f"\n결과: {ok}/{len(b)} 통과")
        for o in RES_C:
            print("  관측", o)
