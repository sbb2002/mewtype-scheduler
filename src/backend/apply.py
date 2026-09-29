"""(v4a) 적용 큐 — 쓰기 서비스 `/apply` 의 로컬 대응물.

v4a 원칙 ① "data 를 쓰는 곳은 쓰기 서비스 하나". 로컬 시험판에서 쓰기 서비스 = 적용 큐 워커 스레드
`q-apply` 하나(`jobqueue.LocalQueue`). 적재 → 한 줄로 서서 → 이 모듈의 `handle()` 이 하나씩 처리한다.

작업 종류:
  reconcile         {scope: "all", mode} | {scope: "video", video_id}   — 정기 · 정밀 확인 (v3 /tick · /wake)
  snapshot          {}                                                  — 일일 모니터링 스냅샷 (v3 /monitor)
  yt_notif          {video_id, relay_kind, now_iso}                     — (D1·D2·D3) 업스트림 YT 알림
  apply_translation {updates, now_iso}                                  — 가공 큐가 모은 번역 반영
  <writers.py 종류>  merge_rows · personal_tweet · apply_notice …       — 콘텐츠 반영 (v3 /write)

작업이 마지막 시도까지 실패하면(`on_dead`) 유실 원문 큐에 넣고 DM (설계 기능 20 ②).
"""
from __future__ import annotations

import json
import logging
import threading
from collections import deque
from datetime import datetime, timedelta, timezone

log = logging.getLogger("backend.apply")

_q = None                      # LocalQueue("apply")
_recent: deque = deque(maxlen=200)   # 최근 작업 결과 (관리 페이지 · 검증용)
_recent_lock = threading.Lock()

# (v4a D3) 같은 방송 판정 창 — v3.8.10 preview.match_item · SCHEDULED_SUPERSEDE_SEC 와 같은 ±45분
SAME_BROADCAST_SEC = 45 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_queue(q) -> None:
    global _q
    _q = q


def has_queue() -> bool:
    return _q is not None


def pending() -> list[dict]:
    return _q.pending() if _q is not None else []


_recent_loaded = False


def _recent_path():
    import os
    from pathlib import Path
    return Path(os.environ.get("LOCAL_DATA_DIR") or "./_local") / "ops" / "recent_jobs.json"


def _recent_load() -> None:
    """(v4a) 재시작해도 최근 결과가 남도록 로컬 파일에서 읽는다(로컬 시험판 한정)."""
    global _recent_loaded
    if _recent_loaded:
        return
    _recent_loaded = True
    from . import storage
    if not storage.is_local():
        return
    try:
        p = _recent_path()
        if p.exists():
            for e in reversed(json.loads(p.read_text(encoding="utf-8")).get("items", [])):
                _recent.appendleft(e)
    except Exception:  # noqa: BLE001
        log.warning("recent_jobs.json 읽기 실패", exc_info=True)


def recent(limit: int = 50) -> list[dict]:
    with _recent_lock:
        _recent_load()
        return list(_recent)[:limit]


def _record(entry: dict) -> None:
    import os
    from . import storage
    with _recent_lock:
        _recent_load()
        _recent.appendleft(entry)
        if storage.is_local():
            try:
                p = _recent_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps({"items": list(_recent)}, ensure_ascii=False, default=str),
                               encoding="utf-8")
                os.replace(tmp, p)
            except Exception:  # noqa: BLE001
                log.warning("recent_jobs.json 저장 실패", exc_info=True)


