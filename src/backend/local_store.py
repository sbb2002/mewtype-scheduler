"""로컬 파일 저장소. GitHubStore 와 같은 인터페이스로 로컬 디렉터리에 읽고 쓰기."""

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .gh_store import _serialize, ConflictError

logger = logging.getLogger(__name__)


# 글로벌 잠금 — 경로별 잠금을 보호
_lock_dict_lock = threading.Lock()
_lock_dict: dict[str, threading.Lock] = {}


def _get_path_lock(abs_path: str) -> threading.Lock:
    """경로별 잠금을 얻음. 처음이면 생성."""
    with _lock_dict_lock:
        if abs_path not in _lock_dict:
            _lock_dict[abs_path] = threading.Lock()
        return _lock_dict[abs_path]


def _sha1_hex(data: bytes) -> str:
    """데이터의 sha1 hex digest."""
    return hashlib.sha1(data).hexdigest()


def replace_retry(src, dst, *, tries: int = 6, delay: float = 0.05) -> None:
    """(v4a) `os.replace` + Windows 권한 오류 짧은 재시도(최대 약 1.5초).

    Windows 는 다른 스레드 · 프로세스가 대상 파일을 열어 둔 동안(읽기 포함) 교체를 PermissionError(WinError 5 · 32)로
    거절한다(2026-09-30 로컬 러너 실측 — flows.json · recent_jobs.json). 잠깐 뒤 다시 하면 대개 된다.
    끝내 안 되면 마지막 예외를 그대로 던진다(호출부의 기존 실패 처리 그대로)."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(delay * (2 ** i))


class LocalStore:
    """로컬 파일 저장소. GitHubStore 와 같은 인터페이스를 제공하되
    GitHub 대신 로컬 파일시스템에서 읽고 쓴다.

    파일 구조:
        <root>/<branch>/<path>

    모든 쓰기는 원자적(temp → os.replace)이고, .commits.jsonl 에 기록된다.
    """

    def __init__(self, root: str, branch: str):
        """로컬 저장소 초기화.

        Args:
            root: 저장소 루트 디렉터리 경로
            branch: 브랜치 이름 (디렉터리 이름으로 사용)
        """
        self.root = root
        self.branch = branch
        self.repo = "local"
        self.token = ""
        self.session = None
        self.timeout = 0

    def _get_file_path(self, path: str) -> str:
        """논리적 경로를 실제 파일 경로로 변환."""
        return os.path.join(self.root, self.branch, path)

    def read_json(self, path: str) -> tuple[Optional[dict], Optional[str]]:
        """JSON 파일을 읽음.

        Args:
            path: 저장소 내 파일 경로 (예: "schedule.json").

        Returns:
            (data, sha) 튜플:
            - 파일 있으면: (파싱된 dict, sha 문자열)
            - 파일 없으면: (None, None)

        Raises:
            RuntimeError: JSON 파싱 오류, 읽기 오류.
        """
        file_path = self._get_file_path(path)

        if not os.path.exists(file_path):
            return None, None

        try:
            with open(file_path, "rb") as f:
                content_bytes = f.read()
                # JSON 파싱
                text = content_bytes.decode("utf-8")
                data = json.loads(text)
                sha = _sha1_hex(content_bytes)
                return data, sha
        except json.JSONDecodeError as e:
            raise RuntimeError(f"JSON parse error in {path}: {e}")
        except Exception as e:
            raise RuntimeError(f"Error reading {path}: {e}")

    def write_json(
        self,
        path: str,
        data: dict,
        *,
        prev_sha: Optional[str],
        message: str,
    ) -> tuple[bool, str]:
        """JSON 파일을 씀. 내용이 동일하면 쓰지 않음.

        직렬화: _serialize(data) (gh_store 와 동일)

        처리 흐름:
        1. read_json 으로 현재 내용과 sha 조회.
        2. 직렬화 문자열이 동일하면 (False, 현재sha) 반환.
        3. prev_sha 가 주어졌는데 현재 sha 와 다르면 → ConflictError.
        4. 아니면 임시파일 → os.replace 로 원자적 쓰기.
        5. .commits.jsonl 에 기록.

        Args:
            path: 저장소 내 파일 경로.
            data: 저장할 딕셔너리.
            prev_sha: 호출자가 계산을 시작할 때 읽은 sha.
                      None 이면 sha 검사 없이 쓴다.
            message: 커밋 메시지.

        Returns:
            (changed, new_sha) 튜플:
            - (False, 현재sha): 내용이 이미 같음.
            - (True, 새sha): 파일이 업데이트됨.

        Raises:
            ConflictError: base sha 가 어긋남.
            RuntimeError: 기타 오류.
        """
        file_path = self._get_file_path(path)

        # 1. 현재 내용 조회
        current_data, current_sha = self.read_json(path)
        serialized = _serialize(data)
        serialized_bytes = serialized.encode("utf-8")

        # 2. 내용 동일 확인
        if current_data is not None and _serialize(current_data) == serialized:
            return False, current_sha

        # 3. base sha 어긋남 확인
        if (
            prev_sha is not None
            and current_sha is not None
            and current_sha != prev_sha
        ):
            raise ConflictError(
                f"{path}: base sha {prev_sha[:8]} != current {current_sha[:8]} "
                f"(다른 실행이 먼저 커밋함)"
            )

        # 4. 파일 쓰기 (원자적)
        return self._write_file(file_path, serialized_bytes, message, path)

    def read_text(self, path: str) -> tuple[Optional[str], Optional[str]]:
        """텍스트 파일을 읽음. read_json 과 동일하되 JSON 파싱 안 함.

        Args:
            path: 저장소 내 파일 경로.

        Returns:
            (content, sha) 또는 404 면 (None, None).

        Raises:
            RuntimeError: 읽기 오류.
        """
        file_path = self._get_file_path(path)

        if not os.path.exists(file_path):
            return None, None

        try:
            with open(file_path, "rb") as f:
                content_bytes = f.read()
                text = content_bytes.decode("utf-8")
                sha = _sha1_hex(content_bytes)
                return text, sha
        except Exception as e:
            raise RuntimeError(f"Error reading {path}: {e}")

    def write_text(
        self,
        path: str,
        text: str,
        *,
        prev_sha: Optional[str] = None,
        message: str,
    ) -> tuple[bool, str]:
        """텍스트 파일을 씀. write_json 과 동일한 무변화 스킵·낙관적 동시성
        규칙을 따르되, JSON 직렬화는 하지 않고 text 를 그대로 쓴다.

        Args:
            path: 저장소 내 파일 경로.
            text: 저장할 텍스트.
            prev_sha: 호출자가 읽은 sha (기본 None).
            message: 커밋 메시지.

        Returns:
            (changed, new_sha) 튜플.

        Raises:
            ConflictError: base sha 가 어긋남.
            RuntimeError: 기타 오류.
        """
        file_path = self._get_file_path(path)

        # 1. 현재 내용 조회
        current_text, current_sha = self.read_text(path)
        text_bytes = text.encode("utf-8")

        # 2. 내용 동일 확인 (raw text)
        if current_text is not None and current_text == text:
            return False, current_sha

        # 3. base sha 어긋남 확인
        if (
            prev_sha is not None
            and current_sha is not None
            and current_sha != prev_sha
        ):
            raise ConflictError(
                f"{path}: base sha {prev_sha[:8]} != current {current_sha[:8]} "
                f"(다른 실행이 먼저 커밋함)"
            )

        # 4. 파일 쓰기 (원자적)
        return self._write_file(file_path, text_bytes, message, path)

    def _write_file(
        self,
        file_path: str,
        content_bytes: bytes,
        message: str,
        log_path: str,
    ) -> tuple[bool, str]:
        """파일을 원자적으로 씀. 잠금을 사용하고 .commits.jsonl 에 기록.

        Args:
            file_path: 실제 파일 경로.
            content_bytes: 쓸 바이트.
            message: 커밋 메시지.
            log_path: .commits.jsonl 에 기록할 논리적 경로.

        Returns:
            (changed, sha) 튜플. changed=True 이면 .commits.jsonl 에 기록됨.
        """
        abs_path = os.path.abspath(file_path)
        lock = _get_path_lock(abs_path)

        with lock:
            # 최종 확인: 현재 내용이 이미 같을 수 있음 (다른 스레드가 방금 씼을 수도)
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    current_bytes = f.read()
                if current_bytes == content_bytes:
                    sha = _sha1_hex(current_bytes)
                    return False, sha

            # 디렉터리 생성
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # 임시 파일에 쓰기 (같은 디렉터리)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=os.path.dirname(file_path),
                delete=False,
            ) as tmp:
                tmp.write(content_bytes)
                tmp_path = tmp.name

            try:
                # os.replace (원자적, 크로스플랫폼)
                replace_retry(tmp_path, file_path)   # (v4a) Windows 권한 오류 짧은 재시도
                sha = _sha1_hex(content_bytes)

                # .commits.jsonl 에 기록
                self._log_commit(log_path, message, sha)

                return True, sha
            except Exception:
                # 예외 발생 시 임시 파일 제거
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise

    def _log_commit(self, path: str, message: str, sha: str):
        """커밋 기록을 .commits.jsonl 에 추가."""
        log_path = os.path.join(self.root, self.branch, ".commits.jsonl")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # 시간 (UTC ISO Z)
        ts_iso = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

        # 로그 항목
        log_entry = {
            "ts": ts_iso,
            "path": path,
            "message": message,
            "sha": sha,
            "thread": threading.current_thread().name,
        }

        # 로그 파일 자체도 잠금 필요 (경로별 잠금 사용)
        log_lock = _get_path_lock(os.path.abspath(log_path))
        with log_lock:
            with open(log_path, "a", encoding="utf-8", newline="") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def list_dir(self, path: str) -> list[str]:
        """디렉터리의 파일 이름 목록. 하위 디렉터리와 점으로 시작하는 파일은 제외.

        Args:
            path: 저장소 내 디렉터리 경로.

        Returns:
            파일명 리스트 (정렬됨). 디렉터리가 없으면 [].
        """
        dir_path = self._get_file_path(path)

        if not os.path.isdir(dir_path):
            return []

        try:
            items = os.listdir(dir_path)
            # 파일만, 점으로 시작하지 않는 것만
            files = [
                name
                for name in items
                if os.path.isfile(os.path.join(dir_path, name))
                and not name.startswith(".")
            ]
            return sorted(files)
        except Exception:
            return []

    def with_branch(self, branch: str) -> "LocalStore":
        """다른 브랜치를 가진 같은 root 의 store 반환."""
        return LocalStore(self.root, branch)


if __name__ == "__main__":
    import sys
    import threading as _threading

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # Self-test
    test_count = 0
    test_pass = 0

    def assert_test(condition: bool, name: str):
        global test_count, test_pass
        test_count += 1
        if condition:
            test_pass += 1
            print(f"[PASS] {name}")
        else:
            print(f"[FAIL] {name}")
            raise AssertionError(name)

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Using temp directory: {tmpdir}\n")

        # 1. 기본 read_json — 파일 없으면 (None, None)
        store = LocalStore(tmpdir, "data")
        data, sha = store.read_json("missing.json")
        assert_test(data is None and sha is None, "missing read_json returns (None, None)")

        # 2. 첫 쓰기 — changed=True
        test_data = {"a": 1, "b": 2}
        changed, sha = store.write_json(
            "test.json", test_data, prev_sha=None, message="Initial commit"
        )
        assert_test(changed is True, "first write returns changed=True")
        assert_test(len(sha) == 40, "sha is 40-char hex string")

        # 3. 같은 데이터 다시 쓰기 — changed=False, 같은 sha
        changed2, sha2 = store.write_json(
            "test.json", test_data, prev_sha=sha, message="Repeat"
        )
        assert_test(changed2 is False, "same data returns changed=False")
        assert_test(sha2 == sha, "sha unchanged when data same")

        # 4. prev_sha 불일치 — ConflictError
        try:
            store.write_json(
                "test.json",
                {"a": 2},
                prev_sha="deadbeef0000000000000000000000000000dead",
                message="Conflict test",
            )
            assert_test(False, "ConflictError raised on sha mismatch")
        except ConflictError:
            assert_test(True, "ConflictError raised on sha mismatch")

        # 5. prev_sha=None 으로 덮어쓰기 — changed=True
        changed3, sha3 = store.write_json(
            "test.json",
            {"a": 3, "b": 4},
            prev_sha=None,
            message="Overwrite without checking",
        )
        assert_test(changed3 is True, "prev_sha=None allows overwrite")

        # 6. read_text / write_text
        text_content = "Hello\n世界\n"
        changed_t, sha_t = store.write_text(
            "readme.txt", text_content, message="Text file"
        )
        assert_test(changed_t is True, "write_text changed=True on new file")

        text_read, sha_t2 = store.read_text("readme.txt")
        assert_test(text_read == text_content, "read_text returns exact content")
        assert_test(sha_t2 == sha_t, "read_text sha matches write_text sha")

        # 7. write_text 무변화 스킵
        changed_t3, sha_t3 = store.write_text(
            "readme.txt", text_content, message="Repeat"
        )
        assert_test(changed_t3 is False, "write_text skips unchanged")
        assert_test(sha_t3 == sha_t, "sha unchanged")

        # 8. list_dir
        store.write_json("a.json", {"x": 1}, prev_sha=None, message="")
        store.write_json("b.json", {"y": 2}, prev_sha=None, message="")
        os.makedirs(os.path.join(tmpdir, "data", "subdir"), exist_ok=True)
        with open(os.path.join(tmpdir, "data", "subdir", "z.json"), "w") as f:
            f.write("{}")

        files = store.list_dir(".")
        assert_test("a.json" in files, "list_dir includes a.json")
        assert_test("b.json" in files, "list_dir includes b.json")
        assert_test("test.json" in files, "list_dir includes test.json")
        assert_test("readme.txt" in files, "list_dir includes readme.txt")
        assert_test(".commits.jsonl" not in files, "list_dir excludes .commits.jsonl")
        assert_test("subdir" not in files, "list_dir excludes subdirectories")
        assert_test(files == sorted(files), "list_dir returns sorted list")

        # 9. with_branch 격리
        store_ops = store.with_branch("ops")
        store_ops.write_json(
            "state.json", {"status": "active"}, prev_sha=None, message="ops state"
        )
        data_in_ops, _ = store_ops.read_json("state.json")
        assert_test(
            data_in_ops is not None and data_in_ops["status"] == "active",
            "with_branch creates isolated store",
        )

        data_in_data, _ = store.read_json("state.json")
        assert_test(
            data_in_data is None,
            "with_branch isolation: data branch doesn't see ops file",
        )

        # 10. .commits.jsonl 에 스레드 이름 기록
        log_path = os.path.join(tmpdir, "data", ".commits.jsonl")
        assert_test(os.path.exists(log_path), ".commits.jsonl created")

        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert_test(len(lines) > 0, ".commits.jsonl has entries")

            # 마지막 항목 파싱
            last_entry = json.loads(lines[-1])
            assert_test("ts" in last_entry, "log entry has 'ts'")
            assert_test("path" in last_entry, "log entry has 'path'")
            assert_test("message" in last_entry, "log entry has 'message'")
            assert_test("sha" in last_entry, "log entry has 'sha'")
            assert_test("thread" in last_entry, "log entry has 'thread'")
            assert_test(
                last_entry["thread"] == "MainThread",
                f"log entry thread name is 'MainThread' (got {last_entry['thread']})",
            )

        # 11. 동시 쓰기 (5개 스레드)
        results = []
        errors = []

        def write_in_thread(i: int):
            try:
                changed, sha = store.write_json(
                    f"concurrent_{i}.json",
                    {"thread": i},
                    prev_sha=None,
                    message=f"Thread {i}",
                )
                results.append((i, changed, sha))
            except Exception as e:
                errors.append((i, e))

        threads = [
            _threading.Thread(target=write_in_thread, args=(i,)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert_test(
            len(errors) == 0, f"concurrent writes have no errors (got {errors})"
        )
        assert_test(len(results) == 5, "concurrent writes all succeeded")
        assert_test(
            all(changed for _, changed, _ in results),
            "all concurrent writes report changed=True",
        )

        # 12. 각 concurrent 파일 읽기 확인
        for i in range(5):
            data, sha = store.read_json(f"concurrent_{i}.json")
            assert_test(
                data is not None and data.get("thread") == i,
                f"concurrent file {i} readable and correct",
            )

        # 13. 서브디렉터리 경로 지원
        changed_sub, sha_sub = store.write_json(
            "monitoring/events-2026-09-29.json",
            {"events": []},
            prev_sha=None,
            message="Nested file",
        )
        assert_test(changed_sub is True, "write_json creates nested directory")

        files_monitoring = store.list_dir("monitoring")
        assert_test(
            "events-2026-09-29.json" in files_monitoring,
            "list_dir finds nested file",
        )

        print(f"\n{'='*60}")
        print(f"Test Results: {test_pass}/{test_count} passed")
        if test_pass == test_count:
            print("✓ All tests passed!")
        else:
            print(f"✗ {test_count - test_pass} test(s) failed")
            sys.exit(1)
