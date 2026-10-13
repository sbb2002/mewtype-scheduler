"""가드 — 자동 수정이 건드려서는 안 되는 것을 **기계적으로** 확인한다 (프롬프트 규약이 아니라 사후 검사).

필수 확인 항목(운영자 지시 2026-10-12): 원격 main · data 브랜치, Vercel 주소, GCP 배포 서버 URL, 배포판이 쓰는 텔레그램 번호.
변경 크기에는 제한을 두지 않는다 — 대신 파일별 +/− 와 합계를 보고한다.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

# 수정을 허용하는 경로(접두사) — 그 밖은 전부 위반
ALLOWED_PREFIXES = ("src/backend/", "src/collector/")
# 허용 경로 안에서도 건드리지 않는 파일: 운영 자원 접근 · 저장소 선택 · 텔레그램 송수신 · 자기 자신
DENIED_PATHS = (
    "src/bus/", "src/busrx/",
    "src/backend/storage.py", "src/backend/gh_store.py", "src/backend/tasks.py", "src/backend/oidc.py",
    "src/backend/config.py", "src/backend/writeclient.py", "src/backend/local_runner.py",
    "src/backend/tg_poll.py", "src/backend/notify.py",
)
# 디스클레이머 · 법적 문구를 지우는 변경 금지
DISCLAIMER_RE = re.compile(r"(?i)disclaimer|디스클레이머|면책|법률")

# 추가되는 줄에 나타나면 안 되는 운영 자원 (이름, 패턴)
FORBIDDEN_ADDED = [
    ("Vercel 주소", re.compile(r"vercel\.app|mewtype-schduler|api\.vercel\.com", re.I)),
    ("GCP 배포 서버 URL", re.compile(r"\.run\.app|asia-northeast1|mewtype-backend|mewtype-telegram|"
                                     r"cloudtasks|secretmanager|googleapis\.com/(?!youtube)", re.I)),
    ("운영 데이터 저장소", re.compile(r"mewtype-scheduler-data|api\.github\.com|raw\.githubusercontent\.com", re.I)),
    # 문자열 한 덩어리("git push")뿐 아니라 인자 리스트(['git', 'push'])도 잡는다
    ("원격 git 조작", re.compile(r"\bgit[\s'\",\[\]]+(push|remote|fetch|pull)\b|\bgh[\s'\",\[\]]+(pr|api|repo)\b|\bgcloud\b|"
                              r"\bvercel[\s'\",\[\]]+(deploy|--prod)", re.I)),
    ("텔레그램 봇 토큰", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("텔레그램 chat id 리터럴", re.compile(r"(?i)chat_?id[\"']?\s*[:=]\s*[\"']?-?\d{6,}")),
    ("운영 헬스체크", re.compile(r"hc-ping\.com|healthchecks\.io/api", re.I)),
    ("main/data 브랜치 직접 지정", re.compile(r"(?i)(?:branch|ref)\s*=\s*[\"'](?:main|data)[\"']|refs/heads/(?:main|data)\b")),
]
PROTECTED_BRANCHES = ("main", "data")


def _git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {r.stderr.strip()[:200]}")
    return r.stdout


# ── 변경 목록 · 합계 ──────────────────────────────────
def numstat(repo: Path, base: str, head: str = "") -> list[tuple[int, int, str]]:
    """[(추가, 삭제, 경로)] — 바이너리는 (0, 0). head 가 비면 스테이징(index) 대비."""
    args = ["diff", "--numstat", base, head] if head else ["diff", "--cached", "--numstat", base]
    rows = []
    for ln in _git(repo, *args).splitlines():
        a, d, p = ln.split("\t", 2)
        rows.append((int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0, p.strip().strip('"')))
    return rows


def totals(rows) -> tuple[int, int, int]:
    return len(rows), sum(r[0] for r in rows), sum(r[1] for r in rows)


# ── 경로 · 내용 검사 ──────────────────────────────────
def path_violations(paths: list[str]) -> list[str]:
    bad = []
    for p in paths:
        q = p.replace("\\", "/")
        if any(q.startswith(d) for d in DENIED_PATHS):
            bad.append(f"금지 경로 수정: {q}")
        elif not any(q.startswith(a) for a in ALLOWED_PREFIXES):
            bad.append(f"허용 범위 밖 경로 수정: {q}")
    return bad


def added_removed_lines(diff_text: str) -> tuple[list[str], list[str]]:
    add, rem = [], []
    for ln in diff_text.splitlines():
        if ln.startswith("+++") or ln.startswith("---"):
            continue
        if ln.startswith("+"):
            add.append(ln[1:])
        elif ln.startswith("-"):
            rem.append(ln[1:])
    return add, rem


def secret_values(env_file: Path | None = None) -> list[str]:
    vals = [v for k, v in os.environ.items() if re.search(r"(?i)KEY|SECRET|TOKEN|PASSWORD", k) and len(v) >= 8]
    if env_file and env_file.exists():
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in raw and not raw.lstrip().startswith("#"):
                k, v = raw.split("=", 1)
                v = v.split(" #")[0].strip().strip('"').strip("'")
                if re.search(r"(?i)KEY|SECRET|TOKEN|PASSWORD|CHAT_ID", k) and len(v) >= 6:
                    vals.append(v)
    return sorted(set(vals), key=len, reverse=True)


def content_violations(diff_text: str, secrets: list[str]) -> list[str]:
    """추가된 줄의 운영 자원 · 비밀값, 삭제된 줄의 디스클레이머."""
    add, rem = added_removed_lines(diff_text)
    bad = []
    for ln in add:
        for name, pat in FORBIDDEN_ADDED:
            if pat.search(ln):
                bad.append(f"{name} 추가: {ln.strip()[:90]}")
        for s in secrets:
            if s in ln:
                bad.append("비밀값/운영 번호 리터럴이 코드에 추가됨")
                break
    for ln in rem:
        if DISCLAIMER_RE.search(ln):
            bad.append(f"디스클레이머성 문구 삭제: {ln.strip()[:90]}")
    return bad


# ── 새 외부 의존성 금지 — 공급자 교체 · 새 키 요구는 사람이 정할 일 (운영자 지시 2026-10-13) ──
# 수정이 코드에 **없던 외부 호스트**(다른 API 공급자 주소)나 **없던 환경변수 이름**(새 API 키)을 끌어들이면 hard 위반.
# 요금제 · 인증 · 쿼터 문제를 코드로 풀겠다며 공급자를 바꾸는 패치가 키도 없이 적용돼 서비스가 조용히 죽는 것을 막는다.
URL_HOST_RE = re.compile(r"https?://([A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,})(?=[/:?#\s\"'`)>\]}]|$)")
ENV_NAME_RE = re.compile(r"""(?:os\.environ(?:\.get)?\s*[\[(]\s*|os\.getenv\s*\(\s*|getenv\s*\(\s*)["']([A-Za-z][A-Za-z0-9_]{2,})["']""")
SAFE_HOSTS = {"example.com", "example.org", "example.net", "localhost"}  # 시험 · 문서용 예시 주소
SCAN_SUFFIXES = (".py", ".json", ".html", ".md", ".txt", ".sh", ".yml", ".yaml")


def known_externals(root: Path) -> tuple[set[str], set[str]]:
    """기준 스냅샷(수정 전 코드)에 이미 있는 외부 호스트 · 환경변수 이름."""
    hosts: set[str] = set()
    envs: set[str] = set()
    for sub in ("src", "config", "deploy"):
        base = root / sub
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in SCAN_SUFFIXES or "__pycache__" in f.parts:
                continue
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hosts.update(h.lower() for h in URL_HOST_RE.findall(txt))
            envs.update(ENV_NAME_RE.findall(txt))
    return hosts, envs


def external_additions(diff_text: str, known_hosts: set[str], known_envs: set[str]) -> list[str]:
    """추가된 줄에서 기준 코드에 없던 외부 호스트 · 환경변수 이름. 주석만 있는 줄은 보지 않는다(문서 링크)."""
    add, _ = added_removed_lines(diff_text)
    bad: list[str] = []
    seen: set[str] = set()
    for ln in add:
        code = ln.strip()
        if code.startswith("#") or code.startswith("//"):
            continue
        for h in URL_HOST_RE.findall(ln):
            h = h.lower()
            if h not in known_hosts and h not in SAFE_HOSTS and ("host:" + h) not in seen:
                seen.add("host:" + h)
                bad.append(f"새 외부 호스트 추가(공급자 교체·새 API 는 사람이 결정): {h}")
        for e in ENV_NAME_RE.findall(ln):
            if e not in known_envs and ("env:" + e) not in seen:
                seen.add("env:" + e)
                bad.append(f"새 환경변수 이름 추가(새 키가 필요한 변경은 사람이 결정): {e}")
    return bad


# ── 저장소 불변 확인 (수정 전 · 후 스냅샷 비교) ─────────
def env_files_hash(repo: Path) -> str:
    h = hashlib.sha1()
    for name in (".env.local", ".env"):
        p = repo / name
        h.update(name.encode())
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def protected_snapshot(repo: Path) -> dict:
    """main · data 로컬 브랜치, 모든 원격 추적 ref, origin URL, 환경 파일 해시."""
    refs = {}
    out = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)", check=False)
    for ln in out.splitlines():
        name, _, sha = ln.partition(" ")
        if name.startswith("refs/remotes/") or name in tuple(f"refs/heads/{b}" for b in PROTECTED_BRANCHES):
            refs[name] = sha
    urls = _git(repo, "config", "--get-regexp", r"^remote\..*\.(url|pushurl)$", check=False)
    return {"refs": refs, "remote_cfg": urls, "env_hash": env_files_hash(repo)}


def snapshot_diff(before: dict, after: dict) -> list[str]:
    bad = []
    for k in sorted(set(before["refs"]) | set(after["refs"])):
        if before["refs"].get(k) != after["refs"].get(k):
            bad.append(f"보호 ref 변동: {k}")
    if before["remote_cfg"] != after["remote_cfg"]:
        bad.append("원격(remote) 설정이 바뀜")
    if before["env_hash"] != after["env_hash"]:
        bad.append("환경 파일(.env/.env.local) 내용이 바뀜")
    return bad


CHECKED_ITEMS = "원격 main · data 브랜치 · 원격 URL · Vercel 주소 · GCP 서버 URL · 텔레그램 번호/토큰 · 환경 파일 · 디스클레이머 · 새 외부 호스트/환경변수"
