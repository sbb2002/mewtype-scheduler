"""Flask 앱: Cloud Run HTTP 진입점.

라우트:
  POST /tick      — Cloud Scheduler (body: {"mode": "baseline"|"light"})
  POST /wake      — Cloud Tasks     (body: {"video_id": "..."})
  POST /write     — mewtype-telegram (body: {"kind": "...", "args": {...}}). GitHub data
                    브랜치 콘텐츠 쓰기 전담 — 이 서비스가 `--concurrency=1
                    --max-instances=1` 이라 여기로 들어오는 모든 요청(이 라우트 포함)이
                    자동으로 직렬화된다. 실제 job 은 `writers.dispatch()`.
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
from datetime import datetime, timezone
from functools import lru_cache

from flask import Flask, jsonify, request

from . import handlers, monitor_report, monitor_snapshot, notify, oidc, writers
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
        now = datetime.now(KST)
        today_bucket = bucket_date_kst(now)
        now_iso = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # (v3.8.9) 스냅샷은 monitor_auto 와 무관하게 매일 — 웹 monitor(이스터에그)의 전 기간
        # 잔디/지난 날짜 상세가 여기에 의존한다. monitor_auto 는 DM 발송만 좌우.
        snap = monitor_snapshot.run_daily(
            gh, today_bucket=today_bucket, now_iso=now_iso,
            healthchecks_api_key=cfg.healthchecks_api_key,
            healthchecks_uuid=(cfg.healthcheck_url.rsplit("/", 1)[-1] if cfg.healthcheck_url else ""),
            vercel_token=cfg.vercel_token,
        )
        yday = snap["yesterdayDate"]
        result = {"date": yday, "snapshotted": snap["snapshotted"], "dm": False}

        # 폴백 페이지(monitor.html 이 /monitor-live 실패 시 보여줌) — 전날 상세 + 전 기간 잔디.
        if snap["yesterday"] is not None:
            try:
                report = monitor_report.snapshot_report(snap["yesterday"], yday, snap["summary"])
                gh.write_text(
                    "monitoring/latest.html", monitor_report.render_html(report), prev_sha=None,
                    message=f"data: monitor latest {yday}",
                )
            except Exception:
                log.exception("monitor: latest.html 커밋 실패 (DM은 계속 진행)")

        control, _ = gh.read_json("control.json")
        if get_monitor_auto(control or default_control()):
            result["dm"] = notify.Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id).send(
                monitor_snapshot.member_status_text(yday, snap["yesterday"]),
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
