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


# scheduled 행(X 릴레이 유래): 실물 upcoming/live 가 (참여) 채널에서 이 시각 ±이만큼
# 안에 뜨면 그 예고가 실물로 확정된 것으로 보고 제거(supersede).
# 한 멤버가 저녁+翌朝 2슬롯을 잡는 경우가 있어 날짜 통째가 아니라 시간 근접으로 본다.
SCHEDULED_SUPERSEDE_SEC = 4 * 3600


def _carry_collab(broadcast: dict, prev_entry: dict | None) -> None:
    """(v2.6) 이전 scheduled 예고가 합동(collab_with 보유)이었으면, 실물로 확정된 행에도
    참여자 + kind='collab' 를 얹어 render 팬아웃이 유지되게 한다.

    실물 행의 channel_key(방송을 실제로 연 멤버)는 빼고 나머지를 collab_with 로 — 예고의
    channel_key 와 실물의 channel_key 가 다를 수 있으므로(개인 채널 합동) 참여자 집합에서
    실물 주체만 제외해 계산한다."""
    if not prev_entry or not prev_entry.get("collab_with"):
        return
    chain = [prev_entry.get("channel_key"), *(prev_entry.get("collab_with") or [])]
    others = [k for k in chain if k and k != broadcast.get("channel_key")]
    if others and not broadcast.get("collab_with"):
        broadcast["collab_with"] = others
    broadcast["kind"] = "collab"
# expires_at 이 없을 때(시각 파싱 실패) first_seen 으로부터의 TTL.
SCHEDULED_NO_TIME_TTL_SEC = 18 * 3600

