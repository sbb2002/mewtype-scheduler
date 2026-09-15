"""GitHub 커밋/브랜치 조회 유틸 — 원래는 push 활동 대시보드(Push Monitor) 전체를
담고 있었으나, v3.5에서 `/monitor`(monitor_report.py)로 완전히 대체되면서 그
대시보드 코드(categorize/build_dashboard_data/render_html/run 등)는 지웠다.
`_CODE_REPO`/`fetch_commits`/`list_branches`만 monitor_report.py의 Vercel
push count 계산용으로 계속 쓰여서 남겨둔다.

옛 Push Monitor 대시보드 자체의 배경(Vercel Hobby "하루 100회 배포" 한도 사고 등)은
docs/VERSION.md v3.2.2~v3.4.x 항목 참고. 코드는 git 이력(v3.4.14 이전)에 남아있다.

self-test: python -m src.backend.push_monitor
"""
from __future__ import annotations

import requests

# main/devpapers/기타 코드 브랜치가 사는 저장소. v3.4.11에서 `data` 브랜치만
# 별도 저장소(mewtype-scheduler-data)로 옮겨졌고 이쪽은 옮겨지지 않았으므로 고정값으로 둔다.
_CODE_REPO = "sbb2002/mewtype-scheduler"


def fetch_commits(
    token: str, repo: str, branch: str, since_iso: str,
    *, session: "requests.Session | None" = None, per_page: int = 100,
) -> list[dict]:
    """GitHub REST API 로 커밋 이력 조회. [{"branch","sha","date","message"}, ...]."""
    session = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    out: list[dict] = []
    page = 1
    while True:
        resp = session.get(
            f"https://api.github.com/repos/{repo}/commits",
            headers=headers,
            params={"sha": branch, "since": since_iso, "per_page": per_page, "page": page},
            timeout=20,
        )
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        for it in items:
            commit = it.get("commit", {}) or {}
            author = commit.get("author", {}) or {}
            msg = (commit.get("message") or "").split("\n", 1)[0]
            out.append({"branch": branch, "sha": it.get("sha"), "date": author.get("date"), "message": msg})
        if len(items) < per_page:
            break
        page += 1
    return out


def list_branches(
    token: str, repo: str, *, session: "requests.Session | None" = None, per_page: int = 100,
) -> list[str]:
    """저장소의 전체 브랜치 이름 목록."""
    session = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    out: list[str] = []
    page = 1
    while True:
        resp = session.get(
            f"https://api.github.com/repos/{repo}/branches",
            headers=headers, params={"per_page": per_page, "page": page}, timeout=20,
        )
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        out.extend(b["name"] for b in items)
        if len(items) < per_page:
            break
        page += 1
    return out


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    class _Resp:
        def __init__(self, payload):
            self._payload = payload
        def raise_for_status(self):
            pass
        def json(self):
            return self._payload

    class _FakeSess:
        def __init__(self, commits, branches):
            self._commits, self._branches = commits, branches
            self.calls = 0
        def get(self, url, params=None, **kw):
            self.calls += 1
            if url.endswith("/commits"):
                return _Resp(self._commits if params.get("page") == 1 else [])
            return _Resp(self._branches if params.get("page") == 1 else [])

    sess = _FakeSess(
        commits=[{"sha": "abc123", "commit": {"author": {"date": "2026-09-16T00:00:00Z"}, "message": "feat: x\n\nbody"}}],
        branches=[{"name": "main"}, {"name": "devpapers"}],
    )
    commits = fetch_commits("tok", "o/r", "main", "2026-09-15T00:00:00Z", session=sess)
    assert commits == [{"branch": "main", "sha": "abc123", "date": "2026-09-16T00:00:00Z", "message": "feat: x"}], commits
    print("[OK] fetch_commits: 커밋 메시지 첫 줄만, 필드 매핑 정확")

    branches = list_branches("tok", "o/r", session=sess)
    assert branches == ["main", "devpapers"]
    print("[OK] list_branches")

    print("\nSUCCESS: push_monitor.py self-test 통과 (mock)")
