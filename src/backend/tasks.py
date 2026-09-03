"""Cloud Tasks enqueue: 방송별 wake 태스크 등록.

TaskQueue: Cloud Tasks 큐 래퍼.
_build_task: 순수 함수. task dict 생성 (네트워크 없이, self-test 대상).
"""

import json
import logging
from datetime import datetime, timezone

try:
    from google.cloud import tasks_v2
    from google.protobuf.timestamp_pb2 import Timestamp
    from google.api_core import exceptions as ga_exceptions
except ImportError:
    # 라이브러리 미설치 환경에서 import 시도 — 스모크는 skip 처리
    tasks_v2 = None
    Timestamp = None
    ga_exceptions = None

logger = logging.getLogger(__name__)


def _parse_iso(s: str) -> datetime:
    """ISO 문자열 파싱. 'Z' → '+00:00', tz-aware UTC 반환."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _to_iso(dt: datetime) -> str:
    """datetime → ISO 문자열 ('...Z')."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_task(
    cfg,
    *,
    path: str,
    body: dict,
    name_key: str,
    schedule_time_iso: str,
) -> dict:
    """순수 함수. Cloud Tasks task dict 생성.

    Args:
        cfg: 객체 또는 dict. .project, .location, .queue, .target_url, .invoker_sa 속성/키 필요.
             또는 self (TaskQueue 인스턴스) 전달 가능.
        path: Cloud Run 라우트 ("/wake" 또는 "/tick").
        body: JSON 직렬화할 요청 바디 (예: {"video_id": "..."} 또는 {"mode": "light"}).
        name_key: 태스크 이름 접두 (예: "wake-<video_id>", "tick-light"). 뒤에 "-{분버킷}" 이 붙는다.
        schedule_time_iso: 태스크 실행 시각 (ISO 'Z' 형식).

    Returns:
        tasks_v2.Task 로 변환 가능한 dict.

    bucket = schedule_time epoch초 // 60 (분 버킷) — 같은 이름·같은 분 재시도는 dedupe(AlreadyExists).
    """
    # cfg 에서 필드 추출
    if isinstance(cfg, dict):
        project = cfg["project"]
        location = cfg["location"]
        queue = cfg["queue"]
        target_url = cfg["target_url"]
        invoker_sa = cfg["invoker_sa"]
    else:
        project = cfg.project
        location = cfg.location
        queue = cfg.queue
        target_url = cfg.target_url
        invoker_sa = cfg.invoker_sa

    # queue_path 생성 (tasks_v2 없어도 문자열로만 생성)
    queue_path = f"projects/{project}/locations/{location}/queues/{queue}"

    # schedule_time 파싱 → bucket (분 단위)
    dt = _parse_iso(schedule_time_iso)
    epoch_seconds = int(dt.timestamp())
    bucket = epoch_seconds // 60

    task_name = f"{queue_path}/tasks/{name_key}-{bucket}"

    task_dict = {
        "name": task_name,
        "schedule_time": {"seconds": epoch_seconds},
        "http_request": {
            "http_method": "POST",
            "url": f"{target_url}{path}",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body).encode(),
            "oidc_token": {
                "service_account_email": invoker_sa,
                "audience": target_url,
            },
        },
    }

    return task_dict


class TaskQueue:
    """Cloud Tasks 큐 래퍼. enqueue_wake 메서드로 태스크 등록."""

    def __init__(
        self,
        *,
        project: str,
        location: str,
        queue: str,
        target_url: str,
        invoker_sa: str,
        client: "tasks_v2.CloudTasksClient | None" = None,
    ):
        """
        Args:
            project: GCP 프로젝트 ID.
            location: Cloud Tasks 리전 (예: asia-northeast1).
            queue: 큐 이름.
            target_url: Cloud Run 서비스 베이스 URL (예: https://mewtype-backend-xxx.a.run.app).
            invoker_sa: OIDC 토큰 발급 서비스계정 email.
            client: CloudTasksClient 인스턴스. 미지정 시 자동 생성.
        """
        self.project = project
        self.location = location
        self.queue = queue
        self.target_url = target_url
        self.invoker_sa = invoker_sa

        if client is None:
            if tasks_v2 is None:
                raise RuntimeError(
                    "google-cloud-tasks not installed. "
                    "Install with: pip install google-cloud-tasks"
                )
            self.client = tasks_v2.CloudTasksClient()
        else:
            self.client = client

    def enqueue_wake(self, video_id: str, schedule_time_iso: str) -> str:
        """Cloud Tasks 큐에 방송별 wake 태스크(`POST /wake {video_id}`) 등록.

        Returns: 생성된 task.name (AlreadyExists 시 유추 name).
        Raises: RuntimeError.
        """
        return self._enqueue(
            path="/wake",
            body={"video_id": video_id},
            name_key=f"wake-{video_id}",
            schedule_time_iso=schedule_time_iso,
        )

    def enqueue_tick(self, mode: str, schedule_time_iso: str) -> str:
        """Cloud Tasks 큐에 후속 tick 태스크(`POST /tick {mode}`) 등록.

        방송이 방금 끝났을 때 handlers 가 "곧이어 다른 방송이 시작됐나" 를 3h light tick 을
        기다리지 않고 ~20분 뒤에 한 번 더 훑도록 쓴다. 이름이 `tick-{mode}-{분버킷}` 이라
        한 tick 에서 여러 방송이 끝나도 후속 tick 은 1개로 dedupe 된다.
        """
        return self._enqueue(
            path="/tick",
            body={"mode": mode},
            name_key=f"tick-{mode}",
            schedule_time_iso=schedule_time_iso,
        )

    def _enqueue(self, *, path: str, body: dict, name_key: str, schedule_time_iso: str) -> str:
        queue_path = self.client.queue_path(self.project, self.location, self.queue)
        task_dict = _build_task(
            self, path=path, body=body, name_key=name_key, schedule_time_iso=schedule_time_iso
        )

        if tasks_v2 is None:
            raise RuntimeError("google-cloud-tasks not installed")

        task = tasks_v2.Task(task_dict)
        try:
            response = self.client.create_task(request={"parent": queue_path, "task": task})
            logger.info(f"Enqueued task: {response.name}")
            return response.name
        except ga_exceptions.AlreadyExists:
            inferred_name = task_dict["name"]
            logger.info(f"Task already exists (dedupe): {inferred_name}")
            return inferred_name
        except Exception as e:
            raise RuntimeError(f"Failed to enqueue task: {e}") from e


