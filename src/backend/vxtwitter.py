"""vxtwitter API unfurl — 트윗 본문·이미지·URL 추출 (순수 함수 + HTTP 통신).

트윗 Snowflake id로 https://api.vxtwitter.com/i/status/<id> 조회 → JSON 파싱.
- 본문(text) + 확장 URL + 미디어(image/video) 추출
- YouTube URL → video_id 11자 추출(정규식)
- 비200·타임아웃·JSON 오류 → None + 경고

self-test: python -m src.backend.vxtwitter
"""
from __future__ import annotations

import logging
import re
import warnings
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore

# YouTube video_id 추출: watch?v=, live/, youtu.be/ 뒤 11자
_YT_VIDEO_RE = re.compile(
    r"(?:"
    r"youtube\.com/(?:watch\?v=|live/)"
    r"|youtu\.be/"
    r")([a-zA-Z0-9_-]{11})"
)

# 인용(QRT)한 트윗의 id — vxtwitter 응답의 qrtURL(".../status/<id>") 에서 추출.
# 인용된 트윗 본문·미디어는 qrtURL 자체엔 안 실려 있어 별도 fetch_tweet 이 필요.
_STATUS_ID_RE = re.compile(r"/status/(\d+)")

# ponytail: vxtwitter 서드파티 무료 서비스 → 가동률 미보장, 실패 시 조용히 None 반환

# (v3.7.3) vxtwitter 는 특정 트윗에서 HTTP 500 을 "영구적으로" 낸다(2026-09-14~19 로그 고유 트윗 12건이 며칠 뒤에도
# 500, 참조 트윗 단독 조회도 500). 같은 성격의 fxtwitter 로 폴백해 본문·첨부·참조 트윗(QRT)을 살린다.
# 두 호출을 순차로 돌아도 업스트림(Automate) HTTP 타임아웃(약 10초) 안에 들어오도록 타임아웃을 낮춘다.
FX_BASE = "https://api.fxtwitter.com"
VX_TIMEOUT_SEC = 5.0
FX_TIMEOUT_SEC = 4.0

_log = logging.getLogger(__name__)


def _strip_orig(url: str) -> str:
    """fxtwitter 사진 URL 의 `?name=orig` 제거 — vxtwitter 의 mediaURLs 형식과 맞춘다."""
    return url[: -len("?name=orig")] if url.endswith("?name=orig") else url


def _fx_media(media: dict | None) -> tuple[list[str], list[dict]]:
    """fxtwitter `media.all` → (vx mediaURLs 형식, media_extended 형식).

    프론트가 모든 미디어를 <img> 로만 그리므로 영상·GIF 는 썸네일 이미지 URL 을 쓴다.
    """
    urls: list[str] = []
    ext: list[dict] = []
    for m in (media or {}).get("all") or []:
        if not isinstance(m, dict):
            continue
        kind = m.get("type")
        if kind == "photo":
            if m.get("url"):
                u = _strip_orig(str(m["url"]))
                urls.append(u)
                ext.append({"url": u, "type": kind})
        elif m.get("thumbnail_url"):
            # vx 형식과 동일: url=원본(mp4), thumbnail_url=썸네일 — 어느 쪽을 그릴지는 _media_urls 가 정한다
            urls.append(str(m["thumbnail_url"]))
            ext.append({"url": m.get("url"), "type": kind, "thumbnail_url": str(m["thumbnail_url"])})
    return urls, ext


