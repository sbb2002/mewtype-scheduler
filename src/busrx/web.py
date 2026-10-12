"""자동제어 관리 페이지 — 수신기 프로세스 안에서 **별도 포트**(기본 8789)로 동작한다 (러너 어드민 페이지와 독립).

읽기: 현황 · 에러 · 보고서 · 수정 이력 · 구독 사용량(세션/주간).  쓰기(1차): 수신기 분석 정지/재개, 발신기 발신 정지/재개, 발신 레벨 변경.
로그인: 텔레그램 일회용 링크(5분, 1회) — 서명 키 `ADMIN_SECRET`. 세션 쿠키 HttpOnly+SameSite=Lax, 쓰기 요청은 CSRF 헤더 필수.
접속: 127.0.0.1 과 이 PC 의 Tailscale IP 에만 바인딩.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import flask

from src.bus import envelope as E

from . import pipelines
from .policy import ACTIONS, SEVERITIES, defaults
from .status import build_status, usage_view

log = logging.getLogger("busrx.web")
STATIC = Path(__file__).parent / "web_static"
SESSION_SEC = 12 * 3600
TOKEN_SEC = 300
REPORT_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[A-Za-z0-9._-]+\.md$")
HB_LOST_SEC = 120


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_token(secret: str, now: float, ttl: int = TOKEN_SEC) -> str:
    payload = _b64(json.dumps({"n": secrets.token_hex(8), "exp": int(now) + ttl, "p": "rxlogin"}).encode())
    sig = hmac.new(secret.encode(), f"rxlogin.{payload}".encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(secret: str, tok: str, now: float) -> dict | None:
    try:
        payload, sig = tok.rsplit(".", 1)
        good = hmac.new(secret.encode(), f"rxlogin.{payload}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        d = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return d if d.get("p") == "rxlogin" and d.get("exp", 0) >= now else None
    except Exception:
        return None


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _age(ts: str, now: float) -> float | None:
    try:
        return now - dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except Exception:
        return None


def create_app(rx, cfg, tg, secret: str, base_url: str, now=time.time) -> flask.Flask:
    app = flask.Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    sessions: dict[str, dict] = {}
    used_nonces: set[str] = set()
    last_req = [0.0]
    bus = cfg.bus_dir

    def _session():
        sid = flask.request.cookies.get("rx_sess", "")
        s = sessions.get(sid)
        if not s or s["exp"] < now():
            sessions.pop(sid, None)
            return None
        return s

    @app.before_request
    def _guard():
        path = flask.request.path
        if path in ("/login", "/login/request", "/auth") or path.startswith("/static"):
            return None
        s = _session()
        if s is None:
            if path.startswith("/api/"):
                return flask.jsonify(error="로그인이 필요합니다"), 401
            return flask.redirect("/login")
        if flask.request.method == "POST" and not hmac.compare_digest(flask.request.headers.get("X-CSRF", ""), s["csrf"]):
            return flask.jsonify(error="CSRF 토큰 불일치"), 403
        return None

    @app.after_request
    def _headers(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
        return resp

    # ── 로그인 ───────────────────────────────────────
    @app.get("/login")
    def login_page():
        return flask.send_file(STATIC / "login.html")

    @app.post("/login/request")
    def login_request():
        if now() - last_req[0] < 20:
            return flask.jsonify(ok=False, msg="잠시 후 다시 시도하세요(20초 간격)"), 429
        last_req[0] = now()
        tok = make_token(secret, now())
        sent = tg.send(f"🔐 자동제어 관리 페이지 로그인 링크 (5분 · 1회용)\n{base_url}/auth?t={tok}") if tg.enabled else False
        if not sent:
            return flask.jsonify(ok=False, msg="텔레그램 전송 실패 — 봇 설정 확인"), 502
        return flask.jsonify(ok=True, msg="텔레그램으로 로그인 링크를 보냈습니다")

    @app.get("/auth")
    def auth():
        d = verify_token(secret, flask.request.args.get("t", ""), now())
        if not d or d["n"] in used_nonces:
            return flask.Response("유효하지 않거나 만료된 링크입니다. /login 에서 다시 요청하세요.", 400)
        used_nonces.add(d["n"])
        sid = secrets.token_urlsafe(24)
        sessions[sid] = {"csrf": secrets.token_urlsafe(16), "exp": now() + SESSION_SEC}
        resp = flask.redirect("/")
        resp.set_cookie("rx_sess", sid, max_age=SESSION_SEC, httponly=True, samesite="Lax")
        return resp

    @app.get("/")
    def index():
        return flask.send_file(STATIC / "index.html")

    @app.get("/api/me")
    def me():
        return flask.jsonify(csrf=_session()["csrf"])

    # ── 읽기 API ─────────────────────────────────────
    def _usage_view():
        return usage_view(rx, now())

    @app.get("/api/status")
    def status():
        return flask.jsonify(build_status(rx, cfg, now()))

    @app.get("/api/errors")
    def errors():
        sev = flask.request.args.get("sev", "")
        rows = []
        for sig, m in rx.state["meta"].items():
            if sev and m.get("sev") != sev:
                continue
            st = rx.state["sigs"].get(sig, {})
            rows.append({"sig": sig, **m, "suppressed": st.get("suppressed", 0), "last_call": st.get("last_call", 0)})
        rows.sort(key=lambda r: r.get("last", ""), reverse=True)
        tail = []
        lp = cfg.rx / "log.jsonl"
        if lp.exists() and flask.request.args.get("log"):
            for ln in lp.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]:
                try:
                    tail.append(json.loads(ln))
                except ValueError:
                    pass
            tail.reverse()
        return flask.jsonify(errors=rows[:200], log=tail)

    @app.get("/api/reports")
    def reports():
        out = []
        for p in sorted((cfg.rx / "reports").glob("*.md"), reverse=True)[:200]:
            head = ""
            try:
                head = p.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
            except Exception:
                pass
            out.append({"name": p.name, "title": head, "size": p.stat().st_size,
                        "mtime": dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        return flask.jsonify(reports=out)

    @app.get("/api/report/<name>")
    def report(name: str):
        if not REPORT_RE.match(name):
            return flask.jsonify(error="잘못된 이름"), 400
        p = cfg.rx / "reports" / name
        if not p.is_file():
            return flask.jsonify(error="없음"), 404
        return flask.jsonify(name=name, text=p.read_text(encoding="utf-8"))

    @app.get("/api/fixes")
    def fixes():
        out = []
        for p in sorted((bus / "report" / "inbox").glob("*.json"), reverse=True)[:300]:
            d = _read_json(p) or {}
            if "fix_status" not in d:
                continue
            stem = d["ts"].replace("-", "").replace(":", "") + "_" + d["signature"]
            out.append({k: d.get(k) for k in ("ts", "signature", "patch_summary", "fix_status", "fix_branch", "fix_version", "files_changed",
                                              "lines_added", "lines_deleted", "guard_ok", "applied", "restarted", "commit_before",
                                              "commit_after", "verdict", "severity")} | {"report": stem + ".md"})
        return flask.jsonify(fixes=out)

    @app.get("/api/ctl")
    def ctl():
        out = []
        for p in sorted((bus / "ctl" / "done").glob("*.json"), reverse=True)[:20]:
            d = _read_json(p) or {}
            c = d.get("ctl") or {}
            out.append({"cmd": c.get("cmd"), "args": c.get("args"), "applied": d.get("applied"), "detail": d.get("detail"),
                        "at": d.get("applied_at")})
        pending = [(_read_json(p) or {}).get("cmd") for p in (bus / "ctl" / "inbox").glob("*.json")]
        return flask.jsonify(done=out, pending=pending)

    @app.get("/api/usage")
    def usage():
        return flask.jsonify(usage=_usage_view())

    @app.get("/api/policy")
    def policy_get():
        return flask.jsonify(policy=rx.policy.all(), defaults=defaults(cfg), severities=list(SEVERITIES), actions=ACTIONS,
                             presets={k: v["name"] for k, v in pipelines.presets_view(cfg).items()}, stage=cfg.stage)

    @app.get("/api/runs")
    def runs():
        out = []
        for p in sorted((cfg.rx / "runs").glob("*.json"), reverse=True)[:40]:
            d = _read_json(p)
            if d:
                out.append(d)
        return flask.jsonify(runs=out)

    # ── 쓰기 API (CSRF 필수) ─────────────────────────
    @app.post("/api/policy")
    def policy_set():
        d = flask.request.get_json(silent=True) or {}
        if d.get("reset"):
            return flask.jsonify(ok=True, policy=rx.policy.reset("dashboard"))
        pol, errs = rx.policy.save(d.get("policy") or {}, "dashboard")
        if errs:
            return flask.jsonify(ok=False, errors=errs, policy=pol), 400
        return flask.jsonify(ok=True, policy=pol)

    @app.post("/api/usage/refresh")
    def usage_refresh():
        u, msg = rx.probe_usage()
        return flask.jsonify(usage=dict(u, age=int(now() - u.get("t", now()))) if u else None, msg=msg)

    @app.post("/api/rx/pause")
    def rx_pause():
        on = bool((flask.request.get_json(silent=True) or {}).get("on"))
        return flask.jsonify(ok=True, rx_paused=rx.set_pause(on))

    @app.post("/api/pub/pause")
    def pub_pause():
        d = flask.request.get_json(silent=True) or {}
        args = {"ttl_sec": int(d["ttl_sec"])} if d.get("on") and d.get("ttl_sec") else None
        ok, msg = rx.send_ctl("pause" if d.get("on") else "resume", args)
        return flask.jsonify(ok=ok, msg=msg), (200 if ok else 400)

    @app.post("/api/pub/level")
    def pub_level():
        d = flask.request.get_json(silent=True) or {}
        args = {"level": d.get("level")}
        if d.get("ttl_sec"):
            args["ttl_sec"] = int(d["ttl_sec"])
        ok, msg = rx.send_ctl("set_level", args)
        return flask.jsonify(ok=ok, msg=msg), (200 if ok else 400)

    return app


def _tailscale_ip() -> str:
    try:
        r = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5)
        ip = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
        return ip if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip) else ""
    except Exception:
        return ""


def start_web(rx, cfg, tg):
    """수신기 프로세스 안에서 관리 페이지를 스레드로 띄운다. ADMIN_SECRET 이 없으면 켜지 않는다."""
    from werkzeug.serving import make_server
    secret = os.environ.get("ADMIN_SECRET", "").strip()
    if not secret:
        log.warning("ADMIN_SECRET 이 없어 자동제어 관리 페이지를 켜지 않음")
        return None
    ip = _tailscale_ip()
    base = os.environ.get("RX_WEB_BASE", "").strip().rstrip("/") or f"http://{ip or '127.0.0.1'}:{cfg.web_port}"
    app = create_app(rx, cfg, tg, secret, base)
    servers = []
    ctx = {"secret": secret, "base": base, "servers": servers}
    for host in dict.fromkeys(["127.0.0.1"] + ([ip] if ip else [])):
        try:
            srv = make_server(host, cfg.web_port, app, threaded=True)
        except OSError as e:
            log.warning("관리 페이지 바인딩 실패 %s:%s — %s", host, cfg.web_port, e)
            continue
        threading.Thread(target=srv.serve_forever, name=f"rx-web-{host}", daemon=True).start()
        servers.append(srv)
        log.info("자동제어 관리 페이지: http://%s:%s/", host, cfg.web_port)
    return ctx
