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

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

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

_PREVIEW_FIELD = {"title": "title", "state": "state", "scheduled_start": "date", "url": "url",
                  # (v4a) 합동 참여 멤버(주 레인 제외) · 회원 전용
                  "collab_with": "collab_with", "membership": "membership",
                  "title_ko": "title_ko"}  # (v4a) 한글 제목(빈 문자열 = 번역 없음)
_EDITABLE_STATES = ("announced", "upcoming", "watching", "live", "end")


def edit_preview(item_id: str, patch: dict, seen: dict) -> dict:
    """예고 항목 수정. patch 키: title · state · scheduled_start(ISO Z) · url · collab_with · membership 중 일부.
    seen = 폼을 열 때 본 같은 키의 값 — 현재 값과 다르면 conflict.
    collab_with = 주 레인(channel_key)을 뺀 참여 멤버 키 목록(빈 목록·None = 합동 아님)."""
    patch = {k: v for k, v in (patch or {}).items() if k in _PREVIEW_FIELD}
    if not patch:
        return _err("바꿀 필드가 없습니다")
    if "state" in patch and patch["state"] not in _EDITABLE_STATES:
        return _err(f"state 는 {', '.join(_EDITABLE_STATES)} 중 하나 (삭제는 삭제 버튼)")
    if "membership" in patch and not isinstance(patch["membership"], bool):
        return _err("membership 은 true/false")
    if "url" in patch:
        # (v4a) 팬 화면(render.js)이 이 값을 그대로 링크로 쓴다 — http(s) 주소만 받는다(javascript: 등 차단). 비우기는 허용
        u = (patch["url"] or "").strip() if isinstance(patch["url"], (str, type(None))) else None
        if u is None or (u and not re.match(r"^https?://[^\s]+$", u, re.IGNORECASE)):
            return _err("URL 은 http:// 또는 https:// 로 시작하는 주소여야 합니다")
        patch["url"] = u or None
    pv = list_preview()
    cur = next((it for it in pv.get("items", []) if it.get("id") == item_id), None)
    if cur is None:
        return _err("항목이 없습니다 (이미 사라짐)")
    if "collab_with" in patch:
        cw = patch["collab_with"] or []
        order = pv.get("channel_order") or []
        if not isinstance(cw, list) or any(k not in order or k == cur.get("channel_key") for k in cw):
            return _err("collab_with 는 주 레인을 뺀 멤버 키 목록")
        # 채널 순서대로 · 중복 제거. 빈 목록은 None(합동 아님)으로 저장 — make_item 기본값과 같게
        patch["collab_with"] = [k for k in order if k in cw] or None
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


def _suppress_until(vid: str | None) -> str | None:
    """(v4a) 이 영상의 재등록 차단(12h — `/del` terminate · 취소 감지 · 삭제 시 차단)이 살아 있으면 해제 시각(UTC ISO), 아니면 None.
    차단 목록은 url 로 적혀 있어 video_id 가 든 url 이면 형식(watch · live · youtu.be)과 무관하게 같은 영상으로 본다."""
    if not vid:
        return None
    from . import admin
    try:
        st, _ = _store().read_json("admin_state.json")
    except Exception:  # noqa: BLE001
        return None
    now = _now_iso()
    ends = [x.get("until") for x in (st or {}).get("suppress") or []
            if vid in (x.get("url") or "") and admin.suppressed({"suppress": [x]}, x.get("url"), now)]
    return max(ends) if ends else None


def _lift_suppress(vid: str | None) -> bool:
    """(v4a) 관리자가 그 영상 하나를 직접 다시 올릴 때 재등록 차단을 푼다 — 안 풀면 다음 수집이 바로 다시 뺀다.
    (공식 스케줄 원문을 통째로 넣는 경우엔 부르지 않는다 — 그 안의 취소된 영상까지 되살리지 않게.) 풀었으면 True."""
    if not _suppress_until(vid):
        return False
    try:
        gh = _store()
        st, sha = gh.read_json("admin_state.json")
        st = dict(st or {})
        st["suppress"] = [x for x in st.get("suppress") or [] if vid not in (x.get("url") or "")]
        gh.write_json("admin_state.json", st, prev_sha=sha, message=f"ops: suppress -= {vid} (관리자 재등록) {_now_iso()}")
        return True
    except Exception:  # noqa: BLE001
        log.warning("재등록 차단 해제 실패 %s", vid, exc_info=True)
        return False


def _suppress_note(t, vid: str | None) -> str:
    """미리보기 안내 — 재등록 차단 중이면 해제 시각과 확정 시 동작을 알린다."""
    until = _suppress_until(vid)
    return f" · ⚠ 재등록 차단 중(해제 {t._kst_label(until)}) — 확정하면 차단을 풀고 올립니다" if until else ""


def _change_plan(t, raw: str, host: str, now: str) -> dict:
    """(v4a) 「내용 감지를 통한 예고 수정」 — 글에서 방송 취소·변경을 감지하고 영향받는 예고를 고른다(미리보기용, 저장 안 함).
    반환 {"action": del|edit|none|failed, "when_iso", "candidates": [{"id","when","title","selected"}], "message"?}"""
    plan = t._detect_broadcast_change(raw, host, now, list_preview().get("items", []))
    if plan is None:
        return {"action": "failed", "when_iso": None, "candidates": [],
                "message": "판정에 실패했습니다(LLM 사용 불가 또는 응답 없음) — 예고는 바뀌지 않습니다"}
    sel = set(plan["target_ids"])
    return {"action": plan["action"], "when_iso": plan["when_iso"], "reason": plan.get("reason") or "",
            "candidates": [{"id": c["id"], "when": t._kst_label(c.get("scheduled_start")),
                            "title": c.get("title_ko") or c.get("title") or "", "selected": c["id"] in sel}
                           for c in plan["candidates"]]}


def _apply_change(host: str, action: str | None, ids: list | None, when_iso: str | None,
                  raw: str | None = None, tag: str | None = None) -> dict:
    """(v4a) 미리보기에서 관리자가 확인한 예고에만 취소·변경 적용. 취소 = `/del` terminate 와 동일
    (삭제 + 영상 URL 12h 재등록 차단 — 안 하면 다음 수집이 되살린다). 채널 자리표시 URL 은 차단하지 않는다.
    raw: 취소·변경을 일으킨 글 — 하나라도 적용되면 원문 보존(`broadcast_change`, 2026-10-01 운영자 결정)."""
    t = _t()
    out = {"action": action, "applied": [], "errors": []}
    if action not in ("del", "edit") or not ids:
        return out
    items = {i["id"]: i for i in list_preview().get("items", [])
             if i.get("channel_key") == host and i.get("state") in t.xtweet._ACTIVE_STATES}
    for iid in ids:
        it = items.get(iid)
        if it is None:
            out["errors"].append(f"{iid}: 이미 사라졌거나 대상이 아닙니다")
            continue
        label = f"{t._kst_label(it.get('scheduled_start'))} {it.get('title_ko') or it.get('title') or ''}".strip()
        if action == "del":
            r = delete_preview(iid, bool(it.get("url") and t.xtweet.YT_VIDEO_RE.search(it["url"])))
        elif when_iso:
            r = edit_preview(iid, {"scheduled_start": when_iso}, {})
        else:
            r = _err("변경할 시각이 없습니다")
        (out["applied"] if r.get("ok") else out["errors"]).append(label if r.get("ok") else f"{label}: {r.get('error')}")
    if out["applied"] and raw:
        t._preserve_raw("broadcast_change", raw, {"channel_key": host, "action": action, "via": "admin", "tag": tag,
                                                  "targets": out["applied"]}, _now_iso())
    return out


