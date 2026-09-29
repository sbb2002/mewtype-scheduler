"""방송 일정 관련 트윗 원문 보존 (결정 D19).

raw/<YYYY-MM>.jsonl 로 각 라인이 한 건의 원문을 JSON 객체로 기록.
각 줄: {"ts": ISO문자열, "kind": 종류, "raw": 원문, "meta": 메타데이터또는{}}

kind 예: "official_schedule", "personal_schedule", "personal_schedule_candidate"

GitHub Contents API 충돌(409)은 최대 3회 재시도 (지수 백오프 + 지터).
네트워크 오류·기타 예외는 로깅하고 False 반환 (예외 발생 안 함).

self-test: python -m src.backend.rawlog
"""
from __future__ import annotations

import base64
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

UTC = timezone.utc
_CONFLICT_RETRY_COUNT = 3
_CONFLICT_RETRY_BASE_MS = 500  # 0.5s → 1s → 2s
_CONFLICT_RETRY_JITTER_MAX_MS = 300


def append_raw(
    store,
    *,
    kind: str,
    raw: str,
    meta: Optional[dict] = None,
    now_iso: str,
) -> bool:
    """원문을 raw/<YYYY-MM>.jsonl 에 한 줄 append.

    store: read_text/write_text 메서드가 있는 객체 (GitHubStore 등).
    kind: "official_schedule" 등 문자열 구분자.
    raw: 원문 텍스트.
    meta: 메타데이터 딕셔너리 (None이면 {}로 저장).
    now_iso: UTC ISO 문자열 ("2026-09-29T12:34:56Z" 형식).

    성공 시 True, 실패 시 False 반환 (예외는 발생 안 함).
    """
    # now_iso에서 월(YYYY-MM) 추출
    try:
        dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        month = dt.strftime("%Y-%m")
    except Exception as e:
        logger.warning(f"rawlog.append_raw: now_iso 파싱 실패 {now_iso!r}: {e}")
        return False

    path = f"raw/{month}.jsonl"

    # 한 줄의 JSON 객체 생성
    line_obj = {
        "ts": now_iso,
        "kind": kind,
        "raw": raw,
        "meta": meta or {},
    }
    line = json.dumps(line_obj, ensure_ascii=False, sort_keys=True) + "\n"

    # 충돌 재시도: 최대 3회
    for attempt in range(_CONFLICT_RETRY_COUNT):
        try:
            text, sha = store.read_text(path)
            new_text = (text or "") + line
            store.write_text(path, new_text, prev_sha=sha, message=f"data: raw append {now_iso}")
            return True
        except Exception as e:
            # ConflictError 판정 (클래스명 비교)
            is_conflict = e.__class__.__name__ == "ConflictError"

            if not is_conflict:
                # 409 아닌 다른 예외 → 재시도 안 함
                logger.warning(f"rawlog.append_raw: {path} 쓰기 실패 (재시도 안 함): {e}")
                return False

            # ConflictError → 재시도
            if attempt == _CONFLICT_RETRY_COUNT - 1:
                logger.warning(f"rawlog.append_raw: {path} 409 충돌 최종 실패 (3회 모두 실패)")
                return False

            wait_ms = (
                _CONFLICT_RETRY_BASE_MS * (2 ** attempt)
                + random.randint(0, _CONFLICT_RETRY_JITTER_MAX_MS)
            )
            logger.debug(
                f"rawlog.append_raw: {path} 409 충돌({attempt + 1}/{_CONFLICT_RETRY_COUNT}) "
                f"— {wait_ms}ms 후 재시도"
            )
            time.sleep(wait_ms / 1000.0)

    return False