def submit(kind: str, args: dict, *, wait: bool = True, run_at_iso: str | None = None,
           name: str | None = None, timeout: float = 300) -> dict:
    """적용 큐에 작업 적재. wait=True 면 결과를 기다려 돌려준다(로컬 한정 — 계획 §1 알려진 차이).

    큐가 없으면(self-test · 비로컬) 그 자리에서 처리한다.
    """
    args = dict(args or {})
    args.pop("gh", None)   # 호출부 store 는 넘기지 않는다 — 쓰기 쪽이 스스로 만든다
    from . import flowtrace
    fid = flowtrace.current.get()
    if fid and "_flow" not in args:
        # (v4a) 흐름 기록 — 이 작업이 어느 알림 · 조작에서 나왔는지. 적재 = 준비 끝 · 적용 대기 시작
        args["_flow"] = fid
        if flowtrace.stage_state("준비", fid) in ("todo", "run"):
            flowtrace.mark("준비", "done", fid=fid)
        flowtrace.mark("적용 대기", "run", fid=fid)
        if not wait:
            flowtrace.annotate(fid=fid, detached=True)   # 요청은 먼저 끝난다 — 워커가 반영 후 흐름을 마무리
    if _q is None:
        return handle(kind, args, {"job_id": "inline", "attempt": 1, "is_last": True, "queue": "inline"})
    if wait:
        # 결과를 기다리는 호출부(접수 쪽)는 실패하면 스스로 원문과 함께 유실 처리한다 — on_dead 가 중복 처리하지 않게 표시
        return _q.submit_and_wait(kind, dict(args, _waited=True), timeout=timeout)
    return {"queued": True, "job_id": _q.enqueue(kind, args, run_at_iso=run_at_iso, name=name)}


def enqueue_reconcile(*, video_id: str | None = None, mode: str = "light",
                      run_at_iso: str | None = None) -> str | None:
    """reconcile(범위) 적재 — v3 의 즉시 wake · 자기 재호출 tick · 재개 tick 을 전부 대체(원칙 ③).

    이름 = 범위 + 실행 시각(분)이라 같은 확인이 여러 번 적재돼도 하나만 남는다(Cloud Tasks 태스크 이름 의미).
    """
    if _q is None:
        return None
    when = run_at_iso or _now_iso()
    if video_id:
        name = f"reconcile-video-{video_id}-{when[:16]}"
        args = {"scope": "video", "video_id": video_id}
        if not any(j.get("name") == name for j in _q.pending()):   # 이미 있는 예약이면 흐름을 새로 안 만든다
            fid = _start_wake_flow(video_id, when)
            if fid:
                args["_flow"] = fid
        return _q.enqueue("reconcile", args, run_at_iso=when, name=name)
    return _q.enqueue("reconcile", {"scope": "all", "mode": mode},
                      run_at_iso=when, name=f"reconcile-all-{mode}-{when[:16]}")


def _kst_hm(iso: str) -> str:
    try:
        dt = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return (dt + timedelta(hours=9)).strftime("%m/%d %H:%M")
    except Exception:  # noqa: BLE001
        return iso


def _broadcast_label(video_id: str) -> str:
    """방송 확인 흐름 설명 — "멤버 「제목」" (예고에 없으면 video_id)."""
    try:
        from ..collector.config import load_channels
        from . import storage
        pv, _ = storage.make_store("data").read_json("preview.json")
        it = next((i for i in (pv or {}).get("items", []) if i.get("video_id") == video_id), None)
        if not it:
            return video_id
        chs = load_channels().get("channels", {})
        keys = [it.get("channel_key")] + list(it.get("collab_with") or [])
        who = "·".join((chs.get(k) or {}).get("name_ko") or k for k in keys if k)
        if len(keys) >= 5:
            who = "5인 합동"
        title = (it.get("title_ko") or it.get("title") or "").strip()
        return f"{who} 「{title[:40]}」 · {video_id}" if title else f"{who} · {video_id}"
    except Exception:  # noqa: BLE001
        return video_id


