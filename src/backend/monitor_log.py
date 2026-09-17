"""모니터링 이벤트 로그 — data 저장소에 하루 1개 JSONL로 append.

2026-09-16 세션에서 합의한 스키마(1단계 정의 → 목업 UI 검증 → 2단계 스키마 확정)를
그대로 구현한다. 공통 필드 ts/flow/result/who/detail + 흐름별 추가 필드(kwargs로 받아
그대로 실어 보냄) — CSV처럼 모든 흐름이 같은 컬럼을 가질 필요가 없어 JSONL을 쓴다.

result 는 ok/degraded/err 셋 중 하나 — 성공/실패로 미리 뭉치지 않고 각 파이프라인이
실제로 반환한 raw mode/상태(detail)는 그대로 두되, 필터링용으로 이 3톤만 별도 태깅한다.

파일: monitoring/events-YYYY-MM-DD.jsonl (KST 날짜 기준 — 대시보드 "하루" 경계와 맞춤).
백엔드 상태(4색)는 여기서 기록하지 않는다 — healthchecks.io API에서 그때그때 조회.

self-test: python -m src.backend.monitor_log
"""
from __future__ import annotations

import json
import logging
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


def bucket_date_kst(now: "str | datetime") -> str:
    """now(ISO 'Z' 문자열 또는 tz-aware datetime) → 06:00 KST 경계 기준 날짜(YYYY-MM-DD)."""
    dt = datetime.fromisoformat(now.replace("Z", "+00:00")) if isinstance(now, str) else now
    return (dt.astimezone(KST) - timedelta(hours=DAY_START_HOUR)).strftime("%Y-%m-%d")


def event_path(now_iso: str) -> str:
    """now_iso(UTC 'Z') → 오늘자 이벤트 로그 경로. 날짜는 06:00 KST 경계 기준(대시보드 "하루"와 일치)."""
    return f"monitoring/events-{bucket_date_kst(now_iso)}.jsonl"


def log_events(gh, now_iso: str, events: list[dict]) -> None:
    """gh(GitHubStore, data 저장소용)로 오늘자 이벤트 로그에 여러 줄 append(배치).

    빈 리스트면 GitHub을 건드리지 않고 반환.
    각 원소는 {"flow", "result", "who"?, "detail"?, ...추가필드}.
    result는 ok/degraded/err 검증. ConflictError는 기존과 같은 2회 재시도.
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

    # 한 번 읽고 모든 줄을 이어붙여 한 번 쓰기, 충돌 시 2회 재시도
    for attempt in range(2):
        text, sha = gh.read_text(path)
        new_text = (text or "") + "\n".join(lines) + "\n"
        try:
            gh.write_text(path, new_text, prev_sha=sha, message=message)
            return
        except ConflictError as e:
            if attempt == 1:
                raise
            logger.warning("monitor_log: 배치 충돌 — 재시도: %s", e)


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

    print("\nSUCCESS: monitor_log.py self-test 통과 (mock)")