def read_month(store, month: str) -> list[dict]:
    """raw/<YYYY-MM>.jsonl 을 읽어 모든 줄을 파싱한 dict 리스트 반환.

    month: "2026-09" 형식의 문자열.

    파싱 실패한 줄은 skip (로그만 남김).
    파일 없음(404)이면 [] 반환.
    네트워크 오류 등은 예외 발생.
    """
    path = f"raw/{month}.jsonl"

    try:
        text, _ = store.read_text(path)
    except Exception as e:
        logger.warning(f"rawlog.read_month: {path} 읽기 실패: {e}")
        raise

    if text is None:
        return []

    result = []
    for line_num, line in enumerate(text.split("\n"), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            result.append(obj)
        except json.JSONDecodeError as e:
            logger.warning(f"rawlog.read_month: {path}:{line_num} JSON 파싱 실패: {e}")
            continue

    return result


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # ──────────────────────────────────────────────────────────────
    # Self-test: 메모리 저장소 시뮬레이션
    # ──────────────────────────────────────────────────────────────

    class FakeStore:
        """read_text/write_text 메서드를 구현한 가짜 저장소.

        ConflictError를 시뮬레이션할 수 있음.
        """

        class ConflictError(RuntimeError):
            pass

        def __init__(self):
            self.data = {}  # path -> (content, sha)
            self.conflict_until = {}  # path -> (이 횟수까지 409 발생)

        def read_text(self, path: str) -> tuple[Optional[str], Optional[str]]:
            if path not in self.data:
                return None, None
            content, sha = self.data[path]
            return content, sha

        def write_text(
            self,
            path: str,
            text: str,
            *,
            prev_sha: Optional[str] = None,
            message: str = "",
        ) -> tuple[bool, Optional[str]]:
            current_content, current_sha = self.read_text(path)

            # 충돌 시뮬레이션: 설정된 횟수까지 409 발생
            if path in self.conflict_until and self.conflict_until[path] > 0:
                self.conflict_until[path] -= 1
                raise FakeStore.ConflictError(
                    f"mock conflict on {path}: prev_sha mismatch"
                )

            # 변화 없으면 False 반환
            if current_content is not None and current_content == text:
                return False, current_sha

            # sha 검증
            if prev_sha is not None and current_sha is not None and current_sha != prev_sha:
                raise FakeStore.ConflictError(
                    f"base sha {prev_sha[:8] if prev_sha else '?'} != current "
                    f"{current_sha[:8] if current_sha else '?'}"
                )

            # 쓰기
            new_sha = f"sha_{len(self.data)}_{len(text)}"
            self.data[path] = (text, new_sha)
            return True, new_sha

    # 테스트 1: 빈 파일에 두 줄 append
    print("테스트 1: 빈 파일에 두 줄 append...")
    store1 = FakeStore()
    ok1 = append_raw(
        store1,
        kind="personal_schedule",
        raw="9월 30일 19시 라이브",
        meta={"source": "tweet"},
        now_iso="2026-09-29T10:00:00Z",
    )
    assert ok1, "첫 줄 추가 실패"

    ok2 = append_raw(
        store1,
        kind="official_schedule",
        raw="공식 생일 방송",
        meta={"channel": "arale"},
        now_iso="2026-09-29T11:00:00Z",
    )
    assert ok2, "두 번째 줄 추가 실패"

    # read_month 확인
    items = read_month(store1, "2026-09")
    assert len(items) == 2, f"기대: 2줄, 실제: {len(items)}"
    assert items[0]["kind"] == "personal_schedule"
    assert items[0]["raw"] == "9월 30일 19시 라이브"
    assert items[1]["kind"] == "official_schedule"
    print(f"  ✓ 두 줄 append 완료, read_month 검증 통과")

    # 테스트 2: ConflictError 2회 후 성공
    print("테스트 2: 409 충돌 2회 후 성공...")
    store2 = FakeStore()
    store2.conflict_until["raw/2026-09.jsonl"] = 2  # 처음 2회 충돌

    ok3 = append_raw(
        store2,
        kind="personal_schedule_candidate",
        raw="후보 텍스트",
        meta={},
        now_iso="2026-09-29T12:00:00Z",
    )
    assert ok3, "재시도 후 성공해야 함"
    print(f"  ✓ 409 충돌 2회 후 성공")

    # 테스트 3: ConflictError 3회 이상 → 실패
    print("테스트 3: 409 충돌 3회 이상 → False 반환...")
    store3 = FakeStore()
    store3.conflict_until["raw/2026-09.jsonl"] = 10  # 항상 충돌

    ok4 = append_raw(
        store3,
        kind="personal_schedule",
        raw="실패할 텍스트",
        meta={},
        now_iso="2026-09-29T12:30:00Z",
    )
    assert not ok4, "3회 재시도 실패 후 False를 반환해야 함"
    print(f"  ✓ 최종 실패 후 False 반환")

    # 테스트 4: 다른 예외 (RuntimeError) → 즉시 False
    print("테스트 4: RuntimeError → 즉시 False...")

    class FailingStore:
        def read_text(self, path):
            raise RuntimeError("네트워크 오류")

    store4 = FailingStore()
    ok5 = append_raw(
        store4,
        kind="personal_schedule",
        raw="네트워크 실패",
        meta={},
        now_iso="2026-09-29T13:00:00Z",
    )
    assert not ok5, "RuntimeError 시 False 반환"
    print(f"  ✓ RuntimeError 시 즉시 False")

    # 테스트 5: 404 파일 → 첫 줄부터 생성
    print("테스트 5: 404 파일 → 첫 줄부터 생성...")
    store5 = FakeStore()
    ok6 = append_raw(
        store5,
        kind="personal_schedule",
        raw="새 파일 첫 줄",
        meta={"order": 1},
        now_iso="2026-09-30T00:00:00Z",
    )
    assert ok6, "404 파일에 첫 줄 추가 실패"
    items5 = read_month(store5, "2026-09")
    assert len(items5) == 1
    assert items5[0]["meta"]["order"] == 1
    print(f"  ✓ 404 파일에서 첫 줄 생성 완료")

    print("\n✓ 모든 rawlog 테스트 통과")
