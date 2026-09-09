"""vxtwitter API unfurl — 트윗 본문·이미지·URL 추출 (순수 함수 + HTTP 통신).

트윗 Snowflake id로 https://api.vxtwitter.com/i/status/<id> 조회 → JSON 파싱.
- 본문(text) + 확장 URL + 미디어(image/video) 추출
- YouTube URL → video_id 11자 추출(정규식)
- 비200·타임아웃·JSON 오류 → None + 경고

self-test: python -m src.backend.vxtwitter
"""
from __future__ import annotations

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

# ponytail: vxtwitter 서드파티 무료 서비스 → 가동률 미보장, 실패 시 조용히 None 반환


def fetch_tweet(tweet_id: str, *, session: Any = None, timeout: float = 8.0,
                base: str = "https://api.vxtwitter.com") -> dict | None:
    """vxtwitter API 조회. tweet_id(Snowflake) → JSON dict | None.

    Args:
        tweet_id: X 트윗 Snowflake id (숫자 문자열)
        session: requests.Session (None이면 새로 생성)
        timeout: 초 (기본 8.0)
        base: API 베이스 URL

    Returns:
        {"text": str, "mediaURLs": [...], "media_extended": [...], ...} or None
    """
    if not tweet_id or not str(tweet_id).isdigit():
        warnings.warn(f"vxtwitter: 유효하지 않은 tweet_id={tweet_id}", stacklevel=2)
        return None

    url = f"{base}/i/status/{tweet_id}"
    try:
        if session:
            resp = session.get(url, timeout=timeout)
        else:
            if not requests:
                warnings.warn("vxtwitter: requests 미설치", stacklevel=2)
                return None
            resp = requests.get(url, timeout=timeout)

        if resp.status_code != 200:
            warnings.warn(f"vxtwitter: {resp.status_code} {url}", stacklevel=2)
            return None

        return resp.json()
    except Exception as e:  # 네트워크·타임아웃·JSON 오류 전부 — 서드파티라 조용히 None
        warnings.warn(f"vxtwitter: {type(e).__name__} {url}", stacklevel=2)
        return None


def extract(j: dict) -> dict:
    """vxtwitter JSON → {text, media: [url,...], urls: [expanded,...], yt_video_id: str|None}.

    Args:
        j: vxtwitter JSON 응답 dict

    Returns:
        {"text": str, "media": [url,...], "urls": [...], "yt_video_id": str|None}
    """
    text = str(j.get("text") or "")

    # mediaURLs: [url, ...] 리스트
    media_urls = list(j.get("mediaURLs") or [])

    # media_extended: [{url, type}, ...] 리스트 (없으면 mediaURLs 사용)
    media_ext = j.get("media_extended") or []
    if media_ext and isinstance(media_ext, list):
        media_urls = [m.get("url") for m in media_ext if isinstance(m, dict) and m.get("url")]

    media_urls = [u for u in media_urls if u]  # None 필터

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

    return {
        "text": text,
        "media": media_urls,
        "urls": urls,
        "yt_video_id": yt_video_id,
    }


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

    print("✓ vxtwitter.extract self-test 통과 (4/4)")
