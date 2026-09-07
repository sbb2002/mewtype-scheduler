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
_LEAD_JUNK = re.compile(r"^[\s＼／｜|・･*※＊✳✨🌟🌏🐔🛸🎊🎉🎁📢📣📺🎤🎮💭💪⭐🔥💫#＃>＞\-–—▼▽▶➡→]+")
_TRAIL_JUNK = re.compile(
    r"[\s　！!？?。、,.\-–—＼／｜|・･*※＊✳✨🌟🌏🐔🛸🎊🎉🎁📢📣📺🎤🎮💭💪⭐❣❕‼🔥💫➡→↓]+$"
)
_HANDLE_HEAD_RE = re.compile(r"^\s*(?:RT\s+)?@(\w{1,15})\s*[:：]")
_CONNECTIVE_RE = re.compile(r"^(?:さらに|そして|また|なお|加えて|そのほか|その他)\s*")
#   과장·캠페인 문구 (제목으로 부적합)
_HYPE_RE = re.compile(
    r"\d+\s*万?\s*人?\s*(?:突破|達成|超え)|事前登録|達成報酬|プレゼント(?:が)?決定|"
    r"フォロー\s*[&＆]|RT\s*[&＆]|抽選で|キャンペーン実施|フォロー&RT|いいね&"
)
#   「」 안이 이벤트/상품 이름일 때만 제목으로 승격
_EVENTISH_RE = re.compile(
    r"特番|生配信|ライブ|LIVE|フェス|FES|公演|イベント|リリース|発売|配信決定|決定|開催|"
    r"スタート|第\s*\d+\s*弾|ツアー|TOUR"
)
_SENTENCE_RE = re.compile(r"[、。]|ので[、。\s]|です[。\s]|ます[。\s]|でした|ください")
#   메타데이터 라벨 줄 (`日程：…` `会場：…`) — 제목이 아니라 부가정보. 후보에서 강제 감점.
_LABEL_LINE_RE = re.compile(
    r"^(?:日程|日時|時間|開始時間?|開場|開演|会場|場所|開催地|受付|申込方法?|応募方法?|"
    r"参加方法?|料金|価格|チケット代?|前売り?|当日券?|定員|人数|出演者?|MC|司会|"
    r"ゲスト|備考|注意事項?|概要|内容|視聴URL|配信URL|URL|リンク|詳細)\s*[:：]"
)
#   외침형 제목 블록 — 같은 장식 문자로 앞뒤를 감싼 (여러 줄에 걸칠 수 있는) 제목.
#   예) `💪集え！#ゆめみた筋トレ部` + `　〜輝け！上腕二頭筋〜💪`  →  한 줄로 이어붙임.
_DECO_OPEN = "💪🔥✨🎊🎉⭐🌟💫🐔🛸🌏📢📣＼"
_DECO_CLOSE = {"＼": "／"}