def _fx_to_vx(fx: dict) -> dict | None:
    """fxtwitter 응답(`{"tweet": {...}}`) → vxtwitter 응답 형식 dict. 내용이 하나도 없으면 None."""
    t = (fx or {}).get("tweet")
    if not isinstance(t, dict) or not (t.get("text") or t.get("media") or t.get("quote")):
        return None
    urls, ext = _fx_media(t.get("media"))
    out: dict = {"text": t.get("text") or "", "mediaURLs": urls, "media_extended": ext,
                 "tweetID": t.get("id")}
    q = t.get("quote")
    if isinstance(q, dict):
        qurls, qext = _fx_media(q.get("media"))
        out["qrtURL"] = q.get("url") or (
            f"https://twitter.com/i/status/{q['id']}" if q.get("id") else None)
        out["qrt"] = {"text": q.get("text") or "", "mediaURLs": qurls, "media_extended": qext,
                      "tweetID": q.get("id")}
    return out


FX_VIDEO_TARGET_BPS = 1_000_000          # 말풍선 재생용 화질 상한(≈480p, 950kbps). 원본은 25Mbps(2048×3640)로 85MB
_VIDEO_SIZE_RE = re.compile(r"/(\d{2,5})x(\d{2,5})/")


def _pick_video(m: dict) -> dict | None:
    """fxtwitter media 항목(video/gif) → 말풍선 재생용 dict (순수).

    video: mp4 변형 중 `FX_VIDEO_TARGET_BPS` 이하에서 가장 높은 화질(없으면 가장 낮은 것).
    gif: X 의 GIF 는 작은 mp4 라 `url` 그대로. 반환 `{url, poster, w, h, sec, kind}` — 재생 가능한 mp4 가
    없거나 poster(썸네일)가 없으면 None(호출부가 썸네일 이미지로 폴백).
    """
    kind = m.get("type")
    if kind not in ("video", "gif") or not m.get("thumbnail_url"):
        return None
    if kind == "gif":
        url = m.get("url")
        w, h = m.get("width"), m.get("height")
    else:
        mp4 = [v for v in (m.get("variants") or [])
               if v.get("content_type") == "video/mp4" and v.get("url") and v.get("bitrate")]
        if not mp4:
            return None
        under = [v for v in mp4 if v["bitrate"] <= FX_VIDEO_TARGET_BPS]
        pick = max(under, key=lambda v: v["bitrate"]) if under else min(mp4, key=lambda v: v["bitrate"])
        url = pick["url"]
        sm = _VIDEO_SIZE_RE.search(url)
        w, h = (int(sm.group(1)), int(sm.group(2))) if sm else (m.get("width"), m.get("height"))
    if not url or not str(url).split("?")[0].lower().endswith(".mp4"):
        return None
    return {"url": str(url), "poster": str(m["thumbnail_url"]), "w": w, "h": h,
            "sec": m.get("duration"), "kind": kind}


def fetch_video(tweet_id: str, *, session: Any = None, timeout: float = FX_TIMEOUT_SEC,
                base: str = FX_BASE) -> dict | None:
    """트윗의 첫 영상·GIF → 말풍선 재생용 `{url, poster, w, h, sec, kind}` | None.

    화질 변형은 fxtwitter 만 준다(vxtwitter 는 최고화질 mp4 하나뿐) — 영상 트윗에만 추가로 1회 호출.
    """
    if not tweet_id or not str(tweet_id).isdigit():
        return None
    j = _get_json(f"{base}/i/status/{tweet_id}", session, timeout, "fxtwitter")
    media = (((j or {}).get("tweet") or {}).get("media") or {}).get("all") or []
    for m in media:
        if isinstance(m, dict) and m.get("type") in ("video", "gif"):
            return _pick_video(m)
    return None


def _get_json(url: str, session: Any, timeout: float, tag: str) -> dict | None:
    """GET → JSON dict. 비200·타임아웃·JSON 오류 전부 경고 + None (서드파티라 조용히)."""
    try:
        if session:
            resp = session.get(url, timeout=timeout)
        else:
            if not requests:
                warnings.warn(f"{tag}: requests 미설치", stacklevel=3)
                return None
            resp = requests.get(url, timeout=timeout)

        if resp.status_code != 200:
            warnings.warn(f"{tag}: {resp.status_code} {url}", stacklevel=3)
            return None

        return resp.json()
    except Exception as e:  # 네트워크·타임아웃·JSON 오류 전부
        warnings.warn(f"{tag}: {type(e).__name__} {url}", stacklevel=3)
        return None


