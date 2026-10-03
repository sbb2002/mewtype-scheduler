"""Flask 앱: Cloud Run HTTP 진입점.

라우트:
  POST /tick      — Cloud Scheduler (body: {"mode": "baseline"|"light"})
  POST /wake      — Cloud Tasks     (body: {"video_id": "..."})
  POST /write     — mewtype-telegram (body: {"kind": "...", "args": {...}}). GitHub data
                    브랜치 콘텐츠 쓰기 전담 — 이 서비스가 `--concurrency=1
                    --max-instances=1` 이라 여기로 들어오는 모든 요청(이 라우트 포함)이
                    자동으로 직렬화된다. (v4) 실제 처리는 `apply.handle()`(writers 의 콘텐츠
                    반영 + v4 전용 작업). 접수 서비스의 동기 호출과 Cloud Tasks 적재가 같은 라우트로 온다.
  POST /monitor   — Cloud Scheduler (1일 1회 KST 06:10, body 없음). (v3.8.9) 매일
                    전일자(06:00 KST 경계 기준, 방금 끝난 하루) 스냅샷을 찍어
                    `monitoring/days/`·`monitoring/summary.json` 에 저장하고
                    (`monitor_snapshot.run_daily` — 최초 실행/스케줄러 누락분 백필 포함),
                    `monitoring/latest.html`(웹 monitor 폴백)을 갱신한다. control.json 의
                    monitor_auto 가 켜져 있으면 "오늘의 멤버 현황"만 텍스트 DM 으로 보낸다.
                    스냅샷은 monitor_auto 와 무관(웹 monitor 가 의존). v3.8.8 까지의
                    일간/월간/연간 HTML 리포트 자동 DM 은 폐지 — 전 기간은 웹 monitor 에서,
                    필요하면 /monitor 명령으로 수동 생성.
  GET  /          — 무인증 헬스체크 ("/healthz" 는 GFE 가 가로채므로 루트를 씀)
"""
from __future__ import annotations

import logging
from functools import lru_cache

from flask import Flask, jsonify, request

from . import handlers, notify, oidc
from .config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backend.app")

app = Flask(__name__)


@lru_cache(maxsize=1)
def _cfg():
    # 지연 로드: 최초 배포(SERVICE_URL 미설정) 시 import 단계에서 죽지 않도록.
    return load_config()


def _authorize() -> None:
    cfg = _cfg()
    oidc.verify_request(
        request.headers,
        expected_audience=cfg.service_url,
        expected_sa=cfg.invoker_sa or None,
    )


def _alert(where: str, exc: BaseException) -> None:
    """서버 오류를 Telegram 으로. 실패해도 조용히."""
    try:
        cfg = _cfg()
        notify.Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id).send(
            notify.error_text(where, exc)
        )
    except Exception:  # noqa: BLE001
        log.warning("오류 알림 전송 실패", exc_info=True)


@app.post("/tick")
def _tick():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    mode = (request.get_json(silent=True) or {}).get("mode", "light")
    try:
        return jsonify(handlers.tick(mode))
    except Exception as e:  # noqa: BLE001
        log.exception("tick 실패")
        _alert(f"/tick mode={mode}", e)
        return jsonify({"error": str(e)}), 500


@app.post("/wake")
def _wake():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    video_id = (request.get_json(silent=True) or {}).get("video_id")
    if not video_id:
        return jsonify({"error": "video_id required"}), 400
    try:
        return jsonify(handlers.wake(video_id))
    except Exception as e:  # noqa: BLE001
        log.exception("wake 실패")
        _alert(f"/wake video_id={video_id}", e)
        return jsonify({"error": str(e)}), 500


_WRITE_MAX_ATTEMPTS = 5   # (v4) Cloud Tasks 로 온 /write 작업의 최대 시도 (큐 기본값 100 회까지 가지 않게)


@app.post("/write")
def _write():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    body = request.get_json(silent=True) or {}
    kind = body.get("kind")
    args = body.get("args") or {}
    if not kind:
        return jsonify({"error": "kind required"}), 400
    # (v4) 모든 작업 종류를 적용 처리기(apply.handle)로 — writers 의 콘텐츠 반영 + v4 전용 작업(yt_notif · reconcile ·
    # snapshot · apply_translation). 접수 서비스의 동기 호출(결과 대기)과 Cloud Tasks 적재(apply.submit(wait=False))가
    # 같은 라우트로 온다. Cloud Tasks 는 실패하면 재시도하므로 _WRITE_MAX_ATTEMPTS 번째 시도에서 유실 처리하고 멈춘다.
    from . import apply
    task_name = request.headers.get("X-CloudTasks-TaskName", "")
    try:
        attempt = int(request.headers.get("X-CloudTasks-TaskRetryCount", "0")) + 1
    except ValueError:
        attempt = 1
    is_last = (not task_name) or attempt >= _WRITE_MAX_ATTEMPTS
    meta = {"job_id": task_name or "sync", "attempt": attempt, "is_last": is_last, "queue": "tasks" if task_name else "sync"}
    try:
        return jsonify(apply.handle(kind, args, meta))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        log.exception("write 실패 kind=%s attempt=%s", kind, attempt)
        if task_name and is_last:
            apply.on_dead({"id": task_name, "kind": kind, "args": args, "attempt": attempt}, e)
            return jsonify({"error": str(e), "dead": True}), 200   # 200 → Cloud Tasks 재시도 중단
        if not task_name:
            _alert(f"/write kind={kind}", e)
        return jsonify({"error": str(e)}), 500


@app.post("/monitor")
def _monitor():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    try:
        # (v4a) 본문은 apply.run_snapshot 으로 옮김 — 로컬 시험판의 스냅샷 작업과 같은 코드
        from . import apply
        return jsonify(apply.run_snapshot())
    except Exception as e:  # noqa: BLE001
        log.exception("monitor 실패")
        _alert("/monitor", e)
        return jsonify({"error": str(e)}), 500


@app.get("/")
def _healthz():
    # "/healthz" 는 GFE 가 컨테이너 도달 전에 404 로 가로챈다 → 루트만 노출.
    return "ok", 200


if __name__ == "__main__":
    # 로컬 개발: ALLOW_UNAUTH=1 로 실행
    app.run(host="127.0.0.1", port=8080, debug=True)
