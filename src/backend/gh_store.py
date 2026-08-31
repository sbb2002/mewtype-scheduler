"""
GitHub Contents API 저장소 클라이언트. schedule.json/archive.json/pending.json 읽고 쓰기.
"""

import base64
import json
import logging
import random
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


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
        3. 다르면 PUT 수행.
        4. 422/409 충돌 → read_json 재조회 후 1회 재시도.
        5. 성공 → (True, 새sha).

        Args:
            path: 저장소 내 파일 경로.
            data: 저장할 딕셔너리.
            prev_sha: 힌트로만 받는 이전 sha (실제 충돌 해소는 재조회 기준).
            message: 커밋 메시지 (예: "data: pending sync 2026-08-31T12:00:00Z").

        Returns:
            (changed, new_sha) 튜플:
            - (False, 현재sha): 내용이 이미 같음.
            - (True, 새sha): 파일이 업데이트됨.

        Raises:
            RuntimeError: 422/409 충돌 1회 재시도 후에도 실패, 또는 그 외 오류.
        """
        # 1. 현재 내용 조회
        current_data, current_sha = self.read_json(path)
        serialized = _serialize(data)

        # 2. 내용 동일 확인
        if current_data is not None:
            current_serialized = _serialize(current_data)
            if current_serialized == serialized:
                return False, current_sha

        # 3. PUT 수행
        return self._put_json_with_retry(path, serialized, current_sha, message)

    # data 브랜치는 여러 Cloud Run 실행이 동시에 커밋을 시도할 수 있다(방송 시작 시간대에
    # 여러 /wake 가 몰림). Contents API 는 sha 낙관적 동시성이므로 충돌 시 재조회 후 재시도한다.
    _CONFLICT_RETRIES = 6
    _CONFLICT_BACKOFF = 0.4  # 초. n번째 재시도는 n*backoff 만큼 대기(지터 포함)

    def _put_json_with_retry(
        self,
        path: str,
        serialized: str,
        current_sha: Optional[str],
        message: str,
        retry_count: int = 0,  # 하위호환용 인자. 사용 안 함
    ) -> tuple[bool, Optional[str]]:
        """PUT 을 수행하고 409/422(sha 충돌) 시 재조회 후 재시도(_CONFLICT_RETRIES 회, 백오프).

        재조회 결과가 우리가 쓰려는 내용과 이미 동일하면(다른 실행이 같은 내용을 먼저 커밋)
        (False, sha) 로 조용히 성공 처리한다.
        """
        url = f"{self.API}/repos/{self.repo}/contents/{path}"
        content_b64 = base64.b64encode(serialized.encode("utf-8")).decode("ascii")
        sess = self.session or requests.Session()

        for attempt in range(self._CONFLICT_RETRIES + 1):
            body = {"message": message, "content": content_b64, "branch": self.branch}
            if current_sha:
                body["sha"] = current_sha

            try:
                resp = sess.put(url, json=body, headers=self._headers(), timeout=self.timeout)
            except requests.RequestException as e:
                raise RuntimeError(f"GitHub API network error: {e}")

            if resp.status_code in (200, 201):
                try:
                    return True, resp.json().get("content", {}).get("sha")
                except ValueError as e:
                    raise RuntimeError(f"GitHub API response parsing error: {e}")

            if resp.status_code not in (409, 422):
                raise RuntimeError(
                    f"GitHub API write failed: {resp.status_code} {resp.reason}. "
                    f"Response: {resp.text[:200]}"
                )

            # ── sha 충돌 ──
            if attempt >= self._CONFLICT_RETRIES:
                raise RuntimeError(
                    f"GitHub API write conflict on {path} (retry exhausted). "
                    f"Response: {resp.text[:200]}"
                )
            time.sleep(self._CONFLICT_BACKOFF * (attempt + 1) + random.uniform(0, 0.2))
            cur_data, current_sha = self.read_json(path)
            if cur_data is not None and _serialize(cur_data) == serialized:
                logger.info("write conflict on %s but content already current — skip", path)
                return False, current_sha
            logger.warning("write conflict on %s, retry %d/%d", path, attempt + 1, self._CONFLICT_RETRIES)

        raise RuntimeError(f"GitHub API write conflict on {path} (unreachable)")


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