def fetch_tweet_fx(tweet_id: str, *, session: Any = None, timeout: float = FX_TIMEOUT_SEC,
                   base: str = FX_BASE) -> dict | None:
    """fxtwitter API 조회 → vxtwitter 응답 형식으로 변환한 dict | None."""
    if not tweet_id or not str(tweet_id).isdigit():
        return None
    j = _get_json(f"{base}/i/status/{tweet_id}", session, timeout, "fxtwitter")
    return _fx_to_vx(j) if j else None


def fetch_tweet(tweet_id: str, *, session: Any = None, timeout: float = VX_TIMEOUT_SEC,
                base: str = "https://api.vxtwitter.com", fx_base: str = FX_BASE,
                fallback: bool = True) -> dict | None:
    """vxtwitter API 조회(실패 시 fxtwitter 폴백). tweet_id(Snowflake) → JSON dict | None.

    Args:
        tweet_id: X 트윗 Snowflake id (숫자 문자열)
        session: requests.Session (None이면 새로 생성)
        timeout: vxtwitter 초 (기본 5.0)
        base: vxtwitter API 베이스 URL
        fx_base: fxtwitter API 베이스 URL
        fallback: False 면 vxtwitter 만

    Returns:
        {"text": str, "mediaURLs": [...], "media_extended": [...], ...} or None
        (fxtwitter 폴백 결과도 같은 형식)
    """
    if not tweet_id or not str(tweet_id).isdigit():
        warnings.warn(f"vxtwitter: 유효하지 않은 tweet_id={tweet_id}", stacklevel=2)
        return None

    j = _get_json(f"{base}/i/status/{tweet_id}", session, timeout, "vxtwitter")
    if j is not None or not fallback:
        return j

    j = fetch_tweet_fx(tweet_id, session=session, base=fx_base)
    if j is not None:
        _log.warning("vxtwitter 실패 → fxtwitter 폴백 성공 tweet=%s", tweet_id)
    return j


_VIDEO_TYPES = ("video", "gif", "animated_gif")


def _is_video_url(u: str) -> bool:
    """영상 파일 URL 인지 — 프론트가 미디어를 <img> 로만 그려서 mp4 를 넣으면 깨진다."""
    base = str(u).split("?")[0].lower()
    return "video.twimg.com" in base or base.endswith((".mp4", ".m3u8"))


def _media_urls(j: dict) -> list[str]:
    """vxtwitter JSON(또는 그 안의 qrt) → 이미지 URL 목록. media_extended 가 있으면 그것을 우선.

    프론트(`tweets.js` `_mediaGrid`)는 모든 URL 을 `<img src>` 로 그린다. 영상·GIF 는 `url` 이 mp4 라
    (2026-09-19 18:07 KST 아라레: 약 85MB mp4 가 깨진 이미지로 표시) 썸네일(`thumbnail_url`)을 쓰고,
    썸네일이 없으면 넣지 않는다. media_extended 가 없어 mediaURLs 만 있을 때도 mp4 는 거른다.
    """
    media_ext = j.get("media_extended") or []
    if media_ext and isinstance(media_ext, list):
        urls = []
        for m in media_ext:
            if not isinstance(m, dict):
                continue
            u = m.get("thumbnail_url") if m.get("type") in _VIDEO_TYPES else m.get("url")
            if u and not _is_video_url(u):
                urls.append(u)
        return urls
    return [u for u in (j.get("mediaURLs") or []) if u and not _is_video_url(u)]  # None·영상 URL 거름


def _has_video(j: dict) -> bool:
    """본인 트윗 첨부에 영상·GIF 가 있는지(참조 트윗 `qrt` 는 보지 않음)."""
    for m in j.get("media_extended") or []:
        if isinstance(m, dict) and m.get("type") in _VIDEO_TYPES:
            return True
    return any(_is_video_url(u) for u in (j.get("mediaURLs") or []) if u)


