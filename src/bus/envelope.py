"""버스 봉투 — 생성 · 심각도 · ID · 시각 (순수, 외부 의존 없음).

규약: docs/BUS_PROTOCOL.md. 이 모듈은 발신기가 쓴다. 수신기는 이 코드를 몰라도 되고
규약 문서와 docs/bus/schema/*.json 만 보면 된다.
"""
from __future__ import annotations

import datetime as dt
import secrets
import socket
import subprocess
import time
from pathlib import Path

SEVERITIES = ("CRITICAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE")
_RANK = {"CRITICAL": 60, "ERROR": 50, "WARN": 40, "INFO": 30, "DEBUG": 20, "TRACE": 10}

MSG_MAX = 4000
TB_MAX = 8000
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def rank(sev: str) -> int:
    return _RANK[sev]


def new_id(now: float | None = None) -> str:
    """ULID — 시간순 정렬되는 26자 Crockford base32 (48bit ms + 80bit 난수)."""
    t = int((time.time() if now is None else now) * 1000)
    n = (t << 80) | int.from_bytes(secrets.token_bytes(10), "big")
    return "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


def iso(ts: float | None = None) -> str:
    d = dt.datetime.fromtimestamp(time.time() if ts is None else ts, dt.timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


_commit_cache: str | None = None


def git_commit() -> str:
    global _commit_cache
    if _commit_cache is None:
        try:
            root = Path(__file__).resolve().parents[2]
            out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                                 text=True, timeout=3)
            _commit_cache = out.stdout.strip() if out.returncode == 0 else ""
        except Exception:
            _commit_cache = ""
    return _commit_cache


def make_source(env: str, service: str) -> dict:
    src = {"env": env, "service": service, "host": socket.gethostname()[:128]}
    c = git_commit()
    if c:
        src["commit"] = c
    return src


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[: limit - 1] + "…", True


def build_err(*, kind: str, severity: str, message: str, source: dict, logger: str = "",
              traceback: str = "", event: dict | None = None, context: dict | None = None,
              ts: str | None = None, occurrences: int | None = None, first_ts: str | None = None,
              last_ts: str | None = None) -> dict:
    """mew.err/1 봉투 dict. 마스킹(redact)은 호출부가 문자열 입력에 먼저 적용한다 — redacted=True 는 그 표시."""
    msg, t1 = _clip(message, MSG_MAX)
    env: dict = {
        "schema": "mew.err/1", "id": new_id(), "ts": ts or iso(), "source": source,
        "kind": kind, "severity": severity, "message": msg, "redacted": True,
    }
    untrusted = ["message"]
    truncated = t1
    if logger:
        env["logger"] = logger[:200]
    if traceback:
        tb, t2 = _clip(traceback, TB_MAX)
        env["traceback"] = tb
        truncated = truncated or t2
        untrusted.append("traceback")
    if event:
        ev = {"flow": str(event.get("flow", ""))[:64], "result": event.get("result")}
        if event.get("who"):
            ev["who"] = str(event["who"])[:64]
        if event.get("detail"):
            d, t3 = _clip(str(event["detail"]), MSG_MAX)
            ev["detail"] = d
            truncated = truncated or t3
            untrusted.append("event.detail")
        env["event"] = ev
    if context:
        env["context"] = context
        untrusted.append("context")
    if occurrences and occurrences > 1:
        env["occurrences"] = occurrences
        env["first_ts"] = first_ts or env["ts"]
        env["last_ts"] = last_ts or env["ts"]
    if truncated:
        env["truncated"] = True
    env["untrusted"] = untrusted
    return env
