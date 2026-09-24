"""모니터링 이벤트 로그 — monitoring 브랜치에 하루 1개 JSONL로 append.

2026-09-16 세션에서 합의한 스키마(1단계 정의 → 목업 UI 검증 → 2단계 스키마 확정)를
그대로 구현한다. 공통 필드 ts/flow/result/who/detail + 흐름별 추가 필드(kwargs로 받아
그대로 실어 보냄) — CSV처럼 모든 흐름이 같은 컬럼을 가질 필요가 없어 JSONL을 쓴다.

result 는 ok/degraded/err 셋 중 하나 — 성공/실패로 미리 뭉치지 않고 각 파이프라인이
실제로 반환한 raw mode/상태(detail)는 그대로 두되, 필터링용으로 이 3톤만 별도 태깅한다.

파일: monitoring/events-YYYY-MM-DD.jsonl (KST 날짜 기준 — 대시보드 "하루" 경계와 맞춤).
백엔드 상태(4색)는 여기서 기록하지 않는다 — healthchecks.io API에서 그때그때 조회.

(v3.9) data 브랜치 머리(HEAD)를 모니터 로그 커밋이 계속 밀어내는 문제를 해결하려
log_event/log_events 는 MONITOR_BRANCH 로 자동 전환한다.

self-test: python -m src.backend.monitor_log
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 2026-09-16 세션 핫픽스: 멤버들이 자정을 넘겨 방송하는 경우가 흔해서, "하루" 경계를
# KST 00:00 이 아니라 06:00(마지막 baseline tick 시각과 동일)으로 옮긴다 — 00:00~05:59
# 사이 이벤트는 전날 파일에 묶인다. monitor_report.py 도 이 경계로 리포트를 자른다.
DAY_START_HOUR = 6

RESULT_OK = "ok"
RESULT_DEGRADED = "degraded"
RESULT_ERR = "err"
_VALID_RESULTS = {RESULT_OK, RESULT_DEGRADED, RESULT_ERR}

# (v3.9) GitHub Contents API 409 충돌 재시도 설정
_CONFLICT_RETRY_COUNT = 5  # 최대 재시도 횟수
_CONFLICT_RETRY_BASE_MS = 500  # 기본 대기(밀리초): 0.5s → 1s → 2s → 4s
_CONFLICT_RETRY_JITTER_MAX_MS = 300  # 지터 상한(밀리초)


def bucket_date_kst(now: "str | datetime") -> str:
    """now(ISO 'Z' 문자열 또는 tz-aware datetime) → 06:00 KST 경계 기준 날짜(YYYY-MM-DD)."""
    dt = datetime.fromisoformat(now.replace("Z", "+00:00")) if isinstance(now, str) else now
    return (dt.astimezone(KST) - timedelta(hours=DAY_START_HOUR)).strftime("%Y-%m-%d")


def event_path(now_iso: str) -> str:
    """now_iso(UTC 'Z') → 오늘자 이벤트 로그 경로. 날짜는 06:00 KST 경계 기준(대시보드 "하루"와 일치)."""
    return f"monitoring/events-{bucket_date_kst(now_iso)}.jsonl"


def _monitor_gh(gh):
    """모니터 로그 전용 store — data 브랜치 HEAD 경합을 피하려 별도 브랜치에 쓴다.

    gh(GitHubStore)를 받아 branch만 monitoring 으로 교체한 복제본을 반환.
    MONITOR_BRANCH 환경변수로 커스터마이즈 가능(기본 "monitoring").

    mock store(attribute 없음)는 원래 gh를 반환해 self-test 호환성 유지.
    """
    from .gh_store import GitHubStore

    # getattr로 속성이 없을 때 None을 반환 — mock store 대비
    if not hasattr(gh, "branch"):
        return gh

    branch = os.environ.get("MONITOR_BRANCH", "monitoring").strip() or "monitoring"
    # 이미 monitoring 브랜치면 그대로 반환 (불필요한 복제 방지)
    if branch == getattr(gh, "branch", None):
        return gh

    # 브랜치만 교체한 새 GitHubStore 반환
    return GitHubStore(gh.token, gh.repo, branch, session=gh.session, timeout=gh.timeout)


def log_events(gh, now_iso: str, events: list[dict]) -> None:
    """gh(GitHubStore)로 오늘자 이벤트 로그에 여러 줄 append(배치).

    빈 리스트면 GitHub을 건드리지 않고 반환.
    각 원소는 {"flow", "result", "who"?, "detail"?, ...추가필드}.
    result는 ok/degraded/err 검증. ConflictError는 기존과 같은 2회 재시도.
    로그는 monitoring 브랜치에 append되므로 data 브랜치 쓰기와 충돌하지 않는다.
    커밋 메시지: n==1 이면 "data: monitor {flow} {now_iso}",
                n>1 이면 "data: monitor {첫 flow}(+{n-1}) {now_iso}"
    """
    from .gh_store import ConflictError

    if not events:
        return

    # 모든 이벤트의 result 검증
    for ev in events:
        result = ev.get("result")
        if result not in _VALID_RESULTS:
            raise ValueError(f"result must be one of {_VALID_RESULTS}, got {result!r}")

    # 줄 생성 — 각 줄을 {"ts": now_iso, "who": "", "detail": "", **ev} 로 만들어
    # 기존 log_event 줄 형식(ts/who/detail 항상 존재)과 같게 한다.
    # 원소에 ts가 있으면 그 값이 우선(현재 동작 유지).
    path = event_path(now_iso)
    lines = []
    for ev in events:
        ts = ev.get("ts") or now_iso
        who = ev.get("who", "")
        detail = ev.get("detail", "")
        # ts/who/detail 제외한 나머지 필드들
        extra = {k: v for k, v in ev.items() if k not in ("ts", "who", "detail")}
        line = json.dumps(
            {"ts": ts, "who": who, "detail": detail, **extra},
            ensure_ascii=False, sort_keys=True,
        )
        lines.append(line)

    # 커밋 메시지 생성
    first_flow = events[0].get("flow", "unknown")
    if len(events) == 1:
        message = f"data: monitor {first_flow} {now_iso}"
    else:
        message = f"data: monitor {first_flow}(+{len(events) - 1}) {now_iso}"

    # monitoring 브랜치 전용 store (브랜치만 교체)
    monitor_gh = _monitor_gh(gh)

    # 한 번 읽고 모든 줄을 이어붙여 한 번 쓰기, 충돌 시 5회까지 재시도
    for attempt in range(_CONFLICT_RETRY_COUNT):
        text, sha = monitor_gh.read_text(path)
        new_text = (text or "") + "\n".join(lines) + "\n"
        try:
            monitor_gh.write_text(path, new_text, prev_sha=sha, message=message)
            return
        except ConflictError as e:
            if attempt == _CONFLICT_RETRY_COUNT - 1:
                raise
            # 지수 백오프 + 지터
            wait_ms = (_CONFLICT_RETRY_BASE_MS * (2 ** attempt) +
                       random.randint(0, _CONFLICT_RETRY_JITTER_MAX_MS))
            logger.warning("monitor_log: 배치 충돌(%d/%d) — %dms 후 재시도: %s",
                          attempt + 1, _CONFLICT_RETRY_COUNT, wait_ms, e)
            time.sleep(wait_ms / 1000.0)


def log_event(
    gh, now_iso: str, flow: str, result: str, *, who: str = "", detail: str = "", **extra
) -> None:
    """gh(GitHubStore, data 저장소용)로 오늘자 이벤트 로그에 한 줄 append.

    실패(네트워크 오류 등)해도 예외를 삼키지 않는다 — 호출부가 이미 각자 try/except 로
    주 로직과 분리해뒀으므로(예: telegram 알림 실패가 tick을 막지 않듯) 그 관례를 따른다.
    ConflictError(다른 실행이 같은 파일에 동시에 append)는 최신 내용을 다시 읽어 2회까지 재시도.
    """
    log_events(gh, now_iso, [
        {"ts": now_iso, "flow": flow, "result": result, "who": who, "detail": detail, **extra}
    ])


# ── 유실 원문 큐 (monitoring 브랜치, 직렬화 창구 우회) ──
LOST_QUEUE_PATH = "monitoring/lost_queue.json"
_LOST_QUEUE_MAX = 50  # 상한 50건


def push_lost(gh, item: dict) -> None:
    """유실 원문 큐에 한 건 적재 — DM 발송 실패 시에도 예외 안 던짐.

    모니터링 브랜치에 저장하므로 data 브랜치 쓰기와 충돌하지 않음.
    409 충돌(ConflictError)만 최대 5회 지수 백오프 재시도. 다른 예외는 1회.
    """
    from .gh_store import ConflictError

    monitor_gh = _monitor_gh(gh)

    for attempt in range(_CONFLICT_RETRY_COUNT):
        try:
            q, sha = monitor_gh.read_json(LOST_QUEUE_PATH)
            pending = list((q or {}).get("pending", []))
            pending.append(item)
            # 상한 초과면 오래된 것부터 버림
            pending = pending[-_LOST_QUEUE_MAX:]
            monitor_gh.write_json(
                LOST_QUEUE_PATH, {"pending": pending},
                prev_sha=sha, message=f"data: lost_queue += {item.get('ts', 'unknown')}",
            )
            return
        except ConflictError as e:
            # 409 충돌만 재시도
            if attempt == _CONFLICT_RETRY_COUNT - 1:
                logger.exception("lost queue push 409 재시도 최종 실패 (무시함)")
                return
            # 지수 백오프 + 지터
            wait_ms = (_CONFLICT_RETRY_BASE_MS * (2 ** attempt) +
                       random.randint(0, _CONFLICT_RETRY_JITTER_MAX_MS))
            logger.warning("lost_queue: 409 충돌(%d/%d) — %dms 후 재시도: %s",
                          attempt + 1, _CONFLICT_RETRY_COUNT, wait_ms, e)
            time.sleep(wait_ms / 1000.0)
        except Exception as e:
            # 409 외 예외는 재시도 없이 즉시 로그만 남김
            logger.exception("lost queue push 실패 (재시도 안 함, 무시함): %s", e)
            return


def read_lost(gh) -> tuple[list, str | None]:
    """유실 원문 큐 전체 읽기. (pending 리스트, sha)."""
    try:
        monitor_gh = _monitor_gh(gh)
        q, sha = monitor_gh.read_json(LOST_QUEUE_PATH)
        pending = list((q or {}).get("pending", []))
        return pending, sha
    except Exception as e:
        logger.exception("lost queue read 실패: %s", e)
        return [], None


def write_lost(gh, items: list, sha: str | None, message: str) -> None:
    """유실 원문 큐 전체 쓰기 (sha 필수) — 충돌 시 예외 던짐.

    409 충돌 시 최대 5회 지수 백오프 재시도.
    """
    from .gh_store import ConflictError

    monitor_gh = _monitor_gh(gh)

    for attempt in range(_CONFLICT_RETRY_COUNT):
        try:
            monitor_gh.write_json(
                LOST_QUEUE_PATH, {"pending": items},
                prev_sha=sha, message=message,
            )
            return
        except ConflictError as e:
            if attempt == _CONFLICT_RETRY_COUNT - 1:
                raise
            # 지수 백오프 + 지터
            wait_ms = (_CONFLICT_RETRY_BASE_MS * (2 ** attempt) +
                       random.randint(0, _CONFLICT_RETRY_JITTER_MAX_MS))
            logger.warning("lost_queue write: 충돌(%d/%d) — %dms 후 재시도: %s",
                          attempt + 1, _CONFLICT_RETRY_COUNT, wait_ms, e)
            time.sleep(wait_ms / 1000.0)


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대비
    except Exception:
        pass

    import base64

    class _Resp:
        def __init__(self, code, payload=None):
            self.status_code, self.reason, self.text = code, "", ""
            self._payload = payload or {}
        def json(self):
            return self._payload

    class _FakeSess:
        """read=GET 은 현재 저장된 텍스트를, write=PUT 은 성공 응답을 돌려준다."""
        def __init__(self, initial: str = ""):
            self.content = initial
            self.sha = "sha0"
            self.put_calls = 0
            self.last_message = None  # 마지막 PUT 의 message 저장
        def get(self, url, **kw):
            if self.content == "" and self.sha == "sha0" and self.put_calls == 0:
                return _Resp(404)
            enc = base64.b64encode(self.content.encode()).decode()
            return _Resp(200, {"content": enc, "sha": self.sha})
        def put(self, url, **kw):
            self.put_calls += 1
            body = kw["json"]
            self.last_message = body.get("message")  # 커밋 메시지 저장
            decoded = base64.b64decode(body["content"]).decode()
            self.content = decoded
            self.sha = f"sha{self.put_calls}"
            return _Resp(201, {"content": {"sha": self.sha}})

    from .gh_store import GitHubStore

    # 검증 1: 경로가 06:00 KST 경계 기준으로 계산되는지
    # UTC 15:30 == KST 00:30(다음날) — 06:00 이전이라 "전날" 파일로 묶인다
    assert event_path("2026-09-15T15:30:00Z") == "monitoring/events-2026-09-15.jsonl", \
        "KST 00:30 은 06:00 경계 이전 — 09-15 파일에 남아야 함"
    assert event_path("2026-09-16T00:00:00Z") == "monitoring/events-2026-09-16.jsonl", \
        "KST 09:00(06:00 이후) — 그날 파일"
    # 자정을 넘겨 방송하는 실제 사례: KST 09-16 23:30(=UTC 09-16 14:30)은 06:00 경계 기준
    # 09-17 05:30 이 아니라 여전히 09-16 방송일
    assert event_path("2026-09-16T14:30:00Z") == "monitoring/events-2026-09-16.jsonl"
    print("✓ event_path: 06:00 KST 경계 계산 정확 (자정 넘긴 방송도 전날로 묶임)")

    # 검증 2: 빈 파일(404)에 첫 줄 append
    sess = _FakeSess()
    gh = GitHubStore("tok", "o/r", "data", session=sess)
    log_event(gh, "2026-09-16T00:03:00Z", "tick", RESULT_OK, who="", detail="baseline",
              quota=14, candidates=8, preview_changed=True)
    lines = [ln for ln in sess.content.strip().split("\n") if ln]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["flow"] == "tick" and row["result"] == "ok" and row["quota"] == 14
    print("✓ log_event: 빈 파일에 첫 줄 append")

    # 검증 3: 두 번째 이벤트가 같은 파일에 누적(덮어쓰기 아님)
    log_event(gh, "2026-09-16T00:10:00Z", "notice", RESULT_DEGRADED, who="",
              detail="mode: added, needs_tl=true")
    lines = [ln for ln in sess.content.strip().split("\n") if ln]
    assert len(lines) == 2
    assert json.loads(lines[1])["result"] == "degraded"
    print("✓ log_event: 같은 날짜 파일에 계속 append(누적)")

    # 검증 4: 잘못된 result 값은 거부
    try:
        log_event(gh, "2026-09-16T00:11:00Z", "tick", "warn")
        assert False, "잘못된 result 는 ValueError 여야 함"
    except ValueError:
        pass
    print("✓ log_event: result는 ok/degraded/err 만 허용")

    # 검증 5: log_events 배치 — 3건 → PUT 1회, 3줄 누적
    sess2 = _FakeSess()
    gh2 = GitHubStore("tok", "o/r", "data", session=sess2)
    events = [
        {"flow": "tick", "result": RESULT_OK, "ts": "2026-09-16T00:05:00Z", "quota": 10},
        {"flow": "preview", "result": RESULT_OK, "ts": "2026-09-16T00:05:10Z", "video_id": "v1"},
        {"flow": "preview", "result": RESULT_DEGRADED, "ts": "2026-09-16T00:05:20Z", "video_id": "v2"},
    ]
    log_events(gh2, "2026-09-16T00:05:00Z", events)
    assert sess2.put_calls == 1, f"PUT은 정확히 1회여야 함, 실제 {sess2.put_calls}회"
    lines = [ln for ln in sess2.content.strip().split("\n") if ln]
    assert len(lines) == 3, f"3줄 누적 예상, 실제 {len(lines)}줄"
    print("✓ log_events: 3건 → PUT 1회, 3줄 누적")

    # 검증 6: log_events 빈 리스트 → PUT 0회
    sess3 = _FakeSess()
    gh3 = GitHubStore("tok", "o/r", "data", session=sess3)
    log_events(gh3, "2026-09-16T00:06:00Z", [])
    assert sess3.put_calls == 0, f"빈 리스트는 PUT 0회여야 함, 실제 {sess3.put_calls}회"
    print("✓ log_events: 빈 리스트 → PUT 0회")

    # 검증 7: log_events 잘못된 result 값은 거부
    try:
        log_events(gh, "2026-09-16T00:07:00Z", [
            {"flow": "tick", "result": "invalid"}
        ])
        assert False, "잘못된 result 는 ValueError 여야 함"
    except ValueError:
        pass
    print("✓ log_events: result 검증")

    # 검증 8: log_events 커밋 메시지 — n==1 일 때 기존 형식, n>1 일 때 확장 형식
    # n==1: "data: monitor tick 2026-..."
    sess4 = _FakeSess()
    gh4 = GitHubStore("tok", "o/r", "data", session=sess4)
    log_events(gh4, "2026-09-16T00:08:00Z", [
        {"flow": "tick", "result": RESULT_OK, "ts": "2026-09-16T00:08:00Z"}
    ])
    assert sess4.last_message == "data: monitor tick 2026-09-16T00:08:00Z", \
        f"n==1 메시지 형식 오류: {sess4.last_message!r}"
    print("✓ log_events: n==1 커밋 메시지 형식 (data: monitor tick 2026-...)")

    # n==3: "data: monitor tick(+2) 2026-..."
    sess5 = _FakeSess()
    gh5 = GitHubStore("tok", "o/r", "data", session=sess5)
    log_events(gh5, "2026-09-16T00:09:00Z", [
        {"flow": "tick", "result": RESULT_OK},
        {"flow": "preview", "result": RESULT_OK},
        {"flow": "preview", "result": RESULT_DEGRADED},
    ])
    assert sess5.last_message == "data: monitor tick(+2) 2026-09-16T00:09:00Z", \
        f"n==3 메시지 형식 오류: {sess5.last_message!r}"
    print("✓ log_events: n==3 커밋 메시지 형식 (data: monitor tick(+2) 2026-...)")

    # 검증 9: _monitor_gh 헬퍼 — 브랜치 교체
    os.environ["MONITOR_BRANCH"] = "monitoring"
    sess6 = _FakeSess()
    gh_data = GitHubStore("tok", "o/r", "data", session=sess6)
    gh_monitor = _monitor_gh(gh_data)
    assert gh_monitor.branch == "monitoring", f"branch 교체 실패: {gh_monitor.branch}"
    assert gh_monitor.token == "tok" and gh_monitor.repo == "o/r", "토큰/리포 보존 실패"
    print("✓ _monitor_gh: branch 교체 (data → monitoring)")

    # 검증 10: _monitor_gh 헬퍼 — mock store 호환성
    class _MockStore:
        """속성이 없는 mock 객체 — self-test 호환성 확인"""
        pass
    mock_store = _MockStore()
    result = _monitor_gh(mock_store)
    assert result is mock_store, "mock store는 그대로 반환해야 함"
    print("✓ _monitor_gh: mock store 안전망 (속성 없으면 원래 객체 반환)")

    # 검증 12: push_lost/read_lost 라운드트립 — tag 필드 포함
    sess_lost = _FakeSess()
    gh_lost = GitHubStore("tok", "o/r", "monitoring", session=sess_lost)
    item1 = {
        "ts": "2026-09-24T10:00:00Z",
        "kind": "personal_tweet",
        "reason": "write 실패",
        "channel_key": "arale",
        "title": "테스트 트윗",
        "tag": "1234567890123456789",
        "tweet_url": "https://x.com/user/status/1234567890123456789",
        "raw": "테스트 원문"
    }
    push_lost(gh_lost, item1)
    pending, sha = read_lost(gh_lost)
    assert len(pending) == 1, f"1건 예상, 실제 {len(pending)}건"
    assert pending[0] == item1, "필드 보존 실패"
    assert pending[0].get("tag") == "1234567890123456789", "tag 필드 유실"
    print("✓ push_lost/read_lost: 라운드트립 및 tag 필드 보존")

    # 검증 13: 상한 50건 초과 시 오래된 것부터 제거
    sess_limit = _FakeSess()
    gh_limit = GitHubStore("tok", "o/r", "monitoring", session=sess_limit)
    for i in range(60):
        push_lost(gh_limit, {"ts": f"2026-09-24T{i:02d}:00:00Z", "kind": "notice", "raw": f"item_{i}"})
    pending, _ = read_lost(gh_limit)
    assert len(pending) == 50, f"상한 50건 예상, 실제 {len(pending)}건"
    # 첫 10개는 버려지고 마지막 50개만 남아야 함
    first_raw = pending[0].get("raw", "")
    assert first_raw == "item_10", f"오래된 10건 제거 실패: 첫 raw = {first_raw}"
    last_raw = pending[-1].get("raw", "")
    assert last_raw == "item_59", f"최신 추가 실패: 마지막 raw = {last_raw}"
    print("✓ push_lost: 상한 50건 초과 시 오래된 것부터 제거")

    # 검증 14: write_lost 409 재시도 → 성공
    sess_retry = _FakeSess()
    gh_retry = GitHubStore("tok", "o/r", "monitoring", session=sess_retry)
    # 첫 push로 초기값 설정
    push_lost(gh_retry, {"ts": "2026-09-24T00:00:00Z", "kind": "notice"})
    # write_lost 호출 (sha 기반)
    pending, sha = read_lost(gh_retry)
    new_items = pending + [{"ts": "2026-09-24T01:00:00Z", "kind": "ingest"}]
    write_lost(gh_retry, new_items, sha, "data: lost_queue updated")
    pending, _ = read_lost(gh_retry)
    assert len(pending) == 2, f"2건 예상, 실제 {len(pending)}건"
    print("✓ write_lost: 409 재시도 로직 포함 (mock에선 1회)")

    # 검증 15: push_lost 실패해도 예외 안 던짐
    class _FailGh:
        """항상 Exception을 던지는 mock."""
        branch = "monitoring"
        def read_json(self, path):
            raise RuntimeError("테스트 실패")
        def write_json(self, path, data, prev_sha=None, message=""):
            raise RuntimeError("테스트 실패")
    fail_gh = _FailGh()
    try:
        push_lost(fail_gh, {"ts": "2026-09-24T02:00:00Z", "kind": "notice"})
        # 예외 안 던지고 그냥 반환해야 함
        print("✓ push_lost: 실패해도 예외 안 던짐 (logger.exception만)")
    except Exception as e:
        assert False, f"push_lost 가 예외를 던져서는 안 됨: {e}"

    # 검증 16: push_lost 409 아닌 예외는 1회만 시도 (재시도 없음)
    class _NonConflictFailGh:
        """RuntimeError를 던지는 mock — 409 아님."""
        branch = "monitoring"
        def __init__(self):
            self.write_calls = 0
        def read_json(self, path):
            return {"pending": []}, "sha-old"
        def write_json(self, path, data, prev_sha=None, message=""):
            self.write_calls += 1
            raise RuntimeError("network down")  # 409 아님

    non_conflict_gh = _NonConflictFailGh()
    push_lost(non_conflict_gh, {"ts": "2026-09-24T03:00:00Z", "kind": "notice"})
    assert non_conflict_gh.write_calls == 1, f"409 아닌 예외는 1회만 시도, 실제 {non_conflict_gh.write_calls}회"
    print("✓ push_lost: 409 아닌 예외는 1회만 시도 (재시도 없음)")

    # 검증 11: 409 충돌 재시도 — log_events 2회 충돌 후 성공
    # 테스트용 상수 오버라이드 (빠른 테스트)
    _orig_retry_count = _CONFLICT_RETRY_COUNT
    _orig_retry_base = _CONFLICT_RETRY_BASE_MS
    _orig_retry_jitter = _CONFLICT_RETRY_JITTER_MAX_MS

    from .gh_store import ConflictError as _ConflictError

    class _ConflictGh:
        """N번 409 던진 후 성공하는 mock."""
        def __init__(self, n_conflicts=2):
            self.n_conflicts = n_conflicts
            self.conflict_count = 0
            self.read_calls = 0
            self.write_calls = 0
            self.branch = "monitoring"  # _monitor_gh가 branch를 확인함

        def read_text(self, path):
            self.read_calls += 1
            return ("", "sha-old")

        def write_text(self, path, text, prev_sha=None, message=""):
            self.write_calls += 1
            if self.conflict_count < self.n_conflicts:
                self.conflict_count += 1
                raise _ConflictError(f"Conflict #{self.conflict_count}")
            # 성공

    try:
        # 임시 상수 오버라이드 (빠른 테스트)
        globals()["_CONFLICT_RETRY_COUNT"] = 5
        globals()["_CONFLICT_RETRY_BASE_MS"] = 10  # 10ms (테스트용)
        globals()["_CONFLICT_RETRY_JITTER_MAX_MS"] = 5   # 5ms (테스트용)

        # 2회 충돌 후 성공
        conflict_gh_2 = _ConflictGh(n_conflicts=2)
        log_events(conflict_gh_2, "2026-09-25T10:00:00Z", [
            {"flow": "tweet", "result": RESULT_OK, "who": "arale"}
        ])
        assert conflict_gh_2.write_calls == 3, f"3회 쓰기 예상(2번 충돌 + 1번 성공), 실제 {conflict_gh_2.write_calls}회"
        assert conflict_gh_2.conflict_count == 2, f"2회 충돌 예상, 실제 {conflict_gh_2.conflict_count}회"
        print(f"✓ log_events 409 재시도: 2회 충돌 후 성공 (write_calls={conflict_gh_2.write_calls}, "
              f"conflict_count={conflict_gh_2.conflict_count})")

        # 5회 모두 충돌 → 최종 raise
        conflict_gh_5 = _ConflictGh(n_conflicts=5)
        try:
            log_events(conflict_gh_5, "2026-09-25T10:01:00Z", [
                {"flow": "notice", "result": RESULT_DEGRADED}
            ])
            assert False, "5회 충돌 후 raise 예상"
        except _ConflictError:
            assert conflict_gh_5.conflict_count == 5, f"5회 모두 충돌 예상, 실제 {conflict_gh_5.conflict_count}회"
            print(f"✓ log_events 409 재시도 한계: 5회 도달 시 raise (conflict_count={conflict_gh_5.conflict_count}/5)")

    finally:
        # 상수 복구
        globals()["_CONFLICT_RETRY_COUNT"] = _orig_retry_count
        globals()["_CONFLICT_RETRY_BASE_MS"] = _orig_retry_base
        globals()["_CONFLICT_RETRY_JITTER_MAX_MS"] = _orig_retry_jitter

    print("\nSUCCESS: monitor_log.py self-test 통과 (mock + lost_queue)")
