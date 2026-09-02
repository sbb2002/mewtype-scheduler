"""
GitHub Contents API 저장소 클라이언트. schedule.json/archive.json/pending.json 읽고 쓰기.
"""

import base64
import json
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class ConflictError(RuntimeError):
    """다른 실행이 우리가 읽은 뒤 먼저 커밋해 base sha 가 어긋났다.

    호출자는 최신 상태를 다시 읽어 재계산한 뒤 다시 write_json 해야 한다.
    (예전엔 여기서 낡은 payload 를 새 sha 로 재-PUT 해 조용히 덮어썼는데,
     그러면 방송 시작 시간대에 tick/wake 가 겹칠 때 pending 상태 전이가 유실됐다.)
    """


def _serialize(data: dict) -> str:
    """
    JSON 직렬화. v1 store.save_json_if_changed 와 100% 동일.

    Args:
        data: 딕셔너리

    Returns:
        ensure_ascii=False, indent=2, sort_keys=True 로 직렬화 후 끝에 개행 1개 추가
    """
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


class GitHubStore:
    """GitHub Contents API 를 이용한 JSON 저장소."""

    API = "https://api.github.com"

    def __init__(
        self,
        token: str,
        repo: str,
        branch: str = "data",
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 15.0,
    ):
        """
        GitHub 저장소 클라이언트 초기화.

        Args:
            token: fine-grained PAT (Contents: Read and write). 비어있으면 ValueError 발생.
            repo: "owner/name" 형식의 저장소 이름.
            branch: 작업할 브랜치 (기본 "data").
            session: requests.Session 객체. 미지정 시 각 요청마다 새로 생성.
            timeout: 요청 타임아웃 (초). 기본 15.0.

        Raises:
            ValueError: token 이 비어있을 때.
        """
        if not token:
            raise ValueError("token must not be empty")

        self.token = token
        self.repo = repo
        self.branch = branch
        self.session = session
        self.timeout = timeout

    def _headers(self) -> dict:
        """API 요청에 필요한 헤더 반환."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mewtype-scheduler-backend",
        }

    def read_json(self, path: str) -> tuple[Optional[dict], Optional[str]]:
        """
        GitHub 저장소에서 JSON 파일을 읽음.

        GET /repos/{repo}/contents/{path}?ref={branch}

        Args:
            path: 저장소 내 파일 경로 (예: "schedule.json").

        Returns:
            (data, sha) 튜플:
            - 200: (파싱된 dict, sha 문자열)
            - 404: (None, None)
            - 그 외 오류: RuntimeError 발생

        Raises:
            RuntimeError: 네트워크 오류, 예상 외 HTTP 상태코드, 베이스64 디코딩 오류, JSON 파싱 오류.
        """
        url = f"{self.API}/repos/{self.repo}/contents/{path}"
        params = {"ref": self.branch}

        try:
            sess = self.session or requests.Session()
            resp = sess.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
            )

            if resp.status_code == 404:
                return None, None

            if resp.status_code != 200:
                raise RuntimeError(
                    f"GitHub API read failed: {resp.status_code} {resp.reason}. "
                    f"Response: {resp.text[:200]}"
                )

            resp_json = resp.json()
            content_b64 = resp_json.get("content", "")
            sha = resp_json.get("sha")

            if not content_b64:
                raise RuntimeError(f"No content in response for {path}")

            # 베이스64 디코딩
            content_bytes = base64.b64decode(content_b64)
            content_str = content_bytes.decode("utf-8")

            # JSON 파싱
            data = json.loads(content_str)

            return data, sha

        except requests.RequestException as e:
            raise RuntimeError(f"GitHub API network error: {e}")
        except (ValueError, KeyError) as e:
            raise RuntimeError(f"GitHub API response parsing error: {e}")

    def write_json(
        self,
        path: str,
        data: dict,
        *,
        prev_sha: Optional[str],
        message: str,
    ) -> tuple[bool, Optional[str]]:
        """
        GitHub 저장소에 JSON 파일을 씀. 내용이 동일하면 PUT 하지 않음.

        직렬화: json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        처리 흐름:
        1. read_json 으로 현재 내용과 sha 조회.
        2. 직렬화 문자열이 동일하면 (False, 현재sha) 반환 (PUT 안 함).
        3. prev_sha 가 주어졌는데 현재 sha 와 다르면 → 우리가 읽은 뒤 남이 다른 내용을
           커밋한 것 → ConflictError (호출자가 재계산해야 함).
        4. 아니면 PUT. 200/201 → (True, 새sha). 409/422 → ConflictError.
        5. 네트워크 오류만 몇 번 재시도.

        Args:
            path: 저장소 내 파일 경로.
            data: 저장할 딕셔너리.
            prev_sha: 호출자가 계산을 시작할 때 읽은 sha. 낙관적 동시성 기준.
                      None 이면 sha 검사 없이 현재 sha 로 그대로 씀(부트스트랩·단독 실행).
            message: 커밋 메시지 (예: "data: pending sync 2026-08-31T12:00:00Z").

        Returns:
            (changed, new_sha) 튜플:
            - (False, 현재sha): 내용이 이미 같음.
            - (True, 새sha): 파일이 업데이트됨.

        Raises:
            ConflictError: base sha 가 어긋남 (호출자가 최신 상태로 재계산 후 재시도).
            RuntimeError: 그 외 GitHub API 오류.
        """
        # 1. 현재 내용 조회
        current_data, current_sha = self.read_json(path)
        serialized = _serialize(data)

        # 2. 내용 동일 확인 (남이 같은 내용을 이미 커밋한 경우 포함)
        if current_data is not None and _serialize(current_data) == serialized:
            return False, current_sha

        # 3. base sha 어긋남 → 재계산 필요
        if prev_sha is not None and current_sha is not None and current_sha != prev_sha:
            raise ConflictError(
                f"{path}: base sha {prev_sha[:8]} != current {current_sha[:8]} "
                f"(다른 실행이 먼저 커밋함)"
            )

        # 4. PUT
        return self._put_json(path, serialized, current_sha, message)

    _NET_RETRIES = 3
    _NET_BACKOFF = 0.5  # 초. n번째 재시도는 n*backoff 대기

    def _put_json(
        self,
        path: str,
        serialized: str,
        current_sha: Optional[str],
        message: str,
    ) -> tuple[bool, Optional[str]]:
        """PUT 1회 (네트워크 오류만 _NET_RETRIES 회 재시도).

        200/201 → (True, 새sha). 409/422(sha 충돌) → ConflictError.
        그 외 상태코드 → RuntimeError.
        """
        url = f"{self.API}/repos/{self.repo}/contents/{path}"
        content_b64 = base64.b64encode(serialized.encode("utf-8")).decode("ascii")
        sess = self.session or requests.Session()
        body = {"message": message, "content": content_b64, "branch": self.branch}
        if current_sha:
            body["sha"] = current_sha

        for attempt in range(self._NET_RETRIES + 1):
            try:
                resp = sess.put(url, json=body, headers=self._headers(), timeout=self.timeout)
            except requests.RequestException as e:
                if attempt >= self._NET_RETRIES:
                    raise RuntimeError(f"GitHub API network error: {e}")
                time.sleep(self._NET_BACKOFF * (attempt + 1))
                continue

            if resp.status_code in (200, 201):
                try:
                    return True, resp.json().get("content", {}).get("sha")
                except ValueError as e:
                    raise RuntimeError(f"GitHub API response parsing error: {e}")

            if resp.status_code in (409, 422):
                raise ConflictError(
                    f"{path}: PUT {resp.status_code} {resp.reason}. Response: {resp.text[:200]}"
                )

            raise RuntimeError(
                f"GitHub API write failed: {resp.status_code} {resp.reason}. "
                f"Response: {resp.text[:200]}"
            )

        raise RuntimeError(f"GitHub API write on {path} (unreachable)")


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대비
    except Exception:
        pass

    # Self-test: 직렬화 규칙 검증 (네트워크 불필요)

    test_data = {
        "z_field": "last",
        "a_field": "first",
        "nested": {
            "z": 1,
            "a": 2,
        },
        "한글": "테스트",
    }

    serialized = _serialize(test_data)

    # 검증 1: 키 정렬
    lines = serialized.strip().split("\n")
    assert lines[0] == "{", "첫 줄은 {"
    # a_field 가 z_field 보다 먼저 나와야 함
    text = "\n".join(lines)
    a_idx = text.index('"a_field"')
    z_idx = text.index('"z_field"')
    assert a_idx < z_idx, "키가 정렬되어야 함 (a < z)"

    # 검증 2: indent 2
    assert "  " in serialized, "indent 2 여야 함"

    # 검증 3: 끝 개행
    assert serialized.endswith("\n"), "끝에 개행 1개 있어야 함"

    # 검증 4: 한글 유지 (비-ASCII)
    assert "한글" in serialized, "한글이 escape 되지 않아야 함"
    assert "테스트" in serialized, "한글 값도 escape 되지 않아야 함"

    # 검증 5: json.loads 로 복원 가능
    restored = json.loads(serialized)
    assert restored == test_data, "직렬화 후 파싱 결과가 동일해야 함"

    print("✓ Serialization rules verified:")
    print("  - Keys sorted alphabetically")
    print("  - Indent 2 applied")
    print("  - Trailing newline present")
    print("  - Non-ASCII (Korean) characters preserved")
    print("  - Round-trip parse successful")

    # 검증 6: 낙관적 동시성 — base sha 어긋나면 ConflictError, 안 어긋나면 PUT (네트워크 mock)
    class _Resp:
        def __init__(self, code, payload=None):
            self.status_code, self.reason, self.text = code, "", ""
            self._payload = payload or {}
        def json(self):
            return self._payload

    class _FakeSess:
        """read=GET 는 항상 현재 원격(cur)을, write=PUT 는 성공 응답을 돌려준다."""
        def __init__(self, cur_content: str, cur_sha: str):
            self.cur_content, self.cur_sha, self.put_calls = cur_content, cur_sha, 0
        def get(self, url, **kw):
            enc = base64.b64encode(self.cur_content.encode()).decode()
            return _Resp(200, {"content": enc, "sha": self.cur_sha})
        def put(self, url, **kw):
            self.put_calls += 1
            return _Resp(201, {"content": {"sha": "newsha"}})

    remote = _serialize({"n": 1})
    # (a) prev_sha 가 현재와 같음 → PUT 됨
    sess_a = _FakeSess(remote, "shaA")
    gh_a = GitHubStore("tok", "o/r", "data", session=sess_a)
    changed, new_sha = gh_a.write_json("pending.json", {"n": 2}, prev_sha="shaA", message="m")
    assert changed and new_sha == "newsha" and sess_a.put_calls == 1

    # (b) prev_sha 가 현재와 다름 → ConflictError, PUT 안 함
    sess_b = _FakeSess(remote, "shaZ")
    gh_b = GitHubStore("tok", "o/r", "data", session=sess_b)
    try:
        gh_b.write_json("pending.json", {"n": 2}, prev_sha="shaA", message="m")
        assert False, "ConflictError 가 발생해야 함"
    except ConflictError:
        pass
    assert sess_b.put_calls == 0

    # (c) 남이 우리와 같은 내용을 이미 커밋 → PUT 없이 (False, sha)
    sess_c = _FakeSess(_serialize({"n": 2}), "shaZ")
    gh_c = GitHubStore("tok", "o/r", "data", session=sess_c)
    changed, sha = gh_c.write_json("pending.json", {"n": 2}, prev_sha="shaA", message="m")
    assert changed is False and sha == "shaZ" and sess_c.put_calls == 0

    print("✓ Optimistic concurrency: ConflictError on stale base sha, no silent clobber")

    # 선택 스모크테스트: GH_TOKEN_TEST 환경변수 있으면 실제 read 시도
    import os
    gh_token_test = os.environ.get("GH_TOKEN_TEST")
    if gh_token_test:
        print("\nAttempting live smoke test with GH_TOKEN_TEST...")
        try:
            gh = GitHubStore(gh_token_test, "sbb2002/mewtype-scheduler", "data")
            data, sha = gh.read_json("schedule.json")
            if data is not None:
                print(f"  ✓ read_json('schedule.json') succeeded, sha={sha[:8]}")
            else:
                print("  ✓ read_json('schedule.json') returned (None, None) - file not found")
        except Exception as e:
            print(f"  ✗ read_json smoke test failed: {e}")
    else:
        print("\nSkipping live smoke test (GH_TOKEN_TEST not set)")
