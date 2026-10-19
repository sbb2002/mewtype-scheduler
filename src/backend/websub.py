"""(v4.5.0) PubSub(WebSub*) 수신 — YouTube 채널 피드 변경을 푸시로 받아 방송 발견 · 신곡 등록을 앞당긴다.

* WebSub(옛 이름 PubSubHubbub) = 허브(`pubsubhubbub.appspot.com`)가 구독자가 알려 준 주소로 변경 내용을 POST 해 주는 웹훅 방식.
  웹소켓이 아니고(연결 유지 없음), GCP 의 Cloud Pub/Sub 과는 다른 서비스다. 시험 결과 · 설계 배경: `ref/pubsub_probe/PUBSUB_VS_POLLING.md`.

역할 (접수 서비스 `mewtype-telegram` 이 콜백을 받고, 쓰기 서비스 `mewtype-backend` 가 구독을 갱신한다)
  - 구독 대상: 멤버 5명의 채널 + 뮤타입 음원 채널(YouTube 가 음원 배포로 자동 만든 「Mugendai MewType - Topic」 채널 — `song_feeds`).
    그룹 공식 채널(@BDP_yumemita)은 RSS 와 같은 이유(노래 영상이 합동 방송으로 올라옴)로 구독하지 않는다.
  - 멤버 채널 알림 → 영상 ID 만 뽑아 기존 wake(`videos.list` 확정)에 즉시 태운다. 본문은 판정에 쓰지 않는다 — 판정은 API 가 한다.
  - 뮤타입 음원 채널 알림 → 본문의 영상 ID · 곡명 · 공개 시각을 `find_new_songs` 입력으로 그대로 쓴다(RSS 항목과 같은 필드).
    보낸 쪽은 서명(`X-Hub-Signature` = `hub.secret` 로 만든 HMAC)으로 인증하므로 본문을 다시 조회하지 않는다.
  - 서명이 없거나 틀리면 무시한다. WebSub 규약상 응답은 2xx(허브가 재시도하지 않게) — 처리만 안 한다.
  - 구독 임대는 5일(432000초)이고 매일 갱신한다(`renew`). 갱신 때마다 허브가 검증 요청(GET)을 보내고, 그 기록(`action=verify`)이
    구독이 살아 있다는 신호다. 36시간 넘게 검증이 없는 채널은 갱신 잡이 DM 으로 알린다.
  - 모니터 이벤트 `flow="websub"`: `verify`(허브 검증) · `notify`(알림 수신) · `renew`(일일 갱신) · `reject`(서명 불일치).
  - (v4.5.2) 버스트 대비: 접수 서비스는 알림을 받으면 **예약만 하고 바로 응답**한다 — `notify` 기록은 쓰기 서비스가 그 확인을 처리하면서
    남긴다(한 줄로 처리되므로 `monitoring` 브랜치 커밋 경합이 없다. 같은 영상이 10분 안에 또 오면 기존 줄의 `count` 를 올린다).
    예약은 PubSub 전용 큐(`WEBSUB_QUEUE`, 5초에 1건)로 보내 쓰기 서비스가 쉬지 않고 바빠지지 않게 하고(그 틈으로 트윗 저장 등 동기 쓰기가 들어간다),
    「2분 뒤 한 번 더」 확인은 첫 확인에서 API 가 아직 그 영상을 모를 때만 쓰기 서비스가 건다. 실측 근거: VERSION.md v4.5.2.

RSS 폴링을 PubSub 으로 대체할지는 env `WEBSUB_REPLACE_RSS=1` 로 정한다(`replaces_rss()`) — 켜면 10분 light 틱이 RSS · 신곡 호출을 생략하고
일일 baseline 만 안전망으로 남긴다. 끄면 알림이 와도 폴링이 그대로 돌아 두 경로가 함께 동작한다(이중 운영 · 롤백).

self-test: python -m src.backend.websub
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger("backend.websub")

HUB_URL = "https://pubsubhubbub.appspot.com/subscribe"
LEASE_SECONDS = 432000            # 5일 — 시험에서 허브가 수락한 값(허브 최대 임대는 미확인)
MAX_BODY = 200_000                # 알림 본문 상한(바이트)
STALE_HOURS = 36                  # 일일 갱신인데 이 시간 넘게 허브 검증이 없으면 구독이 끊긴 것으로 본다
SONG_PREFIX = "song-"             # 뮤타입 음원 채널의 구독 이름 접두 (`song-<song_feeds.key>`)
WAKE_RETRY_SEC = 120              # 신규 영상은 API 반영이 늦을 수 있어 즉시 확인 뒤 한 번 더 확인한다
_REJECT_LOG_GAP_SEC = 600         # 서명 불일치 이벤트는 프로세스당 10분에 한 번만 남긴다(공개 주소라 스팸 방지)

_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "at": "http://purl.org/atompub/tombstones/1.0",
}
_HASHES = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha384": hashlib.sha384, "sha512": hashlib.sha512}


def replaces_rss() -> bool:
    """PubSub 이 RSS 폴링(10분 틱의 RSS · 신곡 호출)을 대체하는 모드인가 — env `WEBSUB_REPLACE_RSS`."""
    return os.environ.get("WEBSUB_REPLACE_RSS", "").strip().lower() in ("1", "true", "yes", "on")


def task_queue():
    """(v4.5.2) PubSub 이 시작하는 작업(확인 · 신곡 등록)을 넣을 Cloud Tasks 큐 — env `WEBSUB_QUEUE`(속도 제한 큐).
    없으면 기본 큐(`TASKS_QUEUE`)로 — 속도 제한만 빠지고 동작은 같다. 클라우드 설정이 없으면 None."""
    from . import tasks
    return tasks.from_env(os.environ.get("WEBSUB_QUEUE", "").strip() or None)


def notify_event(now_iso: str, who: str, video_id: str, title: str, detail: str, result: str = "ok") -> dict:
    """(v4.5.2) 알림 수신 기록 — 쓰기 서비스가 확인 · 신곡 등록을 처리하면서 남긴다. 같은 영상이 10분 안에 또 오면
    `monitor_log.log_events` 가 새 줄 대신 기존 줄의 `count` 를 올린다(`merge_key`)."""
    return {"ts": now_iso, "flow": "websub", "result": result, "who": who, "action": "notify", "video_id": video_id,
            "title": (title or "")[:80], "detail": detail, "merge_key": f"websub-notify:{video_id}"}


def topic_url(channel_id: str) -> str:
    return f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"


def subscriptions(channels_cfg: dict) -> dict[str, dict]:
    """구독 이름 → {channel_id, kind(member|song), key}. 멤버 채널 + 뮤타입 음원 채널. 그룹 공식 채널은 제외."""
    out: dict[str, dict] = {}
    chans = channels_cfg.get("channels") or {}
    for key in channels_cfg.get("channel_order") or list(chans):
        c = chans.get(key) or {}
        if c.get("is_group") or not c.get("channel_id"):
            continue
        out[key] = {"channel_id": c["channel_id"], "kind": "member", "key": key}
    for f in channels_cfg.get("song_feeds") or []:
        if f.get("channel_id"):
            key = f.get("key") or "song"
            out[SONG_PREFIX + key] = {"channel_id": f["channel_id"], "kind": "song", "key": key, "who": f.get("who") or "group"}
    return out


# ── 알림 파싱 · 인증 ─────────────────────────────────────────────────────────────

def parse_notification(xml_text: str) -> dict:
    """허브가 보낸 Atom → {"entries": [{video_id, channel_id, title, published, updated, description}], "deleted": [video_id]}.

    entries 의 필드는 `songs.parse_feed_entries`(RSS 항목)와 같다(description 만 푸시 본문에 없어 빈 값).
    서명 검증을 통과한 본문에만 부른다. 파싱 실패 · 삭제 알림(tombstone)이면 해당 목록이 빈다."""
    out: dict = {"entries": [], "deleted": []}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("PubSub 알림 파싱 실패: %s", e)
        return out
    for entry in root.findall("a:entry", _NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=_NS)
        if not vid:
            continue
        out["entries"].append({
            "video_id": vid,
            "channel_id": entry.findtext("yt:channelId", default="", namespaces=_NS),
            "title": entry.findtext("a:title", default="", namespaces=_NS).strip(),
            "published": entry.findtext("a:published", default="", namespaces=_NS),
            "updated": entry.findtext("a:updated", default="", namespaces=_NS),
            "description": "",
        })
    for d in root.findall("at:deleted-entry", _NS):
        ref = d.get("ref") or ""
        if ref.startswith("yt:video:"):
            out["deleted"].append(ref[len("yt:video:"):])
    return out


def signature_ok(secret: str, body: bytes, header: str | None) -> bool:
    """`X-Hub-Signature: <algo>=<hex>` 검증 — body 에 `hub.secret` 으로 만든 HMAC. 상수 시간 비교."""
    if not secret or not header:
        return False
    algo, _, hexsig = header.strip().partition("=")
    fn = _HASHES.get(algo.strip().lower())
    if fn is None or not hexsig.strip():
        return False
    want = hmac.new(secret.encode("utf-8"), body, fn).hexdigest()
    return hmac.compare_digest(want, hexsig.strip().lower())


def check_verification(args, subs: dict[str, dict], name: str) -> tuple[bool, str]:
    """허브의 구독 검증(GET) 요청이 우리가 낸 구독이 맞는지 — (맞는가, 돌려줄 challenge)."""
    sub = subs.get(name)
    mode = (args.get("hub.mode") or "").strip()
    topic = (args.get("hub.topic") or "").strip()
    challenge = args.get("hub.challenge") or ""
    if not sub or mode not in ("subscribe", "unsubscribe") or not challenge:
        return False, ""
    if topic != topic_url(sub["channel_id"]):
        return False, ""
    return True, challenge


# ── 구독 · 갱신 ──────────────────────────────────────────────────────────────────

def subscribe_form(callback: str, channel_id: str, secret: str, lease: int = LEASE_SECONDS) -> dict:
    return {
        "hub.callback": callback, "hub.mode": "subscribe", "hub.verify": "async",
        "hub.topic": topic_url(channel_id), "hub.lease_seconds": str(lease), "hub.secret": secret,
    }


def subscribe_all(base_url: str, subs: dict[str, dict], secret: str, *, lease: int = LEASE_SECONDS,
                  post=None, sleep=time.sleep) -> list[dict]:
    """모든 구독을 (재)요청 — 허브는 같은 콜백 · 토픽이면 임대를 갱신한다(멱등). 결과 [{name, ok, http|error}]."""
    post = post or requests.post
    results = []
    for name, sub in subs.items():
        callback = f"{base_url.rstrip('/')}/websub/{name}"
        try:
            r = post(HUB_URL, data=subscribe_form(callback, sub["channel_id"], secret, lease), timeout=20)
            results.append({"name": name, "http": r.status_code, "ok": r.status_code in (202, 204)})
        except Exception as e:  # noqa: BLE001
            results.append({"name": name, "ok": False, "error": f"{type(e).__name__}: {e}"[:160]})
        sleep(0.5)
    return results


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def read_recent_events(gh, now_iso: str, days: int = 3) -> list[dict]:
    """모니터링 브랜치에서 최근 며칠 치 `flow=websub` 이벤트를 읽는다(읽기 실패한 날은 건너뜀)."""
    from . import monitor_log
    mgh = monitor_log._monitor_gh(gh)
    now = _parse_ts(now_iso) or datetime.now(timezone.utc)
    out: list[dict] = []
    seen_paths = set()
    for back in range(days + 1):
        path = monitor_log.event_path((now - timedelta(days=back)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        if path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            text, _ = mgh.read_text(path)
        except Exception:  # noqa: BLE001
            log.warning("websub 이벤트 읽기 실패 %s", path, exc_info=True)
            continue
        for line in (text or "").splitlines():
            if '"websub"' not in line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("flow") == "websub":
                out.append(ev)
    return out


def stale_channels(events: list[dict], subs: dict[str, dict], now_iso: str, hours: int = STALE_HOURS) -> list[str] | None:
    """허브 검증(`verify`)이 `hours` 시간 넘게 없는 구독 이름들. 이전 갱신 기록(`renew`)이 하나도 없으면(첫 실행) None = 판정 불가."""
    if not any(e.get("action") == "renew" for e in events):
        return None
    now = _parse_ts(now_iso) or datetime.now(timezone.utc)
    last: dict[str, datetime] = {}
    for e in events:
        if e.get("action") != "verify":
            continue
        t = _parse_ts(e.get("ts", ""))
        if t and e.get("who") in subs and (e["who"] not in last or t > last[e["who"]]):
            last[e["who"]] = t
    return [n for n in subs if n not in last or (now - last[n]) > timedelta(hours=hours)]


def renew(gh, now_iso: str, channels_cfg: dict, callback_base: str, secret: str, *, post=None,
          read_events=None, log_events_fn=None, send_dm=None, sleep=time.sleep) -> dict:
    """일일 구독 갱신 잡(`POST /websub-renew`, Cloud Scheduler → 쓰기 서비스).

    ① 갱신 전에 지난 검증 기록으로 끊긴 구독을 찾고 ② 전부 다시 구독 요청하고 ③ 결과를 모니터 이벤트로 남기며
    ④ 요청 실패 · 끊긴 구독이 있으면 DM. 허브의 검증 GET 은 비동기로 뒤따라 와서 콜백(`verify`)이 기록한다."""
    subs = subscriptions(channels_cfg)
    if not secret or not callback_base:
        raise RuntimeError("WEBSUB_SECRET 또는 WEBSUB_CALLBACK_BASE 가 설정되지 않음")
    read_events = read_events or (lambda: read_recent_events(gh, now_iso))
    try:
        stale = stale_channels(read_events(), subs, now_iso)
    except Exception:  # noqa: BLE001
        log.warning("구독 상태 확인 실패 — 갱신은 계속", exc_info=True)
        stale = None
    results = subscribe_all(callback_base, subs, secret, post=post, sleep=sleep)
    failed = [r for r in results if not r["ok"]]
    problems = []
    if failed:
        problems.append("구독 요청 실패 " + ", ".join(f"{r['name']}({r.get('http') or r.get('error')})" for r in failed))
    if stale:
        problems.append(f"허브 검증이 {STALE_HOURS}시간 넘게 없음: " + ", ".join(stale))
    detail = f"구독 갱신 요청 {len(results) - len(failed)}/{len(results)} 수락" + ("" if not problems else " · " + " · ".join(problems))
    from .monitor_log import RESULT_OK, RESULT_WARN, log_events
    ev = {"ts": now_iso, "flow": "websub", "result": RESULT_WARN if problems else RESULT_OK, "who": "",
          "detail": detail, "action": "renew", "requested": len(results), "failed": len(failed)}
    try:
        (log_events_fn or log_events)(gh, now_iso, [ev])
    except Exception:  # noqa: BLE001
        log.warning("renew 이벤트 기록 실패", exc_info=True)
    if problems and send_dm is not None:
        try:
            send_dm("⚠️ PubSub 구독 점검\n" + "\n".join(problems) + "\n(다음 갱신에서 자동으로 다시 시도합니다 — 계속되면 허브·콜백 주소를 확인)")
        except Exception:  # noqa: BLE001
            log.warning("구독 점검 DM 실패", exc_info=True)
    return {"requested": len(results), "failed": [r["name"] for r in failed], "stale": stale, "detail": detail}


# ── 콜백 라우트 (접수 서비스) ────────────────────────────────────────────────────

_last_reject_log = [0.0]


def register_callbacks(app, *, load_cfg, make_gh, enqueue_wake, submit, log_events_fn, now_iso_fn, secret_fn=None) -> None:
    """`GET/POST /websub/<name>` 등록 — 허브 검증(GET)과 알림(POST).

    load_cfg() → channels.json 딕트, make_gh() → data store 또는 None, enqueue_wake(video_id, when_iso, meta) → 즉시 확인 예약,
    submit(kind, args) → 쓰기 서비스 작업 적재, log_events_fn(gh, now_iso, events), now_iso_fn() → UTC ISO.
    모두 주입받는다(self-test 는 가짜를 넣는다).

    (v4.5.2) 알림(POST)은 예약만 하고 **커밋 없이** 응답한다 — 수신 기록(`notify`)은 쓰기 서비스가 남긴다. 접수 쪽에서 커밋하는 것은
    드문 경우(서명 불일치 — 10분에 한 번 · 예약 실패)뿐이다. 삭제 알림(tombstone)은 서비스 로그로만 남긴다."""
    from flask import Response, request
    from .monitor_log import RESULT_OK, RESULT_WARN, RESULT_ERR

    secret_fn = secret_fn or (lambda: os.environ.get("WEBSUB_SECRET", "").strip())

    def _log(events: list[dict]) -> None:
        try:
            gh = make_gh()
            if gh is not None and events:
                log_events_fn(gh, events[0]["ts"], events)
        except Exception:  # noqa: BLE001
            log.warning("websub 이벤트 기록 실패", exc_info=True)

    @app.get("/websub/<name>", endpoint="websub_verify")
    def _websub_verify(name):
        subs = subscriptions(load_cfg())
        ok, challenge = check_verification(request.args, subs, name)
        if not ok:
            return Response("", status=404)
        now = now_iso_fn()
        _log([{"ts": now, "flow": "websub", "result": RESULT_OK, "who": name, "action": "verify",
               "detail": f"허브 검증 통과 ({request.args.get('hub.mode')}) · 임대 {request.args.get('hub.lease_seconds') or '?'}초",
               "lease": request.args.get("hub.lease_seconds")}])
        return Response(challenge, status=200, mimetype="text/plain")

    @app.post("/websub/<name>", endpoint="websub_notify")
    def _websub_notify(name):
        secret = secret_fn()
        if not secret:
            return Response("", status=503)
        subs = subscriptions(load_cfg())
        sub = subs.get(name)
        if sub is None:
            return Response("", status=404)
        body = request.get_data(cache=False)[:MAX_BODY]
        now = now_iso_fn()
        header = request.headers.get("X-Hub-Signature")
        if not signature_ok(secret, body, header):
            # 규약: 서명이 맞지 않아도 2xx 로 받았다고 답하고 내용만 무시한다(허브 재시도 방지)
            log.warning("PubSub 서명 불일치/누락 name=%s header=%s", name, "있음" if header else "없음")
            if time.time() - _last_reject_log[0] > _REJECT_LOG_GAP_SEC:
                _last_reject_log[0] = time.time()
                _log([{"ts": now, "flow": "websub", "result": RESULT_WARN, "who": name, "action": "reject",
                       "detail": "서명 " + ("불일치" if header else "헤더 없음") + " — 알림 무시"}])
            return Response("", status=204)
        parsed = parse_notification(body.decode("utf-8", "replace"))
        entries = [e for e in parsed["entries"] if e["channel_id"] == sub["channel_id"]]
        log.info("PubSub 알림 name=%s videos=%s deleted=%s", name, [e["video_id"] for e in entries], parsed["deleted"][:5])
        try:
            if entries and sub["kind"] == "member":
                for e in entries:
                    # 방송이면 바로 카드로, 아니면 아무 변화 없음. 「2분 뒤 한 번 더」는 쓰기 서비스가 API 미반영일 때만 건다(v4.5.2)
                    enqueue_wake(e["video_id"], now, {"websub": {"who": name, "title": e["title"][:80], "attempt": 1}})
            elif entries and sub["kind"] == "song":
                submit("song_push", {"entries": entries, "now_iso": now, "who": name})
        except Exception as e:  # noqa: BLE001
            log.exception("PubSub 알림 처리 실패 name=%s", name)
            _log([{"ts": now, "flow": "websub", "result": RESULT_ERR, "who": name, "action": "notify_fail",
                   "detail": f"알림 처리 실패(허브가 재시도) — {type(e).__name__}: {str(e)[:120]}"}])
            return Response("", status=503)      # 2xx 가 아니면 허브가 나중에 다시 보낸다
        return Response("", status=204)


# ── self-test ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path

    fx = Path(__file__).resolve().parents[2] / "fixtures" / "websub_notify.sample.xml"
    body_xml = fx.read_text(encoding="utf-8")

    # 알림 파싱 — 실제 알림 1건(리츠 4Qg5SkkDuMI)과 삭제 알림
    p = parse_notification(body_xml)
    assert len(p["entries"]) == 1 and p["deleted"] == []
    e0 = p["entries"][0]
    assert e0["video_id"] == "4Qg5SkkDuMI" and e0["channel_id"] == "UCxc0MrPoACKTFlV24GqX2sg"
    assert e0["published"] == "2026-10-15T13:34:11+00:00" and e0["title"].startswith("【ぽんこつ社】") and e0["description"] == ""
    from . import songs as _songs
    assert [{k: v for k, v in x.items() if k in ("video_id", "title", "published")} for x in _songs.parse_feed_entries(body_xml)] == \
        [{k: v for k, v in e0.items() if k in ("video_id", "title", "published")}], "RSS 항목과 같은 필드"
    tomb = ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:at="http://purl.org/atompub/tombstones/1.0">'
            '<at:deleted-entry ref="yt:video:ABCDEFGHIJK" when="2026-10-19T00:00:00+00:00"><link href="https://www.youtube.com/watch?v=ABCDEFGHIJK"/>'
            '</at:deleted-entry></feed>')
    pd = parse_notification(tomb)
    assert pd["entries"] == [] and pd["deleted"] == ["ABCDEFGHIJK"]
    assert parse_notification("<not xml") == {"entries": [], "deleted": []}

    # 서명 검증 — sha1 / sha256 / 틀림 / 헤더 없음 / 알 수 없는 알고리즘
    raw = body_xml.encode("utf-8")
    sig1 = "sha1=" + hmac.new(b"s3cret", raw, hashlib.sha1).hexdigest()
    sig256 = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
    assert signature_ok("s3cret", raw, sig1) and signature_ok("s3cret", raw, sig256) and signature_ok("s3cret", raw, sig1.upper().replace("SHA1", "sha1"))
    assert not signature_ok("other", raw, sig1) and not signature_ok("s3cret", raw + b"x", sig1)
    assert not signature_ok("s3cret", raw, None) and not signature_ok("s3cret", raw, "") and not signature_ok("", raw, sig1)
    assert not signature_ok("s3cret", raw, "md5=" + "0" * 32) and not signature_ok("s3cret", raw, "sha1=")

    # 구독 대상 — 멤버 5명 + 뮤타입 음원 채널, 그룹 공식 채널 제외
    cfg = {"channel_order": ["arale", "ritsu"],
           "channels": {"arale": {"channel_id": "UCa"}, "ritsu": {"channel_id": "UCxc0MrPoACKTFlV24GqX2sg"},
                        "group": {"channel_id": "UCg", "is_group": True}},
           "song_feeds": [{"key": "topic", "name": "Mugendai MewType - Topic", "channel_id": "UCs", "who": "group"}]}
    subs = subscriptions(cfg)
    assert list(subs) == ["arale", "ritsu", "song-topic"] and subs["song-topic"]["kind"] == "song" and "group" not in subs
    real = subscriptions(json.loads((Path(__file__).resolve().parents[2] / "config" / "channels.json").read_text(encoding="utf-8")))
    assert len(real) == 6 and sum(1 for s in real.values() if s["kind"] == "member") == 5 and "song-topic" in real

    # 허브 검증 GET
    ok, ch = check_verification({"hub.mode": "subscribe", "hub.topic": topic_url("UCa"), "hub.challenge": "xyz"}, subs, "arale")
    assert ok and ch == "xyz"
    assert not check_verification({"hub.mode": "subscribe", "hub.topic": topic_url("UCother"), "hub.challenge": "x"}, subs, "arale")[0]
    assert not check_verification({"hub.mode": "publish", "hub.topic": topic_url("UCa"), "hub.challenge": "x"}, subs, "arale")[0]
    assert not check_verification({"hub.mode": "subscribe", "hub.topic": topic_url("UCa")}, subs, "arale")[0]
    assert not check_verification({"hub.mode": "subscribe", "hub.topic": topic_url("UCa"), "hub.challenge": "x"}, subs, "nope")[0]

    # 구독 요청 — 폼 필드 · 실패 처리
    sent = []

    class _R:
        def __init__(self, c):
            self.status_code = c

    def _post(url, data=None, timeout=None):
        sent.append((url, data))
        if "UCxc0" in data["hub.topic"]:
            raise TimeoutError("허브 응답 없음")
        return _R(202 if "UCa" in data["hub.topic"] else 500)

    res = subscribe_all("https://cb.example/", subs, "s3cret", post=_post, sleep=lambda s: None)
    assert [(r["name"], r["ok"]) for r in res] == [("arale", True), ("ritsu", False), ("song-topic", False)]
    assert res[1]["error"].startswith("TimeoutError") and res[2]["http"] == 500
    f0 = sent[0][1]
    assert sent[0][0] == HUB_URL and f0["hub.callback"] == "https://cb.example/websub/arale" and f0["hub.secret"] == "s3cret"
    assert f0["hub.verify"] == "async" and f0["hub.lease_seconds"] == "432000" and f0["hub.mode"] == "subscribe"

    # 끊긴 구독 판정 — 첫 실행(renew 기록 없음)은 판정 불가, 이후는 36시간 기준
    now = "2026-10-20T00:00:00Z"
    assert stale_channels([], subs, now) is None
    base = [{"flow": "websub", "action": "renew", "ts": "2026-10-19T00:00:00Z"}]
    vf = lambda who, ts: {"flow": "websub", "action": "verify", "who": who, "ts": ts}   # noqa: E731
    assert stale_channels(base + [vf("arale", "2026-10-19T00:00:05Z"), vf("ritsu", "2026-10-19T00:00:06Z"), vf("song-topic", "2026-10-19T00:00:07Z")], subs, now) == []
    assert stale_channels(base + [vf("arale", "2026-10-19T00:00:05Z"), vf("ritsu", "2026-10-18T05:00:00Z")], subs, now) == ["ritsu", "song-topic"]

    # 일일 갱신 — 정상 / 실패 + 끊김 → 이벤트 · DM
    logged, dms = [], []
    out = renew(None, now, cfg, "https://cb.example", "s3cret", post=lambda u, data=None, timeout=None: _R(202),
                read_events=lambda: [], log_events_fn=lambda g, n, evs: logged.extend(evs), send_dm=dms.append, sleep=lambda s: None)
    assert out["failed"] == [] and out["stale"] is None and not dms
    assert logged[0]["action"] == "renew" and logged[0]["result"] == "ok" and logged[0]["requested"] == 3
    logged.clear()
    out = renew(None, now, cfg, "https://cb.example", "s3cret", post=_post, read_events=lambda: base + [vf("arale", "2026-10-19T00:00:05Z")],
                log_events_fn=lambda g, n, evs: logged.extend(evs), send_dm=dms.append, sleep=lambda s: None)
    assert out["failed"] == ["ritsu", "song-topic"] and out["stale"] == ["ritsu", "song-topic"]
    assert logged[0]["result"] == "warn" and logged[0]["failed"] == 2 and len(dms) == 1 and "ritsu" in dms[0]
    try:
        renew(None, now, cfg, "", "s3cret")
        raise AssertionError("콜백 주소 없으면 실패해야 함")
    except RuntimeError:
        pass

    # 콜백 라우트 — Flask 테스트 클라이언트 + 가짜 의존성
    try:
        from flask import Flask
    except ImportError:
        print("[PASS] websub self-test (Flask 미설치 — 라우트 시험 생략)")
        raise SystemExit(0)
    tapp = Flask("websub_test")
    wakes, writes, evs = [], [], []
    state = {"fail": False}

    def _enqueue(vid, when, meta=None):
        if state["fail"]:
            raise RuntimeError("Cloud Tasks 장애")
        wakes.append((vid, when, meta))

    def _submit(kind, args):
        writes.append((kind, args))
        return {"queued": True}

    register_callbacks(tapp, load_cfg=lambda: cfg, make_gh=lambda: object(), enqueue_wake=_enqueue, submit=_submit,
                       log_events_fn=lambda g, n, es: evs.extend(es), now_iso_fn=lambda: "2026-10-20T00:00:00Z", secret_fn=lambda: "s3cret")
    c = tapp.test_client()
    sig = {"X-Hub-Signature": sig1}
    # GET 검증
    r = c.get("/websub/arale", query_string={"hub.mode": "subscribe", "hub.topic": topic_url("UCa"), "hub.challenge": "abc", "hub.lease_seconds": "432000"})
    assert r.status_code == 200 and r.get_data(as_text=True) == "abc"
    assert evs[-1]["action"] == "verify" and evs[-1]["who"] == "arale" and evs[-1]["lease"] == "432000"
    assert c.get("/websub/arale", query_string={"hub.mode": "subscribe", "hub.topic": topic_url("UCzzz"), "hub.challenge": "abc"}).status_code == 404
    # 멤버 알림(서명 정상) → 즉시 확인 1건만 예약(+ PubSub 정보), 영상 ID 만 사용. (v4.5.2) 접수 쪽은 기록 커밋 없음
    n_ev = len(evs)
    r = c.post("/websub/ritsu", data=raw, headers=sig)
    assert r.status_code == 204
    assert wakes == [("4Qg5SkkDuMI", "2026-10-20T00:00:00Z", {"websub": {"who": "ritsu", "title": "【ぽんこつ社】峰月社長と商品開発会議【峰月律/ゆめみた】", "attempt": 1}})], wakes
    assert len(evs) == n_ev and not writes, "알림 수신은 접수 서비스에서 커밋하지 않는다(쓰기 서비스가 기록)"
    # 서명 불일치 · 헤더 없음 → 204 로 받고 무시(예약 없음), 이벤트는 10분에 한 번
    n = len(wakes)
    assert c.post("/websub/ritsu", data=raw, headers={"X-Hub-Signature": "sha1=" + "0" * 40}).status_code == 204
    assert c.post("/websub/ritsu", data=raw).status_code == 204
    assert len(wakes) == n and sum(1 for e in evs if e["action"] == "reject") == 1
    # 다른 채널 항목(채널 ID 불일치)은 무시 — 아라레 구독으로 리츠 영상이 와도 예약하지 않는다
    sig_a = {"X-Hub-Signature": sig1}
    assert c.post("/websub/arale", data=raw, headers=sig_a).status_code == 204 and len(wakes) == n
    # 뮤타입 음원 채널 → song_push 작업 적재(본문 필드 그대로)
    song_xml = body_xml.replace("UCxc0MrPoACKTFlV24GqX2sg", "UCs").replace("4Qg5SkkDuMI", "SONGVIDEO01")
    sraw = song_xml.encode("utf-8")
    r = c.post("/websub/song-topic", data=sraw, headers={"X-Hub-Signature": "sha1=" + hmac.new(b"s3cret", sraw, hashlib.sha1).hexdigest()})
    assert r.status_code == 204 and writes[0][0] == "song_push" and writes[0][1]["entries"][0]["video_id"] == "SONGVIDEO01"
    assert writes[0][1]["now_iso"] == "2026-10-20T00:00:00Z" and writes[0][1]["who"] == "song-topic" and len(wakes) == n
    # 삭제 알림 — 예약 · 적재 · 커밋 없이 서비스 로그만
    traw = tomb.encode("utf-8")
    n_ev = len(evs)
    assert c.post("/websub/arale", data=traw, headers={"X-Hub-Signature": "sha1=" + hmac.new(b"s3cret", traw, hashlib.sha1).hexdigest()}).status_code == 204
    assert len(evs) == n_ev and len(wakes) == n and len(writes) == 1
    # notify_event — 쓰기 서비스가 남기는 수신 기록(같은 영상은 merge_key 로 묶임)
    ne = notify_event("2026-10-20T00:00:00Z", "ritsu", "4Qg5SkkDuMI", "t" * 100, "알림 수신")
    assert ne["action"] == "notify" and ne["merge_key"] == "websub-notify:4Qg5SkkDuMI" and len(ne["title"]) == 80
    # 예약 실패 → 503(허브가 재시도) + err 이벤트
    state["fail"] = True
    assert c.post("/websub/ritsu", data=raw, headers=sig).status_code == 503 and evs[-1]["action"] == "notify_fail" and evs[-1]["result"] == "err"
    state["fail"] = False
    # 모르는 이름 404 · 시크릿 미설정 503
    assert c.post("/websub/nobody", data=raw, headers=sig).status_code == 404
    tapp2 = Flask("websub_test2")
    register_callbacks(tapp2, load_cfg=lambda: cfg, make_gh=lambda: None, enqueue_wake=_enqueue, submit=_submit,
                       log_events_fn=lambda g, n, es: None, now_iso_fn=lambda: "2026-10-20T00:00:00Z", secret_fn=lambda: "")
    assert tapp2.test_client().post("/websub/ritsu", data=raw, headers=sig).status_code == 503
    print("[PASS] websub self-test (파싱 · 서명 · 구독 대상 · 검증 GET · 구독 요청 · 끊긴 구독 판정 · 일일 갱신 · 콜백 라우트)")
