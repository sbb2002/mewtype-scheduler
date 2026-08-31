"""오케스트레이션: `/tick` (Cloud Scheduler) 와 `/wake` (Cloud Tasks) 처리.

v1 collector 의 순수 모듈(rss / youtube / reconcile)을 그대로 재사용하고,
저장은 GitHub Contents API(`gh_store`), 폴링 상태는 `statemachine`(pending.json),
다음 wake 는 Cloud Tasks(`tasks`)로 나간다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..collector.config import load_channels
from ..collector.reconcile import build_schedule
from ..collector.rss import fetch_all_rss_video_ids
from ..collector.store import default_schedule
from ..collector.youtube import YouTubeClient
from .config import load_config
from .gh_store import GitHubStore
from .pending import default_pending
from .statemachine import sync_pending

log = logging.getLogger("backend.handlers")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tracked_unresolved_ids(schedule: dict) -> list[str]:
    return [
        b["video_id"]
        for b in (schedule or {}).get("broadcasts", [])
        if b.get("status") in ("upcoming", "live")
    ]


def _merge_archive(prev_archive: dict, newly_ended: list[dict], now_iso: str) -> tuple[dict, bool]:
    """archive.json 에 newly_ended 를 video_id 기준 dedupe 하며 append. (new_archive, changed)."""
    prev_archive = prev_archive or {"updated_at": None, "broadcasts": []}
    existing = {b["video_id"] for b in prev_archive.get("broadcasts", [])}
    fresh = [r for r in newly_ended if r["video_id"] not in existing]
    if not fresh:
        return prev_archive, False
    merged = {
        "updated_at": now_iso,
        "broadcasts": list(prev_archive.get("broadcasts", [])) + fresh,
    }
    return merged, True


def _make_task_queue(cfg):
    """TaskQueue 생성. 라이브러리 미설치/설정 부족(로컬)이면 None 반환."""
    try:
        from .tasks import TaskQueue

        return TaskQueue(
            project=cfg.gcp_project,
            location=cfg.gcp_location,
            queue=cfg.tasks_queue,
            target_url=cfg.service_url,
            invoker_sa=cfg.invoker_sa,
        )
    except Exception as e:  # noqa: BLE001 - 로컬/부트스트랩 허용
        log.warning("TaskQueue 비활성 (%s) — enqueue 건너뜀", e)
        return None


def _run(mode: str, woken_video_id: str | None) -> dict:
    cfg = load_config()
    now_iso = _now_iso()
    is_wake = woken_video_id is not None

    channels_cfg = load_channels()
    id_by_key = {k: v["channel_id"] for k, v in channels_cfg["channels"].items()}
    channel_id_to_key = {v["channel_id"]: k for k, v in channels_cfg["channels"].items()}

    gh = GitHubStore(cfg.github_token, cfg.github_repo, cfg.data_branch)
    prev_schedule, sched_sha = gh.read_json("schedule.json")
    if prev_schedule is None:
        prev_schedule = default_schedule(channels_cfg)
    prev_pending, pend_sha = gh.read_json("pending.json")
    if prev_pending is None:
        prev_pending = default_pending()
    prev_archive, arch_sha = gh.read_json("archive.json")

    # ── 후보 video_id 집합 ──
    candidates: set[str] = set(prev_pending.get("entries", {}).keys())
    candidates.update(_tracked_unresolved_ids(prev_schedule))
    if woken_video_id:
        candidates.add(woken_video_id)
    if not is_wake:
        rss_map = fetch_all_rss_video_ids(id_by_key)
        for ids in rss_map.values():
            candidates.update(ids)

    yt = YouTubeClient(cfg.youtube_api_key)
    avatars: dict[str, str] = {}
    if mode == "baseline":
        avatars = yt.channels_list(list(id_by_key.values()))

    videos = yt.videos_list(sorted(candidates)) if candidates else {}

    # ── schedule.json / archive.json ──
    new_schedule, newly_ended = build_schedule(
        channels_cfg, videos, prev_schedule, now_iso, avatars
    )
    sched_changed, _ = gh.write_json(
        "schedule.json", new_schedule, prev_sha=sched_sha,
        message=f"data: schedule {now_iso}",
    )
    new_archive, arch_changed = _merge_archive(prev_archive, newly_ended, now_iso)
    if arch_changed:
        gh.write_json(
            "archive.json", new_archive, prev_sha=arch_sha,
            message=f"data: archive {now_iso}",
        )

    # ── pending.json / Cloud Tasks ──
    decision = sync_pending(
        prev_pending, videos, channel_id_to_key, now_iso,
        mode=("wake" if is_wake else "sync"),
        woken_video_id=woken_video_id,
    )
    pend_changed, _ = gh.write_json(
        "pending.json", decision.new_pending, prev_sha=pend_sha,
        message=f"data: pending {now_iso}",
    )

    enqueued, enqueue_errors = 0, []
    if decision.enqueue:
        tq = _make_task_queue(cfg)
        if tq is not None:
            for vid, when in decision.enqueue:
                try:
                    tq.enqueue_wake(vid, when)
                    enqueued += 1
                except Exception as e:  # noqa: BLE001
                    enqueue_errors.append(f"{vid}: {e}")
                    log.error("enqueue 실패 %s @ %s: %s", vid, when, e)

    return {
        "mode": mode,
        "woken": woken_video_id,
        "candidates": len(candidates),
        "videos": len(videos),
        "schedule_changed": sched_changed,
        "archive_changed": arch_changed,
        "archived": [r["video_id"] for r in newly_ended],
        "pending_changed": pend_changed,
        "pending_entries": len(decision.new_pending.get("entries", {})),
        "dropped": decision.dropped,
        "enqueue_planned": len(decision.enqueue),
        "enqueued": enqueued,
        "enqueue_errors": enqueue_errors,
        "quota_used": yt.quota_used,
        "log": decision.log,
    }


def tick(mode: str) -> dict:
    """Cloud Scheduler 진입점. mode: "baseline" | "light"."""
    mode = mode if mode in ("baseline", "light") else "light"
    log.info("tick start mode=%s", mode)
    result = _run(mode, None)
    log.info("tick done: %s", result)
    return result


def wake(video_id: str) -> dict:
    """Cloud Tasks 진입점. 단일 방송 wake."""
    log.info("wake start video_id=%s", video_id)
    result = _run("wake", video_id)
    log.info("wake done: %s", result)
    return result
