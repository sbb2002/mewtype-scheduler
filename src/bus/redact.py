"""비밀값 마스킹 — 봉투에 넣기 전에 문자열에 적용. 수신기도 모델에 넘기기 전 한 번 더 적용해야 한다(이중 방어)."""
from __future__ import annotations

import os
import re

MASK = "***"

# (패턴, 치환) — 순서 중요(URL 쿼리 키를 먼저)
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)([?&;\s](?:key|api_key|apikey|token|access_token|secret|password|x-ingest-secret)=)[^&\s\"')]+"), r"\1" + MASK),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1" + MASK),
    (re.compile(r"AIza[0-9A-Za-z_-]{30,}"), MASK),                       # Google API 키
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), MASK),                       # Groq
    (re.compile(r"\b(?:gh[opsu]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), MASK),  # GitHub
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), MASK),               # 텔레그램 봇 토큰
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), MASK),  # JWT
    (re.compile(r"(?i)(/admin/login\?t=)[A-Za-z0-9._-]+"), r"\1" + MASK),
]

_SECRET_NAME = re.compile(r"(?i)(KEY|SECRET|TOKEN|PASSWORD)")


def _env_secrets() -> list[str]:
    out = []
    for k, v in os.environ.items():
        if _SECRET_NAME.search(k) and len(v) >= 8:
            out.append(v)
    out.sort(key=len, reverse=True)
    return out


def redact(text: str) -> str:
    if not text:
        return text
    for v in _env_secrets():
        if v in text:
            text = text.replace(v, MASK)
    for pat, rep in _PATTERNS:
        text = pat.sub(rep, text)
    return text