def _join_shout_titles(lines: list[str]) -> list[str]:
    """장식 문자로 열린 줄을 그 닫는 문자가 나오는 줄까지(최대 3줄) 하나로 합친다."""
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        cur = lines[i]
        opener = cur.lstrip()[:1]
        end = None
        if opener in _DECO_OPEN:
            closer = _DECO_CLOSE.get(opener, opener)
            if cur.rstrip()[-1:] != closer:                 # 같은 줄에서 이미 안 닫혔으면
                for k in range(i + 1, min(i + 4, n)):
                    if lines[k].strip() and lines[k].rstrip()[-1:] == closer:
                        end = k
                        break
        if end is not None:
            joined = " ".join(s.strip() for s in lines[i:end + 1] if s.strip())
            if len(joined) <= 80:
                out.append(joined)
                i = end + 1
                continue
        out.append(cur)
        i += 1
    return out


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
        dl = bool(m.group("dl")) or ("まで" in t[m.end():m.end() + 4] or "迄" in t[m.end():m.end() + 4])
        cands.append((mo, da, dl, m.start()))
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
    """제목 뽑기 — 줄마다 점수 매겨 최고점. 「」 안이 이벤트/상품명이면 그걸 승격.

    첫 줄이 `＼⏰9月27日まで⏰／` 나 `事前登録150万人突破` 같은 장식·홍보라도 진짜 제목을 찾는다.
    """
    quote = None
    qm = _QUOTE_RE.search(t)
    if qm:
        quote = qm.group(1).strip().lstrip("#＃").strip()

    best, best_score = None, -1e9
    for raw in _join_shout_titles(t.split("\n")):
        line = raw.strip()
        if not line or HEADER_RE.search(line):
            continue
        if re.fullmatch(r"[＼／\s｜|・･*　]*", line):
            continue
        if line[:1] in ("#", "＃", "※", "▼", "▽", "▶", "＞", ">", "☆", "★"):
            continue
        if line.startswith("http") or " http" in line:
            continue
        if re.fullmatch(r"🛸?\s*夢限大みゅーたいぷ", line):
            continue
        label_line = bool(_LABEL_LINE_RE.match(line))
        cleaned = _TRAIL_JUNK.sub("", _LEAD_JUNK.sub("", line)).strip(" 　")
        cleaned = _CONNECTIVE_RE.sub("", cleaned)
        if len(cleaned) < 4:
            continue
        score = min(len(cleaned), 40) * 0.3
        if label_line or _LABEL_LINE_RE.match(cleaned):
            score -= 40                       # `日程：` `会場：` 등 부가정보 줄 — 제목 아님
        if _HYPE_RE.search(cleaned):
            score -= 100
        if _RE_LIVE.search(cleaned) or _RE_RELEASE.search(cleaned) or _RE_PLATFORM.search(cleaned):
            score += 40
        if "「" in cleaned or "『" in cleaned:
            score += 20
        if _SENTENCE_RE.search(cleaned):
            score -= 25                       # 설명 문장은 제목 아님
        if re.match(r"^(?:〜|\d{1,2}\s*[/月])", cleaned):
            score -= 15                       # 날짜로 시작하는 조각
        nonword = len(re.findall(r"[^0-9A-Za-z぀-ヿ一-鿿ー「」『』・]", cleaned))
        if nonword / max(len(cleaned), 1) > 0.5:
            score -= 30
        if score > best_score:
            best, best_score = cleaned, score

    if quote and _EVENTISH_RE.search(quote) and (not best or f"「{quote}」" not in best):
        return f"「{quote}」"[:90]
    if best:
        return best[:90]
    flat = re.sub(r"\s+", " ", t).strip()
    return _TRAIL_JUNK.sub("", _LEAD_JUNK.sub("", flat))[:90] or "(제목 없음)"


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
    assert r1["title"] == "「アワーノーツ リリース日決定特番」", r1["title"]   # 홍보 첫 줄 무시
    assert r1["anchor_b"] == "アワーノーツリリース日決定特番", r1["anchor_b"]
    assert r1["deadline"] is False
    print("[OK] S1  라이브 예고 (제목=「」, 홍보 첫 줄 무시)")

    # S2: 굿즈 수주(마감형) — 첫 줄이 ＼⏰…まで⏰／ 장식, 진짜 제목은 셋째 줄
    S2 = ("＼⏰9月27日まで受注受付！⏰／\n🛸TVアニメ「#バンドリ！ ゆめ∞みた」🛸\n"
          "メモリアルグッズの第2弾が発売🌟\n今回は受注生産なので、期間中の売切れはナシ❣\n"
          "▼ご注文はコチラ！\nhttps://bushiroad-store.com/pages/anime-yumemita_memorial-fair2\n#アニメゆめみた")
    r2 = parse(S2, NOW, tag="p#https://x.com/#1tweet-2096529833870479645")
    assert r2 and r2["category"] == "release", r2
    assert r2["date"] == "2026-09-27" and r2["deadline"] is True, r2   # "9月27日まで" → deadline
    assert r2["title"] == "メモリアルグッズの第2弾が発売", r2["title"]   # 장식·프랜차이즈 「」 무시
    assert r2["site"] == "store" and r2["anchor_a"] == "anime-yumemita_memorial-fair2", r2
    print("[OK] S2  굿즈 수주 (まで→deadline, 제목=실질 줄)")

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

    # S9: 외침형 제목 블록(💪…💪 2줄) + 라벨 줄(日程：/会場：) 감점 → 진짜 제목 추출
    S9 = ("＼チケットプレイガイド先行開始📢／\n\n"
          "💪集え！#ゆめみた筋トレ部 \n　～輝け！上腕二頭筋～💪\n\n"
          "日程：11月21日(土)\n会場：GARDEN 新木場 FACTORY\n\n"
          "🎫お申し込みはこちら\nhttps://eplus.jp/yumemita_kinntorebu2026/\n\n"
          "昼の部・夜の部\nどちらもお見逃しなく✨\n\n#バンドリ")
    r9 = parse(S9, NOW, tag="p#x#1tweet-2099999999999999999")
    assert r9 and r9["date"] == "2026-11-21", r9
    assert r9["title"] == "集え！#ゆめみた筋トレ部 〜輝け！上腕二頭筋〜", r9["title"]
    assert "会場" not in r9["title"] and "eplus" not in r9["title"], r9["title"]
    assert r9["url"] == "https://eplus.jp/yumemita_kinntorebu2026/", r9
    print("[OK] S9  외침형 제목 블록 + 라벨 줄 감점")

    # _join_shout_titles 단위 — 같은 줄에서 닫힌 경우엔 병합 안 함
    assert _join_shout_titles(["＼abc／", "def"]) == ["＼abc／", "def"]
    assert _join_shout_titles(["💪타이틀", "　서브〜💪", "다음"]) == ["💪타이틀 서브〜💪", "다음"]
    assert _join_shout_titles(["🛸夢限大みゅーたいぷ", "9/1", "본문"]) == \
        ["🛸夢限大みゅーたいぷ", "9/1", "본문"]           # 닫는 🛸 없음 → 병합 안 함
    print("[OK] _join_shout_titles")

    print("\nSUCCESS: xnotice self-test 통과")
