"""(v3.8.2) DB 관제소 — `data` 저장소(GitHub Contents API) 접근을 한 줄로 세우는 얇은 관문.

제어 채널(`mewtype-telegram`)과 백엔드(`mewtype-backend`) 모두 `data` 저장소를 직접 두드리지 않고
관제소 서비스(`mewtype-db-tower`, `tower_app.py`)로 요청을 보낸다. 관제소는:

  1. **FIFO + 쓰기 방벽** — 도착한 순서를 지킨다. 읽기끼리는 함께(최대 `MAX_READERS`) 통과하지만 **쓰기는
     방벽**이다: 앞선 읽기가 모두 끝나야 진입하고, 진행 중엔 뒤에 온 요청이 (읽기라도) 앞지르지 못한다.
     그래서 "읽기 도중 데이터가 바뀌는" 일이 없고 결과가 도착 순서를 반영한다(GitHub 문서: 쓰기를 직렬로 큐잉).
     쓰기끼리는 항상 한 번에 하나.
  2. **쓰기 간격** — 쓰기(PUT) 사이에 최소 `WRITE_GAP_SEC`(0.3초) 를 둔다. GitHub 문서 권고는 쓰기가 많을 때 ≥1초지만
     짧은 버스트에선 지연 비용이 커서(시뮬레이션: 1초=관제소 없는 경로의 약 2배, 0.3초=+10%) 낮췄다 — 한도 초과는 3번의
     속도 제한 대기가 안전망. `TOWER_WRITE_GAP_SEC` 로 재배포 없이 조정.
  3. **속도 제한 대기** — 403/429(`RateLimitError`) 를 만나면 `retry-after` 만큼 큐 전체를 멈춘다.
     없으면 문서 권고대로 1분부터 지수 백오프. 재시도는 `MAX_RETRIES` 회까지.
  4. **대기 상한** — 요청마다 `budget` 초(호출자 타임아웃 안쪽)를 받아, 줄서기+대기가 그걸 넘으면
     `TowerBusy(retry_after)` — 서비스는 503 + `Retry-After` 로 돌려주고 호출자가 판단한다.
  5. **읽기 ETag 캐시** — 안 바뀐 파일은 조건부 요청(304)으로 읽는다(304 는 primary 한도에 안 세어짐).

트랜잭션(읽기→병합→쓰기 한 덩어리)의 직렬화는 이 모듈의 일이 아니다 — 백엔드 `/write` 잡이 그대로
맡는다(`writers.py`). 관제소는 **개별 GitHub 호출**의 순서·속도만 다룬다.

상태(큐·쿨다운·ETag 캐시)는 프로세스 메모리에만 있다. 서비스는 scale-to-zero 라 꺼지면 사라지지만,
다시 켜진 뒤 첫 요청이 429 를 받으면 `retry-after` 를 새로 배우므로 정확성엔 영향이 없다(낭비 1회).
순서·방벽이 성립하려면 인스턴스가 하나여야 한다(`--max-instances=1`).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

from .gh_store import ConflictError, GitHubStore, RateLimitError

log = logging.getLogger("backend.tower")

WRITE_GAP_SEC = 0.3        # 쓰기 사이 최소 간격 (GitHub 문서 권고는 ≥1초[쓰기가 많을 때] — 버스트 지연 때문에 0.3 으로 낮춤)
DEFAULT_BUDGET_SEC = 25.0  # 호출자가 budget 을 안 주면 — 줄서기+대기 상한
MAX_READERS = 6           # 동시에 통과시키는 읽기 최대 수 (쓰기는 항상 1)
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


class _RwGate:
    """도착 순서(FIFO)를 지키되 읽기끼리는 함께 통과시키는 문 — 쓰기는 방벽(barrier).

    · 읽기: 쓰기가 진행 중이지 않고 읽기 수 < max_readers 이며 **큐의 맨 앞**일 때 진입.
    · 쓰기: 진행 중인 읽기·쓰기가 없고 **큐의 맨 앞**일 때 진입 → 앞선 읽기가 끝날 때까지 기다림.
    큐 맨 앞만 진입할 수 있으므로 쓰기 뒤에 온 읽기는 쓰기를 앞지르지 못한다.
    """

    def __init__(self, clock: Callable[[], float], max_readers: int, trace: Optional[list] = None):
        self._cv = threading.Condition()
        self._q: deque = deque()          # (ticket, is_write)
        self._readers = 0
        self._writer = False
        self._max_readers = max(1, int(max_readers))
        self._clock = clock
        self.arrivals = 0                 # 지금까지 줄에 선 요청 수 (도착 번호 = arrivals-1). 테스트가 도착 순서를 고정하는 데 씀
        self._trace = trace               # 주어지면 진입 시 (도착 번호, 쓰기?, 진입 직전 읽기 수, 진입 직전 쓰기 중?) 를 기록

    def _can_go(self, ticket: object, is_write: bool) -> bool:
        if self._q[0][0] is not ticket:
            return False
        if is_write:
            return self._readers == 0 and not self._writer
        return (not self._writer) and self._readers < self._max_readers

    def enter(self, is_write: bool, deadline: float) -> None:
        with self._cv:
            seq = self.arrivals
            self.arrivals += 1
            item = (object(), is_write)
            self._q.append(item)
            while not self._can_go(item[0], is_write):
                remaining = deadline - self._clock()
                if remaining <= 0:
                    self._q.remove(item)
                    self._cv.notify_all()
                    raise TowerBusy("관제소 대기열이 길어 상한 안에 차례가 오지 않음",
                                    retry_after=max(2.0, 2.0 * len(self._q)))
                self._cv.wait(timeout=remaining)
            self._q.popleft()
            if self._trace is not None:
                self._trace.append((seq, is_write, self._readers, self._writer))
            if is_write:
                self._writer = True
            else:
                self._readers += 1
            self._cv.notify_all()          # 다음 머리(연속된 읽기) 가 이어서 진입할 수 있게

    def leave(self, is_write: bool) -> None:
        with self._cv:
            if is_write:
                self._writer = False
            else:
                self._readers -= 1
            self._cv.notify_all()

    def depth(self) -> int:
        with self._cv:
            return len(self._q) + self._readers + (1 if self._writer else 0)


class Tower:
    """GitHubStore 위에 FIFO·간격·속도제한 대기를 얹은 관문. 스레드 안전.

    Args:
        gh: 실제 GitHub 호출을 하는 `GitHubStore` (`etag_cache` 를 켜 두면 읽기가 304 를 쓴다).
        clock/sleep: 테스트 주입용.
    """

    def __init__(self, gh: GitHubStore, *, write_gap: float = WRITE_GAP_SEC,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 max_retries: int = MAX_RETRIES, backoff_base: float = BACKOFF_BASE_SEC,
                 max_readers: int = MAX_READERS, trace: Optional[list] = None):
        self.gh = gh
        self.write_gap = write_gap
        self.clock = clock
        self.sleep = sleep
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._gate = _RwGate(clock, max_readers, trace)
        self._state = threading.Lock()  # _cooldown_until·_last_write_end 갱신 (읽기가 동시에 실행되므로)
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
        return {"depth": self._gate.depth(),
                "cooldown_sec": round(max(0.0, self._cooldown_until - self.clock()), 1)}

    # ── 내부 ──
    def _run(self, fn: Callable[[], Any], *, write: bool, budget: float):
        deadline = self.clock() + max(0.0, budget)
        self._gate.enter(write, deadline)    # 줄서기 (TowerBusy 가능). 쓰기는 방벽, 읽기는 병렬
        try:
            retries = 0
            while True:
                self._wait_until_ok(write, deadline)
                try:
                    result = fn()
                except RateLimitError as e:
                    retries += 1
                    wait = e.retry_after if e.retry_after is not None else self.backoff_base * (2 ** (retries - 1))
                    with self._state:
                        self._cooldown_until = max(self._cooldown_until, self.clock() + wait)
                    log.warning("GitHub 속도 제한(%s) — %.1f초 대기 (재시도 %d/%d)", e.status, wait, retries, self.max_retries)
                    if retries > self.max_retries:
                        raise TowerBusy(f"속도 제한이 계속됨: {e}", retry_after=wait)
                    continue                 # 다음 반복의 _wait_until_ok 가 쿨다운(≤ 상한) 을 기다림
                if write:
                    with self._state:
                        self._last_write_end = self.clock()
                return result
        finally:
            self._gate.leave(write)

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

    class SlowSess(FakeSess):
        """읽기/쓰기 지연을 늘려 겹침을 관찰하기 쉽게 한 가짜. 지연 **전 구간** 의 겹침을 센다."""

        def __init__(self, rd=0.15, wr=0.15):
            super().__init__()
            self.rd, self.wr, self.spans = rd, wr, []
            self.r_now = self.w_now = self.r_max = self.w_max = 0
            self.rw_overlap = 0           # 읽기와 쓰기가 동시에 진행된 횟수 (방벽이면 0)
            self._c = threading.Lock()

        def get(self, url, **kw):
            t0 = time.monotonic()
            with self._c:
                self.r_now += 1
                self.r_max = max(self.r_max, self.r_now)
                if self.w_now:
                    self.rw_overlap += 1
            try:
                time.sleep(self.rd)
                r = super().get(url, **kw)
            finally:
                with self._c:
                    self.r_now -= 1
            self.spans.append(("R", t0, time.monotonic(), url.split("/contents/")[1]))
            return r

        def put(self, url, **kw):
            t0 = time.monotonic()
            with self._c:
                self.w_now += 1
                self.w_max = max(self.w_max, self.w_now)
                if self.r_now:
                    self.rw_overlap += 1
            try:
                time.sleep(self.wr)
                r = super().put(url, **kw)
            finally:
                with self._c:
                    self.w_now -= 1
            self.spans.append(("W", t0, time.monotonic(), url.split("/contents/")[1]))
            return r

    def start_in_order(tw, fns):
        """fns 를 하나씩 스레드로 띄우되, 각 스레드가 대기열에 **도착한 것을 확인한 뒤** 다음을 띄운다
        (sleep 으로 도착 순서를 맞추면 CPU 가 바쁠 때 뒤바뀐다). 반환: 스레드 목록."""
        ths = []
        for k, fn in enumerate(fns):
            t = threading.Thread(target=fn)
            t.start()
            ths.append(t)
            deadline = time.monotonic() + 10
            while tw._gate.arrivals < k + 1:
                assert time.monotonic() < deadline, "스레드가 대기열에 도착하지 못함"
                time.sleep(0.001)
        return ths

    def mk_slow(**kw):
        sess = SlowSess()
        gh = GitHubStore("t", "o/r", "data", session=sess, etag_cache={})
        return Tower(gh, **kw), sess

    # 1) 경로 검증
    assert safe_data_path("preview.json") and safe_data_path("monitoring/events-2026-09-21.jsonl")
    for bad in ("../x", "/etc", "a" + chr(92) + "b", "", "a/../b", None, 5):
        assert not safe_data_path(bad), bad
    print("[PASS] safe_data_path")

    # 2a) max_readers=1 이면 읽기도 도착 순서대로 한 줄 — 진입 순서가 도착 순서와 같고, GitHub 동시 호출은 1
    trace = []
    tw, sess = mk_slow(write_gap=0.0, max_readers=1, trace=trace)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    ths = start_in_order(tw, [(lambda: tw.read_json("a.json")) for _ in range(8)])
    [t.join() for t in ths]
    assert [x[0] for x in trace] == list(range(8)), trace
    assert sess.r_max == 1, sess.r_max
    print("[PASS] max_readers=1: 진입 순서 = 도착 순서, GitHub 동시 읽기 1")

    # 2b) 읽기끼리는 병렬 (상한 max_readers) — 겹침 수로 판정: 상한을 넘지 않고, 실제로 겹쳤다
    tw, sess = mk_slow(write_gap=0.0, max_readers=3)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    ths = [threading.Thread(target=lambda: tw.read_json("a.json")) for _ in range(9)]
    [t.start() for t in ths]; [t.join() for t in ths]
    assert sess.r_max <= 3, sess.r_max
    assert sess.r_max >= 2, sess.r_max
    print("[PASS] 읽기 병렬: 동시 읽기 최대 %d (상한 3, 직렬이면 1)" % sess.r_max)

    # 2c) 쓰기 방벽 — 읽기 3 → 쓰기 → 읽기 3 (도착 순서 고정). 쓰기는 앞선 읽기가 끝나야 진입하고, 쓰기와 겹치는 읽기는 0
    trace = []
    tw, sess = mk_slow(write_gap=0.0, max_readers=4, trace=trace)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    rd = lambda: tw.read_json("a.json")
    wr = lambda: tw.write_json("w.json", {"x": 1}, prev_sha=None, message="m")
    ths = start_in_order(tw, [rd, rd, rd, wr, rd, rd, rd])
    [t.join() for t in ths]
    assert sess.rw_overlap == 0, ("읽기와 쓰기가 겹침", sess.rw_overlap)
    assert [x[0] for x in trace] == list(range(7)), trace                      # 진입 순서 = 도착 순서
    w_entry = [x for x in trace if x[1]][0]
    assert w_entry[2] == 0 and w_entry[3] is False, w_entry                    # 쓰기 진입 시점에 읽기 0·쓰기 없음
    # 쓰기(w.json) 구간 = 내부 sha 조회 GET 시작 ~ PUT 끝. a.json 읽기는 그 구간 밖: 앞 3건은 먼저 끝, 뒤 3건은 나중에 시작
    w_get = [sp for sp in sess.spans if sp[0] == "R" and sp[3] == "w.json"][0]
    w_put = [sp for sp in sess.spans if sp[0] == "W"][0]
    a_reads = [sp for sp in sess.spans if sp[0] == "R" and sp[3] == "a.json"]
    before = [sp for sp in a_reads if sp[2] <= w_get[1] + 0.005]
    after = [sp for sp in a_reads if sp[1] >= w_put[2] - 0.005]
    assert len(a_reads) == 6 and len(before) == 3 and len(after) == 3, (len(before), len(after), len(a_reads))
    print("[PASS] 쓰기 방벽: 앞선 읽기 3건 종료 후 쓰기, 읽기-쓰기 겹침 0, 뒤 읽기 3건은 쓰기 뒤")

    # 2d) 쓰기끼리는 항상 한 번에 하나
    tw, sess = mk_slow(write_gap=0.0, max_readers=4)
    ths = [threading.Thread(target=lambda i=i: tw.write_json(f"w{i}.json", {"i": i}, prev_sha=None, message="m")) for i in range(5)]
    [t.start() for t in ths]; [t.join() for t in ths]
    assert sess.w_max == 1, sess.w_max
    print("[PASS] 쓰기끼리 직렬 (동시 쓰기 최대 1)")

    # 2e) 무작위 부하 — 불변식 검증: 읽기·쓰기 200건을 무작위 지연으로 24개 스레드가 섞어 던진다.
    #     (a) 쓰기는 항상 단독(읽기·다른 쓰기 없음) (b) 읽기는 상한 초과 안 함 (c) 진입 순서 = 도착 순서(FIFO)
    #     (d) 전부 끝남(교착·기아 없음). 시간 단언 없음 — CPU 가 바빠도 성립해야 하는 성질만 본다.
    import random
    rng = random.Random(20260921)
    trace = []
    tw, sess = mk(write_gap=0.0, max_readers=4, trace=trace)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    box = {"r": 0, "w": 0, "viol": [], "done": 0}
    bl = threading.Lock()
    gate = tw._gate
    orig_enter, orig_leave = gate.enter, gate.leave

    def enter(is_write, deadline):
        orig_enter(is_write, deadline)
        with bl:
            if is_write:
                if box["r"] or box["w"]:
                    box["viol"].append(("W 진입 시 다른 작업 진행 중", box["r"], box["w"]))
                box["w"] += 1
            else:
                if box["w"]:
                    box["viol"].append(("R 이 쓰기 중 진입",))
                box["r"] += 1
                if box["r"] > 4:
                    box["viol"].append(("R 상한 초과", box["r"]))

    def leave(is_write):
        with bl:
            if is_write:
                box["w"] -= 1
            else:
                box["r"] -= 1
        orig_leave(is_write)
    gate.enter, gate.leave = enter, leave

    def op(i):
        time.sleep(rng.random() * 0.02)
        if rng.random() < 0.3:
            tw.write_json(f"s{i % 7}.json", {"i": i}, prev_sha=None, message="m")
        else:
            tw.read_json("a.json")
        with bl:
            box["done"] += 1
    ths = [threading.Thread(target=op, args=(i,)) for i in range(200)]
    [t.start() for t in ths]
    for t in ths:
        t.join(timeout=60)
    assert box["done"] == 200, ("교착/기아: 끝나지 않음", box["done"])
    assert not box["viol"], box["viol"][:3]
    seqs = [x[0] for x in trace]
    assert seqs == sorted(seqs), "진입 순서가 도착 순서와 다름(FIFO 위반)"
    assert sess.max_active >= 1
    print("[PASS] 무작위 부하 200건: 쓰기 단독·읽기 상한·FIFO·전부 완료 (위반 0, 진입 %d건)" % len(seqs))

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
    # 첫 GET(429 를 받는 요청) 자체는 스레드 시작이 늦어져도 구간 밖이 되도록 0.25초부터, 쿨다운(0.5초) 끝나기 전까지만 본다
    gets_during_cooldown = [t for (m, p, t) in sess.log if m == "GET" and t0 + 0.25 < t < t0 + 0.45]
    assert sorted(res) == ["first", "second"], res              # 둘 다 성공
    assert not gets_during_cooldown, gets_during_cooldown       # 쿨다운 중 GitHub 호출 없음
    print("[PASS] 쿨다운 중 큐 전체 정지 (읽기 병렬이어도 호출 0건)")

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
    tw, sess = mk(write_gap=0.0, max_readers=1)
    sess.files["a.json"] = (_json.dumps({"n": 1}), "s0")
    slow, started = threading.Event(), threading.Event()
    real_get = sess.get

    def slow_get(url, **kw):
        started.set()
        slow.wait(2.0)
        return real_get(url, **kw)
    sess.get = slow_get
    th = threading.Thread(target=lambda: tw.read_json("a.json", budget=5)); th.start()
    assert started.wait(5), "앞 요청이 시작되지 않음"
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
