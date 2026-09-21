"""(v3.8.2) DB 관제소 — `data` 저장소(GitHub Contents API) 접근을 한 줄로 세우는 얇은 관문.

제어 채널(`mewtype-telegram`)과 백엔드(`mewtype-backend`) 모두 `data` 저장소를 직접 두드리지 않고
관제소 서비스(`mewtype-db-tower`, `tower_app.py`)로 요청을 보낸다. 관제소는:

  1. **FIFO** — 도착한 순서대로 한 번에 하나씩 GitHub 를 호출한다(GitHub 문서: secondary rate limit 을
     피하려면 요청을 동시가 아니라 직렬로 보내고 큐를 두라).
  2. **쓰기 간격** — 쓰기(PUT) 사이에 최소 `WRITE_GAP_SEC`(1초) 를 둔다(같은 문서 권고).
  3. **속도 제한 대기** — 403/429(`RateLimitError`) 를 만나면 `retry-after` 만큼 큐 전체를 멈춘다.
     없으면 문서 권고대로 1분부터 지수 백오프. 재시도는 `MAX_RETRIES` 회까지.
  4. **대기 상한** — 요청마다 `budget` 초(호출자 타임아웃 안쪽)를 받아, 줄서기+대기가 그걸 넘으면
     `TowerBusy(retry_after)` — 서비스는 503 + `Retry-After` 로 돌려주고 호출자가 판단한다.
  5. **읽기 ETag 캐시** — 안 바뀐 파일은 조건부 요청(304)으로 읽는다(304 는 primary 한도에 안 세어짐).

트랜잭션(읽기→병합→쓰기 한 덩어리)의 직렬화는 이 모듈의 일이 아니다 — 백엔드 `/write` 잡이 그대로
맡는다(`writers.py`). 관제소는 **개별 GitHub 호출**의 순서·속도만 다룬다.

상태(큐·쿨다운·ETag 캐시)는 프로세스 메모리에만 있다. 서비스는 scale-to-zero 라 꺼지면 사라지지만,
다시 켜진 뒤 첫 요청이 429 를 받으면 `retry-after` 를 새로 배우므로 정확성엔 영향이 없다(낭비 1회).
FIFO 가 성립하려면 인스턴스가 하나여야 한다(`--max-instances=1`).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

from .gh_store import ConflictError, GitHubStore, RateLimitError

log = logging.getLogger("backend.tower")

WRITE_GAP_SEC = 1.0        # 쓰기 사이 최소 간격 (GitHub 문서: 쓰기가 많으면 ≥1초)
DEFAULT_BUDGET_SEC = 25.0  # 호출자가 budget 을 안 주면 — 줄서기+대기 상한
MAX_RETRIES = 3            # 속도 제한 재시도 횟수
BACKOFF_BASE_SEC = 60.0    # retry-after 가 없을 때: 1분, 2분, 4분 (GitHub 문서: 1분 이상 + 지수)


class TowerBusy(RuntimeError):
    """대기 상한 안에 처리할 수 없다 — 호출자는 `retry_after` 초 뒤에 다시 시도하면 된다."""

    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = max(1.0, float(retry_after))


def safe_data_path(path: Any) -> bool:
    """data 저장소 안의 상대 경로만 허용 (빈 값·절대경로·`..`·역슬래시 거부)."""
    return (isinstance(path, str) and bool(path) and len(path) <= 200
            and not path.startswith("/") and "\\" not in path
            and ".." not in path.split("/"))


class _Fifo:
    """도착 순서대로 한 번에 하나만 통과시키는 문 (threading.Lock 은 순서를 보장하지 않는다)."""

    def __init__(self, clock: Callable[[], float]):
        self._cv = threading.Condition()
        self._q: deque = deque()
        self._busy = False
        self._clock = clock

    def enter(self, deadline: float) -> None:
        ticket = object()
        with self._cv:
            self._q.append(ticket)
            while not (self._q[0] is ticket and not self._busy):
                remaining = deadline - self._clock()
                if remaining <= 0:
                    self._q.remove(ticket)
                    self._cv.notify_all()
                    raise TowerBusy("관제소 대기열이 길어 상한 안에 차례가 오지 않음", retry_after=max(2.0, 2.0 * len(self._q)))
                self._cv.wait(timeout=remaining)
            self._q.popleft()
            self._busy = True

    def leave(self) -> None:
        with self._cv:
            self._busy = False
            self._cv.notify_all()

    def depth(self) -> int:
        with self._cv:
            return len(self._q) + (1 if self._busy else 0)


class Tower:
    """GitHubStore 위에 FIFO·간격·속도제한 대기를 얹은 관문. 스레드 안전.

    Args:
        gh: 실제 GitHub 호출을 하는 `GitHubStore` (`etag_cache` 를 켜 두면 읽기가 304 를 쓴다).
        clock/sleep: 테스트 주입용.
    """

    def __init__(self, gh: GitHubStore, *, write_gap: float = WRITE_GAP_SEC,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 max_retries: int = MAX_RETRIES, backoff_base: float = BACKOFF_BASE_SEC):
        self.gh = gh
        self.write_gap = write_gap
        self.clock = clock
        self.sleep = sleep
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._fifo = _Fifo(clock)
        self._cooldown_until = 0.0     # 속도 제한 해제 예정 시각(clock 기준). 큐 전체가 따른다.
        self._last_write_end = -1e9

    # ── 공개 API ──
    def read_json(self, path: str, *, budget: float = DEFAULT_BUDGET_SEC):
        return self._run(lambda: self.gh.read_json(path), write=False, budget=budget)

    def read_text(self, path: str, *, budget: float = DEFAULT_BUDGET_SEC):
        return self._run(lambda: self.gh.read_text(path), write=False, budget=budget)

    def write_json(self, path: str, data: dict, *, prev_sha: Optional[str], message: str,
                   budget: float = DEFAULT_BUDGET_SEC):
        return self._run(lambda: self.gh.write_json(path, data, prev_sha=prev_sha, message=message),
                         write=True, budget=budget)

    def write_text(self, path: str, text: str, *, prev_sha: Optional[str] = None, message: str,
                   budget: float = DEFAULT_BUDGET_SEC):
        return self._run(lambda: self.gh.write_text(path, text, prev_sha=prev_sha, message=message),
                         write=True, budget=budget)

    def status(self) -> dict:
        """헬스·디버그용: 대기열 길이와 남은 쿨다운(초)."""
        return {"depth": self._fifo.depth(),
                "cooldown_sec": round(max(0.0, self._cooldown_until - self.clock()), 1)}

    # ── 내부 ──
    def _run(self, fn: Callable[[], Any], *, write: bool, budget: float):
        deadline = self.clock() + max(0.0, budget)
        self._fifo.enter(deadline)           # 줄서기 (TowerBusy 가능)
        try:
            retries = 0
            while True:
                self._wait_until_ok(write, deadline)
                try:
                    result = fn()
                except RateLimitError as e:
                    retries += 1
                    wait = e.retry_after if e.retry_after is not None else self.backoff_base * (2 ** (retries - 1))
                    self._cooldown_until = max(self._cooldown_until, self.clock() + wait)
                    log.warning("GitHub 속도 제한(%s) — %.1f초 대기 (재시도 %d/%d)", e.status, wait, retries, self.max_retries)
                    if retries > self.max_retries:
                        raise TowerBusy(f"속도 제한이 계속됨: {e}", retry_after=wait)
                    continue                 # 다음 반복의 _wait_until_ok 가 쿨다운(≤ 상한) 을 기다림
                if write:
                    self._last_write_end = self.clock()
                return result
        finally:
            self._fifo.leave()

    def _wait_until_ok(self, write: bool, deadline: float) -> None:
        """쿨다운·쓰기 간격이 끝날 때까지 기다리되, 상한(deadline) 을 넘으면 TowerBusy."""
        now = self.clock()
        need = max(0.0, self._cooldown_until - now)
        if write:
            need = max(need, self.write_gap - (now - self._last_write_end))
        if need <= 0:
            return
        if now + need > deadline:
            raise TowerBusy(f"대기 필요 {need:.0f}초가 상한을 넘음", retry_after=need)
        self.sleep(need)


if __name__ == "__main__":
    import base64
    import json as _json
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # ── 가짜 GitHub (Contents API) ──
    class _Resp:
        def __init__(self, code, payload=None, headers=None, text=""):
            self.status_code, self.reason, self.text = code, "x", text
            self._p, self.headers = payload or {}, headers or {}

        def json(self):
            return self._p

    class FakeSess:
        """files: path→(text, sha). script: 앞으로 돌려줄 강제 응답 큐(속도 제한 등)."""

        def __init__(self):
            self.files, self.script, self.log = {}, [], []
            self.lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def _enter(self):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.01)  # 동시 호출이 있으면 겹치도록 잠깐 머문다

        def _leave(self):
            with self.lock:
                self.active -= 1

        def get(self, url, **kw):
            self._enter()
            try:
                path = url.split("/contents/")[1]
                self.log.append(("GET", path, time.monotonic()))
                if self.script:
                    return self.script.pop(0)
                inm = kw["headers"].get("If-None-Match")
                if path not in self.files:
                    return _Resp(404)
                text, sha = self.files[path]
                if inm == f'"{sha}"':
                    return _Resp(304)
                return _Resp(200, {"content": base64.b64encode(text.encode()).decode(), "sha": sha}, {"etag": f'"{sha}"'})
            finally:
                self._leave()

        def put(self, url, **kw):
            self._enter()
            try:
                path = url.split("/contents/")[1]
                self.log.append(("PUT", path, time.monotonic()))
                if self.script:
                    return self.script.pop(0)
                cur = self.files.get(path)
                if cur and kw["json"].get("sha") != cur[1]:
                    return _Resp(409)
                text = base64.b64decode(kw["json"]["content"]).decode()
                sha = f"s{len(self.log)}"
                self.files[path] = (text, sha)
                return _Resp(200, {"content": {"sha": sha}})
            finally:
                self._leave()

    def mk(**kw):
        sess = FakeSess()
        gh = GitHubStore("t", "o/r", "data", session=sess, etag_cache={})
        return Tower(gh, **kw), sess

    # 1) 경로 검증
    assert safe_data_path("preview.json") and safe_data_path("monitoring/events-2026-09-21.jsonl")
    for bad in ("../x", "/etc", "a" + chr(92) + "b", "", "a/../b", None, 5):
        assert not safe_data_path(bad), bad
    print("[PASS] safe_data_path")

    # 2) FIFO — 도착 순서대로 처리, GitHub 호출은 절대 동시에 둘이 아님
    tw, sess = mk(write_gap=0.0)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    order, ths = [], []

    def worker(i):
        time.sleep(0.02 * i)                       # 도착 순서를 i 순으로 고정
        tw.read_json("a.json")
        order.append(i)
    for i in range(8):
        t = threading.Thread(target=worker, args=(i,)); ths.append(t); t.start()
    for t in ths:
        t.join()
    assert order == list(range(8)), order
    assert sess.max_active == 1, sess.max_active
    print("[PASS] FIFO 순서 + GitHub 동시 호출 0 (max_active=1)")

    # 3) 쓰기 간격 ≥ write_gap
    tw, sess = mk(write_gap=0.3)
    tw.write_json("x.json", {"a": 1}, prev_sha=None, message="m")
    tw.write_json("y.json", {"a": 2}, prev_sha=None, message="m")
    puts = [t for (m, p, t) in sess.log if m == "PUT"]
    assert len(puts) == 2 and puts[1] - puts[0] >= 0.28, puts
    print("[PASS] 쓰기 간 최소 간격")

    # 4) 속도 제한: retry-after 만큼 기다렸다가 성공, 그 사이 큐 전체가 정지
    tw, sess = mk(write_gap=0.0)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    sess.script = [_Resp(429, headers={"retry-after": "0.4"}, text="limit")]
    t0 = time.monotonic()
    data, sha = tw.read_json("a.json", budget=5)
    dt = time.monotonic() - t0
    assert data == {"n": 1} and dt >= 0.38, (data, dt)
    tw.read_json("a.json", budget=5)
    print("[PASS] 429 retry-after 대기 후 성공 (%.2f초)" % dt)

    # 5) 쿨다운은 뒤 요청도 따른다 (뒤 요청이 GitHub 를 두드리지 않음)
    tw, sess = mk(write_gap=0.0)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    sess.script = [_Resp(429, headers={"retry-after": "0.5"})]
    res, stamps = [], {}

    def first():
        tw.read_json("a.json", budget=5); res.append("first")

    def second():
        time.sleep(0.1)
        tw.read_json("a.json", budget=5); res.append("second")
        stamps["second_at"] = time.monotonic()
    t1 = threading.Thread(target=first); t2 = threading.Thread(target=second)
    t0 = time.monotonic(); t1.start(); t2.start(); t1.join(); t2.join()
    gets_during_cooldown = [t for (m, p, t) in sess.log if m == "GET" and t0 + 0.05 < t < t0 + 0.45]
    assert res == ["first", "second"], res                      # FIFO 유지
    assert not gets_during_cooldown, gets_during_cooldown       # 쿨다운 중 GitHub 호출 없음
    print("[PASS] 쿨다운 중 큐 전체 정지 (호출 0건), 순서 유지")

    # 6) 대기 상한 초과 → TowerBusy(retry_after)
    tw, sess = mk(write_gap=0.0)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    sess.script = [_Resp(429, headers={"retry-after": "30"})]
    try:
        tw.read_json("a.json", budget=1)
        raise AssertionError("TowerBusy 여야 함")
    except TowerBusy as e:
        assert 29 <= e.retry_after <= 31, e.retry_after
    print("[PASS] retry-after 30초 > 상한 1초 → TowerBusy(retry_after≈30)")

    # 7) retry-after 없으면 1분 백오프 (상한 안이면 기다림 — 여기선 base 를 줄여 검증)
    tw, sess = mk(write_gap=0.0, backoff_base=0.2)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    sess.script = [_Resp(403, text="You have exceeded a secondary rate limit.")]
    t0 = time.monotonic()
    tw.read_json("a.json", budget=5)
    assert time.monotonic() - t0 >= 0.18
    print("[PASS] retry-after 없음 → 지수 백오프 기본값 적용")

    # 8) 재시도 횟수 초과 → TowerBusy
    tw, sess = mk(write_gap=0.0, max_retries=2, backoff_base=0.05)
    sess.script = [_Resp(429, headers={"retry-after": "0.05"}) for _ in range(5)]
    try:
        tw.read_json("a.json", budget=5)
        raise AssertionError("TowerBusy 여야 함")
    except TowerBusy:
        pass
    print("[PASS] 재시도 횟수 초과 → TowerBusy")

    # 9) 줄서기 자체가 상한을 넘으면 TowerBusy (앞 요청이 오래 잡고 있을 때)
    tw, sess = mk(write_gap=0.0)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    slow = threading.Event()
    real_get = sess.get

    def slow_get(url, **kw):
        slow.wait(1.0)
        return real_get(url, **kw)
    sess.get = slow_get
    th = threading.Thread(target=lambda: tw.read_json("a.json", budget=5)); th.start()
    time.sleep(0.05)
    try:
        tw.read_json("a.json", budget=0.2)
        raise AssertionError("TowerBusy 여야 함")
    except TowerBusy:
        pass
    slow.set(); th.join()
    print("[PASS] 앞 요청이 길어 줄서기 상한 초과 → TowerBusy")

    # 10) ETag 캐시: 두 번째 읽기는 304
    tw, sess = mk(write_gap=0.0)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    assert tw.read_json("a.json")[0] == {"n": 1}
    assert tw.read_json("a.json")[0] == {"n": 1}
    assert tw.gh.etag_cache, "etag 캐시가 채워져야 함"
    print("[PASS] 읽기 ETag 캐시")

    # 11) ConflictError 는 그대로 전달 (재시도·삼킴 없음)
    tw, sess = mk(write_gap=0.0)
    sess.files["c.json"] = (_json.dumps({"v": 1}), "cur")
    try:
        tw.write_json("c.json", {"v": 2}, prev_sha="stale", message="m")
        raise AssertionError("ConflictError 여야 함")
    except ConflictError:
        pass
    print("[PASS] sha 충돌은 ConflictError 로 전달")
    print("SUCCESS: tower self-test 통과")