def ingest_preview_raw(raw: str, *, confirm: bool, channel_key: str | None = None, detect_change: bool = False,
                       change_ids: list | None = None, change_action: str | None = None,
                       change_when: str | None = None, tag: str | None = None, quote: str | None = None,
                       members: list | None = None, media: list | None = None) -> dict:
    """예고 원문 투입 + (v4a) 「내용 감지를 통한 예고 수정」. detect_change 는 호스트(channel_key)가 있을 때만.
    감지만 되고 예고로는 인식되지 않는 글(예: 휴방 안내)도 미리보기 · 확정이 된다(change_only)."""
    if not (detect_change and channel_key):
        return _ingest_preview_raw_core(raw, confirm=confirm, channel_key=channel_key, tag=tag, quote=quote,
                                        members=members, media=media)
    t = _t()
    if not confirm:
        plan = _change_plan(t, (raw or "").strip(), channel_key, _now_iso())
        res = _ingest_preview_raw_core(raw, confirm=False, channel_key=channel_key, tag=tag, quote=quote,
                                       members=members, media=media)
        if res.get("ok"):
            res["change"] = plan
            return res
        if plan["action"] in ("del", "edit"):
            return {"ok": True, "preview": [], "change": plan,
                    "note": "예고 글로는 인식되지 않았지만 방송 취소·변경으로 감지되었습니다"}
        return res
    res = _ingest_preview_raw_core(raw, confirm=True, channel_key=channel_key, tag=tag, quote=quote,
                                   members=members, media=media)
    recog_fail = (not res.get("ok")) and "인식되지 않았습니다" in (res.get("error") or "")
    if res.get("ok") or (recog_fail and change_ids):
        ch = _apply_change(channel_key, change_action, change_ids, change_when, raw=raw, tag=tag)
        if recog_fail:
            res = _ok({"change_only": True})
        res["change"] = ch
    return res


def _video_preview(t, chs: dict, vid: str, author_key: str | None, now: str,
                   members: list | None = None) -> tuple[dict | None, str, str | None]:
    """(v4a) 유튜브 영상을 `videos.list` 로 확인해 preview 항목을 미리 만든다(저장 안 함). 반환 (항목 | None, 안내, next_check_at).
    항목의 상태는 API 가 알려 주는 실제 상태(upcoming · watching · live)라 확정하면 그 상태로 바로 올라간다.
    members: 그룹 공식 채널 영상의 **참여 멤버**(관리자가 고른 것) — 주면 5인 팬아웃 대신 그 멤버만 올린다
    (1명이면 그 멤버의 일반 예고, 2명 이상이면 host="group" 합동)."""
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key or t.YouTubeClient is None:
        return None, "YouTube API 키가 없어 영상을 확인하지 못했습니다", None
    try:
        info = t.YouTubeClient(api_key).videos_list([vid]).get(vid)
    except Exception:  # noqa: BLE001
        log.warning("영상 미리보기: videos.list 실패", exc_info=True)
        return None, "영상 조회에 실패했습니다(잠시 뒤 다시 시도)", None
    if info is None or not info.channel_id:
        return None, "영상을 API 로 확인하지 못했습니다(회원 전용 · 비공개 · 삭제 등)", None
    if t.preview_build.is_group_release(info, chs):
        return None, "그룹 채널의 프리미어 공개(녹화된 노래 · 뮤비 · 커버 등) 영상이라 방송 예고로 올리지 않습니다", None
    host_key, host, collab = t.xtweet.resolve_url_host(info.channel_id, author_key, chs)
    if host_key is None:
        return None, "유메미타 멤버 · 그룹 공식 채널의 영상이 아닙니다", None
    picked = False
    if host == "group" and members is not None:
        order = chs.get("channel_order") or []
        sel = [k for k in order if k in members]
        if sel:
            host_key, collab = sel[0], (sel[1:] or None)
            host = "group" if collab else None
            picked = True
    if host is None and not picked:
        guests = t.xtweet.find_guest_members(chs, host_key, info.title)
        collab = [*(collab or []), *[g for g in guests if g not in (collab or [])]] or None
    item, next_check = t.xtweet.build_item_from_video(info, channel_key=host_key, host=host, collab_with=collab,
                                                      now_iso=now)
    label = {"live": "라이브 중", "watching": "시작 임박", "upcoming": "예정", "end": "종료"}.get(
        item.get("state"), item.get("state"))
    tail = "선택한 참여 멤버로 올라갑니다" if picked else "합동 여부는 확정할 때 LLM 이 한 번 더 확인합니다"
    return item, f"영상 확인됨 — 확정하면 「{label}」 상태로 바로 올라갑니다 · {tail}{_suppress_note(t, vid)}", next_check


def _group_choice(t, vid: str, item: dict, media: list | None, text: str | None = None) -> dict:
    """(v4a) 그룹 공식 채널 영상 = 5인 합동으로 자동 팬아웃하지 않는다 — 프론트가 참여 멤버 선택 팝업을 띄우게 응답한다.
    트윗의 첨부 이미지가 있으면 비전 OCR 로 읽은 멤버를 `suggested` 로 미리 제안한다(관리자가 확인 · 수정).
    이미 같은 영상이 등록돼 있으면 새로 만들지 않는다(예고 탭 수정에서 합동 멤버를 바꾼다)."""
    existing = next((i for i in list_preview().get("items", []) if i.get("video_id") == vid), None)
    if existing is not None:
        names = "·".join([existing.get("channel_key"), *(existing.get("collab_with") or [])])
        return _err(f"이미 등록된 영상입니다({names}) — 참여 멤버를 바꾸려면 예고 탭의 수정을 쓰세요")
    # (v4a) 제안 순서 = 글의 근거(정식 이름 · 全員 등 인원 표현) → 영상 제목의 정식 이름 → 첨부 이미지 OCR
    suggested, ocr = t.xrelay.members_evidence(text)
    if not suggested:
        suggested, ocr = t.xrelay.members_evidence(item.get("title"))
    if not suggested:
        suggested, ocr = t._ocr_cast_keys(media)
    return {"ok": True, "choose_members": True, "preview": [], "suggested": suggested or [], "ocr": ocr,
            "video": {"video_id": vid, "title": item.get("title"), "scheduled_start": item.get("scheduled_start"),
                      "state": item.get("state")},
            "note": "그룹 공식 채널 영상 — 참여 멤버를 골라야 합니다"}


def _commit_group_video(item: dict, vid: str, next_check: str | None, now: str) -> dict:
    """(v4a) 관리자가 고른 참여 멤버로 그룹 영상을 직접 커밋(합동 LLM 확인 · 5인 팬아웃 경로를 타지 않는다)."""
    res = _submit("url_confirmed_commit", {"video_id": vid, "new_item": item, "next_check_at": next_check,
                                           "host_key": item["channel_key"], "now_iso": now, "via": "ops"})
    if res["ok"]:
        _lift_suppress(vid)
        apply.enqueue_reconcile(video_id=vid)
    return _record("ingest_preview", item["channel_key"], f"영상 URL {vid} · 선택 멤버", res)


def _ingest_video_url(t, chs: dict, vid: str, url: str, confirm: bool, members: list | None = None) -> dict:
    """(v4a) 자동 · 예고 — 유튜브 영상 URL 만으로 예고 등록. 호스트 = 영상 채널(멤버 채널 · 그룹 공식만),
    제목 · 시각 · 상태 = API. 작성자 트윗이 없으므로 외부 채널 영상은 받지 않는다.

    **그룹 공식 채널 영상은 5인 합동으로 자동 팬아웃하지 않는다** — 참여 멤버를 관리자가 골라야 한다.
    `members` 없이 부르면 {"choose_members": True, "video": ...} 만 돌려줘 프론트가 선택 팝업을 띄우고,
    고른 멤버(`members`)로 다시 부르면 그 멤버만 올린다(1명 = 그 멤버의 일반 예고, 2명 이상 = host="group" 합동).
    이미 같은 영상이 등록돼 있으면 새로 만들지 않는다(예고 탭 수정에서 합동 멤버를 바꾼다)."""
    now = _now_iso()
    item, note, next_check = _video_preview(t, chs, vid, None, now, members)
    if item is None:
        return _err(note + " — 수동 입력을 쓰세요" if "확인하지 못" in note or "실패" in note else note)
    # 그룹 채널 영상인지는 members 를 안 준 미리보기 항목의 host 로 판정한다
    if members is None and item.get("host") == "group":
        return _group_choice(t, vid, item, None)          # 영상 URL 만 — 이미지가 없으니 제안 없이 선택 팝업
    if not confirm:
        return {"ok": True, "preview": [item], "note": note}
    if members is not None:
        return _commit_group_video(item, vid, next_check, now)
    try:
        done = t._maybe_url_confirmed_schedule(_store(), url, item["channel_key"], now, chs, via="ops")
    except Exception as e:  # noqa: BLE001
        return _record("ingest_preview", item["channel_key"], f"영상 URL {vid}", _err(str(e)[:250]))
    if not done:
        return _err("영상을 확정하지 못했습니다 — 수동 입력을 쓰세요")
    _lift_suppress(vid)
    apply.enqueue_reconcile(video_id=vid)
    return _record("ingest_preview", item["channel_key"], f"영상 URL {vid}", _ok({"path": "url_confirmed"}))


