"""Flask 앱: Cloud Run HTTP 진입점.

라우트:
  POST /tick          — Cloud Scheduler (body: {"mode": "baseline"|"light"})
  POST /wake          — Cloud Tasks     (body: {"video_id": "..."})
  POST /push-monitor  — Cloud Scheduler (1일 1회 KST 06:00, body 없음). control.json
                        의 push_monitor_auto 가 꺼져 있으면 조회 없이 즉시 종료,
                        켜져 있으면 tick 실행 후 결과 html 을 텔레그램 DM 으로 전송
                        (v3.4 — 더 이상 GitHub 에 html 을 커밋하지 않음)
  GET  /              — 무인증 헬스체크 ("/healthz" 는 GFE 가 가로채므로 루트를 씀)
"""
from __future__ import annotations

import logging
from functools import lru_cache

from flask import Flask, jsonify, request

from . import handlers, notify, oidc, push_monitor
from .config import load_config
from .control import default_control, get_push_monitor_auto
from .gh_store import GitHubStore

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


@app.post("/push-monitor")
def _push_monitor():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    try:
        cfg = _cfg()
        gh = GitHubStore(cfg.github_token, cfg.github_repo, cfg.data_branch)
        control, _ = gh.read_json("control.json")
        if not get_push_monitor_auto(control or default_control()):
            return jsonify({"skipped": True, "reason": "push_monitor_auto off"})

        result = push_monitor.run(cfg.github_token, cfg.github_repo)
        html = result.pop("html")
        notify.Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id).send_document(
            "push_monitor.html",
            html.encode("utf-8"),
            caption=f"📊 Push Monitor 자동 리포트 — 최근 {result['days']}일치 {result['records']}건",
        )
        return jsonify(result)
    except Exception as e:  # noqa: BLE001
        log.exception("push-monitor 실패")
        _alert("/push-monitor", e)
        return jsonify({"error": str(e)}), 500


@app.get("/")
def _healthz():
    # "/healthz" 는 GFE 가 컨테이너 도달 전에 404 로 가로챈다 → 루트만 노출.
    return "ok", 200


if __name__ == "__main__":
    # 로컬 개발: ALLOW_UNAUTH=1 로 실행
    app.run(host="127.0.0.1", port=8080, debug=True)
