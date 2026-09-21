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


class RateLimitError(RuntimeError):
    """GitHub 가 속도 제한(primary/secondary)을 알렸다 — 403 또는 429.

    `retry_after` 는 `retry-after` 헤더(초). 없으면 `x-ratelimit-reset`(에포크) 로 계산하고, 그것도
    없으면 None(호출자가 백오프 — GitHub 문서: 1분 이상 기다린 뒤 지수적으로 늘림).
    DB 관제소(`tower.py`)가 이 예외를 받아 큐를 멈추고 기다린다.
    """

    def __init__(self, message: str, *, status: int = 429, retry_after: Optional[float] = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _rate_limit_from(resp) -> Optional["RateLimitError"]:
    """비정상 응답이 속도 제한이면 RateLimitError, 아니면 None (권한 403 등은 None)."""
    status = getattr(resp, "status_code", 0)
    if status not in (403, 429):
        return None
    headers = getattr(resp, "headers", None) or {}
    get = (lambda k: headers.get(k)) if hasattr(headers, "get") else (lambda k: None)
    retry = get("retry-after") or get("Retry-After")
    remaining = get("x-ratelimit-remaining") or get("X-RateLimit-Remaining")
    reset = get("x-ratelimit-reset") or get("X-RateLimit-Reset")
    body = (getattr(resp, "text", "") or "").lower()
    limited = status == 429 or retry is not None or str(remaining) == "0" or "rate limit" in body
    if not limited:
        return None
    wait: Optional[float] = None
    try:
        if retry is not None:
            wait = float(retry)
        elif str(remaining) == "0" and reset is not None:
            wait = max(0.0, float(reset) - time.time())
    except (TypeError, ValueError):
        wait = None
    return RateLimitError(
        f"GitHub rate limit: {status}. Response: {(getattr(resp, 'text', '') or '')[:200]}",
        status=status, retry_after=wait,
    )


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
        etag_cache: Optional[dict] = None,
    ):
        """
        GitHub 저장소 클라이언트 초기화.

        Args:
            token: fine-grained PAT (Contents: Read and write). 비어있으면 ValueError 발생.
            repo: "owner/name" 형식의 저장소 이름.
            branch: 작업할 브랜치 (기본 "data").
            session: requests.Session 객체. 미지정 시 각 요청마다 새로 생성.
            timeout: 요청 타임아웃 (초). 기본 15.0.
            etag_cache: dict 를 주면 읽기에 조건부 요청(If-None-Match)을 쓰고 304 면 캐시를 돌려준다
                        (304 는 primary rate limit 에 집계되지 않는다 — GitHub 문서). None 이면 사용 안 함.

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
        self.etag_cache = etag_cache

    def _headers(self) -> dict:
        """API 요청에 필요한 헤더 반환."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mewtype-scheduler-backend",
        }

    def _get_contents(self, path: str):
        """Contents API GET 1회. 반환: 404 면 None, 아니면 (content_b64, sha).

        etag_cache 가 있으면 If-None-Match 를 보내고 304 는 캐시 사용. 속도 제한(403/429) 은
        RateLimitError, 그 외 비정상 상태는 RuntimeError.
        """
        url = f"{self.API}/repos/{self.repo}/contents/{path}"
        params = {"ref": self.branch}
        headers = self._headers()
        cached = self.etag_cache.get((self.branch, path)) if self.etag_cache is not None else None
        if cached:
            headers["If-None-Match"] = cached[0]
        try:
            sess = self.session or requests.Session()
            resp = sess.get(url, params=params, headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise RuntimeError(f"GitHub API network error: {e}")

        if resp.status_code == 304 and cached:
            return cached[1], cached[2]
        if resp.status_code == 404:
            if self.etag_cache is not None:
                self.etag_cache.pop((self.branch, path), None)
            return None
        if resp.status_code != 200:
            rl = _rate_limit_from(resp)
            if rl is not None:
                raise rl
            raise RuntimeError(
                f"GitHub API read failed: {resp.status_code} {resp.reason}. "
                f"Response: {resp.text[:200]}"
            )
        try:
            resp_json = resp.json()
        except ValueError as e:
            raise RuntimeError(f"GitHub API response parsing error: {e}")
        content_b64 = resp_json.get("content", "")
        sha = resp_json.get("sha")
        if not content_b64:
            raise RuntimeError(f"No content in response for {path}")
        if self.etag_cache is not None:
            etag = (getattr(resp, "headers", None) or {}).get("etag") if hasattr(getattr(resp, "headers", None), "get") else None
            if etag:
                self.etag_cache[(self.branch, path)] = (etag, content_b64, sha)
        return content_b64, sha

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
        got = self._get_contents(path)
        if got is None:
            return None, None
        content_b64, sha = got
        try:
            content_str = base64.b64decode(content_b64).decode("utf-8")
            return json.loads(content_str), sha
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
        return self._put_content(path, serialized, current_sha, message)

    def read_text(self, path: str) -> tuple[Optional[str], Optional[str]]:
        """GitHub 저장소에서 일반 텍스트 파일(HTML 등)을 읽음. read_json 과 동일하되 JSON 파싱 안 함.

        Returns:
            (content_str, sha) 또는 404 면 (None, None).
        """
        got = self._get_contents(path)
        if got is None:
            return None, None
        content_b64, sha = got
        return base64.b64decode(content_b64).decode("utf-8"), sha

    def write_text(
        self, path: str, text: str, *, prev_sha: Optional[str] = None, message: str,
    ) -> tuple[bool, Optional[str]]:
        """일반 텍스트 파일(HTML 등)을 씀. write_json 과 동일한 무변화 스킵·낙관적 동시성
        규칙을 따르되, JSON 직렬화는 하지 않고 text 를 그대로 쓴다."""
        current_text, current_sha = self.read_text(path)
        if current_text is not None and current_text == text:
            return False, current_sha
        if prev_sha is not None and current_sha is not None and current_sha != prev_sha:
            raise ConflictError(
                f"{path}: base sha {prev_sha[:8]} != current {current_sha[:8]} "
                f"(다른 실행이 먼저 커밋함)"
            )
        return self._put_content(path, text, current_sha, message)

    _NET_RETRIES = 3
    _NET_BACKOFF = 0.5  # 초. n번째 재시도는 n*backoff 대기

    def _put_content(
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

            rl = _rate_limit_from(resp)
            if rl is not None:
                raise rl

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

    # write_text / read_text (v3.2.3 — PUSH_MONITOR.html 같은 비-JSON 텍스트 파일용)
    sess_d = _FakeSess("<html>old</html>", "shaD")
    gh_d = GitHubStore("tok", "o/r", "devpapers", session=sess_d)
    changed_d, sha_d = gh_d.write_text("docs/x.html", "<html>new</html>", message="m")
    assert changed_d and sha_d == "newsha" and sess_d.put_calls == 1
    print("✓ write_text: 변경 있으면 PUT")

    sess_e = _FakeSess("<html>same</html>", "shaE")
    gh_e = GitHubStore("tok", "o/r", "devpapers", session=sess_e)
    changed_e, sha_e = gh_e.write_text("docs/x.html", "<html>same</html>", message="m")
    assert changed_e is False and sha_e == "shaE" and sess_e.put_calls == 0
    print("✓ write_text: 내용 동일하면 PUT 생략")

    # (v3.8.2 관제소) 속도 제한 예외 + ETag 조건부 요청
    class _RResp:
        def __init__(self, code, payload=None, headers=None, text=""):
            self.status_code, self.reason, self.text = code, "x", text
            self._payload, self.headers = payload or {}, headers or {}
        def json(self):
            return self._payload

    enc = base64.b64encode(_serialize({"n": 1}).encode()).decode()

    class _EtagSess:
        def __init__(self):
            self.sent = []
        def get(self, url, **kw):
            inm = kw["headers"].get("If-None-Match")
            self.sent.append(inm)
            if inm == "E1":
                return _RResp(304)
            return _RResp(200, {"content": enc, "sha": "s1"}, {"etag": "E1"})

    es = _EtagSess()
    gh_et = GitHubStore("tok", "o/r", "data", session=es, etag_cache={})
    assert gh_et.read_json("a.json") == ({"n": 1}, "s1")      # 200 → 캐시 저장
    assert gh_et.read_json("a.json") == ({"n": 1}, "s1")      # 304 → 캐시 사용
    assert es.sent == [None, "E1"], es.sent
    print("✓ ETag: 두 번째 읽기는 If-None-Match 로 304 → 캐시 사용")

    class _LimSess:
        def __init__(self, resp):
            self.resp = resp
        def get(self, url, **kw):
            return self.resp
        def put(self, url, **kw):
            return self.resp

    for resp, want in [
        (_RResp(429, headers={"retry-after": "7"}, text="slow down"), 7.0),
        (_RResp(403, headers={"retry-after": "3"}, text="secondary rate limit"), 3.0),
        (_RResp(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 30)}), None),
        (_RResp(403, text="You have exceeded a secondary rate limit."), None),
    ]:
        g = GitHubStore("tok", "o/r", "data", session=_LimSess(resp))
        try:
            g.read_json("p.json")
            assert False, "RateLimitError 여야 함"
        except RateLimitError as e:
            if want is not None:
                assert e.retry_after == want, (e.retry_after, want)
            else:
                assert e.retry_after is None or 0 <= e.retry_after <= 31
    # 권한 403(속도 제한 신호 없음)은 RateLimitError 가 아니라 RuntimeError
    g = GitHubStore("tok", "o/r", "data", session=_LimSess(_RResp(403, text="Resource not accessible")))
    try:
        g.read_json("p.json")
        assert False
    except RateLimitError:
        assert False, "권한 403 을 속도 제한으로 오분류"
    except RuntimeError:
        pass
    print("✓ 403/429: 속도 제한 신호가 있으면 RateLimitError(retry_after), 권한 403 은 RuntimeError")

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
