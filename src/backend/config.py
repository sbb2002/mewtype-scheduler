"""Cloud Run 백엔드 환경변수 로드.

모든 값은 환경변수에서 온다. 로컬 개발은 `ALLOW_UNAUTH=1` 로 OIDC 검증을 끄고
나머지 필수 값만 채우면 된다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    github_token: str
    github_repo: str          # "owner/name"
    data_branch: str          # 기본 "data"
    youtube_api_key: str
    gcp_project: str
    gcp_location: str          # Cloud Run / Tasks / Scheduler 공통 리전
    tasks_queue: str
    service_url: str           # 자기 자신의 Cloud Run URL (OIDC audience + Task 타깃)
    invoker_sa: str            # Scheduler/Tasks 가 쓰는 서비스계정 email
    allow_unauth: bool         # 로컬 개발 시 OIDC 검증 skip


_REQUIRED = (
    "GITHUB_TOKEN",
    "GITHUB_REPO",
    "YOUTUBE_API_KEY",
    "GCP_PROJECT",
    "GCP_LOCATION",
    "TASKS_QUEUE",
    "SERVICE_URL",
    "INVOKER_SA",
)


def load_config() -> Config:
    """환경변수를 읽어 Config 를 만든다.

    `ALLOW_UNAUTH` 가 "1" 이 아니면 `_REQUIRED` 전부 있어야 하며, 누락 시 RuntimeError.
    `ALLOW_UNAUTH=1` (로컬)일 때도 실제로 호출되는 경로에 필요한 값은 있어야 하지만,
    여기서는 경고만 하고 통과시킨다 (핸들러가 사용 시점에 실패).
    """
    allow_unauth = os.environ.get("ALLOW_UNAUTH", "").strip() == "1"

    if not allow_unauth:
        missing = [k for k in _REQUIRED if not os.environ.get(k, "").strip()]
        if missing:
            raise RuntimeError(f"필수 환경변수 누락: {', '.join(missing)}")

    return Config(
        github_token=os.environ.get("GITHUB_TOKEN", "").strip(),
        github_repo=os.environ.get("GITHUB_REPO", "").strip(),
        data_branch=os.environ.get("DATA_BRANCH", "data").strip() or "data",
        youtube_api_key=os.environ.get("YOUTUBE_API_KEY", "").strip(),
        gcp_project=os.environ.get("GCP_PROJECT", "").strip(),
        gcp_location=os.environ.get("GCP_LOCATION", "").strip(),
        tasks_queue=os.environ.get("TASKS_QUEUE", "").strip(),
        service_url=os.environ.get("SERVICE_URL", "").strip().rstrip("/"),
        invoker_sa=os.environ.get("INVOKER_SA", "").strip(),
        allow_unauth=allow_unauth,
    )


if __name__ == "__main__":
    os.environ["ALLOW_UNAUTH"] = "1"
    cfg = load_config()
    assert cfg.data_branch == "data"
    assert cfg.allow_unauth is True
    print("config self-test ok:", cfg)