# (핫픽스) assumed_live 인데 video_id 가 없어 실물 트래킹(wake/pending FSM)을 못 타는
# scheduled 행 — 종료를 검사할 주체가 없어 expires_at(start+3~5h) 까지 "방송 중(추정)"
# 으로 남는다. 개인 트윗/회원전용 예고에서 실제 방송이 이보다 일찍 끝나면 유령 라이브가
# 오래 걸린다 → 예고 시각 +90분이면 종료된 것으로 보고 제거. video_id 가 (어떤 경로로든)
# 채워지면 후보집합에 들어가 정규 로직이 처리하므로 이 클램프는 건너뛴다.
ASSUMED_LIVE_MAX_SEC = 90 * 60


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
            _carry_collab(broadcast, prev_broadcasts.get(video_id))
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
            _carry_collab(broadcast, prev_broadcasts.get(video_id))
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
        # (v2.6) 이 예고가 video_id 를 갖고 있었고 그게 이번 videos.list 로 확정됐으면
        # 위 루프가 이미 실물 행(+ _carry_collab)을 만들었다 → 자리표시는 버린다.
        if prev_entry.get("video_id") and prev_entry["video_id"] in videos:
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
        # (v2.6) 참여자(channel_key ∪ collab_with) 중 아무 채널에나 실물 upcoming/live 가
        # ±4h 안에 뜨면 supersede. 합동 예고였으면 그 실물 행에 collab_with 이관(팬아웃 유지).
        # host="group"(parse_appearance, 외부 이벤트)은 예외 — 추적 5채널 밖이라 TTL 로만 소멸.
        _chans = {prev_entry.get("channel_key"), *(prev_entry.get("collab_with") or [])}
        _hit = None
        if ss and not prev_entry.get("host"):
            _hit = next(
                (r for r in _real
                 if r.get("channel_key") in _chans
                 and r.get("scheduled_start")
                 and abs(_age_sec(r["scheduled_start"], ss)) <= SCHEDULED_SUPERSEDE_SEC),
                None,
            )
        if _hit is not None:
            _carry_collab(_hit, prev_entry)
            continue
        carried = dict(prev_entry)
        # 예고 시각 도달 → assumed_live. 회원전용은 API 로 실물을 못 보므로 이 플래그로만
        # "방송 중(추정)" 을 프론트에 알린다. expires_at 되면 어차피 제거됨.
        carried["assumed_live"] = bool(ss) and _reached(ss, now_iso)
        # (핫픽스) video_id 없는 assumed_live 는 종료검사 주체가 없다 → 예고 시각 +90분이면
        # 방송이 끝난 것으로 보고 제거(expires_at 을 기다리지 않는다).
        if (carried["assumed_live"] and not carried.get("video_id")
                and _age_sec(ss, now_iso) >= ASSUMED_LIVE_MAX_SEC):
            continue
        new_schedule["broadcasts"].append(carried)

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
            {  # (핫픽스) 개인 트윗 예고, video_id 없음, 시작(10:00)+2h > 90분 · expires 미도달
               #  → assumed_live 클램프로 제거 (종료검사 주체가 없어 유령 라이브 방지)
                "video_id": None, "sched_id": "sched:miyako:2026-08-30T10:00:00Z",
                "channel_key": "miyako", "status": "scheduled", "source": "personal",
                "scheduled_start": "2026-08-30T10:00:00Z",
                "first_seen": "2026-08-30T08:00:00Z",
                "expires_at": "2026-08-30T15:00:00Z",
            },
            {  # 회원전용, 시작(11:00)+1h < 90분·expires 미도달 → 보존 + assumed_live
                "video_id": None, "sched_id": "sched:ritsu:2026-08-30T11:00:00Z",
                "channel_key": "ritsu", "status": "scheduled", "members_only": True,
                "scheduled_start": "2026-08-30T11:00:00Z", "source": "bdp_schedule",
                "first_seen": "2026-08-30T08:00:00Z",
                "expires_at": "2026-08-30T15:00:00Z",
            },
            {  # host=group 합동방송 — arale 실물 upcoming_vid(13:00)와 30분 차지만
               # host 가드로 supersede 안 됨 (別 채널). expires 미도달 → 보존.
                "video_id": None, "sched_id": "sched:arale:2026-08-30T13:30:00Z",
                "channel_key": "arale", "status": "scheduled", "host": "group",
                "collab_with": ["nonoka"], "kind": "collab",
                "scheduled_start": "2026-08-30T13:30:00Z", "source": "bdp_schedule",
                "first_seen": "2026-08-30T08:00:00Z",
                "expires_at": "2026-08-30T17:00:00Z",
            },
            {  # (v2.6) 개인 채널 합동(host 없음) — nonoka 명의 예고지만 실물은 arale 채널
               # upcoming_vid(13:00). 참여자에 arale 포함 → supersede + upcoming_vid 에
               # collab_with=[nonoka] 이관.
                "video_id": None, "sched_id": "sched:nonoka:2026-08-30T13:10:00Z",
                "channel_key": "nonoka", "status": "scheduled",
                "collab_with": ["arale"], "kind": "collab",
                "scheduled_start": "2026-08-30T13:10:00Z", "source": "bdp_schedule",
                "first_seen": "2026-08-30T08:00:00Z",
                "expires_at": "2026-08-30T16:00:00Z",
            },
            {  # (v2.6) 트윗이 video_id 를 준 합동 예고 — live_vid(yuno) 로 이번에 확정됨.
               # 자리표시는 안 실리고 live_vid 행이 collab_with=[ritsu] 를 얻는다.
                "video_id": "live_vid", "sched_id": "sched:yuno:2026-08-30T12:00:00Z",
                "channel_key": "yuno", "status": "scheduled",
                "collab_with": ["ritsu"], "kind": "collab",
                "scheduled_start": "2026-08-30T12:00:00Z", "source": "bdp_schedule",
                "first_seen": "2026-08-30T08:00:00Z",
                "expires_at": "2026-08-30T15:00:00Z",
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

    # upcoming_vid, live_vid, 유예된 grace_vid + 살아남은 scheduled 3건
    # (ritsu 시작지남, yuno 미래, arale host=group 합동)
    assert ids == {
        "upcoming_vid", "live_vid", "grace_vid",
        "sched:ritsu:2026-08-30T11:00:00Z", "sched:yuno:2026-08-30T20:00:00Z",
        "sched:arale:2026-08-30T13:30:00Z",
    }, ids
    # ended_vid(none+actual_end) → ended, removed_vid(오래 누락) → removed
    assert reasons == ["ended", "removed"], reasons
    # grace_vid 는 archive 되지 않음 + last_updated 안 건드림(볼라틸 비교에서 무시되도록)
    assert "grace_vid" not in {r["video_id"] for r in newly_ended}
    g = next(b for b in new_schedule["broadcasts"] if b.get("video_id") == "grace_vid")
    assert g["last_updated"] == "2026-08-30T11:00:00Z", g["last_updated"]
    # scheduled: arale 는 실물 ±4h → supersede, miyako(09:00) 는 expires_at 경과,
    # miyako(10:00) 는 assumed_live +90분 클램프 → 셋 다 빠짐.
    # ritsu 는 시작(11:00) 1h 지남 → assumed_live(90분 이내 보존), yuno 는 미래(20:00) → False.
    _sched = {b["sched_id"]: b for b in new_schedule["broadcasts"] if b.get("status") == "scheduled"}
    assert set(_sched) == {
        "sched:ritsu:2026-08-30T11:00:00Z", "sched:yuno:2026-08-30T20:00:00Z",
        "sched:arale:2026-08-30T13:30:00Z",
    }, _sched
    assert "sched:miyako:2026-08-30T10:00:00Z" not in _sched  # (핫픽스) 90분 클램프
    assert _sched["sched:ritsu:2026-08-30T11:00:00Z"]["assumed_live"] is True
    assert _sched["sched:yuno:2026-08-30T20:00:00Z"]["assumed_live"] is False
    # host=group 합동은 멤버 실물 ±4h 여도 보존 (collab_with 도 그대로 이관)
    assert _sched["sched:arale:2026-08-30T13:30:00Z"]["collab_with"] == ["nonoka"]
    # (v2.6) 개인 채널 합동: nonoka 예고 자리표시는 사라지고 upcoming_vid 가 합동이 됨
    assert "sched:nonoka:2026-08-30T13:10:00Z" not in _sched
    _up = next(b for b in new_schedule["broadcasts"] if b.get("video_id") == "upcoming_vid")
    assert _up["kind"] == "collab" and _up["collab_with"] == ["nonoka"], _up
    # (v2.6) video_id 준 합동 예고: 자리표시 안 실리고 live_vid 가 합동이 됨
    assert "sched:yuno:2026-08-30T12:00:00Z" not in _sched
    _lv = next(b for b in new_schedule["broadcasts"] if b.get("video_id") == "live_vid")
    assert _lv["kind"] == "collab" and _lv["collab_with"] == ["ritsu"], _lv
    print("SUCCESS: reconcile self-test passed (supersede/TTL/assumed_live + host=group + v2.6 개인채널·video_id 합동)")
