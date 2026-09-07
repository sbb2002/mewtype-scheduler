"""멤버 개인 트윗 — android.title 라우팅 + tweets.json 계약 + (v2.8.1) scheduled 승격 (순수 함수).

계약: docs/plan/v2_8_personal_tweets.md · docs/plan/v2_8_1_personal_schedule.md
현행 ingest 경로: docs/INGEST_FLOW.md

외부 백엔드(폰 Automate)가 팔로우한 7계정(개인5 + 공식 + 테스트 부계정)의 푸시 알림이
지금과 **똑같이** POST /ingest 로 들어온다. android.title(게시자 표시 이름)로 갈래를 나눈다:
  - 공식(夢限大みゅーたいぷ) · 그 외      → "official"     (기존 소식/스케줄 경로 = INGEST_FLOW 4번)
  - 개인 5인 표시명                        → "<channel_key>" (이 모듈이 처리하고 종료)
  - 테스트 부계정(INGEST_TEST_TITLES)      → "test"          (4번 거치되 강제 ECHO — 헬스체크)

tweets.json
  { "generated_at": "...Z",
    "tweets": { "<ck>": { channel_key, id, text, url, handle, received_at, expires_at } } }
  채널당 최대 1건. 24h(TTL_HOURS) 안에 트윗 없으면 키 자체가 없음.
tweet_archive.json
  { "tweets": [ <위 + archived_at + archived_reason("expired"|"replaced")> ] }  append-only, id dedupe

self-test: python -m src.backend.xtweet
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from .xrelay import JST, YT_VIDEO_RE, normalize
from .xnotice import _first_time, _pick_event_date

UTC = timezone.utc

TTL_HOURS = 24
_TEXT_CAP = 600

# android.title 매칭 폴백 (config/channels.json 에 x_names 가 없을 때).
_FALLBACK_X_NAMES: dict[str, list[str]] = {
    "arale": ["仲町あられ"],
    "yuno": ["千石ユノ"],
    "nonoka": ["宮永ののか"],
    "ritsu": ["峰月律"],
    "miyako": ["藤都子"],
}
_OFFICIAL_NAMES = ("夢限大みゅーたいぷ", "ゆめみた", "みゅーたいぷ")

_TWEET_ID_RE = re.compile(r"tweet-(\d{6,25})")
# 이름 비교용 — 히라가나·가타카나·한자·영숫자만 남기고 소문자화 (이모지·기호·공백 제거)
_KEEP_RE = re.compile(r"[0-9A-Za-z぀-ヿ㐀-鿿ｦ-ﾟ]+")
# 본문 앞뒤의 순수 장식 줄
_JUNK_LINE_RE = re.compile(r"^[\s＼／\\/|｜·・*—\-–＞>▼▽▶➡→]+$")


def _strip_decor(s: str) -> str:
    return "".join(_KEEP_RE.findall(normalize(s or ""))).lower()


def _x_names(channels_cfg: dict) -> dict[str, list[str]]:
    out = {k: list(v) for k, v in _FALLBACK_X_NAMES.items()}
    for ck, meta in (channels_cfg or {}).get("channels", {}).items():
        names = meta.get("x_names")
        if names:
            out[ck] = list(names)
    return out


def route_by_title(title: str, channels_cfg: dict, *,
                   test_titles: tuple[str, ...] = ()) -> str:
    """android.title → "official" | "<channel_key>" | "test"."""
    t = _strip_decor(title)
    if not t:
        return "official"                       # 빈 title(일부 RT/원글) → 기존 경로
    for tt in test_titles:
        s = _strip_decor(tt)
        if s and s in t:
            return "test"
    if any(_strip_decor(o) in t for o in _OFFICIAL_NAMES):
        return "official"
    for ck, names in _x_names(channels_cfg).items():
        for nm in names:
            base = _strip_decor(nm)
            if base and (t.startswith(base) or base in t):
                return ck
    return "official"


def _tweet_id(tag: str | None) -> str:
    m = _TWEET_ID_RE.search(tag or "")
    return m.group(1) if m else ""


def _clean_text(text: str) -> str:
    """normalize + 앞뒤 장식/빈 줄 제거 + 길이 제한."""
    lines = [ln.rstrip() for ln in normalize(text or "").split("\n")]
    while lines and (not lines[0] or _JUNK_LINE_RE.match(lines[0])):
        lines.pop(0)
    while lines and (not lines[-1] or _JUNK_LINE_RE.match(lines[-1])):
        lines.pop()
    return "\n".join(lines).strip()[:_TEXT_CAP]


def _parse_iso(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _reached(iso_when: str | None, now_iso: str) -> bool:
    a, b = _parse_iso(iso_when), _parse_iso(now_iso)
    return bool(a and b and a <= b)


def parse(text: str, *, title: str, tag: str | None, channel_key: str,
          now_iso: str, handle: str = "") -> dict | None:
    """개인 트윗 1건 dict. text 가 (장식 제거 후) 비면 None."""
    body = _clean_text(text)
    if not body:
        return None
    tid = _tweet_id(tag)
    synthetic = not tid
    if synthetic:
        tid = "p" + hashlib.sha1(
            (channel_key + "|" + body[:80]).encode("utf-8")
        ).hexdigest()[:15]
    now = _parse_iso(now_iso) or datetime.now(UTC)
    exp = (now + timedelta(hours=TTL_HOURS)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "channel_key": channel_key,
        "id": tid,
        "text": body,
        "url": None if synthetic else f"https://x.com/i/status/{tid}",
        "handle": handle or "",
        "received_at": now_iso,
        "expires_at": exp,
    }


# ── tweets.json 계약 ────────────────────────────────────────────────────

def default_tweets() -> dict:
    return {"generated_at": None, "tweets": {}}


def default_archive() -> dict:
    return {"tweets": []}


_ROW_KEYS = ("channel_key", "id", "text", "url", "handle", "received_at", "expires_at")


def _newer(inc: dict, cur: dict) -> bool:
    """inc 가 cur 보다 최신인가 — Snowflake id 우선(시간순 단조), 합성이면 received_at."""
    ai, bi = str(inc.get("id") or ""), str(cur.get("id") or "")
    if ai.isdigit() and bi.isdigit():
        return int(ai) > int(bi)
    return (inc.get("received_at") or "") > (cur.get("received_at") or "")


def _archive_push(archive: dict, row: dict, now_iso: str, reason: str) -> dict:
    have = {a.get("id") for a in archive.get("tweets", [])}
    if row.get("id") in have:
        return archive
    return {"tweets": list(archive.get("tweets", [])) + [
        dict({k: row.get(k) for k in _ROW_KEYS}, archived_at=now_iso, archived_reason=reason)
    ]}


def merge_tweet(prev: dict, incoming: dict, now_iso: str, *,
                archive: dict | None = None) -> tuple[dict, dict, bool, str]:
    """(new_tweets, new_archive, changed, mode). mode ∈ added|replaced|dup|stale."""
    prev = prev or default_tweets()
    arch = archive if archive is not None else default_archive()
    ck = incoming.get("channel_key")
    if not ck or not incoming.get("id") or _reached(incoming.get("expires_at"), now_iso):
        return prev, arch, False, "stale"

    tweets = dict(prev.get("tweets", {}))
    cur = tweets.get(ck)
    if cur is not None:
        if str(cur.get("id")) == str(incoming.get("id")) or not _newer(incoming, cur):
            return prev, arch, False, "dup"
        arch = _archive_push(arch, cur, now_iso, "replaced")
        mode = "replaced"
    else:
        mode = "added"

    tweets[ck] = {k: incoming.get(k) for k in _ROW_KEYS}
    out = dict(prev)
    out["tweets"] = tweets
    out["generated_at"] = now_iso
    return out, arch, True, mode


def sweep_expired(prev: dict, archive: dict, now_iso: str
                  ) -> tuple[dict, dict, list[str]]:
    """expires_at 지난 슬롯 → tweet_archive.json. (new_tweets, new_archive, removed_keys)."""
    prev = prev or default_tweets()
    archive = archive or default_archive()
    kept, removed = {}, []
    for ck, t in (prev.get("tweets") or {}).items():
        if _reached(t.get("expires_at"), now_iso):
            archive = _archive_push(archive, t, now_iso, "expired")
            removed.append(ck)
        else:
            kept[ck] = t
    if not removed:
        return prev, archive, []
    out = dict(prev)
    out["tweets"] = kept
    out["generated_at"] = now_iso
    return out, archive, removed


def summary_line(t: dict) -> str:
    txt = (t.get("text") or "").replace("\n", " ")
    return f"{t.get('channel_key', '?')} · {txt[:70]}"


# ═══ v2.8.1 — 개인 트윗 예고 → schedule.json 의 scheduled 행 ═══════════════
#   계약·규칙: docs/plan/v2_8_1_personal_schedule.md
#   단계 필수조건: scheduled ⇒ date  /  upcoming ⇒ date+time+url+thumbnail+video_id
#   최신 정보(트윗 Snowflake 시각 vs API tick 시각)가 날짜·시각의 정본. override 는
#   더 나중 트윗 또는 API 값 자체의 변화(api_start_seen 불일치) 전까지 유지.

_TW_EPOCH_MS = 1288834974657          # X(Twitter) Snowflake epoch

_SCHED_KW_RE = re.compile(r"配信|生配信|生放送|プレミア公開|歌枠|放送|ライブ配信|同時配信|枠")
_RECAP_RE = re.compile(
    r"ありがとう(?:ございました)?|お疲れ(?:様|さま)?|無事終了|見てくれて|"
    r"来てくれて|ご視聴|お越しくださり|終わりました"
)
_FUTURE_WORD = ("本日", "今日", "きょう", "今夜", "今晩", "これから", "まもなく", "ただいま", "今から")
_MEMBERS_ONLY_RE = re.compile(r"メン限|メンバー限定|会員限定|🔒|限定配信")
_HANDLE_HEAD_RE = re.compile(r"^\s*(?:RT\s+)?@\w{1,15}\s*[:：]")
_KIND_KW = [
    (re.compile(r"歌枠|歌配信|うた枠"), "song"),
    (re.compile(r"ゲーム"), "game"),
    (re.compile(r"雑談|フリートーク|お喋り"), "talk"),
    (re.compile(r"朝活|モーニング"), "morning"),
    (re.compile(r"コラボ|合同|合作|×"), "collab"),
]
_STAGE = {"live": 3, "upcoming": 2, "scheduled": 1}
_SRC_RANK = {"bdp_schedule": 2, "appearance": 2, "personal": 1}
_SAME_BROADCAST_SEC = 90 * 60


def snowflake_iso(tid: str | None) -> str | None:
    """트윗 Snowflake id → 작성 시각 ISO-Z. 못 뽑으면 None."""
    if not tid or not str(tid).isdigit() or len(str(tid)) < 15:
        return None
    ms = (int(tid) >> 22) + _TW_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(iso: str | None) -> float:
    d = _parse_iso(iso)
    return d.timestamp() if d else 0.0


def _jst_date(iso: str | None) -> str:
    d = _parse_iso(iso)
    return d.astimezone(JST).strftime("%Y-%m-%d") if d else ""


def _kind_of(t: str) -> str:
    for rx, k in _KIND_KW:
        if rx.search(t):
            return k
    return "unknown"


def _start_from(date_iso: str, time_hm: str | None) -> datetime:
    """date(+time) → JST datetime. time 없으면 그 날 00:00. 심야표기 24:xx 는 +1일."""
    base = datetime.fromisoformat(date_iso).replace(tzinfo=JST)
    if not time_hm:
        return base
    hh, mm = int(time_hm.split(":")[0]), int(time_hm.split(":")[1])
    carry, hh = divmod(hh, 24)
    return (base + timedelta(days=carry)).replace(hour=hh, minute=mm)


def _expires_at(start_jst: datetime, *, time_tbd: bool, members_only: bool) -> str:
    if time_tbd:
        end = (start_jst + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        end = start_jst.astimezone(UTC) + timedelta(hours=5 if members_only else 3)
    return end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_schedule(text: str, *, channel_key: str, tag: str | None, now_iso: str,
                   handle: str = "") -> dict | None:
    """개인 트윗이 방송 예고면 scheduled 행 dict, 아니면 None (배지만).

    게이트: `配信` 계열 키워드 AND (구체 미래 날짜[시각 옵션] OR 온전한 YT URL).
    오탐 가드: 남의 리트윗 / 후기(과거 시각 + 미래마커 없음) / 날짜·URL 둘 다 없음.
    URL 만 있고 날짜 없음 → None (§3 특례 — RSS 가 그 영상을 잡는다).
    """
    if not text:
        return None
    t = normalize(text)
    if _HANDLE_HEAD_RE.match(t):
        return None
    if not _SCHED_KW_RE.search(t):
        return None

    now = _parse_iso(now_iso) or datetime.now(UTC)
    now_jst = now.astimezone(JST)

    date_iso, _dl = _pick_event_date(t, now_jst)
    time_hm = _first_time(t)
    has_future = any(w in t for w in _FUTURE_WORD)
    if not date_iso and time_hm and has_future:
        date_iso = now_jst.strftime("%Y-%m-%d")

    m = YT_VIDEO_RE.search(t)
    video_id = m.group(1) if m else None
    url = None
    if m:
        u = m.group(0)
        url = u if u.startswith("http") else "https://" + u

    if not date_iso:
        return None                       # URL만 / 아무 날짜도 없음 → 배지만

    time_tbd = time_hm is None
    start_jst = _start_from(date_iso, time_hm)

    if (_RECAP_RE.search(t) and not has_future
            and start_jst < now_jst - timedelta(minutes=30)):
        return None                       # 후기

    # time_tbd 는 "그 날짜" 자리표시자 — <date>T00:00:00Z 리터럴로 저장(계약 §2).
    start_z = (f"{date_iso}T00:00:00Z" if time_tbd
               else start_jst.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    members_only = bool(_MEMBERS_ONLY_RE.search(t))
    tid = _tweet_id(tag)
    info_at = snowflake_iso(tid) or now_iso

    return {
        "status": "scheduled",
        "channel_key": channel_key,
        "sched_id": f"sched:{channel_key}:{start_z}",
        "video_id": video_id,
        "title": None,
        "url": url or (f"https://www.youtube.com/@{handle}" if handle else None),
        "thumbnail": None,
        "scheduled_start": start_z,
        "time_tbd": time_tbd,
        "start_approx": "頃" in t,
        "kind": _kind_of(t),
        "icon": None,
        "members_only": members_only,
        "collab_with": [],
        "source": "personal",
        "source_at": now_iso,
        "info_source": "personal",
        "info_at": info_at,
        "api_start_seen": None,
        "first_seen": now_iso,
        "last_updated": now_iso,
        "assumed_live": False,
        "expires_at": _expires_at(start_jst, time_tbd=time_tbd, members_only=members_only),
    }


def _same_broadcast(a: dict, b: dict) -> bool:
    """두 행이 같은 방송인가 (§4). URL/video_id 동일성 먼저, 아니면 채널+시각/날짜 폴백."""
    if a.get("channel_key") != b.get("channel_key"):
        return False
    av, bv = a.get("video_id"), b.get("video_id")
    if av and bv:
        return av == bv                   # 다르면 다른 방송 (재시작 등)
    as_, bs = a.get("scheduled_start"), b.get("scheduled_start")
    if not as_ or not bs:
        return False
    if a.get("time_tbd") or b.get("time_tbd"):
        return _jst_date(as_) == _jst_date(bs)     # 같은 JST 날짜
    return abs(_epoch(as_) - _epoch(bs)) <= _SAME_BROADCAST_SEC


def _incoming_wins(cur: dict, inc: dict) -> bool:
    """붕괴 시 생존 우선순위: video_id > 상위 단계 > info_at 최신 > bdp_schedule > personal."""
    if bool(inc.get("video_id")) != bool(cur.get("video_id")):
        return bool(inc.get("video_id"))
    cs, is_ = _STAGE.get(cur.get("status"), 0), _STAGE.get(inc.get("status"), 0)
    if cs != is_:
        return is_ > cs
    ca, ia = cur.get("info_at") or "", inc.get("info_at") or ""
    if ca != ia:
        return ia > ca
    return _SRC_RANK.get(inc.get("info_source"), 0) > _SRC_RANK.get(cur.get("info_source"), 0)


def _apply_tweet_time(cur: dict, inc: dict, now_iso: str) -> None:
    """cur 가 생존한 행. inc(트윗)가 더 나중이고 cur 단계 필수조건을 충족하면 시각 override."""
    if (inc.get("info_at") or "") <= (cur.get("info_at") or ""):
        return
    if cur.get("status") in ("upcoming", "live"):
        if inc.get("time_tbd") or not inc.get("scheduled_start"):
            return                        # upcoming 수정엔 date+time 필요
        cur["api_start_seen"] = cur.get("scheduled_start")   # API 가 말하던 값 기억
    cur["scheduled_start"] = inc["scheduled_start"]
    cur["time_tbd"] = bool(inc.get("time_tbd"))
    cur["start_approx"] = bool(inc.get("start_approx"))
    cur["info_source"] = inc.get("info_source", "personal")
    cur["info_at"] = inc["info_at"]
    cur["last_updated"] = now_iso
    if cur.get("status") == "scheduled":
        sj = _parse_iso(cur["scheduled_start"]).astimezone(JST)
        cur["expires_at"] = _expires_at(
            sj, time_tbd=cur["time_tbd"], members_only=bool(cur.get("members_only")))


_INHERIT = ("video_id", "url", "thumbnail", "title", "kind", "icon", "collab_with", "first_seen")


def merge_personal_schedule(prev_schedule: dict, rows: list[dict], now_iso: str) -> dict:
    """개인 트윗 scheduled 행을 schedule.json 에 upsert (replace-by-date 아님)."""
    prev = prev_schedule or {}
    bcasts = [dict(b) for b in prev.get("broadcasts", [])]
    for row in rows:
        idx = next((i for i, b in enumerate(bcasts) if _same_broadcast(b, row)), None)
        if idx is None:
            bcasts.append(row)
            continue
        cur = bcasts[idx]
        if _incoming_wins(cur, row):
            merged = dict(row)
            for k in _INHERIT:
                if not merged.get(k) and cur.get(k):
                    merged[k] = cur[k]
            bcasts[idx] = merged
        else:
            _apply_tweet_time(cur, row, now_iso)
            for k in ("url", "video_id", "kind"):
                if not cur.get(k) and row.get(k):
                    cur[k] = row[k]
    # 실물로 확정된 video_id 를 가진 personal 자리표시는 버린다 (reconcile 이 정리하지만 겹침 방지)
    resolved = {b.get("video_id") for b in bcasts
                if b.get("video_id") and b.get("status") != "scheduled"}
    bcasts = [b for b in bcasts if not (
        b.get("source") == "personal" and b.get("status") == "scheduled"
        and b.get("video_id") in resolved)]

    out = dict(prev)
    out["broadcasts"] = _sort_sched(bcasts)
    out["generated_at"] = now_iso
    return out


def _sort_sched(bcasts: list[dict]) -> list[dict]:
    rank = {"live": 0, "upcoming": 1, "scheduled": 2}
    return sorted(bcasts, key=lambda b: (
        rank.get(b.get("status"), 3),
        b.get("scheduled_start") is None,
        b.get("scheduled_start") or "",
        b.get("video_id") or b.get("sched_id") or "",
    ))


def apply_overrides(new_schedule: dict, prev_schedule: dict, now_iso: str) -> dict:
    """(handlers 후처리) reconcile 이 API 로 재구성한 schedule 에 트윗 유래 시각 override 재적용.

    prev 행 info_source ∈ (personal|bdp_schedule|appearance) 이고 time_tbd 아님:
      · reconcile 이 이번 tick 에 API 로 scheduled_start 를 얻음
        - api_now == prev.api_start_seen (override 없으면 prev.scheduled_start)  → 트윗값 유지
        - 다름(스트림 실제 수정) → API 승 (info_source="api", api_start_seen=null)
      · reconcile 미해결(scheduled 유지) → prev 시각·provenance 그대로
    """
    prev = prev_schedule or {}
    new = new_schedule or {}
    prev_rows = prev.get("broadcasts", []) or []
    for b in new.get("broadcasts", []) or []:
        pb = next((p for p in prev_rows if _same_broadcast(p, b)), None)
        if pb is None:
            continue
        psrc = pb.get("info_source")
        if psrc not in ("personal", "bdp_schedule", "appearance"):
            continue
        if pb.get("time_tbd") or not pb.get("scheduled_start"):
            # 시각 미정 트윗 → API 가 채우면 그대로 둔다 (override 아님)
            continue
        api_resolved = b.get("status") in ("upcoming", "live") and bool(b.get("video_id"))
        if not api_resolved:
            b["scheduled_start"] = pb["scheduled_start"]
            b["time_tbd"] = bool(pb.get("time_tbd"))
            b["info_source"] = psrc
            b["info_at"] = pb.get("info_at")
            b["api_start_seen"] = pb.get("api_start_seen")
            continue
        api_now = b.get("scheduled_start")
        baseline = pb.get("api_start_seen") or pb.get("scheduled_start")
        if api_now and baseline and abs(_epoch(api_now) - _epoch(baseline)) <= 60:
            # API 값 안 바뀜 → 트윗값 유지
            b["scheduled_start"] = pb["scheduled_start"]
            b["info_source"] = psrc
            b["info_at"] = pb.get("info_at")
            b["api_start_seen"] = pb.get("api_start_seen") or api_now
        else:
            # 스트림 실제 수정 → API 승
            b["info_source"] = "api"
            b["info_at"] = now_iso
            b["api_start_seen"] = None
    return new


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    CFG = {"channels": {
        "arale": {"x_names": ["仲町あられ"]},
        "yuno": {"x_names": ["千石ユノ"]},
        "nonoka": {"x_names": ["宮永ののか"]},
        "ritsu": {"x_names": ["峰月律"]},
        "miyako": {"x_names": ["藤都子"]},
    }}
    NOW = "2026-09-07T12:00:00Z"

    # ── route_by_title ───────────────────────────────────────────────
    assert route_by_title("仲町あられ", CFG) == "arale"
    assert route_by_title("宮永ののか🐰🩹", CFG) == "nonoka"          # 표시명 뒤 이모지 무시
    assert route_by_title("  藤都子 ", CFG) == "miyako"
    assert route_by_title("夢限大みゅーたいぷ", CFG) == "official"
    assert route_by_title("夢限大みゅーたいぷ公式", CFG) == "official"
    assert route_by_title("", CFG) == "official"                     # 빈 title
    assert route_by_title("だれか知らない人", CFG) == "official"      # 미매칭
    assert route_by_title("jehy", CFG, test_titles=("jehy",)) == "test"
    assert route_by_title("JEHY (sub)", CFG, test_titles=("jehy",)) == "test"
    # 폴백(x_names 없는 cfg)로도 매칭
    assert route_by_title("峰月律", {"channels": {}}) == "ritsu"
    print("[OK] route_by_title")

    # ── parse ───────────────────────────────────────────────────────
    TAG = "p#https://x.com/#1tweet-2096552878769152326"
    r = parse("＼\nおはよう！今日は22時から歌枠やります🎤\n／", title="仲町あられ",
              tag=TAG, channel_key="arale", now_iso=NOW, handle="arale_yumemita")
    assert r and r["id"] == "2096552878769152326", r
    assert r["text"] == "おはよう！今日は22時から歌枠やります🎤", repr(r["text"])   # 앞뒤 ＼／ 제거
    assert r["url"] == "https://x.com/i/status/2096552878769152326"
    assert r["handle"] == "arale_yumemita"
    assert r["expires_at"] == "2026-09-08T12:00:00Z"                 # +24h
    assert parse("   \n＼／\n  ", title="峰月律", tag=None, channel_key="ritsu", now_iso=NOW) is None
    # 태그 없음 → 합성 id, url 없음
    r2 = parse("ねむい", title="峰月律", tag=None, channel_key="ritsu", now_iso=NOW)
    assert r2["id"].startswith("p") and r2["url"] is None, r2
    print("[OK] parse")

    # ── merge_tweet ─────────────────────────────────────────────────
    T, A = default_tweets(), default_archive()
    T, A, ch, m = merge_tweet(T, r, NOW, archive=A)
    assert ch and m == "added" and T["tweets"]["arale"]["id"] == "2096552878769152326"
    # 같은 트윗 재도착 → dup
    _, _, ch, m = merge_tweet(T, r, NOW, archive=A)
    assert not ch and m == "dup", m
    # 더 오래된 id → dup (교체 안 함)
    older = dict(r, id="2096000000000000000", text="古い", received_at=NOW,
                 expires_at="2026-09-08T12:00:00Z")
    _, _, ch, m = merge_tweet(T, older, NOW, archive=A)
    assert not ch and m == "dup", m
    # 더 최신 id → replaced, 기존 건 아카이브로
    newer = dict(r, id="2096999999999999999", text="新しい",
                 url="https://x.com/i/status/2096999999999999999",
                 received_at="2026-09-07T15:00:00Z", expires_at="2026-09-08T15:00:00Z")
    T, A, ch, m = merge_tweet(T, newer, "2026-09-07T15:00:00Z", archive=A)
    assert ch and m == "replaced" and T["tweets"]["arale"]["text"] == "新しい"
    assert len(A["tweets"]) == 1 and A["tweets"][0]["id"] == "2096552878769152326"
    assert A["tweets"][0]["archived_reason"] == "replaced"
    # 이미 만료된 트윗 인입 → stale
    exp_in = dict(r, id="2097000000000000000", channel_key="yuno",
                  expires_at="2026-09-06T00:00:00Z")
    _, _, ch, m = merge_tweet(T, exp_in, NOW, archive=A)
    assert not ch and m == "stale", m
    print("[OK] merge_tweet (added/dup/replaced/stale)")

    # ── sweep_expired ───────────────────────────────────────────────
    S = {"generated_at": None, "tweets": {
        "arale": dict(r, expires_at="2026-09-06T00:00:00Z"),   # 지남
        "yuno": dict(r, channel_key="yuno", id="2098000000000000000",
                     expires_at="2099-01-01T00:00:00Z"),        # 미래
    }}
    s_out, s_arch, removed = sweep_expired(S, default_archive(), NOW)
    assert removed == ["arale"] and "yuno" in s_out["tweets"] and "arale" not in s_out["tweets"]
    assert s_arch["tweets"][0]["archived_reason"] == "expired"
    assert sweep_expired(s_out, s_arch, NOW)[2] == []            # 두 번째 sweep 은 no-op
    print("[OK] sweep_expired")

    # ═══ v2.8.1 — parse_schedule / merge_personal_schedule / apply_overrides ═══
    SNOW = "2026-09-07T12:00:00Z"

    # S-A: 날짜+시각+키워드 → scheduled 행
    a = parse_schedule("今日22時から歌枠配信します！\nみんな来てね〜", channel_key="miyako",
                       tag="p#x#1tweet-2096795604856836521", now_iso=SNOW, handle="miyako_yumemita")
    assert a and a["status"] == "scheduled" and a["source"] == "personal", a
    assert a["scheduled_start"] == "2026-09-07T13:00:00Z" and a["time_tbd"] is False, a
    assert a["kind"] == "song" and a["expires_at"] == "2026-09-07T16:00:00Z"
    assert a["info_source"] == "personal" and a["info_at"] == snowflake_iso("2096795604856836521")
    print("[OK] parse_schedule  (날짜+시각 → scheduled +3h TTL)")

    # S-B: 날짜만(시각 없음) → time_tbd, TTL 자정
    b1 = parse_schedule("9月13日に配信あります！詳細は後ほど", channel_key="yuno",
                        tag=None, now_iso=SNOW)
    assert b1 and b1["time_tbd"] is True and b1["scheduled_start"] == "2026-09-13T00:00:00Z", b1
    assert b1["expires_at"] == "2026-09-13T15:00:00Z", b1   # 9/14 00:00 JST = 9/13 15:00Z
    print("[OK] parse_schedule  (날짜만 → time_tbd, 자정 TTL)")

    # S-C: 게이트 미통과 / 오탐 가드
    assert parse_schedule("今日は天気がいいね", channel_key="ritsu", tag=None, now_iso=SNOW) is None
    assert parse_schedule("RT @someone: 22時から配信します 9/13", channel_key="ritsu",
                          tag=None, now_iso=SNOW) is None           # 남의 리트윗
    assert parse_schedule("昨日の配信ありがとうございました！20時まで楽しかった",
                          channel_key="ritsu", tag=None, now_iso=SNOW) is None  # 후기(날짜 없음)
    assert parse_schedule("配信URLはこちら https://youtube.com/live/abcdEFGH123",
                          channel_key="ritsu", tag=None, now_iso=SNOW) is None  # URL만 → None
    print("[OK] parse_schedule  (키워드 없음 / RT / 후기 / URL만 → None)")

    # S-D: URL 있는 예고 → video_id 추출
    d = parse_schedule("本日21:00〜 生配信！\nhttps://www.youtube.com/watch?v=dQw4w9WgXcQ",
                       channel_key="arale", tag=None, now_iso=SNOW)
    assert d and d["video_id"] == "dQw4w9WgXcQ", d
    assert d["scheduled_start"] == "2026-09-07T12:00:00Z", d
    assert d["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print("[OK] parse_schedule  (본문 YT URL → video_id)")

    # S-E: merge_personal_schedule — 신규 append
    sched = {"broadcasts": [], "generated_at": None}
    sched = merge_personal_schedule(sched, [a], SNOW)
    assert len(sched["broadcasts"]) == 1 and sched["broadcasts"][0]["channel_key"] == "miyako"

    # S-F: 같은 방송에 공식 bdp 행이 나중에 → 붕괴 (video_id 없으니 채널+±90분)
    bdp = {"status": "scheduled", "channel_key": "miyako", "source": "bdp_schedule",
           "sched_id": "sched:miyako:2026-09-07T13:15:00Z", "video_id": None,
           "scheduled_start": "2026-09-07T13:15:00Z", "time_tbd": False,
           "info_source": "bdp_schedule", "info_at": "2026-09-07T13:00:00Z",
           "collab_with": [], "expires_at": "2026-09-07T16:15:00Z"}
    sched2 = merge_personal_schedule(sched, [dict(bdp)], SNOW)
    assert len(sched2["broadcasts"]) == 1, sched2   # 하나로 붕괴
    surv = sched2["broadcasts"][0]
    assert surv["info_source"] == "bdp_schedule", surv   # bdp info_at(13:00) > personal(트윗시각)
    print("[OK] merge_personal_schedule  (append + 같은 방송 붕괴)")

    # S-G: apply_overrides — 트윗이 upcoming 시각을 당겨놨고 API 는 원래 값 유지 → 트윗값 유지
    prev = {"broadcasts": [{
        "video_id": "vidX", "channel_key": "arale", "status": "upcoming",
        "scheduled_start": "2026-09-07T13:30:00Z",   # 트윗이 당겨놓음
        "time_tbd": False, "info_source": "personal", "info_at": "2026-09-07T12:50:00Z",
        "api_start_seen": "2026-09-07T13:00:00Z",     # API 는 원래 13:00
    }]}
    new = {"broadcasts": [{
        "video_id": "vidX", "channel_key": "arale", "status": "upcoming",
        "scheduled_start": "2026-09-07T13:00:00Z",    # reconcile 이 API 로 다시 채움
        "thumbnail": "t.jpg",
    }]}
    out = apply_overrides(new, prev, "2026-09-07T15:00:00Z")
    ob = out["broadcasts"][0]
    assert ob["scheduled_start"] == "2026-09-07T13:30:00Z", ob     # 트윗값 유지
    assert ob["info_source"] == "personal" and ob["thumbnail"] == "t.jpg"

    # S-H: 스트림이 실제 수정됨(API 값 변경) → API 승
    new2 = {"broadcasts": [dict(new["broadcasts"][0], scheduled_start="2026-09-07T14:00:00Z")]}
    out2 = apply_overrides(new2, prev, "2026-09-07T15:00:00Z")
    ob2 = out2["broadcasts"][0]
    assert ob2["scheduled_start"] == "2026-09-07T14:00:00Z" and ob2["info_source"] == "api"
    assert ob2["api_start_seen"] is None
    print("[OK] apply_overrides  (API 불변→트윗 유지 / API 변경→API 승)")

    print("\nSUCCESS: xtweet self-test 통과")
