"""`claude -p` 호출 공통부 — 모델 · 도구 · 환경 격리를 한 곳에서 정한다.

모델 배정(운영자 결정 2026-10-12, docs/AUTOFIX.md):
  - 분석 · 명세서 작성 · 검증 · 이중 검토 = Sonnet 5.5 (`claude-sonnet-5-5`)
  - 코드 수정 · 구현 = Haiku 5.5 (`claude-haiku-5-5`)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

MODEL_ANALYSIS = "claude-sonnet-5-5"
MODEL_CODE = "claude-haiku-5-5"

# claude 서브프로세스에 넘기는 환경 변수 — 필요한 것만(GROQ · YOUTUBE · 텔레그램 · GitHub 키 등은 비전달)
_KEEP = ("PATH", "SYSTEMROOT", "SystemRoot", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOME", "TEMP", "TMP",
         "USERNAME", "COMSPEC", "PATHEXT", "WINDIR", "PROGRAMFILES", "PROGRAMDATA", "HOMEDRIVE", "HOMEPATH")


def clean_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k in _KEEP or k.startswith(("ANTHROPIC_", "CLAUDE_"))}
    env.pop("CLAUDECODE", None)  # 중첩 세션 표시는 넘기지 않는다
    if extra:
        env.update(extra)
    return env


def run_claude(cfg, *, model: str, prompt: str, cwd: Path, tools: str, schema: dict | None = None,
               allowed: str = "", disallowed: str = "", add_dirs: tuple = (), budget: float | None = None,
               system: str = "", permission_mode: str = "", timeout: int | None = None
               ) -> tuple[dict | None, float | None, str]:
    """(구조화 결과 dict | None, 비용 추정 USD, 결과 텍스트). 실패는 RuntimeError."""
    cmd = list(cfg.claude_cmd) + ["-p", "--output-format", "json", "--tools", tools, "--no-session-persistence",
                                  "--disable-slash-commands", "--strict-mcp-config",
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
    outer = json.loads(r.stdout)
    if outer.get("is_error"):
        raise RuntimeError(f"claude 오류 응답: {str(outer.get('result'))[:300]}")
    data = outer.get("structured_output")
    text = outer.get("result") or ""
    if schema is not None and not isinstance(data, dict):
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0)) if m else None
    return (data if isinstance(data, dict) else None), outer.get("total_cost_usd"), text
