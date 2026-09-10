"""멤버 개인 트윗 — android.title 라우팅 + tweets.json 계약 + (v3) preview 병합 (순수 함수).

계약: docs/plan/v3_impl_spec.md §2 (WP-8) · docs/plan/v2_8_personal_tweets.md (v2 하위호환)
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
from . import preview  # ponytail: v3 preview 스키마 헬퍼

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
    """normalize + 앞뒤 장식/빈 줄 제거 + 길이 제한. 표시용이라 VS16 은 보존."""
    lines = [ln.rstrip() for ln in normalize(text or "", strip_vs16=False).split("\n")]
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
    """개인 트윗 1건 dict. text 가 (장식 제거 후) 비면 None. 리트윗/타인글은 필터."""
    body = _clean_text(text)
    if not body:
        return None
    if _HANDLE_HEAD_RE.match(body):
        return None                          # 리트윗/타인글(@핸들: 패턴) 필터
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
        "text_ko": None,                     # handlers 가 llm.translate 로 채움 (v3)
        "url": None if synthetic else f"https://x.com/i/status/{tid}",
        "handle": handle or "",
        "received_at": now_iso,
        "expires_at": exp,
    }


# ── tweets.json 계약 I (v3.1 — 유닛당 스레드) ─────────────────────────────
#   tweets[ck] = [ <메시지 dict> ]  최신이 뒤, 최대 MAX_THREAD 개.
#   v2.8 단건(dict) 데이터는 _as_list 가 [dict] 로 감싸 하위호환.

MAX_THREAD = 5   # 유닛당 최근 트윗 최대 개수


def default_tweets() -> dict:
    return {"generated_at": None, "tweets": {}}


def default_archive() -> dict:
    return {"tweets": []}


_ROW_KEYS = ("channel_key", "id", "text", "text_ko", "url", "handle", "received_at", "expires_at")


def _as_list(v) -> list:
    """계약 I 하위호환: tweets[ck] 가 dict(v2.8 단건)면 [dict], list 면 dict 만 추림, 그 외 []."""
    if isinstance(v, list):
        return [m for m in v if isinstance(m, dict)]
    if isinstance(v, dict):
        return [v]
    return []


def _sort_key(m: dict):
    """received_at 오름차순 + Snowflake id tiebreak (합성 id 는 0)."""
    sid = str(m.get("id") or "")
    return (m.get("received_at") or "", int(sid) if sid.isdigit() else 0)


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


def merge_thread(prev: dict, incoming: dict, now_iso: str, *,
                 archive: dict | None = None) -> tuple[dict, dict, bool, str]:
    """유닛 스레드에 incoming 1건 병합. (new_tweets, new_archive, changed, mode).

    mode ∈ added | rolled | dup | stale.
      dup    = 같은 id 이미 있음 (연타 중복 도착)
      rolled = 병합 후 MAX_THREAD 초과 → 가장 오래된 것(들)을 archive("rolled") 로
      stale  = incoming 이 이미 만료 / ck·id 없음
    """
    prev = prev or default_tweets()
    arch = archive if archive is not None else default_archive()
    ck = incoming.get("channel_key")
    if not ck or not incoming.get("id") or _reached(incoming.get("expires_at"), now_iso):
        return prev, arch, False, "stale"

    tweets = dict(prev.get("tweets", {}))
    lst = _as_list(tweets.get(ck))
    if any(str(m.get("id")) == str(incoming.get("id")) for m in lst):
        return prev, arch, False, "dup"

    row = {k: incoming.get(k) for k in _ROW_KEYS}
    lst = sorted(lst + [row], key=_sort_key)          # 최신이 뒤

    mode = "added"
    while len(lst) > MAX_THREAD:
        arch = _archive_push(arch, lst.pop(0), now_iso, "rolled")   # 오래된 것부터
        mode = "rolled"

    tweets[ck] = lst
    out = dict(prev)
    out["tweets"] = tweets
    out["generated_at"] = now_iso
    return out, arch, True, mode


# v2.8 이름 하위호환 (단건 merge = 스레드 병합 1건).
merge_tweet = merge_thread


def sweep_expired(prev: dict, archive: dict, now_iso: str
                  ) -> tuple[dict, dict, list[str]]:
    """스레드 안 expires_at 지난 메시지 → tweet_archive.json.
    (new_tweets, new_archive, touched_keys). 스레드가 비면 그 키도 제거된다."""
    prev = prev or default_tweets()
    archive = archive or default_archive()
    out_tweets, touched = {}, []
    for ck, v in (prev.get("tweets") or {}).items():
        lst = _as_list(v)
        kept = []
        for m in lst:
            if _reached(m.get("expires_at"), now_iso):
                archive = _archive_push(archive, m, now_iso, "expired")
            else:
                kept.append(m)
        if len(kept) != len(lst):
            touched.append(ck)
        if kept:
            out_tweets[ck] = kept
    if not touched:
        return prev, archive, []
    out = dict(prev)
    out["tweets"] = out_tweets
    out["generated_at"] = now_iso
    return out, archive, touched


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
    """개인 트윗이 방송 예고면 preview 아이템 (v3 schema), 아니면 None (배지만).

    (v3) state="announced", source="personal" 로 설정.
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
    membership = bool(_MEMBERS_ONLY_RE.search(t))
    tid = _tweet_id(tag)
    info_at = snowflake_iso(tid) or now_iso

    # (v3) preview 아이템으로 반환 (make_item 이 id/state_since/expires_at 계산)
    return preview.make_item(
        channel_key=channel_key,
        state="announced",
        source="personal",
        now_iso=now_iso,
        video_id=video_id,
        title=None,
        url=url or (f"https://www.youtube.com/@{handle}" if handle else None),
        thumbnail=None,
        scheduled_start=start_z,
        time_tbd=time_tbd,
        kind=_kind_of(t),
        membership=membership,
        collab_with=[],
        info_source="personal",
        info_at=info_at,
        api_start_seen=None,
        first_seen=now_iso,
        assumed_live=False,
    )


