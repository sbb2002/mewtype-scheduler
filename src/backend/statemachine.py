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
LIVE_TIGHT_SEC = 5 * 60  # 300초 — live 후기 체크 간격 (5분, +60분 이상). 프론트엔드가 읽는 raw CDN 캐시가 max-age=300 이라 3분은 화면에 반영되지 않음 (v3 개선 WP-5)
END_WINDOW_SEC = 30 * 60  # 1800초 — end 상태 창 (30분)
END_TICK_SEC = 5 * 60  # 300초 — end 체크 간격 (5분)
MAX_TASK_HORIZON_SEC = 696 * 3600  # 2505600초 — Cloud Tasks 상한 (696h, 29일)


def _parse_iso(s: str) -> datetime:
    """ISO 문자열 파싱 (Z → +00:00, tz-aware UTC)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _to_iso(dt: datetime) -> str:
    """datetime → ISO 문자열 (UTC, Z suffix)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _after(now: datetime, sec: int) -> str:
    """"지금부터 약 sec 초 뒤" 체크 시각 — sec 주기 격자(epoch 기준)의 다음 눈금으로 맞춘다.

    `now + sec` 그대로 쓰면 실행 시각이 다른 실행(정기 tick·다른 방송의 wake)마다 서로 다른 시각의
    태스크를 등록하고, wake 태스크는 이름이 (영상, 분)이라 dedupe 가 안 되어 실행 하나마다 체인이 하나씩
    늘어난다(2026-09-17 DWMQTpDQ1fc: 3분 주기가 위상 3개로 분당 1회, 48시간 3,331회). 눈금에 맞추면 같은
    구간의 모든 실행이 같은 시각을 계산해 같은 이름으로 dedupe 된다. 지연은 [sec/2, 1.5*sec) 로 평균이
    sec 이고 최소 sec/2 ≥ 90초라 `_bound_schedule_time` 의 60초 하한에 걸려 위상이 깨지지 않는다.
    절대 시각(ss-3분 예약 등)은 원래 실행마다 같은 값이라 대상이 아니다.
    """
    import math
    t = math.ceil((now.timestamp() + sec / 2) / sec) * sec
    return _to_iso(datetime.fromtimestamp(t, timezone.utc))


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
        6. live 후기 cadence (+60분 이상, 5분 간격)
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
            next_check_at = _after(now, LIVE_EARLY_SEC)
            log.append(f"membership direct-to-live {item_id}")

        # 규칙 3 이후 재진입 차단 (v3.7.3): scheduled_start 로부터 120분 넘게 지난 예고는 다시
        # watching 에 안 넣는다. 안 막으면 규칙 3(watching→announced) 과 아래 규칙 1(announced→
        # watching) 이 매 실행마다 서로를 되돌려 TTL 까지 왕복한다(2026-09-18 아라레 자리표시
        # pv_c181ee4c: 23:00~24:00 KST 140회). 시간이 지난 예고는 announced 로 두고 TTL 이 지운다.
        elif ss and (now - ss).total_seconds() >= WATCH_LATE_DEMOTE_SEC:
            next_state = state
            next_check_at = None
            log.append(f"late-hold {item_id}")

        # 규칙 1: pre-live 진입 — scheduled_start 3분 전부터 watching 진입
        elif ss and now >= ss - timedelta(seconds=PRELIVE_LEAD_SEC):
            next_state = "watching"
            next_check_at = _after(now, PRELIVE_TIGHT_SEC)
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
            next_check_at = _after(now, LIVE_EARLY_SEC)
            log.append(f"→live {item_id}")

        # 규칙 2 예외 (v3.7.3): 예정 시각이 3분보다 더 미래로 밀렸으면(수신 시각으로 잘못 잡혔다가
        # API 시작 시각으로 정정된 경우 등) watching 을 유지할 이유가 없다 — 대기 상태로 되돌리고
        # ss-3분에 재진입 예약. 안 되돌리면 시작이 며칠 뒤여도 watching 3분 폴링이 계속된다
        # (2026-09-17 17:03 KST 이후 DWMQTpDQ1fc: ss 는 9/25 인데 48시간 동안 /wake 3,331회).
        elif ss and now < ss - timedelta(seconds=PRELIVE_LEAD_SEC):
            next_state = "upcoming" if video_id else "announced"
            next_check_at = _to_iso(ss - timedelta(seconds=PRELIVE_LEAD_SEC))
            log.append(f"watching-regress→{next_state} {item_id}")

        # 규칙 2: watching 계속 — 3분 간격 폴링
        else:
            next_state = "watching"
            next_check_at = _after(now, PRELIVE_TIGHT_SEC)
            log.append(f"watching-check {item_id}")

    # ─ 규칙 5·6: live 상태 ─
    elif state == "live":
        if live_seen is False:
            # live_seen=False (명시적으로 live 아님 확인) → end 로 전이.
            # live_seen=None(미확인)은 여기서 종료로 보지 않는다 — 계속 live 유지하고 재확인 예약.
            next_state = "end"
            next_check_at = _after(now, END_TICK_SEC)
            log.append(f"→end {item_id}")

        else:
            # live_seen=True 또는 None → 계속 live
            # 규칙 5·6: 시작 후 시간에 따라 폴링 간격 조정
            elapsed_sec = (now - actual_start).total_seconds() if actual_start else 0
            if elapsed_sec < LIVE_EARLY_WINDOW_SEC:
                # 초기 (60분 미만): 10분 간격
                next_check_at = _after(now, LIVE_EARLY_SEC)
            else:
                # 후기 (60분 이상): 5분 간격
                next_check_at = _after(now, LIVE_TIGHT_SEC)
            log.append(f"live-check {item_id}")

    # ─ 규칙 7·8·9: end 상태 ─
    elif state == "end":
        # 규칙 9: 예고 스트림 재등장 (preview_stream_seen=True)
        if preview_stream_seen:
            next_state = "upcoming"
            next_check_at = _after(now, PRELIVE_TIGHT_SEC)
            log.append(f"end-recover→upcoming {item_id}")

        # 규칙 8: 30분 경과 → none (삭제)
        elif state_since and (now - state_since).total_seconds() >= END_WINDOW_SEC:
            next_state = "none"
            next_check_at = None
            log.append(f"end→none {item_id}")

        # 규칙 7: end 창 (30분 미만) — 5분 간격
        else:
            next_state = "end"
            next_check_at = _after(now, END_TICK_SEC)
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
    # 주석의 의도("ss - 3분 후" = watching 진입 뒤)에 맞게 ss-2분. 이전 값(base_now=ss-60분)은 정상 경로에선 나올 수 없는
    # 상태(watching 은 ss-3분에야 진입)라 v3.7.3 규칙 14(미래로 밀린 watching 되돌림)와 충돌해 수정.
    now_2 = "2026-08-31T12:58:00Z"
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
    print("✓ 규칙 6: live, actual_start 60분 이상 → check in 5min")
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
    assert 300 <= delta_6 <= MAX_TASK_HORIZON_SEC, f"expected ~5min, got {delta_6}sec"
    assert delta_6 == LIVE_TIGHT_SEC, f"expected LIVE_TIGHT_SEC ({LIVE_TIGHT_SEC}), got {delta_6}sec"
    print(f"  state: live, elapsed=60min → check in {delta_6}sec (~5min)")

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

    # ── v3.7.3: 왕복 차단 / 미래로 밀린 watching 되돌림 / 체크 시각 격자 ──
    print("\n" + "=" * 70)
    print("✓ 규칙 13: 강등된 예고(ss+120분 초과)는 watching 으로 재진입하지 않음 (왕복 차단)")
    print("=" * 70)
    # 실측 2026-09-18: arale 자리표시 ss=21:00 KST(12:00Z), video_id 없음. 23:00:00 KST 에 규칙 3 강등 → 다음 실행에서
    # 규칙 1 이 즉시 되돌리던 것을, 실행마다 상태를 이어받아 반복 시뮬레이션(분당 여러 번 실행)
    ph = {"id": "pv_c181ee4c", "state": "watching", "scheduled_start": "2026-09-18T12:00:00Z",
          "video_id": None, "membership": False, "state_since": "2026-09-18T11:57:15Z"}
    flips = 0
    cur = dict(ph)
    for now_x in ("2026-09-18T13:59:00Z", "2026-09-18T14:00:00Z", "2026-09-18T14:00:05Z",
                  "2026-09-18T14:00:13Z", "2026-09-18T14:01:00Z", "2026-09-18T14:30:00Z",
                  "2026-09-18T14:59:59Z"):
        t = derive(cur, now_x)
        if t.next_state != cur["state"]:
            flips += 1
            cur = dict(cur, state=t.next_state)
    assert cur["state"] == "announced" and flips == 1, (cur["state"], flips)
    print("  watching→announced 딱 1번(23:00:00 KST), 이후 실행 6회 동안 announced 유지 (수정 전: 매 실행 왕복)")

    up = {"id": "pv_x", "state": "upcoming", "scheduled_start": "2026-09-18T12:00:00Z", "video_id": "vid",
          "state_since": "2026-09-18T11:00:00Z"}
    t = derive(up, "2026-09-18T15:00:00Z")
    assert t.next_state == "upcoming" and t.next_check_at is None and any("late-hold" in l for l in t.log), t
    assert derive(up, "2026-09-18T13:59:00Z").next_state == "watching", "ss+120분 이내는 종전대로 watching 진입"
    print("  ss+120분 이내는 종전대로 watching 진입, 초과면 late-hold(다음 체크 없음)")

    print("\n" + "=" * 70)
    print("✓ 규칙 14: ss 가 3분보다 미래로 밀린 watching → 대기 상태로 되돌림")
    print("=" * 70)
    # 실측 2026-09-17: DWMQTpDQ1fc 는 수신 시각(17:03 KST)을 ss 로 잡아 watching 이 된 뒤 API 시작 시각(9/25)으로
    # 정정됐는데 watching 이 유지돼 48시간 동안 wake 가 이어졌다.
    w = {"id": "pv_f4f2157c", "state": "watching", "scheduled_start": "2026-09-25T10:30:00Z",
         "video_id": "DWMQTpDQ1fc", "state_since": "2026-09-17T08:10:02Z"}
    t = derive(w, "2026-09-19T08:00:00Z")
    assert t.next_state == "upcoming" and t.next_check_at == "2026-09-25T10:27:00Z", (t.next_state, t.next_check_at)
    t = derive(dict(w, video_id=None), "2026-09-19T08:00:00Z")
    assert t.next_state == "announced" and t.next_check_at == "2026-09-25T10:27:00Z", (t.next_state, t.next_check_at)
    near = dict(w, scheduled_start="2026-09-19T08:05:00Z")
    assert derive(near, "2026-09-19T08:00:00Z").next_state == "upcoming"
    assert derive(dict(near, state="upcoming"), "2026-09-19T08:02:30Z").next_state == "watching"
    assert derive(w, "2026-09-19T08:00:00Z", live_seen=True).next_state == "live", "시작 신호가 예정 시각보다 우선"
    assert derive(dict(w, scheduled_start="2026-09-19T08:02:00Z"), "2026-09-19T08:00:00Z").next_state == "watching"
    print("  미래로 밀린 watching → upcoming(video_id 있음)/announced(없음) + ss-3분 예약, live_seen 우선, 정상 watching 유지")

    print("\n" + "=" * 70)
    print("✓ 규칙 15: 상대 체크 시각은 주기 격자에 맞춰져 실행 위상이 달라도 같은 시각으로 수렴 (체인 증식 차단)")
    print("=" * 70)
    from datetime import datetime as _dt, timezone as _tz
    for state, kw, sec in (("watching", {}, PRELIVE_TIGHT_SEC), ("live", {"actual_start": "2026-09-19T08:00:00Z"}, LIVE_EARLY_SEC),
                           ("live", {"actual_start": "2026-09-19T05:00:00Z"}, LIVE_TIGHT_SEC)):
        base = {"id": "pv_g", "state": state, "scheduled_start": "2026-09-19T08:00:00Z", "video_id": "v", **kw}
        # 같은 sec 구간 안에서 서로 다른 실행 시각(초 단위 위상 차이)이 같은 next_check_at 으로 모이는지
        seen = {}
        for off in range(0, sec, 7):
            n = _dt(2026, 9, 19, 8, 30, 0, tzinfo=_tz.utc).timestamp() // sec * sec + off
            now_i = _dt.fromtimestamp(n, _tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            tk = derive(base, now_i)
            d = (_dt.fromisoformat(tk.next_check_at.replace("Z", "+00:00")) - _dt.fromisoformat(now_i.replace("Z", "+00:00"))).total_seconds()
            assert sec / 2 <= d < 1.5 * sec, (state, sec, off, d)
            seen[tk.next_check_at] = seen.get(tk.next_check_at, 0) + 1
        assert len(seen) <= 2, f"한 주기 안의 실행이 {len(seen)}개 시각으로 흩어짐: {list(seen)}"
    print("  watching(180s)/live 초기(600s)/live 후기(300s): 한 주기 안 어느 위상에서 실행해도 다음 체크는 ≤2개 격자 시각")

    # 위상이 다른 3개 체인이 하나로 합쳐지는지 시뮬레이션 — 수정 전(now+180s)은 3개 유지, 수정 후 1개로 수렴
    def chains(step_fn, starts):
        # 체인 수 = 서로 다른 위상(t mod 주기)의 개수. 같은 위상의 체인은 정확히 주기의 배수만큼 어긋난
        # 같은 시퀀스라 태스크 이름((영상, 분))이 겹쳐 하나로 dedupe 된다.
        ts = list(starts)
        for _ in range(12):
            ts = sorted({step_fn(t) for t in ts})
        return len({round(t) % PRELIVE_TIGHT_SEC for t in ts})
    def _iso(t): return _dt.fromtimestamp(t, _tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    w3 = {"id": "pv_w", "state": "watching", "scheduled_start": "2026-09-19T08:00:00Z", "video_id": "v"}
    def fixed(t): return t + PRELIVE_TIGHT_SEC
    def snapped(t): return _dt.fromisoformat(derive(w3, _iso(t)).next_check_at.replace("Z", "+00:00")).timestamp()
    t0 = _dt(2026, 9, 19, 8, 33, 0, tzinfo=_tz.utc).timestamp()
    starts = [t0, t0 + 60, t0 + 121]           # 위상이 다른 체인 3개
    assert chains(fixed, starts) == 3 and chains(snapped, starts) == 1
    print("  위상 다른 3개 체인: 수정 전 방식(now+180s)은 3개 유지, 격자 방식은 1개로 수렴")

    print("\n" + "=" * 70)
    print("SUCCESS: 모든 15개 시나리오 통과 ✓")
    print("=" * 70)
