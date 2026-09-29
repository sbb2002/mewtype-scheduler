"""v4a 로컬 시험판 — 시나리오 재생 검증 하네스.

실제 로컬 러너 구성(Flask 접수 앱 + q-apply · q-enrich 워커 스레드 + LocalStore)을 그대로 쓰고,
외부 서비스(YouTube Data API · RSS · Groq · vxtwitter · yt-dlp · Telegram)만 가짜로 바꾼다.
모든 단계를 TRACE 에 남겨 (1) 흐름도 대조 (2) 애니메이션 데이터로 쓴다.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # 저장소 루트 (ref/v4a/verify → 루트)
WORK = HERE / "run"             # 실행 산출물 — git 에 안 올림
if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.update({
    "V4A_RUNTIME": "local", "LOCAL_DATA_DIR": str(WORK / "_local"), "ALLOW_UNAUTH": "1",
    "INGEST_SECRET": "s", "ADMIN_SECRET": "adminsecret", "YOUTUBE_API_KEY": "dummy",
    "GROQ_API_KEY": "dummy", "TELEGRAM_BOT_TOKEN": "dummy", "TELEGRAM_CHAT_ID": "1",
    "TELEGRAM_WEBHOOK_SECRET": "whsecret", "LOCAL_BIND": "127.0.0.1", "LOCAL_PORT": "8792",
    "INGEST_TEST_TITLES": "jehy",
})
for k in ("MAIN_SERVICE_URL", "HEALTHCHECK_URL", "VERCEL_TOKEN", "HEALTHCHECKS_IO_READONLEY_TOKEN",
          "INGEST_ECHO", "INGEST_DRY_RUN", "GITHUB_TOKEN"):
    os.environ.pop(k, None)

import logging
logging.basicConfig(level=logging.WARNING, format="%(threadName)s %(levelname)s %(name)s %(message)s")

# ── 추적 ──────────────────────────────────────────────────────────────────────
TRACE: list[dict] = []
_TL = threading.Lock()
SCEN = {"name": "setup"}
T0 = time.time()


def role() -> str:
    n = threading.current_thread().name
    if n == "q-apply":
        return "writer"
    if n == "q-enrich":
        return "enrich"
    return "intake"


def tr(step: str, **d) -> None:
    with _TL:
        TRACE.append({"i": len(TRACE), "t": round(time.time() - T0, 3), "scenario": SCEN["name"],
                      "actor": role(), "thread": threading.current_thread().name, "step": step, **d})


# ── 가짜 시계 (reconcile 의 now) ────────────────────────────────────────────────
class Clock:
    def __init__(self):
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def iso(self):
        return self.now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def set(self, dt):
        self.now = dt.replace(microsecond=0)


CLOCK = Clock()
REAL_NOW = CLOCK.now


def z(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 대상 모듈 import + 가짜 외부 서비스 ─────────────────────────────────────────
from src.collector import youtube as ytmod
from src.collector.youtube import VideoInfo
from src.backend import (admin_api, apply, enrich, handlers, jobqueue, llm, local_runner, local_store,
                         notify, storage, telegram_app, tasks, vxtwitter, writers, ytdlp_probe)

CH = json.load(open(ROOT / "config/channels.json", encoding="utf-8"))
CID = {k: v["channel_id"] for k, v in CH["channels"].items()}
WORLD: dict[str, VideoInfo] = {}
RSS: dict[str, list[str]] = {}
SEARCH: dict[str, list[str]] = {}
DMS: list[str] = []
_VI = list(inspect.signature(VideoInfo).parameters)


def video(vid, ck, state, ss, title=None, actual_start=None, actual_end=None):
    kw = dict(video_id=vid, channel_id=CID[ck], title=title or f"{ck} 방송 {vid}",
              thumbnail=f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg", live_state=state,
              scheduled_start=ss, actual_start=actual_start, actual_end=actual_end, concurrent_viewers=None)
    WORLD[vid] = VideoInfo(**{k: kw.get(k) for k in _VI})


def _videos_list(self, ids):
    tr("external", svc="youtube", call="videos.list", n=len(ids))
    return {i: WORLD[i] for i in ids if i in WORLD}


def _search_live(self, cid):
    tr("external", svc="youtube", call="search.list(eventType=live)", channel=cid)
    return list(SEARCH.get(cid, []))


ytmod.YouTubeClient.videos_list = _videos_list
ytmod.YouTubeClient.search_live = _search_live
ytmod.YouTubeClient.channels_list = lambda self, ids: (tr("external", svc="youtube", call="channels.list")
                                                      or {c: f"https://yt3.ggpht.com/{c}=s176" for c in ids})
handlers.fetch_all_rss_video_ids = lambda id_by_key: (tr("external", svc="youtube", call="RSS") or dict(RSS))


def _no_tasks(*a, **k):
    tr("VIOLATION", what="Cloud Tasks TaskQueue 생성 시도(지름길)")
    raise RuntimeError("TaskQueue 사용 금지 (로컬)")


tasks.TaskQueue = _no_tasks

for name in ("extract", "fetch_tweet"):
    setattr(vxtwitter, name, lambda *a, _n=name, **k: (tr("external", svc="vxtwitter", call=_n) or None))
vxtwitter.qrt_id = lambda *a, **k: None


def _find_member_live(cid, title, **k):
    tr("external", svc="yt-dlp", call="streams 탭")
    return {"video_id": "MEMVID00001", "title": title or "メン限", "url": "https://www.youtube.com/watch?v=MEMVID00001",
            "live_status": "is_live"}


ytdlp_probe.find_member_live = _find_member_live


class FakeLLM:
    pass


def _llm(name, fn):
    def w(self, *a, **k):
        tr("external", svc="groq", call=name)
        return fn(*a, **k)
    setattr(llm.LLMClient, name, w)


_llm("translate", lambda t, **k: "KO:" + (t or "")[:20])
_llm("notice_title", lambda body, **k: {"title_ja": (body or "").split("\n")[0][:30], "title_ko": "KO소식"})
_llm("announces_own_broadcast", lambda t, **k: "ありがとう" not in t)
_llm("participation", lambda t, **k: True)
_llm("collab_partners", lambda t, **k: list(k.get("candidate_names") or []))
_llm("broadcast_change", lambda t, **k: {"action": "none", "when": None})
_llm("duplicate_notice", lambda *a, **k: None)


def _tg_send(self, text, *, parse_mode="HTML", silent=False):
    DMS.append(text)
    tr("dm", text=re.sub(r"<[^>]+>", "", text)[:80])
    return True


notify.Telegram.send = _tg_send
handlers._now_iso = lambda: CLOCK.iso()

# 쓰기 · 적재 · 작업 추적
_orig_wj, _orig_wt = local_store.LocalStore.write_json, local_store.LocalStore.write_text


def _wj(self, path, data, *, prev_sha, message):
    r = _orig_wj(self, path, data, prev_sha=prev_sha, message=message)
    if r[0]:
        tr("write", branch=self.branch, path=path)
    return r


def _wt(self, path, text, *, prev_sha=None, message):
    r = _orig_wt(self, path, text, prev_sha=prev_sha, message=message)
    if r[0]:
        tr("write", branch=self.branch, path=path)
    return r


local_store.LocalStore.write_json, local_store.LocalStore.write_text = _wj, _wt

_orig_enq = jobqueue.LocalQueue.enqueue


def _enq(self, kind, args, *, run_at_iso=None, name=None, _holder=None):
    jid = _orig_enq(self, kind, args, run_at_iso=run_at_iso, name=name, _holder=_holder)
    tr("enqueue", queue=self.name, kind=kind, run_at=run_at_iso, name=name,
       scope=(args or {}).get("scope"), video_id=(args or {}).get("video_id"))
    return jid


jobqueue.LocalQueue.enqueue = _enq
BUSY = {"apply": 0, "enrich": 0}


FAIL_KINDS: set = set()


def _wrap_handler(qname, fn):
    def h(kind, args, meta):
        BUSY[qname] += 1
        if kind in FAIL_KINDS:
            BUSY[qname] -= 1
            tr("job-start", queue=qname, kind=kind, attempt=meta.get("attempt"))
            tr("job-fail", queue=qname, kind=kind, error="주입된 실패 (검증용)")
            raise RuntimeError("주입된 실패 (검증용)")
        tr("job-start", queue=qname, kind=kind, scope=(args or {}).get("scope"),
           video_id=(args or {}).get("video_id"), attempt=meta.get("attempt"))
        try:
            out = fn(kind, args, meta)
            tr("job-done", queue=qname, kind=kind)
            return out
        except Exception as e:
            tr("job-fail", queue=qname, kind=kind, error=str(e)[:120])
            raise
        finally:
            BUSY[qname] -= 1
    return h


FAIL_INJECT = {"personal_tweet": False}
_orig_dispatch = writers.dispatch


def _dispatch(kind, gh, args):
    if FAIL_INJECT.get(kind):
        raise RuntimeError("주입된 실패 (검증용)")
    return _orig_dispatch(kind, gh, args)


writers.dispatch = _dispatch

q_apply = jobqueue.LocalQueue("apply", _wrap_handler("apply", apply.handle), max_attempts=3,
                              backoff_sec=(0.2,), on_done=apply.on_done, on_dead=apply.on_dead,
                              persist_path=str(WORK / "_local/queue/apply.json"))
q_enrich = jobqueue.LocalQueue("enrich", _wrap_handler("enrich", enrich.handle), max_attempts=2,
                               backoff_sec=(0.2,), persist_path=str(WORK / "_local/queue/enrich.json"))
apply.set_queue(q_apply)
enrich.set_queue(q_enrich)
q_apply.start()
q_enrich.start()
app = local_runner.build_app()


@app.before_request
def _trace_req():
    from flask import request
    if request.method == "POST" and request.path.startswith("/admin/api/"):
        tr("action", label="관리 페이지 · " + request.path.rsplit("/", 1)[-1], trigger="admin")
    elif request.path == "/admin/login":
        tr("action", label="관리 페이지 로그인 링크 열기", trigger="admin")
    tr("http-in", method=request.method, path=request.path)


client = app.test_client()


# ── 도우미 ────────────────────────────────────────────────────────────────────
def idle(timeout=30):
    """지금 실행할 작업(run_at ≤ 실제 지금)이 없고 워커가 쉬고 있을 때까지."""
    end = time.time() + timeout
    while time.time() < end:
        now = z(datetime.now(timezone.utc))
        due = [j for j in q_apply.pending() + q_enrich.pending() if j["run_at_iso"] <= now]
        if not due and BUSY["apply"] == 0 and BUSY["enrich"] == 0:
            time.sleep(0.15)
            if BUSY["apply"] == 0 and BUSY["enrich"] == 0:
                return True
        time.sleep(0.05)
    return False


def ingest_x(text, title, tag=""):
    first = next((l for l in text.split(chr(10)) if l.strip() and "#" not in l[:2]), text)[:26]
    tr("action", label=f"X 알림 · {title} · {first}", trigger="upstream")
    r = client.post("/ingest", data={"source": "x", "text": text, "title": title, "template": "", "tag": tag},
                    headers={"X-Ingest-Secret": "s"})
    idle()
    return r.get_json()


def ingest_yt(video_id, kind, title):
    k = kind.split(":")[1].replace("NOTIFICATION_TYPE_", "") if ":" in kind else kind
    tr("action", label=f"YouTube 알림 · {k} · {video_id}", trigger="upstream")
    r = client.post("/ingest", data={"source": "yt", "video_id": video_id, "title": title, "kind": kind, "tag": ""},
                    headers={"X-Ingest-Secret": "s"})
    idle()
    return r.get_json()


def tg(text):
    tr("action", label=f"텔레그램 {text}", trigger="telegram")
    DMS.clear()
    client.post("/telegram", json={"message": {"chat": {"id": 1}, "text": text}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "whsecret"})
    idle()
    return list(DMS)


def reconcile(video_id=None, mode="light", at=None):
    if at is not None:
        CLOCK.set(at)
    kst = CLOCK.now.astimezone(timezone(timedelta(hours=9))).strftime("%H:%M")
    tr("action", label=(f"reconcile(영상 {video_id})" if video_id else f"reconcile(전체 · {mode})") + f" — 시각 {kst} KST",
       trigger="schedule")
    args = {"scope": "video", "video_id": video_id} if video_id else {"scope": "all", "mode": mode}
    r = apply.submit("reconcile", args, wait=True)
    idle()
    return r


GH = storage.make_store("data")


def pv():
    return (GH.read_json("preview.json")[0] or {}).get("items", [])


def item(pred):
    return next((i for i in pv() if pred(i)), None)


def archive():
    return (GH.read_json("preview_archive.json")[0] or {}).get("items", [])


RESULTS: list[dict] = []


def check(feature, desc, cond, detail=""):
    RESULTS.append({"scenario": SCEN["name"], "feature": feature, "check": desc, "ok": bool(cond),
                    "detail": str(detail)[:300]})
    tr("check", feature=feature, desc=desc, ok=bool(cond))
    print(("  PASS " if cond else "  FAIL ") + f"[{feature}] {desc}" + ("" if cond else f"  → {str(detail)[:200]}"))


def scenario(name):
    SCEN["name"] = name
    print(f"\n== {name}")
    tr("scenario", title=name)


JST = timezone(timedelta(hours=9))


def jst_line_time(dt):
    """JST 시각 → 공식 스케줄 표기 (자정 넘으면 24~29시 표기)."""
    j = dt.astimezone(JST)
    base = REAL_NOW.astimezone(JST).date()
    h = j.hour + 24 * (j.date() - base).days
    return f"{h}:{j.minute:02d}"


def sched_tweet(lines):
    d = REAL_NOW.astimezone(JST)
    wd = "月火水木金土日"[d.weekday()]
    return "🛸#ゆめみた\n" + f"{d.month}/{d.day}({wd}) 配信スケジュール\n" + "\n".join(lines) + "\n#バンドリ #ゆめみた"


def rnd(dt, m=5):
    dt = dt.replace(second=0, microsecond=0)
    return dt + timedelta(minutes=(m - dt.minute % m) % m)


# ══════════════════════════════════════════════════════════════════════════════
def run():
    # F1 · F2 · F4 · D2 · D6 · D7 — 정기 감지 → 정밀 추적 → 종료 → 복구 → out
    scenario("F1·F2 정기 감지와 방송별 정밀 추적 (D2·D6·D7)")
    ss = rnd(REAL_NOW + timedelta(hours=3))
    video("VUP00000001", "arale", "upcoming", z(ss), title="【歌枠】アコギ")
    RSS.clear(); RSS["arale"] = ["VUP00000001"]
    reconcile(at=REAL_NOW)
    it = item(lambda i: i.get("video_id") == "VUP00000001")
    check("1", "RSS+videos.list 로 upcoming 등록", it and it["state"] == "upcoming", it)
    wake = [j for j in q_apply.pending() if j["name"] and "VUP00000001" in j["name"]]
    check("2", "다음 확인이 reconcile(영상) 작업으로 예약 (예정 20분 전)",
          wake and wake[0]["run_at_iso"] == z(ss - timedelta(minutes=20)), wake)
    reconcile("VUP00000001", at=ss - timedelta(minutes=19))
    check("D2", "예정 19분 전 → watching", item(lambda i: i.get("video_id") == "VUP00000001")["state"] == "watching")
    video("VUP00000001", "arale", "live", z(ss), title="【歌枠】アコギ", actual_start=z(ss + timedelta(minutes=1)))
    DMS.clear()
    reconcile("VUP00000001", at=ss + timedelta(minutes=2))
    check("2", "폴링으로 live 전환", item(lambda i: i.get("video_id") == "VUP00000001")["state"] == "live")
    check("19", "live 시작 알림 DM", any("방송 시작" in d or "LIVE" in d or "🔴" in d for d in DMS), DMS)
    video("VUP00000001", "arale", "none", z(ss), title="【歌枠】アコギ", actual_start=z(ss + timedelta(minutes=1)),
          actual_end=z(ss + timedelta(minutes=80)))
    reconcile("VUP00000001", at=ss + timedelta(minutes=82))
    check("2", "API none → end", item(lambda i: i.get("video_id") == "VUP00000001")["state"] == "end")
    video("VUP00000001", "arale", "live", z(ss), title="【歌枠】アコギ", actual_start=z(ss + timedelta(minutes=1)))
    reconcile("VUP00000001", at=ss + timedelta(minutes=90))
    check("D6", "end 창 안에서 같은 영상 live 재관측 → live 복구",
          item(lambda i: i.get("video_id") == "VUP00000001")["state"] == "live")
    video("VUP00000001", "arale", "none", z(ss), title="【歌枠】アコギ", actual_start=z(ss + timedelta(minutes=1)),
          actual_end=z(ss + timedelta(minutes=95)))
    reconcile("VUP00000001", at=ss + timedelta(minutes=96))
    reconcile("VUP00000001", at=ss + timedelta(minutes=130))
    check("4·D7", "end 30분 뒤 out → 아카이브", item(lambda i: i.get("video_id") == "VUP00000001") is None
          and any(a.get("video_id") == "VUP00000001" for a in archive()))
    RSS.clear()
    CLOCK.set(REAL_NOW)

    # F7 · D13 · D19 — 공식 스케줄 (URL 없음 + 합동 URL)
    scenario("F7 공식 스케줄 트윗 (D13 영상 URL 즉시 확인 · D19 원문 보존)")
    t_yuno = rnd(REAL_NOW + timedelta(hours=4))
    t_col = rnd(REAL_NOW + timedelta(hours=5))
    video("COLLAB00001", "arale", "upcoming", z(t_col), title="【合同】あられ×都子")
    text = sched_tweet([f"🎤{jst_line_time(t_yuno)}〜 千石ユノ", "youtube.com/@yuno_yumemita",
                        f"💪{jst_line_time(t_col)}〜 仲町あられ×藤都子", "youtube.com/watch?v=COLLAB00001"])
    ingest_x(text, "夢限大みゅーたいぷ", tag="p#x#1tweet-2100000000000000001")
    y = item(lambda i: i.get("channel_key") == "yuno" and i.get("source") == "x-relay")
    c = item(lambda i: i.get("video_id") == "COLLAB00001")
    check("7", "URL 없는 행 → announced", y and y["state"] == "announced", y)
    check("D13", "영상 URL 행 → 접수 시 videos.list 확인 → upcoming + API 제목", c and c["state"] == "upcoming"
          and c["title"] == "【合同】あられ×都子" and c.get("collab_with") == ["miyako"], c)
    raw_files = list((WORK / "_local/raw/raw").glob("*.jsonl"))
    check("D19", "공식 스케줄 원문 보존 (_local/raw)", raw_files and "配信スケジュール" in raw_files[0].read_text(encoding="utf-8"))

    # F8 · F9 — 개인 트윗
    scenario("F8·F9 개인 트윗 (배지 · 예고 텍스트 · 예고 URL)")
    ingest_x("おはよう！今日もがんばる☀", "千石ユノ", tag="p#x#1tweet-2100000000000000002")
    tw = (GH.read_json("tweets.json")[0] or {}).get("tweets", {}).get("yuno")
    check("8", "개인 트윗 → tweets.json", tw and "おはよう" in json.dumps(tw, ensure_ascii=False), tw)
    ingest_x("明日21時から歌枠配信します🎤 来てね！", "峰月律", tag="p#x#1tweet-2100000000000000003")
    r = item(lambda i: i.get("channel_key") == "ritsu" and i.get("source") == "personal")
    check("9c", "URL 없는 개인 예고 → 정규식 + LLM 확인 → announced", r and r["state"] == "announced", r)
    t_p = rnd(REAL_NOW + timedelta(hours=2))
    video("PERSVID0001", "nonoka", "upcoming", z(t_p), title="【ギター】弾き語り")
    ingest_x("このあと配信するよ！ https://www.youtube.com/watch?v=PERSVID0001", "宮永ののか🐰🩹",
             tag="p#x#1tweet-2100000000000000004")
    p = item(lambda i: i.get("video_id") == "PERSVID0001")
    check("9a", "YouTube URL 개인 예고 → videos.list 확정 → upcoming", p and p["state"] == "upcoming", p)
    ingest_x("RT @ritsu_yumemita: 配信ありがとう！", "千石ユノ", tag="p#x#1tweet-2100000000000000005")

    # F10 · D16 — 소식
    scenario("F10 소식 (D16 리트윗 제외)")
    before = len((GH.read_json("notices.json")[0] or {}).get("notices", []))
    ingest_x("RT @bang_dream_info: ／\nTVアニメ「バンドリ！ ゆめ∞みた」\n最終話放送記念リポストキャンペーン🛸✨\n＼\n10/9(木)23:59まで",
             "夢限大みゅーたいぷ", tag="p#x#1tweet-2100000000000000006")
    after_rt = len((GH.read_json("notices.json")[0] or {}).get("notices", []))
    check("D16", "리트윗 → 소식 아님", after_rt == before, after_rt)
    d = (REAL_NOW + timedelta(days=6)).astimezone(JST)
    ingest_x(f"💿夢限大みゅーたいぷ 6th Single💿\n{d.month}/{d.day}発売決定！\n予約受付中です✨\n#ゆめみた",
             "夢限大みゅーたいぷ", tag="p#x#1tweet-2100000000000000007")
    ns = (GH.read_json("notices.json")[0] or {}).get("notices", [])
    check("10", "공식 소식 → notices.json", len(ns) == before + 1, ns[-1:] if ns else ns)

    # F12 · D1 · D2 · D3 — YT 알림
    scenario("F12 YouTube 알림 (D1 시작 · D2 30분 전 · D3 URL 없는 예고 ±45분)")
    t_r = rnd(REAL_NOW + timedelta(minutes=35))
    ingest_x(sched_tweet([f"💭{jst_line_time(t_r)}〜 藤都子", "youtube.com/@miyako_yumemita"]),
             "夢限大みゅーたいぷ", tag="p#x#1tweet-2100000000000000008")
    ph = item(lambda i: i.get("channel_key") == "miyako" and not i.get("video_id") and i.get("source") == "x-relay"
              and i.get("scheduled_start") == z(t_r))
    check("7", "URL 없는 예고 (미야코, 35분 뒤)", ph and ph["state"] == "announced", ph)
    video("MIYAKO00001", "miyako", "upcoming", z(t_r + timedelta(minutes=5)), title="【雑談】みやこの部屋")
    ingest_yt("MIYAKO00001", "a:NOTIFICATION_TYPE_LIVESTREAM_TUNEIN:1", "【雑談】みやこの部屋")
    def _near(i, t, sec=45 * 60):
        ss_ = i.get("scheduled_start")
        return ss_ and abs((datetime.fromisoformat(ss_.replace("Z", "+00:00")) - t).total_seconds()) <= sec
    mi = [i for i in pv() if i.get("channel_key") == "miyako" and _near(i, t_r)]
    m1 = item(lambda i: i.get("video_id") == "MIYAKO00001")
    check("D3", "30분 전 알림 → 자리표시가 영상과 합쳐짐 (미야코 항목 1개)", len(mi) == 1 and m1 is not None, mi)
    check("D2", "30분 전 알림 → watching (20분 창보다 일러도 유지)", m1 and m1["state"] == "watching"
          and m1.get("yt_tunein") is True, m1)
    reconcile("MIYAKO00001", at=REAL_NOW + timedelta(minutes=2))
    check("D2", "다음 reconcile 에서도 watching 유지 (되돌림 없음)",
          item(lambda i: i.get("video_id") == "MIYAKO00001")["state"] == "watching")
    DMS.clear()
    ingest_yt("MIYAKO00001", "a:NOTIFICATION_TYPE_SUBSCRIPTION_LIVESTREAM_START:1", "【雑談】みやこの部屋")
    check("D1", "시작 알림 → live (API 는 아직 upcoming)", item(lambda i: i.get("video_id") == "MIYAKO00001")["state"] == "live")
    reconcile("MIYAKO00001", at=REAL_NOW + timedelta(minutes=5))
    check("D1", "API 가 아직 upcoming 이어도 live 유지 (end 로 안 떨어짐)",
          item(lambda i: i.get("video_id") == "MIYAKO00001")["state"] == "live")
    video("MIYAKO00001", "miyako", "live", z(t_r + timedelta(minutes=5)), title="【雑談】みやこの部屋",
          actual_start=z(REAL_NOW + timedelta(minutes=1)))
    reconcile("MIYAKO00001", at=REAL_NOW + timedelta(minutes=12))
    check("D1", "폴링 안전망이 live 확인", item(lambda i: i.get("video_id") == "MIYAKO00001")["state"] == "live")

    # D4 — URL 없는 예고: +2분 검색 · +1시간 out
    scenario("D4 URL 없는 예고 — 시작+2분 search.list 1회 · +1시간 out")
    t4 = rnd(REAL_NOW + timedelta(minutes=50))
    ingest_x(sched_tweet([f"🎮{jst_line_time(t4)}〜 宮永ののか", "youtube.com/@nonoka_yumemi…",
                          f"🎤{jst_line_time(t4)}〜 峰月律", "youtube.com/@ritsu_yumemita"]),
             "夢限大みゅーたいぷ", tag="p#x#1tweet-2100000000000000009")
    SEARCH[CID["nonoka"]] = ["NONOKA00001"]
    video("NONOKA00001", "nonoka", "live", z(t4), title="【ゲーム】", actual_start=z(t4 + timedelta(minutes=1)))
    n_search_before = sum(1 for e in TRACE if e.get("call", "").startswith("search.list"))
    reconcile(at=t4 + timedelta(minutes=2))
    n_search = sum(1 for e in TRACE if e.get("call", "").startswith("search.list")) - n_search_before
    nn = item(lambda i: i.get("channel_key") == "nonoka" and i.get("scheduled_start") == z(t4))
    check("D4", "+2분 search.list → 찾으면 video_id 부여", nn and nn.get("video_id") == "NONOKA00001", nn)
    check("D4", "search.list 는 URL 없는 예고마다 1회 (2건 → 2회)", n_search == 2, n_search)
    reconcile("NONOKA00001", at=t4 + timedelta(minutes=3))
    check("D4", "찾은 영상 → reconcile(영상) → live", item(lambda i: i.get("video_id") == "NONOKA00001")["state"] == "live")
    reconcile(at=t4 + timedelta(minutes=20))
    n2 = sum(1 for e in TRACE if e.get("call", "").startswith("search.list")) - n_search_before
    check("D4", "재실행해도 검색 반복 없음", n2 == 2, n2)
    reconcile(at=t4 + timedelta(minutes=61))
    rr = item(lambda i: i.get("channel_key") == "ritsu" and i.get("scheduled_start") == z(t4))
    check("D4", "못 찾은 예고 → +1시간 out (아카이브)", rr is None and any(
        a.get("channel_key") == "ritsu" and a.get("scheduled_start") == z(t4) for a in archive()))
    CLOCK.set(REAL_NOW)

    # F11 — 회원 전용 라이브
    scenario("F11 회원 전용 라이브 (알림 + yt-dlp)")
    ingest_yt("default", "a:NOTIFICATION_TYPE_SPONSORSHIPS_LIVESTREAM_START:1",
              "仲町あられ -Nakamachi Arale- / 夢限大みゅーたいぷ 실시간 스트리밍 시작: 🔒メン限雑談")
    mem = item(lambda i: i.get("video_id") == "MEMVID00001")
    check("11", "회원 전용 시작 알림 → yt-dlp video_id → live · membership", mem and mem["state"] == "live"
          and mem.get("membership") is True, mem)

    # F6 — 번역 재시도 (가공 큐)
    scenario("F6 번역 재시도 (가공 큐 → 적용 큐)")
    need = [i for i in pv() if i.get("needs_tl")]
    reconcile(at=REAL_NOW + timedelta(minutes=1))
    time.sleep(0.3); idle()
    left = [i for i in pv() if i.get("needs_tl")]
    check("6", "needs_tl 항목이 가공 큐 수집 → 적용 큐 반영으로 번역됨", need and not left,
          {"before": len(need), "after": len(left)})
    en = [e for e in TRACE if e["scenario"] == SCEN["name"] and e["step"] == "job-start"]
    check("6", "순서: reconcile(q-apply) → translate_sweep(q-enrich) → apply_translation(q-apply)",
          [e["kind"] for e in en][:3] == ["reconcile", "translate_sweep", "apply_translation"], [e["kind"] for e in en])

    # F13~F17 · F27 — 관리 페이지 · 비상 명령
    scenario("F27·F13~F17 관리 페이지 (일회용 로그인 · 조작) + 텔레그램 비상 명령")
    dms = tg("/admin")
    url = next((re.search(r"https?://\S+/admin/login\?t=\S+", d).group(0) for d in dms
                if "/admin/login" in d), None)
    check("27", "/admin → 일회용 로그인 링크 DM", url, dms)
    path = url.split("://", 1)[1].split("/", 1)[1]
    r = client.get("/" + path)
    check("27", "링크 열기 → 세션 쿠키", r.status_code == 302, r.status_code)
    check("27", "같은 링크 재사용 → 403", client.get("/" + path).status_code == 403)
    tok = client.get("/admin/api/csrf").get_json()["token"]
    H = {"X-CSRF-Token": tok}
    lst = client.get("/admin/api/list_preview").get_json()
    check("13", "관리 API 읽기 (예고 목록)", len(lst.get("items", [])) >= 3, len(lst.get("items", [])))
    tgt = item(lambda i: i.get("video_id") == "COLLAB00001")
    res = client.post("/admin/api/edit_preview", json={"item_id": tgt["id"], "patch": {"title": "수정된 제목"},
                                                       "seen": {"title": tgt["title"]}}, headers=H).get_json()
    idle()
    check("14d", "예고 편집 → 적용 큐 → 반영", res.get("ok") and item(lambda i: i.get("id") == tgt["id"])["title"] == "수정된 제목", res)
    res = client.post("/admin/api/edit_preview", json={"item_id": tgt["id"], "patch": {"title": "또"},
                                                       "seen": {"title": "옛 값"}}, headers=H).get_json()
    check("14d", "열람 값 충돌 → conflict", res.get("error") == "conflict:title", res)
    check("CSRF", "CSRF 없이 POST → 403", client.post("/admin/api/set_paused", json={"paused": True}).status_code == 403)
    res = client.post("/admin/api/delete_preview", json={"item_id": tgt["id"], "suppress": True}, headers=H).get_json()
    idle()
    adm = (GH.read_json("admin_state.json")[0] or {})
    check("14g", "예고 삭제 + 재등록 차단(ops)", res.get("ok") and item(lambda i: i.get("id") == tgt["id"]) is None
          and any("COLLAB00001" in (s.get("url") or "") for s in adm.get("suppress", [])), res)
    reconcile(at=REAL_NOW + timedelta(minutes=2))
    check("14g", "차단된 URL 은 reconcile 이 다시 싣지 않음", item(lambda i: i.get("video_id") == "COLLAB00001") is None)
    res = client.post("/admin/api/set_paused", json={"paused": True}, headers=H).get_json()
    check("16", "관리 페이지 일시정지 → ops/control.json", res.get("ok") and
          json.load(open(WORK / "_local/ops/control.json", encoding="utf-8"))["paused"] is True, res)
    n_before = len(pv())
    ingest_x(sched_tweet([f"🎤{jst_line_time(rnd(REAL_NOW + timedelta(hours=6)))}〜 仲町あられ"]), "夢限大みゅーたいぷ")
    check("16", "일시정지 중 ingest 무시", len(pv()) == n_before)
    res = client.post("/admin/api/set_paused", json={"paused": False}, headers=H).get_json()
    check("16", "재개 → reconcile(전체) 적재 (자기 호출 없음)", res.get("ok") and res.get("job_id"), res)
    idle()
    hist = client.get("/admin/api/list_history").get_json()
    check("14j", "작업 이력(ops/history.json)", [h["action"] for h in hist][:2] == ["set_paused", "set_paused"], hist[:3])
    dms = tg("/status")
    check("D24", "/status 비상 명령 응답", dms, dms)
    dms = tg("/edit preview")
    check("D24", "마법사 명령 → 관리 페이지 안내", any("관리 페이지" in d for d in dms), dms)
    dms = tg("/pause")
    ctrl = json.load(open(WORK / "_local/ops/control.json", encoding="utf-8"))
    check("16", "/pause 비상 명령 → ops control", ctrl["paused"] is True)
    tg("/resume")
    ctrl = json.load(open(WORK / "_local/ops/control.json", encoding="utf-8"))
    check("16", "/resume → 재개 + reconcile 적재", ctrl["paused"] is False)

    # F20 · F18 — 유실 원문
    # F3 · F5 — 그룹 채널 팬아웃 · 아바타
    scenario("F3·F5 그룹 공식 채널 5인 팬아웃 · 아바타 (baseline)")
    tg_ = rnd(REAL_NOW + timedelta(hours=7))
    video("GRPVID00001", "group", "upcoming", z(tg_), title="【5人】同時視聴")
    RSS.clear(); RSS["group"] = ["GRPVID00001"]
    reconcile(mode="baseline", at=REAL_NOW)
    g = item(lambda i: i.get("video_id") == "GRPVID00001")
    check("3", "그룹 채널 영상 → 5인 레인 팬아웃(host=group)", g and g.get("host") == "group"
          and len(g.get("collab_with") or []) == 4, g)
    chs = (GH.read_json("preview.json")[0] or {}).get("channels", {})
    check("5", "baseline → channels.list 아바타 반영", all((chs.get(k) or {}).get("avatar") for k in
                                                           ("arale", "yuno", "nonoka", "ritsu", "miyako")))
    RSS.clear()

    # F9b — 비YouTube URL → 소식
    scenario("F9b 개인 트윗 비YouTube URL → 소식")
    n0 = len((GH.read_json("notices.json")[0] or {}).get("notices", []))
    d9 = (REAL_NOW + timedelta(days=2)).astimezone(JST)
    ingest_x(f"{d9.month}/{d9.day} 20時からbilibiliで配信します！ https://live.bilibili.com/12345678", "仲町あられ",
             tag="p#x#1tweet-2100000000000000011")
    ns = (GH.read_json("notices.json")[0] or {}).get("notices", [])
    check("9b", "비YouTube URL 개인 트윗 → notices.json (preview 아님)", len(ns) == n0 + 1, ns[-1:])

    # F14a~F15 — 관리 페이지 원문 투입 · 소식/트윗 편집 · 삭제 · 수동 번역
    scenario("F14a~F15 관리 페이지 원문 투입 · 소식/트윗 편집 · 삭제 · 번역")
    t14 = rnd(REAL_NOW + timedelta(hours=9))
    raw14 = sched_tweet([f"🎤{jst_line_time(t14)}〜 峰月律", "youtube.com/@ritsu_yumemita"])
    pv14 = client.post("/admin/api/ingest_preview_raw", json={"raw": raw14, "confirm": False}, headers=H).get_json()
    n_before = len(pv())
    check("14a", "원문 투입 미리보기 — 반영 안 함", pv14.get("ok") and len(pv14.get("preview") or []) == 1
          and len(pv()) == n_before, pv14)
    r14 = client.post("/admin/api/ingest_preview_raw", json={"raw": raw14, "confirm": True}, headers=H).get_json()
    idle()
    check("14a", "확정 → 적용 큐 → preview 반영", r14.get("ok") and item(lambda i: i.get("channel_key") == "ritsu"
          and i.get("scheduled_start") == z(t14)), r14)
    d14 = (REAL_NOW + timedelta(days=9)).astimezone(JST)
    nraw = "\n".join(["🎪イベント出演決定！", f"{d14.month}/{d14.day} ゆめみたファンミーティング開催✨",
                      "詳細は公式サイトへ"])
    pn = client.post("/admin/api/ingest_notice_raw", json={"raw": nraw, "confirm": False}, headers=H).get_json()
    check("14b", "소식 원문 미리보기", pn.get("ok") and (pn.get("preview") or {}).get("parsed"), pn)
    rn = client.post("/admin/api/ingest_notice_raw", json={"raw": nraw, "confirm": True}, headers=H).get_json()
    idle()
    ns = (GH.read_json("notices.json")[0] or {}).get("notices", [])
    fan = next((n for n in ns if "ファンミーティング" in (n.get("body_raw") or "")), None)
    check("14b", "소식 확정 → notices.json", rn.get("ok") and fan, rn)
    re_ = client.post("/admin/api/edit_notice", json={"nid": fan["id"], "patch": {"title": "팬미팅 개최"}},
                      headers=H).get_json()
    idle()
    ns = (GH.read_json("notices.json")[0] or {}).get("notices", [])
    check("14e", "소식 편집", re_.get("ok") and any(n.get("title") == "팬미팅 개최" for n in ns), re_)
    tr_ = client.post("/admin/api/translate", json={"target": "notice", "key": fan["id"]}, headers=H).get_json()
    idle()
    check("15", "수동 번역(소식) — 이미 번역돼 있어도 덮어씀(force)", tr_.get("ok"), tr_)
    rd = client.post("/admin/api/delete_notice", json={"nid": fan["id"]}, headers=H).get_json()
    idle()
    ns = (GH.read_json("notices.json")[0] or {}).get("notices", [])
    check("14h", "소식 삭제", rd.get("ok") and not any(n.get("id") == fan["id"] for n in ns), rd)
    pt = client.post("/admin/api/ingest_tweet_raw", json={"raw": "新曲の練習中🎸", "unit": "arale", "confirm": False},
                     headers=H).get_json()
    check("14c", "트윗 원문 미리보기(번역 포함)", pt.get("ok") and (pt.get("preview") or {}).get("text_ko"), pt)
    rt = client.post("/admin/api/ingest_tweet_raw", json={"raw": "新曲の練習中🎸", "unit": "arale", "confirm": True},
                     headers=H).get_json()
    idle()
    tw = (GH.read_json("tweets.json")[0] or {}).get("tweets", {}).get("arale") or []
    check("14c·14f", "트윗 투입 → tweets.json", rt.get("ok") and any("新曲" in (t.get("text") or "") for t in tw), rt)
    one = item(lambda i: i.get("channel_key") == "ritsu" and i.get("scheduled_start") == z(t14))
    nt = client.post("/admin/api/translate", json={"target": "preview", "key": one["id"]}, headers=H).get_json()
    check("15", "제목 없는 예고 번역 → 분명한 오류", nt.get("error", "").startswith("제목이 없는"), nt)
    one = item(lambda i: i.get("video_id") == "GRPVID00001")
    tp = client.post("/admin/api/translate", json={"target": "preview", "key": one["id"]}, headers=H).get_json()
    idle()
    check("15", "수동 번역(예고)", tp.get("ok") and (item(lambda i: i.get("id") == one["id"]) or {}).get("title_ko"), tp)
    rdt = client.post("/admin/api/delete_tweet", json={"unit": "arale"}, headers=H).get_json()
    idle()
    check("14i", "트윗 삭제", rdt.get("ok") and not (GH.read_json("tweets.json")[0] or {}).get("tweets", {}).get("arale"), rdt)
    hist = client.get("/admin/api/list_history?limit=20").get_json()
    check("14j", "조작마다 작업 이력", {"ingest_preview", "ingest_notice", "edit_notice", "delete_notice", "ingest_tweet",
                                    "delete_tweet", "translate"} <= {h["action"] for h in hist}, [h["action"] for h in hist])

    scenario("F20·F18 유실 원문 (마지막 시도 실패 → 유실 큐 → 관리 페이지 재투입)")
    FAIL_INJECT["personal_tweet"] = True
    DMS.clear()
    ingest_x("今日のおやつはプリン🍮", "藤都子", tag="p#x#1tweet-2100000000000000010")
    time.sleep(1.0); idle()
    lost = client.get("/admin/api/list_lost").get_json()
    mine = [l for l in lost if "プリン" in (l.get("raw") or "")]
    check("20", "결과를 기다린 작업 실패 → 유실 원문 1건(원문 그대로 · kind=personal_tweet)", len(mine) == 1
          and mine[0]["raw"] == "今日のおやつはプリン🍮" and mine[0]["kind"] == "personal_tweet", mine)
    loss_dms = [d for d in DMS if "유실" in d or "작업 실패" in d]
    check("20", "유실 알림 DM 1건 (중복 없음)", len(loss_dms) == 1, loss_dms)
    FAIL_INJECT["personal_tweet"] = False
    res = client.post("/admin/api/retry_lost", json={"ids": [mine[0]["id"]]}, headers=H).get_json()
    idle()
    tw = (GH.read_json("tweets.json")[0] or {}).get("tweets", {}).get("miyako") or []
    texts = [t.get("text") for t in (tw if isinstance(tw, list) else [tw])]
    check("18", "재투입 → 원문 그대로 반영", res.get("done") and "今日のおやつはプリン🍮" in texts, (res, texts))
    lost2 = client.get("/admin/api/list_lost").get_json()
    check("18", "성공한 항목은 유실 큐에서 제거", not any("プリン" in (l.get("raw") or "") for l in lost2), lost2)
    ns = (GH.read_json("notices.json")[0] or {}).get("notices", [])
    check("18", "엉터리 소식 없음 (작업 인자 JSON 이 원문으로 처리되지 않음)",
          not any((n.get("title") or "").startswith("{") for n in ns), [n.get("title") for n in ns])
    # 결과를 기다리지 않은 작업(yt_notif)의 실패 → 작업 자체를 보관 → 재투입 = 같은 작업 재적재
    FAIL_KINDS.add("yt_notif")
    video("RITSULV0001", "ritsu", "live", z(REAL_NOW), title="【雑談】", actual_start=z(REAL_NOW))
    DMS.clear()
    ingest_yt("RITSULV0001", "a:NOTIFICATION_TYPE_SUBSCRIPTION_LIVESTREAM_START:1", "【雑談】")
    time.sleep(1.0); idle()
    lost3 = [l for l in client.get("/admin/api/list_lost").get_json() if l.get("kind") == "apply_job"]
    check("20", "비동기 작업 실패 → 유실 큐에 작업(apply_job) 보관 + 쓰기 쪽 DM",
          len(lost3) == 1 and lost3[0].get("job_kind") == "yt_notif" and any("작업 실패" in d for d in DMS), (lost3, DMS))
    FAIL_KINDS.discard("yt_notif")
    res = client.post("/admin/api/retry_lost", json={"ids": [lost3[0]["id"]]}, headers=H).get_json()
    idle()
    check("18", "apply_job 재투입 → 같은 작업 재적재 → 반영",
          res.get("done") and (item(lambda i: i.get("video_id") == "RITSULV0001") or {}).get("state") == "live", res)

    # F22 · F23 — 스냅샷 · 웹 모니터
    scenario("F22·F23 스냅샷 잡 · 웹 모니터")
    tr("action", label="스냅샷 잡 (06:10 KST)", trigger="schedule")
    r = apply.submit("snapshot", {}, wait=True)
    check("22", "스냅샷 작업 (q-apply)", r.get("date"), r)
    check("23", "웹 모니터 /monitor-live", client.get("/monitor-live").status_code == 200)
    check("25", "프론트 / + /data/preview.json", client.get("/").status_code == 200
          and client.get("/data/preview.json").status_code == 200)

    # ── 원칙 검증 ─────────────────────────────────────────────────────────────
    scenario("원칙 검증")
    commits = [json.loads(l) for l in open(WORK / "_local/data/.commits.jsonl", encoding="utf-8")]
    bad = [c for c in commits if c["thread"] != "q-apply"]
    check("원칙①", f"data 브랜치 커밋 {len(commits)}건 전부 q-apply 스레드", not bad, bad[:5])
    viol = [e for e in TRACE if e["step"] == "VIOLATION"]
    check("원칙③", "Cloud Tasks · 자기 호출 지름길 사용 0건", not viol, viol)
    ext = [e for e in TRACE if e["step"] == "external"]
    llm_w = [e for e in ext if e["svc"] in ("groq", "vxtwitter", "yt-dlp") and e["actor"] == "writer"]
    check("원칙④", "LLM · vxtwitter · yt-dlp 호출이 쓰기 스레드에서 0건", not llm_w,
          [(e["svc"], e["call"], e["scenario"]) for e in llm_w][:5])
    ops_w = [e for e in TRACE if e["step"] == "write" and e["branch"] == "ops"]
    check("원칙⑤", f"운영 상태 쓰기 {len(ops_w)}건 → ops 브랜치", ops_w and not (WORK / "_local/data/control.json").exists())


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        tr("harness-error", error=traceback.format_exc()[-500:])
    finally:
        q_apply.stop(); q_enrich.stop()
        (HERE / "trace.json").write_text(json.dumps(TRACE, ensure_ascii=False, indent=1), encoding="utf-8")
        (HERE / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
        ok = sum(r["ok"] for r in RESULTS)
        print(f"\n결과: {ok}/{len(RESULTS)} 통과 · trace {len(TRACE)}건")
