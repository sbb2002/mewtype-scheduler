"""(v4a) 로컬 시험판 러너 — 운영자 로컬 PC(24시간)에서 v4a 전체를 한 프로세스로 돌린다.

    python -m src.backend.local_runner            # 저장소 루트에서. .env.local 을 읽는다
    python -m src.backend.local_runner --check    # 설정만 점검하고 종료

v4a 구성 요소 → 이 프로세스 (`ref/v4a/v4a_impl_plan.md` §1)
  접수 서비스       Flask 앱 (telegram_app 라우트 /ingest · /telegram · /monitor-live + /admin)
  쓰기 서비스       스레드 q-apply  — 적용 큐 워커. data 를 쓰는 유일한 스레드
  가공 큐           스레드 q-enrich — 번역 수집(읽기 + LLM) → 적용 큐로 넘김
  정기 reconcile 잡 · 스냅샷 잡   스레드 scheduler — 10분 · 매일 06:00 JST · 06:10 KST 에 적용 큐 적재
  Telegram webhook  스레드 tg-poll — 로컬 봇 getUpdates → 같은 /telegram 처리
  raw CDN · 프론트  같은 Flask 앱: / (src/frontend) · /data/* (_local/data)

바인딩: 127.0.0.1 + LOCAL_BIND(비우면 이 기기의 `tailscale ip -4` 자동 감지), 포트 LOCAL_PORT(기본 8787).
외부 인터넷 인바운드는 필요 없다(폰 → Tailscale → 이 PC, 나머지는 전부 이 PC 에서 나가는 연결).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("backend.local_runner")

ROOT = Path(__file__).resolve().parents[2]          # 저장소 루트
FRONTEND = ROOT / "src" / "frontend"
_DATA_FILES = {"preview.json", "notices.json", "tweets.json"}
JST = timezone(timedelta(hours=9))

_DEFAULTS = {
    "V4A_RUNTIME": "local",
    "ALLOW_UNAUTH": "1",          # 로컬: Cloud Run OIDC 검증 경로를 쓰지 않음(/admin 은 자체 인증)
    "LOCAL_DATA_DIR": str(ROOT / "_local"),
    "LOCAL_PORT": "8787",
}
_REQUIRED = ("YOUTUBE_API_KEY", "INGEST_SECRET", "ADMIN_SECRET")
_RECOMMENDED = ("GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def load_env_file(path: Path) -> list[str]:
    """KEY=VALUE 줄을 읽어 os.environ 에 없을 때만 넣는다(셸에서 준 값이 우선). 읽은 키 목록 반환."""
    keys = []
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
        keys.append(k)
    return keys


def detect_tailscale_ip() -> str:
    """이 기기의 Tailscale IPv4 (`tailscale ip -4`). CLI 가 PATH 에 없으면 OS 기본 설치 경로도 본다. 못 찾으면 ""."""
    import shutil
    import subprocess

    cands = [shutil.which("tailscale"), str(Path("C:/Program Files/Tailscale/tailscale.exe")),
             "/Applications/Tailscale.app/Contents/MacOS/Tailscale", "/usr/bin/tailscale"]
    for exe in [c for c in cands if c and Path(c).exists()]:
        try:
            out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=10).stdout
        except Exception:  # noqa: BLE001
            continue
        ip = next((l.strip() for l in out.splitlines() if l.strip().startswith("100.")), "")
        if ip:
            return ip
    return ""


def check_config() -> list[str]:
    """필수 설정 누락 목록. 권장 값 누락은 경고만."""
    missing = [k for k in _REQUIRED if not os.environ.get(k, "").strip()]
    for k in _RECOMMENDED:
        if not os.environ.get(k, "").strip():
            log.warning("권장 설정 없음: %s (해당 기능 비활성)", k)
    if os.environ.get("TELEGRAM_BOT_TOKEN") and not os.environ.get("TELEGRAM_WEBHOOK_SECRET"):
        # 폴링 → /telegram 전달 시 헤더로 쓰는 값. 로컬 전용이라 없으면 만들어 쓴다.
        import secrets
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = secrets.token_hex(16)
    return missing


# ── 큐 ────────────────────────────────────────────────────────────────────────

def start_queues():
    from . import apply, enrich
    from .jobqueue import LocalQueue

    qdir = Path(os.environ["LOCAL_DATA_DIR"]) / "queue"
    qdir.mkdir(parents=True, exist_ok=True)
    q_apply = LocalQueue("apply", apply.handle, persist_path=str(qdir / "apply.json"), max_attempts=5,
                         backoff_sec=(2, 5, 15, 30, 60), on_done=apply.on_done, on_dead=apply.on_dead)
    q_enrich = LocalQueue("enrich", enrich.handle, persist_path=str(qdir / "enrich.json"), max_attempts=3,
                          backoff_sec=(30, 120, 300))
    apply.set_queue(q_apply)
    enrich.set_queue(q_enrich)
    q_apply.start()
    q_enrich.start()
    return q_apply, q_enrich


# ── 정기 잡 (Cloud Scheduler 대응) ────────────────────────────────────────────

def next_fire_times(now: datetime) -> dict[str, datetime]:
    """다음 정기 실행 시각(UTC). light=10분 격자 · baseline=매일 06:00 JST · snapshot=매일 06:10 KST(=JST)."""
    now = now.astimezone(timezone.utc)
    light = (now.replace(second=0, microsecond=0) + timedelta(minutes=10 - now.minute % 10))
    def _daily(h, m):
        t = now.astimezone(JST).replace(hour=h, minute=m, second=0, microsecond=0)
        if t <= now.astimezone(JST):
            t += timedelta(days=1)
        return t.astimezone(timezone.utc)
    return {"light": light, "baseline": _daily(6, 0), "snapshot": _daily(6, 10)}


def scheduler_loop(stop: threading.Event) -> None:
    """정기 잡을 적용 큐에 적재 — 실행 자체는 q-apply 가 한다(정기 reconcile 도 작업과 한 줄로 선다)."""
    from . import apply

    apply.enqueue_reconcile(mode="baseline")          # 기동 직후 1회 전체 확인(아바타 포함)
    while not stop.is_set():
        now = datetime.now(timezone.utc)
        fires = next_fire_times(now)
        kind, when = min(fires.items(), key=lambda kv: kv[1])
        if stop.wait(max(1.0, (when - now).total_seconds())):
            break
        iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")
        if kind == "snapshot":
            apply.submit("snapshot", {}, wait=False, name=f"snapshot-{iso[:10]}")
        else:
            apply.enqueue_reconcile(mode=kind, run_at_iso=iso)
        log.info("scheduler: %s 적재 @ %s", kind, iso)


# ── Flask 앱 ─────────────────────────────────────────────────────────────────

def build_app():
    from flask import abort, send_from_directory

    from . import admin_api, admin_web, storage, telegram_app

    app = telegram_app.app
    if app is None:
        raise RuntimeError("Flask 미설치 — pip install flask")

    app.register_blueprint(admin_web.create_blueprint(
        api=admin_api, ops_store=storage.make_store("ops"), secret=os.environ["ADMIN_SECRET"]))

    data_dir = Path(os.environ["LOCAL_DATA_DIR"]) / storage.branch_for("data")

    def _index():
        return send_from_directory(FRONTEND, "index.html")

    # 기존 "/" (Cloud Run 헬스체크) 뷰를 프론트 index 로 교체 — 같은 경로 규칙을 둘 만들지 않는다
    for rule in app.url_map.iter_rules():
        if rule.rule == "/":
            app.view_functions[rule.endpoint] = _index

    @app.get("/data/<path:name>", endpoint="lr_data")
    def _data(name: str):
        if name not in _DATA_FILES:
            abort(404)
        resp = send_from_directory(data_dir, name, max_age=0)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/healthz-local", endpoint="lr_health")
    def _health():
        from . import apply, enrich
        return {"ok": True, "apply_pending": len(apply.pending()), "enrich_pending": len(enrich.pending())}

    @app.get("/<path:name>", endpoint="lr_static")
    def _static(name: str):
        # 프론트 정적 파일(css · js · assets · monitor.html). /ingest 등 기존 라우트가 우선한다.
        target = (FRONTEND / name).resolve()
        if FRONTEND.resolve() not in target.parents or not target.is_file():
            abort(404)
        return send_from_directory(FRONTEND, name)

    return app


def start_tg_poll(app, stop: threading.Event):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN 없음 — 텔레그램 명령 수신 비활성")
        return None
    from . import tg_poll

    # 안전장치: 폴링은 시작할 때 deleteWebhook 을 부른다. 운영 봇 토큰을 넣으면 운영 webhook 이 지워져
    # 운영 텔레그램 명령이 멎는다 — 웹훅이 걸려 있는 봇이면 건드리지 않고 폴링을 거부한다(로컬 전용 봇만 허용).
    try:
        import requests
        info = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10).json()
        hook = ((info or {}).get("result") or {}).get("url") or ""
    except Exception as e:  # noqa: BLE001
        log.error("getWebhookInfo 실패(%s) — 안전을 위해 텔레그램 폴링을 시작하지 않음", e)
        return None
    if hook:
        log.error("이 봇에는 webhook 이 걸려 있다(%s…) — 운영 봇으로 보여 폴링을 거부. 로컬 전용 봇 토큰을 쓰세요",
                  hook[:40])
        return None

    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    client = app.test_client()

    def _on_update(update: dict) -> None:
        client.post("/telegram", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": secret})

    th = threading.Thread(target=tg_poll.run_polling, name="tg-poll", daemon=True, kwargs=dict(
        bot_token=token, on_update=_on_update, stop_event=stop,
        offset_path=str(Path(os.environ["LOCAL_DATA_DIR"]) / "queue" / "tg_offset.txt")))
    th.start()
    return th


def serve(app, stop: threading.Event):
    from werkzeug.serving import make_server

    port = int(os.environ["LOCAL_PORT"])
    hosts = ["127.0.0.1"]
    bind = os.environ.get("LOCAL_BIND", "").strip()
    if bind and bind not in hosts:
        hosts.append(bind)
    servers = []
    for h in hosts:
        try:
            srv = make_server(h, port, app, threaded=True)
        except OSError as e:
            log.error("바인딩 실패 %s:%s — %s (Tailscale 이 꺼져 있으면 이 주소가 없다)", h, port, e)
            continue
        threading.Thread(target=srv.serve_forever, name=f"http-{h}", daemon=True).start()
        servers.append(srv)
        log.info("listening http://%s:%s", h, port)
    return servers


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="mewtype v4a 로컬 시험판 러너")
    ap.add_argument("--env", default=str(ROOT / ".env.local"), help="환경 파일 (기본 .env.local)")
    ap.add_argument("--check", action="store_true", help="설정만 점검하고 종료")
    ap.add_argument("--no-scheduler", action="store_true", help="정기 잡 끄기 (시나리오 재생용)")
    ap.add_argument("--no-telegram", action="store_true", help="텔레그램 폴링 끄기")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(threadName)s %(levelname)s %(name)s %(message)s")
    load_env_file(Path(args.env))
    for k, v in _DEFAULTS.items():
        os.environ.setdefault(k, v)
    if not os.environ.get("LOCAL_BIND", "").strip():
        ip = detect_tailscale_ip()
        if ip:
            os.environ["LOCAL_BIND"] = ip
            log.info("Tailscale IP 자동 감지: %s", ip)
        else:
            log.warning("Tailscale IP 를 못 찾음 — 127.0.0.1 에만 바인딩(폰에서 접속 불가). Tailscale 로그인 확인 또는 LOCAL_BIND 지정")
    log.info("접속 주소: http://%s:%s/  (관리 페이지 링크 기준 %s)", os.environ.get("LOCAL_BIND") or "127.0.0.1",
             os.environ["LOCAL_PORT"], os.environ.get("ADMIN_BASE_URL") or "LOCAL_BIND")
    missing = check_config()
    if missing:
        log.error("필수 설정 누락: %s — %s 에 넣으세요", ", ".join(missing), args.env)
        return 2
    log.info("V4A_RUNTIME=%s LOCAL_DATA_DIR=%s", os.environ["V4A_RUNTIME"], os.environ["LOCAL_DATA_DIR"])
    if args.check:
        return 0

    stop = threading.Event()
    start_queues()
    app = build_app()
    servers = serve(app, stop)
    if not servers:
        return 3
    if not args.no_scheduler:
        threading.Thread(target=scheduler_loop, args=(stop,), name="scheduler", daemon=True).start()
    if not args.no_telegram:
        start_tg_poll(app, stop)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log.info("종료 중…")
    finally:
        stop.set()
        for s in servers:
            s.shutdown()
        from . import apply, enrich
        for q in (apply._q, enrich._q):
            if q is not None:
                q.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
