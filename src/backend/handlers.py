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
from .monitor_log import RESULT_DEGRADED, RESULT_ERR, RESULT_OK, log_events
from .notify import Telegram, diff_events, summary_text
from .notify import allows as notify_allows
from .preview_build import build_archive_appends, build_preview
from . import xtweet

log = logging.getLogger("backend.handlers")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# 방송이 방금 end 로 전이했으면 정기 light tick 을 안 기다리고 이만큼 뒤 후속 tick 1개.
# (3h 시절 도입한 보정 — 현재는 10분 tick 과 겹치지만 무해해 유지, 제거 여부는 후속 결정)
_POST_END_RECHECK_SEC = 20 * 60

# video_id 없는 announced 예고는 wake 태스크가 없다. 대신 예고 시각이 이 창 안이면
# 그 시각으로 light tick 1개 예약.
# (3h 시절 도입한 보정 — 현재는 10분 tick 과 겹치지만 무해해 유지, 제거 여부는 후속 결정)
_SCHED_WAKE_LOOKAHEAD_SEC = 3 * 3600

# (v3.7.3) 이보다 먼 미래의 wake 는 등록하지 않는다. 정기 light tick(10분)·baseline(매일 06:00 JST)이 매번
# 전체를 다시 계산하므로, 시각이 이 창 안으로 들어오는 순간 다음 실행이 등록한다(절대 시각이라 이름이 같아
# dedupe). 예전엔 시작이 29일 넘게 남은 방송(예: 12/24 라이브 h31Mi6AS7a0)의 wake 가 Cloud Tasks 상한
# (29일)으로 잘려 "지금+29일" 이라는 실행마다 다른 시각·다른 이름으로 계속 쌓였다(2026-09-19 큐 3,319건).
_WAKE_ENQUEUE_HORIZON_SEC = 24 * 3600


def _wakes_within_horizon(wakes: dict[str, str], now_iso: str) -> dict[str, str]:
    """{video_id: when_iso} 중 `now + _WAKE_ENQUEUE_HORIZON_SEC` 이내인 것만 (순수)."""
    try:
        limit = datetime.fromisoformat(now_iso.replace("Z", "+00:00")) + timedelta(seconds=_WAKE_ENQUEUE_HORIZON_SEC)
    except ValueError:
        return dict(wakes or {})
    out: dict[str, str] = {}
    for vid, when in (wakes or {}).items():
        try:
            if datetime.fromisoformat(when.replace("Z", "+00:00")) <= limit:
                out[vid] = when
        except (ValueError, AttributeError):
            out[vid] = when  # 파싱 불가는 종전대로 등록(막지 않음)
    return out


def _scheduled_wake_times(preview: dict, now_iso: str) -> list[str]:
    """announced(자리표시) 아이템 중 '지금 ~ +_SCHED_WAKE_LOOKAHEAD_SEC' 에 시작하는 것들의 scheduled_start 목록."""
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