# Self-test
if __name__ == "__main__":
    import sys

    # Check: google-cloud-tasks 설치 여부
    if tasks_v2 is None:
        print("-- google-cloud-tasks not installed. Skipping smoke test.")
        print("   Install with: pip install google-cloud-tasks google-auth")
        sys.exit(0)

    print("Testing _build_task...")

    # Mock config
    mock_cfg = {
        "project": "test-project",
        "location": "asia-northeast1",
        "queue": "test-queue",
        "target_url": "https://example.com",
        "invoker_sa": "invoker@test-project.iam.gserviceaccount.com",
    }

    def wake_task(cfg, vid, when):
        return _build_task(cfg, path="/wake", body={"video_id": vid},
                           name_key=f"wake-{vid}", schedule_time_iso=when)

    _WHEN = "2026-09-01T12:00:00Z"
    _BUCKET = int(_parse_iso(_WHEN).timestamp()) // 60

    # Test 1: wake 기본 형식 검증
    task = wake_task(mock_cfg, "video123", _WHEN)
    assert task["name"] == (
        "projects/test-project/locations/asia-northeast1/queues/test-queue"
        f"/tasks/wake-video123-{_BUCKET}"
    ), f"Unexpected name: {task['name']}"
    assert task["http_request"]["http_method"] == "POST"
    assert task["http_request"]["url"] == "https://example.com/wake"
    assert task["http_request"]["headers"]["Content-Type"] == "application/json"
    assert json.loads(task["http_request"]["body"].decode()) == {"video_id": "video123"}
    assert task["http_request"]["oidc_token"]["service_account_email"] == "invoker@test-project.iam.gserviceaccount.com"
    assert task["http_request"]["oidc_token"]["audience"] == "https://example.com"
    print("[OK] Basic format check passed")

    # Test 2: schedule_time dict 형식
    assert "seconds" in task["schedule_time"]
    assert isinstance(task["schedule_time"]["seconds"], int)
    assert task["schedule_time"]["seconds"] > 0
    print("[OK] schedule_time format check passed")

    # Test 3: 같은 시각, 다른 video_id → 다른 name (bucket은 같음)
    task2 = wake_task(mock_cfg, "video456", _WHEN)
    assert task2["name"] != task["name"], "Different video_id should produce different name"
    assert "wake-video456" in task2["name"]
    print("[OK] Different video_id produces different task name")

    # Test 4: 다른 시각 → 다른 bucket
    task3 = wake_task(mock_cfg, "video123", "2026-09-01T12:01:00Z")
    assert task3["name"] != task["name"], "Different schedule_time should produce different name"
    print("[OK] Different schedule_time produces different task name")

    # Test 5: tick 태스크 — /tick 라우트, {mode} 바디, tick-{mode}-{bucket} 이름
    tick = _build_task(mock_cfg, path="/tick", body={"mode": "light"},
                       name_key="tick-light", schedule_time_iso=_WHEN)
    assert tick["http_request"]["url"] == "https://example.com/tick"
    assert json.loads(tick["http_request"]["body"].decode()) == {"mode": "light"}
    assert tick["name"].endswith(f"/tasks/tick-light-{_BUCKET}"), tick["name"]
    # 같은 분에 여러 번 → 같은 이름 → Cloud Tasks 가 dedupe
    tick_again = _build_task(mock_cfg, path="/tick", body={"mode": "light"},
                             name_key="tick-light", schedule_time_iso="2026-09-01T12:00:30Z")
    assert tick_again["name"] == tick["name"], "같은 분 tick 은 이름이 같아야(dedupe)"
    print("[OK] tick task format + minute-bucket dedupe")

    # Test 6: TaskQueue 인스턴스를 cfg로 전달
    class MockClient:
        def queue_path(self, project, location, queue):
            return f"projects/{project}/locations/{location}/queues/{queue}"

    tq = TaskQueue(
        project="test-project",
        location="asia-northeast1",
        queue="test-queue",
        target_url="https://example.com",
        invoker_sa="invoker@test-project.iam.gserviceaccount.com",
        client=MockClient(),
    )
    task4 = wake_task(tq, "video789", "2026-09-01T12:00:00Z")
    assert "wake-video789" in task4["name"]
    print("[OK] TaskQueue instance as cfg works")

    print("\n[PASS] All smoke tests passed!")
