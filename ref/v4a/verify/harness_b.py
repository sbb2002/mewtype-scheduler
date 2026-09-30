"""v4a 검증 2차 (2026-09-30) — 09-29 이후 추가된 관리 페이지 · 판정 기능 시나리오.

`harness.py` 를 모듈로 불러와 같은 구성(Flask 접수 앱 + q-apply · q-enrich 워커 + LocalStore, 외부 서비스만 가짜)을
그대로 쓴다. 실행 산출물은 `run/`(git 제외), 결과는 `results_b.json`.

    python ref/v4a/verify/harness_b.py
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as h  # noqa: E402  — 가짜 외부 서비스 · 워커 · 로컬 저장소 구성이 여기서 끝난다

from src.backend import admin_api, handlers, llm, telegram_app, vxtwitter  # noqa: E402
from src.collector.youtube import VideoInfo  # noqa: E402

check, scenario, item, pv, idle, tr = h.check, h.scenario, h.item, h.pv, h.idle, h.tr
REAL_NOW, CLOCK, KST = h.REAL_NOW, h.CLOCK, timezone(timedelta(hours=9))
z = h.z

# ── 추가 가짜: 트윗 조회 · 취소/변경 판정 · 비전 OCR · RSS 호출 기록 ────────────────────────
TW: dict[str, dict] = {}


def _fetch_tweet(tid, *a, **k):
    tr("external", svc="vxtwitter", call="fetch_tweet")
    return TW.get(str(tid))


def _extract(j):
    return {"text": j.get("text", ""), "author": j.get("author", ""), "media": j.get("media", []), "urls": [],
            "yt_video_id": None, "qrt_url": None, "qrt": None}


vxtwitter.fetch_tweet, vxtwitter.extract = _fetch_tweet, _extract

CHANGE = {"fn": lambda raw, cands, now_label: {"action": "none", "target_ids": [], "when": None, "reason": "기본"}}
CHANGE_CALLS: list[str] = []


def _change(raw, cands, now_label):
    CHANGE_CALLS.append(raw)
    return CHANGE["fn"](raw, cands, now_label)


h._llm("broadcast_change_targets", _change)

OCR: dict[str, list[str]] = {}


class _FakeVision:
    def cast_names(self, image_url=None, **k):
        tr("external", svc="groq-vision", call="cast_names")
        return OCR.get(image_url)


telegram_app._make_vision_client = lambda: _FakeVision()

RSS_KEYS: list[list[str]] = []
_rss_prev = handlers.fetch_all_rss_video_ids


def _rss(id_by_key):
    RSS_KEYS.append(sorted(id_by_key))
    return _rss_prev(id_by_key)


handlers.fetch_all_rss_video_ids = _rss


def ext_video(vid, cid, ss, title="外部コラボ"):
    kw = dict(video_id=vid, channel_id=cid, title=title, thumbnail=None, live_state="upcoming", scheduled_start=ss,
              actual_start=None, actual_end=None, concurrent_viewers=None)
    h.WORLD[vid] = VideoInfo(**{k: kw.get(k) for k in h._VI})


def kst_date(dt):
    return dt.astimezone(KST).strftime("%Y-%m-%d")


def mmdd(dt):
    j = dt.astimezone(KST)
    return f"{j.month}/{j.day}"


def suppressed_urls():
    st, _ = h.storage.make_store("ops").read_json("admin_state.json")
    return [s.get("url") for s in (st or {}).get("suppress", [])]


def events(pred):
    out = []
    for f in sorted((h.WORK / "_local").rglob("events-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if pred(e):
                out.append(e)
    return out


RES_B: list[dict] = []


def run():
    # 로그인 (텔레그램 /admin 일회용 링크)
    dms = h.tg("/admin")
    url = next(re.search(r"https?://\S+/admin/login\?t=\S+", d).group(0) for d in dms if "/admin/login" in d)
    h.client.get("/" + url.split("://", 1)[1].split("/", 1)[1])
    H = {"X-CSRF-Token": h.client.get("/admin/api/csrf").get_json()["token"]}

    def post(name, body):
        r = h.client.post(f"/admin/api/{name}", json=body, headers=H)
        idle()
        return r.get_json() or {"status": r.status_code}

    # ═════ B1 수동 · 예고 ═════
    scenario("B1 수동 · 예고 (같은 방송 합치기 · id 고유 · 시각 미정 · KST→UTC · 영상 URL)")
    d1 = REAL_NOW + timedelta(days=2)
    D1 = kst_date(d1)
    r = post("ingest_preview_manual", {"host": "nonoka", "date": D1, "time": "20:00", "title": "手動A", "confirm": True})
    a = item(lambda i: i.get("title") == "手動A")
    check("B1", "수동 예고 추가 · KST 20:00 → UTC 11:00", r.get("ok") and a and a["scheduled_start"] == f"{D1}T11:00:00Z", (r, a))
    check("B1", "title_manual 보호 · 한글 비움 → needs_tl · source=manual",
          a and a.get("title_manual") and a.get("needs_tl") and a.get("source") == "manual", a)
    post("ingest_preview_manual", {"host": "nonoka", "date": D1, "time": "23:00", "title": "手動B", "confirm": True})
    b = item(lambda i: i.get("title") == "手動B")
    check("B1", "같은 날 3시간 뒤 두 번째 수동 예고 → 별개 항목 · id 다름", b and a and b["id"] != a["id"]
          and item(lambda i: i.get("title") == "手動A"), (a and a.get("id"), b and b.get("id")))
    p = post("ingest_preview_manual", {"host": "nonoka", "date": D1, "time": "20:30", "title": "手動A2", "confirm": False})
    check("B1", "±45분 안 같은 호스트 → 미리보기가 '합쳐짐' 안내 + 대상 id", (p.get("merge") or {}).get("id") == a["id"], p)
    post("ingest_preview_manual", {"host": "nonoka", "date": D1, "time": "20:30", "title": "手動A2", "confirm": True})
    a2 = item(lambda i: i.get("id") == a["id"])
    check("B1", "확정 → 기존 항목에 덮어씀(항목 수 그대로 · 시각 20:30)",
          a2 and a2["title"] == "手動A2" and a2["scheduled_start"] == f"{D1}T11:30:00Z"
          and not item(lambda i: i.get("title") == "手動A"), a2)
    D2 = kst_date(d1 + timedelta(days=1))
    post("ingest_preview_manual", {"host": "yuno", "date": D2, "time_tbd": True, "title": "時刻未定", "confirm": True})
    c = item(lambda i: i.get("title") == "時刻未定")
    check("B1", "시각 미정 → <날짜>T00:00:00Z · time_tbd", c and c["scheduled_start"] == f"{D2}T00:00:00Z" and c.get("time_tbd"), c)
    ss = (d1 + timedelta(days=3)).astimezone(KST).replace(hour=20, minute=0, second=0, microsecond=0)
    h.video("NONOVID0001", "nonoka", "upcoming", z(ss), title="APIが付けた題名")
    post("ingest_preview_manual", {"host": "nonoka", "date": kst_date(ss), "time": "20:00", "title": "手動C",
                                   "url": "https://youtu.be/NONOVID0001", "confirm": True})
    cc = item(lambda i: i.get("video_id") == "NONOVID0001")
    check("B1", "영상 URL 포함 → 확정 뒤 영상 확인으로 upcoming · 직접 쓴 제목 유지",
          cc and cc["state"] == "upcoming" and cc["title"] == "手動C", cc)
    check("B1", "잘못된 입력 거부(호스트 없음 · 시각 없음 · 제목 없음)",
          not post("ingest_preview_manual", {"host": "group", "date": D1, "time": "20:00", "title": "x", "confirm": False}).get("ok")
          and not post("ingest_preview_manual", {"host": "yuno", "date": D1, "title": "x", "confirm": False}).get("ok")
          and not post("ingest_preview_manual", {"host": "yuno", "date": D1, "time": "20:00", "title": "", "confirm": False}).get("ok"))

    # ═════ B2 자동 · 예고 URL ═════
    scenario("B2 자동 · 예고 URL 투입 (YouTube 멤버 · 외부 · 그룹 / 트윗 멤버 · 비멤버 · 공식)")
    t_y = h.rnd(REAL_NOW + timedelta(hours=5))
    h.video("YUNOVID0001", "yuno", "upcoming", z(t_y), title="【歌枠】ユノ")
    p = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=YUNOVID0001", "confirm": False})
    check("B2", "멤버 영상 URL → 미리보기 upcoming", p.get("ok") and p["preview"][0]["state"] == "upcoming", p)
    r = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=YUNOVID0001", "confirm": True})
    check("B2", "확정 → 유노 upcoming 등록", r.get("ok") and (item(lambda i: i.get("video_id") == "YUNOVID0001") or {}).get("state") == "upcoming", r)
    ext_video("EXTVID00001", "UC_external_channel_xxx", z(t_y))
    p = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=EXTVID00001", "confirm": False})
    check("B2", "외부 채널 영상 URL → 거부", not p.get("ok") and "아닙니다" in (p.get("error") or ""), p)
    t_g = h.rnd(REAL_NOW + timedelta(hours=6))
    h.video("GRPVID00001", "group", "upcoming", z(t_g), title="【同時視聴】ゆめみた")
    p = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=GRPVID00001", "confirm": False})
    check("B3", "그룹 영상 URL → 5인 팬아웃 대신 참여 멤버 선택 요청", p.get("choose_members") and not p.get("preview"), p)
    p = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=GRPVID00001", "confirm": False, "members": ["yuno"]})
    pi = (p.get("preview") or [{}])[0]
    check("B3", "1명 선택 → 그 멤버의 일반 예고(host 없음)", pi.get("channel_key") == "yuno" and not pi.get("host")
          and not pi.get("collab_with"), pi)
    r = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=GRPVID00001", "confirm": True,
                                    "members": ["ritsu", "yuno"]})
    g = item(lambda i: i.get("video_id") == "GRPVID00001")
    check("B3", "2명 선택 확정 → channel_order 순 주 레인 + 합동(host=group)",
          r.get("ok") and g and g["channel_key"] == "yuno" and g.get("collab_with") == ["ritsu"] and g.get("host") == "group", g)
    h.reconcile("GRPVID00001")
    h.reconcile()
    g = item(lambda i: i.get("video_id") == "GRPVID00001")
    check("B3", "이후 reconcile(영상 · 전체)이 5인으로 되돌리지 않음", g and g.get("collab_with") == ["ritsu"], g)
    p = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=GRPVID00001", "confirm": False})
    check("B3", "같은 그룹 영상 재투입 → 이미 등록 안내", not p.get("ok") and "이미 등록" in (p.get("error") or ""), p)

    TW["2100000000000000101"] = {"author": "ritsu_yumemita", "text": "明日21時から歌枠配信します🎤 来てね！"}
    p = post("ingest_preview_url", {"url": "https://x.com/i/status/2100000000000000101", "confirm": False})
    check("B2", "멤버 트윗 URL → 작성자 핸들로 호스트 판별 · 개인 예고 미리보기",
          p.get("ok") and p.get("unit") == "ritsu" and p.get("preview"), p)
    TW["2100000000000000102"] = {"author": "someone_else", "text": "明日21時から配信します"}
    p = post("ingest_preview_url", {"url": "https://x.com/someone_else/status/2100000000000000102", "confirm": False})
    check("B2", "비멤버 트윗 → 되묻기(not_member)", p.get("confirm_needed") == "not_member", p)
    p = post("ingest_preview_url", {"url": "https://x.com/someone_else/status/2100000000000000102", "confirm": False,
                                    "force_unit": "miyako"})
    check("B2", "그래도 넣기(force_unit) → 고른 호스트로 미리보기", p.get("ok") and p.get("unit") == "miyako" and p.get("forced"), p)
    h.video("GRPVID00003", "group", "upcoming", z(t_g + timedelta(hours=2)), title="生配信")
    TW["2100000000000000103"] = {"author": "BDP_yumemita",
                                 "text": "本日21時〜生配信！\n#ゆめみた\nhttps://www.youtube.com/watch?v=GRPVID00003"}
    p = post("ingest_preview_url", {"url": "https://x.com/BDP_yumemita/status/2100000000000000103", "confirm": False})
    rows = p.get("preview") or []
    RES_B.append({"obs": "C1-공식 트윗 URL", "choose_members": p.get("choose_members"),
                  "rows": [(x.get("channel_key"), x.get("collab_with"), x.get("host")) for x in rows]})
    check("C1", "[관측] 공식(@BDP) 트윗 URL 안 그룹 영상 · 이름 없음 → 참여 멤버 선택 팝업을 거치는가",
          p.get("choose_members") is True, rows)

    # ═════ B3' 트윗 안 그룹 영상 (OCR 제안) ═════
    scenario("B3 트윗 안 그룹 영상 — 첨부 이미지 OCR 로 참여 멤버 제안 → 관리자 확인")
    h.video("GRPVID00002", "group", "upcoming", z(t_g + timedelta(hours=1)), title="コラボ配信")
    OCR["https://pbs.twimg.com/media/cast1.jpg"] = ["仲町あられ", "宮永ののか"]
    TW["2100000000000000104"] = {"author": "arale_yumemita", "media": ["https://pbs.twimg.com/media/cast1.jpg"],
                                 "text": "今日はコラボ配信！ https://www.youtube.com/watch?v=GRPVID00002"}
    u = "https://x.com/arale_yumemita/status/2100000000000000104"
    p = post("ingest_preview_url", {"url": u, "confirm": False})
    check("B3", "멤버 트윗 안 그룹 영상 → 선택 팝업 + OCR 제안(아라레 · 노노카)",
          p.get("choose_members") and p.get("suggested") == ["arale", "nonoka"] and p.get("ocr") == "ok", p)
    r = post("ingest_preview_url", {"url": u, "confirm": True})
    check("B3", "멤버 없이 확정 → 거부", not r.get("ok"), r)
    r = post("ingest_preview_url", {"url": u, "confirm": True, "members": ["arale", "nonoka"]})
    g2 = item(lambda i: i.get("video_id") == "GRPVID00002")
    check("B3", "고른 멤버로 확정 → 아라레 주 레인 + 노노카 합동", r.get("ok") and g2 and g2["channel_key"] == "arale"
          and g2.get("collab_with") == ["nonoka"], (r, g2))

    # ═════ B4 트윗 + 예고 동시 ═════
    scenario("B4 트윗과 예고를 같이 추가 (with_preview)")
    d4 = REAL_NOW + timedelta(days=1)
    TW["2100000000000000105"] = {"author": "miyako_yumemita", "text": f"{mmdd(d4)} 22時から雑談配信します！"}
    u5 = "https://x.com/miyako_yumemita/status/2100000000000000105"
    p = post("ingest_tweet_url", {"url": u5, "confirm": False, "with_preview": True})
    check("B4", "미리보기에 트윗 + 예고 둘 다", p.get("ok") and (p.get("schedule") or {}).get("ok"), p)
    r = post("ingest_tweet_url", {"url": u5, "confirm": True, "with_preview": True})
    tws = (h.GH.read_json("tweets.json")[0] or {}).get("tweets", {}).get("miyako") or []
    mi = item(lambda i: i.get("channel_key") == "miyako" and (i.get("scheduled_start") or "").startswith(kst_date(d4)[:10]))
    check("B4", "확정 → 트윗 저장 + 미야코 예고 추가", r.get("ok") and (r.get("schedule") or {}).get("ok")
          and any(str(t.get("id")) == "2100000000000000105" for t in tws) and mi, (r, mi))
    TW["2100000000000000106"] = {"author": "miyako_yumemita", "text": "今日のおやつはプリン🍮"}
    r = post("ingest_tweet_url", {"url": "https://x.com/miyako_yumemita/status/2100000000000000106", "confirm": True,
                                  "with_preview": True})
    check("B4", "예고가 아닌 트윗 → 트윗만 저장, 예고 부분은 실패로 알림",
          r.get("ok") and (r.get("schedule") or {}).get("ok") is False, r)

    # ═════ B7 트윗 수정 ═════
    scenario("B7 트윗 수정 (한글 번역만)")
    r = post("edit_tweet", {"unit": "miyako", "tweet_id": "2100000000000000105", "text_ko": "직접 고친 번역"})
    t5 = next((t for t in (h.GH.read_json("tweets.json")[0] or {})["tweets"]["miyako"] if str(t.get("id")) == "2100000000000000105"), {})
    check("B7", "번역 수정 반영 · 원문 그대로 · needs_tl 해제", r.get("ok") and t5.get("text_ko") == "직접 고친 번역"
          and "雑談配信" in (t5.get("text") or "") and not t5.get("needs_tl"), t5)
    check("B7", "빈 번역 거부", not post("edit_tweet", {"unit": "miyako", "tweet_id": "2100000000000000105", "text_ko": " "}).get("ok"))
    post("ingest_tweet_url", {"url": u5, "confirm": True})
    t5b = next((t for t in (h.GH.read_json("tweets.json")[0] or {})["tweets"]["miyako"] if str(t.get("id")) == "2100000000000000105"), {})
    RES_B.append({"obs": "B7-재투입 후 번역", "text_ko": t5b.get("text_ko")})
    check("B7", "[관측] 같은 트윗 재투입 후에도 고친 번역 유지", t5b.get("text_ko") == "직접 고친 번역", t5b.get("text_ko"))

    # ═════ B5 내용 감지 예고 수정 (관리 페이지) ═════
    scenario("B5 내용 감지를 통한 예고 수정 — 관리 페이지 (선택 적용 · 변경 · 취소만)")
    t_am, t_pm = h.rnd(REAL_NOW + timedelta(hours=2)), h.rnd(REAL_NOW + timedelta(hours=8))
    h.video("RITAM000001", "ritsu", "upcoming", z(t_am), title="朝配信")
    h.video("RITPM000001", "ritsu", "upcoming", z(t_pm), title="夜配信")
    h.RSS.clear(); h.RSS["ritsu"] = ["RITAM000001", "RITPM000001"]
    h.reconcile()
    am = item(lambda i: i.get("video_id") == "RITAM000001")
    pm = item(lambda i: i.get("video_id") == "RITPM000001")
    CHANGE["fn"] = lambda raw, cands, nl: {"action": "del", "target_ids": [c["id"] for c in cands if c["title"] != "時刻未定"],
                                           "when": None, "reason": "오늘 방송을 쉰다고 함"}
    TW["2100000000000000107"] = {"author": "ritsu_yumemita", "text": "今日の配信、諸事情によりお休みさせて頂きます…！"}
    u7 = "https://x.com/ritsu_yumemita/status/2100000000000000107"
    p = post("ingest_tweet_url", {"url": u7, "confirm": False, "detect_change": True})
    ch = p.get("change") or {}
    sel = [c["id"] for c in ch.get("candidates", []) if c.get("selected")]
    check("B5", "미리보기 — 취소 감지 · 오늘 두 방송 모두 미리 체크 · 판정 근거",
          ch.get("action") == "del" and am["id"] in sel and pm["id"] in sel and ch.get("reason"), ch)
    r = post("ingest_tweet_url", {"url": u7, "confirm": True, "detect_change": True, "change_action": "del",
                                  "change_ids": [pm["id"]]})
    check("B5", "관리자가 밤 방송만 남기고 확정 → 밤 방송만 삭제",
          r.get("ok") and not item(lambda i: i.get("id") == pm["id"]) and item(lambda i: i.get("id") == am["id"]), r.get("change"))
    check("B5", "취소 = terminate — 영상 URL 12h 재등록 차단", "https://www.youtube.com/watch?v=RITPM000001" in suppressed_urls(),
          suppressed_urls())
    h.reconcile()
    check("B5", "다음 수집(RSS 에 그대로 있어도)이 되살리지 않음", not item(lambda i: i.get("video_id") == "RITPM000001"))
    new_at = t_am + timedelta(hours=1)
    CHANGE["fn"] = lambda raw, cands, nl: {"action": "edit", "target_ids": [am["id"]],
                                           "when": new_at.astimezone(KST).strftime("%m/%d %H:%M"), "reason": "1시간 늦춘다고 함"}
    p = post("ingest_tweet_manual", {"url": "https://x.com/ritsu_yumemita/status/2100000000000000108", "host": "ritsu",
                                     "text": "配信1時間遅らせます！", "confirm": False, "detect_change": True})
    ch = p.get("change") or {}
    check("B5", "변경 감지 → 새 시각 해석", ch.get("action") == "edit" and ch.get("when_iso") == z(new_at), ch)
    post("ingest_tweet_manual", {"url": "https://x.com/ritsu_yumemita/status/2100000000000000108", "host": "ritsu",
                                 "text": "配信1時間遅らせます！", "confirm": True, "detect_change": True,
                                 "change_action": "edit", "change_ids": [am["id"]], "change_when": ch.get("when_iso")})
    am2 = item(lambda i: i.get("id") == am["id"])
    check("B5", "변경 확정 → 예고 시각 이동", am2 and am2["scheduled_start"] == z(new_at), am2)
    h.reconcile()
    am3 = item(lambda i: i.get("id") == am["id"])
    RES_B.append({"obs": "B5-변경 후 reconcile", "after": am3 and am3.get("scheduled_start"), "api": z(t_am)})
    check("B5", "[관측] 영상 있는 예고의 시각 변경이 다음 수집 뒤에도 유지", am3 and am3["scheduled_start"] == z(new_at),
          (am3 or {}).get("scheduled_start"))
    CHANGE["fn"] = lambda raw, cands, nl: {"action": "del", "target_ids": [am["id"]], "when": None, "reason": "쉰다고 함"}
    TW["2100000000000000109"] = {"author": "ritsu_yumemita", "text": "ごめん、今日はお休み！"}
    u9 = "https://x.com/ritsu_yumemita/status/2100000000000000109"
    p = post("ingest_preview_url", {"url": u9, "confirm": False, "detect_change": True})
    check("B5", "예고 글이 아니어도 취소만 감지되면 미리보기 가능", p.get("ok") and not p.get("preview")
          and (p.get("change") or {}).get("action") == "del", p)
    r = post("ingest_preview_url", {"url": u9, "confirm": True, "detect_change": True, "change_action": "del",
                                    "change_ids": [am["id"]]})
    check("B5", "취소만 확정(change_only) → 삭제", r.get("ok") and (r.get("result") or {}).get("change_only") and not item(lambda i: i.get("id") == am["id"]), r)
    h.RSS.clear()

    # ═════ B6 자동 인입 취소 감지 ═════
    scenario("B6 자동 인입 — 配信 게이트 · 선택 삭제 · 근거 로그 · 오판 복구")
    t_n = h.rnd(REAL_NOW + timedelta(hours=3))
    h.video("NONOVID0002", "nonoka", "upcoming", z(t_n), title="ののか雑談")
    h.RSS["nonoka"] = ["NONOVID0002"]
    h.reconcile()
    n2 = item(lambda i: i.get("video_id") == "NONOVID0002")
    CHANGE_CALLS.clear()
    h.ingest_x("今日はお休みします🙏", "宮永ののか🐰🩹", tag="p#x#1tweet-2100000000000000110")
    check("B6", "配信 없는 글 → 판정 호출 없음(게이트)", not CHANGE_CALLS and item(lambda i: i.get("id") == n2["id"]))
    CHANGE["fn"] = lambda raw, cands, nl: {"action": "none", "target_ids": [], "when": None, "reason": "방송 후기라 취소 아님"}
    h.ingest_x("今日の配信ありがとう！楽しかった", "宮永ののか🐰🩹", tag="p#x#1tweet-2100000000000000111")
    ev_none = events(lambda e: "broadcast-change none" in e.get("detail", ""))
    check("B6", "'없음' 판정도 근거와 함께 로그", CHANGE_CALLS and ev_none and "후기" in ev_none[-1]["detail"], ev_none[-1:])
    CHANGE["fn"] = lambda raw, cands, nl: {"action": "del", "target_ids": [c["id"] for c in cands], "when": None,
                                           "reason": "오늘 방송 취소"}
    h.ingest_x("今日の配信お休みします🙏ごめんね", "宮永ののか🐰🩹", tag="p#x#1tweet-2100000000000000112")
    check("B6", "취소 판정 → 삭제 + 12h 재등록 차단 + 근거 로그",
          not item(lambda i: i.get("id") == n2["id"]) and "https://www.youtube.com/watch?v=NONOVID0002" in suppressed_urls()
          and events(lambda e: "broadcast-change del" in e.get("detail", "")))
    # 오판이었다고 치고 관리자가 복구를 시도
    r = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=NONOVID0002", "confirm": True})
    h.reconcile()
    back = item(lambda i: i.get("video_id") == "NONOVID0002")
    RES_B.append({"obs": "B6-오판 복구", "ingest_ok": r.get("ok"), "back": bool(back)})
    # URL 재투입은 12h 재등록 차단 때문에 다음 수집에서 빠진다(차단이 제 역할) — 오판 복구는 LLM 판단 되돌리기(B11)
    check("B6", "URL 재투입은 재등록 차단으로 빠짐 — 복구 수단은 LLM 판단 되돌리기(B11)", back is None, r)
    h.RSS.clear()

    # ═════ T1 삭제 뒤 예약된 영상 확인 ═════
    scenario("C1·F 삭제한 예고의 예약된 영상 확인이 돌 때")
    g = item(lambda i: i.get("video_id") == "GRPVID00001")
    post("delete_preview", {"item_id": g["id"], "suppress": False})
    h.reconcile("GRPVID00001")
    g_back = item(lambda i: i.get("video_id") == "GRPVID00001")
    RES_B.append({"obs": "T1", "back": g_back and (g_back["channel_key"], g_back.get("collab_with"), g_back.get("host"))})
    check("C1", "[관측] 차단 없이 지운 그룹 예고 → 예약 확인 뒤에도 사라진 채", g_back is None,
          g_back and (g_back["channel_key"], g_back.get("collab_with"), g_back.get("host")))

    # ═════ B8 RSS ═════
    scenario("B8 RSS 는 개인 유닛 채널만")
    h.RSS.clear()
    RSS_KEYS.clear()
    h.video("GRPVID00002", "group", "upcoming", z(t_g + timedelta(hours=1)), title="コラボ配信（題名変更）")
    h.reconcile()
    check("B8", "RSS 호출 대상에 그룹 채널 없음", RSS_KEYS and "group" not in RSS_KEYS[-1] and len(RSS_KEYS[-1]) == 5, RSS_KEYS[-1:])
    g2 = item(lambda i: i.get("video_id") == "GRPVID00002")
    check("B8", "이미 추적 중인 그룹 영상은 계속 갱신(제목)", g2 and g2["title"] == "コラボ配信（題名変更）"
          and g2.get("collab_with") == ["nonoka"], g2)

    # ═════ B9 그룹 영상 참여 멤버 근거 · 확인 대기 (2026-09-30 운영자 결정) ═════
    scenario("B9 그룹 영상 — 근거 없으면 확인 대기, 같은 영상 URL 근거로 확정, 다른 인입은 계속")
    OFF = "夢限大みゅーたいぷ"

    def off_tweet(tid, text, media=None):
        TW[tid] = {"author": "BDP_yumemita", "text": text, "media": media or []}
        return h.ingest_x(text, OFF, tag=f"p#x#1tweet-{tid}")

    def pending():
        return {e["video_id"]: e for e in h.client.get("/admin/api/list_group_pending").get_json().get("items", [])}

    t_d2 = h.rnd(REAL_NOW + timedelta(days=2))
    h.video("GRPDAY20001", "group", "upcoming", z(t_d2), title="フリーライブ DAY2")
    DAY2_1 = ("＼全編無料生配信あり📺✨／\n\n#アニメゆめみた 放送記念フリーライブ\n「新宿着陸計画」DAY2🌎\n\n"
              "当日は全編無料配信有🛸✅\n📡こちら\nhttps://youtube.com/live/GRPDAY20001\n\n#バンドリ")
    h.DMS.clear()
    r = off_tweet("2100000000000000201", DAY2_1)
    check("B9", "공식 글 · 이름 / 인원 표현 / 이미지 근거 없음 → 예고에 안 올림 + 확인 대기",
          not item(lambda i: i.get("video_id") == "GRPDAY20001") and "GRPDAY20001" in pending(), (r, pending()))
    check("B9", "확인 대기 DM 1건", sum("참여 멤버 확인 대기" in d for d in h.DMS) == 1, h.DMS[-2:])
    h.DMS.clear()
    off_tweet("2100000000000000202", DAY2_1.replace("#バンドリ", "#ゆめみたフリーライブ_DAY2"))
    check("B9", "같은 영상 재공지(근거 없음) → 대기 유지 · DM 중복 없음",
          "GRPDAY20001" in pending() and not any("참여 멤버 확인 대기" in d for d in h.DMS), h.DMS[-2:])
    # 대기 중에도 다른 인입은 평소대로 — 개인 트윗 배지
    TW["2100000000000000203"] = {"author": "yuno_yumemita", "text": "今日もがんばる☀"}
    h.ingest_x("今日もがんばる☀", "千石ユノ", tag="p#x#1tweet-2100000000000000203")
    yt = (h.GH.read_json("tweets.json")[0] or {}).get("tweets", {}).get("yuno") or []
    check("B9", "확인 대기가 다른 인입을 막지 않음(이어서 온 개인 트윗 반영)",
          any(str(t.get("id")) == "2100000000000000203" for t in (yt if isinstance(yt, list) else [yt])), yt)
    DAY2_2 = ("＼明日開催📢／\n#アニメゆめみた 放送記念フリーライブ\n「新宿着陸計画」DAY2🌎\n"
              "メンバー5人からコメント動画が到着💡✨\n📡こちら\nhttps://youtube.com/live/GRPDAY20001")
    off_tweet("2100000000000000204", DAY2_2)
    g = item(lambda i: i.get("video_id") == "GRPDAY20001")
    check("B9", "같은 영상 URL 을 담은 뒤 공지의 'メンバー5人' → 5인 합동 확정 + 대기에서 빠짐",
          g and g.get("host") == "group" and len([g["channel_key"], *(g.get("collab_with") or [])]) == 5
          and "GRPDAY20001" not in pending(), g)
    check("B9", "확정 즉시 영상 확인 → upcoming", g and g["state"] == "upcoming", g and g["state"])

    # 이미지 OCR 근거 — 사인회처럼 출연자 이름이 이미지에만 있는 글
    t_s = h.rnd(REAL_NOW + timedelta(days=3))
    h.video("SIGNEVT0001", "group", "upcoming", z(t_s), title="サイン会")
    OCR["https://pbs.twimg.com/media/sign.jpg"] = ["仲町あられ", "宮永ののか", "峰月律", "藤都子", "千石ユノ"]
    off_tweet("2100000000000000205", "【📺配信開始📢】\n🛸夢限大みゅーたいぷ 5th Single\nリリース記念 インターネットサイン会🖋\n"
              "📺ご視聴はこちら\nhttps://youtube.com/live/SIGNEVT0001", media=["https://pbs.twimg.com/media/sign.jpg"])
    g = item(lambda i: i.get("video_id") == "SIGNEVT0001")
    check("B9", "글에 근거가 없어도 이미지 OCR 로 5명 판독 → 5인 합동", g and len([g["channel_key"], *(g.get("collab_with") or [])]) == 5, g)
    OCR["https://pbs.twimg.com/media/two.jpg"] = ["峰月律", "藤都子"]
    h.video("GRPTWO00001", "group", "upcoming", z(t_s + timedelta(hours=3)), title="コラボ")
    off_tweet("2100000000000000206", "＼配信開始📡／\n🛸#ゆめみた コラボ生配信\nhttps://youtube.com/live/GRPTWO00001",
              media=["https://pbs.twimg.com/media/two.jpg"])
    g = item(lambda i: i.get("video_id") == "GRPTWO00001")
    check("B9", "OCR 이 읽은 멤버만(리츠 · 미야코) — 5인 아님", g and g["channel_key"] == "ritsu" and g.get("collab_with") == ["miyako"], g)

    # 일일 스케줄의 "全員" 줄
    t_all = h.rnd(REAL_NOW + timedelta(hours=10))
    h.video("ALLMEMB0001", "group", "upcoming", z(t_all), title="全員集合")
    off_tweet("2100000000000000207", h.sched_tweet([f"🛸{h.jst_line_time(t_all)}〜 全員",
                                                    "https://www.youtube.com/watch?v=ALLMEMB0001"]))
    g = item(lambda i: i.get("video_id") == "ALLMEMB0001")
    check("B9", "스케줄 '全員' 줄 → 5인 합동", g and g.get("host") == "group" and len(g.get("collab_with") or []) == 4, g)

    # 경로 ① — 멤버 트윗 안의 그룹 영상
    h.video("MEMGRP00001", "group", "upcoming", z(t_s + timedelta(hours=6)), title="歌ってみた")
    TW["2100000000000000208"] = {"author": "arale_yumemita", "text": "見てね！ https://www.youtube.com/watch?v=MEMGRP00001"}
    h.ingest_x("見てね！ https://www.youtube.com/watch?v=MEMGRP00001", "仲町あられ", tag="p#x#1tweet-2100000000000000208")
    check("B9", "멤버 트윗 · 그룹 영상 · 근거 없음 → 올리지 않고 확인 대기(작성자 자동 포함 안 함)",
          not item(lambda i: i.get("video_id") == "MEMGRP00001") and "MEMGRP00001" in pending(), pending().keys())
    h.video("MEMGRP00002", "group", "upcoming", z(t_s + timedelta(hours=7)), title="【歌ってみた】covered by 仲町あられ・峰月律")
    TW["2100000000000000209"] = {"author": "arale_yumemita", "text": "プレミア公開！ https://www.youtube.com/watch?v=MEMGRP00002"}
    h.ingest_x("プレミア公開！ https://www.youtube.com/watch?v=MEMGRP00002", "仲町あられ", tag="p#x#1tweet-2100000000000000209")
    g = item(lambda i: i.get("video_id") == "MEMGRP00002")
    check("B9", "멤버 트윗 · 영상 제목의 정식 이름(仲町あられ・峰月律) → 그 두 명만", g and g["channel_key"] == "arale"
          and g.get("collab_with") == ["ritsu"], g)
    h.video("MEMGRP00003", "group", "upcoming", z(t_s + timedelta(hours=8)), title="全員集合")
    TW["2100000000000000210"] = {"author": "nonoka_yumemita", "text": "今日22時から！ 全体配信あります！ https://www.youtube.com/watch?v=MEMGRP00003"}
    h.ingest_x("今日22時から！ 全体配信あります！ https://www.youtube.com/watch?v=MEMGRP00003", "宮永ののか🐰🩹",
               tag="p#x#1tweet-2100000000000000210")
    g = item(lambda i: i.get("video_id") == "MEMGRP00003")
    check("B9", "멤버 트윗 · '全体配信' → 5인", g and len([g["channel_key"], *(g.get("collab_with") or [])]) == 5, g)

    # 관리 페이지 — 확인 대기 확정 · 무시
    r = post("resolve_group_pending", {"video_id": "MEMGRP00001", "members": ["yuno", "arale"]})
    g = item(lambda i: i.get("video_id") == "MEMGRP00001")
    check("B9", "관리 페이지 확정(아라레 · 유노 선택) → channel_order 순 합동 + 대기에서 빠짐",
          r.get("ok") and g and g["channel_key"] == "arale" and g.get("collab_with") == ["yuno"] and "MEMGRP00001" not in pending(), (r, g))
    h.video("GRPIGN00001", "group", "upcoming", z(t_s + timedelta(hours=9)), title="何か")
    off_tweet("2100000000000000211", "＼配信開始📡／\n夢限大みゅーたいぷ\nhttps://youtube.com/live/GRPIGN00001")
    r = post("dismiss_group_pending", {"video_id": "GRPIGN00001"})
    check("B9", "관리 페이지 무시 → 대기에서 빠지고 예고엔 없음", r.get("ok") and "GRPIGN00001" not in pending()
          and not item(lambda i: i.get("video_id") == "GRPIGN00001"), r)
    h.reconcile("GRPIGN00001")
    check("B9", "무시한 그룹 영상은 예약된 확인 · 수집이 새로 만들지 않음", not item(lambda i: i.get("video_id") == "GRPIGN00001"))

    # 삭제 → 그 영상의 예약된 확인 취소
    t_c = h.rnd(REAL_NOW + timedelta(hours=5))
    h.video("CANCEL00001", "yuno", "upcoming", z(t_c), title="消す予定")
    h.RSS.clear(); h.RSS["yuno"] = ["CANCEL00001"]
    h.reconcile()
    h.RSS.clear()
    c = item(lambda i: i.get("video_id") == "CANCEL00001")
    before = [j for j in h.q_apply.pending() if j["name"] and "CANCEL00001" in j["name"]]
    post("delete_preview", {"item_id": c["id"], "suppress": False})
    after = [j for j in h.q_apply.pending() if j["name"] and "CANCEL00001" in j["name"]]
    check("C1", "예고 삭제 → 그 영상의 예약된 확인도 취소", before and not after, (before, after))
    # ═════ B10 프리미어(녹화 영상 공개 — 노래 · 뮤비 · 커버)는 방송 카드로 올리지 않음 ═════
    scenario("B10 노래 · 뮤비 등 프리미어(녹화 영상)는 빼고, 歌枠 같은 노래 생방송은 그대로")

    def premiere(vid, ck, ss, title):
        kw = dict(video_id=vid, channel_id=h.CID[ck], title=title, thumbnail=None, live_state="upcoming",
                  scheduled_start=ss, actual_start=None, actual_end=None, concurrent_viewers=None, is_premiere=True)
        h.WORLD[vid] = VideoInfo(**{k: kw.get(k) for k in h._VI})

    def releases():
        st, _ = h.storage.make_store("ops").read_json("video_releases.json")
        return {i["video_id"] for i in (st or {}).get("items", [])}

    t_p = h.rnd(REAL_NOW + timedelta(hours=4))
    premiere("PREMMV00001", "arale", z(t_p), "【MV】新曲")
    h.video("UTAWAKU0001", "arale", "upcoming", z(t_p + timedelta(hours=2)), title="【歌枠】アコギで歌う")
    h.RSS.clear(); h.RSS["arale"] = ["PREMMV00001", "UTAWAKU0001"]
    h.reconcile()
    h.RSS.clear()
    check("B10", "RSS 로 찾은 프리미어(MV) → 예고로 안 만듦 + 기록", not item(lambda i: i.get("video_id") == "PREMMV00001")
          and "PREMMV00001" in releases(), releases())
    check("B10", "歌枠(노래 생방송)은 그대로 upcoming", (item(lambda i: i.get("video_id") == "UTAWAKU0001") or {}).get("state") == "upcoming")
    premiere("PREMCV00001", "ritsu", z(t_p + timedelta(hours=1)), "【歌ってみた】カバー")
    post("ingest_preview_manual", {"host": "ritsu", "date": kst_date(t_p), "time": t_p.astimezone(KST).strftime("%H:%M"),
                                   "title": "手動で入れた", "url": "https://www.youtube.com/watch?v=PREMCV00001", "confirm": True})
    check("B10", "수동 예고에 프리미어 URL → 확정 뒤 영상 확인에서 빠짐", not item(lambda i: i.get("video_id") == "PREMCV00001"))
    premiere("PREMCV00002", "yuno", z(t_p + timedelta(hours=3)), "【歌ってみた】新しいカバー")
    TW["2100000000000000301"] = {"author": "yuno_yumemita", "text": "カバー動画プレミア公開！ https://www.youtube.com/watch?v=PREMCV00002"}
    h.ingest_x("カバー動画プレミア公開！ https://www.youtube.com/watch?v=PREMCV00002", "千石ユノ", tag="p#x#1tweet-2100000000000000301")
    check("B10", "멤버 트윗의 프리미어 URL → 예고 안 만듦 + 기록", not item(lambda i: i.get("video_id") == "PREMCV00002")
          and "PREMCV00002" in releases())
    r = post("ingest_preview_url", {"url": "https://www.youtube.com/watch?v=PREMCV00002", "confirm": False})
    check("B10", "관리 페이지 URL 투입도 거절 + 이유", not r.get("ok") and "프리미어" in (r.get("error") or ""), r)

    # ═════ B11 LLM 판단 기록 · 되돌리기 ═════
    scenario("B11 LLM 판단 — 작업 탭 필터 표시 · 되돌리기")

    def llm_actions():
        return h.client.get("/admin/api/list_llm_actions").get_json().get("items", [])

    t_n = h.rnd(REAL_NOW + timedelta(hours=3, minutes=30))
    h.video("NONOVID0009", "nonoka", "upcoming", z(t_n), title="ののか雑談2")
    h.RSS.clear(); h.RSS["nonoka"] = ["NONOVID0009"]
    h.reconcile()
    CHANGE["fn"] = lambda raw, cands, nl: {"action": "del", "target_ids": [c["id"] for c in cands if "雑談2" in c["title"]],
                                           "when": None, "reason": "오늘 방송을 쉰다고 함(오판 가정)"}
    h.ingest_x("今日の配信お休みします🙏", "宮永ののか🐰🩹", tag="p#x#1tweet-2100000000000000302")
    check("B11", "(전제) LLM 자동 취소 → 삭제 + 재등록 차단", not item(lambda i: i.get("video_id") == "NONOVID0009")
          and "https://www.youtube.com/watch?v=NONOVID0009" in suppressed_urls())
    act = next((a for a in llm_actions() if a["kind"] == "broadcast_change" and a.get("undo")), None)
    check("B11", "LLM 판단 기록 — 요약 · 근거 · 되돌리기 정보", act and "오판" in (act.get("reason") or "") and act["undo"]["type"] == "restore_items", act)
    flows = h.client.get("/admin/api/jobs_overview").get_json().get("flows", [])
    check("B11", "작업 탭 흐름에 LLM 판단 표시(필터 대상)", any(any(x.get("id") == (act or {}).get("id") for x in f.get("llm") or []) for f in flows),
          [f.get("llm") for f in flows if f.get("llm")][:2])
    r = post("undo_llm_action", {"action_id": act["id"]})
    back = item(lambda i: i.get("video_id") == "NONOVID0009")
    check("B11", "되돌리기 → 예고 되살림 + 재등록 차단 해제", r.get("ok") and back
          and "https://www.youtube.com/watch?v=NONOVID0009" not in suppressed_urls(), r)
    h.reconcile(); h.RSS.clear()
    check("B11", "되살린 뒤 수집에도 유지", item(lambda i: i.get("video_id") == "NONOVID0009") is not None)
    r2 = post("undo_llm_action", {"action_id": act["id"]})
    check("B11", "같은 판단 두 번 되돌리기 → 거절", not r2.get("ok") and "이미" in (r2.get("error") or ""), r2)
    none_act = next((a for a in llm_actions() if a["kind"] == "broadcast_change" and not a.get("undo")), None)
    r3 = post("undo_llm_action", {"action_id": (none_act or {}).get("id", "x")})
    check("B11", "검토용 판단(취소 아님) → 되돌리기 없음 안내", none_act and not r3.get("ok") and "검토용" in (r3.get("error") or ""), r3)

    TW["2100000000000000303"] = {"author": "miyako_yumemita", "text": "明日21時から歌枠配信します🎤"}
    h.ingest_x("明日21時から歌枠配信します🎤", "藤都子", tag="p#x#1tweet-2100000000000000303")
    own = next((a for a in llm_actions() if a["kind"] == "own_broadcast" and a.get("undo")), None)
    created = own and item(lambda i: i.get("channel_key") == "miyako" and i.get("source") == "personal"
                           and "21:00" in h.xrelay._jst_hm(i.get("scheduled_start")) if False else True)
    check("B11", "본인 예고 확인(LLM) 기록 · 되돌리기 정보", own is not None, llm_actions()[:3])
    before = [i for i in pv() if i.get("channel_key") == "miyako" and i.get("source") == "personal"]
    r = post("undo_llm_action", {"action_id": own["id"]}) if own else {}
    after = [i for i in pv() if i.get("channel_key") == "miyako" and i.get("source") == "personal"]
    check("B11", "되돌리기 → LLM 이 등록한 본인 예고 지움", r.get("ok") and len(after) == len(before) - 1, (r, len(before), len(after)))

    OCR["https://pbs.twimg.com/media/ocr3.jpg"] = ["峰月律", "千石ユノ"]
    h.video("GRPOCR00003", "group", "upcoming", z(REAL_NOW + timedelta(days=4)), title="コラボ")
    TW["2100000000000000304"] = {"author": "BDP_yumemita", "media": ["https://pbs.twimg.com/media/ocr3.jpg"],
                                 "text": "＼配信開始📡／\n🛸#ゆめみた コラボ生配信\nhttps://youtube.com/live/GRPOCR00003"}
    h.ingest_x(TW["2100000000000000304"]["text"], "夢限大みゅーたいぷ", tag="p#x#1tweet-2100000000000000304")
    oc = next((a for a in llm_actions() if a["kind"] == "ocr_members"
               and (a.get("undo") or {}).get("items", [{}])[0].get("video_id") == "GRPOCR00003"), None)
    check("B11", "이미지 OCR 판정(LLM) 기록", oc is not None and item(lambda i: i.get("video_id") == "GRPOCR00003"))
    r = post("undo_llm_action", {"action_id": oc["id"]}) if oc else {}
    pend = {e["video_id"]: e for e in h.client.get("/admin/api/list_group_pending").get_json().get("items", [])}
    check("B11", "OCR 판정 되돌리기 → 예고에서 빼고 확인 대기로(OCR 제안 유지)", r.get("ok")
          and not item(lambda i: i.get("video_id") == "GRPOCR00003") and pend.get("GRPOCR00003", {}).get("suggested") == ["yuno", "ritsu"],
          (r, pend.get("GRPOCR00003")))

    # ═════ 원칙 ═════
    scenario("원칙 (2차 시나리오 포함)")
    commits = [json.loads(l) for l in open(h.WORK / "_local/data/.commits.jsonl", encoding="utf-8")]
    bad = [c for c in commits if c["thread"] != "q-apply"]
    check("원칙①", f"data 커밋 {len(commits)}건 전부 q-apply 스레드", not bad, bad[:5])
    ext = [e for e in h.TRACE if e["step"] == "external"]
    w = [e for e in ext if e["svc"] in ("groq", "groq-vision", "vxtwitter", "yt-dlp") and e["actor"] == "writer"]
    check("원칙④", "LLM · 비전 · vxtwitter 호출이 쓰기 스레드에서 0건", not w, [(e["svc"], e["call"]) for e in w][:5])


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
    finally:
        h.q_apply.stop(); h.q_enrich.stop()
        b = [r for r in h.RESULTS]
        (HERE / "results_b.json").write_text(json.dumps({"results": b, "observations": RES_B}, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
        ok = sum(r["ok"] for r in b)
        print(f"\n결과: {ok}/{len(b)} 통과")
        for o in RES_B:
            print("  관측", o)
