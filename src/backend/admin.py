"""admin_state.json 스키마 및 헬퍼 함수 (v2.5 — 텔레그램 수동 관리 명령).

계약: docs/plan/v2_5_admin_commands.md

  {
    "pending_del": null | {
      "unit": "arale",
      "idx": 2,                    // /list 당시 1-based 순번 (표시용, 매칭엔 snapshot 사용)
      "snapshot": {...},           // 지우려는 broadcasts[] 항목 원본 (재확인용)
      "warn_text": "...",          // /del 이 보낸 경고문 (로그용)
      "at": "..."                  // 확인 대기 시작 시각 (ISO 'Z')
    },
    "undo": null | {
      "action": "...",             // 사람이 읽을 설명 ("/del arale#2", "ingest 2026-..." 등)
      "prev_content": {...},       // 변경 직전 schedule.json 전체
      "new_sha": "...",            // 변경 커밋 직후 schedule.json 의 sha (undo 시 CAS 확인용)
      "at": "..."
    }
  }

`pending_del`/`undo` 는 각각 슬롯 1개 — 새 요청이 오면 이전 슬롯을 덮어쓴다.
"""
from __future__ import annotations

from datetime import datetime, timezone

PENDING_DEL_TTL_SEC = 300  # /del 경고 후 (y/N) 대기 상한 — 지나면 만료 취급


def default_admin_state() -> dict:
    """기본 admin_state.json 형태."""
    return {"pending_del": None, "undo": None}


def _as_dict(state) -> dict:
    """state 가 dict 아니면 기본형. (원본은 건드리지 않음)"""
    return dict(state) if isinstance(state, dict) else default_admin_state()


def get_pending_del(state) -> dict | None:
    """대기 중인 삭제 확인 반환. 없으면 None."""
    if not isinstance(state, dict):
        return None
    return state.get("pending_del")


def set_pending_del(state, *, unit: str, idx: int, snapshot: dict, warn_text: str, now_iso: str) -> dict:
    """새 삭제 확인 대기 상태로 교체한 새 dict 반환 (원본 불변). undo 슬롯은 보존."""
    result = _as_dict(state)
    result["pending_del"] = {
        "unit": unit,
        "idx": idx,
        "snapshot": snapshot,
        "warn_text": warn_text,
        "at": now_iso,
    }
    return result


def clear_pending_del(state) -> dict:
    """삭제 확인 대기 상태를 비운 새 dict 반환 (원본 불변). undo 슬롯은 보존."""
    result = _as_dict(state)
    result["pending_del"] = None
    return result


def pending_del_expired(pending: dict | None, now_iso: str, ttl_sec: int = PENDING_DEL_TTL_SEC) -> bool:
    """pending_del 이 TTL 을 넘겼는지. pending 이 없으면(None) True(= 유효하지 않음) 취급."""
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


def get_undo(state) -> dict | None:
    """되돌리기 가능한 마지막 작업 반환. 없으면 None."""
    if not isinstance(state, dict):
        return None
    return state.get("undo")


def set_undo(state, *, action: str, prev_content: dict, new_sha: str | None, now_iso: str) -> dict:
    """새 undo 스냅샷으로 교체한 새 dict 반환 (원본 불변). pending_del 슬롯은 보존."""
    result = _as_dict(state)
    result["undo"] = {
        "action": action,
        "prev_content": prev_content,
        "new_sha": new_sha,
        "at": now_iso,
    }
    return result


def clear_undo(state) -> dict:
    """undo 슬롯을 비운 새 dict 반환 (원본 불변). pending_del 슬롯은 보존."""
    result = _as_dict(state)
    result["undo"] = None
    return result


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    d = default_admin_state()
    assert d["pending_del"] is None and d["undo"] is None
    assert get_pending_del(None) is None and get_undo({}) is None
    print("✓ defaults / getters")

    p = set_pending_del(
        d, unit="arale", idx=2,
        snapshot={"channel_key": "arale", "status": "scheduled"},
        warn_text="#2 나카마치 아라레의 20:00~23:00 방송예고를 내리시겠습니까?",
        now_iso="2026-09-05T12:00:00Z",
    )
    assert get_pending_del(p)["unit"] == "arale"
    assert get_undo(p) is None, "undo 슬롯 안 건드림"
    c = clear_pending_del(p)
    assert get_pending_del(c) is None
    print("✓ pending_del 설정/해제 (원본 불변, undo 슬롯 보존)")

    assert pending_del_expired(None, "2026-09-05T12:00:00Z") is True
    fresh = get_pending_del(p)
    assert pending_del_expired(fresh, "2026-09-05T12:04:00Z") is False   # 4분 후 — 아직 유효(TTL 5분)
    assert pending_del_expired(fresh, "2026-09-05T12:06:00Z") is True    # 6분 후 — 만료
    print("✓ pending_del_expired TTL")

    u = set_undo(
        d, action="/del arale#2", prev_content={"broadcasts": []},
        new_sha="sha_after", now_iso="2026-09-05T12:01:00Z",
    )
    assert get_undo(u)["new_sha"] == "sha_after"
    assert get_pending_del(u) is None, "pending_del 슬롯 안 건드림"
    u2 = clear_undo(u)
    assert get_undo(u2) is None
    print("✓ undo 설정/해제 (원본 불변, pending_del 슬롯 보존)")

    orig = default_admin_state()
    set_pending_del(orig, unit="x", idx=1, snapshot={}, warn_text="", now_iso="z")
    set_undo(orig, action="x", prev_content={}, new_sha="s", now_iso="z")
    assert orig == default_admin_state(), "원본 불변"
    print("✓ 원본 불변")

    print("\nSUCCESS: admin.py smoke test passed")
