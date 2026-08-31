"""
control.json 스키마 및 헬퍼 함수.
계약 F 참고: § IMPLEMENTATION_v2.1.md
"""


def default_control() -> dict:
    """
    기본 control.json 형태 반환.

    Returns:
        {"paused": False, "since": None, "by": None, "updated_at": None}
    """
    return {
        "paused": False,
        "since": None,
        "by": None,
        "updated_at": None,
    }


def is_paused(control: dict) -> bool:
    """
    control 상태가 paused 인지 판정.

    dict가 아니거나 paused 키가 없으면 False (안전 기본값).

    Args:
        control: control.json dict 또는 None/빈 dict

    Returns:
        bool: paused 상태 (기본값 False)
    """
    if not isinstance(control, dict):
        return False
    return control.get("paused", False)


def set_paused(
    control: dict,
    paused: bool,
    *,
    by: str,
    now_iso: str,
) -> dict:
    """
    paused 상태를 변경한 새로운 control dict 반환 (원본 불변).

    Args:
        control: 기존 control dict (기본값으로 빈 dict 가능)
        paused: 새로운 paused 상태
        by: 상태 변경 출처 메모 (예: "telegram:/pause")
        now_iso: 현재 시각 (ISO 'Z' format)

    Returns:
        새로운 control dict:
        - paused=True: since=now_iso
        - paused=False: since=None
        - by, updated_at는 항상 now_iso 로 갱신
    """
    # 기존 값 보존 (안전하게)
    if not isinstance(control, dict):
        control = default_control()

    # 새 dict 생성 (원본 불변)
    result = {
        "paused": paused,
        "since": now_iso if paused else None,
        "by": by,
        "updated_at": now_iso,
    }
    return result


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대비
    except Exception:
        pass

    # smoke test

    # 1. default_control
    default = default_control()
    assert default == {
        "paused": False,
        "since": None,
        "by": None,
        "updated_at": None,
    }, "default_control failed"
    print("✓ default_control")

    # 2. is_paused(default) == False
    assert is_paused(default) is False, "is_paused(default) should be False"
    print("✓ is_paused(default)==False")

    # 3. is_paused(None) == False
    assert is_paused(None) is False, "is_paused(None) should be False"
    print("✓ is_paused(None)==False")

    # 4. is_paused({}) == False
    assert is_paused({}) is False, "is_paused({}) should be False"
    print("✓ is_paused({})==False")

    # 5. set_paused round-trip: True → since 채워짐 → False → since None
    control = default_control()
    control_paused = set_paused(
        control,
        paused=True,
        by="telegram:/pause",
        now_iso="2026-08-31T12:00:00Z",
    )
    assert control_paused["paused"] is True, "should be paused"
    assert control_paused["since"] == "2026-08-31T12:00:00Z", "since should be set"
    assert control_paused["by"] == "telegram:/pause", "by should be set"
    assert control_paused["updated_at"] == "2026-08-31T12:00:00Z", "updated_at should be set"
    print("✓ set_paused(True) fills since")

    # 6. set_paused(paused=False) → since=None
    control_resumed = set_paused(
        control_paused,
        paused=False,
        by="telegram:/resume",
        now_iso="2026-08-31T12:15:00Z",
    )
    assert control_resumed["paused"] is False, "should be resumed"
    assert control_resumed["since"] is None, "since should be None when paused=False"
    assert control_resumed["by"] == "telegram:/resume", "by should be updated"
    assert control_resumed["updated_at"] == "2026-08-31T12:15:00Z", "updated_at should be updated"
    print("✓ set_paused(False) clears since")

    # 7. 원본 불변 확인
    original = default_control()
    _modified = set_paused(
        original,
        paused=True,
        by="test",
        now_iso="2026-08-31T12:00:00Z",
    )
    assert original == default_control(), "original should not be modified"
    assert original["paused"] is False, "original paused should still be False"
    print("✓ original dict is immutable")

    print("\nSUCCESS: control.py smoke test passed")