def ingest_preview_url(url: str, *, confirm: bool, force_unit: str | None = None, detect_change: bool = False,
                       change_ids: list | None = None, change_action: str | None = None,
                       change_when: str | None = None, members: list | None = None) -> dict:
    """(v4a) 자동 · 예고 — URL 하나로 예고 등록.
    · 트윗 URL: 작성자(X 핸들)가 멤버면 그 호스트의 개인 예고, 그룹 공식(@BDP_yumemita)이면 일일 스케줄 서식,
      그 밖이면 되묻는다(`confirm_needed`, `force_unit` 으로 붙일 호스트를 골라 다시). 본문 · 인용 · 영상 URL 은 원문 투입과 같은 경로.
    · 유튜브 영상 URL: 멤버 · 그룹 채널 영상이면 API 가 알려 주는 실제 상태(예정 · 임박 · 라이브)로 바로 올린다.
    detect_change(내용 감지를 통한 예고 수정)는 멤버 트윗 URL 에서만 의미가 있다."""
    from . import vxtwitter
    t = _t()
    chs = t._load_channels_config()
    url = (url or "").strip()
    m = _TWEET_URL_RE.match(url)
    if not m:
        ym = t.xtweet.YT_VIDEO_RE.search(url) or re.search(r"youtu\.be/([\w-]{11})(?![\w-])", url)
        if not ym:
            return _err("트윗 URL 또는 YouTube 영상 URL 이 아닙니다")
        return _ingest_video_url(t, chs, ym.group(1), url, confirm, members)
    tid = m.group(2)
    j = vxtwitter.fetch_tweet(tid)
    if not j:
        return _err("트윗을 가져오지 못했습니다 — 비공개이거나 삭제됐거나 조회 서비스가 응답하지 않습니다")
    ex = vxtwitter.extract(j)
    author = (ex.get("author") or m.group(1) or "").lstrip("@")
    text = ex.get("text") or ""
    channels = chs.get("channels") or {}
    if any(v.get("is_group") and (v.get("handle") or "").lower() == author.lower() for v in channels.values()):
        grp = _official_group_video(t, text, confirm=confirm, members=members, media=ex.get("media"))
        if grp is not None:
            return grp
        return ingest_preview_raw(text, confirm=confirm)          # 공식 스케줄 서식(호스트 없음)
    natural = next((k for k, v in channels.items()
                    if not v.get("is_group") and (v.get("handle") or "").lower() == author.lower()), None)
    unit = natural
    if unit is None:
        if not force_unit:
            return {"ok": False, "confirm_needed": "not_member", "author": author,
                    "message": "이 트윗은 유메미타 멤버가 아닙니다. 그래도 넣을까요?"}
        if not _host_ok(chs, force_unit):
            return _err("붙일 호스트를 고르세요")
        unit = force_unit
    res = ingest_preview_raw(text, confirm=confirm, channel_key=unit, tag=f"tweet-{tid}",
                             quote=(ex.get("qrt") or {}).get("text"), detect_change=detect_change,
                             change_ids=change_ids, change_action=change_action, change_when=change_when,
                             members=members, media=ex.get("media"))
    if not confirm and res.get("ok"):
        res["author"], res["unit"], res["forced"] = author, unit, natural is None
    return res


def _commit_group_rows(t, rows: list[dict], now: str, desc: str) -> dict:
    """(v4a) 참여 멤버가 정해진 그룹 영상 행을 반영 — 영상 즉시 확인(D13) → 예고 반영 → 확인 대기에서 뺌 → 영상 확인 적재."""
    rows, vids = t._confirm_rows_with_videos(rows, now)
    res = _submit("merge_rows", {"rows": rows, "now_iso": now, "message": f"data: admin 그룹 영상 {now}",
                                 "action": f"admin 그룹 영상 {desc}"[:80]})
    if res.get("ok"):
        done = [r.get("video_id") for r in rows if r.get("video_id")]
        if done:
            _submit("group_pending", {"op": "remove", "now_iso": now, "video_ids": done})
        for v in vids:
            apply.enqueue_reconcile(video_id=v)
    return _record("ingest_preview", "group", desc, res)


def _official_group_video(t, text: str, *, confirm: bool, members: list | None, media: list | None) -> dict | None:
    """(v4a) 공식 트윗 URL 투입 중 그룹 영상 처리. 해당 없으면 None(일반 공식 스케줄 경로로).
    · 참여 멤버 근거(이름 · 全員 등)가 없는 그룹 방송 글 → 선택 팝업(첨부 이미지 OCR 제안). 고른 멤버로 미리보기 · 확정.
    · 글이 「확인 대기」 중인 영상 URL 을 담고 근거가 있으면 → 그 멤버로 확정(같은 영상 URL 근거)."""
    now = _now_iso()
    registered = {i.get("video_id") for i in list_preview().get("items", []) if i.get("video_id")}
    if t.xrelay.parse(text, now):
        return None                                   # 근거가 있는 서식 — 일반 경로
    cand = next((c for c in t.xrelay.parse_pending(text, now)), None)
    if cand is None:
        pending = t._group_pending_items(_store())
        ev, basis = t.xrelay.members_evidence(text)
        vid = next((m.group(1) for m in t.xrelay.YT_VIDEO_RE.finditer(t.xrelay.normalize(text))
                    if m.group(1) in pending and m.group(1) not in registered), None)
        if vid is None or not ev:
            return None
        row = t.xrelay.group_row(pending[vid], ev, now)
        if not confirm:
            return {"ok": True, "preview": [row],
                    "note": f"확인 대기 중인 그룹 영상 — 이 글의 근거({'인원 표현' if basis == 'count' else '이름'})로 확정됩니다"}
        return _commit_group_rows(t, [row], now, f"{vid} · 같은 영상 URL 근거")
    vid = cand["video_id"]
    if vid in registered:
        return _err("이미 등록된 영상입니다 — 참여 멤버를 바꾸려면 예고 탭의 수정을 쓰세요")
    if members is None:
        suggested, ocr = t._ocr_cast_keys(media)
        return {"ok": True, "choose_members": True, "preview": [], "suggested": suggested, "ocr": ocr,
                "video": {"video_id": vid, "title": cand.get("title"), "scheduled_start": cand.get("scheduled_start"),
                          "state": "announced"},
                "note": "공식 글에 참여 멤버 근거(이름 · 全員 등 인원 표현)가 없습니다 — 참여 멤버를 고르세요"}
    sel = [k for k in (t._load_channels_config().get("channel_order") or []) if k in members]
    if not sel:
        return _err("참여 멤버를 한 명 이상 고르세요")
    row = t.xrelay.group_row(cand, sel, now)
    if not confirm:
        return {"ok": True, "preview": [row], "note": "선택한 참여 멤버로 올라갑니다"}
    return _commit_group_rows(t, [row], now, f"{vid} · 선택 멤버")


def list_llm_actions(limit: int = 300) -> dict:
    """(v4a) LLM 판단 기록(최신 먼저) — 작업 탭 「LLM 판단」 필터 · 되돌리기."""
    items = _t()._llm_actions_read(_store())
    return {"items": list(reversed(items))[: max(1, int(limit or 300))]}


def undo_llm_action(action_id: str) -> dict:
    """(v4a) LLM 판단 되돌리기 — 그때 바뀐 항목만 되돌린다(그 뒤 다른 이유로 바뀐 항목은 건너뜀). 되살린 영상은 곧바로 확인 적재."""
    res = _submit("llm_action", {"op": "undo", "now_iso": _now_iso(), "action_id": action_id})
    if res.get("ok") and (res.get("result") or {}).get("error"):
        res = _err(res["result"]["error"])
    elif res.get("ok"):
        for v in (res.get("result") or {}).get("restored_video_ids") or []:
            apply.enqueue_reconcile(video_id=v)
        if not (res.get("result") or {}).get("applied"):
            res = dict(res, ok=False, error="되돌릴 것이 없습니다 — " + "; ".join((res.get("result") or {}).get("skipped") or []))
    return _record("undo_llm_action", action_id, "; ".join((res.get("result") or {}).get("applied") or []), res)


def list_group_pending() -> dict:
    """(v4a) 그룹 영상 「참여 멤버 확인 대기」 목록 — 근거가 없어 예고에 올리지 않은 영상."""
    t = _t()
    items = sorted(t._group_pending_items(_store()).values(), key=lambda e: e.get("scheduled_start") or "")
    return {"items": items}