def extract(j: dict) -> dict:
    """vxtwitter JSON → {text, media: [url,...], urls: [expanded,...], yt_video_id: str|None}.

    Args:
        j: vxtwitter JSON 응답 dict

    Returns:
        {"text": str, "media": [url,...], "urls": [...], "yt_video_id": str|None}
    """
    text = str(j.get("text") or "")
    media_urls = _media_urls(j)

    # 확장 URL: 트윗 본문 내 URL들 (들어있으면 사용)
    urls = []
    if "urls" in j and j["urls"]:
        urls = [str(u.get("expanded_url") or u) for u in j["urls"] if u]

    # YouTube video_id 추출: text + urls + media 내용
    yt_video_id = None
    search_text = text + " " + " ".join(urls) + " " + " ".join(media_urls)
    m = _YT_VIDEO_RE.search(search_text)
    if m:
        yt_video_id = m.group(1)

    qrt_url = j.get("qrtURL") or None

    # (v3.7.3) 응답에 인용 트윗 본문이 실려 오면 그대로 쓴다 — 별도 fetch_tweet(qrt_id) 는 vxtwitter 가
    # 그 참조 트윗을 500 으로 못 주는 경우(2026-09-18 아라레 "2年半前…")에 유실되므로 최후 수단으로만.
    qrt = None
    q = j.get("qrt")
    if isinstance(q, dict):
        q_text, q_media = str(q.get("text") or ""), _media_urls(q)
        if q_text or q_media:
            qrt = {"text": q_text, "media": q_media}

    return {
        "text": text,
        "media": media_urls,
        "urls": urls,
        "yt_video_id": yt_video_id,
        "qrt_url": qrt_url,
        "qrt": qrt,
        "has_video": _has_video(j),
    }


def qrt_id(qrt_url: str | None) -> str | None:
    """extract() 의 qrt_url(".../status/<id>") → 인용된 트윗 id. 없으면 None."""
    m = _STATUS_ID_RE.search(qrt_url or "")
    return m.group(1) if m else None


