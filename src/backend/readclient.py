"""(v3.8.2) `mewtype-telegram` → `mewtype-backend` `/fetch` 읽기 클라이언트.

`writeclient` 가 콘텐츠 쓰기를 백엔드 `/write` 한 줄로 모으듯, `data` 저장소 **읽기**도 백엔드
`POST /fetch` 로 모은다. 제어 채널(동시 처리 80)이 GitHub Contents API 를 직접 두드리지 않으니
GitHub 호출(읽기+쓰기)이 `--concurrency=1 --max-instances=1` 인 백엔드 한 곳으로 직렬화된다 —
버스트·동시 요청이 GitHub 의 secondary rate limit(403/429) 이나 409 충돌로 번지는 경로를 줄인다.

`BackendReadStore` 는 `GitHubStore` 의 `read_json` / `read_text` 만 백엔드 호출로 바꾼 서브클래스다.
호출부(`gh.read_json(path)` 82곳)는 그대로 — 반환 계약 `(data, sha)`·404 → `(None, None)`·그 외
`RuntimeError` 도 같다. 쓰기(`write_json` 등)는 상속 그대로라, 그 안의 "현재 sha 읽기" 도 자동으로
백엔드를 거친다. (쓰기 자체를 `/write` 로 옮기는 것은 별개 — control.json 등 예외는 SPEC §8.14.)

`MAIN_SERVICE_URL` 이 비어 있으면(로컬 개발·self-test) 일반 `GitHubStore` 를 돌려준다.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .gh_store import GitHubStore

try:
    from google.oauth2.id_token import fetch_id_token
    from google.auth.transport.requests import Request
except ImportError:  # pragma: no cover
    fetch_id_token = None
    Request = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

log = logging.getLogger("backend.readclient")

_TIMEOUT_SEC = 60  # 백엔드가 tick/write 처리 중이면 그 뒤에 줄을 선다(concurrency=1) — /write 와 같은 값.


class BackendReadStore(GitHubStore):
    """읽기를 백엔드 `/fetch` 로 보내는 `GitHubStore`. 쓰기는 상속(직접)."""

    def __init__(self, token: str, repo: str, branch: str = "data", *, main_url: str,
                 session: Optional[Any] = None, timeout: float = _TIMEOUT_SEC):
        super().__init__(token, repo, branch, session=session, timeout=timeout)
        self.main_url = main_url.rstrip("/")

    # ── 읽기 ──
    def read_json(self, path: str):
        body = self._fetch(path, "json")
        if not body.get("found"):
            return None, None
        return body.get("data"), body.get("sha")

    def read_text(self, path: str):
        body = self._fetch(path, "text")
        if not body.get("found"):
            return None, None
        return body.get("text"), body.get("sha")

    def _fetch(self, path: str, kind: str) -> dict:
        try:
            if self.session is not None:  # 테스트 주입용 — 운영에선 None
                resp = self.session.post(
                    f"{self.main_url}/fetch", json={"path": path, "as": kind},
                    headers={"Authorization": "Bearer test"}, timeout=self.timeout)
            else:
                if not (fetch_id_token and Request and requests):
                    raise RuntimeError("google-auth/requests 미탑재 — /fetch 호출 불가")
                tok = fetch_id_token(Request(), self.main_url)
                resp = requests.post(
                    f"{self.main_url}/fetch", json={"path": path, "as": kind},
                    headers={"Authorization": f"Bearer {tok}"}, timeout=self.timeout)
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"/fetch 호출 실패({path}): {e}") from e
        if resp.status_code != 200:
            raise RuntimeError(f"/fetch 실패({path}): HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()


def make_store(token: str, repo: str, branch: str = "data") -> GitHubStore:
    """운영(`MAIN_SERVICE_URL` 설정)이면 `BackendReadStore`, 아니면 일반 `GitHubStore`."""
    main_url = os.environ.get("MAIN_SERVICE_URL", "").strip().rstrip("/")
    if main_url:
        return BackendReadStore(token, repo, branch, main_url=main_url)
    return GitHubStore(token, repo, branch)


if __name__ == "__main__":
    # self-test (네트워크 불필요): 가짜 세션으로 /fetch 왕복·404·오류·make_store 분기를 확인.
    class _Resp:
        def __init__(self, code, payload=None, text=""):
            self.status_code, self._p, self.text = code, payload, text

        def json(self):
            return self._p

    class _Sess:
        def __init__(self, resp):
            self.resp, self.calls = resp, []

        def post(self, url, json=None, headers=None, timeout=None):
            self.calls.append((url, json))
            return self.resp

    s = _Sess(_Resp(200, {"found": True, "data": {"a": 1}, "sha": "abc"}))
    st = BackendReadStore("tok", "o/r", "data", main_url="https://main.example/", session=s)
    assert st.read_json("preview.json") == ({"a": 1}, "abc")
    assert s.calls == [("https://main.example/fetch", {"path": "preview.json", "as": "json"})], s.calls
    print("[PASS] read_json → /fetch")

    s = _Sess(_Resp(200, {"found": True, "text": "<html>", "sha": "s2"}))
    st = BackendReadStore("tok", "o/r", "data", main_url="https://main.example", session=s)
    assert st.read_text("monitoring/latest.html") == ("<html>", "s2")
    assert s.calls[0][1] == {"path": "monitoring/latest.html", "as": "text"}
    print("[PASS] read_text → /fetch")

    st = BackendReadStore("tok", "o/r", "data", main_url="https://m", session=_Sess(_Resp(200, {"found": False})))
    assert st.read_json("nope.json") == (None, None)
    print("[PASS] 404 → (None, None)")

    for code in (403, 429, 500):
        st = BackendReadStore("tok", "o/r", "data", main_url="https://m", session=_Sess(_Resp(code, text="x")))
        try:
            st.read_json("p.json")
            raise AssertionError("비200 은 RuntimeError 여야 함")
        except RuntimeError as e:
            assert str(code) in str(e)
    print("[PASS] non-200 → RuntimeError")

    os.environ.pop("MAIN_SERVICE_URL", None)
    assert type(make_store("t", "o/r", "data")) is GitHubStore
    os.environ["MAIN_SERVICE_URL"] = "https://main.example"
    assert type(make_store("t", "o/r", "data")) is BackendReadStore
    os.environ.pop("MAIN_SERVICE_URL", None)
    print("[PASS] make_store 분기")
