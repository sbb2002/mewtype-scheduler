"""
YouTube RSS feed collector.
Fetches video IDs from YouTube channel RSS feeds.
"""

import logging
import threading
import time
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)

# Namespaces used in YouTube RSS feeds
NAMESPACES = {
    'atom': 'http://www.w3.org/2005/Atom',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
}

# Browser-like User-Agent
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# 간헐 404·5xx·타임아웃 대응 짧은 백오프 — 재시도 2회(총 시도 3회), 단위 초
RETRY_BACKOFF_SEC = (1.0, 3.0)
# 재시도할 HTTP 상태 코드 (그 외 4xx 는 영구 실패로 보고 즉시 포기)
_RETRY_STATUS = {404, 429, 500, 502, 503, 504}


def _sleep(sec: float) -> None:
    """백오프 대기. 테스트에서 no-op 으로 바꿔 끼울 수 있도록 감싼다."""
    time.sleep(sec)


def _parse_rss(xml_text: str) -> list[str]:
    """
    Pure function to parse YouTube RSS XML and extract video IDs.

    Args:
        xml_text: XML content as string

    Returns:
        List of video IDs in document order (newest first), max 15
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"Failed to parse RSS XML: {e}")
        return []

    video_ids = []

    # Find all entry elements and extract yt:videoId
    for entry in root.findall('atom:entry', NAMESPACES):
        video_id_elem = entry.find('yt:videoId', NAMESPACES)
        if video_id_elem is not None and video_id_elem.text:
            video_ids.append(video_id_elem.text)

    # Return max 15 videos
    return video_ids[:15]


# 지속 실패 채널 휴지 — 한 번 실패(재시도 포함)한 채널은 연속 실패 횟수에 따라 잠시 건너뛴다(10분 → 30분 → 60분).
# 몇 시간째 404 가 이어지는 채널에 매 틱 요청 · 로그를 쌓지 않기 위함. 프로세스 메모리에만 둔다(러너 재시작 시 초기화).
SUSPEND_SEC = (600, 1800, 3600)
WARN_EVERY_SEC = 3600  # 같은 채널의 WARN 은 이 간격마다 한 번만
_STATE: dict[str, dict] = {}
_LOCK = threading.Lock()
_clock = time.time


def _fetch_text_with_retry(url: str, session, timeout: float) -> tuple[Optional[str], Optional[Exception], int]:
    """(본문 | None, 마지막 오류, 시도 횟수). 재시도 대상은 _RETRY_STATUS · 타임아웃 · 연결 오류."""
    headers = {'User-Agent': USER_AGENT}
    last_error: Optional[Exception] = None
    attempts = 0
    for attempt in range(len(RETRY_BACKOFF_SEC) + 1):
        attempts = attempt + 1
        try:
            response = session.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            return response.text, None, attempts
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            last_error = e
            if status not in _RETRY_STATUS:
                break
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
        except Exception as e:  # noqa: BLE001
            last_error = e
            break
        if attempt < len(RETRY_BACKOFF_SEC):
            logger.debug("RSS retry %s after attempt %d: %s", url, attempts, last_error)
            _sleep(RETRY_BACKOFF_SEC[attempt])
    return None, last_error, attempts


def fetch_feed_text(channel_id: str, *, timeout: float = 10.0, session: Optional[requests.Session] = None,
                    fail_msg: str = "Failed to fetch RSS for channel {cid}") -> Optional[str]:
    """채널 RSS 본문. 실패(재시도 후)나 휴지 중이면 None.
    휴지 중에는 요청도 로그도 하지 않고, 채널당 WARN 은 WARN_EVERY_SEC 마다 한 번, 복구되면 INFO 한 번."""
    now = _clock()
    with _LOCK:
        st = _STATE.get(channel_id)
        if st and now < st["until"]:
            logger.debug("RSS 휴지 중 %s (남은 %ds)", channel_id, st["until"] - now)
            return None
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    text, err, attempts = _fetch_text_with_retry(url, session if session is not None else requests.Session(), timeout)
    now = _clock()
    with _LOCK:
        st = _STATE.get(channel_id)
        if text is not None:
            if st:
                _STATE.pop(channel_id, None)
                logger.info("RSS 복구: %s (연속 %d회 실패 후, 약 %d분)", channel_id, st["streak"], (now - st["since"]) // 60)
            return text
        if st is None:
            st = _STATE[channel_id] = {"streak": 0, "since": now, "last_warn": 0.0, "until": 0.0}
        st["streak"] += 1
        wait = SUSPEND_SEC[min(st["streak"], len(SUSPEND_SEC)) - 1]
        st["until"] = now + wait
        warn = now - st["last_warn"] >= WARN_EVERY_SEC
        if warn:
            st["last_warn"] = now
        streak = st["streak"]
    if warn:
        logger.warning("%s: %s (시도 %d회, 연속 실패 %d번째 — %d분간 건너뜀)", fail_msg.format(cid=channel_id), err, attempts, streak, wait // 60)
    else:
        logger.debug("%s: %s (연속 실패 %d번째)", fail_msg.format(cid=channel_id), err, streak)
    return None


# ── 시차 폴링 (로컬 러너) ─────────────────────────────────────────────────────
# 틱마다 6개 채널을 1~2분 안에 몰아 요청하면 YouTube 쪽 제한(404·500)에 걸릴 수 있다는 가설에 따라, 별도 스레드가
# 채널마다 STAGGER_SEC(1분)씩 어긋나게 PERIOD_SEC(10분)당 한 번씩 받아 캐시에 둔다. 틱은 캐시만 읽는다(네트워크 없음).
# 폴러가 켜져 있지 않으면(Cloud Run 등) 기존처럼 틱이 직접 요청한다.
PERIOD_SEC = 600
STAGGER_SEC = 60
_CACHE: dict[str, dict] = {}
_POLLER_ON = False


def poller_active() -> bool:
    return _POLLER_ON


def cached_feed_text(channel_id: str) -> Optional[str]:
    """폴러가 마지막으로 받은 본문(없으면 None). 실패한 폴링은 이전 본문을 지우지 않는다."""
    with _LOCK:
        c = _CACHE.get(channel_id)
        return c["text"] if c else None


def next_slot(now: float, index: int, count: int, *, period: int = PERIOD_SEC, stagger: int = STAGGER_SEC) -> float:
    """index 번째 채널의 다음 폴링 시각(epoch). 마지막 채널이 격자(period 배수)보다 1분 앞에 끝나도록 앞쪽에 배치해,
    격자 시각에 도는 틱이 방금 받은 데이터를 읽게 한다. (period=600, count=6 → 격자 앞 6~1분 사이 매분 한 채널)"""
    off = (period - (count - index) * stagger) % period
    base = now - (now % period) + off
    while base <= now:
        base += period
    return base


def poll_loop(channel_ids: list[str], stop: threading.Event, *, now=None, period: int = PERIOD_SEC, stagger: int = STAGGER_SEC) -> None:
    """채널마다 시차를 두고 RSS 를 받아 캐시한다. 시작하자마자 stagger 간격으로 한 바퀴 돌아 캐시를 채운다."""
    global _POLLER_ON
    clock = now or _clock
    n = len(channel_ids)
    due = {cid: clock() + i * stagger for i, cid in enumerate(channel_ids)}
    _POLLER_ON = True
    logger.info("RSS 폴러 시작: 채널 %d개, %d초 주기, %d초 간격", n, period, stagger)
    session = requests.Session()
    try:
        while not stop.is_set() and due:
            cid, when = min(due.items(), key=lambda kv: kv[1])
            if stop.wait(max(0.0, when - clock())):
                break
            text = fetch_feed_text(cid, session=session)
            if text is not None:
                with _LOCK:
                    _CACHE[cid] = {"text": text, "at": clock()}
            due[cid] = next_slot(clock() + period // 2, channel_ids.index(cid), n, period=period, stagger=stagger)  # 시작 직후 한 바퀴가 격자와 겹쳐 연달아 두 번 받지 않게 최소 반 주기 뒤
    finally:
        _POLLER_ON = False


def start_poller(channel_ids: list[str], stop: threading.Event) -> threading.Thread:
    th = threading.Thread(target=poll_loop, args=(list(channel_ids), stop), name="rss-poller", daemon=True)
    th.start()
    return th


def fetch_rss_video_ids(
    channel_id: str,
    *,
    timeout: float = 10.0,
    session: Optional[requests.Session] = None
) -> list[str]:
    """
    Fetch video IDs from a YouTube channel's RSS feed.

    Returns:
        List of video IDs (newest-first, max 15).
        재시도 대상(404·429·5xx · 타임아웃 · 연결 오류)은 1초·3초 백오프로 재시도하고,
        그래도 실패하면 [] — 그 채널은 연속 실패 횟수에 따라 10/30/60분 건너뛴다(fetch_feed_text).
        파싱 실패와 그 외 4xx 는 재시도하지 않는다.
    """
    text = fetch_feed_text(channel_id, timeout=timeout, session=session)
    if text is None:
        return []
    try:
        return _parse_rss(text)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Error processing RSS for channel {channel_id}: {e}")
        return []


def fetch_all_rss_video_ids(channel_id_by_key: dict[str, str]) -> dict[str, list[str]]:
    """
    Fetch video IDs for multiple channels using a shared session.

    Args:
        channel_id_by_key: Dict mapping channel key to channel ID

    Returns:
        Dict mapping channel key to list of video IDs.
        Failed channels yield [] for that key.
    """
    result = {}

    # Reuse one session for all requests
    if _POLLER_ON:  # 폴러가 시차를 두고 받아 둔 캐시만 읽는다 — 틱은 YouTube 에 요청하지 않는다
        for key, channel_id in channel_id_by_key.items():
            text = cached_feed_text(channel_id)
            try:
                result[key] = _parse_rss(text) if text else []
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Error processing RSS for channel {channel_id}: {e}")
                result[key] = []
        return result

    with requests.Session() as session:
        for key, channel_id in channel_id_by_key.items():
            result[key] = fetch_rss_video_ids(channel_id, session=session)

    return result


if __name__ == "__main__":
    # Test with fixture file
    fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "rss_arale.xml"

    try:
        xml_content = fixture_path.read_text(encoding='utf-8')
        video_ids = _parse_rss(xml_content)

        count = len(video_ids)
        print(f"Total videos: {count}")
        print(f"First 3 IDs: {video_ids[:3]}")

        # Verify count is exactly 15
        assert count == 15, f"Expected 15 videos, got {count}"
        print("SUCCESS: RSS parser test passed")

        # 재시도 검사 — 네트워크 없이 가짜 session 과 no-op _sleep 으로 실행
        class _FakeResponse:
            def __init__(self, status=200, text=""):
                self.status_code = status
                self.text = text

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError(f"{self.status_code} Error", response=self)

        class _FakeSession:
            def __init__(self, script):
                self.script = list(script)
                self.calls = 0

            def get(self, url, timeout=None, headers=None):
                self.calls += 1
                item = self.script.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item

        class _Cap(logging.Handler):
            def __init__(self):
                super().__init__()
                self.records = []

            def emit(self, record):
                self.records.append(record)

        def _run(script):
            _STATE.clear()
            sleeps = []
            cap = _Cap()
            logger.addHandler(cap)
            saved_sleep = globals()["_sleep"]
            globals()["_sleep"] = sleeps.append
            try:
                sess = _FakeSession(script)
                ids = fetch_rss_video_ids("UCtest", session=sess)
            finally:
                globals()["_sleep"] = saved_sleep
                logger.removeHandler(cap)
            warns = [r.getMessage() for r in cap.records if r.levelno == logging.WARNING]
            return ids, sess.calls, sleeps, warns

        expected_ids = _parse_rss(xml_content)

        # A. 404 두 번 후 성공 → 15개, 시도 3회, 백오프 2번, WARN 없음
        ids, calls, sleeps, warns = _run([
            _FakeResponse(404), _FakeResponse(404), _FakeResponse(200, xml_content),
        ])
        assert ids == expected_ids, f"A: ids mismatch: {ids}"
        assert calls == 3, f"A: expected 3 calls, got {calls}"
        assert sleeps == [1.0, 3.0], f"A: sleeps {sleeps}"
        assert warns == [], f"A: unexpected warnings {warns}"

        # B. 404 세 번 → [], 시도 3회, WARN 정확히 1건(시도 3회 표기)
        ids, calls, sleeps, warns = _run([
            _FakeResponse(404), _FakeResponse(404), _FakeResponse(404),
        ])
        assert ids == [], f"B: expected [], got {ids}"
        assert calls == 3, f"B: expected 3 calls, got {calls}"
        assert len(warns) == 1 and "시도 3회" in warns[0], f"B: warnings {warns}"

        # C. 403 → 재시도 없이 1회 시도 후 [], WARN 1건(시도 1회 표기)
        ids, calls, sleeps, warns = _run([_FakeResponse(403)])
        assert ids == [], f"C: expected [], got {ids}"
        assert calls == 1, f"C: expected 1 call, got {calls}"
        assert sleeps == [], f"C: unexpected sleeps {sleeps}"
        assert len(warns) == 1 and "시도 1회" in warns[0], f"C: warnings {warns}"

        # D. 타임아웃 → 연결 오류 → 성공 → 15개, 시도 3회
        ids, calls, sleeps, warns = _run([
            requests.Timeout("timeout"), requests.ConnectionError("conn"),
            _FakeResponse(200, xml_content),
        ])
        assert ids == expected_ids, f"D: ids mismatch: {ids}"
        assert calls == 3, f"D: expected 3 calls, got {calls}"
        assert warns == [], f"D: unexpected warnings {warns}"

        # E. 연결 오류 세 번 → [], 시도 3회, WARN 1건
        ids, calls, sleeps, warns = _run([
            requests.ConnectionError("c1"), requests.ConnectionError("c2"),
            requests.ConnectionError("c3"),
        ])
        assert ids == [] and calls == 3, f"E: ids={ids} calls={calls}"
        assert len(warns) == 1 and "시도 3회" in warns[0], f"E: warnings {warns}"

        # F. 500 한 번 후 성공 → 15개, 시도 2회, 백오프 1번
        ids, calls, sleeps, warns = _run([
            _FakeResponse(500), _FakeResponse(200, xml_content),
        ])
        assert ids == expected_ids and calls == 2, f"F: ids={len(ids)} calls={calls}"
        assert sleeps == [1.0], f"F: sleeps {sleeps}"

        # G. 파싱 실패(200 + 깨진 XML) → 재시도 없이 1회, [] (WARN 은 _parse_rss 의 파싱 경고)
        ids, calls, sleeps, warns = _run([_FakeResponse(200, "<feed><broken")])
        assert ids == [] and calls == 1, f"G: ids={ids} calls={calls}"
        assert sleeps == [], f"G: unexpected sleeps {sleeps}"
        assert not any("Failed to fetch" in w for w in warns), f"G: warnings {warns}"

        # H. 지속 실패 휴지 · WARN 간격 · 복구 알림 (가짜 시계)
        _STATE.clear()
        cap = _Cap()
        logger.addHandler(cap)
        logger.setLevel(logging.DEBUG)
        saved_sleep, saved_clock = globals()["_sleep"], globals()["_clock"]
        clk = [100000.0]
        globals()["_sleep"], globals()["_clock"] = (lambda s: None), (lambda: clk[0])
        try:
            sess = _FakeSession([_FakeResponse(404)] * 3)
            assert fetch_rss_video_ids("UCh", session=sess) == [] and sess.calls == 3, "H1: 첫 실패는 3회 시도"
            clk[0] += 300
            assert fetch_rss_video_ids("UCh", session=sess) == [] and sess.calls == 3, "H2: 휴지(10분) 중에는 요청하지 않음"
            clk[0] += 400  # 휴지 끝
            sess.script += [_FakeResponse(404)] * 3
            fetch_rss_video_ids("UCh", session=sess)
            assert sess.calls == 6 and _STATE["UCh"]["streak"] == 2, "H3: 휴지가 끝나면 다시 시도, 연속 실패 2"
            w = [r.getMessage() for r in cap.records if r.levelno == logging.WARNING]
            assert len(w) == 1, f"H4: 1시간 안에는 WARN 한 번만: {w}"
            clk[0] += 1900
            sess.script += [_FakeResponse(200, xml_content)]
            assert fetch_rss_video_ids("UCh", session=sess) == expected_ids and "UCh" not in _STATE, "H5: 휴지 끝난 뒤 성공 → 상태 해제"
            infos = [r.getMessage() for r in cap.records if r.levelno == logging.INFO]
            assert len(infos) == 1 and "복구" in infos[0], f"H6: 복구 INFO 한 번: {infos}"
        finally:
            globals()["_sleep"], globals()["_clock"] = saved_sleep, saved_clock
            logger.removeHandler(cap)
            _STATE.clear()

        # I. 시차 폴링 격자: 6채널이 격자 앞 6~1분에 매분 하나씩, 끝 채널은 격자 1분 전
        g = 1_000_200  # 600 의 배수
        slots = [next_slot(g - 400, i, 6) - g for i in range(6)]
        assert slots == [-360, -300, -240, -180, -120, -60], f"I1: {slots}"
        assert next_slot(g - 59, 5, 6) - g == 540, "I2: 지난 슬롯은 다음 주기로"
        assert len({round(s) for s in slots}) == 6, "I3: 채널마다 시각이 다름"

        # J. 폴러가 켜져 있으면 fetch_all 은 캐시만 읽고 네트워크를 쓰지 않는다
        _CACHE.clear()
        _CACHE["UCj1"] = {"text": xml_content, "at": 0}
        globals()["_POLLER_ON"] = True
        try:
            class _NoNet:
                def get(self, *a, **k):
                    raise AssertionError("폴러 모드에서 틱이 네트워크를 호출함")
            saved = requests.Session
            requests.Session = _NoNet  # type: ignore[assignment,misc]
            try:
                out = fetch_all_rss_video_ids({"a": "UCj1", "b": "UCj2"})
            finally:
                requests.Session = saved
            assert out["a"] == expected_ids and out["b"] == [], f"J: {out}"
        finally:
            globals()["_POLLER_ON"] = False
            _CACHE.clear()

        print("SUCCESS: RSS retry test passed")

    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)
