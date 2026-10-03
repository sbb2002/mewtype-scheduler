"""
(v4a) 로컬 시뮬레이션용 in-process 작업 큐.
프로덕션에서 Cloud Tasks 이 하나씩 전달하는 잡을 단일 워커 스레드로 처리한다.

스펙: ref/v4a/v4a_impl_plan.md §1, §4-2
"""

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger("backend.jobqueue")


class LocalQueue:
    """
    In-process job queue with single daemon worker thread.
    - Enqueue jobs to run one at a time, ordered by run_at (ties FIFO)
    - Retry logic with exponential backoff on handler failure
    - Optional persistence to JSON file
    - Optional name-based deduplication
    """

    def __init__(
        self,
        name: str,
        handler: Callable[[str, dict, dict], dict],
        *,
        persist_path: Optional[str] = None,
        max_attempts: int = 5,
        backoff_sec: tuple = (1, 2, 4, 8, 16),
        on_done: Optional[Callable] = None,
        on_dead: Optional[Callable] = None,
        clock: Callable[[], float] = time.time,
    ):
        """
        큐 생성.

        Args:
            name: 큐 이름 (워커 스레드 이름 q-{name} 에 사용)
            handler: (kind, args, meta) -> dict 콜러블
            persist_path: 미처리 잡 저장 경로 (JSON, 옵션)
            max_attempts: 최대 재시도 횟수
            backoff_sec: 재시도 대기시간 튜플 (attempt-1 인덱스)
            on_done: 성공 콜백 (job_dict, result)
            on_dead: 최종 실패 콜백 (job_dict, exc)
            clock: 시간 함수 (테스트용 주입)
        """
        self.name = name
        self.handler = handler
        self.persist_path = persist_path
        self.max_attempts = max_attempts
        self.backoff_sec = backoff_sec
        self.on_done = on_done
        self.on_dead = on_dead
        self.clock = clock

        # 잡 저장소: {job_id: {id, name, kind, args, run_at, run_at_iso, attempt, created_at}}
        self._jobs: dict[str, dict] = {}

        # Lock 및 조건변수 (워커 대기용)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)

        # 워커 스레드
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # submit_and_wait 호출자 대기용: job_id -> {event, result, exc}
        self._wait_holders: dict[str, dict] = {}

        # 지속화 파일에서 잡 로드
        if self.persist_path and os.path.exists(self.persist_path):
            self._load_jobs()

    def _load_jobs(self) -> None:
        """persist_path 에서 미처리 잡 복원."""
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for job_dict in data:
                    job_id = job_dict["id"]
                    self._jobs[job_id] = job_dict
            logger.info(
                f"Loaded {len(self._jobs)} pending jobs from {self.persist_path}"
            )
        except Exception as e:
            logger.error(f"Failed to load jobs from {self.persist_path}: {e}")

    def _save_jobs(self) -> None:
        """현 미처리 잡을 persist_path 에 원자적으로 저장."""
        if not self.persist_path:
            return
        try:
            os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
            data = list(self._jobs.values())
            # 원자적 쓰기: 임시파일 + replace
            tmp_path = self.persist_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            from .local_store import replace_retry   # (v4a) Windows 권한 오류 짧은 재시도
            replace_retry(tmp_path, self.persist_path)
        except Exception as e:
            logger.error(f"Failed to save jobs to {self.persist_path}: {e}")

    def _parse_iso(self, iso_str: str) -> float:
        """ISO 8601 UTC 문자열 → epoch 초."""
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.timestamp()

    def _iso_now(self) -> str:
        """현재 시각 → ISO 8601 UTC 문자열."""
        dt = datetime.fromtimestamp(self.clock(), tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")

    def start(self) -> None:
        """워커 스레드 시작 (daemon, 이름 = f"q-{self.name}")."""
        with self._lock:
            if self._worker_thread is not None:
                return  # 이미 시작됨
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True, name=f"q-{self.name}"
            )
            self._worker_thread.start()
            logger.info(f"Started worker thread: q-{self.name}")

    def stop(self, timeout: float = 5) -> None:
        """워커 스레드 정지 (graceful shutdown)."""
        with self._lock:
            if self._worker_thread is None:
                return
            self._stop_event.set()
            self._condition.notify_all()

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout)

        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning(
                f"Worker thread q-{self.name} did not stop within {timeout}s"
            )
        else:
            logger.info(f"Stopped worker thread: q-{self.name}")

    def enqueue(
        self,
        kind: str,
        args: dict,
        *,
        run_at_iso: Optional[str] = None,
        name: Optional[str] = None,
        _holder: Optional[dict] = None,
    ) -> str:
        """
        잡 등록.

        - run_at_iso 기본값 = now (ISO 8601 UTC)
        - name 지정 시, 같은 이름의 미처리 잡이 있으면 그 id 반환 (중복 방지)
        - args 가 JSON-serializable 이 아니면 TypeError 발생 (persist_path 설정 시)
        - 즉시 반환, 잡 id 문자열 반환 (12자 hex)
        - _holder: 내부용, submit_and_wait 에서 사용해 race condition 방지
        """
        with self._lock:
            # run_at_iso 기본값
            if run_at_iso is None:
                run_at_iso = self._iso_now()

            # name 중복 확인 (미처리 잡 중에만)
            if name:
                for job_dict in self._jobs.values():
                    if job_dict.get("name") == name:
                        logger.debug(
                            f"Job with name '{name}' already pending, returning existing id {job_dict['id']}"
                        )
                        return job_dict["id"]

            # 새 잡 생성
            job_id = uuid.uuid4().hex[:12]

            # persist_path 설정 시 JSON-serializable 확인
            if self.persist_path:
                try:
                    json.dumps(args, ensure_ascii=False)
                except TypeError as e:
                    raise TypeError(f"args not JSON-serializable: {e}")

            job_dict = {
                "id": job_id,
                "name": name,
                "kind": kind,
                "args": args,
                "run_at": self._parse_iso(run_at_iso),
                "run_at_iso": run_at_iso,
                "attempt": 1,
                "created_at": self._iso_now(),
            }
            self._jobs[job_id] = job_dict

            # submit_and_wait holder 등록 (race condition 방지)
            if _holder is not None:
                self._wait_holders[job_id] = _holder

            # 저장 및 워커 깨우기
            self._save_jobs()
            self._condition.notify_all()

            logger.debug(f"Enqueued job {job_id} (kind={kind}, name={name})")
            return job_id

    def cancel(self, pred) -> list[dict]:
        """(v4a) 아직 실행 전인 잡 중 `pred(job_dict)` 가 참인 것을 지운다. 결과를 기다리는 잡(submit_and_wait)은 건드리지 않는다.
        지운 잡들의 사본을 돌려준다(실행 중인 잡은 이미 목록에서 빠져 있어 대상이 아니다)."""
        with self._lock:
            gone = [j for jid, j in self._jobs.items() if jid not in self._wait_holders and pred(j)]
            for j in gone:
                del self._jobs[j["id"]]
            if gone:
                self._save_jobs()
                self._condition.notify_all()
            return [dict(j) for j in gone]

    def pending(self) -> list[dict]:
        """미처리 잡 스냅샷 (id, name, kind, run_at_iso, attempt)."""
        with self._lock:
            return [
                {
                    "id": j["id"],
                    "name": j["name"],
                    "kind": j["kind"],
                    "run_at_iso": j["run_at_iso"],
                    "attempt": j["attempt"],
                }
                for j in self._jobs.values()
            ]

    def _worker_loop(self) -> None:
        """워커 루프: run_at 순서대로 잡을 처리 (조건변수로 대기)."""
        logger.info(f"Worker {threading.current_thread().name} started")
        try:
            while not self._stop_event.is_set():
                with self._condition:
                    # 다음 잡 선택
                    if not self._jobs:
                        # 잡 없음: stop 또는 새 enqueue 까지 대기
                        self._condition.wait(timeout=1)
                        continue

                    # run_at 순서로 정렬, 첫 번째 반환
                    next_job_id = min(
                        self._jobs.keys(), key=lambda jid: self._jobs[jid]["run_at"]
                    )
                    job_dict = self._jobs[next_job_id]
                    run_at = job_dict["run_at"]
                    now = self.clock()

                    # 아직 실행 시간이 아니면 대기
                    if run_at > now:
                        wait_time = run_at - now
                        self._condition.wait(timeout=wait_time)
                        continue

                    # 잡 제거 (실행 중 중복 enqueue 방지)
                    del self._jobs[next_job_id]

                # 잡 실행 (lock 바깥에서)
                self._execute_job(next_job_id, job_dict)
        except Exception as e:
            logger.exception(f"Worker {threading.current_thread().name} crashed: {e}")

    def _execute_job(self, job_id: str, job_dict: dict) -> None:
        """
        잡 실행.

        - handler 호출 (kind, args, meta)
        - 성공: on_done 콜백 호출 (있으면)
        - 실패: 재시도 또는 on_dead 콜백 호출
        - submit_and_wait 호출자 대기 가능
        """
        kind = job_dict["kind"]
        args = job_dict["args"]
        attempt = job_dict["attempt"]
        is_last = attempt >= self.max_attempts

        meta = {
            "job_id": job_id,
            "name": job_dict.get("name"),
            "attempt": attempt,
            "is_last": is_last,
            "queue": self.name,
        }

        try:
            result = self.handler(kind, args, meta)
            # 성공
            if self.on_done:
                try:
                    self.on_done(job_dict, result)
                except Exception as e:
                    logger.exception(f"on_done callback failed for job {job_id}: {e}")

            # submit_and_wait 호출자 깨우기
            with self._lock:
                if job_id in self._wait_holders:
                    self._wait_holders[job_id]["result"] = result
                    self._wait_holders[job_id]["event"].set()

            logger.info(f"Job {job_id} succeeded on attempt {attempt}")
        except Exception as exc:
            if is_last:
                # 마지막 재시도 실패 → on_dead
                if self.on_dead:
                    try:
                        self.on_dead(job_dict, exc)
                    except Exception as e:
                        logger.exception(f"on_dead callback failed for job {job_id}: {e}")

                # submit_and_wait 호출자 깨우기
                with self._lock:
                    if job_id in self._wait_holders:
                        self._wait_holders[job_id]["exc"] = exc
                        self._wait_holders[job_id]["event"].set()

                logger.error(f"Job {job_id} dead after {attempt} attempts: {exc}")
            else:
                # 재시도 예약
                backoff = self.backoff_sec[
                    min(attempt - 1, len(self.backoff_sec) - 1)
                ]
                next_run_at = self.clock() + backoff
                dt = datetime.fromtimestamp(next_run_at, tz=timezone.utc)
                next_run_at_iso = dt.isoformat().replace("+00:00", "Z")

                with self._lock:
                    job_dict["attempt"] = attempt + 1
                    job_dict["run_at"] = next_run_at
                    job_dict["run_at_iso"] = next_run_at_iso
                    self._jobs[job_id] = job_dict
                    self._save_jobs()
                    self._condition.notify_all()

                logger.warning(
                    f"Job {job_id} failed (attempt {attempt}), "
                    f"retrying in {backoff}s: {exc}"
                )

    def submit_and_wait(
        self, kind: str, args: dict, *, timeout: float = 120
    ) -> dict:
        """
        잡 등록 + 완료 대기.

        - 호출한 스레드가 워커 스레드이면 inline 실행 (deadlock 방지)
        - 그 외: 대기 (timeout 제한)
        - 성공 시 result dict 반환
        - 실패 시 마지막 예외 발생
        - TimeoutError 발생 가능
        """
        # 현 스레드가 워커 스레드인가?
        if threading.current_thread() == self._worker_thread:
            # inline 실행 (deadlock 방지)
            meta = {
                "job_id": "inline",
                "name": None,
                "attempt": 1,
                "is_last": True,  # inline 이므로 재시도 없음
                "queue": self.name,
            }
            result = self.handler(kind, args, meta)
            return result

        # 결과 대기용 holder 사전 생성
        holder = {
            "event": threading.Event(),
            "result": None,
            "exc": None,
        }

        # enqueue 시 holder 등록 (race condition 방지)
        job_id = self.enqueue(kind, args, _holder=holder)

        try:
            # 대기
            if not holder["event"].wait(timeout=timeout):
                raise TimeoutError(
                    f"Job {job_id} did not complete within {timeout}s"
                )

            if holder["exc"]:
                raise holder["exc"]

            return holder["result"]
        finally:
            with self._lock:
                self._wait_holders.pop(job_id, None)


