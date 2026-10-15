"""규약 적합성 검사 — docs/bus/schema/*.json 대비 봉투 검증 (jsonschema 없이 쓰는 최소 구현).

발신기 · 수신기 양쪽이 서로의 코드를 보지 않고도 같은 기준으로 자기 출력/입력을 검증하기 위한 도구.
지원 키워드: type const enum required properties items pattern maxLength minimum maximum.
(additionalProperties 는 전부 허용 — 하위 호환 규칙: 모르는 필드는 무시)

    python -m src.bus.conform            # docs/bus/examples 전체 점검 (valid 는 통과 · invalid 는 실패해야 함)
    python -m src.bus.conform FILE...    # 지정 파일 검증
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs" / "bus"
_SCHEMAS: dict[str, dict] = {}


def schema_for(name: str) -> dict:
    if not _SCHEMAS:
        for p in (DOCS / "schema").glob("*.json"):
            s = json.loads(p.read_text(encoding="utf-8"))
            _SCHEMAS[s["$id"]] = s
    return _SCHEMAS[name]


_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def _check(v, s: dict, path: str, errs: list[str]) -> None:
    if "const" in s and v != s["const"]:
        errs.append(f"{path}: const {s['const']!r} 아님 ({v!r})")
        return
    if "enum" in s and v not in s["enum"]:
        errs.append(f"{path}: {v!r} 는 {s['enum']} 중 하나여야 함")
        return
    t = s.get("type")
    if t and not _TYPES[t](v):
        errs.append(f"{path}: {t} 여야 함")
        return
    if isinstance(v, str):
        if "pattern" in s and not re.search(s["pattern"], v):
            errs.append(f"{path}: 형식 불일치 ({v[:40]!r})")
        if "maxLength" in s and len(v) > s["maxLength"]:
            errs.append(f"{path}: 길이 {len(v)} > {s['maxLength']}")
    if isinstance(v, int) and not isinstance(v, bool):
        if "minimum" in s and v < s["minimum"]:
            errs.append(f"{path}: {v} < {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            errs.append(f"{path}: {v} > {s['maximum']}")
    if isinstance(v, dict):
        for r in s.get("required", []):
            if r not in v:
                errs.append(f"{path}.{r}: 필수 필드 없음")
        for k, sub in s.get("properties", {}).items():
            if k in v:
                _check(v[k], sub, f"{path}.{k}", errs)
    if isinstance(v, list) and "items" in s:
        for i, x in enumerate(v):
            _check(x, s["items"], f"{path}[{i}]", errs)


def validate(obj: dict) -> list[str]:
    """위반 목록(빈 리스트 = 적합). 스키마는 obj['schema'] 로 고른다."""
    name = obj.get("schema") if isinstance(obj, dict) else None
    try:
        s = schema_for(name)
    except KeyError:
        return [f"$: 알 수 없는 schema {name!r}"]
    errs: list[str] = []
    _check(obj, s, "$", errs)
    return errs


def main(argv: list[str]) -> int:
    bad = 0
    if argv:
        for f in argv:
            errs = validate(json.loads(Path(f).read_text(encoding="utf-8")))
            print(("OK  " if not errs else "FAIL") + f"  {f}" + ("" if not errs else "  " + "; ".join(errs)))
            bad += bool(errs)
        return 1 if bad else 0
    ex = DOCS / "examples"
    for p in sorted(ex.glob("*.json")):
        errs = validate(json.loads(p.read_text(encoding="utf-8")))
        ok = not errs
        print(("OK  " if ok else "FAIL") + f"  valid    {p.name}" + ("" if ok else "  " + "; ".join(errs)))
        bad += not ok
    for p in sorted((ex / "invalid").glob("*.json")):
        errs = validate(json.loads(p.read_text(encoding="utf-8")))
        ok = bool(errs)
        print(("OK  " if ok else "FAIL") + f"  invalid  {p.name}" + (f"  → {errs[0]}" if ok else "  (위반이어야 하는데 통과함)"))
        bad += not ok
    print("적합성 검사", "통과" if not bad else f"실패 {bad}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
