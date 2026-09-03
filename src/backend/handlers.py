"""오케스트레이션: `/tick` (Cloud Scheduler) 와 `/wake` (Cloud Tasks) 처리.

v1 collector 의 순수 모듈(rss / youtube / reconcile)을 그대로 재사용하고,
저장은 GitHub Contents API(`gh_store`), 폴링 상태는 `statemachine`(pending.json),
다음 wake 는 Cloud Tasks(`tasks`)로 나간다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

from ..collector.config import load_channels
from ..collector.reconcile import build_schedule
from ..collector.rss import fetch_all_rss_video_ids
from ..collector.store import default_schedule
from ..collector.youtube import YouTubeClient
from .config import load_config
from .control import default_control, get_log_level, is_paused
from .gh_store import ConflictError, GitHubStore
from .notify import Telegram, diff_events, summary_text
from .notify import allows as notify_allows
from .pending import default_pending
from .statemachine import sync_pending

log = logging.getLogger("backend.handlers")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# 실질 변화가 없어도 generated_at(= 프론트 하단 "업데이트" 시각)은 최소 이 간격으로
# 전진시킨다 — 사용자가 "언제 마지막으로 확인됐나" 를 판단할 수 있도록. 라이브 중
# wake 3분 간격마다 커밋되는 것은 막는다.
# ponytail: 고정 임계값. 커밋 수가 문제되면 config 로 뺀다.
_HEARTBEAT_MIN_SEC = 20 * 60

# 방송이 방금 끝났으면, 정기 light tick(3h) 을 기다리지 않고 이만큼 뒤에 후속 tick 을 한 번
# Cloud Tasks 로 예약한다 — "일반 방송 끝나고 곧이어 다른 방송(회원전용 재시작 포함) 시작"
# 같은 백투백 케이스에서 다음 방송을 3h 안이 아니라 ~20분 안에 줍기 위함. quota +1콜/end.
# tick 이름이 분버킷이라 한 tick 에서 여러 방송이 끝나도 후속 tick 은 1개.
_POST_END_RECHECK_SEC = 20 * 60


def _heartbeat_generated_at(prev_gen, now_iso: str, min_sec: int = _HEARTBEAT_MIN_SEC) -> str:
    """실질 변화가 없을 때 쓸 generated_at 값.

    prev 로부터 min_sec 이상 지났으면 now 로 전진(→ 커밋 1회), 아니면 prev 유지(→ 커밋 스킵).
    """
    if not prev_gen:
        return now_iso
    try:
        prev_dt = datetime.fromisoformat(prev_gen.replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except ValueError:
        return now_iso
    return now_iso if (now_dt - prev_dt).total_seconds() >= min_sec else prev_gen


def _tracked_unresolved_ids(schedule: dict) -> list[str]:
    return [
        b["video_id"]
        for b in (schedule or {}).get("broadcasts", [])
        if b.get("status") in ("upcoming", "live")
    ]


def _stable_view(schedule: dict) -> dict:
    """schedule 에서 volatile 타임스탬프(generated_at, 각 broadcast 의 last_updated)를 뺀 비교용 뷰.

    concurrent_viewers 도 라이브 중 계속 변하므로 제외 — 시청자 수 변동만으로는 커밋/알림 안 함.
    """
    schedule = schedule or {}
    return {
        "channel_order": schedule.get("channel_order"),
        "channels": schedule.get("channels"),
        "broadcasts": sorted(
            (
                {k: v for k, v in b.items() if k not in ("last_updated", "concurrent_viewers")}
                for b in schedule.get("broadcasts", [])
            ),
            key=lambda b: b.get("video_id", ""),
        ),
    }


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


def _ping_healthcheck(url: str) -> None:
    """healthchecks.io dead-man's-switch 핑. 실패는 무시."""
    if not url:
        return
    try:
        requests.get(url, timeout=5)
    except Exception as e:  # noqa: BLE001
        log.warning("healthcheck 핑 실패: %s", e)


