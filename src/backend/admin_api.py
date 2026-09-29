"""(v4a D24) 관리 페이지가 부르는 함수 모음 — 읽기 + 적용 큐 적재.

관리 페이지(`admin_web.py`)는 이 모듈의 함수만 부른다. data 브랜치를 직접 쓰지 않고, 콘텐츠 조작은 전부
적용 큐(`apply.submit`)로 보낸다(v4a 원칙 ①⑤). 운영 상태(control · 재등록 차단 · 작업 이력)는 ops 에 직접 쓴다
(설계 §6 — `/pause` 는 적용 큐 상태와 무관하게 즉시 먹혀야 하므로).

조작 함수 공통 반환: {"ok": bool, "job_id": str | None, "result": dict | None, "error": str | None}
- ok=False 이고 error 가 "conflict:<필드들>" 이면 열람 값 충돌(그 사이 reconcile 이 바꿈).

느린 외부 호출(LLM · videos.list · vxtwitter)은 여기(접수 쪽)에서 하고, 적용 큐 작업은 커밋만 한다(원칙 ④).
기존 텔레그램 명령이 쓰던 준비 · 커밋 함수(`telegram_app._prepare_*` · `writers.py` 종류)를 그대로 재사용한다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from . import apply, enrich, storage

log = logging.getLogger("backend.admin_api")

_HISTORY_PATH = "history.json"      # ops 브랜치
_HISTORY_MAX = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store():
    return storage.make_store("data")


def _t():
    from . import telegram_app
    return telegram_app


def _ok(result=None, job_id=None) -> dict:
    return {"ok": True, "job_id": job_id, "result": result, "error": None}


def _err(msg: str) -> dict:
    return {"ok": False, "job_id": None, "result": None, "error": msg}


def _record(action: str, target: str, summary: str, res: dict) -> dict:
    """운영자 조작 이력(ops/history.json, 최신순). 기록 실패는 조작 결과에 영향 없음."""
    try:
        ops = storage.make_store("ops")
        for _ in range(3):
            data, sha = ops.read_json(_HISTORY_PATH)
            items = list((data or {}).get("items", []))
            items.insert(0, {"id": uuid.uuid4().hex[:10], "ts": _now_iso(), "action": action, "target": target,
                             "summary": summary[:300], "ok": bool(res.get("ok")), "error": res.get("error"),
                             "job_id": res.get("job_id")})
            try:
                ops.write_json(_HISTORY_PATH, {"items": items[:_HISTORY_MAX]}, prev_sha=sha,
                               message=f"ops: history {action} {target}")
                break
            except Exception:  # noqa: BLE001 — ConflictError 면 다시 읽기
                continue
    except Exception:  # noqa: BLE001
        log.warning("작업 이력 기록 실패", exc_info=True)
    return res


def _submit(kind: str, args: dict) -> dict:
    """적용 큐 적재 + 결과 대기 → 공통 반환 형식."""
    try:
        result = apply.submit(kind, args, wait=True)
        return _ok(result)
    except Exception as e:  # noqa: BLE001
        return _err(f"{type(e).__name__}: {str(e)[:250]}")


# ── 읽기 ──────────────────────────────────────────────────────────────────────

def list_preview() -> dict:
    """preview.json 전체 ({"generated_at", "channel_order", "channels", "items"})."""
    return _store().read_json("preview.json")[0] or {"items": []}


def list_notices() -> dict:
    """notices.json 전체 ({"generated_at", "notices": [...]})."""
    return _store().read_json("notices.json")[0] or {"notices": []}


def list_tweets() -> dict:
    """tweets.json 전체 ({"generated_at", "tweets": {<unit>: [..]}})."""
    return _store().read_json("tweets.json")[0] or {"tweets": {}}


def get_control() -> dict:
    """ops 의 control.json ({"paused", "log_level", "monitor_auto", ...})."""
    from .control import default_control
    return _store().read_json("control.json")[0] or default_control()


def list_history(limit: int = 50) -> list[dict]:
    """운영자 조작 이력(최신순). 항목: {"id", "ts", "action", "target", "summary", "job_id", "ok", "error"}."""
    data, _ = storage.make_store("ops").read_json(_HISTORY_PATH)
    return list((data or {}).get("items", []))[: max(1, int(limit or 50))]


def _lost_id(idx: int, item: dict) -> str:
    return f"{idx}:{item.get('ts', '')}"


def list_lost() -> list[dict]:
    """유실 원문 큐(monitoring/lost_queue.json 의 pending). 항목마다 재투입용 "id" 를 붙여 돌려준다."""
    from . import monitor_log
    pending, _ = monitor_log.read_lost(_store())
    return [dict(it, id=_lost_id(i, it)) for i, it in enumerate(pending or [])]


def list_jobs() -> dict:
    """큐 상태: {"apply": [대기 작업...], "enrich": [...], "recent": [최근 작업 결과...]}."""
    return {"apply": apply.pending(), "enrich": enrich.pending(), "recent": apply.recent(50)}


def channels() -> dict:
    """config/channels.json 의 {"channel_order": [...], "channels": {key: {name, name_ko, ...}}}."""
    from ..collector.config import load_channels
    return load_channels()


# ── 조작 (적용 큐 적재) ─────────────────────────────────────────────────────────

_PREVIEW_FIELD = {"title": "title", "state": "state", "scheduled_start": "date", "url": "url"}
_EDITABLE_STATES = ("announced", "upcoming", "watching", "live", "end")


def edit_preview(item_id: str, patch: dict, seen: dict) -> dict:
    """예고 항목 수정. patch 키: title · state · scheduled_start(ISO Z) · url 중 일부.
    seen = 폼을 열 때 본 같은 키의 값 — 현재 값과 다르면 conflict."""
    patch = {k: v for k, v in (patch or {}).items() if k in _PREVIEW_FIELD}
    if not patch:
        return _err("바꿀 필드가 없습니다")
    if "state" in patch and patch["state"] not in _EDITABLE_STATES:
        return _err(f"state 는 {', '.join(_EDITABLE_STATES)} 중 하나 (삭제는 삭제 버튼)")
    pv = list_preview()
    cur = next((it for it in pv.get("items", []) if it.get("id") == item_id), None)
    if cur is None:
        return _err("항목이 없습니다 (이미 사라짐)")
    seen = seen or {}
    changed = [k for k in patch if k in seen and cur.get(k) != seen.get(k)]
    if changed:
        return _err("conflict:" + ",".join(changed))
    ctx = {"id": item_id,
           "patch": {_PREVIEW_FIELD[k]: v for k, v in patch.items()},
           "pre": {_PREVIEW_FIELD[k]: cur.get(k) for k in patch}}
    res = _submit("apply_preview_edit", {"now_iso": _now_iso(), "ctx": ctx})
    return _record("edit_preview", item_id, f"{cur.get('channel_key')} {cur.get('title') or ''} ← {patch}", res)


def delete_preview(item_id: str, suppress: bool) -> dict:
    """예고 항목 삭제(아카이브). suppress=True 면 그 URL 을 12시간 재등록 차단(ops admin_state)."""
    pv = list_preview()
    cur = next((it for it in pv.get("items", []) if it.get("id") == item_id), None)
    if cur is None:
        return _err("항목이 없습니다 (이미 사라짐)")
    now = _now_iso()
    res = _submit("remove_broadcast", {"snapshot": cur, "now_iso": now,
                                       "action": f"admin 삭제 {cur.get('channel_key')} {item_id}"})
    if res["ok"] and not (res.get("result") or {}).get("removed"):
        res = _err("삭제 안 됨 — 그 사이 항목이 바뀌었거나 사라졌습니다")
    if res["ok"] and suppress and cur.get("url"):
        from . import admin
        try:
            gh = _store()
            st, sha = gh.read_json("admin_state.json")
            gh.write_json("admin_state.json", admin.add_suppress(st or admin.default_admin_state(),
                                                                 url=cur["url"], now_iso=now),
                          prev_sha=sha, message=f"ops: suppress += {cur['url']} {now}")
            res["result"] = dict(res.get("result") or {}, suppressed=True)
        except Exception as e:  # noqa: BLE001
            res["result"] = dict(res.get("result") or {}, suppressed=False, suppress_error=str(e)[:100])
    return _record("delete_preview", item_id,
                   f"{cur.get('channel_key')} {cur.get('title') or ''}" + (" (재등록 차단)" if suppress else ""), res)


def ingest_preview_raw(raw: str, *, confirm: bool, channel_key: str | None = None) -> dict:
    """예고 원문 투입. confirm=False → 반영 없이 파싱 미리보기 {"ok", "preview": [행...], "note"}.
    confirm=True → 적용 큐 적재. channel_key 는 개인 예고일 때 유닛 지정(없으면 공식 스케줄 형식만)."""
    t = _t()
    raw = (raw or "").strip()
    if not raw:
        return _err("원문이 비었습니다")
    now = _now_iso()
    gh = _store()
    chs = t._load_channels_config()
    rows = t.xrelay.parse(raw, now) if t.xrelay is not None else []
    if rows:
        if not confirm:
            return {"ok": True, "preview": rows, "note": f"공식 스케줄 형식 — {len(rows)}행 "
                    f"(인식 실패 {len(t.xrelay.unparsed_lines(raw))}줄). 확정 시 합동 LLM 확인 · 영상 URL 즉시 확인"}
        rows = t._confirm_relay_rows_collab(gh, raw, rows, chs, now, via="ops")
        rows, vids = t._confirm_rows_with_videos(rows, now)
        t._preserve_raw("official_schedule", raw, {"via": "admin", "rows": len(rows)}, now)
        res = _submit("merge_rows", {"rows": rows, "now_iso": now, "message": f"data: admin 예고 투입 {now}",
                                     "action": f"admin 예고 투입 {raw[:30]}"})
        for v in vids:
            apply.enqueue_reconcile(video_id=v)
        return _record("ingest_preview", "official", f"{len(rows)}행", res)

    if not channel_key:
        return _err("공식 스케줄 형식이 아닙니다 — 개인 예고면 유닛을 고르세요")
    if t.xtweet is None:
        return _err("xtweet 모듈 없음")
    has_yt = bool(t.xtweet.YT_VIDEO_RE.search(t.xtweet.normalize(raw)))
    if has_yt:
        if not confirm:
            vid = t.xtweet.YT_VIDEO_RE.search(t.xtweet.normalize(raw)).group(1)
            return {"ok": True, "preview": {"channel_key": channel_key, "video_id": vid},
                    "note": "영상 URL 있음 — 확정 시 videos.list 로 확인해 등록(외부 채널이면 LLM 참여 판정)"}
        try:
            t._maybe_url_confirmed_schedule(gh, raw, channel_key, now, chs, via="ops")
            t._preserve_raw("personal_schedule_url", raw, {"channel_key": channel_key, "via": "admin"}, now)
            res = _ok({"path": "url_confirmed"})
        except Exception as e:  # noqa: BLE001
            res = _err(str(e)[:250])
        return _record("ingest_preview", channel_key, "개인 예고(영상 URL)", res)

    row = t.xtweet.parse_schedule(raw, channel_key=channel_key, tag=None, now_iso=now)
    if not row:
        return _err("예고로 인식되지 않았습니다 (配信 계열 키워드 + 미래 날짜 필요)")
    row = dict(row, source="manual", info_source="personal")
    if not confirm:
        return {"ok": True, "preview": row, "note": "개인 예고(URL 없음) — 운영자 확정이라 LLM 최종 확인은 생략"}
    t._preserve_raw("personal_schedule_candidate", raw, {"channel_key": channel_key, "via": "admin"}, now)
    res = _submit("merge_rows", {"rows": [row], "now_iso": now, "merge_fn": "personal_schedule",
                                 "message": f"data: admin 개인 예고 투입 {now}",
                                 "action": f"admin 개인 예고 {channel_key}"})
    return _record("ingest_preview", channel_key, "개인 예고(URL 없음)", res)


def ingest_notice_raw(raw: str, *, confirm: bool) -> dict:
    """소식 원문 투입. confirm=False → 미리보기 {"ok", "preview": {소식 항목}}."""
    t = _t()
    raw = (raw or "").strip()
    now = _now_iso()
    gh = _store()
    prepared = t._prepare_notice(raw, now, gh=gh) if raw else None
    if not prepared:
        return _err("소식으로 인식되지 않았습니다 (리트윗 · 스케줄 형식 · 날짜 없음 등)")
    if not confirm:
        return {"ok": True, "preview": {"parsed": prepared.get("parsed"), "tl": prepared.get("tl"),
                                        "dup_id": prepared.get("dup_id")},
                "note": "중복이면 dup_id 에 기존 소식 id"}
    apply.submit("notice_sweep", {"now_iso": now}, wait=True)
    res = _submit("apply_notice", {"prepared": prepared, "now_iso": now})
    title = (prepared.get("parsed") or {}).get("title") or ""
    return _record("ingest_notice", "notice", title, res)


def ingest_tweet_raw(raw: str, *, unit: str, confirm: bool) -> dict:
    """개인 트윗 원문 투입(교체 포함). confirm=False → 미리보기 {"ok", "preview": {트윗 항목}}."""
    t = _t()
    raw = (raw or "").strip()
    chs = t._load_channels_config()
    if unit not in (chs.get("channels") or {}):
        return _err("유닛을 고르세요")
    now = _now_iso()
    name = chs["channels"][unit].get("name") or unit
    prepared = t._prepare_personal_tweet(raw, title=name, tag=None, channel_key=unit, now_iso=now,
                                         gh=_store()) if raw else None
    if not prepared:
        return _err("트윗으로 인식되지 않았습니다 (리트윗 · 빈 본문 등)")
    if not confirm:
        return {"ok": True, "preview": {"parsed": prepared.get("parsed"), "text_ko": prepared.get("text_ko")}}
    res = _submit("personal_tweet", {"prepared": prepared, "channel_key": unit, "now_iso": now, "via": "ops"})
    return _record("ingest_tweet", unit, raw[:60], res)


def edit_notice(nid: str, patch: dict) -> dict:
    """소식 수정. patch 키: title · date(YYYY-MM-DD) · url 중 일부."""
    patch = {k: v for k, v in (patch or {}).items() if k in ("title", "date", "url")}
    if not patch:
        return _err("바꿀 필드가 없습니다")
    res = _submit("notice_edit_commit", {"nid": nid, "patch": patch, "now_iso": _now_iso()})
    if res["ok"] and not (res.get("result") or {}).get("changed"):
        res = _err("바뀐 것이 없거나 소식이 없습니다")
    return _record("edit_notice", nid, str(patch), res)


def delete_notice(nid: str) -> dict:
    """소식 삭제(아카이브)."""
    res = _submit("notice_del_commit", {"nid": nid, "now_iso": _now_iso()})
    if res["ok"] and (res.get("result") or {}).get("removed") is False:
        res = _err("소식이 없습니다")
    return _record("delete_notice", nid, "", res)


def delete_tweet(unit: str) -> dict:
    """해당 유닛의 현재 트윗 삭제(아카이브)."""
    res = _submit("tweet_del_commit", {"unit": unit, "now_iso": _now_iso()})
    if res["ok"] and (res.get("result") or {}).get("found") is False:
        res = _err("그 유닛의 트윗이 없습니다")
    return _record("delete_tweet", unit, "", res)


def translate(target: str, key: str) -> dict:
    """수동 번역. target ∈ {"preview", "notice", "tweet"}, key = 항목 id(트윗은 유닛)."""
    from .config import load_config
    from .handlers import _make_llm
    cfg = load_config()
    if not cfg.groq_api_key:
        return _err("GROQ_API_KEY 없음")
    llm = _make_llm(cfg)
    up = enrich.empty_updates()
    if target == "preview":
        it = next((i for i in list_preview().get("items", []) if i.get("id") == key), None)
        if not it or not it.get("title"):
            return _err("항목 없음")
        ko = llm.translate(it["title"])
        if ko:
            up["preview"][key] = {"title": it["title"], "title_ko": ko}
    elif target == "notice":
        n = next((x for x in list_notices().get("notices", []) if x.get("id") == key), None)
        if not n:
            return _err("소식 없음")
        r = llm.notice_title(n.get("body_for_llm") or n.get("title") or "")
        if r and r.get("title_ko"):
            up["notices"][key] = {"title": r.get("title_ja") or n.get("title"), "title_ko": r["title_ko"]}
    elif target == "tweet":
        lst = (list_tweets().get("tweets") or {}).get(key) or []
        for tw in (lst if isinstance(lst, list) else [lst]):
            ko = llm.translate(tw.get("text") or "")
            if ko:
                up["tweets"][f"{key}|{tw.get('id')}"] = {"text_ko": ko}
    else:
        return _err("target 은 preview · notice · tweet")
    if not enrich.count(up):
        return _record("translate", f"{target}:{key}", "번역 실패", _err("LLM 번역 실패"))
    res = _submit("apply_translation", {"updates": up, "now_iso": _now_iso(), "force": True})
    return _record("translate", f"{target}:{key}", "", res)


def _retry_one(t, item: dict, chs: dict, now: str) -> str:
    """유실 원문 1건 재처리 → 결과 모드 문자열 (v3.9 `/ingest --retroactive` 와 같은 갈래)."""
    kind = item.get("kind", "ingest")
    raw, title, tag = item.get("raw", ""), item.get("title", ""), item.get("tag")
    if kind == "personal_tweet":
        return t._maybe_personal_tweet(raw, title=title, tag=tag, channel_key=item.get("channel_key", ""),
                                       now_iso=now, via="ops")
    if kind == "notice":
        return t._maybe_auto_notice(raw, now, tag=tag, title=title)
    route = "official"
    if t.xtweet is not None:
        try:
            route = t.xtweet.route_by_title(title, chs, test_titles=())
        except Exception:  # noqa: BLE001
            route = "official"
    if route != "official":
        return t._maybe_personal_tweet(raw, title=title, tag=tag, channel_key=route, now_iso=now, via="ops")
    return t._maybe_auto_notice(raw, now, tag=tag, title=title)


def retry_lost(ids: list[str]) -> dict:
    """유실 원문 재투입 — 한 건씩 순차(동시 발사가 애초 유실 원인, v3.9). 성공한 항목만 큐에서 뺀다."""
    from . import monitor_log
    t = _t()
    gh = _store()
    pending, sha = monitor_log.read_lost(gh)
    pending = pending or []
    want = set(ids or [])
    chs = t._load_channels_config()
    now = _now_iso()
    done, failed, keep = [], [], []
    for i, it in enumerate(pending):
        lid = _lost_id(i, it)
        if lid not in want:
            keep.append(it)
            continue
        try:
            mode = _retry_one(t, it, chs, now)
            if mode in ("error", "none", None):
                failed.append({"id": lid, "error": f"mode={mode}"})
                keep.append(it)
            else:
                done.append(lid)
        except Exception as e:  # noqa: BLE001
            failed.append({"id": lid, "error": str(e)[:150]})
            keep.append(it)
    if done:
        monitor_log.write_lost(gh, keep, sha, f"data: lost_queue admin 재투입 ({len(done)}/{len(want)})")
    res = {"ok": not failed, "job_id": None, "result": {"done": done, "failed": failed},
           "error": None if not failed else f"{len(failed)}건 실패"}
    res["done"], res["failed"] = done, failed
    return _record("retry_lost", ",".join(sorted(want))[:100], f"성공 {len(done)} · 실패 {len(failed)}", res)


def _write_control(mutate, action: str) -> dict:
    """ops control.json 직접 쓰기(설계 §6 — 적용 큐와 무관하게 즉시)."""
    from .control import default_control
    gh = _store()
    for _ in range(3):
        cur, sha = gh.read_json("control.json")
        new = mutate(cur or default_control())
        try:
            gh.write_json("control.json", new, prev_sha=sha, message=f"ops: {action} {_now_iso()}")
            return _ok(new)
        except Exception:  # noqa: BLE001 — 충돌이면 다시
            continue
    return _err("control.json 쓰기 충돌")


def set_paused(paused: bool) -> dict:
    """일시정지 · 재개 (재개면 reconcile(전체) 적재 — v3 의 /tick 동기 호출 대체)."""
    from .control import set_paused as _sp
    res = _write_control(lambda c: _sp(c, bool(paused), by="admin", now_iso=_now_iso()),
                         "pause" if paused else "resume")
    if res["ok"] and not paused:
        res["job_id"] = apply.enqueue_reconcile(mode="light")
    return _record("set_paused", str(bool(paused)), "", res)


def set_log_level(level: str) -> dict:
    """알림 레벨 simple · normal · detail."""
    from .control import LOG_LEVELS, set_log_level as _sl
    if level not in LOG_LEVELS:
        return _err(f"레벨은 {', '.join(LOG_LEVELS)}")
    return _record("set_log_level", level, "",
                   _write_control(lambda c: _sl(c, level, by="admin", now_iso=_now_iso()), "log_level"))


def set_monitor_auto(enabled: bool) -> dict:
    """일일 멤버 현황 DM on/off."""
    from .control import set_monitor_auto as _sm
    return _record("set_monitor_auto", str(bool(enabled)), "",
                   _write_control(lambda c: _sm(c, bool(enabled), by="admin", now_iso=_now_iso()),
                                  "monitor_auto"))


def undo(history_id: str) -> dict:
    """(범위 밖 — 항목 단위 되돌리기는 배포 단계) 현재는 {"ok": False, "error": "미구현"}."""
    return {"ok": False, "job_id": None, "result": None, "error": "미구현 (v4a 로컬 시험판 범위 밖)"}


API_FUNCTIONS: tuple[str, ...] = (
    "list_preview", "list_notices", "list_tweets", "get_control", "list_history", "list_lost",
    "list_jobs", "channels", "edit_preview", "delete_preview", "ingest_preview_raw",
    "ingest_notice_raw", "ingest_tweet_raw", "edit_notice", "delete_notice", "delete_tweet",
    "translate", "retry_lost", "set_paused", "set_log_level", "set_monitor_auto", "undo",
)


if __name__ == "__main__":
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        os.environ.update({"V4A_RUNTIME": "local", "LOCAL_DATA_DIR": d, "ALLOW_UNAUTH": "1"})
        gh = _store()
        now = "2026-09-29T12:00:00Z"
        gh.write_json("preview.json", {"items": [
            {"id": "pv_a", "channel_key": "arale", "state": "announced", "title": "歌枠",
             "scheduled_start": "2026-09-29T13:00:00Z", "video_id": None, "url": None},
        ]}, prev_sha=None, message="seed")
        # 읽기
        assert list_preview()["items"][0]["id"] == "pv_a"
        assert get_control()["paused"] is False
        assert set(channels()["channels"]) >= {"arale", "yuno"}
        # 수정 — 충돌
        r = edit_preview("pv_a", {"title": "새 제목"}, {"title": "다른 값"})
        assert r["ok"] is False and r["error"] == "conflict:title", r
        # 수정 — 정상 (큐 없으면 apply.submit 이 그 자리 처리)
        r = edit_preview("pv_a", {"title": "새 제목"}, {"title": "歌枠"})
        assert r["ok"], r
        assert list_preview()["items"][0]["title"] == "새 제목"
        assert edit_preview("pv_a", {"state": "out"}, {})["ok"] is False, "out 은 삭제 버튼으로"
        # 운영 설정 → ops
        assert set_log_level("detail")["ok"] and get_control()["log_level"] == "detail"
        assert os.path.exists(os.path.join(d, "ops", "control.json"))
        assert set_paused(True)["ok"] and get_control()["paused"] is True
        # 삭제 + 재등록 차단 (url 없으면 차단 생략)
        r = delete_preview("pv_a", True)
        assert r["ok"] and list_preview()["items"] == [], r
        # 이력
        h = list_history()
        assert [x["action"] for x in h][:3] == ["delete_preview", "set_paused", "set_log_level"], h
        assert os.path.exists(os.path.join(d, "ops", "history.json"))
        # 원문 투입 미리보기 — 개인 예고 유닛 미지정
        assert ingest_preview_raw("こんにちは", confirm=False)["ok"] is False
        assert undo("x")["ok"] is False
    print("[PASS] admin_api self-test: 읽기 · 충돌 · 수정 · 운영 설정(ops) · 삭제 · 이력")
