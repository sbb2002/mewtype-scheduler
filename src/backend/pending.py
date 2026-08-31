"""
pending.json 스키마 및 헬퍼 함수.
계약 E 참고: §3 IMPLEMENTATION_v2.md
"""

import logging

logger = logging.getLogger(__name__)

PHASE_PRELIVE = "pre-live"
PHASE_LIVEWATCH = "live-watch"


def default_pending() -> dict:
    """
    기본 pending.json 형태 반환.

    Returns:
        {"updated_at": None, "entries": {}}
    """
    return {"updated_at": None, "entries": {}}


def make_entry(
    *,
    channel_key: str,
    scheduled_start: str | None,
    next_check_at: str,
    now_iso: str,
    phase: str = PHASE_PRELIVE,
    actual_start: str | None = None,
) -> dict:
    """
    계약 E 형태의 엔트리 1개 생성.

    Args:
        channel_key: 채널 식별자 (예: "arale")
        scheduled_start: 예정 시작 시각 (ISO 'Z' format 또는 None)
        next_check_at: 다음 점검 시각 (ISO 'Z' format)
        now_iso: 현재 시각 (ISO 'Z' format) — first_seen으로 사용
        phase: "pre-live" 또는 "live-watch" (기본: "pre-live")
        actual_start: 실제 시작 시각 (ISO 'Z' format 또는 None, 기본 None)

    Returns:
        엔트리 dict
    """
    return {
        "channel_key": channel_key,
        "phase": phase,
        "scheduled_start": scheduled_start,
        "actual_start": actual_start,
        "next_check_at": next_check_at,
        "attempts": 0,
        "first_seen": now_iso,
        "last_checked": None,
    }


def validate(pending: dict) -> dict:
    """
    pending 구조 방어 및 정제.

    dict가 아니거나 entries 키가 없으면 default_pending() 반환.
    엔트리 중 필수 키(channel_key, phase, next_check_at)가 없거나
    phase 값이 유효하지 않으면 그 엔트리만 제외한 새 dict 반환 (원본 불변).
    각 제외 이유는 logging.warning으로 남김.

    Args:
        pending: 검증할 dict

    Returns:
        정제된 pending dict
    """
    if not isinstance(pending, dict):
        logger.warning("pending is not a dict, returning default")
        return default_pending()

    if "entries" not in pending:
        logger.warning("pending missing 'entries' key, returning default")
        return default_pending()

    valid_phases = {PHASE_PRELIVE, PHASE_LIVEWATCH}
    cleaned_entries = {}

    for video_id, entry in pending.get("entries", {}).items():
        if not isinstance(entry, dict):
            logger.warning(f"entry {video_id} is not a dict, skipping")
            continue

        # 필수 키 확인
        if "channel_key" not in entry:
            logger.warning(f"entry {video_id} missing 'channel_key', skipping")
            continue
        if "phase" not in entry:
            logger.warning(f"entry {video_id} missing 'phase', skipping")
            continue
        if "next_check_at" not in entry:
            logger.warning(f"entry {video_id} missing 'next_check_at', skipping")
            continue

        # phase 값 확인
        if entry["phase"] not in valid_phases:
            logger.warning(f"entry {video_id} has invalid phase '{entry['phase']}', skipping")
            continue

        cleaned_entries[video_id] = entry

    return {
        "updated_at": pending.get("updated_at"),
        "entries": cleaned_entries,
    }


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대비
    except Exception:
        pass

    # 간단한 smoke test

    # 1. default_pending
    default = default_pending()
    assert default == {"updated_at": None, "entries": {}}, "default_pending failed"
    print("✓ default_pending")

    # 2. make_entry
    entry = make_entry(
        channel_key="arale",
        scheduled_start="2026-08-31T13:00:00Z",
        next_check_at="2026-08-31T12:45:00Z",
        now_iso="2026-08-31T12:00:00Z",
        phase=PHASE_PRELIVE,
    )
    assert entry["channel_key"] == "arale"
    assert entry["phase"] == PHASE_PRELIVE
    assert entry["attempts"] == 0
    assert entry["first_seen"] == "2026-08-31T12:00:00Z"
    assert entry["last_checked"] is None
    print("✓ make_entry")

    # 3. validate - 정상
    pending = {
        "updated_at": "2026-08-31T12:00:00Z",
        "entries": {
            "vid1": make_entry(
                channel_key="arale",
                scheduled_start="2026-08-31T13:00:00Z",
                next_check_at="2026-08-31T12:45:00Z",
                now_iso="2026-08-31T12:00:00Z",
            )
        },
    }
    validated = validate(pending)
    assert "vid1" in validated["entries"]
    print("✓ validate (normal)")

    # 4. validate - 잘못된 phase
    bad_pending = {
        "updated_at": None,
        "entries": {
            "vid_bad": {
                "channel_key": "arale",
                "phase": "invalid-phase",
                "next_check_at": "2026-08-31T12:45:00Z",
            }
        },
    }
    validated = validate(bad_pending)
    assert "vid_bad" not in validated["entries"]
    print("✓ validate (invalid phase rejected)")

    # 5. validate - 필수 키 누락
    incomplete = {
        "updated_at": None,
        "entries": {
            "vid_incomplete": {
                "channel_key": "arale",
                # phase, next_check_at 누락
            }
        },
    }
    validated = validate(incomplete)
    assert "vid_incomplete" not in validated["entries"]
    print("✓ validate (incomplete entry rejected)")

    # 6. validate - dict 아님
    validated = validate(None)
    assert validated == {"updated_at": None, "entries": {}}
    print("✓ validate (non-dict rejected)")

    print("\nSUCCESS: pending.py smoke test passed")
