"""Flask 앱: Cloud Run HTTP 진입점.

라우트:
  POST /tick      — Cloud Scheduler (body: {"mode": "baseline"|"light"})
  POST /wake      — Cloud Tasks     (body: {"video_id": "...", "websub"?: {who, title, attempt}} — (v4.5.2) PubSub 알림이 시작한 확인)
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
  POST /websub-renew — Cloud Scheduler (매일, body 없음). (v4.5.0) PubSub(WebSub) 구독 일일 갱신 + 끊긴 구독 점검(`websub.renew`).
  POST /daily     — Cloud Scheduler (매일 KST 06:00, 일일 묶음 잡 `mewtype-daily`, self-reply D6 · 명세 §4-6). 먼저 그날
                    06:10 `/monitor` · 06:20 `/websub-renew` 을 Cloud Tasks(`DAILY_QUEUE`)에 예약하고, 그다음 baseline tick 을 그대로 돈다.
                    예약 이름이 날짜로 고정이라 Scheduler 재시도가 와도 두 번 만들어지지 않는다(`AlreadyExists`).
  GET  /          — 무인증 헬스체크 ("/healthz" 는 GFE 가 가로채므로 루트를 씀)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
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
    body = request.get_json(silent=True) or {}
    video_id = body.get("video_id")
    if not video_id:
        return jsonify({"error": "video_id required"}), 400
    websub = body.get("websub") if isinstance(body.get("websub"), dict) else None   # (v4.5.2) PubSub 알림으로 시작한 확인
    try:
        return jsonify(handlers.wake(video_id, websub=websub))
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


@app.post("/websub-renew")
def _websub_renew():
    """(v4.5.0) PubSub(WebSub) 구독 일일 갱신 — Cloud Scheduler. 멤버 5채널 + 뮤타입 음원 채널을 다시 구독 요청하고(임대 5일),
    지난 허브 검증 기록으로 끊긴 구독을 찾는다. 콜백(허브 검증 · 알림 수신)은 접수 서비스 `mewtype-telegram` 이 받는다."""
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    try:
        import os
        from datetime import datetime, timezone

        from ..collector.config import load_channels
        from . import storage, websub
        from .gh_store import GitHubStore

        cfg = _cfg()
        gh = storage.make_store("data") or GitHubStore(cfg.github_token, cfg.github_repo, cfg.data_branch)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tg = notify.Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id)
        return jsonify(websub.renew(
            gh, now_iso, load_channels(), os.environ.get("WEBSUB_CALLBACK_BASE", "").strip(),
            os.environ.get("WEBSUB_SECRET", "").strip(), send_dm=tg.send,
        ))
    except Exception as e:  # noqa: BLE001
        log.exception("websub-renew 실패")
        _alert("/websub-renew", e)
        return jsonify({"error": str(e)}), 500


_DAILY_KST = timezone(timedelta(hours=9))


def _daily_plan(now_utc: datetime) -> list[tuple[str, str, str]]:
    """(순수, self-test 용) 그날 KST 06:10 · 06:20 의 예약 목록 [(태스크 이름 키, 라우트, 실행 시각 UTC ISO)].
    이름은 날짜 · 시각으로 고정 — 같은 날 재시도하면 같은 이름이 된다(분 버킷도 06:10 · 06:20 이라 고정)."""
    day = now_utc.astimezone(_DAILY_KST).date()
    def at(h: int, m: int) -> str:
        return datetime(day.year, day.month, day.day, h, m, tzinfo=_DAILY_KST).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [("daily-monitor", "/monitor", at(6, 10)), ("daily-websub-renew", "/websub-renew", at(6, 20))]


@app.post("/daily")
def _daily():
    """(self-reply D6 · 명세 §4-6) 일일 묶음 잡 — Scheduler 1개(KST 06:00)가 옛 잡 3개(baseline · monitor · websub-renew)를 대신한다.
    순서: ① 그날 06:10 `/monitor` · 06:20 `/websub-renew` 태스크를 **먼저** 예약(큐 `DAILY_QUEUE`, 재시도 4회) ② baseline tick 을 그대로 실행
    (`/tick {"mode":"baseline"}` 과 같은 코드 · 일시정지 가드 포함). 예약이 실패해도 tick 은 돈다. 실패는 응답 500 과 운영자 알림 1회."""
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    from . import tasks
    cfg = _cfg()
    errors: list[str] = []
    queued: list[str] = []
    queue = os.environ.get("DAILY_QUEUE", "").strip()
    tq = tasks.from_env(queue, target_url=cfg.service_url) if queue else None
    if tq is None:
        errors.append("DAILY_QUEUE · SERVICE_URL 미설정 — 06:10 · 06:20 예약 안 됨")
    else:
        for name, path, when in _daily_plan(datetime.now(timezone.utc)):
            try:
                tq.enqueue_path(path, {}, name, when)
                queued.append(name)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {str(e)[:150]}")
    if errors:
        _alert("/daily 예약 실패", RuntimeError("; ".join(errors)))
    try:
        body = handlers.tick("baseline")
    except Exception as e:  # noqa: BLE001
        log.exception("daily baseline tick 실패")
        _alert("/daily baseline", e)
        return jsonify({"error": str(e), "queued": queued}), 500
    if errors:
        return jsonify({**body, "queued": queued, "error": "; ".join(errors)}), 500
    return jsonify({**body, "queued": queued}), 200


@app.get("/")
def _healthz():
    # "/healthz" 는 GFE 가 컨테이너 도달 전에 404 로 가로챈다 → 루트만 노출.
    return "ok", 200


if __name__ == "__main__":
    # 로컬 개발: ALLOW_UNAUTH=1 로 실행
    app.run(host="127.0.0.1", port=8080, debug=True)
