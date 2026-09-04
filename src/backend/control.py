"""
control.json 스키마 및 헬퍼 함수.
계약 F 참고: docs/SPEC.md §6

  {
    "paused": false,
    "since": null,               // paused=true 로 바뀐 시각 (ISO 'Z')
    "by": null,                  // 마지막 변경 출처 메모
    "log_level": "normal",       // "detail" | "normal" | "simple"
    "updated_at": "..."
  }
"""

LOG_LEVELS = ("detail", "normal", "simple")
DEFAULT_LOG_LEVEL = "normal"


def default_control() -> dict:
    """기본 control.json 형태."""
    return {
        "paused": False,
        "since": None,
        "by": None,
        "log_level": DEFAULT_LOG_LEVEL,
        "updated_at": None,
    }


def _as_dict(control) -> dict:
    """control 이 dict 아니면 기본형. (원본은 건드리지 않음)"""
    return dict(control) if isinstance(control, dict) else default_control()


def is_paused(control) -> bool:
    """paused 상태 판정. dict 아니거나 키 없으면 False."""
    if not isinstance(control, dict):
        return False
    return bool(control.get("paused", False))


def get_log_level(control) -> str:
    """로그 레벨 반환. 값이 없거나 이상하면 'normal'."""
    if not isinstance(control, dict):
        return DEFAULT_LOG_LEVEL
    lvl = control.get("log_level", DEFAULT_LOG_LEVEL)
    return lvl if lvl in LOG_LEVELS else DEFAULT_LOG_LEVEL


def set_paused(control, paused: bool, *, by: str, now_iso: str) -> dict:
    """paused 상태만 바꾼 새 dict 반환 (log_level 등 다른 필드는 보존, 원본 불변).

    paused=True → since=now_iso, paused=False → since=None. by/updated_at 갱신.
    """
    result = _as_dict(control)
    result["paused"] = bool(paused)
    result["since"] = now_iso if paused else None
    result["by"] = by
    result["updated_at"] = now_iso
    result.setdefault("log_level", DEFAULT_LOG_LEVEL)
    return result


def set_log_level(control, level: str, *, by: str, now_iso: str) -> dict:
    """log_level 만 바꾼 새 dict 반환 (paused 등 보존, 원본 불변).

    level 이 LOG_LEVELS 밖이면 ValueError.
    """
    if level not in LOG_LEVELS:
        raise ValueError(f"invalid log level: {level!r} (택: {', '.join(LOG_LEVELS)})")
    result = _as_dict(control)
    result["log_level"] = level
    result["by"] = by
    result["updated_at"] = now_iso
    result.setdefault("paused", False)
    result.setdefault("since", None)
    return result


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    d = default_control()
    assert d["paused"] is False and d["log_level"] == "normal"
    assert is_paused(None) is False and is_paused({}) is False
    assert get_log_level(None) == "normal"
    assert get_log_level({"log_level": "bogus"}) == "normal"
    assert get_log_level({"log_level": "simple"}) == "simple"
    print("✓ defaults / getters")

    p = set_paused(d, True, by="telegram:/pause", now_iso="2026-08-31T12:00:00Z")
    assert p["paused"] is True and p["since"] == "2026-08-31T12:00:00Z"
    assert p["log_level"] == "normal", "log_level 보존"
    r = set_paused(p, False, by="telegram:/resume", now_iso="2026-08-31T12:15:00Z")
    assert r["paused"] is False and r["since"] is None
    print("✓ set_paused round-trip (log_level 보존)")

    lv = set_log_level(p, "detail", by="telegram:/log", now_iso="2026-08-31T12:20:00Z")
    assert lv["log_level"] == "detail" and lv["paused"] is True, "paused 보존"
    try:
        set_log_level(d, "verbose", by="x", now_iso="z")
        assert False, "invalid level 은 ValueError"
    except ValueError:
        pass
    print("✓ set_log_level (paused 보존, 검증)")

    orig = default_control()
    set_paused(orig, True, by="t", now_iso="z")
    set_log_level(orig, "simple", by="t", now_iso="z")
    assert orig == default_control(), "원본 불변"
    print("✓ 원본 불변")

    print("\nSUCCESS: control.py smoke test passed")
