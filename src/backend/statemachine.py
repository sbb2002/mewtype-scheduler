"""
폴링 상태머신: pending.json 상태 전이 및 Cloud Tasks enqueue 계산.

계약: §4 [haiku #1] IMPLEMENTATION_v2.md 참고
순수 파이썬, 네트워크·파일·시계 접근 금지 (now_iso는 인자).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# 상수 — 문서 §백엔드 로직 그대로. config 아님, 여기 고정.
PRELIVE_LEAD_SEC = 15 * 60  # 최초 wake: scheduled_start − 15분
PRELIVE_TIGHT_SEC = 3 * 60  # scheduled_start 지난 뒤 3분 간격
PRELIVE_FALLBACK_AFTER_SEC = 60 * 60  # scheduled_start + 60분 경과 → fallback 진입
FALLBACK_RETRY_SEC = 60 * 60  # fallback에서 변동 없을 때 1시간 간격
FALLBACK_MAX_ATTEMPTS = 6  # fallback 6회 연속 실패 시 canceled로 간주
LIVEWATCH_EARLY_SEC = 30 * 60  # live 시작 ~ +60분: 30분 간격
LIVEWATCH_EARLY_WINDOW_SEC = 60 * 60
LIVEWATCH_TIGHT_SEC = 3 * 60  # +60분 이후: 3분 간격

# Cloud Tasks 는 scheduleTime 을 최대 720h(30일) 뒤까지만 허용한다.
# 그보다 먼 장기 예약(대기소/프리챗 프레임 등)은 이 상한으로 당겨서 "롱폴링"으로 처리 —
# 상한 시각에 깨어나 여전히 먼 미래면 다시 상한으로 재예약한다.
MAX_TASK_HORIZON_SEC = 29 * 24 * 60 * 60  # 696h. 720h 하드리밋보다 보수적

PHASE_PRELIVE = "pre-live"
PHASE_LIVEWATCH = "live-watch"


def _parse_iso(s: str) -> datetime:
    """
    ISO 문자열 파싱 (Z → +00:00, tz-aware UTC).

    Args:
        s: ISO 형식 문자열 (예: "2026-08-31T12:00:00Z")

    Returns:
        datetime (tz-aware UTC)
    """
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _to_iso(dt: datetime) -> str:
    """
    datetime을 ISO 문자열로 변환 (UTC, 'Z' suffix).

    Args:
        dt: datetime (timezone-aware 권장)

    Returns:
        ISO 형식 문자열 (예: "2026-08-31T12:00:00Z")
    """
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bound_schedule_time(schedule_time_iso: str, now_iso: str) -> str:
    """다음 wake 시각을 [now+60초, now+MAX_TASK_HORIZON] 범위로 클램프.

    - 과거이거나 임박한 시각 → now+60초 (Cloud Tasks 즉시 실행 방지).
    - Cloud Tasks 720h 상한을 넘는 먼 미래 → now+696시간 (롱폴링).

    Args:
        schedule_time_iso: 예정 시각 (ISO 'Z')
        now_iso: 현재 시각 (ISO 'Z')

    Returns:
        클램프된 시각 (ISO 'Z')
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
class Decision:
    """
    sync_pending 반환값: 새 pending.json과 enqueue 목록.
    """

    new_pending: dict  # 갱신된 pending.json (updated_at 포함)
    enqueue: list[tuple[str, str]] = field(default_factory=list)  # [(video_id, schedule_time_iso)]
    dropped: list[str] = field(default_factory=list)  # 이번에 pending에서 제거된 video_id
    log: list[str] = field(default_factory=list)  # 사람이 읽을 전이 로그


