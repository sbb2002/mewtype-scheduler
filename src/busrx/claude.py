"""`claude -p` 호출 공통부 — 모델 · 도구 · 환경 격리 · 구독 사용량(rate limit) 수집을 한 곳에서 정한다.

모델 배정(운영자 결정 2026-10-12, docs/AUTOFIX.md):
  - 분석 · 명세서 작성 · 검증 · 이중 검토 = Sonnet 5.5 (`claude-sonnet-5-5`)
  - 코드 수정 · 구현 = Haiku 5.5 (`claude-haiku-5-5`)

사용량: `--output-format stream-json --verbose` 의 `rate_limit_event` 에 5시간(세션) · 7일(주간) 사용률(utilization 0~1)과
초기화 시각(resetsAt, epoch)이 실려 온다. 호출마다 모아 두었다가 보고에 붙인다(`USAGE`). 구독 인증(claude.ai 로그인)일 때만 있다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import time
from pathlib import Path

MODEL_ANALYSIS = "claude-sonnet-5-5"
MODEL_CODE = "claude-haiku-5-5"
KST = dt.timezone(dt.timedelta(hours=9))

# claude 서브프로세스에 넘기는 환경 변수 — 필요한 것만(GROQ · YOUTUBE · 텔레그램 · GitHub 키 등은 비전달)
_KEEP = ("PATH", "SYSTEMROOT", "SystemRoot", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOME", "TEMP", "TMP",
         "USERNAME", "COMSPEC", "PATHEXT", "WINDIR", "PROGRAMFILES", "PROGRAMDATA", "HOMEDRIVE", "HOMEPATH")


def clean_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k in _KEEP or k.startswith(("ANTHROPIC_", "CLAUDE_"))}
    env.pop("CLAUDECODE", None)  # 중첩 세션 표시는 넘기지 않는다
    if extra:
        env.update(extra)
    return env


class UsageLog:
    """호출마다 받은 rate_limit_event 를 시간순으로 쌓는다. 값은 0~1 사용률."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def add(self, info: dict) -> None:
        w = (info or {}).get("unifiedWindows") or {}
        five, seven = w.get("five_hour") or {}, w.get("seven_day") or {}
        self.events.append({"t": time.time(), "five": five.get("utilization"), "reset5": five.get("resetsAt"),
                            "seven": seven.get("utilization"), "reset7": seven.get("resetsAt")})
        self.events = self.events[-200:]

    def mark(self) -> int:
        return len(self.events)

    def last(self) -> dict | None:
        return self.events[-1] if self.events else None


USAGE = UsageLog()


def _kst(epoch, with_date: bool) -> str:
    try:
        d = dt.datetime.fromtimestamp(int(epoch), KST)
        return d.strftime("%m-%d %H:%M" if with_date else "%H:%M") + " KST"
    except Exception:
        return "?"


def usage_summary(mark: int, prev: dict | None = None) -> dict | None:
    """mark 이후 호출들의 사용량 요약. prev = 직전 보고 때 저장한 {'five','reset5','t'} (같은 5시간 창이면 그 값을 기준선으로)."""
    evs = [e for e in USAGE.events[mark:] if e.get("five") is not None or e.get("seven") is not None]
    if not evs:
        return None
    first, last = evs[0], evs[-1]
    base = first["five"]
    if prev and prev.get("five") is not None and prev.get("reset5") == last.get("reset5") and time.time() - prev.get("t", 0) < 900:
        base = prev["five"]  # 직전 처리 이후 기준(처리 사이의 다른 사용분도 포함)
    delta = (last["five"] - base) if last.get("five") is not None and base is not None else None
    return {"five": last.get("five"), "reset5": last.get("reset5"), "seven": last.get("seven"), "reset7": last.get("reset7"),
            "delta_five": delta, "calls_seen": len(evs)}


def usage_lines(u: dict | None) -> list[str]:
    out = ["── 사용량(구독) ──"]
    if not u:
        return out + ["사용량 정보 없음 (구독 인증이 아니거나 호출 전 실패)"]
    if u.get("five") is not None:
        s = f"세션(5시간): {u['five'] * 100:.0f}% 사용 · 남음 {100 - u['five'] * 100:.0f}% · 초기화 {_kst(u['reset5'], False)}"
        if u.get("delta_five") is not None:
            s += f" · 이번 처리 {u['delta_five'] * 100:+.0f}%p"
        out.append(s)
    if u.get("seven") is not None:
        out.append(f"주간(7일): {u['seven'] * 100:.0f}% 사용 · 남음 {100 - u['seven'] * 100:.0f}% · 초기화 {_kst(u['reset7'], True)}")
    out.append("(사용률은 같은 계정의 다른 세션 사용분을 포함한 값 · 1%p 단위로 갱신)")
    return out


def run_claude(cfg, *, model: str, prompt: str, cwd: Path, tools: str, schema: dict | None = None,
               allowed: str = "", disallowed: str = "", add_dirs: tuple = (), budget: float | None = None,
               system: str = "", permission_mode: str = "", timeout: int | None = None
               ) -> tuple[dict | None, float | None, str]:
    """(구조화 결과 dict | None, 비용 추정 USD, 결과 텍스트). 실패는 RuntimeError."""
    cmd = list(cfg.claude_cmd) + ["-p", "--output-format", "stream-json", "--verbose", "--tools", tools,
                                  "--no-session-persistence", "--disable-slash-commands", "--strict-mcp-config",
                                  "--max-budget-usd", str(budget if budget is not None else cfg.budget_usd)]
    if model:
        cmd += ["--model", model]
    if allowed:
        cmd += ["--allowedTools", allowed]
    if disallowed:
        cmd += ["--disallowedTools", disallowed]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
    if system:
        cmd += ["--append-system-prompt", system]
    if schema is not None:
        cmd += ["--json-schema", json.dumps(schema)]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout or cfg.timeout_sec, cwd=cwd, env=clean_env(cfg.extra_env))
    if r.returncode != 0:
        raise RuntimeError(f"claude 종료코드 {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
    outer = None
    for ln in r.stdout.splitlines():
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "rate_limit_event":
            USAGE.add(ev.get("rate_limit_info") or {})
        elif ev.get("type") == "result" or ("type" not in ev and ("structured_output" in ev or "result" in ev)):
            outer = ev  # (type 없는 단일 JSON 은 스텁/구버전 호환)
    if outer is None:
        raise RuntimeError(f"claude 결과 이벤트 없음: {r.stdout[-200:]}")
    if outer.get("is_error"):
        raise RuntimeError(f"claude 오류 응답: {str(outer.get('result'))[:300]}")
    data = outer.get("structured_output")
    text = outer.get("result") or ""
    if schema is not None and not isinstance(data, dict):
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0)) if m else None
    return (data if isinstance(data, dict) else None), outer.get("total_cost_usd"), text
