"""
Reconciliation logic: merge video data with previous schedule state.
Builds new schedule.json and identifies newly ended broadcasts for archive.json.
"""

import json
import types
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .youtube import VideoInfo

# videos.list 응답에서 추적 중이던 방송이 통째로 빠지면(= liveBroadcastContent 신호조차 없음)
# 보통은 삭제/비공개다. 하지만 배치 응답 일시 누락이나 "공개 → 회원전용/비공개" 전환 순간에도
# 똑같이 빠지므로, 곧바로 archive("removed") 하면 오탐이 남는다(archive 는 video_id dedupe 라
# 되돌리기 지저분함). last_updated 기준 이 시간 이상 연속 누락일 때만 진짜 삭제로 본다.
# light tick 3h 간격의 2회분 + 여유.
STALE_REMOVE_SEC = 6 * 3600 + 1800  # 6.5h


def _age_sec(iso_then: str, now_iso: str) -> float:
    """now_iso - iso_then 을 초로. 파싱 실패 시 0 (= 유예 없이 즉시 처리)."""
    try:
        then = datetime.fromisoformat(iso_then.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return (now - then).total_seconds()
    except (ValueError, AttributeError):
        return 0.0


def _reached(iso_when: str, now_iso: str) -> bool:
    """now 가 iso_when 시각에 도달했는지. 파싱 실패 시 False (= 보존)."""
    try:
        when = datetime.fromisoformat(iso_when.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        return now >= when
    except (ValueError, AttributeError):
        return False


# scheduled 행(X 릴레이 유래, video_id 없음): 실물 upcoming/live 가 같은 채널에서
# 이 시각 ±이만큼 안에 뜨면 그 예고가 실물로 확정된 것으로 보고 제거(supersede).
# 한 멤버가 저녁+翌朝 2슬롯을 잡는 경우가 있어 날짜 통째가 아니라 시간 근접으로 본다.
SCHEDULED_SUPERSEDE_SEC = 4 * 3600
# expires_at 이 없을 때(시각 파싱 실패) first_seen 으로부터의 TTL.
SCHEDULED_NO_TIME_TTL_SEC = 18 * 3600


def build_schedule(
    channels_cfg: dict,
    videos: dict[str, "VideoInfo"],
    prev_schedule: dict,
    now_iso: str,
    avatars: dict | None = None,
) -> tuple[dict, list[dict]]:
    """
    Build new schedule and identify newly ended broadcasts.

    Args:
        channels_cfg: {"channel_order": [...], "channels": {key: {...}}}
        videos: {video_id: VideoInfo}
        prev_schedule: Previous schedule.json (or default if new)
        now_iso: Current time in ISO format (e.g., "2026-08-30T12:00:00Z")
        avatars: optional {channel_id: avatar_url}. When a channel is absent here,
                 its avatar is carried over from prev_schedule.

    Returns:
        (new_schedule, newly_ended) where:
        - new_schedule follows contract A
        - newly_ended is a list of archive records (contract B)
    """
    avatars = avatars or {}
    prev_channels = (prev_schedule or {}).get("channels", {}) or {}
    # Build channel_id -> channel_key mapping
    channel_id_to_key = {}
    for key, channel_info in channels_cfg["channels"].items():
        channel_id_to_key[channel_info["channel_id"]] = key

    # Build prev_broadcasts lookup: {video_id: broadcast_row}
    prev_broadcasts = {}
    if prev_schedule.get("broadcasts"):
        for bcast in prev_schedule["broadcasts"]:
            # scheduled 행은 video_id 가 없다 → sched_id 로 키.
            prev_broadcasts[bcast.get("video_id") or bcast.get("sched_id")] = bcast

    # Prepare new schedule structure
    new_schedule = {
        "generated_at": now_iso,
        "channel_order": channels_cfg["channel_order"],
        "channels": {},
        "broadcasts": [],
    }

    # Build channels with derived channel_url
    for key in channels_cfg["channel_order"]:
        ch = channels_cfg["channels"][key].copy()
        ch["channel_url"] = f"https://www.youtube.com/@{ch['handle']}"
        avatar = avatars.get(ch["channel_id"]) or prev_channels.get(key, {}).get("avatar")
        if avatar:
            ch["avatar"] = avatar
        new_schedule["channels"][key] = ch

    newly_ended = []

    # Process each video
    for video_id, video in videos.items():
        # Skip if channel_id not in our 5 channels
        if video.channel_id not in channel_id_to_key:
            continue

        channel_key = channel_id_to_key[video.channel_id]

        if video.live_state == "upcoming":
            # Add as upcoming broadcast
            broadcast = {
                "video_id": video_id,
                "channel_key": channel_key,
                "title": video.title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": video.thumbnail,
                "status": "upcoming",
                "scheduled_start": video.scheduled_start,
                "actual_start": None,
                "concurrent_viewers": None,
                "first_seen": prev_broadcasts.get(video_id, {}).get("first_seen", now_iso),
                "last_updated": now_iso,
            }
            new_schedule["broadcasts"].append(broadcast)

        elif video.live_state == "live":
            # Add as live broadcast
            broadcast = {
                "video_id": video_id,
                "channel_key": channel_key,
                "title": video.title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": video.thumbnail,
                "status": "live",
                "scheduled_start": video.scheduled_start,
                "actual_start": video.actual_start,
                "concurrent_viewers": video.concurrent_viewers,
                "first_seen": prev_broadcasts.get(video_id, {}).get("first_seen", now_iso),
                "last_updated": now_iso,
            }
            new_schedule["broadcasts"].append(broadcast)

        elif video.live_state == "none":
            # live_state is "none" - check if it was previously tracked
            if video_id in prev_broadcasts:
                prev_entry = prev_broadcasts[video_id]
                if prev_entry["status"] in ("upcoming", "live"):
                    # Was tracking it, now it's "none"
                    if video.actual_end:
                        # Has end time -> naturally ended
                        reason = "ended"
                    else:
                        # No end time -> was canceled
                        reason = "canceled"

                    ended_rec = ended_record(prev_entry, video, reason, now_iso)
                    newly_ended.append(ended_rec)

    # Check for videos that were in prev but are now entirely absent
    for prev_video_id, prev_entry in prev_broadcasts.items():
        if prev_video_id in videos:
            continue
        if prev_entry["status"] not in ("upcoming", "live"):
            continue
        # 통째로 사라짐. 마지막으로 본 지 얼마 안 됐으면 유예 — 마지막 상태 그대로 유지하고
        # archive 하지 않는다. STALE_REMOVE_SEC 이상 연속 누락이면 진짜 삭제로 보고 archive.
        last_seen = prev_entry.get("last_updated")
        if last_seen and _age_sec(last_seen, now_iso) < STALE_REMOVE_SEC:
            new_schedule["broadcasts"].append(dict(prev_entry))  # carry forward, no bump
            continue
        newly_ended.append(ended_record(prev_entry, None, "removed", now_iso))

    # scheduled 행(X 릴레이) 보존 — video_id 가 없어 위 루프들이 다루지 않는다.
    #   · expires_at 도달(또는 시각 없고 first_seen+18h 경과) → 제거
    #   · 같은 채널 실물 upcoming/live 가 ±4h 안에 있음 → supersede(제거)
    #   · 그 외 → 그대로 이관 (다음 tick 이 다시 판정)
    _real = [
        b for b in new_schedule["broadcasts"] if b.get("status") in ("upcoming", "live")
    ]
    for prev_entry in prev_broadcasts.values():
        if prev_entry.get("status") != "scheduled":
            continue
        exp = prev_entry.get("expires_at")
        if exp:
            if _reached(exp, now_iso):
                continue
        else:
            fs = prev_entry.get("first_seen")
            if fs and _age_sec(fs, now_iso) >= SCHEDULED_NO_TIME_TTL_SEC:
                continue
        ss = prev_entry.get("scheduled_start")
        if ss and any(
            r.get("channel_key") == prev_entry.get("channel_key")
            and r.get("scheduled_start")
            and abs(_age_sec(r["scheduled_start"], ss)) <= SCHEDULED_SUPERSEDE_SEC
            for r in _real
        ):
            continue
        new_schedule["broadcasts"].append(dict(prev_entry))

    # Sort: live → upcoming → scheduled, then scheduled_start asc (None last), then id.
    _rank = {"live": 0, "upcoming": 1, "scheduled": 2}

    def sort_key(bcast):
        scheduled = bcast.get("scheduled_start")
        ident = bcast.get("video_id") or bcast.get("sched_id") or ""
        return (_rank.get(bcast.get("status"), 3), scheduled is None, scheduled or "", ident)

    new_schedule["broadcasts"].sort(key=sort_key)

    return new_schedule, newly_ended


def ended_record(
    prev_entry: dict,
    video: "VideoInfo | None",
    reason: str,
    now_iso: str,
) -> dict:
    """
    Build an archive record (contract B) for an ended broadcast.

    Args:
        prev_entry: Previous broadcast row from schedule.json
        video: VideoInfo if available, else None
        reason: "ended" | "canceled" | "removed"
        now_iso: Current time in ISO format

    Returns:
        Archive record following contract B
    """
    record = {
        "video_id": prev_entry["video_id"],
        "channel_key": prev_entry["channel_key"],
        "title": prev_entry["title"],
        "url": prev_entry["url"],
        "thumbnail": prev_entry["thumbnail"],
        "status": "ended",
        "scheduled_start": prev_entry.get("scheduled_start"),
        "actual_start": prev_entry.get("actual_start"),
        "actual_end": video.actual_end if video else prev_entry.get("actual_end"),
        "archived_at": now_iso,
        "reason": reason,
    }
    return record


if __name__ == "__main__":
    import json
    import os

    # Load channels config
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    channels_path = os.path.join(repo_root, "config", "channels.json")
    with open(channels_path, encoding="utf-8") as f:
        channels_cfg = json.load(f)

    # Create fake VideoInfo objects using SimpleNamespace
    now_iso = "2026-08-30T12:00:00Z"

    videos = {
        # One upcoming
        "upcoming_vid": types.SimpleNamespace(
            video_id="upcoming_vid",
            channel_id="UCWfF0DB6m_t2CE3KcOOOX7g",  # arale
            title="Upcoming Test",
            thumbnail="https://i.ytimg.com/vi/upcoming_vid/hqdefault.jpg",
            live_state="upcoming",
            scheduled_start="2026-08-30T13:00:00Z",
            actual_start=None,
            actual_end=None,
            concurrent_viewers=None,
        ),
        # One live
        "live_vid": types.SimpleNamespace(
            video_id="live_vid",
            channel_id="UC99kOG6_9RD0mR3OG4EOfxw",  # yuno
            title="Live Test",
            thumbnail="https://i.ytimg.com/vi/live_vid/hqdefault.jpg",
            live_state="live",
            scheduled_start="2026-08-30T12:00:00Z",
            actual_start="2026-08-30T12:05:00Z",
            actual_end=None,
            concurrent_viewers=1234,
        ),
        # One "none" that was previously upcoming with actual_end (ended)
        "ended_vid": types.SimpleNamespace(
            video_id="ended_vid",
            channel_id="UCGeCnpimiSN5rgiKbJzHd3A",  # nonoka
            title="Ended Test",
            thumbnail="https://i.ytimg.com/vi/ended_vid/hqdefault.jpg",
            live_state="none",
            scheduled_start=None,
            actual_start=None,
            actual_end="2026-08-30T11:45:00Z",
            concurrent_viewers=None,
        ),
    }

    # Previous schedule: 하나 진행중, 하나는 오래 사라짐(→removed), 하나는 방금 사라짐(→유예)
    prev_schedule = {
        "generated_at": "2026-08-30T11:00:00Z",
        "channel_order": channels_cfg["channel_order"],
        "channels": channels_cfg["channels"],
        "broadcasts": [
            {
                "video_id": "ended_vid",
                "channel_key": "nonoka",
                "title": "Ended Test",
                "url": "https://www.youtube.com/watch?v=ended_vid",
                "thumbnail": "https://i.ytimg.com/vi/ended_vid/hqdefault.jpg",
                "status": "upcoming",
                "scheduled_start": "2026-08-30T11:00:00Z",
                "actual_start": None,
                "concurrent_viewers": None,
                "first_seen": "2026-08-30T10:00:00Z",
                "last_updated": "2026-08-30T11:00:00Z",
            },
            {
                "video_id": "removed_vid",
                "channel_key": "ritsu",
                "title": "Removed Test",
                "url": "https://www.youtube.com/watch?v=removed_vid",
                "thumbnail": "https://i.ytimg.com/vi/removed_vid/hqdefault.jpg",
                "status": "live",
                "scheduled_start": "2026-08-30T10:00:00Z",
                "actual_start": "2026-08-30T10:02:00Z",
                "concurrent_viewers": 5000,
                "first_seen": "2026-08-30T09:00:00Z",
                "last_updated": "2026-08-30T02:00:00Z",  # 10h 전 — STALE_REMOVE_SEC 초과 → removed
            },
            {
                "video_id": "grace_vid",
                "channel_key": "miyako",
                "title": "Grace Test",
                "url": "https://www.youtube.com/watch?v=grace_vid",
                "thumbnail": "https://i.ytimg.com/vi/grace_vid/hqdefault.jpg",
                "status": "upcoming",
                "scheduled_start": "2026-08-30T14:00:00Z",
                "actual_start": None,
                "concurrent_viewers": None,
                "first_seen": "2026-08-30T09:00:00Z",
                "last_updated": "2026-08-30T11:00:00Z",  # 1h 전 — 유예, archive 안 함
            },
            # ── scheduled 행 (X 릴레이) ──
            {  # arale 실물 upcoming_vid(13:00)이 ±4h 안 → supersede 로 제거
                "video_id": None, "sched_id": "sched:arale:2026-08-30T13:00:00Z",
                "channel_key": "arale", "status": "scheduled",
                "scheduled_start": "2026-08-30T13:00:00Z", "source": "bdp_schedule",
                "first_seen": "2026-08-30T08:00:00Z",
                "expires_at": "2026-08-30T16:00:00Z",
            },
            {  # yuno 실물 live_vid(예정 12:00)와 8h 차 → 보존
                "video_id": None, "sched_id": "sched:yuno:2026-08-30T20:00:00Z",
                "channel_key": "yuno", "status": "scheduled",
                "scheduled_start": "2026-08-30T20:00:00Z", "source": "bdp_schedule",
                "first_seen": "2026-08-30T08:00:00Z",
                "expires_at": "2026-08-30T23:00:00Z",
            },
            {  # expires_at 이 now(12:00) 이전 → 제거
                "video_id": None, "sched_id": "sched:miyako:2026-08-30T09:00:00Z",
                "channel_key": "miyako", "status": "scheduled",
                "scheduled_start": "2026-08-30T09:00:00Z", "source": "bdp_schedule",
                "first_seen": "2026-08-30T08:00:00Z",
                "expires_at": "2026-08-30T11:00:00Z",
            },
        ],
    }

    # Run build_schedule
    new_schedule, newly_ended = build_schedule(channels_cfg, videos, prev_schedule, now_iso)

    broadcast_count = len(new_schedule["broadcasts"])
    reasons = sorted(r["reason"] for r in newly_ended)
    ids = {b.get("video_id") or b.get("sched_id") for b in new_schedule["broadcasts"]}

    print(f"Broadcast count: {broadcast_count}  ids={sorted(ids)}")
    print(f"Newly ended: {[(r['video_id'], r['reason']) for r in newly_ended]}")

    # upcoming_vid, live_vid, 유예된 grace_vid + supersede/TTL 안 걸린 yuno scheduled 만 남는다
    assert ids == {
        "upcoming_vid", "live_vid", "grace_vid", "sched:yuno:2026-08-30T20:00:00Z"
    }, ids
    # ended_vid(none+actual_end) → ended, removed_vid(오래 누락) → removed
    assert reasons == ["ended", "removed"], reasons
    # grace_vid 는 archive 되지 않음 + last_updated 안 건드림(볼라틸 비교에서 무시되도록)
    assert "grace_vid" not in {r["video_id"] for r in newly_ended}
    g = next(b for b in new_schedule["broadcasts"] if b.get("video_id") == "grace_vid")
    assert g["last_updated"] == "2026-08-30T11:00:00Z", g["last_updated"]
    # scheduled: arale 는 실물 ±4h → supersede, miyako 는 expires_at 경과 → 둘 다 빠짐
    _sched = [b for b in new_schedule["broadcasts"] if b.get("status") == "scheduled"]
    assert [b["sched_id"] for b in _sched] == ["sched:yuno:2026-08-30T20:00:00Z"], _sched
    print("SUCCESS: reconcile self-test passed (removed 유예 + scheduled supersede/TTL)")
