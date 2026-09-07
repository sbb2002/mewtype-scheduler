"""멤버 개인 트윗 — android.title 라우팅 + tweets.json 계약 (순수 함수).

계약: docs/plan/v2_8_personal_tweets.md · 현행 ingest 경로: docs/INGEST_FLOW.md

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

from .xrelay import normalize

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

    print("\nSUCCESS: xtweet self-test 통과")
