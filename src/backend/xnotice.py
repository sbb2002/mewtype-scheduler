"""X 소식 파서 — `@BDP_yumemita` 의 **방송 외 이벤트** 트윗을 notices.json 항목으로.

계약: docs/plan/v2_7_notice_board.md

규칙
- **날짜 또는 시각이 하나도 없으면 → None** (소식 아님. 상시 홍보는 안 다룬다.)
- `配信スケジュール` / `出演情報` 트윗 → None (스케줄 파이프라인 담당 — 섞이지 않게)
- 카테고리 4개 (먼저 맞는 것): platform → live → release → etc(분류 안 되면)
- 중복키: 이벤트 날짜 겹치고 + (`anchor_a`=URL id 겹치거나, a 없으면 `anchor_b`=「」인용구 겹침)
  → 같은 소식 (판정·머지는 notices.merge_notice)

순수 함수. self-test 는 `python -m src.backend.xnotice`.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from .xrelay import JST, UTC, HEADER_RE, YT_VIDEO_RE, _infer_year, normalize

# ── 날짜 · 시각 ────────────────────────────────────────────────────────────
#   "9/13" · "9月13日" · "9/13(日)" · "〜9/27" · "〜 9月27日"
_DATE_RE = re.compile(
    r"(?P<dl>〜\s*)?(?P<m>\d{1,2})\s*[/月]\s*(?P<d>\d{1,2})\s*日?"
    r"(?:\s*[（(][日月火水木金土][）)])?"
)
#   "21:00" · "24:30" · "21時" · "21時30分"
_TIME_RE = re.compile(r"(?P<h>\d{1,2})\s*(?::|：|時)\s*(?P<mi>\d{2})?\s*分?")
#   이벤트 날짜를 고를 때 근처에 오면 우선하는 동사
_EVENT_VERB = ("開催", "発売", "配信", "リリース", "放送", "開始", "より", "から", "スタート")
_TODAY_WORD = ("本日", "今夜", "今晩", "まもなく", "これから", "ただいま")

# ── 카테고리 키워드 ──────────────────────────────────────────────────────
_RE_PLATFORM = re.compile(
    r"bilibili|ビリビリ|ニコ生|ニコニコ生|ツイキャス|twitcast|mildom|twitch|全員【",
    re.IGNORECASE,
)
_RE_LIVE = re.compile(
    r"配信決定|特番|生配信|生放送|放送決定|放送日|プレミア公開|ライブ配信|同時配信|"
    r"配信いたします|配信します|配信予定"
)
_RE_RELEASE = re.compile(
    r"リリース|発売|配信開始|予約(?:受付|開始)?|受注|グッズ|メモリアルグッズ|"
    r"CD|アルバム|EP|シングル|ダウンロード|フェア"
)

# ── 후기(recap) 키워드 ──────────────────────────────────────────────────
_RE_RECAP = re.compile(
    r"ありがとうございました|御礼|お礼|お疲れ(?:様|さま)|無事終了|振り返り|"
    r"感想は|感想お待ち|ご来場|終演|閉幕"
)

# ── 사이트 판별 ────────────────────────────────────────────────────────
_URL_RE = re.compile(r"https?://[^\s　]+")
_BILI_RE = re.compile(r"(?:space|live|m|www)\.bilibili\.com/(\d+)|b23\.tv/(\w+)")
_STORE_RE = re.compile(r"(bushiroad|store|shop|booth\.pm|ec\.|\.stores\.jp|/goods|/products?/)", re.IGNORECASE)
_MUSIC_RE = re.compile(r"(lnk\.to|linkco\.re|spotify|music\.apple|apple\.co|/music/)", re.IGNORECASE)

_TWEET_ID_RE = re.compile(r"tweet-(\d{6,25})")
_QUOTE_RE = re.compile(r"[「『]([^」』\n]{1,80})[」』]")
_LEAD_JUNK = re.compile(r"^[\s＼／｜|・･*※＊✳️✨🌟🌏🐔🛸🎊🎉🎁📢📣📺🎤🎮💭💪⭐#＃>＞\-–—]+")
_HANDLE_HEAD_RE = re.compile(r"^\s*(?:RT\s+)?@(\w{1,15})\s*[:：]")


def _tweet_id(tag: str | None) -> str:
    m = _TWEET_ID_RE.search(tag or "")
    return m.group(1) if m else ""


def _first_time(t: str) -> str | None:
    """본문 첫 'HH:MM' (또는 'HH시') → 'HH:MM'. 없으면 None. 심야표기(24~29) 그대로 둠."""
    for m in _TIME_RE.finditer(t):
        h = int(m.group("h"))
        mi = m.group("mi")
        if h > 29:                       # "300万人" 같은 숫자 오탐 방지
            continue
        return f"{h:02d}:{int(mi) if mi else 0:02d}"
    return None


def _pick_event_date(t: str, now_jst: datetime) -> tuple[str | None, bool]:
    """이벤트 날짜(ISO) + deadline 여부. 동사 근처 우선, 없으면 미래 최근접."""
    cands: list[tuple[int, int, bool, int]] = []   # (month, day, deadline, pos)
    for m in _DATE_RE.finditer(t):
        try:
            mo, da = int(m.group("m")), int(m.group("d"))
            if not (1 <= mo <= 12 and 1 <= da <= 31):
                continue
        except ValueError:
            continue
        cands.append((mo, da, bool(m.group("dl")), m.start()))
    if not cands:
        return None, False

    def iso(mo: int, da: int) -> str | None:
        try:
            return datetime(_infer_year(mo, da, now_jst), mo, da, tzinfo=JST).strftime("%Y-%m-%d")
        except ValueError:
            return None

    # 1) 동사 근처(뒤 12자 안)에 오는 날짜 우선
    for mo, da, dl, pos in cands:
        after = t[pos:pos + 40]
        if any(v in after for v in _EVENT_VERB):
            d = iso(mo, da)
            if d:
                return d, dl
    # 2) 오늘 이후로 가장 가까운 날짜
    today = now_jst.date()
    best = None
    for mo, da, dl, _ in cands:
        d = iso(mo, da)
        if not d:
            continue
        dt = datetime.fromisoformat(d).date()
        if dt >= today and (best is None or dt < best[0]):
            best = (dt, d, dl)
    if best:
        return best[1], best[2]
    # 3) 그냥 첫 번째
    mo, da, dl, _ = cands[0]
    return iso(mo, da), dl


def _site_url_anchor(t: str) -> tuple[str, str | None, str | None]:
    """(site, url, anchor_a). 본문의 온전한 URL 하나를 골라 판별."""
    urls = _URL_RE.findall(t)
    for u in urls:
        u = u.rstrip("）)。、,")
        ym = YT_VIDEO_RE.search(u)
        if ym:
            return "youtube", (u if u.startswith("http") else "https://" + u), ym.group(1)
        bm = _BILI_RE.search(u)
        if bm:
            return "bilibili", u, (bm.group(1) or bm.group(2))
        if _MUSIC_RE.search(u):
            return "music", u, _url_tail(u)
        if _STORE_RE.search(u):
            return "store", u, _url_tail(u)
    if urls:
        u = urls[0].rstrip("）)。、,")
        return "web", u, _url_tail(u)
    return "x", None, None


def _url_tail(u: str) -> str:
    seg = [s for s in re.split(r"[/?#]", u) if s]
    return seg[-1][:40] if seg else u[:40]


def _headline(t: str) -> str:
    """가장 눈에 띄는 한 줄 → 제목. 장식·해시태그·정형구 줄 제외."""
    for raw in t.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if HEADER_RE.search(line):
            continue
        if re.fullmatch(r"[＼／\s｜|・･*　]*", line):
            continue
        if line.startswith("#") or line.startswith("＃"):
            continue
        if line.startswith("※"):
            continue
        if re.fullmatch(r"🛸?\s*夢限大みゅーたいぷ", line):
            continue
        cleaned = _LEAD_JUNK.sub("", line).strip(" 　")
        if len(cleaned) >= 4:
            return cleaned[:90]
    flat = re.sub(r"\s+", " ", t).strip()
    return _LEAD_JUNK.sub("", flat)[:90] or "(제목 없음)"


def _title_slug(title: str) -> str:
    s = re.sub(r"[#＃]\S+", "", title)
    s = re.sub(r"\d{1,2}\s*[/月]\s*\d{1,2}\s*日?", "", s)     # 날짜 제거
    s = re.sub(r"\d{1,2}\s*[:：時]\s*\d{0,2}\s*分?", "", s)    # 시각 제거
    s = re.sub(r"[^0-9A-Za-z぀-ヿ一-鿿]+", "", s)  # 영숫자·가나·한자만
    return s.lower()[:24]


def _src_handle(t: str, title: str | None) -> str:
    m = _HANDLE_HEAD_RE.match(t)
    if m:
        return f"RT @{m.group(1)}"
    if title and title.strip() and "夢限大みゅーたいぷ" not in title and "ゆめみた" not in title:
        # android.title 이 공식 표시 이름이 아니면 리포스트/외부 계정
        return f"RT {title.strip()}" if title.strip().startswith("@") else "@BDP_yumemita"
    if "pic.x.com/" in t and _HANDLE_HEAD_RE.match(t):
        return "RT " + _HANDLE_HEAD_RE.match(t).group(0).strip(": 　")
    return "@BDP_yumemita"


def _category(t: str) -> str:
    if _RE_PLATFORM.search(t):
        return "platform"
    if _RE_LIVE.search(t):
        return "live"
    if _RE_RELEASE.search(t):
        return "release"
    return "etc"


def _expires_at(date_iso: str | None, time_hm: str | None, posted_iso: str, now_jst: datetime) -> str:
    """이벤트 '그 날'의 JST 자정 다음(= 다음날 00:00)을 UTC ISO 로. 심야표기면 +1일."""
    try:
        base = datetime.fromisoformat(date_iso).replace(tzinfo=JST) if date_iso else now_jst
    except (TypeError, ValueError):
        base = now_jst
    carry = 1 if (time_hm and int(time_hm.split(":")[0]) >= 24) else 0
    end = (base + timedelta(days=1 + carry)).replace(hour=0, minute=0, second=0, microsecond=0)
    return end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(text: str, now_iso: str, *, tag: str | None = None, title: str | None = None) -> dict | None:
    """트윗 → 소식 dict. 소식이 아니면 None."""
    if not text or not text.strip():
        return None
    t = normalize(text)
    if "配信スケジュール" in t or "出演情報" in t:
        return None                       # 스케줄/출연 파이프라인 담당

    try:
        now_jst = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(JST)
    except (ValueError, AttributeError):
        now_jst = datetime.now(JST)

    date_iso, deadline = _pick_event_date(t, now_jst)
    time_hm = _first_time(t)
    if not date_iso and time_hm and any(w in t for w in _TODAY_WORD):
        date_iso = now_jst.strftime("%Y-%m-%d")
    if not date_iso and not time_hm:
        return None                       # 날짜·시각 둘 다 없음 → 소식 아님
    if not date_iso and time_hm:
        date_iso = now_jst.strftime("%Y-%m-%d")   # 시각만 → 오늘로 간주

    site, url, anchor_a = _site_url_anchor(t)
    qm = _QUOTE_RE.search(t)
    anchor_b = re.sub(r"\s+", "", qm.group(1)).lower()[:40] if qm else None
    headline = _headline(t)
    tid = _tweet_id(tag)
    category = _category(t)

    if not tid:
        tid = "n" + hashlib.sha1(
            (category + (date_iso or "") + _title_slug(headline)).encode("utf-8")
        ).hexdigest()[:15]

    return {
        "id": tid,
        "category": category,
        "title": headline,
        "date": date_iso,
        "time": time_hm,
        "deadline": deadline,
        "site": site,
        "url": url,
        "tweet_url": (f"https://x.com/i/status/{_tweet_id(tag)}" if _tweet_id(tag) else None),
        "src_handle": _src_handle(t, title),
        "is_recap": bool(_RE_RECAP.search(t)),
        "anchor_a": anchor_a,
        "anchor_b": anchor_b,
        "title_slug": _title_slug(headline),
        "expires_at": _expires_at(date_iso, time_hm, now_iso, now_jst),
    }


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    NOW = "2026-09-10T00:00:00Z"          # JST 2026-09-10 09:00

    # S1: 특번(라이브 예고) — リリース 단어 있지만 特番 → live 우선
    S1 = ("＼事前登録150万人突破🎊／\nさらに「アワーノーツ リリース日決定特番」\n"
          "9月13日(日)21:00より配信決定🎉\n公式XとYouTubeにて配信いたします\n#バンドリ")
    r1 = parse(S1, NOW, tag="p#https://x.com/#1tweet-2096519341575721125")
    assert r1 and r1["category"] == "live", r1
    assert r1["date"] == "2026-09-13" and r1["time"] == "21:00", r1
    assert r1["id"] == "2096519341575721125"
    assert r1["tweet_url"] == "https://x.com/i/status/2096519341575721125"
    assert r1["anchor_b"] == "アワーノーツリリース日決定特番", r1["anchor_b"]
    assert r1["deadline"] is False
    print("[OK] S1  라이브 예고 (特番 → live, 날짜·시각·인용구)")

    # S2: 굿즈 수주(마감형) — 〜9/27
    S2 = ("🛸メモリアルグッズの第2弾が発売🌟\n受注受付は〜9/27まで❣\n"
          "▼ご注文はコチラ\nhttps://bushiroad-store.com/pages/anime-yumemita_fair2\n#ゆめみた")
    r2 = parse(S2, NOW, tag="p#https://x.com/#1tweet-2096529833870479645")
    assert r2 and r2["category"] == "release", r2
    assert r2["date"] == "2026-09-27" and r2["deadline"] is True, r2
    assert r2["site"] == "store" and r2["url"].startswith("https://bushiroad-store.com"), r2
    assert r2["anchor_a"] == "anime-yumemita_fair2", r2["anchor_a"]
    print("[OK] S2  굿즈 수주 (release, deadline, store anchor_a)")

    # S3: bilibili 전원 방송
    S3 = ("／\n🛸夢限大みゅーたいぷ\n＼\n⭐9/23(火) 22:00〜 全員【bilibili】生配信\n"
          "https://space.bilibili.com/3546592848120041\n#バンドリ #ゆめみた")
    r3 = parse(S3, NOW, tag="p#https://x.com/#1tweet-2096600000000000000")
    assert r3 and r3["category"] == "platform", r3
    assert r3["site"] == "bilibili" and r3["anchor_a"] == "3546592848120041", r3
    assert r3["date"] == "2026-09-23" and r3["time"] == "22:00", r3
    print("[OK] S3  bilibili 전원 (platform, space id anchor_a)")

    # S4: 후기 트윗 — 날짜 있음 + ありがとう → is_recap
    S4 = ("🌏9/6(日)開催🌏\nBM-ECHOES FESTIVAL 2026 DAY2\nご来場ありがとうございました❣️\n"
          "感想は #BMFES_2026_DAY2 でお待ちしています")
    r4 = parse(S4, NOW)
    assert r4 and r4["is_recap"] is True and r4["date"] == "2026-09-06", r4
    assert r4["id"].startswith("n"), "tag 없음 → 합성 id"
    print("[OK] S4  후기 트윗 (is_recap, 날짜, 합성 id)")

    # S5/S6: 스케줄·출연 → None
    assert parse("8/30(日) 配信スケジュール\n🎮11:00〜 宮永ののか", NOW) is None
    assert parse("＼🛸出演情報📢／\n9/10(木) 22:00頃〜\n「イベント」", NOW) is None
    print("[OK] S5/S6  配信スケジュール · 出演情報 → None")

    # S7: 날짜·시각 없음 → None
    assert parse("＼🛸ありがとうございました🛸／\n来週にはアニメ最終回を迎えます\n#ゆめみた", NOW) is None
    print("[OK] S7  날짜·시각 없음 → None")

    # S8: 시각만(本日) → 오늘로
    r8 = parse("本日22:00〜 緊急生配信きました！\nhttps://youtube.com/live/abcdef12345\n#ゆめみた", NOW)
    assert r8 and r8["date"] == "2026-09-10" and r8["time"] == "22:00", r8
    assert r8["site"] == "youtube" and r8["anchor_a"] == "abcdef12345", r8
    print("[OK] S8  본일 시각만 → 오늘 날짜 보정")

    print("\nSUCCESS: xnotice self-test 통과")