# ═══ v3 — preview.json 아이템 머지 ═════════════════════════════════════
#   개인 트윗 예고를 preview 아이템으로 변환·병합.
#   계약: docs/plan/v3_impl_spec.md §2 (WP-8)


def merge_personal_schedule(prev_items: list[dict], inc: dict, now_iso: str) -> tuple[list[dict], bool]:
    """개인 트윗 예고 아이템을 preview.items 에 upsert.

    Args:
        prev_items: 이전 preview.json 의 items 배열 (또는 None)
        inc: parse_schedule() 의 결과 (preview 아이템)
        now_iso: 현재 시각 (UTC ISO)

    Returns:
        (new_items, changed) — new_items 는 정렬되지 않음 (호출부 책임)
    """
    prev = prev_items or []
    items = [dict(i) for i in prev]

    # 같은 방송 찾기
    matched = preview.match_item(items, inc)

    if matched is None:
        # 새로운 아이템
        items.append(inc)
        return items, True

    # 기존 아이템과 merge
    idx = items.index(matched)
    cur = items[idx]
    original = dict(cur)

    # video_id 우선 (없으면 새 값)
    if inc.get("video_id"):
        cur["video_id"] = inc["video_id"]

    # info_at 최신이면 시각 정보 업데이트
    if (inc.get("info_at") or "") > (cur.get("info_at") or ""):
        cur["scheduled_start"] = inc["scheduled_start"]
        cur["time_tbd"] = inc.get("time_tbd", False)
        cur["info_at"] = inc["info_at"]
        cur["info_source"] = inc.get("info_source", "personal")

    cur["last_updated"] = now_iso

    changed = (cur != original)
    return items, changed