def resolve_group_pending(video_id: str, members: list) -> dict:
    """(v4a) 확인 대기 영상을 관리자가 고른 참여 멤버로 예고에 올린다(1명 = 그 멤버 단독, 2명 이상 = 합동)."""
    t = _t()
    entry = t._group_pending_items(_store()).get(video_id or "")
    if entry is None:
        return _err("확인 대기 목록에 없습니다 (이미 확정됐거나 지났음)")
    sel = [k for k in (t._load_channels_config().get("channel_order") or []) if k in (members or [])]
    if not sel:
        return _err("참여 멤버를 한 명 이상 고르세요")
    now = _now_iso()
    if any(i.get("video_id") == video_id for i in list_preview().get("items", [])):
        _submit("group_pending", {"op": "remove", "now_iso": now, "video_ids": [video_id]})
        return _err("이미 예고에 있는 영상입니다 — 대기에서만 뺐습니다. 참여 멤버는 예고 탭 수정으로 바꾸세요")
    return _commit_group_rows(t, [t.xrelay.group_row(entry, sel, now)], now, f"{video_id} · 확인 대기 확정")


def dismiss_group_pending(video_id: str) -> dict:
    """(v4a) 확인 대기에서 뺀다(방송이 아니거나 올리지 않을 영상)."""
    res = _submit("group_pending", {"op": "remove", "now_iso": _now_iso(), "video_ids": [video_id]})
    if res.get("ok") and not (res.get("result") or {}).get("removed"):
        res = _err("확인 대기 목록에 없습니다")
    return _record("dismiss_group_pending", video_id, "", res)


def _ingest_preview_raw_core(raw: str, *, confirm: bool, channel_key: str | None = None,
                             tag: str | None = None, quote: str | None = None,
                             members: list | None = None, media: list | None = None) -> dict:
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
    # 영상 URL 은 본문 · 인용한 트윗 어느 쪽에 있어도 찾는다(v3.8.5)
    ym = t.xtweet.YT_VIDEO_RE.search(t.xtweet.normalize(raw + ("\n" + quote if quote else "")))
    vnote = ""
    if ym:
        vid = ym.group(1)
        # 확정(_maybe_url_confirmed_schedule)과 같게 — 영상 URL 이 본문엔 없고 인용한 공식 일일 스케줄에만 있으면
        # 작성자를 게스트로 넣지 않는다(2026-10-01 운영자 결정). 미리보기 단계의 게스트도 그에 맞춘다
        url_only_in_official_quote = (t.xrelay is not None and t.xrelay.is_daily_schedule(quote)
                                      and not t.xrelay.YT_VIDEO_RE.search(t.xrelay.normalize(raw)))
        guest_author = None if url_only_in_official_quote else channel_key
        if not confirm:
            item, vnote, _nc = _video_preview(t, chs, vid, guest_author, now, members)
            if item is not None:
                if members is None and item.get("host") == "group":
                    # 5인 팬아웃 금지 — 글 · 제목의 근거 또는 이미지 OCR 로 제안 + 선택 팝업
                    return _group_choice(t, vid, item, media, raw + ("\n" + quote if quote else ""))
                return {"ok": True, "preview": [item], "note": vnote}
        else:
            gitem, _gn, gnc = _video_preview(t, chs, vid, guest_author, now, members)
            if gitem is not None and gitem.get("host") == "group" and members is None:
                return _err("그룹 공식 채널 영상은 참여 멤버를 골라야 합니다 — 미리보기에서 멤버를 고르세요")
            if gitem is not None and members is not None:
                return _commit_group_video(gitem, vid, gnc, now)
            try:
                done = t._maybe_url_confirmed_schedule(gh, raw, channel_key, now, chs, via="ops", quote=quote)
            except Exception as e:  # noqa: BLE001
                return _record("ingest_preview", channel_key, "개인 예고(영상 URL)", _err(str(e)[:250]))
            if done:
                t._preserve_raw("personal_schedule_url", raw, {"channel_key": channel_key, "via": "admin"}, now)
                _lift_suppress(vid)
                apply.enqueue_reconcile(video_id=vid)
                return _record("ingest_preview", channel_key, "개인 예고(영상 URL)", _ok({"path": "url_confirmed"}))
            # 영상을 API 로 확정하지 못함(회원 전용 · 삭제 등) — 본문 파싱으로 최소한 등록(v3.6 과 같은 폴백)
            vnote = "영상을 API 로 확인하지 못해 본문 파싱으로 등록합니다"

    row = t.xtweet.parse_schedule(raw, channel_key=channel_key, tag=tag, now_iso=now)
    if not row:
        return _err("예고로 인식되지 않았습니다 (配信 계열 키워드 + 미래 날짜 필요)")
    row = dict(row, source="manual", info_source="personal")
    if not confirm:
        return {"ok": True, "preview": row,
                "note": (vnote + " · " if vnote else "") + "개인 예고 — 운영자 확정이라 LLM 최종 확인은 생략"}
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


