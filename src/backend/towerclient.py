"""(v3.8.2) 제어 채널·백엔드 → DB 관제소(`mewtype-db-tower`) 클라이언트.

`TowerStore` 는 `GitHubStore` 의 `read_json`/`read_text`/`write_json`/`write_text` 4개만 관제소 호출로
바꾼 서브클래스다 — 호출부(`gh.read_json(path)` · `gh.write_json(...)` 수십 곳)는 그대로. 반환 계약
`(data, sha)`·404 → `(None, None)`·`(changed, sha)`·sha 충돌 `ConflictError`·그 외 `RuntimeError` 도 같다.
`prev_sha` 낙관적 동시성 검사는 관제소가 쓰는 시점의 현재 sha 로 한다.

관제소가 대기 상한 안에 처리하지 못하면 503 + `Retry-After` → `TowerBusyError`(RuntimeError 서브클래스)
를 던진다. 호출부는 기존의 `RuntimeError` 처리(명령 오류 DM 등)로 그대로 받는다.

`TOWER_URL` 이 비어 있으면(로컬 개발·self-test) `make_store` 는 일반 `GitHubStore` 를 돌려준다.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .gh_store import ConflictError, GitHubStore

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

log = logging.getLogger("backend.towerclient")

_TIMEOUT_SEC = 60.0
_BUDGET_MARGIN_SEC = 8.0  # 관제소 대기 상한 = 이 클라이언트 타임아웃 − 여유 (응답이 타임아웃 전에 오도록)


class TowerBusyError(RuntimeError):
    """관제소가 대기 상한 안에 처리하지 못함(503). `retry_after` 초 뒤 재시도 가능."""

    def __init__(self, message: str, retry_after: float = 0.0):
        super().__init__(message)
        self.retry_after = retry_after


class TowerStore(GitHubStore):
    """`data` 저장소 읽기·쓰기를 전부 관제소로 보내는 `GitHubStore`."""

    def __init__(self, token: str, repo: str, branch: str = "data", *, tower_url: str,
                 session: Optional[Any] = None, timeout: float = _TIMEOUT_SEC):
        super().__init__(token, repo, branch, session=session, timeout=timeout)
        self.tower_url = tower_url.rstrip("/")

    # ── 읽기 → /fetch ──
    def read_json(self, path: str):
        body = self._post("/fetch", {"path": path, "as": "json"}, path)
        if not body.get("found"):
            return None, None
        return body.get("data"), body.get("sha")

    def read_text(self, path: str):
        body = self._post("/fetch", {"path": path, "as": "text"}, path)
        if not body.get("found"):
            return None, None
        return body.get("text"), body.get("sha")

    # ── 쓰기 → /put ──
    def write_json(self, path: str, data: dict, *, prev_sha: Optional[str], message: str):
        r = self._post("/put", {"path": path, "as": "json", "data": data,
                                "prev_sha": prev_sha, "message": message}, path)
        return bool(r.get("changed")), r.get("sha")

    def write_text(self, path: str, text: str, *, prev_sha: Optional[str] = None, message: str):
        r = self._post("/put", {"path": path, "as": "text", "text": text,
                                "prev_sha": prev_sha, "message": message}, path)
        return bool(r.get("changed")), r.get("sha")

    def _post(self, route: str, payload: dict, label: str) -> dict:
        payload = dict(payload, budget=max(1.0, float(self.timeout) - _BUDGET_MARGIN_SEC))
        try:
            if self.session is not None:  # 테스트 주입용 — 운영에선 None
                resp = self.session.post(f"{self.tower_url}{route}", json=payload,
                                         headers={"Authorization": "Bearer test"}, timeout=self.timeout)
            else:
                if not (fetch_id_token and Request and requests):
                    raise RuntimeError("google-auth/requests 미탑재 — 관제소 호출 불가")
                tok = fetch_id_token(Request(), self.tower_url)
                resp = requests.post(f"{self.tower_url}{route}", json=payload,
                                     headers={"Authorization": f"Bearer {tok}"}, timeout=self.timeout)
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"관제소 {route} 호출 실패({label}): {e}") from e
        if resp.status_code == 409:  # sha 충돌 — 호출부가 ConflictError 로 재계산·재시도
            raise ConflictError(f"{label}: {resp.text[:200]}")
        if resp.status_code == 503:
            try:
                ra = float((resp.json() or {}).get("retry_after", 0))
            except Exception:  # noqa: BLE001
                ra = 0.0
            raise TowerBusyError(f"관제소가 바쁨({label}) — {ra:.0f}초 뒤 다시 시도", retry_after=ra)
        if resp.status_code != 200:
            raise RuntimeError(f"관제소 {route} 실패({label}): HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()


def make_store(token: str, repo: str, branch: str = "data") -> GitHubStore:
    """운영(`TOWER_URL` 설정)이면 `TowerStore`, 아니면 일반 `GitHubStore`(로컬·self-test)."""
    tower_url = os.environ.get("TOWER_URL", "").strip().rstrip("/")
    if tower_url:
        return TowerStore(token, repo, branch, tower_url=tower_url)
    return GitHubStore(token, repo, branch)


if __name__ == "__main__":
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

    def mk(resp):
        s = _Sess(resp)
        return TowerStore("tok", "o/r", "data", tower_url="https://tower.example/", session=s), s

    st, s = mk(_Resp(200, {"found": True, "data": {"a": 1}, "sha": "abc"}))
    assert st.read_json("preview.json") == ({"a": 1}, "abc")
    url, body = s.calls[0]
    assert url == "https://tower.example/fetch" and body["path"] == "preview.json" and body["as"] == "json"
    assert body["budget"] == 52.0, body           # 타임아웃 60 − 여유 8
    print("[PASS] read_json → /fetch (budget 전달)")

    st, s = mk(_Resp(200, {"found": True, "text": "<html>", "sha": "s2"}))
    assert st.read_text("monitoring/latest.html") == ("<html>", "s2")
    print("[PASS] read_text → /fetch")

    st, _ = mk(_Resp(200, {"found": False}))
    assert st.read_json("nope.json") == (None, None)
    print("[PASS] 404 → (None, None)")

    st, s = mk(_Resp(200, {"changed": True, "sha": "n1"}))
    assert st.write_json("control.json", {"paused": True}, prev_sha="p", message="m") == (True, "n1")
    url, body = s.calls[0]
    assert url == "https://tower.example/put" and body["as"] == "json" and body["prev_sha"] == "p"
    assert body["data"] == {"paused": True} and body["message"] == "m"
    print("[PASS] write_json → /put")

    st, s = mk(_Resp(200, {"changed": False, "sha": "n2"}))
    assert st.write_text("monitoring/x.jsonl", "line\n", message="m") == (False, "n2")
    assert s.calls[0][1]["as"] == "text" and s.calls[0][1]["text"] == "line\n"
    print("[PASS] write_text → /put")

    st, _ = mk(_Resp(409, text="base sha mismatch"))
    try:
        st.write_json("p.json", {}, prev_sha="a", message="m")
        raise AssertionError("409 는 ConflictError 여야 함")
    except ConflictError:
        pass
    print("[PASS] 409 → ConflictError")

    st, _ = mk(_Resp(503, {"busy": True, "retry_after": 12}, text="busy"))
    try:
        st.read_json("p.json")
        raise AssertionError("503 은 TowerBusyError 여야 함")
    except TowerBusyError as e:
        assert e.retry_after == 12.0 and isinstance(e, RuntimeError)
    print("[PASS] 503 → TowerBusyError(retry_after) — RuntimeError 로도 잡힘")

    for code in (403, 500):
        st, _ = mk(_Resp(code, text="x"))
        try:
            st.write_json("p.json", {}, prev_sha=None, message="m")
            raise AssertionError("비200 은 RuntimeError 여야 함")
        except (ConflictError, TowerBusyError):
            raise AssertionError("오분류")
        except RuntimeError as e:
            assert str(code) in str(e)
    print("[PASS] 그 외 비200 → RuntimeError")

    os.environ.pop("TOWER_URL", None)
    assert type(make_store("t", "o/r", "data")) is GitHubStore
    os.environ["TOWER_URL"] = "https://tower.example"
    assert type(make_store("t", "o/r", "data")) is TowerStore
    os.environ.pop("TOWER_URL", None)
    print("[PASS] make_store 분기")
