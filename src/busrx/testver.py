"""테스트판 버전 기록 (브랜치 v4.3-fullauto 전용 — 2026-10-13 운영자 지시).

규칙: 테스트판은 `vT1.0.0` 에서 시작하고 프로젝트의 기존 규칙대로 올린다(CLAUDE.md). 자동 대응이 만든 수정은 **핫픽스 = 패치 번호(Z)** 를 올린다.
**커밋까지 간 수정만** 번호를 쓴다(폐기 · 실패한 시도는 번호를 쓰지 않는다 — 기록은 `rx/runs/` 에만). 기능(새 요소)은 마이너(Y) — 사람이 직접 올린다.
기록은 수신기가 `docs/VERSION_vT.md` 에 쓴다(수정 파이프라인 · 구현 모델이 아니라 — 가드는 `docs/` 수정을 금지한다).
최신 번호는 그 파일의 맨 위 `## vT…` 제목에서 읽는다(= 저장소가 진실 소스, 수신기 상태 파일이 아님).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

FILE = "docs/VERSION_vT.md"
MARK = "<!-- ENTRIES: 최신이 위 -->"
VER_RE = re.compile(r"^## vT(\d+)\.(\d+)\.(\d+)", re.M)
KST = dt.timezone(dt.timedelta(hours=9))


def latest(root: Path) -> tuple[int, int, int]:
    """기록 파일의 가장 위 버전. 파일이 없거나 항목이 없으면 기준선 (1, 0, 0)."""
    p = Path(root) / FILE
    try:
        m = VER_RE.search(p.read_text(encoding="utf-8"))
    except OSError:
        m = None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (1, 0, 0)


def fmt(v: tuple[int, int, int]) -> str:
    return f"vT{v[0]}.{v[1]}.{v[2]}"


def next_patch(root: Path) -> str:
    a, b, c = latest(root)
    return fmt((a, b, c + 1))


def record(root: Path, version: str, *, title: str, sig: str, cause: str, files: list, base: str, head: str, branch: str,
           preset: str, origin: str, now: dt.datetime | None = None) -> Path:
    """기록 파일 맨 위(표지 아래)에 항목 추가. files = [(+, −, path)]."""
    p = Path(root) / FILE
    text = p.read_text(encoding="utf-8")
    assert MARK in text, f"{FILE} 에 항목 표지가 없음"
    when = (now or dt.datetime.now(KST)).astimezone(KST).strftime("%Y-%m-%d %H:%M")
    adds = sum(f[0] for f in files)
    dels = sum(f[1] for f in files)
    fl = ", ".join(f"`{f[2]}` (+{f[0]} −{f[1]})" for f in files) or "(없음)"
    entry = (f"\n## {version} — {when} KST · 핫픽스 ({origin})\n\n"
             f"- **제목**: {title}\n"
             f"- **에러**: `{sig}` — {' '.join(cause.split())[:200]}\n"
             f"- **변경**: {fl} · 합계 +{adds} −{dels}\n"
             f"- **커밋**: `{base}` → `{head}` · 브랜치 `{branch}` · 파이프라인 {preset}\n")
    p.write_text(text.replace(MARK, MARK + "\n" + entry, 1), encoding="utf-8", newline="\n")
    return p


def mark_reverted(root: Path, version: str, reason: str) -> None:
    """해당 버전 항목 끝에 revert 표시를 덧붙인다(번호는 결번으로 남는다)."""
    p = Path(root) / FILE
    text = p.read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(version)} .*?(?=^## |\Z)", text, re.S | re.M)
    if not m:
        raise ValueError(f"{version} 항목을 찾지 못함")
    block = m.group(0).rstrip("\n") + f"\n- **상태**: ⚠️ {reason}\n\n"
    p.write_text(text[:m.start()] + block + text[m.end():], encoding="utf-8", newline="\n")


if __name__ == "__main__":
    import tempfile

    d = Path(tempfile.mkdtemp())
    (d / "docs").mkdir()
    (d / FILE).write_text(f"# t\n{MARK}\n\n## vT1.0.0 — 기준선\n", encoding="utf-8")
    assert latest(d) == (1, 0, 0) and next_patch(d) == "vT1.0.1"
    record(d, "vT1.0.1", title="x", sig="s", cause="원인\n두 줄", files=[(3, 1, "src/a.py")], base="aaa", head="bbb", branch="auto/s-1", preset="표준", origin="자동")
    assert latest(d) == (1, 0, 1) and next_patch(d) == "vT1.0.2"
    record(d, "vT1.0.2", title="y", sig="s2", cause="c", files=[], base="bbb", head="ccc", branch="auto/s2-2", preset="긴급", origin="반자동 승인")
    t = (d / FILE).read_text(encoding="utf-8")
    assert t.index("vT1.0.2") < t.index("vT1.0.1") < t.index("vT1.0.0") and "+3 −1" in t
    assert latest(Path(tempfile.mkdtemp())) == (1, 0, 0)
    mark_reverted(d, "vT1.0.2", "되돌림")
    t2 = (d / FILE).read_text(encoding="utf-8")
    assert "⚠️ 되돌림" in t2 and t2.index("⚠️") < t2.index("## vT1.0.1") and latest(d) == (1, 0, 2)
    print("testver self-test 통과")
