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

from .xrelay import JST, YT_VIDEO_RE, normalize, _TOMORROW_WORD
from .xnotice import _first_time, _pick_event_date
from . import preview  # ponytail: v3 preview 스키마 헬퍼
from . import statemachine  # v3.6 URL 우선 ingest — build_item_from_video 의 wake 시각 파생

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
          now_iso: str, handle: str = "",
          media: list[str] | None = None, quote: dict | None = None) -> dict | None:
    """개인 트윗 1건 dict. text 가 (장식 제거 후) 비면 None. 리트윗/타인글은 필터.

    media: 본인 트윗에 첨부된 이미지 URL 목록(표시용, 파싱엔 안 씀).
    quote: 인용(QRT)한 남의 트윗 {"text","media"} — 표시만 하고 ingest(파싱)는 안 함.
    """
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
        "media": list(media) if media else [],
        "quote": ({"text": quote.get("text") or "", "media": list(quote.get("media") or []),
                    "text_ko": None} if quote else None),
    }


def find_reused_ko(text: str, *, tweets_data: dict | None = None,
                    archive_data: dict | None = None,
                    notices_data: dict | None = None) -> str | None:
    """`text` 가 tweets/tweet_archive/notices 어디에서든 이미 번역된 적 있으면 그 번역을
    재사용 — 같은 인용(QRT) 원본이 여러 트윗에 반복 등장할 때 LLM 재호출을 피한다
    (v3.4.6). 못 찾으면 None → 호출부가 새로 번역."""
    if not text:
        return None

    def _scan_msgs(msgs):
        for m in msgs or []:
            if not isinstance(m, dict):
                continue
            if m.get("text") == text and m.get("text_ko"):
                return m["text_ko"]
            q = m.get("quote")
            if isinstance(q, dict) and q.get("text") == text and q.get("text_ko"):
                return q["text_ko"]
        return None

    if tweets_data:
        for lst in (tweets_data.get("tweets") or {}).values():
            hit = _scan_msgs(_as_list(lst))
            if hit:
                return hit
    if archive_data:
        hit = _scan_msgs(archive_data.get("tweets"))
        if hit:
            return hit
    if notices_data:
        for n in notices_data.get("notices") or []:
            if isinstance(n, dict) and n.get("title") == text and n.get("title_ko"):
                return n["title_ko"]
    return None


# ── tweets.json 계약 I (v3.1 — 유닛당 스레드) ─────────────────────────────
#   tweets[ck] = [ <메시지 dict> ]  최신이 뒤, 최대 MAX_THREAD 개.
#   v2.8 단건(dict) 데이터는 _as_list 가 [dict] 로 감싸 하위호환.

# ponytail: 유닛당 저장 개수의 안전 상한(폭주 방지용 그릇 크기) — 실제 노출 범위는
# 프론트(tweets.js)가 12시간 창으로 별도 제한한다. 5였을 때는 활발한 멤버가 12시간
# 안에 5건을 넘기면 더 오래된 트윗이 이미 사라져 있었다(버그리포트 20260916 #3).
MAX_THREAD = 50


def default_tweets() -> dict:
    return {"generated_at": None, "tweets": {}}


def default_archive() -> dict:
    return {"tweets": []}


