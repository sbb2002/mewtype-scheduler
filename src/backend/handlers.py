"""오케스트레이션: `/tick` (Cloud Scheduler) 와 `/wake` (Cloud Tasks) 처리 — v3.

v1 collector 의 순수 모듈(rss / youtube)을 재사용하고, 상태 판정은 v3 `preview_build`
(reconcile 포크 + FSM 파생), 저장은 GitHub Contents API(`gh_store`), 다음 wake 는
Cloud Tasks(`tasks`)로 나간다. v2 의 `pending.json` 은 폐지 — FSM 이 preview 아이템에서 파생.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

from ..collector.config import load_channels
from ..collector.rss import fetch_all_rss_video_ids
from ..collector.youtube import YouTubeClient
from . import preview as preview_mod
from .config import load_config
from .control import default_control, get_log_level, is_paused
from .gh_store import ConflictError, GitHubStore
from .notify import Telegram, diff_events, summary_text
from .notify import allows as notify_allows
from .preview_build import build_archive_appends, build_preview

log = logging.getLogger("backend.handlers")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# 실질 변화가 없어도 generated_at 은 최소 이 간격으로 전진시킨다 (프론트 "업데이트" 시각).
# ponytail: 고정 임계값. 커밋 수가 문제되면 config 로 뺀다.
_HEARTBEAT_MIN_SEC = 20 * 60

# 방송이 방금 end 로 전이했으면 정기 light tick(3h)을 안 기다리고 이만큼 뒤 후속 tick 1개.
_POST_END_RECHECK_SEC = 20 * 60

# video_id 없는 announced 예고는 wake 태스크가 없다. 대신 예고 시각이 이 창 안이면
# 그 시각으로 light tick 1개 예약 — 공개 방송 정시 시작을 3h 안 기다리고 RSS 로 줍는다.
_SCHED_WAKE_LOOKAHEAD_SEC = 3 * 3600


def _scheduled_wake_times(preview: dict, now_iso: str) -> list[str]:
    """announced(자리표시) 아이템 중 '지금 ~ +3h' 에 시작하는 것들의 scheduled_start 목록."""
    try:
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except ValueError:
        return []
    horizon = now + timedelta(seconds=_SCHED_WAKE_LOOKAHEAD_SEC)
    out: set[str] = set()
    for it in (preview or {}).get("items", []):
        if it.get("state") != "announced" or it.get("video_id") or it.get("time_tbd"):
            continue
        ss = it.get("scheduled_start")
        if not ss:
            continue
        try:
            t = datetime.fromisoformat(ss.replace("Z", "+00:00"))
        except ValueError:
            continue
        if now < t <= horizon:
            out.add(ss)
    return sorted(out)


def _heartbeat_generated_at(prev_gen, now_iso: str, min_sec: int = _HEARTBEAT_MIN_SEC) -> str:
    """실질 변화가 없을 때 쓸 generated_at 값 — min_sec 지났으면 now, 아니면 prev 유지."""
    if not prev_gen:
        return now_iso
    try:
        prev_dt = datetime.fromisoformat(prev_gen.replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except ValueError:
        return now_iso
    return now_iso if (now_dt - prev_dt).total_seconds() >= min_sec else prev_gen


def _tracked_unresolved_ids(preview: dict) -> list[str]:
    """다음 videos.list 후보에 넣을 video_id — 아직 종결 안 된 추적 대상."""
    return [
        it["video_id"]
        for it in (preview or {}).get("items", [])
        if it.get("video_id")
        and it.get("state") in ("announced", "upcoming", "watching", "live", "end")
    ]


# preview 비교용 뷰에서 뺄 volatile 필드 (이것만 바뀌면 커밋/알림 안 함).
_VOLATILE = ("last_updated", "concurrent_viewers")


def _stable_view(preview: dict) -> dict:
    preview = preview or {}
    return {
        "channel_order": preview.get("channel_order"),
        "channels": preview.get("channels"),
        "items": sorted(
            (
                {k: v for k, v in it.items() if k not in _VOLATILE}
                for it in preview.get("items", [])
            ),
            key=lambda it: it.get("id") or it.get("video_id") or "",
        ),
    }


def _make_task_queue(cfg):
    try:
        from .tasks import TaskQueue

        return TaskQueue(
            project=cfg.gcp_project,
            location=cfg.gcp_location,
            queue=cfg.tasks_queue,
            target_url=cfg.service_url,
            invoker_sa=cfg.invoker_sa,
        )
    except Exception as e:  # noqa: BLE001 — 로컬/부트스트랩 허용
        log.warning("TaskQueue 비활성 (%s) — enqueue 건너뜀", e)
        return None


def _ping_healthcheck(url: str) -> None:
    if not url:
        return
    try:
        requests.get(url, timeout=5)
    except Exception as e:  # noqa: BLE001
        log.warning("healthcheck 핑 실패: %s", e)


def _make_llm(cfg):
    """LLMClient 생성. 키 없으면 disabled 인스턴스(모든 호출 None)."""
    try:
        from .llm import LLMClient

        return LLMClient(
            cfg.groq_api_key, model=cfg.groq_model, fallback=cfg.groq_model_fallback
        )
    except Exception as e:  # noqa: BLE001
        log.warning("LLMClient 비활성 (%s)", e)
        return None


def _translate_sweep(gh: GitHubStore, cfg, now_iso: str) -> dict:
    """notices.json / tweets.json 에서 `needs_tl` 플래그 붙은 행을 재번역.

    자동 파이프라인(`/ingest`)이 인라인 번역에 실패하면 그 행에 `needs_tl=True` 를 남긴다.
    "행 자체가 큐" — 여기서 재시도하고 성공하면 플래그를 지운다. LLM disabled 면 no-op.
    """
    out = {"notice_tl": 0, "tweet_tl": 0}
    if not cfg.groq_api_key:
        return out
    llm = _make_llm(cfg)
    if llm is None:
        return out

    # notices.json
    try:
        nj, sha = gh.read_json("notices.json")
        if nj and nj.get("notices"):
            changed = False
            for n in nj["notices"]:
                if not n.get("needs_tl"):
                    continue
                res = llm.notice_title(n.get("body_for_llm") or n.get("title") or "")
                if res and res.get("title_ko"):
                    n["title"] = res.get("title_ja") or n.get("title")
                    n["title_ko"] = res["title_ko"]
                    n.pop("needs_tl", None)
                    n["last_updated"] = now_iso
                    changed = True
                    out["notice_tl"] += 1
            if changed:
                nj["generated_at"] = now_iso
                gh.write_json("notices.json", nj, prev_sha=sha,
                              message=f"data: notices tl {now_iso}")
    except Exception as e:  # noqa: BLE001
        log.warning("notice 번역 sweep 실패: %s", e)

    # tweets.json
    try:
        tj, sha = gh.read_json("tweets.json")
        if tj and tj.get("tweets"):
            changed = False
            for _k, t in tj["tweets"].items():
                if not t.get("needs_tl"):
                    continue
                ko = llm.translate(t.get("text") or "")
                if ko:
                    t["text_ko"] = ko
                    t.pop("needs_tl", None)
                    changed = True
                    out["tweet_tl"] += 1
            if changed:
                tj["generated_at"] = now_iso
                gh.write_json("tweets.json", tj, prev_sha=sha,
                              message=f"data: tweets tl {now_iso}")
    except Exception as e:  # noqa: BLE001
        log.warning("tweet 번역 sweep 실패: %s", e)

    return out


def _run(mode: str, woken_video_id: str | None) -> dict:
    cfg = load_config()
    now_iso = _now_iso()
    is_wake = woken_video_id is not None

    channels_cfg = load_channels()
    id_by_key = {k: v["channel_id"] for k, v in channels_cfg["channels"].items()}

    gh = GitHubStore(cfg.github_token, cfg.github_repo, cfg.data_branch)

    # ── 일시정지 가드 ──
    control, _ = gh.read_json("control.json")
    if is_paused(control or default_control()):
        if not is_wake:
            _ping_healthcheck(cfg.healthcheck_url)
        log.info("paused — skip (mode=%s woken=%s)", mode, woken_video_id)
        return {"paused": True, "mode": mode, "woken": woken_video_id}

    # 후보 집합 계산용 초기 읽기
    _pv0, _ = gh.read_json("preview.json")
    _pv0 = _pv0 or preview_mod.default_preview()

    candidates: set[str] = set(_tracked_unresolved_ids(_pv0))
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

    # ── 커밋 루프 (최대 2회, ConflictError 재계산 재시도). RSS/YT 는 위에서 1회, videos 재사용. ──
    prev_preview = _pv0
    for _attempt in (1, 2):
        prev_preview, pv_sha = gh.read_json("preview.json")
        if prev_preview is None:
            prev_preview = preview_mod.default_preview()
        prev_archive, arch_sha = gh.read_json("preview_archive.json")

        new_preview, transitions, wakes, gone_items = build_preview(
            channels_cfg, videos, prev_preview, now_iso, avatars=avatars,
        )

        # ── /del terminate 로 12h 차단된 url · 아이템 단위 편집 락 반영 ──
        try:
            adm, _ = gh.read_json("admin_state.json")
        except Exception:  # noqa: BLE001
            adm = None
        if adm:
            try:
                from . import admin as _admin

                kept = []
                for it in new_preview.get("items", []):
                    u = it.get("url")
                    if u and _admin.suppressed(adm, u, now_iso):
                        continue  # 재진입 차단 — 이 아이템은 안 싣는다
                    lock = _admin.get_edit_lock(adm)
                    if (lock and lock.get("id") == it.get("id")
                            and _admin.edit_lock_active(adm, it.get("id"), now_iso)):
                        # 락 걸린 아이템은 prev 값을 그대로 유지(이번 사이클 갱신 스킵)
                        pv = next((p for p in prev_preview.get("items", [])
                                   if p.get("id") == it.get("id")), None)
                        kept.append(pv or it)
                    else:
                        kept.append(it)
                new_preview["items"] = kept
            except Exception:  # noqa: BLE001
                log.warning("suppress/edit_lock 반영 실패 — 무시", exc_info=True)

        # 실질 변화 없으면 volatile 동결 + generated_at heartbeat.
        if _stable_view(prev_preview) == _stable_view(new_preview):
            new_preview["generated_at"] = _heartbeat_generated_at(
                prev_preview.get("generated_at"), now_iso
            )
            _prev_by = {it.get("id"): it for it in prev_preview.get("items", [])}
            for it in new_preview.get("items", []):
                pb = _prev_by.get(it.get("id"))
                if not pb:
                    continue
                for f in _VOLATILE:
                    if f in pb:
                        it[f] = pb[f]

        new_archive, arch_changed = build_archive_appends(
            prev_archive or {}, gone_items, now_iso
        )

        try:
            pv_changed, _ = gh.write_json(
                "preview.json", new_preview, prev_sha=pv_sha,
                message=f"data: preview {now_iso}",
            )
            if arch_changed:
                gh.write_json(
                    "preview_archive.json", new_archive, prev_sha=arch_sha,
                    message=f"data: preview_archive {now_iso}",
                )
            break
        except ConflictError as e:
            if _attempt == 2:
                raise
            log.warning("write 충돌 — 최신 상태로 재계산 후 재시도: %s", e)

    # ── Cloud Tasks enqueue ──
    enqueued, enqueue_errors = 0, []
    sched_wakes = _scheduled_wake_times(new_preview, now_iso)
    newly_ended = any("→end" in t for t in transitions)
    need_tq = bool(wakes or sched_wakes or newly_ended)
    tq = _make_task_queue(cfg) if need_tq else None
    if tq is not None:
        for vid, when in wakes.items():
            try:
                tq.enqueue_wake(vid, when)
                enqueued += 1
            except Exception as e:  # noqa: BLE001
                enqueue_errors.append(f"{vid}: {e}")
                log.error("enqueue 실패 %s @ %s: %s", vid, when, e)
        for when in sched_wakes:
            try:
                tq.enqueue_tick("light", when)
            except Exception as e:  # noqa: BLE001
                enqueue_errors.append(f"sched tick {when}: {e}")
                log.error("scheduled wake tick enqueue 실패 @ %s: %s", when, e)
        if newly_ended:
            recheck_at = (
                datetime.now(timezone.utc) + timedelta(seconds=_POST_END_RECHECK_SEC)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                tq.enqueue_tick("light", recheck_at)
            except Exception as e:  # noqa: BLE001
                enqueue_errors.append(f"post-end tick: {e}")
                log.error("post-end tick enqueue 실패: %s", e)

    # ── LLM 번역 재시도 sweep (needs_tl 행) — 정기 tick 에서만 ──
    tl = {"notice_tl": 0, "tweet_tl": 0}
    if not is_wake:
        tl = _translate_sweep(gh, cfg, now_iso)

    # 상태 카운트
    state_counts: dict[str, int] = {}
    for it in new_preview.get("items", []):
        state_counts[it.get("state", "?")] = state_counts.get(it.get("state", "?"), 0) + 1

    result = {
        "mode": mode,
        "woken": woken_video_id,
        "candidates": len(candidates),
        "videos": len(videos),
        "preview_changed": pv_changed,
        "archive_changed": arch_changed,
        "archived": [g.get("video_id") or g.get("id") for g in gone_items],
        "preview_items": len(new_preview.get("items", [])),
        "state_counts": state_counts,
        "wakes": len(wakes),
        "enqueued": enqueued,
        "enqueue_errors": enqueue_errors,
        "translated": tl,
        "quota_used": yt.quota_used,
        "log": transitions,
    }

    # ── Telegram 알림 — 실패해도 주 로직 무영향 ──
    try:
        level = get_log_level(control or default_control())
        tg = Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id)
        events = diff_events(
            _pv0.get("items"), new_preview.get("items", []),
            transitions, channels_cfg["channels"], now_iso,
        )
        for ev in events:
            if notify_allows(level, ev.kind):
                tg.send(ev.text)
        if notify_allows(level, "summary"):
            tg.send(summary_text(result, now_iso), silent=True)
    except Exception as e:  # noqa: BLE001
        log.warning("telegram 알림 실패: %s", e)

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
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    _b = "2026-09-01T12:00:00Z"
    assert _heartbeat_generated_at(None, _b) == _b
    assert _heartbeat_generated_at(_b, "2026-09-01T12:05:00Z") == _b
    assert _heartbeat_generated_at(_b, "2026-09-01T12:20:00Z") == "2026-09-01T12:20:00Z"
    assert _heartbeat_generated_at("garbage", "2026-09-01T13:00:00Z") == "2026-09-01T13:00:00Z"
    print("[OK] _heartbeat_generated_at")

    _now = "2026-09-01T12:00:00Z"
    _pv = {"items": [
        {"state": "announced", "scheduled_start": "2026-09-01T13:30:00Z"},   # 1.5h 후 → 포함
        {"state": "announced", "scheduled_start": "2026-09-01T18:00:00Z"},   # 6h 후 → 제외
        {"state": "announced", "scheduled_start": "2026-09-01T11:00:00Z"},   # 과거 → 제외
        {"state": "announced", "scheduled_start": None},                     # 시각 없음 → 제외
        {"state": "announced", "scheduled_start": "2026-09-01T13:00:00Z", "video_id": "x"},  # video_id 有 → 제외
        {"state": "announced", "scheduled_start": "2026-09-01T13:00:00Z", "time_tbd": True}, # time_tbd → 제외
        {"state": "upcoming",  "scheduled_start": "2026-09-01T13:00:00Z"},   # announced 아님 → 제외
    ]}
    assert _scheduled_wake_times(_pv, _now) == ["2026-09-01T13:30:00Z"], _scheduled_wake_times(_pv, _now)
    print("[OK] _scheduled_wake_times")

    _a = {"items": [{"state": "live", "id": "pv_1", "video_id": "v1", "last_updated": "x"}]}
    _bv = {"items": [{"state": "live", "id": "pv_1", "video_id": "v1", "last_updated": "y"}]}
    assert _stable_view(_a) == _stable_view(_bv), "volatile 차이만이면 stable_view 동일"
    print("[OK] _stable_view volatile 제외")

    assert _tracked_unresolved_ids(_a) == ["v1"]
    print("[OK] _tracked_unresolved_ids")

    print("SUCCESS: handlers self-test 통과")