def apply_overrides(new_items: list[dict], prev_items: list[dict], now_iso: str) -> list[dict]:
    """(handlers 후처리) reconcile 의 API 재구성에 트윗 유래 시각 override 재적용.

    prev 행 info_source ∈ (personal|bdp_schedule|appearance) 이고 time_tbd 아님:
      · reconcile 이 이번 tick 에 API 로 scheduled_start 를 얻음
        - api_now == prev.api_start_seen (override 없으면 prev.scheduled_start) → 트윗값 유지
        - 다름(스트림 실제 수정) → API 승 (info_source="api", api_start_seen=null)
      · reconcile 미해결(announced 유지) → prev 시각·provenance 그대로

    Args:
        new_items: reconcile 후 preview.json 의 items 배열
        prev_items: 이전 preview.json 의 items 배열
        now_iso: 현재 시각 (UTC ISO)

    Returns:
        override 적용된 new_items
    """
    prev = prev_items or []
    new = [dict(b) for b in (new_items or [])]

    for b in new:
        # 이전 아이템에서 같은 방송 찾기
        pb = preview.match_item(prev, b)
        if pb is None:
            continue

        psrc = pb.get("info_source")
        if psrc not in ("personal", "bdp_schedule", "appearance"):
            continue

        # time_tbd 아이템은 override 대상 아님
        if pb.get("time_tbd") or not pb.get("scheduled_start"):
            continue

        # API 로 upcoming/watching/live 해결된가? (video_id 필수)
        api_resolved = b.get("state") in ("upcoming", "watching", "live") and bool(b.get("video_id"))

        if not api_resolved:
            # API 미해결 (announced 유지) → 이전 정보 그대로
            b["scheduled_start"] = pb["scheduled_start"]
            b["time_tbd"] = bool(pb.get("time_tbd"))
            b["info_source"] = psrc
            b["info_at"] = pb.get("info_at")
            b["api_start_seen"] = pb.get("api_start_seen")
            continue

        # API 해결 — baseline 대비 변경 여부 판정
        api_now = b.get("scheduled_start")
        baseline = pb.get("api_start_seen") or pb.get("scheduled_start")

        if api_now and baseline and abs(_epoch(api_now) - _epoch(baseline)) <= 60:
            # API 값 안 바뀜 (60초 이내) → 트윗값 유지
            b["scheduled_start"] = pb["scheduled_start"]
            b["info_source"] = psrc
            b["info_at"] = pb.get("info_at")
            b["api_start_seen"] = pb.get("api_start_seen") or api_now
        else:
            # 스트림 실제 수정 (60초 이상 차이) → API 승
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
    assert r["text_ko"] is None                                       # (v3) text_ko 초기값
    assert parse("   \n＼／\n  ", title="峰月律", tag=None, channel_key="ritsu", now_iso=NOW) is None
    # 태그 없음 → 합성 id, url 없음
    r2 = parse("ねむい", title="峰月律", tag=None, channel_key="ritsu", now_iso=NOW)
    assert r2["id"].startswith("p") and r2["url"] is None, r2
    # (v3) 리트윗/타인글 필터
    assert parse("@arale: 今日の配信楽しみ〜", title="峰月律", tag=None, channel_key="ritsu", now_iso=NOW) is None
    assert parse("@someone：話題です", title="峰月律", tag=None, channel_key="ritsu", now_iso=NOW) is None
    assert parse("RT @janesmith: 配信時間変更", title="峰月律", tag=None, channel_key="ritsu", now_iso=NOW) is None
    print("[OK] parse (+ v3 리트윗 필터)")

    # ── merge_thread (계약 I — 스레드) ─────────────────────────────
    T, A = default_tweets(), default_archive()
    T, A, ch, m = merge_thread(T, r, NOW, archive=A)
    assert ch and m == "added" and _as_list(T["tweets"]["arale"])[-1]["id"] == "2096552878769152326"
    # 같은 id 재도착 → dup
    _, _, ch, m = merge_thread(T, r, NOW, archive=A)
    assert not ch and m == "dup", m
    # 다른 id 3건 연타 → 스레드에 최신이 뒤로 쌓임 (received_at 정렬)
    for i, rid in enumerate(("2096600000000000000", "2096700000000000000", "2096800000000000000")):
        msg = dict(r, id=rid, text=f"연타{i}",
                   received_at=f"2026-09-07T12:0{i+1}:00Z",
                   expires_at="2026-09-08T13:00:00Z")
        T, A, ch, m = merge_thread(T, msg, "2026-09-07T12:05:00Z", archive=A)
        assert ch and m == "added", m
    thread = _as_list(T["tweets"]["arale"])
    assert [x["id"] for x in thread] == ["2096552878769152326", "2096600000000000000",
                                         "2096700000000000000", "2096800000000000000"], thread
    # 5개째 → 아직 cap 안 넘음(added), 6개째 → rolled (가장 오래된 것 archive)
    T, A, ch, m = merge_thread(T, dict(r, id="2096900000000000000", text="5번째",
                                       received_at="2026-09-07T12:04:00Z",
                                       expires_at="2026-09-08T13:00:00Z"),
                               "2026-09-07T12:05:00Z", archive=A)
    assert ch and m == "added" and len(_as_list(T["tweets"]["arale"])) == 5
    T, A, ch, m = merge_thread(T, dict(r, id="2097100000000000000", text="6번째",
                                       received_at="2026-09-07T12:06:00Z",
                                       expires_at="2026-09-08T13:00:00Z"),
                               "2026-09-07T12:06:00Z", archive=A)
    assert ch and m == "rolled" and len(_as_list(T["tweets"]["arale"])) == 5
    assert any(x["archived_reason"] == "rolled" and x["id"] == "2096552878769152326"
               for x in A["tweets"]), A["tweets"]
    # 이미 만료된 트윗 인입 → stale
    _, _, ch, m = merge_thread(T, dict(r, id="2097200000000000000", channel_key="yuno",
                                       expires_at="2026-09-06T00:00:00Z"), NOW, archive=A)
    assert not ch and m == "stale", m
    # v2.8 단건(dict) 데이터 위에 병합 → [dict] 로 승계 후 append
    LEGACY = {"generated_at": None, "tweets": {"yuno": dict(r, channel_key="yuno",
              id="2098000000000000000", expires_at="2099-01-01T00:00:00Z")}}
    L2, _, ch, m = merge_thread(LEGACY, dict(r, channel_key="yuno", id="2098100000000000000",
                                             received_at="2026-09-07T13:00:00Z",
                                             expires_at="2099-01-01T00:00:00Z"),
                                "2026-09-07T13:00:00Z")
    assert ch and [x["id"] for x in _as_list(L2["tweets"]["yuno"])] == \
        ["2098000000000000000", "2098100000000000000"], L2["tweets"]["yuno"]
    print("[OK] merge_thread (added/dup/rolled/stale + 단건 하위호환)")

    # ── sweep_expired (메시지별) ───────────────────────────────────
    S = {"generated_at": None, "tweets": {
        "arale": [
            dict(r, id="a1", expires_at="2026-09-06T00:00:00Z"),   # 지남 → archive
            dict(r, id="a2", expires_at="2099-01-01T00:00:00Z"),   # 미래 → 유지
        ],
        "yuno": dict(r, channel_key="yuno", id="y1",
                     expires_at="2026-09-06T00:00:00Z"),           # 단건 dict + 지남 → 키 제거
    }}
    s_out, s_arch, touched = sweep_expired(S, default_archive(), NOW)
    assert sorted(touched) == ["arale", "yuno"], touched
    assert [x["id"] for x in _as_list(s_out["tweets"]["arale"])] == ["a2"]
    assert "yuno" not in s_out["tweets"]
    assert {x["archived_reason"] for x in s_arch["tweets"]} == {"expired"}
    assert sweep_expired(s_out, s_arch, NOW)[2] == []              # 두 번째 sweep 은 no-op
    print("[OK] sweep_expired (메시지별 · 빈 스레드 키 제거)")

    # ═══ v3 — parse_schedule / merge_personal_schedule / apply_overrides ═══
    SNOW = "2026-09-07T12:00:00Z"

    # S-A: 날짜+시각+키워드 → announced preview 아이템
    a = parse_schedule("今日22時から歌枠配信します！\nみんな来てね〜", channel_key="miyako",
                       tag="p#x#1tweet-2096795604856836521", now_iso=SNOW, handle="miyako_yumemita")
    assert a and a["state"] == "announced" and a["source"] == "personal", a
    assert a["scheduled_start"] == "2026-09-07T13:00:00Z" and a["time_tbd"] is False, a
    assert a["kind"] == "song" and a["info_source"] == "personal"
    assert a["id"].startswith("pv_") and a["first_seen"] == SNOW
    assert a["info_at"] == snowflake_iso("2096795604856836521")
    print("[OK] parse_schedule (v3)  (날짜+시각 → announced preview +3h TTL)")

    # S-B: 날짜만(시각 없음) → time_tbd, TTL 자정
    b1 = parse_schedule("9月13日に配信あります！詳細は後ほど", channel_key="yuno",
                        tag=None, now_iso=SNOW)
    assert b1 and b1["time_tbd"] is True and b1["scheduled_start"] == "2026-09-13T00:00:00Z", b1
    assert b1["state"] == "announced" and b1["expires_at"] == "2026-09-13T15:00:00Z"
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
    assert d and d["video_id"] == "dQw4w9WgXcQ" and d["state"] == "announced", d
    assert d["scheduled_start"] == "2026-09-07T12:00:00Z", d
    assert d["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print("[OK] parse_schedule  (본문 YT URL → video_id)")

    # S-E: merge_personal_schedule — 신규 append, changed=True
    items, ch = merge_personal_schedule([], a, SNOW)
    assert ch and len(items) == 1 and items[0]["channel_key"] == "miyako"
    assert items[0]["id"] == a["id"]  # id 유지

    # S-F: 같은 방송에 다른 source 예고 → upsert (info_at 최신 우선)
    bdp = preview.make_item(
        channel_key="miyako", state="announced", source="bdp_schedule", now_iso="2026-09-07T13:00:00Z",
        scheduled_start="2026-09-07T13:15:00Z", time_tbd=False,
        info_source="bdp_schedule", info_at="2026-09-07T13:00:00Z"
    )
    items2, ch2 = merge_personal_schedule(items, bdp, SNOW)
    assert ch2 and len(items2) == 1, items2  # 하나로 merge
    surv = items2[0]
    # bdp info_at(13:00) > personal 트윗시각(SNOW 보다 먼저) → bdp 정보 우선
    assert surv["info_source"] == "bdp_schedule"
    print("[OK] merge_personal_schedule  (append + upsert)")

    # S-G: apply_overrides — 트윗이 시각 override, API 는 원래 값 유지 → 트윗값 유지
    prev_item = preview.make_item(
        channel_key="arale", state="upcoming", source="personal", now_iso="2026-09-07T12:50:00Z",
        video_id="vidX", scheduled_start="2026-09-07T13:30:00Z",  # 트윗이 당겨놓음
        info_source="personal", info_at="2026-09-07T12:50:00Z",
        api_start_seen="2026-09-07T13:00:00Z"  # API 는 원래 13:00
    )
    new_item = preview.make_item(
        channel_key="arale", state="upcoming", source="api", now_iso=SNOW,
        video_id="vidX", scheduled_start="2026-09-07T13:00:00Z",  # reconcile 이 API 로 재설정
        thumbnail="t.jpg", info_source="api"
    )
    out = apply_overrides([new_item], [prev_item], SNOW)
    ob = out[0]
    assert ob["scheduled_start"] == "2026-09-07T13:30:00Z", ob     # 트윗값 유지
    assert ob["info_source"] == "personal" and ob["thumbnail"] == "t.jpg"
    print("[OK] apply_overrides  (API 불변→트윗 유지)")

    # S-H: 스트림이 실제 수정됨(API 값 변경) → API 승
    new_item2 = preview.make_item(
        channel_key="arale", state="upcoming", source="api", now_iso=SNOW,
        video_id="vidX", scheduled_start="2026-09-07T14:00:00Z",  # API 실제 변경
        thumbnail="t.jpg", info_source="api"
    )
    out2 = apply_overrides([new_item2], [prev_item], SNOW)
    ob2 = out2[0]
    assert ob2["scheduled_start"] == "2026-09-07T14:00:00Z" and ob2["info_source"] == "api"
    assert ob2["api_start_seen"] is None
    print("[OK] apply_overrides  (API 변경→API 승)")

    print("\nSUCCESS: xtweet self-test 통과")