def sync_pending(
    prev_pending: dict,
    videos: dict[str, "VideoInfo"],
    channel_id_to_key: dict[str, str],
    now_iso: str,
    *,
    mode: str,  # "wake" | "sync"
    woken_video_id: str | None = None,
) -> Decision:
    """
    pending.json과 Cloud Tasks enqueue 목록을 계산한다.

    pending.json과 schedule.json / archive.json은 이 모듈의 책임이 아님
    (reconcile.build_schedule 담당).

    시간 파싱/산술: UTC 기준. 출력: "...Z"

    전이 규칙: 명세 §4 참고

    Args:
        prev_pending: 이전 pending.json (dict)
        videos: {video_id: VideoInfo} duck-typed (video_id, channel_id, live_state,
                scheduled_start, actual_start, actual_end, concurrent_viewers, title, thumbnail)
        channel_id_to_key: {channel_id: channel_key} 매핑
        now_iso: 현재 시각 (ISO 'Z')
        mode: "wake" 또는 "sync"
        woken_video_id: mode=="wake"일 때 깨어난 video_id (선택사항)

    Returns:
        Decision 객체
    """
    from .pending import PHASE_PRELIVE, PHASE_LIVEWATCH, validate, make_entry

    now = _parse_iso(now_iso)

    # prev_pending 검증
    pending = validate(prev_pending)
    entries = pending["entries"].copy()

    decision = Decision(new_pending=pending)
    changed = False

    # ─ 1. 신규 엔트리 감지 (mode 무관) ─
    for video_id, video in videos.items():
        if video_id in entries:
            continue  # 이미 pending에 있음

        if video.live_state == "upcoming" and video.scheduled_start:
            # 신규 upcoming
            scheduled = _parse_iso(video.scheduled_start)
            next_time = scheduled - timedelta(seconds=PRELIVE_LEAD_SEC)
            if next_time < now:
                next_time = now + timedelta(seconds=60)

            entry = make_entry(
                channel_key=channel_id_to_key.get(video.channel_id, "unknown"),
                scheduled_start=video.scheduled_start,
                next_check_at=_to_iso(next_time),
                now_iso=now_iso,
                phase=PHASE_PRELIVE,
            )
            entries[video_id] = entry
            decision.enqueue.append((video_id, _to_iso(next_time)))
            decision.log.append(f"new pre-live {video_id}")
            changed = True

        elif video.live_state == "live":
            # 신규 live (관측 누락 복구)
            next_time = now + timedelta(seconds=LIVEWATCH_EARLY_SEC)
            entry = make_entry(
                channel_key=channel_id_to_key.get(video.channel_id, "unknown"),
                scheduled_start=video.scheduled_start,
                next_check_at=_to_iso(next_time),
                now_iso=now_iso,
                phase=PHASE_LIVEWATCH,
                actual_start=video.actual_start or now_iso,
            )
            entries[video_id] = entry
            decision.enqueue.append((video_id, _to_iso(next_time)))
            decision.log.append(f"new live-watch {video_id} (관측 누락 복구)")
            changed = True

    # ─ 2. drift refresh (mode 무관) ─
    for video_id, entry in list(entries.items()):
        if entry.get("phase") != PHASE_PRELIVE:
            continue

        video = videos.get(video_id)
        if not video or video.live_state != "upcoming":
            continue

        old_scheduled = entry.get("scheduled_start")
        if video.scheduled_start != old_scheduled and video.scheduled_start:
            new_scheduled = _parse_iso(video.scheduled_start)
            if new_scheduled > now:
                # scheduled_start 변동 감지
                entry["scheduled_start"] = video.scheduled_start
                next_time = new_scheduled - timedelta(
                    seconds=PRELIVE_LEAD_SEC
                )
                if next_time < now:
                    next_time = now + timedelta(seconds=60)

                entry["next_check_at"] = _to_iso(next_time)
                entry["attempts"] = 0
                decision.enqueue.append((video_id, _to_iso(next_time)))
                decision.log.append(f"reschedule {video_id} → {_to_iso(next_time)}")
                changed = True

    # ─ 3. due 처리 (phase FSM) ─
    due_video_ids = []
    for video_id, entry in entries.items():
        next_check = _parse_iso(entry["next_check_at"])
        if next_check <= now:
            due_video_ids.append(video_id)

    # mode=="wake"이면 woken_video_id는 next_check_at 무관하게 포함
    if mode == "wake" and woken_video_id:
        if woken_video_id in entries and woken_video_id not in due_video_ids:
            due_video_ids.append(woken_video_id)

    for video_id in due_video_ids:
        entry = entries[video_id]
        phase = entry.get("phase")
        video = videos.get(video_id)

        if phase == PHASE_PRELIVE:
            if video is None or video.live_state == "none":
                # pre-live + none → fallback 시작 또는 canceled
                entry["attempts"] = entry.get("attempts", 0) + 1
                attempts = entry["attempts"]

                if attempts >= FALLBACK_MAX_ATTEMPTS:
                    # canceled로 간주, 엔트리 드롭
                    del entries[video_id]
                    decision.dropped.append(video_id)
                    decision.log.append(f"canceled {video_id}")
                    changed = True
                else:
                    # fallback 재시도
                    next_time = now + timedelta(
                        seconds=FALLBACK_RETRY_SEC
                    )
                    entry["next_check_at"] = _to_iso(next_time)
                    entry["last_checked"] = now_iso
                    decision.enqueue.append((video_id, _to_iso(next_time)))
                    decision.log.append(f"pre-live none, retry {video_id}")
                    changed = True

            elif video.live_state == "live":
                # pre-live + live → live-watch 전이
                entry["phase"] = PHASE_LIVEWATCH
                entry["actual_start"] = video.actual_start or now_iso
                entry["attempts"] = 0
                next_time = now + timedelta(
                    seconds=LIVEWATCH_EARLY_SEC
                )
                entry["next_check_at"] = _to_iso(next_time)
                entry["last_checked"] = now_iso
                decision.enqueue.append((video_id, _to_iso(next_time)))
                decision.log.append(f"pre-live→live-watch {video_id}")
                changed = True

            elif video.live_state == "upcoming":
                # pre-live + upcoming → 대기
                ss_str = entry.get("scheduled_start")
                ss = _parse_iso(ss_str) if ss_str else now
                entry["attempts"] = entry.get("attempts", 0) + 1
                attempts = entry["attempts"]

                if now < ss:
                    # 시작 시각 아직 미래
                    next_time = ss
                elif now < ss + timedelta(seconds=PRELIVE_FALLBACK_AFTER_SEC):
                    # scheduled_start 지난 뒤 60분 이내
                    next_time = now + timedelta(
                        seconds=PRELIVE_TIGHT_SEC
                    )
                else:
                    # fallback (60분 경과)
                    next_time = now + timedelta(
                        seconds=FALLBACK_RETRY_SEC
                    )

                entry["next_check_at"] = _to_iso(next_time)
                entry["last_checked"] = now_iso
                decision.enqueue.append((video_id, _to_iso(next_time)))
                decision.log.append(f"pre-live wait {video_id} attempts={attempts}")
                changed = True

        elif phase == PHASE_LIVEWATCH:
            if video is None or video.live_state == "none":
                # live-watch + none → ended, 엔트리 드롭, enqueue 없음
                del entries[video_id]
                decision.dropped.append(video_id)
                decision.log.append(f"live-watch→ended {video_id}")
                changed = True

            elif video.live_state == "live":
                # live-watch + live → 계속
                entry["attempts"] = entry.get("attempts", 0) + 1
                actual_start_str = entry.get("actual_start")
                started = (
                    _parse_iso(actual_start_str) if actual_start_str else now
                )
                elapsed = (now - started).total_seconds()

                if elapsed < LIVEWATCH_EARLY_WINDOW_SEC:
                    next_time = now + timedelta(
                        seconds=LIVEWATCH_EARLY_SEC
                    )
                else:
                    next_time = now + timedelta(
                        seconds=LIVEWATCH_TIGHT_SEC
                    )

                entry["next_check_at"] = _to_iso(next_time)
                entry["last_checked"] = now_iso
                decision.enqueue.append((video_id, _to_iso(next_time)))
                decision.log.append(f"live-watch continue {video_id}")
                changed = True

            elif video.live_state == "upcoming":
                # live-watch + upcoming → 재예약 (드문 케이스)
                entry["phase"] = PHASE_PRELIVE
                entry["attempts"] = 0
                entry["scheduled_start"] = video.scheduled_start

                if video.scheduled_start:
                    new_scheduled = _parse_iso(video.scheduled_start)
                    next_time = new_scheduled - timedelta(
                        seconds=PRELIVE_LEAD_SEC
                    )
                    if next_time < now:
                        next_time = now + timedelta(seconds=60)
                else:
                    next_time = now + timedelta(
                        seconds=FALLBACK_RETRY_SEC
                    )

                entry["next_check_at"] = _to_iso(next_time)
                entry["last_checked"] = now_iso
                decision.enqueue.append((video_id, _to_iso(next_time)))
                decision.log.append(f"live-watch→pre-live {video_id} (재예약)")
                changed = True

    # ─ 4. 마무리 ─
    # enqueue 시각을 [now+60s, now+696h] 로 클램프하고, 살아있는 엔트리의
    # next_check_at 도 같은 값으로 맞춰 pending.json 과 실제 태스크를 일치시킨다.
    bounded_enqueue = []
    for video_id, schedule_time_iso in decision.enqueue:
        bounded = _bound_schedule_time(schedule_time_iso, now_iso)
        bounded_enqueue.append((video_id, bounded))
        if video_id in entries:
            entries[video_id]["next_check_at"] = bounded

    decision.enqueue = bounded_enqueue

    # 변경 있으면 updated_at 갱신, 없으면 유지
    if changed:
        entries_copy = {}
        for vid, entry in entries.items():
            entries_copy[vid] = entry

        decision.new_pending = {
            "updated_at": now_iso,
            "entries": entries_copy,
        }
    else:
        decision.new_pending = {
            "updated_at": pending.get("updated_at"),
            "entries": entries,
        }

    return decision