def _start_wake_flow(video_id: str, when: str) -> str | None:
    """(v4a) 방송 확인 예약 흐름 — 예약(누가) → 대기(언제까지). 이 예약을 만든 흐름이 방송 확인이면
    그 흐름의 "다음 확인" 단계를 채운다."""
    from . import flowtrace
    if not flowtrace.enabled():
        return None
    parent = flowtrace.get(flowtrace.current.get())
    if parent and parent.get("cat") == "wake":
        origin = "이전 확인에서"
        flowtrace.mark("다음 확인", "done", f"{_kst_hm(when)} 예약", fid=parent["id"], ms=_kst_hm(when)[6:])
    elif parent:
        origin = f"{parent.get('kind', '')}에서"
    else:
        origin = "정기 수집에서"
    fid = flowtrace.start("wake", "방송 확인", _broadcast_label(video_id), bind=False,
                          video_id=video_id, run_at=when)
    flowtrace.mark("예약", "done", origin, fid=fid, ms=_kst_hm(_now_iso())[6:])
    flowtrace.mark("대기", "wait", f"{_kst_hm(when)} 까지", fid=fid)
    return fid


class LocalTaskShim:
    """handlers 가 쓰던 Cloud Tasks `TaskQueue` 자리에 들어가는 로컬 대응물 — 전부 reconcile 적재."""

    def enqueue_wake(self, video_id: str, schedule_time_iso: str) -> str:
        return enqueue_reconcile(video_id=video_id, run_at_iso=schedule_time_iso) or ""

    def enqueue_tick(self, mode: str, schedule_time_iso: str) -> str:
        return enqueue_reconcile(mode=mode, run_at_iso=schedule_time_iso) or ""


# ── 작업 처리 (스레드 q-apply) ────────────────────────────────────────────────

_KIND_LABEL = {
    "merge_rows": "예고 반영", "personal_tweet": "개인 트윗 반영", "apply_notice": "소식 반영",
    "url_confirmed_commit": "URL 확정 예고 반영", "yt_member_live_commit": "회원 전용 라이브 반영",
    "yt_notif": "YouTube 알림 반영", "apply_preview_edit": "예고 수정 반영", "remove_broadcast": "예고 삭제",
    "notice_edit_commit": "소식 수정 반영", "notice_del_commit": "소식 삭제", "tweet_del_commit": "트윗 삭제",
    "apply_translation": "번역 반영", "notice_sweep": "지난 소식 정리", "snapshot": "일일 스냅샷",
}


def _wake_note(res: dict) -> str:
    """방송 확인 결과 한 줄 — 상태 전이가 있으면 그것, 없으면 변화 없음."""
    trans = [x for x in (res or {}).get("log") or [] if isinstance(x, str) and x.startswith("→")]
    q = (res or {}).get("quota_used")
    head = " · ".join(t.split(" ")[0] for t in trans) if trans else "변화 없음"
    return head + (f" · 쿼터 {q}" if q else "")


def handle(kind: str, args: dict, meta: dict) -> dict:
    """(v4a) 작업 처리 + 흐름 기록(작업 인자 `_flow`). 흐름 기록은 로컬 전용 · 실패해도 처리엔 영향 없음."""
    from . import flowtrace
    fid = (args or {}).get("_flow")
    if not fid:
        return _handle(kind, args, meta)
    is_wake = kind == "reconcile" and (args or {}).get("scope") == "video"
    with flowtrace.bound(fid):
        flowtrace.mark("대기" if is_wake else "적용 대기", "done")
        try:
            res = _handle(kind, args, meta)
        except Exception as exc:
            stage = "확인 · 반영" if is_wake else "반영"
            if meta.get("is_last", True):
                flowtrace.mark(stage, "fail", f"{type(exc).__name__}: {str(exc)[:120]}")
                if is_wake:
                    flowtrace.finish("확인 실패 — 다음 정기 수집이 다시 확인합니다")
            else:
                flowtrace.mark(stage, "run", f"{meta.get('attempt')}번째 시도 실패 — 재시도 대기: {str(exc)[:80]}")
            raise
        if is_wake:
            flowtrace.mark("확인 · 반영", "done", _wake_note(res))
            f = flowtrace.get(fid)
            nxt = next((s for s in (f or {}).get("stages", []) if s["n"] == "다음 확인"), None)
            flowtrace.finish("완료 — " + _wake_note(res) +
                             ("" if nxt and nxt["s"] == "done" else " · 이 방송의 추가 확인 예약 없음"))
        else:
            flowtrace.mark("반영", "done", _KIND_LABEL.get(kind, kind))
            f = flowtrace.get(fid)
            if f and f.get("detached") and f.get("status") in ("run", "wait"):
                flowtrace.finish(f"완료 — {_KIND_LABEL.get(kind, kind)}")
        return res