_TWEET_URL_RE = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([^/?#\s]+)/status(?:es)?/(\d{6,25})")
TWEET_TOO_OLD_MSG = "게시된지 48시간이 지난 트윗입니다."


def _tweet_too_old(tid: str, now: str) -> dict | None:
    """(v4a, 10-01 운영자 결정) 트윗 수명 = X 게시 시각 + 48h — 이미 지난 트윗은 넣어도 팬 화면에 안 보이므로 받지 않는다.
    관리 페이지는 `too_old` 를 보고 경고창을 띄운다. 게시 시각을 못 얻으면(id 형식 밖) 막지 않는다."""
    from . import xtweet
    posted = xtweet._parse_iso(xtweet.snowflake_iso(tid))
    cur = xtweet._parse_iso(now)
    if posted and cur and cur >= posted + timedelta(hours=xtweet.TTL_HOURS):
        return dict(_err(TWEET_TOO_OLD_MSG), too_old=True)
    return None


def ingest_tweet_url(url: str, *, confirm: bool, force_unit: str | None = None, detect_change: bool = False,
                     change_ids: list | None = None, change_action: str | None = None,
                     change_when: str | None = None, with_preview: bool = False,
                     members: list | None = None) -> dict:
    """개인 트윗 URL 투입. URL 만 받아 작성자(호스트) 판별 · 본문 · 미디어 · 번역을 자동으로 채운다.

    작성자 = vxtwitter/fxtwitter 응답의 X 핸들(URL 의 핸들은 `i` 일 수 있어 응답을 우선) — `config/channels.json`
    의 `handle`(X 핸들과 같다, 운영자 확인 2026-09-30)과 대소문자 무시로 맞춘다.
    멤버가 아니면 {"ok": False, "confirm_needed": "not_member", "author", "message"} — 관리자가 `force_unit`(붙일
    호스트)을 골라 다시 부르면 그 호스트 레인에 넣는다.
    confirm=False → 반영 없이 미리보기 {"ok", "preview": {"parsed", "text_ko", "unit", "author"}}."""
    from . import vxtwitter
    m = _TWEET_URL_RE.match((url or "").strip())
    if not m:
        return _err("트윗 URL 이 아닙니다 (https://x.com/…/status/숫자)")
    tid = m.group(2)
    old = _tweet_too_old(tid, _now_iso())      # 조회 전에 — 게시 시각은 id 만으로 안다
    if old:
        return old
    j = vxtwitter.fetch_tweet(tid)
    if not j:
        return _err("트윗을 가져오지 못했습니다 — 비공개이거나 삭제됐거나 조회 서비스가 응답하지 않습니다")
    ex = vxtwitter.extract(j)
    author = (ex.get("author") or m.group(1) or "").lstrip("@")
    t = _t()
    chs = t._load_channels_config().get("channels") or {}
    natural = next((k for k, v in chs.items()
                    if not v.get("is_group") and (v.get("handle") or "").lower() == author.lower()), None)
    unit = natural
    if unit is None:
        if not force_unit:
            return {"ok": False, "confirm_needed": "not_member", "author": author,
                    "message": "이 트윗은 유메미타 멤버가 아닙니다. 그래도 넣을까요?"}
        if force_unit not in chs or chs[force_unit].get("is_group"):
            return _err("붙일 호스트를 고르세요")
        unit = force_unit
    now = _now_iso()
    name = chs[unit].get("name") or unit
    prepared = t._prepare_personal_tweet(ex.get("text") or "", title=name, tag=f"tweet-{tid}", channel_key=unit,
                                         now_iso=now, vx_extract=ex, gh=_store())
    if not prepared:
        return _err("트윗으로 인식되지 않았습니다 (리트윗 · 빈 본문 등)")
    if not confirm:
        out = {"ok": True, "preview": {"parsed": prepared.get("parsed"), "text_ko": prepared.get("text_ko"),
                                       "unit": unit, "author": author, "forced": natural is None}}
        if detect_change:
            out["change"] = _change_plan(t, ex.get("text") or "", unit, now)
        if with_preview:      # 트윗과 예고를 같이 올릴 때 — 같은 글에서 예고도 만들어 미리 보여 준다
            sch = ingest_preview_raw(ex.get("text") or "", confirm=False, channel_key=unit, tag=f"tweet-{tid}",
                                     quote=(ex.get("qrt") or {}).get("text"), members=members, media=ex.get("media"))
            if sch.get("choose_members"):
                return sch          # 그룹 공식 채널 영상 — 참여 멤버부터 고른 뒤(팝업) 트윗 · 예고를 함께 미리 본다
            out["schedule"] = ({"ok": True, "preview": sch.get("preview"), "note": sch.get("note")} if sch.get("ok")
                               else {"ok": False, "error": sch.get("error")})
        return out
    res = _submit("personal_tweet", {"prepared": prepared, "channel_key": unit, "now_iso": now, "via": "ops"})
    res = _record("ingest_tweet", unit, f"tweet-{tid}", res)
    if with_preview and res.get("ok"):
        sres = ingest_preview_raw(ex.get("text") or "", confirm=True, channel_key=unit, tag=f"tweet-{tid}",
                                  quote=(ex.get("qrt") or {}).get("text"), members=members, media=ex.get("media"))
        res["schedule"] = {"ok": bool(sres.get("ok")), "error": sres.get("error")}
    if detect_change and res.get("ok"):
        res["change"] = _apply_change(unit, change_action, change_ids, change_when, raw=ex.get("text"), tag=f"tweet-{tid}")
    return res


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
_NOTICE_CATS = ("live", "release", "platform", "etc")


def _host_ok(chs: dict, key: str | None) -> bool:
    v = (chs.get("channels") or {}).get(key or "")
    return bool(v) and not v.get("is_group")


def ingest_preview_manual(*, host: str, date: str, title: str, confirm: bool, collab_with: list | None = None,
                          time: str | None = None, time_tbd: bool = False, membership: bool = False,
                          title_ko: str = "", url: str = "") -> dict:
    """(v4a) 예고 수동 입력 — 관리자가 호스트 · 합동 · 시각 · 제목을 직접 정한다.

    시각은 KST 로 받아 UTC 로 저장(time_tbd 면 `<날짜>T00:00:00Z` 자리표시, 계약 §2). 제목은 title_manual 로
    보호돼 API 제목 · 자동 번역이 덮지 않는다(한글을 비우면 needs_tl 로 자동 번역). 같은 방송이 이미 있으면
    입력값을 그 항목에 덮어쓰고(상태 · video_id 보존) 미리보기에 알린다. 유튜브 URL 이 있으면 확정 뒤 그 영상을 즉시 확인."""
    t = _t()
    chs = t._load_channels_config()
    order = chs.get("channel_order") or []
    title, title_ko, url = (title or "").strip(), (title_ko or "").strip(), (url or "").strip()
    if not _host_ok(chs, host):
        return _err("호스트를 고르세요")
    cw = [k for k in order if k in (collab_with or []) and k != host]
    if any(k not in order for k in (collab_with or [])):
        return _err("합동 멤버 키가 올바르지 않습니다")
    if not _DATE_RE.match(date or ""):
        return _err("방송 날짜를 입력하세요")
    if not time_tbd and not _TIME_RE.match(time or ""):
        return _err("시작 시각을 입력하세요 (모르면 「시각 미정」을 체크)")
    if not title:
        return _err("원문 제목을 입력하세요")
    vid = None
    if url:
        m = t.xtweet.YT_VIDEO_RE.search(url) or re.search(r"youtu\.be/([\w-]{11})(?![\w-])", url)
        if not m:
            return _err("유튜브 영상 URL 이 아닙니다")
        vid = m.group(1)
        url = f"https://www.youtube.com/watch?v={vid}"
    try:
        start_z = (f"{date}T00:00:00Z" if time_tbd
                   else t.xtweet._start_from(date, time).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return _err("날짜 · 시각 형식이 올바르지 않습니다")
    now = _now_iso()
    handle = chs["channels"][host].get("handle") or ""
    item = t.preview_mod.make_item(
        channel_key=host, state="announced", source="manual", now_iso=now,
        video_id=vid, title=title, title_ko=title_ko or None,
        url=url or (f"https://www.youtube.com/@{handle}" if handle else None),
        scheduled_start=start_z, time_tbd=bool(time_tbd), membership=bool(membership),
        collab_with=cw or None, kind="collab" if cw else None,
        info_source="manual", info_at=now)
    # make_item 의 id salt 는 url 을 먼저 쓰는데 영상 없는 수동 예고의 url 은 채널 페이지라 같다 — 같은 초에 같은 호스트로
    # 만든 두 예고의 id 가 겹쳐 삭제 · 수정 · 취소 판정이 엉뚱한 항목에 적용됐다. 시각 + 제목으로 구분한다
    item["id"] = t.preview_mod.new_id(host, item["first_seen"], f"{start_z}|{title}|{vid or ''}")
    item["title_manual"] = True
    item["needs_tl"] = not title_ko
    probe = dict(item, url=item.get("url") if vid else None)      # 채널 자리표시 url 로는 매칭하지 않는다
    matched = t.preview_mod.match_item(list_preview().get("items", []), probe)
    if not confirm:
        note = ("같은 방송이 이미 있어 그 항목에 합쳐집니다 — 상태 · 영상 연결은 유지하고 입력한 값만 덮어씁니다"
                if matched else "새 예고로 추가됩니다")
        if vid:
            note += " · 확정 뒤 영상 URL 을 바로 확인합니다" + _suppress_note(t, vid)
        return {"ok": True, "preview": item, "note": note,
                "merge": ({"id": matched.get("id"), "title": matched.get("title"),
                           "scheduled_start": matched.get("scheduled_start")} if matched else None)}
    res = _submit("manual_preview", {"item": item, "now_iso": now})
    if res["ok"] and vid:
        _lift_suppress(vid)
        apply.enqueue_reconcile(video_id=vid)
    return _record("ingest_preview", host, f"수동 · {title[:40]}", res)


def ingest_notice_manual(*, title: str, confirm: bool, date: str | None = None, category: str = "etc",
                         url: str = "", title_ko: str = "") -> dict:
    """(v4a) 소식 수동 입력 — 제목 · 날짜 · 분류 · URL 을 직접 넣는다. 한글 제목을 비우면 자동 번역(needs_tl).
    미리보기 형태는 원문 투입과 같다({"parsed","tl","dup_id"})."""
    import hashlib
    t = _t()
    title, title_ko, url = (title or "").strip(), (title_ko or "").strip(), (url or "").strip()
    if not title:
        return _err("원문 제목을 입력하세요")
    if date and not _DATE_RE.match(date):
        return _err("날짜 형식이 올바르지 않습니다")
    if category not in _NOTICE_CATS:
        return _err("분류가 올바르지 않습니다")
    if url and not re.match(r"^https?://", url):
        return _err("URL 은 http(s):// 로 시작해야 합니다")
    now = _now_iso()
    xn = t.xnotice
    site, site_url, anchor_a = xn._site_url_anchor(url) if url else (None, None, None)
    now_jst = datetime.now(xn.JST)
    parsed = {
        "id": "m" + hashlib.sha1(f"{category}|{date}|{title}".encode("utf-8")).hexdigest()[:15],
        "category": category, "title": title, "title_raw": title, "title_ko": title_ko or None,
        "body_for_llm": title, "body_raw": title, "date": date or None, "time": None, "deadline": False,
        "site": site, "url": site_url or url or None, "tweet_url": None, "src_handle": None, "is_recap": False,
        "anchor_a": anchor_a, "anchor_b": None, "title_slug": xn._title_slug(title),
        "expires_at": xn._expires_at(date, None, now, now_jst),
    }
    gh = _store()
    dup_id = None
    try:
        import copy
        prev, _ = gh.read_json(t._NOTICES_PATH)
        arch, _ = gh.read_json(t._NOTICE_ARCHIVE_PATH)
        prev = prev or t.notices.default_notices()
        arch = arch or t.notices.default_archive()
        _, _, changed, mode = t.notices.merge_notice(copy.deepcopy(prev), copy.deepcopy(parsed), now,
                                                     archive=copy.deepcopy(arch))
        if changed and mode == "added":
            dup_id = t._inline_notice_dup_check(parsed, prev)
    except Exception:  # noqa: BLE001
        log.warning("수동 소식: 중복 확인 실패", exc_info=True)
    prepared = {"parsed": parsed, "tl": ({"title_ja": title, "title_ko": title_ko} if title_ko else None),
                "dup_id": dup_id}
    if not confirm:
        return {"ok": True, "preview": {"parsed": parsed, "tl": prepared["tl"], "dup_id": dup_id},
                "note": "수동 입력 — 한글 제목을 비우면 저장 후 자동 번역됩니다"}
    apply.submit("notice_sweep", {"now_iso": now}, wait=True)
    res = _submit("apply_notice", {"prepared": prepared, "now_iso": now})
    return _record("ingest_notice", "notice", f"수동 · {title[:40]}", res)


def ingest_tweet_manual(*, url: str, host: str, text: str, confirm: bool, text_ko: str = "",
                        detect_change: bool = False, change_ids: list | None = None,
                        change_action: str | None = None, change_when: str | None = None) -> dict:
    """(v4a) 트윗 수동 입력 — 트윗 URL(X 카드) + 호스트 + 원문 + (선택)한글 번역. 번역을 비우면 자동 번역.
    작성자 판별은 하지 않는다(호스트는 관리자가 고른다). 미디어 · 인용 트윗은 URL 로 조회해 채운다."""
    t = _t()
    chs = t._load_channels_config()
    if not _host_ok(chs, host):
        return _err("호스트를 고르세요")
    m = _TWEET_URL_RE.match((url or "").strip())
    if not m:
        return _err("트윗 URL 이 아닙니다 (https://x.com/…/status/숫자)")
    old = _tweet_too_old(m.group(2), _now_iso())
    if old:
        return old
    text, text_ko = (text or "").strip(), (text_ko or "").strip()
    if not text:
        return _err("원문을 입력하세요")
    now = _now_iso()
    name = chs["channels"][host].get("name") or host
    prepared = t._prepare_personal_tweet(text, title=name, tag=f"tweet-{m.group(2)}", channel_key=host,
                                         now_iso=now, gh=_store(), text_ko_override=text_ko or None)
    if not prepared:
        return _err("트윗으로 인식되지 않았습니다 (리트윗 형식 등)")
    if not confirm:
        out = {"ok": True, "preview": {"parsed": prepared.get("parsed"), "text_ko": prepared.get("text_ko"),
                                       "unit": host, "author": None, "forced": False}}
        if detect_change:
            out["change"] = _change_plan(t, text, host, now)
        return out
    res = _submit("personal_tweet", {"prepared": prepared, "channel_key": host, "now_iso": now, "via": "ops"})
    res = _record("ingest_tweet", host, f"수동 · tweet-{m.group(2)}", res)
    if detect_change and res.get("ok"):
        res["change"] = _apply_change(host, change_action, change_ids, change_when, raw=text, tag=f"tweet-{m.group(2)}")
    return res


def edit_notice(nid: str, patch: dict) -> dict:
    """소식 수정. patch 키: title · title_ko · date(YYYY-MM-DD) · url 중 일부.

    (v4a) 텔레그램 /notice-edit 과 같게 파생값을 다시 계산한다(`_notice_edit_finalize` — 날짜 → expires_at,
    URL → site · anchor_a, 제목 → title_slug). 전엔 값만 덮어써 날짜를 바꿔도 옛 날짜 기준으로 만료됐다.
    제목(원문·한글)을 고치면 자동 번역을 끈다(needs_tl=False). 한글 빈 문자열 = 번역 없음."""
    patch = {k: v for k, v in (patch or {}).items() if k in ("title", "title_ko", "date", "url")}
    if not patch:
        return _err("바꿀 필드가 없습니다")
    row = next((n for n in list_notices().get("notices", []) if n.get("id") == nid), None)
    if row is None:
        return _err("소식이 없습니다")
    t = _t()
    full = t._notice_edit_finalize({k: v for k, v in patch.items() if k != "title_ko"}, row, _now_iso())
    if "title_ko" in patch and patch["title_ko"] != row.get("title_ko"):
        full["title_ko"] = patch["title_ko"]
    if "title" in full or "title_ko" in full:
        full["needs_tl"] = False
    if not full:
        return _err("바뀐 것이 없습니다")
    patch = full
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


def delete_tweet(unit: str, tweet_id: str | None = None) -> dict:
    """트윗 삭제. tweet_id 를 주면 그 트윗 1건만, 없으면 그 유닛의 트윗 전부(텔레그램 /del tweet 과 같음)."""
    args = {"unit": unit, "now_iso": _now_iso()}
    if tweet_id:
        args["tweet_id"] = str(tweet_id)
    res = _submit("tweet_del_commit", args)
    if res["ok"] and (res.get("result") or {}).get("found") is False:
        res = _err("그 트윗이 없습니다 (이미 지워졌거나 만료)")
    return _record("delete_tweet", f"{unit}:{tweet_id}" if tweet_id else unit, "", res)


def edit_tweet(unit: str, tweet_id: str, text_ko: str) -> dict:
    """(v4a) 트윗 수정 — 한글 번역만(원문 · X 카드는 그대로). 비울 수 없다: 번역이 없으면 팬 화면 말풍선이
    「번역 준비 중…」으로 남고 원문으로 대신하지 않는다. 직접 고친 번역은 자동 번역이 덮지 않는다(needs_tl 해제)."""
    text_ko = (text_ko or "").strip()
    if not text_ko:
        return _err("한글 번역을 비울 수 없습니다 — 비우면 팬 화면에 「번역 준비 중…」으로 남습니다")
    lst = (list_tweets().get("tweets") or {}).get(unit) or []
    lst = lst if isinstance(lst, list) else [lst]
    if not any(str((m or {}).get("id")) == str(tweet_id) for m in lst):
        return _err("그 트윗이 없습니다 (이미 지워졌거나 만료)")
    res = _submit("tweet_edit_commit", {"unit": unit, "tweet_id": str(tweet_id), "text_ko": text_ko,
                                        "now_iso": _now_iso()})
    if res["ok"] and not (res.get("result") or {}).get("found", True):
        res = _err("그 트윗이 없습니다 (이미 지워졌거나 만료)")
    elif res["ok"] and not (res.get("result") or {}).get("changed", True):
        res = _err("바뀐 것이 없습니다")
    return _record("edit_tweet", f"{unit}:{tweet_id}", text_ko[:60], res)


def translate_text(text: str) -> dict:
    """(v4a) 수정 창의 「번역」 — 입력 중인 원문 제목을 번역만 해서 돌려준다(저장 안 함, 적용 큐 안 탐).
    반환: {"ok", "result": {"title_ko": str}} · 실패 시 ok=False."""
    text = (text or "").strip()
    if not text:
        return _err("번역할 원문이 비었습니다")
    from .config import load_config
    from .handlers import _make_llm
    cfg = load_config()
    if not cfg.groq_api_key:
        return _err("GROQ_API_KEY 없음")
    ko = _make_llm(cfg).translate(text[:500])
    if not ko:
        return _err("번역 실패 (LLM 응답 없음) — 잠시 뒤 다시 시도")
    return _ok({"title_ko": ko})


def _retry_one(t, item: dict, chs: dict, now: str) -> str:
    """유실 원문 1건 재처리 → 결과 모드 문자열 (v3.9 `/ingest --retroactive` 와 같은 갈래)."""
    kind = item.get("kind", "ingest")
    raw, title, tag = item.get("raw", ""), item.get("title", ""), item.get("tag")
    if kind == "apply_job":
        # 결과를 기다리지 않은 적용 큐 작업의 실패 — 같은 작업을 다시 적재(결과 대기)
        import json as _json
        args = _json.loads(raw or "{}")
        args.pop("_waited", None)
        apply.submit(item.get("job_kind") or "", args, wait=True)
        return "resubmitted"
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


# ── (v4a) 작업 탭 — 흐름 · 예정된 확인 · 최근 자동 처리 · 번역 대기 ───────────────────────────────────────

# 관리 조작 흐름 이름 (admin_web 이 조작 1건마다 흐름을 연다). 미리보기(confirm=False)는 조작이 아니라 제외.
ADMIN_FLOW_LABELS = {
    "edit_preview": "예고 수정", "delete_preview": "예고 삭제", "ingest_preview_raw": "원문 투입 · 예고",
    "ingest_notice_raw": "원문 투입 · 소식", "ingest_tweet_raw": "원문 투입 · 트윗", "ingest_tweet_url": "URL 투입 · 트윗", "ingest_preview_url": "URL 투입 · 예고",
    "ingest_preview_manual": "수동 입력 · 예고", "ingest_notice_manual": "수동 입력 · 소식",
    "ingest_tweet_manual": "수동 입력 · 트윗", "edit_notice": "소식 수정", "edit_tweet": "트윗 수정",
    "delete_notice": "소식 삭제", "delete_tweet": "트윗 삭제", "retry_lost": "유실 원문 재투입",
    "set_paused": "일시정지 · 재개", "set_log_level": "알림 레벨", "set_monitor_auto": "멤버 현황 DM",
    "resolve_group_pending": "그룹 영상 확인 대기 · 확정", "dismiss_group_pending": "그룹 영상 확인 대기 · 무시",
    "undo_llm_action": "LLM 판단 되돌리기",
}


def _names() -> dict:
    try:
        return {k: (v or {}).get("name_ko") or k for k, v in (channels().get("channels") or {}).items()}
    except Exception:  # noqa: BLE001
        return {}


def _item_label(it: dict, names: dict) -> str:
    keys = [it.get("channel_key")] + list(it.get("collab_with") or [])
    who = "5인 합동" if len(keys) >= 5 else "·".join(names.get(k, k) for k in keys if k)
    title = (it.get("title_ko") or it.get("title") or "").strip()
    return f"{who} 「{title[:40]}」" if title else who


def describe_target(name: str, body: dict) -> str:
    """관리 조작 흐름 설명 한 줄 — 무엇을 건드렸는지."""
    try:
        names = _names()
        if name == "undo_llm_action":
            e = next((x for x in _t()._llm_actions_read(_store()) if x.get("id") == body.get("action_id")), {})
            return (e.get("summary") or body.get("action_id") or "")[:60]
        if name in ("resolve_group_pending", "dismiss_group_pending"):
            e = _t()._group_pending_items(_store()).get(body.get("video_id") or "") or {}
            who = "·".join(names.get(k, k) for k in (body.get("members") or []))
            return " · ".join(x for x in ((e.get("title") or "")[:40], body.get("video_id") or "", who) if x)
        if name in ("edit_preview", "delete_preview"):
            key = body.get("item_id") or body.get("key")
            it = next((i for i in list_preview().get("items", []) if i.get("id") == key), None)
            return _item_label(it, names) if it else str(key)
        if name in ("edit_notice", "delete_notice"):
            key = body.get("nid") or body.get("key")
            n = next((x for x in list_notices().get("notices", []) if x.get("id") == key), None)
            return (n.get("title_ko") or n.get("title") or key) if n else str(key)
        if name in ("delete_tweet", "edit_tweet"):
            unit = (body.get("unit") or body.get("key") or "").split("|")[0]
            return f"{names.get(unit, unit)} 트윗"
        if name.startswith("ingest_"):
            who = body.get("channel_key") or body.get("unit") or body.get("host")
            what = body.get("raw") or body.get("title") or body.get("url") or body.get("text") or ""
            return (f"{names.get(who, who)} · " if who else "") + what.replace("\n", " ")[:50]
        if name == "retry_lost":
            return f"{len(body.get('ids') or [])}건"
        if name == "set_paused":
            return "일시정지" if body.get("paused") else "재개"
        if name == "set_log_level":
            return str(body.get("level"))
        if name == "set_monitor_auto":
            return "켬" if body.get("enabled") else "끔"
    except Exception:  # noqa: BLE001
        pass
    return ""


def _check_reason(it: dict | None, run_at: str) -> str:
    """방송 확인 예약의 이유 — 예고 상태 · 시작 시각과 예약 시각의 차이로 설명."""
    if not it:
        return "대상 예고가 이미 정리됨 — 확인만 하고 끝납니다"
    st = it.get("state")
    ss = it.get("scheduled_start")
    try:
        if ss and st in ("announced", "upcoming", "watching"):
            d = (datetime.strptime(ss[:19], "%Y-%m-%dT%H:%M:%S") -
                 datetime.strptime(run_at[:19], "%Y-%m-%dT%H:%M:%S")).total_seconds() / 60
            if d >= 1:
                return f"방송 {round(d)}분 전 확인 ({_kst(ss)} 시작 예정)"
            return f"시작 예정 시각 이후 — 라이브 시작 여부 확인 ({_kst(ss)} 예정)"
    except Exception:  # noqa: BLE001
        pass
    return {"live": "라이브 상태 확인 — 종료 여부", "end": "종료 재확인 — 재개 여부"}.get(st, f"상태 확인 ({st})")


def _kst(iso: str) -> str:
    try:
        from datetime import timedelta
        dt = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return (dt + timedelta(hours=9)).strftime("%m/%d %H:%M")
    except Exception:  # noqa: BLE001
        return iso or ""


_AUTO_LABEL = {
    "snapshot": "일일 스냅샷", "apply_translation": "번역 반영", "notice_sweep": "지난 소식 정리",
    "yt_notif": "YouTube 알림 반영", "merge_rows": "예고 반영", "personal_tweet": "개인 트윗 반영",
    "apply_notice": "소식 반영", "url_confirmed_commit": "URL 확정 예고 반영",
    "yt_member_live_commit": "회원 전용 라이브 반영", "apply_preview_edit": "예고 수정 반영",
    "remove_broadcast": "예고 삭제", "notice_edit_commit": "소식 수정 반영", "notice_del_commit": "소식 삭제",
    "tweet_del_commit": "트윗 삭제",
    # (2026-10-01) 내부 이름(llm_action 등)이 그대로 보이던 작업들
    "manual_preview": "수동 예고 반영", "tweet_edit_commit": "트윗 수정 반영", "video_release": "프리미어 기록",
    "group_pending": "그룹 영상 확인 대기", "llm_action": "LLM 판단 기록",
}


def _auto_text(e: dict, items_by_vid: dict, names: dict) -> str:
    """최근 결과 1건 → 우리말 요약."""
    kind, b, r = e.get("kind"), e.get("brief") or {}, e.get("result") or {}
    if not e.get("ok"):
        return f"{_AUTO_LABEL.get(kind, kind)} 실패 — {e.get('summary') or ''}"[:200]
    if kind == "reconcile":
        trans = [x.split(" ")[0] for x in (r.get("log") or []) if isinstance(x, str) and x.startswith("→")]
        change = ("상태 " + " · ".join(trans)) if trans else ("예고 갱신" if r.get("preview_changed") else "변화 없음")
        if b.get("scope") == "video":
            it = items_by_vid.get(b.get("video_id"))
            what = _item_label(it, names) if it else b.get("video_id")
            return f"방송 확인 · {what} — {change}"
        mode = {"light": "10분", "baseline": "매일 전체"}.get(b.get("mode") or r.get("mode"), b.get("mode") or "")
        n = r.get("candidates")
        return f"정기 수집({mode}) — 영상 {n}개 확인, {change}" if n is not None else f"정기 수집({mode}) — {change}"
    if kind == "llm_action" and b.get("op") == "undo":
        # 결과 요약(summary)은 결과 dict 의 JSON — 되돌린 내용(applied)을 꺼내 보인다. 잘렸거나 못 읽으면 이름만
        try:
            applied = (json.loads(e.get("summary") or "{}").get("applied") or [])
        except (ValueError, AttributeError):
            applied = []
        return "↩ LLM 판단 되돌리기" + (f" — {' · '.join(applied)}" if applied else "")
    return _AUTO_LABEL.get(kind, kind)


def jobs_overview() -> dict:
    """작업 탭 한 번에: 최근 흐름 · 예정된 확인 · 최근 자동 처리 · 번역 대기 · 다음 정기 실행."""
    from . import flowtrace
    names = _names()
    pv = list_preview()
    items_by_vid = {i.get("video_id"): i for i in pv.get("items", []) if i.get("video_id")}

    scheduled = []
    for j in apply.pending():
        nm = j.get("name") or ""
        if j.get("kind") != "reconcile" or not nm.startswith("reconcile-video-"):
            continue
        # 이름 = "reconcile-video-<video_id>-<YYYY-MM-DDTHH:MM>" — video_id 에도 "-" 가 들어갈 수 있어 뒤 17자를 뗀다
        vid = nm[len("reconcile-video-"):-17]
        it = items_by_vid.get(vid)
        scheduled.append({"run_at": j.get("run_at_iso"), "video_id": vid, "attempt": j.get("attempt"),
                          "what": _item_label(it, names) if it else vid, "why": _check_reason(it, j.get("run_at_iso") or "")})
    scheduled.sort(key=lambda x: x["run_at"] or "")

    periodic = None
    try:
        from .local_runner import next_fire_times
        fires = next_fire_times(datetime.now(timezone.utc))
        periodic = {k: v.strftime("%Y-%m-%dT%H:%M:%SZ") for k, v in fires.items()}
    except Exception:  # noqa: BLE001
        pass

    auto = [{"ts": e.get("ts"), "ok": bool(e.get("ok")), "text": _auto_text(e, items_by_vid, names)}
            for e in apply.recent(100)]

    pending_tl = []
    for it in pv.get("items", []):
        if it.get("needs_tl") and it.get("title"):
            pending_tl.append(f"예고 · {_item_label(it, names)}")
    for n in list_notices().get("notices", []):
        if n.get("needs_tl"):
            pending_tl.append(f"소식 · {n.get('title') or n.get('id')}")
    for unit, lst in (list_tweets().get("tweets") or {}).items():
        for tw in (lst if isinstance(lst, list) else [lst]):
            if tw and tw.get("needs_tl"):
                pending_tl.append(f"트윗 · {names.get(unit, unit)} 「{(tw.get('text') or '')[:30]}」")

    return {"flows": flowtrace.list_flows(), "scheduled": scheduled, "periodic": periodic, "auto": auto,
            "pending_tl": pending_tl, "enrich_pending": len(enrich.pending()),
            "now": _now_status(pv, names, flowtrace)}


def _last_upstream(flows: list[dict]) -> dict:
    """마지막 업스트림 알림(X · YouTube 각각) — 흐름 기록(인증 실패 포함)과 모니터 이벤트 로그 중 더 최근 것.
    이벤트 로그는 흐름 기록이 생기기 전(재시작 전)의 수신도 담고 있다."""
    out = {"x": None, "yt": None}
    for f in flows:
        c = f.get("cat")
        if c in out and (out[c] is None or f["t0"] > out[c]["ts"]):
            out[c] = {"ts": f["t0"], "ok": f.get("status") != "fail", "text": f.get("reason") or f.get("status")}
    try:
        import json as _json
        from datetime import timedelta
        from . import monitor_log
        mon = storage.make_store("monitoring")
        now = datetime.now(timezone.utc)
        for d in (now, now - timedelta(days=1)):
            txt = mon.read_text(monitor_log.event_path(d.strftime("%Y-%m-%dT%H:%M:%SZ")))[0] or ""
            for line in txt.splitlines():
                try:
                    e = _json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if e.get("flow") != "upstream":
                    continue
                c = "yt" if e.get("source") == "yt" else "x"
                if out[c] is None or e.get("ts", "") > out[c]["ts"]:
                    out[c] = {"ts": e.get("ts"), "ok": e.get("result") != "err", "text": e.get("detail") or ""}
    except Exception:  # noqa: BLE001
        log.warning("업스트림 이벤트 읽기 실패", exc_info=True)
    return out


def _now_status(pv: dict, names: dict, flowtrace) -> dict:
    """작업 탭 "지금 상태" — 러너 · 텔레그램 · 마지막 알림 · 큐 · 방송 · 데이터 갱신."""
    import json as _json
    import os as _os
    from pathlib import Path as _Path
    now_iso = _now_iso()
    runner = None
    try:
        p = _Path(_os.environ.get("LOCAL_DATA_DIR") or "./_local") / "ops" / "runner.json"
        runner = _json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import tg_poll
        tg = dict(tg_poll.STATUS)
    except Exception:  # noqa: BLE001
        tg = {"state": "unknown"}
    pend = apply.pending()
    due = [j for j in pend if (j.get("run_at_iso") or "") <= now_iso]
    items = pv.get("items", []) or []
    live = [_item_label(i, names) for i in items if i.get("state") == "live"]
    nxt = sorted((i for i in items if i.get("state") in ("announced", "upcoming", "watching")
                  and (i.get("scheduled_start") or "") >= now_iso[:13]), key=lambda i: i.get("scheduled_start") or "")
    last_rec = next((e for e in apply.recent(200) if e.get("kind") == "reconcile" and e.get("ok")), None)
    return {
        "server_now": now_iso,
        "runner": runner,
        "telegram": tg,
        "upstream": _last_upstream(flowtrace.list_flows()),
        "queue": {"due": len(due), "scheduled": len(pend) - len(due), "enrich": len(enrich.pending())},
        "live": live,
        "next": [{"at": i.get("scheduled_start"), "what": _item_label(i, names), "state": i.get("state")}
                 for i in nxt[:2]],
        "preview_generated_at": pv.get("generated_at"),
        "last_reconcile": last_rec.get("ts") if last_rec else None,
    }


API_FUNCTIONS: tuple[str, ...] = (
    "list_preview", "list_notices", "list_tweets", "get_control", "list_history", "list_lost",
    "list_jobs", "channels", "edit_preview", "delete_preview", "ingest_preview_raw",
    "ingest_notice_raw", "ingest_tweet_raw", "ingest_tweet_url", "ingest_preview_url", "ingest_preview_manual",
    "ingest_notice_manual", "ingest_tweet_manual", "edit_notice", "edit_tweet", "delete_notice", "delete_tweet",
    "retry_lost", "set_paused", "set_log_level", "set_monitor_auto",
    "translate_text", "jobs_overview",
)


if __name__ == "__main__":
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        os.environ.update({"V4A_RUNTIME": "local", "LOCAL_DATA_DIR": d, "ALLOW_UNAUTH": "1"})
        gh = _store()
        now = "2026-09-29T12:00:00Z"
        gh.write_json("preview.json", {"channel_order": ["arale", "yuno", "nonoka", "ritsu", "miyako"], "items": [
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
        # (v4a) 합동 멤버 · 회원 전용
        assert edit_preview("pv_a", {"collab_with": ["arale"]}, {})["ok"] is False, "주 레인은 참여 멤버에 못 넣음"
        assert edit_preview("pv_a", {"collab_with": ["nobody"]}, {})["ok"] is False
        assert edit_preview("pv_a", {"membership": "yes"}, {})["ok"] is False
        r = edit_preview("pv_a", {"collab_with": ["miyako", "yuno", "yuno"], "membership": True},
                         {"collab_with": None, "membership": None})
        assert r["ok"], r
        it = list_preview()["items"][0]
        assert it["collab_with"] == ["yuno", "miyako"] and it["kind"] == "collab" and it["membership"] is True, it
        r = edit_preview("pv_a", {"collab_with": [], "membership": False},
                         {"collab_with": ["yuno", "miyako"], "membership": True})
        assert r["ok"], r
        it = list_preview()["items"][0]
        assert it["collab_with"] is None and it["kind"] is None and it["membership"] is False, it
        # (v4a) 제목 원문·한글 수정 → 운영자 제목 보호 · 자동 번역 끔 / 원문 비우면 보호 해제
        r = edit_preview("pv_a", {"title": "新タイトル", "title_ko": ""}, {"title": "새 제목", "title_ko": None})
        assert r["ok"], r
        it = list_preview()["items"][0]
        assert it["title"] == "新タイトル" and it["title_ko"] == "" and it["title_manual"] is True \
            and it["needs_tl"] is False, it
        r = edit_preview("pv_a", {"title": ""}, {"title": "新タイトル"})
        it = list_preview()["items"][0]
        assert r["ok"] and "title_manual" not in it and it["title"] is None, it
        assert translate_text("")["ok"] is False
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
        # (2026-10-01) 쓰이지 않던 API 정리 — 목록 번역(translate) · 미구현 이력 되돌리기(undo)
        assert "translate" not in API_FUNCTIONS and "undo" not in API_FUNCTIONS
        # (v4a) 트윗 단위 삭제 — 같은 유닛의 다른 트윗은 남는다
        gh.write_json("tweets.json", {"tweets": {"arale": [{"id": "1", "text": "a"}, {"id": "2", "text": "b"}]}},
                      prev_sha=gh.read_json("tweets.json")[1], message="seed")
        assert delete_tweet("arale", "9")["ok"] is False, "없는 트윗"
        assert delete_tweet("arale", "1")["ok"]
        assert [m["id"] for m in list_tweets()["tweets"]["arale"]] == ["2"]
        assert delete_tweet("arale", "2")["ok"] and "arale" not in list_tweets()["tweets"], "마지막이면 유닛 제거"
    print("[PASS] admin_api self-test: 읽기 · 충돌 · 수정 · 운영 설정(ops) · 삭제 · 이력")
