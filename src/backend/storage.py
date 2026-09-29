"""(v4a) store 팩토리 — 로컬 파일(LocalStore) / GitHub(GitHubStore) 선택 + ops 라우팅.

v4a 는 데이터 저장소의 역할을 브랜치로 나눈다(`ref/v4a/v4a_design.md` §6):
  data       — 공개 콘텐츠(preview · notices · tweets + archive). 쓰기 서비스만 쓴다
  ops        — 운영 상태(control · admin_state(재등록 차단 · 편집 락 · undo) · 작업 이력 · 로그인 nonce)
  monitoring — 이벤트 로그 · 스냅샷 · 유실 큐
  raw        — (v4a D19) 스케줄 관련 원문 보존. 로컬 시험판 전용(배포 시 위치는 미결 — 공개 저장소 문제)

기존 코드는 `control.json` · `admin_state.json` 을 data store 에서 읽고 쓴다. 호출부 수십 곳을 고치는 대신
`RoutedStore` 가 이 두 경로만 ops store 로 보낸다(monitor_log._monitor_gh 가 브랜치만 바꿔 쓰던 방식과 같은 발상).

런타임:
  V4A_RUNTIME=local  → LocalStore(<LOCAL_DATA_DIR>/<branch>) (기본 LOCAL_DATA_DIR=_local)
  그 외             → GitHubStore(GITHUB_TOKEN, GITHUB_REPO, <branch>). ops 라우팅은 OPS_BRANCH 가 있을 때만
                      (현행 운영 v3.8.10 동작을 바꾸지 않기 위함).
"""
from __future__ import annotations

import os
from typing import Optional

from .gh_store import GitHubStore

# ops 로 보내는 경로 (data 브랜치에서 빠짐)
OPS_PATHS = frozenset({"control.json", "admin_state.json"})

_ROLE_ENV = {
    "data": ("DATA_BRANCH", "data"),
    "ops": ("OPS_BRANCH", "ops"),
    "monitoring": ("MONITOR_BRANCH", "monitoring"),
    "raw": ("RAW_BRANCH", "raw"),
}


def is_local() -> bool:
    """로컬 시험판 런타임인지 (V4A_RUNTIME=local)."""
    return os.environ.get("V4A_RUNTIME", "").strip().lower() == "local"


def local_root() -> str:
    return os.environ.get("LOCAL_DATA_DIR", "").strip() or "_local"


def branch_for(role: str) -> str:
    env, default = _ROLE_ENV[role]
    return os.environ.get(env, "").strip() or default


class RoutedStore:
    """data store 를 감싸 `OPS_PATHS` 만 ops store 로 보낸다. 나머지 속성은 data store 것을 그대로 노출."""

    def __init__(self, data_store, ops_store):
        self._data = data_store
        self._ops = ops_store

    # monitor_log._monitor_gh · 기존 코드가 보는 속성
    def __getattr__(self, name):
        return getattr(self._data, name)

    def _pick(self, path: str):
        return self._ops if path in OPS_PATHS else self._data

    def read_json(self, path: str):
        return self._pick(path).read_json(path)

    def write_json(self, path: str, data: dict, *, prev_sha: Optional[str], message: str):
        return self._pick(path).write_json(path, data, prev_sha=prev_sha, message=message)

    def read_text(self, path: str):
        return self._pick(path).read_text(path)

    def write_text(self, path: str, text: str, *, prev_sha: Optional[str] = None, message: str):
        return self._pick(path).write_text(path, text, prev_sha=prev_sha, message=message)

    def list_dir(self, path: str):
        return self._data.list_dir(path)

    def with_branch(self, branch: str):
        return with_branch(self._data, branch)

    @property
    def ops(self):
        return self._ops

    @property
    def data(self):
        return self._data


def _raw_store(branch: str):
    if is_local():
        from .local_store import LocalStore

        return LocalStore(local_root(), branch)
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()
    if not token or not repo:
        return None
    return GitHubStore(token, repo, branch)


def make_store(role: str = "data"):
    """역할별 store. data 는 ops 라우팅이 붙는다(로컬이거나 OPS_BRANCH 지정 시). 구성 불가면 None."""
    base = _raw_store(branch_for(role))
    if base is None or role != "data":
        return base
    if is_local() or os.environ.get("OPS_BRANCH", "").strip():
        ops = _raw_store(branch_for("ops"))
        if ops is not None:
            return RoutedStore(base, ops)
    return base


def with_branch(store, branch: str):
    """store 의 브랜치만 바꾼 복제본 (LocalStore · GitHubStore · RoutedStore 공통)."""
    if isinstance(store, RoutedStore):
        return store.with_branch(branch)
    if hasattr(store, "with_branch"):
        return store.with_branch(branch)
    return GitHubStore(store.token, store.repo, branch, session=store.session, timeout=store.timeout)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        os.environ["V4A_RUNTIME"] = "local"
        os.environ["LOCAL_DATA_DIR"] = d
        s = make_store("data")
        assert isinstance(s, RoutedStore), s
        s.write_json("preview.json", {"items": []}, prev_sha=None, message="t")
        s.write_json("control.json", {"paused": False}, prev_sha=None, message="t")
        assert os.path.exists(os.path.join(d, "data", "preview.json"))
        assert os.path.exists(os.path.join(d, "ops", "control.json")), "control.json 은 ops 로"
        assert not os.path.exists(os.path.join(d, "data", "control.json"))
        assert s.read_json("control.json")[0] == {"paused": False}
        m = with_branch(s, "monitoring")
        assert m.branch == "monitoring" and s.branch == "data"
        m.write_text("monitoring/x.jsonl", "a\n", message="t")
        assert os.path.exists(os.path.join(d, "monitoring", "monitoring", "x.jsonl"))
        assert make_store("raw").branch == "raw"
        # 비로컬 + OPS_BRANCH 없음 → 라우팅 없이 GitHubStore (현행 동작 유지)
        os.environ["V4A_RUNTIME"] = ""
        os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPO"] = "tok", "o/r"
        os.environ.pop("OPS_BRANCH", None)
        assert isinstance(make_store("data"), GitHubStore)
    print("[PASS] storage self-test: 로컬 라우팅(control → ops) · 브랜치 복제 · 비로컬 현행 유지")
