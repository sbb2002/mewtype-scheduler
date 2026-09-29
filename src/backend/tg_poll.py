"""로컬 Telegram 봇 장기 폴링 (v4a 로컬 판다).

수신 웹훅을 받을 수 없는 로컬 환경에서 getUpdates 로 메시지를 폴링.

run_polling(bot_token, on_update, ...) 함수:
- deleteWebhook 호출해 웹훅 비활성화
- 루프: getUpdates → on_update(각 메시지) → offset 저장
- 네트워크 오류 시 지수 백오프 재시도
- stop_event 설정 시 종료

self-test: python -m src.backend.tg_poll
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 테스트용 백오프 상수 (테스트에서 패치 가능)
_BACKOFF = (1, 2, 4, 8, 16, 30)  # 초 단위, 마지막 값이 상한

_MAX_BACKOFF = 30  # 최대 대기 시간 (초)


def _mask_token(token: str) -> str:
    """토큰을 마스킹해서 로그에 안전하게 기록."""
    if not token or len(token) < 8:
        return "***"
    return token[:4] + "..." + token[-4:]


def run_polling(
    bot_token: str,
    on_update: Callable[[dict], None],
    *,
    stop_event: threading.Event,
    offset_path: Optional[str] = None,
    session=None,
    poll_timeout: int = 50,
) -> None:
    """Telegram API 장기 폴링 루프 (stop_event 설정까지 실행).

    Args:
        bot_token: Telegram bot token. 로그에는 마스킹되어 출력됨.
        on_update: 각 업데이트를 받을 콜백 함수. 예외 발생 시 로그만 남기고 계속.
        stop_event: 이 event가 set될 때까지 실행. 백오프 중 대기 시에도 반응성 있음.
        offset_path: 마지막 offset을 저장할 파일 경로 (str). 없으면 저장 안 함.
        session: requests.Session 객체. 없으면 매 요청마다 새로 생성(mock용).
        poll_timeout: getUpdates 요청 타임아웃(초). 요청 timeout은 poll_timeout+10.

    절차:
    1. deleteWebhook 호출 (결과 에러 무시)
    2. offset_path에서 마지막 offset 로드 (있으면)
    3. stop_event 설정까지 루프:
       - getUpdates: timeout=poll_timeout, allowed_updates=["message"]
       - 각 update마다 on_update 호출 (예외는 로그만)
       - offset = update_id + 1로 갱신 및 저장
       - 네트워크/non-200/ok:false → 로그 + 백오프 (stop_event.wait 사용)
    """
    import requests

    if session is None:
        session = requests.Session()

    api_base = f"https://api.telegram.org/bot{bot_token}"
    masked = _mask_token(bot_token)
    logger.info(f"tg_poll: deleteWebhook 호출 (bot={masked})")

    # Step 1: deleteWebhook
    try:
        url = f"{api_base}/deleteWebhook"
        resp = session.get(url, timeout=10)
        # 에러도 무시하고 로그만
        if resp.status_code != 200:
            logger.warning(f"tg_poll: deleteWebhook {resp.status_code} (무시함)")
    except Exception as e:
        logger.warning(f"tg_poll: deleteWebhook 예외 (무시함): {e}")

    # Step 2: offset 로드
    offset = 0
    if offset_path:
        try:
            if os.path.exists(offset_path):
                with open(offset_path, "r") as f:
                    offset = int(f.read().strip())
                logger.info(f"tg_poll: offset {offset} 로드됨 ({offset_path})")
        except Exception as e:
            logger.warning(f"tg_poll: offset 로드 실패: {e}")

    # Step 3: 루프
    backoff_attempt = 0
    logger.info(f"tg_poll: 폴링 시작 (offset={offset}, timeout={poll_timeout}s)")

    while not stop_event.is_set():
        try:
            # getUpdates 호출
            url = f"{api_base}/getUpdates"
            params = {
                "offset": offset,
                "timeout": poll_timeout,
                "allowed_updates": json.dumps(["message"]),  # JSON 배열로 인코딩
            }
            req_timeout = poll_timeout + 10

            logger.debug(f"tg_poll: getUpdates 호출 (offset={offset})")
            resp = session.get(url, params=params, timeout=req_timeout)

            # 상태 코드 확인
            if resp.status_code != 200:
                logger.warning(
                    f"tg_poll: getUpdates {resp.status_code} {resp.reason} "
                    f"(응답: {resp.text[:200]})"
                )
                # 백오프로 이동
                raise RuntimeError(f"HTTP {resp.status_code}")

            # JSON 파싱
            try:
                data = resp.json()
            except Exception as e:
                logger.warning(f"tg_poll: JSON 파싱 실패: {e}")
                raise RuntimeError(f"JSON parse error: {e}")

            # ok 확인
            if not data.get("ok"):
                logger.warning(f"tg_poll: ok=false (응답: {json.dumps(data)[:200]})")
                # 백오프로 이동
                raise RuntimeError("ok=false")

            # 업데이트 처리
            updates = data.get("result", [])
            if updates:
                logger.debug(f"tg_poll: {len(updates)}개 업데이트 수신")
                backoff_attempt = 0  # 성공 시 리셋

            for update in updates:
                try:
                    on_update(update)
                except Exception as e:
                    logger.exception(f"tg_poll: on_update 콜백 실패 (무시함): {e}")

                # offset 갱신
                update_id = update.get("update_id")
                if update_id is not None:
                    offset = update_id + 1

            # offset 저장 (매 루프마다, 성공했을 때)
            if offset_path and updates:
                try:
                    os.makedirs(os.path.dirname(offset_path), exist_ok=True)
                    with open(offset_path, "w") as f:
                        f.write(str(offset))
                except Exception as e:
                    logger.warning(f"tg_poll: offset 저장 실패: {e}")

        except Exception as e:
            # 네트워크 오류 또는 기타 예외 → 백오프
            wait_time = _BACKOFF[min(backoff_attempt, len(_BACKOFF) - 1)]
            backoff_attempt += 1

            logger.warning(
                f"tg_poll: 오류 (시도 {backoff_attempt}) — {wait_time}초 대기 후 재시도: {e}"
            )

            # stop_event.wait 사용으로 중단에 반응
            if stop_event.wait(wait_time):
                # stop_event가 set됨
                logger.info("tg_poll: stop_event 설정됨 — 백오프 중단")
                break

    logger.info("tg_poll: 폴링 종료")


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # ──────────────────────────────────────────────────────────────
    # Self-test
    # ──────────────────────────────────────────────────────────────

    import tempfile

    # 테스트 1: 두 개 업데이트 수신 후 stop
    print("테스트 1: 두 업데이트 수신...")

    class FakeSess:
        def __init__(self):
            self.call_count = 0
            self.get_calls = []

        def get(self, url, params=None, timeout=None):
            self.call_count += 1
            self.get_calls.append({"url": url, "params": params})

            class FakeResp:
                def __init__(self, data):
                    self.status_code = 200
                    self.reason = "OK"
                    self.text = json.dumps(data)
                    self._data = data

                def json(self):
                    return self._data

            if self.call_count == 1:
                # deleteWebhook 전(실제로는 get이 아니지만 테스트용)
                return FakeResp({"ok": True})
            elif self.call_count == 2:
                # 첫 getUpdates
                return FakeResp(
                    {
                        "ok": True,
                        "result": [
                            {
                                "update_id": 1,
                                "message": {
                                    "message_id": 1,
                                    "text": "hello",
                                },
                            },
                            {
                                "update_id": 2,
                                "message": {
                                    "message_id": 2,
                                    "text": "world",
                                },
                            },
                        ],
                    }
                )
            else:
                # 다음 업데이트가 없으면 stop_event 설정
                import threading

                def set_stop():
                    time.sleep(0.1)
                    stop_event_ref.set()

                threading.Thread(target=set_stop, daemon=True).start()
                return FakeResp({"ok": True, "result": []})

    received_updates = []

    def on_update(update):
        received_updates.append(update)

    stop_event_ref = threading.Event()
    sess = FakeSess()

    # 임시 offset 파일
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        offset_path = f.name
        f.write("0")

    try:
        run_polling(
            "test_token_12345",
            on_update,
            stop_event=stop_event_ref,
            offset_path=offset_path,
            session=sess,
            poll_timeout=1,
        )

        assert len(received_updates) == 2, f"기대: 2개, 실제: {len(received_updates)}"
        assert received_updates[0]["update_id"] == 1
        assert received_updates[1]["update_id"] == 2
        print(f"  ✓ 두 업데이트 수신 완료")

        # offset 저장 확인
        with open(offset_path, "r") as f:
            saved_offset = int(f.read().strip())
        assert saved_offset == 3, f"기대: offset 3, 실제: {saved_offset}"
        print(f"  ✓ offset 저장됨 (3)")
    finally:
        try:
            os.unlink(offset_path)
        except:
            pass

    # 테스트 2: offset 재시작 시 복원
    print("테스트 2: offset 파일에서 재로드...")

    class FakeSess2:
        def __init__(self, initial_offset):
            self.expected_offset = initial_offset
            self.call_count = 0

        def get(self, url, params=None, timeout=None):
            self.call_count += 1

            if self.call_count == 1:
                # deleteWebhook
                class FakeResp:
                    status_code = 200
                    reason = "OK"
                    text = "{}"

                    def json(self):
                        return {"ok": True}

                return FakeResp()

            # getUpdates에서 offset 확인
            if params and params.get("offset") == self.expected_offset:
                pass  # OK
            else:
                raise AssertionError(
                    f"offset 예상: {self.expected_offset}, 받은 params: {params}"
                )

            # stop_event 설정해서 루프 종료
            import threading

            def set_stop():
                time.sleep(0.1)
                stop_event_ref2.set()

            threading.Thread(target=set_stop, daemon=True).start()

            class FakeResp2:
                status_code = 200
                reason = "OK"
                text = '{"ok": true, "result": []}'

                def json(self):
                    return {"ok": True, "result": []}

            return FakeResp2()

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        offset_path2 = f.name
        f.write("42")  # 특정 offset

    try:
        stop_event_ref2 = threading.Event()
        sess2 = FakeSess2(42)

        run_polling(
            "test_token_12345",
            lambda u: None,
            stop_event=stop_event_ref2,
            offset_path=offset_path2,
            session=sess2,
            poll_timeout=1,
        )
        print(f"  ✓ offset 42 에서 재시작")
    finally:
        try:
            os.unlink(offset_path2)
        except:
            pass

    # 테스트 3: on_update 예외가 루프를 멈추지 않음
    print("테스트 3: on_update 예외 무시...")

    exception_count = [0]

    def on_update_with_error(update):
        exception_count[0] += 1
        if exception_count[0] == 1:
            raise ValueError("첫 번째 업데이트 오류")
        # 두 번째는 정상

    class FakeSess3:
        def __init__(self):
            self.call_count = 0

        def get(self, url, params=None, timeout=None):
            self.call_count += 1

            if self.call_count == 1:
                return self._fake_resp({"ok": True})
            elif self.call_count == 2:
                # 두 업데이트 반환
                return self._fake_resp(
                    {
                        "ok": True,
                        "result": [
                            {"update_id": 100, "message": {"text": "1"}},
                            {"update_id": 101, "message": {"text": "2"}},
                        ],
                    }
                )
            else:
                # stop
                import threading

                stop_event_ref3.set()
                return self._fake_resp({"ok": True, "result": []})

        @staticmethod
        def _fake_resp(data):
            class FakeResp:
                status_code = 200
                reason = "OK"
                text = json.dumps(data)

                def json(self):
                    return data

            return FakeResp()

    stop_event_ref3 = threading.Event()
    run_polling(
        "test_token_12345",
        on_update_with_error,
        stop_event=stop_event_ref3,
        session=FakeSess3(),
        poll_timeout=1,
    )

    assert exception_count[0] == 2, f"콜백이 2번 호출되어야 함 (1번째 오류 무시하고 계속)"
    print(f"  ✓ on_update 예외 무시하고 계속")

    # 테스트 4: 네트워크 오류 → 백오프
    print("테스트 4: 네트워크 오류 백오프...")

    class FakeSess4:
        def __init__(self):
            self.call_count = 0

        def get(self, url, params=None, timeout=None):
            self.call_count += 1
            if self.call_count == 1:
                # deleteWebhook (성공)
                return self._fake_resp({"ok": True})
            elif self.call_count <= 3:
                # 1~2번 실패
                raise RuntimeError("네트워크 연결 끊김")
            else:
                # 4번째 성공, stop 설정
                import threading

                stop_event_ref4.set()
                return self._fake_resp({"ok": True, "result": []})

        @staticmethod
        def _fake_resp(data):
            class FakeResp:
                status_code = 200
                reason = "OK"
                text = json.dumps(data)

                def json(self):
                    return data

            return FakeResp()

    # 빠른 테스트를 위해 백오프 패치
    import src.backend.tg_poll as tg_poll_module
    original_backoff = tg_poll_module._BACKOFF
    try:
        tg_poll_module._BACKOFF = (0.01, 0.02, 0.03)  # 매우 짧은 백오프

        stop_event_ref4 = threading.Event()
        run_polling(
            "test_token_12345",
            lambda u: None,
            stop_event=stop_event_ref4,
            session=FakeSess4(),
            poll_timeout=1,
        )
        print(f"  ✓ 네트워크 오류 백오프 + 재시도 완료")
    finally:
        tg_poll_module._BACKOFF = original_backoff

    # 테스트 5: deleteWebhook 호출 확인
    print("테스트 5: deleteWebhook 호출 검증...")

    class FakeSess5:
        def __init__(self):
            self.call_count = 0
            self.first_url = None

        def get(self, url, params=None, timeout=None):
            self.call_count += 1
            if self.call_count == 1:
                self.first_url = url
                class FakeResp:
                    status_code = 200
                    reason = "OK"
                    text = "{}"

                    def json(self):
                        return {"ok": True}

                return FakeResp()
            else:
                import threading

                stop_event_ref5.set()

                class FakeResp2:
                    status_code = 200
                    reason = "OK"
                    text = '{"ok": true, "result": []}'

                    def json(self):
                        return {"ok": True, "result": []}

                return FakeResp2()

    stop_event_ref5 = threading.Event()
    sess5 = FakeSess5()
    run_polling(
        "test_token_abc123xyz",
        lambda u: None,
        stop_event=stop_event_ref5,
        session=sess5,
        poll_timeout=1,
    )

    assert sess5.first_url and "deleteWebhook" in sess5.first_url, (
        f"첫 호출이 deleteWebhook이어야 함, 실제: {sess5.first_url}"
    )
    print(f"  ✓ deleteWebhook 호출됨")

    print("\n✓ 모든 tg_poll 테스트 통과")