def _handle(kind: str, args: dict, meta: dict) -> dict:
    from . import storage, writers

    if kind == "reconcile":
        from . import handlers
        if args.get("scope") == "video" and args.get("video_id"):
            return _slim(handlers.wake(args["video_id"]))
        return _slim(handlers.tick(args.get("mode") or "light"))
    if kind == "snapshot":
        return run_snapshot()
    if kind == "yt_notif":
        return apply_yt_notif(storage.make_store("data"), args)
    if kind == "apply_translation":
        from . import enrich
        return enrich.apply_translations(storage.make_store("data"), args.get("updates"),
                                         args.get("now_iso") or _now_iso(), force=bool(args.get("force")))
    return writers.dispatch(kind, storage.make_store("data"), args)


def _slim(result: dict) -> dict:
    """reconcile 결과에서 관리 페이지 · 기록에 필요한 것만."""
    keep = ("mode", "woken", "paused", "candidates", "videos", "preview_changed", "archive_changed",
            "archived", "state_counts", "wakes", "enqueued", "enqueue_errors", "quota_used", "log")
    return {k: result.get(k) for k in keep if k in (result or {})}


def _brief(job: dict) -> dict:
    a = job.get("args") or {}
    return {k: a[k] for k in ("scope", "mode", "video_id", "channel_key", "unit", "nid") if a.get(k)}


def on_done(job: dict, result) -> None:
    _record({"ts": _now_iso(), "job_id": job.get("id"), "kind": job.get("kind"), "ok": True,
             "attempt": job.get("attempt"), "summary": _summary(result), "brief": _brief(job),
             "result": _slim(result) if isinstance(result, dict) and "log" in result else None})


def on_dead(job: dict, exc: BaseException) -> None:
    """마지막 시도까지 실패 — 유실 원문 큐 + DM (설계 기능 20 ②)."""
    _record({"ts": _now_iso(), "job_id": job.get("id"), "kind": job.get("kind"), "ok": False,
             "attempt": job.get("attempt"), "summary": f"{type(exc).__name__}: {str(exc)[:200]}",
             "brief": _brief(job)})
    args = job.get("args") or {}
    if job.get("kind") in ("reconcile", "snapshot", "apply_translation"):
        return  # 재계산으로 복구되는 작업 — 원문이 없으므로 유실 큐 대상 아님
    if args.get("_waited"):
        return  # 결과를 기다리던 접수 쪽이 원문과 함께 유실 처리한다(_dm_lost_raw) — 중복 적재 · 중복 DM 방지
    try:
        from . import monitor_log, storage
        # 결과를 기다리지 않은 작업(yt_notif 등) — 원문 트윗이 아니라 "작업 그 자체"를 보관하고,
        # 관리 페이지 재투입은 같은 작업을 다시 적재한다(admin_api._retry_one 의 apply_job 갈래).
        monitor_log.push_lost(storage.make_store("data"), {
            "ts": _now_iso(), "reason": f"적용 큐 작업 실패({job.get('kind')}): {str(exc)[:200]}",
            "kind": "apply_job", "job_kind": job.get("kind"),
            "raw": json.dumps(args, ensure_ascii=False, default=str)[:4000],
            "channel_key": args.get("channel_key"), "job_id": job.get("id"),
        })
    except Exception:  # noqa: BLE001
        log.exception("on_dead: 유실 큐 적재 실패")
    try:
        from .telegram_app import _send_telegram
        _send_telegram(f"⚠️ 적용 큐 작업 실패 — {job.get('kind')} (시도 {job.get('attempt')}회)\n{str(exc)[:300]}\n"
                       "원문은 유실 원문 큐에 보관 — 관리 페이지에서 재투입")
    except Exception:  # noqa: BLE001
        log.warning("on_dead DM 실패", exc_info=True)


