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
import random
import threading
import time
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

# (v3.8.9) /write 429/503 백오프 재시도
_MAX_RETRIES = 5  # 최대 5회 재시도 = 총 6회 시도
_INITIAL_BACKOFF_SEC = 1.5  # 첫 재시도 대기 시간
_MAX_BACKOFF_SEC = 20.0  # 지수 백오프 상한(총 대기 시간 60초 이내 유지)
_BACKOFF_MULTIPLIER = 2.0  # 매 재시도마다 2배
_JITTER_SEC = 0.5  # 지터 범위 상한


class WriteError(RuntimeError):
    """`/write` 호출 실패(HTTP 오류·네트워크 오류 등)."""


def call_write(kind: str, *, gh=None, label: str | None = None, **args: Any) -> dict:
    """`kind` job 을 (동기로) 실행하고 결과 dict 를 반환.

    `MAIN_SERVICE_URL` 미설정 시 로컬 디스패치(같은 프로세스, `gh` 필요) — self-test·
    단일 서비스 로컬 개발용. 설정돼 있으면 OIDC 로 `mewtype-backend` 의 `/write` 를 호출한다.
    2초 안에 응답이 없으면 "처리 대기 중" DM 을 1회 보낸다(운영자 체감 응답성 확보).

    `label`: 대기/완료 DM 에 붙일 내용 태그(예: `"千石ユノ 예고"` → `"[千石ユノ 예고]merge_rows"`).
    생략하면 `args["action"]`(대부분의 호출부가 이미 undo 로그용으로 넘기고 있음)을 폴백으로
    쓰고, 그것도 없으면 태그 없이 `kind` 만 나간다(기존 문구와 동일).
    (v3.8.4) 대기 DM 이 실제로 나간 경우에만, 처리가 끝난 시점(성공/실패 모두)에 짝이 되는
    완료/실패 DM 을 보낸다 — 예전엔 "처리 대기 중…"만 오고 끝났는지 알 길이 없었다.
    2초 안에 끝나는 빠른 경로는 지금처럼 아무 DM 도 안 나간다(각 핸들러가 이미 보내는
    자체 완료 DM 과 중복 안 되게).
    """
    main_url = os.environ.get("MAIN_SERVICE_URL", "").strip().rstrip("/")
    if not main_url:
        from . import writers
        if gh is None:
            raise WriteError("call_write: MAIN_SERVICE_URL 미설정 + gh 없음 — 로컬 디스패치 불가")
        return writers.dispatch(kind, gh, args)

    if not (fetch_id_token and Request and requests):
        raise WriteError("call_write: google-auth/requests 미탑재 — /write 호출 불가")

    tag = label or (args.get("action") or "")
    notice_sent = threading.Event()

    def _fire_wait_notice() -> None:
        # DM 발송 자체보다 먼저 플래그를 세운다 — 메인 스레드가 timer.cancel() 직후
        # notice_sent 를 확인할 때, "타이머는 발화했는데 아직 플래그 전이면 완료 DM 을
        # 놓치는" 레이스를 피하기 위함(반대 방향 레이스는 무해 — DM 두 개 순서만 살짝
        # 어긋날 수 있는 정도).
        notice_sent.set()
        _send_wait_notice(kind, tag)

    timer = threading.Timer(_WAIT_NOTICE_DELAY_SEC, _fire_wait_notice)
    timer.daemon = True
    timer.start()
    try:
        tok = fetch_id_token(Request(), main_url)

        # (v3.8.9) /write 429/503 지수 백오프 재시도
        retry = 0
        while True:
            resp = requests.post(
                f"{main_url}/write",
                json={"kind": kind, "args": args},
                headers={"Authorization": f"Bearer {tok}"},
                timeout=_TIMEOUT_SEC,
            )

            # 429/503 → 지수 백오프 재시도 (Cloud Run이 백엔드 컨테이너에 요청을 배정하기 전에
            # 거절한 것이라 백엔드가 요청을 보지 못했다 — 재시도해도 중복 커밋이 없다)
            if resp.status_code in (429, 503) and retry < _MAX_RETRIES:
                retry += 1
                backoff = min(
                    _INITIAL_BACKOFF_SEC * (_BACKOFF_MULTIPLIER ** (retry - 1)),
                    _MAX_BACKOFF_SEC,
                )
                wait = backoff + random.uniform(0, _JITTER_SEC)
                log.warning(
                    "/write HTTP %d, 재시도 %d/%d, %.2f초 대기",
                    resp.status_code,
                    retry,
                    _MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                continue
            break
    except Exception as e:  # noqa: BLE001
        if notice_sent.is_set():
            _send_done_notice(kind, tag, ok=False, err=str(e))
        raise WriteError(f"/write 호출 실패({kind}): {e}") from e
    finally:
        timer.cancel()

    if resp.status_code != 200:
        if notice_sent.is_set():
            _send_done_notice(kind, tag, ok=False, err=f"HTTP {resp.status_code}")
        raise WriteError(f"/write 실패({kind}): HTTP {resp.status_code} {resp.text[:200]}")

    if notice_sent.is_set():
        _send_done_notice(kind, tag, ok=True)
    return resp.json()


def _tag_prefix(tag: str) -> str:
    return f"[{tag}]" if tag else ""


def _send_wait_notice(kind: str, tag: str = "") -> None:
    try:
        from .telegram_app import _send_telegram
        _send_telegram(f"⏳ 처리 대기 중… {_tag_prefix(tag)}{kind}", silent=True)
    except Exception:  # noqa: BLE001
        log.warning("대기 안내 DM 실패(%s)", kind)


def _send_done_notice(kind: str, tag: str, *, ok: bool, err: str | None = None) -> None:
    try:
        from .telegram_app import _send_telegram
        if ok:
            _send_telegram(f"✅ 처리 완료 {_tag_prefix(tag)}{kind}", silent=True)
        else:
            _send_telegram(f"⚠️ 처리 실패 {_tag_prefix(tag)}{kind}: {(err or '')[:150]}")
    except Exception:  # noqa: BLE001
        log.warning("완료 안내 DM 실패(%s)", kind)


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

    # ── (v3.8.4) 대기/완료 DM 짝 맞추기 + label 태그 — 네트워크 경로 시뮬레이션 ──
    import time as _time

    sent: list[tuple[str, bool]] = []

    class _FakeTelegramApp:
        @staticmethod
        def _send_telegram(text, silent=False):
            sent.append((text, silent))

    class _FakeResp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"ok": True, "changed": True}

    class _FakeRespErr:
        status_code = 500
        text = "boom"

    class _FakeRequestsSlow:
        @staticmethod
        def post(*a, **k):
            _time.sleep(_WAIT_NOTICE_DELAY_SEC + 0.3)  # 대기 DM 타이머가 반드시 발화하도록
            return _FakeResp()

    class _FakeRequestsSlowErr:
        @staticmethod
        def post(*a, **k):
            _time.sleep(_WAIT_NOTICE_DELAY_SEC + 0.3)
            return _FakeRespErr()

    class _FakeRequestsFast:
        @staticmethod
        def post(*a, **k):
            return _FakeResp()

    _orig_fetch_id_token, _orig_request_cls, _orig_requests = fetch_id_token, Request, requests

    def _with_fakes(requests_stub, fn):
        sys.modules["src.backend.telegram_app"] = _FakeTelegramApp  # type: ignore[assignment]
        os.environ["MAIN_SERVICE_URL"] = "https://fake.example"
        globals()["fetch_id_token"] = lambda *a, **k: "faketoken"
        globals()["Request"] = lambda: None
        globals()["requests"] = requests_stub
        try:
            return fn()
        finally:
            globals()["fetch_id_token"] = _orig_fetch_id_token
            globals()["Request"] = _orig_request_cls
            globals()["requests"] = _orig_requests
            os.environ.pop("MAIN_SERVICE_URL", None)

    result = _with_fakes(_FakeRequestsSlow, lambda: call_write("apply_notice", label="千石ユノ 예고"))
    assert result == {"ok": True, "changed": True}
    assert len(sent) == 2, f"대기 DM + 완료 DM 2건 기대, 받음 {sent}"
    assert sent[0] == ("⏳ 처리 대기 중… [千石ユノ 예고]apply_notice", True), sent[0]
    assert sent[1] == ("✅ 처리 완료 [千石ユノ 예고]apply_notice", True), sent[1]
    print("[PASS] writeclient: 느린 경로 → 대기+완료 DM 짝, label 태그 포함")

    sent.clear()
    _with_fakes(_FakeRequestsSlow, lambda: call_write("merge_rows", action="/ingest 개인예고 아라레"))
    assert sent[0][0].startswith("⏳ 처리 대기 중… [/ingest 개인예고 아라레]merge_rows"), sent[0]
    print("[PASS] writeclient: label 생략 시 args['action'] 폴백")

    sent.clear()
    try:
        _with_fakes(_FakeRequestsSlowErr, lambda: call_write("merge_rows", label="실패케이스"))
        raise AssertionError("HTTP 500 이면 WriteError 를 던져야 함")
    except WriteError:
        pass
    assert len(sent) == 2, sent
    assert sent[1][0].startswith("⚠️ 처리 실패 [실패케이스]merge_rows"), sent[1]
    assert sent[1][1] is False, "실패 DM 은 silent 아니어야 함"
    print("[PASS] writeclient: 실패 시에도 대기/실패 DM 짝 맞추기")

    sent.clear()
    _with_fakes(_FakeRequestsFast, lambda: call_write("merge_rows", label="빠른케이스"))
    assert sent == [], f"2초 안에 끝나면 대기/완료 DM 모두 없어야 함(기존 동작 유지), 받음 {sent}"
    print("[PASS] writeclient: 빠른 경로는 DM 없음(기존 동작 유지)")

    # ── (v3.8.9) 429/503 재시도 테스트 ──
    class _FakeResp429Retry:
        """429를 2번 반환하고 3번째에 200 반환."""
        call_count = 0

        @classmethod
        def json(cls):
            return {"ok": True, "changed": True}

        @classmethod
        def post(cls, *a, **k):
            cls.call_count += 1
            resp = type("Resp", (), {})()
            if cls.call_count <= 2:
                resp.status_code = 429
                resp.text = "Rate limit exceeded"
            else:
                resp.status_code = 200
                resp.text = ""
                resp.json = cls.json
            return resp

    class _FakeResp429All:
        """계속 429 반환."""
        call_count = 0

        @classmethod
        def post(cls, *a, **k):
            cls.call_count += 1
            resp = type("Resp", (), {})()
            resp.status_code = 429
            resp.text = "Rate limit"
            return resp

    class _FakeRespNetErr:
        """네트워크 예외 발생."""
        call_count = 0

        @classmethod
        def post(cls, *a, **k):
            cls.call_count += 1
            raise ConnectionError("네트워크 실패")

    # 테스트용 짧은 상수로 오버라이드
    _orig_backoff = _INITIAL_BACKOFF_SEC, _MAX_BACKOFF_SEC, _BACKOFF_MULTIPLIER, _JITTER_SEC
    _orig_notice_delay = _WAIT_NOTICE_DELAY_SEC
    globals()["_INITIAL_BACKOFF_SEC"] = 0.01
    globals()["_MAX_BACKOFF_SEC"] = 0.05
    globals()["_BACKOFF_MULTIPLIER"] = 2.0
    globals()["_JITTER_SEC"] = 0.05  # 지터도 짧게 설정
    globals()["_WAIT_NOTICE_DELAY_SEC"] = 0.001  # 대기 DM이 발화하도록 매우 짧게 설정

    # 테스트 1: 429→429→200 성공
    sent.clear()
    _FakeResp429Retry.call_count = 0
    result = _with_fakes(_FakeResp429Retry, lambda: call_write("test_retry", label="재시도성공"))
    assert result == {"ok": True, "changed": True}, f"재시도 후 성공 결과 예상, 받음: {result}"
    assert _FakeResp429Retry.call_count == 3, f"3회 시도 예상, 받음: {_FakeResp429Retry.call_count}"
    assert len(sent) == 2, f"재시도 후 성공: 대기 DM + 완료 DM 2건 기대, 받음 {len(sent)}"
    print("[PASS] writeclient: 429 재시도 후 성공")

    # 테스트 2: 계속 429 → 재시도 소진 후 실패
    sent.clear()
    _FakeResp429All.call_count = 0
    try:
        _with_fakes(_FakeResp429All, lambda: call_write("test_all_429", label="재시도소진"))
        raise AssertionError("계속 429이면 WriteError 를 던져야 함")
    except WriteError as e:
        assert "HTTP 429" in str(e), f"HTTP 429 실패 메시지 예상, 받음: {e}"
        assert _FakeResp429All.call_count == 6, f"1+5회 시도=6회 예상, 받음: {_FakeResp429All.call_count}"
    assert len(sent) == 2, f"재시도 소진 후 실패: 대기 DM + 실패 DM 2건 기대, 받음 {len(sent)}"
    assert sent[1][0].startswith("⚠️"), "실패 DM이어야 함"
    print("[PASS] writeclient: 429 재시도 소진 후 실패")

    # 테스트 3: 네트워크 예외 → 재시도 금지
    sent.clear()
    _FakeRespNetErr.call_count = 0
    try:
        _with_fakes(_FakeRespNetErr, lambda: call_write("test_net_err", label="네트워크실패"))
        raise AssertionError("네트워크 예외는 즉시 실패해야 함")
    except WriteError as e:
        assert "네트워크 실패" in str(e), f"네트워크 예외 메시지 예상, 받음: {e}"
        assert _FakeRespNetErr.call_count == 1, f"재시도 없이 1회만 시도, 받음: {_FakeRespNetErr.call_count}"
    print("[PASS] writeclient: 네트워크 예외는 재시도 금지")

    # 원래 상수 복구
    globals()["_INITIAL_BACKOFF_SEC"], globals()["_MAX_BACKOFF_SEC"], globals()["_BACKOFF_MULTIPLIER"], globals()["_JITTER_SEC"] = _orig_backoff
    globals()["_WAIT_NOTICE_DELAY_SEC"] = _orig_notice_delay
