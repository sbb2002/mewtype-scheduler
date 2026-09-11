"""
v3 preview.json 생성 (reconcile.py 포크 → 6상태).

reconcile.build_schedule 의 v3 대응:
  3상태 (upcoming/live/none) → 6상태 (announced/upcoming/watching/live/end/none)
  schedule.json → preview.json
  FSM 전이 적용 + ytnotif 머지 지원

순수 모듈 (네트워크·파일·시계 금지, now_iso 인자).
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING

from . import preview, statemachine

if TYPE_CHECKING:
    from ..collector.youtube import VideoInfo

# videos.list 응답에서 추적 중이던 방송이 통째로 빠지면 "removed" 으로 보기 전
# 최소 유예 시간 (light tick 3h 간격 2회 + 여유). reconcile 과 동일.
STALE_REMOVE_SEC = 6 * 3600 + 1800  # 6.5h

# announced/upcoming 예고가 실물 upcoming/live 로 확정되는 시간 범위.
# 한 멤버가 저녁+翌朝 2슬롯을 잡는 경우도 있으므로 날짜 아니라 시간 근접.
SCHEDULED_SUPERSEDE_SEC = 4 * 3600

# announced 행(x-relay/personal 유래)이 expires_at 없을 때 first_seen 기준 TTL.
ANNOUNCED_NO_TIME_TTL_SEC = 18 * 3600

# config/channels.json 의 그룹 공식 채널(@BDP_yumemita) 키. channel_order 밖(전용 레인 없음) —
# 이 채널에서 감지된 영상은 5인 합동(出演情報 과 동일하게 host="group")으로 팬아웃한다.
GROUP_CHANNEL_KEY = "group"


def _age_sec(iso_then: str, now_iso: str) -> float:
    """now_iso - iso_then 을 초로. 파싱 실패 시 0."""
    try:
        then = datetime.fromisoformat(iso_then.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return (now - then).total_seconds()
    except (ValueError, AttributeError):
        return 0.0


def _reached(iso_when: str, now_iso: str) -> bool:
    """now 가 iso_when 시각에 도달했는지. 파싱 실패 시 False."""
    try:
        when = datetime.fromisoformat(iso_when.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return now >= when
    except (ValueError, AttributeError):
        return False


def _carry_collab(broadcast: dict, prev_entry: dict | None) -> None:
    """이전 announced 예고가 합동(collab_with)이었으면, 실물에 참여자를 이관.

    실물 broadcast 의 channel_key(방송 주체)는 제외하고 나머지를 collab_with 로.
    """
    if not prev_entry or not prev_entry.get("collab_with"):
        return
    chain = [prev_entry.get("channel_key"), *(prev_entry.get("collab_with") or [])]
    others = [k for k in chain if k and k != broadcast.get("channel_key")]
    if others and not broadcast.get("collab_with"):
        broadcast["collab_with"] = others
    broadcast["kind"] = "collab"


def build_preview(
    channels_cfg: dict,
    videos: dict[str, "VideoInfo"],
    prev_preview: dict,
    now_iso: str,
    *,
    avatars: dict | None = None,
    ytnotif_items: list[dict] | None = None,
) -> tuple[dict, list[str], dict, list[dict]]:
    """
    Build new preview.json and identify wakes for Cloud Tasks enqueue.

    Args:
        channels_cfg: {"channel_order": [...], "channels": {key: {...}}}
        videos: {video_id: VideoInfo}
        prev_preview: Previous preview.json (or default if new)
        now_iso: Current time in ISO format
        avatars: optional {channel_id: avatar_url}
        ytnotif_items: optional list of ytnotif parsed dicts

    Returns:
        (new_preview, transitions, wakes, gone_items) where:
        - new_preview: dict following preview.json contract
        - transitions: list of FSM log strings (for notify.diff_events)
        - wakes: {video_id: next_check_at_iso} — Cloud Tasks targets
        - gone_items: list of archive records (handlers 가 build_archive_appends 에 넘김)
    """
    avatars = avatars or {}
    ytnotif_items = ytnotif_items or []
    prev_channels = (prev_preview or {}).get("channels", {}) or {}
    prev_items = (prev_preview or {}).get("items", []) or []

    # 채널 ID → key 매핑
    channel_id_to_key = {}
    for key, channel_info in channels_cfg["channels"].items():
        channel_id_to_key[channel_info["channel_id"]] = key

    # 이전 아이템 by video_id/id 색인 (id는 announced/personal/x-relay 용)
    prev_by_video_id = {}
    prev_by_id = {}
    for item in prev_items:
        if item.get("video_id"):
            prev_by_video_id[item["video_id"]] = item
        if item.get("id"):
            prev_by_id[item["id"]] = item

    # 새 preview 구조
    new_preview = {
        "generated_at": now_iso,
        "channel_order": channels_cfg["channel_order"],
        "channels": {},
        "items": [],
    }

    # 채널 블록 구성 (avatar carry-over 포함)
    for key in channels_cfg["channel_order"]:
        ch = channels_cfg["channels"][key].copy()
        ch["channel_url"] = f"https://www.youtube.com/@{ch['handle']}"
        avatar = avatars.get(ch["channel_id"]) or prev_channels.get(key, {}).get("avatar")
        if avatar:
            ch["avatar"] = avatar
        new_preview["channels"][key] = ch

    items = []
    transitions = []
    wakes = {}
    gone_items = []  # archive 이관 아이템들

    # ─ 1. videos.list 결과 처리 (API 확정 영상) ─
    for video_id, video in videos.items():
        if video.channel_id not in channel_id_to_key:
            continue

        channel_key = channel_id_to_key[video.channel_id]
        live_seen = video.live_state == "live"

        # 그룹 공식 채널(@BDP_yumemita) 감지 — channel_order 밖이므로 전용 레인이 없다.
        # 5인 전원 레인에 팬아웃되도록 주 레인 + collab_with 로 변환(신규 생성시에만 필요).
        group_collab_with = None
        if channel_key == GROUP_CHANNEL_KEY:
            order = channels_cfg["channel_order"]
            channel_key = order[0]
            group_collab_with = order[1:] or None

        url = f"https://www.youtube.com/watch?v={video_id}"
        # video_id 는 고유하므로 이전 아이템은 video_id 로만 정확히 잡는다.
        # (in-progress items 대상 match_item 은 백투백 방송에서 오매칭 위험 → 안 씀)
        matched = prev_by_video_id.get(video_id)

        if matched:
            # 기존 아이템 업데이트
            item = dict(matched)
            item["title"] = video.title
            item["thumbnail"] = video.thumbnail
            item["url"] = url
            item["video_id"] = video_id
            item["last_updated"] = now_iso
            # API scheduled_start 기록 (apply_overrides 용)
            item["api_start_seen"] = video.scheduled_start
            # info_source 가 personal/x-relay 면 scheduled_start 덮지 말 것
            if item.get("info_source") not in ("personal", "x-relay"):
                item["scheduled_start"] = video.scheduled_start
        else:
            # 신규 아이템
            if video.live_state in ("upcoming", "live"):
                item = preview.make_item(
                    channel_key=channel_key,
                    state="announced",  # FSM 이 판정
                    source="api",
                    now_iso=now_iso,
                    title=video.title,
                    thumbnail=video.thumbnail,
                    url=url,
                    video_id=video_id,
                    scheduled_start=video.scheduled_start,
                    api_start_seen=video.scheduled_start,
                    first_seen=now_iso,
                    collab_with=group_collab_with,
                    host="group" if group_collab_with else None,
                    kind="collab" if group_collab_with else None,
                )
            else:
                continue  # live_state="none" 은 처리 안 함 (이미 archive 됨)

        # 신규/upcoming→announced 승격 (정보 충족도)
        if item["state"] == "announced":
            promoted = preview.promote_state(item)
            if promoted != item["state"]:
                item = preview.set_state(item, promoted, now_iso)

        # live 상태 설정
        if video.live_state == "live":
            if item["state"] not in ("watching", "live", "end"):
                item = preview.set_state(item, "live", now_iso)
            item["actual_start"] = video.actual_start
            item["concurrent_viewers"] = video.concurrent_viewers
        elif video.live_state == "none" and item["state"] == "live":
            # live 였던 것이 none 으로 → end 로 전이 (라이브 종료)
            item = preview.set_state(item, "end", now_iso)
            live_seen = False  # live 아님이 확정됨

        # FSM 파생
        tick = statemachine.derive(item, now_iso, live_seen=live_seen)
        transitions.extend(tick.log)

        # 상태 업데이트
        if tick.next_state != item["state"]:
            item = preview.set_state(item, tick.next_state, now_iso)

        # none 이면 archive 이관, 아니면 items 에 추가
        if tick.next_state == "none":
            gone_items.append(preview.to_archive_record(item, now_iso))
        else:
            items.append(item)
            # 다음 체크 시각 기록 (watching/live/end 만)
            if tick.next_check_at and tick.next_state in ("watching", "live", "end"):
                wakes[video_id] = tick.next_check_at

    # ─ 2. 이전 prev_items 중 이번 videos 에 없던 것 처리 ─
    for prev_item in prev_items:
        vid = prev_item.get("video_id")
        if vid and vid in videos:
            continue  # 섹션 1 에서 이미 처리됨

        item = dict(prev_item)

        # 2-a. video_id 보유 아이템 — 이번 API 응답에서만 빠짐 → removed 유예 + FSM
        if vid:
            last_seen = item.get("last_updated")
            if not (last_seen and _age_sec(last_seen, now_iso) < STALE_REMOVE_SEC):
                # 유예 경과 → removed 로 archive
                gone_items.append(preview.to_archive_record(item, now_iso))
                continue
            # 유예 중 — carry + FSM(live_seen=None 미확인)
            tick = statemachine.derive(item, now_iso, live_seen=None)
            transitions.extend(tick.log)
            if tick.next_state != item["state"]:
                item = preview.set_state(item, tick.next_state, now_iso)
            if tick.next_state == "none":
                gone_items.append(preview.to_archive_record(item, now_iso))
                continue
            if tick.next_check_at and tick.next_state in ("watching", "live", "end"):
                wakes[vid] = tick.next_check_at
            items.append(item)
            continue

        # 2-b. video_id 없는 announced 자리표시 (x-relay/personal/yt-notif)
        announced_ss = item.get("scheduled_start")
        _host = item.get("host")
        # 참여자(channel_key ∪ collab_with) 중 아무 채널에나 실물이 ±4h 안에 뜨면 supersede.
        # host="group"(出演情報, 외부 이벤트)은 예외 — TTL 로만 소멸.
        if announced_ss and _host != "group":
            _chans = {item.get("channel_key"), *(item.get("collab_with") or [])}
            _hit = next(
                (it for it in items
                 if it.get("video_id")
                 and it.get("channel_key") in _chans
                 and it.get("scheduled_start")
                 and abs(_age_sec(it["scheduled_start"], announced_ss)) <= SCHEDULED_SUPERSEDE_SEC),
                None,
            )
            if _hit is not None:
                _carry_collab(_hit, item)  # _hit 은 items 안의 참조 → 제자리 갱신
                continue

        # expires_at / first_seen TTL
        exp = item.get("expires_at")
        if exp and _reached(exp, now_iso):
            gone_items.append(preview.to_archive_record(item, now_iso))
            continue
        if not exp:
            fs = item.get("first_seen")
            if fs and _age_sec(fs, now_iso) >= ANNOUNCED_NO_TIME_TTL_SEC:
                gone_items.append(preview.to_archive_record(item, now_iso))
                continue

        # 살아남음 — FSM(assumed_live 90분 폴백·watching 지각강등 등)
        tick = statemachine.derive(item, now_iso, live_seen=None)
        transitions.extend(tick.log)
        if tick.next_state != item["state"]:
            item = preview.set_state(item, tick.next_state, now_iso)
        if tick.next_state == "none":
            gone_items.append(preview.to_archive_record(item, now_iso))
            continue
        # video_id 없으면 wakes 에 안 넣는다 (Cloud Tasks 대상 아님 — handlers 가 light tick 예약)
        items.append(item)

    # ─ 3. ytnotif 머지 (있으면) ─
    #   video_id 로 기존 아이템을 찾아 상태/정보만 끌어올린다. 매칭 실패 + 채널 미상이면
    #   이번 틱에서는 skip — handlers 가 이 video_id 를 videos.list 후보로 넘겨 다음 틱에
    #   정규 파이프라인(섹션 1)이 채널까지 확정해 흡수한다.
    #   ponytail: 회원전용(videos.list 404 라 영영 채널 미상) 카드 구성은 D6(INGEST_YT_ENABLED) 뒤로.
    for nx_item in ytnotif_items:
        nx_vid = nx_item.get("video_id")
        # ytnotif 는 channel_key 가 없어 match_item 을 못 쓴다 → video_id 로 직접 스캔.
        idx = next((i for i, it in enumerate(items) if it.get("video_id") == nx_vid), None)
        if idx is None:
            continue
        it = dict(items[idx])
        kind = nx_item.get("kind")
        if nx_item.get("thumbnail"):
            it["thumbnail"] = it.get("thumbnail") or nx_item["thumbnail"]
        if nx_item.get("title") and not it.get("title"):
            it["title"] = nx_item["title"]
        if kind in ("reminder", "sub_start"):
            if it["state"] not in ("live", "end"):
                it = preview.set_state(it, "live", now_iso)
            it["actual_start"] = it.get("actual_start") or now_iso
        elif kind == "tunein" and it["state"] == "announced" and not it.get("scheduled_start"):
            it["scheduled_start"] = nx_item.get("scheduled_start")
        it["last_updated"] = now_iso
        items[idx] = it

    # ─ 4. 정렬 및 반환 ─
    new_preview["items"] = preview.sort_items(items)
    return new_preview, transitions, wakes, gone_items


def build_archive_appends(
    prev_archive: dict,
    gone_items: list[dict],
    now_iso: str,
) -> tuple[dict, bool]:
    """
    Append gone_items to preview_archive.json.

    Args:
        prev_archive: Previous preview_archive.json (or default if new)
        gone_items: List of archive records (from build_preview gone_items)
        now_iso: Current time (for consistency)

    Returns:
        (new_archive, changed) where:
        - new_archive: Updated archive dict
        - changed: Whether any items were appended (True if new_archive modified)
    """
    new_archive = dict(prev_archive or {})
    new_archive["generated_at"] = now_iso
    archive_items = new_archive.get("items", []) or []

    # Dedupe by (video_id, id) — 같은 아이템이 이미 archive 에 있으면 스킵
    seen_keys = {
        (it.get("video_id"), it.get("id"))
        for it in archive_items
    }

    appended_count = 0
    for item in gone_items:
        key = (item.get("video_id"), item.get("id"))
        if key not in seen_keys:
            archive_items.append(item)
            seen_keys.add(key)
            appended_count += 1

    new_archive["items"] = archive_items
    changed = appended_count > 0
    return new_archive, changed


if __name__ == "__main__":
    # Self-test: reconcile 시나리오를 6상태 preview 로 재작성 + FSM 전이 + ytnotif
    import sys
    import types

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 70)
    print("✓ Test 1: API upcoming → announced (state)")
    print("=" * 70)
    now_iso = "2026-09-09T12:00:00Z"

    # 채널 구성
    channels_cfg = {
        "channel_order": ["arale", "yuno"],
        "channels": {
            "arale": {"channel_id": "UCWfF0DB6m_t2CE3KcOOOX7g", "handle": "araragi_ch"},
            "yuno": {"channel_id": "UC99kOG6_9RD0mR3OG4EOfxw", "handle": "sengoku_yuno"},
        },
    }

    videos = {
        "vid_up": types.SimpleNamespace(
            video_id="vid_up",
            channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
            title="Test Upcoming",
            thumbnail="https://i.ytimg.com/vi/vid_up/mqdefault.jpg",
            live_state="upcoming",
            scheduled_start="2026-09-09T13:00:00Z",  # 1h 뒤, watching 미진입
            actual_start=None,
            actual_end=None,
            concurrent_viewers=None,
        ),
    }

    prev_preview = preview.default_preview()
    new_preview, trans, wakes, _g = build_preview(channels_cfg, videos, prev_preview, now_iso)

    assert len(new_preview["items"]) == 1, f"Expected 1 item, got {len(new_preview['items'])}"
    item = new_preview["items"][0]
    assert item["state"] in ("announced", "upcoming"), f"Expected announced/upcoming, got {item['state']}"
    assert item["video_id"] == "vid_up"
    assert item["title"] == "Test Upcoming"
    # wakes 는 announced 이면 watching 진입 예약되지 않음
    print(f"  item state: {item['state']}, scheduled 1h away (watching check scheduled in FSM)")

    print("\n" + "=" * 70)
    print("✓ Test 2: API live → live (FSM)")
    print("=" * 70)
    videos_live = {
        "vid_live": types.SimpleNamespace(
            video_id="vid_live",
            channel_id="UC99kOG6_9RD0mR3OG4EOfxw",
            title="Test Live",
            thumbnail="https://i.ytimg.com/vi/vid_live/mqdefault.jpg",
            live_state="live",
            scheduled_start="2026-09-09T12:00:00Z",
            actual_start="2026-09-09T12:05:00Z",
            actual_end=None,
            concurrent_viewers=500,
        ),
    }
    new_preview_2, trans_2, wakes_2, _g = build_preview(
        channels_cfg, videos_live, prev_preview, now_iso
    )
    item_2 = new_preview_2["items"][0]
    assert item_2["state"] == "live", f"Expected live, got {item_2['state']}"
    assert item_2["actual_start"] == "2026-09-09T12:05:00Z"
    assert item_2["concurrent_viewers"] == 500
    print(f"  item state: {item_2['state']}, viewers: {item_2['concurrent_viewers']}")

    print("\n" + "=" * 70)
    print("✓ Test 3: Removed 유예 (6.5h 미만)")
    print("=" * 70)
    prev_with_item = preview.default_preview()
    prev_with_item["items"] = [
        preview.make_item(
            channel_key="arale",
            state="upcoming",
            source="api",
            now_iso="2026-09-09T08:00:00Z",  # 4시간 전
            video_id="old_vid",
            title="Old",
            url="https://youtube.com/watch?v=old_vid",
            scheduled_start="2026-09-09T14:00:00Z",
            last_updated="2026-09-09T08:00:00Z",
        ),
    ]
    new_preview_3, trans_3, wakes_3, _g = build_preview(
        channels_cfg, {}, prev_with_item, now_iso  # videos 비움
    )
    # old_vid 는 4시간 누락 (< 6.5h) → 유예, carry forward
    carried = next(
        (it for it in new_preview_3["items"] if it.get("video_id") == "old_vid"), None
    )
    assert carried is not None, "old_vid should be carried (유예)"
    print(f"  old_vid carried forward (4h < 6.5h stale threshold)")

    print("\n" + "=" * 70)
    print("✓ Test 4: ytnotif 머지 (kind=reminder → 매칭된 아이템 live 승격)")
    print("=" * 70)
    # 현실: handlers 가 nx_vid 를 videos.list 후보로 넘겨 섹션 1 이 아이템을 만든다.
    videos_nx = {
        "nx_vid": types.SimpleNamespace(
            video_id="nx_vid", channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
            title="ytnotif broadcast", thumbnail="https://i.ytimg.com/vi/nx_vid/mqdefault.jpg",
            live_state="upcoming", scheduled_start=now_iso,
            actual_start=None, actual_end=None, concurrent_viewers=None,
        ),
    }
    ytnotif_list = [{
        "video_id": "nx_vid", "url": "https://youtube.com/watch?v=nx_vid",
        "thumbnail": "https://i.ytimg.com/vi/nx_vid/mqdefault.jpg",
        "title": "ytnotif broadcast", "kind": "reminder",
        "scheduled_start": now_iso, "time_approx": False, "source": "yt-notif",
    }]
    new_preview_4, trans_4, wakes_4, _g = build_preview(
        channels_cfg, videos_nx, prev_preview, now_iso, ytnotif_items=ytnotif_list
    )
    nx_item = next((it for it in new_preview_4["items"] if it.get("video_id") == "nx_vid"), None)
    assert nx_item is not None, "ytnotif item not found"
    assert nx_item["state"] == "live", f"Expected live (reminder), got {nx_item['state']}"
    assert nx_item["actual_start"] == now_iso
    print(f"  ytnotif reminder → matched item live, actual_start set")

    # 미매칭 + 채널 미상 ytnotif 는 이번 틱에서 skip
    np4b, _, _, _ = build_preview(
        channels_cfg, {}, prev_preview, now_iso, ytnotif_items=[
            {"video_id": "orphan_vid", "kind": "reminder", "scheduled_start": now_iso,
             "url": "u", "thumbnail": "t", "title": "x", "source": "yt-notif"}
        ]
    )
    assert not np4b["items"], "미매칭 ytnotif 는 skip 되어야 함"
    print("  미매칭 ytnotif skip 확인")

    print("\n" + "=" * 70)
    print("✓ Test 5: archive append (gone_items)")
    print("=" * 70)
    gone = [
        preview.to_archive_record(
            preview.make_item(
                channel_key="arale",
                state="end",
                source="api",
                now_iso=now_iso,
                video_id="ended_vid",
                title="Ended",
                url="https://youtube.com/watch?v=ended_vid",
            ),
            now_iso,
        ),
    ]
    prev_archive = preview.default_preview()  # 구조는 다르지만 items 있음
    prev_archive["items"] = []
    new_archive, changed = build_archive_appends(prev_archive, gone, now_iso)
    assert changed, "Archive should be changed"
    assert len(new_archive["items"]) == 1
    assert new_archive["items"][0]["video_id"] == "ended_vid"
    print(f"  1 item appended to archive, changed={changed}")

    print("\n" + "=" * 70)
    print("✓ Test 6: collab supersede (announced+collab_with → announced 실물에 이관)")
    print("=" * 70)
    # x-relay 예고: arale 13:00 예정, nonoka 참여
    # API: arale upcoming 13:00 실물 (비슷한 시각)
    # → 예고 사라지고, 실물 upcoming 에 collab_with=[nonoka] 이관
    videos_collab = {
        "arale_up": types.SimpleNamespace(
            video_id="arale_up",
            channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
            title="Test Collab Broadcast",
            thumbnail="https://i.ytimg.com/vi/arale_up/mqdefault.jpg",
            live_state="upcoming",
            scheduled_start="2026-09-09T13:10:00Z",  # 예고와 10분 차
            actual_start=None,
            actual_end=None,
            concurrent_viewers=None,
        ),
    }

    prev_with_collab = preview.default_preview()
    prev_with_collab["items"] = [
        preview.make_item(
            channel_key="arale",
            state="announced",
            source="x-relay",
            now_iso=now_iso,
            id="pv_collab1",
            scheduled_start="2026-09-09T13:00:00Z",
            collab_with=["nonoka"],
            kind="collab",
            first_seen=now_iso,
        ),
    ]

    new_preview_6, trans_6, wakes_6, _g = build_preview(
        channels_cfg, videos_collab, prev_with_collab, now_iso
    )
    # 실물 arale_up 이 collab_with=[nonoka] 를 얻어야 함
    # 예고 "pv_collab1" 은 supersede 로 사라짐
    assert len(new_preview_6["items"]) == 1
    arale_item = new_preview_6["items"][0]
    assert arale_item["video_id"] == "arale_up"
    assert arale_item["collab_with"] == ["nonoka"], f"Got {arale_item.get('collab_with')}"
    assert arale_item["kind"] == "collab"
    print(f"  supersede: announced collab → upcoming real, collab_with transferred")

    print("\n" + "=" * 70)
    print("✓ Test 7: announced expires_at 도달 → archive")
    print("=" * 70)
    prev_with_expired = preview.default_preview()
    prev_with_expired["items"] = [
        preview.make_item(
            channel_key="yuno",
            state="announced",
            source="x-relay",
            now_iso="2026-09-09T11:00:00Z",
            id="pv_exp1",
            scheduled_start="2026-09-09T12:30:00Z",
            expires_at="2026-09-09T11:50:00Z",  # 이미 경과
            first_seen="2026-09-09T11:00:00Z",
        ),
    ]
    new_preview_7, trans_7, wakes_7, _g = build_preview(
        channels_cfg, {}, prev_with_expired, now_iso
    )
    # 아이템이 전부 archive 로 가야 함
    assert len(new_preview_7["items"]) == 0, f"Expected 0 items, got {len(new_preview_7['items'])}"
    print(f"  expired announced removed (expires_at passed)")

    print("\n" + "=" * 70)
    print("✓ Test 8: watching 상태 FSM 전이 → live (live_seen=True)")
    print("=" * 70)
    prev_watching = preview.default_preview()
    prev_watching["items"] = [
        preview.make_item(
            channel_key="arale",
            state="watching",
            source="api",
            now_iso="2026-09-09T12:57:00Z",
            id="pv_watch1",
            video_id="watch_vid",
            url="https://youtube.com/watch?v=watch_vid",
            scheduled_start="2026-09-09T13:00:00Z",
            state_since="2026-09-09T12:57:00Z",
            first_seen=now_iso,
        ),
    ]
    # 이번 API 호출에서 watch_vid 가 live 로 보임
    videos_watch = {
        "watch_vid": types.SimpleNamespace(
            video_id="watch_vid",
            channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",
            title="Test Watch to Live",
            thumbnail="https://i.ytimg.com/vi/watch_vid/mqdefault.jpg",
            live_state="live",
            scheduled_start="2026-09-09T13:00:00Z",
            actual_start="2026-09-09T13:02:00Z",
            actual_end=None,
            concurrent_viewers=300,
        ),
    }
    new_preview_8, trans_8, wakes_8, _g = build_preview(
        channels_cfg, videos_watch, prev_watching, now_iso
    )
    assert len(new_preview_8["items"]) == 1
    item_8 = new_preview_8["items"][0]
    assert item_8["state"] == "live", f"Expected live, got {item_8['state']}"
    assert "watch_vid" in wakes_8  # live 폴링 예약
    print(f"  watching + live_seen → live, check scheduled")

    print("\n" + "=" * 70)
    print("✓ Test 9: live → end transition (API에서 none 확인)")
    print("=" * 70)
    prev_live = preview.default_preview()
    prev_live["items"] = [
        preview.make_item(
            channel_key="yuno",
            state="live",
            source="api",
            now_iso="2026-09-09T13:00:00Z",
            id="pv_live1",
            video_id="end_vid",
            url="https://youtube.com/watch?v=end_vid",
            scheduled_start="2026-09-09T13:00:00Z",
            actual_start="2026-09-09T13:00:00Z",
            state_since="2026-09-09T13:00:00Z",
            first_seen=now_iso,
        ),
    ]
    # 이번 API 호출에서 end_vid 가 live_state="none" 으로 반환됨
    videos_ended = {
        "end_vid": types.SimpleNamespace(
            video_id="end_vid",
            channel_id="UC99kOG6_9RD0mR3OG4EOfxw",
            title="Test End",
            thumbnail="https://i.ytimg.com/vi/end_vid/mqdefault.jpg",
            live_state="none",  # 더 이상 live 아님
            scheduled_start="2026-09-09T13:00:00Z",
            actual_start="2026-09-09T13:00:00Z",
            actual_end="2026-09-09T13:05:00Z",
            concurrent_viewers=None,
        ),
    }
    new_preview_9, trans_9, wakes_9, _g = build_preview(
        channels_cfg, videos_ended, prev_live, now_iso
    )
    assert len(new_preview_9["items"]) == 1
    item_9 = new_preview_9["items"][0]
    assert item_9["state"] == "end", f"Expected end, got {item_9['state']}"
    assert "end_vid" in wakes_9  # end 폴링 예약 (30분 윈도우)
    print(f"  live (live_state=none) → end, check scheduled for deletion")

    print("\n" + "=" * 70)
    print("✓ Test 10: announced assumed_live → none (90분 경과)")
    print("=" * 70)
    prev_assumed = preview.default_preview()
    prev_assumed["items"] = [
        preview.make_item(
            channel_key="miyako",
            state="announced",
            source="x-relay",
            now_iso="2026-09-09T11:00:00Z",
            id="pv_assumed1",
            scheduled_start="2026-09-09T11:30:00Z",  # 이미 1.5시간 지남
            assumed_live=True,
            video_id=None,  # video_id 없음
            first_seen="2026-09-09T11:00:00Z",
        ),
    ]
    # now_iso = "2026-09-09T12:00:00Z", ss = 11:30 → diff = 30분, assumed_live 폴백은 90분에서
    # 하지만 위 시간 설정이 이상함. 시간을 다시 설정.
    now_iso_assumed = "2026-09-09T13:00:00Z"  # 11:30으로부터 90분 경과
    prev_assumed["items"][0]["scheduled_start"] = "2026-09-09T11:30:00Z"
    new_preview_10, trans_10, wakes_10, _g = build_preview(
        channels_cfg, {}, prev_assumed, now_iso_assumed
    )
    assert len(new_preview_10["items"]) == 0, f"Expected 0 (assumed_live drop), got {len(new_preview_10['items'])}"
    print(f"  assumed_live (90min elapsed, no video_id) → none, removed")

    print("\n" + "=" * 70)
    print("✓ Test 11: ytnotif kind=tunein → 매칭 아이템에 scheduled_start 보강")
    print("=" * 70)
    # tunein 은 videos.list 가 아직 시각을 안 준 announced 아이템에 파생 시각을 채운다.
    videos_tunein = {
        "tunein_vid": types.SimpleNamespace(
            video_id="tunein_vid", channel_id="UC99kOG6_9RD0mR3OG4EOfxw",
            title="tunein broadcast", thumbnail="https://i.ytimg.com/vi/tunein_vid/mqdefault.jpg",
            live_state="upcoming", scheduled_start=None,  # 아직 시각 미상
            actual_start=None, actual_end=None, concurrent_viewers=None,
        ),
    }
    ytnotif_tunein = [{
        "video_id": "tunein_vid", "url": "https://youtube.com/watch?v=tunein_vid",
        "thumbnail": "https://i.ytimg.com/vi/tunein_vid/mqdefault.jpg",
        "title": "tunein broadcast in 30min", "kind": "tunein",
        "scheduled_start": "2026-09-09T12:30:00Z", "time_approx": True, "source": "yt-notif",
    }]
    new_preview_11, trans_11, wakes_11, _g = build_preview(
        channels_cfg, videos_tunein, preview.default_preview(), now_iso, ytnotif_items=ytnotif_tunein
    )
    assert len(new_preview_11["items"]) == 1
    item_11 = new_preview_11["items"][0]
    assert item_11["state"] in ("announced", "upcoming"), f"got {item_11['state']}"
    assert item_11["scheduled_start"] == "2026-09-09T12:30:00Z", item_11["scheduled_start"]
    print(f"  ytnotif tunein → {item_11['state']}, scheduled_start 보강됨")

    print("\n" + "=" * 70)
    print("✓ Test 12: removed 유예 경과 (6.5h 이상 누락) → archive")
    print("=" * 70)
    prev_stale = preview.default_preview()
    prev_stale["items"] = [
        preview.make_item(
            channel_key="ritsu",
            state="live",
            source="api",
            now_iso="2026-09-08T15:00:00Z",  # 21시간 전
            id="pv_stale1",
            video_id="stale_vid",
            url="https://youtube.com/watch?v=stale_vid",
            scheduled_start="2026-09-08T14:00:00Z",
            actual_start="2026-09-08T14:05:00Z",
            state_since="2026-09-08T14:05:00Z",
            last_updated="2026-09-08T15:00:00Z",
            first_seen="2026-09-08T13:00:00Z",
        ),
    ]
    new_preview_12, trans_12, wakes_12, _g = build_preview(
        channels_cfg, {}, prev_stale, now_iso
    )
    # stale_vid 는 21시간 누락 (> 6.5h) → removed로 archive
    assert len(new_preview_12["items"]) == 0
    print(f"  stale video (21h no update) → removed, archived")

    print("\n" + "=" * 70)
    print("✓ Test 13: 그룹 공식 채널(@BDP_yumemita) 영상 → 5인 팬아웃 (host=group)")
    print("=" * 70)
    channels_cfg_g = {
        "channel_order": ["arale", "yuno", "nonoka"],
        "channels": {
            "arale": {"channel_id": "UCWfF0DB6m_t2CE3KcOOOX7g", "handle": "arale_ch"},
            "yuno": {"channel_id": "UC99kOG6_9RD0mR3OG4EOfxw", "handle": "yuno_ch"},
            "nonoka": {"channel_id": "UCGeCnpimiSN5rgiKbJzHd3A", "handle": "nonoka_ch"},
            "group": {"channel_id": "UCxL_Vlnhfo46sN6vPHR_4hA", "handle": "BDP_yumemita"},
        },
    }
    videos_group = {
        "grp_vid": types.SimpleNamespace(
            video_id="grp_vid",
            channel_id="UCxL_Vlnhfo46sN6vPHR_4hA",
            title="同時視聴配信 #13",
            thumbnail="https://i.ytimg.com/vi/grp_vid/mqdefault.jpg",
            live_state="live",
            scheduled_start="2026-09-11T13:58:00Z",
            actual_start="2026-09-11T13:58:00Z",
            actual_end=None,
            concurrent_viewers=1000,
        ),
    }
    new_preview_13, trans_13, wakes_13, _g = build_preview(
        channels_cfg_g, videos_group, preview.default_preview(), now_iso
    )
    assert len(new_preview_13["items"]) == 1, new_preview_13["items"]
    grp_item = new_preview_13["items"][0]
    assert grp_item["channel_key"] == "arale", grp_item  # channel_order[0] 이 주 레인
    assert grp_item["collab_with"] == ["yuno", "nonoka"], grp_item
    assert grp_item["host"] == "group", grp_item
    assert grp_item["kind"] == "collab", grp_item
    assert grp_item["video_id"] == "grp_vid", grp_item
    assert grp_item["state"] == "live", grp_item
    print(f"  group channel video → channel_key=arale, collab_with=[yuno,nonoka], host=group")

    # 다음 tick 재매칭(video_id) — 기존 팬아웃 필드 유지 확인
    new_preview_13b, *_r = build_preview(
        channels_cfg_g, videos_group, new_preview_13, now_iso
    )
    grp_item_b = new_preview_13b["items"][0]
    assert grp_item_b["collab_with"] == ["yuno", "nonoka"], grp_item_b
    assert grp_item_b["host"] == "group", grp_item_b
    print(f"  재매칭(video_id)에도 팬아웃 필드 유지")

    print("\n" + "=" * 70)
    print("SUCCESS: 모든 13개 self-test scenarios passed ✓")
    print("=" * 70)