def _summary(result) -> str:
    if not isinstance(result, dict):
        return str(result)[:200]
    if "log" in result or "preview_changed" in result:
        return (f"candidates={result.get('candidates')} changed={result.get('preview_changed')} "
                f"archived={len(result.get('archived') or [])}")
    return json.dumps(result, ensure_ascii=False, default=str)[:200]


# ── 일일 스냅샷 (v3 app.py /monitor 본문) ──────────────────────────────────────

def run_snapshot() -> dict:
    """모니터링 스냅샷 + (monitor_auto 면) 멤버 현황 DM. v3 `app.py /monitor` 와 같은 동작."""
    from . import monitor_report, monitor_snapshot, notify, storage
    from .config import load_config
    from .control import default_control, get_monitor_auto
    from .monitor_log import KST, bucket_date_kst

    cfg = load_config()
    gh = storage.make_store("data")
    gh_monitor = storage.with_branch(gh, cfg.monitor_branch)
    now = datetime.now(KST)
    today_bucket = bucket_date_kst(now)
    now_iso = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap = monitor_snapshot.run_daily(
        gh_monitor, today_bucket=today_bucket, now_iso=now_iso,
        healthchecks_api_key=cfg.healthchecks_api_key,
        healthchecks_uuid=(cfg.healthcheck_url.rsplit("/", 1)[-1] if cfg.healthcheck_url else ""),
        vercel_token=cfg.vercel_token,
    )
    yday = snap["yesterdayDate"]
    result = {"date": yday, "snapshotted": snap["snapshotted"], "dm": False}
    if snap["yesterday"] is not None:
        try:
            report = monitor_report.snapshot_report(snap["yesterday"], yday, snap["summary"])
            gh_monitor.write_text("monitoring/latest.html", monitor_report.render_html(report), prev_sha=None,
                                  message=f"data: monitor latest {yday}")
        except Exception:  # noqa: BLE001
            log.exception("snapshot: latest.html 실패 (DM 은 계속)")
    control, _ = gh.read_json("control.json")
    if get_monitor_auto(control or default_control()):
        result["dm"] = notify.Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id).send(
            monitor_snapshot.member_status_text(yday, snap["yesterday"]))
    return result


# ── (v4a D1·D2·D3) 업스트림 YouTube 알림 ──────────────────────────────────────

def _parse(iso: str | None):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def mark_from_notif(items: list[dict], video_id: str, relay_kind: str, now_iso: str,
                    channel_key: str | None = None) -> tuple[list[dict], dict | None, str]:
    """알림을 preview 아이템에 반영 (순수). 반환 = (items, 바뀐 아이템 | None, 사유).

    1) 같은 video_id 아이템 → tunein 이면 watching(D2), reminder/sub_start 면 live(D1)
    2) (D3) 없으면 같은 채널의 URL 없는 예고 중 예고 시각이 (알림 시각 + tunein 30분 | 0분) ±45분인 것에
       URL 을 붙이고 같은 상태로. channel_key 를 모르면 이 단계는 건너뛴다.
    상태를 되돌리지는 않는다(live/end 인 아이템에 tunein 이 와도 그대로).
    """
    from . import preview as preview_mod

    items = [dict(i) for i in (items or [])]
    now = _parse(now_iso)
    to_state = "watching" if relay_kind == "tunein" else "live"
    rank = {"announced": 0, "upcoming": 1, "watching": 2, "live": 3, "end": 4}

    def _apply(it: dict) -> dict:
        if rank.get(it.get("state"), 0) >= rank[to_state]:
            return it
        it = preview_mod.set_state(it, to_state, now_iso)
        it["info_source"] = it.get("info_source") or "yt-notif"
        if to_state == "watching":
            it["yt_tunein"] = True        # 20분 창보다 이른 watching 을 FSM 이 되돌리지 않게
        else:
            it["actual_start"] = it.get("actual_start") or now_iso
        return it

    for idx, it in enumerate(items):
        if it.get("video_id") == video_id:
            new = _apply(it)
            if new is it:
                return items, None, "no-change"
            items[idx] = new
            return items, new, "video_id"

    if channel_key and now:
        target = now + timedelta(minutes=30 if relay_kind == "tunein" else 0)
        best = None
        for idx, it in enumerate(items):
            if it.get("video_id") or it.get("channel_key") != channel_key or it.get("state") != "announced":
                continue
            ss = _parse(it.get("scheduled_start"))
            if not ss:
                continue
            d = abs((ss - target).total_seconds())
            if d <= SAME_BROADCAST_SEC and (best is None or d < best[0]):
                best = (d, idx)
        if best is not None:
            it = dict(items[best[1]])
            it["video_id"] = video_id
            it["url"] = f"https://www.youtube.com/watch?v={video_id}"
            new = _apply(it)
            items[best[1]] = new
            return items, new, "placeholder"
    return items, None, "not-found"