if __name__ == "__main__":
    # Smoke test: 명세 §4의 6개 시나리오

    import sys
    import types

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대비
    except Exception:
        pass

    now_iso = "2026-08-31T12:00:00Z"

    # 채널 매핑
    channel_id_to_key = {"UCWfF0DB6m_t2CE3KcOOOX7g": "arale"}

    print("=" * 60)
    print("시나리오 1: 신규 upcoming → pre-live 엔트리 + enqueue")
    print("=" * 60)

    pending_1 = {"updated_at": None, "entries": {}}
    video_1 = types.SimpleNamespace(
        video_id="upcoming_vid",
        channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
        live_state="upcoming",
        scheduled_start="2026-08-31T13:00:00Z",
        actual_start=None,
        actual_end=None,
        concurrent_viewers=None,
        title="Test",
        thumbnail="http://test.jpg",
    )
    videos_1 = {"upcoming_vid": video_1}

    decision_1 = sync_pending(
        pending_1, videos_1, channel_id_to_key, now_iso, mode="sync"
    )

    assert "upcoming_vid" in decision_1.new_pending["entries"]
    assert decision_1.new_pending["entries"]["upcoming_vid"]["phase"] == PHASE_PRELIVE
    assert len(decision_1.enqueue) == 1
    print(f"✓ 엔트리 생성됨: {decision_1.new_pending['entries']['upcoming_vid']}")
    print(f"✓ enqueue: {decision_1.enqueue}")

    print("\n" + "=" * 60)
    print("시나리오 2: pre-live + live 관측 → live-watch 전이")
    print("=" * 60)

    pending_2 = {
        "updated_at": "2026-08-31T12:00:00Z",
        "entries": {
            "vid2": {
                "channel_key": "arale",
                "phase": PHASE_PRELIVE,
                "scheduled_start": "2026-08-31T13:00:00Z",
                "actual_start": None,
                "next_check_at": "2026-08-31T12:00:00Z",  # 지금 처리 대상
                "attempts": 0,
                "first_seen": "2026-08-31T11:00:00Z",
                "last_checked": None,
            }
        },
    }

    video_2 = types.SimpleNamespace(
        video_id="vid2",
        channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
        live_state="live",
        scheduled_start="2026-08-31T13:00:00Z",
        actual_start="2026-08-31T12:10:00Z",
        actual_end=None,
        concurrent_viewers=100,
        title="Test",
        thumbnail="http://test.jpg",
    )
    videos_2 = {"vid2": video_2}

    decision_2 = sync_pending(
        pending_2, videos_2, channel_id_to_key, now_iso, mode="sync"
    )

    assert decision_2.new_pending["entries"]["vid2"]["phase"] == PHASE_LIVEWATCH
    assert decision_2.new_pending["entries"]["vid2"]["actual_start"] == "2026-08-31T12:10:00Z"
    print(f"✓ phase 전이: {decision_2.new_pending['entries']['vid2']['phase']}")
    print(f"✓ log: {decision_2.log}")

    print("\n" + "=" * 60)
    print("시나리오 3: pre-live + upcoming, 시작 전 → next==scheduled_start")
    print("=" * 60)

    pending_3 = {
        "updated_at": "2026-08-31T11:00:00Z",
        "entries": {
            "vid3": {
                "channel_key": "arale",
                "phase": PHASE_PRELIVE,
                "scheduled_start": "2026-08-31T13:00:00Z",
                "actual_start": None,
                "next_check_at": "2026-08-31T12:00:00Z",  # 지금 처리
                "attempts": 0,
                "first_seen": "2026-08-31T11:00:00Z",
                "last_checked": None,
            }
        },
    }

    video_3 = types.SimpleNamespace(
        video_id="vid3",
        channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
        live_state="upcoming",
        scheduled_start="2026-08-31T13:00:00Z",
        actual_start=None,
        actual_end=None,
        concurrent_viewers=None,
        title="Test",
        thumbnail="http://test.jpg",
    )
    videos_3 = {"vid3": video_3}

    decision_3 = sync_pending(
        pending_3, videos_3, channel_id_to_key, now_iso, mode="sync"
    )

    entry_3 = decision_3.new_pending["entries"]["vid3"]
    # now < ss이므로 next = ss (13:00:00Z)
    assert entry_3["next_check_at"] == "2026-08-31T13:00:00Z", f"got {entry_3['next_check_at']}"
    print(f"✓ next_check_at: {entry_3['next_check_at']}")
    print(f"✓ enqueue: {decision_3.enqueue}")

    print("\n" + "=" * 60)
    print("시나리오 4: pre-live + 시작 60분 경과 none, attempts 누적 → canceled")
    print("=" * 60)

    now_iso_4 = "2026-08-31T13:05:00Z"  # scheduled_start(13:00) + 5분
    pending_4 = {
        "updated_at": "2026-08-31T12:00:00Z",
        "entries": {
            "vid4": {
                "channel_key": "arale",
                "phase": PHASE_PRELIVE,
                "scheduled_start": "2026-08-31T13:00:00Z",
                "actual_start": None,
                "next_check_at": now_iso_4,  # 지금 처리
                "attempts": 5,  # 5회 시도 후
                "first_seen": "2026-08-31T11:00:00Z",
                "last_checked": "2026-08-31T13:04:00Z",
            }
        },
    }

    # video 없음 (none과 동일)
    videos_4 = {}

    decision_4 = sync_pending(
        pending_4, videos_4, channel_id_to_key, now_iso_4, mode="sync"
    )

    # attempts = 6이 되면서 MAX_ATTEMPTS(6)에 도달 → 드롭
    assert "vid4" not in decision_4.new_pending["entries"]
    assert "vid4" in decision_4.dropped
    print(f"✓ 엔트리 드롭됨: {decision_4.dropped}")
    print(f"✓ log: {decision_4.log}")

    print("\n" + "=" * 60)
    print("시나리오 5: live-watch + none → ended, enqueue 없음")
    print("=" * 60)

    pending_5 = {
        "updated_at": "2026-08-31T12:00:00Z",
        "entries": {
            "vid5": {
                "channel_key": "arale",
                "phase": PHASE_LIVEWATCH,
                "scheduled_start": "2026-08-31T13:00:00Z",
                "actual_start": "2026-08-31T12:10:00Z",
                "next_check_at": "2026-08-31T12:00:00Z",  # 지금 처리
                "attempts": 1,
                "first_seen": "2026-08-31T11:00:00Z",
                "last_checked": "2026-08-31T11:59:00Z",
            }
        },
    }

    # video 없음
    videos_5 = {}

    decision_5 = sync_pending(
        pending_5, videos_5, channel_id_to_key, now_iso, mode="sync"
    )

    assert "vid5" not in decision_5.new_pending["entries"]
    assert "vid5" in decision_5.dropped
    assert len(decision_5.enqueue) == 0, "live-watch→ended는 enqueue 없음"
    print(f"✓ 엔트리 드롭됨: {decision_5.dropped}")
    print(f"✓ enqueue: {decision_5.enqueue} (비어있음)")

    print("\n" + "=" * 60)
    print("시나리오 6: drift - scheduled_start 변동 → reschedule enqueue")
    print("=" * 60)

    pending_6 = {
        "updated_at": "2026-08-31T11:00:00Z",
        "entries": {
            "vid6": {
                "channel_key": "arale",
                "phase": PHASE_PRELIVE,
                "scheduled_start": "2026-08-31T13:00:00Z",
                "actual_start": None,
                "next_check_at": "2026-08-31T12:50:00Z",  # 미래, 아직 due 아님
                "attempts": 0,
                "first_seen": "2026-08-31T10:00:00Z",
                "last_checked": None,
            }
        },
    }

    video_6 = types.SimpleNamespace(
        video_id="vid6",
        channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
        live_state="upcoming",
        scheduled_start="2026-08-31T13:30:00Z",  # 변경: 13:00 → 13:30
        actual_start=None,
        actual_end=None,
        concurrent_viewers=None,
        title="Test",
        thumbnail="http://test.jpg",
    )
    videos_6 = {"vid6": video_6}

    decision_6 = sync_pending(
        pending_6, videos_6, channel_id_to_key, now_iso, mode="sync"
    )

    entry_6 = decision_6.new_pending["entries"]["vid6"]
    assert entry_6["scheduled_start"] == "2026-08-31T13:30:00Z"
    assert entry_6["attempts"] == 0  # attempts 리셋
    # next_check_at = 13:30 - 15분 = 13:15
    assert entry_6["next_check_at"] == "2026-08-31T13:15:00Z"
    assert len(decision_6.enqueue) > 0
    print(f"✓ scheduled_start 업데이트: {entry_6['scheduled_start']}")
    print(f"✓ next_check_at 리셋: {entry_6['next_check_at']}")
    print(f"✓ enqueue: {decision_6.enqueue}")

    print("\n" + "=" * 60)
    print("시나리오 7: 장기 예약(720h 초과) → next_check_at 이 696h 상한으로 클램프")
    print("=" * 60)

    pending_7 = {"updated_at": None, "entries": {}}
    video_7 = types.SimpleNamespace(
        video_id="farfuture_vid",
        channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
        live_state="upcoming",
        scheduled_start="2028-01-01T14:30:00Z",  # 약 1년 4개월 뒤
        actual_start=None,
        actual_end=None,
        concurrent_viewers=None,
        title="Test",
        thumbnail="http://test.jpg",
    )
    decision_7 = sync_pending(
        pending_7, {"farfuture_vid": video_7}, channel_id_to_key, now_iso, mode="sync"
    )
    entry_7 = decision_7.new_pending["entries"]["farfuture_vid"]
    horizon = _to_iso(_parse_iso(now_iso) + timedelta(seconds=MAX_TASK_HORIZON_SEC))
    assert entry_7["next_check_at"] == horizon, f"got {entry_7['next_check_at']}, want {horizon}"
    assert decision_7.enqueue[0][1] == horizon
    print(f"✓ next_check_at 클램프: {entry_7['next_check_at']} (= now + 696h)")
    print(f"✓ enqueue 시각도 동일: {decision_7.enqueue}")

    print("\n" + "=" * 60)
    print("SUCCESS: 모든 7개 시나리오 통과")
    print("=" * 60)
