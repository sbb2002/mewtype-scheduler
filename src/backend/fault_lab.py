"""결함 주입 시험용 격리 모듈 (docs/AUTOFIX_FAULT_INJECTION.md) — **일부러 버그가 들어 있다**.

- 러너 · 백엔드는 이 모듈을 import 하지 않는다. 자동 수정이 이 모듈을 고쳐도 서비스 동작은 달라지지 않는다.
- 아래 함수들의 `# BUG` 는 시험 대상이다. 사람이 고치지 말 것(자동 수정 파이프라인이 고쳐야 한다). 고친 뒤에는 `git reset`/태그로 되돌려 다시 시험한다.
- `python -m src.backend.fault_lab` 는 버그 때문에 **의도적으로 실패**한다(정상 상태 = 실패, 자동 수정 후 = 통과).
- 에러를 실제 경로로 만드는 트리거: `python -m src.backend.fault_lab_run <시나리오>`.
"""
from __future__ import annotations


def moving_average(values: list[float], window: int) -> list[float]:
    """이동 평균: 각 위치에서 **최근 window 개** 값의 평균. 처음 window-1 개 위치는 지금까지의 값만으로 계산한다."""
    out = []
    for i in range(len(values)):
        chunk = values[max(0, i - window):i + 1]  # BUG: off-by-one — window+1 개를 본다 (i - window + 1 부터여야 함)
        out.append(sum(chunk) / len(chunk))
    return out


def clamp(x: float, lo: float, hi: float) -> float:
    """x 를 [lo, hi] 범위로 제한한다."""
    if x < lo:
        return hi  # BUG: 경계가 반대 — lo 를 돌려줘야 함
    if x > hi:
        return lo  # BUG: 경계가 반대 — hi 를 돌려줘야 함
    return x


def format_duration(seconds: int) -> str:
    """초를 사람이 읽는 문자열로: 60초 미만은 'S초', 이상은 'M분 S초'."""
    if seconds < 60:
        return f"{seconds}초"
    m, s = divmod(seconds, 60)
    return f"{m}분 {m}초"  # BUG: 초 자리에 s 가 아니라 m 을 쓴다


def selfcheck_moving_average() -> None:
    assert moving_average([1, 2, 3, 4], 2) == [1.0, 1.5, 2.5, 3.5], f"moving_average 결과가 틀림: {moving_average([1, 2, 3, 4], 2)}"


def selfcheck_clamp() -> None:
    assert clamp(-5, 0, 10) == 0 and clamp(15, 0, 10) == 10 and clamp(5, 0, 10) == 5, f"clamp 경계 처리가 틀림: {clamp(-5, 0, 10)}, {clamp(15, 0, 10)}"


def selfcheck_format_duration() -> None:
    assert format_duration(135) == "2분 15초" and format_duration(42) == "42초", f"format_duration 결과가 틀림: {format_duration(135)!r}"


def selfcheck_all() -> None:
    """세 함수를 모두 검사한다 (한 번에 여러 결함을 고쳐야 통과 — 다중 파일/다중 결함 시나리오용)."""
    selfcheck_moving_average()
    selfcheck_clamp()
    selfcheck_format_duration()


if __name__ == "__main__":
    selfcheck_all()
    print("fault_lab: 모든 검사 통과")
