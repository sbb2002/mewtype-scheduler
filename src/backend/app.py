"""Flask 앱: Cloud Run HTTP 진입점.

라우트:
  POST /tick      — Cloud Scheduler (body: {"mode": "baseline"|"light"})
  POST /wake      — Cloud Tasks     (body: {"video_id": "..."})
  POST /write     — mewtype-telegram (body: {"kind": "...", "args": {...}}). GitHub data
                    브랜치 콘텐츠 쓰기 전담 — 이 서비스가 `--concurrency=1
                    --max-instances=1` 이라 여기로 들어오는 모든 요청(이 라우트 포함)이
                    자동으로 직렬화된다. 실제 job 은 `writers.dispatch()`.
  POST /monitor   — Cloud Scheduler (1일 1회 KST 06:10, body 없음). control.json
                    의 monitor_auto 가 꺼져 있으면 조회 없이 즉시 종료,
                    켜져 있으면 전일자(06:00 KST 경계 기준, 방금 끝난 하루) 리포트 생성 후
                    텔레그램 DM 으로 전송 — 발사 시각이 새 하루 경계 바로 다음이라 "오늘"
                    버킷은 아직 거의 비어 있으므로 명시적으로 전날을 지정한다.
                    (v3.5 — push_monitor/push-monitor 를 대체. 구 이름은 devpapers 참고)
                    (v3.8.5 핫픽스) 그날이 매월 1일이면 일간 대신 **전월** `--monthly`
                    리포트로, 1월 1일이면 일간 대신 **전년** `--yearly` 리포트로 대체한다 —
                    /monitor 명령의 `--monthly`(구 `--full`)/`--yearly` 참고.
  GET  /          — 무인증 헬스체크 ("/healthz" 는 GFE 가 가로채므로 루트를 씀)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import lru_cache

from flask import Flask, jsonify, request

from . import handlers, monitor_report, notify, oidc, writers
from .config import load_config
from .control import default_control, get_monitor_auto
from .gh_store import GitHubStore
from .monitor_log import KST, bucket_date_kst

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
    try:
        cfg = _cfg()
        gh = GitHubStore(cfg.github_token, cfg.github_repo, cfg.data_branch)
        return jsonify(writers.dispatch(kind, gh, args))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        log.exception("write 실패 kind=%s", kind)
        _alert(f"/write kind={kind}", e)
        return jsonify({"error": str(e)}), 500


@app.post("/monitor")
def _monitor():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    try:
        cfg = _cfg()
        gh = GitHubStore(cfg.github_token, cfg.github_repo, cfg.data_branch)
        control, _ = gh.read_json("control.json")
        if not get_monitor_auto(control or default_control()):
            return jsonify({"skipped": True, "reason": "monitor_auto off"})

        today_bucket = bucket_date_kst(datetime.now(KST))
        today_date = datetime.strptime(today_bucket, "%Y-%m-%d")
        prev_day_kst = (today_date - timedelta(days=1)).strftime("%Y-%m-%d")

        # (v3.8.5 핫픽스) 매월 1일 = 전월 --monthly, 1월 1일 = 전년 --yearly 로 일간을 대체.
        # anchor를 "그 기간의 마지막 날"로 주면 monitor_report._month_dates/_year_dates가
        # 각각 그 달/그 해 전체를 계산한다(build_report 참고).
        if today_date.month == 1 and today_date.day == 1:
            run_kwargs = {"date_kst": f"{today_date.year - 1}-12-31", "yearly": True}
            label = "연간"
        elif today_date.day == 1:
            run_kwargs = {"date_kst": prev_day_kst, "monthly": True}
            label = "월간"
        else:
            run_kwargs = {"date_kst": prev_day_kst}
            label = "일간"

        result = monitor_report.run(
            gh,
            **run_kwargs,
            healthchecks_api_key=cfg.healthchecks_api_key,
            healthchecks_uuid=(cfg.healthcheck_url.rsplit("/", 1)[-1] if cfg.healthcheck_url else ""),
            github_token_for_commits=cfg.github_token,
        )
        html = result.pop("html")
        filename = result["filename"]
        try:
            # (v3.9) monitoring/latest.html 은 monitoring 브랜치에 쓰기.
            # GitHubStore 는 모듈 상단에서 이미 import 한다 — 여기서 다시 import 하면
            # 파이썬이 이 이름을 _monitor() 전체의 지역 변수로 보게 돼, 함수 앞부분의
            # gh = GitHubStore(...) 가 UnboundLocalError 로 죽는다(실제로 겪은 장애).
            gh_monitor = GitHubStore(cfg.github_token, cfg.github_repo, cfg.monitor_branch)
            gh_monitor.write_text(
                "monitoring/latest.html", html, prev_sha=None,
                message=f"data: monitor latest {result['date']}",
            )
        except Exception:
            log.exception("monitor: latest.html 커밋 실패 (DM은 계속 진행)")
        notify.Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id).send_document(
            filename,
            html.encode("utf-8"),
            caption=f"📊 Monitor 자동 리포트({label}) — {result['date']} · {result['events']}건",
        )
        return jsonify(result)
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