def _channel_key_of_video(store, video_id: str) -> str | None:
    """reconcile(영상) 뒤 preview 에서 그 영상의 채널. 없으면(회원 전용 · API 실패) None."""
    try:
        pv, _ = store.read_json("preview.json")
    except Exception:  # noqa: BLE001
        return None
    for it in (pv or {}).get("items", []) or []:
        if it.get("video_id") == video_id:
            return it.get("channel_key")
    return None


def apply_yt_notif(store, args: dict) -> dict:
    """적용 큐 작업 yt_notif: reconcile(영상)으로 API 사실을 먼저 반영 → 알림으로 상태를 올린다.

    API 가 이미 live 로 보면 reconcile 만으로 끝난다. API 가 늦으면(아직 upcoming) 알림이 먼저 상태를 올리고,
    다음 reconcile 들이 폴링 안전망으로 확인한다(D1). reconcile 이 video_id 로 채널을 알게 되므로 URL 없는
    예고와의 ±45분 합치기(D3)는 reconcile 의 자리표시 흡수(preview_build 2-b)가 먼저 처리하고, 여기서는
    그래도 남은 자리표시가 있으면 알림 시각 기준으로 한 번 더 찾는다.
    """
    from . import handlers, monitor_log, notify
    from . import preview as preview_mod
    from .config import load_config
    from .control import default_control, get_log_level

    video_id = args["video_id"]
    relay_kind = args.get("relay_kind") or "sub_start"
    now_iso = args.get("now_iso") or _now_iso()

    rec = handlers.wake(video_id)          # API 확인 (같은 스레드 — 원칙 ①)
    ck = _channel_key_of_video(store, video_id) or args.get("channel_key")

    for _ in range(3):
        pv, sha = store.read_json("preview.json")
        pv = pv or preview_mod.default_preview()
        items, changed, why = mark_from_notif(pv.get("items", []), video_id, relay_kind, now_iso, ck)
        if changed is None:
            break
        new_pv = dict(pv, items=preview_mod.sort_items(items), generated_at=now_iso)
        try:
            store.write_json("preview.json", new_pv, prev_sha=sha, message=f"data: yt-notif {relay_kind} {video_id}")
        except Exception as e:  # noqa: BLE001 — ConflictError 면 다시 읽어 재계산
            from .gh_store import ConflictError
            if isinstance(e, ConflictError):
                continue
            raise
        prev_items = pv.get("items", [])
        try:
            cfg = load_config()
            control, _ = store.read_json("control.json")
            level = get_log_level(control or default_control())
            from ..collector.config import load_channels
            chs = load_channels()["channels"]
            tg = notify.Telegram(cfg.telegram_bot_token, cfg.telegram_chat_id)
            for ev in notify.diff_events(prev_items, new_pv["items"], [], chs, now_iso):
                if notify.allows(level, ev.kind):
                    tg.send(ev.text)
        except Exception:  # noqa: BLE001
            log.warning("yt_notif DM 실패", exc_info=True)
        evs = [{
            "ts": now_iso, "flow": "preview", "result": monitor_log.RESULT_OK, "who": ev.get("channel_key", ""),
            "detail": f"{ev.get('from_state')}→{ev.get('to_state')} (yt-notif {relay_kind})",
            "from_state": ev.get("from_state"), "to_state": ev.get("to_state"), "video_id": ev.get("video_id"),
            "item_id": ev.get("id"), "title": ev.get("title"),
        } for ev in handlers._preview_log_events(prev_items, new_pv["items"], [])]
        monitor_log.log_events(store, now_iso, evs)
        # 다음 확인: watching 은 3분 격자 · live 는 10분 격자로 FSM 이 잡는다 — 지금 한 번 더 예약
        enqueue_reconcile(video_id=video_id, run_at_iso=(datetime.now(timezone.utc) + timedelta(minutes=3))
                          .strftime("%Y-%m-%dT%H:%M:%SZ"))
        return {"video_id": video_id, "relay_kind": relay_kind, "marked": why,
                "state": changed.get("state"), "reconcile": _slim(rec)}
    return {"video_id": video_id, "relay_kind": relay_kind, "marked": "none", "reconcile": _slim(rec)}