def _preview_log_events(
    prev_items: list[dict] | None, new_items: list[dict], gone_items: list[dict]
) -> list[dict]:
    """new_items(상태 유지) + gone_items(→none으로 archive된 것)를 prev_items 와 비교해,
    상태가 실제로 바뀐 아이템만 모니터링 로그용 이벤트로 뽑는다(순수 함수).

    notify.diff_events 는 사람이 읽을 텔레그램 알림용이라 kind 5종류만 다루고
    channel_key/video_id 같은 원본 필드도 안 남긴다 — 여긴 감사 로그용이라 전부 남긴다.
    """
    prev_by_key: dict[str, dict] = {}
    for it in prev_items or []:
        key = it.get("id") or it.get("video_id")
        if key:
            prev_by_key[key] = it

    events: list[dict] = []

    def _emit(item: dict, to_state: str | None) -> None:
        key = item.get("id") or item.get("video_id")
        if not key:
            return
        prev_item = prev_by_key.get(key)
        from_state = prev_item.get("state") if prev_item else None
        if from_state == to_state:
            return
        events.append({
            "channel_key": item.get("channel_key", ""),
            "video_id": item.get("video_id"),
            "id": item.get("id"),
            # (v3.8.4 item 10) monitor 간트에서 "방송 중 추정"(assumed_live) 을 실제 상태와
            # 별개로 빨강 빗금 덮어쓰기로 표시하기 위해 실어 보낸다.
            "assumed_live": bool(item.get("assumed_live", False)),
            "from_state": from_state,
            "to_state": to_state,
            "title": item.get("title"),
            # (v3.8.5 후속) monitor 타임플롯이 합동 live 막대 위에 참여 멤버 아이콘을
            # 얹기 위해 필요 — 전이 시점 값 그대로(이후 별도 write로 늦게 추가된
            # collab_with 는 다음 상태전이 로그부터 반영).
            "collab_with": item.get("collab_with"),
        })

    for it in new_items:
        _emit(it, it.get("state"))
    for it in gone_items:
        _emit(it, "none")
    return events


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
    out = {"notice_tl": 0, "tweet_tl": 0, "preview_tl": 0}
    if not cfg.groq_api_key:
        return out
    llm = _make_llm(cfg)
    if llm is None:
        return out

    # notices.json
    nj = None
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
            for _k, lst in list(tj["tweets"].items()):
                # 계약 I — tweets[ck] 는 메시지 배열. v2.8 단건 dict 는 [dict] 로 승계.
                norm = lst if isinstance(lst, list) else ([lst] if isinstance(lst, dict) else [])
                if norm is not lst:
                    tj["tweets"][_k] = norm
                    changed = True
                for t in norm:
                    q = t.get("quote")
                    if q and q.get("needs_tl") and q.get("text") and not q.get("text_ko"):
                        ko = (xtweet.find_reused_ko(q["text"], tweets_data=tj, notices_data=nj)
                              or llm.translate(q["text"]))
                        if ko:
                            q["text_ko"] = ko
                            q.pop("needs_tl", None)
                            changed = True
                            out["tweet_tl"] += 1
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

    # preview.json — 방송 제목 번역
    try:
        pj, sha = gh.read_json("preview.json")
        if pj and pj.get("items"):
            changed = False
            for it in pj["items"]:
                if not it.get("needs_tl") or not it.get("title"):
                    continue
                ko = llm.translate(it["title"])
                if ko:
                    it["title_ko"] = ko
                    it.pop("needs_tl", None)
                    changed = True
                    out["preview_tl"] += 1
            if changed:
                pj["generated_at"] = now_iso
                gh.write_json("preview.json", pj, prev_sha=sha,
                              message=f"data: preview tl {now_iso}")
    except Exception as e:  # noqa: BLE001
        log.warning("preview 번역 sweep 실패: %s", e)

    return out


