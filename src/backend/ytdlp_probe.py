"""회원 전용 라이브 조회 (yt-dlp) — 유튜브 앱 "회원 전용 실시간 스트림" 푸시 알림 후속.

알림(`SPONSORSHIPS_LIVESTREAM_START`)에는 `video_id` 가 `default` 라 영상 URL 을 알 수 없다.
그래서 알림을 받은 즉시 그 멤버 채널의 streams 탭을 yt-dlp 로 읽어 회원 전용(subscriber_only)
라이브의 video_id/URL 을 얻는다. 채널 목록 페이지만 읽으므로(영상 스트림 요청 없음) Cloud Run
데이터센터 IP 에서도 쿠키 없이 동작함을 확인했다(2026-09-19, asia-northeast1). 쿠키(`YT_COOKIES_FILE`)가
있으면 먼저 쿠키로 시도하고, 실패하면 쿠키 없이 재시도한다.

self-test: python -m src.backend.ytdlp_probe
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import unicodedata

log = logging.getLogger(__name__)

DEADLINE_SEC = 6.0        # Automate HTTP 타임아웃(약 10초) 안에 끝내기 위한 전체 상한
RETRY_GAP_SEC = 2.0       # 알림 직후엔 목록 반영이 늦을 수 있어 1회 재시도
LIST_LIMIT = 12
SOCKET_TIMEOUT_SEC = 5.0


def _norm(s: str | None) -> str:
    return " ".join(unicodedata.normalize("NFKC", s or "").split())


def _title_match(entry_title: str | None, want: str | None) -> bool:
    if not want:
        return False
    a, b = _norm(entry_title), _norm(want)
    if not a or not b:
        return False
    if b.endswith("…") or b.endswith("..."):
        return a.startswith(b.rstrip("….").rstrip())
    return a == b


def pick_member_live(entries: list[dict], title: str | None) -> dict | None:
    """streams 탭 항목들에서 지금 시작한 회원 전용 라이브 1건을 고른다 (순수).

    후보 = availability `subscriber_only` 이면서 live_status 가 is_live/is_upcoming.
    1) 제목이 일치하는 후보(is_live 우선)  2) 제목 매칭 실패 시 is_live 가 정확히 1건이면 그것.
    was_live 는 이미 끝난 방송이라 후보에서 제외. 2025년 옛 예정 항목처럼 제목이 안 맞는
    is_upcoming 은 고르지 않는다.
    """
    cands = [
        e for e in entries or []
        if e and e.get("availability") == "subscriber_only"
        and e.get("live_status") in ("is_live", "is_upcoming") and e.get("id")
    ]
    matched = [e for e in cands if _title_match(e.get("title"), title)]
    matched.sort(key=lambda e: 0 if e.get("live_status") == "is_live" else 1)
    pick = matched[0] if matched else None
    if pick is None:
        live_only = [e for e in cands if e.get("live_status") == "is_live"]
        if len(live_only) == 1:
            pick = live_only[0]
    if pick is None:
        return None
    vid = pick["id"]
    return {
        "video_id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": pick.get("title"),
        "live_status": pick.get("live_status"),
    }


def list_streams(channel_id: str, *, cookiefile: str | None = None) -> list[dict]:
    """채널 streams 탭 상단 항목(flat). yt-dlp 는 지연 import (미설치 환경 self-test 보호)."""
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": LIST_LIMIT,
        "skip_download": True,
        "socket_timeout": SOCKET_TIMEOUT_SEC,
        "cachedir": False,
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/channel/{channel_id}/streams", download=False)
    return [e for e in ((info or {}).get("entries") or []) if e]


def _cookie_copy() -> str | None:
    """마운트된 쿠키(읽기 전용 Secret)를 /tmp 로 복사. yt-dlp 가 종료 시 쿠키 파일을 다시 쓰기 때문."""
    src = os.environ.get("YT_COOKIES_FILE", "").strip()
    if not src or not os.path.isfile(src):
        return None
    fd, dst = tempfile.mkstemp(prefix="ytck_", suffix=".txt")
    os.close(fd)
    shutil.copyfile(src, dst)
    return dst


def find_member_live(
    channel_id: str, title: str | None, *,
    lister=list_streams, deadline_sec: float = DEADLINE_SEC, retry_gap_sec: float = RETRY_GAP_SEC,
    sleep=time.sleep, monotonic=time.monotonic, cookiefile: str | None = None,
) -> dict | None:
    """알림 직후 회원 전용 라이브의 video_id/URL 을 찾는다. 못 찾으면 None (호출부가 폴백).

    쿠키가 있으면 쿠키→쿠키 없이 순서로 시도. 목록에 아직 안 떴으면 retry_gap 후 1회 재시도.
    전체 소요는 deadline_sec 를 넘기지 않는다.
    """
    t0 = monotonic()
    own_cookie = False
    if cookiefile is None:
        cookiefile = _cookie_copy()
        own_cookie = cookiefile is not None
    modes = [cookiefile, None] if cookiefile else [None]
    try:
        for attempt in (1, 2):
            for ck in modes:
                if monotonic() - t0 >= deadline_sec:
                    return None
                try:
                    found = pick_member_live(lister(channel_id, cookiefile=ck), title)
                except Exception as e:  # noqa: BLE001
                    log.warning("yt-dlp 조회 실패(cookie=%s attempt=%d): %s", bool(ck), attempt, str(e)[:160])
                    continue
                if found:
                    found["via_cookie"] = bool(ck)
                    return found
                break  # 조회는 성공했지만 후보 없음 → 쿠키 없이 재조회는 무의미, 재시도로
            if attempt == 1:
                if monotonic() - t0 + retry_gap_sec >= deadline_sec:
                    return None
                sleep(retry_gap_sec)
    finally:
        if own_cookie:
            try:
                os.remove(cookiefile)
            except OSError:
                pass
    return None


if __name__ == "__main__":
    # 실측: 2026-09-19 아라레 streams 탭 (yt-dlp --flat-playlist). HN2xeIVMqWI = 9/18 회원 전용 방송(당시 시작 전 상태로 재구성).
    T = "【🟡メン限】今の鼻事情いつもの気ままあーんど作業？？【 仲町あられ / 夢限大みゅーたいぷ 】"
    base = [
        {"id": "yK8WRu40qVY", "title": "🌟ライブTY🌟ARALE Acoustic LIVE ～Copal～", "live_status": "is_upcoming", "availability": "subscriber_only"},
        {"id": "3tQbs-OKrys", "title": "🌟誕生日グッズ2026🌟", "live_status": "is_upcoming", "availability": None},
        {"id": "6rJiVrTaTBE", "title": "【🟡#アワーノーツ 】", "live_status": "was_live", "availability": None},
    ]
    live = base + [{"id": "HN2xeIVMqWI", "title": T, "live_status": "is_live", "availability": "subscriber_only"}]

    p = pick_member_live(live, T)
    assert p and p["video_id"] == "HN2xeIVMqWI" and p["url"].endswith("v=HN2xeIVMqWI"), p
    print("[OK] 제목 일치 + is_live → 선택")

    p = pick_member_live(live, "다른 제목")
    assert p and p["video_id"] == "HN2xeIVMqWI", "제목 불일치여도 is_live 가 1건이면 선택"
    print("[OK] 제목 불일치 + is_live 1건 → 선택 (2025 옛 is_upcoming 은 무시)")

    p = pick_member_live(live, T[:20] + "…")
    assert p and p["video_id"] == "HN2xeIVMqWI", "말줄임 접두 일치"
    print("[OK] 말줄임(…) 접두 매칭")

    two = live + [{"id": "ZZZZZZZZZZZ", "title": "다른 멤버방", "live_status": "is_live", "availability": "subscriber_only"}]
    assert pick_member_live(two, "무관") is None, "is_live 가 2건이면 제목 없이는 모호 → None"
    assert pick_member_live(two, T)["video_id"] == "HN2xeIVMqWI"
    print("[OK] is_live 2건: 제목 있어야만 선택")

    ended = base + [{"id": "HN2xeIVMqWI", "title": T, "live_status": "was_live", "availability": "subscriber_only"}]
    assert pick_member_live(ended, T) is None, "was_live 는 제외"
    assert pick_member_live(base, "무관") is None
    print("[OK] was_live·후보 없음 → None")

    pub = base + [{"id": "PUBLICLIVE01", "title": T, "live_status": "is_live", "availability": None}]
    assert pick_member_live(pub, T) is None, "공개 방송은 회원 전용 후보 아님"
    print("[OK] 공개 라이브는 후보 제외")

    # find_member_live: 재시도·쿠키 폴백·데드라인 (가짜 lister / 가짜 시계)
    class Clock:
        def __init__(self): self.t = 0.0
        def mono(self): return self.t
        def sleep(self, s): self.t += s

    c = Clock(); calls = []
    def lister_lag(cid, cookiefile=None):
        calls.append((cid, cookiefile))
        c.t += 0.5
        return live if len(calls) >= 2 else base
    r = find_member_live("UCX", T, lister=lister_lag, sleep=c.sleep, monotonic=c.mono, cookiefile=None)
    assert r and r["video_id"] == "HN2xeIVMqWI" and len(calls) == 2
    print("[OK] 목록 반영 지연 → 재시도 후 성공")

    c = Clock(); calls = []
    def lister_cookie_bad(cid, cookiefile=None):
        calls.append(cookiefile)
        if cookiefile:
            raise RuntimeError("Sign in to confirm")
        return live
    r = find_member_live("UCX", T, lister=lister_cookie_bad, sleep=c.sleep, monotonic=c.mono, cookiefile="/tmp/x")
    assert r and r["via_cookie"] is False and calls == ["/tmp/x", None], calls
    print("[OK] 쿠키 실패 → 쿠키 없이 폴백")

    c = Clock()
    def lister_slow(cid, cookiefile=None):
        c.t += 5.0
        return base
    assert find_member_live("UCX", T, lister=lister_slow, sleep=c.sleep, monotonic=c.mono, cookiefile=None) is None
    assert c.t <= 6.0 + 5.0
    print("[OK] 데드라인 초과 → None")

    def lister_boom(cid, cookiefile=None):
        raise RuntimeError("network")
    c = Clock()
    assert find_member_live("UCX", T, lister=lister_boom, sleep=c.sleep, monotonic=c.mono, cookiefile=None) is None
    print("[OK] 조회 예외 → None (호출부 폴백)")
    print("\nSUCCESS: ytdlp_probe self-test 통과")
