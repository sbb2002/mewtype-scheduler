"""admin_state.json v3 스키마 및 헬퍼 함수.

계약: docs/plan/v3_impl_spec.md §0.4, v3_telegram_controller.md

  {
    "pending_op": null | {
      "cmd": "ingest" | "edit" | "del" | "translate",
      "contents": "preview" | "notice" | "tweet",
      "step": "await_idx" | "await_raw" | ... (명령별 상태머신 스텝 이름),
      "ctx": { /* unit, target_id, patch 누적, snapshot 등 */ },
      "at": "2026-...Z"
    },
    "edit_lock": null | { "id": "pv_ab12cd34", "until": "2026-...Z" },
    "suppress": [ { "url": "...", "until": "2026-...Z" } ],
    "undo": null | {
      "cmd": "del" | "ingest" | "edit" | "translate",
      "contents": "preview" | "notice" | "tweet",
      "path": "preview.json" | "notices.json" | "tweets.json",
      "prev_content": { /* 그 파일 전체(변경 직전) */ },
      "new_sha": "...",
      "at": "2026-...Z"
    },
    "pending_undo": null | { "at": "...", "target_sha": "...", "action": "..." }
  }
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _plus_seconds_iso(now_iso: str, sec: int) -> str:
    """now_iso + sec 초를 "%Y-%m-%dT%H:%M:%SZ" 로. 파싱 실패 시 now_iso 그대로."""
    try:
        dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except Exception:
        return now_iso
    return (dt + timedelta(seconds=sec)).astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def default_admin_state() -> dict:
    """기본 admin_state.json 형태."""
    return {
        "pending_op": None,
        "edit_lock": None,
        "suppress": [],
        "undo": None,
        "pending_undo": None,
    }


def _as_dict(state) -> dict:
    """state 가 dict 아니면 기본형. (원본은 건드리지 않음)"""
    return dict(state) if isinstance(state, dict) else default_admin_state()


# ============================================================================
# pending_op: 명령 진행 상태 (cmd × contents × step 격자)
# ============================================================================

def get_pending_op(state) -> dict | None:
    """진행 중인 명령 반환. 없으면 None."""
    if not isinstance(state, dict):
        return None
    return state.get("pending_op")


def set_pending_op(state, *, cmd: str, contents: str, step: str, ctx: dict | None, now_iso: str) -> dict:
    """새 pending_op 로 교체한 새 dict 반환 (원본 불변, 타 슬롯 보존).

    `cmd` ∈ ingest | edit | del | translate
    `contents` ∈ preview | notice | tweet
    `step` = 명령별 상태머신 스텝 이름 (await_idx, await_raw, ...)
    `ctx` = 단계 간 누적 데이터 (unit, target_id, patch, snapshot 등)
    """
    result = _as_dict(state)
    result["pending_op"] = {
        "cmd": cmd,
        "contents": contents,
        "step": step,
        "ctx": dict(ctx or {}),
        "at": now_iso,
    }
    return result


def clear_pending_op(state) -> dict:
    """pending_op 를 비운 새 dict 반환 (원본 불변, 타 슬롯 보존)."""
    result = _as_dict(state)
    result["pending_op"] = None
    return result


def pending_op_expired(pending: dict | None, now_iso: str, ttl_sec: int = 60) -> bool:
    """pending_op 가 TTL 을 넘겼는지. None 이면 True(= 유효하지 않음) 취급."""
    if not pending:
        return True
    at = pending.get("at")
    if not at:
        return True
    try:
        at_dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except Exception:
        return True
    return (now_dt - at_dt).total_seconds() > ttl_sec


# ============================================================================
# edit_lock: 아이템 단위 편집 락
# ============================================================================

def get_edit_lock(state) -> dict | None:
    """진행 중인 편집 락 반환. 없으면 None."""
    if not isinstance(state, dict):
        return None
    return state.get("edit_lock")


def set_edit_lock(state, *, id: str, now_iso: str, ttl_sec: int = 60) -> dict:
    """새 edit_lock 으로 교체한 새 dict 반환 (원본 불변, 타 슬롯 보존).

    `until` = `now_iso` + `ttl_sec` 초로 자동 계산.
    """
    result = _as_dict(state)
    result["edit_lock"] = {"id": id, "until": _plus_seconds_iso(now_iso, ttl_sec)}
    return result


def clear_edit_lock(state) -> dict:
    """edit_lock 를 비운 새 dict 반환 (원본 불변, 타 슬롯 보존)."""
    result = _as_dict(state)
    result["edit_lock"] = None
    return result


def edit_lock_active(state, item_id: str, now_iso: str) -> bool:
    """편집 락이 활성화되어 있는지 (해당 item_id, 시각 내).

    락이 걸려있고 now < until 이면 True.
    """
    lock = get_edit_lock(state)
    if not lock:
        return False
    if lock.get("id") != item_id:
        return False
    until = lock.get("until")
    if not until:
        return False
    try:
        until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except Exception:
        return False
    return now_dt < until_dt


# ============================================================================
# suppress: URL 재진입 차단 배열 (12시간)
# ============================================================================

def add_suppress(state, *, url: str, now_iso: str, ttl_sec: int = 12 * 3600) -> dict:
    """URL 을 suppress 배열에 추가한 새 dict 반환 (원본 불변, 타 슬롯 보존).

    `until` = `now_iso` + `ttl_sec` 초.
    """
    result = _as_dict(state)
    suppress = list(result.get("suppress") or [])
    suppress.append({"url": url, "until": _plus_seconds_iso(now_iso, ttl_sec)})
    result["suppress"] = suppress
    return result


def sweep_suppress(state, now_iso: str) -> dict:
    """만료된 suppress 항목을 제거한 새 dict 반환 (원본 불변, 타 슬롯 보존)."""
    result = _as_dict(state)
    suppress = list(result.get("suppress") or [])

    try:
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except Exception:
        result["suppress"] = suppress
        return result

    alive = []
    for item in suppress:
        until = item.get("until")
        if not until:
            continue
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if now_dt < until_dt:
                alive.append(item)
        except Exception:
            alive.append(item)

    result["suppress"] = alive
    return result


def suppressed(state, url: str, now_iso: str) -> bool:
    """URL 이 현재 차단 중인지 확인."""
    suppress = list(state.get("suppress") or []) if isinstance(state, dict) else []

    try:
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except Exception:
        return False

    for item in suppress:
        if item.get("url") != url:
            continue
        until = item.get("until")
        if not until:
            continue
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if now_dt < until_dt:
                return True
        except Exception:
            pass

    return False


# ============================================================================
# undo: 마지막 mutating 명령 스냅샷
# ============================================================================

def set_undo(state, *, cmd: str, contents: str, path: str, prev_content: dict,
             new_sha: str | None, now_iso: str) -> dict:
    """새 undo 스냅샷으로 교체한 새 dict 반환 (원본 불변, 타 슬롯 보존).

    `cmd` ∈ ingest | edit | del | translate
    `contents` ∈ preview | notice | tweet
    `path` ∈ preview.json | notices.json | tweets.json
    `prev_content` = 변경 직전 그 파일 전체
    `new_sha` = 변경 후 그 파일의 git sha (CAS 검증용)
    """
    result = _as_dict(state)
    result["undo"] = {
        "cmd": cmd,
        "contents": contents,
        "path": path,
        "prev_content": dict(prev_content or {}),
        "new_sha": new_sha,
        "at": now_iso,
    }
    return result


def clear_undo(state) -> dict:
    """undo 슬롯을 비운 새 dict 반환 (원본 불변, 타 슬롯 보존)."""
    result = _as_dict(state)
    result["undo"] = None
    return result


def get_undo(state) -> dict | None:
    """되돌리기 가능한 마지막 작업 반환. 없으면 None."""
    if not isinstance(state, dict):
        return None
    return state.get("undo")


# ============================================================================
# pending_undo: undo 최종확인 대기 (y/N)
# ============================================================================

def set_pending_undo(state, *, target_sha: str | None, action: str, now_iso: str) -> dict:
    """undo 최종확인 대기 상태로 교체한 새 dict 반환 (원본 불변, 타 슬롯 보존).

    `target_sha` = undo.new_sha 와 대조할 현재 파일 sha (안전 확인)
    `action` = 사람이 읽을 설명 ("/del arale#2", "ingest 2026-..." 등)
    """
    result = _as_dict(state)
    result["pending_undo"] = {
        "at": now_iso,
        "target_sha": target_sha,
        "action": action,
    }
    return result


def clear_pending_undo(state) -> dict:
    """pending_undo 슬롯을 비운 새 dict 반환 (원본 불변, 타 슬롯 보존)."""
    result = _as_dict(state)
    result["pending_undo"] = None
    return result


def get_pending_undo(state) -> dict | None:
    """undo 최종확인 대기 상태 반환. 없으면 None."""
    if not isinstance(state, dict):
        return None
    return state.get("pending_undo")


def pending_undo_expired(pending: dict | None, now_iso: str, ttl_sec: int = 60) -> bool:
    """pending_undo 가 TTL 을 넘겼는지. None 이면 True 취급."""
    if not pending:
        return True
    at = pending.get("at")
    if not at:
        return True
    try:
        at_dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
        now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except Exception:
        return True
    return (now_dt - at_dt).total_seconds() > ttl_sec


# ============================================================================
# Self-test
# ============================================================================

if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # 기본 상태
    d = default_admin_state()
    assert d["pending_op"] is None and d["edit_lock"] is None
    assert d["suppress"] == [] and d["undo"] is None and d["pending_undo"] is None
    print("✓ default_admin_state")

    # pending_op 슬롯 보존
    p = set_pending_op(d, cmd="del", contents="preview", step="await_idx", ctx={"unit": "arale"}, now_iso="2026-09-09T12:00:00Z")
    assert get_pending_op(p)["cmd"] == "del"
    assert get_edit_lock(p) is None, "edit_lock 슬롯 안 건드림"
    assert p["suppress"] == [], "suppress 슬롯 보존"
    p2 = clear_pending_op(p)
    assert get_pending_op(p2) is None and get_edit_lock(p2) is None and p2["suppress"] == []
    print("✓ pending_op set/clear 시 타 슬롯 보존")

    # pending_op_expired TTL 60초
    assert pending_op_expired(None, "2026-09-09T12:00:00Z") is True
    fresh_op = get_pending_op(p)
    assert pending_op_expired(fresh_op, "2026-09-09T12:00:45Z") is False  # 45초 < 60초
    assert pending_op_expired(fresh_op, "2026-09-09T12:01:10Z") is True    # 70초 > 60초
    print("✓ pending_op_expired TTL 60s 경계")

    # edit_lock 슬롯 보존
    e = set_edit_lock(d, id="pv_abcd1234", now_iso="2026-09-09T12:00:00Z", ttl_sec=60)
    assert get_edit_lock(e)["id"] == "pv_abcd1234"
    assert get_pending_op(e) is None, "pending_op 슬롯 안 건드림"
    assert e["suppress"] == []
    e2 = clear_edit_lock(e)
    assert get_edit_lock(e2) is None and get_pending_op(e2) is None
    print("✓ edit_lock set/clear 시 타 슬롯 보존")

    # edit_lock_active 시각 경계
    assert edit_lock_active(e, "pv_abcd1234", "2026-09-09T12:00:30Z") is True   # 30초 < until(60초)
    assert edit_lock_active(e, "pv_abcd1234", "2026-09-09T12:01:10Z") is False  # 70초 > until
    assert edit_lock_active(e, "pv_other", "2026-09-09T12:00:30Z") is False     # id 미매칭
    assert edit_lock_active(d, "pv_abcd1234", "2026-09-09T12:00:30Z") is False  # 락 없음
    print("✓ edit_lock_active 시각 경계 + id 매칭")

    # suppress 슬롯 + add/sweep/suppressed
    s1 = add_suppress(d, url="https://example.com/a", now_iso="2026-09-09T12:00:00Z", ttl_sec=12*3600)
    assert len(s1["suppress"]) == 1
    assert suppressed(s1, "https://example.com/a", "2026-09-09T13:00:00Z") is True  # 1시간 < 12시간
    assert suppressed(s1, "https://example.com/a", "2026-09-10T01:00:00Z") is False # 13시간 > 12시간
    assert suppressed(s1, "https://example.com/b", "2026-09-09T13:00:00Z") is False # url 미매칭
    print("✓ suppress add/suppressed 12h 차단")

    s2 = add_suppress(s1, url="https://example.com/b", now_iso="2026-09-09T12:00:00Z", ttl_sec=12*3600)
    assert len(s2["suppress"]) == 2
    s3 = sweep_suppress(s2, "2026-09-10T01:30:00Z")  # 13.5시간 후
    assert len(s3["suppress"]) == 0, "모두 만료됨"
    assert get_pending_op(s3) is None, "타 슬롯 보존"
    print("✓ suppress sweep_suppress 만료 제거")

    # undo 슬롯 + path 분기
    u1 = set_undo(d, cmd="del", contents="preview", path="preview.json",
                  prev_content={"items": []}, new_sha="sha_preview", now_iso="2026-09-09T12:00:00Z")
    assert get_undo(u1)["path"] == "preview.json"
    assert get_pending_op(u1) is None, "pending_op 슬롯 보존"
    print("✓ undo set path=preview.json + 타 슬롯 보존")

    u2 = set_undo(d, cmd="edit", contents="notice", path="notices.json",
                  prev_content={"notices": []}, new_sha="sha_notice", now_iso="2026-09-09T12:00:00Z")
    assert get_undo(u2)["path"] == "notices.json"
    print("✓ undo path=notices.json")

    u3 = set_undo(d, cmd="ingest", contents="tweet", path="tweets.json",
                  prev_content={"tweets": []}, new_sha="sha_tweet", now_iso="2026-09-09T12:00:00Z")
    assert get_undo(u3)["path"] == "tweets.json"
    print("✓ undo path=tweets.json")

    u4 = clear_undo(u1)
    assert get_undo(u4) is None
    print("✓ undo clear")

    # pending_undo 슬롯
    pu = set_pending_undo(d, target_sha="sha_after", action="/del arale#2", now_iso="2026-09-09T12:00:00Z")
    assert get_pending_undo(pu)["action"] == "/del arale#2"
    assert pending_undo_expired(None, "2026-09-09T12:00:00Z") is True
    assert pending_undo_expired(get_pending_undo(pu), "2026-09-09T12:00:45Z") is False
    assert pending_undo_expired(get_pending_undo(pu), "2026-09-09T12:01:10Z") is True
    pu2 = clear_pending_undo(pu)
    assert get_pending_undo(pu2) is None
    print("✓ pending_undo set/clear/expired TTL 60s")

    # 원본 불변 확인
    orig = default_admin_state()
    set_pending_op(orig, cmd="x", contents="preview", step="x", ctx={}, now_iso="z")
    set_edit_lock(orig, id="x", now_iso="z")
    add_suppress(orig, url="x", now_iso="z")
    set_undo(orig, cmd="x", contents="preview", path="preview.json", prev_content={}, new_sha="s", now_iso="z")
    set_pending_undo(orig, target_sha="s", action="x", now_iso="z")
    assert orig == default_admin_state(), "모든 set* 호출 후에도 원본 불변"
    print("✓ 원본 불변")

    print("\nSUCCESS: admin.py v3 self-test passed (14 assert)")
