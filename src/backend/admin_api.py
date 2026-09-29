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
        if not it:
            return _err("항목 없음")
        if not it.get("title"):
            return _err("제목이 없는 예고라 번역할 것이 없습니다")
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
        # key = 유닛(그 유닛 전부) 또는 "유닛|트윗id"(그 트윗만)
        unit, _, tid = key.partition("|")
        lst = (list_tweets().get("tweets") or {}).get(unit) or []
        lst = lst if isinstance(lst, list) else [lst]
        if tid:
            lst = [tw for tw in lst if str(tw.get("id")) == tid]
            if not lst:
                return _err("트윗 없음")
        for tw in lst:
            ko = llm.translate(tw.get("text") or "")
            if ko:
                up["tweets"][f"{unit}|{tw.get('id')}"] = {"text_ko": ko}
    else:
        return _err("target 은 preview · notice · tweet")
    if not enrich.count(up):
        return _record("translate", f"{target}:{key}", "번역 실패", _err("LLM 번역 실패"))
    res = _submit("apply_translation", {"updates": up, "now_iso": _now_iso(), "force": True})
    return _record("translate", f"{target}:{key}", "", res)


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


def undo(history_id: str) -> dict:
    """(범위 밖 — 항목 단위 되돌리기는 배포 단계) 현재는 {"ok": False, "error": "미구현"}."""
    return {"ok": False, "job_id": None, "result": None, "error": "미구현 (v4a 로컬 시험판 범위 밖)"}


# ── (v4a) 작업 탭 — 흐름 · 예정된 확인 · 최근 자동 처리 · 번역 대기 ───────────────────────────────────────

# 관리 조작 흐름 이름 (admin_web 이 조작 1건마다 흐름을 연다). 미리보기(confirm=False)는 조작이 아니라 제외.
ADMIN_FLOW_LABELS = {
    "edit_preview": "예고 수정", "delete_preview": "예고 삭제", "ingest_preview_raw": "원문 투입 · 예고",
    "ingest_notice_raw": "원문 투입 · 소식", "ingest_tweet_raw": "원문 투입 · 트윗", "edit_notice": "소식 수정",
    "delete_notice": "소식 삭제", "delete_tweet": "트윗 삭제", "translate": "번역", "retry_lost": "유실 원문 재투입",
    "set_paused": "일시정지 · 재개", "set_log_level": "알림 레벨", "set_monitor_auto": "멤버 현황 DM",
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
        if name in ("edit_preview", "delete_preview") or (name == "translate" and body.get("target") == "preview"):
            key = body.get("item_id") or body.get("key")
            it = next((i for i in list_preview().get("items", []) if i.get("id") == key), None)
            return _item_label(it, names) if it else str(key)
        if name in ("edit_notice", "delete_notice") or (name == "translate" and body.get("target") == "notice"):
            key = body.get("nid") or body.get("key")
            n = next((x for x in list_notices().get("notices", []) if x.get("id") == key), None)
            return (n.get("title_ko") or n.get("title") or key) if n else str(key)
        if name == "delete_tweet" or (name == "translate" and body.get("target") == "tweet"):
            unit = (body.get("unit") or body.get("key") or "").split("|")[0]
            return f"{names.get(unit, unit)} 트윗"
        if name.startswith("ingest_"):
            who = body.get("channel_key") or body.get("unit")
            return (f"{names.get(who, who)} · " if who else "") + (body.get("raw") or "").replace("\n", " ")[:50]
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
    "ingest_notice_raw", "ingest_tweet_raw", "edit_notice", "delete_notice", "delete_tweet",
    "translate", "retry_lost", "set_paused", "set_log_level", "set_monitor_auto", "undo",
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
        assert undo("x")["ok"] is False
        # (v4a) 트윗 단위 삭제 — 같은 유닛의 다른 트윗은 남는다
        gh.write_json("tweets.json", {"tweets": {"arale": [{"id": "1", "text": "a"}, {"id": "2", "text": "b"}]}},
                      prev_sha=gh.read_json("tweets.json")[1], message="seed")
        assert delete_tweet("arale", "9")["ok"] is False, "없는 트윗"
        assert delete_tweet("arale", "1")["ok"]
        assert [m["id"] for m in list_tweets()["tweets"]["arale"]] == ["2"]
        assert delete_tweet("arale", "2")["ok"] and "arale" not in list_tweets()["tweets"], "마지막이면 유닛 제거"
    print("[PASS] admin_api self-test: 읽기 · 충돌 · 수정 · 운영 설정(ops) · 삭제 · 이력")