if __name__ == "__main__":
    # self-test: fixture 없이 fake 세션으로 fetch 호출 + extract 테스트

    # (1) 200 응답 시뮬레이션 - 이미지 첨부 트윗
    fixture_image_tweet = {
        "text": "新しい衣装で配信します！https://www.youtube.com/live/abc123XYZ12",
        "mediaURLs": [
            "https://pbs.twimg.com/media/abc123.jpg",
            "https://pbs.twimg.com/media/def456.jpg",
        ],
        "media_extended": [
            {"url": "https://pbs.twimg.com/media/abc123.jpg", "type": "photo"},
        ],
        "urls": [
            {"expanded_url": "https://www.youtube.com/live/abc123XYZ12"},
        ],
    }

    # (2) 200 응답 - YouTube URL 포함 트윗 (이미지 없음)
    fixture_yt_tweet = {
        "text": "今日の配信は 20:00 から\nhttps://youtu.be/xyz789AB123",
        "mediaURLs": [],
        "urls": [
            {"expanded_url": "https://youtu.be/xyz789AB123"},
        ],
    }

    # (3) extract 테스트 - 이미지 트윗
    result1 = extract(fixture_image_tweet)
    assert result1["text"] == "新しい衣装で配信します！https://www.youtube.com/live/abc123XYZ12"
    assert len(result1["media"]) >= 1, f"media 개수: {len(result1['media'])}"
    assert result1["yt_video_id"] == "abc123XYZ12", f"yt_video_id={result1['yt_video_id']}"

    # (4) extract 테스트 - youtu.be URL
    result2 = extract(fixture_yt_tweet)
    assert result2["yt_video_id"] == "xyz789AB123", f"yt_video_id={result2['yt_video_id']}"

    # (5) extract 테스트 - youtube.com/watch?v= 형식
    fixture_watch = {"text": "https://www.youtube.com/watch?v=watch1AB12C"}
    result3 = extract(fixture_watch)
    assert result3["yt_video_id"] == "watch1AB12C", f"yt_video_id={result3['yt_video_id']}"

    # (6) extract 테스트 - video_id 없는 경우
    fixture_no_yt = {"text": "일반 소식입니다", "mediaURLs": []}
    result4 = extract(fixture_no_yt)
    assert result4["yt_video_id"] is None

    # (7) extract/qrt_id 테스트 - 인용(QRT) 트윗
    fixture_qrt_tweet = {
        "text": "音楽配信サービスでも聴いてもらえるの嬉しいなっ",
        "mediaURLs": [],
        "qrtURL": "https://twitter.com/i/status/1518309187515781125",
    }
    result5 = extract(fixture_qrt_tweet)
    assert result5["qrt_url"] == "https://twitter.com/i/status/1518309187515781125"
    assert qrt_id(result5["qrt_url"]) == "1518309187515781125"
    assert qrt_id(None) is None
    assert extract(fixture_no_yt)["qrt_url"] is None

    # ── (v3.7.3) fxtwitter 폴백 + 임베드 참조 트윗 ─────────────────────────────────────
    # 실측 2026-09-18 19:32 KST 아라레 "2年半前…💛💙"(2100895649764192693): vxtwitter 는 이 트윗과
    # 참조 트윗(1776172940654219620) 모두 HTTP 500, fxtwitter 는 200 + 참조 트윗 전문/사진 반환.
    QUOTE_TEXT = (
        "＼💛歌ってみた動画公開💙／\n\n#夢限大みゅーたいぷ\n"
        "仲町あられ・峰月律の歌ってみた動画をプレミア公開🎤✨️\n\n唱 / Ado\n"
        "【 covered by 仲町あられ・峰月律 】\n\nぜひたくさん聴いてくださいね🥰🎶\n\n"
        "ご視聴はこちらから👇\nhttps://www.youtube.com/watch?v=zVdR0urFjnc\n\n#バンドリ #ゆめみた"
    )
    fx_real = {
        "code": 200, "message": "OK",
        "tweet": {
            "id": "2100895649764192693", "text": "2年半前…💛💙", "media": None,
            "url": "https://x.com/arale_yumemita/status/2100895649764192693",
            "quote": {
                "id": "1776172940654219620", "text": QUOTE_TEXT,
                "url": "https://x.com/BDP_yumemita/status/1776172940654219620",
                "media": {"all": [{"type": "photo", "id": "1775814052524232705",
                                   "url": "https://pbs.twimg.com/media/GKT1eNvakAEbC3Q.png?name=orig"}]},
            },
        },
    }

    class _Resp:
        def __init__(self, status, body=None):
            self.status_code, self._body = status, body
        def json(self):
            if self._body is None:
                raise ValueError("no json")
            return self._body

    class _Sess:
        def __init__(self, vx, fx):
            self.vx, self.fx, self.calls = vx, fx, []
        def get(self, url, timeout=None):
            self.calls.append(url)
            r = self.fx if "fxtwitter" in url else self.vx
            if isinstance(r, Exception):
                raise r
            return r

    TID = "2100895649764192693"

    # (8) vx 500 → fx 폴백: 본문·참조 트윗 전문·사진(`?name=orig` 제거)
    s = _Sess(_Resp(500), _Resp(200, fx_real))
    j = fetch_tweet(TID, session=s)
    assert j and j["text"] == "2年半前…💛💙" and j["qrtURL"].endswith("/status/1776172940654219620"), j
    ex = extract(j)
    assert ex["qrt"] == {"text": QUOTE_TEXT, "media": ["https://pbs.twimg.com/media/GKT1eNvakAEbC3Q.png"]}, ex["qrt"]
    assert qrt_id(ex["qrt_url"]) == "1776172940654219620"
    assert len(s.calls) == 2 and "vxtwitter" in s.calls[0] and "fxtwitter" in s.calls[1], s.calls
    print("  vx 500 → fx 폴백 → 참조 트윗 전문·사진 복원")

    # (9) vx 정상이면 fx 는 부르지 않는다 (무회귀)
    s = _Sess(_Resp(200, {"text": "본문", "mediaURLs": [], "qrtURL": None}), _Resp(200, fx_real))
    assert fetch_tweet(TID, session=s)["text"] == "본문" and len(s.calls) == 1
    print("  vx 정상 → fx 미호출")

    # (10) 예외(타임아웃)·JSON 오류도 폴백, 둘 다 실패면 None (종전 동작)
    assert fetch_tweet(TID, session=_Sess(TimeoutError("t"), _Resp(200, fx_real)))["text"] == "2年半前…💛💙"
    assert fetch_tweet(TID, session=_Sess(_Resp(200, None), _Resp(200, fx_real)))["text"] == "2年半前…💛💙"
    assert fetch_tweet(TID, session=_Sess(_Resp(500), _Resp(404))) is None
    assert fetch_tweet(TID, session=_Sess(_Resp(500), _Resp(200, {"code": 404, "tweet": None}))) is None
    assert fetch_tweet(TID, session=_Sess(_Resp(500), _Resp(200, fx_real)), fallback=False) is None
    assert fetch_tweet("abc") is None
    print("  타임아웃·JSON 오류 폴백 / 둘 다 실패·fallback=False → None")

    # (11) 응답에 실린 vx `qrt` 도 임베드로 추출 (별도 조회 불필요)
    ex = extract({"text": "인용함", "mediaURLs": [], "qrtURL": "https://twitter.com/i/status/9",
                  "qrt": {"text": "원문", "mediaURLs": ["https://pbs.twimg.com/media/a.jpg"]}})
    assert ex["qrt"] == {"text": "원문", "media": ["https://pbs.twimg.com/media/a.jpg"]}
    assert extract({"text": "인용 없음"})["qrt"] is None
    assert extract({"text": "x", "qrt": {"text": "", "mediaURLs": []}})["qrt"] is None
    print("  vx 임베드 qrt 추출 / 없으면 None")

    # (12) 영상·GIF 는 썸네일, 사진은 원본, 사진+영상 혼합
    fx_media = {"tweet": {"id": "1", "text": "t", "media": {"all": [
        {"type": "photo", "url": "https://pbs.twimg.com/media/p.jpg?name=orig"},
        {"type": "video", "url": "https://video.twimg.com/v.mp4", "thumbnail_url": "https://pbs.twimg.com/v_thumb.jpg"},
        {"type": "gif", "url": "https://video.twimg.com/g.mp4", "thumbnail_url": "https://pbs.twimg.com/g_thumb.jpg"},
    ]}, "quote": None}}
    assert extract(_fx_to_vx(fx_media))["media"] == [
        "https://pbs.twimg.com/media/p.jpg", "https://pbs.twimg.com/v_thumb.jpg", "https://pbs.twimg.com/g_thumb.jpg"]
    assert _fx_to_vx({"tweet": {"id": "1"}}) is None and _fx_to_vx({}) is None
    print("  fx 미디어: 사진 원본 / 영상·GIF 썸네일, 빈 응답 None")

    # ── (v3.7.4) 영상·GIF 는 썸네일 — 실측 2026-09-19 18:07 KST 아라레(2101235831302431170) 응답 ──
    VID = "https://video.twimg.com/amplify_video/2101235386622337024/vid/avc1/2048x3640/iJ5bUEboPJurhJ1-.mp4"
    THUMB = "https://pbs.twimg.com/amplify_video_thumb/2101235386622337024/img/n0IZViYALnC2NzA-.jpg"
    vx_video = {
        "text": "今日はみゃーちゃんのお誕生日〜🎂✨️", "mediaURLs": [VID],
        "media_extended": [{"type": "video", "url": VID, "thumbnail_url": THUMB}],
        "qrtURL": "https://twitter.com/i/status/1",
        "qrt": {"text": "／\nHappy Birthday🎂", "mediaURLs": ["https://pbs.twimg.com/media/HSimxbEbMAAZAKH.jpg"],
                "media_extended": [{"type": "image", "url": "https://pbs.twimg.com/media/HSimxbEbMAAZAKH.jpg",
                                    "thumbnail_url": "https://pbs.twimg.com/media/HSimxbEbMAAZAKH.jpg"}]},
    }
    ex = extract(vx_video)
    assert ex["media"] == [THUMB], ex["media"]                      # mp4 → 썸네일 (수정 전: [VID] → 깨진 <img>)
    assert ex["qrt"]["media"] == ["https://pbs.twimg.com/media/HSimxbEbMAAZAKH.jpg"], ex["qrt"]  # 이미지는 종전대로
    print("  vx 영상: mp4 대신 썸네일, 참조 트윗의 이미지는 그대로")

    # 이미지+영상 혼합 / GIF / 썸네일 없는 영상(넣지 않음) / media_extended 없이 mediaURLs 에 mp4 만
    mixed = {"text": "t", "media_extended": [
        {"type": "image", "url": "https://pbs.twimg.com/media/a.jpg", "thumbnail_url": "https://pbs.twimg.com/media/a.jpg"},
        {"type": "video", "url": VID, "thumbnail_url": THUMB},
        {"type": "gif", "url": "https://video.twimg.com/tweet_video/g.mp4", "thumbnail_url": "https://pbs.twimg.com/tweet_video_thumb/g.jpg"},
        {"type": "video", "url": "https://video.twimg.com/x.mp4"},
    ]}
    assert extract(mixed)["media"] == ["https://pbs.twimg.com/media/a.jpg", THUMB, "https://pbs.twimg.com/tweet_video_thumb/g.jpg"]
    assert extract({"text": "t", "mediaURLs": [VID, "https://pbs.twimg.com/media/b.jpg?name=orig"]})["media"] == \
        ["https://pbs.twimg.com/media/b.jpg?name=orig"]
    assert extract({"text": "t", "mediaURLs": ["https://x/y.m3u8", "https://video.twimg.com/z"]})["media"] == []
    print("  혼합·GIF·썸네일 없는 영상(제외)·mediaURLs 만 있는 mp4(제외)")

    # fx 경로와 결과가 같은 형태 — 영상 트윗을 fx 로 받아도 vx 와 같은 썸네일
    fx_vid = {"tweet": {"id": "2101235831302431170", "text": "t", "media": {"all": [
        {"type": "video", "url": VID, "thumbnail_url": THUMB}]}, "quote": None}}
    assert extract(_fx_to_vx(fx_vid))["media"] == extract(vx_video)["media"] == [THUMB]
    print("  vx·fx 경로가 같은 썸네일을 낸다")

    # ── (v3.8.0) 말풍선 재생용 영상 변형 선택 — 실측 2026-09-19 18:07 KST 아라레 fxtwitter 변형 목록 ──
    B = "https://video.twimg.com/amplify_video/2101235386622337024/vid/avc1/"
    fx_variants = [
        {"bitrate": 0, "content_type": "application/x-mpegURL", "url": "https://video.twimg.com/amplify_video/2101235386622337024/pl/kg.m3u8?tag=29"},
        {"bitrate": 632000, "content_type": "video/mp4", "url": B + "320x568/dnX6.mp4?tag=29"},
        {"bitrate": 950000, "content_type": "video/mp4", "url": B + "480x852/64BM.mp4?tag=29"},
        {"bitrate": 2176000, "content_type": "video/mp4", "url": B + "720x1278/tziaL.mp4?tag=29"},
        {"bitrate": 10368000, "content_type": "video/mp4", "url": B + "1080x1918/IXHq.mp4?tag=29"},
        {"bitrate": 25128000, "content_type": "video/mp4", "url": B + "2048x3640/iJ5b.mp4?tag=29"},
    ]
    fx_video_media = {"type": "video", "url": B + "2048x3640/iJ5b.mp4?tag=29", "thumbnail_url": THUMB,
                      "width": 2048, "height": 3640, "duration": 35.68, "variants": fx_variants}
    pv = _pick_video(fx_video_media)
    assert pv == {"url": B + "480x852/64BM.mp4?tag=29", "poster": THUMB, "w": 480, "h": 852, "sec": 35.68, "kind": "video"}, pv
    print("  영상: 950kbps(480×852) 선택 — 원본 25Mbps·m3u8 제외, w/h 는 URL 에서")

    only_big = dict(fx_video_media, variants=[v for v in fx_variants if v["bitrate"] >= 2000000])
    assert "720x1278" in _pick_video(only_big)["url"], "상한 이하가 없으면 가장 낮은 mp4"
    assert _pick_video(dict(fx_video_media, variants=[fx_variants[0]])) is None, "mp4 변형이 없으면 None(썸네일 폴백)"
    assert _pick_video(dict(fx_video_media, thumbnail_url=None)) is None, "poster 없으면 None"
    print("  상한 이하 없음→최저 mp4 / mp4 없음·poster 없음→None")

    gif = {"type": "gif", "url": "https://video.twimg.com/tweet_video/G1.mp4", "thumbnail_url": "https://pbs.twimg.com/tweet_video_thumb/G1.jpg",
           "width": 400, "height": 300, "duration": 3.2}
    assert _pick_video(gif) == {"url": "https://video.twimg.com/tweet_video/G1.mp4", "poster": "https://pbs.twimg.com/tweet_video_thumb/G1.jpg",
                                "w": 400, "h": 300, "sec": 3.2, "kind": "gif"}
    assert _pick_video({"type": "photo", "url": "https://pbs.twimg.com/media/a.jpg"}) is None
    print("  GIF: url(mp4) 그대로 / 사진은 None")

    # fetch_video: fx 응답에서 첫 영상 선택, 사진만 있으면 None, 실패하면 None
    fx_tweet = {"tweet": {"id": TID, "text": "t", "media": {"all": [
        {"type": "photo", "url": "https://pbs.twimg.com/media/p.jpg?name=orig"}, fx_video_media]}}}
    s = _Sess(_Resp(500), _Resp(200, fx_tweet))
    assert fetch_video(TID, session=s)["w"] == 480 and len(s.calls) == 1 and "fxtwitter" in s.calls[0]
    assert fetch_video(TID, session=_Sess(_Resp(500), _Resp(200, {"tweet": {"media": {"all": [{"type": "photo", "url": "u"}]}}}))) is None
    assert fetch_video(TID, session=_Sess(_Resp(500), _Resp(404))) is None and fetch_video("abc") is None
    print("  fetch_video: 혼합 미디어에서 영상만 / 사진만·실패 → None")

    # extract().has_video — 영상 트윗만 True (참조 트윗의 영상은 보지 않음)
    assert extract(vx_video)["has_video"] is True
    assert extract({"text": "t", "mediaURLs": ["https://pbs.twimg.com/media/a.jpg"]})["has_video"] is False
    assert extract({"text": "t", "mediaURLs": [VID]})["has_video"] is True
    assert extract({"text": "t", "qrt": {"text": "q", "media_extended": [{"type": "video", "url": VID, "thumbnail_url": THUMB}]}})["has_video"] is False
    print("  extract.has_video: 본인 영상만 True")

    print("✓ vxtwitter.extract self-test 통과 (20/20)")