# Self-test
if __name__ == "__main__":
    import tempfile

    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s - %(levelname)s - %(message)s",
    )

    print("=== LocalQueue Self-Test ===\n")

    # Case 1: FIFO 순서
    print("[1] FIFO order of 3 immediate jobs...")
    order = []

    def handler_order(kind, args, meta):
        order.append(args["idx"])
        assert (
            threading.current_thread().name == "q-test"
        ), f"Expected 'q-test', got {threading.current_thread().name}"
        return {"ok": True}

    q = LocalQueue("test", handler_order, clock=time.time, backoff_sec=(0.05,))
    q.start()
    q.enqueue("job", {"idx": 1})
    q.enqueue("job", {"idx": 2})
    q.enqueue("job", {"idx": 3})
    time.sleep(0.5)  # 모두 처리될 때까지
    q.stop()
    assert order == [1, 2, 3], f"Expected [1, 2, 3], got {order}"
    print("[PASS] FIFO order correct, worker thread name verified\n")

    # Case 2: run_at 미래 vs 즉시
    print("[2] Future run_at runs after immediate job...")
    order = []

    def handler_order2(kind, args, meta):
        order.append(args["idx"])
        return {"ok": True}

    q = LocalQueue("test", handler_order2, clock=time.time, backoff_sec=(0.05,))
    q.start()
    future_iso = datetime.fromtimestamp(
        q.clock() + 0.3, tz=timezone.utc
    ).isoformat().replace("+00:00", "Z")
    q.enqueue("job", {"idx": 1}, run_at_iso=future_iso)  # 나중에
    time.sleep(0.1)
    q.enqueue("job", {"idx": 2})  # 지금
    time.sleep(0.5)  # 모두 처리될 때까지
    q.stop()
    assert order == [2, 1], f"Expected [2, 1], got {order}"
    print("[PASS] Future job runs after immediate job\n")

    # Case 3: name 중복
    print("[3] Name dedupe...")
    call_count = [0]
    executed_ids = []

    def handler_dedupe(kind, args, meta):
        call_count[0] += 1
        executed_ids.append(meta["job_id"])
        return {"ok": True}

    q = LocalQueue("test", handler_dedupe, clock=time.time, backoff_sec=(0.05,))
    q.start()
    # Enqueue both jobs quickly before worker has time to start the first one
    id1 = q.enqueue("job", {"data": "x"}, name="my_job")
    id2 = q.enqueue("job", {"data": "y"}, name="my_job")  # 같은 name, 펜딩 중
    assert id1 == id2, f"Expected same id, got {id1} vs {id2}"
    time.sleep(0.3)  # Wait for execution
    q.stop()
    assert call_count[0] == 1, f"Expected 1 execution, got {call_count[0]}"
    print("[PASS] Dedupe works, one execution\n")

    # Case 4: Retry 성공
    print("[4] Retry: fail twice then succeed...")
    attempts_seen = []

    def handler_retry(kind, args, meta):
        attempts_seen.append(meta["attempt"])
        if meta["attempt"] < 3:
            raise ValueError("temp error")
        return {"result": "ok"}

    q = LocalQueue(
        "test",
        handler_retry,
        max_attempts=3,
        clock=time.time,
        backoff_sec=(0.05, 0.05),
    )
    q.start()
    q.enqueue("job", {})
    time.sleep(1.5)  # 충분한 대기
    q.stop()
    assert (
        attempts_seen == [1, 2, 3]
    ), f"Expected [1, 2, 3], got {attempts_seen}"
    print("[PASS] Retry succeeded on 3rd attempt\n")

    # Case 5: Dead (항상 실패)
    print("[5] Dead: always failing...")
    dead_calls = []

    def handler_dead(kind, args, meta):
        raise ValueError("permanent error")

    def on_dead_callback(job_dict, exc):
        dead_calls.append(job_dict["id"])

    q = LocalQueue(
        "test",
        handler_dead,
        max_attempts=2,
        clock=time.time,
        backoff_sec=(0.05,),
        on_dead=on_dead_callback,
    )
    q.start()
    job_id = q.enqueue("job", {})
    time.sleep(0.5)
    q.stop()
    assert len(dead_calls) == 1, f"Expected on_dead called once, got {len(dead_calls)}"
    assert dead_calls[0] == job_id
    print("[PASS] on_dead called for permanently failing job\n")

    # Case 6: submit_and_wait
    print("[6] submit_and_wait returns result...")

    def handler_result(kind, args, meta):
        return {"status": "done", "value": args.get("x", 0) * 2}

    q = LocalQueue("test", handler_result, clock=time.time)
    q.start()
    result = q.submit_and_wait("job", {"x": 5})
    q.stop()
    assert (
        result == {"status": "done", "value": 10}
    ), f"Expected correct result, got {result}"
    print("[PASS] submit_and_wait returns result\n")

    # Case 6b: submit_and_wait exception propagates
    print("[6b] submit_and_wait exception propagates...")

    def handler_exc(kind, args, meta):
        raise RuntimeError("test error")

    q = LocalQueue(
        "test", handler_exc, max_attempts=1, clock=time.time, backoff_sec=(0.05,)
    )
    q.start()
    try:
        q.submit_and_wait("job", {}, timeout=2)
        assert False, "Should have raised"
    except RuntimeError as e:
        assert str(e) == "test error"
    q.stop()
    print("[PASS] Exception propagated\n")

    # Case 6c: submit_and_wait from worker thread (inline)
    print("[6c] submit_and_wait from worker thread runs inline...")

    def handler_inline(kind, args, meta):
        if args.get("recurse"):
            # 워커 스레드에서 submit_and_wait 호출
            result = q.submit_and_wait("nested", {"nested": True})
            return {"outer": result}
        else:
            return {"nested": "done"}

    q = LocalQueue("test", handler_inline, clock=time.time)
    q.start()
    result = q.submit_and_wait("job", {"recurse": True}, timeout=2)
    q.stop()
    assert (
        result == {"outer": {"nested": "done"}}
    ), f"Expected nested result, got {result}"
    print("[PASS] Inline execution from worker thread\n")

    # Case 7: Persistence
    print("[7] Persistence...")
    with tempfile.TemporaryDirectory() as tmpdir:
        persist_file = os.path.join(tmpdir, "queue.json")

        # Enqueue 후 stop (far-future job)
        def dummy_handler(kind, args, meta):
            return {}

        q1 = LocalQueue(
            "test",
            dummy_handler,
            persist_path=persist_file,
            clock=time.time,
            backoff_sec=(0.05,),
        )
        q1.start()
        future_iso = datetime.fromtimestamp(
            q1.clock() + 3600, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
        job_id = q1.enqueue("job", {"data": "persisted"}, run_at_iso=future_iso)
        q1.stop()

        # 새 큐 만들고 로드
        q2 = LocalQueue(
            "test",
            dummy_handler,
            persist_path=persist_file,
            clock=time.time,
            backoff_sec=(0.05,),
        )
        pending = q2.pending()
        assert len(pending) == 1, f"Expected 1 pending job, got {len(pending)}"
        assert pending[0]["id"] == job_id
        q2.start()
        q2.stop()

    print("[PASS] Persistence works\n")

    print("=== All tests passed ===")