_ROW_KEYS = ("channel_key", "id", "text", "text_ko", "url", "handle", "received_at", "expires_at",
             "media", "quote")


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
    has_tomorrow = any(w in t for w in _TOMORROW_WORD)
    if not date_iso and time_hm:
        if has_future:
            date_iso = now_jst.strftime("%Y-%m-%d")
        elif has_tomorrow:
            date_iso = (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")

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

    # (버그리포트 20260916 #2) 예전엔 여기에 `start_jst < now_jst - 30분` 조건이 더
    # 있었다 — "추출된 날짜가 과거일 때만" 후기로 인정. 그런데 후기 트윗 본문에 우연히
    # 무관한 미래 숫자(예: "9/24까지 기다려지네요" — 게임 출시일 카운트다운)가 있으면
    # _DATE_RE/_TIME_RE 가 그걸 날짜/시각으로 잘못 뽑아 start_jst 가 미래가 돼버리고,
    # ありがとうございました 가 명백히 있는데도 이 조건에 막혀 통과해 버렸다(아라레
    # 실사례: "2時間プレイ…9/24まで待ち遠しい" → "2時間"의 "2時"를 시각으로, "9/24"를
    # 날짜로 오합성해 9/24 02:00 예고로 둔갑). 날짜 추출이 맞다는 전제 위에서만 도는
    # 재검증이라 추출 자체가 틀리면 무력화되는 구조라, 이 시각 비교를 없애고
    # _RECAP_RE + not has_future 만으로 판정한다.
    if _RECAP_RE.search(t) and not has_future:
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


# ═══ v3.6 — URL 우선 ingest ═══════════════════════════════════════════
#   개인 트윗 원문에 유튜브 URL 이 있으면 텍스트 정규식(날짜/시각) 대신 그 영상을
#   `videos.list` 로 직접 조회해 메타(제목/시각/실제 상태)를 확정하는 경로.
#   버그리포트 20260916: 아라레 9/24 오탐(후기 트윗의 "9/24"·"2時間"이 날짜/시각으로
#   오합성됨), 노노카 50분 지연(라이브 시작을 알리는 트윗에 `配信` 계열 키워드가 없어
#   게이트 자체를 못 넘음)이 계기. 네트워크 I/O(videos.list·LLM)는 telegram_app.py 가
#   담당 — 이 섹션은 그 결과를 preview 아이템으로 조립하는 순수 함수만 둔다.
#   계약: 대화 내 설계(2026-09-16), 문서화는 추후 docs/SPEC.md 반영 예정.

_STATE_ORDER = {"announced": 0, "upcoming": 1, "watching": 2, "live": 3, "end": 4}


def resolve_url_host(video_channel_id: str, author_channel_key: str, channels_cfg: dict
                      ) -> tuple[str | None, str | None, list[str] | None]:
    """유튜브 영상의 channel_id 로 등록할 레인(host)을 정한다.

    Returns:
        (channel_key, host, collab_with)
        - 우리 5인 개인 채널   → (그 채널 key, None, [author] 또는 None(본인 채널이면))
        - 그룹 공식 채널       → (channel_order[0], "group", channel_order[1:]) — v3.1.4 팬아웃과 동일.
        - 우리 채널 아님       → (None, None, None) — 호출부가 LLM 참여 확인 후 author 레인에 등록.
    """
    channel_id_to_key = {
        meta.get("channel_id"): key
        for key, meta in (channels_cfg.get("channels") or {}).items()
    }
    key = channel_id_to_key.get(video_channel_id)
    if key is None:
        return None, None, None
    if key == "group":
        order = list(channels_cfg.get("channel_order") or [])
        if not order:
            return None, None, None
        return order[0], "group", (order[1:] or None)
    collab = [author_channel_key] if author_channel_key and author_channel_key != key else None
    return key, None, collab


def build_item_from_video(info, *, channel_key: str, host: str | None,
                          collab_with: list[str] | None, now_iso: str) -> tuple[dict, str | None]:
    """`videos.list` 로 확정된 영상(`info` — collector.youtube.VideoInfo)을 preview 아이템으로.

    build_preview 섹션 1(신규 아이템: 승격→live 반영→FSM derive)을 단일 영상에 그대로
    재현한다 — 나중에 정기 tick 이 같은 video_id 를 발견해도 동일한 결과가 나오도록
    일관성을 맞추기 위함. state 는 announced 로 시작해 API 가 알려주는 실제 상태
    (upcoming/watching/live)로 곧장 승격된다(고정값 아님 — 버그리포트 20260916 #1).

    Returns:
        (item, next_check_at) — next_check_at 은 Cloud Tasks 즉시 enqueue 용(None 이면 불필요).
    """
    url = f"https://www.youtube.com/watch?v={info.video_id}"
    item = preview.make_item(
        channel_key=channel_key,
        state="announced",
        source="personal",
        now_iso=now_iso,
        title=info.title,
        thumbnail=info.thumbnail,
        url=url,
        video_id=info.video_id,
        scheduled_start=info.scheduled_start,
        api_start_seen=info.scheduled_start,
        first_seen=now_iso,
        collab_with=collab_with,
        host=host,
        kind="collab" if (collab_with or host == "group") else None,
        info_source="personal",
        info_at=now_iso,
    )

    if item["state"] == "announced":
        promoted = preview.promote_state(item)
        if promoted != item["state"]:
            item = preview.set_state(item, promoted, now_iso)

    if info.live_state == "live":
        if item["state"] not in ("watching", "live", "end"):
            item = preview.set_state(item, "live", now_iso)
        item["actual_start"] = info.actual_start
        item["concurrent_viewers"] = info.concurrent_viewers

    tick = statemachine.derive(item, now_iso, live_seen=(info.live_state == "live"))
    if tick.next_state != item["state"]:
        item = preview.set_state(item, tick.next_state, now_iso)

    return item, tick.next_check_at


def merge_video_confirmed(prev_items: list[dict], video_id: str, new_item: dict, now_iso: str
                          ) -> tuple[list[dict], bool]:
    """video_id 로 기존 아이템을 찾아 API 확정 값으로 갱신(없으면 append).

    channel_key/host/collab_with 는 처음 만들어질 때 값을 그대로 유지 — 이미 추적 중인
    아이템이면 `new_item` 계산 시점에 넘겨준 host/collab_with 를 신뢰하지 않고 기존 값을
    보존한다(다른 경로가 이미 정확히 배정해 둔 레인을 이 경로가 실수로 바꾸지 않도록).
    상태는 뒷걸음치지 않는다 — 이미 live/watching 인데 지연 도착한 트윗이 announced/
    upcoming 판정을 들고 와도 강등되지 않는다(`_STATE_ORDER`).
    """
    items = [dict(i) for i in (prev_items or [])]
    idx = next((i for i, it in enumerate(items) if it.get("video_id") == video_id), None)
    if idx is None:
        items.append(new_item)
        return items, True

    cur = items[idx]
    original = dict(cur)

    if new_item.get("title") != cur.get("title"):
        cur["title"] = new_item.get("title")
        cur["title_ko"] = None
        cur["needs_tl"] = bool(new_item.get("title"))
    cur["thumbnail"] = new_item.get("thumbnail") or cur.get("thumbnail")
    cur["url"] = new_item.get("url") or cur.get("url")
    cur["api_start_seen"] = new_item.get("api_start_seen")
    if cur.get("info_source") not in ("x-relay",):
        cur["scheduled_start"] = new_item.get("scheduled_start") or cur.get("scheduled_start")
    if new_item.get("actual_start"):
        cur["actual_start"] = new_item["actual_start"]
    if new_item.get("concurrent_viewers") is not None:
        cur["concurrent_viewers"] = new_item["concurrent_viewers"]

    new_state = new_item.get("state")
    cur_state = cur.get("state", "announced")
    if new_state and _STATE_ORDER.get(new_state, 0) > _STATE_ORDER.get(cur_state, 0):
        cur["state"] = new_state
        cur["state_since"] = now_iso

    cur["last_updated"] = now_iso
    items[idx] = cur

    changed = (cur != original)
    return items, changed


def apply_overrides(new_items: list[dict], prev_items: list[dict], now_iso: str) -> list[dict]:
    """(handlers 후처리) reconcile 의 API 재구성에 트윗·릴레이 유래 시각 override 재적용.

    v3 계약: `api_start_seen` 은 마지막 API scheduled_start. 이 값이 바뀌면(스트림 실수정)
    트윗값 대신 API 승.

    규칙 각 b 에 대해 pb = match_item(prev_items, b):
    1. pb 없음 → 그대로.
    2. b.info_source ∉ ("personal", "x-relay") → 그대로.
    3. b.time_tbd 또는 b.scheduled_start 없음 → 그대로.
    4. api_now = b.api_start_seen, api_prev = pb.api_start_seen.
       둘 중 하나라도 없음 → 그대로(처음 API 관측).
    5. abs(epoch(api_now) − epoch(api_prev)) <= 60 → 그대로(트윗 시각 유지).
    6. 60초 초과(스트림 실제 수정) → scheduled_start=api_now, info_source="api",
       info_at=now_iso (api_start_seen 은 api_now 유지).

    Args:
        new_items: build_preview 후 preview.json 의 items 배열
        prev_items: 이전 preview.json 의 items 배열
        now_iso: 현재 시각 (UTC ISO)

    Returns:
        override 적용된 new_items 사본 (입력 변형 없음)
    """
    prev = prev_items or []
    new = [dict(b) for b in (new_items or [])]

    for b in new:
        # 규칙 1: 이전 아이템에서 같은 방송 찾기
        pb = preview.match_item(prev, b)
        if pb is None:
            continue

        # 규칙 2: 원래 info_source가 personal 또는 x-relay만
        if b.get("info_source") not in ("personal", "x-relay"):
            continue

        # 규칙 3: time_tbd 또는 scheduled_start 없으면 패스
        if b.get("time_tbd") or not b.get("scheduled_start"):
            continue

        # 규칙 4: 양쪽 api_start_seen 비교 준비
        api_now = b.get("api_start_seen")
        api_prev = pb.get("api_start_seen")

        # 규칙 4: 둘 중 하나라도 없으면 그대로
        if api_now is None or api_prev is None:
            continue

        # 규칙 5~6: 60초 임계값으로 판정
        delta_sec = abs(_epoch(api_now) - _epoch(api_prev))
        if delta_sec <= 60:
            # 규칙 5: API 값 불변 → 트윗 시각 유지
            # (이미 b["scheduled_start"] 는 트윗값이므로 유지)
            pass
        else:
            # 규칙 6: API 값 변경 → API 승
            b["scheduled_start"] = api_now
            b["info_source"] = "api"
            b["info_at"] = now_iso

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
    base = datetime(2026, 9, 7, 12, 1, tzinfo=timezone.utc)
    for i, rid in enumerate(("2096600000000000000", "2096700000000000000", "2096800000000000000")):
        msg = dict(r, id=rid, text=f"연타{i}",
                   received_at=(base + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:00Z"),
                   expires_at="2026-09-08T13:00:00Z")
        T, A, ch, m = merge_thread(T, msg, "2026-09-07T12:05:00Z", archive=A)
        assert ch and m == "added", m
    thread = _as_list(T["tweets"]["arale"])
    assert [x["id"] for x in thread] == ["2096552878769152326", "2096600000000000000",
                                         "2096700000000000000", "2096800000000000000"], thread
    # cap(MAX_THREAD) 직전까지 채워도 added, cap 을 넘는 한 건이 와야 rolled(가장 오래된 것 archive)
    next_id = 2096900000000000000
    for i in range(MAX_THREAD - len(thread)):
        T, A, ch, m = merge_thread(T, dict(r, id=str(next_id + i), text=f"채움{i}",
                                           received_at=(base + timedelta(minutes=4 + i)).strftime("%Y-%m-%dT%H:%M:00Z"),
                                           expires_at="2026-09-08T13:00:00Z"),
                                   "2026-09-07T12:05:00Z", archive=A)
        assert ch and m == "added", m
    assert len(_as_list(T["tweets"]["arale"])) == MAX_THREAD
    T, A, ch, m = merge_thread(T, dict(r, id=str(next_id + MAX_THREAD), text="cap+1",
                                       received_at=(base + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00Z"),
                                       expires_at="2026-09-08T13:00:00Z"),
                               "2026-09-07T13:06:00Z", archive=A)
    assert ch and m == "rolled" and len(_as_list(T["tweets"]["arale"])) == MAX_THREAD
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

    # S-A2: (v3.4.5 핫픽스) "明日" 계열 상대날짜 + 시각 → +1일 반영
    #   버그리포트: 19:43 JST 트윗 "次回の配信予定は明日22:00！" 이 게이트 통과 못 하던 것.
    a2 = parse_schedule("次回の配信予定は明日22:00！✨\nよろしくねぇ〜",
                        channel_key="arale", tag=None, now_iso=SNOW)
    assert a2 and a2["time_tbd"] is False, a2
    assert a2["scheduled_start"] == "2026-09-08T13:00:00Z", a2   # 明日(9/8) 22:00 JST = 9/8 13:00Z
    print("[OK] parse_schedule  (明日HH:MM → +1일 반영)")

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

    # S-C2: (버그리포트 20260916 #2) 후기 트윗 속 무관한 미래 숫자가 날짜/시각으로
    # 오합성돼도 ありがとうございました 가 있으면 후기로 걸러짐(아라레 실사례 재현)
    assert parse_schedule(
        "#アワーノーツ 先行プレイ配信\nありがとうございました！\n\n"
        "ガッツリ2時間プレイ！！\n9/24まで待ち遠しい〜〜〜！！！",
        channel_key="arale", tag=None, now_iso=SNOW,
    ) is None
    print("[OK] parse_schedule  (후기 속 무관한 미래 날짜/시각 오합성 → 후기로 걸러짐)")

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

    # S-G: apply_overrides — API 불변(60초 이내) → 트윗 값 유지
    # build_preview 가 personal/x-relay 정보원의 scheduled_start 를 갱신하지 않으므로
    # new_item 도 prev 값 13:30Z 유지 (API 값 13:00Z가 아님)
    prev_item = preview.make_item(
        channel_key="arale", state="upcoming", source="personal", now_iso="2026-09-07T12:50:00Z",
        video_id="vidX", scheduled_start="2026-09-07T13:30:00Z",  # 트윗이 당겨놓음
        info_source="personal", info_at="2026-09-07T12:50:00Z",
        api_start_seen="2026-09-07T13:00:00Z"  # API 는 원래 13:00
    )
    new_item_g = preview.make_item(
        channel_key="arale", state="upcoming", source="personal", now_iso=SNOW,
        video_id="vidX", scheduled_start="2026-09-07T13:30:00Z",  # build_preview 가 안 건드림
        api_start_seen="2026-09-07T13:00:00Z",  # API 값이 이전 tick 과 같아 api_start_seen 이 그대로
        info_source="personal", info_at="2026-09-07T12:50:00Z"
    )
    out_g = apply_overrides([new_item_g], [prev_item], SNOW)
    # 규칙 5: api_start_seen 이 같으면 (60초 이내) 그대로 → scheduled_start 변경 없음
    assert out_g[0]["scheduled_start"] == "2026-09-07T13:30:00Z", out_g[0]
    assert out_g[0]["info_source"] == "personal"
    print("[OK] apply_overrides  (G: API 불변 60초 이내→트윗값 유지)")

    # S-H: API 값 변경(60초 초과) → API 승
    # build_preview 가 personal 정보원의 scheduled_start 를 갱신하지 않으므로
    # new_item 도 prev 값 13:30Z 유지. 하지만 api_start_seen 은 갱신된다.
    new_item_h = preview.make_item(
        channel_key="arale", state="upcoming", source="personal", now_iso=SNOW,
        video_id="vidX", scheduled_start="2026-09-07T13:30:00Z",  # build_preview 가 안 건드림
        api_start_seen="2026-09-07T14:00:00Z",  # api_start_seen 갱신됨 (60초 이상 차이)
        info_source="personal", info_at="2026-09-07T12:50:00Z"
    )
    out_h = apply_overrides([new_item_h], [prev_item], SNOW)
    # 규칙 6: api_start_seen 이 60초 이상 차이나면 API 승 → scheduled_start 를 api_start_seen 으로
    assert out_h[0]["scheduled_start"] == "2026-09-07T14:00:00Z", out_h[0]
    assert out_h[0]["info_source"] == "api" and out_h[0]["info_at"] == SNOW  # API 승
    print("[OK] apply_overrides  (H: API 변경 60초 초과→API승)")

    # S-I: 이전 api_start_seen 이 None → 처음 관측, override 작동 안 함
    prev_item_i = preview.make_item(
        channel_key="arale", state="announced", source="personal", now_iso="2026-09-07T12:50:00Z",
        video_id="vidY", scheduled_start="2026-09-07T13:30:00Z",
        info_source="personal", info_at="2026-09-07T12:50:00Z",
        api_start_seen=None  # 처음엔 API 관측 전
    )
    new_item_i = preview.make_item(
        channel_key="arale", state="upcoming", source="personal", now_iso=SNOW,
        video_id="vidY", scheduled_start="2026-09-07T13:30:00Z",  # build_preview 가 안 건드림
        api_start_seen="2026-09-07T13:00:00Z",  # 처음 관측됨
        info_source="personal", info_at="2026-09-07T12:50:00Z"
    )
    out_i = apply_overrides([new_item_i], [prev_item_i], SNOW)
    # 규칙 4: api_prev 가 None 이면 그대로 → override 작동 안 함
    assert out_i[0]["scheduled_start"] == "2026-09-07T13:30:00Z", out_i[0]
    assert out_i[0]["info_source"] == "personal"  # info_source 변경 없음
    print("[OK] apply_overrides  (I: 이전 api_start_seen=None→처음관측,override안함)")

    # S-J: info_source=x-relay 도 동일하게 동작 (H 와 같음)
    prev_item_j = preview.make_item(
        channel_key="yuno", state="upcoming", source="x-relay", now_iso="2026-09-07T12:50:00Z",
        video_id="vidZ", scheduled_start="2026-09-07T13:30:00Z",
        info_source="x-relay", info_at="2026-09-07T12:50:00Z",
        api_start_seen="2026-09-07T13:00:00Z"
    )
    new_item_j = preview.make_item(
        channel_key="yuno", state="upcoming", source="x-relay", now_iso=SNOW,
        video_id="vidZ", scheduled_start="2026-09-07T13:30:00Z",  # build_preview 가 안 건드림
        api_start_seen="2026-09-07T14:00:00Z",  # API 변경(60초 이상)
        info_source="x-relay", info_at="2026-09-07T12:50:00Z"
    )
    out_j = apply_overrides([new_item_j], [prev_item_j], SNOW)
    assert out_j[0]["scheduled_start"] == "2026-09-07T14:00:00Z", out_j[0]  # API 값
    assert out_j[0]["info_source"] == "api" and out_j[0]["info_at"] == SNOW  # API 승
    print("[OK] apply_overrides  (J: x-relay도동일(H처럼)→API승)")

    # S-K: info_source=api 아이템은 규칙 2 에서 패스, 손대지 않음
    prev_item_k = preview.make_item(
        channel_key="nonoka", state="upcoming", source="api", now_iso="2026-09-07T12:50:00Z",
        video_id="vidK", scheduled_start="2026-09-07T14:00:00Z",
        info_source="api", info_at="2026-09-07T12:50:00Z",
        api_start_seen="2026-09-07T14:00:00Z"
    )
    new_item_k = preview.make_item(
        channel_key="nonoka", state="upcoming", source="api", now_iso=SNOW,
        video_id="vidK", scheduled_start="2026-09-07T15:00:00Z",
        api_start_seen="2026-09-07T15:00:00Z",  # API 변경
        info_source="api", info_at=SNOW
    )
    out_k = apply_overrides([new_item_k], [prev_item_k], SNOW)
    assert out_k[0]["scheduled_start"] == "2026-09-07T15:00:00Z", out_k[0]  # 그대로 유지
    assert out_k[0]["info_source"] == "api"  # info_source 변경 없음
    print("[OK] apply_overrides  (K: info_source=api→규칙2패스,손대지않음)")

    # ── v3.6 URL 우선 ingest — resolve_url_host / build_item_from_video / merge_video_confirmed ──
    class _FakeVideo:
        def __init__(self, video_id, channel_id, title, live_state,
                     scheduled_start=None, actual_start=None, concurrent_viewers=None,
                     thumbnail="thumb.jpg"):
            self.video_id = video_id
            self.channel_id = channel_id
            self.title = title
            self.thumbnail = thumbnail
            self.live_state = live_state
            self.scheduled_start = scheduled_start
            self.actual_start = actual_start
            self.concurrent_viewers = concurrent_viewers

    CFG2 = {
        "channel_order": ["arale", "yuno", "nonoka", "ritsu", "miyako"],
        "channels": {
            "arale": {"channel_id": "UC_arale"},
            "yuno": {"channel_id": "UC_yuno"},
            "nonoka": {"channel_id": "UC_nonoka"},
            "ritsu": {"channel_id": "UC_ritsu"},
            "miyako": {"channel_id": "UC_miyako"},
            "group": {"channel_id": "UC_group"},
        },
    }

    # 본인 채널 — collab_with 없음
    assert resolve_url_host("UC_nonoka", "nonoka", CFG2) == ("nonoka", None, None)
    # 다른 멤버 채널에서 열린 콜라보 — 그 채널이 host, 작성자가 collab_with
    assert resolve_url_host("UC_nonoka", "arale", CFG2) == ("nonoka", None, ["arale"])
    # 그룹 공식 채널 — v3.1.4 팬아웃과 동일 (channel_order[0] + 나머지 4인)
    assert resolve_url_host("UC_group", "arale", CFG2) == (
        "arale", "group", ["yuno", "nonoka", "ritsu", "miyako"]
    )
    # 우리 채널 아님
    assert resolve_url_host("UC_someone_else", "arale", CFG2) == (None, None, None)
    print("[OK] resolve_url_host  (본인/타 멤버/그룹/외부 4갈래)")

    NOW6 = "2026-09-16T12:00:05Z"

    # 이미 라이브 중인 영상 — state 가 "upcoming" 으로 고정되지 않고 "live" 로 직행
    v_live = _FakeVideo("vidLive", "UC_nonoka", "방송중", "live",
                        scheduled_start="2026-09-16T11:06:58Z",
                        actual_start="2026-09-16T11:07:20Z", concurrent_viewers=627)
    item_live, wake_live = build_item_from_video(
        v_live, channel_key="nonoka", host=None, collab_with=None, now_iso=NOW6
    )
    assert item_live["state"] == "live", item_live
    assert item_live["actual_start"] == "2026-09-16T11:07:20Z"
    assert item_live["concurrent_viewers"] == 627
    assert wake_live is not None                                   # live cadence 재확인 예약됨
    print("[OK] build_item_from_video  (버그리포트 20260916 #1: live 로 직행, upcoming 고정 아님)")

    # 아직 시작 전 — upcoming 유지, precheck 시각으로 wake 예약
    v_future = _FakeVideo("vidFuture", "UC_arale", "다음주 방송", "upcoming",
                          scheduled_start="2026-09-23T05:00:00Z")
    item_future, wake_future = build_item_from_video(
        v_future, channel_key="arale", host=None, collab_with=None, now_iso=NOW6
    )
    assert item_future["state"] == "upcoming", item_future
    assert wake_future is not None
    print("[OK] build_item_from_video  (미래 예정 → upcoming + precheck wake)")

    # scheduled_start 는 지났는데 API 가 아직 upcoming(약간의 랙) → watching 으로 승격
    v_due = _FakeVideo("vidDue", "UC_yuno", "곧 시작", "upcoming",
                       scheduled_start="2026-09-16T11:58:00Z")   # NOW6 보다 2분 전
    item_due, wake_due = build_item_from_video(
        v_due, channel_key="yuno", host=None, collab_with=None, now_iso=NOW6
    )
    assert item_due["state"] == "watching", item_due
    print("[OK] build_item_from_video  (시작시각 도래+API 랙 → watching)")

    # merge_video_confirmed — 신규 append
    items_m, ch_m = merge_video_confirmed([], "vidLive", item_live, NOW6)
    assert ch_m and len(items_m) == 1
    print("[OK] merge_video_confirmed  (신규 append)")

    # merge_video_confirmed — 이미 watching 인 아이템에 뒤늦게 도착한 upcoming 판정은 강등 안 함
    watching_item = dict(item_due)
    stale_upcoming = dict(item_future)
    stale_upcoming["video_id"] = "vidDue"   # 같은 영상, 지연 도착한 재계산이라 가정
    items_m2, ch_m2 = merge_video_confirmed([watching_item], "vidDue", stale_upcoming, NOW6)
    assert items_m2[0]["state"] == "watching", items_m2[0]   # 강등되지 않음
    print("[OK] merge_video_confirmed  (상태 역행 방지)")

    # merge_video_confirmed — 제목 변경 시 title_ko/needs_tl 리셋
    tracked = dict(item_future)
    tracked["title_ko"] = "번역된 제목"
    tracked["needs_tl"] = False
    retitled = dict(item_future)
    retitled["title"] = "제목이 바뀜"
    items_m3, ch_m3 = merge_video_confirmed([tracked], "vidFuture", retitled, NOW6)
    assert items_m3[0]["title"] == "제목이 바뀜"
    assert items_m3[0]["title_ko"] is None and items_m3[0]["needs_tl"] is True
    print("[OK] merge_video_confirmed  (제목 변경 → 재번역 대상)")

    print("\nSUCCESS: xtweet self-test 통과")