if __name__ == "__main__":
    # mark_from_notif (순수) — D1 · D2 · D3
    now = "2026-09-29T12:00:00Z"
    base = [
        {"id": "a", "channel_key": "arale", "state": "upcoming", "video_id": "V1",
         "scheduled_start": "2026-09-29T12:30:00Z", "title": "t"},
        {"id": "b", "channel_key": "yuno", "state": "announced", "video_id": None,
         "scheduled_start": "2026-09-29T12:40:00Z", "title": "u"},
        {"id": "c", "channel_key": "yuno", "state": "announced", "video_id": None,
         "scheduled_start": "2026-09-29T15:00:00Z", "title": "w"},
        {"id": "d", "channel_key": "ritsu", "state": "live", "video_id": "V4"},
    ]
    items, ch, why = mark_from_notif(base, "V1", "tunein", now)
    assert why == "video_id" and ch["state"] == "watching" and ch["yt_tunein"] is True, (why, ch)
    items, ch, why = mark_from_notif(base, "V1", "sub_start", now)
    assert ch["state"] == "live" and ch["actual_start"] == now, ch
    # D3: tunein 12:00 → 예고 시각 12:30 ±45분 안의 URL 없는 yuno 예고(12:40)에 URL 부여
    items, ch, why = mark_from_notif(base, "V9", "tunein", now, channel_key="yuno")
    assert why == "placeholder" and ch["id"] == "b" and ch["video_id"] == "V9" and ch["state"] == "watching", (why, ch)
    assert next(i for i in items if i["id"] == "c")["video_id"] is None, "먼 예고(15:00)는 안 건드림"
    # 채널 모름 / 창 밖
    assert mark_from_notif(base, "V9", "tunein", now)[2] == "not-found"
    assert mark_from_notif(base, "V9", "sub_start", "2026-09-29T10:00:00Z", channel_key="yuno")[2] == "not-found"
    # 되돌리지 않음: live 인 아이템에 tunein
    assert mark_from_notif(base, "V4", "tunein", now)[2] == "no-change"

    # 큐 없이 submit → 그 자리 처리 (writers 알 수 없는 종류는 ValueError)
    try:
        submit("no-such-kind", {})
        raise AssertionError
    except ValueError:
        pass
    print("[PASS] apply self-test: yt 알림 반영(D1·D2·D3) · 되돌림 없음 · 큐 없을 때 즉시 처리")
