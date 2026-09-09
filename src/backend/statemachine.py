"""
상태머신: preview.json 아이템의 상태 전이 및 다음 폴링 시각 파생.

계약: docs/SPEC.md v3 (예정), v3_impl_spec.md §0.2 (FSM 규칙 + 상수).
순수 파이썬, 네트워크·파일·시계 접근 금지 (now_iso 는 인자).

v3: pending.json 저장 타이머 폐지 — FSM 은 상태 전이와 next_check_at 을 순수 파생하고,
저장은 `handlers` 가 담당.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# 상수 — v3_impl_spec.md §0.2 그대로
PRELIVE_LEAD_SEC = 3 * 60  # 180초 — scheduled_start 3분 전부터 watching 진입
PRELIVE_TIGHT_SEC = 3 * 60  # 180초 — watching 체크 간격 (3분)
WATCH_LATE_DEMOTE_SEC = 2 * 60 * 60  # 7200초 — watching 에서 announced 강등 경계 (2시간)
ASSUMED_LIVE_MAX_SEC = 90 * 60  # 5400초 — assumed-live 폴백 경계 (90분)
LIVE_EARLY_SEC = 10 * 60  # 600초 — live 초기 체크 간격 (10분, +60분 미만)
LIVE_EARLY_WINDOW_SEC = 60 * 60  # 3600초 — live 초기/후기 경계 (60분)
LIVE_TIGHT_SEC = 3 * 60  # 180초 — live 후기 체크 간격 (3분, +60분 이상)
END_WINDOW_SEC = 30 * 60  # 1800초 — end 상태 창 (30분)
END_TICK_SEC = 5 * 60  # 300초 — end 체크 간격 (5분)
MAX_TASK_HORIZON_SEC = 696 * 3600  # 2505600초 — Cloud Tasks 상한 (696h, 29일)


def _parse_iso(s: str) -> datetime:
    """ISO 문자열 파싱 (Z → +00:00, tz-aware UTC)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _to_iso(dt: datetime) -> str:
    """datetime → ISO 문자열 (UTC, Z suffix)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bound_schedule_time(schedule_time_iso: str, now_iso: str) -> str:
    """다음 wake 시각을 [now+60초, now+MAX_TASK_HORIZON] 범위로 클램프.

    - 과거/임박 → now+60초 (즉시 실행 방지)
    - MAX_TASK_HORIZON 초과 → now+MAX_TASK_HORIZON (롱폴링)
    """
    t = _parse_iso(schedule_time_iso)
    now = _parse_iso(now_iso)
    lo = now + timedelta(seconds=60)
    hi = now + timedelta(seconds=MAX_TASK_HORIZON_SEC)
    if t < lo:
        t = lo
    elif t > hi:
        t = hi
    return _to_iso(t)


@dataclass
class Tick:
    """FSM 파생 결과.

    Attributes:
        next_state: 새 상태. 입력 state 와 동일하면 전이 없음.
        next_check_at: 다음 폴링 시각 (ISO Z). None = 더 이상 폴링 불필요.
        log: 상태 전이 로그 (사람 가독·notify 토큰용).
    """

    next_state: str
    next_check_at: str | None
    log: list[str]


def derive(
    item: dict,
    now_iso: str,
    *,
    live_seen: bool | None = None,
    preview_stream_seen: bool = False,
) -> Tick:
    """상태 전이 및 다음 폴링 시각을 파생한다.

    Args:
        item: preview.json 아이템 dict. 필드:
            - state: str (announced | upcoming | watching | live | end | none)
            - scheduled_start: str | None (ISO Z)
            - actual_start: str | None (ISO Z)
            - state_since: str | None (ISO Z, 현 상태 진입 시각)
            - assumed_live: bool (v3 폴백, 기본값 False)
            - membership: bool (회원전용, 기본값 False)
            - video_id: str | None
            - id: str (로깅용)
        now_iso: 현재 시각 (ISO Z)
        live_seen: API/알림이 이 video_id 를 live 로 확인했는지.
                  None = 미확인 (아직 체크 안 함)
        preview_stream_seen: 예고 스트림으로 재등장했는지 (end 상태에서 upcoming 복구용)

    Returns:
        Tick(next_state, next_check_at, log)

    v3_impl_spec.md §0.2 FSM 규칙 표 구현:
        1. pre-live 진입 (announced/upcoming + ss 3분 전)
        2. watching 체크 (120분 미만)
        3. watching 지각 강등 (120분 경과)
        4. assumed-live 폴백 (90분 경과)
        5. live 초기 cadence (+60분 미만, 10분 간격)
        6. live 후기 cadence (+60분 이상, 3분 간격)
        7. end 창 (30분 미만, 5분 간격)
        8. end→none (30분 경과)
        9. end→upcoming (예고 스트림 재등장)
       10. membership 특례 (waiting 스킵, live_seen 시 직행)
    """
    now = _parse_iso(now_iso)
    state = item.get("state", "announced")
    scheduled_start_iso = item.get("scheduled_start")
    actual_start_iso = item.get("actual_start")
    state_since_iso = item.get("state_since")
    assumed_live = item.get("assumed_live", False)
    membership = item.get("membership", False)
    video_id = item.get("video_id")
    item_id = item.get("id", "?")

    # 시각 파싱
    ss = _parse_iso(scheduled_start_iso) if scheduled_start_iso else None
    actual_start = _parse_iso(actual_start_iso) if actual_start_iso else None
    state_since = _parse_iso(state_since_iso) if state_since_iso else now

    log = []
    next_state = state
    next_check_at = None

    # ─ 규칙 1·3·4·10: announced / upcoming 상태 ─
    if state in ("announced", "upcoming"):
        # 규칙 4: assumed-live 폴백 (우선도 높음 — video_id 없고 90분 경과)
        if (
            assumed_live
            and not video_id
            and ss
            and (now - ss).total_seconds() >= ASSUMED_LIVE_MAX_SEC
        ):
            next_state = "none"
            next_check_at = None
            log.append(f"assumed-live drop {item_id}")

        # 규칙 10: membership 특례 (live_seen 신호로 직행, API 체크 없음)
        elif membership and live_seen:
            next_state = "live"
            next_check_at = _to_iso(now + timedelta(seconds=LIVE_EARLY_SEC))
            log.append(f"membership direct-to-live {item_id}")

        # 규칙 1: pre-live 진입 — scheduled_start 3분 전부터 watching 진입
        elif ss and now >= ss - timedelta(seconds=PRELIVE_LEAD_SEC):
            next_state = "watching"
            next_check_at = _to_iso(now + timedelta(seconds=PRELIVE_TIGHT_SEC))
            log.append(f"→watching {item_id}")

        # 규칙 1 폴백: 아직 3분 전이 아니면, ss - 3분에 watching 진입하도록 예약
        elif ss and now < ss - timedelta(seconds=PRELIVE_LEAD_SEC):
            next_state = state  # announced/upcoming 유지
            next_check_at = _to_iso(ss - timedelta(seconds=PRELIVE_LEAD_SEC))
            log.append(f"waiting-for-precheck {item_id}")

    # ─ 규칙 2·3: watching 상태 ─
    elif state == "watching":
        # 규칙 3: 지각 강등 — scheduled_start 기준 120분 경과
        if ss and (now - ss).total_seconds() >= WATCH_LATE_DEMOTE_SEC:
            next_state = "announced"
            next_check_at = None
            log.append(f"watching-demote→announced {item_id}")

        # live_seen=True → live 로 전이
        elif live_seen:
            next_state = "live"
            next_check_at = _to_iso(now + timedelta(seconds=LIVE_EARLY_SEC))
            log.append(f"→live {item_id}")

        # 규칙 2: watching 계속 — 3분 간격 폴링
        else:
            next_state = "watching"
            next_check_at = _to_iso(now + timedelta(seconds=PRELIVE_TIGHT_SEC))
            log.append(f"watching-check {item_id}")

    # ─ 규칙 5·6: live 상태 ─
    elif state == "live":
        if live_seen is False:
            # live_seen=False (명시적으로 live 아님 확인) → end 로 전이.
            # live_seen=None(미확인)은 여기서 종료로 보지 않는다 — 계속 live 유지하고 재확인 예약.
            next_state = "end"
            next_check_at = _to_iso(now + timedelta(seconds=END_TICK_SEC))
            log.append(f"→end {item_id}")

        else:
            # live_seen=True 또는 None → 계속 live
            # 규칙 5·6: 시작 후 시간에 따라 폴링 간격 조정
            elapsed_sec = (now - actual_start).total_seconds() if actual_start else 0
            if elapsed_sec < LIVE_EARLY_WINDOW_SEC:
                # 초기 (60분 미만): 10분 간격
                next_check_at = _to_iso(now + timedelta(seconds=LIVE_EARLY_SEC))
            else:
                # 후기 (60분 이상): 3분 간격
                next_check_at = _to_iso(now + timedelta(seconds=LIVE_TIGHT_SEC))
            log.append(f"live-check {item_id}")

    # ─ 규칙 7·8·9: end 상태 ─
    elif state == "end":
        # 규칙 9: 예고 스트림 재등장 (preview_stream_seen=True)
        if preview_stream_seen:
            next_state = "upcoming"
            next_check_at = _to_iso(now + timedelta(seconds=PRELIVE_TIGHT_SEC))
            log.append(f"end-recover→upcoming {item_id}")

        # 규칙 8: 30분 경과 → none (삭제)
        elif state_since and (now - state_since).total_seconds() >= END_WINDOW_SEC:
            next_state = "none"
            next_check_at = None
            log.append(f"end→none {item_id}")

        # 규칙 7: end 창 (30분 미만) — 5분 간격
        else:
            next_state = "end"
            next_check_at = _to_iso(now + timedelta(seconds=END_TICK_SEC))
            log.append(f"end-check {item_id}")

    # ─ next_check_at 클램프 ─
    if next_check_at:
        next_check_at = _bound_schedule_time(next_check_at, now_iso)

    return Tick(next_state=next_state, next_check_at=next_check_at, log=log)


if __name__ == "__main__":
    # Smoke test: v3_impl_spec.md §0.2 표 각 행 시나리오 + membership + horizon
    # 최소 11 assert

    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    base_now = "2026-08-31T12:00:00Z"
    base_ss = "2026-08-31T13:00:00Z"

    print("=" * 70)
    print("✓ 규칙 1: announced, scheduled_start 3분 전 → watching")
    print("=" * 70)
    now_1 = "2026-08-31T12:57:00Z"  # ss - 3분
    item_1 = {
        "id": "pv_test1",
        "state": "announced",
        "scheduled_start": base_ss,
        "actual_start": None,
        "state_since": "2026-08-31T12:00:00Z",
    }
    tick_1 = derive(item_1, now_1)
    assert tick_1.next_state == "watching", f"expected watching, got {tick_1.next_state}"
    assert tick_1.next_check_at is not None
    assert "watching" in tick_1.log[0].lower()
    print(f"  state: announced → {tick_1.next_state}, check in 3min")
    print(f"  log: {tick_1.log}")

    print("\n" + "=" * 70)
    print("✓ 규칙 2: watching, 120분 미만, live_seen=None → watching 계속")
    print("=" * 70)
    now_2 = base_now  # ss - 3분 후
    item_2 = {
        "id": "pv_test2",
        "state": "watching",
        "scheduled_start": base_ss,
        "actual_start": None,
        "state_since": "2026-08-31T12:00:00Z",
    }
    tick_2 = derive(item_2, now_2)
    assert tick_2.next_state == "watching"
    assert tick_2.next_check_at is not None
    print(f"  state: watching → {tick_2.next_state}, check in 3min")

    print("\n" + "=" * 70)
    print("✓ 규칙 3: watching, 120분 경과 → announced (지각 강등)")
    print("=" * 70)
    now_3 = "2026-08-31T15:00:00Z"  # ss + 2시간
    item_3 = {
        "id": "pv_test3",
        "state": "watching",
        "scheduled_start": base_ss,
        "actual_start": None,
        "state_since": "2026-08-31T12:00:00Z",
    }
    tick_3 = derive(item_3, now_3)
    assert tick_3.next_state == "announced", f"expected announced, got {tick_3.next_state}"
    assert tick_3.next_check_at is None
    print(f"  state: watching → {tick_3.next_state}, no more check")

    print("\n" + "=" * 70)
    print("✓ 규칙 4: announced, assumed_live=True, video_id=None, 90분 경과 → none")
    print("=" * 70)
    now_4 = "2026-08-31T14:30:00Z"  # ss + 90분
    item_4 = {
        "id": "pv_test4",
        "state": "announced",
        "scheduled_start": base_ss,
        "actual_start": None,
        "state_since": "2026-08-31T12:00:00Z",
        "assumed_live": True,
        "video_id": None,
    }
    tick_4 = derive(item_4, now_4)
    assert tick_4.next_state == "none", f"expected none, got {tick_4.next_state}"
    assert tick_4.next_check_at is None
    print(f"  state: announced → {tick_4.next_state} (assumed-live drop)")

    print("\n" + "=" * 70)
    print("✓ 규칙 5: live, actual_start 60분 미만 → check in 10min")
    print("=" * 70)
    now_5 = "2026-08-31T13:30:00Z"  # actual_start + 30분
    item_5 = {
        "id": "pv_test5",
        "state": "live",
        "scheduled_start": base_ss,
        "actual_start": "2026-08-31T13:00:00Z",
        "state_since": "2026-08-31T13:00:00Z",
    }
    tick_5 = derive(item_5, now_5, live_seen=True)
    assert tick_5.next_state == "live"
    assert tick_5.next_check_at is not None
    check_5 = _parse_iso(tick_5.next_check_at)
    now_5_dt = _parse_iso(now_5)
    delta_5 = (check_5 - now_5_dt).total_seconds()
    # 클램프 없으면 600초, 클램프 있으면 [60, MAX_TASK_HORIZON]
    assert 600 <= delta_5 <= MAX_TASK_HORIZON_SEC, f"expected ~10min, got {delta_5}sec"
    print(f"  state: live, elapsed=30min → check in {delta_5}sec (~10min)")

    print("\n" + "=" * 70)
    print("✓ 규칙 6: live, actual_start 60분 이상 → check in 3min")
    print("=" * 70)
    now_6 = "2026-08-31T14:00:00Z"  # actual_start + 60분
    item_6 = {
        "id": "pv_test6",
        "state": "live",
        "scheduled_start": base_ss,
        "actual_start": "2026-08-31T13:00:00Z",
        "state_since": "2026-08-31T13:00:00Z",
    }
    tick_6 = derive(item_6, now_6, live_seen=True)
    assert tick_6.next_state == "live"
    check_6 = _parse_iso(tick_6.next_check_at)
    now_6_dt = _parse_iso(now_6)
    delta_6 = (check_6 - now_6_dt).total_seconds()
    assert 180 <= delta_6 <= MAX_TASK_HORIZON_SEC, f"expected ~3min, got {delta_6}sec"
    print(f"  state: live, elapsed=60min → check in {delta_6}sec (~3min)")

    print("\n" + "=" * 70)
    print("✓ 규칙 7·8: end, 30분 미만 → check in 5min")
    print("=" * 70)
    now_7 = "2026-08-31T13:10:00Z"  # state_since + 10분
    item_7 = {
        "id": "pv_test7",
        "state": "end",
        "scheduled_start": base_ss,
        "actual_start": "2026-08-31T13:00:00Z",
        "state_since": "2026-08-31T13:00:00Z",
    }
    tick_7 = derive(item_7, now_7)
    assert tick_7.next_state == "end"
    assert tick_7.next_check_at is not None
    print(f"  state: end, elapsed=10min → check in 5min")

    print("\n" + "=" * 70)
    print("✓ 규칙 8: end, 30분 경과 → none")
    print("=" * 70)
    now_8 = "2026-08-31T13:35:00Z"  # state_since + 35분
    item_8 = {
        "id": "pv_test8",
        "state": "end",
        "scheduled_start": base_ss,
        "actual_start": "2026-08-31T13:00:00Z",
        "state_since": "2026-08-31T13:00:00Z",
    }
    tick_8 = derive(item_8, now_8)
    assert tick_8.next_state == "none", f"expected none, got {tick_8.next_state}"
    assert tick_8.next_check_at is None
    print(f"  state: end → {tick_8.next_state} (30min window expired)")

    print("\n" + "=" * 70)
    print("✓ 규칙 9: end, preview_stream_seen=True → upcoming")
    print("=" * 70)
    now_9 = "2026-08-31T13:10:00Z"
    item_9 = {
        "id": "pv_test9",
        "state": "end",
        "scheduled_start": base_ss,
        "actual_start": "2026-08-31T13:00:00Z",
        "state_since": "2026-08-31T13:00:00Z",
    }
    tick_9 = derive(item_9, now_9, preview_stream_seen=True)
    assert tick_9.next_state == "upcoming", f"expected upcoming, got {tick_9.next_state}"
    print(f"  state: end → {tick_9.next_state} (preview stream reappeared)")

    print("\n" + "=" * 70)
    print("✓ 규칙 10: membership=True, live_seen=True → live (skip watching)")
    print("=" * 70)
    now_10 = base_now
    item_10 = {
        "id": "pv_test10",
        "state": "announced",
        "scheduled_start": base_ss,
        "actual_start": None,
        "state_since": "2026-08-31T11:00:00Z",
        "membership": True,
    }
    tick_10 = derive(item_10, now_10, live_seen=True)
    assert tick_10.next_state == "live", f"expected live, got {tick_10.next_state}"
    assert "membership" in tick_10.log[0].lower()
    print(f"  membership + live_seen → {tick_10.next_state} (skip watching)")

    print("\n" + "=" * 70)
    print("✓ next_check_at 클램프: 먼 미래 → now + MAX_TASK_HORIZON")
    print("=" * 70)
    now_11 = "2026-08-31T12:00:00Z"
    far_future = "2028-01-01T00:00:00Z"  # 1년 4개월 뒤
    item_11 = {
        "id": "pv_test11",
        "state": "announced",
        "scheduled_start": far_future,
        "actual_start": None,
        "state_since": now_11,
    }
    tick_11 = derive(item_11, now_11)
    assert tick_11.next_state == "announced"
    assert tick_11.next_check_at is not None
    horizon = _to_iso(_parse_iso(now_11) + timedelta(seconds=MAX_TASK_HORIZON_SEC))
    assert tick_11.next_check_at == horizon, (
        f"expected {horizon}, got {tick_11.next_check_at}"
    )
    print(f"  far future (1.3 years) clamped to now + 696h")

    print("\n" + "=" * 70)
    print("✓ watching → live transition (live_seen=True)")
    print("=" * 70)
    now_12 = "2026-08-31T12:50:00Z"
    item_12 = {
        "id": "pv_test12",
        "state": "watching",
        "scheduled_start": base_ss,
        "actual_start": "2026-08-31T12:45:00Z",
        "state_since": "2026-08-31T12:57:00Z",
    }
    tick_12 = derive(item_12, now_12, live_seen=True)
    assert tick_12.next_state == "live", f"expected live, got {tick_12.next_state}"
    print(f"  watching + live_seen → {tick_12.next_state}")

    print("\n" + "=" * 70)
    print("SUCCESS: 모든 12개 시나리오 통과 ✓")
    print("=" * 70)