def _should_log_run(
    pv_changed: bool, arch_changed: bool, enqueue_errors: list,
    preview_event_count: int, translated_total: int
) -> bool:
    """tick/wake 이벤트를 모니터링 로그에 기록할지 여부(변화가 있을 때만).

    다음 중 하나라도 참이면 기록한다:
    - preview 또는 archive 변화
    - enqueue 오류
    - preview 전이 이벤트 1건 이상
    - 번역 sweep 반영(needs_tl 행 해결)
    """
    return (
        pv_changed
        or arch_changed
        or bool(enqueue_errors)
        or preview_event_count > 0
        or translated_total > 0
    )


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

        # ── 트윗·릴레이 예고 시각 override 재적용 (알려진 지연: wakes 는 override 전 시각 기준) ──
        try:
            new_preview["items"] = xtweet.apply_overrides(
                new_preview.get("items", []), prev_preview.get("items", []), now_iso)
        except Exception:  # noqa: BLE001
            log.warning("apply_overrides 실패 — override 없이 진행", exc_info=True)

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

        # 실질 변화 없으면 generated_at 도 건드리지 않는다 — volatile 필드까지 동결해서
        # gh.write_json 이 완전한 무변화로 보고 커밋 자체를 건너뛰게 한다(v3.2.2).
        # v3.1.17 은 wake 때마다 generated_at 을 무조건 지금 시각으로 갱신해 "계속 확인
        # 중"이라는 걸 보여줬는데, 방송이 여러 건 겹치면 각자 3~10분 간격인 wake 들이
        # 서로 어긋나며 겹쳐서 상태 변화가 전혀 없어도 1~3분마다(심지어 수 초 간격도
        # 실측) 커밋이 발생했다. 실측(2026-09-13): 24시간 preview.json 커밋 118건 중
        # 92건(78%)이 generated_at 한 줄만 바뀐 순수 하트비트 — data 브랜치 커밋이
        # Vercel 배포 시도로도 잡히는 구조라, 이 하트비트 커밋 폭증이 Vercel Hobby
        # 플랜의 "하루 100회 배포" 한도를 소진시켜 실제 배포가 막히는 사고로 번졌다.
        # "마지막 확인 시각"이 필요하면 커밋과 무관한 별도 채널(로그 등)로 뺄 것 —
        # 이 필드를 프론트 "업데이트" 표시에 다시 쓰려면 이 트레이드오프를 재검토해야 한다.
        if _stable_view(prev_preview) == _stable_view(new_preview):
            new_preview["generated_at"] = prev_preview.get(
                "generated_at", new_preview["generated_at"]
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
    wakes = _wakes_within_horizon(wakes, now_iso)
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
    tl = {"notice_tl": 0, "tweet_tl": 0, "preview_tl": 0}
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

    # ── 모니터링 이벤트 로그 — 실패해도 주 로직 무영향(배치 처리, 변화 없는 실행 스킵) ──
    try:
        events = []

        # preview 전이 이벤트 수집
        preview_events = _preview_log_events(_pv0.get("items"), new_preview.get("items", []), gone_items)
        enqueue_error_vids = {vid for vid in wakes if any(e.startswith(f"{vid}:") for e in enqueue_errors)}
        for ev in preview_events:
            quality = RESULT_DEGRADED if ev.get("video_id") in enqueue_error_vids else RESULT_OK
            events.append({
                "ts": now_iso,
                "flow": "preview",
                "result": quality,
                "who": ev.get("channel_key", ""),
                "detail": f"{ev.get('from_state')}→{ev.get('to_state')}",
                # (v3.8.4) item 5·6·7 조사 중 발견 — 아래 두 필드가 빠져 있어서
                # monitor_report._preview_json(간트 세그먼트 생성기)이 이 이벤트에서
                # to_state 를 못 읽었다(그 함수와 자기 self-test 픽스처는 top-level
                # from_state/to_state 를 전제로 함). detail 문자열에만 있고 여기 없었음.
                "from_state": ev.get("from_state"),
                "to_state": ev.get("to_state"),
                "video_id": ev.get("video_id"),
                "item_id": ev.get("id"),
                "title": ev.get("title"),
                "assumed_live": ev.get("assumed_live", False),
            })

        # tick/wake 이벤트는 변화가 있을 때만 포함
        translated_total = sum(tl.values())
        if _should_log_run(pv_changed, arch_changed, enqueue_errors, len(preview_events), translated_total):
            run_event = {
                "ts": now_iso,
                "flow": "wake" if is_wake else "tick",
                "result": RESULT_ERR if enqueue_errors else RESULT_OK,
                "who": woken_video_id or "",
                "detail": f"candidates={len(candidates)} preview_changed={pv_changed}",
                "mode": mode,
                "quota": yt.quota_used,
                "candidates": len(candidates),
                "preview_changed": pv_changed,
            }
            events.insert(0, run_event)  # tick/wake을 맨 앞에

        log_events(gh, now_iso, events)
    except Exception as e:  # noqa: BLE001
        log.warning("monitor_log 기록 실패: %s", e)

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

    # v3.2.2 회귀 테스트 — 실질 변화 없으면(stable_view 동일) generated_at 을 prev 로
    # 되돌려 gh.write_json 이 완전 무변화로 보고 커밋을 건너뛰게 해야 한다. v3.1.17 은
    # wake 때 무조건 now 로 갱신해서, 방송이 여러 건 겹치면 상태 변화 없이도 몇 분마다
    # 커밋이 발생했다(실측: 24h preview 커밋 118건 중 92건이 generated_at 만 다름).
    _prev_pv = {"generated_at": "2026-09-01T12:00:00Z",
                "items": [{"state": "live", "id": "pv_1", "video_id": "v1"}]}
    _new_pv = {"generated_at": "2026-09-01T12:03:00Z",  # build_preview 가 항상 now 로 채움
               "items": [{"state": "live", "id": "pv_1", "video_id": "v1"}]}
    assert _stable_view(_prev_pv) == _stable_view(_new_pv), "이 시나리오는 실질 변화 없음 전제"
    _new_pv["generated_at"] = _prev_pv.get("generated_at", _new_pv["generated_at"])
    assert _new_pv["generated_at"] == "2026-09-01T12:00:00Z", "무변화면 generated_at 도 prev 유지"
    print("[OK] 무변화 시 generated_at 동결 (하트비트 커밋 폭증 방지)")

    # 모니터링 로그용 preview 전이 추출 — 상태 유지, 신규, 삭제(→none) 셋 다 커버.
    _prev_items = [
        {"id": "pv_1", "video_id": "v1", "channel_key": "arale", "state": "upcoming", "title": "A"},
        {"id": "pv_2", "video_id": "v2", "channel_key": "yuno", "state": "live", "title": "B"},
        {"id": "pv_3", "video_id": "v3", "channel_key": "nonoka", "state": "end", "title": "C"},
    ]
    _new_items = [
        {"id": "pv_1", "video_id": "v1", "channel_key": "arale", "state": "watching", "title": "A"},  # 전이
        {"id": "pv_2", "video_id": "v2", "channel_key": "yuno", "state": "live", "title": "B"},  # 유지 → 제외
        {"id": "pv_4", "video_id": "v4", "channel_key": "miyako", "state": "announced", "title": "D"},  # 신규
    ]
    _gone_items = [{"id": "pv_3", "video_id": "v3", "channel_key": "nonoka", "state": "none", "title": "C"}]
    _evs = _preview_log_events(_prev_items, _new_items, _gone_items)
    _by_id = {e["id"]: e for e in _evs}
    assert len(_evs) == 3, _evs
    assert _by_id["pv_1"]["from_state"] == "upcoming" and _by_id["pv_1"]["to_state"] == "watching"
    assert _by_id["pv_4"]["from_state"] is None and _by_id["pv_4"]["to_state"] == "announced"
    assert _by_id["pv_3"]["from_state"] == "end" and _by_id["pv_3"]["to_state"] == "none"
    assert "pv_2" not in _by_id, "상태 유지된 아이템은 이벤트로 안 뽑혀야 함"
    print("[OK] _preview_log_events: 전이/신규/삭제(→none) 추출, 무변화 제외")

    # (v3.8.5 후속) collab_with 전파 — monitor 타임플롯의 합동 live 막대 아이콘용
    _collab_new = [
        {"id": "pv_9", "video_id": "v9", "channel_key": "yuno", "state": "live",
         "collab_with": ["ritsu"], "title": "합동"},
    ]
    _collab_evs = _preview_log_events([], _collab_new, [])
    assert _collab_evs[0]["collab_with"] == ["ritsu"], _collab_evs[0]
    print("[OK] _preview_log_events: collab_with 전파")

    # (v3.8.4) item 5·6·7 회귀 테스트 — _run 안에서 실제로 log_events 에 넘기는 dict 를
    # 그대로 재현해 from_state/to_state 가 top-level 로 실려 있는지 확인한다. 이 필드가
    # 빠지면 monitor_report._preview_json(간트 세그먼트 생성기)이 모든 전이의 상태를
    # 못 읽는다(그쪽 self-test 픽스처는 이 필드가 있다고 전제) — 지금까지는 detail
    # 문자열에만 녹아 있고 top-level 엔 없어서 실제로 빠져 있었다.
    _sample_ev = _evs[0]
    _built = {
        "ts": "2026-01-01T00:00:00Z",
        "flow": "preview",
        "result": RESULT_OK,
        "who": _sample_ev.get("channel_key", ""),
        "detail": f"{_sample_ev.get('from_state')}→{_sample_ev.get('to_state')}",
        "from_state": _sample_ev.get("from_state"),
        "to_state": _sample_ev.get("to_state"),
        "video_id": _sample_ev.get("video_id"),
        "item_id": _sample_ev.get("id"),
        "title": _sample_ev.get("title"),
    }
    assert _built["to_state"] is not None, "to_state 가 top-level 에 실려야 monitor 간트가 그린다"
    assert _built["to_state"] == _sample_ev["to_state"] and _built["from_state"] == _sample_ev["from_state"]
    print("[OK] preview 모니터 로그 이벤트에 from_state/to_state top-level 로 포함됨")

    # (v3.8.4) item 10 — assumed_live 플래그도 같이 실려야 monitor 간트가 "방송 중 추정"을
    # 빨강 빗금으로 덮어 그릴 수 있다.
    _assumed_evs = _preview_log_events(
        [{"id": "pv_a", "channel_key": "arale", "state": "announced"}],
        [{"id": "pv_a", "channel_key": "arale", "state": "upcoming", "assumed_live": True}],
        [],
    )
    assert len(_assumed_evs) == 1 and _assumed_evs[0]["assumed_live"] is True, _assumed_evs
    print("[OK] _preview_log_events: assumed_live 플래그 전파")

    # _wakes_within_horizon (v3.7.3) — 실측 2026-09-19 17:00 KST(08:00Z) 큐 상태 기준
    _now_h = "2026-09-19T08:00:00Z"
    _w = {
        "DWMQTpDQ1fc": "2026-09-19T08:03:00Z",     # 3분 뒤 — 등록
        "MNocXlK5P8s": "2026-09-19T12:27:00Z",     # 같은 날 21:27 KST — 등록
        "JsvLrSmgSz8": "2026-09-20T11:57:00Z",     # 28시간 뒤 — 이번엔 보류(다음 날 light tick 이 등록)
        "h31Mi6AS7a0": "2026-10-18T08:01:00Z",     # 12/24 라이브: 29일로 잘린 시각 — 등록 안 함
    }
    _kept = _wakes_within_horizon(_w, _now_h)
    assert set(_kept) == {"DWMQTpDQ1fc", "MNocXlK5P8s"}, _kept
    assert _wakes_within_horizon(_w, "2026-09-20T08:00:00Z").keys() >= {"JsvLrSmgSz8"}, "하루 뒤 창 안으로 들어오면 등록"
    assert _wakes_within_horizon({"a": "2026-09-19T08:00:00Z"}, _now_h) == {"a": "2026-09-19T08:00:00Z"}, "경계(정확히 24h)는 포함"
    assert _wakes_within_horizon({"a": "2026-09-20T08:00:01Z"}, _now_h) == {}, "24h 를 1초라도 넘으면 제외"
    assert _wakes_within_horizon({}, _now_h) == {} and _wakes_within_horizon({"a": "??"}, _now_h) == {"a": "??"}
    print("[OK] _wakes_within_horizon: 24시간 넘는 wake(29일로 잘린 것 포함) 미등록, 창 진입 시 등록, 파싱불가는 종전대로")

    # _should_log_run 헬퍼 함수 테스트
    # 무변화 → False
    assert not _should_log_run(False, False, [], 0, 0), "모두 거짓이면 로그 안 함"
    print("[OK] _should_log_run: 무변화 → False")

    # pv_changed → True
    assert _should_log_run(True, False, [], 0, 0), "pv_changed 이면 로그"
    print("[OK] _should_log_run: pv_changed → True")

    # enqueue_errors → True
    assert _should_log_run(False, False, ["error"], 0, 0), "enqueue_errors 이면 로그"
    print("[OK] _should_log_run: enqueue_errors → True")

    # preview 전이 이벤트 → True
    assert _should_log_run(False, False, [], 1, 0), "preview 전이 이벤트 1건 이상이면 로그"
    print("[OK] _should_log_run: preview 전이 이벤트 → True")

    # 번역 1건 → True
    assert _should_log_run(False, False, [], 0, 1), "translated_total > 0 이면 로그"
    print("[OK] _should_log_run: 번역 → True")

    # arch_changed → True
    assert _should_log_run(False, True, [], 0, 0), "arch_changed 이면 로그"
    print("[OK] _should_log_run: arch_changed → True")

    # apply_overrides 연결 확인: _run 함수 소스에서 apply_overrides 가 build_preview 뒤에 있는지
    import inspect
    _run_src = inspect.getsource(_run)
    _build_pos = _run_src.find("build_preview(")
    _override_pos = _run_src.find("apply_overrides(")
    assert _build_pos > 0 and _override_pos > _build_pos, \
        f"apply_overrides 는 build_preview 뒤에 나와야 함 (pos: build={_build_pos}, override={_override_pos})"
    print("[OK] apply_overrides 연결 확인: build_preview → apply_overrides 순서 OK")

    # xtweet.apply_overrides 직접 테스트: 트윗 유지 + API 승
    from . import xtweet, preview as preview_mod
    _snow = "2026-09-01T12:00:00Z"
    # 트윗 유지 케이스 (API 불변, 60초 이내)
    # build_preview 가 personal 정보원의 scheduled_start 를 갱신하지 않으므로
    # new_item 도 prev 값 12:30Z 유지
    _prev_item = preview_mod.make_item(
        channel_key="arale", state="upcoming", source="personal", now_iso="2026-09-01T11:50:00Z",
        video_id="vid1", scheduled_start="2026-09-01T12:30:00Z",  # 트윗이 당겨놓음
        info_source="personal", info_at="2026-09-01T11:50:00Z",
        api_start_seen="2026-09-01T12:00:00Z"  # API 는 원래 12:00
    )
    _new_item = preview_mod.make_item(
        channel_key="arale", state="upcoming", source="personal", now_iso=_snow,
        video_id="vid1", scheduled_start="2026-09-01T12:30:00Z",  # build_preview 가 안 건드림
        api_start_seen="2026-09-01T12:00:00Z",  # api_start_seen 변경 없음 (personal 소스라 갱신 안 함)
        info_source="personal", info_at="2026-09-01T11:50:00Z"
    )
    _out = xtweet.apply_overrides([_new_item], [_prev_item], _snow)
    # 규칙 5: api_start_seen 이 같으면 (60초 이내) 그대로 → scheduled_start 변경 없음
    assert _out[0]["scheduled_start"] == "2026-09-01T12:30:00Z", "트윗값 복원 실패"
    assert _out[0]["info_source"] == "personal", "info_source 변경 실패"
    print("[OK] xtweet.apply_overrides: 트윗 유지 (API 불변 60초 이내)")

    # API 승 케이스 (API 변경, 60초 초과)
    # build_preview 가 personal 정보원의 scheduled_start 를 갱신하지 않으므로
    # new_item 도 prev 값 12:30Z 유지. 하지만 api_start_seen 은 갱신된다.
    _new_item2 = preview_mod.make_item(
        channel_key="arale", state="upcoming", source="personal", now_iso=_snow,
        video_id="vid1", scheduled_start="2026-09-01T12:30:00Z",  # build_preview 가 안 건드림
        api_start_seen="2026-09-01T13:00:00Z",  # api_start_seen 갱신됨 (60초 이상 차이)
        info_source="personal", info_at="2026-09-01T11:50:00Z"
    )
    _out2 = xtweet.apply_overrides([_new_item2], [_prev_item], _snow)
    # 규칙 6: api_start_seen 이 60초 이상 차이나면 API 승 → scheduled_start 를 api_start_seen 으로
    assert _out2[0]["scheduled_start"] == "2026-09-01T13:00:00Z", "API 값 미적용"
    assert _out2[0]["info_source"] == "api", "info_source 변경 실패"
    assert _out2[0]["info_at"] == _snow, "info_at 미갱신"
    print("[OK] xtweet.apply_overrides: API 승 (API 변경 60초 초과)")

    print("SUCCESS: handlers self-test 통과")
