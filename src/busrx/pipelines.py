"""자동 수정 파이프라인 — 블록 카탈로그 · 파이프라인 정의 · 검증 (레고식 조립의 규칙).

파이프라인 = 블록의 순서 있는 목록. 각 블록은 {id, enabled, params}. 엔진(`autofix.py`)이 이 정의대로 실행한다.
**잠금 블록**(명세서 · 워크트리 · 구현 · 가드 · 테스트 · 커밋 · 보호 확인)은 빼거나 끌 수 없고 서로의 순서도 바꿀 수 없다 —
운영 자원 보호(가드 · 보호 대상 불변 확인)와 안전한 커밋 절차를 사용자 설정으로 약화시킬 수 없게 하기 위함이다.
조립 가능한 부분: 검증 · 독립 검토(켜기/끄기 · 서로 순서 · 모델/예산), 적용 · 재시작(켜기/끄기), 구현의 수정 라운드 수, 테스트 범위.

저장: 내장 프리셋(표준 · 긴급)은 코드에 있고, 사용자 정의는 `<버스>/rx/pipelines.json`.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

# 블록 카탈로그. phase: pre(1회) / cycle(구현→검사 반복) / post(통과 후). needs = 앞에 있어야 하는 블록
BLOCKS: dict[str, dict] = {
    "spec":      {"name": "명세서(Sonnet)", "phase": "pre", "locked": True, "needs": []},
    "worktree":  {"name": "수정 브랜치 · 워크트리", "phase": "pre", "locked": True, "needs": ["spec"]},
    "implement": {"name": "구현(Haiku)", "phase": "cycle", "locked": True, "needs": ["worktree"]},
    "guard":     {"name": "가드: 금지 자원 확인", "phase": "cycle", "locked": True, "needs": ["implement"]},
    "tests":     {"name": "문법 · self-test", "phase": "cycle", "locked": True, "needs": ["guard"]},
    "verify":    {"name": "검증(Sonnet)", "phase": "cycle", "locked": False, "needs": ["tests"]},
    "review":    {"name": "독립 검토(Sonnet)", "phase": "cycle", "locked": False, "needs": ["tests"]},
    "commit":    {"name": "로컬 브랜치 커밋", "phase": "post", "locked": True, "needs": ["tests"]},
    "protected": {"name": "보호 대상 불변 확인", "phase": "post", "locked": True, "needs": ["commit"]},
    "apply":     {"name": "러너 브랜치에 적용", "phase": "post", "locked": False, "needs": ["protected"]},
    "restart":   {"name": "러너 재시작 + 건강 확인", "phase": "post", "locked": False, "needs": ["apply"]},
}
# 잠금 블록의 고정 순서
LOCKED_ORDER = ["spec", "worktree", "implement", "guard", "tests", "commit", "protected"]
ALLOWED_MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5")

# 블록별 조절 가능한 값: (범위/허용값) — 아래 validate 가 검사
PARAM_RULES = {
    "implement": {"max_revisions": (0, 3), "model": ALLOWED_MODELS, "budget": (0.05, 5.0)},
    "spec": {"model": ALLOWED_MODELS, "budget": (0.05, 5.0)},
    "verify": {"model": ALLOWED_MODELS, "budget": (0.05, 5.0)},
    "review": {"model": ALLOWED_MODELS, "budget": (0.05, 5.0)},
    "tests": {"core": (False, True)},
}


def _blk(bid: str, enabled: bool = True, **params) -> dict:
    return {"id": bid, "enabled": enabled, "params": params}


def _standard() -> list[dict]:
    return [_blk("spec"), _blk("worktree"), _blk("implement", max_revisions=1), _blk("guard"), _blk("tests", core=True),
            _blk("verify"), _blk("review"), _blk("commit"), _blk("protected"), _blk("apply"), _blk("restart")]


def _urgent() -> list[dict]:
    b = _standard()
    for x in b:
        if x["id"] in ("verify", "review"):
            x["enabled"] = False
        if x["id"] == "tests":
            x["params"] = {"core": False}
    return b


BUILTIN: dict[str, dict] = {
    "standard": {"id": "standard", "name": "표준(충분한 검증)", "builtin": True, "blocks": _standard()},
    "urgent": {"id": "urgent", "name": "긴급(최소 검증)", "builtin": True, "blocks": _urgent()},
}


def validate(pl: dict) -> list[str]:
    """파이프라인 정의 검증. 오류 목록(빈 리스트 = 유효)."""
    errs: list[str] = []
    blocks = pl.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return ["blocks 가 비어 있음"]
    ids = []
    for b in blocks:
        if not isinstance(b, dict) or b.get("id") not in BLOCKS:
            errs.append(f"알 수 없는 블록 {b.get('id') if isinstance(b, dict) else b!r}")
            continue
        ids.append(b["id"])
        if not isinstance(b.get("enabled", True), bool):
            errs.append(f"{b['id']}: enabled 는 true/false")
        rules = PARAM_RULES.get(b["id"], {})
        for k, v in (b.get("params") or {}).items():
            if k not in rules:
                errs.append(f"{b['id']}: 알 수 없는 설정 {k!r}")
                continue
            r = rules[k]
            if k == "core":
                if not isinstance(v, bool):
                    errs.append(f"{b['id']}.core 는 true/false")
            elif k == "model":
                if v not in r:
                    errs.append(f"{b['id']}.model 은 {list(r)} 중 하나")
            elif isinstance(v, bool) or not isinstance(v, (int, float)) or not r[0] <= v <= r[1]:
                errs.append(f"{b['id']}.{k} 는 {r[0]}~{r[1]}")
    if len(set(ids)) != len(ids):
        errs.append("같은 블록을 두 번 넣을 수 없음")
    for bid in LOCKED_ORDER:  # 잠금 블록: 반드시 있고 켜져 있어야 함
        blk = next((b for b in blocks if isinstance(b, dict) and b.get("id") == bid), None)
        if blk is None:
            errs.append(f"잠금 블록 '{BLOCKS[bid]['name']}' 을(를) 뺄 수 없음")
        elif blk.get("enabled", True) is not True:
            errs.append(f"잠금 블록 '{BLOCKS[bid]['name']}' 을(를) 끌 수 없음")
    if errs:
        return errs
    pos = {bid: ids.index(bid) for bid in ids}
    locked_pos = [pos[b] for b in LOCKED_ORDER]
    if locked_pos != sorted(locked_pos):
        errs.append("잠금 블록의 순서는 바꿀 수 없음 (" + " → ".join(BLOCKS[b]["name"] for b in LOCKED_ORDER) + ")")
    # 선택 블록 위치 규칙
    for bid in ("verify", "review"):
        if bid in pos and not (pos["tests"] < pos[bid] < pos["commit"]):
            errs.append(f"{BLOCKS[bid]['name']} 은(는) '문법 · self-test' 뒤, '커밋' 앞에만 놓을 수 있음")
    for bid, after in (("apply", "protected"), ("restart", "apply")):
        if bid in pos and after not in pos:
            errs.append(f"{BLOCKS[bid]['name']} 은(는) '{BLOCKS[after]['name']}' 이(가) 있어야 함")
        elif bid in pos and pos[bid] < pos[after]:
            errs.append(f"{BLOCKS[bid]['name']} 은(는) '{BLOCKS[after]['name']}' 뒤에 놓아야 함")
    if "restart" in pos and not _enabled(blocks, "apply") and _enabled(blocks, "restart"):
        errs.append("적용을 끄면 재시작도 켤 수 없음")
    return errs


def _enabled(blocks: list[dict], bid: str) -> bool:
    return any(b.get("id") == bid and b.get("enabled", True) for b in blocks)


class Pipeline:
    """엔진이 쓰는 읽기용 뷰 — 단계 순서 · 켜짐 여부 · 설정."""

    def __init__(self, pl: dict):
        self.id, self.name = pl["id"], pl.get("name", pl["id"])
        self.blocks = [{"id": b["id"], "enabled": b.get("enabled", True), "params": dict(b.get("params") or {})} for b in pl["blocks"]]

    def enabled(self, bid: str) -> bool:
        return any(b["id"] == bid and b["enabled"] for b in self.blocks)

    def block(self, bid: str) -> dict | None:
        return next((b for b in self.blocks if b["id"] == bid), None)

    def param(self, bid: str, key: str, default=None):
        b = self.block(bid)
        return (b or {}).get("params", {}).get(key, default)

    def phase(self, phase: str) -> list[dict]:
        return [b for b in self.blocks if BLOCKS[b["id"]]["phase"] == phase]


# ── 저장소(사용자 정의) ───────────────────────────────
def _path(cfg) -> Path:
    return cfg.rx / "pipelines.json"


def load_custom(cfg) -> dict[str, dict]:
    try:
        data = json.loads(_path(cfg).read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for pid, pl in (data.get("pipelines") or {}).items():
        pl = dict(pl, id=pid)
        if pid not in BUILTIN and not validate(pl):  # 손상 · 부정 항목은 조용히 무시(내장 프리셋으로 안전하게)
            out[pid] = pl
    return out


def all_pipelines(cfg) -> dict[str, dict]:
    d = {k: copy.deepcopy(v) for k, v in BUILTIN.items()}
    d.update(load_custom(cfg))
    return d


def resolve(cfg, pid: str) -> Pipeline:
    pls = all_pipelines(cfg)
    return Pipeline(pls.get(pid) or pls["standard"])


def save_custom(cfg, pid: str, name: str, blocks: list[dict]) -> list[str]:
    """사용자 정의 파이프라인 저장. 내장 id 는 덮어쓸 수 없다. 오류 목록(빈 리스트 = 저장됨)."""
    import re
    if pid in BUILTIN or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", pid or ""):
        return ["id 는 소문자·숫자·-_ (최대 32자)이고 내장 프리셋(standard/urgent)과 달라야 함"]
    pl = {"id": pid, "name": (name or pid)[:40], "blocks": blocks}
    errs = validate(pl)
    if errs:
        return errs
    cur = load_custom(cfg)
    cur[pid] = pl
    _write(cfg, cur)
    return []


def delete_custom(cfg, pid: str) -> bool:
    cur = load_custom(cfg)
    if pid in BUILTIN or pid not in cur:
        return False
    cur.pop(pid)
    _write(cfg, cur)
    return True


def _write(cfg, pls: dict) -> None:
    p = _path(cfg)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"pipelines": pls}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def reset_custom(cfg, who: str = "dashboard") -> int:
    """사용자 정의 파이프라인을 모두 지우고 내장 프리셋(표준 · 긴급)만 남긴다. 지운 개수. (정책이 가리키던 id 는 정책 로드 때 기본 프리셋으로 대체됨)"""
    import time
    n = len(load_custom(cfg))
    _path(cfg).unlink(missing_ok=True)
    with (cfg.rx / "pipelines_history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "by": who, "reset": True, "removed": n}, ensure_ascii=False) + "\n")
    return n


def presets_view(cfg) -> dict[str, dict]:
    """정책 · 화면용 요약 {id: {name, builtin}}."""
    return {k: {"name": v["name"], "builtin": bool(v.get("builtin"))} for k, v in all_pipelines(cfg).items()}