def _run(mode: str, woken_video_id: str | None) -> dict:
    cfg = load_config()
    now_iso = _now_iso()
    is_wake = woken_video_id is not None

    channels_cfg = load_channels()
    id_by_key = {k: v["channel_id"] for k, v in channels_cfg["channels"].items()}
    channel_id_to_key = {v["channel_id"]: k for k, v in channels_cfg["channels"].items()}

    gh = GitHubStore(cfg.github_token, cfg.github_repo, cfg.data_branch)

    # ── 일시정지 가드 (v2.1) ──
    control, _ = gh.read_json("control.json")
    if is_paused(control or default_control()):
        if not is_wake:
            _ping_healthcheck(cfg.healthcheck_url)  # 다운 오탐 방지
        log.info("paused — skip (mode=%s woken=%s)", mode, woken_video_id)
        return {"paused": True, "mode": mode, "woken": woken_video_id}

    # 후보 집합 계산용 초기 읽기 (커밋용 재읽기는 아래 재시도 루프 안에서 다시 한다)
    _pp0, _ = gh.read_json("pending.json")
    _ps0, _ = gh.read_json("schedule.json")

    # ── 후보 video_id 집합 ──
    candidates: set[str] = set((_pp0 or default_pending()).get("entries", {}).keys())
    candidates.update(_tracked_unresolved_ids(_ps0 or {}))
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

    # ── 커밋: schedule/archive/pending. 다른 실행이 우리가 읽은 뒤 먼저 커밋해서 base sha 가
    #    어긋나면(방송 시작 시간대에 tick/wake 가 겹침) 최신 상태를 다시 읽어 1회 재계산한다.
    #    RSS/YouTube 조회는 위에서 한 번만 — videos 는 재사용한다. ──
    for _attempt in (1, 2):
        prev_schedule, sched_sha = gh.read_json("schedule.json")
        if prev_schedule is None:
            prev_schedule = default_schedule(channels_cfg)
        prev_pending, pend_sha = gh.read_json("pending.json")
        if prev_pending is None:
            prev_pending = default_pending()
        prev_archive, arch_sha = gh.read_json("archive.json")

        new_schedule, newly_ended = build_schedule(
            channels_cfg, videos, prev_schedule, now_iso, avatars
        )
        # 실질 변화(_stable_view)가 없으면 broadcast 별 volatile 필드는 prev 로 동결하고,
        # generated_at 은 heartbeat 간격(_HEARTBEAT_MIN_SEC)마다만 전진시킨다.
        if _stable_view(prev_schedule) == _stable_view(new_schedule):
            new_schedule["generated_at"] = _heartbeat_generated_at(
                prev_schedule.get("generated_at"), now_iso
            )
            _prev_bc = {b.get("video_id"): b for b in prev_schedule.get("broadcasts", [])}
            for b in new_schedule.get("broadcasts", []):
                pb = _prev_bc.get(b.get("video_id"))
                if not pb:
                    continue
                for f in ("last_updated", "concurrent_viewers"):
                    if f in pb:
                        b[f] = pb[f]

        new_archive, arch_changed = _merge_archive(prev_archive, newly_ended, now_iso)
        decision = sync_pending(
            prev_pending, videos, channel_id_to_key, now_iso,
            mode=("wake" if is_wake else "sync"),
            woken_video_id=woken_video_id,
        )

        try:
            sched_changed, _ = gh.write_json(
                "schedule.json", new_schedule, prev_sha=sched_sha,
                message=f"data: schedule {now_iso}",
            )
            if arch_changed:
                gh.write_json(
                    "archive.json", new_archive, prev_sha=arch_sha,
                    message=f"data: archive {now_iso}",
                )
            pend_changed, _ = gh.write_json(
                "pending.json", decision.new_pending, prev_sha=pend_sha,
                message=f"data: pending {now_iso}",
            )
            break
        except ConflictError as e:
            if _attempt == 2:
                raise
            log.warning("write 충돌 — 최신 상태로 재계산 후 재시도: %s", e)

    # ── Cloud Tasks enqueue ──
    enqueued, enqueue_errors = 0, []
    tq = _make_task_queue(cfg) if (decision.enqueue or newly_ended) else None
    if tq is not None:
        for vid, when in decision.enqueue:
            try:
                tq.enqueue_wake(vid, when)
                enqueued += 1
            except Exception as e:  # noqa: BLE001
                enqueue_errors.append(f"{vid}: {e}")
                log.error("enqueue 실패 %s @ %s: %s", vid, when, e)
        # 방송이 방금 끝났으면 후속 light tick 1개 예약 — 백투백 다음 방송을 3h 이내가 아니라
        # ~20분 이내에 줍기 위함. tick 이름이 분버킷이라 여러 방송이 끝나도 후속 tick 은 1개.
        if newly_ended:
            recheck_at = (
                datetime.now(timezone.utc) + timedelta(seconds=_POST_END_RECHECK_SEC)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                tq.enqueue_tick("light", recheck_at)
                log.info("post-end recheck tick 예약 @ %s", recheck_at)
            except Exception as e:  # noqa: BLE001
                enqueue_errors.append(f"post-end tick: {e}")
                log.error("post-end tick enqueue 실패: %s", e)

    result = {
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

    # ── Telegram 알림 (v2.1) — 실패해도 주 로직 무영향 ──
    # control.json log_level 로 게이팅: detail=전부+매실행 요약 / normal=전이+fallback / simple=fallback·error
    try:
        level = get_log_level(control or default_control())
        tg = Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id)
        # 이 실행이 시작될 때의 스냅샷(_ps0)과 비교 — 재시도로 loop 안 prev_schedule 이
        # 우리 첫 커밋 결과로 바뀌어도 전이 알림을 놓치지 않도록.
        events = diff_events(
            _ps0 or default_schedule(channels_cfg), new_schedule, newly_ended,
            decision.log, channels_cfg["channels"], now_iso,
        )
        for ev in events:
            if notify_allows(level, ev.kind):
                tg.send(ev.text)
        if notify_allows(level, "summary"):  # 사실상 detail 일 때만
            tg.send(summary_text(result, now_iso), silent=True)
    except Exception as e:  # noqa: BLE001
        log.warning("telegram 알림 실패: %s", e)

    # ── dead-man's-switch (정기 tick 성공 시에만) ──
    if not is_wake:
        _ping_healthcheck(cfg.healthcheck_url)

    return result


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


if __name__ == "__main__":
    # _heartbeat_generated_at 스모크 (네트워크 불필요)
    _b = "2026-09-01T12:00:00Z"
    assert _heartbeat_generated_at(None, _b) == _b
    assert _heartbeat_generated_at(_b, "2026-09-01T12:05:00Z") == _b                        # 5분 < 20분 → 유지
    assert _heartbeat_generated_at(_b, "2026-09-01T12:20:00Z") == "2026-09-01T12:20:00Z"    # 20분 == 임계 → 전진
    assert _heartbeat_generated_at(_b, "2026-09-01T13:00:00Z") == "2026-09-01T13:00:00Z"
    assert _heartbeat_generated_at("garbage", "2026-09-01T13:00:00Z") == "2026-09-01T13:00:00Z"
    print("[OK] _heartbeat_generated_at")
