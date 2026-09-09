"""
Preview items schema (v3) — 순수 모듈 (네트워크·파일·시계 금지, now_iso 인자).

v2 schedule.json 을 대체. state ∈ {announced, upcoming, watching, live, end}.
none = 파일에서 삭제(반환 안 함). 각 아이템의 생애: announced → (upcoming) → (watching) → live ↔ end → none.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone


def default_preview() -> dict:
    """
    Create a default empty preview structure.

    Returns:
        {"generated_at": None, "channel_order": [...], "channels": {}, "items": []}
    """
    return {
        "generated_at": None,
        "channel_order": [],
        "channels": {},
        "items": [],
    }


def new_id(channel_key: str, first_seen_iso: str) -> str:
    """
    Generate a stable item ID from channel_key and first_seen timestamp.

    ID format: "pv_" + first 8 hex chars of sha1(f"{channel_key}|{first_seen}").

    Args:
        channel_key: e.g., "arale"
        first_seen_iso: UTC ISO timestamp, e.g., "2026-08-30T12:00:00Z"

    Returns:
        ID like "pv_a1b2c3d4"
    """
    source = f"{channel_key}|{first_seen_iso}".encode("utf-8")
    hash_obj = hashlib.sha1(source)
    return "pv_" + hash_obj.hexdigest()[:8]


def make_item(
    *,
    channel_key: str,
    state: str,
    source: str,
    now_iso: str,
    **fields
) -> dict:
    """
    Create a new preview item with defaults and user-provided fields.

    Args:
        channel_key: e.g., "arale"
        state: One of announced|upcoming|watching|live|end
        source: One of x-relay|personal|yt-notif|api|manual
        now_iso: Current time in UTC ISO format
        **fields: Optional fields (title, url, video_id, scheduled_start, etc.)
                 Missing fields get schema defaults.

    Returns:
        Item dict following preview.json contract
    """
    # 필수 필드 — now_iso 로 초기화
    item = {
        "id": new_id(channel_key, fields.get("first_seen", now_iso)),
        "state": state,
        "state_since": now_iso,
        "channel_key": channel_key,
        "source": source,
        "first_seen": fields.get("first_seen", now_iso),
        "last_updated": now_iso,
    }

    # 선택 필드 — 스키마 기본값 적용
    item["collab_with"] = fields.get("collab_with")
    item["host"] = fields.get("host")
    item["kind"] = fields.get("kind")
    item["membership"] = fields.get("membership", False)
    item["title"] = fields.get("title")
    item["url"] = fields.get("url")
    item["video_id"] = fields.get("video_id")
    item["thumbnail"] = fields.get("thumbnail")
    item["scheduled_start"] = fields.get("scheduled_start")
    item["time_tbd"] = fields.get("time_tbd", False)
    item["actual_start"] = fields.get("actual_start")
    item["concurrent_viewers"] = fields.get("concurrent_viewers")
    item["info_source"] = fields.get("info_source", source)
    item["info_at"] = fields.get("info_at")
    item["api_start_seen"] = fields.get("api_start_seen")
    item["assumed_live"] = fields.get("assumed_live", False)

    # expires_at 계산 (명세 0.1)
    expires_at = fields.get("expires_at")
    if expires_at is None:
        expires_at = _calculate_expires_at(
            fields.get("scheduled_start"),
            fields.get("time_tbd", False),
            fields.get("membership", False),
        )
    item["expires_at"] = expires_at

    return item


def _calculate_expires_at(scheduled_start: str | None, time_tbd: bool, membership: bool) -> str | None:
    """
    Calculate expires_at based on scheduled_start, time_tbd, and membership.

    Rules (명세 0.1):
    - 공개: scheduled_start + 3h
    - membership: scheduled_start + 5h
    - time_tbd: 그날 JST 자정 (00:00 JST = 15:00 UTC 이전날)
    - 시각 없으면 None

    Args:
        scheduled_start: UTC ISO or None
        time_tbd: Whether scheduled_start is date-only
        membership: Whether this is membership-only

    Returns:
        Expiry time in UTC ISO or None
    """
    if not scheduled_start:
        return None

    try:
        dt = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    if time_tbd:
        # time_tbd 아이템은 "그 날짜" 끝까지 살아야 한다 → 예정일의 다음 JST 자정에 만료.
        # (placeholder scheduled_start = "<date>T00:00:00Z" → JST 로는 그날 09:00,
        #  여기에 하루를 더해 자정으로 내리면 그 날짜의 끝 = 다음 JST 00:00.)
        jst_tz = timezone(timedelta(hours=9))
        dt_jst = dt.astimezone(jst_tz)
        next_midnight_jst = (dt_jst + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return next_midnight_jst.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 공개 또는 회원전용 기반 TTL
    ttl_hours = 5 if membership else 3
    expires = dt + timedelta(hours=ttl_hours)
    return expires.strftime("%Y-%m-%dT%H:%M:%SZ")


def match_item(
    items: list[dict],
    inc: dict,
    *,
    superscede_sec: int = 4 * 3600,
) -> dict | None:
    """
    Find an existing item that matches the incoming item by:
    - Same channel_key
    - AND (video_id match OR url match OR scheduled_start within ±superscede_sec)

    An item that has transitioned to "end" → "none" (deleted) will not match
    because it's already removed from items list (caller responsibility).

    Args:
        items: List of current preview items
        inc: Incoming item to match against
        superscede_sec: Time window for scheduled_start proximity (default 4h)

    Returns:
        Matching item dict or None
    """
    inc_channel = inc.get("channel_key")
    inc_video_id = inc.get("video_id")
    inc_url = inc.get("url")
    inc_ss = inc.get("scheduled_start")

    for item in items:
        if item.get("channel_key") != inc_channel:
            continue

        # video_id 매칭
        if inc_video_id and item.get("video_id") == inc_video_id:
            return item

        # url 매칭
        if inc_url and item.get("url") == inc_url:
            return item

        # scheduled_start 시각근접 (±superscede_sec)
        if inc_ss and item.get("scheduled_start"):
            try:
                inc_dt = datetime.fromisoformat(inc_ss.replace("Z", "+00:00"))
                item_dt = datetime.fromisoformat(
                    item["scheduled_start"].replace("Z", "+00:00")
                )
                diff_sec = abs((inc_dt - item_dt).total_seconds())
                if diff_sec <= superscede_sec:
                    return item
            except (ValueError, AttributeError):
                pass

    return None


def sort_items(items: list[dict]) -> list[dict]:
    """
    Sort items by state priority → scheduled_start asc (None last) → id.

    State priority: live > watching > upcoming > announced

    Args:
        items: List of preview items

    Returns:
        Sorted list
    """
    state_priority = {"live": 0, "watching": 1, "upcoming": 2, "announced": 3}

    def sort_key(item):
        state = item.get("state", "announced")
        priority = state_priority.get(state, 99)
        ss = item.get("scheduled_start")
        item_id = item.get("id", "")
        # (priority, is_ss_none, ss_value, id)
        return (priority, ss is None, ss or "", item_id)

    return sorted(items, key=sort_key)


def promote_state(item: dict) -> str:
    """
    Determine whether item should be promoted to "upcoming" or stay "announced".

    Rules (명세 WP-0):
    - "upcoming" = scheduled_start && !time_tbd && title && thumbnail && url && video_id
    - Otherwise = "announced"

    Args:
        item: Item dict

    Returns:
        "announced" or "upcoming"
    """
    has_ss = bool(item.get("scheduled_start"))
    no_time_tbd = not item.get("time_tbd", False)
    has_title = bool(item.get("title"))
    has_thumbnail = bool(item.get("thumbnail"))
    has_url = bool(item.get("url"))
    has_video_id = bool(item.get("video_id"))

    if (
        has_ss
        and no_time_tbd
        and has_title
        and has_thumbnail
        and has_url
        and has_video_id
    ):
        return "upcoming"

    return "announced"


def set_state(item: dict, new_state: str, now_iso: str) -> dict:
    """
    Create a copy of item with state changed.

    Updates: state, state_since, last_updated

    Args:
        item: Original item dict
        new_state: New state value
        now_iso: Current time in UTC ISO

    Returns:
        Modified copy of item
    """
    result = dict(item)
    result["state"] = new_state
    result["state_since"] = now_iso
    result["last_updated"] = now_iso
    return result


def to_archive_record(item: dict, now_iso: str) -> dict:
    """
    Convert an item to an archive record.

    Adds archived_at, preserves state (for auditing).

    Args:
        item: Item dict from preview.json
        now_iso: Current time in UTC ISO

    Returns:
        Archive record dict (intended for preview_archive.json)
    """
    record = dict(item)
    record["archived_at"] = now_iso
    return record


if __name__ == "__main__":
    # Self-test: match_item, sort_items, promote_state, new_id
    now = "2026-09-09T12:00:00Z"

    # Test 1: new_id 안정성
    id1 = new_id("arale", "2026-09-08T09:00:00Z")
    id2 = new_id("arale", "2026-09-08T09:00:00Z")
    assert id1 == id2, "new_id 재현성 실패"
    assert id1.startswith("pv_") and len(id1) == 11, "new_id 형식 실패"
    print(f"✓ new_id 안정성: {id1}")

    # Test 2: match_item — video_id 매칭
    items = [
        {
            "id": "pv_aaa1",
            "channel_key": "arale",
            "video_id": "abc123",
            "url": "https://youtube.com/watch?v=abc123",
            "scheduled_start": "2026-09-09T13:00:00Z",
            "state": "announced",
        },
    ]
    inc = {
        "channel_key": "arale",
        "video_id": "abc123",
        "url": None,
        "scheduled_start": None,
    }
    match = match_item(items, inc)
    assert match is not None and match["id"] == "pv_aaa1", "video_id 매칭 실패"
    print(f"✓ match_item (video_id): {match['id']}")

    # Test 3: match_item — url 매칭
    inc2 = {
        "channel_key": "arale",
        "video_id": None,
        "url": "https://youtube.com/watch?v=abc123",
        "scheduled_start": None,
    }
    match2 = match_item(items, inc2)
    assert match2 is not None and match2["id"] == "pv_aaa1", "url 매칭 실패"
    print(f"✓ match_item (url): {match2['id']}")

    # Test 4: match_item — 시각근접 (±4h)
    inc3 = {
        "channel_key": "arale",
        "video_id": None,
        "url": None,
        "scheduled_start": "2026-09-09T14:30:00Z",  # 1.5h 뒤
    }
    match3 = match_item(items, inc3, superscede_sec=4 * 3600)
    assert (
        match3 is not None and match3["id"] == "pv_aaa1"
    ), "시각근접 매칭 실패"
    print(f"✓ match_item (scheduled_start ±4h): {match3['id']}")

    # Test 5: match_item — 다른 channel_key 는 매칭 안 함
    inc_other = {
        "channel_key": "yuno",
        "video_id": "abc123",
        "url": None,
        "scheduled_start": None,
    }
    match_other = match_item(items, inc_other)
    assert match_other is None, "다른 채널 매칭 (false positive)"
    print(f"✓ match_item (다른 channel_key): None")

    # Test 6: sort_items 우선순위
    unsorted = [
        {
            "id": "announced1",
            "state": "announced",
            "scheduled_start": "2026-09-10T12:00:00Z",
        },
        {
            "id": "live1",
            "state": "live",
            "scheduled_start": "2026-09-09T12:00:00Z",
        },
        {
            "id": "upcoming1",
            "state": "upcoming",
            "scheduled_start": "2026-09-09T14:00:00Z",
        },
        {
            "id": "watching1",
            "state": "watching",
            "scheduled_start": "2026-09-09T13:00:00Z",
        },
    ]
    sorted_items = sort_items(unsorted)
    order = [item["id"] for item in sorted_items]
    assert order == [
        "live1",
        "watching1",
        "upcoming1",
        "announced1",
    ], f"정렬 순서 실패: {order}"
    print(f"✓ sort_items: {order}")

    # Test 7: promote_state — upcoming 조건
    full_item = {
        "scheduled_start": "2026-09-09T13:00:00Z",
        "time_tbd": False,
        "title": "Test Title",
        "thumbnail": "https://i.ytimg.com/vi/abc123/mqdefault.jpg",
        "url": "https://youtube.com/watch?v=abc123",
        "video_id": "abc123",
    }
    promoted = promote_state(full_item)
    assert promoted == "upcoming", f"upcoming 승격 실패: {promoted}"
    print(f"✓ promote_state (full): {promoted}")

    # Test 8: promote_state — announced (no video_id)
    partial_item = {
        "scheduled_start": "2026-09-09T13:00:00Z",
        "time_tbd": False,
        "title": "Test Title",
        "thumbnail": "https://i.ytimg.com/vi/abc123/mqdefault.jpg",
        "url": "https://youtube.com/watch?v=abc123",
        "video_id": None,  # 빠짐
    }
    demoted = promote_state(partial_item)
    assert demoted == "announced", f"announced 강등 실패: {demoted}"
    print(f"✓ promote_state (no video_id): {demoted}")

    # Test 9: promote_state — time_tbd
    time_tbd_item = {
        "scheduled_start": "2026-09-09T00:00:00Z",
        "time_tbd": True,  # 시각 미정
        "title": "Test",
        "thumbnail": "https://i.ytimg.com/vi/abc123/mqdefault.jpg",
        "url": "https://youtube.com/watch?v=abc123",
        "video_id": "abc123",
    }
    state_tbd = promote_state(time_tbd_item)
    assert state_tbd == "announced", f"time_tbd announced 실패: {state_tbd}"
    print(f"✓ promote_state (time_tbd): {state_tbd}")

    # Test 10: set_state
    original = {"id": "pv_test", "state": "announced", "title": "Test"}
    updated = set_state(original, "upcoming", now)
    assert updated["state"] == "upcoming", "set_state 실패"
    assert updated["state_since"] == now, "state_since 미설정"
    assert updated["last_updated"] == now, "last_updated 미설정"
    assert updated["id"] == "pv_test", "원본 수정됨"
    assert original["state"] == "announced", "원본 변경됨 (깊은 복사 실패)"
    print(f"✓ set_state: announced → upcoming, 원본 보존")

    # Test 11: to_archive_record
    item_to_archive = {
        "id": "pv_archived",
        "state": "end",
        "channel_key": "arale",
        "title": "Test",
    }
    archived = to_archive_record(item_to_archive, now)
    assert archived["archived_at"] == now, "archived_at 미설정"
    assert archived["state"] == "end", "state 변경됨"
    assert archived["id"] == "pv_archived", "id 변경됨"
    print(f"✓ to_archive_record: {archived['id']}")

    # Test 12: expires_at 계산 — 공개 3h
    item_public = make_item(
        channel_key="arale",
        state="announced",
        source="api",
        now_iso=now,
        scheduled_start="2026-09-09T13:00:00Z",
        membership=False,
    )
    assert item_public["expires_at"] == "2026-09-09T16:00:00Z", (
        f"공개 3h 만료 계산 실패: {item_public['expires_at']}"
    )
    print(f"✓ expires_at (공개 3h): {item_public['expires_at']}")

    # Test 13: expires_at 계산 — 회원전용 5h
    item_membership = make_item(
        channel_key="arale",
        state="announced",
        source="yt-notif",
        now_iso=now,
        scheduled_start="2026-09-09T13:00:00Z",
        membership=True,
    )
    assert item_membership["expires_at"] == "2026-09-09T18:00:00Z", (
        f"회원전용 5h 만료 계산 실패: {item_membership['expires_at']}"
    )
    print(f"✓ expires_at (회원전용 5h): {item_membership['expires_at']}")

    print("\n✓ All 13 self-test assertions passed")
