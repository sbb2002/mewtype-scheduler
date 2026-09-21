"""Flask 앱: Cloud Run HTTP 진입점.

라우트:
  POST /tick      — Cloud Scheduler (body: {"mode": "baseline"|"light"})
  POST /wake      — Cloud Tasks     (body: {"video_id": "..."})
  POST /write     — mewtype-telegram (body: {"kind": "...", "args": {...}}). GitHub data
                    브랜치 콘텐츠 쓰기 전담 — 이 서비스가 `--concurrency=1
                    --max-instances=1` 이라 여기로 들어오는 모든 요청(이 라우트 포함)이
                    자동으로 직렬화된다. 실제 job 은 `writers.dispatch()`.
  POST /fetch     — mewtype-telegram (body: {"path": "preview.json", "as": "json"|"text"}).
                    GitHub data 브랜치 **읽기** 전담(v3.8.2) — 제어 채널이 GitHub 를 직접 읽지 않고
                    이 라우트로 보내, GitHub 호출이 이 서비스(concurrency=1) 한 곳으로 모인다.
                    응답 {"found": bool, "data"|"text": ..., "sha": ...}. 없으면 found=false(200).
  POST /monitor   — Cloud Scheduler (1일 1회 KST 06:10, body 없음). control.json
                    의 monitor_auto 가 꺼져 있으면 조회 없이 즉시 종료,
                    켜져 있으면 전일자(06:00 KST 경계 기준, 방금 끝난 하루) 리포트 생성 후
                    텔레그램 DM 으로 전송 — 발사 시각이 새 하루 경계 바로 다음이라 "오늘"
                    버킷은 아직 거의 비어 있으므로 명시적으로 전날을 지정한다.
                    (v3.5 — push_monitor/push-monitor 를 대체. 구 이름은 devpapers 참고)
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


def _safe_data_path(path) -> bool:
    """data 저장소 안의 상대 경로만 허용 (빈 값·절대경로·`..`·역슬래시 거부)."""
    return (isinstance(path, str) and bool(path) and len(path) <= 200
            and not path.startswith("/") and "\\" not in path
            and ".." not in path.split("/"))


@app.post("/fetch")
def _fetch():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    body = request.get_json(silent=True) or {}
    path = body.get("path")
    kind = body.get("as", "json")
    if not _safe_data_path(path) or kind not in ("json", "text"):
        return jsonify({"error": "path(str, data 저장소 상대경로) / as(json|text) 필요"}), 400
    try:
        cfg = _cfg()
        gh = GitHubStore(cfg.github_token, cfg.github_repo, cfg.data_branch)
        if kind == "json":
            data, sha = gh.read_json(path)
            return jsonify({"found": data is not None, "data": data, "sha": sha})
        text, sha = gh.read_text(path)
        return jsonify({"found": text is not None, "text": text, "sha": sha})
    except Exception as e:  # noqa: BLE001
        # /write 와 달리 DM 알림은 안 보낸다 — 읽기는 호출량이 많아 버스트 시 알림 폭주. 호출한 쪽이 DM 으로 알린다.
        log.exception("fetch 실패 path=%s", path)
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
        prev_day_kst = (datetime.strptime(today_bucket, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        result = monitor_report.run(
            gh,
            date_kst=prev_day_kst,
            healthchecks_api_key=cfg.healthchecks_api_key,
            healthchecks_uuid=(cfg.healthcheck_url.rsplit("/", 1)[-1] if cfg.healthcheck_url else ""),
            github_token_for_commits=cfg.github_token,
        )
        html = result.pop("html")
        try:
            gh.write_text(
                "monitoring/latest.html", html, prev_sha=None,
                message=f"data: monitor latest {result['date']}",
            )
        except Exception:
            log.exception("monitor: latest.html 커밋 실패 (DM은 계속 진행)")
        notify.Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id).send_document(
            "monitor.html",
            html.encode("utf-8"),
            caption=f"📊 Monitor 자동 리포트 — {result['date']} · {result['events']}건",
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
