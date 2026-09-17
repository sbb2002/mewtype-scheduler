"""(write-queue) `mewtype-telegram` → `mewtype-backend` `/write` 동기 호출 클라이언트.

`mewtype-backend` 는 `--concurrency=1 --max-instances=1` 로 배포돼 있어(deploy/deploy.sh),
그 서비스로 들어오는 모든 요청은 Cloud Run 이 한 번에 하나씩만 처리한다 — 그래서 콘텐츠
쓰기(`src/backend/writers.py` 의 JOB_REGISTRY)는 전부 이 함수를 거쳐 그 서비스 위에서
실행되도록 몰아서, 서로 다른 파일에 쓰는 요청끼리도(브랜치 ref 단위로 직렬화되는 GitHub
Contents API 특성상) 경합하지 않게 만든다.

`_handle_resume` 가 `/tick` 을 부르는 기존 패턴(OIDC id token + requests.post)을 그대로 재사용.
`MAIN_SERVICE_URL` 이 비어 있으면(로컬 개발·self-test) 네트워크를 타지 않고 같은 프로세스
안에서 `writers.dispatch` 를 직접 호출한다 — 이때는 호출부가 넘겨준 `gh` 를 그대로 쓴다
(운영 중엔 `gh` 를 절대 네트워크로 안 보낸다 — 서버 쪽이 env 로 직접 재구성).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

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

log = logging.getLogger("backend.writeclient")

_TIMEOUT_SEC = 60
_WAIT_NOTICE_DELAY_SEC = 2.0


class WriteError(RuntimeError):
    """`/write` 호출 실패(HTTP 오류·네트워크 오류 등)."""


def call_write(kind: str, *, gh=None, **args: Any) -> dict:
    """`kind` job 을 (동기로) 실행하고 결과 dict 를 반환.

    `MAIN_SERVICE_URL` 미설정 시 로컬 디스패치(같은 프로세스, `gh` 필요) — self-test·
    단일 서비스 로컬 개발용. 설정돼 있으면 OIDC 로 `mewtype-backend` 의 `/write` 를 호출한다.
    2초 안에 응답이 없으면 "처리 대기 중" DM 을 1회 보낸다(운영자 체감 응답성 확보).
    """
    main_url = os.environ.get("MAIN_SERVICE_URL", "").strip().rstrip("/")
    if not main_url:
        from . import writers
        if gh is None:
            raise WriteError("call_write: MAIN_SERVICE_URL 미설정 + gh 없음 — 로컬 디스패치 불가")
        return writers.dispatch(kind, gh, args)

    if not (fetch_id_token and Request and requests):
        raise WriteError("call_write: google-auth/requests 미탑재 — /write 호출 불가")

    timer = threading.Timer(_WAIT_NOTICE_DELAY_SEC, _send_wait_notice, args=(kind,))
    timer.daemon = True
    timer.start()
    try:
        tok = fetch_id_token(Request(), main_url)
        resp = requests.post(
            f"{main_url}/write",
            json={"kind": kind, "args": args},
            headers={"Authorization": f"Bearer {tok}"},
            timeout=_TIMEOUT_SEC,
        )
    except Exception as e:  # noqa: BLE001
        raise WriteError(f"/write 호출 실패({kind}): {e}") from e
    finally:
        timer.cancel()

    if resp.status_code != 200:
        raise WriteError(f"/write 실패({kind}): HTTP {resp.status_code} {resp.text[:200]}")
    return resp.json()


def _send_wait_notice(kind: str) -> None:
    try:
        from .telegram_app import _send_telegram
        _send_telegram(f"⏳ 처리 대기 중… ({kind})", silent=True)
    except Exception:  # noqa: BLE001
        log.warning("대기 안내 DM 실패(%s)", kind)


if __name__ == "__main__":
    # self-test: MAIN_SERVICE_URL 없을 때 로컬 디스패치 경로가 writers.dispatch 로 정확히
    # 넘어가는지만 확인(네트워크 불필요).
    os.environ.pop("MAIN_SERVICE_URL", None)

    class _MockGh:
        pass

    calls = []

    class _FakeWriters:
        @staticmethod
        def dispatch(kind, gh, args):
            calls.append((kind, gh, args))
            return {"ok": True}

    import sys
    sys.modules["src.backend.writers"] = _FakeWriters  # type: ignore[assignment]

    g = _MockGh()
    result = call_write("merge_rows", gh=g, rows=[1, 2], now_iso="2026-01-01T00:00:00Z", message="m")
    assert result == {"ok": True}
    assert calls == [("merge_rows", g, {"rows": [1, 2], "now_iso": "2026-01-01T00:00:00Z", "message": "m"})]
    print("[PASS] writeclient local-dispatch self-test")

    try:
        call_write("merge_rows", rows=[])
        raise AssertionError("gh 없이 로컬 디스패치는 실패해야 함")
    except WriteError:
        pass
    print("[PASS] writeclient missing-gh guard")
